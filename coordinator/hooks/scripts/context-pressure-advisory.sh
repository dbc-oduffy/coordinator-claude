#!/bin/bash
# Context Pressure Advisory — PostToolUse hook
#
# Moved from UserPromptSubmit (2026-03-28): UserPromptSubmit hooks block
# before the model generates ANY response. On Windows/Git Bash, timeout
# enforcement is unreliable — a hung stdin read on every message killed
# all sessions. PostToolUse is safer: fires after a tool completes, so a
# hang only delays the next tool step rather than freezing the terminal.
#
# Phase 1: Post-compaction orientation (sentinel bridge) — checked every
#          invocation (cheap stat call, no throttle)
# Phase 2: Threshold-based warnings — self-throttled to run every 5 min
#
# Hook execution is serial within a session — no TOCTOU risk on sentinel
# check-then-delete.
set -uo pipefail
# NOTE: -e deliberately omitted. This is an advisory hook and must fail-open;
# critical sections use explicit `|| true` guards. A blanket -e would abort
# the hook on any subcommand non-zero (e.g., stat/jq/find), defeating that.

# --- Safe stdin read (the fix for the Windows hang) ---
# GNU timeout is available in Git Bash via coreutils. If somehow missing,
# fall back to plain cat — the PostToolUse hook is far less dangerous than
# UserPromptSubmit even without the timeout wrapper.
if command -v timeout &>/dev/null; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat)
fi

# Extract fields — prefer jq, fall back to sed
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | sed -n 's/.*"transcript_path"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)
fi

if [[ -z "$SESSION_ID" ]]; then
  exit 0  # fail-open
fi

# --- Phase 1: Post-compaction sentinel bridge ---
# PreCompact writes /tmp/compaction-occurred-{SESSION_ID} as a side-effect,
# plus /tmp/compaction-state-{SESSION_ID}.md with session state snapshot.
# We detect the sentinel here, read the state, and emit both. Delete-on-read.
# No throttle — compaction recovery should fire on the first tool use after.
COMPACTION_SENTINEL="/tmp/compaction-occurred-${SESSION_ID}"
COMPACTION_STATE="/tmp/compaction-state-${SESSION_ID}.md"

