#!/usr/bin/env bash
# PostToolUse hook: when a file is Written or Edited under state/initiatives/*.yaml
# AND the written initiative has empty/absent goals AND the repo has >=1 goal under
# state/goals/ — surface an offer-shaped nudge with matching candidate goal-ids.
#
# Why PostToolUse + exit 2 (not PreToolUse deny):
#   The predecessor design-as-offers doctrine (eager-agent-calibration.md §
#   Offer-Shape vs Friction-as-Warning) requires that tooling LEADS WITH the better
#   alternative, not the violation.  A PostToolUse advisory reaches the model's next
#   turn via exit 2 + stderr WITHOUT blocking the write.  A PreToolUse deny would
#   prevent the author from writing the initiative at all — wrong altitude for a
#   "have you considered tagging a goal?" nudge.
#
#   Platform contract (docs/wiki/hook-best-practices.md § Friction-as-warning):
#     - PostToolUse exit 2  -> tool already ran; stderr fed into model's next turn.
#     - exit 0 + stderr     -> goes to the user terminal only, never the model.
#   This is the ONLY warn-reaches-the-model-without-blocking channel.
#
# Fires on: PostToolUse Write|Edit when file_path matches */state/initiatives/*.yaml
#   AND written initiative content has empty or absent goals field
#   AND the writing repo has >=1 *.md file under state/goals/.
#
# Suppressed (silent exit 0):
#   - COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF=1 (autonomous runs, noise reduction).
#   - File path is outside state/initiatives/.
#   - Initiative content already has a non-empty goals field.
#   - No goals exist under state/goals/ in the repo (nothing to suggest, checked via *.md glob).
#
# Nudged (exit 2 + stderr): all other cases. The message LEADS WITH candidate
# goal-ids (offer-shape per eager-agent-calibration.md § Offer-Shape vs Friction-as-
# Warning) — "did you mean to tag goal X or Y?" — then the attachment command.
# Never blocks; never demands an override.
#
# Spec backlink: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § C4

set -uo pipefail

# ── Silence switch for autonomous mode ────────────────────────────────────────
if [[ "${COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF:-0}" == "1" ]]; then
  exit 0
fi

# ── Safe stdin read ────────────────────────────────────────────────────────────
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# ── Parse fields (prefer jq, fall back to python3, then sed) ──────────────────
CONTENT=""
TOOL_NAME=""
FILE_PATH=""

if command -v jq &>/dev/null; then
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
  TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  CONTENT=$(printf '%s' "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty' 2>/dev/null | head -60 || true)
elif command -v python3 &>/dev/null; then
  PARSED=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
  d = json.loads(sys.stdin.read())
  ti = d.get("tool_input", {}) or {}
  for v in (ti.get("file_path", ""), d.get("tool_name", "")):
    sys.stdout.write((v or "") + "\n")
except Exception:
  sys.stdout.write("\n\n")
' | tr -d '\r')
  { IFS= read -r FILE_PATH; IFS= read -r TOOL_NAME; } <<< "$PARSED"
  CONTENT=$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
  d = json.loads(sys.stdin.read())
  ti = d.get("tool_input", {}) or {}
  val = ti.get("content") or ti.get("new_string") or ""
  sys.stdout.write(str(val)[:4000])
except Exception:
  pass
' | tr -d '\r' | head -60)
else
  FILE_PATH=$(printf '%s' "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TOOL_NAME=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  # CONTENT left empty — reliable YAML extraction needs a JSON parser; fail-open
  # means the EM gets a nudge to proceed past if goals cannot be checked from content.
fi

# ── Only fire on Write or Edit ─────────────────────────────────────────────────
case "${TOOL_NAME:-}" in
  Write|Edit) ;;
  *) exit 0 ;;
esac

[[ -z "$FILE_PATH" ]] && exit 0

FILE_PATH_NORM="${FILE_PATH//\\//}"

# ── Only fire on state/initiatives/*.yaml paths ───────────────────────────────
case "$FILE_PATH_NORM" in
  */state/initiatives/*.yaml|state/initiatives/*.yaml) ;;
  *) exit 0 ;;
esac

# ── First-class suppression: initiative already has goals ─────────────────────
# Check the written content for a non-empty goals field.
# Matches: "goals:" followed by a non-empty value on the same line, OR a list item on
# the next line starting with "  -" (YAML list form).  A bare "goals: null", "goals: []",
# or absent "goals:" is treated as empty — trigger the nudge.
if [[ -n "$CONTENT" ]]; then
  # Inline value form: goals: something-non-empty (not null, not [], not "")
  if printf '%s' "$CONTENT" | grep -qE '^goals:[[:space:]]*[^[:space:]#\[]' ; then
    # Has an inline non-null value — check it's not explicitly null or empty string.
    _goals_val=$(printf '%s' "$CONTENT" | grep -E '^goals:' | head -1 | sed 's/^goals:[[:space:]]*//')
    case "${_goals_val:-}" in
      null|""|"[]"|"~") ;;  # empty/null — fall through to nudge
      *) exit 0 ;;           # non-empty value — suppress
    esac
  fi
  # List form: goals: followed by a "  - " item on the next line.
  if printf '%s' "$CONTENT" | grep -qE '^goals:' && printf '%s' "$CONTENT" | grep -A1 '^goals:' | grep -qE '^[[:space:]]+-'; then
    exit 0
  fi
