#!/usr/bin/env bash
# enforce-agent-dispatch-mode.sh — PreToolUse hook, matcher: Agent
#
# Purpose: raises dispatched-agent permission mode up to the parent session posture.
# When the parent is running in an autonomous mode (auto, dontAsk, bypassPermissions),
# child agents inherit that posture so they don't hang on interactive permission prompts
# during test/validation steps (e.g. pytest, pnpm typecheck, shell commands).
#
# Spec backlink: docs/plans/2026-07-06-agent-dispatch-mode-mirror.md § "Layer 1 — Hook"
#
# Autonomy order (least → most):
#   plan(0) < default/manual(1) < acceptEdits(2) < auto(3) < dontAsk(4) < bypassPermissions(5)
#
# Behavior:
#   PARENT ∈ {auto, dontAsk, bypassPermissions} AND CHILD effective mode below parent
#   → emit permissionDecision:"allow" + updatedInput (full tool_input merge, mode overwritten)
#   Otherwise → silent pass (exit 0, no output). Never lower autonomy.
#
# Absent child mode → treated as acceptEdits (rank 2; below every autonomous parent).
# Escape hatch: COORDINATOR_AGENT_MODE_OK set in env → silent pass (deliberate down-scope).
# Fail-open on: missing jq/python, malformed JSON, absent fields, stdin timeout.
#
# CRITICAL: updatedInput carries the FULL original tool_input with mode overwritten —
# a partial object would drop prompt/subagent_type/run_in_background/etc.
#
# SEQUENCING ASSUMPTION (load-bearing — do not remove):
# (1) This hook co-registers on the Agent PreToolUse matcher alongside
#     nudge-foreground-agent-dispatch.sh. Claude Code hook conflict resolution uses
#     documented deny-precedence: "the most restrictive answer applies, in order
#     deny, defer, ask, allow." A `deny` from nudge-foreground therefore always
#     beats this hook's `allow` — the foreground guard cannot be defeated by this
#     hook no matter which runs first.
# (2) This hook MUST remain the ONLY updatedInput-emitting hook on the Agent
#     PreToolUse matcher. Adding a second input-modifier would make the rewrite
#     non-deterministic: the Claude Code docs state "last-to-finish wins" for
#     parallel hooks and parallel order is undefined. One updatedInput emitter is
#     required for deterministic behaviour.
# Review: code-reviewer — F2: documents deny-precedence and single-emitter contract
#   so future maintainers do not accidentally register a competing updatedInput hook.

set -uo pipefail
# -e intentionally absent: every extraction has an explicit || fallback so the
# fast path is fail-open. Blanket -e would abort on any non-zero subcommand
# (jq/python), defeating that.

# --- Safe stdin read (Windows Git-Bash hang guard) ---
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# --- Escape hatch: deliberate down-scope dispatch (e.g. read-only scout from YOLO session) ---
[[ -n "${COORDINATOR_AGENT_MODE_OK:-}" ]] && exit 0

# --- Autonomy rank table ---
# Returns numeric rank for a known permission_mode; -1 for unknown.
# plan=0 < default=manual=1 < acceptEdits=2 < auto=3 < dontAsk=4 < bypassPermissions=5
mode_rank() {
  case "$1" in
    plan)               echo 0 ;;
    default|manual)     echo 1 ;;
    acceptEdits)        echo 2 ;;
    auto)               echo 3 ;;
    dontAsk)            echo 4 ;;
    bypassPermissions)  echo 5 ;;
    *)                  echo -1 ;;
  esac
}

# --- Extract parent permission_mode and child tool_input.mode ---
# jq preferred, Python fallback, substring last-resort (extraction only — emission always needs jq/python).
# Fail-open defaults: empty strings → exit 0 via guard below.
PARENT_MODE=""
CHILD_MODE=""

if command -v jq >/dev/null 2>&1; then
  PARENT_MODE=$(printf '%s' "$INPUT" | jq -r '.permission_mode // empty' 2>/dev/null || true)
  CHILD_MODE=$(printf '%s' "$INPUT"  | jq -r '.tool_input.mode // empty'  2>/dev/null || true)
elif command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  PY=$(command -v python3 2>/dev/null || command -v python)
  read -r PARENT_MODE CHILD_MODE <<<"$(printf '%s' "$INPUT" | "$PY" -c '
