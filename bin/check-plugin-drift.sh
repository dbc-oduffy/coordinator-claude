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

# Resolve machine-local dir through the settings-home seam (C1).
# MACHINE_LOCAL_REGISTRY_DIR is rung-1 (direct override, bypasses home resolution);
# otherwise resolve via _coordinator_settings_home() from settings-home.sh.
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C2b
# shellcheck source=../lib/settings-home.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/settings-home.sh"

if [[ -n "${MACHINE_LOCAL_REGISTRY_DIR:-}" ]]; then
    REGISTRY_DIR="$MACHINE_LOCAL_REGISTRY_DIR"
else
    REGISTRY_DIR="$(_coordinator_settings_home)/machine-local"
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

# _read_all_mirrors is defined in the shared parser lib/read-mirrors.sh
# (extracted 2026-05-28 so list-reverse-drift-cmds.sh can reuse the same
# nested-and-flat-key TOML parsing). $PYTHON is exported above; the lib reads it.
# Spec backlink: docs/plans/2026-05-28-reverse-drift-gate-meta-repo-coverage.md §Chunk 3a
export PYTHON

# SCRIPT_DIR is needed to reference ../lib/spawn-hidden.sh (console-flash suppressor).
# Note: spawn-hidden.sh lives in the coordinator-level lib/, one level up from bin/ —
# NOT bin/lib/ (which holds read-mirrors.sh et al.). The ../ is load-bearing.
# Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/read-mirrors.sh
source "$SCRIPT_DIR/lib/read-mirrors.sh"

IS_WINDOWS=0
UNAME_S="$(uname -s 2>/dev/null || echo '')"
if [[ "$UNAME_S" == MINGW* ]] || [[ "$UNAME_S" == CYGWIN* ]] || [[ -n "${WINDIR:-}" ]]; then
    IS_WINDOWS=1
fi

TOTAL_DRIFT=0

# Returns the physical git work-tree root of $1 IFF $1 is itself that root
# (not a data-only dir nested in a parent repo, not a submodule). Empty otherwise.
# Canon via cd && pwd -P (realpath is GNU-only, DR-148).
_git_worktree_root_if_self() {
    local dir="$1" canon top
    canon="$( (cd "$dir" 2>/dev/null && pwd -P) || true )"
    [[ -z "$canon" ]] && return 0
    top="$( (cd "$dir" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null) | tr -d '\r' )"
    [[ -z "$top" ]] && return 0
    top="$( (cd "$top" 2>/dev/null && pwd -P) || true )"
    # empty → not a git root; caller skips; non-empty → $1 IS its own work-tree root.
    [[ "$top" == "$canon" ]] && printf '%s\n' "$canon"
}