fi

# ── Resolve repo root for goals/ lookup ───────────────────────────────────────
# Prefer git rev-parse from the file's directory; fall back to PWD.
_repo_root=""
_dir_of_file="$(dirname "$FILE_PATH_NORM")"
if [[ -d "$_dir_of_file" ]]; then
  _repo_root="$(git -C "$_dir_of_file" rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$_repo_root" ]]; then
  _repo_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$_repo_root" ]]; then
  # Cannot resolve repo — fail-open: no nudge (we can't check goals/ either).
  exit 0
fi

# ── Suppress if no goals exist under state/goals/ ────────────────────────────
_goals_dir="${_repo_root}/state/goals"
if [[ ! -d "$_goals_dir" ]]; then
  exit 0
fi
_goal_count=0
# BSD-compatible: use a glob pattern test rather than find -count.
# Review: code-reviewer — goals are scaffolded as *.md (coordinator-doc-new --type goal
# outputs state/goals/YYYY-MM-DD-<slug>.md); *.yaml glob was a dead letter (F7).
for _f in "${_goals_dir}"/*.md; do
  [[ -f "$_f" ]] && _goal_count=$(( _goal_count + 1 ))
done
if [[ "$_goal_count" -eq 0 ]]; then
  exit 0
fi

# ── Resolve candidate goals via resolve-goal-candidates.sh ───────────────────
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
_RESOLVE_BIN="${_SCRIPT_DIR}/../../bin/resolve-goal-candidates.sh"

# Derive match text from the initiative label/description in the written content,
# falling back to the file basename stem.
_match_text=""
if [[ -n "$CONTENT" ]]; then
  # Try 'label:' field first, then 'description:'.
  _match_text=$(printf '%s' "$CONTENT" | grep -E '^label:[[:space:]]+' | head -1 | sed 's/^label:[[:space:]]*//' | tr -d '"' || true)
  if [[ -z "$_match_text" ]]; then
    _match_text=$(printf '%s' "$CONTENT" | grep -E '^description:[[:space:]]+' | head -1 | sed 's/^description:[[:space:]]*//' | tr -d '"' | cut -c1-120 || true)
  fi
fi
if [[ -z "$_match_text" ]]; then
  # Fall back to filename stem (e.g. "my-initiative" from my-initiative.yaml).
  _match_text="$(basename "$FILE_PATH_NORM" .yaml)"
fi

_candidates_json=""
if [[ -f "$_RESOLVE_BIN" ]]; then
  _candidates_json="$(bash "$_RESOLVE_BIN" --repo "$_repo_root" --text "$_match_text" 2>/dev/null || true)"
fi

# ── Extract top candidate goal-ids from JSON ─────────────────────────────────
# Parse candidates JSON (prefer python3; BSD sed fallback for simple cases).
_candidate_ids=""
if [[ -n "$_candidates_json" ]] && command -v python3 &>/dev/null; then
  _candidate_ids=$(printf '%s' "$_candidates_json" | python3 -c '  # popup-safe-env-suppressed
import json, sys
try:
  d = json.loads(sys.stdin.read())
  cands = d.get("candidates", [])
  ids = [c.get("goal_id", "") for c in cands[:3] if c.get("goal_id")]
  print(" or ".join(ids))
except Exception:
  pass
' 2>/dev/null || true)
fi

# ── Build the offer-shaped nudge message ─────────────────────────────────────
# Leads with the candidate goal-ids (offer-shape: better path first, not the violation).
_initiative_id="$(basename "$FILE_PATH_NORM" .yaml)"

{
  printf '[nudge] Initiative %s was written without a goals field' "$_initiative_id"
  if [[ -n "$_candidate_ids" ]]; then
    printf ' — did you mean to tag goal %s?\n' "$_candidate_ids"
    printf '[nudge]\n'
    printf '[nudge] To attach goal(s) to this initiative:\n'
    printf '[nudge]   coordinator-initiative attach --goals %s state/initiatives/%s.yaml\n' \
      "$(printf '%s' "$_candidate_ids" | awk '{print $1}')" "$_initiative_id"
    printf '[nudge]\n'
    printf '[nudge] Other matching goals: %s\n' "$_candidate_ids"
  else
    printf '.\n'
    printf '[nudge]\n'
    printf '[nudge] This repo has goals under state/goals/ — consider tagging one:\n'
    printf '[nudge]   coordinator-initiative attach --goals <goal-id> state/initiatives/%s.yaml\n' \
      "$_initiative_id"
  fi
  printf '[nudge]\n'
  printf '[nudge] If this initiative intentionally has no goals, ignore this — nothing is blocked.\n'
  printf '[nudge] Silence in autonomous runs: COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF=1.\n'
} >&2

exit 2
