#!/usr/bin/env bash
# reap-sessions.sh — reap stale session substrate via session.reap.
#
# Purpose: strangler-facade wrapper that routes stale-session cleanup through
# the coordinator_core session op (`session.reap`) on the native path, with the
# cs_reap_stale / cs_reap_agents / cs_reap_stale_claims trio (coordinator-session.sh)
# as the State-1 legacy fallback.  The 12h .last-reap cadence gate is preserved in
# the legacy path; on the native path the op self-gates and self-manages .last-reap.
#
# Usage:
#   reap-sessions.sh [<repo_root>]
#
#   <repo_root>  Optional; defaults to `git rev-parse --show-toplevel`.
#
# Commit semantics:
#   NO git commit on ANY path.  session.reap mutates only .git/coordinator-sessions/
#   (untracked substrate; Class-B op).  No git diff, no git commit.
#
# Transport routing (three-state model from strangler-facade.sh):
#   State 1 (seam absent): legacy cs_reap_* trio with 12h .last-reap cadence gate.
#   State 2 (native OK):   strangle_route_mutation wrapping session.reap op.
#   State 3 (transport err): log-and-continue to stderr; exit 0.
#
# Exit codes:
#   0 — normal completion (including legacy path, transport warn, cadence-gated skip).
#   Reaper MUST NOT block session start; all error paths exit 0.
#
# Negative-spec:
#   - Does NOT commit to git on any path.
#   - Does NOT pass `force` to the op (let the op self-gate cadence).
#   - Does NOT print an integer count to stdout (unlike sweep-terminal-plans.sh;
#     session-init's reaper block does not consume a count).
#   - Does NOT fall back to legacy after a native transport failure (State 3).
#
# Spec backlink: docs/plans/2026-07-06-session-init-op-absorption-repoint.md § C1
# BSD-portable bash>=4; GNU-isms guarded per DR-148.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash>=4 guard — must be reachable on bash 3.2 (plain comparison, no bash-4 syntax)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'reap-sessions.sh: requires bash >= 4 (current: %s)\n' "${BASH_VERSION:-unknown}" >&2
  printf '  macOS: brew install bash\n' >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Plugin root — never hardcoded; survives marketplace-install layout.
# Cold-fallback note (Design pin 4 / P3): session-init-hook shell is cold;
# use direct .doe-root file read, never `machine-local get` CLI.
# ---------------------------------------------------------------------------
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
# shellcheck source=../lib/coordinator-trusted-root-guard.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/coordinator-trusted-root-guard.sh"
if ! coordinator_trusted_root_guard --mode=fail-open --root="$PLUGIN_ROOT" --site="$0"; then
  PLUGIN_ROOT=''
fi
if [[ -z "$PLUGIN_ROOT" ]]; then
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [[ -z "$_doe_root" ]] || [[ ! -d "$_doe_root/coordinator" ]]; then
    printf 'ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install\n' >&2
    exit 1
  fi
  PLUGIN_ROOT="$_doe_root/coordinator"
fi

# ---------------------------------------------------------------------------
# Source strangler facade (also sources cc_invoke transport seam).
# Provides: _sf_seam_present, cc_invoke, strangle_route, strangle_route_mutation.
# ---------------------------------------------------------------------------
_RS_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_RS_SCRIPT_DIR}/../lib/strangler-facade.sh" || {
  printf 'reap-sessions.sh: failed to source strangler-facade.sh\n' >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Repo root — accept as arg or resolve from git.
# ---------------------------------------------------------------------------
_repo_root="${1:-}"
if [[ -z "$_repo_root" ]]; then
  _repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    printf 'reap-sessions.sh: cannot resolve git repo root\n' >&2
    exit 0  # best-effort: never block session start
  }
fi

# ---------------------------------------------------------------------------
# Source coordinator-session.sh for legacy path (cs_reap_* fns).
# ---------------------------------------------------------------------------
_cs_session_lib="${PLUGIN_ROOT}/lib/coordinator-session.sh"
if [[ -f "$_cs_session_lib" ]]; then
  # shellcheck source=../lib/coordinator-session.sh
  source "$_cs_session_lib" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Legacy function — State 1 path.
# Preserves the 12h .last-reap cadence gate that session-init.sh used to own.
# Three guarded reaper calls: cs_reap_stale, cs_reap_agents, cs_reap_stale_claims.
# All three are independently command-v-guarded so a missing fn is a visible no-op.
# ---------------------------------------------------------------------------
_legacy_reap_sessions() {
  if ! command -v cs_reap_stale_claims >/dev/null 2>&1; then
    return 0
  fi

  local _sessions_dir="${_repo_root}/.git/coordinator-sessions"
  local _reap_marker="${_sessions_dir}/.last-reap"
  local _reap_interval=$(( 12 * 3600 ))
  local _reap_now
  _reap_now=$(date +%s 2>/dev/null || echo 0)
  local _reap_last=0

  if [[ -f "$_reap_marker" ]]; then
    # Fallback 0 is intentional: unknown mtime → treat as epoch-0, so the gap
    # always exceeds _reap_interval and the reaper fires ("trigger reap" default).
    # Two-stat fallback chain (GNU stat -c %Y, BSD stat -f %m) — DR-148.
    _reap_last=$(stat -c %Y "$_reap_marker" 2>/dev/null \
      || stat -f %m "$_reap_marker" 2>/dev/null || echo 0)
  fi

  if [[ "$_reap_now" -gt 0 && $(( _reap_now - _reap_last )) -ge "$_reap_interval" ]]; then
    command -v cs_reap_stale        >/dev/null 2>&1 && { cs_reap_stale        >/dev/null 2>&1 || true; }
    command -v cs_reap_agents       >/dev/null 2>&1 && { cs_reap_agents       >/dev/null 2>&1 || true; }
    command -v cs_reap_stale_claims >/dev/null 2>&1 && { cs_reap_stale_claims >/dev/null 2>&1 || true; }   # basename-only handoff + memo + plan claims (DR-110)
    : > "$_reap_marker" 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# Native function — States 2/3.
# Routes session.reap through strangle_route_mutation (NOT bare strangle_route)
# so the op result's .exit_code/.error is honored.
# Non-zero rc: log-and-continue to stderr; exit 0 (best-effort ceremony).
# Does NOT pass `force` — the op self-gates cadence and self-manages .last-reap.
# ---------------------------------------------------------------------------
_native_reap_sessions() {
  local _srm_rc=0
  strangle_route_mutation "session.reap" "_legacy_reap_sessions" '{}' || _srm_rc=$?
  if [[ "${_srm_rc}" -ne 0 ]]; then
    # State 3: transport error (cc_invoke already printed diagnostic to stderr)
    # or State 2: op returned non-zero exit_code (strangle_route_mutation WARNed).
    # Either way: best-effort ceremony; never block session start.
    printf 'reap-sessions.sh: session.reap returned rc=%s — continuing (best-effort)\n' "${_srm_rc}" >&2
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Routing — three-state model.
# _sf_seam_present: returns 0 if coordinator_core.invoke is importable (States 2/3);
#                   returns 1 if seam absent (State 1 legacy path).
# ---------------------------------------------------------------------------
if _sf_seam_present 2>/dev/null; then
  _native_reap_sessions
else
  _legacy_reap_sessions
fi
