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
INTERACTIVE=0

for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=1
            ;;
        --interactive)
            INTERACTIVE=1
            ;;
        --help|-h)
            cat <<'EOF'
Usage: refresh-plugin-live-install.sh <plugin> [--force] [--interactive]

Perform a managed two-leg refresh of a registered plugin's live install:
  Leg 1 (git-state)  — fetch origin and checkout track_ref
  Leg 2 (venv-state) — re-run editable install if pyproject or MAPPING is stale

Options:
  --force         Override clean-tree refusal (use for broken-install recovery only).
                  Does NOT skip snapshot or concurrency lock.
  --interactive   Per-file approval gate BEFORE the atomic refresh executes.
                  Prompts for each incoming file: y=mirror N=skip d=diff a=all s=skip-rest q=quit.
                  Per-plugin blast radius only. Complementary to the atomic refresh, not a replacement.
                  Not supported for copy_install plugins (no per-file diff available).

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
    bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$REGISTRY_LOCAL" "$PLUGIN" <<'PYEOF' | tr -d '\r'
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

# Build the mirrors dict from two sources (must match check-plugin-drift.sh
# _read_all_mirrors): (1) nested [plugin.mirrors.<name>] tables; (2) flat
# dotted-key form "plugin.mirrors.<name>.<field>" = "..." written by
# `machine-local set`. Both are valid registry writes; nested wins on collision.
mirrors = {}
nested = data.get("plugin", {}).get("mirrors", {})
if isinstance(nested, dict):
    for _name, _entry in nested.items():
        if isinstance(_entry, dict):
            mirrors[_name] = dict(_entry)
_PREFIX = "plugin.mirrors."
for _raw_key, _raw_val in data.items():
    if not isinstance(_raw_key, str) or not _raw_key.startswith(_PREFIX):
        continue
    _parts = _raw_key[len(_PREFIX):].split(".", 1)
    if len(_parts) != 2:
        continue
    _pname, _field = _parts
    mirrors.setdefault(_pname, {})
    if _field not in mirrors[_pname]:
        mirrors[_pname][_field] = _raw_val

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
refresh_cmd = entry.get("refresh_cmd", "")

# Enforce the single-line constraint HERE — the shell `IFS='=' read` loop would
# silently truncate a multi-line value to its first line (code-reviewer F1). Fail
# loud at the read locus instead, where the newline is still observable.
if "\n" in refresh_cmd or "\r" in refresh_cmd:
    print(f"ERROR: refresh_cmd for '{plugin_name}' contains a newline — single-line commands only", file=sys.stderr)
    sys.exit(7)

if not source_path or not live_path:
    print(f"ERROR: registry entry for '{plugin_name}' missing source_path or live_path", file=sys.stderr)
    sys.exit(6)

# Emit shell-safe key=value pairs. Values may contain spaces and embedded '='
# (e.g. refresh_cmd = "VAR=1 bash scripts/foo.sh --flag"); the shell parser uses
# `IFS='=' read -r key value`, so the remainder after the first '=' lands in value
# intact (including further '=' and spaces). refresh_cmd MUST NOT contain a newline.
print(f"propagation_mode={prop_mode}")
print(f"source_path={source_path}")
print(f"live_path={live_path}")
print(f"track_ref={track_ref}")
print(f"dist_name={dist_name}")
print(f"refresh_cmd={refresh_cmd}")
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
PROPAGATION_MODE=""
SOURCE_PATH=""
LIVE_PATH=""
TRACK_REF="origin/main"
DIST_NAME=""
REFRESH_CMD=""

while IFS='=' read -r key value; do
    case "$key" in
        propagation_mode) PROPAGATION_MODE="$value" ;;
        source_path) SOURCE_PATH="$value" ;;
        live_path)   LIVE_PATH="$value"   ;;
        track_ref)   TRACK_REF="$value"   ;;
        dist_name)   DIST_NAME="$value"   ;;
        refresh_cmd) REFRESH_CMD="$value" ;;
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
# copy_install mode — branch before git/venv legs.
#
# Refresh action = the registry-supplied refresh_cmd, run from source_path. We do
# NOT hardcode `install-plugin.sh <plugin> --no-enable`: the holodeck trio gates
# standalone component installs behind HOLODECK_UMBRELLA_INSTALL=1 (the gate at
# install-plugin.sh refuses a bare component install), reachable only via the
# component forwarders' --allow-standalone passthrough — and the docs/umbrella
# component has no forwarder at all. The correct invocation is holodeck-install
# internal knowledge, so it lives in the registry (operator/installer-supplied,
# same trust level as source_path/live_path the script already executes against),
# not coordinator-hardcoded. See docs/wiki/live-install-drift-audit.md § copy_install.
# ---------------------------------------------------------------------------

