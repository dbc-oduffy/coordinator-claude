---
description: End-of-day orchestration — update docs, consolidate branches, run health survey
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Update docs, consolidate work branches, and run a health survey. **Does NOT merge to main.** Merging is a deliberate, supervised act via `/merge-to-main`.

## Design Rationale

Main never changes unsupervised or overnight. No live customers are affected by branch state — the splash damage of waiting for the morning is zero. This builds the right habit for when colleagues exist: main is always clean, always supervised.

## Instructions

When invoked, run the full end-of-day sequence. If any step fails, stop and report — don't proceed to later steps on a broken foundation.

### Step 1: Run `/update-docs`

Invoke `/update-docs` for full repo-wide maintenance. This commits and pushes to the current branch.

Wait for it to complete before proceeding.

### Step 2: Branch Consolidation

Consolidate all of today's work branches for this machine into one clean branch.

1. **Discover branches:**
   ```bash
   MACHINE=$(hostname | tr '[:upper:]' '[:lower:]' | tr ' .' '-' | tr -cd 'a-z0-9-')
   TODAY=$(date +%Y-%m-%d)

   # Local branches for today
   git branch --list "work/$MACHINE/$TODAY*"

   # Remote branches for today
   git branch -r --list "origin/work/$MACHINE/$TODAY*"
   ```

2. **If multiple branches exist:** Merge them into the current branch:
   ```bash
   # For each other branch:
   git merge <other-branch> -m "consolidate: merge <other-branch> into $(git branch --show-current)"
   ```
   If merge conflicts occur: resolve them. If conflicts are non-trivial, report to PM and halt.

3. **Rebase on main:**
   ```bash
   git fetch origin main
   git rebase origin/main
   ```
   If rebase conflicts occur: resolve them. This ensures the consolidated branch is up-to-date with main and ready for morning review.

   If rebase fails with non-trivial conflicts:
   ```bash
   git rebase --abort
   ```
   Fall back to merge:
   ```bash
   git merge origin/main -m "merge main into work branch for consolidation"
   ```

4. **Push the consolidated branch:**
   ```bash
   git push origin $(git branch --show-current) --force-with-lease
   ```
   Force-with-lease protects against concurrent pushes. If it rejects (another session pushed since our last fetch):
   ```bash
   git fetch origin
   git rebase origin/$(git branch --show-current)
   git push origin $(git branch --show-current) --force-with-lease
   ```
   If the second attempt also fails, report the conflict to the PM — do not force-push without `--force-with-lease`.

5. **Clean up merged branches:**
   Delete local branches that were merged into the current branch (except the current branch itself):
   ```bash
   git branch --merged | grep "work/$MACHINE/$TODAY" | grep -v "$(git branch --show-current)" | xargs -r git branch -d
   ```

**Feature branches are excluded** — they are intentionally long-lived and not part of end-of-day cleanup.

### Step 3: Code Health Survey (Night Shift)

Run the daily code health check on today's commits. This is the "night shift colleague" — health investigation happens at end-of-day, results are ready for the next morning's session-start.

1. Run `/code-health`
2. The skill handles: finding commits, dispatching reviewer, applying findings, updating health ledger
3. If findings exist, they are committed to the branch by the skill
4. Push to remote after health survey completes — results are safe even if machine shuts down:
   ```bash
   git push origin $(git branch --show-current)
   ```

### Step 3.5: Refresh Code Statistics

If `scc` is available (check `scc` then `~/bin/scc`), run a fresh count:
```bash
scc --no-complexity --no-cocomo --no-duplicates --sort code
```
Include the compact summary (total lines, top 5 languages) in the final summary. This establishes a daily snapshot of project scale. If scc is not installed, skip silently.

### Step 4: Final Summary

```
## Workday Complete

**Docs updated:** [yes/no, what changed]
**Branches consolidated:** [N branches merged into current]
**Branch state:** [branch name], rebased on main, pushed to remote
**Health survey:** [N findings / clean / skipped]
**Code stats:** [total lines / top language breakdown, or "scc not available"]
**Orientation cache:** [refreshed by /update-docs / not present]
**NOT merged to main** — use `/merge-to-main` when ready (runs test suite first)
```

If `$ARGUMENTS` is provided, include it as a summary line at the top: _"Day summary: {arguments}"_

### What This Does NOT Do

- **Merge to main.** Use `/merge-to-main` for that — it runs the test suite first.
- **Delete the work branch.** It stays alive for morning review.
- **Auto-push to main.** Main is supervised-only.

### Concurrent Session Safety

Health files (`tasks/health-ledger.md`, `tasks/health-summary.md`, `tasks/debt-backlog.md`) are global to the project. Only one session should write them — the workday-complete session is inherently single-writer (runs at end of day). Session-start health surface is read-only.

> **Force-with-lease rejection:** Branch consolidation (Step 2) uses `--force-with-lease` which will safely reject if another session pushed to the same branch after our last fetch. If rejection occurs, fetch-rebase-retry once. If that also fails, report to PM.

### Relationship to Other Commands

- **`/merge-to-main`** is the separate, deliberate merge skill. Run it in the morning after reviewing the branch.
- **`/update-docs`** is invoked as Step 1 of this command.
- **`/code-health`** is invoked as Step 3 for the health survey.
