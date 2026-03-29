#!/bin/bash
# Context Pressure — Stop hook (primary threshold check)
#
# Fires once per turn when the model finishes generating. This is the
# primary warning mechanism for context pressure. PostToolUse carries
# the mid-chain safety net (throttled) and the post-compaction sentinel
# bridge — this script handles the clean end-of-turn check.
#
# Session-age gate: skips entirely if session is < 10 minutes old.
# On 1M Opus context, early sessions are nowhere near compaction risk.
set -euo pipefail

# --- Safe stdin read ---
if command -v timeout &>/dev/null; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat)
fi

# Extract fields
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | sed -n 's/.*"transcript_path"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)
fi

if [[ -z "$SESSION_ID" ]]; then
  exit 0
fi

# --- Session-age gate ---
# Skip if session is less than 10 minutes old. The session start time
# is recorded as a sentinel file's mtime on first check.
SESSION_BIRTH="/tmp/context-pressure-birth-${SESSION_ID}"
if [[ ! -f "$SESSION_BIRTH" ]]; then
  touch "$SESSION_BIRTH"
  exit 0  # first firing — session just started
fi

if [[ "$OSTYPE" == darwin* ]]; then
  BIRTH_MTIME=$(stat -f %m "$SESSION_BIRTH" 2>/dev/null || echo 0)
else
  BIRTH_MTIME=$(stat -c %Y "$SESSION_BIRTH" 2>/dev/null || echo 0)
fi
NOW=$(date +%s)
SESSION_AGE=$(( NOW - BIRTH_MTIME ))
if [[ "$SESSION_AGE" -lt 600 ]]; then
  exit 0  # session < 10 minutes old
fi

# --- Transcript size check ---
if [[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]]; then
  exit 0
fi

# Model detection (first 20 lines only)
MODEL_ID=""
if command -v jq &>/dev/null; then
  MODEL_ID=$(head -n 20 "$TRANSCRIPT_PATH" | jq -r 'select(.model != null) | .model' 2>/dev/null | head -1 || true)
fi
if [[ -z "$MODEL_ID" ]]; then
  MODEL_ID=$(head -n 20 "$TRANSCRIPT_PATH" | sed -n 's/.*"model"\s*:\s*"\([^"]*\)".*/\1/p' | head -1 || true)
fi

# Context window size by model (tokens)
case "$MODEL_ID" in
  *opus*4*6*|*opus-4-6*)     CONTEXT_WINDOW=1000000 ;;
  *sonnet*4*6*|*sonnet-4-6*) CONTEXT_WINDOW=200000  ;;
  *haiku*4*5*|*haiku-4-5*)   CONTEXT_WINDOW=200000  ;;
  *)                         CONTEXT_WINDOW=200000  ;;
esac

# Threshold percentages
ADVISORY_PCT=60
CRITICAL_PCT=78

# Convert to file size thresholds (bytes, ~5 bytes/token)
BYTES_PER_TOKEN=5
ADVISORY_BYTES=$(( CONTEXT_WINDOW * ADVISORY_PCT * BYTES_PER_TOKEN / 100 ))
CRITICAL_BYTES=$(( CONTEXT_WINDOW * CRITICAL_PCT * BYTES_PER_TOKEN / 100 ))

# Env var overrides for testing
ADVISORY_BYTES=${CONTEXT_ADVISORY_THRESHOLD:-$ADVISORY_BYTES}
CRITICAL_BYTES=${CONTEXT_CRITICAL_THRESHOLD:-$CRITICAL_BYTES}

# Get transcript file size
if [[ "$OSTYPE" == darwin* ]]; then
  FILE_SIZE=$(stat -f %z "$TRANSCRIPT_PATH" 2>/dev/null || echo 0)
else
  FILE_SIZE=$(stat -c %s "$TRANSCRIPT_PATH" 2>/dev/null || echo 0)
fi

if [[ "$FILE_SIZE" -eq 0 ]]; then
  exit 0
fi

# --- Bark-once sentinels ---
if command -v md5sum &>/dev/null; then
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | md5sum | cut -d' ' -f1)
elif command -v md5 &>/dev/null; then
  TRANSCRIPT_HASH=$(echo -n "$TRANSCRIPT_PATH" | md5 -q)
else
  TRANSCRIPT_HASH="$SESSION_ID"
fi

ADVISORY_SENTINEL="/tmp/context-pressure-advisory-${TRANSCRIPT_HASH}"
CRITICAL_SENTINEL="/tmp/context-pressure-critical-${TRANSCRIPT_HASH}"

# Autonomous run detection
AUTONOMOUS_SENTINEL="/tmp/autonomous-run-${SESSION_ID}"
AUTONOMOUS_RUN=false
if [[ -f "$AUTONOMOUS_SENTINEL" ]]; then
  AUTONOMOUS_RUN=true
fi

# Critical check first
if [[ "$FILE_SIZE" -ge "$CRITICAL_BYTES" && ! -f "$CRITICAL_SENTINEL" ]]; then
  touch "$ADVISORY_SENTINEL" "$CRITICAL_SENTINEL"
  EST_PCT=$(( FILE_SIZE * 100 / (CONTEXT_WINDOW * BYTES_PER_TOKEN) ))
  if [[ "$AUTONOMOUS_RUN" == true ]]; then
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Compaction is close (~83.5%). Autonomous run active — continuing per PM instruction. Verify all progress is in TaskList and committed to disk. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  else
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Compaction fires at ~83.5% of context window. You are close. RECOMMENDED: Run /handoff NOW to preserve session state. A fresh session will perform better. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
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
{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Context usage is getting heavy. Autonomous run active — continuing per PM instruction. Ensure flight recorder (TaskList) is current so work survives compaction. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  else
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Context usage is getting heavy. Consider completing the current task unit, then running /handoff. This is informational — no action required yet. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  fi
  exit 0
fi

exit 0
