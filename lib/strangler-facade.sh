#!/usr/bin/env bash
# coordinator/lib/strangler-facade.sh — DR-210/DR-215 shared transport/routing helper.
#
# Purpose: exposes one public function `strangle_route` implementing the
# three-state routing model (Design pin 3) so every body-swapped emitter
# script de-duplicates presence/spawn/dispatch plumbing without compromising
# per-verb discipline.  The function decides native-vs-legacy (disk-presence
# gate) and dispatches via cc_invoke (coordinator-core-invoke.sh) — a
# spawn-per-call command-type transport (DR-215; retired UDS daemon replaced).
#
# Spec backlinks:
#   docs/plans/2026-07-04-strang-01-tc3-emission-port-facade-respin.md § C4b
#   docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C1 / KD-1
#
# no-batch-shortcut guard (seam-discipline §5):
#   This helper de-duplicates TRANSPORT plumbing only.  Each calling script
#   (C2/C3 and each strang-04..strang-10 verb) still earns its own:
#     - read-before-write (verify the target script before body-swap)
#     - byte-identical-vs-DoE-HEAD conformance check
#     - legacy_fn capturing the pre-swap body
#     - per-verb tests (routing branches + grep-gate)
#   A shared router is not a batch-strangle; per-verb discipline stays intact.
#
# Three-state routing model (Design pin 3 -- do not re-open):
#
#   State 1 -- coordinator_core.invoke NOT importable (seam absent on disk):
#             -> call `legacy_fn` with the legacy-args; return its exit status.
#             Legacy fires ONLY on disk-absence -- never on transport failure.
#
#   State 2 -- seam present + cc_invoke succeeds (spawn-per-call, ~59ms cold start):
#             -> cc_invoke spawns coordinator_core.invoke as a subprocess once per call.
#             No daemon, no socket, no lazy-launch; each call is a fresh process.
#             This is the normal steady state -- not an error.
#
#   State 3 -- seam present + cc_invoke fails (timeout / import error / bad envelope):
#             -> cc_invoke exits 2; propagate that exit (never fall back to legacy).
#             NEVER fall back to legacy -- fail loud (native-primary integrity).
#
# Testing/parity affordance layered over the three states (not a 4th state):
#   COORDINATOR_FORCE_LEGACY=1 forces the State-1 legacy branch even when the
#   seam is present on disk.  Defaults off (empty/unset preserves the three-state
#   behavior above unchanged).  Exists so a byte-parity harness comparing legacy
#   vs. native output can deterministically exercise the bash path without fighting
#   coordinator-example-orchestration-hub-root.sh's EXAMPLE_ORCHESTRATION_HUB_ROOT re-resolution (unsetting the env var
#   alone does not force legacy -- the resolver rediscovers and re-exports it).
#   This is opt-in test plumbing, not a production fallback: State 3's fail-loud
#   contract is untouched when the lever is off.
#
# Spawn-per-call in-band outcome semantics (DR-215):
#   cc_invoke emits the BARE result object to stdout (envelope wrapper stripped).
#   Callers parsing cc_invoke output inspect TOP-LEVEL keys (.exit_code, .acted[],
#   .verdict_line, etc.) -- NEVER .result.X (no double-nesting; cc_invoke strips it).
#   strangle_route itself does NOT parse cc_invoke output -- it propagates exit code only.
#   Individual verb callers that need result JSON parse it themselves.
#
# Standalone-repo / no-linked-worktree assumption:
#   Repo-root auto-resolution uses `git -C "$PWD" rev-parse --show-toplevel`.
#   The coordinator bans linked worktrees (coordinator/CLAUDE.md); on the DoE layout
#   git_common_dir is always .git (not a linked worktree gitfile), so --show-toplevel
#   resolves to the correct root without ambiguity.
#
# Public API:
#   strangle_route <op-name> <legacy_fn> [<params-json>] [legacy-args...]
#
#   <op-name>      op forwarded to coordinator_core.invoke via cc_invoke,
#                  e.g. "artifact.emit"
#   <legacy_fn>    name of shell function implementing the legacy path
#   <params-json>  JSON object string passed to cc_invoke, e.g. '{"key":"val"}'.
#                  Supply '{}' for ops with no parameters; omit to default to '{}'.
#   [legacy-args]  positional args forwarded verbatim to legacy_fn (State 1 only).
#                  Callers typically pass their own "$@" captured before sourcing.
#                  NOTE: no 4th positional is added for the repo root -- that is
#                  resolved internally from PWD (standalone-repo note above).
#
# Usage (C2 / C3 call site pattern):
#   # At top of body-swapped script, before defining legacy_fn:
#   _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "${_SCRIPT_DIR}/../lib/strangler-facade.sh"
#
#   legacy_emit() { ... original script body ... }
#
#   _params_json="$(build_params_json "$@")"
#   strangle_route "artifact.emit" "legacy_emit" "$_params_json" "$@"
#
# Disk-presence check:
#   Tests coordinator_core.invoke importability with EXAMPLE_ORCHESTRATION_HUB_ROOT on PYTHONPATH
#   (runs an import probe with subprocess).  EXAMPLE_ORCHESTRATION_HUB_ROOT is resolved via the sibling
#   coordinator-example-orchestration-hub-root.sh lib if not already in the environment.  If EXAMPLE_ORCHESTRATION_HUB_ROOT
#   cannot be resolved, the helper treats the seam as absent (defensive) and routes
#   to legacy with a notice on stderr.
#
# Negative-spec:
#   - Does NOT probe liveness (no UDS socket, no daemon pid) -- DR-215 retired the daemon.
#   - Does NOT re-implement spawn_service_detached / wait_for_endpoint (retired DR-215).
#   - Does NOT fall back to legacy after a native transport failure (State 3).
#   - Does NOT call `machine-local get` as a CLI in any code path (bootstrap
#     hazard, Design pin 4).  EXAMPLE_ORCHESTRATION_HUB_ROOT resolution via coordinator-example-orchestration-hub-root.sh
#     is the only machine-local call, and it uses the resolver lib's §4c ladder.
#     Cold-fallback self-location for each verb's legacy_fn lives in the calling
#     script (C2/C3), not here.
#   - Does NOT add a 4th positional arg to strangle_route for repo root (would
#     collide with legacy-args at position 4+, e.g. memo-transition-facade.sh).
#   - COORDINATOR_FORCE_LEGACY=1 is an opt-in, test-only lever (byte-parity
#     harnesses) -- it does NOT change State 3's native-transport-failure
#     fail-loud semantics; with the lever off (default), behavior is identical
#     to the three-state model above.
#
# Cross-platform: bash >=4 required (coordinator-core-invoke.sh uses bash-4 features).
# BSD coreutils; no GNU-isms; safe to source multiple times (idempotent).

