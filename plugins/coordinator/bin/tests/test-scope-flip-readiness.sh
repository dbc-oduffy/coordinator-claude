#!/bin/bash
# Tests for scope-flip-readiness
#
# Usage: bash tests/test-scope-flip-readiness.sh
# Must be run from coordinator/bin/ or with BIN_DIR set.
#
# Synthesizes warn-log fixtures with various pass/fail conditions and verifies
# the predicate fires correctly. No permanent side effects.

set -euo pipefail

BIN_DIR="${BIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SCRIPT="${BIN_DIR}/scope-flip-readiness"

PASS=0
FAIL=0
ERRORS=()

pass() { PASS=$(( PASS + 1 )); echo "  PASS: $1"; }
fail() { FAIL=$(( FAIL + 1 )); ERRORS+=("$1"); echo "  FAIL: $1"; }

setup_git_repo() {
  local tmpdir
  tmpdir=$(mktemp -d)
  git init -q "$tmpdir"
  mkdir -p "${tmpdir}/.git/coordinator-sessions"
  echo "$tmpdir"
}

# Write .warn-mode-enabled-at sentinel with a date N days in the past
write_sentinel() {
  local repo="$1"
  local days_ago="$2"
  local sentinel="${repo}/.git/coordinator-sessions/.warn-mode-enabled-at"
  # Compute timestamp N days ago (GNU date)
  local ts
  ts=$(date -u -d "-${days_ago} days" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
    || date -u -v-${days_ago}d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
    || echo "2026-01-01T00:00:00Z")
  echo "$ts" > "$sentinel"
}

# Write N scope-warning entries for a session, with given resolution
# session_dir is created under .git/coordinator-sessions/<session_id>/
add_warn_entries() {
  local repo="$1"
  local session_id="$2"
  local count="$3"
  local resolution="$4"
  local orphan="${5:-false}"  # if "true", owner field says "orphan"
  local days_ago="${6:-30}"   # timestamp age of entries

  local sdir="${repo}/.git/coordinator-sessions/${session_id}"
  mkdir -p "$sdir"
  local log="${sdir}/scope-warnings.log"

  local ts
  ts=$(date -u -d "-${days_ago} days" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
    || date -u -v-${days_ago}d +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null \
    || echo "2026-01-01T00:00:00Z")

  local owner_label
  if [[ "$orphan" == "true" ]]; then
    owner_label="owner:orphan"
  else
    owner_label="owner:session other-session-xyz"
  fi

  for i in $(seq 1 "$count"); do
    echo "${ts} | ${session_id} | foreign-staged | plugins/file${i}.sh | ${owner_label} | ${resolution}" >> "$log"
  done
}

# ---------------------------------------------------------------------------
echo "=== scope-flip-readiness tests ==="
echo ""

# ---------------------------------------------------------------------------
# Test 1: zero-data case — no logs, no sentinel → NOT-READY, exit 1
# ---------------------------------------------------------------------------
echo "Test 1: zero-data case → NOT-READY"
REPO=$(setup_git_repo)

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "zero-data case exits non-zero (NOT-READY)"
else
  fail "zero-data case should exit non-zero"
fi
if echo "$OUTPUT" | grep -q "NOT-READY"; then
  pass "zero-data case outputs NOT-READY"
else
  fail "zero-data output should contain NOT-READY; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 2: all criteria met → READY, exit 0
# ---------------------------------------------------------------------------
echo "Test 2: all criteria met → READY"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 15  # 15 days ago > 14-day minimum

# 10 sessions, each with 4 resolved warns (0 false positives → 0% FP rate)
for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 4 "not-mine-unstaged" "false" 20
done
# No unresolved orphan warns in trailing 7d

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -eq 0 ]]; then
  pass "all-criteria-met case exits 0 (READY)"
else
  fail "all-criteria-met case should exit 0, got $EXIT_CODE; output: $OUTPUT"
fi
if echo "$OUTPUT" | grep -q "READY"; then
  pass "all-criteria-met case outputs READY"
