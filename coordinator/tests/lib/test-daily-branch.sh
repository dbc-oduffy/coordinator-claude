#!/usr/bin/env bash
# test-daily-branch.sh — Tests for coordinator-daily-branch.sh helpers.
#
# Purpose: verifies cs_rename_target — the midnight-rename target-name selection
# (workday-start Step 0 Check 4). The load-bearing behavior: a 0-ahead branch
# must NOT inherit a {start}to{today} span (the history has merged; the span
# would advertise WIP that no longer exists), but a >0-ahead branch must keep
# the span to carry genuine multi-day WIP forward.
#
# Spec backlink: docs/wiki/daily-branch-discipline.md § Honest-name rule
#
# Run: bash ~/.claude/plugins/coordinator/tests/lib/test-daily-branch.sh

# -e intentionally omitted: (( PASS++ )) returns non-zero when the counter was 0
# before the increment, which would abort under -e. Same rationale as the
# sibling test-resolve-validation-cmd.sh.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../../lib/coordinator-daily-branch.sh"

if [[ ! -f "$LIB" ]]; then
  echo "FATAL: lib not found at $LIB" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$LIB"

PASS=0
FAIL=0
FAIL_MSGS=()
pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() { echo "  FAIL: $1"; FAIL_MSGS+=("$1"); (( FAIL++ )) || true; }

# assert_eq <label> <expected> <actual>
assert_eq() {
  if [[ "$2" == "$3" ]]; then pass "$1 → $3"; else fail "$1: expected '$2', got '$3'"; fi
}

echo "--- cs_rename_target"

# 0-ahead, crossed a day boundary: span would be misleading → today-only.
assert_eq "0-ahead crossing midnight collapses to today-only" \
  "work/machine-a/2026-06-02" \
  "$(cs_rename_target machine-a 2026-06-01 2026-06-02 0)"

# 0-ahead, multi-day-old start (history all merged) → today-only, span dropped.
assert_eq "0-ahead drops a multi-day span entirely" \
  "work/machine-a/2026-06-02" \
  "$(cs_rename_target machine-a 2026-05-31 2026-06-02 0)"

# 0-ahead, start already today (no boundary) → today-only.
assert_eq "0-ahead same-day stays today-only" \
  "work/machine-a/2026-06-02" \
  "$(cs_rename_target machine-a 2026-06-02 2026-06-02 0)"

# >0-ahead crossing midnight: genuine WIP → span suffix carried forward.
assert_eq "1-ahead crossing midnight keeps the span" \
  "work/machine-a/2026-06-01to02" \
  "$(cs_rename_target machine-a 2026-06-01 2026-06-02 1)"

# >0-ahead, multi-day span with genuine WIP → full start-to-today span.
assert_eq "5-ahead keeps the multi-day span" \
  "work/machine-a/2026-05-31to02" \
  "$(cs_rename_target machine-a 2026-05-31 2026-06-02 5)"

# >0-ahead but start == today → cs_format_span_suffix collapses to single date.
assert_eq "ahead but same-day yields single date (no spurious span)" \
  "work/machine-a/2026-06-02" \
  "$(cs_rename_target machine-a 2026-06-02 2026-06-02 3)"

# Non-integer commits_ahead fails loud rather than silently picking 0-ahead.
if cs_rename_target machine-a 2026-06-01 2026-06-02 "abc" >/dev/null 2>&1; then
  fail "non-integer commits_ahead should return non-zero"
else
  pass "non-integer commits_ahead fails loud"
fi

# Empty commits_ahead fails loud (bash would otherwise treat '' as 0).
if cs_rename_target machine-a 2026-06-01 2026-06-02 "" >/dev/null 2>&1; then
  fail "empty commits_ahead should return non-zero"
else
  pass "empty commits_ahead fails loud"
fi

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
  echo ""
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do echo "  - $msg"; done
  exit 1
fi
exit 0