_check_plugin() {
    local plugin_name="$1" source_path="$2" live_path="$3" track_ref="$4" dist_name="$5" prop_mode="$6" source_subpath="$7"
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
            echo "[info] $plugin_name: copy_install — no version.txt sentinel (installer did not write one; see example-game-repo memo)"
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
            return 0
        fi

        # Sentinel lags source HEAD — run content-equivalence fallback (blob-SHA mechanism).
        # Fires when content arrived via git pull from a peer that ran install on a later HEAD.
        # [ok-via-git-propagation] exit-0 follows the [warn]/[info] exit-0 precedent in
        # docs/wiki/live-install-drift-audit.md (non-blocking informational states exit 0).
        # Spec backlink: docs/plans/2026-05-28-forward-drift-probe-content-equivalence.md §Chunk1

        # Resolve source_subpath: default "plugin/<plugin_name>" when absent.
        local resolved_subpath="${source_subpath:-plugin/${plugin_name}}"
        local full_source_subpath="${ci_source_path}/${resolved_subpath}"

        if [[ ! -d "$full_source_subpath" ]]; then
            echo "[warn] $plugin_name: copy_install — sentinel mismatch and source_subpath '${resolved_subpath}' not found; cannot run content-equivalence check"
            return 0
        fi

        # Enumerate source tracked files + blob SHAs; compare against live tree.
        # Iterates the SOURCE tracked set — untracked live artifacts (__pycache__, *.pyc)
        # are never enumerated. Per-machine files (version.txt, .content-sentinel) are
        # git-IGNORED in the live repo, so git ls-tree on SOURCE never lists them — no
        # exclusion list needed.
        # Do NOT mutate version.txt; sentinel is advanced only by the install script.
        # Cites: docs/wiki/plugin-identity-and-health-sentinels.md § scanner-is-reader-never-writer
        # Review: code-reviewer (F3) — ls_tree_err pre-init was dead; use $ls_tree_out directly in warn.
        local ls_tree_out
        ls_tree_out="$(git -C "$ci_source_path" ls-tree -r HEAD -- "$resolved_subpath" 2>&1)" || {
            echo "[warn] $plugin_name: copy_install — could not enumerate source tracked files (git ls-tree failed): ${ls_tree_out}"
            return 0
        }

        if [[ -z "$ls_tree_out" ]]; then
            echo "[warn] $plugin_name: copy_install — git ls-tree returned empty for source_subpath '${resolved_subpath}'; cannot run content-equivalence check"
            return 0
        fi

        local mismatched_paths=()
        while IFS= read -r ls_line; do
            [[ -z "$ls_line" ]] && continue
            # ls-tree output: "<mode> <type> <sha>\t<path>"
            # Review: code-reviewer (F1) — extract path with TAB delimiter; whitespace-split
            # truncates paths containing spaces. blob_sha extraction stays on $3 (no spaces).
            # Review: code-reviewer (F2) — skip non-blob entries (e.g. submodule 'commit' type)
            # to avoid false drift from git hash-object on submodule entries.
            local blob_sha entry_type tracked_path
            entry_type="$(printf '%s' "$ls_line" | awk '{print $2}')"
            [[ "$entry_type" != "blob" ]] && continue
            blob_sha="$(printf '%s' "$ls_line" | awk '{print $3}')"
            tracked_path="$(printf '%s' "$ls_line" | awk -F'\t' '{print $2}')"
            [[ -z "$tracked_path" ]] && continue

            # Path relative to source_subpath (strip the subpath prefix).
            local rel_path="${tracked_path#${resolved_subpath}/}"
            local live_file="${ci_live_path}/${rel_path}"

            if [[ ! -f "$live_file" ]]; then
                mismatched_paths+=("$tracked_path (missing in live)")
                continue
            fi

            # Compute live file's blob SHA via git hash-object in the live repo context
            # (applies the live repo's clean filter incl. autocrlf — apples-to-apples).
            local live_sha
            live_sha="$(git -C "$CLAUDE_HOME" hash-object "$live_file" 2>/dev/null | tr -d '\r')" || {
                mismatched_paths+=("$tracked_path (hash-object failed)")
                continue
            }

            if [[ "$blob_sha" != "$live_sha" ]]; then
                mismatched_paths+=("$tracked_path")
            fi
        # Review: code-reviewer (F15) — here-string feeds ls-tree output line by line;
        # safe for paths with spaces because IFS= read -r and TAB-split extraction handle them.
        done <<< "$ls_tree_out"

        if [[ ${#mismatched_paths[@]} -eq 0 ]]; then
            # Content equivalent — live received content via git pull; sentinel will
            # advance on next local install run.
            echo "[ok-via-git-propagation] $plugin_name: copy_install — live content matches source HEAD (${source_head:0:12}); sentinel at ${sentinel_sha:0:12} (lagging — will refresh on next install)"
            return 0
        else
            # Genuine drift — sentinel lags AND content differs.
            local count=${#mismatched_paths[@]}
            echo "[drift] copy_install: $plugin_name — sentinel ${sentinel_sha:0:12} ≠ source HEAD ${source_head:0:12} AND content differs:"
            local shown=0
            for mp in "${mismatched_paths[@]}"; do
                if [[ $shown -ge 10 ]]; then
                    local remaining=$(( count - shown ))
                    echo "  … + ${remaining} more"
                    break
                fi
                echo "  ${mp}"
                # Review: code-reviewer (F4) — POSIX-safe arithmetic; (( shown++ )) exits 1 when result is 0.
                shown=$(( shown + 1 ))
            done
            return 1
        fi
    fi

    # editable_sibling_venv: self-contained early-return — no default git/venv/working-tree
    # legs follow. This mode decouples the two legs: git-state runs on source_path (the
    # addon's own git repo); venv-state runs on live_path/.venv (the HOST plugin's venv
    # that holds the editable install). live_path IS the host plugin's (frequently dirty)
    # dev tree — allowing the unconditional working-tree cleanliness leg at L475-481 to
    # run would false-positive [drift] working-tree on every dev invocation (the Staff Engineer P1-3).
    # Spec backlink: docs/plans/2026-05-30-editable-sibling-venv-propagation-mode.md §Chunk 2
    if [[ "$prop_mode" == "editable_sibling_venv" ]]; then
        local esv_live_path="${live_path//\\//}"
        local esv_source_path="${source_path//\\//}"
        local esv_drift=0

        # --check-clean-only: the host plugin's working-tree cleanliness is the host's
        # concern, not the addon's. The venv-only addon has no own working tree to gate on.
        if [[ $CHECK_CLEAN_ONLY -eq 1 ]]; then
            return 0
        fi

        if [[ -z "$esv_live_path" ]] || [[ ! -d "$esv_live_path" ]]; then
            echo "[drift] $plugin_name (editable_sibling_venv): live_path (host venv dir) missing or not a directory: '$esv_live_path'"
            return 1
        fi

        # git-state leg: run on source_path (the addon's own git repo), NOT live_path.
        # When track_ref == "live" (explicit sentinel), the addon source is a live working
        # tree — do NOT fetch/checkout. This prevents clobbering in-flight dev-branch work.
        # Decision 2: track_ref="live" is the only safe dev posture; omitting track_ref
        # defaults to "origin/main" (parser default) and would clobber the working tree.
        if [[ "$track_ref" == "live" ]]; then
            echo "[info] $plugin_name (editable_sibling_venv): git-state: live (track_ref=live sentinel) — skipped"
        else
            if [[ -z "$esv_source_path" ]] || [[ ! -d "$esv_source_path" ]]; then
                echo "[drift] $plugin_name (editable_sibling_venv): source_path (addon git repo) missing or not a directory: '$esv_source_path'"
                esv_drift=1
            else
                git -C "$esv_source_path" fetch -q origin 2>/dev/null || true
                local esv_behind
                esv_behind="$(git -C "$esv_source_path" rev-list --count HEAD.."${track_ref}" 2>/dev/null | tr -d '\r')" || esv_behind=""
                if [[ -n "$esv_behind" ]] && [[ "$esv_behind" -gt 0 ]]; then
                    local esv_src_sha
                    esv_src_sha="$(git -C "$esv_source_path" rev-parse "${track_ref}" 2>/dev/null | head -c 12)" || esv_src_sha="unknown"
                    echo "[drift] git-state: $plugin_name (editable_sibling_venv) is $esv_behind commits behind $track_ref (source HEAD: ${esv_src_sha})"
                    esv_drift=1
                fi
            fi
        fi

        # venv-state legs: dist-info location is live_path/.venv (the host venv), but the
        # expected pin-resolution root is source_path (the addon's own repo). The python
        # helpers below accept an expected_pin_root as argv[4] (legs 2a) / argv[1] for
        # the per-leg scripts (see parameterized calls below). Default-mode callers pass
        # live_path as expected_pin_root, preserving existing behaviour.
        local esv_venv_dir="${esv_live_path}/.venv"
        local esv_site_packages=""
        if [[ $IS_WINDOWS -eq 1 ]]; then
            esv_site_packages="${esv_venv_dir}/Lib/site-packages"
        else
            local esv_sp_candidate
            esv_sp_candidate="$(ls -d "${esv_venv_dir}/lib/python"*/site-packages 2>/dev/null | head -1)"
            if [[ -n "$esv_sp_candidate" ]] && [[ -d "$esv_sp_candidate" ]]; then
                esv_site_packages="$esv_sp_candidate"
            else
                esv_site_packages=""
            fi
        fi

        # Review: code-reviewer F5 — when site-packages discovery fails on a non-Windows
        # venv (no python*/site-packages dir found), legs 2c/2a would silently skip even
        # though the venv directory exists and is broken. Surface as drift instead.
        if [[ -z "$esv_site_packages" ]] && [[ -d "$esv_venv_dir" ]]; then
            echo "[drift] $plugin_name (editable_sibling_venv): venv-state: site-packages dir not found under $esv_venv_dir"
            esv_drift=1
        fi

        # Leg 2a (venv-pin): check editable pin resolves to source_path, NOT live_path.
        # argv[1]=live_path (venv host, for dist-info glob), argv[2]=dist_name,
        # argv[3]=site_packages, argv[4]=expected_pin_root (source_path in this mode).
        if [[ -d "$esv_venv_dir" ]]; then
            local esv_direct_url_result
            esv_direct_url_result="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$esv_live_path" "$dist_name" "$esv_site_packages" "$esv_source_path" <<'PYEOF' | tr -d '\r'
import sys, json, pathlib
live_path = pathlib.Path(sys.argv[1])
dist_name = sys.argv[2]
site_pkg_dir = pathlib.Path(sys.argv[3])
# argv[4] = expected pin-resolution root (source_path in editable_sibling_venv mode;
# defaults to live_path in default mode callers that pass only 3 args).
expected_pin_root = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 else live_path
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
    import os, urllib.parse
    # urlparse yields the absolute path: '/abs/path' on POSIX, '/C:/path' on Windows.
    # The old url[8:] slice consumed the path-initial '/' (file:// + /abs-path), producing
    # a broken *relative* path on POSIX (e.g. 'private/var/...'); unquote also handles
    # %-encoded chars (spaces). pathlib.Path accepts '/' separators on every platform.
    pinned_str = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    if os.name == 'nt' and len(pinned_str) > 2 and pinned_str[0] == '/' and pinned_str[2] == ':':
        pinned_str = pinned_str[1:]   # strip leading '/' before the Windows drive letter
    pinned_path = pathlib.Path(pinned_str)
else:
    pinned_path = pathlib.Path(url)
try:
    if not pinned_path.exists():
        print(f"DANGLING:{pinned_path}"); sys.exit(1)
    if pinned_path.resolve() != expected_pin_root.resolve():
        print(f"WRONG_PATH:{pinned_path}"); sys.exit(1)
    print("OK"); sys.exit(0)
except Exception as e:
    print(f"ERROR:{e}"); sys.exit(1)
PYEOF
)" || true
            case "$esv_direct_url_result" in
                OK|NO_VENV) : ;;
                # Review: code-reviewer F3 — NO_DIST_INFO means the addon is not installed
                # in the host venv at all; that IS drift, not a silent-OK state.
                NO_DIST_INFO)
                    echo "[drift] venv-pin: $plugin_name (editable_sibling_venv) not installed in host venv — run refresh-plugin-live-install.sh"
                    esv_drift=1 ;;
                NO_DIRECT_URL)
                    echo "[drift] venv-pin: $plugin_name (editable_sibling_venv) direct_url.json not found -- re-run refresh-plugin-live-install.sh"
                    esv_drift=1 ;;
                DANGLING:*)
                    echo "[drift] venv-pin: $plugin_name (editable_sibling_venv) direct_url.json dangling: ${esv_direct_url_result#DANGLING:}"
                    esv_drift=1 ;;
                WRONG_PATH:*)
                    echo "[drift] venv-pin: $plugin_name (editable_sibling_venv) editable pin points to wrong checkout: ${esv_direct_url_result#WRONG_PATH:}"
                    esv_drift=1 ;;
                # Review: code-reviewer F4 — wildcard catches PARSE_ERROR:<msg> and ERROR:<msg>
                # from Python (json parse failure, unexpected exception); both are drift signals.
                *)
                    echo "[drift] venv-pin: $plugin_name (editable_sibling_venv) check error: $esv_direct_url_result"
                    esv_drift=1 ;;
            esac
        fi

        # Leg 2b (venv-pyproject hash): reads source_path/pyproject.toml, NOT live_path/pyproject.toml.
        # live_path is the host plugin tree — its pyproject.toml is a different package.
        local esv_pyproject_path="${esv_source_path}/pyproject.toml"
        if [[ -f "$esv_pyproject_path" ]]; then
            local esv_current_hash
            esv_current_hash="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$esv_pyproject_path" <<'HASHEOF' | tr -d '\r'
