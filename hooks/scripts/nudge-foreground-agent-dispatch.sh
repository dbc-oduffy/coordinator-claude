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
#   - tool_input has NO run_in_background key AND this session has not yet proven
#     the harness exposes the param — UNCALIBRATED capability-probe pass.
#
#     The hard problem: from tool_input alone, an absent key is ambiguous. On a
#     param-LESS build (e.g. the Claude Code 2.1.176 fork/background-by-default
#     window, where the Agent param set was description/isolation/mode/model/name/
#     prompt/subagent_type/team_name and the harness dropped run_in_background as
#     unknown) absent means "can't honor it — background is automatic" and a deny is
#     unsatisfiable: no value flips it and the env-var escape lives in the harness
#     process env, unreachable from a tool-call shell → deny-ALL bricks the session
#     (project-rag-ue-addon-em memo, 2026-06-21). But on a param-FUL build (2.1.178+
#     re-exposed the param; the presence flip-flopped) absent means the EM simply
#     omitted it and the dispatch runs FOREGROUND — exactly what we must deny. Both
#     look identical in tool_input. Key-presence-of-this-one-call cannot tell them
#     apart, so the prior "absent → always pass" rule left a hole on 2.1.178: the
#     normal foreground dispatch (omit the param) sailed through.
#
#     Resolution — LEARN the capability per session. The harness leaks it for free:
#     if ANY Agent dispatch this session carries the key (either value), this build
#     exposes the param, so a later absent key is a deliberate foreground omission →
#     DENY. If the key has NEVER appeared this session, stay conservative → PASS.
#     The proof is a session-scoped sentinel at
#       <git_root>/.git/coordinator-sessions/<session_id>/.harness-bg-capable
#     Session-scoped ON PURPOSE: a fresh session starts uncalibrated (absent→pass,
#     brick-proof), and the sentinel never outlives the session that wrote it, so it
#     cannot go stale across a binary up/downgrade (the classic downgrade-brick).
#     Within a session it self-heals after the first param-bearing dispatch (usually
#     an early backgrounded one). Discrimination is still key-presence for the
#     present cases: present-and-false always denies (foreground deliberately chosen
#     on a build that supports the param); present-and-true always passes AND
#     calibrates. A deny only ever fires on a build we have PROVEN honors the param,
#     so retry-with-`run_in_background: true` is always satisfiable — no brick.
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

# --- Source C0 advisory-flatten-call helper (soft-degrade; absent → advisory calls no-op) ---
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""
_AFC="${_cc_root:+$_cc_root/hooks/scripts/lib/advisory-flatten-call.sh}"
[ -n "$_AFC" ] && [ -f "$_AFC" ] && . "$_AFC"

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

# --- Resolve session-scoped capability sentinel ---
# Proof that THIS build exposes run_in_background — learned at runtime, scoped to
# the firing session so it can never go stale across a binary up/downgrade.
# session_id is a top-level hook-payload field; floating match on first occurrence
# (it precedes tool_input in observed payloads). If session_id or git root is
# unavailable we cannot scope the sentinel → CAP_SENTINEL stays empty, which
# degrades the absent-key path to the conservative pass (never bricks).
CAP_DIR=""
CAP_SENTINEL=""
if [[ "$INPUT" == *'"session_id"'* ]]; then
  _session_id_tail="${INPUT#*\"session_id\":\"}"
  SESSION_ID="${_session_id_tail%%\"*}"
  # Review: code-reviewer — mirrors AGENT_ID format guard in track-dispatched-agents.sh;
  # nulls garbage session_id so a malformed value can't produce a bogus CAP_DIR path.
  [[ "$SESSION_ID" =~ ^[a-zA-Z0-9_-]{4,}$ ]] || SESSION_ID=""
  if [[ -n "$SESSION_ID" ]]; then
    if command -v timeout >/dev/null 2>&1; then
      GIT_ROOT=$(timeout 1 git rev-parse --show-toplevel 2>/dev/null || true)
    else
      GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
    fi
    if [[ -n "$GIT_ROOT" ]]; then
      CAP_DIR="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID}"
      CAP_SENTINEL="${CAP_DIR}/.harness-bg-capable"
    fi
  fi
fi

