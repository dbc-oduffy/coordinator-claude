#!/usr/bin/env bash
# sweep-boot.sh — session.boot_sweep strangler wrapper.
#
# Purpose: strangler-facade wrapper routing boot-time composite archival sweep through
# coordinator_core session.boot_sweep op on the native path (ONE cold-start for all
# four archival classes in a single process), with legacy per-class sweeps as the
# State-1 fallback.
#
# Usage:
#   sweep-boot.sh [<repo_root>] [<state_common_dir>]
#
#   <repo_root>         Optional; defaults to `git rev-parse --show-toplevel`.
#   <state_common_dir>  Optional; the STATE-hosting repo's `.git` common dir
#                        (symmetric with <repo_root>, per the session.boot_sweep
#                        state_common_dir param contract — cross-repo memo
#                        2026-07-07-gap6-gpgsign-landed-boot-sweep-two-repo-split.md
#                        item 2). Forwarded into the native op's params JSON
#                        ONLY — the legacy path has no two-repo awareness and
#                        collapses to unified-state (see _legacy_sweep_boot
#                        header note). Absent/omitted → native op falls back
#                        to unified-state collapse itself (op-side contract).
#
# Stdout contract:
#   An INTEGER count of items archived is printed to stdout on BOTH paths:
#     - Native path:  sum of len(.archived) across the four result buckets
#                     (consumed_handoffs, plans, shipped_handoffs, memos).
#     - Legacy path:  sum of integer counts from the available legacy sweeps.
#   This integer is consumed by the caller's numeric guard.
#
# Commit semantics:
#   Native path: session.boot_sweep self-commits all four archival classes — the
#     caller MUST NOT stage or commit afterwards; the wrapper enforces this by never
#     calling git add/commit itself.
#   Legacy path: each legacy sweep owns its own commit semantics (see each sweep).
#
# Three-state routing (three-state model from strangler-facade.sh):
#   State 1 (seam absent): legacy per-class sweeps (actioned-memos, terminal-plans,
#     shipped-handoffs). Consumed-handoff sweep is caller-owned on the legacy path
#     (see note in _legacy_sweep_boot below).
#   State 2 (native OK):   strangle_route_mutation -> cc_invoke session.boot_sweep,
#     single call (no two-phase round-trip). Parses four result buckets; prints count.
#   State 3 (transport err): log-and-continue to stderr; print 0 (best-effort ceremony).
#
# Split-repo detection (the Director of Engineering F2 / AC7): NOT in this wrapper.
#   sweep-boot.sh does NOT source coordinator-state-root.sh or independently
#   resolve _STATE_REPO — it only accepts a caller-supplied <state_common_dir>
#   positional and forwards it verbatim. The caller (session-init) owns the
#   _STATE_REPO != GIT_ROOT precondition and computes state_common_dir itself,
#   exactly like INIT_SKIP_SWEEP.
#
# INIT_SKIP_SWEEP: NOT in this wrapper — caller precondition (parity with sweep-terminal-plans.sh,
#   which also does not self-skip).
#
# Exit codes:
#   0 — normal completion (including no-candidates, legacy path, transport warn).
#
# Spec backlink: docs/plans/2026-07-06-strang-11-b8-session-init-op-absorption.md § C2 / AC7
# DR-215: single-process four-class sweep replaces four separate cc_invoke cold-starts.
# BSD-portable bash>=4; GNU-isms guarded per DR-148.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash>=4 guard — must be reachable on bash 3.2 (plain comparison, no bash-4 syntax)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  printf 'sweep-boot.sh: requires bash >= 4 (current: %s)\n' "${BASH_VERSION:-unknown}" >&2
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
_SB_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_SB_SCRIPT_DIR}/../lib/strangler-facade.sh" || {
  printf 'sweep-boot.sh: failed to source strangler-facade.sh\n' >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Repo root — accept as arg or resolve from git
# ---------------------------------------------------------------------------
_repo_root="${1:-}"
if [[ -z "$_repo_root" ]]; then
  _repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    printf 'sweep-boot.sh: cannot resolve git repo root\n' >&2
    printf '0\n'
    exit 0
  }
fi

