---
description: "Distill accumulated session artifacts (plans, handoffs, completed work) into evergreen wiki documents (docs/guides/, docs/decisions/), then delete source material. Extract knowledge before pruning — the pipeline that bridges artifact-consolidation and wiki maintenance."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--dry-run] [--no-delete] [path]"
---

# Distill — Artifact Distillation Pipeline

Extract knowledge from accumulated session artifacts into evergreen wiki documents, then delete the source material. The archive is the compost heap; the wiki is the garden.

**Reference:** Full pipeline design in `~/.claude/plugins/oduffy-custom/coordinator/pipelines/artifact-distillation/PIPELINE.md`. Agent prompt templates in the same directory's `agent-prompts.md`.

**Announce at start:** "I'm running `/distill` to extract knowledge from [N artifacts / artifacts in path] into wiki documents."

**For bulk pruning without knowledge extraction, use `coordinator:artifact-consolidation` instead.**

---

## Arguments

`$ARGUMENTS` may include any combination of:

**`--dry-run`**
Run Phases 0-3 only. Preview extraction results and the deletion manifest, but apply nothing to disk. Presents the summary at Phase 4 and stops. Use to verify what would be extracted before committing.

**`--no-delete`**
Apply wiki updates (Phases 0-5 write steps), but skip all deletions. For repos that want the wiki enrichment without sacrificing source material. Phase 5 writes guides and decision records but skips steps 4-7 (deletion, log update, scratch clean).

**`[path]`**
Scope the inventory to a specific subdirectory. Only artifacts under that path are processed. Example: `/distill tasks/camera-refactor/` distills a single feature directory.

### Examples

```
/distill                          # full repo distillation
/distill --dry-run                # preview only, no writes
/distill --no-delete              # extract wiki content, keep source files
/distill tasks/camera-refactor/   # scope to a single feature dir
/distill --dry-run plans/         # preview what would be extracted from plans/
```

---

## Phase Overview

Full phase definitions, dispatch instructions, scratch path conventions, and failure modes are in `PIPELINE.md`. This is a summary for orientation.

```
Phase 0 (Coordinator) → Phase 1 (Haiku ×N, parallel) → Phase 1.5 (Haiku ×N, QG)
  → [Clustering] → Phase 2 (Sonnet ×M, parallel) → Phase 3 (Opus, single)
  → Phase 4 (PM gate) → Phase 5 (Coordinator, apply + delete)
```

| Phase | Model | Purpose |
|-------|-------|---------|
| **Phase 0** | Coordinator | Inventory artifacts, catalog formats, read existing wiki, group into batches, generate run ID |
| **Phase 1** | Haiku (parallel) | Scan each batch — extract knowledge nuggets (`[DECISION]`, `[KNOWLEDGE]`, `[EPHEMERAL]`, `[AMBIGUOUS]`) |
| **Phase 1.5** | Haiku (parallel) | Quality gate — verify Phase 1 coverage, template compliance, and path spot-checks |
| **Clustering** | Coordinator or Haiku | Regroup nuggets from input-batch ordering to output-topic ordering |
| **Phase 2** | Sonnet (parallel) | One agent per guide topic — synthesize nuggets into guide content and decision records |
| **Phase 3** | Opus (single) | Cross-reference assembly — apply deltas, resolve contradictions, produce deletion manifest |
| **Phase 4** | Coordinator | PM approval gate — present deletion manifest, wait for explicit approval |
| **Phase 5** | Coordinator | Apply wiki writes, commit additions, delete approved artifacts, update distillation log |

**If `--dry-run`:** Phases 4-5 are skipped. The pipeline stops after Phase 3 and presents the summary.

**If `--no-delete`:** Phase 5 applies wiki writes and commits, but skips artifact deletion (steps 4-7).

---

## Relationship to Other Commands

| Command | When to use |
|---------|-------------|
| `/distill` | Extract knowledge into wiki docs, then delete source material |
| `coordinator:artifact-consolidation` | Bulk prune without knowledge extraction — count, classify, delete |

`artifact-consolidation` remains available for repos that want to clean up without wiki investment. `/distill` supersedes it for the distill-then-delete workflow.
