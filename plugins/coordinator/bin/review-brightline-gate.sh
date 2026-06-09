#!/usr/bin/env bash
# review-brightline-gate.sh — mechanical partition-vs-single gate for /workstream-complete Step 2.9.
# Prints: loc, commits, surfaces, and VERDICT={PARTITION-MANDATORY|single-reviewer-ok}.
# Usage: review-brightline-gate.sh [<git-range>]   (default: $(git merge-base origin/main HEAD)..HEAD)
# Thresholds (any one trips): loc>=500 (gross: insertions+deletions), commits>=5, surfaces>=4.
#
# 2026-06-09 recalibration (PM disposition):
#   - Dropped files>=8 — mass-rename can touch 50 files at zero review-cost; file count is a blunt proxy for review-cost.
#   - Added commits>=5 — commit count tracks independent logical slices (the unit slicing actually operates on).
#   - Bumped surfaces from 3→4 — hook-fixes routinely span shell+test+wiki (3 surfaces) without genuine breadth;
#     4 surfaces demands real cross-surface reach (e.g. bash+json+tests+doctrine), matching the 2026-06-08 worked counterexample.
#
# Rationale: gross LOC tracks the surface area the reviewer's context window must hold,
#            which is the constraint that motivates partitioning in the first place.
# Surfaces = file-role buckets (shell/python/js/config/doctrine/test/cpp/other), NOT directories.
# Commits = `git log --oneline <range> | wc -l` over the range.
# files= field is still reported for context (operator visibility), but is NOT a gate.

set -euo pipefail

if [ -z "${1:-}" ]; then
  base=$(git merge-base origin/main HEAD 2>/dev/null) || {
    echo "review-brightline-gate.sh: cannot resolve origin/main — pass a range explicitly" >&2
    exit 1
  }
  range="${base}..HEAD"
else
  range="$1"
fi

loc=$(git diff --shortstat "$range" 2>/dev/null \
  | grep -oE '[0-9]+ insertion|[0-9]+ deletion' \
  | awk '{s+=$1} END{print s+0}')
files=$(git diff --name-only "$range" 2>/dev/null | sed '/^$/d' | wc -l | tr -d ' ')
commits=$(git log --oneline "$range" 2>/dev/null | wc -l | tr -d ' ')
surfaces=$(git diff --name-only "$range" 2>/dev/null | awk '
  /(^|\/)tests?\//       {print "test"; next}
  /\.sh$/                {print "shell"; next}
  /\.py$/                {print "python"; next}
  /\.(ts|js|tsx|jsx)$/   {print "js"; next}
  /\.(json|ya?ml|toml)$/ {print "config"; next}
  /\.(md|mdx)$/          {print "doctrine"; next}
  /\.(cpp|h|hpp|c)$/     {print "cpp"; next}
                         {print "other"}
' | sort -u | wc -l | tr -d ' ')

verdict="single-reviewer-ok"
if [ "$loc" -ge 500 ] || [ "$commits" -ge 5 ] || [ "$surfaces" -ge 4 ]; then
  verdict="PARTITION-MANDATORY"
fi

# files= reported for context but is NOT a gate (recalibrated 2026-06-09).
printf 'range=%s loc=%s commits=%s surfaces=%s files=%s VERDICT=%s\n' \
  "$range" "$loc" "$commits" "$surfaces" "$files" "$verdict"
