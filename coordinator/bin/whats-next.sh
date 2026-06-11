#!/usr/bin/env bash
# whats-next.sh — Prioritized next-work surface for /workday-start Step 4.
#
# Spec backlink: archive/specs/2026-05-05-script-first-deterministic-ops.md §T3
#
# Purpose: Replace the 7-file manual read chain in /workday-start Step 4 with
# a single deterministic script. Emits three priority surfaces to stdout:
#   1. Head of state/coordinator-improvement-queue.md (top 5 entries).
#   2. docs/project-tracker.md rows where status column is Ready or Executing.
#   3. Open handoffs (filename + line-1 heading), excluding archived/superseded.
#
# Output is plaintext for the EM to frame. No clustering or narrative.
#
# Exit codes: 0 always. Missing files produce "(not found)" notices, not errors.
#
# Negative-spec: does NOT extend bin/query-records. project-tracker.md is a
# markdown table — parsed with awk/grep here, not via query-records (separate
# workstream per plan §T3 note).

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "ERROR: not inside a git repository" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Section 1: Coordinator improvement queue — top 5 active entries
# ---------------------------------------------------------------------------
echo "== Improvement queue (top 5) =="
QUEUE="$HOME/.claude/state/coordinator-improvement-queue.md"
if [[ -f "$QUEUE" ]]; then
  # Extract bullet list entries (lines starting with "- "), skip headers/blanks
  ENTRIES=$(grep '^- ' "$QUEUE" 2>/dev/null || true)
  if [[ -n "$ENTRIES" ]]; then
    echo "$ENTRIES" | head -5 | while IFS= read -r line; do
      printf "  %s\n" "$line"
    done
    TOTAL=$(echo "$ENTRIES" | wc -l | tr -d ' ')
    if [[ "$TOTAL" -gt 5 ]]; then
      printf "  ... and %d more entries\n" $(( TOTAL - 5 ))
    fi
  else
    echo "  (queue is empty)"
  fi
else
  echo "  (coordinator-improvement-queue.md not found)"
fi
echo ""

# ---------------------------------------------------------------------------
# Section 2: project-tracker.md — Ready and Executing rows
# Parses markdown tables with awk: looks for | Status | column and matches
# rows where the Status cell contains "Ready" or "Executing".
# ---------------------------------------------------------------------------
echo "== Tracker: Ready / Executing =="
TRACKER="$REPO_ROOT/docs/project-tracker.md"
if [[ -f "$TRACKER" ]]; then
  # Find header row to determine which pipe-delimited column holds Status.
  # Then emit data rows matching Ready or Executing in that column.
  # Strategy: grep for table rows containing Ready or Executing (case-insensitive),
  # then also grab the workstream name from the preceding section heading.
  MATCHES=$(grep -n 'Ready\|Executing' "$TRACKER" 2>/dev/null \
    | { grep '|' || true; })
  if [[ -n "$MATCHES" ]]; then
    echo "$MATCHES" | while IFS= read -r line; do
      printf "  %s\n" "$line"
    done
  else
    # Fall back: look for **Status:** lines (non-table format)
    MATCHES2=$(grep -n '\*\*Status:\*\*.*\(Ready\|Executing\)' "$TRACKER" 2>/dev/null || true)
    if [[ -n "$MATCHES2" ]]; then
      echo "$MATCHES2" | while IFS= read -r line; do
        printf "  %s\n" "$line"
      done
    else
      echo "  (no Ready or Executing items)"
    fi
  fi
else
  echo "  (docs/project-tracker.md not found)"
fi
echo ""

# ---------------------------------------------------------------------------
# Section 3: Open handoffs — filename + line-1 heading
# Excludes files where line 1 or frontmatter signals archived/superseded.
# ---------------------------------------------------------------------------
echo "== Open handoffs =="
HANDOFFS_DIR="$REPO_ROOT/state/handoffs"
if [[ -d "$HANDOFFS_DIR" ]]; then
  HIT=0
  while IFS= read -r f; do
    # Skip if frontmatter contains status: archived or status: superseded
    fm_status=$(grep -m1 '^status:' "$f" 2>/dev/null | tr -d ' ' || true)
    case "$fm_status" in
      status:archived|status:superseded) continue ;;
    esac
    heading=$(head -1 "$f" 2>/dev/null | sed 's/^#* *//' || echo "(no heading)")
    printf "  %-50s  # %s\n" "$(basename "$f")" "$heading"
    HIT=1
  done < <(find "$HANDOFFS_DIR" -maxdepth 1 -name '*.md' -print 2>/dev/null | sort || true)
  if [[ $HIT -eq 0 ]]; then echo "  (no open handoffs)"; fi
else
  echo "  (state/handoffs/ not found)"
fi