import sys, hashlib, pathlib
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
HASHEOF
)" || esv_current_hash=""
            # Review: code-reviewer F7 — Set by refresh-plugin-live-install.sh post-flight call
            # to compare against a freshly-computed hash rather than the stale log entry.
            local esv_baseline_hash="${CURRENT_PYPROJECT_HASH_OVERRIDE:-}"
            if [[ -z "$esv_baseline_hash" ]] && [[ -f "$REFRESH_LOG" ]]; then
                esv_baseline_hash="$(grep " ${plugin_name} " "$REFRESH_LOG" 2>/dev/null | grep "pyproject_hash=" | tail -1 | sed 's/.*pyproject_hash=\([a-f0-9]*\).*/\1/' | tr -d '\r')" || esv_baseline_hash=""
            fi
            if [[ -n "$esv_current_hash" ]] && [[ -n "$esv_baseline_hash" ]]; then
                if [[ "$esv_current_hash" != "$esv_baseline_hash" ]]; then
                    echo "[drift] venv-pyproject: $plugin_name (editable_sibling_venv) pyproject.toml changed since last refresh"
                    esv_drift=1
                fi
            elif [[ -n "$esv_current_hash" ]]; then
                if [[ -f "$REFRESH_LOG" ]]; then
                    echo "[info] venv-pyproject: $plugin_name (editable_sibling_venv) no refresh baseline found"
                else
                    echo "[info] venv-pyproject: $plugin_name (editable_sibling_venv) no refresh log found"
                fi
            fi
        fi

        # Leg 2c (venv-MAPPING): MAPPING paths must resolve relative to source_path, NOT live_path.
        # argv[1]=live_path (for dist-info host), argv[2]=site_packages, argv[3]=expected_pin_root (source_path).
        if [[ -d "$esv_site_packages" ]]; then
            local esv_mapping_result
            esv_mapping_result="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$esv_live_path" "$esv_site_packages" "$esv_source_path" <<'PYEOF' | tr -d '\r'