if [[ "$PROPAGATION_MODE" == "copy_install" ]]; then
    # --interactive is out of scope for copy_install: the refresh action is an opaque
    # registry-supplied refresh_cmd, not a git checkout — there is no per-file diff to gate.
    if [[ $INTERACTIVE -eq 1 ]]; then
        echo "refresh-plugin-live-install.sh: --interactive is unsupported for copy_install plugins (no per-file diff available). Run without --interactive." >&2
        exit 1
    fi

    # Normalise backslashes (Windows paths from registry).
    SOURCE_PATH="${SOURCE_PATH//\\//}"
    LIVE_PATH="${LIVE_PATH//\\//}"

    # rm-rf safety guard for the registry-supplied live_path. The restore paths
    # below `rm -rf` this path; a malformed, broad, traversal (`.../plugins/../..`),
    # or symlinked registry value must never reach that. Resolve to the physical
    # path — `cd … && pwd -P` collapses `..` and symlinks AND requires the dir to
    # exist — then require a `/plugins/` segment in the *resolved* path, and rm-rf
    # only the resolved path. (the Staff Engineer F0: the prior self-compare guarded nothing;
    # code-reviewer F2/F6: substring-on-raw-path missed `..` traversal and symlinks,
    # and the "$HOME" case arms were redundant with the empty/"/" arms.)
    LIVE_PATH_RESOLVED="$(cd "$LIVE_PATH" 2>/dev/null && pwd -P)" || true
    if [[ -z "$LIVE_PATH_RESOLVED" ]]; then
        echo "refresh-plugin-live-install.sh: ABORT: live_path '$LIVE_PATH' is not an existing directory — refusing copy_install refresh." >&2
        exit 1
    fi
    # Require the resolved live_path to live UNDER the coordinator plugins dir, not
    # merely contain a `/plugins/` substring (security-audit medium: a substring guard
    # accepts `/home/user/my-plugins-archive/live`). Resolve PLUGINS_DIR too so the
    # prefix compare is physical-vs-physical.
    PLUGINS_DIR_RESOLVED="$(cd "$PLUGINS_DIR" 2>/dev/null && pwd -P)" || true
    if [[ -z "$PLUGINS_DIR_RESOLVED" ]] || [[ "$LIVE_PATH_RESOLVED" != "$PLUGINS_DIR_RESOLVED"/* ]]; then
        echo "refresh-plugin-live-install.sh: ABORT: resolved live_path '$LIVE_PATH_RESOLVED' is not under the coordinator plugins dir '$PLUGINS_DIR_RESOLVED' — refusing (rm-rf guard)." >&2
        exit 1
    fi
    LIVE_PATH="$LIVE_PATH_RESOLVED"

    # No refresh_cmd registered → cannot auto-refresh (the bare installer would hit
    # the standalone gate). Print the actionable manual path and exit non-zero.
    # The cross-repo memo asks the holodeck installer to self-register refresh_cmd
    # at install time so this degraded path closes on a clean machine.
    if [[ -z "$REFRESH_CMD" ]]; then
        cat >&2 <<EOF
refresh-plugin-live-install.sh: [copy_install] $PLUGIN has no refresh_cmd registered — cannot auto-refresh.
  Refresh manually, then re-run the probe (check-plugin-drift.sh $PLUGIN):
    holodeck trio (umbrella):  /holodeck:install
    per-component (standalone): ( cd "$SOURCE_PATH" && bash scripts/install-<component>-plugin.sh --allow-standalone --no-enable )
  To enable automated refresh, register the invocation (run from source_path):
    machine-local set plugin.mirrors.$PLUGIN.refresh_cmd '<command>'
EOF
        exit 1
    fi

    # Skip the git clean-tree pre-flight — copy_install has no live git working tree;
    # re-running the idempotent copy installer is always safe.

    # Snapshot live install for rollback insurance.
    ISO_TS="$(date -u '+%Y%m%dT%H%M%SZ')"
    SNAPSHOT_PATH="$SNAPSHOTS_DIR/${PLUGIN}-${ISO_TS}"
    mkdir -p "$SNAPSHOTS_DIR"
    echo "refresh-plugin-live-install.sh: [copy_install] snapshotting $LIVE_PATH -> $SNAPSHOT_PATH"
    cp -r "$LIVE_PATH" "$SNAPSHOT_PATH" || {
        echo "refresh-plugin-live-install.sh: snapshot failed — aborting for safety." >&2
        exit 1
    }

    # Run the registry-supplied refresh command from source_path. Capture non-zero
    # exit explicitly — do not rely solely on bare set -euo pipefail through the subshell.
    # bash -euo pipefail -c so pipeline failures inside refresh_cmd fail-fast
    # (a plain `bash -c` would let `failing | true` mask errors — code-reviewer F7).
    echo "refresh-plugin-live-install.sh: [copy_install] running (cwd=$SOURCE_PATH): $REFRESH_CMD"
    if ! ( cd "$SOURCE_PATH" && bash -euo pipefail -c "$REFRESH_CMD" ); then
        echo "refresh-plugin-live-install.sh: copy-install refresh failed — restoring from snapshot." >&2
        if [[ -d "$SNAPSHOT_PATH" ]]; then
            # REPLACE semantics (not overlay): stage-then-swap so LIVE_PATH stays intact
            # until the copy succeeds — prevents data loss if cp is interrupted mid-transfer.
            _restore_staging="${LIVE_PATH}.restore.$$"
            cp -r "$SNAPSHOT_PATH" "$_restore_staging" || {
                echo "refresh-plugin-live-install.sh: restore staging failed — $LIVE_PATH is intact. Manual: copy from $SNAPSHOT_PATH" >&2
                rm -rf "$_restore_staging" 2>/dev/null || true
                exit 1
            }
            # staging copy succeeded — safe to remove live and swap in staged copy.
            rm -rf "$LIVE_PATH"
            mv "$_restore_staging" "$LIVE_PATH" || {
                echo "refresh-plugin-live-install.sh: restore mv failed — both $LIVE_PATH and $_restore_staging exist on disk. Manual recovery needed." >&2
                exit 1
            }
            echo "refresh-plugin-live-install.sh: restored from snapshot." >&2
        else
            echo "refresh-plugin-live-install.sh: snapshot not found at $SNAPSHOT_PATH — manual recovery required." >&2
        fi
        exit 1
    fi

    # Post-flight drift probe — assert sentinel now matches source HEAD.
    BIN_DIR_CI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    DRIFT_PROBE_CI="$BIN_DIR_CI/check-plugin-drift.sh"
    POST_FLIGHT_CLEAN_CI=1
    if [[ -x "$DRIFT_PROBE_CI" ]]; then
        # Forward the same registry the main script resolved, so the post-flight
        # probe can't drift to a different registry on a non-standard install (F3).
        if ! MACHINE_LOCAL_REGISTRY_DIR="$(dirname "$REGISTRY_LOCAL")" "$DRIFT_PROBE_CI" "$PLUGIN" 2>/dev/null; then
            POST_FLIGHT_CLEAN_CI=0
        fi
    fi

    if [[ $POST_FLIGHT_CLEAN_CI -eq 0 ]]; then
        echo "refresh-plugin-live-install.sh: ERROR: post-flight drift probe failed for copy_install — restoring from snapshot." >&2
        if [[ -d "$SNAPSHOT_PATH" ]]; then
            # Review: post-flight rollback — stage-then-swap so LIVE_PATH stays intact
            # until the copy succeeds (symmetric fix to primary rollback at L398-408).
            _postflight_staging="${LIVE_PATH}.postflight.$$"
            cp -r "$SNAPSHOT_PATH" "$_postflight_staging" || {
                echo "refresh-plugin-live-install.sh: post-flight restore staging failed — $LIVE_PATH is intact. Manual: copy from $SNAPSHOT_PATH" >&2
                rm -rf "$_postflight_staging" 2>/dev/null || true
                exit 1
            }
            rm -rf "$LIVE_PATH"
            mv "$_postflight_staging" "$LIVE_PATH" || {
                echo "refresh-plugin-live-install.sh: post-flight restore mv failed — both $LIVE_PATH and $_postflight_staging exist on disk. Manual recovery needed." >&2
                exit 1
            }
            echo "refresh-plugin-live-install.sh: restored from snapshot. Investigate and retry." >&2
        else
            echo "refresh-plugin-live-install.sh: snapshot not found — manual recovery required." >&2
        fi
        exit 1
    fi

    # Append audit row.
    END_TS_CI="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "${END_TS_CI}  ${PLUGIN}  copy_install  refresh_cmd=${REFRESH_CMD}" \
        >> "$REFRESH_LOG"
    echo "refresh-plugin-live-install.sh: done (copy_install). Audit row appended to $REFRESH_LOG"
    exit 0
fi

# Check if venv state is OK (direct_url.json resolves + MAPPING intact).
#
# Defined HERE (before the editable_sibling_venv / copy_install / git-leg dispatch)
# because the editable_sibling_venv branch below calls it earlier in execution order
# than the default venv leg does. Bash makes a function available only after its
# definition line executes.
#
# ARGS: $1 = live_path (venv host — where .venv and dist-info live)
#       $2 = dist_name
#       $3 = pin_root (OPTIONAL) — the path the editable pin (direct_url.json url) +
#                    MAPPING paths must resolve to. Defaults to $1 (live) so all
#                    existing callers are unchanged. Pass SOURCE_PATH in
#                    editable_sibling_venv mode where the venv host (live_path) and
#                    the install root (source_path) diverge.
#
# Spec backlink: docs/plans/2026-05-30-editable-sibling-venv-propagation-mode.md § Chunk 1
_check_venv_state() {
    local live="$1"
    local dist="$2"
    local pin_root="${3:-$1}"
    bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$live" "$dist" "$pin_root" <<'VENVEOF' 2>/dev/null
import sys, os, json, pathlib, re

live_path = pathlib.Path(sys.argv[1])
dist_name = sys.argv[2]
pin_root = pathlib.Path(sys.argv[3])

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
    # NOTE 2026-05-28 (harness-uncovered fix): use os.sep (with explicit `import os`)
    # not pathlib.os.sep — Python 3.13 removed the `os` submodule attribute from
    # pathlib, so the prior form silently AttributeErrors and the script falls
    # through to "venv state stale", re-installing on every refresh. Matches the
    # pattern check-plugin-drift.sh already uses (lines 263-266).
    pinned_path = pathlib.Path(pinned_path_str.replace('/', os.sep))
else:
    pinned_path = pathlib.Path(url)

# Review: code-reviewer F2 — removed dead `live_resolved = live_path.resolve()` assignment;
# the comparison uses pin_root_resolved, not live_resolved.
try:
    pin_resolved = pinned_path.resolve()
    pin_root_resolved = pin_root.resolve()
    if pin_resolved != pin_root_resolved:
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
                    # MAPPING paths resolve to pin_root (= source_path in
                    # editable_sibling_venv mode; = live_path otherwise via the $3 default).
                    candidate.resolve().relative_to(pin_root_resolved)
                except ValueError:
                    sys.exit(1)
    except Exception:
        pass  # Non-fatal — MAPPING check error doesn't block (matches original intent).
VENVEOF
}

# ---------------------------------------------------------------------------
# editable_sibling_venv mode — branch before git/venv legs.
#
# In this mode source_path and live_path point at TWO DIFFERENT plugins:
#   source_path = the addon's own git checkout (git-state leg target)
#   live_path   = the sibling host plugin whose .venv hosts the editable install
#                 (venv-state leg target: live_path/.venv)
#
# track_ref = "live" sentinel: the addon source is a live working tree — skip the
# git leg entirely. Consumer machines set track_ref = "origin/main" for the full
# two-leg (git-state on source_path, venv-state on live_path/.venv).
#
# No snapshot is taken: the source tree is a git repo (state recoverable via git)
# and the editable install is idempotent. On venv-leg failure: fail loud and leave
# state for manual `uv pip install -e <SOURCE_PATH> --python <LIVE_PATH venv python>`
# retry. Do NOT rm-rf anything — LIVE_PATH is the host plugin tree.
#
# MCP NOTICE targets LIVE_PATH (the host), not $PLUGINS_DIR/$PLUGIN.
#
# Spec backlink: docs/plans/2026-05-30-editable-sibling-venv-propagation-mode.md § Chunk 1
# ---------------------------------------------------------------------------

if [[ "$PROPAGATION_MODE" == "editable_sibling_venv" ]]; then
    # Step ESV-1: Normalise backslashes (Windows paths from registry).
    SOURCE_PATH="${SOURCE_PATH//\\//}"
    LIVE_PATH="${LIVE_PATH//\\//}"

    BIN_DIR_ESV="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    DRIFT_PROBE_ESV="$BIN_DIR_ESV/check-plugin-drift.sh"

    # Step ESV-2: git-state leg.
    if [[ "$TRACK_REF" == "live" ]]; then
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] git-state live (track_ref=live sentinel) — skipping git leg"
    else
        # Full two-leg: advance the addon's own git checkout.
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [git-leg] fetching origin in $SOURCE_PATH"

        # Step ESV-3: clean-tree precondition on SOURCE_PATH (only when git-leg active).
        # Do NOT block venv-only refresh on a dirty dev tree.
        ESV_CLEAN_TREE_OK=1
        ESV_PORCELAIN="$(git -C "$SOURCE_PATH" status --porcelain 2>&1 | tr -d '\r')" || ESV_CLEAN_TREE_OK=0
        if [[ $ESV_CLEAN_TREE_OK -eq 1 ]] && [[ -n "$ESV_PORCELAIN" ]]; then
            ESV_CLEAN_TREE_OK=0
        fi
        if [[ $ESV_CLEAN_TREE_OK -eq 0 ]]; then
            if [[ $FORCE -eq 1 ]]; then
                echo "refresh-plugin-live-install.sh: [editable_sibling_venv] WARNING: addon source at $SOURCE_PATH has uncommitted edits (--force given, proceeding)." >&2
            else
                echo "refresh-plugin-live-install.sh: [editable_sibling_venv] addon source at $SOURCE_PATH has uncommitted edits." >&2
                echo "  Resolve or stash local edits, then re-run." >&2
                echo "  To override (broken-install recovery only): add --force" >&2
                exit 1
            fi
        fi

        git -C "$SOURCE_PATH" fetch origin || {
            echo "refresh-plugin-live-install.sh: [editable_sibling_venv] git fetch failed in $SOURCE_PATH." >&2
            exit 1
        }

        # Resolve CHECKOUT_REF on SOURCE_PATH.
        ESV_CHECKOUT_REF=""
        if git -C "$SOURCE_PATH" rev-parse --verify "refs/remotes/$TRACK_REF" >/dev/null 2>&1; then
            ESV_CHECKOUT_REF="$TRACK_REF"
        elif git -C "$SOURCE_PATH" rev-parse --verify "refs/tags/$TRACK_REF" >/dev/null 2>&1; then
            ESV_CHECKOUT_REF="$TRACK_REF"
        elif git -C "$SOURCE_PATH" rev-parse --verify "FETCH_HEAD" >/dev/null 2>&1; then
            ESV_CHECKOUT_REF="FETCH_HEAD"
        else
            ESV_CHECKOUT_REF="$TRACK_REF"
        fi

        ESV_OLD_SHA="$(git -C "$SOURCE_PATH" rev-parse HEAD 2>/dev/null | tr -d '\r')" || ESV_OLD_SHA="unknown"
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [git-leg] checking out $ESV_CHECKOUT_REF in $SOURCE_PATH"
        # Review: code-reviewer F6 — when ESV_CHECKOUT_REF is a remote-tracking ref of the
        # form "origin/<branch>", a plain `git checkout origin/main` leaves a detached HEAD.
        # Use `git checkout -B <branch> origin/<branch>` to land on a local tracking branch
        # instead. Falls back to plain checkout for tags and FETCH_HEAD (non-origin/ forms).
        if [[ "$ESV_CHECKOUT_REF" == origin/* ]]; then
            ESV_LOCAL_BRANCH="${ESV_CHECKOUT_REF#origin/}"
            git -C "$SOURCE_PATH" checkout -B "$ESV_LOCAL_BRANCH" "$ESV_CHECKOUT_REF" || {
                echo "refresh-plugin-live-install.sh: [editable_sibling_venv] git checkout -B $ESV_LOCAL_BRANCH $ESV_CHECKOUT_REF failed." >&2
                exit 1
            }
        else
            git -C "$SOURCE_PATH" checkout "$ESV_CHECKOUT_REF" || {
                echo "refresh-plugin-live-install.sh: [editable_sibling_venv] git checkout $ESV_CHECKOUT_REF failed." >&2
                exit 1
            }
        fi
        ESV_NEW_SHA="$(git -C "$SOURCE_PATH" rev-parse HEAD 2>/dev/null | tr -d '\r')" || ESV_NEW_SHA="unknown"
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [git-leg] HEAD advanced: ${ESV_OLD_SHA:0:12}->${ESV_NEW_SHA:0:12}"
    fi

    # Step ESV-4: venv-state leg.
    # pyproject hash: reads SOURCE_PATH/pyproject.toml (NOT LIVE_PATH — the default flow
    # reads LIVE_PATH; this mode MUST diverge per the operand table).
    ESV_PYPROJECT="$SOURCE_PATH/pyproject.toml"
    ESV_VENV_REFRESHED="n"
    ESV_INSTALL_TOOL="none"
    ESV_PYPROJECT_CHANGED="n"

    ESV_CURRENT_PYPROJECT_HASH=""
    if [[ -f "$ESV_PYPROJECT" ]]; then
        ESV_CURRENT_PYPROJECT_HASH="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$ESV_PYPROJECT" <<'HASHEOF' | tr -d '\r'
import sys, hashlib, pathlib
data = pathlib.Path(sys.argv[1]).read_bytes()
print(hashlib.sha256(data).hexdigest())
HASHEOF
)"
    fi

    ESV_LAST_RECORDED_HASH=""
    if [[ -f "$REFRESH_LOG" ]]; then
        ESV_LAST_RECORDED_HASH="$(grep " ${PLUGIN} " "$REFRESH_LOG" 2>/dev/null \
            | grep "pyproject_hash=" \
            | tail -1 \
            | sed 's/.*pyproject_hash=\([a-f0-9]*\).*/\1/' \
            | tr -d '\r')" || true
    fi

    # Check venv state: dist-info location = LIVE_PATH/.venv; pin-root = SOURCE_PATH.
    ESV_VENV_STATE_OK=0
    if [[ -d "$LIVE_PATH/.venv" ]]; then
        if _check_venv_state "$LIVE_PATH" "$DIST_NAME" "$SOURCE_PATH"; then
            ESV_VENV_STATE_OK=1
        fi
    fi

    ESV_NEED_VENV_INSTALL=0
    if [[ -z "$ESV_CURRENT_PYPROJECT_HASH" ]]; then
        : # No pyproject.toml in SOURCE_PATH — skip venv install
    elif [[ "$ESV_CURRENT_PYPROJECT_HASH" != "$ESV_LAST_RECORDED_HASH" ]]; then
        ESV_PYPROJECT_CHANGED="y"
        ESV_NEED_VENV_INSTALL=1
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [venv-leg] pyproject.toml changed (hash mismatch) — re-install needed."
    elif [[ $ESV_VENV_STATE_OK -eq 0 ]]; then
        ESV_NEED_VENV_INSTALL=1
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [venv-leg] venv state stale (direct_url or MAPPING) — re-install needed."
    else
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [venv-leg] pyproject unchanged and venv state OK — skipping re-install."
    fi

    if [[ $ESV_NEED_VENV_INSTALL -eq 1 ]]; then
        # Resolve --python interpreter from LIVE_PATH/.venv (the host venv).
        # Reuse the pyvenv.cfg-aware resolution pattern, pointed at LIVE_PATH/.venv.
        ESV_PYVENV_CFG="$LIVE_PATH/.venv/pyvenv.cfg"
        ESV_VENV_CREATED_BY_PIP=0
        if [[ -f "$ESV_PYVENV_CFG" ]]; then
            if grep -qiE "virtualenv|pip" "$ESV_PYVENV_CFG" 2>/dev/null && \
               ! grep -qi "uv" "$ESV_PYVENV_CFG" 2>/dev/null; then
                ESV_VENV_CREATED_BY_PIP=1
            fi
        fi

        ESV_UNAME_S="$(uname -s 2>/dev/null || echo '')"
        if [[ "$ESV_UNAME_S" == MINGW* ]] || [[ "$ESV_UNAME_S" == CYGWIN* ]] || [[ -n "${WINDIR:-}" ]]; then
            ESV_VENV_PYTHON="$LIVE_PATH/.venv/Scripts/python.exe"
        else
            ESV_VENV_PYTHON="$LIVE_PATH/.venv/bin/python"
        fi
        if [[ ! -f "$ESV_VENV_PYTHON" ]] && [[ -f "$ESV_PYVENV_CFG" ]]; then
            ESV_PYVENV_HOME="$(grep '^home' "$ESV_PYVENV_CFG" | head -1 | sed 's/home *= *//' | tr -d '\r')"
            if [[ -n "$ESV_PYVENV_HOME" ]]; then
                if [[ -f "$ESV_PYVENV_HOME/python.exe" ]]; then
                    ESV_VENV_PYTHON="$ESV_PYVENV_HOME/python.exe"
                elif [[ -f "$ESV_PYVENV_HOME/python" ]]; then
                    ESV_VENV_PYTHON="$ESV_PYVENV_HOME/python"
                fi
            fi
        fi

        # Tool selection: prefer uv; bootstrap if absent; pip fallback if venv was pip-created.
        # editable install target = SOURCE_PATH (NOT LIVE_PATH) — this installs the ADDON source
        # into the HOST venv. Do NOT `cd "$LIVE_PATH" && uv pip install -e .` — that installs
        # the host package, not the addon.
        if command -v uv >/dev/null 2>&1; then
            ESV_INSTALL_TOOL="uv"
        elif [[ $ESV_VENV_CREATED_BY_PIP -eq 1 ]]; then
            echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [venv-leg] venv created by pip; using pip for editable install."
            ESV_INSTALL_TOOL="pip"
        else
            echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [venv-leg] uv not on PATH — bootstrapping via pip install uv (180s timeout)"
            if bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" -m pip install uv --timeout 180 --quiet; then
                ESV_INSTALL_TOOL="uv"
            else
                echo "refresh-plugin-live-install.sh: [editable_sibling_venv] FATAL: uv bootstrap failed." >&2
                echo "  Install uv manually: https://docs.astral.sh/uv/getting-started/installation/" >&2
                exit 1
            fi
        fi

        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [venv-leg] running $ESV_INSTALL_TOOL pip install -e '$SOURCE_PATH' --python '$ESV_VENV_PYTHON'"
        if [[ "$ESV_INSTALL_TOOL" == "uv" ]]; then
            uv pip install -e "$SOURCE_PATH" --python "$ESV_VENV_PYTHON" || {
                echo "refresh-plugin-live-install.sh: [editable_sibling_venv] uv pip install -e failed." >&2
                echo "  Manual retry: uv pip install -e '$SOURCE_PATH' --python '$ESV_VENV_PYTHON'" >&2
                exit 1
            }
        else
            "$ESV_VENV_PYTHON" -m pip install -e "$SOURCE_PATH" --quiet || {
                echo "refresh-plugin-live-install.sh: [editable_sibling_venv] pip install -e failed." >&2
                echo "  Manual retry: '$ESV_VENV_PYTHON' -m pip install -e '$SOURCE_PATH'" >&2
                exit 1
            }
        fi

        ESV_VENV_REFRESHED="y"
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] [venv-leg] editable install complete (tool: $ESV_INSTALL_TOOL)."
    fi

    # Step ESV-5: MCP NOTICE — target LIVE_PATH (the host), not $PLUGINS_DIR/$PLUGIN.
    # The MCP server that must restart on addon update is the HOST's (project-rag),
    # whose sentinel lives at live_path/data/doctor-last-run.json.
    ESV_DOCTOR_SENTINEL="$LIVE_PATH/data/doctor-last-run.json"
    if [[ -f "$ESV_DOCTOR_SENTINEL" ]]; then
        ESV_MCP_PID="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$ESV_DOCTOR_SENTINEL" <<'PIDEOF' 2>/dev/null | tr -d '\r'
import sys, json, pathlib
try:
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    pid = data.get("mcp_server_pid", "")
    print(pid if pid else "")
except Exception:
    print("")
PIDEOF
)" || ESV_MCP_PID=""

        if [[ -n "$ESV_MCP_PID" ]]; then
            cat >&2 <<EOF