if [[ -f "$COMPACTION_SENTINEL" ]]; then
  # Read pre-compaction transcript size recorded by precompact hook, then
  # delete the sentinel.
  PRE_SIZE=$(head -1 "$COMPACTION_SENTINEL" 2>/dev/null | tr -d '[:space:]' || true)
  rm -f "$COMPACTION_SENTINEL"

  # False-positive guard: Claude Code fires PreCompact in scenarios that don't
  # actually shrink the parent transcript meaningfully (notably subagent-result
  # integration on 1M-context models). If the transcript size hasn't dropped
  # at least 15% since precompact fired, treat as a false alarm: clean up state
  # and exit silently rather than emitting a misleading orientation prompt.
  if [[ -n "$PRE_SIZE" && "$PRE_SIZE" =~ ^[0-9]+$ && -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
    POST_SIZE=$(stat -c '%s' "$TRANSCRIPT_PATH" 2>/dev/null || stat -f '%z' "$TRANSCRIPT_PATH" 2>/dev/null || echo "$PRE_SIZE")
    # Threshold: post must be < pre * 0.85 (i.e., >=15% shrink) to count as real.
    THRESHOLD=$(( PRE_SIZE * 85 / 100 ))
    if [[ "$POST_SIZE" -ge "$THRESHOLD" ]]; then
      # No meaningful shrink — silently consume associated state and exit.
      rm -f "$COMPACTION_STATE"
      exit 0
    fi
  fi

  STATE_CONTENT=""
  if [[ -f "$COMPACTION_STATE" ]]; then
    STATE_CONTENT=$(cat "$COMPACTION_STATE" 2>/dev/null || true)
    rm -f "$COMPACTION_STATE"
  fi

  if [[ -n "$STATE_CONTENT" ]]; then
    PREAMBLE="COMPACTION OCCURRED: Context was compressed. Tasks survived (use TaskList/TaskGet to re-orient). Re-read any active plan files to restore continuity. Key decisions should already be on disk — verify by checking your task list. Check metadata.tried_and_abandoned on tasks for failed approaches before retrying anything.\n\n--- PRE-COMPACTION STATE SNAPSHOT ---\n"
    POSTAMBLE="\n--- END SNAPSHOT ---"
    jq -n \
      --arg preamble "$PREAMBLE" \
      --arg state "$STATE_CONTENT" \
      --arg postamble "$POSTAMBLE" \
      '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ($preamble + $state + $postamble)}}'
  else
    cat <<'JSONEOF'
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COMPACTION OCCURRED: Context was compressed. Tasks survived (use TaskList/TaskGet to re-orient). Re-read any active plan files to restore continuity. Key decisions should already be on disk — verify by checking your task list. Check metadata.tried_and_abandoned on tasks for failed approaches before retrying anything."}}
JSONEOF
  fi
  exit 0
fi

# --- Phase 2: Threshold-based context pressure warnings ---
# Self-throttle: only run the expensive transcript size check every 5 minutes.
# The sentinel file's mtime is the clock. On every other invocation we exit
# immediately — this keeps PostToolUse overhead near zero.
THROTTLE_SENTINEL="/tmp/context-pressure-throttle-${SESSION_ID}"
THROTTLE_SECONDS=300  # 5 minutes

if [[ -f "$THROTTLE_SENTINEL" ]]; then
  # Check age of throttle sentinel
  if [[ "$OSTYPE" == darwin* ]]; then
    SENTINEL_MTIME=$(stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || echo 0)
  else
    SENTINEL_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || echo 0)
  fi
  NOW=$(date +%s)
  ELAPSED=$(( NOW - SENTINEL_MTIME ))
  if [[ "$ELAPSED" -lt "$THROTTLE_SECONDS" ]]; then
    exit 0  # fast path — checked recently, skip
  fi
fi

# Update throttle timestamp (touch even if we end up not emitting anything)
touch "$THROTTLE_SENTINEL"

# Calibration (2026-05-18, observed on Opus 1M): auto-compaction now fires at
# ~60% of context window (e.g. 600K on a 1M window). Earlier research had it
# at ~83.5% on a 200K window; treat 60% as the new global trigger until we
# observe per-model divergence. Override via CONTEXT_*_THRESHOLD env vars.
# We can't know exact token count — file size in bytes is a ROUGH proxy.
# Read-heavy EM sessions (markdown/substrate/JSON) run 6-8 bytes/token; prose ~4-5.
# 7 is mid-band, biased to the read-heavy case this hook front-loads on.
# Recalibrated 2026-05-27 (queue 2026-05-26): prior value 5 over-counted tokens
# on read-heavy transcripts and fired HIGH at a real ~55% byte-of-window with
# runway left. CRITICAL_PCT is HELD at 50 (ratio-only recalibration, PM decision
# 2026-05-27): the BPT 5→7 change shifts the trip ~40% later in bytes, addressing
# the premature-firing report without stacking a percentage-gate raise.

if [[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]]; then
  exit 0  # fail-open: no transcript to measure
fi

# --- Model detection — robust, format- and preamble-agnostic ---
# Two prior bugs (fixed here, 2026-05-26): (1) the jq path read top-level
# `.model`, but Claude Code nests it at `.message.model`, so it never matched;
# (2) the sed fallback was capped at `head -n 20`, but preamble-heavy sessions
# (pickup handoffs, attachments, queue-ops, system reminders) push the first
# assistant line — the first one carrying a model ID — well past line 20. The
# net effect was MODEL_ID="" on exactly the read-heavy sessions an EM front-loads
# context on, defaulting CONTEXT_WINDOW to 200K and firing a false CRITICAL at
# ~500KB (~11% of a real 1M Opus window). Grep the first literal
# `"model":"claude-..."` instead: -m1 stops at the first matching LINE (cost
# bounded by the first model-bearing line, not transcript size), the `claude-`
# anchor disambiguates from any other "model" key in tool output, and it is
# agnostic to JSON nesting. The `[^"]*` character class (no embedded quote) is
# load-bearing twice: it terminates the ID at the closing quote, AND it
# guarantees MODEL_ID can never contain a `"` that would break the unquoted JSON
# heredocs below — do not widen it without re-checking those heredocs. The
# trailing `head -1` defends against a minified line carrying multiple matches.
MODEL_ID=$(grep -m1 -oE '"model"[[:space:]]*:[[:space:]]*"claude-[^"]*"' "$TRANSCRIPT_PATH" 2>/dev/null \
  | grep -oE 'claude-[^"]*' | head -1 || true)
# Detection-failure diagnostic (stderr only — never touches the JSON stdout the
# hook consumer parses). Surfaces the silent case Finding 7 flagged: an
# undetected model assumes the 1M default below, which on a genuinely-200K setup
# means warnings fire too late (or never). Rare given the robust detection above.
if [[ -z "$MODEL_ID" ]]; then
  echo "context-pressure-advisory: model detection failed; assuming 1M-token window (pin via COORDINATOR_DEFAULT_CONTEXT_WINDOW for 200K setups)" >&2
fi

# --- Context window size by model (tokens) ---
# Note: Anthropic encodes 1M-context variants with a "[1m]" suffix on the model ID
# (e.g., "claude-opus-4-7[1m]"). Match that suffix explicitly before the bare model
# pattern so a plain ID falls through to the 200K default.
case "$MODEL_ID" in
  # Explicit 1M-context variants — must match before the bare family arms below.
  # Anthropic encodes 1M-context variants with a "[1m]" suffix (e.g.
  # "claude-opus-4-7[1m]"); some ID shapes use a "-1m" infix.
  # Matching here prevents a 1M-context Sonnet from falling into the *sonnet*
  # arm and producing false-positive handoff nudges at ~200K bytes.
  # NB: no bare `*1m*` arm — it would false-match a date/version token (e.g.
  # a hypothetical "claude-sonnet-4-10m") and assign a 200K model the 1M window.
  *\[1m\]*)       CONTEXT_WINDOW=1000000 ;;  # Explicit "[1m]" suffix
  *-1m*)          CONTEXT_WINDOW=1000000 ;;  # "-1m" infix variant
  # Explicit 200K overrides for Opus variants known to ship without the 1M window
  # (add specific model IDs here as they appear).
  # Generic family fallbacks — any Opus is presumed 1M, any Sonnet/Haiku 200K,
  # unless an override above caught it first.
  # Family-fallback patterns survive minor version bumps; pinned arms break.
  *opus*)         CONTEXT_WINDOW=1000000 ;;  # Opus family default: 1M
  *sonnet*)       CONTEXT_WINDOW=200000  ;;  # Sonnet family default: 200K
  *haiku*)        CONTEXT_WINDOW=200000  ;;  # Haiku family default: 200K
  # Unknown model OR detection failure (empty MODEL_ID): with robust detection
  # above this arm is now rarely reached, but it is also the error-recovery path
  # (grep failure / transcript race), so do not delete it as "only for unknown
  # models". Default to Opus/1M — Opus is the EM's primary system, and a too-large window
  # only delays warnings (it never fires a false CRITICAL), which is the safer
  # failure direction than the prior 200K default's premature-handoff churn.
  # Sonnet-only setups can pin the conservative window via the override.
  *)              CONTEXT_WINDOW=${COORDINATOR_DEFAULT_CONTEXT_WINDOW:-1000000} ;;
