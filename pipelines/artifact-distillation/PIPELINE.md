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

`/update-docs` Phase 8b = prune without extracting (count → classify → delete). Runs unconditionally on every `/update-docs` invocation under conservative thresholds. Replaces the former `coordinator:artifact-consolidation` skill. See `pipelines/update-docs/artifact-pruning.md`.

`/distill` = extract knowledge into wiki, then delete source material. Runs upstream of Phase 8b conceptually: knowledge extraction first, raw bulk pruning second. Use `/distill` when there's wiki-worthy knowledge in the artifacts about to age out; rely on `/update-docs` Phase 8b for routine bulk cleanup.

---

## Phase Pipeline — STRICT SEQUENCE

```
Phase 0 (Coordinator) → Phase 1 (Haiku ×N, parallel) → Phase 1.5 (Haiku ×N, QG)
  → [Clustering] → [Consolidation, coordinator, mechanical] → Phase 2 (Sonnet ×M, parallel)
  → [Coverage gate, mechanical set-diff — gap re-synth (Sonnet) only for uncovered nuggets]
  → Phase 2.5 (Sonnet ×K, judgment-mining)
  → Phase 3a (Sonnet ×C, parallel by cluster) → [cross-cluster-check] → [Esc: Opus + fidelity-check (Sonnet), if needed]
  → Phase 3b (Sonnet, single) → Phase 3c (Coordinator, mechanical) → Phase 3d (Sonnet, single)
  → Phase 4 (PM gate) → Phase 5 (Coordinator, apply + delete)

Phase 2.5 through 3d (all agent-dispatching sub-steps of that range, including the cross-cluster
check and conditional Opus escalation) are folded into `distill-harvest.workflow.js` — the
background Workflow dispatches them directly, in-memory, with no EM turn between stages. Phase
3c stays coordinator-mechanical (no agent, folded or otherwise); Phase 4/5 stay EM-orchestrated.

Cross-Repo Archive Specialist Branch (Sonnet ×1 or ×N shards, parallel to Phase 1/1.5)
  runs alongside the generic scan, feeds its own dispositions into Phase 3c/3d
```

**Phases MUST run sequentially.** Each phase's output shapes the next phase's prompts. Do not begin the next phase until all agents in the current phase have completed and their scratch files verified. The Cross-Repo Archive Specialist Branch is the one exception — it processes a disjoint input cohort (`cross-repo/archive/*.md`) and runs in parallel with Phase 1/1.5, converging with the main pipeline at Phase 3c/3d consumption. See § Cross-Repo Archive Specialist Branch below.

---

## Phase 0: Scoping (Coordinator, ~5 min)

**Native op backing this phase:** the harvest-debt set, ripeness partition, memo cohort,
`wikiDirs`/`wikiSlugs` index, and batching computed by steps 1-6 below are the same outputs
emitted as one JSON payload by claude-klabauter's `distill.scope` op (`coordinator_core/ops/distill_scope.py`,
`@register_op("distill.scope")`) — cite this op, not the retired per-script names, when pointing at
"what computes Phase 0's Workflow INPUT". The individual `bin/distill-*.py` CLIs cited below remain
valid as the C8-contract entrypoints `distill.scope` is built from.

