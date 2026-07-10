#!/usr/bin/env bash
# bin/check-machine-local-regeneratability.sh — Machine-local registry regeneratability observer
#
# Purpose: POST-HOC OFFER (exit 0 always). Reads the [regeneratability] TOML table
# from the machine-local registry and flags:
#   (1) Any session-accumulated-must-survive-crash entry that lives ONLY in a gitignored
#       *.local.toml with no tracked baseline or idempotent regenerator — this is an
#       install-surface-completeness defect.
#   (2) Any coordinator-owned key absent from the [regeneratability] table (unclassified-key
#       warning).
#
# Spec backlink: docs/plans/2026-06-22-invariant-verification-observers.md § C1
# Offer shape: exit 0 always; findings to stderr; silent on clean.
#
# Cross-platform: bash >= 4 + BSD coreutils; see CLAUDE.md § Cross-platform shell.

if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    echo "ERROR: bash >= 4 required (found ${BASH_VERSION:-unknown}). Install via homebrew: brew install bash" >&2
    exit 0
fi

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Resolve claude home (CLAUDE_HOME > HOME > USERPROFILE fallback)
# ---------------------------------------------------------------------------
_resolve_claude_dir() {
    local home_base
    if [[ -n "${CLAUDE_HOME:-}" ]]; then
        home_base="$CLAUDE_HOME"
    elif [[ -n "${HOME:-}" ]]; then
        home_base="$HOME"
    elif [[ -n "${USERPROFILE:-}" ]]; then
        home_base="$USERPROFILE"
    else
        echo "ERROR: Cannot resolve HOME for machine-local registry lookup" >&2
        echo ""
        return
    fi
    echo "${home_base}/.claude"
}

CLAUDE_DIR="$(_resolve_claude_dir)"
if [[ -z "$CLAUDE_DIR" ]]; then
    echo "check-machine-local-regeneratability: CLAUDE_DIR is empty (HOME/CLAUDE_HOME/USERPROFILE unresolved) — skipping checks" >&2
    exit 0
fi
ML_DIR="${CLAUDE_DIR}/machine-local"

# ---------------------------------------------------------------------------
# Registry discovery: find the TOML files to inspect
# ---------------------------------------------------------------------------
# Tracked baseline files (git-tracked, not .local.toml)
TRACKED_REGISTRY="${ML_DIR}/registry.toml"
# Gitignored per-machine files
LOCAL_REGISTRY="${ML_DIR}/registry.local.toml"

# ---------------------------------------------------------------------------
# Coordinator-owned keys: the canonical set of keys we expect classified.
# Derived from the repos.* declarations in machine-local/registry.toml.
# plugin.mirrors.* is a namespace; we check the prefix rather than exact keys
# since entries are per-plugin (set per-machine via `machine-local set`).
# ---------------------------------------------------------------------------
COORDINATOR_OWNED_KEYS=(
    "coordinator.python"
    "plugin.mirrors"
    "publish.targets"
    "repos.example-sim-repo"
    "repos.project_rag"
    "repos.project_rag_ue_addon"
    "repos.example_game_workbench_repo"
    "repos.example_repo"
    "repos.example_stats_repo"
    "repos.example_league_data_repo"
    "repos.experiments"
    "repos.example_cockpit_repo"
    "repos.example-os-repo"
)

# ---------------------------------------------------------------------------
# Shared Python helper — parametric TOML reader (DRY: one tomllib import block).
# Modes: "regen" → [regeneratability] sub-table; "flat_str" → top-level str
# values only; "flat_nondict" → top-level non-table values (str + list).
# verify-no-console-flash: allow — one-shot TOML-parse helper; not on Windows hot-path
# ---------------------------------------------------------------------------
_TOML_HELPER=$(mktemp "${TMPDIR:-/tmp}/ml_regen_toml_helper.XXXXXX.py")
trap 'rm -f "$_TOML_HELPER"' EXIT
cat > "$_TOML_HELPER" <<'PYEOF'
import sys, os

mode = sys.argv[1]   # "regen" | "flat_str" | "flat_nondict"
toml_file = sys.argv[2] if len(sys.argv) > 2 else None

if not toml_file or not os.path.exists(toml_file):
    sys.exit(0)

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        if mode == "regen":
            print("ERROR: tomllib not available (Python 3.11+ required, or install tomli)", file=sys.stderr)
        sys.exit(0)

with open(toml_file, "rb") as f:
    try:
        data = tomllib.load(f)
    except Exception as e:
        if mode == "regen":
            print(f"ERROR: Failed to parse {toml_file}: {e}", file=sys.stderr)
        sys.exit(0)

if mode == "regen":
    regen = data.get("regeneratability", {})
    for k, v in regen.items():
        print(f"{k}\t{v}")
elif mode == "flat_str":
    for k, v in data.items():
        if isinstance(v, str):
            print(f"{k}\t{v}")
elif mode == "flat_nondict":
    # flat_nondict counts both str and list values as tracked baselines
    for k, v in data.items():
        if not isinstance(v, dict):
            print(f"{k}\t{v}")
PYEOF

_read_regeneratability_table() {
    local toml_file="$1"
    python3 "$_TOML_HELPER" regen "$toml_file"
}

# ---------------------------------------------------------------------------
# Collect ALL [regeneratability] table entries across all tracked files
# ---------------------------------------------------------------------------
declare -A REGEN_TABLE  # key -> value

