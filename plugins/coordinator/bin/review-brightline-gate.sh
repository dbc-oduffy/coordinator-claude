#!/usr/bin/env bash
# review-brightline-gate.sh — mechanical partition-vs-single gate for /workstream-complete Step 2.9.
# Prints: loc, files, surfaces, and VERDICT={PARTITION-MANDATORY|single-reviewer-ok}.
# Usage: review-brightline-gate.sh [<git-range>]   (default: $(git merge-base origin/main HEAD)..HEAD)
# Thresholds (any one trips): loc>=500 (gross: insertions+deletions), files>=8, surfaces>=3.
# Rationale: gross LOC tracks the surface area the reviewer's context window must hold,
#            which is the constraint that motivates partitioning in the first place.
# Surfaces = file-role buckets (shell/python/js/config/doctrine/test/cpp/other), NOT directories.

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
if [ "$loc" -ge 500 ] || [ "$files" -ge 8 ] || [ "$surfaces" -ge 3 ]; then
  verdict="PARTITION-MANDATORY"
fi

printf 'range=%s loc=%s files=%s surfaces=%s VERDICT=%s\n' \
  "$range" "$loc" "$files" "$surfaces" "$verdict"
