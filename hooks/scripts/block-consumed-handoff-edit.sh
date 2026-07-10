#!/usr/bin/env bash
# PreToolUse hook: Blocks runtime Write/Edit/MultiEdit/NotebookEdit on handoff
# files (state/handoffs/*.md) whose YAML frontmatter declares `status: consumed`.
#
# Why: a consumed handoff is paper trail, not a live progress journal. A picked-
# up handoff has been claimed (status: consumed, consumed_by: <session>) and the
# next session is supposed to find a SUCCESSOR handoff (status: active,
# deployment_state: ready_to_fire) via `/handoff` chain-archival. Appending
# progress sections in-place to the consumed predecessor (a) corrupts the audit
# trail (one file with N sessions' progress prose stapled together), (b) bypasses
# the carry-forward / cascade machinery the handoff skill enforces, and (c) is
# invisible to the pickup index — the next opener would have to grep an archived
# predecessor's body to find current state.
#
# Design-as-offers: this deny LEADS WITH the alternative ("write a successor via
# `/handoff`"), not a bare block. The consumed-handoff body is a checkpoint, the
# next checkpoint goes in a new file.
#
# Exemptions baked in:
# - Pickup consume transition and ship-stamp — `cs_consume_handoff` (pickup
#   consume transition) and `stamp_shipped_in` (ship/supersede) in
#   `lib/coordinator-archive-stamp.sh` write frontmatter via node-over-Bash.
#   They are NOT matched by this Edit-family-only hook. The lifecycle write
#   sails through; manual Edit-tool body-appends to a consumed handoff stay
#   blocked — that is the behavior we want.
# - `/pickup` in-place status-flip (legacy Edit path) — the frontmatter fields
#   status/consumed_by/consumed_at were written BEFORE the file reaches
#   `status: consumed`, so this hook did not see them (the on-disk state at the
#   moment of the Edit was still `status: active`). Now superseded by the
#   `cs_consume_handoff` bash helper above.
# - `/handoff` chain-archival — moves the file to archive/handoffs/ via shell
#   `git mv` / `mv`, not a Write/Edit tool call; this hook does not fire on Bash.
#
# Override: COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT=1 is recovery-only —
# reserved for recovery-flavor crash-invalidation notes into sibling consumed
# handoffs (the handoff skill's recovery sweep) and one-off paper-trail
# corrections. It is NOT needed for routine pickup; the lifecycle write now
# routes through the bash helper family above, which bypasses this hook by
# tool-type. Never use this override for progress appends.
#
# Deny mechanism: hookSpecificOutput.permissionDecision → stdout → exit 0
#   (matches block-tracker-edit.sh; the {"decision":"block"}→stderr→exit 1 shape
#    is documented as silently non-blocking in hook-best-practices.md.)

set -uo pipefail

# Safe stdin read
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

# Honor escape hatch
if [[ "${COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT:-0}" == "1" ]]; then
  exit 0
fi

# Filter on tool_name before parsing file_path
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
case "$TOOL_NAME" in
  Write|Edit|MultiEdit|NotebookEdit) : ;;
  *) exit 0 ;;
esac

# Parse file_path(s): Write/Edit/NotebookEdit carry a top-level file_path;
# MultiEdit carries per-edit file_path values inside .tool_input.edits[].
# Review: code-reviewer (F8) — MultiEdit bypass fixed: jq path now enumerates
# all edits[].file_path when top-level file_path is absent, then checks each
# candidate for consumed-handoff status instead of exiting 0 on empty path.
if command -v jq &>/dev/null; then
  _CANDIDATES=$(echo "$INPUT" | jq -r \
    '.tool_input.file_path // ((.tool_input.edits // [])[] | .file_path // empty)' \
    2>/dev/null | grep -v '^$' || true)
