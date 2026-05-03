#!/bin/bash
# SessionStart hook: Initialize the coordinator session directory and write the
# .current-session-id sentinel so coordinator-safe-commit can resolve the
# session_id from a non-hook subprocess (the EM's interactive Bash).
#
# Without this hook, the helper has no path to the session_id:
#   - CLAUDE_SESSION_ID is not exported to the EM's subprocess (Claude Code only
#     puts session_id in hook input JSON).
#   - track-touched-files.sh creates session dirs only on the first Edit/Write,
#     so early-session helper invocations would fail.
#   - The PID-scan fallback is broken because cs_init records $$ (the hook
#     subprocess PID), which is dead by the time the helper runs.
#
# Concurrency note: the sentinel is "last writer wins". When two Claude Code
# sessions run in the same repo, the most recently started session owns the
# sentinel. Other sessions must use CLAUDE_SESSION_ID explicitly. This is
# acceptable — the sentinel is a convenience for the common single-session case;
# the helper's post-filter (touched.txt membership requirement) prevents foreign
# files from being staged even on sentinel collisions.
#
# Input schema (SessionStart):
#   { "session_id": "<id>", "source": "startup|compact|clear", ... }
#
# Always exits 0 — never blocks session start.

# --- Safe stdin read with timeout (mirror existing hook pattern) ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

[[ -z "$INPUT" ]] && exit 0

# --- Extract session_id (prefer jq, fall back to bash string ops) ---
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  if [[ "$INPUT" != *'"session_id"'* ]]; then
    exit 0
  fi
  _tmp="${INPUT#*\"session_id\":\"}"
  SESSION_ID="${_tmp%%\"*}"
fi

[[ -z "$SESSION_ID" ]] && exit 0

# --- Locate git root (skip if not in a repo) ---
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

SESSIONS_DIR="${GIT_ROOT}/.git/coordinator-sessions"
mkdir -p "$SESSIONS_DIR" 2>/dev/null || exit 0

# --- Source the lib and call cs_init for proper session-dir setup ---
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
[[ ! -f "$LIB_PATH" ]] && LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh"

if [[ -f "$LIB_PATH" ]]; then
  # shellcheck source=/dev/null
  source "$LIB_PATH"
  cs_init "$SESSION_ID" 2>/dev/null || true
else
  # Lib missing — minimal session-dir bootstrap (mirror track-touched-files.sh)
  SESSION_DIR="${SESSIONS_DIR}/${SESSION_ID}"
  mkdir -p "$SESSION_DIR" 2>/dev/null || exit 0
  touch "${SESSION_DIR}/touched.txt"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SESSION_DIR}/started_at"
  git rev-parse HEAD 2>/dev/null > "${SESSION_DIR}/head_at_start" || echo "unknown" > "${SESSION_DIR}/head_at_start"
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  printf '{"session_id":"%s","branch":"%s","pid":"%s","last_activity":"%s","goal":""}\n' \
    "$SESSION_ID" "$BRANCH" "$$" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "${SESSION_DIR}/meta.json"
fi

# --- Write the .current-session-id sentinel ---
# This is what coordinator-safe-commit's Priority-2 resolution reads.
echo "$SESSION_ID" > "${SESSIONS_DIR}/.current-session-id"

exit 0