1. **Inventory artifact directories:** `plans/`, `docs/completed-work/`, completed `tasks/*/` dirs, `docs/research/`, `~/docs/research/`, `docs/superpowers/specs/`, `tasks/*/spec.md`, `tasks/*/design.md`. **`cross-repo/archive/` (closed `status: actioned` memos) is EXCLUDED from this generic candidate list** — it is routed to the dedicated Cross-Repo Archive Specialist Branch (§ below) instead, not scanned by the generic Haiku/Sonnet path. See `commands/distill.md` § Cross-repo archive distillation for the input-enumeration detail. **`archive/handoffs/` is EXCLUDED from every distillation cohort** — handoffs are not a knowledge source and carry no distill fate; the whole archive gets the bounded outlier scan (§ Handoff outlier scan below) and never a scan batch, a harvest, or a deletion row.

   **Plan files are the priority cohort.** Terminal plans already swept to `archive/specs/` by the session-init sweep (enumerated via `bin/query-records --type plan --format paths --root archive/specs/`, minus any paths already recorded in `state/distillation-log.md` under a `DISTILLED`/`PROMOTE` disposition — the un-harvested set = "harvest debt") are the highest-yield distillation source (`commands/distill.md:20-21`) and carry the heaviest Phase 5 sub-step (knowledge-harvest). They are processed **first** and banked before ephemera disposal — see the harvest-debt drain contract in Phase 5 and `commands/distill.md § Phase 5`.

   **[claude-klabauter-reliant] Compute the un-harvested set via `bin/distill-harvest-debt.py`, not LLM
   re-derivation.** Per the C8 contract (`docs/contracts/distill-engine-scripts.md` § 2):
   `bin/distill-harvest-debt.py <archive/specs-dir> state/distillation-log.md` emits
   `{"harvest_debt": [...basenames], "harvested_count": N, "total_specs": N, "warn": bool}` on
   stdout. `harvest_debt` IS the un-harvested set referenced throughout this Phase — do not
   compute it by hand-comparing directory listings against log rows. **FAIL LOUD invariant:**
   the script exits non-zero with a stderr error if `state/distillation-log.md` is absent — an
   absent log must NEVER be read as "harvest everything" (finding #1 correctness hazard); if
   the script fails this way, halt Phase 0 and surface to the coordinator rather than
   proceeding with an unbounded/fabricated debt list. A `warn: true` field is a loud
   stale-log signal (debt disproportionate to logged rows), not a hard failure — surface it in
   the Phase 0 output. **Agentic-path fallback if claude-klabauter declines / the script is
   unavailable:** revert to manually diffing `archive/specs/` basenames against
   `state/distillation-log.md` `DISTILLED`/`PROMOTE` rows, preserving the same fail-loud
   absent-log behavior — degraded (LLM token cost, re-derivation risk), not broken.
2. **Catalog artifact formats:** identify which directories contain frontmatter-bearing markdown, plain markdown, JSON/YAML, or mixed formats.
3. **Inventory existing wiki:** `docs/wiki/`, `docs/decisions/` — needed for idempotent merging. Extract guide headings/topic lists for the reality check. Also note any gaps: systems that appear in specs or research but have no corresponding guide yet (these are new-guide candidates). **Index on filename, not just H1 title.** Capture the full `docs/wiki/*.md` and `docs/decisions/*.md` filename list alongside the H1/topic headings — near-duplicate FILENAME collisions (e.g. `onboarding-flow-shape.md` already on disk while a synthesizer later proposes `onboarding-flow.md`) are invisible to a heading-keyed index. Pass the filename list to the reality-check scout so ALREADY_CAPTURED classification can match on filename stem similarity, not only on title. (sibling: `CLAUDE.md` § Pre-Dispatch Verification — "grep existing surface before scaffolding agent-facing files; collisions hide under longer existing names".)

   **DUAL-TREE HAZARD — enumerate EVERY wiki tree present, not just `docs/wiki/`.** A repo may
   carry more than one wiki tree. This coordinator source repo is the concrete instance: it has
   BOTH `docs/wiki/` (project-scoped guides) AND `coordinator/docs/wiki/` (plugin-bundled
   doctrine guides — see `docs/README.md` § Plugin-bundled wikis). Phase 0 MUST enumerate every
   wiki tree the repo actually has (generically — `docs/wiki/` always, plus
   `coordinator/docs/wiki/` when that directory exists; do not hardcode "exactly two" as a
   universal, the two-tree case is this repo's instance, not the general rule) and build ONE
   flat slug index spanning all of them. Enumerating only `docs/wiki/` blinds the downstream
   reality check to whatever doctrine lives in the second tree and synth defaults to minting a
   duplicate NEW file instead of merging into the existing guide.

   **Output shape:** `wikiDirs` — an ordered list of every wiki tree found (`['docs/wiki',
   'coordinator/docs/wiki']` in this repo's case, or just `['docs/wiki']` on a single-tree repo);
   element `[0]` is the default/primary home for any NEW file the run mints. `wikiSlugs` — a flat
   `{'<slugified-filename-stem>': '<repo-relative-path>'}` index, union across every dir in
   `wikiDirs` (cheap — filenames only, no content read). These two structures are the Phase 0
   wiki-inventory OUTPUT and are what downstream Workflow dispatch consumes (see § Consolidation
   below and `commands/distill.md` § Phase 0). This replaces the older single-map
   `wikiInventory` shape — a caller that still passes `wikiInventory` without `wikiSlugs` is
   tolerated (derives an empty slug index rather than crashing) but new callers pass
   `wikiSlugs`/`wikiDirs`.

   **Filename-stem overlap check (Phase 0 gate):** Before Phase 3c proposes any new `DIRECTORY_GUIDE.md` entry (and before any synthesizer emits a new guide filename), compare the proposed guide name stem against all existing `docs/wiki/` filenames after normalization (strip `-shape`, `-design`, `-v2`, date prefixes, pluralization; prefix/substring rule fires only when shorter stem ≥8 chars). Near-duplicate collisions are surfaced at the Phase 4 PM gate — NOT auto-created and NOT auto-skipped. The coordinator decides at Phase 4, not the synthesizer at Phase 2. Rationale: synthesizers propose guide names from their topic cluster without seeing the full wiki inventory; the Phase 0 stem check is the mechanical gate that catches near-duplicates before they become disk collisions.
4. **Read distillation log** (`state/distillation-log.md` — the SINGLE canonical log per repo; schema-of-record: `coordinator/schemas/distillation-log.schema.md`) if it exists — use as a hint for the reality check, but do NOT rely on it as the sole exclusion mechanism. The log can be stale or incomplete.
5. **Read `state/handoffs/`** for active context (read-only, never deleted)
6. **Reality check (Haiku scout):** Dispatch a single Haiku agent with the candidate file list + existing guide headings. The scout reads each candidate file and classifies it:
   - **NEW** — contains knowledge not yet captured in existing guides or decision records
   - **ALREADY_CAPTURED** — knowledge is already in the wiki (compare against guide headings/content) (in-repo wiki/DR only — a `~/.claude` memory pointer is NOT durable capture; see MEMORY-NOT-DURABLE-CAPTURE)
   - **EPHEMERAL** — pure session tracking, status updates, no lasting value
   - **SKIP** — active reference, forward-looking content, or in-progress work

   **Special classification rules (override general logic):**
   - **Research outputs** (`docs/research/*.md`, `~/docs/research/*.md`, Pipeline A/B/C/D final outputs): always **PROMOTE** — source files are never deleted, never modified in place; but key findings (decisions, architecture insights, gotchas) must be extracted and merged into the relevant guide sections. If no matching guide exists for the research topic, create one. Copy verbatim to `docs/research/` if not already there. Pipeline C outputs (structured YAML/JSON, files containing `manifest_version:`) fall under this same rule.
   - **NotebookLM outputs** (`tasks/notebooklm-*/`, any file with "notebooklm" in its path, `*-claims.json`, `*-summary.md` from research pipelines): always **PRESERVE** — never deleted, never modified in place. Key claims may be extracted into guides at synthesizer discretion.
   - **Archived handoffs** (`archive/handoffs/*.md`): **not a cohort.** Never classified, never harvested, never deleted by `/distill`. They reach this ceremony only through the bounded outlier scan (§ Handoff outlier scan), whose product is PM-gate context, never a nugget or a deletion row.
   - **Design specs** (`docs/superpowers/specs/*.md`, `tasks/*/spec.md`, `tasks/*/design.md`): classify as **NEW** if the spec was executed (check for corresponding implementation in git log or code) — extract all design decisions as decision records in the relevant guide, then mark the spec as archivable. Classify as **SKIP** if the spec is still in-progress or unapproved.
   - **Tasks cohort — forward-looking / speculative artifacts** (`tasks/**/*.md`): spike / recon / scaffold artifacts describing not-yet-actualized work (sibling-repo recon, not-yet-built forks, exploratory spikes) are **SKIP** — do not crystallize speculative patterns into evergreen wiki until the work actualizes (coordinator "wait for instance #3" doctrine). Forward-looking content is already **SKIP** per the general SKIP definition, but the Phase 0 classifier over-promotes tasks without an explicit rule; this bullet closes that gap. Only task artifacts backed by **shipped / actualized work** are NEW-eligible.
   - **Canonical plans** (`archive/specs/**/*.md`): classified by the **ripeness gate** below — only RIPE (delivered) plans are **NEW** (harvest: extract knowledge nuggets); PARTIAL plans are **BLOCKED** at Phase 3d (naming the unverifiable AC — the knowledge is genuinely not harvestable yet) and ABANDONED plans are **PRESERVE**-in-archive (never harvested, never deleted); both stay retained in `archive/specs/` — the session-init sweep already moved them there. IN-FLIGHT plans remain in `docs/plans/` and are not in this cohort at all.

   **Phase 0 ripeness gate (plans — delegates to `plan-delivery-audit`).** Do NOT hand-roll a done-vs-in-flight predicate — the canonical classifier is `skills/plan-delivery-audit/SKILL.md:128-136`. For each plan in `archive/specs/` (the harvest-debt set = plans in `archive/specs/` minus plans already recorded in `state/distillation-log.md` under a `DISTILLED`/`PROMOTE` disposition), classify by frontmatter `status:` + AC verifiability at HEAD. IN-FLIGHT plans are not in this cohort — they remain in `docs/plans/` untouched by the sweep:

   **[claude-klabauter-reliant] Frontmatter `status:` partition via `bin/distill-ripe-filter.py`.** Per
   the C8 contract (`docs/contracts/distill-engine-scripts.md` § 3): `bin/distill-ripe-filter.py
   <archive/specs-dir>` emits `{"harvest": [...RIPE paths], "skip": [{"path", "status",
   "reason"}, ...]}` on stdout — a pure frontmatter `status:` scan, no LLM. This mechanically
   produces the `status: implemented`/`status: shipped` half of the RIPE/PARTIAL/ABANDONED
   split below (`harvest` entries are RIPE-by-status; every `skip` row's `reason` names the
   actual status found). **The script does NOT verify AC pass-at-HEAD** — that half of the
   RIPE gate (Oracle DELIVERED+REVIEWED / DELIVERED-UNREVIEWED tie-break) stays the
   `plan-delivery-audit` judgment layer's job on top of the script's `harvest` set; the script
   narrows the candidate set the AC-verification judgment runs over, it does not replace that
   judgment. **Agentic-path fallback if claude-klabauter declines / the script is unavailable:** revert
   to an LLM reading each plan's frontmatter by hand to partition RIPE/PARTIAL/ABANDONED/
   IN-FLIGHT — degraded (per-spec LLM token cost), not broken.
   - **RIPE → NEW** (harvest: extract nuggets + trim→archive): `status: implemented` or `status: shipped` AND all typed-prefix ACs pass at HEAD (Oracle DELIVERED+REVIEWED or DELIVERED-UNREVIEWED). This is the dominant case — `status: implemented` is on the large majority of completed plans.
   - **PARTIAL → BLOCKED** (Phase 3d manifest disposition, `coordinator/pipelines/artifact-distillation/agent-prompts/phase-3d.md`): `status: implemented`/`shipped` but ACs fail or are absent/unverifiable ("self-assertion without machine-checkable evidence is not delivery" — Oracle PARTIAL tie-break). The row names the specific unverifiable AC. Un-harvested, retained in `archive/specs/` — the sweep moved it there but knowledge-harvest is blocked until ACs are verifiable. This is a real external condition (an unresolved AC), not the run's own incompleteness — it is BLOCKED, never SEND_BACK.
   - **IN-FLIGHT → no Phase 3d mapping.** `status: in-progress` / `draft` / `reviewed`. These plans are NOT in the archive/specs/ cohort at all — they remain in `docs/plans/`, not yet swept, untouched, and never reach the Phase 3d manifest under any disposition. Do not invent a mapping for this case.
   - **ABANDONED → PRESERVE-in-archive**: `status: superseded` / `abandoned` / `cancelled`. The sweep moved the plan to `archive/specs/` (terminal status), but it is **never harvested** — retained in archive, not deleted, and never re-harvested. An abandoned plan must NOT be harvested as if delivered.
   - **Default on ambiguity → BLOCKED** (treat as PARTIAL — this is an alias of the PARTIAL case above, not a fifth case: it inherits PARTIAL's BLOCKED mapping, naming the unverifiable AC). Wrongly burying a live plan costs more than leaving a ripe plan one cycle; the conservative default is intentional. This widens the Phase 3d manifest's BLOCKED enum (`agent-prompts/phase-3d.md`) to a second, Phase-0-sourced case alongside its commitment/active-reference/unapproved-spec cases: "a Phase-0 ripeness-gate PARTIAL/ambiguity-default plan, naming the unverifiable AC."
   - **Excluded signals (do NOT use):** `## Deviations` sections (retired at `skills/workstream-complete/SKILL.md:93` — dead surface), and `SHIPPED: X (was: Y)` annotations (a forecast-correction marker on a small minority of plans, a Phase 1 knowledge input, NOT a ripeness gate). `status: consumed`/`shipped`-as-handoff-status do not apply to plans.

   **Handoff outlier scan (bounded, non-harvesting).** Archived handoffs are not a distillation
   cohort — there is no resolution gate, no harvest eligibility, and no per-batch scan. Instead,
   dispatch exactly **two Sonnet scouts over the whole `archive/handoffs/` archive**, once per run,
   briefed to surface outliers only: long predecessor/successor chains, roadmap batons, and visible
   reversals. Their product is context for the Phase 4 PM gate. They hold **no deletion authority**
   — no `archive/handoffs/**` path is ever eligible for a deletion-manifest row, and no handoff
   section is ever harvested into a guide or DR.

   Deletion of archived handoffs remains owned by `/update-docs` Phase 8b
   (`pipelines/update-docs/artifact-pruning.md`), which is unaffected by this pipeline.

   The scout returns a classified list with counts. This is the **ground truth** for scope, replacing the distill-log as the primary filter. The distill-log is a hint; the scout is the authority.

7. **Scope gate:**
   - **0 NEW artifacts:** **Abort.** Report "nothing to distill" and stop. Optionally offer to delete EPHEMERAL files directly.
   - **Otherwise:** proceed as the single pipeline shape below — the background Workflow (`commands/distill.md` § Phase Overview) is the vehicle unconditionally, no size gate. The former tiered scope-gate (lightweight / standard / full-pipeline modes split by NEW-artifact count, and the separate N>500 Phase-3d-fanout flip) is retired: once the Workflow is always the vehicle, the single-Sonnet-vs-fanout mode distinction it existed to express no longer applies — Wave 1 scan is always journaled per-artifact and Wave 2 synthesis is always one-agent-owns-one-guide, regardless of corpus size. See `commands/distill.md` for the Workflow's own internal batching/concurrency-cap mechanics.
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

**Input types:** `docs/plans/*.md` (canonical specs) and scaffolding stubs in `tasks/<feature>/stubs/`. **`archive/handoffs/*.md` is not an input type** — handoffs are not a knowledge source; they get the bounded outlier scan in Phase 0 and never enter a Haiku batch.

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

Scout output must conform to § Phase 1 Scout Output Schema (below) — fenced YAML block under each group H2 heading is mandatory.

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

## Cross-Repo Archive Specialist Branch (Sonnet, parallel to Phase 1/1.5)

**Model:** Sonnet. **Dispatch:** Single agent (or sharded by chronological window on large
cohorts — see prompt template). **Runs:** parallel to Phase 1/1.5, on a disjoint input
cohort (`cross-repo/archive/*.md`, closed `status: actioned` memos only — excluded from
the generic Phase 0 candidate list, per § Phase 0 step 1 above).

**Why a dedicated branch, not the generic Haiku nugget-scanner + topic-Sonnet path:**
Cross-repo memos carry commitment-closure state (does a linked sibling-repo promise
remain open?) and occasional boundary-ratification content (rare cross-team
architecture decisions) that a fragment-level Haiku nugget pass is poorly suited to
judge — both require reading the memo whole, not as extracted nuggets, for any memo
the EM hasn't already labeled at action time (see the specialist prompt's frontmatter
fast-path for `distill_fate:`-stamped memos, which skip the full-body read). Routing
this cohort through the generic path risks silently deleting a memo whose sibling
commitment is still open, or reducing a genuine boundary-ratification decision to an
`[EPHEMERAL]` nugget. AC6.

**[claude-klabauter-reliant] `memo.triage` pre-filter (run BEFORE the Sonnet specialist dispatch).**
Per the C8 contract (`docs/contracts/distill-engine-scripts.md` § 1), dispatch claude-klabauter's
`memo.triage` COMPUTE_ONLY op (`coordinator_core/ops/memo_triage.py`, registered as
`memo.triage`) over the `cross-repo/archive/*.md` cohort before this branch's Sonnet agent
runs. The op returns `{promote: [...], disqualified: [...], candidates: [...], counts: {...}}`
— a deterministic pre-filter, not a final promotion decision. **Judgment stays here, not in
the op:** the Sonnet specialist's commitment-closure + boundary-ratification lens still runs
over the op's `promote` set (the small candidate list), replacing the pre-rebuild behavior of
feeding the ENTIRE memo corpus to Sonnet for classification — this is the dominant cost this
rebuild eliminates (findings #1–#5, #8: the 2026-07-12 dogfood run fed all 257 memos to
Sonnet). Entries in `disqualified` are excluded from the specialist's input cohort entirely
(already-captured or scored below the pre-filter threshold) unless the coordinator has reason
to override for a specific memo. **Observability (#9):** read `counts.promote` /
`counts.total` from the op's output — warn if the ratio exceeds 20% (a wide-net promote set
defeats the point of the pre-filter; the op itself only emits the counts, the caller computes
and warns from the ratio). **Fail-loud on malformed op output:** if the op's stdout is
missing any of `promote`/`disqualified`/`counts.promote`/`counts.total`, treat as
op-unavailable and fall back to the agentic path — do not attempt the ratio computation
against a malformed response. **Agentic-path fallback if claude-klabauter declines / the op is
unavailable:** revert to feeding the full `cross-repo/archive/*.md` cohort directly to the
Sonnet specialist below with no pre-filter — degraded (the full per-memo LLM cost findings
#1–#5/#8 diagnose), not broken.

**Lens:** commitment-closure + boundary-ratification. Full procedure, dispatch prompt,
output schema, sharding rule, and out-of-scope list:
`agent-prompts/cross-repo-archive-specialist.md`.

**Inherits** the pipeline-wide "Out-of-scope actions for all dispatched agents" block
(`commands/distill.md` § top-of-file) — no destructive `gh`/git actions. The specialist
prompt adds branch-specific out-of-scope items (no direct wiki/DR writes, no memo
deletion, no commitment-ledger mutation, no `cross-repo/inbox/` reads) on top of that
inherited floor.

**Native op backing the read-scope partition:** the mechanical split between the
unlabeled-residue partition (what this branch's Sonnet specialists should read) and the
labeled partition (mechanical log-append eligible) is computed by claude-klabauter's `memo.fate_partition`
op (`coordinator_core/ops/memo_fate_partition.py`, `@register_op("memo.fate_partition")`) —
partitions on `distill_fate:`/`in_repo_capture:` plus a capture-target existence check. Cite
this op name when describing why the specialist reads only one partition.

**Convergence with the main pipeline:** the specialist's `cross_repo_dispositions:`
scratch output is consumed by Phase 3d (deletion manifest — `ROUTINE` entries become
synthetic `deletions:` rows; `COMMITMENT_OPEN` entries are excluded) and, for any
`BOUNDARY_RATIFICATION` draft, by Phase 3c/Phase 5 apply-agents the same way a Phase 2
new-guide/DR output is consumed. No Phase 2.5/2.7-QG/3a participation — this branch
does not produce nuggets or dispositions in the Phase 2 shape, so the contradiction-
detection and coverage-gate machinery built for that shape does not apply to it.

**Scratch verification:** Verify the specialist's scratch file(s) exist before Phase 3c/3d
proceed to consume `cross_repo_dispositions:` output.

**Drop protection is two-layered:** the specialist's own mandatory self set-diff
(assigned memos vs. `cross_repo_dispositions:` keys, `assigned_count` echoed in
frontmatter — see `agent-prompts/cross-repo-archive-specialist.md` § Output schema) is
the first line; the coordinator's dispatched-vs-classified set-diff at consumption time
remains the backstop, not the sole guard.

---

## Baton Fate — routing note

Batons (`.git/coordinator-sessions/<sid>/baton.json` and written continuation/execution/spinoff
batons) are never a Phase 0-8 harvest input — plans are what get wikified, batons are a plan's
exhaust. A birth (unpromoted) baton is deleted on a distillation run without entering any scan
batch. A written baton survives as cross-reference for an agent working its joined plan (joined
on `deliverable_id`) and is deleted with that plan once the plan is wiki-ified or
pruned — keyed on the plan's own Phase 5 disposition, never on the handoff archive (which this
pipeline no longer disposes of at all). No baton
carries a fate field; no phase in this pipeline decides one. The deletion mechanism itself is
engine-plane and pending, requested at
`state/memo-outbox/2026-08-21-baton-fate-and-lineage-ruling.md` (C7) — this pipeline states the
fate as present-tense truth regardless of that ask's outcome. Rationale: `distill-residue` wiki
page.

---

## Phase 1 Scout Output Schema

Phase 1 Haiku agents must emit a fenced YAML block for each classification group (EPHEMERAL clusters, ALREADY_CAPTURED clusters) — specifically, the first fenced YAML block occurring after the H2 heading and before the next H2 heading (or EOF). Phase 5 reads this YAML block when expanding `deletion_groups:` entries — the YAML block is authoritative; the surrounding Markdown prose is human-readable documentation only.

**H2 heading format:** The heading text must exactly match the `section_anchor:` value declared in the corresponding `deletion_groups:` entry in the Phase 3d manifest. Example:

```
## EPHEMERAL — task tracking and session logs (archive/completed/2026-05)
```

**Fenced YAML block (mandatory, immediately under the H2 heading):**

```yaml
artifact_paths:
  - archive/completed/2026-05/2026-05-01-foo.md
  - archive/completed/2026-05/2026-05-02-bar.md
description: "Completion logs from 2026-05 sprint — pure session tracking, no lasting knowledge."
```

**Schema:**
- `artifact_paths:` — required. Ordered list of file paths (relative to repo root) belonging to this group. Phase 5 iterates this list to build synthetic `deletions:` rows. The `count:` field in the `deletion_groups:` entry must equal `len(artifact_paths)` — mismatch causes Phase 5 to abort.
- `description:` — optional. Human-readable summary of the group for PM review and distillation log. Not consumed programmatically.

**Invariant (AC16):** Every group section in a Phase 1 scout output that is cited by a `deletion_groups:` entry MUST have this fenced YAML block. Missing YAML block → Phase 5 `deletion_groups:` expansion aborts for that group with a named error.

---

## Clustering Interstitial (Coordinator or Haiku)

After all Phase 1.5 verdicts are PASS (or batches are marked FAIL/SKIP), regroup nuggets from input-batch grouping to output-topic grouping.

**For ≤100 nuggets:** Coordinator reads all Phase 1 scratch files and builds the clustering table directly (mechanical, not wasteful at this scale).

**For >100 nuggets:** Dispatch a single Haiku clustering agent using the **Clustering: Haiku Clustering Prompt** from `agent-prompts/clustering.md`. The agent produces a mapping of `{system_tag → [nugget_ids_with_batch_references]}`. Coordinator validates the mapping before proceeding.

**Output:** topic dispatch table mapping each guide topic to its source nuggets across all batches. This table drives Phase 2 dispatch.

---

## Consolidation (Coordinator, mechanical — pure function, no dispatch)

Runs between Clustering and Phase 2/Wave 2, over the clustering table's raw cluster set —
**after** curation (§ above) has already run on invocation A's tag census and every surviving
tag has cleared claude-klabauter's `distill.curate_clusters` verdict. That ordering is why consolidation is
now a single unconditional rule rather than a shrapnel-triage pass: curation decided per-tag,
upstream of clustering, whether a tag deserves a home at all, so by the time a cluster reaches
consolidation the question "does this shit deserve a home" is already answered — consolidation
only decides *which* home.

**Homed / homeless partition.** Partition the raw cluster set by whether `wikiSlugs[slugify(cluster.topicKey)]`
resolves to an existing file (exact slug match, or a `findFuzzyWikiHome` hit):
- **homed** — slug matches an existing wiki file → passes through UNCHANGED; merges into that guide at Phase 2.
- **homeless** — no existing home → **unconditionally becomes a NEW file.** No coarsening, no
  folding, no cap, no misc bucket: every surviving homeless cluster earns its own file, because
  curation already ruled it a real topic before it ever reached clustering.

**The coarsen/fold/cap/misc-bucket mechanics that used to sit here are retired**, not merely
disused — `MISC_MAX_NUGGET_SHARE`, `MIN_SHARED_SEGMENTS`, the segment-prefix trie
(`buildSegmentTrie`/`longestSharedPrefixKey`), `consolidateClusters()` Steps 2-5, and the
`misc-harvest-<RUN_ID>` emission are all deleted from `distill-harvest.workflow.js`, not merely
unreferenced. They existed to triage the homeless bucket *after the fact*, deciding per-cluster
whether a run's inevitable shrapnel earned its own file or got folded into a shared dump. That
triage now happens upstream, per-tag, before clustering — so there is no post-hoc shrapnel left
to triage, and the code that used to do it is gone.

**`SINGLETON_FLOOR` and `NEW_FILE_CAP` are DELETED OUTRIGHT, not held (chunk C4b, commit
`3e99e52c3`).** They are not defined anywhere in `distill-harvest.workflow.js` and are not
pending re-wiring — the two open questions that used to hold them unwired (does curation's `keep`
verdict weight per-tag nugget volume; what does a cold-start drop-rate census show) are both
answered, per `cross-repo/inbox/2026-08-06-claude-klabauter-em-curate-clusters-four-answers-volume-
is-weighted-but-not-a-floor.md`. The minting policy they used to encode now lives in exactly one
place — claude-klabauter's `distill.curate_clusters` gate — parameterized by `recommended_keep_threshold`,
a value returned alongside `tag_counts` from invocation A and derived below.

**Volume IS weighted, but not by a floor we hold — by a threshold WE pass.** The curation gate
compares `keep_threshold` against a cluster **FAMILY's** total nugget count, summed across every
tag folded into that family, not any single tag's count — two count-1 siblings clear a threshold
neither would clear alone. The drop test is `family_total < keep_threshold`. **At the gate's
default of 2 this drops only 1-nugget families — a 2-nugget cluster is KEPT.** The retired floor's
stated job ("a 1-2-nugget cluster doesn't earn its own new file") is thus only PARTLY discharged
at threshold 2, not fully — record that gap honestly rather than smoothing it over.

**Why the threshold lives on our side.** We emit **1 for cold-start** (empty wiki tree, or fewer
than 150 carry-forward nuggets) and **2 for mature**, derived from claude-klabauter's own measured drop
rates (mean of 20 seeds over their 433-nugget/249-tag census, deterministically subsampled to
simulate first runs of increasing size):

| N nuggets | thr=2 | thr=1 |
|---:|---:|---:|
| 20 | 71.2% | 12.0% |
| 60 | 44.4% | 8.7% |
| 150 | 27.4% | 8.8% |
| 433 (full) | 17.1% | 8.1% |

We deliberately do NOT emit 3. This is now a **decided tradeoff with a measured price**, not an
open gap awaiting a number. Threshold 3 has been measured (their reproducer, same seeds 0..19,
deterministic, full 433-nugget corpus):

| threshold | keep | normalize | merge | drop | tag-drop | nugget-drop |
|---|---|---|---|---|---|---|
| 3 | 38 | 2 | 124 | 85 | 34.1% | 23.1% |
| 2 (default) | 51 | 2 | 132 | 64 | 25.7% | 17.1% |
| 1 | 86 | 6 | 132 | 25 | 10.0% | 8.1% |

Cold-start (mean of 20 seeds, N=20 nuggets): threshold 3 drops **94.2%** of the corpus, against
71.2% at 2 and 12.0% at 1. Adopting full floor semantics on a mature corpus costs about six points
of nugget loss (23.1% vs 17.1% at 2) — that cost is harvested knowledge discarded permanently.
What it buys is suppressing some 2-nugget wiki files, which are cheap, visible, and mergeable
later. Trading recall for tidiness is the wrong direction for a knowledge harvest, so the retired
floor's 2-nugget-suppression job stays deliberately undone: we stay at 2. Floor semantics want a
high threshold; cold-start survival wants a low one; it is a single knob, so it cannot be a fixed
constant anywhere — it is derived per run from corpus maturity, a fact this repo owns and the
gate cannot see. The policy still lives in exactly one place (their gate); we only parameterize
it.

**Mechanism, not tidying.** `drop_summary.by_cause` makes the 2→3 delta legible: the entire delta is
`below-threshold` (60 / 39 / 0 at thresholds 3 / 2 / 1), while `bare-no-sibling` stays FLAT at 25
across all three thresholds — structural, threshold-invariant, moving the knob changes nothing
about it. The extra drops at 3 are not junk being cleaned up; they are real small topics, which is
exactly why the ruling above goes the way it does.

**Corroboration, not a dependency.** Their gate now auto-derives `keep_threshold` when the caller
omits it; we always pass ours in, so their auto-derivation never fires for us. On their mature
corpus it resolves to 2 — the same value our derivation picks, from a different fact. Two
agreeing heuristics corroborate each other; neither proves the other correct.

**A prediction this plan made, and measurement refuted.** The plan's original worry was that the
gate's structural bare-token rule would savage a cold-start corpus. It does not, and the same
census settles it: at `keep_threshold=1` the drop rate is FLAT — 8-12% across a 20x range of
corpus size, no cold-start blow-up. The structural rule is corpus-size-invariant because it never
consults corpus size; the cold-start degeneration is entirely `keep_threshold`, not the bare-token
rule (71.2% at threshold 2 on a 20-nugget run vs. 17.1% on the full corpus). This is claude-klabauter's
measurement on their own corpus, with their own caveat attached: a single corpus, and a materially
different tag-naming convention could move the ~10% floor.

**Count-conservation invariant, and where drops actually happen now.** No nugget is ever dropped
by *consolidation* — every input nugget lands in exactly one output cluster (`homed ∪ new`). This
is still an assertable invariant (total nugget count in equals total nugget count out), asserted
by the workflow at consolidation time, and it is still true. But it is now the wrong place to
look for where nuggets get dropped: consolidation drops nothing, full stop. **Curation, upstream
of clustering, is where drops happen** — a tag whose verdict resolves to `drop` is deliberately
excluded before its nuggets ever reach a cluster, and every drop is recorded by tag, nugget, and
reason, then surfaced in the `drop_summary` structure returned from invocation B (verdict counts,
homing-override count, dropped-nugget count and share of the pre-curation corpus, and the top-10
dropped tags by nugget volume with their reasons). A `WARNING` log line fires when the dropped
share exceeds `DROP_SHARE_WARNING_THRESHOLD` (0.25, a first guess — claude-klabauter's cold-start census has
since landed, see the threshold derivation above, and does not by itself argue for moving this
number) — a visibility tripwire, not a gate; it never halts a run or suppresses output.

**Verdict payload contract (confirmed, chunk C3c, commit `810ffe46d`).** One verdict entry per
RAW input tag, always. `merge_target` is the destination slug a tag folds INTO — populated ONLY
on `merge`, never null there, and null on keep/normalize/drop. `canonical_slug` is the tag's OWN
normalized slug, not a destination. `reason` is non-empty on every drop, naming which of three
paths fired: placeholder / bare-token-with-no-compound-sibling / family-total-below-threshold. The
drop set is a FILTER over the verdict list (`verdict === 'drop'`), never a separate top-level
`dropped:` key — that key does not exist and is not coming. Clustering keys `keep` on
`canonical_slug` (falling back to the raw tag), `normalize` on `canonical_slug`, `merge` on
`merge_target`; a tag absent from the map, a merge with no `merge_target`, a normalize with no
`canonical_slug`, or an unknown verdict each stop the run rather than inventing a bucket.
**Landed (chunk C3c-successor, commit `67b7061f6`) — code against it.** Per-verdict `drop_cause`,
an enum of `placeholder` / `bare-no-sibling` / `below-threshold`, `null` on non-drops. Plus a
`by_cause` count block nested under `drop_summary`, and top-level result fields `threshold_applied`,
`threshold_auto`, and `nugget_drop_share`. Our drop logging keys on the enum now, not on parsing the
`reason` prose string. The
pinned verdict payload this contract is measured against is a committed test fixture under
`coordinator/pipelines/artifact-distillation/tests/`, asserting the three contract properties
above plus the flat-`bare-no-sibling`-at-25 invariant — the contract is test-enforced, not only
described here.

**Log line:** the Workflow emits a one-line summary at this step —
`consolidation: <rawCount> raw -> <homedCount> homed + <newCount> new (no-misc: curation already
decided upstream which tags survive, per plan chunk C4)` — so a run's homed-vs-new ratio is
visible in the run log without reading scratch files. There is no misc term in this line because
there is no misc bucket left to report.

**Output:** the consolidated cluster set (homed clusters unchanged + every homeless cluster
promoted to `new`) replaces the raw clustering-table output as Phase 2/Wave 2's input. Phase 2's
`synthBriefFor`-equivalent honors a cluster's consolidation-assigned target path when present,
else falls back to the disk-resolved `wikiSlugs` target from § Phase 0 step 3.

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
- `[CANDIDATE_RESTATEMENTS]` — the routing record's `candidate_restatements: [{line, excerpt}]`
  list for this system's target wiki path (same field the automated
  `distill-harvest.workflow.js` Wave 1.5 relay computes — on this hand-orchestrated path, source
  it from the routing record directly, or "none" if empty), or run the Wave-1.5-equivalent CLI
  yourself against the target if no routing record exists for this manual run
- `[SCRATCH_PATH]` — `state/scratch/artifact-distillation/{run-id}/topic-{name}-phase2-sonnet.md`

Instruct each agent in its prompt to use Read and Write. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.) Dispatch with `run_in_background: true`.

**Phase 2 scratch output schema:** Each Phase 2 scratch file opens with a `dispositions:` YAML frontmatter block listing every assigned nugget ID with its operation and target. Full schema: `agent-prompts/phase-2.md` § Disposition Manifest.

**Ownership boundary:** Synthesizers own their scratch files. They write to `state/scratch/artifact-distillation/{run-id}/` only — never to `docs/wiki/` or `docs/decisions/`. Production guides are coordinator-only territory (applied in Phase 5).

**Scratch verification:** Verify all expected topic files exist before proceeding to Phase 3a.

**Recovery for Phase 3a/3b/3d (the highest-risk steps — largest context load, longest runtime) is `resumeFromRunId`, not a manual scratch checkpoint.** `distill-harvest.workflow.js` folds Phase 2.5, 3a (plus the cross-cluster check and conditional Opus escalation), 3b, and 3d into itself (§ below) — Wave 1's scan is journaled by the Workflow runtime, and a rate-limit wipeout mid-run resumes by re-invoking the script with `resumeFromRunId` set to the failed invocation's Workflow-tool `wf_...` id (never to `run_id`, the distillation slug — see the script's own NEGATIVE-SPEC comment). There is no separate `git add`/`git commit` checkpoint step for this vehicle; the two surfaces describe one recovery mechanism, not two.

---

## Coverage Gate (Coordinator, mechanical — retired the former Phase 2.7-QG Haiku wave)

**Model:** none — mechanical JS, no agent dispatch. **Runs:** in-process, inside
`distill-harvest.workflow.js`, immediately after Wave 2 (the Workflow's synth stage, the
resumable-Workflow equivalent of Phase 2) succeeds — before the in-Workflow Phase 2.5
(`judgment-mining-2-5`) stage.

**Retired: the former "Phase 2.7-QG" Haiku ×M-per-cluster wave.** The check is a pure set-diff —
each cluster's returned `dispositions:` nugget IDs vs. its assigned nugget IDs from the
Clustering/Consolidation output — with no semantic interpretation (set membership only). That is
exactly the shape of work a dispatched Haiku agent adds zero judgment to and only adds cost,
latency, and nondeterminism (an agent can misread its own scratch file); doing the diff as free
JS in the Workflow script removes all three.

For each cluster with a synth result, `findCoverageGaps()` computes `uncoveredNuggets` (assigned
nugget objects whose id is absent from that cluster's `dispositions:`). The Workflow logs one
line — `covered/total` nugget counts plus the list of gap cluster topic keys — every run, whether
or not any gaps exist (no silent caps).

**Gap recovery:** any cluster with `uncoveredNuggets.length > 0` triggers exactly ONE Sonnet
gap-synth `agent()` call scoped to only that cluster's uncovered nugget subset (same
`SYNTH_SCHEMA`, same additive-write contract as Wave 2, targeting the same `wiki_path`). The
gap agent's returned `dispositions:` are unioned into the original synth result (dedup by
`nugget_id`, gap-synth entries fill only ids the original result was missing) — there is no
retry-cap/halt-and-surface-to-PM ceremony as the old Phase 2.7-QG FAIL path had, because a
gap-synth failure is caught and logged (`unresolved_gap_clusters`) rather than blocking the run;
Wave 2's own `resumeFromRunId` re-run mechanics remain the recovery path for a hard synth
failure.

Full mechanics: `distill-harvest.workflow.js` § "Coverage gate" (function `findCoverageGaps`,
the gap-synth `agent()` dispatch, and the merge-back loop).

---

## Phase 2.5: Judgment Mining (folded into the Workflow — Sonnet, parallel by topic-cluster)

Mine the run's reviewer sidecars for cross-spec convergence patterns — findings that recur across ≥N distinct plans (default `N=3`, override via `/distill --min-convergence=N`). Convergent findings emit `judgment-proposals` for Phase 3b review and wiki promotion into `docs/wiki/codebase-judgment/`.

**Model:** Sonnet, one agent per topic-cluster, all simultaneous, dispatched directly by `distill-harvest.workflow.js`'s `judgment-mining` phase — read-only orchestrator boundary (no nested sub-agents), reusing the Workflow's own `CONCURRENCY_CAP` (a literal constant — Workflow scripts have no Node API access, so no phase in this pipeline derives its own concurrency cap via `import('node:os')`). Strict-sequencing gate: Phase 2 and its in-Workflow Coverage Gate fully complete before this phase begins; this phase completes before Phase 3a — structural by placement in the script, not a runtime check.

**Full procedure** (corpus collection, finding eligibility, shape-matching rules, update path, convergence threshold, proposal format, promoted-entry frontmatter schema): see `agent-prompts/phase-2-5-judgment-mining.md` — the eligibility/shape-matching/threshold rules it documents are unchanged; the Workflow's dispatch brief follows them inline rather than through a hand-filled template.

**Judgment proposals stay in-memory** (`judgmentResults`, appended to `judgment-proposals.md` by each mining agent for cross-agent visibility within the fan-out) and are returned as part of the Workflow's result — Phase 3b (also folded into the Workflow, § below) consumes them directly rather than re-reading a hand-managed scratch file mid-chain.

---

## Phase 3a: Contradiction Detection (folded into the Workflow — Sonnet, parallel by cluster)

**Model:** Sonnet. **Dispatch:** One agent per topic cluster, all simultaneously, dispatched directly by `distill-harvest.workflow.js`'s `contradiction-detection` phase.

**Sharding rule (Option B — clustered pairwise):** Reuses Phase 2.5's shape-match clustering apparatus (the caller-supplied `contradictionClusters` input, per D3 of the coordinator's own pipeline-defects wiki: cluster on coarse topic domains, never exact topic-string equality). Each 3a agent compares all topics *within its cluster* — detecting intra-cluster contradictions. The Workflow handles cross-cluster contradictions separately (see below).

**Single-topic cluster exemption:** A cluster with fewer than two topics cannot have an intra-cluster contradiction by definition — no agent is dispatched for it; the Workflow folds in a zero-contradiction result directly rather than omitting the cluster.

**Full brief content** (comparison lens, resolvable-vs-unresolvable classification, `contradiction_refs` shape): the Workflow's `contradictionBriefFor()` function builds the dispatch brief inline — the guidance `agent-prompts/phase-3a.md` documents is unchanged, only its delivery mechanism (hand-filled template vs. in-script string) differs.

### Cross-cluster check (mechanical, post-3a, in-process)

After all 3a agents complete, `findCrossClusterContradictions()` runs a mechanical enumeration pass across every returned `contradiction_refs` entry (in-memory, not a scratch-file scan):

1. Collect every `claim_id` and its originating cluster/topic-pair from every 3a result.
2. Flag any `claim_id` that recurs across ≥2 clusters with a differing topic pair as a **cross-cluster contradiction candidate**.
3. Feed these candidates into the Opus escalation path (same path as intra-cluster `unresolvable_contradictions`).

This mechanical step closes the cross-cluster blind spot that per-cluster agents cannot see. No subagent dispatch.

### Opus escalation (conditional, auto-dispatch, folded into the Workflow)

After the cross-cluster check, the Workflow reads `unresolvable_contradictions` from every 3a result plus the cross-cluster candidates:

- **If total unresolvable count = 0 and no cross-cluster candidates:** proceed directly to Phase 3b with no escalation dispatch at all.
- **If any unresolvable contradictions or cross-cluster candidates exist:** the Workflow auto-dispatches a single Opus resolution agent (same lens `agent-prompts/phase-3-esc.md` documents), then a single Sonnet fidelity-check agent verifying every flagged source id was cited.

**No PM gate on the escalation itself.** Phase 4 PM gate still applies to the assembled output. If the Opus agent fails to return a result, or the fidelity check reports `FAIL`, the Workflow logs the gap and surfaces it in the returned `opus_escalation` object rather than halting the run — PM decides at Phase 4 whether to accept output without full contradiction resolution or request a re-run.

---

## Phase 3b: Decision-Record Dedup (folded into the Workflow — Sonnet, single)

**Model:** Sonnet. **Dispatch:** Single agent, dispatched directly by `distill-harvest.workflow.js`'s `phase-3b` phase. **Runs after:** Phase 3a, the cross-cluster check, and the conditional Opus escalation above.

**Input, in-memory, not scratch files:** every `CREATE_DR` disposition from Wave 2's returned `dispositions[]` (the decision records synth agents already wrote directly to `docs/decisions/*.md`, the same direct-write contract wiki guides get), plus judgment-mining `new-entry` proposals (cross-reference only — `docs/wiki/codebase-judgment/` is a separate namespace from `docs/decisions/`, never merged into a DR), plus the Opus escalation resolution when Phase 3a triggered one. The dedup agent Reads the real `docs/decisions/*.md` files stamped with this run's `run_id` rather than re-reading a Phase 2 scratch file — there is no staged-apply step for DRs in this pipeline.

**CRITICAL FAILURE MODE:** An empty canonical DR set (zero decision records found) despite non-empty `CREATE_DR` input is always a pipeline error, never a valid outcome. Unlike the retired turn-by-turn path, the Workflow does not halt the run on this — it surfaces `failure: true` plus `failure_detail` on the returned `phase_3b_dr_dedup` object for the Phase 4 PM gate to weigh, the same log-and-surface treatment every other late-pipeline single-agent failure in this Workflow gets. When there is nothing DR-shaped to dedup at all (zero `CREATE_DR` dispositions AND zero judgment new-entry proposals), the Workflow skips the dispatch entirely and records the same failure shape without spending an agent call on it.

---

## Phase 3c: DIRECTORY_GUIDE.md Assembly (Coordinator, mechanical)

**Model:** Coordinator (no subagent). **Runs after:** `distill-harvest.workflow.js` returns, before Phase 4 — despite its number, Phase 3c is deliberately NOT a mid-chain stage inside the Workflow. Phase 3d (which the Workflow does run, immediately after Phase 3b) does not consume Phase 3c's output, so no EM turn is needed between them; Phase 3c stays a post-Workflow, pre-Phase-4 coordinator step because it is already mechanical and needs no agent.

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

**Fuzzy-name overlap check on NEW-guide proposals.** For every new guide name in the Phase 2 frontmatter, compare its filename stem against every existing `docs/wiki/` / `docs/decisions/` filename stem. Flag a **near-duplicate collision** when stems match after normalizing (strip `-shape`, `-design`, `-v2`, date prefixes, and pluralization; case-insensitive; or one stem is a prefix/substring of the other with ≤4 trailing chars difference — **but apply the prefix/substring rule only when the shorter stem is ≥8 characters**, so short distinct stems like `auth` vs `author`/`oauth` do not trip a false collision, while `onboarding-flow` vs `onboarding-flow-shape` still does). Example: proposed `onboarding-flow.md` collides with existing `onboarding-flow-shape.md`. For each flagged collision, do NOT silently create the new guide — surface it in the Phase 3c preview under a `## New-guide collisions (PM decision)` heading with both names and a one-line recommendation (merge into existing guide vs. confirm genuinely distinct). The PM resolves at the **existing Phase 4 gate — this does not add a new halt or block auto-proceed; it adds a decision item to the gate that already waits for explicit approval.** This is the duplicate-guide gate — detect-then-surface, never detect-then-silently-create (coordinator/`CLAUDE.md` § Implementation Standards — "detect-then-silently-pick is a footgun").

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

## Phase 3d: Deletion Manifest (folded into the Workflow — Sonnet, single)

**Model:** Sonnet. **Dispatch:** Single agent, dispatched directly by `distill-harvest.workflow.js`'s `phase-3d` phase. **Runs after:** Phase 3b (structural by placement in the script — does not consume Phase 3b's output, so the two could in principle overlap, but the script runs them in sequence).