# ---------------------------------------------------------------------------
# state_common_dir — optional 2nd positional; forwarded into native params
# JSON only (see header). Left empty means unified-state (single-repo) —
# the native op's own fallback contract handles that case identically to an
# absent param, so no extra branching is needed here.
# ---------------------------------------------------------------------------
_state_common_dir="${2:-}"

# ---------------------------------------------------------------------------
# Source coordinator-session.sh for legacy path (cs_sweep_actioned_memos).
# ---------------------------------------------------------------------------
_cs_session_lib="${PLUGIN_ROOT}/lib/coordinator-session.sh"
if [[ -f "$_cs_session_lib" ]]; then
  # shellcheck source=../lib/coordinator-session.sh
  source "$_cs_session_lib" 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
# Legacy function — State 1 path.
#
# Calls the three available legacy sweeps: actioned-memos, terminal-plans,
# shipped-handoffs. Prints an integer count = sum of archived across all three.
#
# Consumed-handoff sweep: NO callable lib function exists in coordinator-session.sh
# that encapsulates the full orphan-consumed-handoff logic (liveness check, 30-min
# recency floor, deployment_state flip, shipped_in stamp, has-live-children guard,
# git-mv, WARN marker). The inline block in session-init.sh is not a lib function.
# The legacy path CANNOT self-contain the consumed-handoff sweep.
# The caller (session-init, at cutover time) must retain its existing inline
# consumed-handoff block. This is a documented seam limitation; AC9 gate resolves it.
# ---------------------------------------------------------------------------
_legacy_sweep_boot() {
  local _total=0

  # 1. Actioned-memo sweep — cs_sweep_actioned_memos prints integer count.
  if command -v cs_sweep_actioned_memos >/dev/null 2>&1; then
    local _memos
    _memos=$(cs_sweep_actioned_memos "$_repo_root" 2>/dev/null || echo 0)
    _memos="${_memos//[[:space:]]/}"
    if [[ "$_memos" =~ ^[0-9]+$ ]]; then
      _total=$(( _total + _memos ))
    fi
  else
    printf 'sweep-boot.sh: cs_sweep_actioned_memos not available (legacy path)\n' >&2
  fi

  # 2. Terminal-plan sweep — sweep-terminal-plans.sh prints integer count.
  local _plans_script="${_SB_SCRIPT_DIR}/sweep-terminal-plans.sh"
  if [[ -f "$_plans_script" ]]; then
    local _plans
    _plans=$(bash "$_plans_script" "$_repo_root" 2>/dev/null || echo 0)
    _plans="${_plans//[[:space:]]/}"
    if [[ "$_plans" =~ ^[0-9]+$ ]]; then
      _total=$(( _total + _plans ))
    fi
  else
    printf 'sweep-boot.sh: sweep-terminal-plans.sh not found (legacy path)\n' >&2
  fi

  # 3. Shipped-handoff sweep — sweep-shipped-handoffs.sh prints "N shipped handoffs archived".
  # Parse the leading integer from its first count line; default 0 if absent or "no".
  local _shipped_script="${_SB_SCRIPT_DIR}/sweep-shipped-handoffs.sh"
  if [[ -f "$_shipped_script" ]]; then
    local _shipped_out _shipped
    _shipped_out=$(bash "$_shipped_script" 2>/dev/null || true)
    _shipped=$(printf '%s\n' "$_shipped_out" | awk '/^[0-9]+ shipped handoffs archived/{print $1; exit}')
    _shipped="${_shipped//[[:space:]]/}"
    if [[ "$_shipped" =~ ^[0-9]+$ ]]; then
      _total=$(( _total + _shipped ))
    fi
  else
    printf 'sweep-boot.sh: sweep-shipped-handoffs.sh not found (legacy path)\n' >&2
  fi

  # 4. Consumed-handoff sweep: no callable lib function available — seam limitation.
  # The caller (session-init, at cutover time) retains its inline consumed-handoff
  # block. This note encodes the seam gap; the caller is authoritative.
  printf 'sweep-boot.sh: consumed-handoff sweep not available on legacy path — caller owns inline block (AC9)\n' >&2

  printf '%s\n' "$_total"
}

