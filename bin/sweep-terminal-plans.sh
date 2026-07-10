#!/usr/bin/env bash
# sweep-terminal-plans.sh — archive terminal plans via fleet.archive_completed_plans.
#
# Purpose: strangler-facade wrapper that routes terminal-plan archival through
# the coordinator_core fleet op (`fleet.archive_completed_plans`) on the native
# path, with `cs_sweep_terminal_plans` (coordinator-session.sh) as the State-1
# legacy fallback.
#
# Usage:
#   sweep-terminal-plans.sh [<repo_root>]
#
#   <repo_root>  Optional; defaults to `git rev-parse --show-toplevel`.
#
# Stdout contract:
#   An INTEGER count of plans archived is printed to stdout on BOTH paths:
#     - Native path:  len(.acted) from the fleet op's bare result object.
#     - Legacy path:  count printed by cs_sweep_terminal_plans.
#   This integer is consumed by session-init.sh's numeric guard.
#
# Commit semantics:
#   Native path: the fleet op self-commits (archive_and_commit) — the caller
#     MUST NOT stage/commit afterwards; the diff --cached guard in session-init
#     naturally prevents double-commit (cache is empty after the op commits).
#   Legacy path: cs_sweep_terminal_plans stages moves; the caller (session-init
#     or Step 2.65) owns the commit, same as before.
#
# Two-call shape (KD-2 plans self-preview):
#   Call 1: dry_run:true  — op selects repo-relative candidate IDs; sidesteps
#            the absolute-id trap (archive_plans.py absolute-path matching).
#   Call 2: dry_run:false — op performs git-mv + self-commit for those IDs.
#   Empty candidates → print 0, skip Call 2, exit 0.
#
# Transport routing (three-state model from strangler-facade.sh):
#   State 1 (seam absent): cs_sweep_terminal_plans legacy fn.
#   State 2 (native OK):   cc_invoke fleet.archive_completed_plans, two-call.
#   State 3 (transport err): log-and-continue, print 0 (best-effort ceremony).
#
# Exit codes:
#   0 — normal completion (including no-candidates, legacy path, transport warn).
#
# Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C3 / KD-2 / KD-3
# DR-215: replaces direct cs_sweep_terminal_plans call-sites in session-init + Step 2.65.
# BSD-portable bash>=4; GNU-isms guarded per DR-148.

set -euo pipefail  # Review: code-reviewer — nit: sibling sweep-shipped-handoffs.sh uses -euo; -e added for consistency

# ---------------------------------------------------------------------------
# bash>=4 guard — must be reachable on bash 3.2 (plain comparison, no bash-4 syntax)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'sweep-terminal-plans.sh: requires bash >= 4 (current: %s)\n' "${BASH_VERSION:-unknown}" >&2
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
# Provides: _sf_seam_present, cc_invoke, strangle_route.
# ---------------------------------------------------------------------------
_STP_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_STP_SCRIPT_DIR}/../lib/strangler-facade.sh" || {
  printf 'sweep-terminal-plans.sh: failed to source strangler-facade.sh\n' >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Repo root — accept as arg or resolve from git
# ---------------------------------------------------------------------------
_repo_root="${1:-}"
if [[ -z "$_repo_root" ]]; then
  _repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    printf 'sweep-terminal-plans.sh: cannot resolve git repo root\n' >&2
    printf '0\n'
    exit 0
  }
fi

# ---------------------------------------------------------------------------
# Source coordinator-session.sh for legacy path (cs_sweep_terminal_plans).
# ---------------------------------------------------------------------------
_cs_session_lib="${PLUGIN_ROOT}/lib/coordinator-session.sh"
if [[ -f "$_cs_session_lib" ]]; then
  # shellcheck source=../lib/coordinator-session.sh
  source "$_cs_session_lib" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Legacy function — State 1 path.
# cs_sweep_terminal_plans prints an integer count and stages git-mv moves.
# Caller owns the commit on the legacy path.
# ---------------------------------------------------------------------------
_legacy_sweep_terminal_plans() {
  if command -v cs_sweep_terminal_plans >/dev/null 2>&1; then
    cs_sweep_terminal_plans "$_repo_root" 2>/dev/null || printf '0\n'
  else
    printf 'sweep-terminal-plans.sh: cs_sweep_terminal_plans not available (legacy path)\n' >&2
    printf '0\n'
  fi
}

