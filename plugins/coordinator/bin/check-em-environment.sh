#!/bin/bash
# EM environment safety-check — invoked as a STEP inside the ceremony skills
# (/session-start, /workday-start, /workweek-start), NOT as a hook. Verifies the
# EM is running on the expected EFFORT (medium) and, best-effort, MODEL (Opus),
# and prints a loud banner on drift. Silent on a clean env. Always exits 0.
#
# Why a skill step, not a hook:
#   A UserPromptSubmit hook would fire before every prompt (overhead + the
#   documented Windows/Git-Bash stdin-hang that moved context-pressure-advisory
#   off that event in 2026-03). A SessionStart hook fires on every boot — noise.
#   Baking the check into the three "start" ceremonies runs it exactly when the
#   EM is deliberately orienting, with zero per-prompt cost. The skill relays
#   any banner this prints; clean env prints nothing.
#
# Division of labour (why model is "best-effort" but effort is authoritative):
#   - EFFORT is the token pit: Anthropic periodically bumps the *default* effort,
#     so an unpinned/bumped effort silently inflates cost. The EM CANNOT observe
#     effort — it shows only in the CLI startup banner ("Opus 4.8 with medium
#     effort"), never in the system prompt or transcript. settings.json
#     `effortLevel` is the only mechanically-readable anchor, so this script is
#     the SOLE guard. (The skill does not ask the EM to self-check effort.)
#   - MODEL the EM CAN self-check from its own system prompt, so the skill
#     carries a one-line EM-side confirmation as the reliable path. This script
#     also reads the model from the session transcript as a best-effort second
#     line of defence, but degrades silently if it can't resolve the transcript.
#
# Usage:  bash check-em-environment.sh
#   Optional: --transcript <path> to pin the transcript for the model check.

TRANSCRIPT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --transcript) TRANSCRIPT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# ---------------------------------------------------------------------------
# EFFORT check — resolve effortLevel across settings.json in CC precedence.
# Authoritative: needs no session context, just the settings files.
# ---------------------------------------------------------------------------
read_effort() {
  local file="$1"
  [[ ! -f "$file" ]] && return
  if command -v jq &>/dev/null; then
    jq -r '.effortLevel // empty' "$file" 2>/dev/null
  else
    grep -o '"effortLevel"[[:space:]]*:[[:space:]]*"[^"]*"' "$file" 2>/dev/null \
      | head -1 | sed 's/.*"effortLevel"[[:space:]]*:[[:space:]]*"//; s/"$//'
  fi
}

EFFORT=""
EFFORT_SOURCE=""
USER_CLAUDE="${HOME:-$USERPROFILE}/.claude"
# CLAUDE_PROJECT_DIR is platform-injected; PWD is the fallback.
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
# Claude Code precedence, highest first: project-local > project > user-local >
# user. settings.local.json overrides settings.json at the same scope.
for cand in \
  "$PROJ/.claude/settings.local.json" \
  "$PROJ/.claude/settings.json" \
  "$USER_CLAUDE/settings.local.json" \
  "$USER_CLAUDE/settings.json"; do
  v=$(read_effort "$cand")
  if [[ -n "$v" ]]; then EFFORT="$v"; EFFORT_SOURCE="$cand"; break; fi
done

EFFORT_WARN=""
if [[ -z "$EFFORT" ]]; then
  EFFORT_WARN="unpinned"
elif [[ "$EFFORT" != "medium" ]]; then
  EFFORT_WARN="$EFFORT"
fi

# ---------------------------------------------------------------------------
# MODEL check — best-effort. Resolve the session transcript and read the most
# recent model line; degrade to silent if it can't be found.
# ---------------------------------------------------------------------------
latest_model() {
  local file="$1"
  [[ ! -f "$file" ]] && return
  # grep is the large producer, tail -1 the early-exiting consumer — the safe
  # pipe direction. No tac, no fixed line-window: keeps the LAST model entry.
  grep -oE '"model":"[^"]*"' "$file" 2>/dev/null \
    | tail -1 \
    | sed 's/"model":"//; s/"$//'
}

# Resolve a transcript if not passed explicitly: the platform session id names
# the file under ~/.claude/projects/<munged-cwd>/<session-id>.jsonl.
if [[ -z "$TRANSCRIPT" && -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
  TRANSCRIPT=$(find "$USER_CLAUDE/projects" -maxdepth 2 -name "${CLAUDE_CODE_SESSION_ID}.jsonl" 2>/dev/null | head -1)
fi

CURRENT_MODEL=""
[[ -n "$TRANSCRIPT" ]] && CURRENT_MODEL=$(latest_model "$TRANSCRIPT")

MODEL_WARN=""
case "$CURRENT_MODEL" in
  ""|*opus*) ;;  # unknown (degrade silent) or opus → no model warning
  *) MODEL_WARN="$CURRENT_MODEL" ;;
esac

# ---------------------------------------------------------------------------
# Emit — only if something drifted.
# ---------------------------------------------------------------------------
[[ -z "$MODEL_WARN" && -z "$EFFORT_WARN" ]] && exit 0

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  ⚠  EM ENVIRONMENT DRIFT"
if [[ -n "$MODEL_WARN" ]]; then
  echo "║"
  echo "║  MODEL: transcript shows ${MODEL_WARN}, not Opus."
  echo "║    → WARN the PM in your first response; recommend /model back to Opus."
fi
if [[ -n "$EFFORT_WARN" ]]; then
  echo "║"
  if [[ "$EFFORT_WARN" == "unpinned" ]]; then
    echo "║  EFFORT: not pinned in any settings.json — runtime follows Anthropic's"
    echo "║    default, which drifts upward (a token pit). Expected: medium."
    echo "║    → Recommend pinning \"effortLevel\": \"medium\" in settings.json."
  else
    echo "║  EFFORT: pinned to '${EFFORT_WARN}', not medium  (${EFFORT_SOURCE/#$HOME/\~})."
    echo "║    → WARN the PM; medium is the cost-calibrated default for EM work."
  fi
fi
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

exit 0
