#!/usr/bin/env bash
# check-shipped-on-main.sh — verify that one or more commits are reachable from
#                             origin/main (i.e., actually shipped).
#
# Spec backlink: docs/plans/2026-05-01-orphan-branch-prevention.md § 1.2
#
# Purpose: thin wrapper around `git merge-base --is-ancestor` providing a
# consistent "is this work on main?" query. Its existence is the doctrine
# signal — callers (handoff.md, lessons, etc.) name this script rather than
# inventing their own one-liner, so the definition of "shipped" stays in one
# place and is greppable.
#
# Negative-spec: read-only. Never modifies the repo.

set -euo pipefail

VERBOSE=0
COMMITS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verbose|-v) VERBOSE=1; shift ;;
    --help|-h)
      cat <<'EOF'
Usage: check-shipped-on-main.sh [--verbose] <commit> [<commit>...]

Checks whether all given commits are ancestors of origin/main.

Arguments:
  commit       A commit SHA, branch tip, or symbolic ref (e.g. HEAD).
               Accepts one or more.

Options:
  --verbose    Print one line per commit: "{sha}: ON_MAIN" or "{sha}: NOT_ON_MAIN ({age})"
  --help       Show this help

Exit codes:
  0  All commits are on origin/main.
  1  At least one commit is NOT on origin/main.
  2  Not inside a git repository, or origin/main is unreachable.
EOF
      exit 0
      ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *)  COMMITS+=("$1"); shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
  echo "check-shipped-on-main: not inside a git repository" >&2
  exit 2
fi

if ! git rev-parse origin/main &>/dev/null 2>&1; then
  # Try fetching
  git fetch origin main --quiet 2>/dev/null || true
  if ! git rev-parse origin/main &>/dev/null 2>&1; then
    echo "check-shipped-on-main: origin/main is not reachable" >&2
    exit 2
  fi
fi

if [[ ${#COMMITS[@]} -eq 0 ]]; then
  echo "check-shipped-on-main: no commits specified. Pass at least one SHA, branch, or HEAD." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Check each commit
# ---------------------------------------------------------------------------
any_not_on_main=0
NOW=$(date +%s)

for ref in "${COMMITS[@]}"; do
  sha=$(git rev-parse "$ref" 2>/dev/null) || {
    echo "check-shipped-on-main: cannot resolve '${ref}' — skipping" >&2
    any_not_on_main=1
    continue
  }

  short="${sha:0:8}"

  if git merge-base --is-ancestor "$sha" origin/main 2>/dev/null; then
    if [[ $VERBOSE -eq 1 ]]; then
      echo "${short}: ON_MAIN"
    fi
  else
    any_not_on_main=1
    if [[ $VERBOSE -eq 1 ]]; then
      # Compute age
      commit_ts=$(git log -1 --format="%ct" "$sha" 2>/dev/null || echo "$NOW")
      age_secs=$(( NOW - commit_ts ))
      if [[ $age_secs -lt 3600 ]]; then
        age="${age_secs}s ago"
      elif [[ $age_secs -lt 86400 ]]; then
        age="$(( age_secs / 3600 ))h ago"
      else
        age="$(( age_secs / 86400 ))d ago"
      fi
      echo "${short}: NOT_ON_MAIN (committed ${age})"
    fi
  fi
done

exit $any_not_on_main
