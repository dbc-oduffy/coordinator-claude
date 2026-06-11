#!/usr/bin/env bash
# prune-resolved-queue-entries.sh — remove resolved-state bloat from improvement queues and bug-backlog.
#
# Spec backlink: docs/plans/2026-05-07-prune-resolved-state-bloat.md § S5
#                (lives in consumer-project docs/plans/, not in this plugin tree)
#
# Purpose: Strip resolved-state bloat from the three named queue files. Doctrine alone
# cannot prevent drift — each EM has a non-deterministic way of marking closure in
# markdown, so the pruner is the structural backstop.
#
# CASE SENSITIVITY: closure keywords are matched UPPERCASE-ONLY by convention. Mixed-case
# "Fixed" or lowercase "fixed" in narrative survives — only the all-caps EM-closure
# convention triggers a strip. This is intentional: lowercase usage is overwhelmingly
# narrative ("the bug was fixed by..."), uppercase is the closure-annotation pattern.
#
# OUT OF SCOPE: inline closure annotations on main-line list entries like
#   "- 2026-MM-DD | source | file | description — APPLIED to X.md"
# are deliberately not stripped — too high false-positive risk against legitimate
# "landed in /X" / "applied to Y" descriptions of active queue items. Doctrine
# expects EMs to delete the line on resolution; the pruner only catches structural
# closure-annotation patterns (heading / strikethrough / table-row shapes).
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
#            "^### " carrying a bracketed status "[FIXED 2026-...]" / "[FIXED]" / "[FIXED — ...]"
#            (keyword immediately followed by closing-bracket, date digit, or em-dash/hyphen),
#            OR ending with bare-keyword-at-EOL (whitespace before keyword, EOL after).
#            Body suppressed until the next ## or ### heading. Catches the
#            holodeck-bug-backlog pattern: "### [FIXED 2026-05-16] BS-... <30 lines of forensic>".
#            Markdown links with closure-keyword display text (e.g. "[CLOSED issue](url)")
#            survive because the bracket-content pattern requires date/dash/close, not a word.
#   Rule 6 — Strikethrough-closure line strip (all three files): drop any single line
#            containing "~~" AND an UPPERCASE closure keyword (FIXED|RESOLVED|CLOSED|DONE|COMPLETED).
#            Catches the DroneSim table-row pattern:
#            "| ~~BS-...~~ | ... ~~P2~~ CLOSED | ... — **FIXED (sha):** ... |".
#            Non-closure strikethrough (e.g. "~~old approach~~ — we now ...") survives
#            because it lacks the keyword.
#   Rule 7 — Table-row resolution strip (all three files): drop any "| BS-..." table
#            row where COLUMN 2 (the first content cell after the id) starts with a
#            closure keyword. Catches "| BS-2026-03-19-1 | FIXED (run 2) — ... |".
#            Rows with the keyword in column 3+, or only in narrative text, survive.
#   Rule 8 — Buffer-orphan guard (queue files only): when a Rule 6/7 closure line
#            appears mid-entry-collection (between a buffered main-line and its
#            sublines), treat the entire entry as closure-annotated — drop the main
#            line, drop the closure line, and suppress subsequent orphaned sublines
#            until the next non-subline. Prevents synthetic-subline corruption.
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
  in_resolved_section = 0       # inside a ## Resolved/Done/... section (Rule 2)
  in_h3_closure = 0             # inside a ### [FIXED ...] block (Rule 5)
  suppress_orphan_sublines = 0  # Rule 8: drop sublines belonging to a closure-orphaned entry
  # Entry buffer (Rule 1): gather a main line + all consecutive 2-space-indented
  # sub-lines, then decide whether to emit or suppress based on whether any
  # sub-line carries "resolution: resolved" or "**Closeout:**" (already-resolved
  # annotation). Handles 2-line, 3-line, and 4+-line entry shapes uniformly.
  buf_count = 0          # number of buffered lines (0 = no entry being collected)
  buf_resolved = 0       # 1 if any buffered sub-line indicates resolution
}

function flush_buffer(   i) {
  if (buf_resolved) {
    # Suppress entire entry — emit nothing.
  } else {
    for (i = 1; i <= buf_count; i++) print buf[i]
  }
  buf_count = 0
  buf_resolved = 0
}

# Rule 8: when a closure line interrupts entry-collection, drop the buffer and
# arm orphan-subline suppression. The next consecutive sublines belong to the
# now-closure-annotated entry — drop them. Cleared on first non-subline.
function discard_buffer_to_orphan() {
  if (buf_count > 0) {
    buf_count = 0
    buf_resolved = 0
    suppress_orphan_sublines = 1
  }
}

# Match an H3 closure heading per Rule 5. Three shapes:
#   1. "^### ... [(FIXED|...) ]"               — bare bracket-close
#   2. "^### ... [(FIXED|...) <digit>...]"     — date suffix inside brackets
#   3. "^### ... [(FIXED|...) (— | - )...]"    — em-dash/hyphen suffix inside brackets
#   4. "^### ... <ws>(FIXED|...)$"             — bare keyword at EOL after whitespace
# Markdown links like "[CLOSED issue](url)" survive because the bracket content
# after CLOSED is a word, not a date/dash/close.
function is_h3_closure(line) {
  if (line !~ /^### /) return 0
  # Bracketed status: keyword IMMEDIATELY followed by ], or by space+digit, or by space+dash/em-dash.
  if (line ~ /\[(FIXED|RESOLVED|CLOSED|DONE|COMPLETED)(\]|[[:space:]]+([0-9]|—|-))/) return 1
  # Bare keyword at EOL with whitespace prefix (em-dash, hyphen, or plain space all qualify).
  if (line ~ /[[:space:]](FIXED|RESOLVED|CLOSED|DONE|COMPLETED)[[:space:]]*$/) return 1
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

# Match a "| BS-..." table row whose COLUMN 2 (first content cell after the id)
# starts with a closure keyword per Rule 7. Single anchored pattern:
#   "^| BS-<id>[ws]*| (FIXED|RESOLVED|CLOSED|DONE|COMPLETED)<non-word>"
# Rows with the keyword in column 3+ or only in narrative text do not match.
function is_table_row_closure(line) {
  if (line ~ /^\| BS-[^ |]+[[:space:]]*\| (FIXED|RESOLVED|CLOSED|DONE|COMPLETED)([^A-Za-z0-9_]|$)/) return 1
  return 0
}

{
  lineno = NR

  # --- Rule 8: orphan-subline suppression (runs first; mid-entry closure cleared the buf) ---
  if (suppress_orphan_sublines) {
    if ($0 ~ /^  /) { next }    # consecutive subline of orphaned entry → drop
    suppress_orphan_sublines = 0  # non-subline ends suppression; fall through
  }

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
    # Rule 8: if a closure line appears mid-entry-collection (queue files), treat
    # the entry as closure-annotated — drop the main line buffer AND arm orphan
    # subline suppression. Otherwise the closure line is standalone — just flush.
    if (buf_count > 0) {
      discard_buffer_to_orphan()
    } else {
      flush_buffer()
    }
    next
  }

  # --- Rule 1: entry-shape strip (queue files only) ---
  if (apply_rule1) {
    is_main = ($0 ~ /^- [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] \|/)
    is_subline = ($0 ~ /^  /)

    if (buf_count == 0) {
      if (is_main) {
        buf[++buf_count] = $0
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
