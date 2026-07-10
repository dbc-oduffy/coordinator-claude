#!/usr/bin/env bash
# handoff-has-live-children.sh — reverse-membership guard: is a handoff still a live parent?
#
# Usage: handoff-has-live-children.sh [--exclude <path>]... [--edge-kinds <csv>] <candidate-handoff-path>
#
# Note: --live-set-json (legacy flag) has been retired per D5 (pcore-03 plan).
# coordinator_core owns live-set resolution internally; a second liveness source is banned.
# Callers that previously passed --live-set-json must be updated to use the cc_invoke path.
#
# Exit codes:
#   0 — has live children (do NOT archive — candidate is still referenced by a live handoff)
#   1 — safe to archive (no live handoff names this candidate as predecessor/additional_predecessor/forked_from,
#       after all --exclude paths are dropped from the live set)
#   2 — internal error / indeterminate (fail-closed): caller decides.
#       Archival callers MUST treat {0,2} as do-not-archive (same conservative contract as before).
#       The review-coverage consumer MUST treat 2 as INDETERMINATE → FAIL-THE-VERDICT (distinct from 0).
#
# Fail-closed on ANY internal error / engine error / cc_invoke failure:
#   → exits 2 (indeterminate, do-not-archive) + diagnostic to stderr
#   This script is wired into the every-session session-init hook; fail-open would risk
#   archiving a live merge-parent.
#
# Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C6 / KD-5 / AC8
# DR-215: migrated from UDS/daemon transport to cc_invoke (command-type, spawn-per-call).
#         coordinator_core is now COMMAND-TYPE; there is no resident service, no UDS socket,
#         and no stale-service gate (fresh process per call). The degrade flag is removed.
#
# - stdlib-only direct imports — coordinator_core is spawned via cc_invoke, not imported.
# - Does NOT open any UDS socket — the daemon and socket path are retired (DR-215).
# - Does NOT read or require any auth token — the command path bypasses IPC auth.
# - _origin_worktree is NOT passed — invoke auto-injects it (handoff.has_live_children ∈ WORKTREE_SCOPED_OPS).
# - python3 spawns below are POSIX-only (no CREATE_NO_WINDOW needed; no Windows console).
# popup-safe-env-suppressed

set -euo pipefail

# ---------------------------------------------------------------------------
# bash≥4 guard (fail-loud for associative arrays / mapfile / ${v^^})
# NOTE: this script does NOT use bash-4-only syntax in the script body itself,
# so the guard is reachable even under bash 3.2. Added as a forward-defensive
# guard per DR-148; remove only if the script is intentionally 3.2-compatible.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "handoff-has-live-children.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 2  # internal error / indeterminate
fi

# ---------------------------------------------------------------------------
# Argument parsing — flag + positional
# Flags: --exclude <path> (repeatable), --edge-kinds <csv>
# Positional: <candidate-handoff-path> (last non-flag argument)
# ---------------------------------------------------------------------------
EXCLUDE_PATHS=()
EDGE_KINDS_CSV="predecessor,additional_predecessors,forked_from"
CANDIDATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --exclude)
      if [[ -z "${2-}" ]]; then
        echo "handoff-has-live-children.sh: --exclude requires an argument" >&2
        exit 2
      fi
      EXCLUDE_PATHS+=("$2")
      shift 2
      ;;
    --edge-kinds)
      if [[ -z "${2-}" ]]; then
        echo "handoff-has-live-children.sh: --edge-kinds requires an argument" >&2
        exit 2
      fi
      EDGE_KINDS_CSV="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "handoff-has-live-children.sh: unknown flag: $1" >&2
      exit 2
      ;;
    *)
      CANDIDATE="$1"
      shift
      ;;
  esac
done

