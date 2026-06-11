#!/usr/bin/env bash
# test-resolve-validation-cmd.sh — Tests for coordinator-resolve-validation-cmd.sh
#
# Purpose: verifies the five AC cases for cs_resolve_fast_test_cmd — env-var precedence,
# local-md fallback, skip-with-notice, no-conventional-fallback (the Staff Engineer F1), and
# exit-code passthrough semantics (the Staff Engineer F5). Also verifies the four cs_resolve_full_test_cmd
# cases (Tests 6-9): env-var, full_test_cmd: key, fast-tier fallback (exit 3), and
# both-tiers-unconfigured (exit 2).
#
# Spec backlink: archive/specs/2026-05-28-workday-complete-fast-test-resolution.md § 5
#
# Run: bash ~/.claude/plugins/coordinator/tests/lib/test-resolve-validation-cmd.sh

# Note: -e intentionally omitted. (( PASS++ )) and (( FAIL++ )) exit non-zero when
# the post-increment evaluates to 0 (i.e., counter was 0 before the increment), and
# the `|| true` guards on those lines rely on -e being OFF. Adding -e would silently
# break the counters at the first PASS/FAIL.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../../lib/coordinator-resolve-validation-cmd.sh"

if [[ ! -f "$LIB" ]]; then
  echo "FATAL: lib not found at $LIB" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Minimal test framework (matching test_probe_cwd_project_rag_relevance.sh pattern)
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
TMP_ROOTS=()

make_tmp_dir() {
  local d
  d=$(mktemp -d)
  TMP_ROOTS+=("$d")
  echo "$d"
}

# Write a coordinator.local.md with the given fast_test_cmd value to the given dir.
write_local_md_with_cmd() {
  local dir="$1"
  local cmd_val="$2"
  cat > "$dir/coordinator.local.md" <<EOF
---
project_type: test
fast_test_cmd: "$cmd_val"
---
EOF
}

# Write a coordinator.local.md WITHOUT fast_test_cmd.
write_local_md_without_cmd() {
  local dir="$1"
  cat > "$dir/coordinator.local.md" <<'EOF'
---
project_type: test
---
EOF
}

cleanup() {
  for d in "${TMP_ROOTS[@]}"; do
    rm -rf "$d"
  done
}
trap cleanup EXIT

# Run cs_resolve_fast_test_cmd with the lib sourced in a clean subshell.
# $1 = repo_root (passed as first arg to the function)
# Additional env vars injected via env(1) by callers.
# Sets STDOUT, STDERR, EXIT_CODE in the calling scope — caller MUST consume all
# three before the next run_resolver call, otherwise stale values shadow silently.
run_resolver() {
  local repo_root="$1"
  shift
  # "$@" are NAME=VALUE pairs to prepend as environment overrides
  local tmp_out tmp_err
  tmp_out=$(mktemp)
  tmp_err=$(mktemp)
  TMP_ROOTS+=("$tmp_out" "$tmp_err")

  env "$@" bash -c "
    source $(printf '%q' "$LIB")
    cs_resolve_fast_test_cmd $(printf '%q' "$repo_root")
  " >"$tmp_out" 2>"$tmp_err"
  EXIT_CODE=$?
  STDOUT=$(cat "$tmp_out")
  STDERR=$(cat "$tmp_err")
}

# ---------------------------------------------------------------------------
# Test 1: env_var_wins
# COORDINATOR_FAST_TEST_CMD="echo HELLO" + coordinator.local.md with different cmd
# → stdout = "echo HELLO", exit 0
# ---------------------------------------------------------------------------
echo "--- Test 1: env_var_wins"

T1=$(make_tmp_dir)
write_local_md_with_cmd "$T1" "python other.py"

run_resolver "$T1" "COORDINATOR_FAST_TEST_CMD=echo HELLO"

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "env_var_wins: exit 0"
else
  fail "env_var_wins: expected exit 0, got $EXIT_CODE"
fi

if [[ "$STDOUT" == "echo HELLO" ]]; then
  pass "env_var_wins: stdout = 'echo HELLO'"
else
  fail "env_var_wins: expected stdout 'echo HELLO', got '$STDOUT'"
