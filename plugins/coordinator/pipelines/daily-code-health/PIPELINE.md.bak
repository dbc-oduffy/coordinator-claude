# Daily Code Health — Catch Issues Before They Accumulate

> Referenced by `/code-health`. This is a pipeline definition, not an invocable skill.

## Overview

The "night shift colleague" — reviews today's commits, dispatches a reviewer for any issues, applies findings via review-integrator, and updates health tracking. Results are ready for the next morning's session-start.

**Announce at start:** "I'm using /code-health to review recent commits."

## When to Trigger

- **End-of-day (primary):** `/workday-complete` runs this as part of its health survey phase
- **On-demand:** Available in the session-start maintenance menu (Option 6)
- **NOT auto-triggered at session-start.** The PM runs 30+ sessions/day; automatic health checks would be friction, not value

## The Process

### Step 1: Find New Commits

Determine the scope of commits to review:

1. Check for a last-check timestamp:
   - Read `tasks/health-ledger.md` header for `Last daily check:` date
   - If no health ledger exists: this is the first run. Use the last 24 hours of commits as scope.
2. Get commits since last check:
   ```bash
   git log --since="<last-check-date>" --oneline --stat
   ```
3. **If no new commits:** Update timestamp, report "No new commits since last health check," and exit.

### Step 2: Generate Diff Scope

```bash
# Get the full diff for review
git diff <last-check-commit>..HEAD
```

Summarize the scope: which files changed, how many insertions/deletions, which systems are affected.

### Step 3: Route to Reviewer

The EM decides reviewer routing based on what changed:
- All game dev / UE changes → Sid
- All frontend changes → Palí
- All data/ML changes → Camelia
- Mixed or backend/architecture → Patrik
- If multiple domains: route to the reviewer for the domain with the most changed files. Non-dominant domain changes get lighter coverage — acceptable for a daily check; weekly-architecture-audit provides full coverage.

Dispatch the selected reviewer with `--problems-only` flag (suppress praise/suggestions). This is a health check, not a feature review — we only care about problems.

### Step 4: Apply Findings

If the reviewer returns findings:

1. Dispatch the review-integrator with the finding list and affected file paths
2. Review-integrator applies inline fixes and annotations
3. Complex findings (3+ interacting files, new abstractions) go to the debt backlog instead

If no findings: skip to Step 6.

### Step 5: Update Debt Backlog

For any findings not fixed inline:

1. Check for `tasks/debt-backlog.md`. If it doesn't exist, create it from template:

   ```markdown
   # Technical Debt Backlog

   > Last triaged: YYYY-MM-DD | Open: 0 items (P0: 0, P1: 0, P2: 0)

   | ID | System | Severity | Source | Description | Effort | Status |
   |----|--------|----------|--------|-------------|--------|--------|
   ```

2. Add entries for each deferred finding with:
   - ID: `DCH-{date}-{N}` (Daily Code Health prefix)
   - Source: `daily-health/{reviewer}/{date}`
   - Status: `open`

3. Update the header counts.

**Concurrency note:** `debt-backlog.md` may be written by overlapping sessions (e.g., `/architecture-rotation` running concurrently). Always append new rows at the bottom of the table — never rewrite or reorganize existing rows. When updating an entry's status, match by ID column only. Update the `> Last triaged:` header line to today's date; do not remove or reorder any other header fields.

### Step 6: Update Health Ledger

1. Check for `tasks/health-ledger.md`. If it doesn't exist, create it from template:

   ```markdown
   # System Health Ledger

   > Last daily check: YYYY-MM-DD | Last full audit: never
   > Next rotation target: [pending first audit]

   ## System Index

   | System | Grade | Status | Last Audited | Open P0 | Open P1 | Open P2 | Lines | Notes |
   |--------|-------|--------|-------------|---------|---------|---------|-------|-------|
   ```

   **Grading anchors:**
   - **A/A+**: No open P0/P1, test coverage >80%, documented architecture, no files >500 lines
   - **B**: No open P0, ≤2 open P1, adequate test coverage, no files >800 lines
   - **C**: Has open P1s OR files approaching size limits OR documented architectural concerns
   - **D**: Has open P0s OR severe debt OR blocks other work
   - **F**: Broken, unmaintainable, or security-critical issues unresolved

   **Status definitions:**
   - **HEALTHY** — No open P0/P1, grade A-B
   - **WATCH** — Has open P2s or grade B-C
   - **ACTION** — Has open P0/P1s
   - **CRITICAL** — Blocks other work, security/correctness issues, or grade D-F

2. Update the `Last daily check` date in the header
3. If findings changed system grades, update the relevant rows
4. If a system was touched by commits but has no row yet, add it with grade `?` (unaudited)

**Grade synchronization:** The health ledger is the single source of truth for system grades. `/architecture-rotation` also updates grades here after weekly audits. When updating a row, read the existing grade first — only change it if the daily review's findings explicitly warrant a grade change. Do not downgrade a system that was just upgraded by a recent `/architecture-rotation` run unless new P0/P1 findings justify it.

### Step 7: Write Health Summary

Write results to `tasks/health-summary.md` — this is what session-start reads the next morning:

```markdown
# Health Summary

> Generated: YYYY-MM-DD HH:MM by daily-code-health

## Commits Reviewed
- **Period:** [last check] to [now]
- **Commits:** N
- **Files changed:** M
- **Domains covered:** [list] | **Domains skipped (minority):** [list or none]

## Findings
- **Total:** N (X applied, Y deferred to debt backlog)
- **By severity:** P0: A, P1: B, P2: C

## Systems Affected
| System | Grade Change | Notes |
|--------|-------------|-------|
| [system] | B → B | No issues found |
| [system] | B → C | 2 new P1 findings |

## Action Items for Next Session
- [List any P0/P1 items that need attention]
- [List any deferred findings that should be prioritized]
```

### Step 8: Commit and Update Timestamp

```bash
git add tasks/health-ledger.md tasks/health-summary.md tasks/debt-backlog.md
git commit -m "daily-code-health: review of commits since [date]"
```

## Cost

1 Opus dispatch (reviewer with --problems-only) + 1 Opus dispatch (review-integrator, if findings exist). ~5-10 min for a typical day's commits.

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| No new commits since last check | All work landed before the last check timestamp | Update timestamp, report "No new commits since last health check," and exit gracefully. Do not treat as an error. |
| Reviewer dispatch fails (529 overload or crash) | Model overload during Step 3 dispatch | Re-dispatch once after 60s with reduced scope (summary of changed files only, no full diff). If second failure, log `SKIPPED — reviewer dispatch failed` in health-summary and proceed to Step 6 with no findings applied. |
| Review-integrator fails (Step 4) | Agent crash or context limit after reviewer returns findings | Defer all reviewer findings to debt-backlog as unreviewed entries (source: `daily-health/integrator-failure/{date}`). Log in health-summary: "Integrator failed — N findings deferred unreviewed." |
