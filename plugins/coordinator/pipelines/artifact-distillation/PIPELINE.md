# Artifact Distillation

> Referenced by `/distill`. This is a pipeline definition, not an invocable skill.

---

## Overview

Session workflows generate artifacts that accumulate indefinitely. The knowledge decays (specific steps become stale) but the decisions and reasoning remain valuable. This pipeline distills accumulated session debris into evergreen wiki documents (`docs/guides/` + `docs/decisions/`), then deletes the source material. The archive is the compost heap; the wiki is the garden.

---

## When to Use

- After major project milestones
- When artifact directories exceed ~50 files
- During periodic maintenance
- When starting a new project phase and you want to crystallize learnings from the last one

**Not for:** Quick cleanups without wiki investment (use `coordinator:artifact-consolidation`), single-document review, or active-session handoffs.

---

## Relationship to artifact-consolidation

`artifact-consolidation` = prune without extracting (count → classify → delete). Remains available for repos that just want to clean up.

`/distill` = extract knowledge into wiki, then delete source material. Supersedes artifact-consolidation for the distill-then-delete workflow. Use `artifact-consolidation` when there's no wiki to maintain; use `/distill` when you want the knowledge before discarding the source.

---

## Phase Pipeline — STRICT SEQUENCE

```
Phase 0 (Coordinator) → Phase 1 (Haiku ×N, parallel) → Phase 1.5 (Haiku ×N, QG)
  → [Clustering] → Phase 2 (Sonnet ×M, parallel) → Phase 3 (Opus, single)
  → Phase 4 (PM gate) → Phase 5 (Coordinator, apply + delete)
```

**Phases MUST run sequentially.** Each phase's output shapes the next phase's prompts. Do not begin the next phase until all agents in the current phase have completed and their scratch files verified.

---

## Phase 0: Scoping (Coordinator, ~5 min)

1. **Inventory artifact directories:** `archive/handoffs/`, `plans/`, `docs/completed-work/`, completed `tasks/*/` dirs, `docs/research/`, `~/docs/research/`
2. **Catalog artifact formats:** identify which directories contain frontmatter-bearing markdown, plain markdown, JSON/YAML, or mixed formats.
3. **Inventory existing wiki:** `docs/guides/`, `docs/decisions/` — needed for idempotent merging. Extract guide headings/topic lists for the reality check.
4. **Read distillation log** (`docs/guides/.distill-log.md`) if it exists — use as a hint for the reality check, but do NOT rely on it as the sole exclusion mechanism. The log can be stale or incomplete.
5. **Read `tasks/handoffs/`** for active context (read-only, never deleted)
6. **Reality check (Haiku scout):** Dispatch a single Haiku agent with the candidate file list + existing guide headings. The scout reads each candidate file and classifies it:
   - **NEW** — contains knowledge not yet captured in existing guides or decision records
   - **ALREADY_CAPTURED** — knowledge is already in the wiki (compare against guide headings/content)
   - **EPHEMERAL** — pure session tracking, status updates, no lasting value
   - **SKIP** — active reference, forward-looking content, or in-progress work

   **Special classification rules (override general logic):**
   - **Research outputs** (`docs/research/*.md`, `~/docs/research/*.md`, Pipeline A/B/C/D final outputs): always **PRESERVE** — never deleted, never modified in place. Copy verbatim to `docs/research/` if not already there. Pipeline C outputs (structured YAML/JSON, files containing `manifest_version:`) and all other pipeline research outputs fall under this same rule.
   - **NotebookLM outputs** (`tasks/notebooklm-*/`, any file with "notebooklm" in its path, `*-claims.json`, `*-summary.md` from research pipelines): always **PRESERVE** — never deleted, never modified in place.
   - **Archived handoffs** (`archive/handoffs/*.md`): always **NEW** — the `## What Was Accomplished`, `## Key Decisions Made`, and `## Blockers or Issues` sections contain architectural decisions and gotchas that must be extracted into guides and decision records.

   The scout returns a classified list with counts. This is the **ground truth** for scope, replacing the distill-log as the primary filter. The distill-log is a hint; the scout is the authority.