========================================================================
NOTICE: refresh staged successfully; ${PLUGIN} addon changes require the
       HOST MCP server (project-rag) to be restarted to take effect.
       Current HOST MCP server PID: ${ESV_MCP_PID} (kill it via
       /project-rag:doctor or restart Claude Code).
       Embed sidecar will self-evict at idle timeout (300s/1800s).
       __pycache__/ bytecode is mtime-invalidated automatically.
========================================================================
EOF
        else
            cat >&2 <<EOF
========================================================================
NOTICE: refresh staged successfully; ${PLUGIN} addon changes require the
       HOST MCP server (project-rag) to be restarted to take effect.
       Embed sidecar will self-evict at idle timeout (300s/1800s).
       __pycache__/ bytecode is mtime-invalidated automatically.
========================================================================
EOF
        fi
    fi

    # Step ESV-6: Append audit row + post-flight drift probe.
    ESV_END_TS="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "${ESV_END_TS}  ${PLUGIN}  editable_sibling_venv  pyproject_changed=${ESV_PYPROJECT_CHANGED}  venv_refreshed=${ESV_VENV_REFRESHED}  install_tool=${ESV_INSTALL_TOOL}  pyproject_hash=${ESV_CURRENT_PYPROJECT_HASH}" \
        >> "$REFRESH_LOG"
    echo "refresh-plugin-live-install.sh: [editable_sibling_venv] done. Audit row appended to $REFRESH_LOG"

    # Post-flight drift probe — mirrors copy_install post-flight.
    ESV_POST_FLIGHT_CLEAN=1
    if [[ -x "$DRIFT_PROBE_ESV" ]]; then
        if ! CURRENT_PYPROJECT_HASH_OVERRIDE="$ESV_CURRENT_PYPROJECT_HASH" \
             "$DRIFT_PROBE_ESV" "$PLUGIN" 2>/dev/null; then
            ESV_POST_FLIGHT_CLEAN=0
        fi
    fi

    if [[ $ESV_POST_FLIGHT_CLEAN -eq 0 ]]; then
        echo "refresh-plugin-live-install.sh: [editable_sibling_venv] WARNING: post-flight drift probe reported drift." >&2
        echo "  The venv-leg completed but drift remains. Investigate manually:" >&2
        echo "    check-plugin-drift.sh $PLUGIN" >&2
        echo "  No snapshot rollback in editable_sibling_venv mode (source tree is a git repo)." >&2
        exit 1
    fi

    exit 0
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
# Interactive per-file approval gate (only when --interactive)
# ---------------------------------------------------------------------------
# Runs BEFORE any mutation (snapshot/checkout/venv). Per-plugin blast radius:
# operates only on the incoming diff for THIS plugin's live checkout.
# Complementary to the atomic refresh — once the approved set is decided,
# the normal Steps 4-10 execute (full set → clean checkout; subset → partial).
#
# CHECKOUT_REF is resolved by the main flow after the Step-5 fetch (to match
# exactly what the Step-6 atomic git checkout advances to). The gate is invoked
# after the fetch so the double-fetch is removed and preview == action.
#
# INTERACTIVE_APPROVED: empty string = full set (normal atomic checkout);
#                       newline-separated paths = partial set.
# INTERACTIVE_PARTIAL:  0 = full atomic path; 1 = partial-checkout path.
CHECKOUT_REF=""
INTERACTIVE_APPROVED=""
INTERACTIVE_PARTIAL=0

