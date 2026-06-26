#!/usr/bin/env bash
# append-goal-event.sh — Append a single goal-event JSON line to state/goals-log.<machine>.jsonl (per-machine, append-only).
#
# Purpose: Pure-append helper that records a "goal event" into a per-machine
#          append-only JSONL log. Idempotent goal_id derived from content hash.
#
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C2
# Review: A-F15 — fabricated plan path repointed to real plan
# Usage: append-goal-event.sh --period <day|week|repo> --period-value <v>
#                              --text <s> [--repo <r>] [--root <p>]

set -euo pipefail

# Bash >=4 guard (BSD macOS ships 3.2; brew bash required)
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Coordinator root — cwd-scope guard (verbatim form, do NOT regroup)
# ---------------------------------------------------------------------------
ROOT="${CLAUDE_HOME:-$HOME}/.claude"

# ---------------------------------------------------------------------------
# Defaults for optional args
# ---------------------------------------------------------------------------
# Review: A-F8 — do not hardcode private repo; derive from git remote at runtime.
# --repo override still works; empty default → derive below after ROOT is set.
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
# Review: A-F8 — derive REPO from git remote when --repo not supplied.
# Falls back to "local" when git is unavailable or no remote is configured.
# ---------------------------------------------------------------------------
if [[ -z "$REPO" ]]; then
  REPO="$(git -C "${ROOT}" remote get-url origin 2>/dev/null | sed -E 's#.*github.com[/:]##; s#\.git$##')"
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
# sha1 helper — prefer shasum (BSD/macOS), fall back to sha1sum (GNU/Linux)
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
# Build JSON object (via jq — never hand-concatenate)
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
LOG_DIR="${ROOT}/state"
# Per-machine append-only log: the machine slug in the filename keeps concurrent Machine-C+Machine-A
# appends in separate files so they never git-conflict (the Data Science Reviewer P1-D6). The emitter globs all
# per-machine logs and derives latest-wins per (repo,root,period,period_value).
MACHINE_SLUG="$(printf '%s' "$DECLARED_BY_MACHINE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"
LOG_FILE="${LOG_DIR}/goals-log.${MACHINE_SLUG}.jsonl"

mkdir -p "$LOG_DIR"
printf '%s\n' "$JSON_LINE" >> "$LOG_FILE"
