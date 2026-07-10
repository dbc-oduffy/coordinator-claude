#!/usr/bin/env bash
# standup.sh — Deterministic daily inventory for /workday-complete Step 4a
#              and /workday-start Step 1 reconciliation.
#
# Spec backlink: archive/specs/2026-05-05-script-first-deterministic-ops.md §T1
#
# Purpose: Produce a deterministic inventory for /workday-complete Step 4a.
# Emits raw inventory (commits, file-change summary, touched handoffs/todos,
# active handoffs) to stdout. Step 4b (Sonnet analyst) clusters and narrates.
#
# Output sections (in order):
#   > Baseline: <sha> (<ISO-timestamp>)   ← parsed by Phase B for git diff baseline
#   == Commits today ==
#   == Files changed by dir ==
#   == Handoffs touched today ==
#   == Todo files touched today ==
#   == Active handoffs ==
#
# Exit codes: 0 on success (including empty-inventory); non-zero only on tool failure.
#
# Cross-platform: works on Git Bash MINGW64 (Windows) and Linux GNU.
# Uses `find -newermt` (GNU find / MINGW64 find). If unavailable, falls back
# to a no-op section with a note — callers should treat absent sections as empty.
#
# Negative-spec: does NOT cluster, narrate, or write files. Stdout only.

set -euo pipefail

# Source state-root seam — C4/stop-the-rot: per-repo state refs route through coordinator_state_root.
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4
_STANDUP_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
# shellcheck source=../lib/coordinator-state-root.sh
source "${_STANDUP_SCRIPT_DIR}/../lib/coordinator-state-root.sh"

# ---------------------------------------------------------------------------
# Resolve repo root
# ---------------------------------------------------------------------------
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "ERROR: not inside a git repository" >&2
  exit 1
}
cd "$REPO_ROOT"
STATE_ROOT="$(coordinator_state_root)"

# ---------------------------------------------------------------------------
# Baseline detection: last workday-complete / workday-start
# commit within the past 3 days; fallback 24 hours ago.
# ---------------------------------------------------------------------------
BASELINE_SHA=""
BASELINE_TS=""

BASELINE_SHA=$(git log --oneline \
  -E --grep="^(workday-complete|workday-start):" \
  --since="3 days ago" -1 --format="%H" 2>/dev/null || true)

if [[ -n "$BASELINE_SHA" ]]; then
  BASELINE_TS=$(git log -1 --format="%ai" "$BASELINE_SHA" 2>/dev/null || echo "unknown")
else
  # Fallback: 24 hours ago — express as a detached timestamp anchor
  BASELINE_SHA=$(git log --since="24 hours ago" --format="%H" | tail -1 2>/dev/null || true)
  if [[ -n "$BASELINE_SHA" ]]; then
    BASELINE_TS=$(git log -1 --format="%ai" "$BASELINE_SHA" 2>/dev/null || echo "unknown")
  else
    BASELINE_SHA="HEAD"
    BASELINE_TS="(no commits in 24h)"
  fi
fi

echo "> Baseline: ${BASELINE_SHA} (${BASELINE_TS})"
echo ""

# ---------------------------------------------------------------------------
# Section 1: Commits since baseline
# ---------------------------------------------------------------------------
echo "== Commits today =="
if [[ "$BASELINE_SHA" == "HEAD" ]]; then
  echo "  (no commits since baseline)"
else
  git log "${BASELINE_SHA}..HEAD" --oneline --stat 2>/dev/null || echo "  (git log failed)"
fi
echo ""

# ---------------------------------------------------------------------------
# Section 2: Files changed by top-level directory
# ---------------------------------------------------------------------------
echo "== Files changed by dir =="
if [[ "$BASELINE_SHA" != "HEAD" ]]; then
  git diff --name-only "${BASELINE_SHA}..HEAD" 2>/dev/null \
    | awk -F/ '{print ($2 == "" ? $1 : $1"/")}' \
    | sort | uniq -c | sort -rn \
    | awk '{printf "  %-20s %s\n", $2, $1}' \
    || echo "  (diff failed)"
else
  echo "  (no baseline commit)"
fi
echo ""

# ---------------------------------------------------------------------------
# Section 3: Handoffs modified since start of today
# Uses find -newermt (GNU find / MINGW64). Fallback: skip with note.
# ---------------------------------------------------------------------------
echo "== Handoffs touched today =="
TODAY_ANCHOR=$(date -I 2>/dev/null || date +%Y-%m-%d)
HANDOFFS_DIR="$STATE_ROOT/handoffs"
if [[ -d "$HANDOFFS_DIR" ]]; then
  _hits="$(find "$HANDOFFS_DIR" -name '*.md' -newermt "${TODAY_ANCHOR} 00:00" -print 2>/dev/null)"
  if [[ -n "$_hits" ]]; then
    find "$HANDOFFS_DIR" -name '*.md' -newermt "${TODAY_ANCHOR} 00:00" \
         -print 2>/dev/null | while IFS= read -r f; do
      heading=$(head -1 "$f" 2>/dev/null | sed 's/^#* *//' || echo "(no heading)")
      printf "  %-50s  # %s\n" "$(basename "$f")" "$heading"
    done
  else
    echo "  (none modified today)"
  fi
else
  echo "  (state/handoffs/ not found)"
fi
echo ""

# ---------------------------------------------------------------------------
# Section 4: tasks/*/todo.md files modified since start of today
# ---------------------------------------------------------------------------
echo "== Todo files touched today =="
TASKS_DIR="$REPO_ROOT/tasks"
if [[ -d "$TASKS_DIR" ]]; then
  TODO_HIT=0
  while IFS= read -r f; do
    heading=$(head -1 "$f" 2>/dev/null | sed 's/^#* *//' || echo "(no heading)")
    rel="${f#"$REPO_ROOT/"}"
    printf "  %-50s  # %s\n" "$rel" "$heading"
    TODO_HIT=1
  done < <(find "$TASKS_DIR" -mindepth 2 -maxdepth 2 -name 'todo.md' \
             -newermt "${TODAY_ANCHOR} 00:00" -print 2>/dev/null || true)
  if [[ $TODO_HIT -eq 0 ]]; then echo "  (none modified today)"; fi
else
  echo "  (tasks/ not found)"
fi
echo ""

# ---------------------------------------------------------------------------
# Section 5: Active handoffs (not in archive/) — filename + line-1 heading
# ---------------------------------------------------------------------------
echo "== Active handoffs =="
if [[ -d "$HANDOFFS_DIR" ]]; then
  HIT=0
  while IFS= read -r f; do
    heading=$(head -1 "$f" 2>/dev/null | sed 's/^#* *//' || echo "(no heading)")
    printf "  %-50s  # %s\n" "$(basename "$f")" "$heading"
    HIT=1
  done < <(find "$HANDOFFS_DIR" -maxdepth 1 -name '*.md' -print 2>/dev/null | sort || true)
  if [[ $HIT -eq 0 ]]; then echo "  (no active handoffs)"; fi
else
  echo "  (state/handoffs/ not found)"
fi
