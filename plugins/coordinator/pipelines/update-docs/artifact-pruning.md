---
name: update-docs/artifact-pruning
description: "Bulk-prune accumulated session artifacts (plans/, archive/handoffs/, stale task dirs). Inlined by /update-docs Phase 8b."
version: 1.0.0
---

# Artifact Pruning Pipeline

> **Inlined by `/update-docs` Phase 8b.** Not invoked standalone — `/update-docs` is the only caller. Replaces the former `coordinator:artifact-consolidation` skill (absorbed 2026-05-06).

> **Negative-spec — consumed markers:** This pipeline moves and deletes files. It does NOT write `<!-- consumed: YYYY-MM-DD -->` markers — that's `/pickup`'s exclusive responsibility. Active handoffs in `tasks/handoffs/` are outside this pipeline's scope; chain-aware archival of those is `pipelines/update-docs/handoff-archival.md`'s job (Phase 8), which runs immediately before this pipeline.

## When This Runs

Every `/update-docs` invocation, after Phase 8 (handoff archival) completes. Conservative thresholds make most runs no-ops — the pipeline only deletes when accumulated artifacts cross the threshold lines below. `/update-docs` is itself PM-invoked, and the safety commit (Step 1 below) makes any deletion `git revert`-able as a single operation.

## Scope

| Directory | What accumulates | Pruning rule |
|-----------|-----------------|--------------|
| `plans/` | Session plan files (`*.md`) | Delete plans older than 14 days with no open references |
| `archive/handoffs/` | Consumed handoff files | Keep the 10 most recent; delete the rest |
| `tasks/*/` | Feature task directories | Delete dirs where all `todo.md` items are `[x]` AND the feature branch is merged or deleted |
| `tasks/handoffs/` | Active handoffs | **Out of scope** — `pipelines/update-docs/handoff-archival.md` (Phase 8) handles these |

## Steps

### Step 1: Inventory

1. **Count and classify:**
   - **Plans (`plans/*.md`):**
     - PRUNE if file is older than 14 days AND not referenced by any active handoff, task file, or `MEMORY.md` entry. Check references by grepping the filename across `tasks/handoffs/`, `tasks/`, and `MEMORY.md`.
     - KEEP otherwise.
   - **Archived handoffs (`archive/handoffs/*.md`):**
     - KEEP the 10 most recent by filename timestamp.
     - PRUNE the rest — they've been consumed and their context lives in successor handoffs.
   - **Feature task directories (`tasks/<feature>/`):**
     - PRUNE if `todo.md` exists and all items are `[x]`, AND no `lessons.md` with unmerged entries, AND the feature branch (if identifiable from the dir name) is merged or deleted.
     - KEEP if any `[ ]` items remain or unmerged lessons present.
     - **Never delete:** `tasks/lessons.md` (global), `tasks/health-ledger.md`, `tasks/bug-backlog.md`, `tasks/debt-backlog.md`, `tasks/architecture-atlas/`, `tasks/improvement-queue.md`, `tasks/coordinator-improvement-queue.md`, `tasks/handoffs/` (active), `tasks/week-changelog/`.

2. **If nothing classifies as PRUNE,** record `prune_count: 0` for the Phase 13 summary and exit this pipeline.

### Step 2: Safety Commit

Before any deletions, snapshot current state:

```
~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "pre-prune checkpoint (update-docs Phase 8b)"
```

This makes the entire prune operation revertible as a single `git revert`.

### Step 3: Delete

Use `git rm` so deletions appear in git history:
- Plans: `git rm plans/<file>`
- Archived handoffs: `git rm archive/handoffs/<file>`
- Feature task dirs: `git rm -r tasks/<feature>/`

Remove any empty directories left behind on the filesystem.

### Step 4: Commit

```
~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "artifact pruning: pruned N plans, N handoffs, N task dirs (update-docs Phase 8b)"
```

### Step 5: Record Counts

Pass `pruned_plans`, `pruned_archived_handoffs`, `pruned_task_dirs`, and the safety-commit SHA to the Phase 13 summary.

## Tuning

The defaults (14-day plan retention, 10 archived handoffs) live in this pipeline file. Override by editing this file — there is no flag interface, because this pipeline runs unconditionally as part of `/update-docs`. Repos with materially different cadence should fork this file rather than thread tuning flags through `/update-docs`.

## Notes

- The safety commit ensures `git revert <safety-sha>` undoes the entire prune in one step.
- For repos with 200k+ artifacts, present counts and disk-reclaimed size in the summary, not per-file lists.
- Never delete the architecture atlas, global tracking files, or active handoffs. When in doubt, keep.
- For `distill`-then-delete (extract knowledge into wiki before deleting source), use `/distill` instead — it runs upstream of this pipeline conceptually. This pipeline prunes raw scaffolding only.