**Input, in-memory, not scratch files:** the Workflow's own mechanically-computed `distillation_log_rows` (one row per source artifact — path, mechanical disposition `DISTILLED`/`EPHEMERAL`/`SKIP`, fate prose — computed earlier in the same run, § "Distillation-log rows" in the script) plus the Opus escalation resolution when Phase 3a triggered one. The agent's job is resolving those three mechanical dispositions into the final `DELETE`/`SEND_BACK`/`BLOCKED`/`PRESERVE` verdict by reading real external state (active `state/handoffs/`, open commitments, research/NotebookLM PRESERVE classes) that the mechanical pass has no visibility into — it never re-reads Phase 1/1.5/2 scratch files.

**Suppressed, not dispatched, on join-integrity failure.** When the Workflow's `join_integrity.verdict` is `failed` (§ "Join-integrity verdict" in the script), this phase does not dispatch at all — the source→nugget join is unsafe to trust for disposal purposes, the same suppression the mechanical `distillation_log_rows` pass is already subject to. Never a partial manifest built on an untrustworthy join.

**Either harvested or not — never a middle disposition.** `SKIP` rows (a batch that never scanned) resolve to `SEND_BACK`, naming "batch never scanned" as the reason — never `DELETE` and never a bare "retain"/"no citation found" row that reads as settled. An artifact whose knowledge is not fully extracted is `SEND_BACK` or `BLOCKED`, both of which route it back for completion at Phase 4/5, not into the delete set.

