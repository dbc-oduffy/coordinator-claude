#!/bin/bash
# test-coordinator-daily-branch.sh — Unit tests for coordinator-daily-branch.sh lib
#
# Spec backlink: docs/plans/2026-05-07-daily-branch-doctrine-rethink.md Phase 1
# Covers: AC-1 (case norm), AC-4 (span parsing), AC-5 (should_prompt_rename helper),
#         AC-10 (forward-only legacy tolerance)
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/bin/tests/test-coordinator-daily-branch.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${SCRIPT_DIR}/../../lib/coordinator-daily-branch.sh"

if [[ ! -f "$LIB" ]]; then
  echo "FATAL: lib not found at $LIB" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$LIB"

# ---------------------------------------------------------------------------
# Test framework
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

run_test() {
  local name="$1"
  local fn="$2"
  echo "--- $name"
  if "$fn"; then
    pass "$name"
  else
    fail "$name"
  fi
}

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    return 0
  else
    echo "    Expected: $(printf '%q' "$expected")" >&2
    echo "    Actual:   $(printf '%q' "$actual")" >&2
    return 1
  fi
}

assert_returns() {
  local label="$1" expected_rc="$2"
  shift 2
  local actual_rc=0
  "$@" > /dev/null 2>&1 || actual_rc=$?
  if [[ "$actual_rc" == "$expected_rc" ]]; then
    return 0
  else
    echo "    Expected exit $expected_rc, got $actual_rc for: $*" >&2
    return 1
  fi
}

# ---------------------------------------------------------------------------
# AC-1: cs_compute_machine — always returns lowercase
# ---------------------------------------------------------------------------

test_compute_machine_computername_uppercase() {
  local result
  result=$(COMPUTERNAME="STRIKER" COORDINATOR_MACHINE="" hostname_override=1 \
    bash -c 'source '"$LIB"'; COMPUTERNAME="STRIKER"; unset COORDINATOR_MACHINE; cs_compute_machine')
  assert_eq "COMPUTERNAME uppercase → lowercase" "striker" "$result"
}

test_compute_machine_computername_mixed() {
  local result
  result=$(bash -c 'source '"$LIB"'; COMPUTERNAME="Striker"; unset COORDINATOR_MACHINE; cs_compute_machine')
  assert_eq "COMPUTERNAME mixed-case → lowercase" "striker" "$result"
}

test_compute_machine_coordinator_machine_env_mixed() {
  local result
  result=$(bash -c 'source '"$LIB"'; COORDINATOR_MACHINE="MyMachine"; cs_compute_machine')
  assert_eq "COORDINATOR_MACHINE mixed-case → lowercase" "mymachine" "$result"
}

test_compute_machine_coordinator_machine_env_uppercase() {
  local result
  result=$(bash -c 'source '"$LIB"'; COORDINATOR_MACHINE="WORKSTATION"; cs_compute_machine')
  assert_eq "COORDINATOR_MACHINE uppercase → lowercase" "workstation" "$result"
}

# ---------------------------------------------------------------------------
# AC-4: cs_parse_branch_span — happy paths
# ---------------------------------------------------------------------------

test_parse_single_day() {
  local result
  result=$(cs_parse_branch_span "work/striker/2026-05-07")
  assert_eq "single-day: start=end" "2026-05-07 2026-05-07" "$result"
}

test_parse_two_day_span() {
  local result
  result=$(cs_parse_branch_span "work/striker/2026-05-07to08")
  assert_eq "two-day span" "2026-05-07 2026-05-08" "$result"
}

test_parse_three_day_span() {
  local result
  result=$(cs_parse_branch_span "work/striker/2026-05-06to09")
  assert_eq "three-day span" "2026-05-06 2026-05-09" "$result"
}

test_parse_case_insensitive() {
  local result
  result=$(cs_parse_branch_span "work/STRIKER/2026-05-07")
  assert_eq "case-insensitive machine" "2026-05-07 2026-05-07" "$result"
}

