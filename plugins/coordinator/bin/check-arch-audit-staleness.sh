#!/usr/bin/env bash
# check-arch-audit-staleness.sh — compute how stale the rotational architecture
# audit is, by reading the `Last targeted audit` clock from the health ledger.
#
# Spec backlink: docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md § Strand 3b
#
# Purpose: /workweek-complete reads this to decide whether to auto-fold a
# targeted-on-diff architecture audit. Mirrors check-weekly-staleness.sh in shape.
#
# Reads state/health-ledger.md, extracts:
#   **Last targeted audit:** YYYY-MM-DD
# and emits one line to stdout:
#   STALE    — > 10 days since the last targeted audit (auto-fold the audit)
#   STALE    — the field is present but unset (placeholder/"none") — never
#              targeted-audited but the ledger exists → overdue
#   FRESH    — ≤ 10 days since the last targeted audit
#   UNKNOWN  — health-ledger.md absent, or the `Last targeted audit` line absent
#              or its date unparseable (caller decides; do NOT auto-fold on UNKNOWN)
#
# IMPORTANT — clock separation: this script reads `Last targeted audit`, NOT
# `Last full audit`. The two clocks are distinct by design (a folded targeted-on-diff
# audit updates ONLY `Last targeted audit`; only a genuine PM-invoked
# /architecture-survey updates `Last full audit`). Reading the wrong field would
# either fire indefinitely or mask the real survey gap.
#
# Exit code: always 0 (informational — callers decide whether to surface the signal).
#
# Negative-spec: does NOT modify any file, does NOT trigger /architecture-audit or
# /workweek-complete, does NOT read the atlas — health-ledger.md only.

set -euo pipefail

STALENESS_THRESHOLD_DAYS=10

# ---------------------------------------------------------------------------
# Locate health-ledger.md — resolve relative to the git repo root so the script
# works when invoked from any working directory inside the repo.
# ---------------------------------------------------------------------------
REPO_ROOT=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Guard the second call too: under set -e a failure here (e.g. a concurrent git
  # lock) would abort without printing UNKNOWN, violating the always-exit-0 contract.
  REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
fi

if [[ -z "$REPO_ROOT" ]]; then
  echo "UNKNOWN"
  exit 0
fi

LEDGER="$REPO_ROOT/state/health-ledger.md"

if [[ ! -f "$LEDGER" ]]; then
  echo "UNKNOWN"
  exit 0
fi

# ---------------------------------------------------------------------------
# Parse the `Last targeted audit` line.
#   **Last targeted audit:** YYYY-MM-DD
# or a placeholder like:
#   **Last targeted audit:** (none — folds into /workweek-complete when >10 days)
# ---------------------------------------------------------------------------
LINE=$(grep -m1 '^\*\*Last targeted audit:\*\*' "$LEDGER" || true)

if [[ -z "$LINE" ]]; then
  # Field absent entirely — can't tell. Do not auto-fold on UNKNOWN.
  echo "UNKNOWN"
  exit 0
fi

LAST_DATE=$(printf '%s\n' "$LINE" \
  | sed -n 's/.*\*\* *\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\).*/\1/p')

if [[ -z "$LAST_DATE" ]]; then
  # Field present but no parseable date (placeholder / "none"). The ledger exists
  # but no targeted audit has ever been recorded → overdue.
  echo "STALE"
  exit 0
fi

# ---------------------------------------------------------------------------
# Compute calendar distance (days since Last targeted audit).
# Portable across macOS (BSD date) and Linux (GNU date).
# ---------------------------------------------------------------------------
TODAY_EPOCH=$(date +%s)
LAST_EPOCH=""

if date --version &>/dev/null 2>&1; then
  # GNU date
  LAST_EPOCH=$(date -d "$LAST_DATE" +%s 2>/dev/null || echo "")
else
  # BSD date (macOS)
  LAST_EPOCH=$(date -j -f "%Y-%m-%d" "$LAST_DATE" +%s 2>/dev/null || echo "")
fi

if [[ -z "$LAST_EPOCH" ]]; then
  echo "UNKNOWN"
  exit 0
fi

DAY_DISTANCE=$(( (TODAY_EPOCH - LAST_EPOCH) / 86400 ))

# Clamp to 0 in case of clock skew
[[ $DAY_DISTANCE -lt 0 ]] && DAY_DISTANCE=0

if (( DAY_DISTANCE > STALENESS_THRESHOLD_DAYS )); then
  echo "STALE"
else
  echo "FRESH"
fi

exit 0
