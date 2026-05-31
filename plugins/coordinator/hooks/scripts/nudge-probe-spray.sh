#!/usr/bin/env bash
# PreToolUse(Bash) hook: detects the channel-test probe-spray loop and nudges
# the model to stop — an OFFER (warn, never block). Every code path exits 0;
# there is no branch that can deny or block a tool call.
#
# Motivation: the tool-output-flakiness protocol names two triggers for the
# blocked/no-return failure. Trigger 1 (a `cd <path> && git ...` stall) is caught
# structurally by offer-git-c-over-cd.sh. Trigger 2 is the spray itself: after an
# empty / `(No output)` / cancel-cascade result, the model misreads the channel as
# dead and fires a burst of liveness probes — `echo "se-flush-3"`, `echo probe`,
# `printf CHAN_OK`, `sleep 1; echo done`, `true`/`pwd`, repeated reads — none of
# which diagnose anything; the channel was fine the whole time. Observed recurring
# across concurrent sessions on 2026-05-30, broken only by PM interrupt.
#
# A per-call PreToolUse hook cannot see sibling calls in a batch, but it CAN keep
# session-keyed DISK STATE: a rolling window of probe-shaped commands plus a small
# ring of recent command hashes (so alternating re-reads are caught, not just
# immediate repeats). At THRESHOLD within WINDOW it nudges once (with a cooldown so
# the nudge isn't itself spam); any clearly-real, non-recurring command resets the
# streak. Doctrine: docs/wiki/tool-output-flakiness-protocol.md
#   § Not this protocol — blocked / no-return (`Waiting...`) is a different failure
#
# Probe shapes (high-signal, to keep single legitimate uses quiet):
#   - `echo <single-token>` with OPTIONAL surrounding quotes (the real-world shape
#     is `echo "se-flush-3"`); token charset excludes path/`=`/`:` data chars so
#     `echo status=ok` / `echo /tmp/x` stay classified as real work.
#   - bare `echo` (no argument), and trivial no-ops `true` / `false` / `:` / `pwd` / `date`
#   - a short `printf` literal with no pipe/redirect
#   - `sleep <N>` (optionally `; echo ...`)
#   - a command whose hash recurs within the recent ring (re-running a read to
#     "test" the channel — a probe regardless of shape; catches alternation)
# A single such command never nudges; only THRESHOLD within WINDOW does.
#
# Concurrency: state writes are last-writer-wins (no flock). Under a high parallel
# fan-out from one session, the streak count can undercount by one — acceptable for
# a nudge (worst case: one extra probe before the nudge). Sessions never share a
# file (keyed by session_id), so cross-session contamination cannot occur.
#
# Mechanism: permissionDecision:"allow" + additionalContext (the only
# warn-reaches-the-model-without-blocking channel for PreToolUse). Off switch:
# COORDINATOR_PROBE_NUDGE_OFF=1 (autonomous runs that legitimately echo/sleep).

set -uo pipefail

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)  # || true keeps PY set for set -u

if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Parse tool_name + command + session_id. session_id comes from the hook payload
# itself (stable across a session's tool calls) — unlike $PPID, which is per-bash-
# invocation and would silently disable the window.
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  TOOL_NAME=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
  CMD=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("command","")))' 2>/dev/null || true)
  SESSION_ID=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("session_id","")))' 2>/dev/null || true)
else
  # sed fallback (no jq, no python) assumes the compact single-line JSON Claude Code
  # emits; a pretty-printed payload could split a key/value across lines and fall back
  # to the $PPID key — acceptable degradation, never a crash.
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  CMD=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:[[:space:]]*"//; s/"$//')
  SESSION_ID=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

[[ "$TOOL_NAME" != "Bash" ]] && exit 0
[[ -z "$CMD" ]] && exit 0
[[ "${COORDINATOR_PROBE_NUDGE_OFF:-0}" == "1" ]] && exit 0

NOW=$(date +%s 2>/dev/null || echo 0)
# If the clock is unreadable the window math is meaningless (and NOW=0 entries
# would never expire) — degrade to a no-op rather than misfire.
[[ "$NOW" -eq 0 ]] 2>/dev/null && exit 0

# --- Session-keyed state (concurrent sessions never share a file) ---
KEY="${SESSION_ID:-${CLAUDE_SESSION_ID:-${PPID:-default}}}"
KEY="${KEY//[^A-Za-z0-9_-]/_}"
STATE_DIR="${TMPDIR:-/tmp}"
PREFIX="${STATE_DIR}/coordinator-probe-spray-${KEY}"
TIMES="${PREFIX}.times"
RING="${PREFIX}.ring"
COOL="${PREFIX}.cool"

WINDOW=90        # seconds — probes older than this fall out of the streak
THRESHOLD=3      # probes within WINDOW before the first nudge
COOLDOWN=30      # seconds between nudges so the nudge is not itself spam
RING_N=8         # recent commands retained for recurrence detection
RING_RECUR_MIN=2 # a command must ALREADY appear this many times in the ring before
                 # a further occurrence counts as a probe — so a legitimately
                 # repeated real command (make, git log) gets latitude, while a
                 # trivial channel probe is caught directly by a shape classifier

# Amortized cleanup of stale state files (~1 in 50 invocations); never fatal.
if (( RANDOM % 50 == 0 )); then
  find "$STATE_DIR" -maxdepth 1 -name 'coordinator-probe-spray-*' -mmin +180 -delete 2>/dev/null || true
fi

# Hash is only meaningful if cksum exists; absent it, recurrence detection is
# disabled (shape classifiers still fire) — graceful degradation, never a block.
HASH=""
if command -v cksum &>/dev/null; then
  HASH=$(printf '%s' "$CMD" | cksum 2>/dev/null | awk '{print $1}' || true)
fi

