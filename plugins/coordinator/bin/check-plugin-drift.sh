#!/usr/bin/env bash
# bin/check-plugin-drift.sh — Read-only drift probe for registered plugin live installs.
#
# Purpose: detect when a live install has fallen behind its source — git-state drift
# (commits-behind), venv-state drift (stale editable pin / MAPPING), and SHA-sentinel
# drift (copy_install mode). Surfaces daily via /workday-start Step 1.10 Addon Health.
#
# Spec backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md §Chunk 1
# Extended by: docs/plans/2026-05-23-copy-install-drift-coverage.md §Chunk 2

set -uo pipefail

FILTER_PLUGIN=""
CHECK_CLEAN_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --help|-h)
            cat <<'EOF'
Usage: check-plugin-drift.sh [<plugin>] [--check-clean-only]
Two-leg drift probe. Exit 0=clean, 1=drift detected.
Environment: MACHINE_LOCAL_REGISTRY_DIR, HOME
EOF
            exit 0
            ;;
        --check-clean-only) CHECK_CLEAN_ONLY=1 ;;
        -*)
            echo "check-plugin-drift.sh: unknown flag: $arg" >&2
            exit 2
            ;;
        *)
            if [[ -z "$FILTER_PLUGIN" ]]; then
                FILTER_PLUGIN="$arg"
            else
                echo "check-plugin-drift.sh: unexpected argument: $arg" >&2
                exit 2
            fi
            ;;
    esac
done

if [[ -n "${MACHINE_LOCAL_REGISTRY_DIR:-}" ]]; then
    REGISTRY_DIR="$MACHINE_LOCAL_REGISTRY_DIR"
else
    REGISTRY_DIR="${HOME}/.claude/machine-local"
fi
REGISTRY_LOCAL="${REGISTRY_DIR}/registry.local.toml"
REGISTRY_TOML="${REGISTRY_DIR}/registry.toml"
CLAUDE_HOME="${HOME}/.claude"
REFRESH_LOG="${CLAUDE_HOME}/plugins/.refresh-log"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "check-plugin-drift.sh: python3 not found" >&2
    exit 2
fi

_read_all_mirrors() {
    local registry_path="$1"
    "$PYTHON" - "$registry_path" <<'PYEOF' | tr -d '\r'
import sys, pathlib
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("ERROR: tomllib/tomli not available", file=sys.stderr)
        sys.exit(2)
registry_path = pathlib.Path(sys.argv[1])
if not registry_path.exists():
    sys.exit(0)
try:
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"ERROR: failed to parse registry: {e}", file=sys.stderr)
    sys.exit(2)

# Build the mirrors dict from two sources:
# 1. Nested table form: [plugin.mirrors.<name>] entries (data["plugin"]["mirrors"])
# 2. Flat dotted-key form: "plugin.mirrors.<name>.<field>" = "..." top-level keys
#    written by `machine-local set` (which uses flat string keys, not TOML tables).
# Both forms are valid registry writes; both must be visible to the probe.
mirrors = {}
# Source 1: nested tables (coordinator-claude, project-rag style).
nested = data.get("plugin", {}).get("mirrors", {})
if isinstance(nested, dict):
    for plugin_name, entry in nested.items():
        if isinstance(entry, dict):
            mirrors[plugin_name] = dict(entry)

# Source 2: flat dotted-key form (`"plugin.mirrors.<name>.<field>" = "..."`) —
# emitted by `machine-local set` which writes flat string keys.
PREFIX = "plugin.mirrors."
for raw_key, raw_val in data.items():
    if not isinstance(raw_key, str) or not raw_key.startswith(PREFIX):
        continue
    rest = raw_key[len(PREFIX):]  # e.g. "holodeck.propagation_mode"
    parts = rest.split(".", 1)
    if len(parts) != 2:
        continue
    plugin_name, field = parts
    if plugin_name not in mirrors:
        mirrors[plugin_name] = {}
    # Only set if not already present from the nested-table form (nested wins).
    if field not in mirrors[plugin_name]:
        mirrors[plugin_name][field] = raw_val

