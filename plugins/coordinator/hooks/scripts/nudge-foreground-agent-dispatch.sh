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
# Mechanism: emits `permissionDecision: "allow"` + `additionalContext` — the
# canonical PreToolUse offer-shape per nudge-probe-spray.sh:39 ("the only
# warn-reaches-the-model-without-blocking channel for PreToolUse"). The
# permissionDecision field is LOAD-BEARING — without it, the platform parses
# the JSON but silently discards additionalContext.
#
# Throttle: per-session strike count (max 3 fires per session), mirroring
# nudge-probe-spray.sh. After 3 fires the EM either internalized the doctrine
# or set COORDINATOR_AGENT_FOREGROUND_OK; further nudges are noise.
#
# Silent pass when:
#   - tool_input.run_in_background = true (already backgrounded; correct shape)
#   - COORDINATOR_AGENT_FOREGROUND_OK is set in env (intentional foreground —
#     no reason required: foreground dispatch is a routine tool with a clear
#     legitimate use, unlike queue-writing where the reason-bar exists to make
#     reflexive deferral expensive)
#   - This session has already fired the nudge 3+ times (strike limit reached)

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

# --- Per-session strike counter (mirrors nudge-probe-spray.sh pattern) ---
# After 3 nudges in a session, suppress further fires. Sentinel keyed on
# CLAUDE_CODE_SESSION_ID per claude-code-platform-gotchas.md:33-50.
SID="${CLAUDE_CODE_SESSION_ID:-unknown}"
STRIKE_SENTINEL="/tmp/coordinator-nudge-foreground-${SID}.strikes"
STRIKE_LIMIT=3

STRIKES=0
if [[ -f "$STRIKE_SENTINEL" ]]; then
  STRIKES=$(cat "$STRIKE_SENTINEL" 2>/dev/null || echo 0)
  [[ ! "$STRIKES" =~ ^[0-9]+$ ]] && STRIKES=0
fi
[[ "$STRIKES" -ge "$STRIKE_LIMIT" ]] && exit 0
echo "$((STRIKES + 1))" > "$STRIKE_SENTINEL" 2>/dev/null || true

# --- Emit nudge: permissionDecision:"allow" + additionalContext ---
# Structured for actionability — lead with the fix, then brief diagnosis,
# then escape hatch. The EM under context pressure scans the first sentence.
MSG="FOREGROUND AGENT DISPATCH — add \`run_in_background: true\` to background this. Coordinator default is backgrounded dispatch: foreground blocks the EM until the subagent returns, wasting cycles that could process other waves, reconcile plans, or handle PM messages in parallel — and the runtime tripwire (docs/wiki/runtime-tripwire.md) only meaningfully fires on backgrounded agents. To suppress this nudge for an intentional foreground dispatch (rare — e.g. inline result needed for the very next statement), set \`COORDINATOR_AGENT_FOREGROUND_OK=1\` in env. Doctrine: coordinator/CLAUDE.md § Subagent Dispatch. (Strike ${STRIKES}/${STRIKE_LIMIT} this session.)"

if command -v jq >/dev/null 2>&1; then
  jq -nc --arg m "$MSG" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow", additionalContext: $m}}'
else
  # Heredoc fallback — MSG has no backslashes or quotes that would break it.
  # Escape interior double quotes to keep JSON valid.
  MSG_ESC=$(printf '%s' "$MSG" | sed 's/"/\\"/g')
  cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "additionalContext": "${MSG_ESC}"}}
JSONEOF
fi
exit 0