# --- Recurrence: has this exact command ALREADY recurred in the recent ring? ---
# Counting occurrences (not mere presence) so a build/test command repeated once or
# twice during normal iteration is not mistaken for channel-probing — only sustained
# repetition crosses the bar.
in_ring=0
if [[ -n "$HASH" && -f "$RING" ]]; then
  ring_hits=$(grep -cxF "$HASH" "$RING" 2>/dev/null)   # -c prints a single count even on no-match
  [[ "$ring_hits" =~ ^[0-9]+$ ]] || ring_hits=0
  (( ring_hits >= RING_RECUR_MIN )) && in_ring=1
fi
# Update the ring (every command, probe or not) so alternation stays visible.
if [[ -n "$HASH" ]]; then
  { cat "$RING" 2>/dev/null; printf '%s\n' "$HASH"; } | grep -v '^$' | tail -n "$RING_N" > "${RING}.tmp" 2>/dev/null \
    && mv -f "${RING}.tmp" "$RING" 2>/dev/null || true
  rm -f "${RING}.tmp" 2>/dev/null || true   # clear an orphan if the mv failed (cross-device, unwritable)
fi

# --- Probe-shape classification ---
is_probe=0
# echo of a single token, EITHER quoted on both sides OR unquoted — `echo "se-flush-3"`,
# `echo probe`. Token starts alphanumeric (so `echo -n` doesn't match); a one-sided
# quote (`echo "token`) is a syntax error and is deliberately NOT classified as a probe.
if [[ "$CMD" =~ ^[[:space:]]*echo[[:space:]]+([\"\'][A-Za-z0-9][A-Za-z0-9_-]*[\"\']|[A-Za-z0-9][A-Za-z0-9_-]*)[[:space:]]*$ ]]; then is_probe=1; fi
# bare echo (no argument) and trivial no-ops used as liveness pings.
if [[ "$CMD" =~ ^[[:space:]]*(echo|true|false|:|pwd|date)[[:space:]]*$ ]]; then is_probe=1; fi
# short printf literal with no pipe/redirect (the <40-char gate keeps a real
# templated printf — `printf '%s\n' "$long_value"` — from being read as a probe).
if [[ "$CMD" =~ ^[[:space:]]*printf[[:space:]] ]] && [[ ! "$CMD" =~ [\|\>\<] ]] && [[ ${#CMD} -lt 40 ]]; then is_probe=1; fi
# sleep N (optionally chained with a trivial echo).
if [[ "$CMD" =~ ^[[:space:]]*sleep[[:space:]]+[0-9] ]]; then is_probe=1; fi
# recurrence within the ring.
if [[ "$in_ring" -eq 1 ]]; then is_probe=1; fi

nudge() {
  local count="$1"
  local msg="PROBE-SPRAY DETECTED: ${count} channel-test-shaped commands (echo / printf / sleep / no-op / repeated read) within ${WINDOW}s. This is the probe-spray loop — see docs/wiki/tool-output-flakiness-protocol.md § Not this protocol — blocked / no-return.

The channel is NOT broken: a real command returned recently, and a healthy 'git -C <path> log -1' returns in <1s. An empty / '(No output)' / cancel-cascade result is a blocked-or-dropped CALL, not a dead channel — re-running echo/printf/sleep variants (or firing 'se-flush' markers) diagnoses nothing and is the trap. A cancel-cascade specifically means one errored call in a parallel batch killed its siblings: issue smaller, same-failure-domain batches instead of more probes.

STOP spraying. Do ONE of:
  - run a single SOLO real command (the answer you actually need), not a probe;
  - if a call truly hung, diagnose the block (lock? permission prompt? cd-prefix?) instead of testing liveness.
Two probes for the same fact is already the stop signal. (Silence this in a legitimate echo/sleep-heavy run: COORDINATOR_PROBE_NUDGE_OFF=1.)"
  if command -v jq &>/dev/null; then
    jq -nc --arg m "$msg" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",additionalContext:$m}}'
  elif [[ -n "$PY" ]]; then
    local mj
    mj=$(printf '%s' "$msg" | "$PY" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || mj="\"$(printf '%s' "$msg" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":%s}}\n' "$mj"
  else
    local esc="${msg//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"%s"}}\n' "$esc"
  fi
}

if [[ "$is_probe" -eq 0 ]]; then
  # Real work — the channel demonstrably works. Reset the streak and cooldown.
  : > "$TIMES" 2>/dev/null || true
  rm -f "$COOL" 2>/dev/null || true
  exit 0
fi

# Prune the window and append this probe.
NEWTIMES=""
if [[ -f "$TIMES" ]]; then
  while IFS= read -r t; do
    [[ "$t" =~ ^[0-9]+$ ]] || continue
    if (( NOW - t <= WINDOW )); then NEWTIMES+="$t"$'\n'; fi
  done < "$TIMES"
fi
NEWTIMES+="$NOW"$'\n'
printf '%s' "$NEWTIMES" > "$TIMES" 2>/dev/null || true
# COUNT comes from the in-memory NEWTIMES, not a re-read of $TIMES: if the write
# failed (unwritable TMPDIR) state cannot persist, so COUNT stays 1 and we fail open.
COUNT=$(printf '%s' "$NEWTIMES" | grep -c . 2>/dev/null || echo 0)

if (( COUNT >= THRESHOLD )); then
  LASTNUDGE=$(cat "$COOL" 2>/dev/null || echo 0)
  [[ "$LASTNUDGE" =~ ^[0-9]+$ ]] || LASTNUDGE=0
  if (( NOW - LASTNUDGE >= COOLDOWN )); then
    printf '%s' "$NOW" > "$COOL" 2>/dev/null || true
    nudge "$COUNT"
    exit 0
  fi
fi

exit 0
