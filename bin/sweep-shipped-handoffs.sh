#!/usr/bin/env bash
# sweep-shipped-handoffs.sh — batch sweep: find terminal handoffs, archive via coordinator-handoff-archive.sh.
#
# Purpose: finder+dispatcher over state/handoffs/*.md. Does NOT re-implement archival logic —
#   delegates each qualifying file to coordinator-handoff-archive.sh (no --stamp-shipped;
#   shipped handoffs are already stamped at /handoff or /workstream-complete time).
#
#   Coverage: the full TERMINAL class of deployment_state — shipped, abandoned, superseded —
#   not shipped-only. The filename is retained for reference-stability even though the
#   selector now covers the broader terminal set (orphan-reaper-flipped abandoned/superseded
#   handoffs are just as terminal as shipped ones and must not be stranded in state/handoffs/).
#   The fleet op fleet.archive_completed_handoffs is deployment_state-agnostic — its own
#   terminality predicate (status==consumed, childless, no live claim, re-verified at act-time)
#   is the safety net for the broadened selector.
#
# Usage:
#   sweep-shipped-handoffs.sh
#
# Env overrides:
#   SWEEP_STALE_THRESHOLD_DAYS — staleness threshold in days for the unresolvable WARNING
#                                 path (default: 14). Applies to the shipped subclass only
#                                 (see negative-spec below). Does not affect the 24h freshness veto.
#
# Negative-spec — retained-forever failure mode:
#   A handoff whose deployment_state is "shipped" but whose shipped_in SHA can no longer be
#   resolved — branch-tip commit gc'd after a squash/rebase merge to main, or an 8-char prefix
#   became ambiguous — is retained SILENTLY by the fail-closed posture. The only observable
#   signal is the WARNING line emitted when stale_unresolvable > 0 at sweep end.
#   This is intentional: archiving against an unresolvable SHA risks orphaning lineage; silent
#   retention is the correct fail-closed choice. This SHA-resolvability gate applies ONLY to the
#   shipped subclass — abandoned/superseded handoffs never carry a shipped_in SHA (they were
#   never shipped) and skip this gate entirely once past the 24h freshness veto.
#
# Exit codes:
#   0 — normal (including all-retained / empty tree / stale-unresolvable; retention is not an error)
#   2 — internal error (not inside a git repo)
#
# Spec: docs/plans/2026-07-01-shipped-handoff-archive-sweep.md
# Wraps: bin/coordinator-handoff-archive.sh (per-file primitive, 2026-06-30-session-terminator-mechanism-unification.md)
# BSD-portable bash>=4; GNU-isms guarded per DR-148.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash>=4 guard — must be reachable on bash 3.2 (plain comparison, no bash-4 syntax)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "sweep-shipped-handoffs.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 2
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
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then
    echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2
    exit 1
  fi
  PLUGIN_ROOT="$_doe_root/coordinator"
fi

# Source the state-root seam — must precede coordinator_state_root calls (C4 per-repo repoint)
_CSR_LIB_DIR="${PLUGIN_ROOT}/lib"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

# ---------------------------------------------------------------------------
# DR-210 facade router — source shared helper (strang-01 C8)
# Cold-fallback note (Design pin 4 / P3): legacy_sweep below uses PLUGIN_ROOT
# (resolved above via direct .doe-root file read) — NEVER 'machine-local get'
# CLI (unreachable in a cold session-init-hook shell). Both this script and
# coordinator-handoff-archive.sh are session-init-hook-invoked; direct-file-read
# cold-fallback is load-bearing. See grep-gate in strang07-c8.bats.
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"

# ---------------------------------------------------------------------------
# Staleness threshold for unresolvable WARNING (overridable via env)
# ---------------------------------------------------------------------------
STALE_THRESHOLD_DAYS="${SWEEP_STALE_THRESHOLD_DAYS:-14}"
STALE_THRESHOLD_SECS=$(( STALE_THRESHOLD_DAYS * 86400 ))

# ---------------------------------------------------------------------------
# Repo root — required for state/handoffs/ resolution
# ---------------------------------------------------------------------------
# Resolve state root via the per-repo seam (C4 seam-adoption).
# coordinator_state_root (no flag) returns $EXAMPLE_ORCHESTRATION_HUB_ROOT/state for the meta-repo,
# or $GIT_ROOT/state for sibling repos.
_ssh_state_root="$(coordinator_state_root)" || {
  echo "sweep-shipped-handoffs.sh: cannot resolve per-repo state root via coordinator_state_root" >&2
  exit 2
}
repo_root="${_ssh_state_root%/state}"

handoffs_dir="${_ssh_state_root}/handoffs"

# ---------------------------------------------------------------------------
# Counters — modified in place by process_file (not a subshell)
# ---------------------------------------------------------------------------
archived=0
unresolvable=0
stale_unresolvable=0

# ---------------------------------------------------------------------------
# Candidate accumulator — populated by process_file after pre-filters pass;
# dispatched in bulk via fleet.archive_completed_handoffs after the main loop.
# ---------------------------------------------------------------------------
_candidates=()

