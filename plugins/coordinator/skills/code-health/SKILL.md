---
description: Night-shift code health review — scans today's commits, dispatches a reviewer, applies findings, and updates health tracking for next session-start
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: (no arguments needed)
---

# Code Health — Night Shift Commit Review

The "night shift colleague." Reads the health ledger's last-check timestamp to find new commits, dispatches a domain-appropriate reviewer with `--problems-only`, applies findings inline via review-integrator, defers complex findings to the debt backlog, updates the health ledger with current grades, and writes a morning-ready summary. Results are waiting at the next session-start.

**Announce at start:** "I'm using /code-health to review recent commits."

---

## Never Skip on a "Small" Day

The strongest predictor of a bug-filled review is a small commit count, not a large one. When today's fixes touched one code path, the adjacent or sibling path is the highest-probability next bug — and a small commit count is exactly when reviewers and EMs are most tempted to skip ("only 8 commits, nothing to see"). That's where the regressions hide.

**Run this review on every committed day, regardless of commit count.** The cost-benefit is asymmetric: a 5-minute review on a quiet day catches the silent regression a fix introduced on a parallel handler; skipping a busy day misses bugs the next session will trip on.

The only valid skip condition is the one already in the Failure Modes table: **zero new commits since last check.** Anything else — even a single commit — run the review.

---

## Step 1: Find New Commits

Determine the scope of commits to review:

1. Read `tasks/health-ledger.md` header for the `Last daily check:` date.
   - If no health ledger exists: this is the first run — use the last 24 hours as scope.
2. Get commits since last check:
   ```bash
   git log --since="<last-check-date>" --oneline --stat
   ```
3. **If no new commits:** Update the `Last daily check` timestamp in the health ledger, report "No new commits since last health check," and exit.

---

## Step 2: Generate Diff Scope

```bash
git diff <last-check-commit>..HEAD
```

Summarize scope: which files changed, how many insertions/deletions, which systems are affected. This summary drives reviewer routing in Step 3.

---

## Step 3: Route to Reviewer

Select the reviewer based on what changed:

| Dominant change type | Reviewer |
|---|---|
| Game dev / Unreal Engine | Sid |
| Frontend / UI | Palí |
| Data / ML / science | Camelia |
| Mixed, backend, or architecture | Patrik |

If multiple domains are present, route to the dominant one (most files changed / most critical path).

Dispatch the selected reviewer with `--problems-only` and `run_in_background: true`. This is a health check — suppress praise and suggestions, return problems only. Process findings when notified of completion.

---

## Step 4: Apply Findings

If the reviewer returns findings:

1. Dispatch review-integrator with the finding list and affected file paths.
2. Review-integrator applies inline fixes and annotations.
3. **Complex findings** — those requiring 3+ interacting files or new abstractions — go to the debt backlog (Step 5) instead of inline application.

If no findings: skip to Step 6.

---

## Step 5: Update Debt Backlog

For any findings not fixed inline:

1. Check for `tasks/debt-backlog.md`. If it doesn't exist, create it from this template:

   ```markdown
   # Technical Debt Backlog

   > Last triaged: YYYY-MM-DD | Open: 0 items (P0: 0, P1: 0, P2: 0)

   | ID | System | Severity | Source | Description | Effort | Status |
   |----|--------|----------|--------|-------------|--------|--------|
   ```

2. Add one row per deferred finding:
   - **ID:** `DCH-{date}-{N}` (e.g., `DCH-2026-03-18-1`)
   - **Source:** `daily-health/{reviewer}/{date}`
   - **Status:** `open`

3. Update the header summary counts.

**Concurrency note:** `debt-backlog.md` may be written by overlapping sessions (e.g., `/architecture-rotation` running concurrently). Always append new rows at the bottom of the table — never rewrite or reorganize existing rows. When updating an entry's status, match by ID column only. Update the `> Last triaged:` header line to today's date; do not remove or reorder any other header fields.

