#!/bin/bash
# PostToolUse hook: Track files touched by the current session.
#
# Fires ONLY on Write|Edit|MultiEdit|NotebookEdit tool calls (see hooks.json
# matcher). Records the modified file path into the per-session touch list at
# .git/coordinator-sessions/<session_id>/touched.txt.
#
# Design notes (per Patrik P0-3):
#   - Bash tool calls are NOT parsed — mtime fallback at commit time handles
#     Bash-driven edits. Parsing arbitrary shell for write effects is unsound.
#   - Hook matcher in hooks.json already restricts to edit tools. This script
#     has a redundant fast-exit check as defense in depth.
#   - Always exits 0 — advisory hook, never blocks tool calls.
#   - Performance target: p95 < 50ms on Windows + Git Bash over 100 fires.
#     NOTE: On Windows + Git Bash, bash process spawn (~25ms) + git rev-parse
#     (~24ms) + stdin read (~22ms) already sum to ~71ms, making the 50ms target
#     physically unachievable for a stateless bash script. The implementation
#     minimizes all other overhead. Measured p95 is recorded in the commit.
#
# Hot-path design (performance):
#   - Bash string ops (not sed/grep) for JSON field extraction — saves ~34ms.
#   - Skip lib source + cs_init on steady-state (dir already exists) — saves ~50ms.
#   - No meta.json last_activity update in hook — too expensive (~36ms) for
#     advisory bookkeeping. The commit helper updates activity at commit time.
#   - No git ls-files for already-relative paths (the common case from Claude tools).
#   - Use read -r for stdin when possible (faster than cat/timeout on single-line JSON).
#
# Input schema (PostToolUse):
#   {
#     "session_id": "<id>",
#     "tool_name": "Write|Edit|MultiEdit|NotebookEdit",
#     "tool_input": { "file_path": "<path>" }
#   }

# --- Safe stdin read (mirror validate-commit.sh timeout pattern) ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

[[ -z "$INPUT" ]] && exit 0

# ---------------------------------------------------------------------------
# Extract fields using pure bash string operations (no external commands).
# This is ~34ms faster than sed on Windows per extraction.
# Pattern: strip prefix up to and including the key's opening quote+colon+quote,
# then strip suffix from the closing quote onward.
# ---------------------------------------------------------------------------

# Extract tool_name — only if the key is present
if [[ "$INPUT" != *'"tool_name"'* ]]; then
  exit 0
fi
_tmp="${INPUT#*\"tool_name\":\"}"
TOOL_NAME="${_tmp%%\"*}"

# --- Defense-in-depth: fast-exit on non-edit tools ---
case "${TOOL_NAME:-}" in
  Write|Edit|MultiEdit|NotebookEdit) ;;  # proceed
  *) exit 0 ;;
esac

# Extract session_id — only if the key is present in INPUT
if [[ "$INPUT" != *'"session_id"'* ]]; then
  exit 0
fi
_tmp="${INPUT#*\"session_id\":\"}"
SESSION_ID="${_tmp%%\"*}"
[[ -z "$SESSION_ID" ]] && exit 0

# Extract file_path (inside tool_input object)
if [[ "$INPUT" != *'"file_path"'* ]]; then
  exit 0
fi
_tmp="${INPUT#*\"file_path\":\"}"
FILE_PATH="${_tmp%%\"*}"
[[ -z "$FILE_PATH" ]] && exit 0

# ---------------------------------------------------------------------------
# Locate git root (one external call — unavoidable for cross-repo correctness).
# ---------------------------------------------------------------------------
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

SESSION_DIR="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID}"
TOUCHED_FILE="${SESSION_DIR}/touched.txt"

