#!/usr/bin/env bash
# PostToolUse hook: Track files touched by the current session.
#
# Fires ONLY on Write|Edit|MultiEdit|NotebookEdit tool calls (see hooks.json
# matcher). Records the modified file path into the per-session touch list at
# .git/coordinator-sessions/<session_id>/touched.txt.
#
# Design notes (per the Staff Engineer P0-3):
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

# Extract raw agent_id (snake_case, top-level — subagent fires only).
# Resolution to canonical EM-side id via resolve_subagent_identity() happens
# after the session-init block (warm path: lib may already be sourced there).
# Supports unnamed hex agents AND named teammate agents (a<name>-<16hex> shape).
# Spec: archive/specs/2026-05/2026-05-05-issue-a-agent-id-linkage.md
#   C10 fix: docs/plans/2026-06-30-loe-dispatch-undercount-teammate-shape.md § C10
_raw_agent_id=""
if [[ "$INPUT" == *'"agent_id"'* ]]; then
  _tmp2="${INPUT#*\"agent_id\":\"}"
  _raw_agent_id="${_tmp2%%\"*}"
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

# ---------------------------------------------------------------------------
# Resolve coordinator root for lib fallbacks (coordinator-session.sh, resolve-python.sh).
# Soft-degrade: hook must always exit 0 — if root unresolvable, _cc_root is
# set empty and downstream [[ -f ]] guards degrade gracefully without blocking.
# ---------------------------------------------------------------------------
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""

# --- Source advisory-flatten-call helper (example-orchestration-hub --advisory wiring) ---
# Spec backlink: cross-repo/inbox/2026-07-05-strang-05-advisory-hook-wiring-spec.md
_AFC="${_cc_root:+$_cc_root/hooks/scripts/lib/advisory-flatten-call.sh}"
[ -n "$_AFC" ] && [ -f "$_AFC" ] && . "$_AFC"

SESSION_DIR="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID}"
TOUCHED_FILE="${SESSION_DIR}/touched.txt"

# ---------------------------------------------------------------------------
# Initialize session dir on first touch (slow path — fires once per session).
# ---------------------------------------------------------------------------
if [[ ! -d "$SESSION_DIR" ]]; then
  LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
  [[ ! -f "$LIB_PATH" ]] && LIB_PATH="${_cc_root}/lib/coordinator-session.sh"
  if [[ -f "$LIB_PATH" ]]; then
    # shellcheck source=/dev/null
    source "$LIB_PATH"
    cs_init "$SESSION_ID" 2>/dev/null || true
  else
    # lib missing — minimal bootstrap
    mkdir -p "$SESSION_DIR"
    touch "$TOUCHED_FILE"
    [[ ! -f "${SESSION_DIR}/started_at" ]] && date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SESSION_DIR}/started_at"
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
    [[ ! -f "$LIB_PATH" ]] && LIB_PATH="${_cc_root}/lib/resolve-python.sh"
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
    [[ ! -f "$_lib" ]] && _lib="${_cc_root}/lib/coordinator-session.sh"
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

# Issue A + C10: parallel agent-keyed write (only for subagent fires).
# .agents/<canonical-id>/touched.txt is what coordinator-safe-commit unions into
# commit scope via cs_compute_scope. resolve_subagent_identity() maps both
# bare-hex unnamed agents AND a<name>-<16hex> named teammates to the canonical
# EM-side id the writer recorded. Empty resolver result → skip (zero-overhead
# path for top-level EM writes that carry no agent_id). Session-keyed write above
# is UNTOUCHED by this block.
# Warm path: lib may be sourced already from session-init above;
# declare -f guard avoids double-source on the hot path.
AGENT_ID=""
if [[ -n "$_raw_agent_id" ]]; then
  if ! declare -f resolve_subagent_identity &>/dev/null; then
    _resolver_lib="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
    [[ ! -f "$_resolver_lib" ]] && _resolver_lib="${_cc_root}/lib/coordinator-session.sh"
    # shellcheck source=/dev/null
    [[ -f "$_resolver_lib" ]] && source "$_resolver_lib"
  fi
  # Review: code-reviewer — F1: guard resolver call identical to other consumers
  # (block-subagent:130, em-check:112, advisory:99); bare-hex fallback preserves
  # unnamed-agent keyed-write in the lib-missing path (regression vs pre-C10 path).
  if declare -f resolve_subagent_identity &>/dev/null; then
    AGENT_ID="$(resolve_subagent_identity "$_raw_agent_id" "$SESSION_ID")"
  elif [[ "$_raw_agent_id" =~ ^[a-f0-9]{12,}$ ]]; then
    AGENT_ID="$_raw_agent_id"
  fi
fi
if [[ -n "$AGENT_ID" ]]; then
  AGENT_DIR="${GIT_ROOT}/.git/coordinator-sessions/.agents/${AGENT_ID}"
  AGENT_TOUCHED="${AGENT_DIR}/touched.txt"
  [[ -d "$AGENT_DIR" ]] || mkdir -p "$AGENT_DIR" 2>/dev/null
  [[ -f "$AGENT_TOUCHED" ]] || touch "$AGENT_TOUCHED" 2>/dev/null
  _atomic_dedup_append "$AGENT_TOUCHED" "$FILE_PATH_NORM"
fi

# Note: meta.json last_activity is NOT updated here (costs ~36ms on Windows).
# Activity is updated by cs_touch when called from the commit helper at commit time.

# --- example-orchestration-hub --advisory fire-and-forget (Class A bookkeeping) ---
# ASYNC-DETACHED by design: this is a hot, highly-concurrent hook (fires on every
# file edit). A SYNCHRONOUS advisory_call — a timeout-bounded subprocess — added load
# across parallel invocations that widened the (documented, benign) grep→append race in
# cs_atomic_dedup_append, regressing test T22. It also blocked every edit-hook on a
# network round-trip. Fire-and-forget belongs off the critical path: run detached AFTER
# the local (authoritative) appends, so the hook returns immediately and no example-orchestration-hub spawn
# overlaps a concurrent append. disown removes job from job table; background process completes independently.
if declare -f advisory_flatten_params >/dev/null 2>&1 && declare -f advisory_call >/dev/null 2>&1; then
  # Review: code-reviewer F6 — disown removes job from job table; the background process completes independently.
  # Review: code-reviewer F2 — flatten moved inside subshell (matches session-heartbeat.sh shape); was running
  #         synchronously on the hot path before the fork, adding per-edit jq subprocess overhead.
  (
    _PARAMS="$(printf '%s' "$INPUT" | advisory_flatten_params 2>/dev/null || echo '{}')"
    advisory_call "hooks.track_touched_files" "$_PARAMS" >/dev/null 2>&1 || true
  ) &
  disown 2>/dev/null || true
fi

exit 0
