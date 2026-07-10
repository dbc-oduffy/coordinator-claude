#!/usr/bin/env bash
# backfill-week-changelog-gaps.sh — DR-216 facade router: changelog.backfill_gaps.
#
# Purpose: routes changelog.backfill_gaps through the example-orchestration-hub native op (native-primary)
# with the original script body preserved as legacy_backfill_gaps() (disk-absence fallback).
# Three-state routing model (Design pin 3):
#   State 1 (seam absent on disk) -> legacy_backfill_gaps (current bash body, byte-identical).
#   State 2 (seam present + invoke succeeds) -> native op via cc_invoke (spawn-per-call, DR-215).
#   State 3 (seam present + cc_invoke fails) -> hard transport error, fail loud (exit 2).
#
# Spec backlink: cross-repo/inbox/2026-07-06-strang-10-facade-adoption.md
#
# Usage (unchanged from pre-facade — zero caller repoints):
#   backfill-week-changelog-gaps.sh [repo-root]
#
# Exit codes (unchanged):
#   0 — success or advisory-error (legacy advisory trap; native op succeeded)
#   2 — native op: post-spawn transport failure (State 3, native path only)
set -euo pipefail

# ---------------------------------------------------------------------------
# DR-216 facade router -- source shared helper (must precede legacy_backfill_gaps).
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"

# ---------------------------------------------------------------------------
# legacy_backfill_gaps -- the pre-facade script body, preserved verbatim.
# Called ONLY on State 1 (coordinator_core.invoke absent on disk).
# BASH_SOURCE[0]-relative self-location inside the function is unchanged and
# safe (resolves to this script path, same as before the body-swap).
# ---------------------------------------------------------------------------
legacy_backfill_gaps() {
# Backfill synthesized daily blocks for week-changelog gaps.
#
# Idempotent: skips any date that already has a YYYY-MM-DD-*.md file.
# Spans from HEADER's `Week starting:` through today.
# Advisory: errors do not abort the caller (workweek-complete Step 1b).
#
# Usage: backfill-week-changelog-gaps.sh [repo-root]
#   Defaults to git rev-parse --show-toplevel, then $PWD.

set -uo pipefail
trap 'exit 0' ERR  # advisory contract — never abort the caller
shopt -s nullglob 2>/dev/null || true  # Review: F2 — prevents word-split when glob matches nothing

# Source the state-root seam -- must precede coordinator_state_root calls (added by repoint-central-state-refs.sh C3)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

PYTHON=$(command -v python3 || command -v python || true)
[[ -n "$PYTHON" ]] || { echo "python not found — skipping backfill" >&2; exit 0; }

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "not a git repo at $ROOT — skipping backfill" >&2; exit 0; }

HEADER="$(coordinator_state_root)/week-changelog/HEADER.md"
[[ -f "$HEADER" ]] || { echo "no HEADER.md at $HEADER — nothing to backfill" >&2; exit 0; }

WEEK_START=$(sed -nE 's/^\*\*Week starting:\*\* *([0-9]{4}-[0-9]{2}-[0-9]{2}).*/\1/p' "$HEADER" | head -1)
[[ -n "$WEEK_START" ]] || { echo "HEADER has no parseable Week starting: — skipping" >&2; exit 0; }

TODAY=$("$PYTHON" -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%d'))") # verify-no-console-flash: allow — on-demand backfill utility, not session-hot-path
HOST=$(hostname -s 2>/dev/null || hostname)

# Date helpers — pass dates as argv (no string interpolation into the Python source).
next_day()  { "$PYTHON" -c "import sys; from datetime import datetime,timedelta; print((datetime.strptime(sys.argv[1],'%Y-%m-%d')+timedelta(days=1)).strftime('%Y-%m-%d'))" "$1"; } # verify-no-console-flash: allow — on-demand backfill utility, not session-hot-path
iso_utc()   { printf '%sT00:00:00+00:00' "$1"; }

# Idempotency glob test (parses on bash 3.2; runs on bash ≥4 per DR-148).
#
# Same-day exception: a synthesized backfill for $TODAY is overwritable — commits
# land throughout the day, so a block written at 09:00 is stale by 17:00. Human
# blocks (no -backfill suffix) stay sacred. Past-date synthesized blocks also stay
# sacred — the day is done, commit set is closed.
#
# Review: F1 — overwrite guard tightened to the exact path this script produces
#   (${TODAY}-${HOST}-backfill.md), so other hosts' same-day backfills and any
#   hand-renamed -backfill.md files remain sacred.
# Review: F2 — nullglob (set above) + quoted directory portion removes word-split
#   risk on $ROOT paths containing spaces; [[ -e ]] guard no longer needed.
has_daily() {
  local date="$1" f
  for f in "$(coordinator_state_root)/week-changelog/$date-"*.md; do
    if [[ "$date" == "$TODAY" && "$f" == "$(coordinator_state_root)/week-changelog/${TODAY}-${HOST}-backfill.md" ]]; then
      # This script's own synthesized block for today — overwritable.
      continue
    fi
    return 0
  done
  return 1
}

d="$WEEK_START"
while [[ "$d" < "$TODAY" || "$d" == "$TODAY" ]]; do
  next=$(next_day "$d")
  if ! has_daily "$d"; then
    # Single git pass per day; capture body, derive count/first/last from it.
    body=$(git -C "$ROOT" log --after="$(iso_utc "$d")" --before="$(iso_utc "$next")" --format='%h %s' 2>/dev/null || true)
    if [[ -n "$body" ]]; then
      n=$(printf '%s\n' "$body" | wc -l | tr -d ' ')
      first=$(printf '%s\n' "$body" | tail -1 | awk '{print $1}')  # oldest (git log is newest-first)
      last=$(printf '%s\n' "$body" | head -1 | awk '{print $1}')   # newest
      out="$(coordinator_state_root)/week-changelog/${d}-${HOST}-backfill.md"
      {
        echo "## $d — $HOST (synthesized backfill)"
        echo
        echo "**Commits:** $n (oldest: ${first}, newest: ${last})"
        echo "**Scope:** (synthesized — daily ceremony skipped, no human-curated narrative)"
        echo
        echo "### Commit log"
        echo
        echo '```'
        printf '%s\n' "$body"
        echo '```'
      } > "$out"
      echo "backfilled: state/week-changelog/${d}-${HOST}-backfill.md ($n commits)"
    fi
  fi
  d="$next"
done
}

# ---------------------------------------------------------------------------
# Build changelog.backfill_gaps params JSON from environment / computed values.
# Maps to op params: host (str, optional) and today (str YYYY-MM-DD, optional).
# host — passed as the current machine hostname (preserves legacy attribution).
# today: null — op defaults to current UTC date, matching legacy.
# Safe JSON construction via jq avoids injection.
# ---------------------------------------------------------------------------
_BACKFILL_HOST="$(hostname -s 2>/dev/null || hostname)"
_PARAMS="$(jq -cn \
  --arg host "$_BACKFILL_HOST" \
  '{host: $host, today: null}')"

# ---------------------------------------------------------------------------
# Three-state facade dispatch.
# strangle_route decides: seam-absent -> legacy_backfill_gaps "$@";
#                         seam-present -> cc_invoke changelog.backfill_gaps.
# "$@" forwarded verbatim so legacy_backfill_gaps receives original CLI args unchanged.
# ---------------------------------------------------------------------------
strangle_route "changelog.backfill_gaps" "legacy_backfill_gaps" "$_PARAMS" "$@"