esac

# --- Threshold percentages ---
# Auto-compaction trigger observed at ~60% of context window (2026-05-18).
# CRITICAL at 50% gives ~10% headroom before compaction — enough for a handoff
# to execute (several tool calls). ADVISORY at 40% is the "start wrapping up"
# signal. Previous values (57/50) fired too late and sessions hit compaction
# before the handoff could complete.
# CRITICAL_PCT HELD at 50 (PM decision 2026-05-27, ratio-only): the BYTES_PER_TOKEN 5→7
# change alone shifts the trip ~40% later in bytes, addressing the premature-firing report
# without stacking a percentage-gate raise that would erode compaction headroom on
# prose-light sessions. ~10% headroom below the ~60% observed compaction point is preserved.
ADVISORY_PCT=40
CRITICAL_PCT=50

# --- Convert to file size thresholds (bytes) ---
# Read-heavy EM sessions (markdown/substrate/JSON) run 6-8 bytes/token; prose ~4-5.
# 5 (prior value) over-counted tokens on read-heavy transcripts and fired HIGH at a
# real ~55% byte-of-window with runway left (queue 2026-05-26). 7 is mid-band, biased
# to the read-heavy case this hook front-loads on. Still a ROUGH proxy — see message text.
BYTES_PER_TOKEN=7
ADVISORY_BYTES=$(( CONTEXT_WINDOW * ADVISORY_PCT * BYTES_PER_TOKEN / 100 ))
CRITICAL_BYTES=$(( CONTEXT_WINDOW * CRITICAL_PCT * BYTES_PER_TOKEN / 100 ))

# --- Env var overrides for testing/recalibration ---
ADVISORY_BYTES=${CONTEXT_ADVISORY_THRESHOLD:-$ADVISORY_BYTES}
CRITICAL_BYTES=${CONTEXT_CRITICAL_THRESHOLD:-$CRITICAL_BYTES}

# --- Get transcript file size (cross-platform) ---
if [[ "$OSTYPE" == darwin* ]]; then
  FILE_SIZE=$(stat -f %z "$TRANSCRIPT_PATH" 2>/dev/null || echo 0)
else
  FILE_SIZE=$(stat -c %s "$TRANSCRIPT_PATH" 2>/dev/null || echo 0)
fi

