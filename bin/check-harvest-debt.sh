#!/usr/bin/env bash
# check-harvest-debt.sh — read-only probe for un-harvested plans in archive/specs/.
#
# Purpose: count plan files under archive/specs/**/*.md that are absent from the
# distill-log (docs/wiki/.distill-log.md). Plans there are "harvest debt" — they
# exist in the archive but /distill has not yet processed them. Prints a one-line
# nudge when the debt count exceeds 5; silent otherwise. Always exits 0.
#
# Spec backlink: chunk C7 of the terminal-plan-archive-flow plan (2026-06).
#
# Matching strategy: the distill-log records archive/specs/<basename>.md (the
# pre-YYYY-MM-subdir flat path). The on-disk layout uses YYYY-MM/ subdirectory
# grouping. We match by basename so both the old flat layout and the current
# nested layout are covered correctly.
#
# Sidecar exclusions: *.review.md, *-check.md, *.the Director of Engineering-review.md are review
# sidecars, not plan files — excluded from the count.
#
# Usage:
#   check-harvest-debt.sh [--root <dir>]
#
# Options:
#   --root <dir>   Repository root to probe (default: git rev-parse --show-toplevel).
#                  Accepts a fixture dir for testing; no git required in that case.
#
# Exit codes: always 0.

set -uo pipefail

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Root resolution — prefer explicit arg, fall back to git
# ---------------------------------------------------------------------------
if [[ -z "$ROOT" ]]; then
  if command -v git >/dev/null 2>&1; then
    ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
  fi
fi

# If we still have no root, bail silently (non-git consumer project no-op).
if [[ -z "$ROOT" ]]; then
  exit 0
fi

SPECS_DIR="$ROOT/archive/specs"
DISTILL_LOG="$ROOT/docs/wiki/.distill-log.md"

# Consumer-project no-op: either path absent → print nothing.
[[ -d "$SPECS_DIR" ]] || exit 0
[[ -f "$DISTILL_LOG" ]] || exit 0

# ---------------------------------------------------------------------------
# Build the set of harvested basenames from the distill-log.
# Format: `- archive/specs/<basename>.md → <DISPOSITION> (run: <run-id>)`
# We only care about basenames, not the full recorded path, because the
# on-disk layout reorganised files under YYYY-MM/ subdirs post-migration.
# ---------------------------------------------------------------------------

# Extract basenames of all archive/specs entries in the distill-log.
# BSD grep and GNU grep both support this form of -o with a BRE pattern.
#   Step 1: grep lines that reference archive/specs/
#   Step 2: extract the filename (last path segment before the arrow)
# Use a portable approach: awk on those lines.
# Pattern: `- archive/specs/[optional-YYYY-MM/]<basename>.md → ...`
# We want the basename (no directory component).
HARVESTED_BASENAMES=$(
  grep "archive/specs/" "$DISTILL_LOG" 2>/dev/null \
  | awk '{
      # Find the token between the last "/" and " →"
      for (i=1; i<=NF; i++) {
        if ($i ~ /\.md$/) {
          n = split($i, parts, "/")
          print parts[n]
          break
        }
      }
    }'
)

# ---------------------------------------------------------------------------
# Walk archive/specs/**/*.md; for each plan file check if its basename is in
# the harvested set. Count the un-harvested ones.
# ---------------------------------------------------------------------------

# BSD find (macOS) does not support -printf; use a portable subshell.
# We need recursive search; `-maxdepth` alone won't reach YYYY-MM/ subdirs.
# Portable: find without -printf, then basename via awk or parameter expansion.

UNHARVESTED=0

# Use a while-read loop to avoid issues with spaces in filenames (though plan
# filenames should never contain spaces) and to stay portable (no mapfile).
while IFS= read -r fpath; do
  # Sidecar exclusions — skip review and check sidecars.
  fname="${fpath##*/}"
  case "$fname" in
    *.review.md|*-check.md|*.the Director of Engineering-review.md) continue ;;
  esac

  # Check if this basename appears in the harvested set.
  # grep -Fx: fixed-string, whole-line match — avoids regex special-char issues.
  if ! printf '%s\n' "$HARVESTED_BASENAMES" | grep -qFx "$fname" 2>/dev/null; then
    UNHARVESTED=$((UNHARVESTED + 1))
  fi
done < <(find "$SPECS_DIR" -name "*.md" 2>/dev/null)

# ---------------------------------------------------------------------------
# Emit nudge when debt exceeds threshold.
# ---------------------------------------------------------------------------
if [[ "$UNHARVESTED" -gt 5 ]]; then
  echo "${UNHARVESTED} un-harvested archived plans — run /distill"
fi

exit 0
