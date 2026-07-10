#!/usr/bin/env bash
# append-goal-event.sh — DR-210 facade router: goal.append (strang-01 C3).
#
# Purpose: routes goal.append through the example-orchestration-hub UDS client (native-primary)
# with the original script body preserved as legacy_append() (disk-absence fallback).
# Three-state routing model (Design pin 3):
#   State 1 (seam absent on disk) -> legacy_append (current bash body, byte-identical).
#   State 2 (seam present + daemon idle-shut) -> C1 client lazy-launches, then RPC.
#   State 3 (seam present + post-spawn unreachable) -> hard transport error, fail loud.
#
# Spec backlink: docs/plans/2026-07-04-strang-01-tc3-emission-port-facade-respin.md § C3
# Prior backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C2
#
# Usage (unchanged from pre-facade — zero caller repoints, AC8):
#   append-goal-event.sh --period <day|week|repo> --period-value <v>
#                        --text <s> [--repo <r>] [--root <p>]
#
# Exit codes (unchanged):
#   0 — success, goal event appended to per-machine JSONL log (or native op succeeded)
#   1 — hard precondition failed or validation failed (legacy path)
#   3 — native op: post-spawn transport failure (State 3, native path only)
set -euo pipefail

# ---------------------------------------------------------------------------
# DR-210 facade router -- source shared helper (C4b, must precede legacy_append).
# Cold-fallback self-location note (Design pin 4 / emission-conformance-contract
# SS CD-3): legacy_append resolves its DoE root via BASH_SOURCE[0]-relative paths
# (see _CSR_LIB_DIR inside the function), NEVER via `machine-local get` as a CLI.
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"

# ---------------------------------------------------------------------------
# legacy_append -- the pre-facade script body, preserved verbatim.
# Called ONLY on State 1 (coordinator_core.client absent on disk).
# BASH_SOURCE[0]-relative self-location inside the function is unchanged and
# safe (resolves to this script path, same as before the body-swap).
# ---------------------------------------------------------------------------
legacy_append() {
# append-goal-event.sh -- Append a single goal-event JSON line to state/goals-log.<machine>.jsonl (per-machine, append-only).
#
# Purpose: Pure-append helper that records a "goal event" into a per-machine
#          append-only JSONL log. Idempotent goal_id derived from content hash.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md SS C2
# Review: A-F15 -- fabricated plan path repointed to real plan
# Usage: append-goal-event.sh --period <day|week|repo> --period-value <v>
#                              --text <s> [--repo <r>] [--root <p>]

set -euo pipefail

# Bash >=4 guard (BSD macOS ships 3.2; brew bash required)
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# Source the state-root seam -- must precede coordinator_state_root calls
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

# ---------------------------------------------------------------------------
# Coordinator root -- cwd-scope guard (verbatim form, do NOT regroup)
# Git-ops root resolved via the shared seam (resolve-coordinator-clone.sh
# --for-git-ops) to support both flat and maximalist install shapes.
# COORDINATOR_ROOT_PATH defaults separately below; state writes use the seam.
# ---------------------------------------------------------------------------
_GIT_OPS_ROOT="$(bash "${_CSR_LIB_DIR}/resolve-coordinator-clone.sh" --for-git-ops 2>/dev/null || true)"

# ---------------------------------------------------------------------------
# Defaults for optional args
# ---------------------------------------------------------------------------
# Review: A-F8 -- do not hardcode private repo; derive from git remote at runtime.
# --repo override still works; empty default -> derive below after ROOT is set.
REPO=""
COORDINATOR_ROOT_PATH="."

# Required args (unset until parsed)
PERIOD=""
PERIOD_VALUE=""
TEXT=""

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --period)
      PERIOD="${2:-}"
      shift 2
      ;;
    --period-value)
      PERIOD_VALUE="${2:-}"
      shift 2
      ;;
    --text)
      TEXT="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --root)
      COORDINATOR_ROOT_PATH="${2:-}"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate required arguments
# ---------------------------------------------------------------------------
if [[ -z "$PERIOD" ]]; then
  echo "ERROR: --period is required (one of: day|week|repo)" >&2
  exit 1
fi

case "$PERIOD" in
  day|week|repo) ;;
  *)
    echo "ERROR: --period must be one of: day|week|repo (got: '$PERIOD')" >&2
    exit 1
    ;;
esac

if [[ -z "$PERIOD_VALUE" ]]; then
  echo "ERROR: --period-value is required" >&2
  exit 1
fi

if [[ -z "$TEXT" ]]; then
  echo "ERROR: --text is required" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Review: A-F8 -- derive REPO from git remote when --repo not supplied.
# Falls back to "local" when git is unavailable or no remote is configured.
# ---------------------------------------------------------------------------
if [[ -z "$REPO" ]]; then
  # Review: code-reviewer — guard against empty _GIT_OPS_ROOT; relying on `git -C ""` failing is implementation-dependent
  if [[ -n "$_GIT_OPS_ROOT" ]]; then
    REPO="$(git -C "${_GIT_OPS_ROOT}" remote get-url origin 2>/dev/null | sed -E 's#.*github.com[/:]##; s#\.git$##')"
  fi
  if [[ -z "$REPO" ]]; then
    REPO="local"
  fi
fi