**Cross-Repo Archive Specialist Branch input.** The Cross-Repo Archive Specialist Branch (§ above) still runs alongside Phase 1/1.5 on its own disjoint cohort and still converges at Phase 3d consumption — that convergence is unaffected by this phase's fold into the Workflow. Its pre-converted rows are passed to `distill-harvest.workflow.js` as the optional `crossRepoDispositions` Workflow input (same input-plumbing shape as the script's other optional inputs, e.g. `contextTerms`) and are spliced into the Phase 3d deletion manifest in-script, immediately after the deletion-manifest agent returns and before the artifact re-entry loop — so re-entry covers them like any other row. An absent or empty `crossRepoDispositions` input is a logged no-op.

**`archive/handoffs/**` is never eligible for any disposition** — omitted from the manifest entirely, per the pipeline-wide rule (§ Phase 0 step 1, § Baton Fate).

---

**Phase 3 produces (combined across 3a–3d):**
1. Cross-reference consistency report — contradictions flagged and resolved (3a + optional Opus, folded into the Workflow)
2. Deduplicated decision records (3b, folded into the Workflow)
3. `DIRECTORY_GUIDE.md` preview (3c, coordinator-mechanical, consumes the Workflow's returned `phase_3b_dr_dedup`/`synth_results` rather than Phase 2 scratch frontmatter when the Workflow vehicle ran this pass)
4. **Deletion manifest** — every source artifact resolved to `DELETE`, `SEND_BACK`, `BLOCKED`, or `PRESERVE` with reason (3d, folded into the Workflow)

**Retired: "Phase 3d fanout assembly" (Workflow-fanout mode only).** A prior revision of this
pipeline gated Phase 3d on `N > 500` total deletion-eligible candidates, flipping to a
per-cluster fanout mode with a canonical-manifest assembly step and a pre-deletion sentinel
against partial assembly. This retires the whole tiered scope-gate: the background
Workflow (`commands/distill.md` § Workflow) is now the vehicle unconditionally, so the
single-Sonnet-vs-fanout mode distinction the assembly step existed to bridge no longer applies
— there is one Phase 3d shape regardless of corpus size.

---

## Artifact-Level Send_Back Re-Entry (folded into the Workflow — Sonnet, one per cluster)

**Model:** Sonnet. **Dispatch:** parallel, one re-harvest agent per SEND_BACK cluster (grouped
by originating batch), dispatched directly by `distill-harvest.workflow.js`'s `artifact-reentry`
phase, immediately after `phase-3d`. Runs only when `phase_3d_deletion_manifest.status` is `ran`.

`findCoverageGaps`' shape lifted from nugget level (§ Coverage gate, Clustering Interstitial
above) to artifact level: Phase 3d's `SEND_BACK` disposition means "not yet harvested, not
settled" — carrying it forward unresolved is the exact defect this gate exists to close: either
an artifact was harvested or it wasn't, and if it isn't, it gets sent back to be completed
rather than recorded as settled.

