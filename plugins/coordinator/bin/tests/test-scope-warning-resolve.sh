#!/bin/bash
# Tests for scope-warning-resolve
#
# Usage: bash tests/test-scope-warning-resolve.sh
# Must be run from coordinator/bin/ or with BIN_DIR set.
#
# Creates a temp git repo and synthetic scope-warnings.log files to test
# in-place resolution editing. No permanent side effects.

set -euo pipefail

BIN_DIR="${BIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCRIPT="${BIN_DIR}/scope-warning-resolve"

PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$(( PASS + 1 )); echo "  PASS: $1"; }
fail() { FAIL=$(( FAIL + 1 )); ERRORS+=("$1"); echo "  FAIL: $1"; }

# ---------------------------------------------------------------------------
# Setup: create a temp git repo so git rev-parse --show-toplevel works
# ---------------------------------------------------------------------------
setup_git_repo() {
  local tmpdir
  tmpdir=$(mktemp -d)
  git init -q "$tmpdir"
  mkdir -p "${tmpdir}/.git/coordinator-sessions/test-session-1"
  echo "$tmpdir"
}

# Create a synthetic scope-warnings.log with N lines of pending-resolution
create_log() {
  local log_path="$1"
  cat > "$log_path" <<'LOG'
2026-04-27T10:00:00Z | test-session-1 | foreign-staged | plugins/foo.sh | owner:orphan | pending-resolution
2026-04-27T10:01:00Z | test-session-1 | foreign-staged | plugins/bar.sh | owner:session abc-456 | pending-resolution
2026-04-27T10:02:00Z | test-session-1 | foreign-staged | plugins/baz.sh | owner:orphan | pending-resolution
LOG
}

# ---------------------------------------------------------------------------
echo "=== scope-warning-resolve tests ==="
echo ""

# ---------------------------------------------------------------------------
# Test 1: resolve line 1 as legitimate-mine
# ---------------------------------------------------------------------------
echo "Test 1: resolve line 1 as legitimate-mine"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"

(cd "$REPO" && "$SCRIPT" test-session-1 1 legitimate-mine > /dev/null)
RESULT=$(sed -n '1p' "$LOG")
if echo "$RESULT" | grep -q "legitimate-mine"; then
  pass "line 1 resolution is legitimate-mine"
else
  fail "line 1 should be legitimate-mine, got: $RESULT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 2: resolve line 2 as not-mine-unstaged
# ---------------------------------------------------------------------------
echo "Test 2: resolve line 2 as not-mine-unstaged"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"

(cd "$REPO" && "$SCRIPT" test-session-1 2 not-mine-unstaged > /dev/null)
RESULT=$(sed -n '2p' "$LOG")
if echo "$RESULT" | grep -q "not-mine-unstaged"; then
  pass "line 2 resolution is not-mine-unstaged"
else
  fail "line 2 should be not-mine-unstaged, got: $RESULT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 3: resolve line 3 as not-mine-committed-anyway
# ---------------------------------------------------------------------------
echo "Test 3: resolve line 3 as not-mine-committed-anyway"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"

(cd "$REPO" && "$SCRIPT" test-session-1 3 not-mine-committed-anyway > /dev/null)
RESULT=$(sed -n '3p' "$LOG")
if echo "$RESULT" | grep -q "not-mine-committed-anyway"; then
  pass "line 3 resolution is not-mine-committed-anyway"
else
  fail "line 3 should be not-mine-committed-anyway, got: $RESULT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 4: orphan-claimed resolution
# ---------------------------------------------------------------------------
echo "Test 4: orphan-claimed resolution"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"

(cd "$REPO" && "$SCRIPT" test-session-1 1 orphan-claimed > /dev/null)
RESULT=$(sed -n '1p' "$LOG")
if echo "$RESULT" | grep -q "orphan-claimed"; then
  pass "line 1 resolution is orphan-claimed"
else
  fail "line 1 should be orphan-claimed, got: $RESULT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 5: orphan-rejected resolution
# ---------------------------------------------------------------------------
echo "Test 5: orphan-rejected resolution"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"

(cd "$REPO" && "$SCRIPT" test-session-1 1 orphan-rejected > /dev/null)
RESULT=$(sed -n '1p' "$LOG")
if echo "$RESULT" | grep -q "orphan-rejected"; then
  pass "line 1 resolution is orphan-rejected"
else
  fail "line 1 should be orphan-rejected, got: $RESULT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 6: sibling lines are not modified
# ---------------------------------------------------------------------------
echo "Test 6: sibling lines remain untouched after resolving line 1"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"

(cd "$REPO" && "$SCRIPT" test-session-1 1 legitimate-mine > /dev/null)
LINE2=$(sed -n '2p' "$LOG")
LINE3=$(sed -n '3p' "$LOG")
if echo "$LINE2" | grep -q "pending-resolution" && echo "$LINE3" | grep -q "pending-resolution"; then
  pass "sibling lines still have pending-resolution after resolving line 1"
else
  fail "sibling lines should still be pending-resolution; line2='$LINE2' line3='$LINE3'"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 7: invalid line number (beyond file length) → non-zero exit
# ---------------------------------------------------------------------------
echo "Test 7: invalid line number beyond file length → exit non-zero"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"  # 3 lines

EXIT_CODE=0
(cd "$REPO" && "$SCRIPT" test-session-1 99 legitimate-mine > /dev/null 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "line number 99 (beyond 3-line file) returns non-zero exit"
else
  fail "line number 99 should return non-zero exit, got 0"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 8: invalid resolution code → non-zero exit
# ---------------------------------------------------------------------------
echo "Test 8: invalid resolution code → exit non-zero"
REPO=$(setup_git_repo)
LOG="${REPO}/.git/coordinator-sessions/test-session-1/scope-warnings.log"
create_log "$LOG"

EXIT_CODE=0
(cd "$REPO" && "$SCRIPT" test-session-1 1 not-a-real-resolution > /dev/null 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "invalid resolution 'not-a-real-resolution' returns non-zero exit"
else
  fail "invalid resolution should return non-zero exit, got 0"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 9: missing log file → non-zero exit
# ---------------------------------------------------------------------------
echo "Test 9: missing log file → exit non-zero"
REPO=$(setup_git_repo)
# Do NOT create scope-warnings.log

EXIT_CODE=0
(cd "$REPO" && "$SCRIPT" test-session-1 1 legitimate-mine > /dev/null 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "missing log file returns non-zero exit"
else
  fail "missing log file should return non-zero exit, got 0"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
  echo "Failures:"
  for err in "${ERRORS[@]}"; do
    echo "  - $err"
  done
  exit 1
fi
exit 0