# NOTE: deliberately no set -e -- this file is SOURCED.  A file-scope errexit
# in a sourced lib propagates to the caller's shell.  Functions capture exit
# codes explicitly.  Mirrors coordinator-currency.sh convention.
# NOTE: -u (nounset) and pipefail ARE included and also propagate to callers
# when this file is sourced; callers are expected to already have these set
# (current callers emit-cockpit-snapshot.sh and append-goal-event.sh both
# set -euo pipefail before sourcing this lib).
set -uo pipefail

# ---------------------------------------------------------------------------
# Bash >=4 guard -- MUST be above all bash-4 syntax; parses safely on bash 3.2.
# Required because coordinator-core-invoke.sh (sourced below) uses bash-4 features.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  {
    printf 'strangler-facade.sh: requires bash >=4 (found %s).\n' "${BASH_VERSION:-unknown}"
    printf '  macOS: brew install bash  (restart terminal; /opt/homebrew/bin/bash is bash 5)\n'
    printf '  Reference: coordinator/docs/wiki/cross-platform-shell-portability.md\n'
  } >&2
  return 1 2>/dev/null || exit 1
fi

# ---------------------------------------------------------------------------
# Internal: _SF_LIB_DIR
# ---------------------------------------------------------------------------
# Absolute path to this file's directory, resolved at source time.  Used to
# locate the sibling coordinator-example-orchestration-hub-root.sh without relying on PATH.
_SF_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Source cc_invoke transport seam (KD-0; DR-215 command-type transport).
# Idempotent: coordinator-core-invoke.sh has its own idempotency guard.
# ---------------------------------------------------------------------------
# shellcheck source=./coordinator-core-invoke.sh
source "${_SF_LIB_DIR}/coordinator-core-invoke.sh" || {
  printf 'strangler-facade.sh: failed to source coordinator-core-invoke.sh\n' >&2
  return 1 2>/dev/null || exit 1
}

