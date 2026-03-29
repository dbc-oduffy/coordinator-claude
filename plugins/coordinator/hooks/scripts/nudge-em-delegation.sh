#!/bin/bash
# PostToolUse hook: nudge the EM to delegate implementation work to executor agents.
# Counts direct Edit/Write calls to implementation files (not plans/tasks/docs).
# After 5 implementation-file edits, fires a one-time advisory nudge.
# Never blocks — advisory only.

set -euo pipefail

# Read hook input from stdin
if command -v timeout &>/dev/null; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat)
fi

# Only process Edit and Write tool results
TOOL_NAME=$(echo "$HOOK_INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
if [[ "$TOOL_NAME" != "Edit" && "$TOOL_NAME" != "Write" ]]; then
  exit 0
fi

# Extract the file path from the tool input
FILE_PATH=$(echo "$HOOK_INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# --- Classify file as EM-appropriate vs implementation ---
# EM-appropriate files: plans, tasks, docs, handoffs, lessons, CLAUDE.md, memory, config
# These are orchestration artifacts the EM legitimately edits directly.
EM_APPROPRIATE=false
case "$FILE_PATH" in
  */plans/*|*/tasks/*|*/handoffs/*|*/lessons*|*CLAUDE.md|*CLAUDE.local.md|*/memory/*|*/.claude/*|*/archive/*|*orientation_cache*|*.workday-start-marker)
    EM_APPROPRIATE=true
    ;;
  */docs/plans/*|*/docs/research/*|*/docs/decisions/*)
    EM_APPROPRIATE=true
    ;;
esac

if [[ "$EM_APPROPRIATE" == "true" ]]; then
  exit 0
fi

# --- EM-only guard ---
# This hook should only nudge the top-level EM session, not dispatched subagents.
# Subagents (executors, enrichers, reviewers) ARE supposed to edit implementation files.
# Detection: agent_id is present in hook input only for subagent contexts.
AGENT_ID=$(echo "$HOOK_INPUT" | jq -r '.agent_id // empty' 2>/dev/null || true)
if [[ -n "$AGENT_ID" ]]; then
  # Subagent session — skip
  exit 0
fi

# --- Session-scoped counter ---
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"' 2>/dev/null || true)
COUNTER_FILE="/tmp/em-edit-count-${SESSION_ID}"
SENTINEL_FILE="/tmp/em-delegation-nudged-${SESSION_ID}"

# Already nudged this session — don't nag again
if [[ -f "$SENTINEL_FILE" ]]; then
  exit 0
fi

# Increment counter
if [[ -f "$COUNTER_FILE" ]]; then
  COUNT=$(cat "$COUNTER_FILE")
  COUNT=$((COUNT + 1))
else
  COUNT=1
fi
echo "$COUNT" > "$COUNTER_FILE"

# Threshold: 5 implementation-file edits
THRESHOLD=5
if [[ "$COUNT" -lt "$THRESHOLD" ]]; then
  exit 0
fi

# Fire the nudge — bark once
touch "$SENTINEL_FILE"

cat << 'HOOK_OUTPUT'
{
  "decision": "approve",
  "systemMessage": "Delegation check: You've made 5+ direct edits to implementation files this session. The EM orchestrates — executors implement. Consider dispatching the remaining work:\n\n- Single-stub execution → /delegate-execution\n- Plan-based batch execution → /execute-plan\n- Ad-hoc multi-file refactor → Agent with subagent_type='coordinator:executor'\n\nLegitimate exceptions: quick one-off fix the PM asked for, mid-review touch-up, or a change so small that dispatching is pure overhead. If this is one of those, carry on."
}
HOOK_OUTPUT
