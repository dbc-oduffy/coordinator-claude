#!/usr/bin/env bash
# append-goal-event.test.sh — Self-contained tests for append-goal-event.sh
#
# Purpose: Verifies that append-goal-event.sh correctly appends a valid
#          goal-event JSON line with all 9 required keys, correct status,
#          12-hex goal_id, and idempotent goal_id for identical inputs.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C2
# Review: A-F15 — fabricated plan path repointed to real plan

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="${SCRIPT_DIR}/append-goal-event.sh"

PASS=0
FAIL=0

pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
fail() { echo "FAIL: $1"; FAIL=$(( FAIL + 1 )); }

# ---------------------------------------------------------------------------
# Setup: temp HOME so ROOT resolves to a temp dir (never touches real state)
# ---------------------------------------------------------------------------
TMP_HOME="$(mktemp -d)"
cleanup() { rm -rf "$TMP_HOME"; }
trap cleanup EXIT

# ROOT in the helper resolves as: ROOT="${CLAUDE_HOME:-$HOME}/.claude"
# So we set CLAUDE_HOME=TMP_HOME (no /.claude suffix) → ROOT=$TMP_HOME/.claude
# Per-machine log filename carries the machine slug (must match the helper's derivation).
MACHINE_SLUG="$(printf '%s' "$(hostname)" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"
LOG_FILE="${TMP_HOME}/.claude/state/goals-log.${MACHINE_SLUG}.jsonl"

# ---------------------------------------------------------------------------
# Test 1: Append a valid goal event; assert file created + one line
# ---------------------------------------------------------------------------
CLAUDE_HOME="${TMP_HOME}" bash "$HELPER" \
  --period week \
  --period-value "2026-W26" \
  --text "Ship the goals cockpit" \
  --repo "dbc-oduffy/.claude-prime" \
  --root "."

if [[ -f "$LOG_FILE" ]]; then
  pass "T1: log file created"
else
  fail "T1: log file not created at $LOG_FILE"
fi

LINE_COUNT=$(wc -l < "$LOG_FILE" | tr -d ' ')
if [[ "$LINE_COUNT" -eq 1 ]]; then
  pass "T1: exactly one line appended"
else
  fail "T1: expected 1 line, got $LINE_COUNT"
fi

# ---------------------------------------------------------------------------
# Test 2: Appended line is valid JSON
# ---------------------------------------------------------------------------
LINE1="$(head -n 1 "$LOG_FILE")"
if echo "$LINE1" | jq -e . >/dev/null 2>&1; then
  pass "T2: appended line is valid JSON"
else
  fail "T2: appended line is not valid JSON: $LINE1"
fi

# ---------------------------------------------------------------------------
# Test 3: All 9 required keys present
# ---------------------------------------------------------------------------
REQUIRED_KEYS=(goal_id repo coordinator_root_path period period_value declared_by_machine declared_at text status)
ALL_KEYS_PRESENT=1
for key in "${REQUIRED_KEYS[@]}"; do
  if ! echo "$LINE1" | jq -e "has(\"$key\")" >/dev/null 2>&1; then
    fail "T3: missing key '$key'"
    ALL_KEYS_PRESENT=0
  fi
done
if [[ "$ALL_KEYS_PRESENT" -eq 1 ]]; then
  pass "T3: all 9 required keys present"
fi

# ---------------------------------------------------------------------------
# Test 4: status == "active"
# ---------------------------------------------------------------------------
ACTUAL_STATUS="$(echo "$LINE1" | jq -r '.status')"
if [[ "$ACTUAL_STATUS" == "active" ]]; then
  pass "T4: status is 'active'"
else
  fail "T4: expected status='active', got '$ACTUAL_STATUS'"
fi

# ---------------------------------------------------------------------------
# Test 5: goal_id is exactly 12 hex chars
# ---------------------------------------------------------------------------
GOAL_ID="$(echo "$LINE1" | jq -r '.goal_id')"
if [[ "$GOAL_ID" =~ ^[0-9a-f]{12}$ ]]; then
  pass "T5: goal_id is 12 hex chars ('$GOAL_ID')"
else
  fail "T5: goal_id '$GOAL_ID' is not 12 lowercase hex chars"
fi

# ---------------------------------------------------------------------------
# Test 6: Idempotent goal_id — appending same inputs twice yields same id
# ---------------------------------------------------------------------------
CLAUDE_HOME="${TMP_HOME}" bash "$HELPER" \
  --period week \
  --period-value "2026-W26" \
  --text "Ship the goals cockpit" \
  --repo "dbc-oduffy/.claude-prime" \
  --root "."

LINE2="$(sed -n '2p' "$LOG_FILE")"
GOAL_ID2="$(echo "$LINE2" | jq -r '.goal_id')"

if [[ "$GOAL_ID" == "$GOAL_ID2" ]]; then
  pass "T6: idempotent goal_id (same inputs -> same id)"
else
  fail "T6: goal_id changed: first='$GOAL_ID' second='$GOAL_ID2'"
fi

# ---------------------------------------------------------------------------
# Test 7: Fail loud on missing required --period
# ---------------------------------------------------------------------------
if CLAUDE_HOME="${TMP_HOME}" bash "$HELPER" \
    --period-value "2026-06-22" \
    --text "some goal" 2>/dev/null; then
  fail "T7: should have exited non-zero when --period missing"
else
  pass "T7: exits non-zero when --period is missing"
fi

# ---------------------------------------------------------------------------
# Test 8: Fail loud on invalid --period value
# ---------------------------------------------------------------------------
if CLAUDE_HOME="${TMP_HOME}" bash "$HELPER" \
    --period badvalue \
    --period-value "2026-06-22" \
    --text "some goal" 2>/dev/null; then
  fail "T8: should have exited non-zero for invalid --period"
else
  pass "T8: exits non-zero for invalid --period value"
fi

# ---------------------------------------------------------------------------
# Test 9: Fail loud on missing --text
# ---------------------------------------------------------------------------
if CLAUDE_HOME="${TMP_HOME}" bash "$HELPER" \
    --period day \
    --period-value "2026-06-22" 2>/dev/null; then
  fail "T9: should have exited non-zero when --text missing"
else
  pass "T9: exits non-zero when --text is missing"
fi

# ---------------------------------------------------------------------------
# Test 10: Different period_value produces different goal_id
# ---------------------------------------------------------------------------
TMP_HOME2="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME" "$TMP_HOME2"' EXIT

CLAUDE_HOME="${TMP_HOME2}" bash "$HELPER" \
  --period week \
  --period-value "2026-W27" \
  --text "Ship the goals cockpit" \
  --repo "dbc-oduffy/.claude-prime" \
  --root "."

# Helper computes ROOT as "${CLAUDE_HOME}/.claude", so log is at TMP_HOME2/.claude/...
LOG2="${TMP_HOME2}/.claude/state/goals-log.${MACHINE_SLUG}.jsonl"
GOAL_ID_DIFF="$(head -n 1 "$LOG2" | jq -r '.goal_id')"

if [[ "$GOAL_ID" != "$GOAL_ID_DIFF" ]]; then
  pass "T10: different period_value produces different goal_id"
else
  fail "T10: different period_value produced same goal_id (hash collision or bug)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
