#!/usr/bin/env bash
# PreToolUse hook: Blocks writes to ~/.claude/docs/wiki/<name>.md when a
# matching plugin-doctrine wiki exists at <plugin>/docs/wiki/<name>.md.
#
# Spec backlink: docs/plans/2026-05-15-plugin-wiki-write-direction-trap.md § Phase 5
#
# Under Option B (2026-05-15), plugin-doctrine wikis live ONLY in the bundled
# plugin tree. A write to the dev-side path (~/.claude/docs/wiki/<name>.md)
# re-introduces the write-direction trap — two copies, drift is the default.
#
# Fires on Write / Edit / NotebookEdit targeting ~/.claude/docs/wiki/<name>.md.
# If a bundled copy exists at the plugin's docs/wiki/<name>.md, the write is
# BLOCKED with a message naming the bundled path.
#
# Override: COORDINATOR_OVERRIDE_WIKI_MIRROR=1 (rare-use; e.g., authoring a
# dev-side wiki that genuinely should not exist in the plugin tree — new
# project-level wikis before a bundled copy exists, or cleanup operations).
# Override is NOT needed for editing bundled wikis directly (the correct path).
#
# See also: docs/wiki/daily-branch-discipline.md for the precedent hook pattern
# (block-off-daily-branch.sh). Same override discipline applies here.
#
# Input schema (PreToolUse for Write/Edit/NotebookEdit):
#   { "tool_name": "Write|Edit|NotebookEdit", "tool_input": { "file_path": "..." }, ... }
#
# Deny mechanism (Form A): emit JSON {"hookSpecificOutput":{...,"permissionDecision":
# "deny",...}} to STDOUT and exit 0. PreToolUse hooks that exit non-zero with JSON on
# stderr (Form B) are silently swallowed — the tool call proceeds. See
# docs/wiki/hook-best-practices.md § "PreToolUse deny: JSON output, not exit 2".

set -uo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-${HOME}/.claude/plugins/coordinator-claude/coordinator}"
BUNDLED_WIKI="${PLUGIN_ROOT}/docs/wiki"

# Safe stdin read — timeout prevents hang on Windows/Git Bash
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Honor escape hatch early
# Inline override: COORDINATOR_OVERRIDE_WIKI_MIRROR=1 prefix in the tool's file_path context
# is not applicable for Write/Edit (unlike Bash). Only env-var override applies here.
if [[ "${COORDINATOR_OVERRIDE_WIKI_MIRROR:-0}" == "1" ]]; then
  exit 0
fi

# Parse file_path from tool input — prefer jq, fall back to sed
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Fast exit: no file_path or path doesn't match dev-wiki prefix
[[ -z "$FILE_PATH" ]] && exit 0

# Normalize: expand ~ and resolve to absolute
FILE_PATH_EXPANDED="${FILE_PATH/#\~/$HOME}"
# On Windows paths may use backslash or forward slash; normalize to forward
FILE_PATH_EXPANDED="${FILE_PATH_EXPANDED//\\//}"

# Check if target is under the dev-side wiki directory
# Both the prefix and the path need to be normalized for comparison
DEV_WIKI_ABS="${HOME}/.claude/docs/wiki"
# Normalize DEV_WIKI_ABS similarly
DEV_WIKI_ABS="${DEV_WIKI_ABS//\\//}"

# Strip trailing slash from prefix for reliable prefix match
DEV_WIKI_NORM="${DEV_WIKI_ABS%/}"

# Check prefix match
if [[ "$FILE_PATH_EXPANDED" != "$DEV_WIKI_NORM/"* ]]; then
  exit 0
fi

# Extract the wiki filename
WIKI_FILENAME="${FILE_PATH_EXPANDED##*/}"

# Check if a bundled copy exists
BUNDLED_PATH="${BUNDLED_WIKI}/${WIKI_FILENAME}"
if [[ ! -f "$BUNDLED_PATH" ]]; then
  # No bundled copy — this is a new project-level wiki or a new plugin-doctrine wiki
  # being created for the first time in the wrong place. Allow but warn.
  # (The sync script will catch it on the next /update-docs run if it ends up
  # being cited from plugin files.)
  exit 0
fi

# Bundled copy exists — this write would re-introduce the dual-tree trap. BLOCK.
REASON="Write-direction trap: ${WIKI_FILENAME} already exists as a plugin-doctrine wiki at ${BUNDLED_PATH}. Writes must go to the bundled path, not the dev-side path (${FILE_PATH_EXPANDED}). Override: set COORDINATOR_OVERRIDE_WIKI_MIRROR=1 only if this is intentionally a separate project-level wiki."

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
  esc="${esc//$'\r'/}"   # strip bare CR — invalid inside a JSON string (Windows path interp)
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
fi

exit 0
