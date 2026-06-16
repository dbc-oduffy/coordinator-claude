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
#   1 — generator script not found at either known location
#   N — generator's own exit code on failure
#
# Negative spec: this script does NOT gate on RAG state. Call check-rag-state.sh
# before this script if gating is desired.

set -euo pipefail

# ── Locate the generator ─────────────────────────────────────────────────────
# Prefer global install; fall back to project-local legacy path.
GENERATOR="$HOME/.claude/.github/scripts/generate-repomap.py"
if [ ! -f "$GENERATOR" ]; then
    GENERATOR=".github/scripts/generate-repomap.py"
fi

if [ ! -f "$GENERATOR" ]; then
    echo "ERROR: generate-repomap.py not found." >&2
    echo "  Expected: $HOME/.claude/.github/scripts/generate-repomap.py" >&2
    echo "  Fallback: .github/scripts/generate-repomap.py" >&2
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

# ── Run the generator ────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    # Default invocation
    exec $PYTHON "$GENERATOR" --project-root "${PROJECT_ROOT:-.}" --budget 4000 --profile balanced # verify-no-console-flash: allow — on-demand repomap generator, not session-hot-path
else
    # User arguments take full precedence — pass through verbatim
    exec $PYTHON "$GENERATOR" "$@" # verify-no-console-flash: allow — on-demand repomap generator, not session-hot-path
fi
