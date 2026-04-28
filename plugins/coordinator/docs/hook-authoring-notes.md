# Hook Authoring Notes

Reference notes for anyone writing Claude Code hooks (SubagentStop, PreToolUse, PostToolUse, etc.) in the coordinator plugin or any plugin that extends it.

These rules apply to every hook regardless of which event it handles. Both bit production hooks in this repo; treat them as load-bearing constraints, not style suggestions.

---

## SubagentStop fires for every subagent — gate on agent_type first

`SubagentStop` fires for ALL subagents in the session, not just the one you intended to monitor. Without an early `agent_type` (or `agent_id`) check, hook output — even a warning or status message — can replace the subagent's actual findings in the return channel. An untagged warning from your hook can silently overwrite the deliverable of an unrelated agent.

**Rule:** Always gate the hook body on the intended `agent_type` or `agent_id` at the very top of the script, before any transcript parsing or output emission. If the check fails, exit 0 silently.

```bash
# example gate at top of SubagentStop hook
AGENT_TYPE="${CLAUDE_AGENT_TYPE:-}"
if [ "$AGENT_TYPE" != "coordinator:executor" ]; then
  exit 0
fi
# ... rest of hook body
```

---

## Stderr is the error channel, not exit code

Claude Code flags a hook as failed if the script writes to stderr — even when it exits 0. This means a missing optional tool (`jq`, `python`, `awk`) that prints a "command not found" warning to stderr will mark the hook as errored even if the hook's logic completed correctly.

**Rule:** Wrap any external tool call so missing-tool messages or warnings go to `/dev/null` or are handled gracefully. A `2>/dev/null` on optional tools is usually enough. For required tools, fail explicitly with a clear message to stdout and a non-zero exit — don't let a noisy stderr trail mask the real error.

```bash
# optional tool — suppress stderr
result=$(jq '.field' "$file" 2>/dev/null) || result=""

# required tool — explicit failure
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required but not installed" >&1
  exit 1
fi
```

---

*Source: coordinator-claude triage 2026-04-27, T1.2 (SubagentStop agent_type gate) + T1.3 (stderr error channel). Both rules verified absent from coordinator docs prior to this landing.*
