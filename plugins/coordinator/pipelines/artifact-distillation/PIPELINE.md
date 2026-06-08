# Artifact Distillation

> Referenced by `/distill`. This is a pipeline definition, not an invocable skill.

---

## Overview

Session workflows generate artifacts that accumulate indefinitely. The knowledge decays (specific steps become stale) but the decisions and reasoning remain valuable. This pipeline distills accumulated session debris into evergreen wiki documents (`docs/wiki/` + `docs/decisions/`), then deletes the source material. The archive is the compost heap; the wiki is the garden.

---

## When to Use

- After major project milestones
- When artifact directories exceed ~50 files
- During periodic maintenance
- When starting a new project phase and you want to crystallize learnings from the last one

**Not for:** Quick cleanups without wiki investment (handled by `/update-docs` Phase 8b — `pipelines/update-docs/artifact-pruning.md`), single-document review, or active-session handoffs.

---

## Relationship to /update-docs Phase 8b (artifact-pruning)

`/update-docs` Phase 8b = prune without extracting (count → classify → delete). Runs unconditionally on every `/update-docs` invocation under conservative thresholds. Replaces the former `coordinator:artifact-consolidation` skill (absorbed 2026-05-06). See `pipelines/update-docs/artifact-pruning.md`.

`/distill` = extract knowledge into wiki, then delete source material. Runs upstream of Phase 8b conceptually: knowledge extraction first, raw bulk pruning second. Use `/distill` when there's wiki-worthy knowledge in the artifacts about to age out; rely on `/update-docs` Phase 8b for routine bulk cleanup.

---

## Phase Pipeline — STRICT SEQUENCE

```
Phase 0 (Coordinator) → Phase 1 (Haiku ×N, parallel) → Phase 1.5 (Haiku ×N, QG)
  → [Clustering] → Phase 2 (Sonnet ×M, parallel) → Phase 2.5 (Sonnet ×K, judgment-mining)
  → Phase 2.7-QG (Haiku ×M, parallel by cluster — coverage gate)
  → Phase 3a (Sonnet ×C, parallel by cluster) → [cross-cluster-check] → [Esc: Opus + fidelity-check (Sonnet), if needed]
  → Phase 3b (Sonnet, single) → Phase 3c (Coordinator, mechanical) → Phase 3d (Sonnet, single)
  → Phase 4 (PM gate) → Phase 5 (Coordinator, apply + delete)
```

**Phases MUST run sequentially.** Each phase's output shapes the next phase's prompts. Do not begin the next phase until all agents in the current phase have completed and their scratch files verified.

---

## Phase 0: Scoping (Coordinator, ~5 min)

1. **Inventory artifact directories:** `archive/handoffs/`, `plans/`, `docs/completed-work/`, completed `tasks/*/` dirs, `docs/research/`, `~/docs/research/`, `docs/superpowers/specs/`, `tasks/*/spec.md`, `tasks/*/design.md`, `cross-repo/archive/` (closed `status: actioned` memos — see `commands/distill.md` § Cross-repo archive distillation)
2. **Catalog artifact formats:** identify which directories contain frontmatter-bearing markdown, plain markdown, JSON/YAML, or mixed formats.
3. **Inventory existing wiki:** `docs/wiki/`, `docs/decisions/` — needed for idempotent merging. Extract guide headings/topic lists for the reality check. Also note any gaps: systems that appear in specs or research but have no corresponding guide yet (these are new-guide candidates). **Index on filename, not just H1 title.** Capture the full `docs/wiki/*.md` and `docs/decisions/*.md` filename list alongside the H1/topic headings — near-duplicate FILENAME collisions (e.g. `coordinator-installer-shape.md` already on disk while a synthesizer later proposes `coordinator-installer.md`) are invisible to a heading-keyed index. Pass the filename list to the reality-check scout so ALREADY_CAPTURED classification can match on filename stem similarity, not only on title. (sibling: `CLAUDE.md` § Pre-Dispatch Verification — "grep existing surface before scaffolding agent-facing files; collisions hide under longer existing names".)

   **Filename-stem overlap check (Phase 0 gate, added 2026-05-28):** Before Phase 3c proposes any new `DIRECTORY_GUIDE.md` entry (and before any synthesizer emits a new guide filename), compare the proposed guide name stem against all existing `docs/wiki/` filenames after normalization (strip `-shape`, `-design`, `-v2`, date prefixes, pluralization; prefix/substring rule fires only when shorter stem ≥8 chars). Near-duplicate collisions are surfaced at the Phase 4 PM gate — NOT auto-created and NOT auto-skipped. The coordinator decides at Phase 4, not the synthesizer at Phase 2. Rationale: synthesizers propose guide names from their topic cluster without seeing the full wiki inventory; the Phase 0 stem check is the mechanical gate that catches near-duplicates before they become disk collisions. (DR-146, 2026-05-27.)