else
  # sed: matches every "file_path" value in the JSON body; for MultiEdit on a
  # single-line payload greedy .* yields the last match — adequate for fallback.
  _CANDIDATES=$(echo "$INPUT" | sed -n \
    's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
fi
[[ -z "$_CANDIDATES" ]] && exit 0

# Walk candidates: find the first one that is a consumed handoff. For MultiEdit
# this checks all edits[].file_path; for single-file tools there is one candidate.
FILE_PATH=""
FILE_PATH_NORM=""
while IFS= read -r _cand; do
  [[ -z "$_cand" ]] && continue
  # Normalize backslashes → forward slashes, collapse slash runs (reviewer F2, 2026-06-09)
  _cn="${_cand//\\//}"
  while [[ "$_cn" == *//* ]]; do _cn="${_cn//\/\///}"; done
  # Security: reject paths containing .. segments (prevents traversal such as
  # ../../state/handoffs/x.md escaping the repo root before the file check).
  # Spec backlink: strang-06 item E security hardening.
  [[ "$_cn" =~ (^|/)\.\.(/|$) ]] && continue
  # Security: resolve against the git root and confirm the path stays under
  # <git-root>/state/handoffs/ — prevents an absolute path outside this repo
  # (e.g. /attacker/state/handoffs/x.md) from matching the regex via its (^|/)
  # anchor and directing a scaffold write to the attacker-controlled location.
  # Canonicalize via cd+pwd -P (portable BSD+GNU, no realpath dependency) so
  # macOS symlinks (/var/... → /private/var/...) don't cause a false mismatch
  # between the git-root canonical form and the incoming path.
  _git_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [[ -n "$_git_root" ]]; then
    if [[ "$_cn" == /* ]]; then
      _abs_cn="$_cn"
    else
      _abs_cn="${_git_root%/}/${_cn}"
    fi
    _abs_cn_canon=$(cd "$(dirname "$_abs_cn")" 2>/dev/null \
      && printf '%s/%s' "$(pwd -P)" "$(basename "$_abs_cn")" \
      || printf '%s' "$_abs_cn")
    [[ "$_abs_cn_canon" != "${_git_root%/}/state/handoffs/"* ]] && continue
  fi
  # Only handoff files under state/handoffs/ (not archive/, not tasks/)
  [[ ! "$_cn" =~ (^|/)state/handoffs/[^/]+\.md$ ]] && continue
  # File must exist — a Write to a new file is fine (new handoffs are status: active)
  [[ ! -f "$_cn" ]] && continue
  # Read status from frontmatter; strip inline comments and surrounding quotes
  # (reviewer F1, 2026-06-09; awk for BSD/GNU portability)
  _st=$(awk '
    BEGIN { in_fm = 0; line_no = 0 }
    /^---[[:space:]]*$/ {
      line_no++
      if (line_no == 1) { in_fm = 1; next }
      if (line_no == 2) { exit }
    }
    in_fm && /^status:[[:space:]]/ {
      sub(/^status:[[:space:]]*/, "")
      sub(/[[:space:]]*#.*$/, "")
      sub(/[[:space:]]*$/, "")
      sub(/^["'"'"']/, "")
      sub(/["'"'"']$/, "")
      print
      exit
    }
  ' "$_cn" 2>/dev/null || true)
  if [[ "$_st" == "consumed" ]]; then
    FILE_PATH="$_cand"
    FILE_PATH_NORM="$_cn"
    break
  fi
done <<< "$_CANDIDATES"

[[ -z "$FILE_PATH" ]] && exit 0

# ─── Scaffold successor (design-as-offers: block AND scaffold next step) ──────
# Parse additional frontmatter fields; attempt to write a pre-scaffolded
# successor so the deny message can name a concrete file to open.
# Degrades gracefully (plain deny, no scaffold) if the handoffs dir is not
# writable or the write fails.

HANDOFFS_DIR=$(dirname "$FILE_PATH_NORM")
CONSUMED_BASENAME=$(basename "$FILE_PATH_NORM")
CONSUMED_STEM=$(basename "$FILE_PATH_NORM" .md)

# Extract a named frontmatter field; strips inline comments and surrounding
# quotes. Same approach as the STATUS extraction above; awk -v for portability.
_extract_fm() {
  local fld="$1"
  awk -v fld="$fld" '
    BEGIN { in_fm=0; ln=0 }
    /^---[[:space:]]*$/ {
      ln++
      if (ln==1) { in_fm=1; next }
      if (ln==2) { exit }
    }
    in_fm && $0 ~ ("^" fld ":[[:space:]]") {
      val = $0
      sub("^" fld ":[[:space:]]*", "", val)
      sub(/[[:space:]]*#.*$/, "", val)
      sub(/[[:space:]]*$/, "", val)
      sub(/^["'"'"']/, "", val)
      sub(/["'"'"']$/, "", val)
      print val
      exit
    }
  ' "$FILE_PATH_NORM" 2>/dev/null || true
}

FM_TITLE=$(_extract_fm "title")
FM_BRANCH=$(_extract_fm "branch")
FM_WORKSTREAM=$(_extract_fm "workstream")
FM_SPRINT=$(_extract_fm "sprint")
FM_ROADMAP_ID=$(_extract_fm "roadmap_id")

if [[ -n "$FM_TITLE" ]]; then
  SUCC_TITLE="Successor of: ${FM_TITLE}"
else
  SUCC_TITLE="Successor of: ${CONSUMED_BASENAME}"
fi

# Review: code-reviewer (F10) — two separate date calls risk midnight-rollover
# split; combine into one call so date and time are from the same instant.
TS=$(date '+%Y-%m-%d_%H%M%S')
SUCC_FILENAME="${TS}_successor-of-${CONSUMED_STEM}.md"
SUCC_PATH="${HANDOFFS_DIR}/${SUCC_FILENAME}"

# Attempt scaffold write. SCAFFOLD_PATH stays empty on any failure so the deny
# message falls back to the original plain-text form (no scaffold reference).
SCAFFOLD_PATH=""

# Review: code-reviewer (F9) — unescaped FM values break YAML; a title with an
# embedded " produced invalid YAML; unquoted branch with : caused a mapping-key
# collision. Escape \ and " before interpolating into double-quoted YAML scalars,
# and quote all inherited FM fields defensively.
_yaml_dq_escape() {
  local v="$1"
  v="${v//\\/\\\\}"
  v="${v//\"/\\\"}"
  printf '%s' "$v"
}

if [[ -w "$HANDOFFS_DIR" ]]; then
  _write_scaffold() {
    printf -- "---\n"
    printf "status: active\n"
    printf "predecessor: %s\n" "$CONSUMED_BASENAME"
    printf 'title: "%s"\n' "$(_yaml_dq_escape "$SUCC_TITLE")"
    if [[ -n "$FM_BRANCH" ]];     then printf 'branch: "%s"\n'     "$(_yaml_dq_escape "$FM_BRANCH")";     fi
    if [[ -n "$FM_WORKSTREAM" ]]; then printf 'workstream: "%s"\n' "$(_yaml_dq_escape "$FM_WORKSTREAM")"; fi
    if [[ -n "$FM_SPRINT" ]];     then printf 'sprint: "%s"\n'     "$(_yaml_dq_escape "$FM_SPRINT")";     fi
    if [[ -n "$FM_ROADMAP_ID" ]]; then printf 'roadmap_id: "%s"\n' "$(_yaml_dq_escape "$FM_ROADMAP_ID")"; fi
    printf -- "---\n"
    printf "\n# %s\n\n" "$SUCC_TITLE"
    printf "_Continuation from %s. Fill in current state here._\n" "$CONSUMED_BASENAME"
  }
  if _write_scaffold > "$SUCC_PATH" 2>/dev/null; then
    SCAFFOLD_PATH="$SUCC_PATH"
  fi
fi

# ─── Emit deny ────────────────────────────────────────────────────────────────
BASENAME=$(basename "$FILE_PATH")
if [[ -n "$SCAFFOLD_PATH" ]]; then
  REASON="Consumed-handoff edit blocked: ${FILE_PATH} has frontmatter \`status: consumed\` — it is paper trail, not a live progress journal. A successor handoff has been pre-scaffolded at \`${SCAFFOLD_PATH}\` — open it and add your content there instead. The consumed predecessor was claimed by a prior /pickup; the next checkpoint belongs in the successor, not appended to this body. Once the successor is populated, invoke \`/handoff\` to chain-archive the predecessor to archive/handoffs/. If this edit is a recovery-sweep crash-invalidation note or a one-off paper-trail correction (not a progress append), set COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT=1. See docs/wiki/coordinator-tripwires.md § consumed-handoff-frozen."
else
  REASON="Consumed-handoff edit blocked: ${FILE_PATH} has frontmatter \`status: consumed\` — it is paper trail, not a live progress journal. The picked-up predecessor was claimed by a prior /pickup; the next checkpoint belongs in a SUCCESSOR handoff, not appended to this body. To continue the workstream: invoke \`/handoff\` (writes a fresh successor with status: active, deployment_state: ready_to_fire, predecessor: ${BASENAME}, then chain-archives the predecessor to archive/handoffs/). The successor is what the next session's /pickup will find; an in-place append is invisible to that index. If this edit is a recovery-sweep crash-invalidation note or a one-off paper-trail correction (not a progress append), set COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT=1. See docs/wiki/coordinator-tripwires.md § consumed-handoff-frozen and skills/pickup/SKILL.md § Step 5 negative-spec."
fi
if command -v jq &>/dev/null; then
  jq -nc --arg reason "$REASON" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
else
  esc="${REASON//\\/\\\\}"
  esc="${esc//\"/\\\"}"
  esc="${esc//$'\n'/\\n}"
  esc="${esc//$'\t'/\\t}"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
fi
exit 0