import sys, pathlib, re
live_path    = pathlib.Path(sys.argv[1]).resolve()
site_pkg_dir = pathlib.Path(sys.argv[2])
# argv[3] = expected pin-resolution root; MAPPING paths must resolve relative to it.
expected_root = pathlib.Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else live_path
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
            print("NO_FINDER"); sys.exit(0)
        try:
            mapping_dict = eval(m.group(1))
        except Exception:
            print("NO_FINDER"); sys.exit(0)
        if not isinstance(mapping_dict, dict):
            continue
        for path_str in mapping_dict.values():
            c = pathlib.Path(str(path_str))
            if not c.exists():
                stale_paths.append(str(c))
                continue
            try: c.resolve().relative_to(expected_root)
            except ValueError: stale_paths.append(str(c))
    except Exception:
        pass
if stale_paths:
    print("STALE:" + "|".join(stale_paths[:3]))
else:
    print("OK")
PYEOF
)" || esv_mapping_result="ERROR"
            case "$esv_mapping_result" in
                OK|NO_SITE_PKGS|NO_FINDER) : ;;
                STALE:*)
                    echo "[drift] venv-mapping: $plugin_name (editable_sibling_venv) editable MAPPING has stale paths"
                    esv_drift=1 ;;
                *) : ;;
            esac
        fi

        # Leg 2d (venv-shims): reads source_path/pyproject.toml (addon's own scripts),
        # NOT live_path/pyproject.toml (the host plugin's scripts — a different package).
        # Shims themselves live in live_path/.venv/{Scripts,bin}/ (the host venv).
        if [[ -f "$esv_pyproject_path" ]]; then
            local esv_shim_result
            esv_shim_result="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$esv_source_path" "$IS_WINDOWS" "$esv_live_path" <<'PYEOF' | tr -d '\r'
