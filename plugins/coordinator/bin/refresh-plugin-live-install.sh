#!/usr/bin/env bash
# bin/refresh-plugin-live-install.sh — Managed refresh for a registered plugin's live install.
#
# Spec backlink: docs/plans/2026-05-21-plugin-source-live-mirror-doctrine.md §Chunk 2
# Purpose: perform both propagation legs atomically — git-state (advance HEAD to
# track_ref) and venv-state (re-run editable install when pyproject or MAPPING stale).
# Refuses on unsafe pre-flight states unless --force is given.
#
# Usage:
#   refresh-plugin-live-install.sh <plugin> [--force]
#
#   <plugin>    Plugin name as registered under plugin.mirrors.<plugin> in
#               ~/.claude/machine-local/registry.local.toml
#   --force     Override clean-tree refusal (use for broken-install recovery).
#               Does NOT skip snapshot or lock.
#
# SIGKILL leaves a stale lock. Operator recovery:
#   rm -rf ~/.claude/plugins/.refresh-<plugin>.lock.d
#
# Idempotency: safe to re-run. If already at target SHA and pyproject unchanged,
# all steps are no-ops or trivial-verify.
#
# Negative spec: does NOT auto-kill the MCP server (concurrent-EM-hostile).
# Embed sidecar self-evicts at idle timeout (300s/1800s). __pycache__/ bytecode
# is mtime-invalidated automatically on next import.

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

PLUGIN=""
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=1
            ;;
        --help|-h)
            cat <<'EOF'
Usage: refresh-plugin-live-install.sh <plugin> [--force]

Perform a managed two-leg refresh of a registered plugin's live install:
  Leg 1 (git-state)  — fetch origin and checkout track_ref
  Leg 2 (venv-state) — re-run editable install if pyproject or MAPPING is stale

Options:
  --force   Override clean-tree refusal (use for broken-install recovery only).
            Does NOT skip snapshot or concurrency lock.

Pre-conditions:
  - Plugin must be registered under plugin.mirrors.<plugin> in
    ~/.claude/machine-local/registry.local.toml
  - Plugin must NOT have propagation_mode = "source_is_live" (no refresh needed)
  - Live checkout working tree must be clean (no uncommitted edits) unless --force

SIGKILL leaves a stale lock. Operator recovery:
  rm -rf ~/.claude/plugins/.refresh-<plugin>.lock.d

Audit log: ~/.claude/plugins/.refresh-log
Snapshots: ~/.claude/plugins/_pre-refresh-snapshots/
EOF
            exit 0
            ;;
        -*)
            echo "refresh-plugin-live-install.sh: unknown flag: $arg" >&2
            echo "Run with --help for usage." >&2
            exit 1
            ;;
        *)
            if [[ -z "$PLUGIN" ]]; then
                PLUGIN="$arg"
            else
                echo "refresh-plugin-live-install.sh: unexpected argument: $arg" >&2
                echo "Run with --help for usage." >&2
                exit 1
            fi
            ;;
    esac
done

if [[ -z "$PLUGIN" ]]; then
    echo "refresh-plugin-live-install.sh: <plugin> argument required." >&2
    echo "Run with --help for usage." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Resolve ~/.claude via claude-home helper
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME_BIN="$SCRIPT_DIR/claude-home"
if [[ ! -x "$CLAUDE_HOME_BIN" ]]; then
    # Fall back to PATH
    CLAUDE_HOME_BIN="claude-home"
fi

# Resolve Python interpreter: prefer python3, fall back to python (matches claude-home pattern).
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "refresh-plugin-live-install.sh: python3 (or python) not found on PATH" >&2
    exit 1
fi

CLAUDE_HOME="$("$CLAUDE_HOME_BIN" dir 2>/dev/null | tr -d '\r')" || {
    echo "refresh-plugin-live-install.sh: claude-home dir failed — cannot resolve ~/.claude" >&2
    exit 1
}

PLUGINS_DIR="$CLAUDE_HOME/plugins"
REGISTRY_LOCAL="$CLAUDE_HOME/machine-local/registry.local.toml"
REFRESH_LOG="$PLUGINS_DIR/.refresh-log"
SNAPSHOTS_DIR="$PLUGINS_DIR/_pre-refresh-snapshots"

# ---------------------------------------------------------------------------
# Step 1: Acquire mkdir-based lock (POSIX-portable; bash-on-windows-gotchas.md §4)
# ---------------------------------------------------------------------------

