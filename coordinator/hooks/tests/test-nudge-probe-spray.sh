#!/usr/bin/env bash
# Test suite for nudge-probe-spray.sh
#
# Stateful hook: drives ordered command sequences through it with isolated
# per-scenario state (a fresh TMPDIR + fixed CLAUDE_SESSION_ID) and asserts the
# nudge fires at the right point in the streak — not before, and resets on real
# work. Never-block is invariant: every nudge is permissionDecision:"allow".

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/nudge-probe-spray.sh"
PASS=0
FAIL=0

# emit includes session_id so the PRIMARY stdin-keyed path is exercised by default
# (KEY resolves to "test", matching the env fallback the run helper also sets).
emit() {
  if command -v jq &>/dev/null; then
    jq -nc --arg c "$1" '{tool_name:"Bash",session_id:"test",tool_input:{command:$c}}'
  else
    local c="${1//\\/\\\\}"; c="${c//\"/\\\"}"; c="${c//$'\n'/\\n}"
    printf '{"tool_name":"Bash","session_id":"test","tool_input":{"command":"%s"}}' "$c"
  fi
}

# run <statedir> <cmd> -> prints "nudge" or "quiet".
run() {
  local out
  out=$(emit "$2" | env TMPDIR="$1" CLAUDE_SESSION_ID=test bash "$HOOK" 2>/dev/null || true)
  if printf '%s' "$out" | grep -q 'PROBE-SPRAY DETECTED'; then echo nudge; else echo quiet; fi
}

