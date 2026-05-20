#!/bin/bash
# PreToolUse hook: Blocks Write creating a new file in tasks/handoffs/ or
# tasks/spinoffs/ unless one of the legitimate authoring skills is active.
#
# Motivation: EMs reflexively reach for /handoff at perceived "tidy stopping
# points" and reach for /spinoff for cross-repo messages — both contrary to
# doctrine. This tripwire enforces the gate at the tool boundary.
#
# Allowed without authorization:
#   - Edits to handoffs/spinoffs that already exist on disk (covers /pickup
#     frontmatter mutation, Step-2.10 review-marker writes, body amendments).
#   - Writes anywhere outside tasks/handoffs/ and tasks/spinoffs/.
#
# Authorization signals (any one allows the new-file Write):
#   - COORDINATOR_HANDOFF_AUTHORIZED=1 in env (manual override).
#   - Recent transcript contains an invocation of /handoff, /session-end, or
#     /spinoff (tail-scan of last ~500 lines via transcript_path).
#
# Blocked: new-file Write into tasks/handoffs/ or tasks/spinoffs/ with no
# detectable skill context. Block message names the four legit triggers and
# the cross-repo primitive (copy-paste in chat / archive/cross-repo/ link).
#
# Override: set COORDINATOR_HANDOFF_AUTHORIZED=1 before the Write only if you
# are deliberately authoring outside the three skills (rare).
#
# Input schema (PreToolUse for Write):
#   { "tool_name": "Write", "tool_input": { "file_path": "..." },
#     "transcript_path": "...", ... }
#
# Deny mechanism: exit non-zero with JSON {"decision":"block","reason":"..."} on stderr.

set -uo pipefail

# Safe stdin read — timeout prevents hang on Windows/Git Bash
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Honor escape hatch early
if [[ "${COORDINATOR_HANDOFF_AUTHORIZED:-0}" == "1" ]]; then
  exit 0
fi

# Parse fields from tool input — prefer jq, fall back to sed
if command -v jq &>/dev/null; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
  TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TRANSCRIPT_PATH=$(echo "$INPUT" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TOOL_NAME=$(echo "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

# Only Write creates files; Edit and NotebookEdit require pre-existing files.
[[ "$TOOL_NAME" != "Write" ]] && exit 0
[[ -z "$FILE_PATH" ]] && exit 0

# Normalize path
FILE_PATH_NORM="${FILE_PATH//\\//}"

# Only fire on tasks/handoffs/ and tasks/spinoffs/ paths
case "$FILE_PATH_NORM" in
  */tasks/handoffs/*|*/tasks/spinoffs/*|tasks/handoffs/*|tasks/spinoffs/*)
    ;;
  *)
    exit 0
    ;;
esac

# Edits to existing handoffs are always allowed (covers /pickup mutation,
# review-marker writes, body amendments)
if [[ -f "$FILE_PATH_NORM" ]]; then
  exit 0
fi

# New file creation — check for skill-activation signal in recent transcript
if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
  # Tail last ~500 lines and grep for skill activation patterns. Matches:
  #   - User-typed slash invocations: /handoff, /session-end, /spinoff
  #   - Skill-tool invocations: Skill(coordinator:handoff), etc.
  #   - command-name tags: <command-name>handoff</command-name>
  if tail -500 "$TRANSCRIPT_PATH" 2>/dev/null | grep -qE '(^|[^a-z])/(handoff|session-end|spinoff)([^a-z]|$)|coordinator:(handoff|session-end|spinoff)|<command-name>(handoff|session-end|spinoff)</command-name>'; then
    exit 0
  fi
fi

# Unauthorized — block with full message
TARGET_DIR=$(echo "$FILE_PATH_NORM" | grep -oE 'tasks/(handoffs|spinoffs)' | head -1)
REASON=$(cat <<'EOF'
Blocked: creating a new file in tasks/handoffs/ or tasks/spinoffs/ requires an active authoring skill.

Handoffs and spinoffs are PM-gated artifacts, not engineering ceremonies. The four legitimate triggers:

  1. /handoff — context pressure forced a mid-workstream save (NOT a tidy stopping point)
  2. /session-end — lessons/state capture for next session
  3. /spinoff — PM-authorized fork of a different mid-session topic (requires explicit PM yes)
  4. /pickup — mutates existing files in place, never creates new ones

If you reached for this because the work feels "done" or "tidy here":
  -> commit and stop, or run /workday-complete

If you are trying to communicate with another repo's EM:
  -> Default: copy-paste the message into chat for the PM to relay.
  -> Large/complex brief: write it to archive/cross-repo/YYYY-MM-DD-<topic>.md and
     hand the PM the link. The PM is the relay between repos.
  -> Do NOT seed tasks/handoffs/ as a queue for the other repo to drain — that
     surface belongs to this repo's session continuity, not cross-repo messaging.

Override (only if you are inside /handoff, /session-end, or /spinoff and the
transcript-detection missed it — e.g. a long autonomous run where the skill
invocation aged past the 500-line tail scan): set
COORDINATOR_HANDOFF_AUTHORIZED=1.
EOF
)

REASON_JSON=$(printf '%s' "$REASON" | python -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null \
  || printf '"%s"' "$(printf '%s' "$REASON" | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/' | tr -d '\n')")

printf '{"decision":"block","reason":%s}\n' "$REASON_JSON" >&2
exit 1