if not mirrors:
    print("NO_MIRRORS")
    sys.exit(0)
for plugin_name, entry in mirrors.items():
    prop_mode   = entry.get("propagation_mode", "")
    source_path = entry.get("source_path", "")
    live_path   = entry.get("live_path", "")
    track_ref   = entry.get("track_ref", "origin/main")
    dist_name   = entry.get("dist_name", plugin_name.replace("-", "_"))
    print(f"{plugin_name}|{source_path}|{live_path}|{track_ref}|{dist_name}|{prop_mode}")
PYEOF
}

IS_WINDOWS=0
UNAME_S="$(uname -s 2>/dev/null || echo '')"
if [[ "$UNAME_S" == MINGW* ]] || [[ "$UNAME_S" == CYGWIN* ]] || [[ -n "${WINDIR:-}" ]]; then
    IS_WINDOWS=1
fi

TOTAL_DRIFT=0

_check_plugin() {
    local plugin_name="$1" source_path="$2" live_path="$3" track_ref="$4" dist_name="$5" prop_mode="$6"
    local plugin_drift=0

    if [[ "$prop_mode" == "source_is_live" ]]; then
        echo "[ok] $plugin_name: propagation_mode=source_is_live -- n/a by design"
        return 0
    fi

    # copy_install: self-contained early-return — no git/venv legs follow.
    # This branch does NOT consume track_ref or dist_name defaults; it exits before
    # any git-state, venv-state, or working-tree leg can be reached.
    if [[ "$prop_mode" == "copy_install" ]]; then
        # Normalise backslashes (Windows paths from registry).
        local ci_live_path="${live_path//\\//}"
        local ci_source_path="${source_path//\\//}"

        # --check-clean-only: copy_install has no live git working tree;
        # re-running the idempotent copy installer is always safe — nothing to block on.
        if [[ $CHECK_CLEAN_ONLY -eq 1 ]]; then
            return 0
        fi

        # (a) Missing live path → drift.
        if [[ -z "$ci_live_path" ]] || [[ ! -d "$ci_live_path" ]]; then
            echo "[drift] $plugin_name: copy_install — live_path missing or not a directory: '$ci_live_path'"
            return 1
        fi

        # (b) No version.txt sentinel → info (not drift; installer may not have written one yet).
        local sentinel_file="${ci_live_path}/version.txt"
        if [[ ! -f "$sentinel_file" ]]; then
            echo "[info] $plugin_name: copy_install — no version.txt sentinel (installer did not write one; see holodeck memo)"
            return 0
        fi

        # (c) Sentinel present — validate format (must be 40 hex chars).
        local sentinel_sha
        sentinel_sha="$(tr -d '\r\n' < "$sentinel_file")"
        local sentinel_len="${#sentinel_sha}"
        if [[ $sentinel_len -ne 40 ]] || ! [[ "$sentinel_sha" =~ ^[0-9a-f]+$ ]]; then
            echo "[warn] $plugin_name: version.txt malformed (len=${sentinel_len}) — refresh to rewrite sentinel"
            return 0
        fi

        # (d/e) Compare sentinel to current source HEAD (no fetch — local HEAD only).
        local source_head
        source_head="$(git -C "$ci_source_path" rev-parse HEAD 2>/dev/null | tr -d '\r')" || {
            echo "[warn] $plugin_name: copy_install — could not read source HEAD from '$ci_source_path'"
            return 0
        }

        if [[ "$sentinel_sha" == "$source_head" ]]; then
            echo "[ok] $plugin_name: copy_install — sentinel matches source HEAD (${sentinel_sha:0:12})"
        else
            echo "[drift] copy_install: $plugin_name live is at ${sentinel_sha:0:12}, source HEAD ${source_head:0:12} — run: refresh-plugin-live-install.sh $plugin_name"
            return 1
        fi
        return 0
    fi

    live_path="${live_path//\\//}"

    if [[ -z "$live_path" ]] || [[ ! -d "$live_path" ]]; then
        echo "[drift] $plugin_name: live_path missing or not a directory: '$live_path'"
        return 1
    fi

    if [[ $CHECK_CLEAN_ONLY -eq 1 ]]; then
        # copy_install entries exit early above; this git status call is only for
        # git-checkout-managed entries that have a live git working tree.
        local porcelain
        porcelain="$(git -C "$live_path" status --porcelain 2>&1 | tr -d '\r')" || { return 1; }
        if [[ -n "$porcelain" ]]; then
            echo "[drift] $plugin_name: working-tree: live checkout has uncommitted edits"
            return 1
        fi
        return 0
    fi

    # Leg 1: git-state
    git -C "$live_path" fetch -q origin 2>/dev/null || true
    local behind
    behind="$(git -C "$live_path" rev-list --count HEAD.."${track_ref}" 2>/dev/null | tr -d '\r')" || behind=""
    if [[ -n "$behind" ]] && [[ "$behind" -gt 0 ]]; then
        local src_sha
        src_sha="$(git -C "$live_path" rev-parse "${track_ref}" 2>/dev/null | head -c 12)" || src_sha="unknown"
        echo "[drift] git-state: $plugin_name is $behind commits behind $track_ref (source HEAD: ${src_sha})"
        plugin_drift=1
    fi

    local venv_dir="${live_path}/.venv"
    local site_packages=""
    if [[ $IS_WINDOWS -eq 1 ]]; then
        site_packages="${venv_dir}/Lib/site-packages"
    else
        local sp_candidate
        # Review: code-reviewer (chain-end finding #5) — python3.x was a non-functional
        # placeholder when glob returns nothing. Leave site_packages="" on miss so
        # downstream venv legs skip gracefully instead of probing a nonexistent path.
        sp_candidate="$(ls -d "${venv_dir}/lib/python"*/site-packages 2>/dev/null | head -1)"
        if [[ -n "$sp_candidate" ]] && [[ -d "$sp_candidate" ]]; then
            site_packages="$sp_candidate"
        else
            site_packages=""
        fi
    fi

    # Leg 2a: venv-pin
    if [[ -d "$venv_dir" ]]; then
        local direct_url_result
        direct_url_result="$("$PYTHON" - "$live_path" "$dist_name" "$site_packages" <<'PYEOF' | tr -d '\r'
import sys, json, pathlib
live_path = pathlib.Path(sys.argv[1])
dist_name = sys.argv[2]
site_pkg_dir = pathlib.Path(sys.argv[3])
if not site_pkg_dir.exists():
    print("NO_VENV"); sys.exit(0)
dist_info_dirs = list(site_pkg_dir.glob(f"{dist_name}-*.dist-info"))
if not dist_info_dirs:
    print("NO_DIST_INFO"); sys.exit(0)
direct_url_path = dist_info_dirs[0] / "direct_url.json"
if not direct_url_path.exists():
    print("NO_DIRECT_URL"); sys.exit(1)
try:
    direct_url = json.loads(direct_url_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"PARSE_ERROR: {e}"); sys.exit(1)
url = direct_url.get("url", "")
if url.startswith("file:///"):
    import os
    pinned_str = url[8:].replace('/', os.sep)
    if os.name == 'nt' and not pinned_str.startswith(tuple('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')):
        pinned_str = pinned_str.lstrip(os.sep)
    pinned_path = pathlib.Path(pinned_str)
else:
    pinned_path = pathlib.Path(url)
try:
    if not pinned_path.exists():
        print(f"DANGLING:{pinned_path}"); sys.exit(1)
    if pinned_path.resolve() != live_path.resolve():
        print(f"WRONG_PATH:{pinned_path}"); sys.exit(1)
    print("OK"); sys.exit(0)
except Exception as e:
    print(f"ERROR:{e}"); sys.exit(1)
PYEOF
)" || true
        case "$direct_url_result" in
            OK|NO_VENV|NO_DIST_INFO) : ;;
            NO_DIRECT_URL)
                echo "[drift] venv-pin: $plugin_name direct_url.json not found -- re-run refresh-plugin-live-install.sh"
                plugin_drift=1 ;;
            DANGLING:*)
                echo "[drift] venv-pin: $plugin_name direct_url.json dangling: ${direct_url_result#DANGLING:}"
                plugin_drift=1 ;;
            WRONG_PATH:*)
                echo "[drift] venv-pin: $plugin_name editable pin points to wrong checkout: ${direct_url_result#WRONG_PATH:}"
                plugin_drift=1 ;;
            *)
                echo "[drift] venv-pin: $plugin_name check error: $direct_url_result"
                plugin_drift=1 ;;
        esac
    fi

    # Leg 2b: venv-pyproject hash
    local pyproject_path="${live_path}/pyproject.toml"
    if [[ -f "$pyproject_path" ]]; then
        local current_hash
        current_hash="$("$PYTHON" - "$pyproject_path" <<'HASHEOF' | tr -d '\r'