4. **Read distillation log** (`docs/wiki/.distill-log.md`) if it exists — use as a hint for the reality check, but do NOT rely on it as the sole exclusion mechanism. The log can be stale or incomplete.
5. **Read `state/handoffs/`** for active context (read-only, never deleted)
6. **Reality check (Haiku scout):** Dispatch a single Haiku agent with the candidate file list + existing guide headings. The scout reads each candidate file and classifies it:
   - **NEW** — contains knowledge not yet captured in existing guides or decision records
   - **ALREADY_CAPTURED** — knowledge is already in the wiki (compare against guide headings/content)
   - **EPHEMERAL** — pure session tracking, status updates, no lasting value
   - **SKIP** — active reference, forward-looking content, or in-progress work

   **Special classification rules (override general logic):**
   - **Research outputs** (`docs/research/*.md`, `~/docs/research/*.md`, Pipeline A/B/C/D final outputs): always **PROMOTE** — source files are never deleted, never modified in place; but key findings (decisions, architecture insights, gotchas) must be extracted and merged into the relevant guide sections. If no matching guide exists for the research topic, create one. Copy verbatim to `docs/research/` if not already there. Pipeline C outputs (structured YAML/JSON, files containing `manifest_version:`) fall under this same rule.
   - **NotebookLM outputs** (`tasks/notebooklm-*/`, any file with "notebooklm" in its path, `*-claims.json`, `*-summary.md` from research pipelines): always **PRESERVE** — never deleted, never modified in place. Key claims may be extracted into guides at synthesizer discretion.
   - **Archived handoffs** (`archive/handoffs/*.md`): always **NEW** — the `## What Was Accomplished`, `## Key Decisions Made`, and `## Blockers or Issues` sections contain architectural decisions and gotchas that must be extracted into guides and decision records.
   - **Design specs** (`docs/superpowers/specs/*.md`, `tasks/*/spec.md`, `tasks/*/design.md`): classify as **NEW** if the spec was executed (check for corresponding implementation in git log or code) — extract all design decisions as decision records in the relevant guide, then mark the spec as archivable. Classify as **SKIP** if the spec is still in-progress or unapproved.

   The scout returns a classified list with counts. This is the **ground truth** for scope, replacing the distill-log as the primary filter. The distill-log is a hint; the scout is the authority.

7. **Scope gate — choose pipeline tier based on the scout's NEW count:**
   - **0 NEW artifacts:** **Abort.** Report "nothing to distill" and stop. Optionally offer to delete EPHEMERAL files directly.
   - **<20 NEW artifacts:** **Lightweight mode.** Dispatch a single Sonnet agent that reads all NEW files and produces guide deltas + decision records + deletion manifest in one pass. No Haiku scanning, no clustering, no Opus assembly. Jump directly to Phase 4 (PM gate).
   - **20-50 NEW artifacts:** **Standard mode.** 2-3 Haiku batches, skip QG (Phase 1.5), coordinator does clustering inline, 2-3 Sonnet synthesizers, coordinator assembles (skip Phase 3a — run 3b/3c/3d only).
   - **50+ NEW artifacts:** **Full pipeline** as designed below.
8. **Generate run ID** (format: `YYYY-MM-DD-HHhMM`), create scratch dir at `state/scratch/artifact-distillation/{run-id}/`
9. **Sort artifacts chronologically** within each source directory (temporal ordering preserved through pipeline — critical for detecting superseded decisions)
10. **Group artifacts into 4-8 batches** of ~20-50 files each (by source dir + chronological window)
11. **Output:** batch table (with format hints), existing wiki inventory, scout classification, **selected pipeline tier**

**If `$ARGUMENTS` includes a path,** scope inventory to that path only.

**If `--dry-run`,** announce dry-run mode. The pipeline runs through Phase 3d, then presents the summary and deletion manifest at the Phase 4 checkpoint without applying anything. Phases 4-5 are skipped.

---

## Phase 1: Artifact Scanning (Haiku, parallel)

**Model:** Haiku. **Dispatch:** All batches simultaneously.

One Haiku agent per batch. Each agent reads every artifact in its batch and extracts structured "knowledge nuggets."

**Input types (since 2026-05-08):** `docs/plans/*.md` (canonical specs), scaffolding stubs in `tasks/<feature>/stubs/`, and **`archive/handoffs/*.md`** (post-`/pickup` handoffs). Handoffs are enumerated via `bin/query-records --type handoff-archived --format paths` (per `commands/distill.md` § Handoff distillation), not raw `find`. Haiku scans handoffs for `[DECISION]` / `[KNOWLEDGE:{system}]` nuggets the same way it scans specs — `## Key Decisions Made` is the highest-yield section per existing handoff template.

**Nugget types:**

- `[DECISION]` — a choice that was made. Include optional `superseded_by:` field if a later artifact in the same batch reverses this decision.
- `[SUPERSEDED]` — a decision or pattern explicitly reversed in a later artifact. Tagged with the reversing artifact reference. These are NOT extracted as active knowledge — they exist so downstream agents can detect contradictions rather than silently presenting outdated guidance.
- `[KNOWLEDGE:{system}]` — architecture, patterns, conventions, gotchas. The `{system}` tag matches architecture atlas system names where possible.
- `[EPHEMERAL]` — task lists, agent logs, "next session should..." → no lasting value
- `[AMBIGUOUS]` — can't classify with confidence → surfaced for Sonnet judgment in Phase 2

**Format awareness:** Haiku receives format hints per batch from Phase 0. YAML frontmatter in artifacts is parsed as metadata (dates, status, branch info), not classified as prose knowledge.

"Haiku catalogs; it does NOT synthesize or judge. Completeness matters more than analysis."