# ---------------------------------------------------------------------------
# jq availability guard
# ---------------------------------------------------------------------------
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required but not found in PATH" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# sha1 helper -- prefer shasum (BSD/macOS), fall back to sha1sum (GNU/Linux)
# ---------------------------------------------------------------------------
sha1_hex() {
  local input="$1"
  if command -v shasum &>/dev/null; then
    printf '%s' "$input" | shasum -a 1 | awk '{print $1}'
  elif command -v sha1sum &>/dev/null; then
    printf '%s' "$input" | sha1sum | awk '{print $1}'
  else
    echo "ERROR: neither shasum nor sha1sum found in PATH" >&2
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Compute derived fields
# ---------------------------------------------------------------------------
DECLARED_BY_MACHINE="$(hostname)"
DECLARED_AT="$(date -u +%FT%TZ)"
STATUS="active"

# Deterministic goal_id: first 12 hex chars of sha1("<repo>|<root>|<period>|<period_value>|<text>")
HASH_INPUT="${REPO}|${COORDINATOR_ROOT_PATH}|${PERIOD}|${PERIOD_VALUE}|${TEXT}"
FULL_HASH="$(sha1_hex "$HASH_INPUT")"
GOAL_ID="${FULL_HASH:0:12}"

# ---------------------------------------------------------------------------
# Build JSON object (via jq -- never hand-concatenate)
# ---------------------------------------------------------------------------
JSON_LINE="$(jq -c -n \
  --arg goal_id              "$GOAL_ID" \
  --arg repo                 "$REPO" \
  --arg coordinator_root_path "$COORDINATOR_ROOT_PATH" \
  --arg period               "$PERIOD" \
  --arg period_value         "$PERIOD_VALUE" \
  --arg declared_by_machine  "$DECLARED_BY_MACHINE" \
  --arg declared_at          "$DECLARED_AT" \
  --arg text                 "$TEXT" \
  --arg status               "$STATUS" \
  '{
    goal_id:              $goal_id,
    repo:                 $repo,
    coordinator_root_path: $coordinator_root_path,
    period:               $period,
    period_value:         $period_value,
    declared_by_machine:  $declared_by_machine,
    declared_at:          $declared_at,
    text:                 $text,
    status:               $status
  }')"

# ---------------------------------------------------------------------------
# Ensure log directory exists; append (never rewrite)
# ---------------------------------------------------------------------------
# ENGINE (example-orchestration-hub): sole consumer emit-cockpit-snapshot.sh:1256 reads goals-log.*.jsonl — §Residency-Is-Not-Ownership; doctrine reclassification pending lockstep cockpit-read flip (improvement-queue entry)
LOG_DIR="$(coordinator_state_root --central)"
# Per-machine append-only log: machine slug keeps concurrent appends in separate
# files so they never git-conflict (the Data Science Reviewer P1-D6). The emitter globs all
# per-machine logs and derives latest-wins per (repo,root,period,period_value).
MACHINE_SLUG="$(printf '%s' "$DECLARED_BY_MACHINE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"
LOG_FILE="${LOG_DIR}/goals-log.${MACHINE_SLUG}.jsonl"

mkdir -p "$LOG_DIR"
printf '%s\n' "$JSON_LINE" >> "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# Build goal.append params JSON from CLI args.
# Maps --period, --period-value, --text, --repo, --root to the goal.append
# op params (coordinator_core/ops/goal_append.py: period, period_value, text,
# repo, coordinator_root_path). Safe JSON construction via jq avoids injection.
# Empty --repo maps to null so the Python op resolves it from context (D7a).
# ---------------------------------------------------------------------------
_GOAL_PERIOD=""
_GOAL_PERIOD_VALUE=""
_GOAL_TEXT=""
_GOAL_REPO=""
_GOAL_ROOT="."
_goal_args=("$@")
for (( _gai=0; _gai<${#_goal_args[@]}; _gai++ )); do
  case "${_goal_args[_gai]}" in
    --period)       _GOAL_PERIOD="${_goal_args[$((_gai+1))]:-}";       _gai=$((_gai+1)) ;;
    --period-value) _GOAL_PERIOD_VALUE="${_goal_args[$((_gai+1))]:-}"; _gai=$((_gai+1)) ;;
    --text)         _GOAL_TEXT="${_goal_args[$((_gai+1))]:-}";         _gai=$((_gai+1)) ;;
    --repo)         _GOAL_REPO="${_goal_args[$((_gai+1))]:-}";         _gai=$((_gai+1)) ;;
    --root)         _GOAL_ROOT="${_goal_args[$((_gai+1))]:-}";         _gai=$((_gai+1)) ;;
  esac
done
_GOAL_PARAMS="$(jq -cn \
  --arg period               "$_GOAL_PERIOD" \
  --arg period_value         "$_GOAL_PERIOD_VALUE" \
  --arg text                 "$_GOAL_TEXT" \
  --arg repo                 "$_GOAL_REPO" \
  --arg coordinator_root_path "$_GOAL_ROOT" \
  '{
    period:               $period,
    period_value:         $period_value,
    text:                 $text,
    repo:                 (if $repo == "" then null else $repo end),
    coordinator_root_path: $coordinator_root_path
  }')"

# ---------------------------------------------------------------------------
# Three-state facade dispatch.
# strangle_route decides: seam-absent -> legacy_append "$@";
#                         seam-present -> python3 -m coordinator_core.client goal.append.  # popup-safe-env-suppressed
# "$@" forwarded verbatim so legacy_append receives original CLI args unchanged.
# ---------------------------------------------------------------------------
strangle_route "goal.append" "legacy_append" "$_GOAL_PARAMS" "$@"
