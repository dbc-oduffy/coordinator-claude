#!/usr/bin/env bash
# Log agent (subagent) completions for observability.
# Fires on PostToolUse for Agent tool — provides audit trail of all dispatched agents.
# Input: PostToolUse JSON on stdin (tool_name, tool_input, tool_output).
set -euo pipefail

LOG_DIR="${CLAUDE_PROJECT_DIR:-.}/logs"
LOG_FILE="${LOG_DIR}/agent-audit.jsonl"

mkdir -p "$LOG_DIR"

INPUT=$(cat)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Extract agent description and type from tool input, append to audit log
echo "$INPUT" | jq -c --arg ts "$TIMESTAMP" '{
  logged_at: $ts,
  description: (.tool_input.description // "unknown"),
  subagent_type: (.tool_input.subagent_type // "general-purpose"),
  name: (.tool_input.name // null)
}' >> "$LOG_FILE" 2>/dev/null || true