**DISPATCH:** Open `agent-prompts/phase-1.md`. Copy the **Phase 1: Haiku Artifact Scanner Prompt** verbatim. Fill in:
- `[BATCH_NUMBER]` — batch number
- `[BATCH_DESCRIPTION]` — brief description of the batch (source dir + date window)
- `[BATCH_FILES]` — full list of file paths in this batch
- `[FORMAT_HINTS]` — format notes from Phase 0 (e.g., "frontmatter-bearing markdown", "plain markdown")
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/batch-{N}-phase1-haiku.md`

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

**DISPATCH:** Open `agent-prompts/phase-1-5.md`. Copy the **Phase 1.5: Haiku Quality Gate Prompt** verbatim. Fill in:
- `[BATCH_NUMBER]` — batch number
- `[BATCH_FILES]` — the original file list from Phase 0's batch table (ground truth for coverage check)
- `[PHASE1_SCRATCH_PATH]` — path to the Phase 1 scratch file for this batch
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/batch-{N}-phase1.5-qg.md`

Instruct each agent in its prompt to use Read, Write, and Glob (Glob for path verification spot-checks). (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) Dispatch with `run_in_background: true`.

**Scratch verification:** Verify all expected QG files exist before proceeding to Clustering.

---

## Clustering Interstitial (Coordinator or Haiku)

After all Phase 1.5 verdicts are PASS (or batches are marked FAIL/SKIP), regroup nuggets from input-batch grouping to output-topic grouping.

**For ≤100 nuggets:** Coordinator reads all Phase 1 scratch files and builds the clustering table directly (mechanical, not wasteful at this scale).

**For >100 nuggets:** Dispatch a single Haiku clustering agent using the **Clustering: Haiku Clustering Prompt** from `agent-prompts/clustering.md`. The agent produces a mapping of `{system_tag → [nugget_ids_with_batch_references]}`. Coordinator validates the mapping before proceeding.

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

**New-guide creation is proactive, not conservative.** If the clustering table reveals a system tag with ≥3 nuggets and no existing guide, the Sonnet agent **must** create a new guide — not fold the nuggets into an existing guide as an appendix. Research outputs and executed specs are strong signals that a new guide is warranted, even if the nugget count is lower. When in doubt, create the guide. A stub guide that grows over sessions is better than knowledge buried in a catch-all guide.

For new guides: produce the full document in standard format (H1 title, optional TOC, architecture overview, reference tables, cross-references). Also note the new guide in the batch scratch file so Phase 5 can update `docs/wiki/DIRECTORY_GUIDE.md` and `docs/README.md`.

Decision records: any `[DECISION]` nugget (not `[SUPERSEDED]`) → draft in standard format with metadata block (Decision ID, Status, Authors, Date, Related, Implementation links).