import sys, pathlib
source_path = pathlib.Path(sys.argv[1])
is_windows = sys.argv[2] == "1"
live_path = pathlib.Path(sys.argv[3])
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)
pyproject = source_path / "pyproject.toml"
if not pyproject.exists(): sys.exit(0)
try:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
except Exception: sys.exit(0)
scripts = data.get("project", {}).get("scripts", {})
if not scripts: sys.exit(0)
# Shims live in the HOST venv, not the addon's own venv.
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
            case "$esv_shim_result" in
                MISSING:*)
                    local esv_missing_names="${esv_shim_result#MISSING:}"
                    IFS='|' read -ra ESV_MISSING_ARRAY <<< "$esv_missing_names"
                    for esv_shim_name in "${ESV_MISSING_ARRAY[@]}"; do
                        echo "[drift] venv-shim: $plugin_name (editable_sibling_venv) entry-point shim missing for '$esv_shim_name'"
                        esv_drift=1
                    done ;;
                *) : ;;
            esac
        fi

        if [[ $esv_drift -eq 0 ]]; then
            echo "[ok] $plugin_name (editable_sibling_venv): all legs clean"
        fi
        return $esv_drift
    fi

    live_path="${live_path//\\//}"

    if [[ -z "$live_path" ]] || [[ ! -d "$live_path" ]]; then
        echo "[drift] $plugin_name: live_path missing or not a directory: '$live_path'"
        return 1
    fi

    if [[ $CHECK_CLEAN_ONLY -eq 1 ]]; then
        # Guard: only run git status when live_path is its own work-tree root.
        # A data-only nested dir (e.g. project-rag) has no .git; the helper returns
        # empty → skip → treat as clean (same semantics as Leg 3 silent-skip).
        local _cco_wtr
        _cco_wtr="$(_git_worktree_root_if_self "$live_path")"
        if [[ -z "$_cco_wtr" ]]; then
            # Emit an [info] diagnostic when the dir IS a git path but not its own root
            # (nested dir or submodule) so the caller can distinguish "not a git dir at
            # all" from "git path skipped — Leg 3 / --check-clean-only not applicable".
            if git -C "$live_path" rev-parse --git-dir >/dev/null 2>&1; then
                echo "[info] $plugin_name: --check-clean-only skipped — live_path is not its own work-tree root (nested dir or submodule)" >&2
            fi
            return 0
        fi
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
    # argv[1]=live_path (venv host + dist-info location), argv[2]=dist_name,
    # argv[3]=site_packages, argv[4]=expected_pin_root (defaults to live_path when absent —
    # preserves all existing default-mode callers that pass only 3 args).
    if [[ -d "$venv_dir" ]]; then
        local direct_url_result
        direct_url_result="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$live_path" "$dist_name" "$site_packages" <<'PYEOF' | tr -d '\r'