# ---------------------------------------------------------------------------
# legacy_sweep — verbatim capture of the original per-file dispatch path.
# Called ONLY on State 1 (coordinator_core.client absent on disk).
# Receives candidate file paths as positional args ("$@").
# Does NOT duplicate pcore-11 git-mv/T3-reverify (coordinator_core owns it).
# ---------------------------------------------------------------------------
legacy_sweep() {
  local _ls_f
  for _ls_f in "$@"; do
    [[ -f "$_ls_f" ]] || continue
    bash "${PLUGIN_ROOT}/bin/coordinator-handoff-archive.sh" "$_ls_f" \
      || echo "sweep-shipped-handoffs.sh: error archiving ${_ls_f}; skipping" >&2
  done
}

# ---------------------------------------------------------------------------
# Portable epoch seconds
# ---------------------------------------------------------------------------
now_secs="$(date +%s)"

# ---------------------------------------------------------------------------
# process_file <path>
#   Evaluates one handoff file and either archives it or retains it.
#   Called as: process_file "$f" || { log; continue; }
#   Returns 0 for all normal outcomes (including skip/retain).
#   A non-zero return indicates an unexpected error that the caller should log.
# ---------------------------------------------------------------------------
process_file() {
  local f="$1"

  # TOCTOU guard — first statement in per-file body; a concurrent /workday-start
  # git mv can vanish the file between glob-enumeration and per-file processing.
  # Must precede any stat/awk call.
  [[ -f "$f" ]] || return 0

  # Parse deployment_state from frontmatter (same awk pattern as sibling; strips whitespace)
  local deployment_state
  deployment_state="$(awk '
    !infm && /^---[[:space:]]*$/ { infm=1; next }
    infm && /^---[[:space:]]*$/ { exit }
    infm && /^deployment_state:/ {
      val=$0
      sub(/^deployment_state:[[:space:]]*/, "", val)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
      print val
      exit
    }
  ' "$f" 2>/dev/null || true)"

  # Only process terminal handoffs — the full terminal class, not shipped-only.
  # Any other deployment_state (awaiting_gate, ready_to_fire, in_flight) is skipped.
  # Review: code-reviewer — an EMPTY string (deployment_state: absent from frontmatter)
  # intentionally falls to the *) arm and is skipped, same as an unrecognized value.
  case "$deployment_state" in
    shipped|abandoned|superseded) ;;
    *) return 0 ;;
  esac

  # 24h freshness veto — skip files younger than 86400s. Applies to every terminal class.
  # Portable stat: GNU (-c %Y) then BSD (-f %m)
  local mtime
  mtime="$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f")"
  local age=$(( now_secs - mtime ))
  [[ "$age" -ge 86400 ]] || return 0

  # SHA-resolvability gate applies to the "shipped" subclass ONLY — abandoned/superseded
  # handoffs have no shipped_in SHA (they were never shipped), so running this gate on
  # them would falsely reject every abandoned/superseded handoff as "unresolvable".
  if [[ "$deployment_state" == "shipped" ]]; then
    # Parse shipped_in from frontmatter (same awk pattern as sibling; strips whitespace)
    local shipped_in
    shipped_in="$(awk '
      !infm && /^---[[:space:]]*$/ { infm=1; next }
      infm && /^---[[:space:]]*$/ { exit }
      infm && /^shipped_in:/ {
        val=$0
        sub(/^shipped_in:[[:space:]]*/, "", val)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
        print val
        exit
      }
    ' "$f" 2>/dev/null || true)"

    # Review: review-integrator B-F3 — strip a single matched pair of surrounding
    # quotes. serializeYamlScalar (coordinator/bin/lib/schema.js) single-quotes
    # all-digit values (SHA-shaped strings would otherwise YAML-coerce to int);
    # this awk-based reader must tolerate that quoting or an all-digit SHA prefix
    # (~2.3% of SHAs) fails the git cat-file lookup below.
    if [[ "$shipped_in" =~ ^\"(.*)\"$ || "$shipped_in" =~ ^\'(.*)\'$ ]]; then
      shipped_in="${BASH_REMATCH[1]}"
    fi

    # Resolvability check: empty / "null" shipped_in, or SHA not present in object store
    local sha="$shipped_in"
    if [[ -z "$sha" || "$sha" == "null" ]] || ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
      # Unresolvable shipped handoff — retain (fail-closed)
      (( unresolvable++ )) || true
      if [[ "$age" -ge "$STALE_THRESHOLD_SECS" ]]; then
        (( stale_unresolvable++ )) || true
      fi
      return 0
    fi
  fi

  # Pre-filters passed — add to candidate list for fleet dispatch.
  # The actual git-mv is routed via fleet.archive_completed_handoffs below.
  _candidates+=("$f")
}

# ---------------------------------------------------------------------------
# Main loop — iterate state/handoffs/*.md
# ---------------------------------------------------------------------------
if [[ -d "$handoffs_dir" ]]; then
  for f in "${handoffs_dir}"/*.md; do
    # Empty-glob guard: bash expands to literal pattern when no files match
    [[ -f "$f" ]] || continue

    process_file "$f" || {
      echo "sweep-shipped-handoffs.sh: error processing ${f}; skipping" >&2
      continue
    }
  done
fi

# ---------------------------------------------------------------------------
# Fleet dispatch via facade — route accumulated candidates to the fleet op.
# Pre-filters (deployment_state==shipped, >=24h freshness veto, resolvable
# shipped_in SHA) have already been applied; only confirmed candidates reach
# this point.
#
# State 1 (seam absent on disk): legacy_sweep dispatches
#   coordinator-handoff-archive.sh per-file — original behavior, verbatim.
# States 2/3: fleet.archive_completed_handoffs performs bulk git-mv via
#   example-orchestration-hub coordinator_core. Do NOT duplicate pcore-11 git-mv/T3-reverify.
#   The op self-commits its git-mv — do NOT add a ceremony-side git add/commit
#   of the moved paths (KD-2 / AC3).
# ---------------------------------------------------------------------------
if [[ "${#_candidates[@]}" -gt 0 ]]; then
  # Build repo-relative candidate IDs.
  # example-orchestration-hub archive_handoffs.py:266-269 matches strictly on repo-relative paths;
  # absolute paths produce silent "skipped:already-archived" mismatches (KD-6).
  _rel_candidates=()
  for _c in "${_candidates[@]}"; do
    _rel_candidates+=("${_c#${repo_root}/}")
  done

  _SWEEP_PARAMS="$(jq -cn \
    '{mode:"already-terminal",dry_run:false,candidate_ids:$ARGS.positional}' \
    --args "${_rel_candidates[@]}")"

  # Capture stdout to parse the bare result object (State 2: cc_invoke emits it).
  # In State 1 (legacy_sweep), stdout is non-JSON — python parse returns -1 sentinel.
  # TWO-SIGNAL contract: check strangle_route rc (transport), then parse .exit_code.
  _sweep_rc=0
  _sweep_out="$(strangle_route "fleet.archive_completed_handoffs" "legacy_sweep" \
    "$_SWEEP_PARAMS" "${_candidates[@]}")" || _sweep_rc=$?

  if [[ "${_sweep_rc}" -ne 0 ]]; then
    # State 3 transport fail-closed — log-and-continue (ceremony is best-effort).
    echo "sweep-shipped-handoffs.sh: fleet dispatch failed (rc=${_sweep_rc}); candidates retained" >&2
  else
    # Parse .acted[] from bare result object (State 2 / cc_invoke output).
    # AC3: .acted[] is non-empty when at least one handoff was actually archived.
    # On State 1 (non-JSON legacy_sweep output): python parse writes -1 sentinel;
    # fall back to counting all candidates (legacy_sweep archives all on success).
    _acted_count="$(printf '%s' "${_sweep_out:-}" \
      | python3 -c 'import json,sys;r=json.loads(sys.stdin.read());sys.stdout.write(str(len(r.get("acted",[])))+"\n")' \
        2>/dev/null || echo "-1")"  # popup-safe-env-suppressed
    if [[ "${_acted_count}" -lt 0 ]]; then
      # State 1 legacy path: all candidates archived by legacy_sweep.
      archived=$(( archived + ${#_candidates[@]} ))
    else
      archived=$(( archived + _acted_count ))
      # TWO-SIGNAL contract (AC7): parse op-level .exit_code for partial-success detection.
      # exit_code==2 (determinate-partial): some handoffs archived, some failed — log WARN and continue.
      # Review: code-reviewer — AC3/AC7: .exit_code second signal; mirrors prune-closed-bugs.sh:181-184
      _op_exit="$(printf '%s' "${_sweep_out:-}" \
        | python3 -c 'import json,sys;r=json.loads(sys.stdin.read());print(r.get("exit_code",0))' \
          2>/dev/null || echo "0")"  # popup-safe-env-suppressed
      if [[ "${_op_exit}" == "2" ]]; then
        echo "sweep-shipped-handoffs.sh: WARN: fleet.archive_completed_handoffs partial (exit_code=2, acted=${_acted_count}) — check example-orchestration-hub logs" >&2
      fi
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
# Review: code-reviewer — summary wording is class-neutral (terminal = shipped/abandoned/
# superseded); the old "shipped handoffs archived" phrasing was misleading once the
# selector broadened past shipped-only (Finding 1).
if [[ "$archived" -eq 0 ]]; then
  echo "no terminal handoffs archived"
else
  echo "${archived} terminal handoffs archived"
fi

if [[ "$unresolvable" -gt 0 ]]; then
  echo "${unresolvable} shipped handoffs retained (unresolvable SHA)"
fi

if [[ "$stale_unresolvable" -gt 0 ]]; then
  echo "WARNING: ${stale_unresolvable} shipped handoffs retained — shipped_in SHA no longer resolves"
fi

exit 0