Each round: compute the current `SEND_BACK` set from the deletion manifest, group by batch, and
dispatch one re-harvest agent per non-empty batch cluster to re-open the SEND_BACK artifact(s),
complete the extraction Phase 3d found missing, and re-resolve each to `DELETE`, `BLOCKED`, or
(if genuinely still incomplete) `SEND_BACK` — re-evaluating the delete guards on return exactly
as Phase 3d itself does.

**Same three properties as the nugget-level Coverage Gate:**
- **No silent caps.** Every round logs covered/total (settled vs. still-`SEND_BACK`) whether or
  not any `SEND_BACK` rows remain, before dispatch decides whether to run.
- **A re-harvest failure is caught and logged**, never a run-blocking halt — a batch cluster
  whose agent fails to return leaves its artifacts `SEND_BACK` for the next round (or the cap
  below), the same non-fatal degrade the Coverage Gate's `unresolved_gap_clusters` gives.
- **Bounded re-entry.** Capped at `SEND_BACK_REENTRY_CAP` (2) rounds. An artifact still
  `SEND_BACK` after the cap becomes `BLOCKED`, naming the cap and the original missing-citation
  reason as the cause — never a silent `SEND_BACK` carried forward into the next `/distill` run.

**Run completion condition.** A `/distill` run ends only when every in-scope artifact's final
disposition is `DELETE`, `PRESERVE`, or `BLOCKED`-with-a-named-cause. A non-empty `SEND_BACK` set
in the Workflow's returned `phase_3d_deletion_manifest.deletions` at the point this gate finishes
is an **incomplete run** — this gate's bounded re-entry plus cap-to-BLOCKED conversion is what
makes that condition true unconditionally, without requiring a separate EM turn between Phase 3d
and Phase 4.

