#!/usr/bin/env bash
# generate-repomap.sh — thin wrapper around the Python repomap generator.
#
# Purpose: run generate-repomap.py with default arguments. Contains NO RAG-gating
# logic — callers gate via bin/check-rag-state.sh before invoking this script.
# Full gating doctrine: docs/wiki/repomap-rag-gating.md
#
# Spec backlink: docs/plans/2026-05-09-skill-consolidation-pass.md § T2
#
# Usage:
#   generate-repomap.sh [<args passed through to the python generator>]
#
# With no arguments, runs with defaults:
#   --project-root .  --budget 4000  --profile balanced
#
# With arguments, passes them verbatim to the python generator (user args take
# full precedence — defaults are not merged).
#
# Exit codes:
#   0 — generator ran successfully
#   1 — generator script not found at any of the three searched locations
#   N — generator's own exit code on failure
#
# Negative spec: this script does NOT gate on RAG state. Call check-rag-state.sh
# before this script if gating is desired.

set -euo pipefail

# ── Locate the generator ─────────────────────────────────────────────────────
# 3-tier resolution: (1) plugin-relative canonical path (coordinator/bin/repomap/);
# (2) legacy meta-repo global install (~/.claude/.github/scripts/); (3) repo-local
# fallback for un-migrated boxes. Tiers 2-3 are intentional legacy bridges.
_plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# shellcheck source=../lib/coordinator-trusted-root-guard.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/coordinator-trusted-root-guard.sh"
coordinator_trusted_root_guard --mode=fail-loud --root="$_plugin_root" --site="$0"
GENERATOR="${_plugin_root}/bin/repomap/generate-repomap.py"
if [ ! -f "$GENERATOR" ]; then
    GENERATOR="$HOME/.claude/.github/scripts/generate-repomap.py"
fi
if [ ! -f "$GENERATOR" ]; then
    GENERATOR=".github/scripts/generate-repomap.py"
fi

if [ ! -f "$GENERATOR" ]; then
    echo "ERROR: generate-repomap.py not found." >&2
    echo "  Expected (tier 1): ${_plugin_root}/bin/repomap/generate-repomap.py" >&2
    echo "  Fallback (tier 2, legacy): $HOME/.claude/.github/scripts/generate-repomap.py" >&2
    echo "  Fallback  (tier 3): .github/scripts/generate-repomap.py" >&2
    echo "  Install the coordinator-claude plugin or run the setup script." >&2
    exit 1
fi

# ── Resolve Python interpreter ───────────────────────────────────────────────
# Windows hosts often ship `python` or `py` rather than `python3`. Respect an
# explicit PYTHON= override; otherwise probe python3 → python → py -3.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then PYTHON=python3
    elif command -v python  >/dev/null 2>&1; then PYTHON=python
    elif command -v py      >/dev/null 2>&1; then PYTHON="py -3"
    else
        echo "ERROR: no python interpreter found (tried python3, python, py)." >&2
        echo "  Set PYTHON=<path> to pin explicitly." >&2
        exit 1
    fi
fi

# Build interpreter array at resolution time. IFS=' ' read -ra avoids glob expansion
# (unlike the bare PYTHON_CMD=($PYTHON) form) while still splitting on spaces for the
# "py -3" two-token Windows case. exec later expands safely via "${PYTHON_CMD[@]}"
# without re-splitting (safe for space-containing paths).
IFS=' ' read -ra PYTHON_CMD <<< "$PYTHON"

# ── Run the generator ────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    # Default invocation
    exec "${PYTHON_CMD[@]}" "$GENERATOR" --project-root "${PROJECT_ROOT:-.}" --budget 4000 --profile balanced # verify-no-console-flash: allow — on-demand repomap generator, not session-hot-path
else
    # User arguments take full precedence — pass through verbatim
    exec "${PYTHON_CMD[@]}" "$GENERATOR" "$@" # verify-no-console-flash: allow — on-demand repomap generator, not session-hot-path
fi
