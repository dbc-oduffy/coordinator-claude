#!/usr/bin/env bash
# prune-closed-bugs.sh — archive closed bug-backlog entries via fleet.prune_closed_bugs.
#
# Purpose: daily ceremony wrapper — selects state/bug-backlog/*.yaml entries with
#   status: closed and archives them via coordinator_core fleet.prune_closed_bugs
#   (the op owns the git-mv + self-commit). Best-effort: errors are logged and the
#   script always exits 0 so it never hard-gates /workday-complete.
#
# Legacy path (_prune_noop): no DoE-local prune mechanism existed before this script —
#   there was no per-entry closed-bug archival in the pre-fleet era. State 1
#   (coordinator_core.invoke absent on disk) silently succeeds with a logged notice.
#
# Selection predicate: status: closed ONLY — verified against
#   coordinator/docs/wiki/bug-backlog-schema.md § Status enum
#   ({open, closed, deferred} + wontfix). wontfix and deferred are NOT pruned by
#   this script; they have distinct lifecycle semantics and are retained.
#
# Usage:
#   prune-closed-bugs.sh [--dry-run]
#
#   --dry-run  pass dry_run:true to the fleet op (candidates returned, no git-mv).
#
# Exit codes:
#   0 — always (best-effort; errors logged to stderr, never propagated to caller)
#
# Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § KD-4 / AC6
# DR-215: fleet ceremony wiring — DoE consumer of coordinator_core fleet.prune_closed_bugs.
# BSD-portable bash>=4; GNU-isms guarded per DR-148.

set -euo pipefail  # Review: code-reviewer — nit: moved before bash-4 guard + added -e to match sibling script order

# ---------------------------------------------------------------------------
# bash>=4 guard — must be reachable on bash 3.2 (plain comparison, no bash-4 syntax)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "prune-closed-bugs.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 0  # best-effort: never block caller
fi

# ---------------------------------------------------------------------------
# Plugin root — never hardcoded; survives marketplace-install layout
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
    echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2
    exit 0  # best-effort: never block caller
  fi
  PLUGIN_ROOT="$_doe_root/coordinator"
fi

# ---------------------------------------------------------------------------
# DR-215 facade router — source shared helper (strangler-facade.sh sources
# coordinator-core-invoke.sh internally; both available before strangle_route call).
# ---------------------------------------------------------------------------
_PRUNE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_PRUNE_SCRIPT_DIR}/../lib/strangler-facade.sh" || {
  echo "prune-closed-bugs.sh: WARN: cannot source strangler-facade.sh (non-blocking)" >&2
  exit 0
}

# ---------------------------------------------------------------------------
# Source the state-root seam for portable state/ resolution
# ---------------------------------------------------------------------------
_CSR_LIB_DIR="${PLUGIN_ROOT}/lib"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh" || {
  echo "prune-closed-bugs.sh: WARN: cannot source coordinator-state-root.sh (non-blocking)" >&2
  exit 0
}

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
_dry_run=false
for _arg in "$@"; do
  case "$_arg" in
    --dry-run) _dry_run=true ;;
    *) echo "prune-closed-bugs.sh: unknown arg: $_arg" >&2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve state root and bug-backlog directory
# ---------------------------------------------------------------------------
_pcb_state_root="$(coordinator_state_root 2>/dev/null)" || {
  echo "prune-closed-bugs.sh: WARN: cannot resolve state root (non-blocking)" >&2
  exit 0
}
_bug_dir="${_pcb_state_root}/bug-backlog"
_repo_root="${_pcb_state_root%/state}"

if [[ ! -d "$_bug_dir" ]]; then
  echo "prune-closed-bugs.sh: no bug-backlog directory at ${_bug_dir} — nothing to prune"
  exit 0
fi

# ---------------------------------------------------------------------------
# Legacy path — no DoE-local prune mechanism prior to fleet.prune_closed_bugs.
# Documented no-op: emits a notice and returns 0 on State 1.
# ---------------------------------------------------------------------------
_prune_noop() {
  echo "prune-closed-bugs.sh: State 1 (coordinator_core.invoke seam absent) — no legacy prune path; skipping" >&2
  return 0
}

