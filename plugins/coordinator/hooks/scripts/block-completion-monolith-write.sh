#!/bin/bash
# PreToolUse hook: Blocks runtime writes to archive/completed/YYYY-MM.md
# outside the legacy/ subdirectory.
#
# Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 10
# Dogfood finding 2026-05-19: the static-grep tripwire
# (bin/check-no-monolith-completion-append.sh) catches LITERAL references to
# the monolith path in source files, but executors continued writing to
# archive/completed/YYYY-MM.md at runtime (their fallback instruction wasn't
# greppable as the literal-path pattern). This PreToolUse hook closes the
# gap by intercepting the actual Write/Edit/NotebookEdit tool call.
#
# Fires on Write / Edit / NotebookEdit targeting paths matching
# archive/completed/<YYYY-MM>.md (anywhere on the filesystem; matched on the
# tail of the path, not the full prefix, so worktrees and project moves work).
#
# Allowed exceptions:
#   - Paths under archive/completed/legacy/ (post-migration canonical home;
#     authoring legacy entries is allowed for AUTO-MIGRATE flow).
#   - The literal migration helper bin/migrate-completion-log-legacy.sh is
#     a Bash invocation, not Write/Edit, so it does not trigger this hook.
#   - Per-entry files under archive/completed/YYYY-MM/* (subdir form is the
#     correct Phase 1 path).
#
# Override: COORDINATOR_OVERRIDE_COMPLETION_MONOLITH=1 (rare-use; e.g.,
# authoring fixture data, test scaffolding, or one-off correction of legacy
# files where the AUTO-MIGRATE path is not appropriate).
#
# Deny mechanism: hookSpecificOutput.permissionDecision → stdout → exit 0
#   (matches block-subagent-archive-write.sh + block-off-daily-branch.sh; the old
#    {"decision":"block"}→stderr→exit 1 shape is documented as silently non-blocking
#    in hook-best-practices.md § PreToolUse deny).

set -uo pipefail

# Safe stdin read
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Honor escape hatch
if [[ "${COORDINATOR_OVERRIDE_COMPLETION_MONOLITH:-0}" == "1" ]]; then
  exit 0
fi

# Code-reviewer F9 fix: filter on tool_name before parsing file_path.
# The hook is registered for Write|Edit|NotebookEdit only, but the PreToolUse
# matcher is best-effort; an explicit guard prevents false-positive matches
# from other tool surfaces that happen to carry a "file_path" string.
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  # Note: sed pattern matches first occurrence of "tool_name"/"file_path"; relies on Claude Code
  # delivering these before any string values containing those literal keys.
  # Review: code-reviewer — documents sed first-occurrence assumption for no-jq fallback path
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
case "$TOOL_NAME" in
  Write|Edit|NotebookEdit|MultiEdit) : ;;
  *) exit 0 ;;
esac

# Parse file_path
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

[[ -z "$FILE_PATH" ]] && exit 0

# Code-reviewer F5 fix: normalize literal backslash → forward slash. The
# previous form `${FILE_PATH//\\\\//}` replaced DOUBLE backslashes (rare in
# practice) rather than the single backslashes Claude Code delivers on
# Windows. In bash parameter substitution, `\\` is a single literal
# backslash. Single-backslash Windows paths (post-jq decode) now normalize.
#
# Then collapse any runs of forward slashes to a single slash. This handles
# the sed-fallback case where the JSON envelope's `\\` (escape for one
# backslash) is extracted as two literal backslashes (sed does not decode
# JSON escapes); the substitution above produces `//`, which we collapse here.
FILE_PATH_NORM="${FILE_PATH//\\//}"
while [[ "$FILE_PATH_NORM" == *//* ]]; do
  FILE_PATH_NORM="${FILE_PATH_NORM//\/\///}"
done

# Match pattern: .../archive/completed/<YYYY-MM>.md
# Where YYYY is 4 digits, MM is 2 digits.
# Allowed exception 1: under archive/completed/legacy/* — never matches the
# pattern above because legacy/ inserts a path segment.
# Allowed exception 2: per-entry files under archive/completed/YYYY-MM/*.md —
# never matches either because there's an extra path segment after YYYY-MM.

if [[ "$FILE_PATH_NORM" =~ archive/completed/[0-9]{4}-[0-9]{2}\.md$ ]]; then
  REASON="Runtime monolith-write blocked: ${FILE_PATH} matches the legacy archive/completed/YYYY-MM.md shape, which Phase 1 of the completion-log release-loop replaced with per-entry files at archive/completed/YYYY-MM/YYYY-MM-DD-<chain-slug>-<sid6>.md. See docs/wiki/completion-log-release-loop.md. If you intended a legacy edit (rare — frozen pre-migration history), the canonical path is archive/completed/legacy/YYYY-MM.md and the override env var COORDINATOR_OVERRIDE_COMPLETION_MONOLITH=1 will permit the write. Otherwise, write a per-entry file under archive/completed/YYYY-MM/ instead."
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
    # Review: code-reviewer — tab escape was missing from no-jq manual escape pipeline; keeps it complete
    esc="${esc//$'\t'/\\t}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
fi

exit 0
