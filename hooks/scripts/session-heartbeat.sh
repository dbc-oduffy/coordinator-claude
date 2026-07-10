#!/usr/bin/env bash
# Pre+PostToolUse:Bash hook: Write a last_activity heartbeat to the current
# session's meta.json so the orphan sweep in session-init.sh and the claim layer
# (_cs_is_session_live) can distinguish a live long-running session (e.g. a
# multi-minute Bash extraction) from a truly dead session that was never cleaned
# up.
#
# Registered on BOTH PreToolUse:Bash and PostToolUse:Bash (hooks.json). The
# PreToolUse leg stamps recency at the START of a Bash call; the PostToolUse leg
# stamps it again at COMPLETION. This closes the F0 staleness hole (the Staff Engineer,
# 2026-06-23): a single Bash command longer than the 30-min liveness window (a UE
# build, a large extraction) would otherwise freeze last_activity at its start
# time and cross the liveness threshold mid-command, making a genuinely-live
# session's claim wrongly takeable/reapable. With both legs, recency is stamped at
# both ends of every command, so only a session idle >30 min BETWEEN commands ages
# out. The two legs are idempotent — same throttle bucket, same write — so the
# PostToolUse leg is a no-op when the PreToolUse leg already wrote within 60s.
# Spec: state/handoffs/2026-06-23_233740_claim-liveness-hardening-r2.md (F0 option 1).
#
# Problem context (spec backlink: docs/plans/2026-05-17-ws2-channel-a-narrow-activation.md § Chunk 7):
#   session-init.sh's orphan sweep gates archival on kill -0 <pid> where pid
#   is the hook subshell PID from cs_init — dead seconds after session open.
#   All sessions therefore look dead to the PID check. The sweep's only real
#   guard is then the "consumed" frontmatter status. A session that is still
#   running a long Bash command will not have updated last_activity unless a
#   heartbeat fires. This hook is the heartbeat producer; session-init.sh is
#   the consumer (checks last_activity recency before archiving).
#
# Throttle: mtime-check on meta.json. If meta.json was modified within the
#   last 60 seconds, skip the write. This prevents hot-loop writes on rapid
#   tool sequences while ensuring at least one write per 60s during any
#   continuous Bash activity. Chosen over flock: mtime-check is a single stat(1)
#   call (~2ms on Windows) and avoids the fd-leak risk of lock files. A missed
#   heartbeat window (two writes colliding in the same 60s bucket) only extends
#   staleness by one bucket — well within the 10-minute sweep threshold.
#
# Input schema (Pre+PostToolUse both carry session_id; PostToolUse adds
#   tool_response, which this hook ignores — it only reads session_id):
#   { "session_id": "<id>", "tool_name": "<name>", ... }
#
# Matchers: Bash on both PreToolUse and PostToolUse (in hooks.json — long-running
#   commands are the primary risk surface; Write/Edit already update last_activity
#   via cs_touch_file). The producer is direction-agnostic: it stamps last_activity
#   from session_id regardless of which leg fired.
#
# Always exits 0 — advisory hook, never blocks tool calls.

# --- Safe stdin read (mirror validate-commit.sh timeout pattern) ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

[[ -z "$INPUT" ]] && exit 0

# --- Extract session_id using pure bash string ops (no external commands) ---
if [[ "$INPUT" != *'"session_id"'* ]]; then
  exit 0
fi
_tmp="${INPUT#*\"session_id\":\"}"
SESSION_ID="${_tmp%%\"*}"
[[ -z "$SESSION_ID" ]] && exit 0

# --- Locate meta.json via git root ---
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

META_JSON="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID}/meta.json"
[[ ! -f "$META_JSON" ]] && exit 0

# --- Throttle: skip if meta.json was touched within the last 60 seconds ---
# _cs_mtime_epoch equivalent inline (avoids sourcing the lib on the hot path).
NOW_EPOCH=$(date +%s 2>/dev/null || echo 0)
if [[ "$OSTYPE" == darwin* ]]; then
  META_MTIME=$(stat -f %m "$META_JSON" 2>/dev/null || echo 0)
else
  META_MTIME=$(stat -c %Y "$META_JSON" 2>/dev/null || echo 0)
fi

THROTTLE_SECONDS=60
if [[ $(( NOW_EPOCH - META_MTIME )) -lt $THROTTLE_SECONDS ]]; then
  exit 0  # recently updated — skip
fi

# Resolve coordinator root once for library fallback lookups (soft-degrade: _cc_root=""
# on .doe-root miss — hook always exits 0, never hard-fails on missing libs).
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""

# --- ExampleOrchestrationHub advisory helper source (soft-degrade: no-op if missing) ---
_AFC="${_cc_root:+$_cc_root/hooks/scripts/lib/advisory-flatten-call.sh}"
[ -n "$_AFC" ] && [ -f "$_AFC" ] && . "$_AFC"

# --- Write last_activity heartbeat (source lib for _cs_update_meta_field) ---
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
[[ ! -f "$LIB_PATH" && -n "$_cc_root" ]] && LIB_PATH="${_cc_root}/lib/coordinator-session.sh"

if [[ -f "$LIB_PATH" ]]; then
  # shellcheck source=/dev/null
  source "$LIB_PATH"
  NOW_ISO=$(_cs_now_iso)
  _cs_update_meta_field "$(dirname "$META_JSON")" "last_activity" "$NOW_ISO" 2>/dev/null || true
else
  # Lib missing — inline ISO timestamp + sed update (fallback, no flock needed:
  # a concurrent heartbeat from a sibling write is idempotent at 1s resolution).
  NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
  _sed_escaped=$(printf '%s' "$NOW_ISO" | sed 's/[&/\\]/\\&/g')
  _tmp=$(mktemp)
  trap 'rm -f "$_tmp"' EXIT
  sed "s/\"last_activity\"[[:space:]]*:[[:space:]]*\"[^\"]*\"/\"last_activity\": \"${_sed_escaped}\"/" \
    "$META_JSON" > "$_tmp" 2>/dev/null && \
    mv "$_tmp" "$META_JSON" || rm -f "$_tmp"
fi

# async-detached fire-and-forget: off the hook's critical path; local bookkeeping above is authoritative.
if declare -f advisory_flatten_params >/dev/null 2>&1 && declare -f advisory_call >/dev/null 2>&1; then
  (
    _P="$(printf '%s' "$INPUT" | advisory_flatten_params 2>/dev/null || echo '{}')"
    advisory_call "hooks.session_heartbeat" "$_P" >/dev/null 2>&1 || true
  ) &
  disown 2>/dev/null || true
fi

exit 0
