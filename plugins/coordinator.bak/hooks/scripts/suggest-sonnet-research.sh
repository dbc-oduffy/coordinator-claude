#!/bin/bash
# PreToolUse hook: nudge the EM to delegate web research to dedicated skills/agents.
# Uses "allow" — never blocks, just injects a nudge into Claude's context.
# Single URL from the user = proceed directly. Everything else = delegate.

# Build the research pipeline suggestions conditionally
RESEARCH_SUGGESTIONS="- Multi-query internet research → /deep-research (Pipeline A) — dispatches deep-research-orchestrator\n- Structured batch research (N subjects, same topics) → /structured-research — dispatches Agent Teams via deep-research plugin\n- Quick codebase exploration → Agent with subagent_type='Explore'\n- Enriching specs with codebase facts → Agent with subagent_type='coordinator:enricher'\n- YouTube / podcast / audio research → /notebooklm-research"

if [[ ! -d "$HOME/.claude/plugins/coordinator-claude/deep-research" ]]; then
  RESEARCH_SUGGESTIONS="- Multi-query internet research → install the deep-research plugin for Pipeline A\n- Structured batch research (N subjects, same topics) → install the deep-research plugin for Pipeline C\n- Quick codebase exploration → Agent with subagent_type='Explore'\n- Enriching specs with codebase facts → Agent with subagent_type='coordinator:enricher'"
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