_interactive_gate() {
    local incoming approved=() skip_rest=0
    # Incoming change set = diff between live HEAD and the resolved checkout target.
    # DIFF BASE (Review: the Staff Engineer Finding 5): diff against CHECKOUT_REF (resolved after
    # Step-5 fetch) so the preview matches the action exactly.
    incoming="$(git -C "$LIVE_PATH" diff --name-only "HEAD..$CHECKOUT_REF" 2>/dev/null | tr -d '\r')"
    if [[ -z "$incoming" ]]; then
        echo "refresh-plugin-live-install.sh: [interactive] $PLUGIN already at $TRACK_REF — nothing to review."
        # empty incoming = live HEAD already up-to-date with CHECKOUT_REF. We still return
        # empty INTERACTIVE_APPROVED (= full set), and the caller runs the full atomic
        # `git checkout` — which is a harmless no-op since there's nothing to apply.
        INTERACTIVE_APPROVED=""
        INTERACTIVE_PARTIAL=0
        return 0
    fi

    # PROMPT SOURCE (Review: the Staff Engineer Finding 8): prompts are written to /dev/tty so they
    # are visible even when stdout is captured, but DECISIONS are read from the script's
    # own stdin (fd 0) — NOT /dev/tty. This makes the loop testable: the AC smoke tests
    # feed decisions via `echo q | ...` / `printf 'a\ny\n' | ...` on stdin, which is the
    # source the loop actually reads. In real interactive use the operator's tty IS the
    # script's stdin, so behavior is identical.
    #
    # SKIP-REST SENTINEL SEMANTICS (Review: the Staff Engineer Finding 1): skip_rest is checked at the
    #   TOP of the outer loop for BOTH values before any inner prompt:
    #     1 = skip all remaining (from 's')        → continue without approving
    #     2 = approve all remaining (from 'a')      → approved+=("$f"); continue
    #   The 'a' branch approves the CURRENT file, sets skip_rest=2, and breaks the inner
    #   loop; the outer-loop guard then folds every subsequent line into `approved` without
    #   re-prompting. This replaces the prior broken draft where skip_rest=2 was set but the
    #   guard only checked ==1, so remaining files re-prompted.
    # Prompt output target: /dev/tty when available (visible even when stdout is captured),
    # falling back to stderr (testable in environments where /dev/tty is absent or broken —
    # notably Git Bash on Windows in piped contexts where -w /dev/tty passes but write fails).
    local _tty
    if printf '' > /dev/tty 2>/dev/null; then _tty=/dev/tty; else _tty=/dev/stderr; fi
    printf 'refresh-plugin-live-install.sh: [interactive] %s — review incoming changes (y/N/d/a/s/q):\n' "$PLUGIN" > "$_tty"
    # Read the file list from fd 3 (heredoc) so that inner `read -r ans` and `read -r conf`
    # can read user decisions from fd 0 (the script's own stdin, the pipe/terminal). Without
    # this split, `done <<< "$incoming"` redirects stdin for the entire while body and the
    # inner reads hit the heredoc data instead of the user's input.
    while IFS= read -r f <&3; do
        [[ -n "$f" ]] || continue
        if [[ $skip_rest -eq 1 ]]; then continue; fi                  # 's': skip all remaining
        if [[ $skip_rest -eq 2 ]]; then approved+=("$f"); continue; fi # 'a': approve all remaining
        while true; do
            printf '  %s  [y=mirror N=skip d=diff a=all s=skip-rest q=quit]: ' "$f" > "$_tty"
            read -r ans <&0 || ans=q                   # read from stdin (fd 0), not /dev/tty or fd 3
            case "$ans" in
                y|Y) approved+=("$f"); break ;;
                n|N|"") break ;;                       # default = skip
                d|D) git -C "$LIVE_PATH" diff "HEAD..$CHECKOUT_REF" -- "$f" > "$_tty" 2>&1 || true ;;  # reprompt
                a|A)
                    printf '  Approve ALL remaining incoming files? [y/N]: ' > "$_tty"
                    read -r conf <&0 || conf=N
                    if [[ "$conf" == y || "$conf" == Y ]]; then
                        approved+=("$f"); skip_rest=2; break   # approve current; guard approves the rest
                    fi
                    ;;                                  # 'N' on confirm → re-prompt the current file
                s|S) skip_rest=1; break ;;              # skip this and all remaining
                q|Q)
                    echo "refresh-plugin-live-install.sh: [interactive] quit — no changes applied." >&2
                    exit 0 ;;                           # EXIT trap releases lock
                *) printf '  unrecognized "%s"\n' "$ans" > "$_tty" ;;
            esac
        done
    done 3<<< "$incoming"

    local total approved_n
    total="$(printf '%s\n' "$incoming" | grep -c .)"
    approved_n=${#approved[@]}
    if [[ $approved_n -eq 0 ]]; then
        echo "refresh-plugin-live-install.sh: [interactive] nothing approved — exiting non-destructively." >&2
        exit 0
    fi
    if [[ $approved_n -lt $total ]]; then
        INTERACTIVE_PARTIAL=1
        INTERACTIVE_APPROVED="$(printf '%s\n' "${approved[@]}")"
        echo "refresh-plugin-live-install.sh: [interactive] PARTIAL: ${approved_n}/${total} files approved." >&2
        echo "  Live install will be a MIXED state (HEAD not advanced; venv leg skipped for safety)." >&2
    else
        INTERACTIVE_PARTIAL=0
        INTERACTIVE_APPROVED=""        # full set → normal clean checkout
        echo "refresh-plugin-live-install.sh: [interactive] all ${total} files approved — proceeding with full atomic refresh."
    fi
    return 0
}

