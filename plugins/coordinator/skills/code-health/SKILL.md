---
name: code-health
description: Night-shift code health review — queries completion entries for today's surfaces, dispatches reviewer, applies findings, updates health tracking.
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: (no arguments needed)
---

# Code Health — Night Shift Commit Review

The "night shift colleague." Queries today's completion entries to identify the surfaces that saw recorded work, dispatches a domain-appropriate reviewer with `--problems-only`, applies findings inline via review-integrator, defers complex findings to the debt backlog, updates the health ledger with current grades, and writes a morning-ready summary. Results are waiting at the next workstream-start.

**Announce at start:** "I'm using /code-health to review recent commits."

---

## Never Skip on a "Small" Day

The strongest predictor of a bug-filled review is a small commit count, not a large one. When today's fixes touched one code path, the adjacent or sibling path is the highest-probability next bug — and a small commit count is exactly when reviewers and EMs are most tempted to skip ("only 8 commits, nothing to see"). That's where the regressions hide.

**Run this review on every committed day, regardless of commit count.** The cost-benefit is asymmetric: a 5-minute review on a quiet day catches the silent regression a fix introduced on a parallel handler; skipping a busy day misses bugs the next session will trip on.

The only valid skip condition is the one already in the Failure Modes table: **zero new commits since last check** (on the git-log fallback path) or **zero completion entries today with no fallback commits either.** Anything else — even a single completion entry or commit — run the review.

---

## Step 1: Identify Surfaces from Today's Completion Entries

Determine the scope of surfaces to review from today's completion log, not from raw commit history:

1. Query today's completion entries:
   ```bash
   bin/query-completions --where "created=<YYYY-MM-DD>" --format json
   ```
   Substitute today's date for `<YYYY-MM-DD>`.
2. Extract the file paths or subsystem names mentioned in the entries' `title`, `description`, and any `files` fields.
3. **If no entries for today:** Read `tasks/health-ledger.md` header for the `Last daily check:` date and fall back to:
   ```bash
   git log --since="<last-check-date>" --oneline --stat
   ```
   Update the `Last daily check` timestamp in the health ledger, report "No completion entries for today — fell back to git log scope," and continue with the commit-based surface list.

The completion-entry approach reduces tokens spent re-reviewing unchanged code by scoping the review to only the surfaces that saw recorded work today.

---

## Step 2: Generate Diff Scope

Scope the diff to the surfaces identified in Step 1:

```bash
git diff HEAD -- <file1> <file2> ...
```

If Step 1 yielded a subsystem or directory name rather than individual files, use the directory prefix (e.g., `skills/code-health/`). If the fallback git-log path was taken, use:

```bash
git diff <last-check-commit>..HEAD
```

Summarize scope: which files changed, how many insertions/deletions, which systems are affected. This summary drives the Sonnet reviewer's emphasis (vocabulary/what-to-weight) in Step 3 — not reviewer selection (that's always `code-reviewer`).

---

## Step 3: Dispatch the Sonnet Reviewer (non-persona)

The nightly health pass dispatches the **Sonnet `code-reviewer`** (`agents/code-reviewer.md`) — **NOT** a named persona. This is recurring Sonnet-tier code review, which by doctrine uses `code-reviewer`, never a persona (personas are Opus-only and reserved for the weekly arch pass, the merge gate, and explicit architectural decisions). Routing a *nightly* health check to an Opus persona is the same daily-cadence miscalibration `/workday-complete` Step 4c was corrected for.

Domain still matters — but for **vocabulary and emphasis**, not reviewer identity. State the dominant change type in the brief so the Sonnet reviewer knows what to scrutinize:

| Dominant change type | Tell the reviewer to weight… |
|---|---|
| Game dev / Unreal Engine | UE idioms, engine-lifecycle/ownership, Blueprint/C++ seams |
| Frontend / UI | component/token reuse, state flow, accessibility |
| Data / ML / science | numeric correctness, data contracts, reproducibility |
| Mixed, backend, or architecture | coupling, error paths, interface seams |