# ---------------------------------------------------------------------------
# Internal: _sf_resolve_example_orchestration_hub_root
# ---------------------------------------------------------------------------
# Prints the resolved EXAMPLE_ORCHESTRATION_HUB_ROOT to stdout; returns 0 on success, 1 on
# failure.  Sources coordinator-example-orchestration-hub-root.sh (idempotent) if EXAMPLE_ORCHESTRATION_HUB_ROOT is
# not already set; that lib exports EXAMPLE_ORCHESTRATION_HUB_ROOT, so subsequent calls are cheap.
_sf_resolve_example_orchestration_hub_root() {
  # Fast path: already set in environment (machine-local-registry.md §4b guard).
  if [[ -n "${EXAMPLE_ORCHESTRATION_HUB_ROOT:-}" ]]; then
    printf '%s' "$EXAMPLE_ORCHESTRATION_HUB_ROOT"
    return 0
  fi

  local _resolver="${_SF_LIB_DIR}/coordinator-example-orchestration-hub-root.sh"
  if [[ ! -f "$_resolver" ]]; then
    printf 'strangler-facade.sh: coordinator-example-orchestration-hub-root.sh not found at %s\n' \
      "$_resolver" >&2
    return 1
  fi

  # shellcheck source=./coordinator-example-orchestration-hub-root.sh
  source "$_resolver"

  local _root
  _root=$(coordinator_example_orchestration_hub_root 2>/dev/null) || {
    printf 'strangler-facade.sh: cannot resolve EXAMPLE_ORCHESTRATION_HUB_ROOT\n' >&2
    return 1
  }
  # coordinator_example_orchestration_hub_root exports EXAMPLE_ORCHESTRATION_HUB_ROOT as a side-effect; return value.
  printf '%s' "$_root"
}

# ---------------------------------------------------------------------------
# Internal: _sf_seam_present
# ---------------------------------------------------------------------------
# Returns 0 if coordinator_core.invoke is importable (disk-presence gate).
# Returns 1 if absent or if EXAMPLE_ORCHESTRATION_HUB_ROOT cannot be resolved.
#
# DR-215: probes coordinator_core.invoke (not the retired coordinator_core.client).
# This is the ONLY gate that triggers legacy fallback.  Transport errors after
# dispatch are handled by cc_invoke (returns 2 on any failure -- never legacy).
_sf_seam_present() {
  local _root
  _root=$(_sf_resolve_example_orchestration_hub_root) || {
    printf 'strangler-facade.sh: EXAMPLE_ORCHESTRATION_HUB_ROOT unresolvable; treating seam as absent\n' >&2
    return 1
  }

  # popup-safe-env-suppressed: POSIX bash subprocess; no Windows console concern.
  PYTHONPATH="${_root}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -c 'import coordinator_core.invoke' 2>/dev/null  # popup-safe-env-suppressed
}

# ---------------------------------------------------------------------------
# Public: strangle_route
# ---------------------------------------------------------------------------
# DR-210/DR-215 three-state facade router.  See header for full contract.
#
# Usage:
#   strangle_route <op-name> <legacy_fn> [<params-json>] [legacy-args...]
#
# Returns:
#   State 1: exit status of legacy_fn.
#   States 2/3: exit status of cc_invoke.
#     - State 2 (invoke success): cc_invoke returns 0.
#     - State 3 (transport failure): cc_invoke returns 2.
#   A non-zero exit from cc_invoke (State 3) is propagated as-is; the
#   function NEVER silently routes to legacy after native is attempted.
strangle_route() {
  local _op_name="${1:?strangle_route: op-name required}"
  local _legacy_fn="${2:?strangle_route: legacy_fn required}"
  shift 2

  # Third positional arg is the JSON params string; default to empty object.
  # Two-step form: ${1:-{}} mis-parses in bash — the first } closes the ${...}
  # expansion, so any non-empty $1 gets a spurious trailing } appended.
  local _params_json="${1:-}"
  [ -z "$_params_json" ] && _params_json='{}'
  [[ $# -gt 0 ]] && shift 1
  # Remaining "$@" = legacy-args forwarded to legacy_fn on State 1.

  # ----- State 1: disk-presence gate ----------------------------------------
  # Route to legacy if the example-orchestration-hub invoke seam is not importable on disk.
  # This is the ONLY production condition that triggers the legacy path --
  # not liveness, not transport failure.
  #
  # COORDINATOR_FORCE_LEGACY=1 is a testing/parity affordance (see header):
  # opt-in, defaults off, forces this same legacy branch even when the seam
  # IS present, so a byte-parity harness can exercise the bash path
  # deterministically without fighting EXAMPLE_ORCHESTRATION_HUB_ROOT re-resolution.  It is NOT
  # a production fallback and NOT a 4th routing state -- State 3 (native
  # transport failure with the lever off) still fails loud unchanged; this
  # lever only ever bypasses native when explicitly set.
  # Review: code-reviewer — F6: if/else replaces early-return; no explicit return needed in
  # either branch (exit status of last command propagates automatically as function return).
  if [[ "${COORDINATOR_FORCE_LEGACY:-}" == "1" ]] || ! _sf_seam_present; then
    "$_legacy_fn" "$@"
  else
    # ----- States 2 / 3: native route via cc_invoke (DR-215 spawn-per-call) -----
    # cc_invoke spawns coordinator_core.invoke once per call (~59ms cold start).
    #   State 2 (invoke success): cc_invoke returns 0; bare result JSON on stdout.
    #   State 3 (transport failure): cc_invoke returns 2.
    # Propagate the exit status unconditionally; do NOT fall back to legacy.
    # Repo root is auto-resolved from PWD (standalone-repo assumption; no 4th positional).
    local _repo_root
    _repo_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)" || {
      printf 'strangler-facade.sh: cannot resolve git repo root from %s\n' "$PWD" >&2
      return 1
    }
    cc_invoke "$_op_name" "$_params_json" "$_repo_root"
  fi
  # Exit status of the last command propagates automatically as the function's
  # return value; no explicit `return` needed in either branch.
}

