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

if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat 2>/dev/null || true)
fi
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# --- ExampleOrchestrationHub advisory helper (degrade-silent; fail-open if unavailable) ---
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""
_AFC="${_cc_root:+$_cc_root/hooks/scripts/lib/advisory-flatten-call.sh}"
[ -n "$_AFC" ] && [ -f "$_AFC" ] && . "$_AFC"

if command -v jq >/dev/null 2>&1; then
  # -c (compact, one-line JSON) is REQUIRED: the skip-if-completed grep in
  # runtime-tripwire-em-check.sh greps for `"agentId":"<id>"` on a single line.
  # Switching to pretty-printed output would break that consumer.
  # Review: code-reviewer F7 — printf '%s\n' instead of echo for INPUT piping (consistent with every other script in this set)
  printf '%s\n' "$INPUT" | jq -c --arg ts "$TIMESTAMP" '{
    logged_at: $ts,
    description: (.tool_input.description // "unknown"),
    subagent_type: (.tool_input.subagent_type // "general-purpose"),
    name: (.tool_input.name // null),
    agentId: (.tool_response.agentId // .tool_response.agent_id // null)
  }' >> "$LOG_FILE" 2>/dev/null || true
fi

# --- ExampleOrchestrationHub advisory call: hooks.agent_completion_log (Class A — op-specific builder) ---
# Reuses $INPUT (already captured above); extracts the same agentId cascade the jq block uses.
# Local logic above runs unconditionally; this advisory call is additive and fire-and-forget.
# async-detached fire-and-forget: off the hook's critical path; local completion-log write above is authoritative.
if declare -f advisory_call >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
  (
    _AID="$(printf '%s' "$INPUT" | jq -r '(.tool_response.agentId // .tool_response.agent_id // "")' 2>/dev/null || true)"
    _AIDS="${_AID//-/_}"
    # Review: code-reviewer F5 — three-source cascade (resolvedModel is the authoritative harness field for background dispatches)
    _MODEL="$(printf '%s' "$INPUT" | jq -r '(.tool_response.resolvedModel // .tool_response.model // .tool_input.model // "unknown")' 2>/dev/null || true)"
    _SID="$(printf '%s' "$INPUT" | jq -r '(.session_id // "")' 2>/dev/null || true)"
    # Review: code-reviewer F4 — add subagent_type (matches local log schema; handler can index/route on agent type)
    _ST="$(printf '%s' "$INPUT" | jq -r '(.tool_input.subagent_type // "general-purpose")' 2>/dev/null || true)"
    _PARAMS="$(jq -nc --arg aid "$_AID" --arg aids "$_AIDS" --arg m "$_MODEL" --arg sid "$_SID" --arg st "$_ST" \
      '{session_id:$sid,dispatched_agent_id:$aid,dispatched_agent_id_snake:$aids,dispatched_model:$m,subagent_type:$st}' 2>/dev/null || echo '{}')"
    advisory_call "hooks.agent_completion_log" "$_PARAMS" >/dev/null 2>&1 || true
  ) &
  disown 2>/dev/null || true
fi

exit 0
