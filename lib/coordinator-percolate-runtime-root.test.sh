#!/usr/bin/env bash
# coordinator-percolate-runtime-root.test.sh — unit tests for coordinator-percolate-runtime-root.sh
#
# Coverage:
#   T1  $COORDINATOR_PERCOLATE_ROOT set + setup/publish.sh present
#         → prints value, returns 0
#   T2  mode 2 (repo-local) — cwd git root has setup/publish.sh, env unset
#         → prints git root, returns 0
#   T3  mode 3 (shared install) — CLAUDE_HOME/.claude/setup/publish.sh present
#         → prints CLAUDE_HOME/.claude, returns 0
#   T4  none present → fail-loud, returns 1, stderr carries remediation
#
# Self-contained: creates temp dirs/git repos, restores env between cases.
# Exits 0 if all pass, 1 if any fail.

set -euo pipefail
# Distinguish a harness abort (broken fixture, missing binary) from a counted
# test failure — both would otherwise exit 1.
trap 'echo "HARNESS ABORT (unexpected error at line $LINENO) — not a counted test failure" >&2; exit 2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_FILE="$SCRIPT_DIR/coordinator-percolate-runtime-root.sh"

PASS=0
FAIL=0

_pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
_fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL+1)); }

echo "=== coordinator-percolate-runtime-root.test.sh ==="

if [[ ! -f "$LIB_FILE" ]]; then
    echo "FATAL: lib not found at $LIB_FILE" >&2
    exit 1
fi

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# Ensure a clean env going into each case.
unset COORDINATOR_PERCOLATE_ROOT 2>/dev/null || true
unset CLAUDE_HOME 2>/dev/null || true

# ---------------------------------------------------------------------------
# T1: $COORDINATOR_PERCOLATE_ROOT set → rung 1 short-circuit
# ---------------------------------------------------------------------------
echo "--- T1: COORDINATOR_PERCOLATE_ROOT set with setup/publish.sh → returns it"

T1_ROOT="$TMPROOT/t1-root"
mkdir -p "$T1_ROOT/setup"
touch "$T1_ROOT/setup/publish.sh"

T1_OUT=$(
    COORDINATOR_PERCOLATE_ROOT="$T1_ROOT" \
    bash -c "unset CLAUDE_HOME 2>/dev/null; cd /tmp; source '$LIB_FILE'; coordinator_percolate_runtime_root"
)
T1_RC=$?

if [[ "$T1_OUT" == "$T1_ROOT" && "$T1_RC" -eq 0 ]]; then
    _pass "T1 env-var rung output and return code"
else
    _fail "T1 env-var rung output and return code" "got rc=$T1_RC out='$T1_OUT'"
fi

# ---------------------------------------------------------------------------
# T2: mode 2 (repo-local) — cwd git root has setup/publish.sh, env unset
# ---------------------------------------------------------------------------
echo "--- T2: repo-local git root with setup/publish.sh, env unset → returns git root"

T2_REPO="$TMPROOT/t2-repo"
mkdir -p "$T2_REPO/setup"
touch "$T2_REPO/setup/publish.sh"
( cd "$T2_REPO" && git init -q )

# Resolve the canonical (symlink-free) git-root path the same way the lib
# does, so the comparison isn't defeated by /tmp → /private/tmp on macOS.
T2_EXPECTED=$(cd "$T2_REPO" && git rev-parse --show-toplevel 2>/dev/null)

T2_OUT=$(
    bash -c "
        unset COORDINATOR_PERCOLATE_ROOT 2>/dev/null
        unset CLAUDE_HOME 2>/dev/null
        cd '$T2_REPO'
        source '$LIB_FILE'
        coordinator_percolate_runtime_root
    "
)
T2_RC=$?

if [[ "$T2_OUT" == "$T2_EXPECTED" && "$T2_RC" -eq 0 ]]; then
    _pass "T2 repo-local rung output and return code"
else
    _fail "T2 repo-local rung output and return code" "got rc=$T2_RC out='$T2_OUT' expected='$T2_EXPECTED'"
fi

# ---------------------------------------------------------------------------
# T3: mode 3 (shared install) — CLAUDE_HOME/.claude/setup/publish.sh present
# ---------------------------------------------------------------------------
echo "--- T3: shared-install CLAUDE_HOME/.claude/setup/publish.sh, others unset → returns CLAUDE_HOME/.claude"

T3_CLAUDE_HOME="$TMPROOT/t3-home"
mkdir -p "$T3_CLAUDE_HOME/.claude/setup"
touch "$T3_CLAUDE_HOME/.claude/setup/publish.sh"

# Run from a non-git cwd (TMPROOT itself is not a git repo) so rung 2 misses.
T3_OUT=$(
    CLAUDE_HOME="$T3_CLAUDE_HOME" \
    bash -c "
        unset COORDINATOR_PERCOLATE_ROOT 2>/dev/null
        cd '$TMPROOT'
        source '$LIB_FILE'
        coordinator_percolate_runtime_root
    "
)
T3_RC=$?

T3_EXPECTED="$T3_CLAUDE_HOME/.claude"
if [[ "$T3_OUT" == "$T3_EXPECTED" && "$T3_RC" -eq 0 ]]; then
    _pass "T3 shared-install rung output and return code"
else
    _fail "T3 shared-install rung output and return code" "got rc=$T3_RC out='$T3_OUT' expected='$T3_EXPECTED'"
fi

# ---------------------------------------------------------------------------
# T4: none present → fail-loud, return 1
# ---------------------------------------------------------------------------
echo "--- T4: no rung resolves → returns 1, stderr carries remediation"

T4_STDERR="$TMPROOT/t4-stderr.txt"
T4_EMPTY_HOME="$TMPROOT/t4-empty-home"
mkdir -p "$T4_EMPTY_HOME"

# Use || to capture the expected rc=1 without triggering the ERR trap.
T4_RC=0
CLAUDE_HOME="$T4_EMPTY_HOME" bash -c "
    unset COORDINATOR_PERCOLATE_ROOT 2>/dev/null
    cd '$TMPROOT'
    source '$LIB_FILE'
    coordinator_percolate_runtime_root
" >"$TMPROOT/t4-stdout.txt" 2>"$T4_STDERR" || T4_RC=$?

if [[ "$T4_RC" -eq 1 ]]; then
    _pass "T4 fail-loud returns 1"
else
    _fail "T4 fail-loud returns 1" "got rc=$T4_RC"
fi

T4_STDERR_CONTENT="$(cat "$T4_STDERR")"
if printf '%s' "$T4_STDERR_CONTENT" | grep -q "PERCOLATE_ROOT"; then
    _pass "T4 stderr contains remediation"
else
    _fail "T4 stderr contains remediation" "got stderr: '$T4_STDERR_CONTENT'"
fi

# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -gt 0 ]] && exit 1
exit 0