fi

if echo "$STDERR" | grep -q 'step=env-var'; then
  pass "env_var_wins: stderr names step=env-var"
else
  fail "env_var_wins: expected step=env-var in stderr, got '$STDERR'"
fi

# Confirm the local.md value was NOT used
if [[ "$STDOUT" == *"python other.py"* ]]; then
  fail "env_var_wins: local.md value leaked into stdout (env var should win)"
else
  pass "env_var_wins: local.md value not in stdout"
fi

# ---------------------------------------------------------------------------
# Test 2: local_md_wins_when_no_env
# env var unset, coordinator.local.md has fast_test_cmd: "python foo.py"
# → stdout = "python foo.py", exit 0
# ---------------------------------------------------------------------------
echo "--- Test 2: local_md_wins_when_no_env"

T2=$(make_tmp_dir)
write_local_md_with_cmd "$T2" "python foo.py"

# Pass env var set to empty string — resolver's `[[ -n "${VAR:-}" ]]` guard treats
# empty-string as unset-equivalent, so this exercises the local-md fallback path.
# (If the guard ever changed to `[[ -v VAR ]]`, this test would break — that's intentional.)
run_resolver "$T2" "COORDINATOR_FAST_TEST_CMD="

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "local_md_wins_when_no_env: exit 0"
else
  fail "local_md_wins_when_no_env: expected exit 0, got $EXIT_CODE"
fi

if [[ "$STDOUT" == "python foo.py" ]]; then
  pass "local_md_wins_when_no_env: stdout = 'python foo.py'"
else
  fail "local_md_wins_when_no_env: expected 'python foo.py', got '$STDOUT'"
fi

if echo "$STDERR" | grep -q 'step=local-md'; then
  pass "local_md_wins_when_no_env: stderr names step=local-md"
else
  fail "local_md_wins_when_no_env: expected step=local-md in stderr, got '$STDERR'"
fi

# ---------------------------------------------------------------------------
# Test 3: skip_with_notice
# env var unset, no coordinator.local.md → exit 2, stderr names both remediation paths
# ---------------------------------------------------------------------------
echo "--- Test 3: skip_with_notice"

T3=$(make_tmp_dir)
# No coordinator.local.md written

run_resolver "$T3" "COORDINATOR_FAST_TEST_CMD="

if [[ "$EXIT_CODE" -eq 2 ]]; then
  pass "skip_with_notice: exit 2"
else
  fail "skip_with_notice: expected exit 2, got $EXIT_CODE"
fi

if [[ -z "$STDOUT" ]]; then
  pass "skip_with_notice: stdout empty"
else
  fail "skip_with_notice: expected empty stdout, got '$STDOUT'"
fi

if echo "$STDERR" | grep -q 'COORDINATOR_FAST_TEST_CMD'; then
  pass "skip_with_notice: stderr names COORDINATOR_FAST_TEST_CMD remediation"
else
  fail "skip_with_notice: expected COORDINATOR_FAST_TEST_CMD in stderr, got '$STDERR'"
fi

if echo "$STDERR" | grep -q 'coordinator.local.md'; then
  pass "skip_with_notice: stderr names coordinator.local.md remediation"
else
  fail "skip_with_notice: expected coordinator.local.md in stderr, got '$STDERR'"
fi

# ---------------------------------------------------------------------------
# Test 4: no_conventional_fallback  (the Staff Engineer F1 acceptance)
# env unset, no coordinator.local.md, but .github/scripts/run-all-checks.py present
# → STILL exit 2 (skip-with-notice), does NOT print conventional script path
# ---------------------------------------------------------------------------
echo "--- Test 4: no_conventional_fallback"

T4=$(make_tmp_dir)
# Create the conventional script in the tmp dir (simulates it being present at repo root)
mkdir -p "$T4/.github/scripts"
echo "#!/usr/bin/env python3" > "$T4/.github/scripts/run-all-checks.py"

run_resolver "$T4" "COORDINATOR_FAST_TEST_CMD="

if [[ "$EXIT_CODE" -eq 2 ]]; then
  pass "no_conventional_fallback: exit 2 (skip, not 0)"
