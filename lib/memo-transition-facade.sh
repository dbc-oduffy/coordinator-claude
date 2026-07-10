#!/usr/bin/env bash
# coordinator/lib/memo-transition-facade.sh — DR-210 memo.transition facade seam.
#
# Purpose: exposes _cs_memo_transition_route <verb> <memo> [flag-args...] as a
# three-state facade over the memo-transition.js node CLI, routing via
# strangle_route (strangler-facade.sh) so callers get native coordinator_core
# dispatch when the seam is present, legacy node invocation when absent.
#
# Spec backlink: DR-210 (docs/decisions/DR-210-cross-repo-memo-strangle.md)
# Strang-09 chunk: C4 (unarmed; coordinator-archive-stamp.sh body-swap is C5, held)
#
# Three-state routing model — see strangler-facade.sh header for full contract.
#   State 1 (seam absent)  -> legacy_memo_transition: node memo-transition.js directly.
#   State 2 (seam present)  -> cc_invoke spawns coordinator_core.invoke per-call; exits 0 on success.
#   State 3 (unreachable)   -> cc_invoke exits 2 (fail-closed); propagated, no legacy fallback.
# Review: code-reviewer — F2: replaced stale "C1 client" / "idle daemon" pre-DR-215 text.
#
# shell-opts note (C5): strangler-facade.sh sets file-scope set -uo pipefail; sourcing it
# here propagates those opts — containment when this facade is later sourced into
# coordinator-archive-stamp.sh is C5's responsibility, not C4's.
#
# Cross-platform: bash >=4 required (via strangler-facade.sh); BSD-portable.
# Safe to source multiple times (function redefinition is idempotent).
# Review: code-reviewer — F5: corrected false >=3.2 claim; strangler-facade.sh bash-<4 guard fires,
# leaving strangle_route undefined on bash 3.2.

# ---------------------------------------------------------------------------
# Source the shared three-state router (idempotent; function redefinition safe).
# NOTE: set -uo pipefail propagates from strangler-facade.sh at file scope.
# ---------------------------------------------------------------------------
_MTF_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./strangler-facade.sh
source "${_MTF_LIB_DIR}/strangler-facade.sh"

