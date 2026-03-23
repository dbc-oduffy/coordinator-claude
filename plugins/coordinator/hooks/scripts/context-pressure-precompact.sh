#!/bin/bash
# PreCompact sentinel + state serialization.
# Output is IGNORED by Claude Code for PreCompact events.
# State is bridged to context via context-pressure-advisory.sh (UserPromptSubmit).
#
# Writes two files:
#   /tmp/compaction-occurred-{SESSION_ID}    — sentinel (triggers advisory)
#   /tmp/compaction-state-{SESSION_ID}.md    — state snapshot (read by advisory)
#
# The sentinel write is critical; the state write is best-effort.
# State file failure must NOT prevent sentinel creation.
#
# Assumption: session_id is UUID format (hex + hyphens, filename-safe).
set -euo pipefail

HOOK_INPUT=$(cat)

# Extract session_id — prefer jq, fall back to grep for environments without it
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)
fi

if [[ -z "$SESSION_ID" ]]; then
  exit 0  # fail-open: no session_id, can't write sentinel
fi

# --- Write sentinel (critical path) ---
touch "/tmp/compaction-occurred-${SESSION_ID}"

# --- Write state snapshot (best-effort, wrapped in subshell) ---
# Per-section budgets prevent any single section from blowing the 100-line cap.
# SESSION_ID maps 1:1 to ~/.claude/tasks/{SESSION_ID}/ directory (verified).
(
  STATE_FILE="/tmp/compaction-state-${SESSION_ID}.md"
  {
    echo "## Tasks"
    TASK_DIR="${HOME}/.claude/tasks/${SESSION_ID}"
    if [[ -d "$TASK_DIR" ]]; then
      for f in "$TASK_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        if command -v jq &>/dev/null; then
          jq -r '"- \(.subject) [\(.status)]"' "$f" 2>/dev/null || true
        else
          # Fallback: extract subject from JSON without jq
          subj=$(sed -n 's/.*"subject"\s*:\s*"\([^"]*\)".*/\1/p' "$f" | head -1)
          stat=$(sed -n 's/.*"status"\s*:\s*"\([^"]*\)".*/\1/p' "$f" | head -1)
          [[ -n "$subj" ]] && echo "- $subj [$stat]"
        fi
      done | head -20
    else
      echo "(no task list for this session)"
    fi

    echo ""
    echo "## Git State"
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
    if [[ -n "$BRANCH" ]]; then
      echo "Branch: $BRANCH"
      echo "Recent commits:"
      git log --oneline -3 2>/dev/null || true
      echo ""
      echo "Modified files:"
      git diff --name-only 2>/dev/null | head -20
      STAGED=$(git diff --staged --name-only 2>/dev/null)
      if [[ -n "$STAGED" ]]; then
        echo "Staged files:"
        echo "$STAGED" | head -10
      fi
    else
      echo "(not a git repository)"
    fi

    echo ""
    echo "## Active Plans"
    # shellcheck disable=SC2086
    ls tasks/*/todo.md 2>/dev/null | head -10 || echo "(none)"

    echo ""
    echo "## Handoffs"
    ls tasks/handoffs/*.md 2>/dev/null | head -5 || echo "(none)"
  } | head -100 > "$STATE_FILE"
) 2>/dev/null || true