# Record old SHA before the git leg.
OLD_SHA="$(git -C "$LIVE_PATH" rev-parse HEAD 2>/dev/null | tr -d '\r')" || OLD_SHA="unknown"

# ---------------------------------------------------------------------------
# Step 5 (pre-gate): Git fetch — runs BEFORE snapshot so _interactive_gate
# has a resolved diff base. Snapshot is taken only once the operator has
# approved (or --interactive is not set), so a 'q' quit exits cleanly with
# no snapshot on disk.
# ---------------------------------------------------------------------------

echo "refresh-plugin-live-install.sh: [git-leg] fetching origin in $LIVE_PATH"
git -C "$LIVE_PATH" fetch origin || {
    echo "refresh-plugin-live-install.sh: git fetch failed." >&2
    exit 1
}

# Resolve CHECKOUT_REF once — this is exactly the ref the Step-6 checkout will advance
# to, and the _interactive_gate diffs against it, so preview == action.
# If TRACK_REF is already a remote-tracking ref (origin/<branch>) or a tag, use it
# directly. If it is a bare local branch name, resolve via FETCH_HEAD so the diff
# reflects what the fetch just pulled, not the stale local branch tip.
if git -C "$LIVE_PATH" rev-parse --verify "refs/remotes/$TRACK_REF" >/dev/null 2>&1; then
    # TRACK_REF is a remote-tracking ref (e.g. origin/main) — use as-is.
    CHECKOUT_REF="$TRACK_REF"
