#!/usr/bin/env bash
# List the week-changelog inventory — substrate-blindness guard.
#
# Prints per daily file: name, total line count, lines starting with a commit SHA (grep '^[a-f0-9]{7,}' — nonzero count means substantive content present). Plus
# the HEADER's Week-starting / Last /workweek-start markers. Used by
# /workweek-complete Step 1a to force an explicit ledger read before any
# "no ledger" claim is allowed downstream.
#
# Idempotent, read-only, exit 0 on empty (the absence IS the signal).
#
# Usage: list-week-changelog.sh [repo-root]
#   Defaults to git rev-parse --show-toplevel, then $PWD.

set -uo pipefail
trap 'exit 0' ERR  # read-only advisory — never abort the caller (workweek-complete Step 1a gate)

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# Review: F5 — explicit git-repo guard; silent $PWD fallback would emit a misleading
#   "(no state/week-changelog/ directory)" that looks like a legitimate "no ledger" signal.
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "list-week-changelog.sh: $ROOT is not a git repo (cwd=$PWD) — cannot resolve state/week-changelog/" >&2; exit 0; }
DIR="$ROOT/state/week-changelog"

if [[ ! -d "$DIR" ]]; then
  echo "(no state/week-changelog/ directory at $ROOT)"
  exit 0
fi

shopt -s nullglob 2>/dev/null || true  # Review: F3 — match peer scripts; non-zero shopt return must not abort under pipefail
any=0
for f in "$DIR"/*.md; do
  base=$(basename "$f")
  [[ "$base" == "HEADER.md" ]] && continue
  any=1
  lines=$(wc -l < "$f" 2>/dev/null | tr -d ' ')
  commits=$(grep -cE '^[a-f0-9]{7,}' "$f" 2>/dev/null || echo 0)
  printf '%s  lines=%s  commit-lines=%s\n' "$base" "$lines" "$commits"
done
[[ $any -eq 0 ]] && echo "(no daily files)"

echo "---"
if [[ -f "$DIR/HEADER.md" ]]; then
  grep -E '^\*\*(Week starting|Last /workweek-start):' "$DIR/HEADER.md" || echo "(HEADER has no Week-starting / Last-workweek-start markers)"
else
  echo "(no HEADER.md)"
fi