7. **Scope gate — choose pipeline tier based on the scout's NEW count:**
   - **0 NEW artifacts:** **Abort.** Report "nothing to distill" and stop. Optionally offer to delete EPHEMERAL files directly.
   - **<20 NEW artifacts:** **Lightweight mode.** Dispatch a single Sonnet agent that reads all NEW files and produces guide deltas + decision records + deletion manifest in one pass. No Haiku scanning, no clustering, no Opus assembly. Jump directly to Phase 4 (PM gate).
   - **20-50 NEW artifacts:** **Standard mode.** 2-3 Haiku batches, skip QG (Phase 1.5), coordinator does clustering inline, 2-3 Sonnet synthesizers, coordinator assembles (skip Opus Phase 3).
   - **50+ NEW artifacts:** **Full pipeline** as designed below.
8. **Generate run ID** (format: `YYYY-MM-DD-HHhMM`), create scratch dir at `tasks/scratch/artifact-distillation/{run-id}/`
9. **Sort artifacts chronologically** within each source directory (temporal ordering preserved through pipeline — critical for detecting superseded decisions)
10. **Group artifacts into 4-8 batches** of ~20-50 files each (by source dir + chronological window)
11. **Output:** batch table (with format hints), existing wiki inventory, scout classification, **selected pipeline tier**

**If `$ARGUMENTS` includes a path,** scope inventory to that path only.

**If `--dry-run`,** announce dry-run mode. The pipeline runs through Phase 3, then presents the summary and deletion manifest at the Phase 4 checkpoint without applying anything. Phases 4-5 are skipped.

---

## Phase 1: Artifact Scanning (Haiku, parallel)

**Model:** Haiku. **Dispatch:** All batches simultaneously.

One Haiku agent per batch. Each agent reads every artifact in its batch and extracts structured "knowledge nuggets."

**Nugget types:**

- `[DECISION]` — a choice that was made. Include optional `superseded_by:` field if a later artifact in the same batch reverses this decision.
- `[SUPERSEDED]` — a decision or pattern explicitly reversed in a later artifact. Tagged with the reversing artifact reference. These are NOT extracted as active knowledge — they exist so downstream agents can detect contradictions rather than silently presenting outdated guidance.
- `[KNOWLEDGE:{system}]` — architecture, patterns, conventions, gotchas. The `{system}` tag matches architecture atlas system names where possible.
- `[EPHEMERAL]` — task lists, agent logs, "next session should..." → no lasting value
- `[AMBIGUOUS]` — can't classify with confidence → surfaced for Sonnet judgment in Phase 2

**Format awareness:** Haiku receives format hints per batch from Phase 0. YAML frontmatter in artifacts is parsed as metadata (dates, status, branch info), not classified as prose knowledge.

"Haiku catalogs; it does NOT synthesize or judge. Completeness matters more than analysis."

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 1: Haiku Artifact Scanner Prompt** verbatim. Fill in:
- `[BATCH_NUMBER]` — batch number
- `[BATCH_DESCRIPTION]` — brief description of the batch (source dir + date window)
- `[BATCH_FILES]` — full list of file paths in this batch
- `[FORMAT_HINTS]` — format notes from Phase 0 (e.g., "frontmatter-bearing markdown", "plain markdown")
- `[SCRATCH_PATH]` — `tasks/scratch/artifact-distillation/{run-id}/batch-{N}-phase1-haiku.md`

Instruct each agent in its prompt to use Read, Write, and Glob. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) Dispatch with `run_in_background: true`.

**Scratch verification:** Before proceeding to Phase 1.5, verify all expected files exist. Re-dispatch the failed agent once on missing files. If it fails again, skip that batch and note the gap.

---

## Phase 1.5: Scout Quality Gate (Haiku, parallel)

**Model:** Haiku. **Dispatch:** One per batch, all simultaneously.

One Haiku agent per batch verifying Phase 1 output.

**Checks:**
- Nugget count > 0 per artifact
- Template compliance (required fields present for each nugget type)
- Spot-check 3 file path references per batch against actual filesystem

**Verdicts:**
- **PASS** — all files covered, templates compliant, paths verified
- **THIN** — coverage gaps (>20% of files missing entries) → re-dispatch Phase 1 for that batch
- **FAIL** — systematic template violations or >50% path misses → skip batch, note the gap

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 1.5: Haiku Quality Gate Prompt** verbatim. Fill in:
- `[BATCH_NUMBER]` — batch number
- `[BATCH_FILES]` — the original file list from Phase 0's batch table (ground truth for coverage check)
- `[PHASE1_SCRATCH_PATH]` — path to the Phase 1 scratch file for this batch
- `[SCRATCH_PATH]` — `tasks/scratch/artifact-distillation/{run-id}/batch-{N}-phase1.5-qg.md`