import sys, hashlib, pathlib
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
HASHEOF
)" || current_hash=""
        # Review: code-reviewer (chain-end finding #2) — honor CURRENT_PYPROJECT_HASH_OVERRIDE
        # when set by refresh-plugin-live-install.sh post-flight invocation.  This allows
        # the probe to compare against the just-updated hash without requiring a pre-write
        # to the audit log (which caused a double-row on every successful refresh).
        local baseline_hash="${CURRENT_PYPROJECT_HASH_OVERRIDE:-}"
        if [[ -z "$baseline_hash" ]] && [[ -f "$REFRESH_LOG" ]]; then
            baseline_hash="$(grep " ${plugin_name} " "$REFRESH_LOG" 2>/dev/null | grep "pyproject_hash=" | tail -1 | sed 's/.*pyproject_hash=\([a-f0-9]*\).*/\1/' | tr -d '\r')" || baseline_hash=""
        fi
        if [[ -n "$current_hash" ]] && [[ -n "$baseline_hash" ]]; then
            if [[ "$current_hash" != "$baseline_hash" ]]; then
                echo "[drift] venv-pyproject: $plugin_name pyproject.toml changed since last refresh"
                plugin_drift=1
            fi
        elif [[ -n "$current_hash" ]]; then
            if [[ -f "$REFRESH_LOG" ]]; then
                echo "[info] venv-pyproject: $plugin_name no refresh baseline found"
            else
                echo "[info] venv-pyproject: $plugin_name no refresh log found"
            fi
        fi
    fi

    # Leg 2c: venv-MAPPING integrity
    if [[ -d "$site_packages" ]]; then
        local mapping_result
        mapping_result="$("$PYTHON" - "$live_path" "$site_packages" <<'PYEOF' | tr -d '\r'
