---
name: update-docs/artifact-pruning
description: "Bulk-prune accumulated session artifacts (plans/, archive/handoffs/, stale task dirs). Inlined by /update-docs Phase 8b."
version: 1.0.0
---

# Artifact Pruning Pipeline

> **Inlined by `/update-docs` Phase 8b.** Not invoked standalone — `/update-docs` is the only caller. Replaces the former `coordinator:artifact-consolidation` skill (absorbed 2026-05-06).

> **This is age-archival, not knowledge-archival.** Two lifecycles wear the word "archive": **knowledge-archival** (`/distill` — trim a ripe plan to its canonical skeleton and move it to `archive/specs/YYYY-MM/` *after* extracting its knowledge into wiki/DR) and **age-archival** (this pipeline — time-thresholded janitorial pruning of aged, non-knowledge-bearing artifacts; no extraction). This pipeline owns the latter only. Boundary doctrine: `commands/distill.md` § Relationship to Other Commands; `docs/wiki/cruft-sweep-cadence.md`.

> **Negative-spec — consumed markers:** This pipeline moves and deletes files. It does NOT write `<!-- consumed: YYYY-MM-DD -->` markers — that's `/pickup`'s exclusive responsibility. Active handoffs in `state/handoffs/` are outside this pipeline's scope; chain-aware archival of those is `pipelines/update-docs/handoff-archival.md`'s job (Phase 8), which runs immediately before this pipeline.

## When This Runs

Every `/update-docs` invocation, after Phase 8 (handoff archival) completes. Conservative thresholds make most runs no-ops — the pipeline only deletes when accumulated artifacts cross the threshold lines below. `/update-docs` is itself PM-invoked, and the safety commit (Step 1 below) makes any deletion `git revert`-able as a single operation.

## Scope

| Directory | What accumulates | Pruning rule |
|-----------|-----------------|--------------|
| `docs/plans/` | Session plan files (`*.md`) | Delete plans older than 14 days with no open references, subject to the ripeness-safety guard below. **Ordering hazard (mirror of the `cross-repo/archive/` 90d floor):** this 14d floor age-DELETES plans — it does not knowledge-archive them. If a plan is RIPE-but-unharvested (delivered, but `/distill` has not yet trimmed→archived it to `archive/specs/`), deleting it here loses the wiki/DR promotion (git history survives, but the extraction never runs). The floor MUST exceed the `/distill` cadence; if `/distill` runs less often than every 14d, raise this floor proportionally — same cadence-exceeds-floor anchor as the cross-repo memo row. Knowledge-archival is `/distill`'s job and runs upstream of this deletion. **Ripeness-safety guard:** a plan in `docs/plans/` is ONLY eligible for age-deletion when BOTH conditions hold: (a) its frontmatter `status:` is terminal-abandoned (`superseded`, `abandoned`, or `cancelled`) OR a trimmed copy already exists under `archive/specs/**` (i.e. `/distill` has already knowledge-archived it — see `commands/distill.md` § Relationship to Other Commands); AND (b) it is not referenced by any active handoff, task file, or `MEMORY.md` entry. NEVER age-delete a plan whose `status:` is `implemented`/`shipped` but which has no counterpart under `archive/specs/**` (ripe-unharvested — that extraction is `/distill`'s job, not this pipeline's). NEVER age-delete a plan with `status:` `draft`, `in-progress`, or `reviewed` (in-flight). When `status:` is absent or unrecognised, treat as in-flight (KEEP). |
| `archive/handoffs/` | Consumed handoff files | Keep the 10 most recent by filename timestamp; delete the rest. **Month-subfolder transition:** files are migrating from flat `archive/handoffs/*.md` to month-subfolders `archive/handoffs/YYYY-MM/<file>.md` (matching the `archive/specs/YYYY-MM/` convention). Enumerate BOTH `archive/handoffs/*.md` AND `archive/handoffs/*/*.md` to cover files in either layout during the transition. Select the 10 most recent across the combined set; delete the rest individually (not `git rm -r`). |
| `tasks/*/` | Feature task directories | Delete dirs where all `todo.md` items are `[x]` AND the feature branch is merged or deleted |
| `state/handoffs/` | Active handoffs | **Out of scope** — `pipelines/update-docs/handoff-archival.md` (Phase 8) handles these |
| `tasks/doc-link-check-*.md` | doc-link-checker reports from prior `/update-docs` runs | Keep the 3 most recent; delete the rest (PRUNE rule below) |
| `cross-repo/archive/` | Closed `actioned` memos swept here after the receiver has acted | Delete memos with `status: actioned` older than **90 days** — 90d is chosen as ≥3× the expected `/distill` cadence so this janitorial sweep never deletes un-mined evergreen content before `/distill` has had a chance to run; if the `/distill` cadence lengthens past 30d, raise this floor proportionally. **Ordering hazard:** this 90d floor MUST exceed the max distill-run interval — if update-docs deletes a >90d actioned memo that `/distill` never mined, any evergreen content is lost (git history survives, but the promotion job never ran). The cadence-exceeds-floor anchor is what closes this hazard. |