# Accept any remaining positional arg after -- as candidate (if not already set)
if [[ $# -gt 0 && -z "$CANDIDATE" ]]; then
  CANDIDATE="$1"
fi

if [[ -z "$CANDIDATE" ]]; then
  echo "handoff-has-live-children.sh: missing argument: <candidate-handoff-path>" >&2
  exit 2  # internal error / indeterminate
fi

if [[ ! -f "$CANDIDATE" ]]; then
  echo "handoff-has-live-children.sh: candidate not found on disk: ${CANDIDATE}" >&2
  exit 2  # internal error / indeterminate
fi

# ---------------------------------------------------------------------------
# Locate coordinator root (this script lives at <coordinator_root>/bin/)
# Source the single transport seam — cc_invoke resolves EXAMPLE_ORCHESTRATION_HUB_ROOT/PYTHONPATH internally.
# Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § KD-0
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=../lib/coordinator-core-invoke.sh
source "${SCRIPT_DIR}/../lib/coordinator-core-invoke.sh" || {
  echo "handoff-has-live-children.sh: failed to source coordinator-core-invoke.sh" >&2
  echo "  Expected at: ${SCRIPT_DIR}/../lib/coordinator-core-invoke.sh" >&2
  exit 2
}

CANDIDATE_ABS="$(cd "$(dirname "$CANDIDATE")" && pwd)/$(basename "$CANDIDATE")"

# ---------------------------------------------------------------------------
# Resolve repo root from candidate's directory (git -C <candidate-parent>).
# Candidate-first discovery allows the test harness to exercise fixture repos
# (e.g. contract_repo with its own .git) so both the Python IPC path and the
# bash RPC client target the same coordinator_core instance (AC5 / C9 wire path).
# Production handoffs live in <repo>/state/handoffs/, so candidate-dir discovery
# always resolves the correct per-repo coordinator_core.
# ---------------------------------------------------------------------------
REPO_ROOT=""
REPO_ROOT="$(git -C "$(dirname "$CANDIDATE_ABS")" rev-parse --show-toplevel 2>/dev/null)" || true
if [[ -z "$REPO_ROOT" ]]; then
  echo "handoff-has-live-children.sh: cannot resolve git repo root from candidate dir" >&2
  echo "  Candidate dir: $(dirname "$CANDIDATE_ABS")" >&2
  echo "  Remediation: ensure candidate file is inside a git repository" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Build params JSON for handoff.has_live_children.
# Params: {candidate (required), exclude (list[str]), edge_kinds (str)}.
# _origin_worktree is NOT passed — invoke auto-injects it for WORKTREE_SCOPED_OPS.
# python3 used for correct JSON escaping (always available; jq not assumed).
# ---------------------------------------------------------------------------
PARAMS_JSON=""
PARAMS_JSON="$(
python3 -c "  # popup-safe-env-suppressed
import json, sys
args = sys.argv[1:]
candidate = args[0]
edge_kinds = args[1]
exclude = args[2:] if len(args) > 2 else []
print(json.dumps({
    'candidate': candidate,
    'exclude': exclude,
    'edge_kinds': edge_kinds,
}, separators=(',', ':')))
" "$CANDIDATE_ABS" "$EDGE_KINDS_CSV" "${EXCLUDE_PATHS[@]+"${EXCLUDE_PATHS[@]}"}")" || {
  echo "handoff-has-live-children.sh: failed to build params JSON" >&2
  exit 2
}

# ---------------------------------------------------------------------------
# Invoke the engine via cc_invoke (command-type, spawn-per-call).
# cc_invoke emits the bare result object to stdout on success (rc 0) — callers
# parse TOP-LEVEL keys: .exit_code, .children[], .referenced, .live_session_count.
# NEVER .result.exit_code — cc_invoke already strips the jsonrpc/id/result wrapper.
#
# On any engine/transport error cc_invoke returns rc 2 and emits a diagnostic to
# stderr (distinguishes ImportError / timeout from op-error). Map rc 2 directly to
# this veneer's fail-closed exit 2 (indeterminate / do-not-archive).
#
# Single-liveness-source contract: the answer comes from invoke, NEVER a local grep.
# Spec backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § KD-5 / AC8
# ---------------------------------------------------------------------------
# Review: code-reviewer F4 — aligned variable naming to rcg's private-prefix convention
# (_HLC_RESULT / _hlc_rc instead of CC_RESULT / CC_RC) so cross-reading the two veneers is
# consistent and a future editor does not copy the unprefixed CC_ convention from this file.
_HLC_RESULT=""
_hlc_rc=0
_HLC_RESULT="$(cc_invoke "handoff.has_live_children" "${PARAMS_JSON}" "${REPO_ROOT}")" || _hlc_rc=$?

if [[ "${_hlc_rc}" -ne 0 ]]; then
  echo "handoff-has-live-children.sh: engine error (cc_invoke rc=${_hlc_rc}) — fail-closed; candidate retained" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Parse reply — print children paths to stdout (frozen contract: one per line),
# then extract and propagate exit_code 0/1/2 (KD-5 / AC8).
#
# cc_invoke emits the BARE result object; parse TOP-LEVEL keys (.children[], .exit_code).
# Exit is PURELY .exit_code-driven — DO NOT introduce a referenced-derived exit branch:
# referenced is ABSENT when exit_code==2 (engine indeterminate), so a referenced-branch
# misfires exactly when it must not. Satisfy "check exit_code before referenced" trivially
# by never reading referenced in the exit logic at all. (the Director of Engineering D6)
#
# python3 used for JSON parsing (always available; jq not assumed).
# ---------------------------------------------------------------------------

# Print each child path to stdout (mirrors legacy veneer's per-path echo)
python3 -c "  # popup-safe-env-suppressed
import json, sys
try:
    result = json.loads(sys.argv[1])
    for c in result.get('children', []):
        print(c)
except Exception:
    pass
" "$_HLC_RESULT" 2>/dev/null || true

# Extract exit_code from bare result object; validate it is in {0,1,2}; default to 2 on error.
# Exit is PURELY .exit_code-driven — no referenced-derived exit branch (the Director of Engineering D6).
HLC_EXIT_CODE=2
HLC_EXIT_CODE="$(python3 -c "  # popup-safe-env-suppressed
import json, sys
try:
    result = json.loads(sys.argv[1])
    ec = int(result.get('exit_code', 2))
    print(ec if ec in (0, 1, 2) else 2)
except Exception:
    print(2)
" "$_HLC_RESULT" 2>/dev/null)" || HLC_EXIT_CODE=2

exit "$HLC_EXIT_CODE"
