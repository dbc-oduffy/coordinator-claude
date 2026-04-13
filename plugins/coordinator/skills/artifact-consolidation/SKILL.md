---
name: artifact-consolidation
description: "Use when artifact directories are bloated, during periodic maintenance, or when disk usage from session debris is excessive. Prunes and consolidates accumulated session artifacts — plans/, archive/handoffs/, stale task dirs. Supports dry-run mode. Standalone invocation only — not part of /update-docs."
version: 1.0.0
---

# Artifact Consolidation

## Overview

Session-based workflows generate artifacts: plan files, handoff archives, feature task directories, execution trackers. These accumulate indefinitely unless actively pruned. This skill consolidates them in bulk.

**For distill-then-delete:** If you want to extract knowledge into wiki documents before deleting artifacts, use `/distill` instead. This skill prunes without extracting; `/distill` extracts into `docs/wiki/` and `docs/decisions/` first.

**This is a destructive operation** — it deletes files. Always start with a dry run. The PM approves the plan before any deletions.

## Scope

| Directory | What accumulates | Pruning strategy |
|-----------|-----------------|-----------------|
| `plans/` | Session plan files (`*.md`) | Delete plans older than 14 days with no open references |
| `archive/handoffs/` | Consumed handoff files | Keep the most recent 10; delete the rest |
| `tasks/*/` | Feature task directories | Delete dirs where all items are `[x]` completed and the feature branch is merged |
| `tasks/handoffs/` | Active handoffs | Chain-aware archival (handled by `handoff-archival`); this skill does NOT touch active handoffs |

## Steps

### Phase 1: Inventory (Dry Run)

Run this phase first, always. Present the results to the PM before proceeding.

1. **Count artifacts:**
   - `plans/` — count `.md` files, note oldest and newest timestamps
   - `archive/handoffs/` — count files
   - `tasks/*/` — list feature directories, note which have all items completed
   - Report total file count and disk usage (`du -sh` each directory)

2. **Classify each artifact as KEEP or PRUNE:**

   **Plans (`plans/*.md`):**
   - PRUNE if: file is older than 14 days AND not referenced by any active handoff, task file, or MEMORY.md entry
   - KEEP if: referenced by an active handoff or in-progress task dir, OR younger than 14 days
   - To check references: grep the filename across `tasks/handoffs/`, `tasks/`, and `MEMORY.md`

   **Archived handoffs (`archive/handoffs/*.md`):**
   - KEEP the 10 most recent by filename timestamp
   - PRUNE the rest — they've been consumed and their context lives in successor handoffs

   **Feature task directories (`tasks/<feature>/`):**
   - PRUNE if: `todo.md` exists and all items are `[x]`, AND no `lessons.md` with unmerged entries, AND the feature branch (if identifiable from the dir name) is merged or deleted
   - KEEP if: any `[ ]` items remain, or contains unmerged lessons
   - **Never delete** `tasks/lessons.md` (global), `tasks/health-ledger.md`, `tasks/bug-backlog.md`, `tasks/debt-backlog.md`, or `tasks/architecture-atlas/`

3. **Present the dry-run report:**

   ```
   ## Artifact Consolidation — Dry Run

   | Category | Total | Keep | Prune |
   |----------|-------|------|-------|
   | Plans | N | N | N |
   | Archived handoffs | N | N | N |
   | Feature task dirs | N | N | N |

   **Total files to delete:** N
   **Disk to reclaim:** ~Xkb

   ### Files to prune:
   - plans/2026-01-15-foo.md (67 days old, no references)
   - ...

   ### Files to keep:
   - plans/2026-03-18-bar.md (2 days old)
   - ...
   ```

4. **Wait for PM approval.** Do not proceed to Phase 2 without explicit confirmation.

### Phase 2: Execute Pruning

1. **Create a safety commit** before any deletions:
   ```
   git add -A && git commit -m "pre-consolidation checkpoint"
   ```

2. **Delete PRUNE-classified files** using `git rm` (so deletions are tracked in git history):
   - Plans: `git rm plans/<file>`
   - Archived handoffs: `git rm archive/handoffs/<file>`
   - Feature task dirs: `git rm -r tasks/<feature>/`

3. **Remove empty directories** left behind (git doesn't track empty dirs, but the filesystem might retain them)

4. **Commit the consolidation:**
   ```
   git add -A && git commit -m "artifact consolidation: pruned N plans, N handoffs, N task dirs"
   ```

5. **Report results:**
   ```
   ## Consolidation Complete

   - Deleted N plan files
   - Deleted N archived handoffs
   - Deleted N feature task directories
   - Reclaimed ~Xkb
   - Safety commit: <hash> (revert target if needed)
   ```

## Tuning

The defaults (14-day plan retention, 10 archived handoffs) are starting points. Override with arguments:

- `/artifact-consolidation --plan-age 30` — keep plans younger than 30 days
- `/artifact-consolidation --keep-handoffs 20` — keep 20 most recent archived handoffs
- `/artifact-consolidation --dry-run` — inventory only, no deletions (default on first run)

## Notes

- This skill is standalone — not part of `/update-docs`. Invoke it explicitly when artifact bloat is noticeable.
- The safety commit ensures `git revert` can undo the entire consolidation in one step.
- For repos with 200k+ artifacts, consider running Phase 1 with `find | wc -l` rather than listing individual files — present counts and size, not filenames.
- **Never delete the architecture atlas** (`tasks/architecture-atlas/`), global tracking files, or active handoffs. When in doubt, keep.
