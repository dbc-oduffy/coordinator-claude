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
#
# Sourceable interface: check_probe_spray <command> <session_id>
# When sourced, only the function is defined; no execution occurs at source time.

# check_probe_spray <command> <session_id>
# Contains all decision logic. Must NOT read stdin. Takes the Bash tool command as
# $1 and the session_id as $2. On trigger, prints the nested hookSpecificOutput JSON
# and returns 0. On no-trigger, prints nothing and returns 0.
check_probe_spray() {
  local CMD="$1"
  local SESSION_ID="$2"

  local PY
  PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)  # || true keeps PY set for set -u

  [[ -z "$CMD" ]] && return 0
  [[ "${COORDINATOR_PROBE_NUDGE_OFF:-0}" == "1" ]] && return 0

  local NOW
  NOW=$(date +%s 2>/dev/null || echo 0)
  # If the clock is unreadable the window math is meaningless (and NOW=0 entries
  # would never expire) — degrade to a no-op rather than misfire.
  [[ "$NOW" =~ ^[0-9]+$ ]] || return 0   # non-integer clock ⇒ window math meaningless; degrade to no-op
  [[ "$NOW" -eq 0 ]] && return 0

  # --- Session-keyed state (concurrent sessions never share a file) ---
  local KEY="${SESSION_ID:-${CLAUDE_SESSION_ID:-${PPID:-default}}}"
  KEY="${KEY//[^A-Za-z0-9_-]/_}"
  local STATE_DIR="${TMPDIR:-/tmp}"
  local PREFIX="${STATE_DIR}/coordinator-probe-spray-${KEY}"
  local TIMES="${PREFIX}.times"
  local RING="${PREFIX}.ring"
  local COOL="${PREFIX}.cool"

  local WINDOW=90        # seconds — probes older than this fall out of the streak
  local THRESHOLD=3      # probes within WINDOW before the first nudge
  local COOLDOWN=30      # seconds between nudges (one mechanism, applies equally to the low-signal
                         # streak and a strong-probe burst — a strong burst nudges once because
                         # EFFECTIVE_THRESHOLD=1 lets it reach this same gate immediately).
  local RING_N=8         # recent commands retained for recurrence detection
  local RING_RECUR_MIN=2 # a command must ALREADY appear this many times in the ring before
                         # a further occurrence counts as a probe — so a legitimately
                         # repeated real command (make, git log) gets latitude, while a
                         # trivial channel probe is caught directly by a shape classifier

  # Amortized cleanup of stale state files (~1 in 50 invocations); never fatal.
  if (( RANDOM % 50 == 0 )); then
    find "$STATE_DIR" -maxdepth 1 -name 'coordinator-probe-spray-*' -mmin +180 -delete 2>/dev/null || true
  fi

  # Hash is only meaningful if cksum exists; absent it, recurrence detection is
  # disabled (shape classifiers still fire) — graceful degradation, never a block.
  local HASH=""
  if command -v cksum &>/dev/null; then
    HASH=$(printf '%s' "$CMD" | cksum 2>/dev/null | awk '{print $1}' || true)
  fi

  # --- Recurrence: has this exact command ALREADY recurred in the recent ring? ---
  # Counting occurrences (not mere presence) so a build/test command repeated once or
  # twice during normal iteration is not mistaken for channel-probing — only sustained
  # repetition crosses the bar.
  local in_ring=0
  if [[ -n "$HASH" && -f "$RING" ]]; then
    local ring_hits
    ring_hits=$(grep -cxF "$HASH" "$RING" 2>/dev/null || true)   # grep exits 1 on no-match but -c still prints 0; || true makes that explicit
    [[ "$ring_hits" =~ ^[0-9]+$ ]] || ring_hits=0
    (( ring_hits >= RING_RECUR_MIN )) && in_ring=1
  fi
  # Update the ring (every command, probe or not) so alternation stays visible.
  if [[ -n "$HASH" ]]; then
    # A && B || C here is intentional, not if-then-else: a failed mv is recovered by the rm on
    # the next line, and a missed ring update only weakens recurrence detection (never blocks).
    # The || true keeps set -e calm; do not "fix" it into a branch.
    # shellcheck disable=SC2015
    { cat "$RING" 2>/dev/null; printf '%s\n' "$HASH"; } | grep -v '^$' | tail -n "$RING_N" > "${RING}.tmp" 2>/dev/null \
      && mv -f "${RING}.tmp" "$RING" 2>/dev/null || true
    rm -f "${RING}.tmp" 2>/dev/null || true   # clear an orphan if the mv failed (cross-device, unwritable)
  fi

  # --- Probe-shape classification ---
  local is_probe=0
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

  # --- High-signal liveness probes (near-zero false positive; nudge on FIRST occurrence) ---
  # The single-token echo classifier above stops at the first `$` so it cannot see
  # `echo alive-$(date +%s)` — and that timestamped form ALSO defeats recurrence
  # detection (every probe hashes uniquely), so the shape classifier is the ONLY net
  # that can catch it. Echoing the wall clock or a liveness lexeme has essentially one
  # purpose (proving the channel is alive), so these warrant a first-occurrence nudge
  # rather than the 3-streak the low-signal shapes (bare echo / true / pwd) need.
  # Narrowed to dodge real work: `echo "head: $(git rev-parse HEAD)"` has no date/nonce
  # and no liveness lexeme, so it stays classified as real.
  local is_strong_probe=0
  # tr absent: CMD_LC = CMD (case-sensitive fallback; acceptable degradation — tr is
  # present on all POSIX systems, and the hook is offer-only so a missed match is benign).
  local CMD_LC
  CMD_LC=$(printf '%s' "$CMD" | tr '[:upper:]' '[:lower:]' 2>/dev/null || printf '%s' "$CMD")
  # Patterns are held in SINGLE-QUOTED vars and matched via `[[ "$x" =~ $var ]]`. This is
  # the safe idiom for ERE patterns containing shell metacharacters: single quotes neutralise
  # `$`, `(`, and the backtick at assignment time, and a *variable* on the =~ RHS is taken
  # literally as the regex (no command substitution). This structurally removes the parse-time
  # hazard that an inline `date / $(date) pattern carries — the bug that broke this hook once.
  # Do NOT inline these patterns or quote the var on the RHS (`=~ "$var"` matches a literal string).
  #
  # ts_probe_pat: echo emitting the wall clock or a nonce. $SECONDS is deliberately EXCLUDED —
  # it is bash's elapsed-time counter (real timing scripts do `echo $SECONDS`), not a liveness
  # nonce. lexeme_pat: distinctive liveness words, word-boundary-fenced so substrings don't
  # over-match (shipping≠ping, reprobed≠probe). The ambiguous tokens `ping`/`probe` are omitted —
  # they recur in real output and their bare form is already caught by the single-token
  # classifier at the 3-streak, so omitting them loses only the first-occurrence upgrade.
  # `se-flush` is omitted for the SAME reason, with an extra wrinkle: the real-world spray is the
  # numbered marker `echo "se-flush-3"` (not a bare `se-flush`), and because the lexeme itself
  # contains a hyphen the `[^a-z0-9_]` boundary fence treats the trailing `-3` as a word boundary —
  # so a first-occurrence-upgrade here would wrongly fire on the marker's FIRST emission. The
  # numbered-marker shape is already caught by the single-token echo classifier at the 3-streak,
  # which is the intended behaviour (Scenario I in test-nudge-probe-spray.sh).
  # single quotes are DELIBERATE: no expansion is the whole point (literal ERE for the =~ RHS).
  # SC2016's "did you mean double quotes" is the opposite of intent here.
  # shellcheck disable=SC2016
  local ts_probe_pat='(\$\(date|`date|\$EPOCHSECONDS|\$RANDOM)'
  # shellcheck disable=SC2016
  local lexeme_pat='(^|[^a-z0-9_])(alive|heartbeat|chan[_-]?ok|still[_-](alive|here|there))([^a-z0-9_]|$)'
  if [[ "$CMD" =~ ^[[:space:]]*echo[[:space:]] ]] && [[ "$CMD" =~ $ts_probe_pat ]] && [[ ! "$CMD" =~ [\|\>] ]]; then is_strong_probe=1; fi
  if [[ "$CMD_LC" =~ ^[[:space:]]*echo[[:space:]] ]] && [[ "$CMD_LC" =~ $lexeme_pat ]] && [[ ! "$CMD" =~ [\|\>] ]]; then is_strong_probe=1; fi
  (( is_strong_probe )) && is_probe=1

  # nudge: inner helper; accesses WINDOW and PY via dynamic scoping from check_probe_spray.
  _probe_nudge() {
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
      mj=$(printf '%s' "$msg" | "$PY" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null)
      # json.dumps on a str is total, so this guards the RARE python-PROCESS failure (crash /
      # broken install / signal) that would otherwise leave mj empty → malformed JSON. Same
      # escape idiom as the no-python branch below (one idiom, no sed/tr); the only difference is
      # the quotes are added INTO mj here to match json.dumps's already-quoted-string shape, since
      # this branch's printf uses a bare %s (the no-python branch quotes in its format string).
      if [[ -z "$mj" ]]; then
        local esc="${msg//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"; mj="\"$esc\""
      fi
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
    return 0
  fi

  # Prune the window and append this probe.
  local NEWTIMES=""
  if [[ -f "$TIMES" ]]; then
    local t
    while IFS= read -r t; do
      [[ "$t" =~ ^[0-9]+$ ]] || continue
      if (( NOW - t <= WINDOW )); then NEWTIMES+="$t"$'\n'; fi
    done < "$TIMES"
  fi
  NEWTIMES+="$NOW"$'\n'
  printf '%s' "$NEWTIMES" > "$TIMES" 2>/dev/null || true
  # COUNT comes from the in-memory NEWTIMES, not a re-read of $TIMES: if the write
  # failed (unwritable TMPDIR) state cannot persist, so COUNT stays 1 and we fail open.
  local COUNT
  COUNT=$(printf '%s' "$NEWTIMES" | grep -c . 2>/dev/null || echo 0)

  # High-signal liveness shapes nudge on first occurrence; low-signal shapes need the
  # 3-streak so a single legitimate `true`/`pwd`/bare-echo is never nagged. The cooldown
  # below still applies, so a burst of strong probes nudges once, not per-probe.
  local EFFECTIVE_THRESHOLD=$THRESHOLD
  (( is_strong_probe )) && EFFECTIVE_THRESHOLD=1

  if (( COUNT >= EFFECTIVE_THRESHOLD )); then
    local LASTNUDGE
    LASTNUDGE=$(cat "$COOL" 2>/dev/null || echo 0)
    [[ "$LASTNUDGE" =~ ^[0-9]+$ ]] || LASTNUDGE=0
    if (( NOW - LASTNUDGE >= COOLDOWN )); then
      printf '%s' "$NOW" > "$COOL" 2>/dev/null || true
      _probe_nudge "$COUNT"
      return 0
    fi
  fi

  return 0
}

# Main guard: runs only when executed directly (not sourced).
# Reads stdin once, parses tool_name + command + session_id, calls check_probe_spray.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -uo pipefail

  PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)  # || true keeps PY set for set -u

  if command -v timeout &>/dev/null; then
    INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    # No external `timeout` (macOS without coreutils, minimal images): use bash's BUILTIN
    # read timeout so a harness that holds stdin open cannot hang every Bash call. `-d ''`
    # reads through newlines to EOF/timeout; `|| true` keeps set -u/-e calm on the non-zero
    # read returns at EOF/timeout (INPUT is still populated with whatever was read).
    IFS= read -r -d '' -t 2 INPUT 2>/dev/null || true
    INPUT="${INPUT:-}"
  fi

  # Parse tool_name + command + session_id. session_id comes from the hook payload
  # itself (stable across a session's tool calls) — unlike $PPID, which is per-bash-
  # invocation and would silently disable the window.
  TOOL_NAME=""
  CMD=""
  SESSION_ID=""
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

  check_probe_spray "$CMD" "$SESSION_ID"
  exit 0
fi