elif git -C "$LIVE_PATH" rev-parse --verify "refs/tags/$TRACK_REF" >/dev/null 2>&1; then
    # TRACK_REF is a tag.
    CHECKOUT_REF="$TRACK_REF"
elif git -C "$LIVE_PATH" rev-parse --verify "FETCH_HEAD" >/dev/null 2>&1; then
    # Bare branch name (local): use FETCH_HEAD which the Step-5 fetch just updated.
    CHECKOUT_REF="FETCH_HEAD"
else
    # Fallback: use TRACK_REF as-is.
    CHECKOUT_REF="$TRACK_REF"
fi

# Invoke the interactive approval gate AFTER the fetch so the diff base is current.
# (Finding 5 double-fetch removed: gate diffs HEAD..$CHECKOUT_REF, not a self-fetched ref.)
# The gate runs BEFORE the snapshot so a 'q' quit exits non-destructively with no snapshot.
if [[ $INTERACTIVE -eq 1 ]]; then
    _interactive_gate
fi

# ---------------------------------------------------------------------------
# Step 4: Snapshot live install for rollback insurance
# (Placed after the interactive gate so a 'q' quit exits before any snapshot
# is written — satisfying the "no snapshot written" AC for non-destructive quit.)
# ---------------------------------------------------------------------------