---

## Phase 4: PM Approval Gate (Coordinator)

**Atlas staleness advisory (sensor, non-blocking) — run FIRST.** Before presenting the manifest, run the read-only atlas check and surface an advisory per `commands/distill.md § Phase 4 — PM Gate: Atlas Staleness Advisory`: run `bin/check-atlas-watch-drift.py`, map the run's churn (RIPE plans + archived handoffs) to atlas systems via the seed keyword/path-prefix map, and for any churned system that is `DRIFT`/`STALE` emit a one-line "good cause to run `/architecture-audit` on `<system>` before deletion" advisory. No-map case emits a fail-loud-soft "advisory skipped" line. `/distill` is the **sensor**, never the actuator — it never invokes the audit and never blocks on it.

Present to PM:
- Summary table: N guides created/updated, N decisions created, N artifacts to delete
- Full deletion manifest (from Phase 3d)
- `DIRECTORY_GUIDE.md` preview (from Phase 3c)
- Atlas staleness advisory (if any churned system is DRIFT/STALE), or the no-map skipped-line
- PM can remove items from the deletion list

**Wait for explicit approval. Do not proceed without it.**

**If `--dry-run`:** present the summary and stop here. Do not proceed to Phase 5.

---

## Phase 5: Apply and Clean (Coordinator-orchestrated, Sonnet-applied)

**Harvest-debt drain contract (plan-priority).** The move of plans to `archive/specs/` is already done by the session-init sweep — decoupled from `/distill`. What Phase 5 runs first is the knowledge-harvest pass over the un-harvested set (plans in `archive/specs/` not yet recorded in `state/distillation-log.md` under a `DISTILLED`/`PROMOTE` disposition — the SINGLE canonical log, schema-of-record: `coordinator/schemas/distillation-log.schema.md`). This harvest pass is committed (step 4) **before** the deletion steps (5-6). A budget-truncated run drains harvest debt before any ephemera disposal — the cheap mechanical deletion never preempts the expensive knowledge-harvest. Full rationale + ordering: `commands/distill.md § Phase 5` intro.

**Native ops backing the deletion-manifest → PM-gate → apply chain:** the disposal path this
Phase's steps 5-6 walk (Phase 3d deletion manifest → Phase 4 PM approval → step 5's actual
`git rm`) is registered engine-side as three ops — `distill.assemble_disposal_manifest`
(Phase 3d), `distill.stamp_disposal` (the PM authorization stamp landed at the Phase 4 gate:
`disposal_authorized_{by,at,sha,note}`), and `distill.apply_disposal` (step 5's delete tier —
re-runs the TOCTOU guard check, drain-ordering ancestry check, and idempotent per-record replay
before deleting) — all three in `coordinator_core/ops/distill_disposal_manifest.py`,
`distill_stamp_disposal.py`, and `distill_apply_disposal.py` respectively. Cite these op names
alongside the phase-numbered description above; the phase numbering and the op names refer to
the same flow, not two competing mechanisms.

0. **Pre-check:** If `git status` shows uncommitted changes outside wiki and artifact directories, warn PM and offer to commit those separately first — keeps the safety checkpoint scoped to distillation.
1. **Safety commit:**

   ```bash
   CLAUDE_INVOKING_COMMAND=distillation "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" --blanket "pre-distillation checkpoint"
   ```

