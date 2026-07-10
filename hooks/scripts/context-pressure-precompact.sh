#!/usr/bin/env bash
# PreCompact sentinel + state serialization.
# Output is IGNORED by Claude Code for PreCompact events.
# State is bridged to context via context-pressure-advisory.sh (PostToolUse).
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

# Safe stdin read — timeout prevents hang if pipe isn't closed (Windows/Git Bash)
if command -v timeout &>/dev/null; then
  HOOK_INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  HOOK_INPUT=$(cat)
fi

# Extract session_id + transcript_path — prefer jq, fall back to grep
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)
else
  # BSD sed treats \s as literal 's' (DR-148 portability audit, 2026-07-10) —
  # [[:space:]] is portable.
  SESSION_ID=$(echo "$HOOK_INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

if [[ -z "$SESSION_ID" ]]; then
  exit 0  # fail-open: no session_id, can't write sentinel
fi

# Security: reject ids containing path-traversal characters (notably '/' and '..')
# before any path construction. Canonical charset: [A-Za-z0-9_@-]. An id with
# '/' or '..' could escape /tmp via path concatenation in the sentinel and
# state-file writes below. Treat as absent — the [[ -z ]] guard above returns 0
# (silent no-op), same behaviour as the missing-session_id path.
if [[ ! "$SESSION_ID" =~ ^[A-Za-z0-9_@-]+$ ]]; then
  exit 0
fi

# --- Write sentinel (critical path) ---
# Sentinel content is the pre-compaction transcript size in bytes (or empty if
# unknown). Advisory hook reads this and compares against post-compaction size
# to suppress false-positive emissions when Claude Code fires PreCompact without
# a meaningful context shrink (e.g., subagent-result integration on 1M models).
PRE_SIZE=""
if [[ -n "$TRANSCRIPT_PATH" && -f "$TRANSCRIPT_PATH" ]]; then
  PRE_SIZE=$(stat -c '%s' "$TRANSCRIPT_PATH" 2>/dev/null || stat -f '%z' "$TRANSCRIPT_PATH" 2>/dev/null || true)
  PRE_SIZE="${PRE_SIZE//$'\r'/}"
fi
echo "${PRE_SIZE}" > "/tmp/compaction-occurred-${SESSION_ID}" || \
  echo "[precompact] sentinel write failed; advisory may be missed" >&2

# Source state-root seam (best-effort; inherited by the subshell below).
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4/AC4
_csr_lib_cpa="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-state-root.sh"
[[ -f "$_csr_lib_cpa" ]] && source "$_csr_lib_cpa" 2>/dev/null || true

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
          # Fallback: extract subject from JSON without jq. BSD sed treats \s as
          # literal 's' (DR-148 portability audit, 2026-07-10) — [[:space:]] is portable.
          subj=$(sed -n 's/.*"subject"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$f" | head -1)
          stat=$(sed -n 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$f" | head -1)
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
    GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
    # Resolve per-repo state root via seam; fall back to GIT_ROOT/state if seam unavailable.
    # Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4/AC4
    if declare -f coordinator_state_root >/dev/null 2>&1; then
      _STATE_ROOT_CPA="$(coordinator_state_root 2>/dev/null)" || _STATE_ROOT_CPA="${GIT_ROOT}/state"
    else
      _STATE_ROOT_CPA="${GIT_ROOT}/state"
    fi
    # shellcheck disable=SC2086
    ls "${GIT_ROOT}/tasks/"*/todo.md 2>/dev/null | head -10 || echo "(none)"

    echo ""
    echo "## Handoffs"
    ls "${_STATE_ROOT_CPA}/handoffs/"*.md 2>/dev/null | head -5 || echo "(none)"
  } | head -100 > "$STATE_FILE"
) 2>/dev/null || true
