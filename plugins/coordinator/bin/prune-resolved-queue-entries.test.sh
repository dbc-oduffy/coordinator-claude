#!/usr/bin/env bash
# prune-resolved-queue-entries.test.sh — Fixture-based tests for the queue pruner.
#
# Run: bash ~/.claude/plugins/coordinator-claude/coordinator/bin/prune-resolved-queue-entries.test.sh
#
# Covers all seven rules:
#   1. Entry-shape (resolution: / **Closeout:** sub-lines)  — queue files only
#   2. Section-body strip (## Resolved/Done/Closed/...)     — all three files
#   3. Trivial ceremony lines (recurring: 0, etc.)          — queue files only
#   4. Idempotency
#   5. H3 status-closure blocks (### [FIXED ...] ...)       — all three files
#   6. Strikethrough closure lines (~~text~~ ... FIXED ...) — all three files
#   7. Table-row resolution strip (| BS-... | FIXED ...)    — all three files

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRUNER="${SCRIPT_DIR}/prune-resolved-queue-entries.sh"

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { echo "  PASS: $1"; (( PASS++ )) || true; }
fail() {
  echo "  FAIL: $1"
  FAIL_MSGS+=("$1")
  (( FAIL++ )) || true
}

run_case() {
  # run_case <name> <basename> <input-content> <expected-output>
  local name="$1" basename="$2" input="$3" expected="$4"
  local tmpdir
  tmpdir=$(mktemp -d)
  local tmpfile="${tmpdir}/${basename}"
  local expectedfile="${tmpdir}/expected"
  printf '%s' "$input" > "$tmpfile"
  printf '%s' "$expected" > "$expectedfile"
  if ! "$PRUNER" "$tmpfile" 2>"${tmpdir}/stderr"; then
    fail "$name (pruner exited non-zero: $(cat "${tmpdir}/stderr"))"
    rm -rf "$tmpdir"
    return
  fi
  if diff -q "$expectedfile" "$tmpfile" >/dev/null 2>&1; then
    pass "$name"
  else
    fail "$name"
    echo "  --- diff (expected vs actual) ---"
    diff "$expectedfile" "$tmpfile" | sed 's/^/    /' || true
  fi
  rm -rf "$tmpdir"
}