else
  fail "no_conventional_fallback: expected exit 2, got $EXIT_CODE (conventional script must NOT be a fallback)"
fi

if [[ -z "$STDOUT" ]]; then
  pass "no_conventional_fallback: stdout empty (conventional script not resolved)"
else
  fail "no_conventional_fallback: expected empty stdout, got '$STDOUT' (conventional fallback fired when it should not have)"
fi

if echo "$STDOUT$STDERR" | grep -q 'run-all-checks'; then
  fail "no_conventional_fallback: conventional script path appeared in output — F1 violated"
else
  pass "no_conventional_fallback: conventional script path absent from output"
fi

# ---------------------------------------------------------------------------
# Test 5: configured_cmd_exit_code_passthrough  (the Staff Engineer F5 acceptance)
# coordinator.local.md declares fast_test_cmd: "exit 42"
# → resolver resolves and exits 0; caller captures exit 42 at runtime
# The resolver does NOT pre-parse or probe the command string.
# ---------------------------------------------------------------------------
echo "--- Test 5: configured_cmd_exit_code_passthrough"

T5=$(make_tmp_dir)
write_local_md_with_cmd "$T5" "exit 42"

run_resolver "$T5" "COORDINATOR_FAST_TEST_CMD="

if [[ "$EXIT_CODE" -eq 0 ]]; then
  pass "configured_cmd_exit_code_passthrough: resolver exits 0"
else
  fail "configured_cmd_exit_code_passthrough: expected resolver exit 0 (not pre-running command), got $EXIT_CODE"
fi

if [[ "$STDOUT" == "exit 42" ]]; then
  pass "configured_cmd_exit_code_passthrough: stdout = 'exit 42' (command passed through verbatim)"
else
  fail "configured_cmd_exit_code_passthrough: expected stdout 'exit 42', got '$STDOUT'"
fi

# Confirm resolver did NOT execute the command (if it had, the subshell would exit 42,
# but we already checked EXIT_CODE=0 above — this is belt-and-suspenders)
if echo "$STDERR" | grep -q 'step=local-md'; then
  pass "configured_cmd_exit_code_passthrough: stderr names step=local-md (resolved, not executed)"
else
  fail "configured_cmd_exit_code_passthrough: expected step=local-md in stderr, got '$STDERR'"
fi

# ---------------------------------------------------------------------------
# cs_resolve_full_test_cmd helpers + tests (Tests 6-9)
# ---------------------------------------------------------------------------

# Write a coordinator.local.md with BOTH keys (fast + full distinct values).
# printf (not an unquoted heredoc) so a `$`/backtick in a fixture value stays literal.
write_local_md_with_both_cmds() {
  local dir="$1" fast_val="$2" full_val="$3"
  {
    printf '%s\n' '---' 'project_type: test'
    printf 'fast_test_cmd: "%s"\n' "$fast_val"
    printf 'full_test_cmd: "%s"\n' "$full_val"
    printf '%s\n' '---'
  } > "$dir/coordinator.local.md"
}

# Same as run_resolver but calls cs_resolve_full_test_cmd.
run_full_resolver() {
  local repo_root="$1"
  shift
  local tmp_out tmp_err
  tmp_out=$(mktemp)
  tmp_err=$(mktemp)
  TMP_ROOTS+=("$tmp_out" "$tmp_err")
  env "$@" bash -c "
    source $(printf '%q' "$LIB")
    cs_resolve_full_test_cmd $(printf '%q' "$repo_root")
  " >"$tmp_out" 2>"$tmp_err"
  EXIT_CODE=$?
  STDOUT=$(cat "$tmp_out")
  STDERR=$(cat "$tmp_err")
}

