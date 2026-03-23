#!/bin/bash
# PreToolUse hook: nudge the EM to delegate holodeck MCP tool calls to domain agents.
# Uses "allow" — doesn't block, but injects a strong reminder that the EM should
# be orchestrating, not typing Python or calling MCP tools directly.

cat << 'HOOK_OUTPUT'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "additionalContext": "DELEGATION PREFERRED: You are about to call a holodeck MCP tool directly. Domain agents have capabilities you lack in this context:\n\n- 40+ hidden tools (via execute_domain_tool proxy) with full schemas loaded in fresh context\n- Pre-loaded verification protocols (inspect → screenshot → compile check) built into their system prompts\n- Domain-specific knowledge and operational patterns you'd need to ToolSearch and read to match\n\nYour 8 visible tools are for verification, quick fact-finding, and simple one-off mutations — not multi-step work. You could ToolSearch for hidden schemas, but that spends Opus context on what a Sonnet agent gets for free.\n\nUse the dedicated holodeck infrastructure:\n\n- Underspecified / cross-domain / large-scope → Agent(subagent_type='holodeck-control:ue-project-orchestrator') for a plan, then dispatch domain agents per the plan\n- World building / level design / actor placement → Agent(subagent_type='holodeck-control:ue-world-builder')\n- Asset creation / Blueprint editing / materials → Agent(subagent_type='holodeck-control:ue-asset-author')\n- Gameplay systems / abilities / AI / game mode → Agent(subagent_type='holodeck-control:ue-gameplay-engineer')\n- Project config / plugins / build / packaging → Agent(subagent_type='holodeck-control:ue-infra-engineer')\n- UE documentation lookup → Agent(subagent_type='game-dev:staff-game-dev') or /ue-lookup command\n- Python script execution in editor → Agent(subagent_type='holodeck-docs:ue-python-executor') or /run-python command\n- Blueprint inspection → Agent(subagent_type='game-dev:ue-blueprint-inspector')\n\nFor multi-domain tasks: dispatch the orchestrator first for decomposition, then dispatch domain agents sequentially per its plan with verification between steps.\n\nDo NOT call MCP tools directly or spin up a generic Agent — use the typed subagent_type to get the right agent with the right tools and system prompt.\n\nOnly proceed with direct MCP calls if: (1) you are verifying an agent's output with a single quick inspection, or (2) the operation is trivially simple (one-liner) and dispatching an agent would be pure overhead."
  }
}
HOOK_OUTPUT