LOCK_DIR="$PLUGINS_DIR/.refresh-${PLUGIN}.lock.d"

_acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$$" > "$LOCK_DIR/pid"
        return 0
    fi

    # Lock dir exists — check for dead holder.
    if [[ -f "$LOCK_DIR/pid" ]]; then
        local stored_pid
        stored_pid="$(cat "$LOCK_DIR/pid" | tr -d '\r')"
        if [[ -n "$stored_pid" ]] && ! kill -0 "$stored_pid" 2>/dev/null; then
            # Dead holder — remove and retry once.
            echo "refresh-plugin-live-install.sh: stale lock from dead PID $stored_pid — clearing and retrying." >&2
            rm -rf "$LOCK_DIR" 2>/dev/null || true
            if mkdir "$LOCK_DIR" 2>/dev/null; then
                echo "$$" > "$LOCK_DIR/pid"
                return 0
            fi
        else
            echo "refresh-plugin-live-install.sh: refresh already in progress (PID ${stored_pid:-unknown})." >&2
            echo "  If this is stale, run: rm -rf '$LOCK_DIR'" >&2
            return 1
        fi
    fi

    echo "refresh-plugin-live-install.sh: could not acquire lock at $LOCK_DIR" >&2
    echo "  If stale, run: rm -rf '$LOCK_DIR'" >&2
    return 1
}

trap 'rm -rf "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

_acquire_lock || exit 1

# ---------------------------------------------------------------------------
# Step 2: Registry lookup via Python (tomllib)
# ---------------------------------------------------------------------------

_read_registry() {
    "$PYTHON" - "$REGISTRY_LOCAL" "$PLUGIN" <<'PYEOF' | tr -d '\r'
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
plugin_name   = sys.argv[2]

if not registry_path.exists():
    print(f"ERROR: registry not found: {registry_path}", file=sys.stderr)
    sys.exit(3)

try:
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"ERROR: failed to parse registry: {e}", file=sys.stderr)
    sys.exit(4)

mirrors = data.get("plugin", {}).get("mirrors", {})
if plugin_name not in mirrors:
    print(f"NOT_REGISTERED", file=sys.stderr)
    sys.exit(5)

entry = mirrors[plugin_name]
prop_mode = entry.get("propagation_mode", "")
if prop_mode == "source_is_live":
    print("SOURCE_IS_LIVE")
    sys.exit(0)

source_path = entry.get("source_path", "")
live_path   = entry.get("live_path", "")
track_ref   = entry.get("track_ref", "origin/main")
dist_name   = entry.get("dist_name", plugin_name.replace("-", "_"))

if not source_path or not live_path:
    print(f"ERROR: registry entry for '{plugin_name}' missing source_path or live_path", file=sys.stderr)
    sys.exit(6)

# Emit shell-safe key=value pairs (no spaces in values expected per doctrine)
print(f"source_path={source_path}")
print(f"live_path={live_path}")
print(f"track_ref={track_ref}")
print(f"dist_name={dist_name}")
PYEOF
}

REGISTRY_OUTPUT="$(_read_registry)" || {
    exit_code=$?
    case $exit_code in
        5)
            echo "refresh-plugin-live-install.sh: plugin '$PLUGIN' is not registered in $REGISTRY_LOCAL" >&2
            echo "  Add a [plugin.mirrors.$PLUGIN] entry to register it." >&2
            ;;
        *)
            echo "refresh-plugin-live-install.sh: registry lookup failed (exit $exit_code)" >&2
            ;;
    esac
    exit $exit_code
}

# Handle source_is_live mode — structural no-op, clean exit.
if [[ "$REGISTRY_OUTPUT" == "SOURCE_IS_LIVE" ]]; then
    echo "refresh-plugin-live-install.sh: $PLUGIN has propagation_mode=source_is_live — live install IS the canonical source. No refresh needed."
    exit 0
fi

# Parse key=value output into shell variables.
SOURCE_PATH=""
LIVE_PATH=""
TRACK_REF="origin/main"
DIST_NAME=""

while IFS='=' read -r key value; do
    case "$key" in
        source_path) SOURCE_PATH="$value" ;;
        live_path)   LIVE_PATH="$value"   ;;
        track_ref)   TRACK_REF="$value"   ;;
        dist_name)   DIST_NAME="$value"   ;;
    esac
done <<< "$REGISTRY_OUTPUT"

