#!/usr/bin/env bash
# workday-start-cross-repo-memo-surface.test.sh — Smoke tests for the Step 1.45 helper.
#
# Spec backlink: docs/plans/2026-05-21-cross-repo-memo-discoverability.md §Chunk 3
#
# Run: bash ~/.claude/plugins/coordinator/bin/workday-start-cross-repo-memo-surface.test.sh
#
# Tests:
#   1. Empty fixture dir → helper emits nothing, exit 0.
#   2. 1 open memo created today → one line with "(0 days)" age.
#   3. 1 open memo created 10 days ago → one line with "[STALE — receiver hasn't read]".
#   4. 1 reviewed memo with reviewed_at 20 days ago → "[STALE — action pending]".
#   5. 1 action_taken + 1 open → emits only the open memo line.
#   6. 10 open memos → 8 lines + truncation line.
#   7. Pre-cutoff memo (created 2026-05-21, status open) → emits nothing (grandfathered).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/workday-start-cross-repo-memo-surface.sh"

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

# Resolve Python binary — same fallback pattern as the helper itself.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "SKIP: no Python available — cannot run tests"
  exit 0
fi

# Fixture dates: all post-cutoff (2026-05-21). Tests that need staleness use MOCK_TODAY
# to simulate running on a future date — the helper script respects MOCK_TODAY for all
# age/staleness computations.
#
# fixture_today: the "created" date for fresh memos. Must be strictly > 2026-05-21.
fixture_today="2026-05-22"
# Staleness fixture dates: also post-cutoff.
fixture_10d="2026-05-22"   # "created 10 days ago" — use MOCK_TODAY = 2026-06-01 (10 days later)
fixture_20d="2026-05-22"   # "reviewed 20 days ago" — use MOCK_TODAY = 2026-06-11 (20 days later)
# MOCK_TODAY values for staleness tests.
mock_today_10d="2026-06-01"   # 10 days after fixture_10d → triggers open stale (>7d)
mock_today_20d="2026-06-11"   # 20 days after fixture_20d → triggers reviewed stale (>14d)
mock_today_fresh="2026-05-22" # same day as fixture_today → no stale flag

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# write_memo <dir> <filename> <frontmatter-body>
write_memo() {
  local dir="$1" fname="$2" fm="$3"
  printf -- '---\n%s\n---\n\nMemo body.\n' "$fm" > "${dir}/${fname}"
}

assert_output_equals() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    pass "$name"
  else
    fail "$name"
    echo "  expected: $(echo "$expected" | head -3 | sed 's/^/    /')" >&2
    echo "  actual:   $(echo "$actual"   | head -3 | sed 's/^/    /')" >&2
  fi
}

assert_contains() {
  local name="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    pass "$name"
  else
    fail "$name"
    echo "  expected to contain: ${needle}" >&2
    echo "  in: ${haystack}" >&2
  fi
}

assert_not_contains() {
  local name="$1" needle="$2" haystack="$3"
  if ! echo "$haystack" | grep -qF "$needle"; then
    pass "$name"
  else
    fail "$name"
    echo "  expected NOT to contain: ${needle}" >&2
  fi
}

# ---------------------------------------------------------------------------
# Test 1: Empty fixture dir — emits nothing, exits 0
# ---------------------------------------------------------------------------
echo "--- Test 1: empty dir"
tmpdir=$(mktemp -d)
output=$(CROSS_REPO_ARCHIVE_DIR="$tmpdir" bash "$HELPER")
rc=$?
if [[ $rc -eq 0 ]] && [[ -z "$output" ]]; then
  pass "Test 1: empty dir → silent exit 0"
else
  fail "Test 1: expected empty output and exit 0, got rc=$rc output='$output'"