import sys, json, pathlib
live_path = pathlib.Path(sys.argv[1])
dist_name = sys.argv[2]
site_pkg_dir = pathlib.Path(sys.argv[3])
# argv[4] = expected pin-resolution root; defaults to live_path when absent (default mode).
expected_pin_root = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 else live_path
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
    import os, urllib.parse
    # urlparse yields the absolute path: '/abs/path' on POSIX, '/C:/path' on Windows.
    # The old url[8:] slice consumed the path-initial '/' (file:// + /abs-path), producing
    # a broken *relative* path on POSIX (e.g. 'private/var/...'); unquote also handles
    # %-encoded chars (spaces). pathlib.Path accepts '/' separators on every platform.
    pinned_str = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    if os.name == 'nt' and len(pinned_str) > 2 and pinned_str[0] == '/' and pinned_str[2] == ':':
        pinned_str = pinned_str[1:]   # strip leading '/' before the Windows drive letter
    pinned_path = pathlib.Path(pinned_str)
else:
    pinned_path = pathlib.Path(url)
try:
    if not pinned_path.exists():
        print(f"DANGLING:{pinned_path}"); sys.exit(1)
    if pinned_path.resolve() != expected_pin_root.resolve():
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
        current_hash="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$pyproject_path" <<'HASHEOF' | tr -d '\r'
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
        mapping_result="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$live_path" "$site_packages" <<'PYEOF' | tr -d '\r'
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
        shim_result="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$live_path" "$IS_WINDOWS" <<'PYEOF' | tr -d '\r'
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

    # Leg 3: working-tree cleanliness.
    # Only run when live_path is the ROOT of its own git work-tree. A data-only
    # live install (e.g. project-rag's ~/.claude/plugins/project-rag, no nested
    # .git) lets `git -C "$live_path" status` escape UPWARD to the enclosing repo
    # and report the parent's transient dirty tree as this plugin's — a perpetual
    # false "refresh blocked". _git_worktree_root_if_self encapsulates the guard:
    # empty → skip; non-empty → live_path IS its own root. Canon via cd&&pwd -P
    # (realpath is GNU-only; DR-148). Non-canonical fallbacks removed (Finding 2/3).
    local leg3_wtr
    leg3_wtr="$(_git_worktree_root_if_self "$live_path")"
    if [[ -n "$leg3_wtr" ]]; then
        local porcelain
        # Fail-loud on git-status failure (corrupt repo, missing index) rather than
        # silently treating the error as clean (Finding 7).
        if ! porcelain="$(git -C "$live_path" status --porcelain 2>&1 | tr -d '\r')"; then
            echo "[warn] $plugin_name: working-tree cleanliness unknown — git status failed" >&2
            plugin_drift=1
        elif [[ -n "$porcelain" ]]; then
            echo "[drift] working-tree: $plugin_name live checkout has uncommitted edits -- refresh blocked"
            plugin_drift=1
        fi
    else
        # live_path is not its own work-tree root — emit an [info] diagnostic when it
        # IS a git path (nested dir or submodule) so the caller can distinguish that
        # case from a non-git data-only dir (the intended silent-skip, e.g. project-rag).
        if git -C "$live_path" rev-parse --git-dir >/dev/null 2>&1; then
            echo "[info] $plugin_name: Leg 3 skipped — live_path is not its own work-tree root (nested dir or submodule); working-tree cleanliness not checked" >&2
        fi
    fi

    return $plugin_drift
}

