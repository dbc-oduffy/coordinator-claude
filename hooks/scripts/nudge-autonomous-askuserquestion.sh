#!/usr/bin/env bash
# PreToolUse hook: nudge the EM away from AskUserQuestion for break-class /
# engineering-approach decisions while an autonomous run is active.
# Advisory only — "allow" always; never blocks. The nudge redirects, it does
# not gate, matching the design-as-offers doctrine (a hard deny would wedge
# a legitimate irreversible-external ask).
#
# Fires ONLY when the autonomous sentinel /tmp/autonomous-run-<SESSION_ID> is
# present — inert in every non-autonomous session. See commands/autonomous.md
# § Behavior While Active for the doctrine this hook echoes back to the EM.
#
# Spec backlink: fix4-report.md §3-4 (ceremony-bugfix-substrate scout sketch).
#
# Suppression: subagent fires (agent_id present) are a different case — a
# delegated worker's AskUserQuestion is not the EM's own halting decision.
# Pattern copied verbatim from suggest-sonnet-research.sh:32-34.
#
# Escape hatch: COORDINATOR_AUTONOMOUS_ASK_OK=1 — the EM sets this
# deliberately before the one legitimate autonomous-mode ask (a genuinely
# irreversible external action with no pre-authorization, or a true
# no-correct-answer product fork). Mirrors the established override
# convention (COORDINATOR_AGENT_FOREGROUND_OK=1, COORDINATOR_OVERRIDE_*).

INPUT=$(cat 2>/dev/null || true)

# Subagent fire → not the EM's own AskUserQuestion → suppress the nudge.
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  exit 0
fi

# Irreversible-external override — EM has deliberately authorized this ask.
if [[ "${COORDINATOR_AUTONOMOUS_ASK_OK:-}" == "1" ]]; then
  exit 0
fi

# Extract session_id — jq primary, sed fallback (same idiom as
# suggest-sonnet-research.sh / block-blanket-git-add.sh / block-no-verify.sh).
SESSION_ID=""
if command -v jq >/dev/null 2>&1; then
  SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  SESSION_ID=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Fail-open: no session_id extracted → cannot resolve the sentinel path → inert.
if [[ -z "$SESSION_ID" ]]; then
  exit 0
fi

# Sentinel gate: only fire inside an active autonomous run.
if [[ ! -f "/tmp/autonomous-run-${SESSION_ID}" ]]; then
  exit 0
fi

cat << HOOK_OUTPUT
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "additionalContext": "You are in autonomous mode. AskUserQuestion halts the run until the (away) PM returns — the most expensive action. Break-class findings are fix-by-default; the fix approach is yours to decide. Decide + dispatch + log the alternatives to the flight recorder + inform in a status line. The only legitimate autonomous ask is a genuinely-irreversible external action (push/PR/external-message/data-deletion) with no pre-authorization, or a true no-correct-answer product fork — for those, set COORDINATOR_AUTONOMOUS_ASK_OK=1 first. Watch for the tell: an excellent diagnosis ending in a blocking ask feels like diligence but is the exact anti-pattern autonomous mode prevents."
  }
}
HOOK_OUTPUT
