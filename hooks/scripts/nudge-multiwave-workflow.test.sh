#!/usr/bin/env bash
# Self-contained test for nudge-multiwave-workflow.sh.
# Sets up an isolated temp git repo, drives the hook via stdin JSON payloads,
# and asserts on stdout (additionalContext presence/absence) and sentinel
# file side-effects. Exits non-zero on any failure.

set -u

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="${HOOK_DIR}/nudge-multiwave-workflow.sh"

TMP_REPO=$(mktemp -d)
trap 'rm -rf "$TMP_REPO"' EXIT

(
  cd "$TMP_REPO" || exit 1
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test"
)

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS: $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL: $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

run_hook() {
  # $1 = payload JSON string
  ( cd "$TMP_REPO" && printf '%s' "$1" | bash "$HOOK" )
}

session_dir() {
  # $1 = session_id
  printf '%s/.git/coordinator-sessions/%s' "$TMP_REPO" "$1"
}

# --- Case 1: EM executor dispatch, no workflow, first time ---
SID1="test-sid-1"
PAYLOAD1='{"session_id":"'"$SID1"'","tool_name":"Agent","tool_input":{"subagent_type":"coordinator:executor","prompt":"do work"}}'
OUT1=$(run_hook "$PAYLOAD1")
if [[ "$OUT1" == *'additionalContext'* ]]; then
  pass "case1: stdout contains additionalContext"
else
  fail "case1: expected additionalContext in stdout, got: $OUT1"
fi
if [[ -f "$(session_dir "$SID1")/multiwave-workflow-nudged" ]]; then
  pass "case1: nudged sentinel created"
else
  fail "case1: nudged sentinel NOT created"
fi

# --- Case 2: second EM executor dispatch (nudged sentinel already present) ---
PAYLOAD2='{"session_id":"'"$SID1"'","tool_name":"Agent","tool_input":{"subagent_type":"coordinator:executor","prompt":"do more work"}}'
OUT2=$(run_hook "$PAYLOAD2")
if [[ -z "$OUT2" ]]; then
  pass "case2: stdout empty (fires at most once per session)"
else
  fail "case2: expected empty stdout, got: $OUT2"
fi

# --- Case 3: workflow-launched sentinel present -> EM executor dispatch ---
SID3="test-sid-3"
mkdir -p "$(session_dir "$SID3")"
: > "$(session_dir "$SID3")/workflow-launched"
PAYLOAD3='{"session_id":"'"$SID3"'","tool_name":"Agent","tool_input":{"subagent_type":"coordinator:executor","prompt":"do work"}}'
OUT3=$(run_hook "$PAYLOAD3")
if [[ -z "$OUT3" ]]; then
  pass "case3: stdout empty when workflow-launched sentinel present"
else
  fail "case3: expected empty stdout, got: $OUT3"
fi

# --- Case 4: subagent-originated (payload includes agent_id) ---
SID4="test-sid-4"
PAYLOAD4='{"session_id":"'"$SID4"'","agent_id":"abc@session-x","tool_name":"Agent","tool_input":{"subagent_type":"coordinator:executor","prompt":"do work"}}'
OUT4=$(run_hook "$PAYLOAD4")
if [[ -z "$OUT4" ]]; then
  pass "case4: stdout empty for subagent-originated dispatch"
else
  fail "case4: expected empty stdout, got: $OUT4"
fi

# --- Case 5: read-only target (subagent_type = Explore) ---
SID5="test-sid-5"
PAYLOAD5='{"session_id":"'"$SID5"'","tool_name":"Agent","tool_input":{"subagent_type":"Explore","prompt":"look around"}}'
OUT5=$(run_hook "$PAYLOAD5")
if [[ -z "$OUT5" ]]; then
  pass "case5: stdout empty for read-only target (Explore)"
else
  fail "case5: expected empty stdout, got: $OUT5"
fi

# --- Case 6: override set ---
SID6="test-sid-6"
PAYLOAD6='{"session_id":"'"$SID6"'","tool_name":"Agent","tool_input":{"subagent_type":"coordinator:executor","prompt":"do work"}}'
OUT6=$( ( cd "$TMP_REPO" && export COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW=1 && printf '%s' "$PAYLOAD6" | bash "$HOOK" ) )
if [[ -z "$OUT6" ]]; then
  pass "case6: stdout empty when override env set"
else
  fail "case6: expected empty stdout, got: $OUT6"
fi

# --- Case 7: Workflow tool call ---
SID7="test-sid-7"
PAYLOAD7='{"session_id":"'"$SID7"'","tool_name":"Workflow","tool_input":{"script":"some-workflow"}}'
OUT7=$(run_hook "$PAYLOAD7")
if [[ -z "$OUT7" ]]; then
  pass "case7: stdout empty for Workflow tool call"
else
  fail "case7: expected empty stdout, got: $OUT7"
fi
if [[ -f "$(session_dir "$SID7")/workflow-launched" ]]; then
  pass "case7: workflow-launched sentinel created"
else
  fail "case7: workflow-launched sentinel NOT created"
fi

# --- Case 8: empty stdin -> silent ---
OUT8=$(run_hook "")
if [[ -z "$OUT8" ]]; then
  pass "case8: stdout empty for empty stdin"
else
  fail "case8: expected empty stdout, got: $OUT8"
fi

# --- Case 9: missing session_id -> silent ---
PAYLOAD9='{"tool_name":"Agent","tool_input":{"subagent_type":"coordinator:executor","prompt":"do work"}}'
OUT9=$(run_hook "$PAYLOAD9")
if [[ -z "$OUT9" ]]; then
  pass "case9: stdout empty for missing session_id"
else
  fail "case9: expected empty stdout, got: $OUT9"
fi

# --- Case 10: missing tool_input -> silent ---
SID10="test-sid-10"
PAYLOAD10='{"session_id":"'"$SID10"'","tool_name":"Agent"}'
OUT10=$(run_hook "$PAYLOAD10")
if [[ -z "$OUT10" ]]; then
  pass "case10: stdout empty for missing tool_input"
else
  fail "case10: expected empty stdout, got: $OUT10"
fi

# --- Case 11: session_id containing "../" -> rejected (silent, no sentinel outside session dir) ---
SID11='../../etc-traversal'
PAYLOAD11='{"session_id":"'"$SID11"'","tool_name":"Agent","tool_input":{"subagent_type":"coordinator:executor","prompt":"do work"}}'
OUT11=$(run_hook "$PAYLOAD11")
if [[ -z "$OUT11" ]]; then
  pass "case11: stdout empty for path-traversal session_id"
else
  fail "case11: expected empty stdout, got: $OUT11"
fi
if [[ -e "${TMP_REPO}/.git/coordinator-sessions/etc-traversal" || -e "${TMP_REPO}/../etc-traversal" ]]; then
  fail "case11: sentinel/dir written outside intended session dir"
else
  pass "case11: no path-traversal sentinel/dir written"
fi

echo ""
echo "Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
exit 0
