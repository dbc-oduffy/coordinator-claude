#!/usr/bin/env bash
# resolve-goal-candidates.sh — DoE-side client for the example-orchestration-hub goal.match_candidates op.
#
# Purpose: shells the example-orchestration-hub coordinator_core.invoke goal.match_candidates op and
# prints the raw candidates JSON to stdout.  Thin caller wrapper following the
# cc_invoke / strangler-facade.sh DR-215 transport pattern.
#
# Usage:
#   resolve-goal-candidates.sh --repo <repo-root> --text <text-to-match>
#
# Output: raw JSON object from the op, e.g.
#   {"candidates": [{"goal_id": "g1", "title": "Goal 1", "score": 0.85}, ...]}
#   On absence (no goals or seam absent): {"candidates": []}
#
# Exit codes:
#   0  — success; JSON printed to stdout
#   1  — bad args or repo-root unusable
#   2  — transport failure (cc_invoke fail-closed; see coordinator-core-invoke.sh)
#
# Wire contract (pinned per dispatch brief):
#   python3 -m coordinator_core.invoke goal.match_candidates '{"text":"<str>"}' --repo <repo>
#   returns {"candidates": [{goal_id, title, score}, ...]}
#   NOTE: the shipped op reads state/goals/*.yaml; may return empty if repo has no goals.
#
# Spec backlink: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § C4
#
# Negative-spec:
#   - Does NOT write any file.
#   - Does NOT fall back to a local bash impl when the seam is absent; exits 0 with
#     {"candidates": []} (caller can treat empty as "no suggestions available").
#   - Does NOT depend on a live example-orchestration-hub daemon — DR-215 spawn-per-call transport.

set -euo pipefail

# ── Bash >=4 guard (BSD macOS ships 3.2) ──────────────────────────────────────
if (( ${BASH_VERSINFO[0]:-0} < 4 )); then
  printf 'resolve-goal-candidates.sh: bash 4+ required (found %s).\n' "${BASH_VERSION:-unknown}" >&2
  printf '  Remediation: brew install bash (macOS) or apt install bash (Linux).\n' >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="${SCRIPT_DIR}/../lib"

# ── Arg parsing ───────────────────────────────────────────────────────────────
REPO_ROOT=""
TEXT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_ROOT="${2:-}"
      shift 2
      ;;
    --text)
      TEXT="${2:-}"
      shift 2
      ;;
    *)
      printf 'resolve-goal-candidates.sh: unknown arg: %s\n' "$1" >&2
      printf '  Usage: resolve-goal-candidates.sh --repo <repo-root> --text <text>\n' >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REPO_ROOT" ]]; then
  printf 'resolve-goal-candidates.sh: --repo is required\n' >&2
  exit 1
fi
if [[ -z "$TEXT" ]]; then
  # Empty text → empty candidates; not a usage error.
  printf '{"candidates": []}\n'
  exit 0
fi

if [[ ! -d "$REPO_ROOT" ]]; then
  printf 'resolve-goal-candidates.sh: repo root not a directory: %s\n' "$REPO_ROOT" >&2
  exit 1
fi

# ── Source cc_invoke transport seam (DR-215 spawn-per-call) ───────────────────
_CC_INVOKE_SH="${LIB_DIR}/coordinator-core-invoke.sh"
if [[ ! -f "$_CC_INVOKE_SH" ]]; then
  printf 'resolve-goal-candidates.sh: coordinator-core-invoke.sh not found at %s\n' "$_CC_INVOKE_SH" >&2
  printf '{"candidates": []}\n'
  exit 0
fi
# shellcheck source=../lib/coordinator-core-invoke.sh
source "$_CC_INVOKE_SH" || {
  printf 'resolve-goal-candidates.sh: failed to source coordinator-core-invoke.sh\n' >&2
  printf '{"candidates": []}\n'
  exit 0
}

# ── Seam presence check (mirrors _sf_seam_present in strangler-facade.sh) ────
_EXAMPLE_ORCHESTRATION_HUB_ROOT_SH="${LIB_DIR}/coordinator-example-orchestration-hub-root.sh"
_EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED=""
if [[ -f "$_EXAMPLE_ORCHESTRATION_HUB_ROOT_SH" ]]; then
  # shellcheck source=../lib/coordinator-example-orchestration-hub-root.sh
  source "$_EXAMPLE_ORCHESTRATION_HUB_ROOT_SH" 2>/dev/null || true
  _EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED="$(coordinator_example_orchestration_hub_root 2>/dev/null || true)"
fi

if [[ -z "$_EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED" ]]; then
  # Seam not resolvable — safe for a nudge: return empty candidates.
  printf '{"candidates": []}\n'
  exit 0
fi

# Test importability before dispatching.
if ! PYTHONPATH="${_EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -c 'import coordinator_core.invoke' 2>/dev/null; then  # popup-safe-env-suppressed
  # Seam absent on disk — return empty (fail-open; nudge can skip).
  printf '{"candidates": []}\n'
  exit 0
fi

# ── Build params JSON ─────────────────────────────────────────────────────────
# Escape text for JSON: replace backslash then double-quote, then newline/tab.
# Uses python3 (already required for cc_invoke) for safe serialisation.
PARAMS_JSON="$(python3 -c '  # popup-safe-env-suppressed
import json, sys
text = sys.argv[1]
print(json.dumps({"text": text}))
' "$TEXT")"

# ── Dispatch via cc_invoke ────────────────────────────────────────────────────
# cc_invoke exits 0 on success (bare result JSON on stdout), 2 on transport failure.
# Propagate transport failures as exit 2 per the contract.
_result=""
_cc_rc=0
_result="$(cc_invoke "goal.match_candidates" "$PARAMS_JSON" "$REPO_ROOT")" || _cc_rc=$?

if [[ "$_cc_rc" -ne 0 ]]; then
  # Transport failure — fail-closed for the caller; stderr already has diagnostics.
  exit "$_cc_rc"
fi

# Emit bare result JSON (already stripped of the jsonrpc wrapper by cc_invoke).
printf '%s\n' "$_result"