if [[ -z "$LIVE_PATH" ]]; then
    echo "refresh-plugin-live-install.sh: failed to parse live_path from registry output" >&2
    exit 1
fi
if [[ -z "$SOURCE_PATH" ]]; then
    echo "refresh-plugin-live-install.sh: failed to parse source_path from registry output" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: Drift probe — working-tree cleanliness check (Chunk 1 contract)
# ---------------------------------------------------------------------------

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIFT_PROBE="$BIN_DIR/check-plugin-drift.sh"

_check_clean_tree() {
    local porcelain
    porcelain="$(git -C "$LIVE_PATH" status --porcelain 2>&1 | tr -d '\r')" || {
        echo "refresh-plugin-live-install.sh: git status failed in $LIVE_PATH" >&2
        return 1
    }
    if [[ -n "$porcelain" ]]; then
        return 1
    fi
    return 0
}

CLEAN_TREE_OK=1
if [[ -x "$DRIFT_PROBE" ]]; then
    # Use the real Chunk 1 probe when available.
    if ! "$DRIFT_PROBE" "$PLUGIN" --check-clean-only 2>/dev/null; then
        CLEAN_TREE_OK=0
    fi
else
    # Fallback: check git porcelain directly (integration path when Chunk 1 not yet on disk).
    if ! _check_clean_tree; then
        CLEAN_TREE_OK=0
    fi
fi

if [[ $CLEAN_TREE_OK -eq 0 ]]; then
    if [[ $FORCE -eq 1 ]]; then
        echo "refresh-plugin-live-install.sh: WARNING: live checkout has uncommitted edits (--force given, proceeding)." >&2
    else
        echo "refresh-plugin-live-install.sh: live checkout at $LIVE_PATH has uncommitted edits." >&2
        echo "  Resolve or stash local edits, then re-run." >&2
        echo "  To override (broken-install recovery only): add --force" >&2
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 4: Snapshot live install for rollback insurance
# ---------------------------------------------------------------------------

ISO_TS="$(date -u '+%Y%m%dT%H%M%SZ')"
SNAPSHOT_PATH="$SNAPSHOTS_DIR/${PLUGIN}-${ISO_TS}"

mkdir -p "$SNAPSHOTS_DIR"
echo "refresh-plugin-live-install.sh: snapshotting $LIVE_PATH -> $SNAPSHOT_PATH"
cp -r "$LIVE_PATH" "$SNAPSHOT_PATH" || {
    echo "refresh-plugin-live-install.sh: snapshot failed — aborting for safety." >&2
    exit 1
}

# Record old SHA before the git leg.
OLD_SHA="$(git -C "$LIVE_PATH" rev-parse HEAD 2>/dev/null | tr -d '\r')" || OLD_SHA="unknown"

# ---------------------------------------------------------------------------
# Steps 5-6: Git leg — fetch + checkout track_ref
# ---------------------------------------------------------------------------

echo "refresh-plugin-live-install.sh: [git-leg] fetching origin in $LIVE_PATH"
git -C "$LIVE_PATH" fetch origin || {
    echo "refresh-plugin-live-install.sh: git fetch failed." >&2
    exit 1
}

echo "refresh-plugin-live-install.sh: [git-leg] checking out $TRACK_REF"
git -C "$LIVE_PATH" checkout "$TRACK_REF" || {
    echo "refresh-plugin-live-install.sh: git checkout $TRACK_REF failed." >&2
    exit 1
}

NEW_SHA="$(git -C "$LIVE_PATH" rev-parse HEAD 2>/dev/null | tr -d '\r')" || NEW_SHA="unknown"
echo "refresh-plugin-live-install.sh: [git-leg] HEAD advanced: ${OLD_SHA:0:12}->${NEW_SHA:0:12}"

# ---------------------------------------------------------------------------
# Steps 7-8: Venv leg — hash pyproject.toml; re-install if stale
# ---------------------------------------------------------------------------

PYPROJECT="$LIVE_PATH/pyproject.toml"
VENV_REFRESHED="n"
INSTALL_TOOL="none"
PYPROJECT_CHANGED="n"

# Compute current pyproject hash.
CURRENT_PYPROJECT_HASH=""
if [[ -f "$PYPROJECT" ]]; then
    CURRENT_PYPROJECT_HASH="$("$PYTHON" - "$PYPROJECT" <<'HASHEOF' | tr -d '\r'
