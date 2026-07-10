#!/usr/bin/env bash
# workday-start-cross-repo-memo-surface.test.sh — Smoke tests for the Step 1.45 helper.
#
# Spec backlink: docs/plans/2026-05-21-cross-repo-memo-discoverability.md §Chunk 3
# Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md §C4 (kind banding)
#
# Run: bash ~/.claude/plugins/coordinator/bin/workday-start-cross-repo-memo-surface.test.sh
#
# Tests:
#   1. Empty fixture dir → helper emits nothing, exit 0.
#   2. 1 open memo created today → one line with "(0 days)" age.
#   3. 1 open memo created 10 days ago → one line with "[STALE — awaiting your action]".
#   4. 1 open memo 20 days old → "[STALE — awaiting your action]".
#   5. 1 actioned + 1 open → emits only the open memo line.
#   6. 10 open memos → 8 lines + truncation line.
#   7. Pre-cutoff memo (created 2026-05-21, status open) → emits nothing (grandfathered).
#   8. Mixed inbox (ask/consult/fyi) → ask+consult surface ABOVE fyi; fyi gets [fyi] marker.
#   9. Memo with no kind field → bands as ask (urgent, no [fyi] marker).
#  10. Memo title containing literal | pipe character — line still parses, kind detected.
#  11. proposal kind → surfaces before fyi (urgent band), no [fyi] marker.

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
output=$(CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
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
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
assert_contains "Test 2: one line emitted"  "Test Memo"       "$output"
assert_contains "Test 2: 0 days in output"   "0 days old"     "$output"
assert_not_contains "Test 2: no stale flag"  "[STALE"         "$output"
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 3: 1 open memo created 10 days before MOCK_TODAY → [STALE — receiver hasn't read]
# ---------------------------------------------------------------------------
echo "--- Test 3: open memo 10 days old (via MOCK_TODAY)"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2099-01-02-test.md" "title: Old Open Memo
from: central-em
to: example-game-repo-em
created: ${fixture_10d}
status: open"
output=$(MOCK_TODAY="${mock_today_10d}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
assert_contains "Test 3: stale flag present"  "[STALE — awaiting your action]"  "$output"
assert_contains "Test 3: 10 days in output"   "10 days old"                    "$output"
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 4: 1 open memo 20 days old → [STALE — awaiting your action]
# ---------------------------------------------------------------------------
echo "--- Test 4: open memo 20 days old (via MOCK_TODAY)"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2099-01-03-test.md" "title: Long Stale Memo
from: central-em
to: example-sim-repo-em
created: ${fixture_20d}
status: open"
output=$(MOCK_TODAY="${mock_today_20d}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
assert_contains "Test 4: stale flag present"    "[STALE — awaiting your action]" "$output"
assert_contains "Test 4: 20 days in output"     "20 days old"                   "$output"
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
to: example-game-repo-em
created: ${fixture_today}
status: open"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
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
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
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
to: example-game-repo-em
created: 2026-05-21
status: open"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
rc=$?
if [[ $rc -eq 0 ]] && [[ -z "$output" ]]; then
  pass "Test 7: pre-cutoff memo silently skipped"
else
  fail "Test 7: expected empty output for pre-cutoff memo, got rc=$rc output='$output'"
fi
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 8: Mixed inbox (ask/consult/fyi) — ask+consult surface ABOVE fyi
#   Verifies: (a) band ordering ask/consult before fyi, (b) [fyi] marker on fyi line,
#   (c) no [fyi] marker on ask/consult lines.
# Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md §C4
# ---------------------------------------------------------------------------
echo "--- Test 8: kind banding — ask+consult before fyi"
tmpdir=$(mktemp -d)
# Write fyi first so alphabetical filename order would surface it first without banding.
write_memo "$tmpdir" "2099-03-01-fyi.md" "title: FYI Notification
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open
kind: fyi"
write_memo "$tmpdir" "2099-03-02-consult.md" "title: Consult Request
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open
kind: consult"
write_memo "$tmpdir" "2099-03-03-ask.md" "title: Action Request
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open
kind: ask"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
# ask and consult should appear before fyi in output
line_ask=$(echo "$output" | grep -n "Action Request" | cut -d: -f1)
line_consult=$(echo "$output" | grep -n "Consult Request" | cut -d: -f1)
line_fyi=$(echo "$output" | grep -n "FYI Notification" | cut -d: -f1)
if [[ -n "$line_ask" ]] && [[ -n "$line_fyi" ]] && [[ "$line_ask" -lt "$line_fyi" ]]; then
  pass "Test 8: ask surfaces before fyi"
else
  fail "Test 8: ask surfaces before fyi (ask_line=${line_ask} fyi_line=${line_fyi})"
fi
if [[ -n "$line_consult" ]] && [[ -n "$line_fyi" ]] && [[ "$line_consult" -lt "$line_fyi" ]]; then
  pass "Test 8: consult surfaces before fyi"
else
  fail "Test 8: consult surfaces before fyi (consult_line=${line_consult} fyi_line=${line_fyi})"
fi
# fyi line should carry [fyi] marker
fyi_line=$(echo "$output" | grep "FYI Notification")
if echo "$fyi_line" | grep -qF "[fyi]"; then
  pass "Test 8: fyi line carries [fyi] marker"
else
  fail "Test 8: fyi line missing [fyi] marker — got: ${fyi_line}"
fi
# ask and consult lines should NOT carry [fyi] marker
ask_line=$(echo "$output" | grep "Action Request")
if ! echo "$ask_line" | grep -qF "[fyi]"; then
  pass "Test 8: ask line has no [fyi] marker"
else
  fail "Test 8: ask line should not carry [fyi] marker — got: ${ask_line}"
fi
consult_line_text=$(echo "$output" | grep "Consult Request")
if ! echo "$consult_line_text" | grep -qF "[fyi]"; then
  pass "Test 8: consult line has no [fyi] marker"
else
  fail "Test 8: consult line should not carry [fyi] marker — got: ${consult_line_text}"
fi
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 9: Memo with NO kind field → bands as ask (urgent, no [fyi] marker)
#   Verifies the absent-kind = ask default from the pinned interface.
# Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md §Pinned interface
# ---------------------------------------------------------------------------
echo "--- Test 9: missing kind field defaults to ask (urgent band)"
tmpdir=$(mktemp -d)
# fyi memo (would surface last with banding)
write_memo "$tmpdir" "2099-04-01-fyi.md" "title: FYI Only
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open
kind: fyi"
# no-kind memo (should default to ask, surface before fyi)
write_memo "$tmpdir" "2099-04-02-nokind.md" "title: No Kind Memo
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
line_nokind=$(echo "$output" | grep -n "No Kind Memo" | cut -d: -f1)
line_fyi=$(echo "$output" | grep -n "FYI Only" | cut -d: -f1)
if [[ -n "$line_nokind" ]] && [[ -n "$line_fyi" ]] && [[ "$line_nokind" -lt "$line_fyi" ]]; then
  pass "Test 9: no-kind memo surfaces before fyi (defaults to ask)"
else
  fail "Test 9: no-kind memo should surface before fyi (nokind_line=${line_nokind} fyi_line=${line_fyi})"
fi
# no-kind memo should NOT carry [fyi] marker
nokind_line_text=$(echo "$output" | grep "No Kind Memo")
if ! echo "$nokind_line_text" | grep -qF "[fyi]"; then
  pass "Test 9: no-kind memo has no [fyi] marker (treated as urgent)"
else
  fail "Test 9: no-kind memo should not carry [fyi] marker — got: ${nokind_line_text}"
fi
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 10: Memo title containing a literal | pipe character — line still parses
#   and kind is correctly detected (F4: Python emitter sanitizes | → –).
#   Verifies: (a) the line still parses (IFS='|' read does not corrupt kind),
#             (b) the fyi kind marker is still correctly emitted.
# Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md §C4
# Review: code-reviewer F4 — pipe-in-title sanitization test
# ---------------------------------------------------------------------------
echo "--- Test 10: pipe character in title sanitized (F4)"
tmpdir=$(mktemp -d)
write_memo "$tmpdir" "2099-05-01-pipe-title.md" "title: Memo With | Pipe In Title
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open
kind: fyi"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
# (a) The title should appear in the output (sanitized pipe → em-dash, or the title
#     prefix "Memo With" should be present even if the pipe was replaced).
if echo "$output" | grep -qF "Memo With"; then
  pass "Test 10a: pipe-title memo appears in output"
else
  fail "Test 10a: pipe-title memo not found in output — got: ${output}"
fi
# (b) The kind should still be correctly detected — fyi memo must carry [fyi] marker.
if echo "$output" | grep "Memo With" | grep -qF "[fyi]"; then
  pass "Test 10b: pipe-title fyi memo carries [fyi] marker (kind correctly parsed)"
else
  fail "Test 10b: pipe-title fyi memo missing [fyi] marker — kind field corrupted? got: ${output}"
fi
rm -rf "$tmpdir"

# ---------------------------------------------------------------------------
# Test 11: proposal kind — surfaces in urgent band (before fyi), no [fyi] marker
#   Verifies: (a) proposal surfaces before fyi (urgent band, same as ask/consult),
#             (b) proposal line carries no [fyi] marker.
# Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md §C4
# Review: code-reviewer F5 — AC6 coverage gate: proposal banding in shell-native test
# ---------------------------------------------------------------------------
echo "--- Test 11: proposal kind bands as urgent (before fyi, no [fyi] marker)"
tmpdir=$(mktemp -d)
# Write fyi first so alphabetical filename order would surface it first without banding.
write_memo "$tmpdir" "2099-06-01-fyi.md" "title: FYI Background Note
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open
kind: fyi"
write_memo "$tmpdir" "2099-06-02-proposal.md" "title: Proposal For Review
from: central-em
to: project-rag-em
created: ${fixture_today}
status: open
kind: proposal"
output=$(MOCK_TODAY="${mock_today_fresh}" CROSS_REPO_INBOX_DIR="$tmpdir" bash "$HELPER")
# (a) proposal should appear before fyi in output
line_proposal=$(echo "$output" | grep -n "Proposal For Review" | cut -d: -f1)
line_fyi=$(echo "$output" | grep -n "FYI Background Note" | cut -d: -f1)
if [[ -n "$line_proposal" ]] && [[ -n "$line_fyi" ]] && [[ "$line_proposal" -lt "$line_fyi" ]]; then
  pass "Test 11a: proposal surfaces before fyi (urgent band)"
else
  fail "Test 11a: proposal should surface before fyi (proposal_line=${line_proposal} fyi_line=${line_fyi})"
fi
# (b) proposal line should NOT carry [fyi] marker
proposal_line_text=$(echo "$output" | grep "Proposal For Review")
if ! echo "$proposal_line_text" | grep -qF "[fyi]"; then
  pass "Test 11b: proposal line has no [fyi] marker"
else
  fail "Test 11b: proposal line should not carry [fyi] marker — got: ${proposal_line_text}"
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
