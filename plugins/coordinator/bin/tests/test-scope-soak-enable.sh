#!/bin/bash
# Tests for scope-soak-enable
#
# Usage: bash tests/test-scope-soak-enable.sh
# Must be run from coordinator/bin/ or with BIN_DIR set.

set -euo pipefail

BIN_DIR="${BIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCRIPT="${BIN_DIR}/scope-soak-enable"

PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$(( PASS + 1 )); echo "  PASS: $1"; }
fail() { FAIL=$(( FAIL + 1 )); ERRORS+=("$1"); echo "  FAIL: $1"; }

setup_git_repo() {
  local tmpdir
  tmpdir=$(mktemp -d)
  git init -q "$tmpdir"
  echo "$tmpdir"
}

# ---------------------------------------------------------------------------
echo "=== scope-soak-enable tests ==="
echo ""

# ---------------------------------------------------------------------------
# Test 1: creates sentinel when not present
# ---------------------------------------------------------------------------
echo "Test 1: creates sentinel when not present"
REPO=$(setup_git_repo)

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT") || EXIT_CODE=$?
SENTINEL="${REPO}/.git/coordinator-sessions/.warn-mode-enabled-at"

if [[ -f "$SENTINEL" ]]; then
  pass "sentinel file created"
else
  fail "sentinel file was not created at ${SENTINEL}"
fi
if [[ $EXIT_CODE -eq 0 ]]; then
  pass "exit code 0 on first run"
else
  fail "exit code should be 0 on first run, got $EXIT_CODE"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 2: sentinel contains valid ISO timestamp
# ---------------------------------------------------------------------------
echo "Test 2: sentinel contains a valid ISO timestamp"
REPO=$(setup_git_repo)
(cd "$REPO" && "$SCRIPT" > /dev/null)
SENTINEL="${REPO}/.git/coordinator-sessions/.warn-mode-enabled-at"
TS=$(cat "$SENTINEL")
if echo "$TS" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'; then
  pass "sentinel contains ISO 8601 UTC timestamp"
else
  fail "sentinel timestamp format invalid: '$TS'"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 3: idempotent — second run does not overwrite sentinel
# ---------------------------------------------------------------------------
echo "Test 3: idempotent — second run does not overwrite existing sentinel"
REPO=$(setup_git_repo)
(cd "$REPO" && "$SCRIPT" > /dev/null)
SENTINEL="${REPO}/.git/coordinator-sessions/.warn-mode-enabled-at"
FIRST_TS=$(cat "$SENTINEL")

sleep 1  # ensure clock would differ if overwritten

OUTPUT2=$(cd "$REPO" && "$SCRIPT")
SECOND_TS=$(cat "$SENTINEL")

if [[ "$FIRST_TS" == "$SECOND_TS" ]]; then
  pass "sentinel timestamp unchanged on second run (idempotent)"
else
  fail "sentinel was overwritten: first='$FIRST_TS' second='$SECOND_TS'"
fi
if echo "$OUTPUT2" | grep -qi "already"; then
  pass "second run output says 'already started'"
else
  fail "second run should mention sentinel already exists"
fi
rm -rf "$REPO"

rm -f "${BIN_DIR}/tests/.gitkeep" 2>/dev/null || true

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