# ---------------------------------------------------------------------------
# Candidate selection — status: closed ONLY
#   Matches both `status: closed` (unquoted) and `status: "closed"` (quoted).
#   wontfix and deferred are explicitly excluded by not matching them here.
# ---------------------------------------------------------------------------
_candidates=()
for _f in "${_bug_dir}"/*.yaml; do
  # Empty-glob guard: bash expands to literal pattern when no files match
  [[ -f "$_f" ]] || continue

  # Check status: closed — field-anchored to start of line; not prose inside body
  if grep -qE '^status:[[:space:]]+"?closed"?[[:space:]]*$' "$_f" 2>/dev/null; then
    # Build repo-relative path (strip leading repo_root/ prefix)
    _rel="${_f#"${_repo_root}/"}"
    _candidates+=("${_rel}")
  fi
done

if [[ "${#_candidates[@]}" -eq 0 ]]; then
  echo "prune-closed-bugs.sh: no closed bug entries found — nothing to prune"
  exit 0
fi

echo "prune-closed-bugs.sh: ${#_candidates[@]} closed bug(s) selected for prune"

# ---------------------------------------------------------------------------
# Build fleet params JSON — mode:"already-terminal" required; candidate_ids
# are repo-relative paths; dry_run controls whether the op commits.
# jq used for safe JSON array construction (same dependency as sibling scripts).
# ---------------------------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  echo "prune-closed-bugs.sh: WARN: jq not found — cannot build fleet params; skipping prune (non-blocking)" >&2
  exit 0
fi

_PRUNE_PARAMS="$(jq -cn \
  --argjson dry_run "${_dry_run}" \
  '{mode:"already-terminal",dry_run:$dry_run,candidate_ids:$ARGS.positional}' \
  --args "${_candidates[@]}")"

# ---------------------------------------------------------------------------
# Fleet dispatch via strangle_route.
#   State 1 (seam absent): _prune_noop — documented no-op, returns 0.
#   State 2 (invoke success): cc_invoke exits 0; bare result JSON on stdout.
#   State 3 (transport failure): cc_invoke exits 2.
#
# Best-effort wrapper: strangle_route result (bare result JSON) captured for
# summary logging; non-zero exit is caught and logged rather than propagated.
#
# TWO-SIGNAL contract (KD-5 / AC7):
#   (1) Check strangle_route's OWN exit code (rc 2 = cc_invoke transport-fail-closed).
#   (2) On rc 0, the bare result object's top-level .exit_code carries the op verdict.
#       .exit_code==0 clean, ==1 setup-error, ==2 determinate-partial.
#   Parse TOP-LEVEL keys (.exit_code, .acted[]) — NEVER .result.exit_code.
# ---------------------------------------------------------------------------
_prune_result=""
_prune_rc=0
_prune_result="$(strangle_route "fleet.prune_closed_bugs" "_prune_noop" \
  "$_PRUNE_PARAMS")" || _prune_rc=$?

if [[ "${_prune_rc}" -ne 0 ]]; then
  echo "prune-closed-bugs.sh: WARN: fleet.prune_closed_bugs transport error (rc=${_prune_rc}) — skipping (non-blocking)" >&2
  exit 0
fi

# Parse op-level result for a summary log line (top-level .exit_code / .acted[]).
# python3 availability check guards the parse; fallback to candidate count on absence.
if [[ -n "${_prune_result}" ]] && command -v python3 >/dev/null 2>&1; then
  _op_exit="$(printf '%s' "${_prune_result}" | python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); print(r.get("exit_code","?"))' 2>/dev/null || echo "?")"  # popup-safe-env-suppressed
  _acted_count="$(printf '%s' "${_prune_result}" | python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); print(len(r.get("acted",[])))' 2>/dev/null || echo "?")"  # popup-safe-env-suppressed

  if [[ "${_op_exit}" == "0" ]]; then
    echo "prune-closed-bugs.sh: fleet.prune_closed_bugs completed — ${_acted_count} entr(ies) archived"
  elif [[ "${_op_exit}" == "2" ]]; then
    echo "prune-closed-bugs.sh: WARN: fleet.prune_closed_bugs partial (exit_code=2, acted=${_acted_count}) — check example-orchestration-hub logs" >&2
  else
    echo "prune-closed-bugs.sh: fleet.prune_closed_bugs exit_code=${_op_exit} (acted=${_acted_count})"
  fi
else
  echo "prune-closed-bugs.sh: fleet.prune_closed_bugs dispatched (${#_candidates[@]} candidate(s))"
fi

exit 0
