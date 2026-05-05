#!/usr/bin/env bash
# check-weekly-staleness.sh — compute how stale the weekly release cadence is
#
# Spec backlink: docs/plans/2026-05-04-workweek-cadence-split.md § Trigger Doctrine
#
# Purpose: reads tasks/week-changelog/HEADER.md to extract the prior-week reset
# SHA and the Week-starting date, then computes two staleness dimensions:
#   • commit distance: git rev-list --count <sha>..HEAD
#   • calendar distance: today - "Week starting" date (in days)
# Emits one line to stdout:
#   STALE  — both thresholds crossed (≥5 days AND ≥15 commits)
#   MILD   — exactly one threshold crossed
#   FRESH  — neither threshold crossed
#   UNKNOWN — HEADER.md absent or unparseable (treated as never-run)
#
# Exit code: always 0 (informational — callers decide whether to surface the signal).
#
# Negative-spec: does NOT modify any file, does NOT trigger /workweek-complete,
# does NOT read daily changelog files — HEADER.md only.

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate HEADER.md — resolve relative to the git repo root so the script
# works when invoked from any working directory inside the repo.
# ---------------------------------------------------------------------------
REPO_ROOT=""
if git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
  REPO_ROOT=$(git rev-parse --show-toplevel)
fi

if [[ -z "$REPO_ROOT" ]]; then
  echo "UNKNOWN"
  exit 0
fi

HEADER="$REPO_ROOT/tasks/week-changelog/HEADER.md"

if [[ ! -f "$HEADER" ]]; then
  echo "UNKNOWN"
  exit 0
fi

# ---------------------------------------------------------------------------
# Parse HEADER.md
# ---------------------------------------------------------------------------

# Extract: **Prior week released:** vX.Y.Z (commit abc1234, YYYY-MM-DD)
# The SHA is the first token inside the parenthesised group after "commit ".
RESET_SHA=$(grep -m1 '^\*\*Prior week released:\*\*' "$HEADER" \
  | sed -n 's/.*commit \([a-f0-9]\{5,40\}\).*/\1/p')

# Extract: **Week starting:** YYYY-MM-DD
WEEK_START=$(grep -m1 '^\*\*Week starting:\*\*' "$HEADER" \
  | sed -n 's/.*\*\* *\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\).*/\1/p')

# ---------------------------------------------------------------------------
# Guard: if either field is missing or looks like a placeholder, emit UNKNOWN
# ---------------------------------------------------------------------------
if [[ -z "$RESET_SHA" || -z "$WEEK_START" || "$WEEK_START" == *"not yet set"* ]]; then
  echo "UNKNOWN"
  exit 0
fi

# Verify the SHA exists in this repo
if ! git cat-file -e "${RESET_SHA}^{commit}" 2>/dev/null; then
  echo "UNKNOWN"
  exit 0
fi

# ---------------------------------------------------------------------------
# Compute commit distance
# ---------------------------------------------------------------------------
COMMIT_DISTANCE=$(git rev-list --count "${RESET_SHA}..HEAD" 2>/dev/null || echo 0)

# ---------------------------------------------------------------------------
# Compute calendar distance (days since Week starting)
# Portable across macOS (BSD date) and Linux (GNU date).
# ---------------------------------------------------------------------------
TODAY_EPOCH=""
WEEK_EPOCH=""

if date --version &>/dev/null 2>&1; then
  # GNU date
  TODAY_EPOCH=$(date +%s)
  WEEK_EPOCH=$(date -d "$WEEK_START" +%s 2>/dev/null || echo "")
else
  # BSD date (macOS)
  TODAY_EPOCH=$(date +%s)
  WEEK_EPOCH=$(date -j -f "%Y-%m-%d" "$WEEK_START" +%s 2>/dev/null || echo "")
fi

if [[ -z "$WEEK_EPOCH" ]]; then
  echo "UNKNOWN"
  exit 0
fi

DAY_DISTANCE=$(( (TODAY_EPOCH - WEEK_EPOCH) / 86400 ))

# Clamp to 0 in case of clock skew
[[ $DAY_DISTANCE -lt 0 ]] && DAY_DISTANCE=0

# ---------------------------------------------------------------------------
# Apply thresholds:  ≥5 days AND ≥15 commits → STALE
#                    one threshold            → MILD
#                    neither                  → FRESH
# ---------------------------------------------------------------------------
DAYS_CROSSED=0
COMMITS_CROSSED=0

[[ $DAY_DISTANCE    -ge 5  ]] && DAYS_CROSSED=1
[[ $COMMIT_DISTANCE -ge 15 ]] && COMMITS_CROSSED=1

if [[ $DAYS_CROSSED -eq 1 && $COMMITS_CROSSED -eq 1 ]]; then
  echo "STALE"
elif [[ $DAYS_CROSSED -eq 1 || $COMMITS_CROSSED -eq 1 ]]; then
  echo "MILD"
else
  echo "FRESH"
fi

exit 0