import sys, hashlib, pathlib
data = pathlib.Path(sys.argv[1]).read_bytes()
print(hashlib.sha256(data).hexdigest())
HASHEOF
)"
fi

# Read last recorded hash from refresh log.
LAST_RECORDED_HASH=""
if [[ -f "$REFRESH_LOG" ]]; then
    # Grep for the most recent line for this plugin with pyproject_hash= field.
    LAST_RECORDED_HASH="$(grep " ${PLUGIN} " "$REFRESH_LOG" 2>/dev/null \
        | grep "pyproject_hash=" \
        | tail -1 \
        | sed 's/.*pyproject_hash=\([a-f0-9]*\).*/\1/' \
        | tr -d '\r')" || true
fi

# Check if venv state is OK (direct_url.json resolves + MAPPING intact).
_check_venv_state() {
    local live="$1"
    local dist="$2"
    "$PYTHON" - "$live" "$dist" <<'VENVEOF' 2>/dev/null
import sys, json, pathlib, re

live_path = pathlib.Path(sys.argv[1])
dist_name = sys.argv[2]

venv = live_path / ".venv"
if not venv.exists():
    sys.exit(1)

sp_candidates = (
    list(venv.glob("Lib/site-packages"))
    + list(venv.glob("lib/python*/site-packages"))
)
if not sp_candidates:
    sys.exit(1)
site_packages = sp_candidates[0]

dist_info_dirs = list(site_packages.glob(f"{dist_name}-*.dist-info"))
if not dist_info_dirs:
    sys.exit(1)
dist_info = dist_info_dirs[0]

direct_url_path = dist_info / "direct_url.json"
if not direct_url_path.exists():
    sys.exit(1)

try:
    direct_url = json.loads(direct_url_path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(1)

url = direct_url.get("url", "")
if url.startswith("file:///"):
    pinned_path_str = url[8:]
    pinned_path = pathlib.Path(pinned_path_str.replace('/', pathlib.os.sep))
else:
    pinned_path = pathlib.Path(url)

live_resolved = live_path.resolve()
try:
    pin_resolved = pinned_path.resolve()
    if pin_resolved != live_resolved:
        sys.exit(1)
except Exception:
    sys.exit(1)

finder_files = list(site_packages.glob("__editable__*_finder.py"))
if finder_files:
    finder = finder_files[0]
    try:
        src = finder.read_text(encoding="utf-8")
        m = re.search(r'MAPPING\s*=\s*\{([^}]*)\}', src, re.DOTALL)
        if m:
            for path_match in re.finditer(r"'([^']+)'", m.group(1)):
                candidate = pathlib.Path(path_match.group(1))
                if not candidate.exists():
                    sys.exit(1)
                try:
                    candidate.resolve().relative_to(live_resolved)
                except ValueError:
                    sys.exit(1)
    except Exception:
        pass  # Non-fatal — MAPPING check error doesn't block.

sys.exit(0)
VENVEOF
}

VENV_STATE_OK=0
if [[ -d "$LIVE_PATH/.venv" ]]; then
    if _check_venv_state "$LIVE_PATH" "$DIST_NAME"; then
        VENV_STATE_OK=1
    fi
fi

# Determine if venv re-install is needed.
NEED_VENV_INSTALL=0
if [[ -z "$CURRENT_PYPROJECT_HASH" ]]; then
    : # No pyproject.toml — skip venv install
elif [[ "$CURRENT_PYPROJECT_HASH" != "$LAST_RECORDED_HASH" ]]; then
    PYPROJECT_CHANGED="y"
    NEED_VENV_INSTALL=1
    echo "refresh-plugin-live-install.sh: [venv-leg] pyproject.toml changed (hash mismatch) — re-install needed."
elif [[ $VENV_STATE_OK -eq 0 ]]; then
    NEED_VENV_INSTALL=1
    echo "refresh-plugin-live-install.sh: [venv-leg] venv state stale (direct_url or MAPPING) — re-install needed."
else
    echo "refresh-plugin-live-install.sh: [venv-leg] pyproject unchanged and venv state OK — skipping re-install."
fi

if [[ $NEED_VENV_INSTALL -eq 1 ]]; then
    # Determine install tool.  Prefer uv; detect venv creator from pyvenv.cfg.
    PYVENV_CFG="$LIVE_PATH/.venv/pyvenv.cfg"
    VENV_CREATED_BY_PIP=0
    if [[ -f "$PYVENV_CFG" ]]; then
        # Detect pip-created venv by absence of uv markers.
        if grep -qi "virtualenv\|pip" "$PYVENV_CFG" 2>/dev/null && \
           ! grep -qi "uv" "$PYVENV_CFG" 2>/dev/null; then
            VENV_CREATED_BY_PIP=1
        fi
    fi

    # Determine Python interpreter path (pyvenv.cfg is authoritative source).
    UNAME_S="$(uname -s 2>/dev/null || echo '')"
    if [[ "$UNAME_S" == MINGW* ]] || [[ "$UNAME_S" == CYGWIN* ]] || [[ -n "${WINDIR:-}" ]]; then
        VENV_PYTHON="$LIVE_PATH/.venv/Scripts/python.exe"
    else
        VENV_PYTHON="$LIVE_PATH/.venv/bin/python"
    fi
    # pyvenv.cfg home is authoritative fallback if default path doesn't exist.
    if [[ ! -f "$VENV_PYTHON" ]] && [[ -f "$PYVENV_CFG" ]]; then
        PYVENV_HOME="$(grep '^home' "$PYVENV_CFG" | head -1 | sed 's/home *= *//' | tr -d '\r')"
        if [[ -n "$PYVENV_HOME" ]]; then
            if [[ -f "$PYVENV_HOME/python.exe" ]]; then
                VENV_PYTHON="$PYVENV_HOME/python.exe"
            elif [[ -f "$PYVENV_HOME/python" ]]; then
                VENV_PYTHON="$PYVENV_HOME/python"
            fi
        fi
    fi

    # Tool selection: prefer uv; bootstrap if absent; no bare pip fallback
    # (per cpu-torch-install-trap.md / substrate-pin-doctrine.md — bare pip install
    # -e . bypasses [tool.uv.sources] and PEP 440 local-version pins).
    if command -v uv >/dev/null 2>&1; then
        INSTALL_TOOL="uv"
    elif [[ $VENV_CREATED_BY_PIP -eq 1 ]]; then
        # Venv was created by pip — use pip to avoid tool-switch dist-info shape artifacts.
        # Document this case in the audit log (install_tool=pip).
        echo "refresh-plugin-live-install.sh: [venv-leg] venv created by pip; using pip for editable install (audit: tool-switch avoided to preserve dist-info shape)."
        INSTALL_TOOL="pip"
    else
        # Attempt to bootstrap uv (fail-loud on failure per substrate-pin-doctrine.md).
        echo "refresh-plugin-live-install.sh: [venv-leg] uv not on PATH — bootstrapping via pip install uv (180s timeout)"
        if "$PYTHON" -m pip install uv --timeout 180 --quiet; then
            INSTALL_TOOL="uv"
        else
            echo "refresh-plugin-live-install.sh: FATAL: uv bootstrap failed." >&2
            echo "  Bare 'pip install -e .' is not a safe fallback — bypasses [tool.uv.sources] and PEP 440 local pins." >&2
            echo "  Install uv manually: https://docs.astral.sh/uv/getting-started/installation/" >&2
            exit 1
        fi
    fi

    # Run the editable install.
    # Note: uv pip install -e . rebuilds __editable__*_finder.py MAPPING dict AND
    # regenerates console-script shims — closes MAPPING-stale and missing-shim failure
    # classes, not just direct_url.json. This is documented explicitly so callers
    # understand the full scope of what this step repairs.
    echo "refresh-plugin-live-install.sh: [venv-leg] running $INSTALL_TOOL pip install -e . (python: $VENV_PYTHON)"
    if [[ "$INSTALL_TOOL" == "uv" ]]; then
        (cd "$LIVE_PATH" && uv pip install -e . --python "$VENV_PYTHON") || {
            echo "refresh-plugin-live-install.sh: uv pip install -e . failed." >&2
            exit 1
        }
    else
        (cd "$LIVE_PATH" && "$VENV_PYTHON" -m pip install -e . --quiet) || {
            echo "refresh-plugin-live-install.sh: pip install -e . failed." >&2
            exit 1
        }
    fi

    VENV_REFRESHED="y"
    echo "refresh-plugin-live-install.sh: [venv-leg] editable install complete (tool: $INSTALL_TOOL)."
fi

# ---------------------------------------------------------------------------
# Step 9: Post-flight drift probe — assert zero items
# ---------------------------------------------------------------------------
# Review: code-reviewer (chain-end finding #2) — eliminated the step 9-pre double-write.
# Previously, a duplicate audit row was written here before the probe ran so the
# probe's venv-pyproject hash check would see the updated hash. Now we pass
# CURRENT_PYPROJECT_HASH_OVERRIDE via env instead; Step 10 is the single audit write.

POST_FLIGHT_CLEAN=1

if [[ -x "$DRIFT_PROBE" ]]; then
    if ! CURRENT_PYPROJECT_HASH_OVERRIDE="$CURRENT_PYPROJECT_HASH" "$DRIFT_PROBE" "$PLUGIN" 2>/dev/null; then
        POST_FLIGHT_CLEAN=0
    fi
else
    # Fallback: check working-tree cleanliness only.
    if ! _check_clean_tree; then
        POST_FLIGHT_CLEAN=0
    fi
fi

if [[ $POST_FLIGHT_CLEAN -eq 0 ]]; then
    echo "refresh-plugin-live-install.sh: ERROR: post-flight drift check failed — restoring from snapshot." >&2
    echo "  Snapshot: $SNAPSHOT_PATH" >&2
    if [[ -d "$SNAPSHOT_PATH" ]]; then
        # Review: code-reviewer (chain-end finding #17) — .git safety guard: refuse to
        # delete LIVE_PATH when it is not a git repo (guards against misconfigured
        # live_path pointing at a broad directory).
        if [[ ! -d "$LIVE_PATH/.git" ]]; then
            echo "refresh-plugin-live-install.sh: ABORT: $LIVE_PATH is not a git repo — refusing rm -rf for safety." >&2
            echo "  Manual recovery: restore from $SNAPSHOT_PATH" >&2
            exit 1
        fi
        # Review: code-reviewer (chain-end finding #10) — use cp -r instead of rm-rf+mv.
        # The old destructive-first pattern left LIVE_PATH absent if mv failed.
        # cp -r keeps LIVE_PATH intact throughout; only cleaned up after success.
        cp -r "$SNAPSHOT_PATH/." "$LIVE_PATH/"
        echo "refresh-plugin-live-install.sh: restored from snapshot. Investigate and retry." >&2
    else
        echo "refresh-plugin-live-install.sh: snapshot not found at $SNAPSHOT_PATH — manual recovery required." >&2
    fi
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 9b: MCP server NOTICE (the Staff Engineer #3)
# ---------------------------------------------------------------------------

DOCTOR_SENTINEL="$PLUGINS_DIR/${PLUGIN}/data/doctor-last-run.json"
if [[ -f "$DOCTOR_SENTINEL" ]]; then
    MCP_PID="$("$PYTHON" - "$DOCTOR_SENTINEL" <<'PIDEOF' 2>/dev/null | tr -d '\r'
import sys, json, pathlib
try:
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    pid = data.get("mcp_server_pid", "")
    print(pid if pid else "")
except Exception:
    print("")
PIDEOF
)" || MCP_PID=""

    if [[ -n "$MCP_PID" ]]; then
        cat >&2 <<EOF
========================================================================
NOTICE: refresh staged successfully; ${PLUGIN} MCP server must be restarted
       to take effect. Current MCP server PID: ${MCP_PID} (kill it via
       /project-rag:doctor or restart Claude Code).
       Embed sidecar will self-evict at idle timeout (300s/1800s).
       __pycache__/ bytecode is mtime-invalidated automatically.
========================================================================
EOF
    else
        cat >&2 <<EOF
========================================================================
NOTICE: refresh staged successfully; ${PLUGIN} MCP server must be restarted
       to take effect.
       Embed sidecar will self-evict at idle timeout (300s/1800s).
       __pycache__/ bytecode is mtime-invalidated automatically.
========================================================================
EOF
    fi
fi

# ---------------------------------------------------------------------------
# Step 10: Append audit row to .refresh-log
# ---------------------------------------------------------------------------

END_TS="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

echo "${END_TS}  ${PLUGIN}  ${OLD_SHA:0:12}->${NEW_SHA:0:12}  pyproject_changed=${PYPROJECT_CHANGED}  venv_refreshed=${VENV_REFRESHED}  install_tool=${INSTALL_TOOL}  pyproject_hash=${CURRENT_PYPROJECT_HASH}" \
    >> "$REFRESH_LOG"

echo "refresh-plugin-live-install.sh: done. Audit row appended to $REFRESH_LOG"
