#!/usr/bin/env bash
# review-coverage-gate.sh — chain-end code-review coverage gate for
# /workstream-complete Step 2.9 and /merge-to-main.
#
# Purpose: verifies mechanically that every commit in a workstream's chain diff
# is covered by at least one code-reviewer trail record. Closes the gap where
# a confident EM substitutes handoff prose for per-commit review reconciliation.
#
# Output (stdout): one line in the form:
#   range=<range> chain_commits=N covered=M uncovered=K VERDICT={COVERED|UNCOVERED|INDETERMINATE}
# On UNCOVERED: also emits one "uncovered: <sha> <subject>" line per gap to stderr.
# On INDETERMINATE: emits "note: <reason>" lines to stderr.
#
# Exit: 0 on COVERED or UNCOVERED (verdict-line shape, matching
# review-brightline-gate.sh). Exit 2 on INDETERMINATE — the calling skill
# treats exit 2 as a halt; this gate never owns the COVERED/UNCOVERED halt.
# Review: code-reviewer F2 — exit 2 / INDETERMINATE documented; prior text omitted it.
#
# Usage:
#   review-coverage-gate.sh [--scope-paths <pathspec>...] [<range>]
#
#   <range>                  git rev-range; default: $(git merge-base origin/main HEAD)..HEAD
#   --scope-paths <paths>... Scope the CHAIN set to commits touching these paths (via
#                            `git rev-list --no-merges <range> -- <paths>`). The REVIEWED
#                            set is NEVER path-filtered — any session's trail record that
#                            covers a commit credits that commit, regardless of which paths
#                            the record was scoped to.
#
# Missing/empty --scope-paths: falls back to unscoped whole-chain (not an error).
# See Design § "Scope filtering — asymmetric by design" for the full rationale.
#
# Key design decisions (see plan Design § for full rationale):
#
#   --no-merges on chain_set (DELIBERATE):
#     Merge commits carry no authored diff that requires review. Additionally,
#     path-history-simplification without --no-merges can non-deterministically
#     include merge commits on shared branches, making chain_set non-reproducible.
#     Merge commits are excluded from chain_set by design, not by accident.
#
#   Unscoped reviewed_set (DELIBERATE — opposite of review-brightline-gate.sh):
#     review-brightline-gate.sh narrows to --session-id to avoid false PARTITION-
#     MANDATORY verdicts from peer commits that are already reviewed. The coverage
#     gate must do the REVERSE: credit ALL sessions' trail records toward the union
#     reviewed_set. A commit reviewed by any session is covered. Scoping reviewed_set
#     to one session would cause false UNCOVERED verdicts on multi-session features —
#     exactly the failure shape this gate is designed to catch.
#
# C5 (DR-215): veneer transport migrated from UDS/nc to command-type cc_invoke.
# Frozen CLI contract preserved exactly. Legacy swarm body removed (dead code — UDS retired DR-215).
#
# Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C3
# DR-215 backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C5

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Script-dir resolution — locate lib/ for coordinator-core-invoke.sh
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../lib"

