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
ML_DIR="${CLAUDE_DIR}/machine-local"

# ---------------------------------------------------------------------------
# Registry discovery: find the TOML files to inspect
# ---------------------------------------------------------------------------
# Tracked baseline files (git-tracked, not .local.toml)
# Review: code-reviewer — removed unused TRACKED_CONCERN_GLOB variable (F10).
TRACKED_REGISTRY="${ML_DIR}/registry.toml"
# Gitignored per-machine files
LOCAL_REGISTRY="${ML_DIR}/registry.local.toml"

# ---------------------------------------------------------------------------
# Coordinator-owned keys: the canonical set of 8 keys we expect classified.
# repos.* covers the 8 known sibling repos. plugin.mirrors.* is a namespace;
# we check the namespace prefix rather than exact keys since entries are per-plugin.
# ---------------------------------------------------------------------------
COORDINATOR_OWNED_KEYS=(
    "coordinator.python"
    "plugin.mirrors"
    "publish.targets"
    "repos.coordinator_claude"
    "repos.dronesim"
    "repos.project_rag"
    "repos.project_rag_ue_addon"
    "repos.claude_unreal_holodeck"
    "repos.geneva_mvp"
    "repos.fifa_stats"
    "repos.experiments"
)

# ---------------------------------------------------------------------------
# Python script to parse [regeneratability] table from a TOML file.
# Uses stdlib tomllib (Python 3.11+) or tomli fallback. No comment parsing.
# ---------------------------------------------------------------------------
_read_regeneratability_table() {
    local toml_file="$1"
    python3 - "$toml_file" <<'PYEOF'
import sys
import os

toml_file = sys.argv[1]
if not os.path.exists(toml_file):
    sys.exit(0)

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("ERROR: tomllib not available (Python 3.11+ required, or install tomli)", file=sys.stderr)
        sys.exit(0)

with open(toml_file, "rb") as f:
    try:
        data = tomllib.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse {toml_file}: {e}", file=sys.stderr)
        sys.exit(0)

regen = data.get("regeneratability", {})
for k, v in regen.items():
    print(f"{k}\t{v}")
PYEOF
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
        # Review: code-reviewer — third branch was tautological (repos.* exact match already covered
        # by branch 1 exact-key check); per-key design means no namespace glob for repos.* needed.
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
    done < <(python3 - "$LOCAL_REGISTRY" <<'PYEOF'
import sys, os
toml_file = sys.argv[1]
if not os.path.exists(toml_file):
    sys.exit(0)
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)
with open(toml_file, "rb") as f:
    try:
        data = tomllib.load(f)
    except Exception:
        sys.exit(0)
# Flatten top-level keys (not tables)
for k, v in data.items():
    if isinstance(v, str):
        print(f"{k}\t{v}")
PYEOF
)
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
        done < <(python3 - "$f" <<'PYEOF'
import sys, os
toml_file = sys.argv[1]
if not os.path.exists(toml_file):
    sys.exit(0)
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)
with open(toml_file, "rb") as f:
    try:
        data = tomllib.load(f)
    except Exception:
        sys.exit(0)
# Review: code-reviewer — isinstance(v, str) misses array-valued keys (e.g. publish.targets = []);
# not isinstance(v, dict) correctly counts both str and list values as tracked baselines.
for k, v in data.items():
    if not isinstance(v, dict):
        print(f"{k}\t{v}")
PYEOF
)
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
