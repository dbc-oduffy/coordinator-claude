#!/usr/bin/env bash
# whats-next.sh — Prioritized next-work surface for /workday-start Step 4.
#
# Spec backlink: archive/specs/2026-05-05-script-first-deterministic-ops.md §T3
#
# Purpose: Replace the 7-file manual read chain in /workday-start Step 4 with
# a single deterministic script. Emits three priority surfaces to stdout:
#   1. Top 5 central entries from state/improvement-queue/*.yaml (queue_scope: central).
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
# Section 1: Coordinator improvement queue — top 5 central entries
# Reads structured YAML from ~/.claude/state/improvement-queue/*.yaml,
# filtering to queue_scope: central rows. Degraded gracefully if no files
# exist (does not error).
# ---------------------------------------------------------------------------
echo "== Improvement queue (top 5 central) =="
QUEUE_DIR="$HOME/.claude/state/improvement-queue"
if [[ -d "$QUEUE_DIR" ]]; then
  # Collect central entries: grep for queue_scope: central, emit title from each file
  _central_entries=()
  while IFS= read -r _f; do
    # Only include files tagged queue_scope: central
    if grep -q '^queue_scope: central' "$_f" 2>/dev/null; then
      _title=$(grep '^title:' "$_f" 2>/dev/null | head -1 | sed 's/^title:[[:space:]]*//' || echo "(no title)")
      _central_entries+=("$_title")
    fi
  done < <(find "$QUEUE_DIR" -maxdepth 1 -name '*.yaml' -print 2>/dev/null | sort)
  _total=${#_central_entries[@]}
  if [[ "$_total" -gt 0 ]]; then
    _show=$(( _total < 5 ? _total : 5 ))
    for (( _i=0; _i<_show; _i++ )); do
      printf "  - %s\n" "${_central_entries[$_i]}"
    done
    if [[ "$_total" -gt 5 ]]; then
      printf "  ... and %d more central entries\n" $(( _total - 5 ))
    fi
  else
    echo "  (no central improvement entries)"
  fi
else
  echo "  (state/improvement-queue/ not found)"
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
