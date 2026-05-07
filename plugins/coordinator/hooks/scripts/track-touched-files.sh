#!/bin/bash
# PostToolUse hook: Track files touched by the current session.
#
# Fires ONLY on Write|Edit|MultiEdit|NotebookEdit tool calls (see hooks.json
# matcher). Records the modified file path into the per-session touch list at
# .git/coordinator-sessions/<session_id>/touched.txt.
#
# Design notes (per Staff Engineer P0-3):
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

# Extract agent_id (snake_case, top-level — subagent fires only).
# Issue A (archive/specs/2026-05-05-issue-a-agent-id-linkage.md): when the firing
# session is a subagent, write the file path to .agents/<agent_id>/touched.txt
# in addition to the session-keyed touched.txt. Top-level EM fires don't have
# agent_id; they skip this block at zero overhead.
AGENT_ID=""
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  _tmp2="${INPUT#*\"agent_id\":\"}"
  AGENT_ID="${_tmp2%%\"*}"
  # Format guard: lowercase hex, 12+ chars (Probe 0.1 captured 17-char hex).
  if [[ ! "$AGENT_ID" =~ ^[a-f0-9]{12,}$ ]]; then
    AGENT_ID=""
  fi
fi

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
  LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
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
      "$SESSION_ID" "$BRANCH" "$$" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "${SESSION_DIR}/meta.json"
  fi
fi

# Ensure touched.txt exists
[[ -f "$TOUCHED_FILE" ]] || touch "$TOUCHED_FILE"

# ---------------------------------------------------------------------------
# Normalize file_path to repo-relative.
# Fast path: skip if already relative (no leading / or drive letter).
# ---------------------------------------------------------------------------
FILE_PATH_NORM="$FILE_PATH"
if [[ "$FILE_PATH" == /* || "$FILE_PATH" == [A-Za-z]:* ]]; then
  REL=$(git ls-files --full-name -- "$FILE_PATH" 2>/dev/null | head -1)
  if [[ -z "$REL" ]]; then
    # Resolve via shared lib so Windows uses pythonw.exe (no console flash).
    LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/resolve-python.sh"
    [[ ! -f "$LIB_PATH" ]] && LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/resolve-python.sh"
    # shellcheck source=/dev/null
    [[ -f "$LIB_PATH" ]] && source "$LIB_PATH"
    if [[ -n "$PYTHON_BIN" ]]; then
      REL=$("$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "import os,sys; print(os.path.relpath(sys.argv[1],sys.argv[2]).replace(os.sep,'/'))" \
            "$FILE_PATH" "$GIT_ROOT" 2>/dev/null) || REL=""
    else
      REL=""
    fi
  fi
  [[ -n "$REL" ]] && FILE_PATH_NORM="$REL"
fi

# ---------------------------------------------------------------------------
# Atomic dedup-append helper.
# Delegates to cs_atomic_dedup_append in lib/coordinator-session.sh.
#
# Spec backlink: plans/safe-commit-fixes.md § Phase 3a
# Prior implementation (mktemp+sort+mv) had a lost-update race under N
# concurrent writers with distinct paths: each writer read-then-overwrote,
# so the last mv silently dropped earlier merges. Replaced with append-only
# writes — see cs_atomic_dedup_append for the full rationale and contract.
#
# lib may already be sourced (warm path: sourced above in the session-init
# block). If not, source it now. If missing entirely, fall back to the
# direct append-only idiom so the hook never blocks tool calls.
# ---------------------------------------------------------------------------
_atomic_dedup_append() {
  local target_file="$1"
  local new_entry="$2"

  # Source lib if cs_atomic_dedup_append is not yet in scope.
  if ! declare -f cs_atomic_dedup_append &>/dev/null; then
    local _lib
    _lib="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
    [[ ! -f "$_lib" ]] && _lib="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh"
    if [[ -f "$_lib" ]]; then
      # shellcheck source=/dev/null
      source "$_lib"
    fi
  fi

  if declare -f cs_atomic_dedup_append &>/dev/null; then
    cs_atomic_dedup_append "$target_file" "$new_entry"
  else
    # Lib missing — inline the append-only fallback (same contract).
    grep -qxF "$new_entry" "$target_file" 2>/dev/null && return 0
    printf '%s\n' "$new_entry" >> "$target_file" 2>/dev/null || true
  fi
  return 0
}

# Session-keyed dedup-append.
_atomic_dedup_append "$TOUCHED_FILE" "$FILE_PATH_NORM"

# Issue A: parallel agent-keyed write (only for subagent fires).
# .agents/<agent_id>/touched.txt provides the agent-id linkage that the
# coordinator-safe-commit helper unions into scope at commit time.
if [[ -n "$AGENT_ID" ]]; then
  AGENT_DIR="${GIT_ROOT}/.git/coordinator-sessions/.agents/${AGENT_ID}"
  AGENT_TOUCHED="${AGENT_DIR}/touched.txt"
  [[ -d "$AGENT_DIR" ]] || mkdir -p "$AGENT_DIR" 2>/dev/null
  [[ -f "$AGENT_TOUCHED" ]] || touch "$AGENT_TOUCHED" 2>/dev/null
  _atomic_dedup_append "$AGENT_TOUCHED" "$FILE_PATH_NORM"
fi

# Note: meta.json last_activity is NOT updated here (costs ~36ms on Windows).
# Activity is updated by cs_touch when called from the commit helper at commit time.

exit 0