ISO_TS="$(date -u '+%Y%m%dT%H%M%SZ')"
SNAPSHOT_PATH="$SNAPSHOTS_DIR/${PLUGIN}-${ISO_TS}"

mkdir -p "$SNAPSHOTS_DIR"
echo "refresh-plugin-live-install.sh: snapshotting $LIVE_PATH -> $SNAPSHOT_PATH"
cp -r "$LIVE_PATH" "$SNAPSHOT_PATH" || {
    echo "refresh-plugin-live-install.sh: snapshot failed — aborting for safety." >&2
    exit 1
}

# Determine whether to do a full atomic checkout or a partial-file checkout.
if [[ $INTERACTIVE_PARTIAL -eq 1 ]]; then
    # Partial mode: apply only the approved file paths; leave HEAD where it is.
    echo "refresh-plugin-live-install.sh: [git-leg] PARTIAL checkout of approved files only (HEAD will NOT advance)."
    while IFS= read -r approved_file; do
        [[ -n "$approved_file" ]] || continue
        git -C "$LIVE_PATH" checkout "$CHECKOUT_REF" -- "$approved_file" || {
            echo "refresh-plugin-live-install.sh: git checkout of '$approved_file' failed." >&2
            exit 1
        }
    done <<< "$INTERACTIVE_APPROVED"
    NEW_SHA="$(git -C "$LIVE_PATH" rev-parse HEAD 2>/dev/null | tr -d '\r')" || NEW_SHA="unknown"
    echo "refresh-plugin-live-install.sh: [git-leg] PARTIAL checkout complete. HEAD stayed at ${NEW_SHA:0:12}."