if [[ "$FILE_SIZE" -eq 0 ]]; then
  exit 0  # fail-open
fi

# --- Bark-once sentinels (scoped to transcript path hash) ---
if command -v md5sum &>/dev/null; then
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | md5sum | cut -d' ' -f1)
elif command -v md5 &>/dev/null; then
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | md5 -q)
elif command -v cksum &>/dev/null; then
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | cksum | awk '{print $1}')
else
  TRANSCRIPT_HASH="$SESSION_ID"
fi

# Stale sentinel cleanup (>24h old) — scope to this session only.
# Previously this matched all sessions' sentinels, so session A's cleanup
# would delete session B's live sentinels. SESSION_ID is guaranteed non-empty
# here (we exit early above when it's blank), but guard defensively.
if [[ -n "${SESSION_ID:-}" ]]; then
  find /tmp -maxdepth 1 \( -name "context-pressure-*${SESSION_ID}*" -o -name "autonomous-run-*${SESSION_ID}*" \) -mmin +1440 -delete 2>/dev/null || true
fi

# --- Autonomous run detection ---
AUTONOMOUS_SENTINEL="/tmp/autonomous-run-${SESSION_ID}"
AUTONOMOUS_RUN=false
if [[ -f "$AUTONOMOUS_SENTINEL" ]]; then
  AUTONOMOUS_RUN=true
fi

ADVISORY_SENTINEL="/tmp/context-pressure-advisory-${TRANSCRIPT_HASH}"
CRITICAL_SENTINEL="/tmp/context-pressure-critical-${TRANSCRIPT_HASH}"

# Critical check first (higher priority)
if [[ "$FILE_SIZE" -ge "$CRITICAL_BYTES" && ! -f "$CRITICAL_SENTINEL" ]]; then
  touch "$ADVISORY_SENTINEL" "$CRITICAL_SENTINEL"
  EST_PCT=$(( FILE_SIZE * 100 / (CONTEXT_WINDOW * BYTES_PER_TOKEN) ))
  if [[ "$AUTONOMOUS_RUN" == true ]]; then
    jq -n \
      --arg ctx "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}): est. ~${EST_PCT}% of window used — a ROUGH byte-based proxy (~${BYTES_PER_TOKEN} bytes/token), not a measured token count. Compaction is close (~60%). Autonomous run active — continuing per PM instruction. Verify all progress is in TaskList and committed to disk. Compaction will compress context but tasks persist. The estimate runs hot on read-heavy sessions. (Transcript: ${FILE_SIZE} bytes vs ${CONTEXT_WINDOW}-token window)" \
      '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
  else
    jq -n \
      --arg ctx "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}): est. ~${EST_PCT}% of window used — a ROUGH byte-based proxy (~${BYTES_PER_TOKEN} bytes/token), not a measured token count, so treat it as a soft signal. Auto-compaction is observed near ~60%. If this estimate looks right for the work you've done, consider running /handoff soon — the handoff itself consumes context, so leave headroom. If you front-loaded large reads (the estimate runs hot on read-heavy sessions), you likely have more runway than this suggests. (Transcript: ${FILE_SIZE} bytes vs ${CONTEXT_WINDOW}-token window)" \
      '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
  fi
  exit 0
fi

# Advisory check
if [[ "$FILE_SIZE" -ge "$ADVISORY_BYTES" && ! -f "$ADVISORY_SENTINEL" ]]; then
  touch "$ADVISORY_SENTINEL"
  EST_PCT=$(( FILE_SIZE * 100 / (CONTEXT_WINDOW * BYTES_PER_TOKEN) ))
  if [[ "$AUTONOMOUS_RUN" == true ]]; then
    jq -n \
      --arg ctx "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}): est. ~${EST_PCT}% of window used — a ROUGH byte-based proxy (~${BYTES_PER_TOKEN} bytes/token), not a measured token count. Context usage is getting heavy. Autonomous run: checkpoint state to disk at the next natural boundary so the run is resumable. The estimate runs hot on read-heavy sessions. (Transcript: ${FILE_SIZE} bytes vs ${CONTEXT_WINDOW}-token window)" \
      '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
  else
    jq -n \
      --arg ctx "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}): est. ~${EST_PCT}% of window used — a ROUGH byte-based proxy (~${BYTES_PER_TOKEN} bytes/token), not a measured token count. Context usage is getting heavy. Consider completing the current task unit, then running /handoff. This is informational — no action required yet, and the estimate runs hot on read-heavy sessions. (Transcript: ${FILE_SIZE} bytes vs ${CONTEXT_WINDOW}-token window)" \
      '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": $ctx}}'
  fi
  exit 0
fi

exit 0
