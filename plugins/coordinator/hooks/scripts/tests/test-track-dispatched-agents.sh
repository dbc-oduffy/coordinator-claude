#!/bin/bash
# Tests for track-dispatched-agents.sh — Phase 2 Chunk 1 smoke suite.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md
# § Chunk 1 AC: new Agent dispatches land with model column; legacy records still
# parse; dedup (column-1) suppresses re-append on both shapes.
#
# Tests:
#   T1. Full payload with model+subagent_type → 3-column record written
#   T2. Payload without model field → record written with "unknown" model
#   T3. Payload without subagent_type → record written with "unknown" subagent_type
#   T4. Dedup: same agentId fired twice → only one line in dispatched-agents.txt
#   T5. Dedup works on legacy bare-agentId line (tab-delimited new fire doesn't re-append)
#   T6. Non-Agent tool_name → fast-exit, nothing written
#   T7. Missing session_id → fast-exit, no crash
#   T8. Missing tool_response → fast-exit, no crash
#   T9. agentId format guard: non-hex string rejected
#
# Exit codes: 0 = all pass, 1 = at least one failure

set -uo pipefail

HOOK_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../track-dispatched-agents.sh"

if [[ ! -f "$HOOK_SCRIPT" ]]; then
  echo "FATAL: hook script not found at $HOOK_SCRIPT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
PASS=0
FAIL=0

pass() { echo "PASS: $1"; (( PASS++ )) || true; }
fail() { echo "FAIL: $1  =>  ${2:-}"; (( FAIL++ )) || true; }

# ---------------------------------------------------------------------------
# Setup: scratch git repo in temp dir
# ---------------------------------------------------------------------------
TMPDIR_BASE=$(mktemp -d 2>/dev/null || mktemp -d -t track-dispatched-test)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

REPO="$TMPDIR_BASE/repo"
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "test@test.com"
git config user.name "Test"
touch README.md && git add README.md && git commit -q -m "init"

HOOK="$HOOK_SCRIPT"
SID="test-session-abc123"
VALID_AID="a47b7551f951cb0"   # 15-char lowercase hex — satisfies 12+ guard
SESSIONS_DIR="$REPO/.git/coordinator-sessions"
DISPATCHED="$SESSIONS_DIR/$SID/dispatched-agents.txt"

# Helper: build a full PostToolUse Agent JSON payload.
#   $1 = agentId (placed in tool_response)
#   $2 = model   (placed in tool_input; pass "" to omit field)
#   $3 = subagent_type (placed in tool_input; pass "" to omit field)
make_agent_payload() {
  local aid="$1"
  local model="${2:-}"
  local stype="${3:-}"

  # Build tool_input object conditionally
  local ti_fields='"description":"test agent"'
  [[ -n "$model" ]] && ti_fields="${ti_fields},\"model\":\"${model}\""
  [[ -n "$stype" ]] && ti_fields="${ti_fields},\"subagent_type\":\"${stype}\""

  printf '{"session_id":"%s","tool_name":"Agent","tool_input":{%s},"tool_response":{"agentId":"%s","output":"done"}}' \
    "$SID" "$ti_fields" "$aid"
}

# ---------------------------------------------------------------------------
# T1: Full payload with model + subagent_type → 3-column record
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
make_agent_payload "$VALID_AID" "claude-opus-4-5" "executor" | bash "$HOOK"

if [[ ! -f "$DISPATCHED" ]]; then
  fail "T1: dispatched-agents.txt not created"
else
  LINE=$(cat "$DISPATCHED")
  COL1=$(echo "$LINE" | cut -f1)
  COL2=$(echo "$LINE" | cut -f2)
  COL3=$(echo "$LINE" | cut -f3)
  if [[ "$COL1" == "$VALID_AID" && "$COL2" == "claude-opus-4-5" && "$COL3" == "executor" ]]; then
    pass "T1: 3-column record written correctly ($LINE)"
  else
    fail "T1: unexpected record shape" "got: '$LINE'"
  fi
fi

# ---------------------------------------------------------------------------
# T2: Payload without model field → model column = "unknown"
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
AID2="b58c8662a062dc1"
make_agent_payload "$AID2" "" "general-purpose" | bash "$HOOK"

if [[ ! -f "$DISPATCHED" ]]; then
  fail "T2: dispatched-agents.txt not created"
else
  LINE=$(cat "$DISPATCHED")
  COL2=$(echo "$LINE" | cut -f2)
  if [[ "$COL2" == "unknown" ]]; then
    pass "T2: missing model field degrades to 'unknown'"
  else
    fail "T2: expected model=unknown" "got col2='$COL2' in '$LINE'"
  fi
fi

