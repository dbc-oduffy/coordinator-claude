#!/bin/bash
# PreToolUse hook: nudge the EM to delegate web research to dedicated skills/agents.
# Uses "allow" — never blocks, just injects a nudge into Claude's context.
# Single URL from the user = proceed directly. Everything else = delegate.
#
# Suppression: when this hook fires from inside a subagent (scout, executor, researcher),
# the EM has ALREADY authorized that dispatch — re-emitting the "delegate to a scout"
# advisory at scout-altitude is doctrine-incorrect and noisy (empirical: 6× misfires
# in a single sanctioned solo-scout dispatch, 2026-06-09). Detect via the top-level
# `agent_id` field, which Claude Code emits on subagent fires only (same convention
# documented in block-subagent-archive-write.sh:76-90 and track-touched-files.sh:72-85).
# Format-guard fails → AGENT_ID empty → nudge fires (safe direction for an advisory).

INPUT=$(cat 2>/dev/null || true)

AGENT_ID=""
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  _tmp_agent="${INPUT#*\"agent_id\":\"}"
  AGENT_ID="${_tmp_agent%%\"*}"
  if [[ ! "$AGENT_ID" =~ ^[a-f0-9]{12,}$ ]]; then
    AGENT_ID=""
  fi
fi

# Subagent fire → caller is already a delegated researcher → suppress the nudge.
if [[ -n "$AGENT_ID" ]]; then
  exit 0
fi

# Build the research pipeline suggestions conditionally
RESEARCH_SUGGESTIONS="- Internet research (web sources) → /research --mode=web <topic>\n- Codebase / repo research → /research --mode=repo <path> [--deepest]\n- Structured batch research (N subjects, schema output) → /research --mode=structured <spec-path>\n- Quick codebase exploration → Agent with subagent_type='Explore'\n- Enriching specs with codebase facts → Agent with subagent_type='coordinator:enricher'\n- YouTube / podcast / audio research → /notebooklm-research"

if [[ ! -d "$HOME/.claude/plugins/coordinator-claude/deep-research" ]]; then
  RESEARCH_SUGGESTIONS="- Any research (web/repo/structured) → install the deep-research plugin, then /research --mode={web,repo,structured}\n- Quick codebase exploration → Agent with subagent_type='Explore'\n- Enriching specs with codebase facts → Agent with subagent_type='coordinator:enricher'"
fi

cat << HOOK_OUTPUT
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "additionalContext": "DELEGATION REQUIRED: You are about to do web research as Opus. The EM orchestrates — researchers execute. Use the dedicated research infrastructure, not ad-hoc agent dispatch:\n\n${RESEARCH_SUGGESTIONS}\n\nOnly proceed with direct web calls if: (1) the user pasted you a specific URL and asked you to read it — one fetch, no research, or (2) you are verifying a single fact mid-conversation where dispatching an agent is pure overhead.\n\nDo NOT spin up a generic Agent(prompt='go search for...') — that discards tested guardrails (phase separation, quality gates, Haiku grounding). Opus tokens are for judgment, not for reading web pages."
  }
}
HOOK_OUTPUT