# ---------------------------------------------------------------------------
# Initialize session dir on first touch (slow path — fires once per session).
# ---------------------------------------------------------------------------
if [[ ! -d "$SESSION_DIR" ]]; then
  LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../../lib/coordinator-session.sh"
  [[ ! -f "$LIB_PATH" ]] && LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh"
  if [[ -f "$LIB_PATH" ]]; then
    # shellcheck source=/dev/null
    source "$LIB_PATH"
    cs_init "$SESSION_ID" 2>/dev/null || true
  else
    # lib missing — minimal bootstrap
    mkdir -p "$SESSION_DIR"
    touch "$TOUCHED_FILE"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SESSION_DIR}/started_at"
    git rev-parse HEAD 2>/dev/null > "${SESSION_DIR}/head_at_start" || echo "unknown" > "${SESSION_DIR}/head_at_start"
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    printf '{"session_id":"%s","branch":"%s","pid":"%s","last_activity":"%s","goal":""}\n' \
      "$SESSION_ID" "$BRANCH" "$PPID" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "${SESSION_DIR}/meta.json"
  fi
fi

# Ensure touched.txt exists
[[ -f "$TOUCHED_FILE" ]] || touch "$TOUCHED_FILE"

# ---------------------------------------------------------------------------
# W1.0b: Record live $PPID in meta.json so PPID-walk has a live ancestor.
#
# cs_init writes $$ (the hook subprocess PID) which is dead by the time
# coordinator-safe-commit runs. $PPID here is the Bash-tool shell that spawned
# this hook — a live ancestor that IS on the helper's process chain.
#
# Atomic write: write to a tempfile then mv-rename to avoid partial-read races.
# Uses jq --arg to avoid filter-injection (unlike the pre-existing
# ".${field}" patterns in coordinator-session.sh:104,119 slated for W6).
# Falls back to sed if jq is unavailable.
# ---------------------------------------------------------------------------
_META_JSON="${SESSION_DIR}/meta.json"
if [[ -f "$_META_JSON" ]]; then
  _LIVE_PID="$PPID"
  _META_TMP="${_META_JSON}.pid.$$"
  if command -v jq &>/dev/null; then
    if jq --arg p "$_LIVE_PID" '.pid = $p' "$_META_JSON" > "$_META_TMP" 2>/dev/null; then
      mv -f "$_META_TMP" "$_META_JSON" 2>/dev/null || rm -f "$_META_TMP"
    else
      rm -f "$_META_TMP"
    fi
  else
    # sed fallback — replaces the first "pid" string value in meta.json
    sed "s/\"pid\"[[:space:]]*:[[:space:]]*\"[^\"]*\"/\"pid\": \"${_LIVE_PID}\"/" \
      "$_META_JSON" > "$_META_TMP" 2>/dev/null \
      && mv -f "$_META_TMP" "$_META_JSON" 2>/dev/null \
      || rm -f "$_META_TMP"
  fi
fi

# ---------------------------------------------------------------------------
# Normalize file_path to repo-relative.
# Fast path: skip if already relative (no leading / or drive letter).
# ---------------------------------------------------------------------------
FILE_PATH_NORM="$FILE_PATH"
if [[ "$FILE_PATH" == /* || "$FILE_PATH" == [A-Za-z]:* ]]; then
  REL=$(git ls-files --full-name -- "$FILE_PATH" 2>/dev/null | head -1)
  if [[ -z "$REL" ]]; then
    REL=$(python3 -c "import os,sys; print(os.path.relpath(sys.argv[1],sys.argv[2]).replace(os.sep,'/'))" \
          "$FILE_PATH" "$GIT_ROOT" 2>/dev/null) \
      || REL=$(python -c "import os,sys; print(os.path.relpath(sys.argv[1],sys.argv[2]).replace(os.sep,'/'))" \
          "$FILE_PATH" "$GIT_ROOT" 2>/dev/null) \
      || REL=""
  fi
  [[ -n "$REL" ]] && FILE_PATH_NORM="$REL"
fi

# ---------------------------------------------------------------------------
# Dedup append: only write if not already in touched.txt.
# grep -qxF: O(n) on file size, fast for typical small lists.
# ---------------------------------------------------------------------------
if grep -qxF "$FILE_PATH_NORM" "$TOUCHED_FILE" 2>/dev/null; then
  exit 0
fi

echo "$FILE_PATH_NORM" >> "$TOUCHED_FILE"

# Note: meta.json last_activity is NOT updated here (costs ~36ms on Windows).
# Activity is updated by cs_touch when called from the commit helper at commit time.

exit 0