else
  fail "all-criteria-met output should contain READY; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 3: fewer than 10 sessions → NOT-READY (sessions criterion)
# ---------------------------------------------------------------------------
echo "Test 3: 7 sessions (need 10) → NOT-READY"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 20

for i in $(seq 1 7); do
  add_warn_entries "$REPO" "session-${i}" 5 "not-mine-unstaged" "false" 25
done

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "7-sessions case exits non-zero (NOT-READY)"
else
  fail "7-sessions case should exit non-zero"
fi
if echo "$OUTPUT" | grep -q "Sessions with warns: 7"; then
  pass "7-sessions case shows correct session count"
else
  fail "output should show 'Sessions with warns: 7'; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 4: false-positive rate >= 10% → NOT-READY
# ---------------------------------------------------------------------------
echo "Test 4: FP rate >= 10% → NOT-READY"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 20

# 10 sessions, each with: 1 legitimate-mine (FP) + 5 not-mine-unstaged
# FP rate = 10 / 60 = 16.7%
for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 1 "legitimate-mine" "false" 25
  add_warn_entries "$REPO" "session-${i}" 5 "not-mine-unstaged" "false" 25
done

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "FP-rate-too-high case exits non-zero (NOT-READY)"
else
  fail "FP-rate-too-high case should exit non-zero; got output: $OUTPUT"
fi
if echo "$OUTPUT" | grep -q "False-positive rate"; then
  pass "FP-rate output mentions false-positive rate"
else
  fail "output should mention false-positive rate; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 5: open orphan warns in trailing 7 days → NOT-READY
# ---------------------------------------------------------------------------
echo "Test 5: open orphan warns in trailing 7d → NOT-READY"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 20

for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 5 "not-mine-unstaged" "false" 25
done

# Add an unresolved orphan warn from 3 days ago (within trailing 7d)
add_warn_entries "$REPO" "session-recent" 1 "pending-resolution" "true" 3

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "open-orphan-warn case exits non-zero (NOT-READY)"
else
  fail "open-orphan-warn case should exit non-zero; got output: $OUTPUT"
fi
if echo "$OUTPUT" | grep -qE "Open orphan warns.*[1-9]"; then
  pass "open-orphan-warn case shows non-zero orphan count"
else
  fail "output should show orphan warn count > 0; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 6: soak duration < 14 days → NOT-READY
# ---------------------------------------------------------------------------
echo "Test 6: soak duration 11 days (need 14) → NOT-READY"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 11  # 11 days < 14-day minimum

for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 5 "not-mine-unstaged" "false" 20
done

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "11-day soak exits non-zero (NOT-READY)"
else
  fail "11-day soak should exit non-zero (14-day minimum not met)"
fi
if echo "$OUTPUT" | grep -q "NOT-READY"; then
  pass "11-day soak output says NOT-READY"
else
  fail "output should say NOT-READY; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 7: missing sentinel → NOT-READY, specific message
# ---------------------------------------------------------------------------
echo "Test 7: missing sentinel → NOT-READY with sentinel-not-found message"
REPO=$(setup_git_repo)
# Write 10 sessions with good data but NO sentinel

for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 5 "not-mine-unstaged" "false" 30
done

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  pass "missing-sentinel case exits non-zero (NOT-READY)"
else
  fail "missing-sentinel case should exit non-zero"
fi
if echo "$OUTPUT" | grep -q "sentinel"; then
  pass "missing-sentinel case mentions sentinel"
else
  fail "output should mention missing sentinel; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 8: --json flag produces valid JSON
# ---------------------------------------------------------------------------
echo "Test 8: --json flag produces parseable JSON"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 20

for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 4 "not-mine-unstaged" "false" 25
done

EXIT_CODE=0
JSON_OUTPUT=$(cd "$REPO" && "$SCRIPT" --json 2>&1) || EXIT_CODE=true

