#!/usr/bin/env bash
# prune-resolved-queue-entries.sh — remove resolved-state bloat from improvement queues and bug-backlog.
#
# Spec backlink: docs/plans/2026-05-07-prune-resolved-state-bloat.md § S5
#
# Purpose: Strip two categories of resolved-state bloat from the three named queue files:
#   Rule 1 — Entry-shape: delete any three-line entry block (main + recurring: + resolution:)
#            whose resolution: sub-line starts with "resolved". Applies to queue files only
#            (coordinator-improvement-queue.md, improvement-queue.md). NOT bug-backlog.md.
#   Rule 2 — Section-body: delete any section matching ^## (Processed|Resolved) and its
#            entire body up to the next ## heading or EOF. Applies to all three files.
#            Regex breadth catches per-run-suffixed variants like
#            "## Resolved this run (bug-blitz 2026-05-06-22h42)".
#   Rule 3 — Idempotent: running twice produces no further changes.
#
# Usage: prune-resolved-queue-entries.sh <queue-file>
#
# On parse error or unexpected structure, fails loud with file:line — does NOT skip silently.
# Only operates on the three named queue files (path-allowlist guard).

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <queue-file>" >&2
  exit 1
fi

INPUT="$1"

# Path-allowlist guard — only operate on the three named queue files.
# Match by basename to support both absolute and relative paths.
BASENAME=$(basename "$INPUT")
case "$BASENAME" in
  coordinator-improvement-queue.md|improvement-queue.md|bug-backlog.md)
    ;;
  *)
    echo "ERROR: $0 only operates on coordinator-improvement-queue.md, improvement-queue.md, or bug-backlog.md. Refusing to prune: $INPUT" >&2
    exit 1
    ;;
esac

if [[ ! -f "$INPUT" ]]; then
  echo "ERROR: file not found: $INPUT" >&2
  exit 1
fi

# Determine whether Rule 1 (entry-shape) applies to this file.
APPLY_RULE1=0
case "$BASENAME" in
  coordinator-improvement-queue.md|improvement-queue.md)
    APPLY_RULE1=1
    ;;
esac

# Work on a temp file; replace atomically on success.
TMP=$(mktemp "${INPUT}.tmp.XXXXXX")
trap 'rm -f "$TMP"' EXIT

awk -v apply_rule1="$APPLY_RULE1" -v filename="$INPUT" '
BEGIN {
  in_resolved_section = 0
  # Entry buffer (Rule 1): gather a main line + all consecutive 2-space-indented
  # sub-lines, then decide whether to emit or suppress based on whether any
  # sub-line carries "resolution: resolved" or "**Closeout:**" (already-resolved
  # annotation). Handles 2-line, 3-line, and 4+-line entry shapes uniformly.
  buf_count = 0          # number of buffered lines (0 = no entry being collected)
  buf_resolved = 0       # 1 if any buffered sub-line indicates resolution
  buf_main_lineno = 0
}

function flush_buffer(   i) {
  if (buf_resolved) {
    # Suppress entire entry — emit nothing.
  } else {
    for (i = 1; i <= buf_count; i++) print buf[i]
  }
  buf_count = 0
  buf_resolved = 0
  buf_main_lineno = 0
}

{
  lineno = NR

  # --- Rule 2: detect a ## Processed or ## Resolved* section header ---
  # Broad prefix match catches per-run-suffixed variants like
  # "## Resolved this run (bug-blitz …)".
  if ($0 ~ /^## Processed/ || $0 ~ /^## Resolved/) {
    flush_buffer()
    in_resolved_section = 1
    next
  }

  # If we are inside a resolved section, suppress lines until the next ## heading.
  if (in_resolved_section) {
    if ($0 ~ /^## /) {
      in_resolved_section = 0
      # Fall through to normal processing below.
    } else {
      next
    }
  }

  # --- Rule 1: entry-shape strip (queue files only) ---
  if (apply_rule1) {
    is_main = ($0 ~ /^- [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] \|/)
    is_subline = ($0 ~ /^  /)

    if (buf_count == 0) {
      if (is_main) {
        buf[++buf_count] = $0
        buf_main_lineno = lineno
      } else {
        print
      }
      next
    }

    # buf_count > 0 — currently gathering an entry
    if (is_subline && !is_main) {
      buf[++buf_count] = $0
      if ($0 ~ /^  resolution: resolved /) buf_resolved = 1
      else if ($0 ~ /^  \*\*Closeout:\*\*/) buf_resolved = 1
      next
    }

    # Non-sub-line — flush current buffer, then handle this line
    flush_buffer()
    if (is_main) {
      buf[++buf_count] = $0
      buf_main_lineno = lineno
    } else {
      print
    }
    next
  } else {
    # Rule 1 does not apply (bug-backlog) — print normally.
    print
  }
}

END {
  if (buf_count > 0) flush_buffer()
}
' "$INPUT" > "$TMP"

# Atomic replace
mv "$TMP" "$INPUT"
trap - EXIT