import sys, pathlib, re
live_path    = pathlib.Path(sys.argv[1]).resolve()
site_pkg_dir = pathlib.Path(sys.argv[2])
if not site_pkg_dir.exists():
    print("NO_SITE_PKGS"); sys.exit(0)
finder_files = list(site_pkg_dir.glob("__editable__*_finder.py"))
if not finder_files:
    print("NO_FINDER"); sys.exit(0)
stale_paths = []
for finder in finder_files:
    try:
        src = finder.read_text(encoding="utf-8")
        m = re.search(r'MAPPING\s*=\s*(\{[^}]*\})', src, re.DOTALL)
        if not m:
            # Review: code-reviewer (chain-end finding #12) — on eval failure, skip the
            # MAPPING check entirely and emit NO_FINDER rather than running a global
            # regex that can match 'str':'str' pairs in comments or docstrings.
            print("NO_FINDER"); sys.exit(0)
        try:
            mapping_dict = eval(m.group(1))
        except Exception:
            # Eval failed — skip rather than falling back to unscoped regex.
            print("NO_FINDER"); sys.exit(0)
        if not isinstance(mapping_dict, dict):
            continue
        for path_str in mapping_dict.values():
            c = pathlib.Path(str(path_str))
            if not c.exists():
                stale_paths.append(str(c))
                continue
            try: c.resolve().relative_to(live_path)
            except ValueError: stale_paths.append(str(c))
    except Exception:
        pass