**DISPATCH:** Open `agent-prompts/phase-2.md`. Copy the **Phase 2: Sonnet Knowledge Synthesis Prompt** verbatim. Fill in:
- `[SYSTEM_TAG]` — system name for this guide
- `[NUGGETS]` — all nuggets for this system from the clustering table
- `[EXISTING_GUIDE_CONTENT]` — current guide content, or "NEW GUIDE"
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/topic-{name}-phase2-sonnet.md`

Instruct each agent in its prompt to use Read and Write. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) Dispatch with `run_in_background: true`.

**Phase 2 scratch output schema:** Each Phase 2 scratch file opens with a `dispositions:` YAML frontmatter block listing every assigned nugget ID with its operation and target. Full schema: `agent-prompts/phase-2.md` § Disposition Manifest.

**Ownership boundary:** Synthesizers own their scratch files. They write to `state/scratch/artifact-distillation/{run-id}/` only — never to `docs/wiki/` or `docs/decisions/`. Production guides are coordinator-only territory (applied in Phase 5).

**Scratch verification:** Verify all expected topic files exist before proceeding to Phase 3a.

**CRITICAL: Checkpoint scratch files before Phase 3a.** `git add state/scratch/artifact-distillation/ && git commit -m "distill: checkpoint Phase 1-2 scratch"`. Phase 3a/3b/3d are the highest-risk steps (largest context load, longest runtime). If any fail, the checkpoint allows re-running without re-doing Phases 1-2.

---

## Phase 2.5: Judgment Mining (Sonnet, parallel by topic-cluster)

Mine the run's reviewer sidecars for cross-spec convergence patterns — findings that recur across ≥N distinct plans (default `N=3`, override via `/distill --min-convergence=N`). Convergent findings emit `judgment-proposals` for Phase 3b review and wiki promotion into `docs/wiki/codebase-judgment/`.

**Model:** Sonnet, one agent per topic-cluster, all simultaneous. Read-only orchestrator boundary (no nested sub-agents). Strict-sequencing gate: Phase 2 fully complete before Phase 2.5 begins; Phase 2.5 complete before Phase 3a/5.

**Full procedure** (corpus collection, finding eligibility, shape-matching rules, update path, convergence threshold, proposal format, promoted-entry frontmatter schema, dispatch instructions): see `agent-prompts/phase-2-5-judgment-mining.md`.

---

## Phase 2.7-QG: Coverage Gate (Haiku, parallel by cluster)

<!-- spec-backlink: docs/plans/2026-05-28-distill-structured-manifests.md § Chunk 2 -->

**Model:** Haiku. **Dispatch:** One agent per Phase 2 cluster, all simultaneously. **Runs after:** Phase 2 fully complete.

Phase 2.7-QG is a mechanical coverage gate. For each Phase 2 cluster output, it reads the `dispositions:` frontmatter and performs a set-diff against the cluster's assigned nugget IDs from the Clustering output. No semantic interpretation — set membership only.

**Verdict:**
- **PASS** — set-diff is empty; all assigned nugget IDs appear in `dispositions:`.
- **FAIL** — one or more assigned nugget IDs absent from `dispositions:`; the missing IDs are named.

**FAIL recovery:** Coordinator dispatches a Phase 2 re-run for the failing cluster only. **Retry cap: 2 re-runs per cluster.** On second consecutive FAIL, halt and surface to PM with the failing cluster's missing IDs and the Phase 2 outputs from both attempts.

**DISPATCH:** Open `agent-prompts/phase-2-7-qg.md`. Copy the **Phase 2.7-QG Prompt** verbatim. Fill in:
- `[PHASE2_SCRATCH_PATH]` — path to the Phase 2 scratch file for this cluster
- `[ASSIGNED_NUGGET_IDS]` — nugget IDs assigned to this cluster from the Clustering output
- `[VERDICT_PATH]` — `state/scratch/artifact-distillation/{run-id}/phase2-7-qg-{cluster-tag}.yaml`

Full prompt and verdict schema: `agent-prompts/phase-2-7-qg.md`.

**Scratch verification:** Verify all expected verdict files exist before proceeding to Phase 3a. Any missing verdict file = treat that cluster as FAIL (re-dispatch Phase 2.7-QG once).

---

## Phase 3a: Contradiction Detection (Sonnet, parallel by cluster)

<!-- spec-backlink: docs/plans/2026-05-14-distill-phase3-em-driven-dispatch.md § AC#2, AC#6a, AC#6e -->

**Model:** Sonnet. **Dispatch:** One agent per topic cluster, all simultaneously.

**Sharding rule (Option B — clustered pairwise):** Reuses Phase 2.5's shape-match clustering apparatus. Topics are already grouped into 3-5 clusters by claim-topic affinity. Each 3a agent compares all topics *within its cluster* — detecting intra-cluster contradictions. The coordinator handles cross-cluster contradictions separately (see below).

**Single-topic cluster exemption:** If a cluster contains only one topic, skip dispatching a 3a agent for it — no within-cluster pairwise comparison is possible. Cross-cluster check (below) still applies.

**DISPATCH:** Open `agent-prompts/phase-3a.md`. Copy the **Phase 3a: Sonnet Contradiction Detection Prompt** verbatim. Fill in:
- `[CLUSTER_TAG]` — the cluster label from Phase 2.5 clustering
- `[TOPIC_PAIR_LIST]` — all topic pairs in this cluster
- `[LIST_OF_PHASE2_SCRATCH_PATHS_FOR_CLUSTER]` — Phase 2 scratch files for the topics in this cluster
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/phase3a-contradictions-{cluster-tag}.md`

Instruct each agent in its prompt to use Read and Write. Dispatch with `run_in_background: true`.

**Scratch verification:** Before proceeding, verify all expected `phase3a-contradictions-{cluster-tag}.md` files exist. Re-dispatch the failed agent once on missing files. If it fails again, skip that cluster and note the gap.

### Coordinator cross-cluster check (mechanical, post-3a)

After all 3a agents complete, the coordinator runs a mechanical enumeration pass across ALL 3a scratch files:

1. Collect every decision-record ID (DR-NNN) and topic-tag from every 3a scratch file.
2. Flag any DR-ID or topic-tag that appears in ≥2 clusters with differing claims as a **cross-cluster contradiction candidate**.
3. Feed these candidates into the Opus escalation path (same path as intra-cluster `unresolvable_contradictions`).

This mechanical step closes the cross-cluster blind spot that per-cluster agents cannot see. No subagent dispatch — the coordinator reads the 3a scratch files directly.

### Opus escalation (conditional, auto-dispatch)

After the cross-cluster check, the coordinator reads the `unresolvable_contradictions` field from every 3a scratch frontmatter AND the cross-cluster candidates:

- **If total unresolvable count = 0 and no cross-cluster candidates:** proceed directly to Phase 3b.
- **If any unresolvable contradictions or cross-cluster candidates exist:** auto-dispatch Opus with the **Phase 3-Esc: Opus Contradiction Resolution Prompt** from `agent-prompts/phase-3-esc.md`. After Opus writes its output, dispatch the **Sonnet fidelity-check agent** (also in `agent-prompts/phase-3-esc.md`) to verify all source nugget IDs are cited. A fidelity `FAIL` halts downstream processing with the dropped IDs named.