run_idempotency_case() {
  # Run pruner twice; second run must be a no-op (byte-identical output).
  local name="$1" basename="$2" input="$3"
  local tmpdir
  tmpdir=$(mktemp -d)
  local tmpfile="${tmpdir}/${basename}"
  printf '%s' "$input" > "$tmpfile"
  "$PRUNER" "$tmpfile" >/dev/null 2>&1 || { fail "$name (first pass failed)"; rm -rf "$tmpdir"; return; }
  local after_first
  after_first=$(cat "$tmpfile")
  "$PRUNER" "$tmpfile" >/dev/null 2>&1 || { fail "$name (second pass failed)"; rm -rf "$tmpdir"; return; }
  local after_second
  after_second=$(cat "$tmpfile")
  if [[ "$after_first" == "$after_second" ]]; then
    pass "$name"
  else
    fail "$name (not idempotent)"
  fi
  rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# Rule 2 — ## Resolved section strip (all three files)
# ---------------------------------------------------------------------------
run_case "Rule 2: ## Resolved section dropped to next ##" "bug-backlog.md" \
"# Header

## Open
- alpha
- beta

## Resolved this run (bug-blitz 2026-05-18)
- gamma — fixed via X
- delta — fixed via Y

## Next steps
- epsilon
" \
"# Header

## Open
- alpha
- beta

## Next steps
- epsilon
"

run_case "Rule 2: ## History / ## Closed / ## Archive all stripped" "bug-backlog.md" \
"## Open
- alpha

## History
- old1

## Closed
- old2

## Archive
- old3

## Active
- beta
" \
"## Open
- alpha

## Active
- beta
"

# ---------------------------------------------------------------------------
# Rule 5 — H3 status-closure block (THE BIG ONE for holodeck bug-backlog)
# ---------------------------------------------------------------------------
run_case "Rule 5: ### [FIXED YYYY-MM-DD] block dropped" "bug-backlog.md" \
"## Open

### BS-2026-05-18-OPEN [P2] still broken
**Status:** OPEN — needs investigation.
Lots of forensic narrative here.

### [FIXED 2026-05-16] BS-2026-05-16-CLOSED [P2] this is done
**Status:** FIXED — shipped commit abc1234.
30 lines of forensic narrative here.
More narrative.
Even more.

### BS-2026-05-18-ALSO-OPEN [P3] still open
Body of open entry.
" \
"## Open

### BS-2026-05-18-OPEN [P2] still broken
**Status:** OPEN — needs investigation.
Lots of forensic narrative here.

### BS-2026-05-18-ALSO-OPEN [P3] still open
Body of open entry.
"

run_case "Rule 5: status anywhere in heading (mid-line bracketed)" "bug-backlog.md" \
"### BS-2026-04-28-WIDGET [P2] [FIXED — STALE ENTRY] something
Body suppressed.
More body.

### BS-2026-05-18-OPEN [P3] still open
Open body.
" \
"### BS-2026-05-18-OPEN [P3] still open
Open body.
"

run_case "Rule 5: em-dash suffix closure" "bug-backlog.md" \
"### BS-2026-04-17-sweep [P0] 12 more FindObject pre-create guards — FIXED
Long body about the fix.

### BS-2026-05-18-OPEN open entry
Open body.
" \
"### BS-2026-05-18-OPEN open entry
Open body.
"

run_case "Rule 5: H3 closure transitions cleanly into next H3 closure" "bug-backlog.md" \
"### [FIXED 2026-05-15] BS-A closed
Body A.

### [RESOLVED 2026-05-16] BS-B also closed
Body B.

### BS-C-OPEN still open
Body C.
" \
"### BS-C-OPEN still open
Body C.
"

run_case "Rule 5: non-closure H3 entries survive (PARTIAL FIX etc)" "bug-backlog.md" \
"### BS-PARTIAL [P2] partial fix in flight
Body partial.

### BS-WILL-BE-DONE [P3] should be done in v2
Body forward-looking.
" \
"### BS-PARTIAL [P2] partial fix in flight
Body partial.

### BS-WILL-BE-DONE [P3] should be done in v2
Body forward-looking.
"

# ---------------------------------------------------------------------------
# Rule 6 — Strikethrough-closure line strip
# ---------------------------------------------------------------------------
run_case "Rule 6: DroneSim-shape strikethrough row dropped" "bug-backlog.md" \
"| ID | Area | Pri | Description | Status | Date |
|----|------|-----|-------------|--------|------|
| ~~BS-2026-04-09-1~~ | FDM | ~~P2~~ CLOSED | ~~text~~ — **FIXED (e36d8a3):** wired CVars. | N/A — fixed | 2026-04-09 |
| BS-2026-05-18-OPEN | FDM | P2 | open thing | OPEN | 2026-05-18 |
" \
"| ID | Area | Pri | Description | Status | Date |
|----|------|-----|-------------|--------|------|
| BS-2026-05-18-OPEN | FDM | P2 | open thing | OPEN | 2026-05-18 |
"

run_case "Rule 6: non-closure strikethrough survives" "bug-backlog.md" \
"Narrative line: ~~old approach~~ — we now use the new approach.
Another line: ~~deprecated module~~ is the predecessor.
" \
"Narrative line: ~~old approach~~ — we now use the new approach.
Another line: ~~deprecated module~~ is the predecessor.
"

# ---------------------------------------------------------------------------
# Rule 7 — Table-row resolution strip (geneva-mvp pattern)
# ---------------------------------------------------------------------------
run_case "Rule 7: geneva-mvp '| BS-... | FIXED ...' row dropped" "bug-backlog.md" \
"| BS-2026-03-19-1 | FIXED (run 2) — webhook lock failure now deletes lock, allowing Stripe retry              |
| BS-2026-03-19-2 | FIXED (run 2) — session-orchestrator terminates AWS session on finalization failure       |
| BS-2026-05-18-OPEN | OPEN — needs work |
" \
"| BS-2026-05-18-OPEN | OPEN — needs work |
"

run_case "Rule 7: BS row with FIXED only in narrative survives" "bug-backlog.md" \
"| BS-2026-05-18-OPEN | OPEN | should be FIXED in v2 | not yet |
" \
"| BS-2026-05-18-OPEN | OPEN | should be FIXED in v2 | not yet |
"

# ---------------------------------------------------------------------------
# Rule 1 — Entry-shape strip (queue files only)
# ---------------------------------------------------------------------------
run_case "Rule 1: resolution: resolved drops entry (queue file)" "coordinator-improvement-queue.md" \
"# Queue

- 2026-05-15 | self | foo.md:10 | done thing | proposed target: wiki
  resolution: resolved 2026-05-16 abc1234
- 2026-05-15 | self | bar.md:20 | open thing | proposed target: wiki
" \
"# Queue

- 2026-05-15 | self | bar.md:20 | open thing | proposed target: wiki
"

run_case "Rule 1: **Closeout:** sub-line drops entry (queue file)" "improvement-queue.md" \
"- 2026-05-15 | self | foo.md:10 | done thing | proposed target: wiki
  **Closeout:** landed in commit abc1234.
- 2026-05-15 | self | bar.md:20 | open thing | proposed target: wiki
" \
"- 2026-05-15 | self | bar.md:20 | open thing | proposed target: wiki
"

# ---------------------------------------------------------------------------
# Rule 3 — Trivial ceremony lines stripped (queue files only)
# ---------------------------------------------------------------------------
run_case "Rule 3: recurring:0 / resolution:pending stripped, entry kept" "coordinator-improvement-queue.md" \
"- 2026-05-15 | self | foo.md:10 | thing | proposed target: wiki
  recurring: 0
  resolution: pending
" \
"- 2026-05-15 | self | foo.md:10 | thing | proposed target: wiki
"

# ---------------------------------------------------------------------------
# Rule 1 does NOT apply to bug-backlog (entry shape differs)
# ---------------------------------------------------------------------------
run_case "Rule 1 inactive on bug-backlog: sub-line entries pass through" "bug-backlog.md" \
"- 2026-05-15 | self | foo.md:10 | thing | proposed target: wiki
  resolution: resolved 2026-05-16
" \
"- 2026-05-15 | self | foo.md:10 | thing | proposed target: wiki
  resolution: resolved 2026-05-16
"

# ---------------------------------------------------------------------------
# Reviewer findings — bug-fix confirmation tests
# ---------------------------------------------------------------------------

# F1: Rule 7 must NOT drop rows where closure keyword starts column 3+
run_case "F1: Rule 7 — keyword in col 3+ survives (not col 2)" "bug-backlog.md" \
"| BS-2026-05-18-A | OPEN | FIXED — keyword in third column | needs work |
| BS-2026-05-18-B | FIXED — col 2, this one drops | shipped |
" \
"| BS-2026-05-18-A | OPEN | FIXED — keyword in third column | needs work |
"

# F2: Rule 5 must NOT drop H3 with markdown link [CLOSED issue](url) as link display text
run_case "F2: Rule 5 — markdown link [CLOSED issue](url) survives" "bug-backlog.md" \
"### BS-2026-05-18-X refers to [CLOSED issue](https://tracker/123) for context
Body of the still-open entry.

### [FIXED 2026-05-18] BS-Y closed
Body suppressed.
" \
"### BS-2026-05-18-X refers to [CLOSED issue](https://tracker/123) for context
Body of the still-open entry.

"

# F3: Rule 8 — closure line mid-entry-collection drops the orphaned entry + sublines
run_case "F3: Rule 8 — closure line mid-entry drops whole entry + orphaned sublines" "coordinator-improvement-queue.md" \
"- 2026-05-15 | self | foo.md:10 | thing | proposed target: wiki
| ~~BS-Y~~ | ~~P2~~ CLOSED | ~~text~~ — **FIXED:** stuff |
  resolution: pending
  some: subline
- 2026-05-15 | self | bar.md:20 | other open | proposed target: wiki
" \
"- 2026-05-15 | self | bar.md:20 | other open | proposed target: wiki
"

# F4: Case sensitivity — uppercase-only by convention; mixed-case 'Fixed' survives
run_case "F4: Rule 6 case-sensitive — lowercase 'fixed' in strikethrough survives" "bug-backlog.md" \
"| ~~BS-A~~ | fixed (lowercase narrative) |
| ~~BS-B~~ | Fixed (mixed case narrative) |
| ~~BS-C~~ | FIXED uppercase closure |
" \
"| ~~BS-A~~ | fixed (lowercase narrative) |
| ~~BS-B~~ | Fixed (mixed case narrative) |
"

# F5: Rule 5 bare-keyword-at-EOL with whitespace prefix drops the heading
run_case "F5: Rule 5 — bare 'DONE' at EOL with whitespace prefix drops" "bug-backlog.md" \
"### BS-2026-05-18-X [P2] DONE
Body suppressed under bare-EOL match.

### BS-2026-05-18-Y [P3] still open
Open body.
" \
"### BS-2026-05-18-Y [P3] still open
Open body.
"

# F6: Rule 7 — tight table format (no space before second |) is also matched
run_case "F6: Rule 7 — tight table '| BS-X| FIXED' matches" "bug-backlog.md" \
"| BS-2026-05-18-A| FIXED — no space before pipe |
| BS-2026-05-18-B | OPEN — still working |
" \
"| BS-2026-05-18-B | OPEN — still working |
"

# F8: Rule 7 — narrative mention of FIXED in col 3 survives (companion to F1)
run_case "F8: Rule 7 — 'should be FIXED' in narrative col survives" "bug-backlog.md" \
"| BS-2026-05-18-OPEN | OPEN | should be FIXED in v2 | not yet |
" \
"| BS-2026-05-18-OPEN | OPEN | should be FIXED in v2 | not yet |
"

# F9: ## Resolved with an inner ### [FIXED] heading — both suppressed by Rule 2
run_case "F9: ## Resolved with inner ### [FIXED] — both suppressed (Rule 2 broader)" "bug-backlog.md" \
"## Open
- alpha

## Resolved
### [FIXED 2026-05-01] BS-X
body of inner H3

## Active
- beta
" \
"## Open
- alpha

## Active
- beta
"

# ---------------------------------------------------------------------------
# Rule 4 — Idempotency (combined ruleset)
# ---------------------------------------------------------------------------
# Per-rule idempotency (F7) — already-clean inputs produce no further changes on a second pass.
run_idempotency_case "F7: Rule 5 idempotent on already-clean H3 entries" "bug-backlog.md" \
"### BS-OPEN-1 [P2] still working
Body 1.

### BS-OPEN-2 [P3] also working
Body 2.
"

run_idempotency_case "F7: Rule 6 idempotent on already-clean strikethrough" "bug-backlog.md" \
"Narrative: ~~old approach~~ — we now use the new way.
"

run_idempotency_case "F7: Rule 7 idempotent on already-clean table rows" "bug-backlog.md" \
"| BS-2026-05-18-OPEN-1 | OPEN | needs work |
| BS-2026-05-18-OPEN-2 | P2 | also open |
"

run_idempotency_case "Rule 4: idempotent across combined ruleset" "bug-backlog.md" \
"# Header

## Open
- alpha

## Resolved this run
- old1

### [FIXED 2026-05-16] BS-X closed
Body suppressed.

| ~~BS-Y~~ | ~~P2~~ CLOSED | ~~text~~ — **FIXED:** stuff |
| BS-Z | FIXED — table-row closure |

### BS-OPEN still open
Open body.
"

# ---------------------------------------------------------------------------
# Allowlist guard — refuses non-allowed basenames
# ---------------------------------------------------------------------------
echo "--- guard: rejects non-allowlisted file"
TMP_BAD=$(mktemp /tmp/random-file.md.XXXXXX)
printf 'content\n' > "$TMP_BAD"
if "$PRUNER" "$TMP_BAD" 2>/dev/null; then
  fail "guard: should reject non-allowlisted basename"
else
  pass "guard: rejected non-allowlisted basename"
fi
rm -f "$TMP_BAD"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "============================================"
echo "  Total: $((PASS + FAIL))   Passed: $PASS   Failed: $FAIL"
echo "============================================"
if (( FAIL > 0 )); then
  echo "Failures:"
  for msg in "${FAIL_MSGS[@]}"; do echo "  - $msg"; done
  exit 1
fi
exit 0