---

## Step 6: Update Health Ledger

1. Check for `tasks/health-ledger.md`. If it doesn't exist, create it from this template:

   ```markdown
   # System Health Ledger

   > Last daily check: YYYY-MM-DD | Last full audit: never
   > Next rotation target: [pending first audit]

   ## System Index

   | System | Grade | Status | Last Audited | Open P0 | Open P1 | Open P2 | Lines | Notes |
   |--------|-------|--------|-------------|---------|---------|---------|-------|-------|
   ```

2. Update `Last daily check` in the header to today's date.
3. If findings changed system grades, update the relevant rows.
4. If a system was touched by commits but has no row yet, add it with grade `?` (unaudited).

**Grade synchronization:** The health ledger is the single source of truth for system grades. `/architecture-rotation` also updates grades here after weekly audits. When updating a row, read the existing grade first — only change it if the daily review's findings explicitly warrant a grade change. Do not downgrade a system that was just upgraded by a recent `/architecture-rotation` run unless new P0/P1 findings justify it.

**Grading anchors:**

| Grade | Criteria |
|---|---|
| A / A+ | No open P0/P1, test coverage >80%, documented architecture, no files >500 lines |
| B | No open P0, ≤2 open P1, adequate test coverage, no files >800 lines |
| C | Has open P1s OR files approaching size limits OR documented architectural concerns |
| D | Has open P0s OR severe debt OR blocks other work |
| F | Broken, unmaintainable, or security-critical issues unresolved |

**Status definitions:**

| Status | Trigger |
|---|---|
| HEALTHY | Grade A-B, no open P0/P1 |
| WATCH | Has open P2s, grade B-C |
| ACTION | Has open P0/P1s |
| CRITICAL | Blocks other work, security/correctness issues, grade D-F |

---

## Step 7: Write Health Summary

Write results to `tasks/health-summary.md` — this is what session-start reads the next morning:

```markdown
# Health Summary

> Generated: YYYY-MM-DD HH:MM by daily-code-health

## Commits Reviewed
- **Period:** [last check] to [now]
- **Commits:** N
- **Files changed:** M

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

---

## Step 8: Commit and Update Timestamp

```bash
git add tasks/health-ledger.md tasks/health-summary.md tasks/debt-backlog.md
git commit -m "daily-code-health: review of commits since [date]"
```

The post-commit hook pushes automatically.

---

## Failure Modes

| Situation | Action |
|---|---|
| No health ledger on first run | Create from template, use last 24 hours as scope |
| No new commits since last check | Update timestamp, report, and exit — no reviewer dispatch |
| Reviewer returns no findings | Skip Steps 4-5, proceed directly to Step 6 |
| Debt backlog doesn't exist | Create from template before adding entries |
| Complex finding can't be fixed inline | Add to debt backlog with severity and effort estimate |
| Git commands fail (no commits, detached HEAD) | Report the error and stop — do not attempt to guess the diff |
| review-integrator unavailable | Log findings to health-summary.md manually, note as deferred |

---

## Cost

1 Opus reviewer dispatch (with `--problems-only`) + 1 Opus review-integrator dispatch if findings exist. Approximately 5-10 minutes for a typical day's commits. If no findings, the reviewer dispatch is the only cost.

---

## Relationship to Other Commands

- **`/workday-complete`** — primary trigger for this command; runs code-health as part of its end-of-day health survey phase. The normal path is to let `/workday-complete` invoke this, not to run it standalone.
- **`/session-start`** — reads `tasks/health-summary.md` (the artifact this command writes) to surface overnight findings at the top of the next session.
- **`/review-dispatch`** — this command dispatches a reviewer directly with `--problems-only`; it does not go through `/review-dispatch`, which is for feature-level reviews. Don't substitute one for the other.
- **`pipelines/daily-code-health/PIPELINE.md`** — the pipeline definition this command executes. If you need to customize routing or scope, read it directly.
