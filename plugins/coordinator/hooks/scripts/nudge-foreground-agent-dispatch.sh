#!/bin/bash
# Nudge: Agent dispatch without run_in_background — suggest backgrounding.
#
# Per 2026-06-08 lesson (and the runtime-tripwire workstream that surfaced it):
# foreground Agent dispatch blocks the EM until the subagent returns. The
# coordinator runtime tripwire (docs/wiki/runtime-tripwire.md) only meaningfully
# fires on BACKGROUNDED dispatches — `track-dispatched-agents.sh` records
# dispatch time correctly only when the Agent tool returns immediately at
# dispatch (background case). For foreground dispatches, the EM is blocked
# anyway and can't act on a runtime nudge, so the tripwire is structurally
# irrelevant.
#
# Doctrine alone has been leaky: the runtime-tripwire workstream itself was
# completed with multiple foreground Agent dispatches that should have been
# backgrounded — proving the doctrine-only approach insufficient. This hook
# is the actuator side of the belt-and-suspenders fix.
#
# Fires on: PreToolUse for Agent tool.
#
# Mechanism: emits `permissionDecision: "deny"` + `permissionDecisionReason` —
# HARD BLOCK. Soft `allow + additionalContext` nudges (the prior shape) lost
# to habit: the dispatch went through, the EM read the warning after
# committing, didn't interrupt itself, and the strike counter ticked without
# behavior change. Deny forces the EM to either retry with
# `run_in_background: true` or set the escape-hatch env var. Strike counter
# removed — there is no point throttling a block; either the EM retries or
# they set the env var.
#
# Silent pass when:
#   - tool_input.run_in_background = true (already backgrounded; correct shape)
#   - COORDINATOR_AGENT_FOREGROUND_OK is set in env (intentional foreground —
#     escape hatch for the rare legitimate case: inline result needed for the
#     very next statement, no other work can proceed in parallel)

set -uo pipefail
# -e intentionally absent: every extraction has an explicit || fallback so the
# fast path is fail-open. Blanket -e would abort on any non-zero subcommand
# (stat/jq/python), defeating that.

# --- Safe stdin read (Windows Git-Bash hang guard) ---
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# --- Escape hatch: explicit opt-out for intentional foreground dispatch ---
[[ -n "${COORDINATOR_AGENT_FOREGROUND_OK:-}" ]] && exit 0

# --- Extract tool_input.run_in_background (jq preferred, Python fallback, sed last) ---
BG="false"
if command -v jq >/dev/null 2>&1; then
  BG=$(echo "$INPUT" | jq -r '.tool_input.run_in_background // false' 2>/dev/null || echo "false")
elif command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  PY=$(command -v python3 2>/dev/null || command -v python)
  BG=$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print("true" if d.get("tool_input", {}).get("run_in_background") else "false")
except Exception:
    print("false")
' 2>/dev/null || echo "false")
else
  # Last-resort: substring match on the literal. Compact and spaced forms.
  if [[ "$INPUT" == *'"run_in_background":true'* ]] || [[ "$INPUT" == *'"run_in_background": true'* ]]; then
    BG="true"
  fi
fi

# --- Backgrounded already → silent pass ---
[[ "$BG" == "true" ]] && exit 0

# --- Emit hard block: permissionDecision:"deny" + permissionDecisionReason ---
# Lead with the retry shape; the EM under context pressure scans the first sentence.
MSG="FOREGROUND AGENT DISPATCH BLOCKED — retry with \`run_in_background: true\`. Coordinator default is backgrounded dispatch: foreground blocks the EM until the subagent returns, wasting cycles that could process other waves, reconcile plans, or handle PM messages in parallel. Escape hatch for rare legitimate foreground (inline result needed for the very next statement): set \`COORDINATOR_AGENT_FOREGROUND_OK=1\` in env. Doctrine: coordinator/CLAUDE.md § Subagent Dispatch."

if command -v jq >/dev/null 2>&1; then
  jq -nc --arg m "$MSG" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $m}}'
else
  # Heredoc fallback — escape interior double quotes to keep JSON valid.
  MSG_ESC=$(printf '%s' "$MSG" | sed 's/"/\\"/g')
  cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "${MSG_ESC}"}}
JSONEOF
fi
exit 0
