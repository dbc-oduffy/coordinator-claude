#!/usr/bin/env bash
# review-brightline-gate.sh — mechanical partition-vs-single gate for /workstream-complete Step 2.9.
# Prints: loc, commits, surfaces, and VERDICT={PARTITION-MANDATORY|single-reviewer-ok}.
# Usage: review-brightline-gate.sh [--session-id <id>] [<git-range>]
#   (range default: $(git merge-base origin/main HEAD)..HEAD)
# Thresholds (any one trips): loc>=500 (gross: insertions+deletions), commits>=5, surfaces>=4.
#
# 2026-06-09 recalibration (PM disposition):
#   - Dropped files>=8 — mass-rename can touch 50 files at zero review-cost; file count is a blunt proxy for review-cost.
#   - Added commits>=5 — commit count tracks independent logical slices (the unit slicing actually operates on).
#   - Bumped surfaces from 3→4 — hook-fixes routinely span shell+test+wiki (3 surfaces) without genuine breadth;
#     4 surfaces demands real cross-surface reach (e.g. bash+json+tests+doctrine), matching the 2026-06-08 worked counterexample.
#
# 2026-06-15 session-scope flag:
#   --session-id <id>  Filter range to commits matching Session-Id: <id> trailer; recompute
#                      loc/commits/surfaces/files over filtered SHAs only. Zero-match → vacuous
#                      verdict with stderr note (fail-loud, non-blocking, exit 0). No fallback to
#                      unfiltered range — silent fallback would re-introduce multi-EM branch noise.
#   Spec backlink: docs/plans/2026-06-15-brightline-session-scope-fix.md § C3
#
# Rationale: gross LOC tracks the surface area the reviewer's context window must hold,
#            which is the constraint that motivates partitioning in the first place.
# Surfaces = file-role buckets (shell/python/js/config/doctrine/test/cpp/other), NOT directories.
# Commits = `git log --oneline <range> | wc -l` over the range.
# files= field is still reported for context (operator visibility), but is NOT a gate.

set -euo pipefail

# ---------------------------------------------------------------------------
# Parse --session-id flag (must precede range argument to preserve existing CLI compat)
# ---------------------------------------------------------------------------
session_id=""
if [[ "${1:-}" == "--session-id" ]]; then
  if [[ -z "${2:-}" ]]; then
    echo "review-brightline-gate.sh: --session-id requires an argument" >&2
    exit 1
  fi
  session_id="$2"
  shift 2
fi

# Review: code-reviewer — validate session_id to prevent ERE metacharacter injection
# into --grep regex. UUIDs match by construction; rejects path traversal, spaces, shell
# metacharacters, and other unexpected shapes in a single allowlist check.
if [[ -n "$session_id" && ! "$session_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]]; then
  echo "review-brightline-gate.sh: --session-id must match ^[a-zA-Z0-9][a-zA-Z0-9_-]*$" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve range (legacy positional $1 preserved)
# ---------------------------------------------------------------------------
if [ -z "${1:-}" ]; then
  base=$(git merge-base origin/main HEAD 2>/dev/null) || {
    echo "review-brightline-gate.sh: cannot resolve origin/main — pass a range explicitly" >&2
    exit 1
  }
  range="${base}..HEAD"
else
  range="$1"
fi

# ---------------------------------------------------------------------------
# Session-scoped path: filter range to commits matching Session-Id trailer
# ---------------------------------------------------------------------------
if [[ -n "${session_id}" ]]; then
  # Collect filtered SHAs (pinned diff-aggregation shape per plan § C3 hard constraints)
  filtered_shas=$(git log --pretty='%H' --grep="^Session-Id: ${session_id}$" "$range" 2>/dev/null) || true
  filtered_count=$(printf '%s\n' "${filtered_shas}" | awk 'NF{c++} END{print c+0}')

  if [[ "${filtered_count}" -eq 0 ]]; then
    # Zero-match: fail-loud-non-blocking per AC6
    printf 'range=%s loc=0 commits=0 surfaces=0 files=0 filtered_to=0 VERDICT=single-reviewer-ok\n' "$range"
    printf 'note: session-id matched 0 commits in range — gate vacuous, EM verify scope manually\n' >&2
    exit 0
  fi

  # Recompute metrics over filtered SHAs only.
  # Pinned aggregation: reuse filtered_shas to avoid TOCTOU + halve git log invocations.
  # Review: code-reviewer — replace duplicate git log with filtered_shas reuse (Finding 11);
  # replace silent || true with stderr warning for diagnosability (Finding 9).
  filtered_diff=$(printf '%s\n' "${filtered_shas}" | xargs git show --stat --format= 2>/dev/null) \
    || echo "review-brightline-gate.sh: warning: git show failed over filtered SHAs — metrics may be incomplete" >&2

  loc=$(printf '%s\n' "${filtered_diff}" \
    | grep -oE '[0-9]+ insertion|[0-9]+ deletion' \
    | awk '{s+=$1} END{print s+0}')
  files=$(printf '%s\n' "${filtered_diff}" \
    | grep -E '^\s*\S.*\|' \
    | awk '{print $1}' \
    | sed '/^$/d' \
    | sort -u \
    | wc -l \
    | tr -d ' ')
  commits="${filtered_count}"
  surfaces=$(printf '%s\n' "${filtered_diff}" \
    | grep -E '^\s*\S.*\|' \
    | awk '{print $1}' \
    | awk '
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

  # Pinned output field order per AC4/AC5: range loc commits surfaces files filtered_to VERDICT
  printf 'range=%s loc=%s commits=%s surfaces=%s files=%s filtered_to=%s VERDICT=%s\n' \
    "$range" "$loc" "$commits" "$surfaces" "$files" "${filtered_count}" "$verdict"
  exit 0
fi

# ---------------------------------------------------------------------------
# Unfiltered path (no --session-id): behaviour byte-identical to pre-change (AC5)
# ---------------------------------------------------------------------------

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