# ---------------------------------------------------------------------------
# AC-4: cs_parse_branch_span — month/year boundary cases (Patrik F4)
# ---------------------------------------------------------------------------

test_parse_month_boundary_may_to_june() {
  local result
  result=$(cs_parse_branch_span "work/striker/2026-05-31to01")
  assert_eq "May→June boundary" "2026-05-31 2026-06-01" "$result"
}

test_parse_month_boundary_dec_to_jan_year_roll() {
  local result
  result=$(cs_parse_branch_span "work/striker/2025-12-31to01")
  assert_eq "Dec→Jan year roll" "2025-12-31 2026-01-01" "$result"
}

test_parse_leap_day_same_month_no_roll() {
  local result
  result=$(cs_parse_branch_span "work/striker/2024-02-28to29")
  assert_eq "leap day Feb-28 to Feb-29 (no roll)" "2024-02-28 2024-02-29" "$result"
}

# ---------------------------------------------------------------------------
# AC-4: cs_parse_branch_span — rejection cases
# ---------------------------------------------------------------------------

test_parse_rejects_feature_foo() {
  assert_returns "rejects feature/foo" 1 cs_parse_branch_span "feature/foo"
}

test_parse_rejects_work_striker_feature_X() {
  assert_returns "rejects work/striker/feature-X" 1 cs_parse_branch_span "work/striker/feature-X"
}

test_parse_rejects_invalid_month() {
  assert_returns "rejects invalid month 13" 1 cs_parse_branch_span "work/striker/2026-13-99"
}

test_parse_rejects_invalid_day_zero() {
  assert_returns "rejects day 00" 1 cs_parse_branch_span "work/striker/2026-05-00"
}

# ---------------------------------------------------------------------------
# AC-4: cs_is_allowed_branch — allow/deny
# ---------------------------------------------------------------------------

test_is_allowed_main() {
  assert_returns "main is allowed" 0 cs_is_allowed_branch "main"
}

test_is_allowed_single_day() {
  assert_returns "single-day branch allowed" 0 cs_is_allowed_branch "work/striker/2026-05-07"
}

test_is_allowed_span() {
  assert_returns "span branch allowed" 0 cs_is_allowed_branch "work/striker/2026-05-07to08"
}

test_is_allowed_legacy_uppercase() {
  # AC-10: existing work/STRIKER/... branches are tolerated (case-insensitive)
  assert_returns "legacy uppercase branch allowed" 0 cs_is_allowed_branch "work/STRIKER/2026-05-07"
}

test_is_denied_feature_foo() {
  assert_returns "feature/foo denied" 1 cs_is_allowed_branch "feature/foo"
}

test_is_denied_work_striker_feature() {
  assert_returns "work/striker/feature-X denied" 1 cs_is_allowed_branch "work/striker/feature-X"
}

# ---------------------------------------------------------------------------
# cs_is_canonical_branch — strict (creation-time) oracle for HEAD-vs-on-disk
# case-mismatch prevention. See lib comment for rationale.
# ---------------------------------------------------------------------------

test_is_canonical_main() {
  assert_returns "main is canonical" 0 cs_is_canonical_branch "main"
}

test_is_canonical_lowercase_single_day() {
  assert_returns "lowercase single-day canonical" 0 cs_is_canonical_branch "work/striker/2026-05-07"
}

test_is_canonical_lowercase_span() {
  assert_returns "lowercase span canonical" 0 cs_is_canonical_branch "work/striker/2026-05-07to08"
}

test_is_not_canonical_uppercase_machine() {
  assert_returns "uppercase machine NOT canonical" 1 cs_is_canonical_branch "work/STRIKER/2026-05-07"
}

test_is_not_canonical_mixed_machine() {
  assert_returns "mixed-case machine NOT canonical" 1 cs_is_canonical_branch "work/Striker/2026-05-07"
}

test_is_not_canonical_uppercase_span_suffix() {
  assert_returns "uppercase TO suffix NOT canonical" 1 cs_is_canonical_branch "work/striker/2026-05-07TO08"
}

