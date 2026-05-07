#!/usr/bin/env bash
# blocked.sh — Surface blocked/paused work without an LLM scan.
#
# Spec backlink: archive/specs/2026-05-05-script-first-deterministic-ops.md §T2
#
# Purpose: Two-part blocked-work detector:
#   1. Handoffs with status: blocked or status: paused — via bin/query-records
#      (no reimplementation of frontmatter parsing).
#   2. tasks/*/todo.md files with `status: blocked`, `status: paused`,
#      `blocked:`, or `waiting on:` lines — via direct grep (query-records
#      does not cover tasks/*/todo.md; extending it is out of scope).
#
# Exit codes: 0 always (callers decide what to do with the output).
#
# Negative-spec: does NOT parse frontmatter directly for handoffs.
# The todo grep is a deliberate scoped exception, not a precedent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "ERROR: not inside a git repository" >&2
  exit 1
}

FOUND_ANY=0

# ---------------------------------------------------------------------------
# Part 1: Blocked/paused handoffs via query-records
# ---------------------------------------------------------------------------
echo "== Blocked handoffs =="
HANDOFF_OUTPUT=$("$SCRIPT_DIR/query-records.sh" \
  --type handoff \
  --where "status in (blocked,paused)" \
  --format markdown-list 2>/dev/null || true)

if [[ -n "$HANDOFF_OUTPUT" ]]; then
  echo "$HANDOFF_OUTPUT"
  FOUND_ANY=1
else
  echo "  (none)"
fi
echo ""

# ---------------------------------------------------------------------------
# Part 2: Blocked/paused items in tasks/*/todo.md — direct grep
# (query-records has no todo type; direct grep is the approved approach here)
# ---------------------------------------------------------------------------
echo "== Blocked todo items =="
TASKS_DIR="$REPO_ROOT/tasks"
if [[ -d "$TASKS_DIR" ]]; then
  TODO_HIT=0
  while IFS= read -r f; do
    matches=$(grep -n \
      -e 'status: blocked' \
      -e 'status: paused' \
      -e 'blocked:' \
      -e 'waiting on:' \
      "$f" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
      rel="${f#"$REPO_ROOT/"}"
      echo "  $rel:"
      while IFS= read -r line; do printf '    %s\n' "$line"; done <<< "$matches"
      TODO_HIT=1
      FOUND_ANY=1
    fi
  done < <(find "$TASKS_DIR" -mindepth 2 -maxdepth 2 -name 'todo.md' -print \
             2>/dev/null | sort || true)
  [[ $TODO_HIT -eq 0 ]] && echo "  (none)"
else
  echo "  (tasks/ not found)"
fi
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ $FOUND_ANY -eq 0 ]]; then
  echo "No blocked items found."
fi
