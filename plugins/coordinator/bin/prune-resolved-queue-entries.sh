#!/usr/bin/env bash
# prune-resolved-queue-entries.sh — remove resolved-state bloat from improvement queues and bug-backlog.
#
# Spec backlink: docs/plans/2026-05-07-prune-resolved-state-bloat.md § S5
#
# Purpose: Strip resolved-state bloat from the three named queue files. Doctrine alone
# cannot prevent drift — each EM has a non-deterministic way of marking closure in
# markdown, so the pruner is the structural backstop.
#
#   Rule 1 — Entry-shape (queue files only): delete any entry block whose resolution:
#            sub-line starts with "resolved" (or any non-pending/non-in_progress value),
#            or which carries a "**Closeout:**" sub-line. Applies to
#            coordinator-improvement-queue.md, improvement-queue.md. NOT bug-backlog.md.
#   Rule 2 — Section-body: delete any section matching
#            ^## (Processed|Resolved|History|Closed|Done|Archive|Closeout) and its
#            entire body up to the next ## heading or EOF. Applies to all three files.
#            Regex breadth catches per-run-suffixed variants like
#            "## Resolved this run (bug-blitz 2026-05-06-22h42)".
#   Rule 3 — Ceremony-line strip (queue files only): drop trivial schema-ceremony
#            sub-lines that never change in practice — "  recurring: 0" and
#            "  resolution: pending" / "  resolution: in_progress". Per DR-056
#            (amended 2026-05-17): main-line-only schema; non-zero recurring counters
#            fold into the main line as " [recurring: N]" when needed.
#   Rule 4 — Idempotent: running twice produces no further changes.
#   Rule 5 — H3 status-closure block (all three files): delete any H3 heading
#            "^### " carrying a bracketed status keyword "[FIXED|RESOLVED|CLOSED|DONE|COMPLETED]"
#            anywhere on the line, OR ending with " — (FIXED|RESOLVED|CLOSED|DONE|COMPLETED)$".
#            Body suppressed until the next ## or ### heading. Catches the
#            holodeck-bug-backlog pattern: "### [FIXED 2026-05-16] BS-... <30 lines of forensic>".
#   Rule 6 — Strikethrough-closure line strip (all three files): drop any single line
#            containing "~~" AND a closure keyword (FIXED|RESOLVED|CLOSED|DONE|COMPLETED).
#            Catches the DroneSim table-row pattern:
#            "| ~~BS-...~~ | ... ~~P2~~ CLOSED | ... — **FIXED (sha):** ... |".
#            Non-closure strikethrough (e.g. "~~old approach~~ — we now ...") survives
#            because it lacks the keyword.
#   Rule 7 — Table-row resolution strip (all three files): drop any "| BS-..." table
#            row whose first content cell starts with a closure keyword.
#            Catches the geneva-mvp pattern: "| BS-2026-03-19-1 | FIXED (run 2) — ... |".
#            Rows with the keyword only inside narrative text (not as a cell value)
#            do not match.
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
  in_resolved_section = 0   # inside a ## Resolved/Done/... section (Rule 2)
  in_h3_closure = 0         # inside a ### [FIXED ...] block (Rule 5)
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

# Match an H3 closure heading per Rule 5. Two shapes:
#   1. "^### " with bracketed status keyword anywhere: ... [FIXED ...] ...
#   2. "^### " ending with em-dash or hyphen suffix: ... — FIXED  (or  - FIXED)
function is_h3_closure(line) {
  if (line !~ /^### /) return 0
  # Bracketed status keyword: "[FIXED" / "[RESOLVED" / ... followed by a non-word char or "]"
  if (line ~ /\[(FIXED|RESOLVED|CLOSED|DONE|COMPLETED)([^A-Za-z0-9_]|$)/) return 1
  # Em-dash or hyphen suffix at EOL: " — FIXED" or " - FIXED" (already non-word-bounded on both ends)
  if (line ~ /(— |- )(FIXED|RESOLVED|CLOSED|DONE|COMPLETED)[[:space:]]*$/) return 1
  return 0
}

# Match a ## Resolved/Done/... section header per Rule 2.
function is_h2_closure(line) {
  if (line ~ /^## Processed/ || line ~ /^## Resolved/ || \
      line ~ /^## History/ || line ~ /^## Closed/ || \
      line ~ /^## Done/ || line ~ /^## Archive/ || \
      line ~ /^## Closeout/) return 1
  return 0
}

# Match a strikethrough-closure line per Rule 6.
# Line must contain "~~" AND a closure keyword as a whole word.
function is_strikethrough_closure(line) {
  if (line !~ /~~/) return 0
  # Closure keyword bounded by non-word chars (or line edges) — portable substitute for \b\b
  if (line ~ /(^|[^A-Za-z0-9_])(FIXED|RESOLVED|CLOSED|DONE|COMPLETED)([^A-Za-z0-9_]|$)/) return 1
  return 0
}

# Match a "| BS-..." table row whose first content cell starts with a closure keyword
# per Rule 7. Pattern: "| BS-<id> | (FIXED|RESOLVED|CLOSED|DONE|COMPLETED) ..."
function is_table_row_closure(line) {
  if (line !~ /^\| BS-[^ |]+[[:space:]]+\|/) return 0
  # First content cell starts with a closure keyword (followed by non-word char)
  if (line ~ /\| (FIXED|RESOLVED|CLOSED|DONE|COMPLETED)([^A-Za-z0-9_]|$)/) return 1
  return 0
}

{
  lineno = NR

  # --- Section-suppression handlers run first so we exit them on heading boundaries ---

  # If inside an H3 closure (Rule 5), suppress until next ## or ### heading.
  # Fall through to re-test that heading (may itself be another closure).
  if (in_h3_closure) {
    if ($0 ~ /^## / || $0 ~ /^### /) {
      in_h3_closure = 0
      # fall through to normal processing below
    } else {
      next
    }
  }

  # If inside a ## Resolved section (Rule 2), suppress until next ## heading.
  if (in_resolved_section) {
    if ($0 ~ /^## /) {
      in_resolved_section = 0
      # fall through
    } else {
      next
    }
  }

  # --- Heading-closure detectors (set suppression flags, consume the heading line) ---

  if (is_h2_closure($0)) {
    flush_buffer()
    in_resolved_section = 1
    next
  }

  if (is_h3_closure($0)) {
    flush_buffer()
    in_h3_closure = 1
    next
  }

  # --- Per-line closure-marker drops (Rules 6, 7) ---

  if (is_strikethrough_closure($0) || is_table_row_closure($0)) {
    flush_buffer()
    next
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
      # Rule 3: ceremony-line strip. Drop trivial schema-ceremony sub-lines
      # entirely (do not even buffer them) — `recurring: 0` and
      # `resolution: pending` / `resolution: in_progress`. Per DR-056 amended
      # 2026-05-17, the queue schema is main-line-only by default.
      if ($0 ~ /^  recurring: 0[[:space:]]*$/) next
      if ($0 ~ /^  resolution: pending[[:space:]]*$/) next
      if ($0 ~ /^  resolution: in_progress[[:space:]]*$/) next
      buf[++buf_count] = $0
      # Rule 1: any resolution value other than pending/in_progress (already
      # filtered above) is a closure marker — suppress the entry.
      if ($0 ~ /^  resolution: /) buf_resolved = 1
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
