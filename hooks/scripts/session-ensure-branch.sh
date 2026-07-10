#!/usr/bin/env bash
# SessionStart hook: cut work/{machine}/{today} when the session opens on main,
# detached HEAD, or a zero-ahead non-span branch.
#
# Purpose: automatically moves the EM onto a valid workstream branch at session
# open — no ceremony required, no nag asking the EM to "please run /workday-start".
# Silent no-op when already on a valid work/* span branch.
#
# nag→action pattern — REFERENCE EXEMPLAR:
#   This hook is the "A" in "A built as template for B" (strang-04). It converts
#   the block-off-daily-branch nag into an active-behavior DO hook. Every subsequent
#   nag→action conversion (strang-06 and beyond) copies this shape:
#     1. Source the shared ensure-lib from lib/.
#     2. Gate to startup/clear events only (not compact).
#     3. Call the ensure function; let it cut and push.
#     4. Emit a one-line heads-up on FRESH-CUT; silent on no-op.
#     5. Never deny, never block, always exit 0.
#   See docs/wiki/hook-best-practices.md § nag→action for the pattern this establishes.
#   strang-06 copies this shape for the next batch of nag→action conversions.
#
# DO hook — not a gate:
#   This hook MUST NOT emit a deny or block. It moves the EM silently or with a
#   single heads-up line. A deny here would stop the session, violating the
#   active-behavior guarantee.
#
# Event gate: startup and clear only. compact is excluded — the EM is already on a
# branch during compaction; re-cutting would be wrong and disruptive.
#
# Soft seam — example-orchestration-hub action layer:
#   The B-half (example-orchestration-hub-native session.ensure_branch op) is a future migration gated
#   on the example-orchestration-hub action layer (pcore-06/10). When that lands, this hook becomes the
#   legacy fallback wrapped by the DR-210 strangler facade. Keep logic clean to wrap.
#
# Always exits 0 — never blocks session start.
# Output (raw text) becomes additionalContext injected into the session.
#
# Spec backlink: state/handoffs/2026-07-04_220004_roadmap-strang-04.md § Phase 2

# --- Read stdin; extract source field ---
# Mirror session-init.sh stdin read pattern (timeout-guarded, jq-preferred).
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# --- Gate: startup and clear only; exit 0 silently on compact or unknown ---
EVENT_SOURCE=""
if [[ -n "$INPUT" ]]; then
  if command -v jq >/dev/null 2>&1; then
    EVENT_SOURCE=$(printf '%s' "$INPUT" | jq -r '.source // empty' 2>/dev/null || true)
  else
    if [[ "$INPUT" == *'"source"'* ]]; then
      _tmp="${INPUT#*\"source\":\"}"
      EVENT_SOURCE="${_tmp%%\"*}"
    fi
  fi
fi

case "$EVENT_SOURCE" in
  startup|clear) : ;;  # proceed
  *)             exit 0 ;;  # compact or unknown — silent no-op
esac

# --- Locate git root (skip if not in a repo) ---
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

# --- Resolve plugin root (BASH_SOURCE-relative primary; CLAUDE_PLUGIN_ROOT fallback) ---
_HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${_HOOK_DIR}/../.." && pwd)"
# Paranoia: if the cd-walk produced something that doesn't look like a plugin root, fall back.
if [[ ! -d "${PLUGIN_ROOT}/lib" ]]; then
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
  # shellcheck source=/dev/null
  source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
  if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
    coordinator_trusted_root_guard --mode=fail-open --root="$PLUGIN_ROOT" --site="$0" || PLUGIN_ROOT=''
  else
    PLUGIN_ROOT=''
  fi
  [[ -z "$PLUGIN_ROOT" || ! -d "${PLUGIN_ROOT}/lib" ]] && exit 0
fi

# --- Source libs (coordinator-daily-branch, coordinator-daily-day, session-ensure-branch) ---
#
# Loading order matters: session-ensure-branch.sh itself sources coordinator-daily-branch.sh,
# so sourcing coordinator-daily-branch.sh first (and coordinator-daily-day.sh second) ensures
# the full symbol set is available before cs_session_ensure_branch is defined.

_LIB_DAILY_BRANCH="${PLUGIN_ROOT}/lib/coordinator-daily-branch.sh"
if [[ ! -f "$_LIB_DAILY_BRANCH" ]]; then
  echo "[coordinator] session-ensure-branch: lib coordinator-daily-branch.sh not found — skipped." >&2
  exit 0
fi
# shellcheck source=/dev/null
source "$_LIB_DAILY_BRANCH"

_LIB_DAILY_DAY="${PLUGIN_ROOT}/lib/coordinator-daily-day.sh"
if [[ ! -f "$_LIB_DAILY_DAY" ]]; then
  echo "[coordinator] session-ensure-branch: lib coordinator-daily-day.sh not found — skipped." >&2
  exit 0
fi
# shellcheck source=/dev/null
source "$_LIB_DAILY_DAY"

_LIB_ENSURE="${PLUGIN_ROOT}/lib/session-ensure-branch.sh"
if [[ ! -f "$_LIB_ENSURE" ]]; then
  echo "[coordinator] session-ensure-branch: lib session-ensure-branch.sh not found — skipped." >&2
  exit 0
fi
# shellcheck source=/dev/null
source "$_LIB_ENSURE"

# --- Compute inputs (same derivation as workday-start-step0.sh) ---
MACHINE=$(cs_compute_machine)
TODAY=$(coordinator_local_day)
CURRENT=$(git -C "$GIT_ROOT" branch --show-current 2>/dev/null || echo "")
HEAD_DETACHED=$(git -C "$GIT_ROOT" symbolic-ref -q HEAD >/dev/null 2>&1 && echo "no" || echo "yes")
COMMITS_AHEAD=0
if [[ -n "$CURRENT" && "$CURRENT" != "main" ]]; then
  COMMITS_AHEAD=$(git -C "$GIT_ROOT" rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
fi

# --- Pin cwd to git root so cs_session_ensure_branch's bare git calls land correctly ---
# The function uses `git checkout -b` and `git push` without -C; cwd must be the repo root.
# This is the last side-effect we need cwd for, so a plain cd is safe here.
cd "$GIT_ROOT" || exit 0

# --- Call the shared gate (may cut + push; sets _CS_ENSURE_RESULT and _CS_ENSURE_NEW_BRANCH) ---
_CS_ENSURE_RESULT=""
_CS_ENSURE_NEW_BRANCH=""
if ! cs_session_ensure_branch "$MACHINE" "$TODAY" "$CURRENT" "$HEAD_DETACHED" "$COMMITS_AHEAD"; then
  echo "[coordinator] session-ensure-branch: suffix collision — could not find unused branch suffix; session continuing on ${CURRENT:-detached HEAD}." >&2
  exit 0
fi

# --- Emit heads-up on FRESH-CUT; silent on no-op ---
if [[ "${_CS_ENSURE_RESULT:-}" == "FRESH-CUT" ]]; then
  echo "[coordinator] Branch cut: now on ${_CS_ENSURE_NEW_BRANCH} (was on ${CURRENT:-detached HEAD})."
fi

exit 0