# ---------------------------------------------------------------------------
# T3: Payload without subagent_type → subagent_type column = "unknown"
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
AID3="c69d9773b173ed2"
make_agent_payload "$AID3" "claude-sonnet-4-6" "" | bash "$HOOK"

if [[ ! -f "$DISPATCHED" ]]; then
  fail "T3: dispatched-agents.txt not created"
else
  LINE=$(cat "$DISPATCHED")
  COL3=$(echo "$LINE" | cut -f3)
  if [[ "$COL3" == "unknown" ]]; then
    pass "T3: missing subagent_type degrades to 'unknown'"
  else
    fail "T3: expected subagent_type=unknown" "got col3='$COL3' in '$LINE'"
  fi
fi

# ---------------------------------------------------------------------------
# T4: Dedup — same agentId fired twice → only ONE line in dispatched-agents.txt
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
make_agent_payload "$VALID_AID" "claude-sonnet-4-6" "executor" | bash "$HOOK"
make_agent_payload "$VALID_AID" "claude-sonnet-4-6" "executor" | bash "$HOOK"

if [[ ! -f "$DISPATCHED" ]]; then
  fail "T4: dispatched-agents.txt not created"
else
  LINE_COUNT=$(wc -l < "$DISPATCHED")
  if [[ "$LINE_COUNT" -eq 1 ]]; then
    pass "T4: dedup suppressed second append — exactly 1 line"
  else
    fail "T4: dedup failed" "expected 1 line, got $LINE_COUNT: $(cat "$DISPATCHED")"
  fi
fi

# ---------------------------------------------------------------------------
# T5: Dedup on legacy bare-agentId line — new tab-delimited fire must NOT re-append
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
mkdir -p "$SESSIONS_DIR/$SID"
# Pre-seed with a legacy bare-agentId record (no tabs, old format)
echo "$VALID_AID" > "$DISPATCHED"

make_agent_payload "$VALID_AID" "claude-opus-4-5" "executor" | bash "$HOOK"

LINE_COUNT=$(wc -l < "$DISPATCHED")
if [[ "$LINE_COUNT" -eq 1 ]]; then
  pass "T5: dedup on legacy bare-agentId line suppressed re-append"
else
  fail "T5: dedup failed on legacy line" "expected 1 line, got $LINE_COUNT: $(cat "$DISPATCHED")"
fi

# ---------------------------------------------------------------------------
# T6: Non-Agent tool_name → fast-exit, nothing written
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
printf '{"session_id":"%s","tool_name":"Bash","tool_input":{"command":"echo hi"},"tool_response":{}}' \
  "$SID" | bash "$HOOK"

if [[ -f "$DISPATCHED" ]] && [[ -s "$DISPATCHED" ]]; then
  fail "T6: dispatched-agents.txt written for non-Agent tool (should fast-exit)"
else
  pass "T6: fast-exit on non-Agent tool_name"
fi

# ---------------------------------------------------------------------------
# T7: Missing session_id → fast-exit, no crash
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
printf '{"tool_name":"Agent","tool_input":{},"tool_response":{"agentId":"%s"}}' \
  "$VALID_AID" | bash "$HOOK"
RC=$?
if [[ "$RC" -ne 0 ]]; then
  fail "T7: expected exit 0 on missing session_id, got $RC"
else
  pass "T7: exit 0 on missing session_id"
fi

# ---------------------------------------------------------------------------
# T8: Missing tool_response → fast-exit, no crash
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
printf '{"session_id":"%s","tool_name":"Agent","tool_input":{"model":"claude-opus-4-5"}}' \
  "$SID" | bash "$HOOK"
RC=$?
if [[ "$RC" -ne 0 ]]; then
  fail "T8: expected exit 0 on missing tool_response, got $RC"
elif [[ -f "$DISPATCHED" ]] && [[ -s "$DISPATCHED" ]]; then
  fail "T8: dispatched-agents.txt written despite missing tool_response"
else
  pass "T8: exit 0 on missing tool_response, nothing written"
fi

# ---------------------------------------------------------------------------
# T9: agentId format guard — non-hex string rejected
# ---------------------------------------------------------------------------
rm -rf "$SESSIONS_DIR"
INVALID_AID="not-a-valid-hex-id"
printf '{"session_id":"%s","tool_name":"Agent","tool_input":{},"tool_response":{"agentId":"%s"}}' \
  "$SID" "$INVALID_AID" | bash "$HOOK"

if [[ -f "$DISPATCHED" ]] && [[ -s "$DISPATCHED" ]]; then
  fail "T9: non-hex agentId was recorded (should be rejected by format guard)"
else
  pass "T9: non-hex agentId rejected by format guard"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
