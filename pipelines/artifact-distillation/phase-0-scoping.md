Part of [`PIPELINE.md`](PIPELINE.md); phases still run in its strict sequence.

## Phase 0: Scoping (Coordinator, ~5 min)

**Native op backing this phase:** the harvest-debt set, ripeness partition, memo cohort,
`wikiDirs`/`wikiSlugs` index, and batching computed by steps 1-6 below are the same outputs
emitted as one JSON payload by the engine repo's `distill.scope` op (`coordinator_core/ops/distill_scope.py`,
`@register_op("distill.scope")`) — cite this op, not the retired per-script names, when pointing at
"what computes Phase 0's Workflow INPUT". The individual `bin/distill-*.py` CLIs cited below remain
valid as the C8-contract entrypoints `distill.scope` is built from.

1. **Inventory artifact directories:** `plans/`, `docs/completed-work/`, completed `tasks/*/` dirs, `docs/research/`, `~/docs/research/`, `docs/superpowers/specs/`, `tasks/*/spec.md`, `tasks/*/design.md`. **`cross-repo/archive/` (closed `status: actioned` memos) is EXCLUDED from this generic candidate list** — it is routed to the dedicated Cross-Repo Archive Specialist Branch (§ below) instead, not scanned by the generic Haiku/Sonnet path. See `commands/distill.md` § Cross-repo archive distillation for the input-enumeration detail. **`archive/handoffs/` is EXCLUDED from every distillation cohort** — handoffs are not a knowledge source and carry no distill fate; the whole archive gets the bounded outlier scan (§ Handoff outlier scan below) and never a scan batch, a harvest, or a deletion row. **`archive/daily-summaries/` is a read-only intake path**, not a member of this candidate list — it is consumed by `/workday-complete` and `update-docs.md`'s doc surfaces, accrues no harvest debt, and is never scanned, harvested, or deleted by this pipeline; see `coordinator/docs/wiki/ceremony-calibration/daily-summary-procedure.md`.

   **`archive/completed/` is a first-class harvest cohort**, supplied to `distill.scope` as an explicit `cohort_specs` list (a supplied list replaces the engine default), copied from `PM_RULING_2026_08_06_COHORT_SPECS` and never passed as the string form:
   `{"name": "memos", "glob": "cross-repo/archive/**/*.md", "filter": "memo_distill_fate_promote", "mode": "harvest"}`, `{"name": "completed", "glob": "archive/completed/**/*.md", "filter": null, "mode": "harvest"}`. There is no `handoffs` row (handoffs are not a cohort, above) and no `week_changelog` row (its source is not yet in the target set). Completion records are harvest inputs only — never deleted, trimmed, or moved (`commands/distill.md` § Delete safety).

   **Plan files are the priority cohort.** Terminal plans already swept to `archive/specs/` by the session-init sweep (enumerated via `bin/query-records --type plan --format paths --root archive/specs/`, minus any paths already recorded in `state/distillation-log.md` under a `DISTILLED`/`PROMOTE` disposition — the un-harvested set = "harvest debt") are the highest-yield distillation source (`commands/distill.md:20-21`) and carry the heaviest Phase 5 sub-step (knowledge-harvest). They are processed **first** and banked before ephemera disposal — see the harvest-debt drain contract in Phase 5 and `commands/distill.md § Phase 5`.

   **[engine-reliant] Pre-filter process-scaffolding sidecar files via `bin/distill-sidecar-sweep.py`,
   not LLM eyeballing.** Per the C8 contract (`docs/contracts/distill-engine-scripts.md` § 4):
   `bin/distill-sidecar-sweep.py --scan-root <inventory-root> --repo-root <repo-root>` emits
   `{"deletion_manifest": [{"path"}], "retained": [{"path", "reason": "active-reference"}]}` —
   sidecar-suffix candidates (the `SIDECAR_SUFFIXES` set, plus timestamped variants) that have
   already cleared the shared active-reference guard land in `deletion_manifest`; still-referenced
   candidates land in `retained` and are excluded from the deletion set entirely. Run this over
   each inventoried directory before batching for Phase 1: `deletion_manifest` entries are folded
   straight into the run's EPHEMERAL disposition set (skip a Haiku scan for them — the guard
   already cleared them mechanically), `retained` entries stay in the normal candidate list for
   Phase 1/1.5 to classify on their merits. This replaces an LLM manually enumerating sidecar
   files by eye and grepping each for active references before proposing deletion. **Fail-loud on
   malformed op output:** if `deletion_manifest`/`retained` is missing from stdout, treat the
   script as unavailable and fall back to the prior manual-grep path for that directory — do not
   guess at a partial result. **Agentic-path fallback if the engine repo declines / the script is
   unavailable:** revert to an LLM enumerating sidecar files by eye and manually checking each for
   active references — degraded (fragile, ordering-invariant risk on proposing deletion before
   confirming no active reference), not broken.

   **[engine-reliant] Compute the un-harvested set via `bin/distill-harvest-debt.py`, not LLM
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
   the Phase 0 output. **Agentic-path fallback if the engine repo declines / the script is
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

   **[engine-reliant] Frontmatter `status:` partition via `bin/distill-ripe-filter.py`.** Per
   the C8 contract (`docs/contracts/distill-engine-scripts.md` § 3): `bin/distill-ripe-filter.py
   <archive/specs-dir>` emits `{"harvest": [...RIPE paths], "skip": [{"path", "status",
   "reason"}, ...]}` on stdout — a pure frontmatter `status:` scan, no LLM. This mechanically
   produces the `status: implemented`/`status: shipped` half of the RIPE/PARTIAL/ABANDONED
   split below (`harvest` entries are RIPE-by-status; every `skip` row's `reason` names the
   actual status found). **The script does NOT verify AC pass-at-HEAD** — that half of the
   RIPE gate (Oracle DELIVERED+REVIEWED / DELIVERED-UNREVIEWED tie-break) stays the
   `plan-delivery-audit` judgment layer's job on top of the script's `harvest` set; the script
   narrows the candidate set the AC-verification judgment runs over, it does not replace that
   judgment. **Agentic-path fallback if the engine repo declines / the script is unavailable:** revert
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
