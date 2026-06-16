#!/usr/bin/env bash
# workday-complete-step1-validate.test.sh — Smoke tests for the Step 1 gate helper.
#
# Spec backlink: commands/workday-complete.md §Step 1
# Model: bin/workday-start-cross-repo-memo-surface.test.sh
#
# Run: bash ~/.claude/plugins/coordinator/bin/workday-complete-step1-validate.test.sh
#
# Tests:
#   1. UBT absent + no fast-test config         → RC_UBT=skipped RC_VALIDATE=skipped, exit 0.
#   2. UBT absent + fake command exits 0         → RC_UBT=skipped RC_VALIDATE=0, exit 0.
#   3. UBT absent + fake command exits 1 + "error: compile" in output → exit 2 (build failure).
#   4. UBT absent + fake command exits 1 + test-only output → exit 3 (test failure).
#   5. Idempotency: run tests 1 and 2 twice; assert identical stdout + exit codes.

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/workday-complete-step1-validate.sh"

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

# Cleanup registry — accumulate mktemp dirs, clean them all at exit.
_TMPDIRS=()
cleanup() {
  for d in "${_TMPDIRS[@]+"${_TMPDIRS[@]}"}"; do
    rm -rf "$d"
  done
}
trap cleanup EXIT

make_tmpdir() {
  local d
  d=$(mktemp -d)
  _TMPDIRS+=("$d")
  echo "$d"
}

# run_helper <env-pairs...>
# Invokes the helper with the given env settings. The caller MUST cd to a
# temp dir that does NOT contain bin/check-ubt-build-fresh.sh so the UBT
# gate is always skipped in these tests (UBT presence-detection is cwd-relative).
# Returns: sets _OUT (stdout), _RC (exit code).
run_helper() {
  local env_pairs=("$@")
  set +e
  # env(1) is POSIX and available on all platforms; avoids export pollution.
  _OUT=$(cd "$_CWD" && env "${env_pairs[@]}" "$BASH" "$HELPER" 2>/dev/null)
  _RC=$?
  set -e
}

# ---------------------------------------------------------------------------
# Test 1: UBT absent + no fast-test config → RC_UBT=skipped RC_VALIDATE=skipped, exit 0
# ---------------------------------------------------------------------------
echo "--- Test 1: UBT absent, no fast-test config → skipped/skipped, exit 0"
_CWD=$(make_tmpdir)

# Ensure no COORDINATOR_FAST_TEST_CMD leaks in from the caller's environment.
run_helper "COORDINATOR_FAST_TEST_CMD="

_expected="RC_UBT=skipped RC_VALIDATE=skipped"
if [[ "$_OUT" == "$_expected" ]]; then
  pass "Test 1: stdout matches '$_expected'"
else
  fail "Test 1: stdout mismatch — expected '$_expected', got '$_OUT'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 1: exit 0"
else
  fail "Test 1: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 2: UBT absent + COORDINATOR_FAST_TEST_CMD=true (exits 0) → RC_VALIDATE=0, exit 0
#
# Stub mechanism: the resolver lib (coordinator-resolve-validation-cmd.sh) checks
# COORDINATOR_FAST_TEST_CMD first (Step 1 of its three-step resolution). Setting
# COORDINATOR_FAST_TEST_CMD=true means `bash -c "true"` runs and exits 0.
# This is the documented env-var override path; no lib patching needed.
# ---------------------------------------------------------------------------
echo "--- Test 2: UBT absent + COORDINATOR_FAST_TEST_CMD=true → RC_VALIDATE=0, exit 0"
_CWD=$(make_tmpdir)

run_helper "COORDINATOR_FAST_TEST_CMD=true" "COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1"

_expected="RC_UBT=skipped RC_VALIDATE=0"
if [[ "$_OUT" == "$_expected" ]]; then
  pass "Test 2: stdout matches '$_expected'"
else
  fail "Test 2: stdout mismatch — expected '$_expected', got '$_OUT'"
fi
if [[ $_RC -eq 0 ]]; then
  pass "Test 2: exit 0"
else
  fail "Test 2: expected exit 0, got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 3: UBT absent + fake command exits 1 with "error: compile" in output
