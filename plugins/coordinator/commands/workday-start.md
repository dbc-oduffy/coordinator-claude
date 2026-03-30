---
description: Morning orientation — triage handoffs, surface staleness, align priorities
allowed-tools: ["Read", "Write", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[optional day focus]"
---

# Workday Start — Morning Orientation

Prepare the day's session-start calls to be maximally efficient. Ensure context is fresh, priorities are clear, and any overnight health findings are surfaced.

**Announce at start:** "I'm running workday-start to prepare the day's context."

## Step 1: Handoff Triage

Read all files in `tasks/handoffs/`. For each:

1. **Check age** — filename includes timestamp (`YYYY-MM-DD_HHMMSS_sessionid.md`)
2. **Check branch activity** — is the handoff's referenced branch still active? Any commits since the handoff was written?
3. **Categorize:**
   - **Actionable** (keep) — <48hr old, OR has recent branch activity, OR references open work
   - **Stale** — >48hr old AND no branch activity since handoff AND work appears complete
4. **Surface, don't archive.** Report stale handoffs to the PM but leave archival to `/update-docs` — it is the single authority on handoff lifecycle. This avoids competing archival logic between two commands.
5. **Report:** "N actionable handoffs for today's sessions. M stale handoffs flagged (will archive on next /update-docs run)."

**Why surface-only:** update-docs Phase 8 already handles archival (via the `handoff-archival` skill) with its 48-hour rule. workday-start adds value by surfacing branch-activity context (a 3-day-old handoff with yesterday's commits is still actionable), but doesn't need to be a second archiver.

**Note:** Handoff archival (via `/update-docs`) respects branch activity — active branches keep their handoffs.

## Step 2: Doc Freshness

Check if documentation is stale relative to recent code changes:

1. Find the last update-docs run:
   ```bash
   git log --oneline --grep="update-docs\|workday-complete" --since="7 days ago" -1
   ```
2. Find commits since that run:
   ```bash
   git log --oneline <last-update-docs-commit>..HEAD
   ```
3. **If commits exist since last update-docs:** Flag: _"Docs are stale — [N] commits since last update-docs. Recommend running `/update-docs` before feature work."_ Do NOT dispatch update-docs automatically — it commits files, which would race with any other workday-start operations on the working tree. The PM can invoke it after workday-start completes.
4. **If no commits since:** "Docs are current."

## Step 3: Test Staleness

Check if the test suite should be run:

1. Detect test framework (same as bug-sweep Phase 0)
2. If tests exist:
   - Find the most recent test-related commit or CI run
   - Find code changes since then
   - **If code changed since last test run:** Flag: _"Tests haven't been run since [N] commits ago. Recommend running test suite."_
   - Don't run them automatically — the PM decides. But surface the staleness.
3. If no tests exist: skip silently

## Step 3.5: Bug Sweep Staleness

Check if a bug sweep should be suggested — based on **code churn since last sweep**, not just calendar time:

1. Read `tasks/bug-backlog.md` header for `Last sweep:` date and `Commit at sweep:` hash

   **Expected header format** (written by `/bug-sweep`):
   `> Last sweep: YYYY-MM-DD | Commit at sweep: [short hash] | Open: N items (P0: X, P1: Y, P2: Z)`
   Parse `Last sweep:` for date and `Commit at sweep:` for the anchor hash.

2. If no backlog exists: no sweep has ever run. Check codebase substance:
   ```bash
   # Count source files (not docs, configs, or generated files)
   find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.cpp" -o -name "*.h" -o -name "*.cs" -o -name "*.go" -o -name "*.rs" | grep -v node_modules | grep -v __pycache__ | wc -l
   ```
   If the repo has >50 source files, suggest a first sweep: _"No bug sweep has ever run on this codebase ([N] source files). Recommend running bug-sweep."_
   If <50 source files, skip silently — small repos don't need formal sweeps.
3. If backlog exists, count commits since the sweep's anchor commit:
   ```bash
   git rev-list --count <sweep-commit>..HEAD
   ```
4. **Suggest sweep if:**
   - >50 commits since last sweep AND >7 days since last sweep (significant churn with time floor — prevents nagging during sprint-mode work), OR
   - >14 days since last sweep AND >20 commits since last sweep (moderate churn + time)
   - _"Bug sweep last ran [date] ([N] commits ago). Recommend running bug-sweep before new feature work."_
5. If few commits since last sweep: "Bug sweep is current ([N] commits since last sweep)."

**The trigger is churn, not calendar.** A repo with no commits in 2 months doesn't need sweeping. A repo with 80 commits in a week might, but we wait at least 7 days to avoid suggestion fatigue during intensive work.

## Step 4: Priority Alignment

Surface the project's current state and help align on today's focus:

1. Read `docs/project-tracker.md` (if exists):
   - Active workstreams and their statuses
   - Items that are Ready or Executing
   - Blocked items and their blockers
2. Read `ACTION-ITEMS.md` or equivalent (if exists):
   - Outstanding action items
3. Read `tasks/health-ledger.md` (if exists):
   - Systems at ACTION/CRITICAL status
   - Overdue audits
4. Read `tasks/bug-backlog.md` (if exists):
   - Open bug count and severity distribution
5. Read `tasks/debt-backlog.md` (if exists):
   - Open debt count
6. Read `tasks/architecture-atlas/systems-index.md` (if exists):
   - Number of mapped systems
   - Any systems with `last_mapped` date >90 days ago (stale)
   - If file doesn't exist: note "no atlas" for the report

## Step 5: Morning Briefing

Present a concise morning report:

```markdown
## Good Morning — Workday Start

**Date:** YYYY-MM-DD
**Branch:** [current branch]

### Context Freshness
- Handoffs: [N] actionable for today, [M] stale (flagged for /update-docs archival)
- Docs: [current / stale — N commits since last update-docs]
- Tests: [current / N commits since last run — suggest running]
- Health: last daily check [today/N days ago], last weekly audit [N days ago]
- Atlas: [N systems mapped, M stale >90 days / no atlas]
- Bug backlog: [N open (P0: X, P1: Y) / empty / no backlog]
- Bug sweep: [current (N commits since) / suggest sweep (N commits since last)]

### Priority Suggestions
Based on project state:
1. **[If bugs exist]** Fix [top severity bug] before new feature work
2. **[If sweep stale]** Run bug-sweep — [N] commits since last sweep
3. **[If tests stale]** Run test suite to verify current state
4. **[If atlas stale]** Consider running deep-architecture-audit refresh
5. **[If tracker items ready]** [Workstream X] is ready for execution
6. **[If debt high]** Debt backlog has [N] items — consider debt-triage

### What should today's focus be?
[Surface tracker Ready items, handoff action items, and PM-facing options]
```

**Set marker:** Write `tasks/.workday-start-marker` with today's date. Single location, no dependency on health tracking subsystem. Session-start checks this one file.
```
YYYY-MM-DD
```

## Step 5.5: Write Orientation Cache

Generate `tasks/orientation_cache.md` — a compact summary for the SessionStart hook to inject in subsequent sessions instead of raw repomap/DIRECTORY content.

**Content derivation:**
1. **Structure:** Read `tasks/repomap.md`, extract top 15 entries by rank. Note total file count.
2. **Navigation:** Read `DIRECTORY.md` or `docs/DIRECTORY.md`, summarize at directory level (directory name + file count + purpose).
3. **Code Statistics:** Run `scc --no-complexity --no-cocomo --no-duplicates --sort code` (if scc is available). Include a compact summary: total lines of code, top 5 languages with line counts. This calibrates session agents on project scale. If scc is not installed, skip silently — `~/bin/scc` is the conventional install path on Windows.
4. **Health Snapshot:** Compact version of the Morning Briefing's health data (already in context from Steps 3-4).
5. **Doc Inventory:** Checklist of standard docs (already checked in Step 2).
6. **Staleness markers:** Repomap age, last update-docs run (already checked in Step 2).

**Frontmatter:** Include `generated_by`, `generated_at` (ISO 8601), `git_head_at_generation` (current HEAD short hash).

**Target: 40-60 lines.** This replaces ~300 lines of raw hook injection for subsequent sessions.

**If `tasks/` directory doesn't exist:** Skip. Not all repos use `tasks/`.

## What This Does NOT Do

- **Run bug-sweep.** That's a dedicated operation the PM invokes when ready.
- **Run daily-code-health.** That's the night shift (workday-complete Step 3).
- **Run deep-architecture-audit.** That's monthly. workday-start just surfaces atlas staleness.
- **Merge to main.** Use `/merge-to-main` for that.
- **Choose work.** That's session-start's Engage section. workday-start prepares the ground; session-start picks the work.
- **Replace session-start.** workday-start prepares the ground; session-start picks the work.
- **Auto-dispatch update-docs.** It commits files, which would race with workday-start operations. Flag staleness; the PM invokes manually after workday-start completes.

## Relationship to Other Commands

- **`session-start`** — runs per-session (many per day). workday-start runs once. Session-start detects if workday-start ran today and skips redundant checks.
- **`workday-complete`** — the evening counterpart. Runs update-docs, consolidates branches, runs health survey.
- **`update-docs`** — may be recommended by workday-start if docs are stale. Not auto-dispatched.
- **`bug-sweep`** — independent skill. workday-start surfaces backlog state but doesn't run the sweep.

## Concurrent Session Safety

workday-start is read-only for all project tracking files. It writes only one file: `tasks/.workday-start-marker`. Multiple sessions can safely read the same health files; the marker is a simple date string with no merge-conflict risk.

If `$ARGUMENTS` is provided, include it as a focus hint in the Morning Briefing: _"Requested focus: {arguments}"_
