#!/usr/bin/env bash
# PreToolUse hook (matchers: Agent, Workflow): nudges the EM toward the
# background Workflow vehicle when it is about to hand-dispatch a
# write-capable executor/worker without having launched a Workflow this
# session.
#
# Offer-shape (never blocks): this hook ALWAYS exits 0. On the nudge path it
# emits {"hookSpecificOutput":{"hookEventName":"PreToolUse",
# "additionalContext":"<message>"}} on stdout — an advisory suggestion
# surfaced to the EM, never a deny. It never sets "decision":"block" and
# never returns a non-zero exit code on the nudge path.
#
# Branches on tool_name:
#   - "Workflow" -> records a session sentinel (workflow-launched) and exits
#     0 silently. Once a Workflow has been launched this session, the nudge
#     never fires again (Agent branch condition 4 below).
#   - "Agent"    -> runs the nudge logic (conditions 1-6 below); fires at
#     most once per session (condition 5), and only for EM-originated
#     (non-subagent) dispatches of write-capable executors/workers.
#   - anything else -> exits 0 silently.
#
# Override: set COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW=1 to suppress the
# nudge entirely (condition 1).
#
# Spec backlink: coordinator/docs/wiki/coordinator-tripwires.md § NUDGE-MULTIWAVE-WORKFLOW

if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi
[[ -z "$INPUT" ]] && exit 0

# Extract tool_name (top-level field).
[[ "$INPUT" != *'"tool_name"'* ]] && exit 0
_tmp="${INPUT#*\"tool_name\":\"}"
TOOL_NAME="${_tmp%%\"*}"

# Extract session_id (top-level field). Required for both branches.
[[ "$INPUT" != *'"session_id"'* ]] && exit 0
_tmp="${INPUT#*\"session_id\":\"}"
SESSION_ID="${_tmp%%\"*}"
[[ -z "$SESSION_ID" ]] && exit 0
# Review: code-reviewer — mirrors AGENT_ID format guard in track-dispatched-agents.sh
# / SESSION_ID guard in nudge-foreground-agent-dispatch.sh:146; nulls garbage
# session_id so a malformed value can't produce a bogus SESSION_DIR path.
[[ "$SESSION_ID" =~ ^[a-zA-Z0-9_-]{4,}$ ]] || exit 0

if command -v timeout &>/dev/null; then
  GIT_ROOT=$(timeout 1 git rev-parse --show-toplevel 2>/dev/null) || exit 0
else
  GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
fi
[[ -z "$GIT_ROOT" ]] && exit 0

SESSIONS_BASE="${GIT_ROOT}/.git/coordinator-sessions"
SESSION_DIR="${SESSIONS_BASE}/${SESSION_ID}"

if [[ "$TOOL_NAME" == "Workflow" ]]; then
  mkdir -p "$SESSION_DIR" 2>/dev/null
  : > "${SESSION_DIR}/workflow-launched" 2>/dev/null
  exit 0
fi

[[ "$TOOL_NAME" != "Agent" ]] && exit 0

# Condition 1: explicit override.
[[ "${COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW:-}" == "1" ]] && exit 0

# Condition 2: subagent-originated dispatch (payload carries agent_id) ->
# this is an executor dispatching further, not the main EM. Never nudge.
[[ "$INPUT" == *'"agent_id"'* ]] && exit 0

# Condition 3: extract subagent_type from tool_input; only fire for
# write-capable executors/workers.
[[ "$INPUT" != *'"tool_input"'* ]] && exit 0
_ti="${INPUT#*\"tool_input\":}"
[[ "$_ti" != *'"subagent_type"'* ]] && exit 0
_tmp="${_ti#*\"subagent_type\":\"}"
SUBAGENT_TYPE="${_tmp%%\"*}"
[[ -z "$SUBAGENT_TYPE" ]] && exit 0

# Lowercase for case-insensitive comparisons (BSD/bash-3.2 portable; avoid
# ${v,,} which is bash-4-only).
SUBAGENT_TYPE_LC=$(printf '%s' "$SUBAGENT_TYPE" | tr '[:upper:]' '[:lower:]')

WRITE_CAPABLE=0
# Review: code-reviewer — this list enumerates the current write-capable
# non-persona worker roster (executor/review-integrator/enricher). Keep it in
# sync with any new write-capable worker type per CLAUDE.md § Roster Doctrine /
# § Adding a Convention — a future type that doesn't match *executor* and isn't
# named review-integrator/enricher will silently miss this nudge.
case "$SUBAGENT_TYPE_LC" in
  *executor*) WRITE_CAPABLE=1 ;;
  review-integrator|coordinator:review-integrator) WRITE_CAPABLE=1 ;;
  enricher|coordinator:enricher) WRITE_CAPABLE=1 ;;
esac
[[ "$WRITE_CAPABLE" -eq 0 ]] && exit 0

# Condition 4: no Workflow launched this session.
[[ -f "${SESSION_DIR}/workflow-launched" ]] && exit 0

# Condition 5: fire at most once per session.
NUDGED_SENTINEL="${SESSION_DIR}/multiwave-workflow-nudged"
[[ -f "$NUDGED_SENTINEL" ]] && exit 0
mkdir -p "$SESSION_DIR" 2>/dev/null
: > "$NUDGED_SENTINEL" 2>/dev/null

# Condition 6: fire. Message contains no double-quotes or backslashes, so a
# plain printf produces valid JSON without extra escaping.
MSG="[multiwave-workflow nudge] You're dispatching a write-capable executor by hand. Plan execution should run as a background Workflow by default — even a single wave / single agent (that's a one-agent() script). You do NOT lose what hand-dispatch feels like it gives you: the Workflow returns each phase's results to YOU, so your eyes stay on every wave; and executors return WITHOUT committing, so YOU commit each phase serially — full commit control stays with you. What a Workflow ADDS: it survives your compaction, encodes the gates deterministically, runs Sonnet executors, and keeps their tool-output out of your context window. Author a Workflow instead? (Legitimate carve-out: name a concrete reason a Workflow CANNOT express this shape - e.g. a mid-run pause for interactive PM input that gates the very next dispatch, or a tool only the main loop can call. NON-qualifying, does NOT license hand-dispatch: [a] a downstream step is EM-inline regardless (scope the Workflow to the dispatched chunks, run the inline step after it returns); [b] small or few dispatches or one uncompacted pass (the default holds for a single agent, a one-agent script); [c] wanting EM eyes between waves (the Workflow returns each phase to you); [d] wanting commit control (executors return uncommitted, you commit each phase). Suppress: COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW=1.) See coordinator/docs/wiki/workflow-orchestration.md"

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"%s"}}' "$MSG"
exit 0