#         → RC_VALIDATE=1, exit 2 (build failure classification)
#
# Stub: write a small script to a tmpdir that exits 1 and prints a build-error
# line, then pass it via COORDINATOR_FAST_TEST_CMD.
# ---------------------------------------------------------------------------
echo "--- Test 3: UBT absent, fake command exits 1 + build error → exit 2"
_CWD=$(make_tmpdir)
_ft_script="${_CWD}/fake-test-build-fail.sh"
cat >"$_ft_script" <<'STUB'
#!/usr/bin/env bash
echo "error: compile failed in src/main.cpp"
exit 1
STUB
chmod +x "$_ft_script"

run_helper "COORDINATOR_FAST_TEST_CMD=$_ft_script"

_expected="RC_UBT=skipped RC_VALIDATE=1"
if [[ "$_OUT" == "$_expected" ]]; then
  pass "Test 3: stdout matches '$_expected'"
else
  fail "Test 3: stdout mismatch — expected '$_expected', got '$_OUT'"
fi
if [[ $_RC -eq 2 ]]; then
  pass "Test 3: exit 2 (build failure)"
else
  fail "Test 3: expected exit 2 (build failure), got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 4: UBT absent + fake command exits 1 with test-failure output only
#         → RC_VALIDATE=1, exit 3 (test failure, NOT build failure)
#
# Output deliberately contains no "error:" / "BUILD FAILED" / "Compilation" patterns.
# ---------------------------------------------------------------------------
echo "--- Test 4: UBT absent, fake command exits 1 + test-only output → exit 3"
_CWD=$(make_tmpdir)
_ft_script="${_CWD}/fake-test-only-fail.sh"
cat >"$_ft_script" <<'STUB'
#!/usr/bin/env bash
echo "FAIL: test_addition expected 4 got 5"
echo "FAIL: test_subtraction expected 0 got 1"
echo "2 tests failed"
exit 1
STUB
chmod +x "$_ft_script"

run_helper "COORDINATOR_FAST_TEST_CMD=$_ft_script"

_expected="RC_UBT=skipped RC_VALIDATE=1"
if [[ "$_OUT" == "$_expected" ]]; then
  pass "Test 4: stdout matches '$_expected'"
else
  fail "Test 4: stdout mismatch — expected '$_expected', got '$_OUT'"
fi
if [[ $_RC -eq 3 ]]; then
  pass "Test 4: exit 3 (test failure, not build failure)"
else
  fail "Test 4: expected exit 3 (test failure), got $_RC"
fi

# ---------------------------------------------------------------------------
# Test 5: Idempotency — run tests 1 and 2 twice; assert identical stdout + exit codes
# ---------------------------------------------------------------------------
echo "--- Test 5: Idempotency"

# 5a: idempotency for the no-config case (based on Test 1)
_CWD=$(make_tmpdir)
run_helper "COORDINATOR_FAST_TEST_CMD="
_out_run1="$_OUT"
_rc_run1=$_RC

run_helper "COORDINATOR_FAST_TEST_CMD="
_out_run2="$_OUT"
_rc_run2=$_RC

if [[ "$_out_run1" == "$_out_run2" ]]; then
  pass "Test 5a: idempotent stdout (no-config case)"
else
  fail "Test 5a: stdout differs between runs — run1='$_out_run1' run2='$_out_run2'"
fi
if [[ $_rc_run1 -eq $_rc_run2 ]]; then
  pass "Test 5a: idempotent exit code (no-config case)"
else
  fail "Test 5a: exit code differs — run1=$_rc_run1 run2=$_rc_run2"
fi

# 5b: idempotency for the passing fast-test case (based on Test 2)
_CWD=$(make_tmpdir)
run_helper "COORDINATOR_FAST_TEST_CMD=true" "COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1"
_out_run1="$_OUT"
_rc_run1=$_RC

run_helper "COORDINATOR_FAST_TEST_CMD=true" "COORDINATOR_FAST_TEST_CMD_SUPPRESS_METACHAR_WARN=1"
_out_run2="$_OUT"
_rc_run2=$_RC

if [[ "$_out_run1" == "$_out_run2" ]]; then
  pass "Test 5b: idempotent stdout (passing fast-test case)"
else
  fail "Test 5b: stdout differs between runs — run1='$_out_run1' run2='$_out_run2'"
fi
if [[ $_rc_run1 -eq $_rc_run2 ]]; then
  pass "Test 5b: idempotent exit code (passing fast-test case)"
else
  fail "Test 5b: exit code differs — run1=$_rc_run1 run2=$_rc_run2"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ ${#FAIL_MSGS[@]} -gt 0 ]]; then
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
  exit 1
fi
exit 0