if stale_paths:
    print("STALE:" + "|".join(stale_paths[:3]))
else:
    print("OK")
PYEOF
)" || mapping_result="ERROR"
        case "$mapping_result" in
            OK|NO_SITE_PKGS|NO_FINDER) : ;;
            STALE:*)
                echo "[drift] venv-mapping: $plugin_name editable MAPPING has stale paths"
                plugin_drift=1 ;;
            *) : ;;
        esac
    fi

    # Leg 2d: venv-shims
    if [[ -f "$pyproject_path" ]]; then
        local shim_result
        shim_result="$("$PYTHON" - "$live_path" "$IS_WINDOWS" <<'PYEOF' | tr -d '\r'
import sys, pathlib
live_path = pathlib.Path(sys.argv[1])
is_windows = sys.argv[2] == "1"
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)
pyproject = live_path / "pyproject.toml"
if not pyproject.exists(): sys.exit(0)
try:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
except Exception: sys.exit(0)
scripts = data.get("project", {}).get("scripts", {})
if not scripts: sys.exit(0)
venv = live_path / ".venv"
missing = []
for ep_name in scripts:
    if is_windows:
        shim = venv / "Scripts" / f"{ep_name}.exe"
        shim_ne = venv / "Scripts" / ep_name
    else:
        shim = venv / "bin" / ep_name
        shim_ne = shim
    if not shim.exists() and not shim_ne.exists():
        missing.append(ep_name)
if missing:
    print("MISSING:" + "|".join(missing))
    sys.exit(1)
sys.exit(0)
PYEOF
)" || true
        case "$shim_result" in
            MISSING:*)
                local missing_names="${shim_result#MISSING:}"
                IFS='|' read -ra MISSING_ARRAY <<< "$missing_names"
                for shim_name in "${MISSING_ARRAY[@]}"; do
                    echo "[drift] venv-shim: $plugin_name entry-point shim missing for '$shim_name'"
                    plugin_drift=1
                done ;;
            *) : ;;
        esac
    fi

    # Leg 3: working-tree cleanliness
    local porcelain
    porcelain="$(git -C "$live_path" status --porcelain 2>&1 | tr -d '\r')" || porcelain=""
    if [[ -n "$porcelain" ]]; then
        echo "[drift] working-tree: $plugin_name live checkout has uncommitted edits -- refresh blocked"
        plugin_drift=1
    fi

    return $plugin_drift
}

# Main
REGISTRY_FILE=""
if [[ -f "$REGISTRY_LOCAL" ]]; then
    REGISTRY_FILE="$REGISTRY_LOCAL"
elif [[ -f "$REGISTRY_TOML" ]]; then
    REGISTRY_FILE="$REGISTRY_TOML"
fi

if [[ -z "$REGISTRY_FILE" ]]; then
    echo "check-plugin-drift.sh: no plugin.mirrors registry found -- skip (no plugin.mirrors registered)"
    exit 0
fi

MIRRORS_OUTPUT="$(_read_all_mirrors "$REGISTRY_FILE")" || {
    echo "check-plugin-drift.sh: failed to read registry" >&2
    exit 2
}

if [[ "$MIRRORS_OUTPUT" == "NO_MIRRORS" ]] || [[ -z "$MIRRORS_OUTPUT" ]]; then
    echo "check-plugin-drift.sh: no plugin.mirrors registered -- nothing to check"
    exit 0
fi

while IFS='|' read -r plugin_name source_path live_path track_ref dist_name prop_mode; do
    [[ -z "$plugin_name" ]] && continue
    if [[ -n "$FILTER_PLUGIN" ]] && [[ "$plugin_name" != "$FILTER_PLUGIN" ]]; then
        continue
    fi
    if ! _check_plugin "$plugin_name" "$source_path" "$live_path" "$track_ref" "$dist_name" "$prop_mode"; then
        TOTAL_DRIFT=1
    fi
done <<< "$MIRRORS_OUTPUT"

exit $TOTAL_DRIFT