If multiple domains are present, weight toward the dominant one (most files changed / most critical path). A finding that genuinely needs persona/Opus judgment is **flagged for the weekly arch pass** (`/workweek-complete` Step 7.5), not escalated to an Opus dispatch here.

Dispatch `code-reviewer` (`model: "sonnet"`) with `--problems-only` and `run_in_background: true`. This is a health check — suppress praise and suggestions, return problems only. Process findings when notified of completion.

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
   - **Source:** `daily-health/code-reviewer/{date}`
   - **Status:** `open`

3. Update the header summary counts.

**Concurrency note:** `debt-backlog.md` may be written by overlapping sessions (e.g., `/architecture-audit` running concurrently). Always append new rows at the bottom of the table — never rewrite or reorganize existing rows. When updating an entry's status, match by ID column only. Update the `> Last triaged:` header line to today's date; do not remove or reorder any other header fields.

---

## Step 6: Update Health Ledger

1. Check for `tasks/health-ledger.md`. If it doesn't exist, create it from this template:

   ```markdown
   # System Health Ledger

   > Last daily check: YYYY-MM-DD | Last full audit: never

   **Last full audit:** (none — run /architecture-survey)
   **Last targeted audit:** (none — folds into /workweek-complete when >10 days)

   > Next rotation target: [pending first audit]

   ## System Index

   | System | Grade | Status | Last Audited | Open P0 | Open P1 | Open P2 | Lines | Notes |
   |--------|-------|--------|-------------|---------|---------|---------|-------|-------|
   ```

2. Update `Last daily check` in the header to today's date.
3. If findings changed system grades, update the relevant rows.
4. If a system was touched by commits but has no row yet, add it with grade `?` (unaudited).

**Grade synchronization:** The health ledger is the single source of truth for system grades. `/architecture-audit` also updates grades here after weekly audits. When updating a row, read the existing grade first — only change it if the daily review's findings explicitly warrant a grade change. Do not downgrade a system that was just upgraded by a recent `/architecture-audit` run unless new P0/P1 findings justify it.

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

Write results to `tasks/health-summary.md` — this is what workstream-start reads the next morning:

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
git commit -m "daily-code-health: review of surfaces from completion entries [date]"
```

The post-commit hook pushes automatically.

---

## Failure Modes

| Situation | Action |
|---|---|
| No health ledger on first run | Create from template, use last 24 hours as scope |
| No completion entries for today | Fall back to `git log --since=<last-check>` scope; report fallback in health summary |
| `bin/query-completions` not found | Fall back to git-log scope; note missing binary in health summary |
| No new commits since last check (fallback path) | Update timestamp, report, and exit — no reviewer dispatch |
| Reviewer returns no findings | Skip Steps 4-5, proceed directly to Step 6 |
| Debt backlog doesn't exist | Create from template before adding entries |
| Complex finding can't be fixed inline | Add to debt backlog with severity and effort estimate |
| Git commands fail (no commits, detached HEAD) | Report the error and stop — do not attempt to guess the diff |
| review-integrator unavailable | Log findings to health-summary.md manually, note as deferred |

---

## Cost

1 Sonnet `code-reviewer` dispatch (with `--problems-only`) + 1 Sonnet `review-integrator` dispatch if findings exist. No persona, no Opus at this nightly cadence. Approximately 5-10 minutes for a typical day's commits. If no findings, the reviewer dispatch is the only cost.

---

## Relationship to Other Commands

- **`/workday-complete`** — primary trigger for this command; runs code-health as part of its end-of-day health survey phase. The normal path is to let `/workday-complete` invoke this, not to run it standalone.
- **`/workstream-start`** — reads `tasks/health-summary.md` (the artifact this command writes) to surface overnight findings at the top of the next session.
- **`/review-code`** — this command dispatches a reviewer directly with `--problems-only` for targeted code health assessment; it does not go through the full `/review-code` feature-review workflow. Don't substitute one for the other.
- **`pipelines/daily-code-health/PIPELINE.md`** — the pipeline definition this command executes. If you need to customize routing or scope, read it directly.