import json, sys
try:
    data = json.loads(sys.stdin.read())
    pm = data.get("permission_mode", "")
    cm = data.get("tool_input", {}).get("mode", "")
    print(pm, cm)
except Exception:
    print("", "")
' 2>/dev/null || echo " ")"
else
  # Last-resort substring scan — extracts known literal tokens only.
  # This path cannot emit (emission requires jq or python), so imprecision
  # here merely means we may reach the emit block unnecessarily; the emit
  # block will fail-open without jq/python regardless.
  if [[ "$INPUT" == *'"permission_mode"'* ]]; then
    for _m in plan default manual acceptEdits auto dontAsk bypassPermissions; do
      if [[ "$INPUT" == *"\"permission_mode\":\"${_m}\""* ]] || \
         [[ "$INPUT" == *"\"permission_mode\": \"${_m}\""* ]]; then
        PARENT_MODE="$_m"
        break
      fi
    done
  fi
  # tool_input.mode is nested; look for bare "mode" key.
  # This path is structurally safe: it cannot emit (the emit block requires
  # jq/python; if either is absent, the last-resort fires AND all emit paths
  # fail-open). A false CHILD_MODE extraction on prompt content only reaches
  # emit when jq/python is present — which means this branch wasn't taken.
  # Review: code-reviewer — F5: corrected containment reasoning (structural,
  #   not field-name-uniqueness).
  if [[ "$INPUT" == *'"tool_input"'* ]]; then
    for _m in plan default manual acceptEdits auto dontAsk bypassPermissions; do
      if [[ "$INPUT" == *"\"mode\":\"${_m}\""* ]] || \
         [[ "$INPUT" == *"\"mode\": \"${_m}\""* ]]; then
        CHILD_MODE="$_m"
        break
      fi
    done
  fi
fi

# --- Fail-open: cannot determine parent mode ---
[[ -z "$PARENT_MODE" ]] && exit 0

# --- Compute autonomy ranks ---
PARENT_RANK=$(mode_rank "$PARENT_MODE")

# Absent child mode → treated as acceptEdits (rank 2); below every autonomous parent.
CHILD_EFFECTIVE="${CHILD_MODE:-acceptEdits}"
CHILD_RANK=$(mode_rank "$CHILD_EFFECTIVE")

# --- Unknown rank → fail-open ---
[[ "$PARENT_RANK" -lt 0 ]] && exit 0
[[ "$CHILD_RANK"  -lt 0 ]] && exit 0

# --- Only raise when parent is autonomous (rank ≥ 3: auto, dontAsk, bypassPermissions) ---
[[ "$PARENT_RANK" -lt 3 ]] && exit 0

# --- Child is already at or above parent posture → no change needed ---
[[ "$CHILD_RANK" -ge "$PARENT_RANK" ]] && exit 0

# --- Emit: permissionDecision:"allow" + updatedInput (full merge) ---
# jq preferred: .tool_input + {mode: $m} merges original keys, overwriting mode only.
# The type guard ("object") ensures we never emit a partial updatedInput when
# tool_input is absent or null — fail-open instead.
if command -v jq >/dev/null 2>&1; then
  OUT=$(jq -nc \
    --argjson orig "$INPUT" \
    --arg m "$PARENT_MODE" \
    'if (($orig.tool_input | type) == "object") then
       {hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow",
        updatedInput: ($orig.tool_input + {mode: $m})}}
     else
       empty
     end' 2>/dev/null || true)
  if [[ -n "$OUT" ]]; then
    printf '%s\n' "$OUT"
    exit 0
  fi
  # jq produced empty (tool_input absent/non-object) or failed → fall through
fi

# Python fallback — same full-merge semantics.
if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  PY=$(command -v python3 2>/dev/null || command -v python)
  result=$(printf '%s' "$INPUT" | ENFORCE_MODE="$PARENT_MODE" "$PY" -c '
import json, sys, os
try:
    data = json.loads(sys.stdin.read())
    ti = data.get("tool_input")
    mode = os.environ.get("ENFORCE_MODE", "")
    if not (isinstance(ti, dict) and ti and mode):
        sys.exit(0)
    merged = dict(ti)
    merged["mode"] = mode
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": merged
        }
    }
    print(json.dumps(out))
except Exception:
    pass
' 2>/dev/null || true)
  if [[ -n "$result" ]]; then
    printf '%s\n' "$result"
    exit 0
  fi
fi

# Last resort: cannot safely reconstruct full updatedInput without jq/python → fail-open.
exit 0