# Check it's valid JSON with jq if available
if command -v jq &>/dev/null; then
  if echo "$JSON_OUTPUT" | jq . > /dev/null 2>&1; then
    pass "--json produces valid JSON"
  else
    fail "--json output is not valid JSON: $JSON_OUTPUT"
  fi
  if echo "$JSON_OUTPUT" | jq -e '.ready' > /dev/null 2>&1; then
    pass "--json output has 'ready' field"
  else
    fail "--json output missing 'ready' field; got: $JSON_OUTPUT"
  fi
  if echo "$JSON_OUTPUT" | jq -e '.criteria' > /dev/null 2>&1; then
    pass "--json output has 'criteria' field"
  else
    fail "--json output missing 'criteria' field"
  fi
else
  # jq not available — check for field presence by string match
  if echo "$JSON_OUTPUT" | grep -q '"ready"'; then
    pass "--json output contains 'ready' field (jq unavailable, string check)"
  else
    fail "--json output missing 'ready' field; got: $JSON_OUTPUT"
  fi
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 9: exactly 10 sessions (boundary) → sessions criterion passes
# ---------------------------------------------------------------------------
echo "Test 9: exactly 10 sessions (boundary >= 10) → sessions criterion passes"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 20

for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 3 "not-mine-unstaged" "false" 25
done

OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || true
if echo "$OUTPUT" | grep -q "Sessions with warns: 10"; then
  pass "exactly 10 sessions shows count 10"
else
  fail "exactly-10-sessions should show count 10; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 10: exactly 14 days soak (boundary) → soak criterion passes
# ---------------------------------------------------------------------------
echo "Test 10: exactly 14 days soak (boundary >= 14d) → soak passes"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 14  # exactly 14 days

for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 4 "not-mine-unstaged" "false" 20
done

OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || true
if echo "$OUTPUT" | grep -qE "Soak elapsed: 14d"; then
  pass "14-day soak shows elapsed 14d"
else
  fail "14-day soak should show elapsed 14d; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 11: orphan warn older than 7 days is NOT counted as "open in trailing 7d"
# ---------------------------------------------------------------------------
echo "Test 11: orphan warn > 7 days old is not counted as open-in-7d"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 20

for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 5 "not-mine-unstaged" "false" 25
done

# Add an unresolved orphan warn from 10 days ago (outside trailing 7d)
add_warn_entries "$REPO" "session-old-orphan" 2 "pending-resolution" "true" 10

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
if echo "$OUTPUT" | grep -qE "Open orphan warns in trailing 7d: 0"; then
  pass "old orphan warn (10d ago) not counted in trailing-7d orphan check"
else
  fail "orphan warn from 10 days ago should not count as trailing-7d open; got: $OUTPUT"
fi
rm -rf "$REPO"

# ---------------------------------------------------------------------------
# Test 12: FP rate exactly at 9% (below 10% threshold) → FP criterion passes
# ---------------------------------------------------------------------------
echo "Test 12: FP rate 9.x% (just under 10% threshold) → FP criterion passes"
REPO=$(setup_git_repo)
write_sentinel "$REPO" 20

# 10 sessions. Each has: 1 legitimate-mine + 10 not-mine-unstaged
# FP = 10 / 110 = 9.09% < 10% → should pass
for i in $(seq 1 10); do
  add_warn_entries "$REPO" "session-${i}" 1 "legitimate-mine" "false" 25
  add_warn_entries "$REPO" "session-${i}" 10 "not-mine-unstaged" "false" 25
done

EXIT_CODE=0
OUTPUT=$(cd "$REPO" && "$SCRIPT" 2>&1) || EXIT_CODE=$?
# FP rate should show ✅ (note: terminal emoji may vary; check for passing criterion)
if echo "$OUTPUT" | grep -q "False-positive rate"; then
  pass "FP rate line present in output"
else
  fail "FP rate line missing from output"
fi
# The exit code depends on whether other criteria are met (soak=20d ✅, sessions=10 ✅)
# orphan=0 ✅, FP=9.09% ✅ → should be READY
if [[ $EXIT_CODE -eq 0 ]]; then
  pass "FP rate 9.09% passes the <10% criterion (overall READY)"
else
  fail "With all criteria met including FP 9.09%, should be READY (exit 0); got exit $EXIT_CODE; output: $OUTPUT"
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