# Test 6: full_env_var_wins — COORDINATOR_FULL_TEST_CMD beats both local.md keys.
echo "--- Test 6: full_env_var_wins"
T6=$(make_tmp_dir)
write_local_md_with_both_cmds "$T6" "fast.py" "full.py"
run_full_resolver "$T6" "COORDINATOR_FULL_TEST_CMD=echo FULL"
if [[ "$EXIT_CODE" -eq 0 ]]; then pass "full_env_var_wins: exit 0"; else fail "full_env_var_wins: expected 0, got $EXIT_CODE"; fi
if [[ "$STDOUT" == "echo FULL" ]]; then pass "full_env_var_wins: stdout = 'echo FULL'"; else fail "full_env_var_wins: expected 'echo FULL', got '$STDOUT'"; fi
if echo "$STDERR" | grep -qF '[cs_resolve_full_test_cmd] step=env-var'; then pass "full_env_var_wins: stderr names full env-var step"; else fail "full_env_var_wins: missing full env-var step, got '$STDERR'"; fi

# Test 7: full_local_md_key_wins — full_test_cmd: used; fast_test_cmd: ignored.
echo "--- Test 7: full_local_md_key_wins"
T7=$(make_tmp_dir)
write_local_md_with_both_cmds "$T7" "fast.py" "full.py"
run_full_resolver "$T7" "COORDINATOR_FULL_TEST_CMD=" "COORDINATOR_FAST_TEST_CMD="
if [[ "$EXIT_CODE" -eq 0 ]]; then pass "full_local_md_key_wins: exit 0"; else fail "full_local_md_key_wins: expected 0, got $EXIT_CODE"; fi
if [[ "$STDOUT" == "full.py" ]]; then pass "full_local_md_key_wins: stdout = 'full.py'"; else fail "full_local_md_key_wins: expected 'full.py', got '$STDOUT'"; fi
if [[ "$STDOUT" == *"fast.py"* ]]; then fail "full_local_md_key_wins: fast value leaked"; else pass "full_local_md_key_wins: fast value not used"; fi

# Test 8: full_falls_back_to_fast — no full_test_cmd, fast_test_cmd present → exit 3, fast cmd on stdout.
echo "--- Test 8: full_falls_back_to_fast"
T8=$(make_tmp_dir)
write_local_md_with_cmd "$T8" "fast-only.py"
run_full_resolver "$T8" "COORDINATOR_FULL_TEST_CMD=" "COORDINATOR_FAST_TEST_CMD="
if [[ "$EXIT_CODE" -eq 3 ]]; then pass "full_falls_back_to_fast: exit 3 (fallback signal)"; else fail "full_falls_back_to_fast: expected 3, got $EXIT_CODE"; fi
if [[ "$STDOUT" == "fast-only.py" ]]; then pass "full_falls_back_to_fast: stdout = fast cmd"; else fail "full_falls_back_to_fast: expected 'fast-only.py', got '$STDOUT'"; fi
if echo "$STDERR" | grep -q 'fast-fallback'; then pass "full_falls_back_to_fast: stderr names fast-fallback caveat"; else fail "full_falls_back_to_fast: missing fast-fallback caveat, got '$STDERR'"; fi
# Documented dual-stderr shape (Finding 6): the inner fast resolver's own diagnostic also fires.
if echo "$STDERR" | grep -q 'cs_resolve_fast_test_cmd.*step=local-md'; then pass "full_falls_back_to_fast: inner fast-resolver diagnostic also present"; else fail "full_falls_back_to_fast: expected inner fast step=local-md diagnostic, got '$STDERR'"; fi

# Test 9: full_unconfigured_both_tiers — neither key, no env → exit 2.
echo "--- Test 9: full_unconfigured_both_tiers"
T9=$(make_tmp_dir)
write_local_md_without_cmd "$T9"
run_full_resolver "$T9" "COORDINATOR_FULL_TEST_CMD=" "COORDINATOR_FAST_TEST_CMD="
if [[ "$EXIT_CODE" -eq 2 ]]; then pass "full_unconfigured_both_tiers: exit 2"; else fail "full_unconfigured_both_tiers: expected 2, got $EXIT_CODE"; fi
if [[ -z "$STDOUT" ]]; then pass "full_unconfigured_both_tiers: stdout empty"; else fail "full_unconfigured_both_tiers: expected empty stdout, got '$STDOUT'"; fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ "$FAIL" -gt 0 ]]; then
  echo ""
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - $msg"
  done
  exit 1
fi

exit 0