**Opus escalation dispatch — fill in:**
- `[LIST_OF_3A_SCRATCH_FILES_WITH_UNRESOLVABLE_CONTRADICTIONS]` — only the 3a files with `unresolvable_contradictions > 0`, plus any cross-cluster candidates
- `[LIST_OF_PHASE2_SCRATCHES_FOR_FLAGGED_TOPICS]` — ONLY the Phase 2 scratch files for the topics cited in the flagged `contradiction_refs` (bounded input — not the full Phase 2 set)
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/phase3-esc-resolution.md`

Full prompt (Opus resolution + Sonnet fidelity-check): `agent-prompts/phase-3-esc.md`.

**No PM gate on the escalation itself.** Opus writes its resolution to `phase3-esc-resolution.md`. Phase 4 PM gate still applies to the assembled output. If Opus fails or times out, surface to Phase 4 PM gate with an escalation-failure note — PM decides whether to accept output without contradiction resolution or retry.

---

## Phase 3b: Decision-Record Dedup (Sonnet, single)

<!-- spec-backlink: docs/plans/2026-05-14-distill-phase3-em-driven-dispatch.md § AC#3, AC#6d -->

**Model:** Sonnet. **Dispatch:** Single agent. **Runs after:** Phase 3a complete and cross-cluster check done (and Opus escalation, if triggered).

**DISPATCH:** Open `agent-prompts/phase-3b.md`. Copy the **Phase 3b: Sonnet Decision-Record Dedup Prompt** verbatim. Fill in:
- `[LIST_OF_PHASE2_SCRATCH_PATHS]` — all Phase 2 scratch file paths
- `[JUDGMENT_PROPOSALS_PATH]` — `state/scratch/artifact-distillation/{run-id}/judgment-proposals.md`
- `[PHASE3_ESC_PATH]` — `state/scratch/artifact-distillation/{run-id}/phase3-esc-resolution.md` (3b checks existence before reading)
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/phase3b-dedup.md`

Instruct the agent in its prompt to use Read and Write.

**Phase 3b scratch output schema:** The Phase 3b scratch file (`phase3b-dedup.md`) includes a `dr_dedup:` YAML manifest listing canonical DR IDs and their duplicate mappings. Full schema: `agent-prompts/phase-3b.md`.

**CRITICAL FAILURE MODE:** An empty DR set (zero decision records found) is always a pipeline error — it means Phase 2 did not run correctly or produced no judgment proposals. The 3b agent writes a `PHASE_3B_FAILURE` report in this case; the coordinator halts and surfaces the error rather than proceeding to Phase 3c.

**Scratch verification:** Verify `phase3b-dedup.md` exists before proceeding to Phase 3c.

---

## Phase 3c: DIRECTORY_GUIDE.md Assembly (Coordinator, mechanical)

<!-- spec-backlink: docs/plans/2026-05-14-distill-phase3-em-driven-dispatch.md § AC#4 -->

**Model:** Coordinator (no subagent). **Runs after:** Phase 3b complete.

The coordinator reads Phase 2 scratch frontmatter + Phase 0 wiki inventory and writes the `DIRECTORY_GUIDE.md` index table directly. This is index construction, not judgment — no subagent dispatch needed.

**Ordering rule:**
- Alphabetical-by-guide-filename within each section.
- Sections appear in the order already present in `docs/wiki/DIRECTORY_GUIDE.md`.
- New sections (if any) append at the end.
- No reordering of existing rows beyond what new-guide insertion requires.

**Inputs the coordinator reads:**
- Phase 2 scratch files — frontmatter lists any new guide names produced
- Phase 3b dedup output — canonical DR IDs for the DIRECTORY_GUIDE.md table
- Existing `docs/wiki/DIRECTORY_GUIDE.md` — current table rows preserved, new rows inserted alphabetically
- Existing `docs/wiki/*.md` and `docs/decisions/*.md` filenames — the canonical on-disk name set for the new-guide collision check below

**Fuzzy-name overlap check on NEW-guide proposals.** For every new guide name in the Phase 2 frontmatter, compare its filename stem against every existing `docs/wiki/` / `docs/decisions/` filename stem. Flag a **near-duplicate collision** when stems match after normalizing (strip `-shape`, `-design`, `-v2`, date prefixes, and pluralization; case-insensitive; or one stem is a prefix/substring of the other with ≤4 trailing chars difference — **but apply the prefix/substring rule only when the shorter stem is ≥8 characters**, so short distinct stems like `auth` vs `author`/`oauth` do not trip a false collision, while `coordinator-installer` vs `coordinator-installer-shape` still does). Example: proposed `coordinator-installer.md` collides with existing `coordinator-installer-shape.md`. For each flagged collision, do NOT silently create the new guide — surface it in the Phase 3c preview under a `## New-guide collisions (PM decision)` heading with both names and a one-line recommendation (merge into existing guide vs. confirm genuinely distinct). The PM resolves at the **existing Phase 4 gate — this does not add a new halt or block auto-proceed; it adds a decision item to the gate that already waits for explicit approval.** This is the duplicate-guide gate — detect-then-surface, never detect-then-silently-create (coordinator/`CLAUDE.md` § Implementation Standards — "detect-then-silently-pick is a footgun").

**Output manifest:** The coordinator writes a `directory_entries:` YAML manifest alongside the preview, at `state/scratch/artifact-distillation/{run-id}/phase3c-manifest.yaml`. Schema:

```yaml
schema_version: 1
directory_entries:
  - topic: <text>
    wiki_path: <path>
    summary: <text>
    status: <text>
```

`status` values: `new` (guide created this run), `updated` (existing guide with new sections), `existing` (unchanged entry carried forward). The manifest is the machine-readable source-of-truth for Phase 5 Apply-Agent B's bookkeeping slice. The prose preview at `phase3c-directory-guide-preview.md` is generated FROM the manifest for PM review at Phase 4 — the manifest is authoritative; the preview is the human-readable derived view.

