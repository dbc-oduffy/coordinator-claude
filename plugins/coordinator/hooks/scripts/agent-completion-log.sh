#!/usr/bin/env bash
# Log agent (subagent) completions for observability.
# Fires on PostToolUse for Agent tool — provides audit trail of all dispatched agents.
# Input: PostToolUse JSON on stdin (tool_name, tool_input, tool_output).
set -uo pipefail

# Log under .git/coordinator-sessions/ (where all other audit logs live).
# Falls back to /tmp if no git root found, to avoid polluting the working tree.
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$GIT_ROOT" ]]; then
  LOG_DIR="${GIT_ROOT}/.git/coordinator-sessions/logs"
else
  LOG_DIR="${TMPDIR:-/tmp}/coordinator-agent-audit"
fi
LOG_FILE="${LOG_DIR}/agent-audit.jsonl"

mkdir -p "$LOG_DIR" 2>/dev/null || exit 0

INPUT=$(cat)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if command -v jq >/dev/null 2>&1; then
  echo "$INPUT" | jq -c --arg ts "$TIMESTAMP" '{
    logged_at: $ts,
    description: (.tool_input.description // "unknown"),
    subagent_type: (.tool_input.subagent_type // "general-purpose"),
    name: (.tool_input.name // null)
  }' >> "$LOG_FILE" 2>/dev/null || true
fi

exit 0