2. **Split apply work across N Sonnet apply-agents, sized by volume (parallel where possible).**

   Single-agent application has timed out at ~50 min / ~170 tool-uses on large runs (e.g., the 2026-04-26 run). The coordinator MUST decompose the apply work into independent slices and dispatch a Sonnet apply-agent per slice. The coordinator orchestrates and verifies; it does not type the edits itself.

   Each Apply-Agent receives the relevant slice of the union of Phase 2 `dispositions:` manifests + Phase 3b/3d manifests as its **input contract**. The done-condition for each agent is a manifest-driven file-path set-diff (see step 3).

   **Slicing is volume-based, not function-based. The function split below (topic-deltas / bookkeeping / leftovers) is the role taxonomy, NOT the agent count.** The topic-delta role (A) scales with run size and MUST shard; the bookkeeping role (B) does not. Wiki files are file-disjoint, so topic deltas are trivially fan-outable — there is no reason to serialize them behind one process. Sizing the slate:

   - **Count the topic-guide targets** = (existing guides with a Phase 2 scratch file) + (new guides). This is the A-role volume.
   - **Small run (A-volume ≤ 4 guides):** combine into 1-2 agents total — one Apply-Agent A (all topic deltas + leftover guides/decision records) plus Apply-Agent B (bookkeeping). The function split collapses cleanly at this size.
   - **Large run (A-volume ≥ 5 guides):** **shard the A-role across ⌈A-volume / 3⌉ apply-agents**, each owning a disjoint group of ~2-3 guides (same per-executor scope discipline as Phase 1 batching — ~5-10 min per agent, 15 min hard ceiling). Dispatch the A-shards in parallel; Apply-Agent B (bookkeeping) runs alongside them. Decision records and any leftover low-volume guides fold into the smallest A-shard or a dedicated final shard — they do not get their own serialized "Agent C".

   > **Anti-pattern — the monolithic Apply-Agent A.** On a large run (14 guides, ~67 deltas, 3 new guides) the function-based template put ALL topic deltas in one Apply-Agent A while B and C each had a ~15-min job; A ran 20+ min in one process. Function-based slicing is fine for small runs and actively harmful for large ones. Slice by volume.

   Roles:

   - **Apply-Agent A (one per guide-group on large runs) — Topic-guide deltas:** For each existing guide in the assigned group with a Phase 2 scratch file, read the delta operations (ADD_SECTION / UPDATE_SECTION / REMOVE_SECTION) and apply them mechanically. For new guides in the group, write the full content from the Phase 2 scratch file. Output: list of guide files touched. Done-condition: every target file path in this agent's assigned `dispositions:` entries appears in `git diff --stat`.
   - **Apply-Agent B — Gotchas distribution + bookkeeping (single agent, does not shard):** Apply cross-cutting nuggets (gotchas, lessons, cross-references) flagged by Phase 3a/3b, then update `docs/wiki/DIRECTORY_GUIDE.md` (using Phase 3c preview as source) and `docs/README.md` (add new guides to the Wikis and Guides table; add promoted research to the Research section; mark archived specs; bump footer timestamp). Output: list of bookkeeping files touched. Done-condition: every target file path in B's assigned manifest entries appears in `git diff --stat`. **Sequencing:** B's DIRECTORY_GUIDE/README bookkeeping reads the set of new/updated guides — it may run concurrently with the A-shards (it reads the manifest, not the applied files), but if any A-shard is re-dispatched in step 3, re-confirm B captured every new guide.

   Apply-agents must use Read, Write, Edit only — no further dispatch. Every A-shard prompt names the other shards' guide groups as out-of-scope (file-disjoint, no overlap).

3. **Verify apply-agent output via manifest-driven file-path set-diff.** Apply-agents under-count their own work in chat (observed on 2026-04-26). After all apply-agents return, run `git diff --stat docs/wiki/ docs/decisions/ docs/README.md` and compare the **set of FILE PATHS** in each agent's assigned manifest against the **set of FILE PATHS** in `git diff --stat`. Multiple operations on the same file collapse to one entry on both sides of the comparison. Non-empty set-diff (manifest paths not in diff) → re-dispatch that agent with the unfinished operation list. Section-level correctness of applied edits remains the Apply-Agent's responsibility and is not verified by this gate.

4. **Commit additions:** `"distill: add/update N guides, N decision records"`