test_is_not_canonical_uppercase_span_machine() {
  assert_returns "uppercase machine in span NOT canonical" 1 cs_is_canonical_branch "work/STRIKER/2026-05-07to08"
}

test_is_not_canonical_feature_foo() {
  # Not allowed at all → not canonical either.
  assert_returns "feature/foo NOT canonical" 1 cs_is_canonical_branch "feature/foo"
}

# ---------------------------------------------------------------------------
# cs_format_span_suffix
# ---------------------------------------------------------------------------

test_format_same_day() {
  local result
  result=$(cs_format_span_suffix "2026-05-07" "2026-05-07")
  assert_eq "same-day: no suffix" "2026-05-07" "$result"
}

test_format_next_day() {
  local result
  result=$(cs_format_span_suffix "2026-05-07" "2026-05-08")
  assert_eq "next-day: to08 suffix" "2026-05-07to08" "$result"
}

test_format_three_day() {
  local result
  result=$(cs_format_span_suffix "2026-05-07" "2026-05-09")
  assert_eq "three-day: to09 suffix" "2026-05-07to09" "$result"
}

# ---------------------------------------------------------------------------
# Round-trip: format → parse → re-format
# ---------------------------------------------------------------------------

test_roundtrip_same_day() {
  local start="2026-05-07"
  local today="2026-05-07"
  local formatted
  formatted=$(cs_format_span_suffix "$start" "$today")
  local parsed
  parsed=$(cs_parse_branch_span "work/striker/${formatted}")
  local parsed_start parsed_end
  parsed_start="${parsed%% *}"
  parsed_end="${parsed##* }"
  local reformatted
  reformatted=$(cs_format_span_suffix "$parsed_start" "$parsed_end")
  assert_eq "round-trip same-day" "$formatted" "$reformatted"
}

test_roundtrip_span() {
  local start="2026-05-07"
  local today="2026-05-08"
  local formatted
  formatted=$(cs_format_span_suffix "$start" "$today")
  local parsed
  parsed=$(cs_parse_branch_span "work/striker/${formatted}")
  local parsed_start parsed_end
  parsed_start="${parsed%% *}"
  parsed_end="${parsed##* }"
  local reformatted
  reformatted=$(cs_format_span_suffix "$parsed_start" "$parsed_end")
  assert_eq "round-trip two-day span" "$formatted" "$reformatted"
}

# ---------------------------------------------------------------------------
# AC-5: cs_should_prompt_rename
# ---------------------------------------------------------------------------

# Helper: epoch for N hours ago
epoch_hours_ago() {
  local h="$1"
  echo $(( $(date +%s) - h * 3600 ))
}

test_should_prompt_yesterday_active() {
  # work/striker/2026-05-06, today=2026-05-07, last-commit <24h ago → should prompt (return 0)
  local epoch
  epoch=$(epoch_hours_ago 2)  # 2h ago — within 24h
  local rc=0
  cs_should_prompt_rename "work/striker/2026-05-06" "2026-05-07" "$epoch" || rc=$?
  assert_eq "yesterday active → prompt (rc=0)" "0" "$rc"
}

test_should_not_prompt_already_in_span() {
  # work/striker/2026-05-06to07, today=2026-05-07, last-commit <24h → already in span (return 1)
  local epoch
  epoch=$(epoch_hours_ago 2)
  local rc=0
  cs_should_prompt_rename "work/striker/2026-05-06to07" "2026-05-07" "$epoch" || rc=$?
  assert_eq "already in span → no prompt (rc=1)" "1" "$rc"
}

test_should_not_prompt_stale_branch() {
  # work/striker/2026-05-04, today=2026-05-07, last-commit >48h → stale, A/B/C (return 1)
  local epoch
  epoch=$(epoch_hours_ago 75)  # 75h ago — older than 48h
  local rc=0
  cs_should_prompt_rename "work/striker/2026-05-04" "2026-05-07" "$epoch" || rc=$?
  assert_eq "stale branch → no prompt (rc=1)" "1" "$rc"
}

# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