## Steps

### Step 1: Inventory

1. **Count and classify:**
   - **Plans (`docs/plans/*.md`):**
     - PRUNE if ALL of the following hold: (1) file is older than 14 days; (2) not referenced by any active handoff, task file, or `MEMORY.md` entry (grep the filename across `state/handoffs/`, `tasks/`, and `MEMORY.md`); AND (3) the ripeness-safety guard passes — `status:` is `superseded`/`abandoned`/`cancelled` OR a trimmed copy exists under `archive/specs/**`. Plans with `status:` `implemented`/`shipped` that have no `archive/specs/**` counterpart are ripe-but-unharvested (KEEP; `/distill`'s job). Plans with `status:` `draft`/`in-progress`/`reviewed` or absent/unrecognised are in-flight (KEEP).
     - KEEP otherwise.
   - **Archived handoffs (`archive/handoffs/*.md` and `archive/handoffs/*/*.md`):**
     - Enumerate BOTH globs to cover flat files and month-subfoldered files during the ongoing migration to `archive/handoffs/YYYY-MM/` layout.
     - KEEP the 10 most recent across the combined set by filename timestamp.
     - PRUNE the rest — they've been consumed and their context lives in successor handoffs.
   - **doc-link-checker reports (`tasks/doc-link-check-*.md`):**
     - KEEP the 3 most recent by filename timestamp.
     - PRUNE the rest — superseded by newer reports.
   - **Feature task directories (`tasks/<feature>/`):**
     - PRUNE if `todo.md` exists and all items are `[x]`, AND no `lessons.md` with unmerged entries, AND the feature branch (if identifiable from the dir name) is merged or deleted.
     - KEEP if any `[ ]` items remain or unmerged lessons present.
     - **Never delete:** `state/lessons.md` (global), `state/health-ledger.md`, `state/bug-backlog.md`, `state/debt-backlog.md`, `docs/architecture/`, `state/improvement-queue.md`, `state/coordinator-improvement-queue.md`, `state/handoffs/` (active), `state/week-changelog/`.
   - **Cross-repo archive memos (`cross-repo/archive/*.md`):**
     - PRUNE if `status: actioned` AND file mtime > 90 days. Parse `status:` from YAML frontmatter; do NOT prune memos lacking a `status:` field (treat as open/unknown).
     - KEEP if `status:` is absent, `open`, or any value other than `actioned`, regardless of age — these are not yet closed channel traffic.
     - KEEP if `status: actioned` AND mtime ≤ 90 days — `/distill` should have a chance to mine them first.
     - **`cross-repo/archive/` is NOT on the never-delete list** — age-based pruning of actioned memos here is safe and intentional. The 90d floor is the guard against premature deletion before `/distill` runs (see Scope table rationale above).

2. **If nothing classifies as PRUNE,** record `prune_count: 0` for the Phase 13 summary and exit this pipeline.

### Step 2: Safety Commit

Before any deletions, snapshot current state:

```bash
CLAUDE_INVOKING_COMMAND=update-docs ~/.claude/plugins/coordinator/bin/coordinator-safe-commit --blanket "pre-prune checkpoint (update-docs Phase 8b)"
```

This makes the entire prune operation revertible as a single `git revert`.

### Step 3: Delete

Use `git rm` so deletions appear in git history:
- Plans: `git rm docs/plans/<file>`
- Archived handoffs: `git rm archive/handoffs/<file>` or `git rm archive/handoffs/<YYYY-MM>/<file>` depending on layout — individual files, not `git rm -r`
- doc-link-check reports: `git rm tasks/doc-link-check-<file>`
- Feature task dirs: `git rm -r tasks/<feature>/`
- Cross-repo archive memos: `git rm cross-repo/archive/<file>` (individual files, NOT `git rm -r cross-repo/archive/` — the directory and its README must survive)

Remove any empty directories left behind on the filesystem.

### Step 4: Commit

```bash
CLAUDE_INVOKING_COMMAND=update-docs ~/.claude/plugins/coordinator/bin/coordinator-safe-commit --blanket "artifact pruning: pruned N plans, N handoffs, N task dirs (update-docs Phase 8b)"
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