# ---------------------------------------------------------------------------
# Native path — States 2/3: two-call fleet op.
# Call 1: dry_run:true  → op self-selects repo-relative candidates.
# Call 2: dry_run:false → op git-mv + self-commits for those candidates.
# Normalizes stdout to integer count (len(.acted)).
# Log-and-continue on any transport failure (best-effort ceremony op).
# ---------------------------------------------------------------------------
_native_sweep_terminal_plans() {
  # --- Call 1: dry-run to preview candidates ---
  local _dry_params='{"mode":"already-terminal","dry_run":true,"candidate_ids":[]}'
  local _dry_result
  # Review: code-reviewer — F5 (P2): 2>&1 merged cc_invoke stderr into _dry_result;
  # a stray Python deprecation warning on rc 0 would prepend to the JSON, causing silent
  # JSON parse failure (0 candidates, no error surfaced). cc_invoke contract: empty stderr
  # on rc 0; legible diagnostic on stderr on rc 2. Use 2>/dev/null; the || handler still
  # fires on non-zero rc.
  _dry_result="$(cc_invoke "fleet.archive_completed_plans" "$_dry_params" "$_repo_root" 2>/dev/null)" || {
    printf 'sweep-terminal-plans.sh: fleet.archive_completed_plans dry-run failed (transport error) — skipping\n' >&2
    printf '0\n'
    return 0
  }

  # Extract .candidates[].id strings from the bare result object (top-level key).
  # cc_invoke emits the bare result object; callers parse TOP-LEVEL keys — never .result.X.
  # The act call's candidate_ids param expects a list of ID strings, NOT the full candidate
  # objects returned by the dry-run preview.  Extract only the "id" field from each dict.
  # NEGATIVE-SPEC: passing full candidate objects to candidate_ids causes TypeError in the
  # handler (worktree_root / <dict> fails), which causes cc_invoke to return 2 (fail-closed)
  # and the act call to silently skip all archival.
  local _candidates_json
  _candidates_json="$(printf '%s' "$_dry_result" | python3 -c '  # popup-safe-env-suppressed
import json, sys
try:
    obj = json.loads(sys.stdin.read())
    cands = obj.get("candidates", [])
    # Review: code-reviewer — F4 (nit): "id" in c passes None/empty through; isinstance(str)
    # rejects null ids, preventing a downstream TypeError in the act handler.
    ids = [c["id"] for c in cands if isinstance(c, dict) and isinstance(c.get("id"), str)]
    if ids:
        print(json.dumps(ids))
    else:
        print("[]")
except Exception:
    print("[]")
' 2>/dev/null)" || _candidates_json="[]"

  # TWO-SIGNAL contract (AC7): parse op-level .exit_code from dry-run result.
  # Non-zero exit_code (e.g., exit_code:1 setup-error) — log WARN and proceed with candidates
  # as-is (the empty-candidates check below handles the degenerate empty case).
  # Review: code-reviewer — AC7: .exit_code second signal; dry-run call
  local _dry_exit
  _dry_exit="$(printf '%s' "$_dry_result" | python3 -c '  # popup-safe-env-suppressed
import json, sys
try:
    obj = json.loads(sys.stdin.read())
    print(obj.get("exit_code", 0))
except Exception:
    print(0)
' 2>/dev/null || echo "0")"
  if [[ "${_dry_exit}" != "0" ]]; then
    printf 'sweep-terminal-plans.sh: WARN: fleet.archive_completed_plans dry-run exit_code=%s — proceeding with candidates as-is\n' "${_dry_exit}" >&2
  fi

  # Empty candidates → nothing to archive, print 0.
  if [[ "$_candidates_json" == "[]" ]] || [[ -z "$_candidates_json" ]]; then
    printf '0\n'
    return 0
  fi

  # --- Call 2: act on candidates ---
  local _act_params
  _act_params="$(python3 -c '  # popup-safe-env-suppressed
import json, sys
cands = json.loads(sys.argv[1])
print(json.dumps({"mode":"already-terminal","dry_run":False,"candidate_ids":cands}))
' "$_candidates_json" 2>/dev/null)" || {
    printf 'sweep-terminal-plans.sh: failed to build act params — skipping\n' >&2
    printf '0\n'
    return 0
  }

  local _act_result
  # Review: code-reviewer — F5 (P2): same as dry-run; 2>/dev/null prevents stderr
  # contamination of _act_result JSON; || handler fires on non-zero rc as before.
  _act_result="$(cc_invoke "fleet.archive_completed_plans" "$_act_params" "$_repo_root" 2>/dev/null)" || {
    printf 'sweep-terminal-plans.sh: fleet.archive_completed_plans act call failed (transport error) — skipping\n' >&2
    printf '0\n'
    return 0
  }

  # Extract integer count from .acted[] (top-level key of bare result object).
  # Fleet op self-commits; we report the count but do NOT stage or commit here.
  local _count
  _count="$(printf '%s' "$_act_result" | python3 -c '  # popup-safe-env-suppressed
import json, sys
try:
    obj = json.loads(sys.stdin.read())
    acted = obj.get("acted", [])
    print(len(acted) if isinstance(acted, list) else 0)
except Exception:
    print(0)
' 2>/dev/null)" || _count=0

  # Ensure integer (strip whitespace / guard non-numeric output).
  _count="${_count//[[:space:]]/}"
  if ! [[ "$_count" =~ ^[0-9]+$ ]]; then
    _count=0
  fi

  # TWO-SIGNAL contract (AC7): parse op-level .exit_code from act result.
  # exit_code==2 (determinate-partial): some plans archived, some failed — log WARN and continue.
  # Review: code-reviewer — AC7: .exit_code second signal; act call; mirrors prune-closed-bugs.sh:183-184
  local _act_exit
  _act_exit="$(printf '%s' "$_act_result" | python3 -c '  # popup-safe-env-suppressed
import json, sys
try:
    obj = json.loads(sys.stdin.read())
    print(obj.get("exit_code", 0))
except Exception:
    print(0)
' 2>/dev/null || echo "0")"
  if [[ "${_act_exit}" == "2" ]]; then
    printf 'sweep-terminal-plans.sh: WARN: fleet.archive_completed_plans partial (exit_code=2, acted=%s) — check example-orchestration-hub logs\n' "${_count}" >&2
  fi

  printf '%s\n' "$_count"
  return 0
}

# ---------------------------------------------------------------------------
# Routing — three-state model.
# _sf_seam_present: returns 0 if coordinator_core.invoke is importable (States 2/3);
#                   returns 1 if seam absent (State 1 legacy path).
# ---------------------------------------------------------------------------
if _sf_seam_present 2>/dev/null; then
  _native_sweep_terminal_plans
else
  _legacy_sweep_terminal_plans
fi