# ---------------------------------------------------------------------------
# Argument parsing: --scope-paths, --from-handoff, and optional positional range
# ---------------------------------------------------------------------------
declare -a SCOPE_PATHS=()
RANGE_ARG=""
FROM_HANDOFF=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope-paths)
      shift
      # Consume all remaining non-flag args as pathspecs until we see a bare --
      # or a known flag.
      while [[ $# -gt 0 && "$1" != "--" && "$1" != --* ]]; do
        SCOPE_PATHS+=("$1")
        shift
      done
      ;;
    --from-handoff)
      shift
      FROM_HANDOFF="${1:-}"
      if [[ -z "$FROM_HANDOFF" ]]; then
        echo "review-coverage-gate.sh: --from-handoff requires a path argument" >&2
        exit 1
      fi
      shift
      ;;
    --)
      shift
      # Everything after -- is the range
      if [[ $# -gt 0 ]]; then
        RANGE_ARG="$1"
        shift
      fi
      ;;
    -*)
      echo "review-coverage-gate.sh: unknown option: $1" >&2
      exit 1
      ;;
    *)
      RANGE_ARG="$1"
      shift
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve the chain range
# ---------------------------------------------------------------------------
# Review: code-reviewer F4 — validate the caller-supplied range against the same
# no-leading-dash pattern the core applies to untrusted trail-JSON sha_range. The
# core's SAFE_RANGE protects trail data, not this gate's own positional range arg;
# without this guard a leading-dash range (e.g. "--output=/x..y") would reach
# `git rev-list` as a flag. Hardening the direct-invocation path to parity with the
# trail-JSON path.
if [[ -n "${RANGE_ARG:-}" ]]; then
  if ! [[ "$RANGE_ARG" =~ ^[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*\.\.\.?[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*$ ]]; then
    echo "review-coverage-gate.sh: unsafe range argument: ${RANGE_ARG}" >&2
    exit 1
  fi
fi

if [[ -z "${RANGE_ARG:-}" ]]; then
  if [[ -n "${FROM_HANDOFF:-}" ]]; then
    # DAG mode: chain_set is derived from the DAG; the flat git range is not needed.
    # Use a descriptive label so the output verdict line is readable.
    RANGE="dag:$(basename "${FROM_HANDOFF}")"
  else
    MERGE_BASE=$(git merge-base origin/main HEAD 2>/dev/null) || {
      echo "review-coverage-gate.sh: cannot resolve origin/main — pass a range explicitly" >&2
      exit 1
    }
    RANGE="${MERGE_BASE}..HEAD"
  fi
else
  RANGE="$RANGE_ARG"
fi

# Review: code-reviewer F2 — warn when --scope-paths is passed in DAG mode; the paths are
# silently ignored (DAG chain_set derives from session-segment trailers, not a path filter).
# SKILL.md template notes SCOPE_ARGS is flat-range-only; in DAG mode pass it empty/omit.
if [[ -n "${FROM_HANDOFF:-}" && ${#SCOPE_PATHS[@]} -gt 0 ]]; then
  echo "review-coverage-gate.sh: WARNING: --scope-paths is ignored in DAG mode (chain_set derives from session-segment trailers, not path filter)" >&2
fi

# Review: code-reviewer F6 — warn when both --from-handoff and a positional RANGE_ARG are set.
# When FROM_HANDOFF is set the params block sends 'from_handoff' (not 'range') to coordinator_core,
# so RANGE_ARG is silently dropped. Surface the drop to callers to prevent silent debugging hazards.
if [[ -n "${FROM_HANDOFF:-}" && -n "${RANGE_ARG:-}" ]]; then
  echo "review-coverage-gate.sh: WARNING: positional range argument (${RANGE_ARG}) is ignored when --from-handoff is set (DAG mode; coordinator_core receives from_handoff, not range)" >&2
fi

# ---------------------------------------------------------------------------
# Invoke coordinator_core via cc_invoke (DR-215 command-type transport)
#
# Replaces the retired UDS/socket transport (DR-215). cc_invoke sources
# coordinator-core-invoke.sh, resolves EXAMPLE_ORCHESTRATION_HUB_ROOT/PYTHONPATH internally,
# and emits the BARE result object (no jsonrpc/id wrapper) on success (rc 0).
# rc 2 = fail-CLOSED (transport/engine error) — the op could not run.
#
# Top-level keys in the bare result: .exit_code, .verdict_line, .notes
# NEVER .result.exit_code — cc_invoke strips the envelope wrapper (KD-0 / D1).
#
# Does NOT open any UDS/AF_UNIX socket — the daemon and socket path are retired (DR-215).
# Does NOT perform a version-drift pre-check — command-type spawn uses current source every
# call; version drift is impossible and that machinery is deleted (DR-215).
# ---------------------------------------------------------------------------

# Source the shared invoke helper (idempotent; resolves EXAMPLE_ORCHESTRATION_HUB_ROOT / PYTHONPATH).
# shellcheck source=../lib/coordinator-core-invoke.sh
source "${LIB_DIR}/coordinator-core-invoke.sh" || {
  echo "review-coverage-gate.sh: failed to source coordinator-core-invoke.sh" >&2
  exit 1
}

# Resolve repo root — required by cc_invoke --repo.
_RCG_REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "review-coverage-gate.sh: cannot find git repo root" >&2
  exit 1
}

# Build coverage.gate params as compact JSON.
# python3 handles safe encoding of paths/strings (special chars in from_handoff/scope_paths).
# coverage.gate op params: {range?, from_handoff?, scope_paths?} — pass only what is provided.
# _origin_worktree is NOT passed; the invoke entrypoint auto-injects it for worktree-scoped ops.
# popup-safe-env-suppressed (POSIX-only veneer; bash exec, not subprocess.run)
# Review: code-reviewer F5 — ${RANGE} (not ${RANGE:-}): RANGE is always non-empty at this point;
# all three branches of the range-resolution block above assign it unconditionally. FROM_HANDOFF
# keeps its ':-' guard (it can be unset/empty). Dead fallback removed — invariant is now visible.
_RCG_PARAMS=$(python3 -c "
import json, sys
from_hf     = sys.argv[1]
range_arg   = sys.argv[2]
scope_paths = sys.argv[3:]
params = {}
if from_hf:
    params['from_handoff'] = from_hf
else:
    if range_arg:
        params['range'] = range_arg
    if scope_paths:
        params['scope_paths'] = scope_paths
print(json.dumps(params, separators=(',', ':')), end='')
" "${FROM_HANDOFF:-}" "${RANGE}" "${SCOPE_PATHS[@]+"${SCOPE_PATHS[@]}"}") || {
  echo "review-coverage-gate.sh: failed to build coverage.gate params" >&2
  exit 1
}

# Dispatch via cc_invoke. rc 0 = success (bare result on stdout); rc 2 = transport fail-closed.
_RCG_RESULT=""
_rcg_rc=0
_RCG_RESULT=$(cc_invoke "coverage.gate" "${_RCG_PARAMS}" "${_RCG_REPO_ROOT}") || _rcg_rc=$?

if [[ "${_rcg_rc}" -ne 0 ]]; then
  # Engine error (transport fail-closed) — cc_invoke already emitted a diagnostic above.
  # Exit 1 is the existing RPC-error/empty fail-closed code for this veneer (KD-5 / AC8).
  # Under command-type, version drift is impossible; this is a generic engine-error diagnostic.
  echo "review-coverage-gate.sh: engine could not compute a verdict (cc_invoke rc=${_rcg_rc})" >&2
  echo "  Verify EXAMPLE_ORCHESTRATION_HUB_ROOT and coordinator_core installation (see diagnostics above)" >&2
  exit 1
fi

# Parse and emit the verdict.
# Bare result object top-level keys (D1 — NEVER .result.X; cc_invoke stripped the wrapper):
#   .exit_code  — 0=COVERED, 1=UNCOVERED, 2=INDETERMINATE; propagated as this veneer's exit.
#   .verdict_line — echoed to stdout (normalized-stdout parity contract).
#   .notes      — emitted to stderr.
# popup-safe-env-suppressed (POSIX-only veneer; bash exec, not subprocess.run)
_RCG_RESULT="$_RCG_RESULT" python3 -c "
import json, os, sys

raw = os.environ.get('_RCG_RESULT', '')
try:
    result = json.loads(raw)
except (json.JSONDecodeError, ValueError) as exc:
    print('review-coverage-gate.sh: malformed result from cc_invoke: ' + str(exc),
          file=sys.stderr)
    sys.exit(1)

verdict  = result.get('verdict_line', '')
# Review: code-reviewer F3 — 'or []' handles both absent key (default=[]) and explicit
# null (result.get returns None when key present with null; the default only fires on absent).
# Without this guard, 'for note in None' raises TypeError; a non-list string iterates chars.
notes    = result.get('notes') or []
if not isinstance(notes, list):
    notes = []
# Review: code-reviewer F2 — guard int() against null/non-numeric exit_code; bare int(None)
# raises TypeError, not caught by the json.JSONDecodeError/ValueError handler above.
_exit_code_raw = result.get('exit_code', 1)
try:
    exitcode = int(_exit_code_raw)
except (TypeError, ValueError):
    print(f'review-coverage-gate.sh: unexpected exit_code type from coordinator_core: {_exit_code_raw!r}; treating as 1', file=sys.stderr)
    exitcode = 1

if exitcode not in (0, 1, 2):
    print(f'review-coverage-gate.sh: unexpected exit_code from coordinator_core: {exitcode}; treating as 1', file=sys.stderr)
    exitcode = 1

# Review: code-reviewer F1 — INDETERMINATE (exit_code==2) must propagate even when verdict_line
# is empty. The empty-verdict guard below exits 1; without this check a malformed INDETERMINATE
# result (empty verdict_line) is silently demoted from exit 2 (halt) to exit 1 (engine-error).
if exitcode == 2:
    sys.exit(2)

if not verdict:
    print('review-coverage-gate.sh: coordinator_core returned empty verdict_line', file=sys.stderr)
    sys.exit(1)

print(verdict)
for note in notes:
    print(note, file=sys.stderr)

sys.exit(exitcode)
"