5. **Delete approved artifacts — `.md`-only filter is MANDATORY.**

   **Retired: fanout assembly sentinel (AC17).** A prior revision gated this step on a
   pre-deletion sentinel for Workflow-fanout mode (`N > 500` candidates) — verifying a
   per-cluster-assembled canonical manifest existed before deletion could proceed. Retired
   alongside the tiered scope-gate it depended on: the background Workflow is
   now the vehicle unconditionally, so there is no separate fanout-vs-single-Sonnet mode for a
   sentinel to distinguish.

   `git rm -r tasks/<feature-dir>/` is **forbidden**. Recursive directory removal sweeps up co-located non-markdown research corpora (e.g., the 2026-04-26 run swept 525 non-md files from a `.next/`/asar corpus shared with a distill target) and violates the "research provenance is always retained" rule.

   Required procedure for each deletion-manifest entry:
   - Build the deletion list as **`*.md` only** — no recursive directory globs.
   - Per directory entry: `git ls-files '<dir>/*.md' '<dir>/**/*.md'` then `git rm` only those.
   - **YAML-manifest consumption (mandatory).** The Phase 3d deletion manifest emits a `deletions:` YAML block (`agent-prompts/phase-3d.md` schema). Extract artifact paths from the `artifact_path:` field of each entry — do NOT use `awk -F'|'` column-extraction on prose Markdown tables. YAML consumption avoids format-drift parsing failures. Entries with `disposition: DELETE` are eligible; `SEND_BACK`, `BLOCKED`, and `PRESERVE` entries are excluded. See `snippets/deletion-list-hygiene.md` for hygiene guards.
   - **`deletion_groups:` expansion (schema_version: 2).** After consuming all `deletions:` rows, check for a sibling `deletion_groups:` list. For each group entry: read the file at `scout_source:`, locate the H2 heading that exactly matches `section_anchor:`, read the first fenced YAML block occurring after that H2 heading and before the next H2 heading (or EOF), and consume the `artifact_paths:` list from that YAML block. Assert `len(artifact_paths) == count` and abort on mismatch (do not silently accept a mismatched expansion). Each path from `artifact_paths:` becomes a synthetic `deletions:` row with `disposition: DELETE` and `reason:` inherited from the group's `reason:` field. The expanded synthetic rows are subject to the `.md`-only audit guard — non-`.md` paths in `artifact_paths:` are silently excluded from the deletion set and appended to `state/distillation-log.md` `## Manual Review` section with disposition `EXCLUDED-NON-MD`. Schema_version: 1 manifests (no `deletion_groups:` key) are consumed as flat `deletions:`-only without error — backward-compat invariant. (AC4, AC8, AC15)
   - **`cross_repo_dispositions:` expansion (Cross-Repo Archive Specialist Branch).** When the run included the Cross-Repo Archive Specialist Branch, `agent-prompts/phase-3d-specialist-assembler.md` already folded the specialist's `ROUTINE`-classified entries into the `deletions:` block at Phase 3d assembly time (see Phase 3d § produces above) — Phase 5 does not re-read the specialist scratch file directly. Phase 5's only obligation here is exclusion-set integrity: confirm no `deletions:` row's `artifact_path:` matches a path in the assembler's own `excluded_memo_paths:` list (sourced from `COMMITMENT_OPEN`-classified entries in the specialist's scratch file(s); cross-check by path). If a match is found, treat it as a manifest-assembly error — halt and surface to PM rather than deleting a memo with an open sibling commitment.
   - **Pre-commit audit gate:** `git status --porcelain | awk '$1=="D"' | grep -v '\.md$'` MUST return empty. If it returns ANY paths, abort the deletion commit, restore the unintended deletions (`git restore --staged --worktree <path>`), and report to PM. Non-`.md` deletions are never silently accepted, even if the deletion manifest names them.
   - Research outputs (`docs/research/`, `~/docs/research/`), NotebookLM artifacts (`*-claims.json`, `*-summary.md`, anything under `tasks/notebooklm-*/`), and Pipeline C structured outputs are **never deleted** by `/distill` regardless of manifest contents — these were marked PRESERVE/PROMOTE at Phase 0 and are corpus, not debris.

6. **Commit deletions:** `"distill: remove N distilled artifacts"`

7. **Update distillation log:** append all processed artifacts **with individual file paths and dispositions** to the SINGLE canonical log at `state/distillation-log.md` (schema-of-record: `coordinator/schemas/distillation-log.schema.md`) — this is the idempotency mechanism for subsequent runs. Canonical row shape: `- <path> -> <disposition>, <fate> (run: <run-id>)`, ASCII `->` (never the U+2192 `→` glyph), `disposition` ∈ `{DISTILLED, PROMOTE, EPHEMERAL, SKIP, PRESERVE}`, grouped under a `## Run <run-id>` header. Per-file entries are required — directory-level summaries are insufficient for Phase 0 exclusion matching.

   **[claude-klabauter-reliant] Append through `bin/distill-log-append.py`, not a hand-rolled string append.** Per the C8 contract (`docs/contracts/distill-engine-scripts.md` § 6), every append to the canonical log goes through claude-klabauter's canonical-log WRITER so the on-disk format can never drift: `python3 bin/distill-log-append.py --log-path state/distillation-log.md --path <artifact-path> --disposition <DISTILLED|PROMOTE|EPHEMERAL|SKIP|PRESERVE> --fate "<free-text fate>" --run-id <run-id>`, once per artifact. The tool emits `{"row": ..., "header_opened": <bool>, "log_path": ...}` on success (exit 0) or `{"error": ...}` on exit 1 (invalid disposition or empty field) — a non-zero exit means NO row was written; do not treat it as a soft warning.

   **For a multi-row run, PREFER claude-klabauter's bulk mode over N single-row invocations.** `bin/distill-log-append.py --batch <file|->` accepts a JSONL stream of `{path, disposition, fate, run_id}` objects, validates every row against the schema-of-record BEFORE writing any of them, and only then writes the whole batch atomically — one bad row fails the entire batch loud rather than landing a partial log. Reach for `--batch` whenever a run is disposing of more than a handful of artifacts; the single-row form above remains correct for a one-or-two-artifact run.

   **Agentic-path fallback if claude-klabauter declines / both the script and `--batch` are unavailable:** hand-appending is degraded (drift-prone), not broken — but it MUST still conform exactly to the schema-of-record (`coordinator/schemas/distillation-log.schema.md`), not an improvised shape:
   - **Row shape is exactly** `- <path> -> <disposition>, <fate> (run: <run-id>)` — `<run-id>` belongs in the trailing `(run: ...)` parenthetical and NOWHERE else; a `last_sha` or any other provenance detail belongs in the `<fate>` prose fragment, never smuggled into the `(run: ...)` parenthetical alongside or instead of the run id.
   - **`<disposition>` MUST be one of the five enum values** `DISTILLED`, `PROMOTE`, `EPHEMERAL`, `SKIP`, `PRESERVE` — verbatim, exact case. Do NOT improvise a sixth value (e.g. an ad-hoc `DELETED` token): two recent claude-klabauter runs hand-appended 195 rows using `DELETED`, which is not in the enum and is invisible to every reader that parses against the schema-of-record. The ratified mapping treats an improvised `DELETED` action as canonical `EPHEMERAL` — use `EPHEMERAL` directly rather than reintroducing the non-canonical token.
   - Never the legacy `docs/wiki/.distill-log.md` path, never the Unicode `→` glyph (ASCII `->` only, per the schema-of-record's single most load-bearing detail).

8. **Amend log update** into the deletion commit

9. **Clean scratch:** `rm -rf state/scratch/artifact-distillation/{run-id}/`

10. **Reap integrated review-findings sidecars:**

    ```bash
    "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/reap-integrated-review-findings"
    ```

    **This is a targeted, named, post-integration reap of one artifact class — NOT a `state/review-trail/` directory purge.** It `git rm`'s only the `state/review-trail/findings/*.md` sidecars carrying a `## Integrator Dispositions` block (i.e., a review-integrator has already folded their findings into a plan — the sidecar has served its purpose and history is preserved via `git rm`, not `rm -rf`). Sidecars without that marker are untouched. Runs after the deletion commit (step 6) so it composes with the same commit discipline; supports `--dry-run` for a preview. This does not contradict `state/`'s never-swept-by-`/distill` posture: the posture protects live substrate, and a sidecar whose findings have already been folded into a plan is spent, not live.

11. **Reap stale subagent sidecars:**

    ```bash
    "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/reap-stale-subagent-sidecars"
    ```

    Named exception: `state/subagent-share/<session-id>/*.md` sidecars of every identity-typed kind — review findings, staff-eng-review, assessment, run-report — are reapable, and nothing else under `state/` is. DR-091 made this the one home for every provisioned subagent sidecar, which is why step 10's reaper is not enough on its own: step 10 covers the RETIRED home (`state/review-trail/findings/`), and a run that fires only step 10 leaves the live home accumulating indefinitely, which is the exact gap `docs/plans/2026-07-24-reviewer-sidecar-provisioning-reconciliation.md` C7 built this op to close.

    **The gate is session liveness AND/OR an age floor, never `status:` in isolation.** `status: complete` means the executor finished WRITING; it does not mean the requesting lead has READ it, and a sidecar reaped between those two moments destroys the only copy of a verdict someone is still waiting on. A `status: blocked`/`thrashing` carve-out only ever SUBTRACTS from the reapable set. Building a `status:`-only or mtime-only sweep as a cheaper substitute is **out of scope and MUST NOT** be done — the op ships and is named here precisely so nobody re-derives one inline.

    Same commit discipline and `--dry-run` support as step 10. The doctrine of record is `docs/wiki/state-placement-law.md` § the `state/subagent-share/` row, which ratifies this call site alongside `/update-docs`' sweep step 11j, a `/workweek-complete` step, and on-demand invocation.

**Two separate commits** (additions vs deletions) so wiki content survives even if deletion needs reverting.

**If `--no-delete`:** skip steps 5-8, 10 and 11, only apply wiki updates (steps 0-4).

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
| Partial 3a completion (k of N cluster agents complete, others fail/time out) | The Workflow's `parallel()` dispatch continues past a single agent's failure; the failed cluster is named in the run log and excluded from `contradictionResults` rather than targeted-re-dispatched — `resumeFromRunId` (re-invoke the same script) is the recovery mechanism, not a per-cluster re-dispatch. |
| Opus escalation auto-dispatches but Opus fails or times out | The Workflow logs the gap and surfaces it in the returned `opus_escalation` object rather than proceeding silently. PM decides at Phase 4 whether to accept output without contradiction resolution or request a re-run. |
| 3b dedup produces an empty DR set despite non-empty `CREATE_DR` input | Always a pipeline inconsistency — not a valid empty outcome. The Workflow surfaces `failure: true` + `failure_detail` on `phase_3b_dr_dedup` for the Phase 4 PM gate to weigh rather than halting the run. When there is nothing DR-shaped at all (zero `CREATE_DR` dispositions and zero judgment new-entry proposals), the Workflow skips the dispatch and records the same failure shape without an agent call. |
| Single-topic cluster in 3a (only one topic, no within-cluster pairwise comparison possible) | The Workflow folds in a zero-contradiction result directly rather than dispatching an agent for that cluster. The cross-cluster check still applies to single-topic clusters. |
| Artifacts distilled twice | Distillation log (`state/distillation-log.md`, schema-of-record: `coordinator/schemas/distillation-log.schema.md`) excludes already-processed artifacts at Phase 0 |
| Distillation log absent, silently treated as "nothing harvested yet" — manufactures a false-positive harvest-debt list covering the whole `archive/specs/` tree | FAIL LOUD when the log is absent — never harvest-everything on a missing log (finding #1 correctness hazard). `bin/distill-harvest-debt.py` (C8 § 2) enforces this by exiting non-zero with a stderr error; the agentic fallback path must replicate the same fail-loud behavior. |
| PM skips approval and deletion runs | "Wait for explicit approval" is unconditional — no timeout, no auto-proceed |
| Scratch file missing after agent completes | Verify with `ls`; re-dispatch once; skip batch on second failure — don't stall the pipeline |
| Phase 5 single apply-agent times out (~50min/170 tool-uses on large runs) | Phase 5 step 2 splits work across N Sonnet apply-agents sized **by volume, not function**: shard the topic-delta role into ⌈guide-count/3⌉ agents (~2-3 guides each, ~5-10 min) on large runs (≥5 guides); coordinator orchestrates, never types edits itself |
| Phase 5 monolithic Apply-Agent A — function-based slicing puts ALL topic deltas in one process (14 guides in one agent, 20+ min) | Phase 5 step 2: A-role shards by guide-count; function split is role taxonomy, not agent count; wiki files are file-disjoint so deltas fan out freely |
| Apply-agents under-count their own work in chat | Phase 5 step 3: verify with `git diff --stat`, treat the diff as ground truth, re-dispatch on missing changes |
| `git rm -r tasks/<dir>/` sweeps up co-located research corpora (asar, `.next/`, datasets) | Phase 5 step 5: `.md`-only deletion lists; pre-commit audit `git status --porcelain \| awk '$1=="D"' \| grep -v '\.md$'` must be empty; PRESERVE/PROMOTE corpora never deleted regardless of manifest |
| Phase 3d 32K output cap on per-file rows at N>~100 source artifacts — a single Sonnet agent's schema-forced structured return is O(N) rows and can trip the cap before it returns | The retired agentic path, kept only as a manual fallback at that scale, still uses the grouped-by-reference shape (`deletion_groups:` sibling key, `agent-prompts/phase-3d.md` § Output-budget self-check) at that scale. The Workflow-folded phase (§ Phase 3d above) returns a flat `deletions:` array only — a corpus large enough to trip the output cap on this vehicle is a known limitation of the current fold, not yet ported to a grouped shape; a run at that scale should watch for a truncated/failed 3d agent result and fall back to the agentic path if it occurs. |
| *(Retired)* Phase 3d fanout fragments exist but canonical manifest was never assembled — Phase 5 reads fragments directly and over-counts or skips rows | This failure mode applied only to the now-retired N>500 fanout tier and its Phase 5 sentinel (AC17, retired) — the background Workflow being the unconditional vehicle removes the fragment/canonical-manifest split this row guarded against. |

---

## Acceptance Criteria

<!-- ACs not listed here are scoped to agent-prompts (AC1-AC3), commands/distill.md (AC9), sibling plans (AC10), or test fixtures (AC11-AC14). This table covers PIPELINE.md-hosted ACs only.
     This is a closed historical delivery ledger for this pipeline's own build — every row below
     is `met` or `retired`, not a live template. `## Acceptance Criteria` is retired as a
     plan-authoring shape: a criterion that must be discharged is now a `## Tasks` spine row, not
     a table row. Do not reproduce this row family in a new plan or pipeline doc. -->

| ID | Criterion | Status |
|----|-----------|--------|
| AC4 | `PIPELINE.md` § Phase 5 documents `deletion_groups:` expansion logic — Read `scout_source:`, locate `section_anchor:` heading, consume the fenced YAML block immediately under it, iterate `artifact_paths:` list. Verify: `deletion_groups` appears in this file's Phase 5 § context. | met |
| ~~AC5~~ | **RETIRED.** Formerly: `PIPELINE.md` § Phase 0 carries a scope-gate row triggering Workflow-fanout-per-cluster mode at `N > 500` deletion-eligible candidates. The background Workflow is now the vehicle unconditionally (no size gate), so the single-Sonnet-vs-fanout mode distinction this AC tested no longer exists. | retired |
| AC8 | Phase 5 implementation honors the new schema — `deletion_groups:` rows are expanded via scout-file YAML-block read (not glob or Markdown parse); `.md`-only audit guard still applies. Verify: cited at PIPELINE.md § Phase 5 step 5 `deletion_groups:` expansion. | met |
| AC15 | Phase 5 consuming a `schema_version: 1` Phase 3d manifest (only `deletions:`, no `deletion_groups:`) succeeds — backward-compat invariant. Schema v1 parses as flat deletions-only under v2 consumer without error. Verify: covered by `coordinator/tests/test_artifact_distillation_phase3d_fixtures.py::TestFixture4SchemaVersion1Backcompat::test_ac15_schema_v1_backcompat`. | met |
| AC16 | Phase 1 scout output includes a fenced YAML block with `artifact_paths:` list under each group section heading (EPHEMERAL / ALREADY_CAPTURED cluster sections), per § Phase 1 Scout Output Schema above. Verify: `artifact_paths:` appears in `agent-prompts/phase-1.md` (or phase-1-5.md / clustering.md — verified by C0 executor). | met |
| ~~AC17~~ | **RETIRED.** Formerly: fanout partial-completion sentinel in Phase 5 step 5, guarding the now-retired N>500 fanout tier. Removed alongside the sentinel and the scope-gate it depended on (AC5). | retired |