# Lib-only sourcing escape hatch for unit tests: `CHECK_PLUGIN_DRIFT_LIB_ONLY=1
# source check-plugin-drift.sh` loads the helper functions (_git_worktree_root_if_self,
# _check_plugin) WITHOUT running the registry scan below. Inert on normal execution
# (BASH_SOURCE == $0), so the production invocation path is unchanged.
# Tested by: check-plugin-drift.test.sh
if [[ "${BASH_SOURCE[0]}" != "${0}" ]] && [[ "${CHECK_PLUGIN_DRIFT_LIB_ONLY:-}" == "1" ]]; then
    return 0 2>/dev/null || true
fi

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

# reverse_drift_cmd (7th field) is consumed by list-reverse-drift-cmds.sh, not here;
# read it into a throwaway var so it does not get appended onto prop_mode.
# source_subpath is NOT in the wire-format (lib/read-mirrors.sh owns that and cannot be
# changed without affecting list-reverse-drift-cmds.sh); we look it up inline from the
# registry for copy_install plugins only.  Default: plugin/<plugin_name>.
# Spec backlink: docs/plans/2026-05-28-forward-drift-probe-content-equivalence.md §Chunk1 wire-format
_lookup_all_source_subpaths() {
    # Batch lookup: takes all copy_install plugin names (space-separated in $1) and the
    # registry path ($2); returns "plugin_name=source_subpath" pairs (one per line) via
    # stdout. A single Python invocation replaces the former per-plugin loop spawn,
    # eliminating the N-subprocess cascade on Windows (console flash + latency).
    #
    # Routed through ../lib/spawn-hidden.sh --stdin-mode safe: the heredoc provides stdin;
    # stdin is caller-controlled → pythonw.exe suppression is safe here.
    # Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 2
    local plugin_names_str="$1" reg_file="$2"
    "$SCRIPT_DIR/../lib/spawn-hidden.sh" --stdin-mode=safe "${PYTHON:-python3}" - "$plugin_names_str" "$reg_file" <<'PYEOF' 2>/dev/null | tr -d '\r'
import sys, pathlib
plugin_names_str = sys.argv[1]
registry_path = pathlib.Path(sys.argv[2])
# Review: code-reviewer (F5) — split on newlines (not whitespace) to support plugin
#   names that contain spaces without fragility.
plugin_names = [n for n in plugin_names_str.split('\n') if n.strip()] if plugin_names_str.strip() else []
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        # Review: code-reviewer (F5) — intentional degradation: no TOML parser available →
        # exit 0 (empty stdout) → callers default to plugin/<plugin_name>. Not a hard error.
        sys.exit(0)
if not registry_path.exists():
    sys.exit(0)
try:
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)
for plugin_name in plugin_names:
    # Try nested table form first.
    val = data.get("plugin", {}).get("mirrors", {}).get(plugin_name, {}).get("source_subpath", None)
    if val is None:
        # Review: code-reviewer (F12) — handles the literal-string-key form written by
        # `machine-local set`, e.g.: "plugin.mirrors.foo.source_subpath" = "some/path"
        # as a top-level quoted key (not parsed as nested tables by tomllib).
        flat_key = f"plugin.mirrors.{plugin_name}.source_subpath"
        val = data.get(flat_key, None)
    if val is not None:
        print(f"{plugin_name}={val}")