# ---------------------------------------------------------------------------
# Public: _cs_memo_transition_route
# ---------------------------------------------------------------------------
# Routes a memo-transition operation through the three-state facade.
#
# Usage:
#   _cs_memo_transition_route <verb> <memo> [flag-args...]
#
#   verb       — claim | action | release
#   memo       — path to the memo markdown file (absolutized if relative — AC9)
#   flag-args  — verb-specific flags forwarded verbatim to memo-transition.js:
#                  claim:   --session-id <id> --at <ISO>
#                  action:  --decision <val> --decision-note <text> --realized-by <ptr>
#                           | --actioned-note <text>
#                  release: (none)
#
# cli_path resolution: resolved from THIS FILE's own bin/ sibling at call time.
# The facade owns this resolution; example-orchestration-hub does NOT reach into DoE.
# NOTE: native memo.transition no longer receives cli_path in params (it is
# inert there per DR-215 native port); legacy State-1 still execs via $_cli_path.
#
# Negative-spec:
#   - Does NOT call coordinator-archive-stamp.sh wrapper functions (that is C5).
#   - Does NOT fall back to legacy after native transport failure (State 3).
#   - Does NOT probe daemon liveness — that is the C1 client's concern.
#   - Does NOT call machine-local get CLI (bootstrap-hazard, Design pin 4).
_cs_memo_transition_route() {
  local _verb="${1:?_cs_memo_transition_route: verb (claim|action|release) required}"
  local _memo_arg="${2:?_cs_memo_transition_route: memo path required}"
  shift 2
  # "$@" now = flag-args only (e.g. --session-id <id> --at <ISO> for claim)

  # (a) AC9: absolutize memo path against caller CWD.
  # If not absolute, prefix with pwd so both native (params JSON) and legacy
  # (reconstructed node argv) receive a path that survives CWD changes.
  local _abs_memo
  if [[ "$_memo_arg" == /* ]]; then
    _abs_memo="$_memo_arg"
  else
    _abs_memo="$(pwd)/${_memo_arg}"
  fi

  # (b) Resolve memo-transition.js CLI from THIS FILE's own bin/ sibling.
  # BASH_SOURCE[0] inside a function is the file where the function is defined
  # (memo-transition-facade.sh), regardless of where it was sourced from.
  # The facade knows its own bin/; example-orchestration-hub does NOT reach into DoE.
  local _cli_path
  _cli_path="$(cd "$(dirname "${BASH_SOURCE[0]}")/../bin" && pwd)/memo-transition.js"

  # (c) Parse flag-args and build op params JSON inline with jq.
  # Mirrors the inline-jq pattern from append-goal-event.sh / emit-cockpit-snapshot.sh
  # (the strang-01 body-swaps). All flag slots included; empty -> null in JSON.
  local _session_id="" _at="" _decision="" _decision_note="" _realized_by="" _actioned_note=""
  local -a _flag_args=()
  [[ $# -gt 0 ]] && _flag_args=("$@")
  local _fi=0
  while [[ $_fi -lt ${#_flag_args[@]} ]]; do
    case "${_flag_args[$_fi]}" in
      --session-id)    _session_id="${_flag_args[$((_fi+1))]}";    _fi=$((_fi+1)) ;;
      --at)            _at="${_flag_args[$((_fi+1))]}";            _fi=$((_fi+1)) ;;
      --decision)      _decision="${_flag_args[$((_fi+1))]}";      _fi=$((_fi+1)) ;;
      --decision-note) _decision_note="${_flag_args[$((_fi+1))]}"; _fi=$((_fi+1)) ;;
      --realized-by)   _realized_by="${_flag_args[$((_fi+1))]}";   _fi=$((_fi+1)) ;;
      --actioned-note) _actioned_note="${_flag_args[$((_fi+1))]}"; _fi=$((_fi+1)) ;;
      # Review: code-reviewer — F9: unknown-flag arm; silently-swallowed flags could
      # eat the following token's value; fail-loud on unknown flags instead.
      *) printf '_cs_memo_transition_route: unknown flag: %s\n' "${_flag_args[$_fi]}" >&2; return 1 ;;
    esac
    _fi=$((_fi+1))
  done

  local _PARAMS
  _PARAMS="$(jq -cn \
    --arg verb           "$_verb" \
    --arg memo           "$_abs_memo" \
    --arg session_id     "$_session_id" \
    --arg at             "$_at" \
    --arg decision       "$_decision" \
    --arg decision_note  "$_decision_note" \
    --arg realized_by    "$_realized_by" \
    --arg actioned_note  "$_actioned_note" \
    '{
      verb:          $verb,
      memo:          $memo,
      session_id:    (if $session_id    == "" then null else $session_id    end),
      at:            (if $at            == "" then null else $at            end),
      decision:      (if $decision      == "" then null else $decision      end),
      decision_note: (if $decision_note == "" then null else $decision_note end),
      realized_by:   (if $realized_by   == "" then null else $realized_by   end),
      actioned_note: (if $actioned_note == "" then null else $actioned_note end)
    }')"

  # (d) Legacy fallback: invoke memo-transition.js directly via node.
  # Called only on State 1 (seam absent on disk) — never after native is attempted.
  # popup-safe-env-suppressed: node CLI; same allow-mark rationale as coordinator-archive-stamp.sh
  # memo verb calls — once-per-memo-transition, not a hot loop.
  # shellcheck disable=SC2317
  legacy_memo_transition() { node "$_cli_path" "$@"; }  # popup-safe-env-suppressed

  # (e) Three-state facade dispatch.
  # strangle_route decides: seam-absent -> legacy_memo_transition (State 1);
  #                         seam-present -> cc_invoke dispatches coordinator_core.invoke memo.transition.
  #
  # Legacy-args reconstructed as: verb --memo abs_memo [original-flag-args]
  # This is the argv shape memo-transition.js expects for all three verbs.
  # "$@" at this point = the flag-args originally passed to this function (after shift 2).
  strangle_route_mutation "memo.transition" legacy_memo_transition "$_PARAMS" \
    "$_verb" --memo "$_abs_memo" "$@"
}