Instruct each agent in its prompt to use Read, Write, and Glob (Glob for path verification spot-checks). (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) Dispatch with `run_in_background: true`.

**Scratch verification:** Verify all expected QG files exist before proceeding to Clustering.

---

## Clustering Interstitial (Coordinator or Haiku)

After all Phase 1.5 verdicts are PASS (or batches are marked FAIL/SKIP), regroup nuggets from input-batch grouping to output-topic grouping.

**For ≤100 nuggets:** Coordinator reads all Phase 1 scratch files and builds the clustering table directly (mechanical, not wasteful at this scale).

**For >100 nuggets:** Dispatch a single Haiku clustering agent using the **Clustering: Haiku Clustering Prompt** from `agent-prompts.md`. The agent produces a mapping of `{system_tag → [nugget_ids_with_batch_references]}`. Coordinator validates the mapping before proceeding.

**Output:** topic dispatch table mapping each guide topic to its source nuggets across all batches. This table drives Phase 2 dispatch.

---

## Phase 2: Knowledge Synthesis (Sonnet, parallel)

**Model:** Sonnet. **Dispatch:** All topic agents simultaneously.

**Key pivot:** one Sonnet agent per target guide topic (not per input batch).

Each agent receives:
- All nuggets for its system (from all batches, via clustering table)
- Existing guide content (if guide exists) — for delta updates
- Guide format template

**Delta format for existing guides** — structured operations, not prose diffs:
- `ADD_SECTION(after: 'existing_heading', content: '...')` — insert new section
- `UPDATE_SECTION(heading: '...', content: '...')` — replace section content
- `REMOVE_SECTION(heading: '...')` — remove obsolete section

Unchanged sections are NOT included in the delta. This prevents guide drift where each distillation subtly rewords existing content.

For new guides: produce the full document in standard format (H1 title, optional TOC, architecture overview, reference tables, cross-references).

Decision records: any `[DECISION]` nugget (not `[SUPERSEDED]`) → draft in standard format with metadata block (Decision ID, Status, Authors, Date, Related, Implementation links).

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 2: Sonnet Knowledge Synthesis Prompt** verbatim. Fill in:
- `[SYSTEM_TAG]` — system name for this guide
- `[NUGGETS]` — all nuggets for this system from the clustering table
- `[EXISTING_GUIDE_CONTENT]` — current guide content, or "NEW GUIDE"
- `[SCRATCH_PATH]` — `tasks/scratch/artifact-distillation/{run-id}/topic-{name}-phase2-sonnet.md`

Instruct each agent in its prompt to use Read and Write. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) Dispatch with `run_in_background: true`.

**Ownership boundary:** Synthesizers own their scratch files. They write to `tasks/scratch/artifact-distillation/{run-id}/` only — never to `docs/guides/` or `docs/decisions/`. Production guides are coordinator-only territory (applied in Phase 5).

**Scratch verification:** Verify all expected topic files exist before proceeding to Phase 3.

**CRITICAL: Checkpoint scratch files before Phase 3.** `git add tasks/scratch/artifact-distillation/ && git commit -m "distill: checkpoint Phase 1-2 scratch"`. Phase 3 is the highest-risk step (largest context load, longest runtime). If it fails, the checkpoint allows re-running Phase 3 without re-doing Phases 1-2.

---

## Phase 3: Cross-Reference Assembly (Opus or decomposed Sonnet)

**Default:** Opus single agent. **If >200 nuggets or >5 topic clusters:** decompose into 2 parallel Sonnet sub-tasks: (a) deduplicate decision records + cross-reference check, (b) produce deletion manifest. The coordinator assembles the final output.

**Opus does NOT expand or apply delta operations.** Phase 2 scratch files contain delta operations for existing guides and full content for new guides — Phase 3 reads them as-is. Mechanical delta application happens in Phase 5 (coordinator). Phase 3's value is in intelligent work only: contradiction detection, deduplication, and the deletion manifest.

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 3: Opus Cross-Reference Assembly Prompt** verbatim. Fill in:
- `[N]` — number of topic-specific Sonnet agents
- Phase 2 scratch file paths
- Existing wiki state (guide files and decision records)
- `[SCRATCH_PATH]` — `tasks/scratch/artifact-distillation/{run-id}/phase3-opus-assembly.md`

Instruct the agent in its prompt to use Read, Write, and Glob. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