PYEOF
}

# Pre-pass: collect all copy_install plugin names (respecting FILTER_PLUGIN) and run a
# single batch Python lookup for source_subpath values. This replaces the former
# per-plugin spawn inside the loop, eliminating the N-window flash cascade on Windows.
# Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 2
# bash 3.2 (macOS stock /bin/bash) has no associative arrays. This runs daily via
# /workday-start Step 1.10, so it cannot fail-loud-and-exit on old bash the way the
# user-facing installers do — store "key<TAB>val" lines and look up by exact key.
_SOURCE_SUBPATH_LINES=""
_lookup_source_subpath() {
    local _want="$1" _k _v
    while IFS=$'\t' read -r _k _v; do
        [[ "$_k" == "$_want" ]] && { printf '%s' "$_v"; return 0; }
    done <<< "$_SOURCE_SUBPATH_LINES"
    # Miss: return 0 with empty stdout — caller defaults via ${source_subpath:-...}.
    return 0
}
_copy_install_names=""
while IFS='|' read -r _pn _sp _lp _tr _dn _pm _rdc; do
    [[ -z "$_pn" ]] && continue
    if [[ -n "$FILTER_PLUGIN" ]] && [[ "$_pn" != "$FILTER_PLUGIN" ]]; then continue; fi
    if [[ "$_pm" == "copy_install" ]]; then
        # Review: code-reviewer (F5) — newline delimiter instead of space to handle plugin
        #   names containing spaces without word-split fragility on the Python side.
        if [[ -z "$_copy_install_names" ]]; then
            _copy_install_names="$_pn"
        else
            _copy_install_names="${_copy_install_names}"$'\n'"${_pn}"
        fi
    fi
done <<< "$MIRRORS_OUTPUT"

if [[ -n "$_copy_install_names" ]]; then
    # One Python invocation for all copy_install plugins.
    # IFS='=' read: _key = plugin name (no '=' per TOML key rule); _val = remainder
    # (any '=' in the subpath is preserved, since read assigns the rest to _val).
    while IFS='=' read -r _key _val; do
        [[ -n "$_key" ]] && _SOURCE_SUBPATH_LINES="${_SOURCE_SUBPATH_LINES}${_key}"$'\t'"${_val}"$'\n'
    done < <(_lookup_all_source_subpaths "$_copy_install_names" "$REGISTRY_FILE")
fi

while IFS='|' read -r plugin_name source_path live_path track_ref dist_name prop_mode _reverse_drift_cmd; do
    [[ -z "$plugin_name" ]] && continue
    if [[ -n "$FILTER_PLUGIN" ]] && [[ "$plugin_name" != "$FILTER_PLUGIN" ]]; then
        continue
    fi
    # Resolve source_subpath from the pre-computed batch map; default handled inside _check_plugin.
    source_subpath=""
    if [[ "$prop_mode" == "copy_install" ]]; then
        source_subpath="$(_lookup_source_subpath "$plugin_name")"
    fi
    if ! _check_plugin "$plugin_name" "$source_path" "$live_path" "$track_ref" "$dist_name" "$prop_mode" "$source_subpath"; then
        TOTAL_DRIFT=1
    fi
done <<< "$MIRRORS_OUTPUT"

exit $TOTAL_DRIFT
