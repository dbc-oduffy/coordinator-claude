#!/usr/bin/env bash
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
#   - tool_input has NO run_in_background key at all — capability-probe pass.
#     On harness builds where the Agent tool does not expose a run_in_background
#     parameter (e.g. Claude Code 2.1.176+ fork/background-by-default model, where
#     Agent's param set is description/isolation/mode/model/name/prompt/subagent_type/
#     team_name and backgrounding is not param-controllable), the harness drops the
#     field as unknown, so `tool_input.run_in_background` is ABSENT. A deny on that
#     build is unsatisfiable — there is no value the EM can pass to flip it, and the
#     env-var escape lives in the harness process env, unreachable from a tool-call
#     shell. That degrades the hook to deny-ALL-Agent-dispatches and bricks the
#     session (project-rag-ue-addon-em memo, 2026-06-21). The invariant we restore:
#     a session must always have SOME in-session way to dispatch a subagent.
#     Discrimination is key-presence, not value: present-and-false still denies
#     (the EM affirmatively chose foreground on a build that supports the param);
#     absent-entirely passes (the build can't honor the param).
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

# --- Extract run_in_background key-PRESENCE and value (jq preferred, Python fallback, sed last) ---
# HAS_BG distinguishes "key absent" (harness can't honor the param → pass) from
# "key present-and-false" (foreground deliberately chosen → deny). The old `// false`
# default collapsed both into false and bricked param-less harness builds.
# These initializers ARE the fail-open default: the sed last-resort branch below
# only ever SETS HAS_BG/BG to "true", never back to "false", so any parser that
# can't find the key (or any future branch that falls through) lands on absent→pass.
# A fourth extraction path must preserve this — never assume HAS_BG is reset for you.
HAS_BG="false"
BG="false"
if command -v jq >/dev/null 2>&1; then
  HAS_BG=$(echo "$INPUT" | jq -r '(.tool_input // {}) | has("run_in_background")' 2>/dev/null || echo "false")
  BG=$(echo "$INPUT" | jq -r '.tool_input.run_in_background // false' 2>/dev/null || echo "false")
elif command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  PY=$(command -v python3 2>/dev/null || command -v python)
  read -r HAS_BG BG <<<"$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
    ti = json.loads(sys.stdin.read()).get("tool_input", {})
    print(("true" if "run_in_background" in ti else "false"),
          ("true" if ti.get("run_in_background") else "false"))
except Exception:
    print("false false")
' 2>/dev/null || echo "false false")"
else
  # Last-resort: substring match on the literal key, then on the true forms.
  if [[ "$INPUT" == *'"run_in_background"'* ]]; then
    HAS_BG="true"
  fi
  if [[ "$INPUT" == *'"run_in_background":true'* ]] || [[ "$INPUT" == *'"run_in_background": true'* ]]; then
    BG="true"
  fi
fi

# --- Capability-probe pass: param absent → this harness can't honor it → never deny ---
[[ "$HAS_BG" != "true" ]] && exit 0

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