else
    # Full atomic checkout (default and full-approve interactive path).
    echo "refresh-plugin-live-install.sh: [git-leg] checking out $CHECKOUT_REF"
    git -C "$LIVE_PATH" checkout "$CHECKOUT_REF" || {
        echo "refresh-plugin-live-install.sh: git checkout $CHECKOUT_REF failed." >&2
        exit 1
    }

    NEW_SHA="$(git -C "$LIVE_PATH" rev-parse HEAD 2>/dev/null | tr -d '\r')" || NEW_SHA="unknown"
    echo "refresh-plugin-live-install.sh: [git-leg] HEAD advanced: ${OLD_SHA:0:12}->${NEW_SHA:0:12}"
fi

# ---------------------------------------------------------------------------
# Steps 7-8: Venv leg — hash pyproject.toml; re-install if stale
# ---------------------------------------------------------------------------

# In partial-interactive mode, skip the venv leg entirely: a partial source checkout
# against an unchanged HEAD is not a coherent editable-install state. Emit a loud
# NOTICE and recommend a full plain refresh to converge.
if [[ $INTERACTIVE_PARTIAL -eq 1 ]]; then
    echo "refresh-plugin-live-install.sh: [venv-leg] SKIPPED — partial-interactive mode. Live install is now in a MIXED state." >&2
    echo "  Run: refresh-plugin-live-install.sh $PLUGIN" >&2
    echo "  A plain (non-interactive) refresh will converge to the full atomic state." >&2
fi

PYPROJECT="$LIVE_PATH/pyproject.toml"
VENV_REFRESHED="n"
INSTALL_TOOL="none"
PYPROJECT_CHANGED="n"

# Compute current pyproject hash.
CURRENT_PYPROJECT_HASH=""
if [[ -f "$PYPROJECT" ]]; then
    CURRENT_PYPROJECT_HASH="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$PYPROJECT" <<'HASHEOF' | tr -d '\r'
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

# Review: code-reviewer F1 — duplicate _check_venv_state definition removed; the L461
# definition above is the single authoritative copy and precedes both call sites.

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

if [[ $INTERACTIVE_PARTIAL -eq 1 ]]; then
    NEED_VENV_INSTALL=0
fi

if [[ $NEED_VENV_INSTALL -eq 1 ]]; then
    # Determine install tool.  Prefer uv; detect venv creator from pyvenv.cfg.
    PYVENV_CFG="$LIVE_PATH/.venv/pyvenv.cfg"
    VENV_CREATED_BY_PIP=0
    if [[ -f "$PYVENV_CFG" ]]; then
        # Detect pip-created venv by absence of uv markers.
        if grep -qiE "virtualenv|pip" "$PYVENV_CFG" 2>/dev/null && \
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
        if bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" -m pip install uv --timeout 180 --quiet; then
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

# In partial-interactive mode, the drift probe will legitimately fail (HEAD ≠ track_ref
# because the partial checkout left HEAD behind). Do NOT restore from snapshot — that
# would undo the partial checkout the operator just approved. Leave the mixed state,
# warn, and recommend a full plain refresh to converge.
if [[ $INTERACTIVE_PARTIAL -eq 1 ]]; then
    echo "refresh-plugin-live-install.sh: [post-flight] SKIPPED for partial-interactive mode — drift is expected (HEAD behind track_ref)." >&2
    echo "  Run: refresh-plugin-live-install.sh $PLUGIN  (plain refresh to converge)" >&2
    POST_FLIGHT_CLEAN=1   # force-pass so the audit row is written and we exit cleanly
elif [[ -x "$DRIFT_PROBE" ]]; then
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
        # .git safety guard: refuse destructive restore when LIVE_PATH is not a git repo.
        # Guards against misconfigured live_path pointing at a broad directory.
        # Note: copy_install entries exit via their own branch above and never reach here —
        # this guard applies only to Default (git-checkout-managed) entries.
        if [[ ! -d "$LIVE_PATH/.git" ]]; then
            echo "refresh-plugin-live-install.sh: ABORT: $LIVE_PATH is not a git repo — refusing rm -rf for safety." >&2
            echo "  Manual recovery: restore from $SNAPSHOT_PATH" >&2
            exit 1
        fi
        # Use cp -r (overlay) for git-checkout-managed restore. The destructive rm-rf+mv
        # pattern left LIVE_PATH absent if mv failed; cp -r keeps LIVE_PATH intact throughout.
        # copy_install uses REPLACE semantics (rm-rf then cp-r) in its own branch above,
        # because a failed copy install may have left orphaned files.
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
    MCP_PID="$(bash "$(dirname "${BASH_SOURCE[0]}")/../lib/spawn-hidden.sh" --stdin-mode=safe "$PYTHON" - "$DOCTOR_SENTINEL" <<'PIDEOF' 2>/dev/null | tr -d '\r'
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
