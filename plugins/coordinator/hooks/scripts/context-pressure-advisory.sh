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
set -euo pipefail

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
  rm -f "$COMPACTION_SENTINEL"

  STATE_CONTENT=""
  if [[ -f "$COMPACTION_STATE" ]]; then
    STATE_CONTENT=$(cat "$COMPACTION_STATE" 2>/dev/null || true)
    rm -f "$COMPACTION_STATE"
  fi

  if [[ -n "$STATE_CONTENT" ]]; then
    ESCAPED_STATE=$(printf '%s' "$STATE_CONTENT" | jq -Rs '.' | sed 's/^"//; s/"$//')
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "COMPACTION OCCURRED: Context was compressed. Tasks survived (use TaskList/TaskGet to re-orient). Re-read any active plan files to restore continuity. Key decisions should already be on disk — verify by checking your task list. Check metadata.tried_and_abandoned on tasks for failed approaches before retrying anything.\\n\\n--- PRE-COMPACTION STATE SNAPSHOT ---\\n${ESCAPED_STATE}\\n--- END SNAPSHOT ---"}}
JSONEOF
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

# Research (2026-03-21): Compaction fires at ~83.5% of context window
# (33K token buffer reserved from 200K window → ~167K trigger point).
# We can't know exact token count — file size in bytes is a rough proxy.
# Using ~5 bytes/token (conservative: real ratio is 5-8 depending on content).

if [[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]]; then
  exit 0  # fail-open: no transcript to measure
fi

# --- Model detection (first 20 lines only — O(1) regardless of transcript size) ---
MODEL_ID=""
if command -v jq &>/dev/null; then
  MODEL_ID=$(head -n 20 "$TRANSCRIPT_PATH" | jq -r 'select(.model != null) | .model' 2>/dev/null | head -1 || true)
fi
if [[ -z "$MODEL_ID" ]]; then
  MODEL_ID=$(head -n 20 "$TRANSCRIPT_PATH" | sed -n 's/.*"model"\s*:\s*"\([^"]*\)".*/\1/p' | head -1 || true)
fi

# --- Context window size by model (tokens) ---
case "$MODEL_ID" in
  *opus*4*6*|*opus-4-6*)     CONTEXT_WINDOW=1000000 ;;  # Opus 4.6: 1M tokens
  *sonnet*4*6*|*sonnet-4-6*) CONTEXT_WINDOW=200000  ;;  # Sonnet 4.6: 200K tokens
  *haiku*4*5*|*haiku-4-5*)   CONTEXT_WINDOW=200000  ;;  # Haiku 4.5: 200K tokens
  *)                         CONTEXT_WINDOW=200000  ;;  # Conservative default
esac

# --- Threshold percentages ---
ADVISORY_PCT=60
CRITICAL_PCT=78

# --- Convert to file size thresholds (bytes) ---
BYTES_PER_TOKEN=5
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
else
  TRANSCRIPT_HASH="$SESSION_ID"
fi

# Stale sentinel cleanup (>24h old)
find /tmp -maxdepth 1 \( -name "context-pressure-*" -o -name "autonomous-run-*" \) -mmin +1440 -delete 2>/dev/null || true

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
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Compaction is close (~83.5%). Autonomous run active — continuing per PM instruction. Verify all progress is in TaskList and committed to disk. Compaction will compress context but tasks persist. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  else
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Compaction fires at ~83.5% of context window. You are close. RECOMMENDED: Run /handoff NOW to preserve session state. A fresh session will perform better. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  fi
  exit 0
fi

# Advisory check
if [[ "$FILE_SIZE" -ge "$ADVISORY_BYTES" && ! -f "$ADVISORY_SENTINEL" ]]; then
  touch "$ADVISORY_SENTINEL"
  EST_PCT=$(( FILE_SIZE * 100 / (CONTEXT_WINDOW * BYTES_PER_TOKEN) ))
  if [[ "$AUTONOMOUS_RUN" == true ]]; then
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Context usage is getting heavy. Autonomous run active — continuing per PM instruction. Ensure flight recorder (TaskList) is current so work survives compaction. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  else
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Context usage is getting heavy. Consider completing the current task unit, then running /handoff. This is informational — no action required yet. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  fi
  exit 0
fi

exit 0
