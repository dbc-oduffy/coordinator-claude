#!/usr/bin/env bash
# PreToolUse hook: Blocks runtime Write/Edit to the generated handoff tracker
# files (state/handoff-tracker.md, state/doe-handoff-tracker.md).
#
# Spec backlink: docs/plans/2026-05-29-handoff-tracker-system.md (edit-resistance follow-up)
#
# Why: the tracker is a DISPOSABLE RENDER produced by bin/render-handoff-tracker.js
# from handoff frontmatter (the single source of truth). A hand-edit is silently
# clobbered on the next render AND, if committed first, masquerades as source —
# the exact failure the tracker system exists to prevent. This hook keeps the
# render authoritative by redirecting edits back to the renderer.
#
# Design-as-offers: this is a deny that LEADS WITH THE ALTERNATIVE ("run the
# renderer") rather than a bare block. The frontmatter, not the table, is where
# a real change belongs.
#
# Fires on Write / Edit / MultiEdit / NotebookEdit targeting a path whose tail
# is state/handoff-tracker.md or state/doe-handoff-tracker.md (matched on the
# tail, not the full prefix, so worktrees and project moves work).
#
# Override: COORDINATOR_OVERRIDE_TRACKER_EDIT=1 (rare-use; e.g. authoring a
# fixture tracker, a one-off manual correction the renderer cannot yet express,
# or test scaffolding).
#
# Deny mechanism: hookSpecificOutput.permissionDecision → stdout → exit 0
#   (matches block-completion-monolith-write.sh; the {"decision":"block"}→stderr
#    →exit 1 shape is documented as silently non-blocking in
#    hook-best-practices.md § PreToolUse deny).

set -uo pipefail
# NOTE: -e deliberately omitted — deny hook must fail-open (allow) on unexpected error, never fail-closed.

# Safe stdin read
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

# Honor escape hatch
if [[ "${COORDINATOR_OVERRIDE_TRACKER_EDIT:-0}" == "1" ]]; then
  exit 0
fi

# Filter on tool_name before parsing file_path (matcher is best-effort; an
# explicit guard prevents false-positive matches from other tool surfaces).
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

# Normalize backslashes → forward slashes, then collapse slash runs (mirrors
# block-completion-monolith-write.sh F5 fix for Windows + sed-fallback paths).
FILE_PATH_NORM="${FILE_PATH//\\//}"
while [[ "$FILE_PATH_NORM" == *//* ]]; do
  FILE_PATH_NORM="${FILE_PATH_NORM//\/\///}"
done

# Match the generated tracker files by path tail. The renderer writes
# <root>/state/handoff-tracker.md and ~/.claude/state/doe-handoff-tracker.md
# (per render-handoff-tracker.js header) — NOT tasks/ (a stale relic from before the
# state/-vs-tasks/ split that silently disabled this guard).
if [[ "$FILE_PATH_NORM" =~ (^|/)state/(handoff-tracker|doe-handoff-tracker)\.md$ ]]; then
  REASON="Tracker edit blocked: ${FILE_PATH} is a GENERATED render, not source. The handoff tracker is produced by bin/render-handoff-tracker.js from handoff frontmatter (the single source of truth) — any hand-edit is overwritten on the next render and, if committed first, masquerades as source. To change what the tracker shows, edit the relevant handoff's frontmatter (category / summary / deployment_state) and re-run: render-handoff-tracker.js (add --root <repo> for another repo, --all-repos for the DoE aggregate). See docs/wiki/handoff-tracker-system.md. If you genuinely must hand-write this file (fixture / one-off correction), set COORDINATOR_OVERRIDE_TRACKER_EDIT=1."
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
fi

exit 0