**Output:** Updated `DIRECTORY_GUIDE.md` preview written to `state/scratch/artifact-distillation/{run-id}/phase3c-directory-guide-preview.md`. This is coordinator-written — presented at Phase 4 PM gate for review before any production write.

---

## Phase 3d: Deletion Manifest (Sonnet, single)

<!-- spec-backlink: docs/plans/2026-05-14-distill-phase3-em-driven-dispatch.md § AC#5, AC#6d -->

**Model:** Sonnet. **Dispatch:** Single agent. **Runs after:** Phase 3b complete. 3d does not consume 3c output, so 3d may overlap with 3c — but both depend on 3b's deduped DR set and run after 3b.

**DISPATCH:** Open `agent-prompts/phase-3d.md`. Copy the **Phase 3d: Sonnet Deletion Manifest Prompt** verbatim. Fill in:
- `[LIST_OF_PHASE1_SCRATCH_PATHS]` — all Phase 1 (Haiku scanner) scratch file paths
- `[LIST_OF_PHASE1_5_SCRATCH_PATHS]` — all Phase 1.5 (QG verdict) scratch file paths
- `[LIST_OF_PHASE2_SCRATCH_PATHS]` — all Phase 2 scratch file paths
- `[PHASE3_ESC_PATH]` — `state/scratch/artifact-distillation/{run-id}/phase3-esc-resolution.md` (3d checks existence before reading)
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/phase3d-deletion-manifest.md`

Instruct the agent in its prompt to use Read and Write.

**Phase 3d scratch output schema:** The Phase 3d scratch file (`phase3d-deletion-manifest.md`) includes a `deletions:` YAML block as the machine-readable source-of-truth. Any prose table is a derived PM-readable view. Full schema: `agent-prompts/phase-3d.md`.

**Phase 3d produces:**
- **Deletion manifest** — every source artifact with `DISTILLED → DELETE`, `EPHEMERAL → DELETE`, `SKIP`, or `PRESERVE` with reason (YAML `deletions:` block; prose table derived view)

**Scratch verification:** Verify `phase3d-deletion-manifest.md` exists before proceeding to Phase 4.

---

**Phase 3 produces (combined across 3a–3d):**
1. Cross-reference consistency report — contradictions flagged and resolved (3a + optional Opus)
2. Deduplicated decision records (3b)
3. `DIRECTORY_GUIDE.md` preview (3c)
4. **Deletion manifest** — every source artifact with `DISTILLED → DELETE`, `EPHEMERAL → DELETE`, `SKIP`, or `PRESERVE` with reason (3d)

**Checkpoint discipline preserved:** The `git checkpoint` before Phase 3a (from the end of Phase 2) applies to 3a/3b/3c/3d re-runnability — each 3a agent writes to a named scratch path, so re-running a completed shard is safe (idempotent).

---

## Phase 4: PM Approval Gate (Coordinator)

Present to PM:
- Summary table: N guides created/updated, N decisions created, N artifacts to delete
- Full deletion manifest (from Phase 3d)
- `DIRECTORY_GUIDE.md` preview (from Phase 3c)
- PM can remove items from the deletion list

**Wait for explicit approval. Do not proceed without it.**

**If `--dry-run`:** present the summary and stop here. Do not proceed to Phase 5.

---

## Phase 5: Apply and Clean (Coordinator-orchestrated, Sonnet-applied)

0. **Pre-check:** If `git status` shows uncommitted changes outside wiki and artifact directories, warn PM and offer to commit those separately first — keeps the safety checkpoint scoped to distillation.
1. **Safety commit:** `CLAUDE_INVOKING_COMMAND=distillation ~/.claude/plugins/coordinator/bin/coordinator-safe-commit --blanket "pre-distillation checkpoint"`

2. **Split apply work across N Sonnet apply-agents, sized by volume (parallel where possible).**

   Single-agent application has timed out at ~50 min / ~170 tool-uses on large runs (e.g., the 2026-04-26 run). The coordinator MUST decompose the apply work into independent slices and dispatch a Sonnet apply-agent per slice. The coordinator orchestrates and verifies; it does not type the edits itself.

   Each Apply-Agent receives the relevant slice of the union of Phase 2 `dispositions:` manifests + Phase 3b/3d manifests as its **input contract**. The done-condition for each agent is a manifest-driven file-path set-diff (see step 3).

   **Slicing is volume-based, not function-based. The function split below (topic-deltas / bookkeeping / leftovers) is the role taxonomy, NOT the agent count.** The topic-delta role (A) scales with run size and MUST shard; the bookkeeping role (B) does not. Wiki files are file-disjoint, so topic deltas are trivially fan-outable — there is no reason to serialize them behind one process. Sizing the slate:

   - **Count the topic-guide targets** = (existing guides with a Phase 2 scratch file) + (new guides). This is the A-role volume.
   - **Small run (A-volume ≤ 4 guides):** combine into 1-2 agents total — one Apply-Agent A (all topic deltas + leftover guides/decision records) plus Apply-Agent B (bookkeeping). The function split collapses cleanly at this size.
   - **Large run (A-volume ≥ 5 guides):** **shard the A-role across ⌈A-volume / 3⌉ apply-agents**, each owning a disjoint group of ~2-3 guides (same per-executor scope discipline as Phase 1 batching — ~5-10 min per agent, 15 min hard ceiling). Dispatch the A-shards in parallel; Apply-Agent B (bookkeeping) runs alongside them. Decision records and any leftover low-volume guides fold into the smallest A-shard or a dedicated final shard — they do not get their own serialized "Agent C".

   > **Anti-pattern — the monolithic Apply-Agent A.** On 2026-05-28-pass1 (14 guides, ~67 deltas, 3 new guides) the function-based template put ALL topic deltas in one Apply-Agent A while B and C each had a ~15-min job; A ran 20+ min in one process and the PM flagged it. Function-based slicing is fine for small runs and actively harmful for large ones. Slice by volume.

   Roles:

   - **Apply-Agent A (one per guide-group on large runs) — Topic-guide deltas:** For each existing guide in the assigned group with a Phase 2 scratch file, read the delta operations (ADD_SECTION / UPDATE_SECTION / REMOVE_SECTION) and apply them mechanically. For new guides in the group, write the full content from the Phase 2 scratch file. Output: list of guide files touched. Done-condition: every target file path in this agent's assigned `dispositions:` entries appears in `git diff --stat`.
   - **Apply-Agent B — Gotchas distribution + bookkeeping (single agent, does not shard):** Apply cross-cutting nuggets (gotchas, lessons, cross-references) flagged by Phase 3a/3b, then update `docs/wiki/DIRECTORY_GUIDE.md` (using Phase 3c preview as source) and `docs/README.md` (add new guides to the Wikis and Guides table; add promoted research to the Research section; mark archived specs; bump footer timestamp). Output: list of bookkeeping files touched. Done-condition: every target file path in B's assigned manifest entries appears in `git diff --stat`. **Sequencing:** B's DIRECTORY_GUIDE/README bookkeeping reads the set of new/updated guides — it may run concurrently with the A-shards (it reads the manifest, not the applied files), but if any A-shard is re-dispatched in step 3, re-confirm B captured every new guide.

   Apply-agents must use Read, Write, Edit only — no further dispatch. Every A-shard prompt names the other shards' guide groups as out-of-scope (file-disjoint, no overlap).

3. **Verify apply-agent output via manifest-driven file-path set-diff.** Apply-agents under-count their own work in chat (observed on 2026-04-26). After all apply-agents return, run `git diff --stat docs/wiki/ docs/decisions/ docs/README.md` and compare the **set of FILE PATHS** in each agent's assigned manifest against the **set of FILE PATHS** in `git diff --stat`. Multiple operations on the same file collapse to one entry on both sides of the comparison. Non-empty set-diff (manifest paths not in diff) → re-dispatch that agent with the unfinished operation list. Section-level correctness of applied edits remains the Apply-Agent's responsibility and is not verified by this gate.

4. **Commit additions:** `"distill: add/update N guides, N decision records"`

5. **Delete approved artifacts — `.md`-only filter is MANDATORY.**

   `git rm -r tasks/<feature-dir>/` is **forbidden**. Recursive directory removal sweeps up co-located non-markdown research corpora (e.g., the 2026-04-26 run swept 525 non-md files from a `.next/`/asar corpus shared with a distill target) and violates the "research provenance is always retained" rule.

   Required procedure for each deletion-manifest entry:
   - Build the deletion list as **`*.md` only** — no recursive directory globs.
   - Per directory entry: `git ls-files '<dir>/*.md' '<dir>/**/*.md'` then `git rm` only those.
   - **YAML-manifest consumption (mandatory).** The Phase 3d deletion manifest emits a `deletions:` YAML block (`agent-prompts/phase-3d.md` schema). Extract artifact paths from the `artifact_path:` field of each entry — do NOT use `awk -F'|'` column-extraction on prose Markdown tables. YAML consumption avoids format-drift parsing failures. Entries with `disposition: DELETE` are eligible; `SKIP` and `PRESERVE` entries are excluded. See `snippets/deletion-list-hygiene.md` for hygiene guards.
   - **Pre-commit audit gate:** `git status --porcelain | awk '$1=="D"' | grep -v '\.md$'` MUST return empty. If it returns ANY paths, abort the deletion commit, restore the unintended deletions (`git restore --staged --worktree <path>`), and report to PM. Non-`.md` deletions are never silently accepted, even if the deletion manifest names them.
   - Research outputs (`docs/research/`, `~/docs/research/`), NotebookLM artifacts (`*-claims.json`, `*-summary.md`, anything under `tasks/notebooklm-*/`), and Pipeline C structured outputs are **never deleted** by `/distill` regardless of manifest contents — these were marked PRESERVE/PROMOTE at Phase 0 and are corpus, not debris.

6. **Commit deletions:** `"distill: remove N distilled artifacts"`

7. **Update distillation log:** append all processed artifacts **with individual file paths and dispositions** to `docs/wiki/.distill-log.md` — this is the idempotency mechanism for subsequent runs. Format: `- [file_path] → [DISTILLED|EPHEMERAL|SKIP|PRESERVE|PROMOTE] (run: [run-id])`. Per-file entries are required — directory-level summaries are insufficient for Phase 0 exclusion matching.

8. **Amend log update** into the deletion commit

9. **Clean scratch:** `rm -rf state/scratch/artifact-distillation/{run-id}/`

**Two separate commits** (additions vs deletions) so wiki content survives even if deletion needs reverting.

**If `--no-delete`:** skip steps 5-8, only apply wiki updates (steps 0-4).

---

## Cost Profile

| Scenario | Haiku | Sonnet | Opus | Wall-Clock |
|----------|-------|--------|------|------------|
| Small (<30 artifacts, 2-4 systems) | 4 (2 scan + 2 QG) | 2-4 + 3a clusters + 3b + 3d | 0 (happy path) | ~20 min |
| Medium (30-200, 4-8 systems) | 8-12 (4-6 + QG) | 4-8 + 3a clusters + 3b + 3d | 0 (happy path) | ~30 min |
| Large (200+, 6-12 systems) | 16 (8 + QG) + 1 clustering | 6-12 + 3a clusters + 3b + 3d | 0–1 (escalation only) | ~45 min |

Plus PM review time at Phase 4 (variable). Interstitial overhead (coordinator reading scratch, clustering, dispatching) accounts for ~5-15 min depending on nugget volume.

---

## Failure Modes

| Failure | Prevention |
|---------|------------|
| Running phases in parallel | Each phase's output shapes the next. Sequential = cheaper AND better. |
| Writing custom dispatch prompts | Templates in `agent-prompts/` are tested infrastructure. Copy verbatim from the relevant per-phase fragment, fill blanks. |
| Haiku synthesizing instead of cataloging | "Completeness matters more than analysis" instruction is in the Phase 1 template. Don't remove it. |
| Delta operation references non-existent heading | Phase 3a flags these as contradictions in its scratch output — surface for coordinator review |
| Deleting active handoff references | Phase 0 reads `state/handoffs/` for active context — those files are read-only, never batched |
| Guide drift across runs | Delta format for existing guides — only changed sections included, not full rewrites. Coordinator applies deltas mechanically in Phase 5; Phase 3 agents do not expand them. |
| Phase 2.5 promotes mechanical findings | Agent prompt explicitly excludes mechanical / docs-checker-class findings; only architectural reviewer findings are eligible. Review `agent-prompts/phase-2-5.md` if false positives appear. |
| Phase 2.5 counts multiple findings from same plan as N convergences | Each plan contributes at most one count toward convergence, regardless of how many findings from that plan shape-match. One plan = one count. |
| Phase 2.5 re-mines historical SHAs on update path | Update path uses the topic key as the join — it does NOT call `git show` on prior `source_findings[*].sha` refs. Only new live findings trigger SHA lookup on initial corpus creation. |
| Phase 2.5 proposals file missing before Phase 3a/3b/3d | If zero proposals emitted, write an empty `judgment-proposals.md` with a `## No proposals — corpus below threshold` header so Phase 3a/3b/3d can proceed. |
| Partial 3a completion (k of N cluster agents complete, others timeout) | Coordinator re-dispatches only the missing shards — 3a agents write to named scratch paths (`phase3a-contradictions-{cluster-tag}.md`), so re-running a completed shard is safe (idempotent). |
| Opus escalation auto-dispatches but Opus fails or times out | Coordinator surfaces an escalation-failure note to the Phase 4 PM gate instead of proceeding. PM decides whether to accept output without contradiction resolution or retry. |
| 3b dedup produces an empty DR set (zero DRs across all Phase 2 outputs) | Always a pipeline failure — not a valid empty outcome. Phase 2 did not run correctly or produced no judgment proposals. 3b agent writes a `PHASE_3B_FAILURE` report; coordinator halts and surfaces the error. |
| Single-topic cluster in 3a (only one topic, no within-cluster pairwise comparison possible) | Coordinator skips dispatching a 3a agent for that cluster. Cross-cluster check (post-3a coordinator pass) still applies to single-topic clusters. |
| Artifacts distilled twice | Distillation log (`docs/wiki/.distill-log.md`) excludes already-processed artifacts at Phase 0 |
| PM skips approval and deletion runs | "Wait for explicit approval" is unconditional — no timeout, no auto-proceed |
| Scratch file missing after agent completes | Verify with `ls`; re-dispatch once; skip batch on second failure — don't stall the pipeline |
| Phase 5 single apply-agent times out (~50min/170 tool-uses on large runs) | Phase 5 step 2 splits work across N Sonnet apply-agents sized **by volume, not function**: shard the topic-delta role into ⌈guide-count/3⌉ agents (~2-3 guides each, ~5-10 min) on large runs (≥5 guides); coordinator orchestrates, never types edits itself |
| Phase 5 monolithic Apply-Agent A — function-based slicing puts ALL topic deltas in one process (2026-05-28-pass1: 14 guides in one agent, 20+ min, PM flagged) | Phase 5 step 2: A-role shards by guide-count; function split is role taxonomy, not agent count; wiki files are file-disjoint so deltas fan out freely |
| Apply-agents under-count their own work in chat | Phase 5 step 3: verify with `git diff --stat`, treat the diff as ground truth, re-dispatch on missing changes |
| `git rm -r tasks/<dir>/` sweeps up co-located research corpora (asar, `.next/`, datasets) | Phase 5 step 5: `.md`-only deletion lists; pre-commit audit `git status --porcelain \| awk '$1=="D"' \| grep -v '\.md$'` must be empty; PRESERVE/PROMOTE corpora never deleted regardless of manifest |