fi
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 2: 1 open memo created at fixture_today — MOCK_TODAY same day → (0 days), no stale flag
# ---------------------------------------------------------------------------
echo "--- Test 2: open memo created today (via MOCK_TODAY)"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2099-01-01-test.md" "title: Test Memo
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_ARCHIVE_DIR="$tmpdir" bash "$HELPER")
assert_contains "Test 2: one line emitted"  "project-rag-em"  "$output"
assert_contains "Test 2: (0 days) in output" "(0 days)"       "$output"
assert_not_contains "Test 2: no stale flag"  "[STALE"         "$output"
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 3: 1 open memo created 10 days before MOCK_TODAY → [STALE — receiver hasn't read]
# ---------------------------------------------------------------------------
echo "--- Test 3: open memo 10 days old (via MOCK_TODAY)"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2099-01-02-test.md" "title: Old Open Memo
from: central-em
to: holodeck-em
created: ${fixture_10d}
status: open"
output=$(MOCK_TODAY="${mock_today_10d}" CROSS_REPO_ARCHIVE_DIR="$tmpdir" bash "$HELPER")
assert_contains "Test 3: stale flag present"  "[STALE — receiver hasn't read]"  "$output"
assert_contains "Test 3: (10 days) in output" "(10 days)"                       "$output"
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 4: 1 reviewed memo with reviewed_at 20 days before MOCK_TODAY → [STALE — action pending]
# ---------------------------------------------------------------------------
echo "--- Test 4: reviewed memo with reviewed_at 20 days ago (via MOCK_TODAY)"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2099-01-03-test.md" "title: Reviewed Stale Memo
from: central-em
to: dronesim-em
created: ${fixture_20d}
status: reviewed
reviewed_at: ${fixture_20d}"
output=$(MOCK_TODAY="${mock_today_20d}" CROSS_REPO_ARCHIVE_DIR="$tmpdir" bash "$HELPER")
assert_contains "Test 4: stale action pending flag" "[STALE — action pending]" "$output"
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 5: 1 action_taken + 1 open → emits only the open memo line
# ---------------------------------------------------------------------------
echo "--- Test 5: action_taken filtered, open surfaced"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2099-01-04-closed.md" "title: Already Done
from: central-em
to: project-rag-em
created: ${fixture_today}
status: action_taken
action_taken_at: ${fixture_today}
decision: accepted"
write_memo "$tmpdir" "2099-01-05-open.md" "title: Still Open
from: central-em
to: holodeck-em
created: ${fixture_today}
status: open"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_ARCHIVE_DIR="$tmpdir" bash "$HELPER")
assert_not_contains "Test 5: action_taken not in output" "Already Done" "$output"
assert_contains     "Test 5: open memo surfaced"          "Still Open"  "$output"
line_count=$(echo "$output" | wc -l | tr -d ' ')
if [[ "$line_count" -eq 1 ]]; then
  pass "Test 5: exactly 1 line in output"
else
  fail "Test 5: expected 1 line, got ${line_count}"
fi
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 6: 10 open memos → 8 lines + truncation line (total 9 output lines)
# ---------------------------------------------------------------------------
echo "--- Test 6: 10 memos truncated to 8 + 1 overflow line"
tmpdir=$(mktemp -d)
for i in $(seq 1 10); do
  write_memo "$tmpdir" "2099-02-$(printf '%02d' "$i")-memo.md" "title: Memo ${i}
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open"
done
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_ARCHIVE_DIR="$tmpdir" bash "$HELPER")
line_count=$(echo "$output" | wc -l | tr -d ' ')
if [[ "$line_count" -eq 9 ]]; then
  pass "Test 6: 9 output lines (8 entries + 1 truncation)"
else
  fail "Test 6: expected 9 lines, got ${line_count}"
fi
assert_contains "Test 6: truncation line present" "(2 more" "$output"
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 7: Pre-cutoff memo (created 2026-05-21, status open) → emits nothing
# ---------------------------------------------------------------------------
echo "--- Test 7: pre-cutoff memo grandfathered"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2026-05-21-legacy.md" "title: Legacy Pre-Lifecycle Memo
from: central-em
to: holodeck-em
created: 2026-05-21
status: open"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_ARCHIVE_DIR="$tmpdir" bash "$HELPER")
rc=$?
if [[ $rc -eq 0 ]] && [[ -z "$output" ]]; then
  pass "Test 7: pre-cutoff memo silently skipped"
else
  fail "Test 7: expected empty output for pre-cutoff memo, got rc=$rc output='$output'"
fi
rm -rf "$tmpdir"

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