**Phase 3 produces:**
1. Cross-reference consistency report (contradictions flagged, with temporal resolution)
2. Deduplicated decision records
3. Updated `DIRECTORY_GUIDE.md` index
4. **Deletion manifest** — every source artifact with `DISTILLED → DELETE`, `EPHEMERAL → DELETE`, or `SKIP` with reason

**Scratch verification:** Verify the Phase 3 file exists before proceeding to Phase 4.

---

## Phase 4: PM Approval Gate (Coordinator)

Present to PM:
- Summary table: N guides created/updated, N decisions created, N artifacts to delete
- Full deletion manifest (from Phase 3)
- PM can remove items from the deletion list

**Wait for explicit approval. Do not proceed without it.**

**If `--dry-run`:** present the summary and stop here. Do not proceed to Phase 5.

---

## Phase 5: Apply and Clean (Coordinator)

0. **Pre-check:** If `git status` shows uncommitted changes outside wiki and artifact directories, warn PM and offer to commit those separately first — keeps the safety checkpoint scoped to distillation.
1. **Safety commit:** `git add -A && git commit -m "pre-distillation checkpoint"`
2. **Apply delta operations** from Phase 2 scratch files: for each existing guide, read the delta operations (ADD_SECTION / UPDATE_SECTION / REMOVE_SECTION) and apply them mechanically. For new guides, copy the full content from the Phase 2 scratch file. Apply cross-reference corrections flagged by Phase 3.
3. **Write wiki files** to `docs/guides/`, `docs/decisions/`, `docs/guides/DIRECTORY_GUIDE.md`
4. **Commit additions:** `"distill: add/update N guides, N decision records"`
5. **Delete approved artifacts:** `git rm` each file from the deletion manifest
6. **Commit deletions:** `"distill: remove N distilled artifacts"`
7. **Update distillation log:** append all processed artifacts **with individual file paths and dispositions** to `docs/guides/.distill-log.md` — this is the idempotency mechanism for subsequent runs. Format: `- [file_path] → [DISTILLED|EPHEMERAL|SKIP|PRESERVE] (run: [run-id])`. Per-file entries are required — directory-level summaries are insufficient for Phase 0 exclusion matching.
8. **Amend log update** into the deletion commit
9. **Clean scratch:** `rm -rf tasks/scratch/artifact-distillation/{run-id}/`

**Two separate commits** (additions vs deletions) so wiki content survives even if deletion needs reverting.

**If `--no-delete`:** skip steps 5-8, only apply wiki updates (steps 0-4).

---

## Cost Profile

| Scenario | Haiku | Sonnet | Opus | Wall-Clock |
|----------|-------|--------|------|------------|
| Small (<30 artifacts, 2-4 systems) | 4 (2 scan + 2 QG) | 2-4 | 1 | ~20 min |
| Medium (30-200, 4-8 systems) | 8-12 (4-6 + QG) | 4-8 | 1 | ~35 min |
| Large (200+, 6-12 systems) | 16 (8 + QG) + 1 clustering | 6-12 | 1 | ~50 min |

Plus PM review time at Phase 4 (variable). Interstitial overhead (coordinator reading scratch, clustering, dispatching) accounts for ~5-15 min depending on nugget volume.

---

## Failure Modes

| Failure | Prevention |
|---------|------------|
| Running phases in parallel | Each phase's output shapes the next. Sequential = cheaper AND better. |
| Writing custom dispatch prompts | Templates in `agent-prompts.md` are tested infrastructure. Copy verbatim, fill blanks. |
| Haiku synthesizing instead of cataloging | "Completeness matters more than analysis" instruction is in the Phase 1 template. Don't remove it. |
| Delta operation references non-existent heading | Phase 3 Opus flags these as errors rather than guessing — surface for coordinator review |
| Deleting active handoff references | Phase 0 reads `tasks/handoffs/` for active context — those files are read-only, never batched |
| Guide drift across runs | Delta format for existing guides — only changed sections included, not full rewrites. Coordinator applies deltas mechanically in Phase 5; Opus does not expand them. |
| Artifacts distilled twice | Distillation log (`docs/guides/.distill-log.md`) excludes already-processed artifacts at Phase 0 |
| PM skips approval and deletion runs | "Wait for explicit approval" is unconditional — no timeout, no auto-proceed |
| Scratch file missing after agent completes | Verify with `ls`; re-dispatch once; skip batch on second failure — don't stall the pipeline |