_load_regen_from_file() {
    local f="$1"
    [[ -f "$f" ]] || return 0
    while IFS=$'\t' read -r key val; do
        [[ -n "$key" ]] && REGEN_TABLE["$key"]="$val"
    done < <(_read_regeneratability_table "$f")
}

# Load from tracked registry files only (not .local.toml)
if [[ -d "$ML_DIR" ]]; then
    for f in "${ML_DIR}"/*.toml; do
        [[ -f "$f" ]] || continue
        # Skip .local.toml files — regeneratability table lives in tracked baseline
        case "$f" in
            *.local.toml) continue ;;
        esac
        _load_regen_from_file "$f"
    done
fi

# ---------------------------------------------------------------------------
# Check 1: Unclassified coordinator-owned keys
# ---------------------------------------------------------------------------
FINDINGS=0

for canon_key in "${COORDINATOR_OWNED_KEYS[@]}"; do
    found=0
    for regen_key in "${!REGEN_TABLE[@]}"; do
        # Match exact key or namespace prefix (e.g. "plugin.mirrors" matches "plugin.mirrors.coordinator-claude")
        if [[ "$regen_key" == "$canon_key" ]] || \
           [[ "$canon_key" == "plugin.mirrors" && "$regen_key" == plugin.mirrors.* ]]; then
            found=1
            break
        fi
    done
    if [[ "$found" -eq 0 ]]; then
        echo "WARN [check-machine-local-regeneratability]: Key '${canon_key}' is coordinator-owned but absent from [regeneratability] table." >&2
        echo "     Offer: add an entry to the [regeneratability] table in registry.toml:" >&2
        echo "       \"${canon_key}\" = \"idempotent-regeneratable|session-accumulated-must-survive-crash|ephemeral\"" >&2
        echo "     See docs/wiki/machine-local-registry.md § Regeneratability Classification for the three-value enum." >&2
        FINDINGS=$((FINDINGS + 1))
    fi
done

# ---------------------------------------------------------------------------
# Check 2: session-accumulated-must-survive-crash entries in gitignored .local.toml only
# ---------------------------------------------------------------------------
# A key is "at risk" if:
#   - Its regeneratability is session-accumulated-must-survive-crash
#   - It exists ONLY in registry.local.toml (gitignored) with no declaration in tracked files
# This is an install-surface-completeness defect.

# Collect keys in .local.toml
declare -A LOCAL_KEYS  # key -> value

if [[ -f "$LOCAL_REGISTRY" ]]; then
    while IFS=$'\t' read -r key val; do
        [[ -n "$key" ]] && LOCAL_KEYS["$key"]="$val"
    done < <(python3 "$_TOML_HELPER" flat_str "$LOCAL_REGISTRY")
fi

# Collect keys in tracked files
declare -A TRACKED_KEYS  # key -> 1 (present)

if [[ -d "$ML_DIR" ]]; then
    for f in "${ML_DIR}"/*.toml; do
        [[ -f "$f" ]] || continue
        case "$f" in
            *.local.toml) continue ;;
        esac
        while IFS=$'\t' read -r key _val; do
            [[ -n "$key" ]] && TRACKED_KEYS["$key"]=1
        done < <(python3 "$_TOML_HELPER" flat_nondict "$f")
    done
fi

# Now flag session-accumulated-must-survive-crash keys that are ONLY in .local.toml
for key in "${!REGEN_TABLE[@]}"; do
    val="${REGEN_TABLE[$key]}"
    if [[ "$val" == "session-accumulated-must-survive-crash" ]]; then
        # Check if key exists in a tracked file — if so, there IS a tracked baseline declaration
        in_tracked="${TRACKED_KEYS[$key]:-0}"
        # Check if key exists in .local.toml (gitignored)
        in_local="${LOCAL_KEYS[$key]:-}"
        # For repos.* keys: probe the path-resolution ladder before flagging as a gap.
        # rc=0 from `machine-local get` means rung-2 autodiscovery (or another ladder rung)
        # can derive the value on a fresh-machine clone — NOT a manual-re-entry gap.
        # Only flag repos.* keys that the ladder cannot resolve AND have no tracked baseline.
        if [[ "$key" == repos.* ]]; then
            if "${CLAUDE_DIR}/bin/machine-local" get "$key" >/dev/null 2>&1; then
                continue  # ladder resolves it — not an install-surface-completeness gap
            fi
        fi
        if [[ "$in_tracked" != "1" ]] && [[ -n "$in_local" ]]; then
            echo "WARN [check-machine-local-regeneratability]: '${key}' is classified session-accumulated-must-survive-crash" >&2
            echo "     but has no declaration in any tracked registry file — only in gitignored registry.local.toml." >&2
            echo "     This is an install-surface-completeness defect: a fresh-machine clone will not have this value." >&2
            echo "     Offer: Add a tracked baseline declaration in registry.toml (empty-value is sufficient):" >&2
            echo "       machine-local set --global \"${key}\" \"\"  # then document the regeneration path" >&2
            echo "     See docs/wiki/install-surface-completeness.md § Bootstrap gap: machine-local/ is not created" >&2
            echo "     by any current installer." >&2
            FINDINGS=$((FINDINGS + 1))
        fi
    fi
done

# Exit 0 always (offer-shaped, never blocking)
exit 0