# ---------------------------------------------------------------------------
# Public: strangle_route_mutation
# ---------------------------------------------------------------------------
# Mutation-safe wrapper around strangle_route for ops whose structured result
# carries an error signal (NOT a verdict).  Identical three-state dispatch;
# additionally captures stdout and parses it for native error shapes so callers
# do not have to inspect .exit_code themselves.
#
# COORDINATOR_FORCE_LEGACY inheritance: this wrapper delegates entirely to
# strangle_route (Step 1 below), so the force-legacy testing lever documented
# there applies here automatically -- no separate handling needed.
#
# Usage:
#   strangle_route_mutation <op-name> <legacy_fn> [<params-json>] [legacy-args...]
#
# Catches two native error shapes:
#   (1) {exit_code:N, ...} with exit_code != 0  — handoff/memo _err shape
#       (coordinator_core/ops/handoff_transition.py _err, memo_transition.py _err)
#   (2) {error:"..."} without exit_code in an rc-0 result — completion.*/plan.* shape
#       (coordinator_core/ops/completion_ops.py lines 499,506,552,559 and plan ops)
#
# STDOUT PASSTHROUGH (load-bearing): the captured strangle_route stdout is
#   re-emitted verbatim on this function's stdout in EVERY branch — same contract
#   as bare strangle_route.  Callers that capture _sr_out (e.g.
#   reconcile-completion-commits.sh:537) depend on this for output normalization.
#   Diagnostics go to STDERR ONLY.
#
# Returns:
#   - non-zero rc from strangle_route (transport error OR legacy non-zero): verbatim
#   - else, if captured stdout is JSON with .exit_code present-and-non-zero:
#       print .error to stderr, re-emit stdout, return that exit_code
#   - else, if captured stdout is JSON with top-level .error present-and-truthy
#     (non-empty string; exit_code absent or 0):
#       print .error to stderr, re-emit stdout, return 1
#   - else: re-emit stdout, return 0
#
# Negative-spec:
#   - Does NOT catch verdict ops: handoff.has_live_children exit_code=1 is a verdict
#     (a normal answer), not an error.  Verdict-op callers use bare strangle_route and
#     parse .exit_code themselves; they NEVER call this helper.
#   - Does NOT catch advisory callers (changelog.backfill_gaps, changelog.append_day)
#     that intentionally ignore op failures — those stay on bare strangle_route.
#   - Does NOT add a jq hard dependency: JSON parsing uses the same inline python3
#     approach as cc_invoke (coordinator-core-invoke.sh lines 189-205).
#   - Does NOT modify the CLI (invoke/__main__.py): exit_code is overloaded for
#     verdict ops; a blanket CLI map would regress archive guards.
#
# Spec backlink: docs/plans/2026-07-06-mutation-transition-exit-code-honoring.md
#   § Fix — a shared mutation-check helper
strangle_route_mutation() {
  local _op_name="${1:?strangle_route_mutation: op-name required}"
  local _legacy_fn="${2:?strangle_route_mutation: legacy_fn required}"
  # All args ($@ = op-name legacy_fn [params-json] [legacy-args...]) forwarded verbatim to strangle_route, which shares the same positional interface.
  # Review: code-reviewer — Finding 4: old comment implied only $3+ forwarded; $@ includes $1/$2 too (no shift needed, code is correct)

  # Step 1: Capture strangle_route stdout and rc.
  # NEVER set +e / set -e inside this function: set is a global shell option, not
  # function-scoped; a set +e here disables errexit in the caller's shell after we
  # return, silently removing its fail-loud protection.
  # Review: code-reviewer — Finding 5: old comment described hazard backwards ("bash exits" vs. "bash stops exiting on errors")
  local _srm_out _srm_rc
  _srm_rc=0
  _srm_out="$(strangle_route "$@")" || _srm_rc=$?

  # Step 2: Non-zero rc from strangle_route — transport error or legacy node
  # non-zero exit.  Re-emit captured stdout; propagate rc verbatim.
  # (Legacy path is fully covered here — node exits non-zero; no JSON parse needed.)
  if [[ "${_srm_rc}" -ne 0 ]]; then
    printf '%s' "${_srm_out}"
    return "${_srm_rc}"
  fi

  # Step 3: rc=0 — parse captured stdout as JSON to detect native structured errors.
  # Mirror the inline-python3 approach from cc_invoke (coordinator-core-invoke.sh:189-205);
  # no jq hard dependency.
  #
  # Python3 emits 2–3 newline-terminated lines: STATUS, EXIT_CODE[, ERROR_MSG].
  # ERROR_MSG is omitted for the "ok" status.
  #   STATUS = "ok"              — no error detected; re-emit, return 0
  #   STATUS = "exit_code_error" — {exit_code:N} shape; return that code
  #   STATUS = "error_field"     — {error:"..."} shape, exit_code absent/0; return 1
  # Review: code-reviewer — Finding 3: "ok" path emits only 2 lines (no ERROR_MSG), comment said 3
  # Line-number parsing with sed (always exits 0) avoids grep's non-zero-on-no-match
  # which would trigger pipefail with set -eo pipefail.
  local _parse_out _parse_status _parse_code _parse_msg
  _parse_out="$(printf '%s' "${_srm_out}" | python3 -c '  # popup-safe-env-suppressed
import json, sys
raw = sys.stdin.read()
try:
    j = json.loads(raw)
except Exception:
    sys.stdout.write("ok\n0\n")
    sys.exit(0)
if not isinstance(j, dict):
    sys.stdout.write("ok\n0\n")
    sys.exit(0)
ec = j.get("exit_code")
err = j.get("error")
if ec is not None:
    try:
        ec_int = int(ec)
    except (TypeError, ValueError):
        ec_int = 0
    if ec_int != 0:
        sys.stdout.write("exit_code_error\n" + str(ec_int) + "\n" + (str(err) if (err and isinstance(err, str)) else "<no error message in result>") + "\n")
        # Review: code-reviewer — Finding 6: reuse already-extracted err; guard against empty/absent .error symmetric with error_field truthy check
        sys.exit(0)
if err and isinstance(err, str) and len(err) > 0:
    sys.stdout.write("error_field\n1\n" + err + "\n")
    sys.exit(0)
sys.stdout.write("ok\n0\n")
' 2>/dev/null)" || {
    # python3 subprocess failed — treat as non-JSON success; passthrough.
    printf '%s' "${_srm_out}"
    return 0
  }

  # Parse structured output from python3.
  # sed -n 'Np' always exits 0 (no grep non-match hazard under pipefail).
  _parse_status="$(printf '%s\n' "${_parse_out}" | sed -n '1p')"
  _parse_code="$(printf '%s\n' "${_parse_out}" | sed -n '2p')"
  _parse_msg="$(printf '%s\n' "${_parse_out}" | sed -n '3p')"

  case "${_parse_status}" in
    exit_code_error)
      # Step 3a: {exit_code:N} shape — handoff/memo _err path.
      printf '%s\n' "${_parse_msg}" >&2
      printf '%s' "${_srm_out}"
      return "${_parse_code}"
      ;;
    error_field)
      # Step 3b: {error:"..."} without exit_code — completion.*/plan.* shape.
      printf '%s\n' "${_parse_msg}" >&2
      printf '%s' "${_srm_out}"
      return 1
      ;;
    *)
      # Step 3c: ok, non-JSON, or empty — passthrough, return 0.
      printf '%s' "${_srm_out}"
      return 0
      ;;
  esac
}