echo "=== coordinator-daily-branch.sh unit tests ==="
echo ""

run_test "cs_compute_machine: COMPUTERNAME uppercase → lowercase" test_compute_machine_computername_uppercase
run_test "cs_compute_machine: COMPUTERNAME mixed-case → lowercase" test_compute_machine_computername_mixed
run_test "cs_compute_machine: COORDINATOR_MACHINE env mixed → lowercase" test_compute_machine_coordinator_machine_env_mixed
run_test "cs_compute_machine: COORDINATOR_MACHINE env uppercase → lowercase" test_compute_machine_coordinator_machine_env_uppercase

run_test "cs_parse_branch_span: single-day" test_parse_single_day
run_test "cs_parse_branch_span: two-day span" test_parse_two_day_span
run_test "cs_parse_branch_span: three-day span" test_parse_three_day_span
run_test "cs_parse_branch_span: case-insensitive machine" test_parse_case_insensitive
run_test "cs_parse_branch_span: month boundary May→June" test_parse_month_boundary_may_to_june
run_test "cs_parse_branch_span: year roll Dec→Jan" test_parse_month_boundary_dec_to_jan_year_roll
run_test "cs_parse_branch_span: leap day Feb-28→Feb-29 no roll" test_parse_leap_day_same_month_no_roll
run_test "cs_parse_branch_span: rejects feature/foo" test_parse_rejects_feature_foo
run_test "cs_parse_branch_span: rejects work/striker/feature-X" test_parse_rejects_work_striker_feature_X
run_test "cs_parse_branch_span: rejects invalid month 13" test_parse_rejects_invalid_month
run_test "cs_parse_branch_span: rejects day 00" test_parse_rejects_invalid_day_zero

run_test "cs_is_allowed_branch: main" test_is_allowed_main
run_test "cs_is_allowed_branch: single-day" test_is_allowed_single_day
run_test "cs_is_allowed_branch: span" test_is_allowed_span
run_test "cs_is_allowed_branch: legacy uppercase (AC-10)" test_is_allowed_legacy_uppercase
run_test "cs_is_allowed_branch: rejects feature/foo" test_is_denied_feature_foo
run_test "cs_is_allowed_branch: rejects work/striker/feature-X" test_is_denied_work_striker_feature

run_test "cs_is_canonical_branch: main" test_is_canonical_main
run_test "cs_is_canonical_branch: lowercase single-day" test_is_canonical_lowercase_single_day
run_test "cs_is_canonical_branch: lowercase span" test_is_canonical_lowercase_span
run_test "cs_is_canonical_branch: uppercase machine NOT canonical" test_is_not_canonical_uppercase_machine
run_test "cs_is_canonical_branch: mixed-case machine NOT canonical" test_is_not_canonical_mixed_machine
run_test "cs_is_canonical_branch: uppercase TO suffix NOT canonical" test_is_not_canonical_uppercase_span_suffix
run_test "cs_is_canonical_branch: uppercase machine in span NOT canonical" test_is_not_canonical_uppercase_span_machine
run_test "cs_is_canonical_branch: feature/foo NOT canonical" test_is_not_canonical_feature_foo

run_test "cs_format_span_suffix: same-day" test_format_same_day
run_test "cs_format_span_suffix: next-day" test_format_next_day
run_test "cs_format_span_suffix: three-day" test_format_three_day

run_test "round-trip: format→parse→re-format same-day" test_roundtrip_same_day
run_test "round-trip: format→parse→re-format span" test_roundtrip_span

run_test "cs_should_prompt_rename: yesterday active → prompt" test_should_prompt_yesterday_active
run_test "cs_should_prompt_rename: already in span → no-op" test_should_not_prompt_already_in_span
run_test "cs_should_prompt_rename: stale → no-op" test_should_not_prompt_stale_branch

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
if (( FAIL > 0 )); then
  echo ""
  echo "Failed tests:"
  for m in "${FAIL_MSGS[@]}"; do echo "  - $m"; done
  exit 1
fi
exit 0