expect() {
  # $1 = description, $2 = expected, $3 = actual
  if [[ "$2" == "$3" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $1 (expected $2, got $3)"
  fi
}

# --- Scenario A: three distinct bare-echo probes -> nudge on the third only ----
SD=$(mktemp -d)
expect "A1 first probe quiet"  quiet "$(run "$SD" 'echo probe')"
expect "A2 second probe quiet" quiet "$(run "$SD" 'echo alive_check')"
# Capture the 3rd call directly in the parent (a `run` subshell would not export
# its output, and a 4th call would fall inside the cooldown and not re-nudge).
A3OUT=$(emit 'echo ping' | env TMPDIR="$SD" CLAUDE_SESSION_ID=test bash "$HOOK" 2>/dev/null || true)
if printf '%s' "$A3OUT" | grep -q 'PROBE-SPRAY DETECTED'; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL: A3 third probe should nudge"; fi
# The nudge must be allow (never block).
if printf '%s' "$A3OUT" | grep -q '"permissionDecision":"allow"'; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL: A nudge must be permissionDecision allow"; fi
rm -rf "$SD"

# --- Scenario B: a real command resets the streak --------------------------------
SD=$(mktemp -d)
expect "B1 echo a quiet" quiet "$(run "$SD" 'echo a')"
expect "B2 echo b quiet" quiet "$(run "$SD" 'echo b')"
expect "B3 real grep resets" quiet "$(run "$SD" 'grep -r foo .')"
expect "B4 echo c quiet (count restarted)" quiet "$(run "$SD" 'echo c')"
expect "B5 echo d quiet" quiet "$(run "$SD" 'echo d')"
expect "B6 echo e nudges (3 since reset)" nudge "$(run "$SD" 'echo e')"
rm -rf "$SD"

# --- Scenario C: echo with pipe/redirect is real work, not a probe ---------------
SD=$(mktemp -d)
expect "C1 echo|tee is real" quiet "$(run "$SD" 'echo hello | tee /dev/null')"
expect "C2 echo>>file is real" quiet "$(run "$SD" 'echo line >> /dev/null')"
expect "C3 probe 1" quiet "$(run "$SD" 'echo a')"
expect "C4 probe 2" quiet "$(run "$SD" 'echo b')"
expect "C5 probe 3 nudges (piped echoes never counted)" nudge "$(run "$SD" 'echo c')"
rm -rf "$SD"

# --- Scenario D: SUSTAINED exact-repeat of a non-echo command eventually probes ---
# With RING_RECUR_MIN=2 a couple of repeats are tolerated as real iteration; only
# sustained repetition (5 identical within the window) crosses the threshold.
SD=$(mktemp -d)
expect "D1 git log baseline (real)" quiet "$(run "$SD" 'git log -1')"
expect "D2 repeat tolerated"        quiet "$(run "$SD" 'git log -1')"
expect "D3 repeat tolerated"        quiet "$(run "$SD" 'git log -1')"
expect "D4 repeat tolerated"        quiet "$(run "$SD" 'git log -1')"
expect "D5 sustained repeat nudges" nudge "$(run "$SD" 'git log -1')"
rm -rf "$SD"

# --- Scenario E: sleep counts as a probe -----------------------------------------
SD=$(mktemp -d)
expect "E1 sleep quiet" quiet "$(run "$SD" 'sleep 1')"
expect "E2 sleep;echo quiet" quiet "$(run "$SD" 'sleep 1; echo done')"
expect "E3 printf nudges" nudge "$(run "$SD" "printf 'CHAN_OK\\n'")"
rm -rf "$SD"

# --- Scenario F: off-switch suppresses the nudge entirely ------------------------
SD=$(mktemp -d)
o1=$(emit 'echo a' | env TMPDIR="$SD" CLAUDE_SESSION_ID=test COORDINATOR_PROBE_NUDGE_OFF=1 bash "$HOOK" 2>/dev/null || true)
o2=$(emit 'echo b' | env TMPDIR="$SD" CLAUDE_SESSION_ID=test COORDINATOR_PROBE_NUDGE_OFF=1 bash "$HOOK" 2>/dev/null || true)
o3=$(emit 'echo c' | env TMPDIR="$SD" CLAUDE_SESSION_ID=test COORDINATOR_PROBE_NUDGE_OFF=1 bash "$HOOK" 2>/dev/null || true)
if printf '%s' "$o3" | grep -q 'PROBE-SPRAY DETECTED'; then FAIL=$((FAIL+1)); echo "FAIL: off-switch should suppress nudge"; else PASS=$((PASS+1)); fi
rm -rf "$SD"

# --- Scenario G: a single legitimate probe never nudges --------------------------
SD=$(mktemp -d)
expect "G1 lone probe quiet" quiet "$(run "$SD" 'echo ok')"
rm -rf "$SD"

# --- Scenario I: real-world quoted single-token echoes (the se-flush shape) ------
# 2026-05-30 transcript: a concurrent session sprayed `echo "se-flush-3"` etc.
# The classifier must match a QUOTED single token, not only a bare word.
SD=$(mktemp -d)
expect "I1 quoted echo quiet" quiet "$(run "$SD" 'echo "se-flush-3"')"
expect "I2 quoted echo quiet" quiet "$(run "$SD" 'echo "se-flush-5"')"
expect "I3 quoted echo nudges" nudge "$(run "$SD" 'echo "se-flush-7"')"
rm -rf "$SD"

# --- Scenario J: trivial no-ops (true / pwd / :) are liveness probes --------------
SD=$(mktemp -d)
expect "J1 true quiet" quiet "$(run "$SD" 'true')"
expect "J2 pwd quiet"  quiet "$(run "$SD" 'pwd')"
expect "J3 : (colon noop) nudges" nudge "$(run "$SD" ':')"
rm -rf "$SD"

# --- Scenario K: SUSTAINED alternating reads caught via the recurrence ring -------
# git log / git status alternating — with RING_RECUR_MIN=2 each must recur a couple
# of times before counting, so the streak builds more slowly than identical spray
# but is still caught (review finding F6, balanced against false positives).
SD=$(mktemp -d)
expect "K1 git log (real)"         quiet "$(run "$SD" 'git log -1')"
expect "K2 git status (real)"      quiet "$(run "$SD" 'git status')"
expect "K3 git log tolerated"      quiet "$(run "$SD" 'git log -1')"
expect "K4 git status tolerated"   quiet "$(run "$SD" 'git status')"
expect "K5 git log recurs"         quiet "$(run "$SD" 'git log -1')"
expect "K6 git status recurs"      quiet "$(run "$SD" 'git status')"
expect "K7 git log recurs nudges"  nudge "$(run "$SD" 'git log -1')"
rm -rf "$SD"

# --- Scenario L: unwritable TMPDIR -> fail open (no nudge, exit 0), never block ----
BADTMP="/nonexistent_probe_state_$$/nope"
emit 'echo a' | env TMPDIR="$BADTMP" CLAUDE_SESSION_ID=test bash "$HOOK" >/dev/null 2>&1
expect "L exits 0 under unwritable TMPDIR" 0 "$?"
emit 'echo b' | env TMPDIR="$BADTMP" CLAUDE_SESSION_ID=test bash "$HOOK" >/dev/null 2>&1
l3=$(emit 'echo c' | env TMPDIR="$BADTMP" CLAUDE_SESSION_ID=test bash "$HOOK" 2>/dev/null || true)
if printf '%s' "$l3" | grep -q 'PROBE-SPRAY DETECTED'; then FAIL=$((FAIL+1)); echo "FAIL: unwritable TMPDIR must not nudge (state cannot persist)"; else PASS=$((PASS+1)); fi

# --- Scenario M: cooldown expiry re-nudges (inject a backdated cooldown) -----------
SD=$(mktemp -d)
run "$SD" 'echo a' >/dev/null
run "$SD" 'echo b' >/dev/null
expect "M nudge at threshold" nudge "$(run "$SD" 'echo c')"
# Filename couples to KEY=test (session_id "test" in emit + CLAUDE_SESSION_ID=test).
printf '%s' "1" > "$SD/coordinator-probe-spray-test.cool"   # epoch 1 = far past
expect "M re-nudges after cooldown expiry" nudge "$(run "$SD" 'echo d')"
rm -rf "$SD"

# --- Scenario N: session_id from the stdin payload keys the window ----------------
SD=$(mktemp -d)
if command -v jq &>/dev/null; then
  emitS() { jq -nc --arg c "$1" '{tool_name:"Bash",session_id:"sess-xyz",tool_input:{command:$c}}'; }
  emitS 'echo a' | env TMPDIR="$SD" bash "$HOOK" >/dev/null 2>&1
  emitS 'echo b' | env TMPDIR="$SD" bash "$HOOK" >/dev/null 2>&1
  n3=$(emitS 'echo c' | env TMPDIR="$SD" bash "$HOOK" 2>/dev/null || true)
  if printf '%s' "$n3" | grep -q 'PROBE-SPRAY DETECTED'; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL: stdin session_id keying should accumulate to a nudge"; fi
  if [[ -f "$SD/coordinator-probe-spray-sess-xyz.times" ]]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL: state must be keyed by the stdin session_id"; fi
else
  PASS=$((PASS+2)); echo "  [SKIP] session_id-from-stdin test needs jq (counted as pass)"
fi
rm -rf "$SD"

# --- Scenario H: non-Bash tool ignored (no output) -------------------------------
nb=$(printf '{"tool_name":"Write","tool_input":{"command":"echo a"}}' | env TMPDIR="$(mktemp -d)" CLAUDE_SESSION_ID=test bash "$HOOK" 2>/dev/null || true)
if [[ -z "$nb" ]]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL: non-Bash tool should be ignored"; fi

# ---------------------------------------------------------------------------
echo "----------------------------------------"
echo "nudge-probe-spray: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]] || exit 1
exit 0
