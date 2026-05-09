#!/bin/bash
# PostToolUse hook (matcher: Agent): records agentIds dispatched by the EM,
# enabling later coordinator-safe-commit invocations to union the executors'
# touched-file lists into scope.
#
# Per archive/specs/2026-05-05-issue-a-agent-id-linkage.md (Issue A, the Staff Engineer
# APPROVED_WITH_NOTES v3 2026-05-06).
#
# Mechanism:
#   - Anchor extraction inside tool_response (Probe 0.3 confirmed EM-side
#     payload uses `tool_response.agentId` — camelCase — NOT top-level
#     `agent_id` (which is the subagent-side field per Probe 0.1).
#   - Write two files:
#       <git_root>/.git/coordinator-sessions/<em_sid>/dispatched-agents.txt
#       <git_root>/.git/coordinator-sessions/.agents/<agentId>/em-session-id.txt
#     The em-session-id.txt back-pointer is the durable linkage that makes
#     the read path sentinel-independent (helper enumerates .agents/* and
#     matches against the candidate em-sid set built from cs_live_session_ids).
#   - Atomic temp+rename for the back-pointer (the Staff Engineer v2 finding 3).
#   - Always exits 0 — advisory bookkeeping, never blocks tool calls.

if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi
[[ -z "$INPUT" ]] && exit 0

# Filter to Agent tool calls only.
[[ "$INPUT" != *'"tool_name":"Agent"'* ]] && exit 0

# Extract session_id (firing session — the EM). Top-level field; floating
# match on first occurrence is correct because session_id appears at top
# level before tool_response in observed payloads.
[[ "$INPUT" != *'"session_id"'* ]] && exit 0
_tmp="${INPUT#*\"session_id\":\"}"
SESSION_ID="${_tmp%%\"*}"
[[ -z "$SESSION_ID" ]] && exit 0

# Extract agentId (camelCase) ANCHORED to tool_response. Per Probe 0.3, the
# EM-side payload uses agentId in tool_response, NOT agent_id at top-level.
# Anchoring prevents grabbing the wrong field if a future schema adds an
# agentId elsewhere in the payload.
[[ "$INPUT" != *'"tool_response"'* ]] && exit 0
_tail="${INPUT#*\"tool_response\":}"
[[ "$_tail" != *'"agentId"'* ]] && exit 0
_tmp="${_tail#*\"agentId\":\"}"
AGENT_ID="${_tmp%%\"*}"

# Format guard: lowercase hex, 12+ chars. Probe 0.3 captured 17-char hex
# (e.g. a47b7551f951cb0cf). Forward-compat caveat: if Claude Code adopts
# UUIDs in a future version, relax this regex.
[[ -z "$AGENT_ID" ]] && exit 0
if [[ ! "$AGENT_ID" =~ ^[a-f0-9]{12,}$ ]]; then
  exit 0
fi

GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

SESSIONS_BASE="${GIT_ROOT}/.git/coordinator-sessions"
SESSION_DIR="${SESSIONS_BASE}/${SESSION_ID}"
AGENT_DIR="${SESSIONS_BASE}/.agents/${AGENT_ID}"
DISPATCHED="${SESSION_DIR}/dispatched-agents.txt"
EM_BACKPOINTER="${AGENT_DIR}/em-session-id.txt"

# Init session-dir if missing (slow path mirrors track-touched-files.sh).
if [[ ! -d "$SESSION_DIR" ]]; then
  LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
  [[ ! -f "$LIB_PATH" ]] && LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh"
  if [[ -f "$LIB_PATH" ]]; then
    # shellcheck source=/dev/null
    source "$LIB_PATH"
    cs_init "$SESSION_ID" 2>/dev/null || true
  else
    mkdir -p "$SESSION_DIR" 2>/dev/null
  fi
fi

# Init agent-dir + write back-pointer atomically (the Staff Engineer v2 finding 3).
# `-s` test: file exists AND is non-empty. Empty back-pointers (partial-write
# survivors) trigger re-write. The temp+rename pattern means a concurrent
# fire either succeeds-second-or-cleans-up — no orphan temp files.
mkdir -p "$AGENT_DIR" 2>/dev/null
if [[ ! -s "$EM_BACKPOINTER" ]]; then
  TMP_BP="${EM_BACKPOINTER}.tmp.$$"
  if echo "$SESSION_ID" > "$TMP_BP" 2>/dev/null; then
    mv "$TMP_BP" "$EM_BACKPOINTER" 2>/dev/null || rm -f "$TMP_BP" 2>/dev/null
  else
    rm -f "$TMP_BP" 2>/dev/null
  fi
fi

# Dedup append to dispatched-agents.txt.
[[ -f "$DISPATCHED" ]] || touch "$DISPATCHED" 2>/dev/null
if grep -qxF "$AGENT_ID" "$DISPATCHED" 2>/dev/null; then
  exit 0
fi
echo "$AGENT_ID" >> "$DISPATCHED"
exit 0