# ---------------------------------------------------------------------------
# Native function — States 2/3: single cc_invoke session.boot_sweep.
#
# Routes through strangle_route_mutation to honor .exit_code/.error signals
# (NOT bare strangle_route — op carries structured error shapes).
# The op self-commits all four archival classes; this wrapper MUST NOT stage
# or commit (enforced by never calling git add/commit here).
#
# strangle_route auto-resolves repo root from $PWD; the subshell `cd $_repo_root`
# ensures correct target repo when the caller passes an explicit $1 repo arg.
# _legacy_sweep_boot is defined in the parent scope and accessible in the subshell;
# strangle_route will not invoke it here (seam is confirmed present at this point).
#
# state_common_dir: forwarded verbatim into the params JSON when the caller
# supplied a non-empty $_state_common_dir (2nd positional). Symmetric with
# repo_root per the cross-repo param contract; absent → '{}' (op-side
# unified-state fallback, unchanged from pre-two-repo-split behavior).
#
# Stdout contract: integer = sum of len(.archived) across four result buckets:
#   consumed_handoffs, plans, shipped_handoffs, memos.
# ---------------------------------------------------------------------------
_native_sweep_boot() {
  local _result _rc _params_json
  _rc=0

  if [[ -n "$_state_common_dir" ]]; then
    # popup-safe-env-suppressed (inline python3; no GUI window on macOS).
    _params_json="$(STATE_COMMON_DIR="$_state_common_dir" python3 -c '  # popup-safe-env-suppressed
import json, os
print(json.dumps({"state_common_dir": os.environ["STATE_COMMON_DIR"]}))
' 2>/dev/null)" || _params_json='{}'
    [[ -z "$_params_json" ]] && _params_json='{}'
  else
    _params_json='{}'
  fi

  # Subshell cd pins PWD so strangle_route resolves the correct repo root.
  # strangle_route_mutation captures .exit_code/.error and logs WARN to stderr;
  # it re-emits the bare result JSON to stdout even on op-level error (exit_code:2
  # DETERMINATE-PARTIAL), so count parsing below works regardless of _rc.
  _result="$(
    cd "$_repo_root" 2>/dev/null || {
      printf 'sweep-boot.sh: cannot cd to %s — treating as transport error\n' "$_repo_root" >&2
      exit 1
    }
    strangle_route_mutation "session.boot_sweep" "_legacy_sweep_boot" "$_params_json"
  )" || _rc=$?

  # Parse archived count: sum len(.archived) across the four result buckets.
  # cc_invoke emits the bare result object; callers parse TOP-LEVEL keys.
  # Returns -1 sentinel on parse failure (transport error / non-JSON result).
  # popup-safe-env-suppressed (inline python3; no GUI window on macOS).
  local _count
  _count="$(printf '%s' "$_result" | python3 -c '  # popup-safe-env-suppressed
import json, sys
try:
    obj = json.loads(sys.stdin.read())
    count = 0
    for bucket in ["consumed_handoffs", "plans", "shipped_handoffs", "memos"]:
        b = obj.get(bucket, {})
        archived = b.get("archived", [])
        if isinstance(archived, list):
            count += len(archived)
    print(count)
except Exception:
    print(-1)
' 2>/dev/null)" || _count="-1"

  # Normalize: strip whitespace; guard against non-numeric output.
  _count="${_count//[[:space:]]/}"

  # State 3: non-JSON or parse failure → transport error.
  # Log-and-continue; print 0 (best-effort ceremony op).
  if [[ "$_count" == "-1" ]] || ! [[ "$_count" =~ ^[0-9]+$ ]]; then
    printf 'sweep-boot.sh: session.boot_sweep transport error (rc=%s) — skipping\n' "$_rc" >&2
    printf '0\n'
    return 0
  fi

  # exit_code:2 (DETERMINATE-PARTIAL): strangle_route_mutation already logged WARN
  # to stderr. Add wrapper-level WARN with count for audit visibility.
  # Still print the partial count — a non-zero exit_code does not suppress archived items.
  if [[ "$_rc" -ne 0 ]]; then
    printf 'sweep-boot.sh: WARN: session.boot_sweep returned rc=%s (partial or setup error) — archived %s item(s)\n' \
      "$_rc" "$_count" >&2
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
  _native_sweep_boot
else
  _legacy_sweep_boot
fi
