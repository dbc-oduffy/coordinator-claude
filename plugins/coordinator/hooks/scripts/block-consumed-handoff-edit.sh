#!/bin/bash
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
# - `/pickup` mutation step itself — the legitimate edits at pickup-time are the
#   frontmatter status/consumed_by/consumed_at fields. Those are written BEFORE
#   the file is `status: consumed`, so this hook does not see them (the on-disk
#   state at the moment of the Edit is still `status: active`).
# - `/handoff` chain-archival — moves the file to archive/handoffs/ via shell
#   `git mv` / `mv`, not a Write/Edit tool call; this hook does not fire on Bash.
# - Recovery flavor sweep — the recovery-flavor crash-rescue sweep in the handoff
#   skill writes one-line crash-invalidation notes into sibling handoffs. Those
#   siblings are typically `status: active`; if they happen to be `consumed`,
#   set COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT=1 for the sweep.
#
# Override: COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT=1 (rare-use; recovery
# sweep, fixture authoring, a one-off correction that is genuinely a paper-trail
# patch and not a progress append).
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

# Parse file_path
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

[[ -z "$FILE_PATH" ]] && exit 0

# Normalize backslashes → forward slashes, collapse slash runs
FILE_PATH_NORM="${FILE_PATH//\\//}"
while [[ "$FILE_PATH_NORM" == *//* ]]; do
  FILE_PATH_NORM="${FILE_PATH_NORM//\/\///}"
done

# Match only handoff files under state/handoffs/ (not archive/, not tasks/)
if [[ ! "$FILE_PATH_NORM" =~ (^|/)state/handoffs/[^/]+\.md$ ]]; then
  exit 0
fi

# File must exist on disk to read frontmatter. A Write to a new file is fine —
# new handoffs are status: active by construction. Use the normalized path: on
# Windows Git-Bash the original FILE_PATH may carry backslashes that bash test
# and awk handle inconsistently (reviewer F2, 2026-06-09).
[[ ! -f "$FILE_PATH_NORM" ]] && exit 0

# Read frontmatter: between first `---` and the next `---`. Bail if no FM.
# Use awk for BSD/GNU portability (no sed -n /1,/.../p ambiguity).
# Strips inline YAML comments before comparison so `status: consumed # picked
# up` does not silently bypass the guard (reviewer F1, 2026-06-09).
STATUS=$(awk '
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
    sub(/^["'\'']/, "")
    sub(/["'\'']$/, "")
    print
    exit
  }
' "$FILE_PATH_NORM" 2>/dev/null || true)

if [[ "$STATUS" != "consumed" ]]; then
  exit 0
fi

# Emit deny
BASENAME=$(basename "$FILE_PATH")
REASON="Consumed-handoff edit blocked: ${FILE_PATH} has frontmatter \`status: consumed\` — it is paper trail, not a live progress journal. The picked-up predecessor was claimed by a prior /pickup; the next checkpoint belongs in a SUCCESSOR handoff, not appended to this body. To continue the workstream: invoke \`/handoff\` (writes a fresh successor with status: active, deployment_state: ready_to_fire, predecessor: ${BASENAME}, then chain-archives the predecessor to archive/handoffs/). The successor is what the next session's /pickup will find; an in-place append is invisible to that index. If this edit is a recovery-sweep crash-invalidation note or a one-off paper-trail correction (not a progress append), set COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT=1. See docs/wiki/coordinator-tripwires.md § consumed-handoff-frozen and skills/pickup/SKILL.md § Step 5 negative-spec."
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