# --- Calibrate: key present (either value) proves the build honors the param ---
# Both present-and-true AND present-and-false calibrate: key presence alone proves
# the build exposes the param, regardless of value. present-and-true then passes
# (exit 0 below); present-and-false hits the deny block further down.
# Review: code-reviewer — prior comment implied only present-and-true calibrated, which
# was wrong; updated to match the actual "key presence = capability proof" semantics.
if [[ "$HAS_BG" == "true" && -n "$CAP_SENTINEL" ]]; then
  if mkdir -p "$CAP_DIR" 2>/dev/null; then
    # Review: code-reviewer — surface sentinel write failure to stderr (keep fail-open)
    : > "$CAP_SENTINEL" 2>/dev/null || echo "nudge-foreground-agent: could not write capability sentinel: $CAP_SENTINEL" >&2
  else
    echo "nudge-foreground-agent: could not create session dir for capability sentinel: $CAP_DIR" >&2
  fi
fi

# --- Backgrounded already → silent pass ---
[[ "$BG" == "true" ]] && exit 0

# --- Param absent → discriminate by LEARNED capability (not key-presence alone) ---
# Calibrated capable (sentinel exists) → omission is a deliberate foreground choice
# → fall through to DENY. Uncalibrated (no sentinel, or unresolvable scope) → we
# cannot prove the build honors the param → PASS (brick-proof, project-rag-ue-addon
# memo 2026-06-21). present-and-false skips this block entirely → always DENY.
if [[ "$HAS_BG" != "true" ]]; then
  [[ -n "$CAP_SENTINEL" && -f "$CAP_SENTINEL" ]] || exit 0
fi

# --- Emit hard block: permissionDecision:"deny" + permissionDecisionReason ---
# Lead with the retry shape; the EM under context pressure scans the first sentence.
MSG="FOREGROUND AGENT DISPATCH BLOCKED — retry with \`run_in_background: true\`. Coordinator default is backgrounded dispatch: foreground blocks the EM until the subagent returns, wasting cycles that could process other waves, reconcile plans, or handle PM messages in parallel. Escape hatch for rare legitimate foreground (inline result needed for the very next statement): set \`COORDINATOR_AGENT_FOREGROUND_OK=1\` in env. Doctrine: coordinator/CLAUDE.md § Subagent Dispatch."

# --- ExampleOrchestrationHub advisory fast-path (Class B deny-decision) ---
# Spec: hooks.nudge_foreground_agent_dispatch. Degrade-silent: empty/partial/parse-fail → fall through
# to local deny below. Consumed ONLY when COORDINATOR_EXAMPLE_ORCHESTRATION_HUB_DENY_AUTHORITATIVE=1 AND a valid
# permissionDecision ("allow"/"deny") parsed — partial/malformed JSON must never silently drop the deny.
# Review: code-reviewer F9 — added declare -f guard for consistency with nudge-improvement-queue-write.sh
# Review: code-reviewer F8 — jq required for advisory consume path; without jq _PD is empty and local deny always fires
if declare -f advisory_flatten_params >/dev/null 2>&1 && declare -f advisory_call >/dev/null 2>&1; then
  _PARAMS="$(printf '%s' "$INPUT" | advisory_flatten_params 2>/dev/null || echo '{}')"
  _EXAMPLE_ORCHESTRATION_HUB="$(advisory_call "hooks.nudge_foreground_agent_dispatch" "$_PARAMS" 2>/dev/null || true)"
  _PD="$(printf '%s' "$_EXAMPLE_ORCHESTRATION_HUB" | jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null)"
  if [ "${COORDINATOR_EXAMPLE_ORCHESTRATION_HUB_DENY_AUTHORITATIVE:-}" = "1" ] && { [ "$_PD" = "allow" ] || [ "$_PD" = "deny" ]; }; then
    if [ "$_PD" = "allow" ]; then
      exit 0
    else
      _EXAMPLE_ORCHESTRATION_HUB_REASON="$(printf '%s' "$_EXAMPLE_ORCHESTRATION_HUB" | jq -r '.hookSpecificOutput.permissionDecisionReason // empty' 2>/dev/null)"
      _DENY_MSG="${_EXAMPLE_ORCHESTRATION_HUB_REASON:-$MSG}"
      if command -v jq >/dev/null 2>&1; then
        jq -nc --arg m "$_DENY_MSG" \
          '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $m}}'
      else
        MSG_ESC=$(printf '%s' "$_DENY_MSG" | sed 's/"/\\"/g')
        cat <<JSONEOF
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "${MSG_ESC}"}}
JSONEOF
      fi
      exit 0
    fi
  fi
fi

# Degrade / partial / parse-fail / unrecognized decision / flag-unset → local deny, byte-for-byte unchanged.
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
