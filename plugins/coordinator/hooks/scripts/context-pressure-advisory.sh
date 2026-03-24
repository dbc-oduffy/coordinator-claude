#!/bin/bash
# Context Pressure Advisory — UserPromptSubmit hook
#
# Phase 1: Post-compaction orientation (sentinel bridge)
# Phase 2: Threshold-based warnings (added after research)
#
# Hook execution is serial within a session — no TOCTOU risk on sentinel
# check-then-delete. If hooks ever execute concurrently, this would need
# an atomic rename-based claim pattern.
set -euo pipefail

HOOK_INPUT=$(cat)

# Extract fields — prefer jq, fall back to grep for environments without it
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
COMPACTION_SENTINEL="/tmp/compaction-occurred-${SESSION_ID}"
COMPACTION_STATE="/tmp/compaction-state-${SESSION_ID}.md"

if [[ -f "$COMPACTION_SENTINEL" ]]; then
  rm -f "$COMPACTION_SENTINEL"

  # Read state snapshot if available (best-effort — may not exist)
  STATE_CONTENT=""
  if [[ -f "$COMPACTION_STATE" ]]; then
    STATE_CONTENT=$(cat "$COMPACTION_STATE" 2>/dev/null || true)
    rm -f "$COMPACTION_STATE"
  fi

  if [[ -n "$STATE_CONTENT" ]]; then
    # Emit with state snapshot — escape for JSON embedding
    # Review: Patrik — sed pipeline using § intermediary breaks on content with § or control chars; jq -Rs is safe
    # Strip the surrounding quotes jq adds so the value embeds cleanly into the outer JSON string
    ESCAPED_STATE=$(printf '%s' "$STATE_CONTENT" | jq -Rs '.' | sed 's/^"//; s/"$//')
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "COMPACTION OCCURRED: Context was compressed. Tasks survived (use TaskList/TaskGet to re-orient). Re-read any active plan files to restore continuity. Key decisions should already be on disk — verify by checking your task list. Check metadata.tried_and_abandoned on tasks for failed approaches before retrying anything.\\n\\n--- PRE-COMPACTION STATE SNAPSHOT ---\\n${ESCAPED_STATE}\\n--- END SNAPSHOT ---"}}
JSONEOF
  else
    # No state file — emit original message
    cat <<'JSONEOF'
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "COMPACTION OCCURRED: Context was compressed. Tasks survived (use TaskList/TaskGet to re-orient). Re-read any active plan files to restore continuity. Key decisions should already be on disk — verify by checking your task list. Check metadata.tried_and_abandoned on tasks for failed approaches before retrying anything."}}
JSONEOF
  fi
  exit 0
fi

# --- Phase 2: Threshold-based context pressure warnings ---
# Research (2026-03-21): Compaction fires at ~83.5% of context window
# (33K token buffer reserved from 200K window → ~167K trigger point).
# Thresholds are proportional to each model's context window size.
#
# We can't know exact token count — file size in bytes is a rough proxy.
# Using ~5 bytes/token (conservative: real ratio is 5-8 depending on content).
# This deliberately errs toward early warning: false positives are cheap,
# false negatives (missing the window) are expensive.

if [[ -z "$TRANSCRIPT_PATH" || ! -f "$TRANSCRIPT_PATH" ]]; then
  exit 0  # fail-open: no transcript to measure
fi

# --- Model detection (first 20 lines only — O(1) regardless of transcript size) ---
MODEL_ID=""
if command -v jq &>/dev/null; then
  MODEL_ID=$(head -n 20 "$TRANSCRIPT_PATH" | jq -r 'select(.model != null) | .model' 2>/dev/null | head -1 || true)
fi
if [[ -z "$MODEL_ID" ]]; then
  # Fallback regex extraction
  MODEL_ID=$(head -n 20 "$TRANSCRIPT_PATH" | sed -n 's/.*"model"\s*:\s*"\([^"]*\)".*/\1/p' | head -1 || true)
fi

# --- Context window size by model (tokens) ---
# Proportional: thresholds scale with context window size.
# Add new models here as they become available.
case "$MODEL_ID" in
  *opus*4*6*|*opus-4-6*)   CONTEXT_WINDOW=1000000 ;;  # Opus 4.6: 1M tokens
  *sonnet*4*6*|*sonnet-4-6*) CONTEXT_WINDOW=200000 ;;  # Sonnet 4.6: 200K tokens
  *haiku*4*5*|*haiku-4-5*)   CONTEXT_WINDOW=200000 ;;  # Haiku 4.5: 200K tokens
  *)                         CONTEXT_WINDOW=200000 ;;  # Conservative default
esac

# --- Threshold percentages (of context window) ---
# Advisory: ~60% — "getting heavy, start thinking about handoff"
# Critical: ~78% — "compaction is close (~83.5%), handoff now or accept losses"
ADVISORY_PCT=60
CRITICAL_PCT=78

# --- Convert to file size thresholds (bytes) ---
# bytes = context_window × percentage × bytes_per_token_estimate
# Using 5 bytes/token (conservative — errs toward early warning)
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
  # Last resort: use session_id (less precise but functional)
  TRANSCRIPT_HASH="$SESSION_ID"
fi

# Review: Patrik — sentinel files were never cleaned up; delete ones older than 24h to prevent indefinite accumulation
find /tmp -maxdepth 1 \( -name "context-pressure-*" -o -name "autonomous-run-*" \) -mmin +1440 -delete 2>/dev/null || true

# --- Autonomous run detection ---
# When the PM has authorized autonomous execution (mise-en-place, /autonomous),
# a sentinel file suppresses /handoff nudges. The hook still fires (context pressure
# is real information) but the message is informational-only, no handoff recommendation.
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
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Compaction is close (~83.5%). Autonomous run active — continuing per PM instruction. Verify all progress is in TaskList and committed to disk. Compaction will compress context but tasks persist. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  else
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "CONTEXT PRESSURE — HIGH (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Compaction fires at ~83.5% of context window. You are close. RECOMMENDED: Run /handoff NOW to preserve session state. A fresh session will perform better. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
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
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Context usage is getting heavy. Autonomous run active — continuing per PM instruction. Ensure flight recorder (TaskList) is current so work survives compaction. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  else
    cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "CONTEXT PRESSURE — ADVISORY (${MODEL_ID:-unknown}, ~${EST_PCT}% est.): Context usage is getting heavy. Consider completing the current task unit, then running /handoff. This is informational — no action required yet. (Transcript: ${FILE_SIZE} bytes, model context: ${CONTEXT_WINDOW} tokens)"}}
JSONEOF
  fi
  exit 0
fi

exit 0
