---
name: distill
description: "Distill session artifacts to wiki and decisions; archive specs, drop scratch."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--dry-run] [--no-delete] [--min-convergence=N] [path]"
---

# Distill — Artifact Distillation Pipeline

Extract knowledge from accumulated session artifacts into evergreen wiki documents. Trim and archive canonical specs; delete scaffolding; write or update wiki entries. The archive is the long-term record; the wiki is the navigable present.

**Scope discipline — record-keeping, not cleanup.** `/distill` exists to capture the *shape* of what shipped, was decided, or happened, and canonicalize it into wiki form for future prior-art-checkers (any agent may consume). Concision and trimming serve **clarity**, not cleanliness — `/distill` is NOT a disposal route for trash the EM didn't delete at workstream-complete time. Three disposal mechanisms are distinct and non-substitutable:

- **Layer 1 (mechanical, age-gated)** — `bin/cruft-sweep` (name + age + fingerprint anchors).
- **Layer 2 (on-demand judgment scan)** — `/cruft-sweep` skill (registry-diff + confirm-needed names).
- **Layer 3 (front-line judgment, fresh context)** — EM self-clean at `/workstream-complete`'s `scratch-disposition-per-file` judgment point (this session's transient scratch the EM authored — runs first in lifecycle order, before Layers 1 and 2 ever see the residue).

`/distill` and `/update-docs` are NOT a substitute for any of those layers — they extract knowledge and index canonical artifacts.

**Plan files are a high-value distillation source alongside wiki entries and archived handoffs.** Terminal plan documents are moved to `archive/specs/` by the session-init sweep; `/distill` reads them from there as harvest debt. Plans — especially those with `(was: <plan-forecast>)` ALLOWLIST corrections from `/workstream-complete`'s `plan-vs-reality-reconcile` judgment point (and, on historical plans, `## Deviations` audit tables) — carry the shipped-vs-forecast reality that future prior-art-checkers consume. The four-fate table below describes the plan cohort as sourced from `archive/specs/` (already relocated by the sweep); the table treats plans as one of four equal categories, but plans + divergence corrections are the source future prior-art-checkers will read most often.

**Four categories, four fates:**

| Artifact | Fate | Rationale |
|---|---|---|
| Canonical plan / spec (`archive/specs/**/*.md`) — **RIPE only** | **Harvest knowledge → record in distill-log** | The session-init sweep already moved terminal plans (`status: implemented`/`superseded`/`abandoned`) from `docs/plans/` to `archive/specs/YYYY-MM/`. `/distill` reads the un-harvested subset (plans in `archive/specs/` minus paths already logged as `DISTILLED`/`PROMOTE` in `state/distillation-log.md` — the "harvest debt") and extracts knowledge into wiki/DR. **Only RIPE (delivered) plans are harvested** — ripeness classified by the `plan-delivery-audit` Oracle (`skills/plan-delivery-audit/SKILL.md:128-136`): `status: implemented`/`shipped` + ACs-pass-at-HEAD → RIPE. PARTIAL and ABANDONED plans are SKIP (un-harvested, retained in `archive/specs/`); IN-FLIGHT plans are not in this cohort (they stay in `docs/plans/`, not yet swept) — see `PIPELINE.md` § Phase 0 ripeness gate. |
| Enriched stubs, reviewer outputs, integrator triage, docs-checker reports | **Delete** | Pure scaffolding. Recoverable from git via distillation log. |
| Wiki entries (`docs/wiki/*.md`) | **Write/update** | What-and-why summary. Carries provenance frontmatter. |
| Archived handoffs (`archive/handoffs/*.md`) | **Resolved/shipped → Extract → delete (opt-out via `--no-delete`). Unresolved / continued / closed / missing-`shipped_in:` → Retain un-harvested (SKIP).** | Post-`/pickup` paper trail. Extract-eligible only when `status: claimed` (dual-read: legacy `consumed`) AND `shipped_in:` present AND `deployment_state` is NOT a non-shipping terminal (`continued` or `closed`); handoffs whose `deployment_state` is `continued` (succeeded by a later handoff) or `closed` (deliberately stopped, `closed_reason:`), or that are missing `shipped_in:`, are retained un-harvested, not extracted or deleted. Harvest gate composes with (and is stricter than) the Phase 5 delete-guard #2 (`shipped_in:` required for deletion) — it gates *harvest*, not just deletion. See § Handoff distillation below. |

**Reference:** Full pipeline design in `${CLAUDE_PLUGIN_ROOT}/pipelines/artifact-distillation/PIPELINE.md`. Agent prompt templates in `agent-prompts/` (per-phase fragments); thin index at `agent-prompts.md`.

**Out-of-scope actions for all dispatched agents in this pipeline:** DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find yourself reaching for a merge, STOP and surface the question to the EM in your final reply. The EM merges via `/merge-to-main`; distill agents do not.

**Announce at start:** "I'm running `/distill` to extract knowledge from [N artifacts / artifacts in path] into wiki documents."

**For bulk pruning without knowledge extraction:** that lives in `/update-docs` Phase 8b (`pipelines/update-docs/artifact-pruning.md`) — runs unconditionally on every `/update-docs` invocation under conservative thresholds. `/distill` extracts knowledge into wiki *before* the source material gets pruned. Use `/distill` when you want the knowledge before discarding the source; rely on `/update-docs` Phase 8b for the raw cleanup.

---

## Arguments

`$ARGUMENTS` may include any combination of:

**`--dry-run`**
Run Phases 0-3d only. Preview extraction results and the deletion manifest, but apply nothing to disk. Presents the summary at the Phase 4 deletion gate and stops. Use to verify what would be deleted before approving disposal — the additive wiki/DR writes are not gated by this flag; they land direct at Phase 5 on any real (non-dry-run) invocation.

**`--no-delete`**
Apply wiki updates (Phases 0-5 write steps), but skip scaffolding deletion AND skip trimming specs in `archive/specs/` (specs already moved there by the session-init sweep remain un-trimmed), including the review-findings sidecar reap (§ Phase 5 step 10). Wiki writes still apply — this flag only suppresses the disposal tier, not the additive/harvest tier.

**`--allow-drop`**
Bypass the negative-AC halt for this run after EM eyeballs the diff and confirms no semantic loss. Logs the bypass to distillation-log.md Manual Review section for audit.

**`--min-convergence=N`**
Override the Phase 2.5 convergence threshold for this run. Default `N=3` (matches the "wait for instance #3 before extracting a pattern" rule in coordinator doctrine). Lower values are useful when bootstrapping against a thin sidecar corpus — raise back to 3 once the corpus matures. Phase 2.5 emits a judgment proposal only when a finding cluster reaches `convergence_count >= N` across distinct plans.

**`[path]`**
Scope the inventory to a specific subdirectory. Only artifacts under that path are processed. Example: `/distill tasks/camera-refactor/` distills a single feature directory.

### Examples

```
/distill                          # full repo distillation
/distill --dry-run                # preview only, no writes
/distill --no-delete              # extract wiki content, keep source files in place
/distill tasks/camera-refactor/   # scope to a single feature dir
/distill --dry-run plans/         # preview what would be extracted from plans/
/distill --min-convergence=2      # bootstrap mode for thin corpus; lower threshold for early judgment entries
```

---

## Phase Overview

Full phase definitions, dispatch instructions, scratch path conventions, and failure modes are in `PIPELINE.md`. This is a summary for orientation.

**The background `Workflow` is the vehicle, unconditionally — no size gate.** Every `/distill` run — one artifact or one thousand — dispatches through the background `Workflow` described in `PIPELINE.md` (script: `pipelines/artifact-distillation/distill-harvest.workflow.js`), invoked TWICE (one script, not two files — see § Phase 0/1 — Curation Split below): **Invocation A** runs Wave 1 Haiku ×N scan (journaled/cached, forced-schema nugget return), source normalization, and the join-integrity gate, then returns early with a per-tag census. The EM runs the curation engine's `distill.curate_clusters` op over that census out-of-band, then re-invokes the SAME script as **Invocation B** with the curated verdict map — the scan wave and source normalization REPLAY from the Workflow runtime's cache rather than re-dispatching (empirically probe-confirmed; see the plan's "## Probe: single-script resume-replay"), and the run proceeds through curated clustering (free join, no dispatch) into Wave 2 Sonnet one-agent-owns-one-topic synthesis with direct additive writes, concurrency-capped at `min(16, cores-2)`, with built-in rate-limit retry and `resumeFromRunId` re-run of only the failed synths. There is no manual small-batch fallback path and no artifact-count threshold that flips dispatch mode — the tiered scope-gate that used to exist here (single-Sonnet lightweight/standard/full-pipeline modes keyed to NEW-artifact count) is retired; the Workflow's own resume/retry machinery is what used to require a size split, and it no longer does.

**Curation policy is the curation engine's; homing is ours.** Between invocation A and B, the `distill.curate_clusters` op decides per-tag whether a raw tag survives as a real topic (keep), folds into another tag (normalize/merge), or is discarded (drop) — this repo ports no verdict logic of its own. Before clustering runs in invocation B, a homing override restores to `keep` (own key) any tag whose slug already matches an existing wiki file — an existing home on our disk outranks a shape verdict made without seeing our wiki tree. The curation op decides whether a tag is a real TOPIC; this repo decides whether that tag already has a HOME. There is no misc bucket: every surviving homeless cluster earns its own new wiki file unconditionally, because curation already decided upstream which tags survive at all.

**The PM gate moves to deletions only.** Additive knowledge writes — wiki entries, decision records, `DIRECTORY_GUIDE.md` updates, distillation-log rows — are **direct-to-disk**: provenance-stamped (§ 5b/§ 5c) and git-reversible, they do not wait on PM sign-off. The Phase 4 gate that used to block on "deletion manifest + DIRECTORY_GUIDE.md preview" now blocks on the **deletion manifest alone** — the DIRECTORY_GUIDE.md preview is informational context accompanying the gate, not a co-equal approval item. Nothing the pipeline can't cheaply reverse via `git revert` requires a live PM turn; the one irreversible-in-spirit action (removing scaffolding/handoffs/memos from the working tree) is exactly the one still gated.

```
Phase 0 (Coordinator) → Workflow Invocation A (Wave 1 Haiku ×N scan, journaled/cached; source
  normalization; join-integrity gate) → early return {tag_counts, recommended_keep_threshold,
  recommended_keep_threshold_reason, join_integrity, failed_batch_ids, run_id, resume_hint}
  → [Coordinator: run curation op over tag_counts with keep_threshold=recommended_keep_threshold,
  out-of-band]
  → Workflow Invocation B (SAME script, resumeFromRunId — scan wave + source normalization
  REPLAY from cache) → [Homing override, then curated clustering, coordinator-side, free join —
  every homeless cluster earns its own new file, no misc bucket] → Wave 2 (Sonnet,
  one-agent-owns-one-topic, additive+provenance direct write) → [Coverage gate, in-Workflow JS,
  mechanical set-diff — gap re-synth (Sonnet) only for uncovered nuggets] → Phase 2.5 (Sonnet ×K, parallel)
  → Phase 3a (Sonnet ×C, parallel by cluster) → [cross-cluster-check] → [Esc: Opus + fidelity-check (Sonnet), if needed]
  → Phase 3b (Sonnet, single) → Phase 3c (Coordinator, mechanical) → Phase 3d (Sonnet, single)
  → Phase 4 (PM gate — DELETIONS ONLY) → Phase 5 (Coordinator, drain harvest debt + delete scaffolding)

Cross-Repo Archive Specialist Branch (Sonnet ×1 or ×N shards, parallel to Wave 1)
  processes cross-repo/archive/*.md (closed status: actioned memos) — excluded from the
  generic Phase 0 candidate list, converges with the main pipeline at Phase 3c/3d.
```

| Phase | Model | Purpose |
|-------|-------|---------|
| **Phase 0** | Coordinator | Inventory artifacts, catalog formats, group into batches, generate run ID; dispatch **Invocation A** of the background Workflow (no scope-gate branching — every run takes this path). **Wiki inventory (see § Phase 0 — Wiki Inventory below):** enumerate EVERY wiki tree present, build `wikiSlugs`/`wikiDirs`, pass both into the Workflow INPUT and the scan brief. **Phase 0 does NOT curate** — curation happens between Invocation A and B, below. |
| **Wave 1 (Workflow, Invocation A)** | Haiku (parallel, journaled) | Scan each batch — extract knowledge nuggets (`[DECISION]`, `[KNOWLEDGE]`, `[EPHEMERAL]`, `[AMBIGUOUS]`) via forced-schema return; cached so replay in Invocation B costs nothing. Invocation A returns early after the join-integrity gate with `{tag_counts, join_integrity, failed_batch_ids, run_id, resume_hint}` — no clustering, no synth. |
| **Cross-Repo Archive Specialist Branch** | Sonnet (parallel to Wave 1) | Dedicated branch for `cross-repo/archive/*.md` — reads full memo bodies with a commitment-closure + boundary-ratification lens instead of the generic Haiku nugget-scanner + topic-Sonnet path. Full contract: `PIPELINE.md § Cross-Repo Archive Specialist Branch`; dispatch prompt: `agent-prompts/cross-repo-archive-specialist.md`. |
| **Curation (Coordinator, out-of-band)** | — | Between Invocation A and B — NOT a Workflow phase. The EM runs the curation engine's `distill.curate_clusters` op over Invocation A's `tag_counts`, passing `keep_threshold=recommended_keep_threshold` (the value Invocation A derived from corpus maturity — 1 for cold-start, 2 for mature; the retired `SINGLETON_FLOOR`/`NEW_FILE_CAP` no longer exist, this threshold is the minting policy's only remaining knob, and it is derived, not a held constant — see `PIPELINE.md` § Consolidation for the full derivation), producing a per-tag verdict map (`keep`/`normalize`/`merge`/`drop`), then re-invokes the SAME script as Invocation B with `curatedTags` set and `resumeFromRunId` pointed at Invocation A's `wf_...` Workflow-tool run id (NOT `run_id` — see § the `resumeFromRunId`/`run_id` distinction below). |
| **Homing override + Clustering (Workflow, Invocation B)** | Coordinator (JS, free join) | Before clustering: any curated tag whose slug already matches an existing wiki file is restored to `keep` under its own key, regardless of the curation verdict — homing outranks a shape verdict made without seeing this repo's wiki tree. Clustering then resolves every raw tag through the (homing-adjusted) curated map — `keep`/`normalize`/`merge` group into topics, `drop` is excluded and recorded (`drop_summary`); a tag absent from the map or an unrecognized verdict fails the run loud, no bucket invented. Every surviving homeless cluster becomes its own new wiki file unconditionally — no misc bucket, no coarsen/fold/cap. |
| **Wave 2 (Workflow)** | Sonnet (parallel, one-agent-owns-one-topic) | Synthesize nuggets into guide content and decision records, **direct additive write** with provenance frontmatter (§ 5b); emits `dispositions:` YAML frontmatter covering all assigned nugget IDs (schema: `agent-prompts/phase-2.md`); rate-limit retry + `resumeFromRunId` cover per-synth failure without re-running the whole wave |
| **Coverage gate (Workflow, in-JS)** | Coordinator (mechanical, no dispatch) | Retired the former Phase 2.7-QG Haiku ×M-per-cluster wave — the check is a pure set-diff (each cluster's `dispositions:` nugget IDs vs. its assigned nugget IDs), computed in-process immediately after Wave 2 (no agent dispatch, no journaling needed). Any cluster with uncovered nuggets automatically re-dispatches ONE Sonnet gap-synth agent scoped to only the uncovered subset, additively merges its returned `dispositions:` into the original synth result, and logs `covered/total` + the list of gap clusters — no silent caps. Full mechanics: `distill-harvest.workflow.js` § Coverage gate. |
| **Phase 2.5** | Sonnet (parallel) | Mine reviewer sidecars for cross-spec convergence patterns; emit promotion proposals to scratch (`state/scratch/artifact-distillation/{run-id}/judgment-proposals.md`). Full contract: `PIPELINE.md § Phase 2.5`. |
| **Phase 3a** | Sonnet (parallel by cluster) | Contradiction detection — one agent per topic cluster; coordinator cross-cluster check post-3a; Opus escalation if unresolvable contradictions found, followed by Sonnet fidelity-check verifying all source nugget IDs cited |
| **Phase 3b** | Sonnet (single) | Decision-record dedup — collect all Wave 2 DRs, produce deduplicated canonical set + `dr_dedup:` YAML manifest (schema: `agent-prompts/phase-3b.md`) |
| **Phase 3c** | Coordinator (mechanical) | `DIRECTORY_GUIDE.md` assembly — read Wave 2 frontmatter + Phase 0 wiki inventory, write `directory_entries:` YAML manifest + prose preview; no subagent |
| **Phase 3d** | Sonnet (single) | Deletion manifest — per-file `deletions:` YAML block and (schema v2) grouped `deletion_groups:` sibling key; >50-row self-check switches bulk EPHEMERAL/ALREADY_CAPTURED to grouped form; prose table is derived PM-readable view; **gated on Phase-1/2 scan success-rate** (see § Pre-Phase-4 — Disposal Manifest Scan-Success Gate below) — a mass-failed scan wave cannot produce a disposal manifest. Full schema: `agent-prompts/phase-3d.md` |
| **Phase 4** | Coordinator | PM approval gate — **deletions only.** Present the deletion manifest (+ DIRECTORY_GUIDE.md preview as informational context) and wait for explicit approval before Phase 5's disposal tier runs. The additive tier (wiki/DR writes, distillation-log rows) already landed direct at Wave 2/Phase 2.5 — this gate does not block it. |
| **Phase 5** | Coordinator | Apply-confirmation pass over the already-landed additive writes (manifest-driven done-conditions: file-path set-diff vs. `git diff --stat`); **drain harvest debt from `archive/specs/` first and bank it (harvest-debt drain contract, see § Phase 5 intro)** — including **Decision Rationale extraction** (§ 5a, required, dispatch-eligible); **delete scaffolding via YAML `deletions:` manifest — EM-only, `git rm`, only after the Phase 4 gate approves** (see § Phase 5 intro, Subagent-scoped vs EM-only); update distillation log (dispatch-eligible); run link-heal pass; **reap integrated review-findings sidecars — EM-only, `git rm`** (§ Phase 5 step 10 — targeted `## Integrator Dispositions`-marked reap, not a `state/subagent-share/` purge); **reap stale `state/subagent-share/` sidecars of every type — EM-only, `git rm`** via `bin/reap-stale-subagent-sidecars.py` (liveness-and-age-floor gated, never `status:` alone — see § tasks/ vs state/ named exception below) |

### Phase 0 — Wiki Inventory

Before dispatching the Workflow, Phase 0 builds the wiki-inventory input the Workflow's Wave 1
scan brief and Wave 2 synth-targeting both rely on. Do NOT enumerate only `docs/wiki/` — a repo may
carry more than one wiki tree (this coordinator source repo has BOTH `docs/wiki/` and
`coordinator/docs/wiki/`; see `PIPELINE.md` § Phase 0 step 3 for the full dual-tree-hazard
rationale). Enumerate every wiki tree present, generically: `docs/wiki/` always, plus
`coordinator/docs/wiki/` when that directory exists — do not hardcode "exactly two" as a universal.

Build, from that enumeration:
- **`wikiSlugs`** — a flat `{'<slugified-filename-stem>': '<repo-relative-path>'}` index, union
  across every wiki tree found.
- **`wikiDirs`** — an ordered list of the wiki trees found; element `[0]` is the default home for
  any NEW file the run mints.

Pass BOTH into the Workflow's `INPUT` (replacing the older single-map `wikiInventory` shape — see
`PIPELINE.md` § Phase 0 step 3 for the back-compat note). Also pass the `wikiSlugs` slug list into
the Wave 1 scan brief so Haiku can mark `ALREADY_CAPTURED` against real files on disk rather than a
topicKey guess.

**If `--dry-run`:** the disposal tier (deletion manifest presentation + Phase 5 delete/trim) is skipped; the pipeline stops after Phase 3d and presents the summary. Additive writes are unaffected by this flag on a real run — `--dry-run`'s scope is "preview the disposal decision," not "preview everything."

### The `resumeFromRunId`/`run_id` distinction (mandatory reading before re-invoking the Workflow)

`resumeFromRunId` is NOT this pipeline's `run_id`. Two different identifiers; passing the wrong one does not error, it silently re-dispatches the whole (expensive) scan wave instead of replaying it:

- **`run_id`** is this pipeline's own distillation slug (`YYYY-MM-DD-HHhMM`), supplied by the EM and used for scratch paths and journal correlation. It never changes across Invocation A and B of the same run.
- **`resumeFromRunId`** is the Workflow *tool's* own harness-assigned run id (`wf_...`), which exists only in Invocation A's Workflow tool RESULT — the script itself cannot see or return it.

Re-invoking as Invocation B: pass `runId: <the same distillation slug as Invocation A>` and `resumeFromRunId: <the wf_... id from Invocation A's own tool result>`. This same distinction governs the Pre-Phase-4 scan-success-gate remediation text below — its `resumeFromRunId` reference is to the `wf_...` id, never to `run_id`.

**If `--no-delete`:** Phase 5 applies wiki writes, but skips scaffolding deletion and spec archival — the disposal tier is opted out for this run; the additive tier (never PM-gated) is unaffected either way.

---

## Handoff distillation

### Input enumeration

Distill enumerates archived handoffs via `bin/query-records --type handoff-archived --format paths` (run from the resolved coordinator plugin root) — NOT a raw `find archive/handoffs/ -name '*.md'`. Using `query-records` preserves frontmatter validation (each handoff is checked against `schemas/handoff-archived.yaml`) and provenance metadata (workstream, predecessor, deployment_state). Same enumeration discipline as `--type plan` for `docs/plans/`.

`bin/query-records` is the CLI front-end over claude-klabauter's native engine, `coordinator_core/ops/records_query.py`, `@register_op("records.query")`. Cite `records.query` when pointing at the underlying enumeration engine rather than `query-records.js` — the Node-era JS oracle is retained only for parity-testing, not as a runtime dependency (de-node cutover, `e187d8c2`..`b3069349`).

### Extraction targets

| Source content | Target | Notes |
|---|---|---|
| Substantive `## Key Decisions Made` section with reasoning | DR in `docs/decisions/` | Existing pattern (Phase 5b provenance frontmatter applies) |
| Reusable cross-cutting patterns / lessons | Wiki entry in `docs/wiki/` | New `archived_handoff:` provenance key — see schema below |
| Neither (only mechanical sections like `## Files Modified`) | No extraction | Eligible for delete under Phase 5 safety guards |

**Memory pointers are NOT a valid extraction target.** A `~/.claude/**/memory/*.md` entry does not count as durable capture — only `docs/decisions/`, `docs/wiki/`, `state/cross-repo-commitments/`, or a canonical plan/spec do.

**Scaffolding new DRs:** use `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type decision --title "<title>" --out docs/decisions/DR-<NNN>-<slug>.md` to generate conformant frontmatter (`id`, `title`, `created`, `status`, `deciders`) from `schemas/decision.yaml`. The canonical identity key is `id`; the canonical temporal key is `created` (not `date`).

### Provenance frontmatter — new `archived_handoff:` key

`archived_handoff:` is a **new top-level key**, NOT a sub-key under `provenance:` (that key is taken by Phase 5b's archived-spec schema as a list-of-objects with `path` + `last_verbose_sha`; collision would break schema-based dispatch).

```yaml
archived_handoff:
  - path: archive/handoffs/2026-05-04_140000_some-workstream.md
    workstream: some-workstream
    last_verbose_sha: a1b2c3d
    distilled: 2026-05-08
```

Sibling key to `provenance:` (specs) and `judgment_provenance:` (codebase-judgment entries).

`archived_handoff:` is a provenance marker: a reference to a deletion candidate inside this block
is a tombstone, not a live dependency, and is excluded from active-reference checking (Guard 3
below).

### Delete safety (mandatory; opt-out is `--no-delete`)

`/distill` deletes handoffs by default after extraction; `--no-delete` overrides for specific runs.

**Aggressive by default.** The four numbered guards below are the COMPLETE **dispositioning-agent-facing** eligibility list — HARD guards only. A dispositioning agent (Phase 3d) MUST NOT invent additional soft retain-reasons beyond these four. (The claude-klabauter engine independently enforces two more mechanical, fate-keyed hard guards at *apply* time — see [§ Engine-enforced fate guards](#engine-enforced-fate-guards-apply-time-both-classes); those are engine-owned, not agent judgment, and do not license the agent to invent soft reasons here.) Named anti-patterns observed and rejected: a `~/.claude` memory-pointer citation is NOT a retain reason (guard 1 already excludes it as non-durable capture); the source spec being "load-bearing" is NOT a retain reason for the *handoff* (load-bearing governs the spec, not this artifact); an open gate-recheck / "active gate tracking" note is NOT a retain reason on its own — only an unresolved item that fails one of the four guards below blocks deletion. Conservatism is opt-in via `--no-delete` (skips disposal entirely for the run), not the default posture.

**Reflex guard — check before deleting.** If the ONLY capture of a decision is a `~/.claude` memory entry, it is NOT durably captured — promote to an in-repo DR before deleting the source memo/handoff.

A handoff is eligible for delete in Phase 5 ONLY if all four guards pass — no fifth, *softer*, guard may be added at dispatch time (these four are the **dispositioning-agent-facing** gates; the claude-klabauter engine independently enforces two mechanical, fate-keyed **hard** guards at apply time — see [§ Engine-enforced fate guards](#engine-enforced-fate-guards-apply-time-both-classes). Those are not agent-invented soft reasons; the "MUST NOT invent" ruling above governs Phase 3d judgment, the fate guards govern `apply_disposal`):

1. **Extraction-artifact present.** At least one DR (in `docs/decisions/`) or wiki entry (in `docs/wiki/`) was written this run referencing the source via `archived_handoff:` provenance frontmatter, OR the handoff is empirically content-free (only `## Files Modified This Session`, no decisions / blockers / next-steps). **Exclusion — a `~/.claude` memory pointer does NOT satisfy this guard.** A `~/.claude/**/memory/*.md` entry (or any `~/.claude` path) citing the handoff's content is NOT durable capture — durable capture is IN-REPO ONLY: `docs/decisions/`, `docs/wiki/`, `state/cross-repo-commitments/`, or a canonical plan/spec. Memory is git-tracked but lives in `~/.claude` (a machine-local personal repo) — relative to the project it is RAM: it doesn't travel on a fresh clone/other machine/OSS-publish target, is NOT RAG-retrievable (RAG indexes the project tree, not `~/.claude`), and is doctrinally a lossy recall index — a pointer TO a durable record, never the record itself. If the only cited capture is a memory pointer, this guard FAILS → retain, do not delete; surface to PM to promote to a DR first.
2. **`shipped_in:` present.** A handoff in `archive/handoffs/` lacking `shipped_in:` (commit SHA or PR ref) cannot be deleted — surface to PM with the missing-paper-trail diagnosis. This catches handoffs that were archived but whose work did not actually ship; deleting would erase the only record of the orphan workstream. `shipped_in:` is set by `/pickup` (rare — only when the SHA is known) or by the picking-up session's `/handoff` or `/workstream-complete` (normal case).
3. **Active-reference check.** Ripgrep `archive/handoffs/<basename>.md` references across `docs/`, `tasks/`, `archive/specs/`, and plugin sources. Any active reference (i.e., not in another to-be-deleted file) blocks deletion of that handoff. Cleanup is higher-risk than it looks — a citation from an active spec must not silently dangle.
4. **Distillation-log row.** Same ≥8-word domain-prose requirement as existing scaffolding rows (per Phase 5c). Reason field describes why the handoff content was decision-bearing or content-free.

**These four guards gate eligibility judgment (dispatch-eligible at Phase 3d) — the resulting deletion at Phase 5 is EM-only**, per § Phase 5 intro, Subagent-scoped vs EM-only.

Git history remains the permanent paper trail. Use `git show <last_verbose_sha>:<original-path>` to recover the verbose handoff text.

### Phase 5d link-heal extension

Add `archive/handoffs/<basename>.md` to the path-rewrite ripgrep set. Healing target: any cross-reference from wiki/DR to a now-deleted archived handoff gets rewritten to the wiki/DR that absorbed it (with parenthetical `(formerly archive/handoffs/<basename>.md @ <sha>)`).

---

## Cross-repo archive distillation

### Input enumeration

Distill enumerates closed cross-repo memos via a direct glob — `cross-repo/archive/*.md` — filtered to files whose frontmatter carries `status: actioned`. There is no `query-records` type for cross-repo memos; use Glob + frontmatter parse directly (the same approach as the workday-start surface query uses for inbox memos).

Do NOT enumerate `cross-repo/inbox/*.md` — active memos in the inbox are never distillation candidates; they are in-flight channel traffic, not closed historical artifacts.

### Extraction targets

| Source content | Target | Notes |
|---|---|---|
| Cross-repo decisions with lasting architectural significance | DR in `docs/decisions/` | E.g. "project-rag confirmed co-located archive over top-level archive/cross-repo/" — rare |
| Cross-cutting patterns surfaced in a memo thread | Wiki entry in `docs/wiki/` | E.g. a sequence of memos that converged on a new installation discipline |
| **Cross-team boundary/shape ratification** — a memo whose `decision:` disposition records an inter-team boundary, ownership split, or contract-shape agreement (e.g. "DoE owns contract, claude-klabauter owns engine") | DR in `docs/decisions/` or wiki entry in `docs/wiki/`, `cross_repo_memo:` provenance | **EXEMPT from the "extraction is rare" bias below — promote BY DEFAULT (AC8).** Scope test: the memo settles *who owns what* or *what the seam looks like* between repos/teams — not merely "this coordination felt important." Ordinary status updates, routine asks, and single-repo-internal decisions relayed cross-repo do NOT qualify, even if consequential. |
| Neither (routine actioned memos with no evergreen content) | No extraction | Eligible for delete under Phase 5 safety guards |

**Memory pointers are NOT a valid extraction target.** A `~/.claude/**/memory/*.md` entry does not count as durable capture — only `docs/decisions/`, `docs/wiki/`, `state/cross-repo-commitments/`, or a canonical plan/spec do.

**Scaffolding new DRs:** same as handoff distillation — `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type decision --title "<title>" --out docs/decisions/DR-<NNN>-<slug>.md`; canonical keys are `id` and `created`.

**Extraction is rare — except cross-team boundary/shape ratifications (see row above), which promote by default.** Most cross-repo memos are coordination records — they do not contain architectural decisions worth promoting. The overwhelming majority are `→ DELETE` (routine coordination extracted to `[EPHEMERAL]`). The distill agent must resist the impulse to force-promote; only genuinely evergreen cross-repo decisions — or a memo matching the boundary/shape-ratification row above — earn wiki or DR entries. **Anti-scope:** the boundary/shape exemption is narrow by design — it must NOT become a force-promote firehose for "any memo that felt important." If a memo doesn't settle an inter-team ownership/contract-shape question, the generic resist-promotion default still applies.

### Provenance frontmatter — `cross_repo_memo:` key

Wiki or DR entries promoted from a cross-repo memo carry:

```yaml
cross_repo_memo:
  - path: cross-repo/archive/YYYY-MM-DD-<slug>.md
    from: project-rag-em
    to: claude-central-em
    distilled: 2026-05-23
```

Sibling key to `archived_handoff:` (handoff distillation) and `provenance:` (archived-spec distillation). Do NOT use `provenance:` — that key is taken by Phase 5b's archived-spec schema.

`cross_repo_memo:` is a provenance marker: a reference to a deletion candidate inside this block
is a tombstone, not a live dependency, and is excluded from active-reference checking (Guard 3
below).

### Delete safety (same four guards as handoff distillation, plus a fifth commitment-closure guard)

A cross-repo archive memo is eligible for delete in Phase 5 ONLY if all five guards pass (plus the two engine-enforced fate guards common to both classes — see [§ Engine-enforced fate guards](#engine-enforced-fate-guards-apply-time-both-classes)):

1. **Extraction-artifact present OR empirically content-free.** At least one DR or wiki entry was written this run referencing the source via `cross_repo_memo:` provenance frontmatter, OR the memo is routine coordination with no decisions or patterns (the common case — classify as `[EPHEMERAL]`). **Exclusion — a `~/.claude` memory pointer does NOT satisfy this guard.** A `~/.claude/**/memory/*.md` entry (or any `~/.claude` path) citing the memo's content is NOT durable capture — durable capture is IN-REPO ONLY: `docs/decisions/`, `docs/wiki/`, `state/cross-repo-commitments/`, or a canonical plan/spec. Memory is git-tracked but lives in `~/.claude` (a machine-local personal repo) — relative to the project it is RAM: it doesn't travel on a fresh clone/other machine/OSS-publish target, is NOT RAG-retrievable (RAG indexes the project tree, not `~/.claude`), and is doctrinally a lossy recall index — a pointer TO a durable record, never the record itself. If the only cited capture is a memory pointer, this guard FAILS → retain, do not delete; surface to PM to promote to a DR first.
2. **`status: actioned` confirmed.** A memo without `status: actioned` is not yet closed channel traffic — do NOT delete. Surface to PM with a "memo not yet actioned" note.
3. **Active-reference check.** Ripgrep the memo's **repo-relative path** (`cross-repo/archive/<basename>.md`, not the bare filename) across `docs/`, `tasks/`, `archive/`, and plugin sources. Any live cite blocks deletion — the memo is still being referenced. (This needle asymmetry vs. Guard 7's path-OR-basename match is what the [§ Engine-enforced fate guards](#engine-enforced-fate-guards-apply-time-both-classes) citation-form convention turns on.)
4. **Distillation-log row.** Same ≥8-word domain-prose requirement as existing scaffolding rows (per Phase 5c). Reason field describes the memo content or states "routine coordination, no evergreen content."
5. **Commitment-closure gate.** Blocks deletion of an actioned memo while EITHER of the following holds:
   - (a) **Sibling loop, our record only.** A linked `state/cross-repo-commitments` entry referencing this memo is `status: open`. **Honest-scope note:** this check reads OUR record of the sibling loop — it is NOT a query against the sibling's own queue (we cannot see their state); it only catches the case where our own tracking still shows the loop open.
   - (b) **Our loop.** The memo's disposition is `decision: accepted` OR `decision: partial`, AND its `realized_by` target is absent or unverifiable (e.g. the cited commit/plan/path does not resolve on disk). `realized_by` is required only on `accepted` and `partial` dispositions (per `coordinator/skills/pickup/SKILL.md` § M3 Accept, "the claim-of-record" — ~line 818) — a `declined` / `fyi-ack` / `consult-reply` terminal carries no `realized_by` requirement and must NOT trip this clause; those dispositions are correctly closable without it.

   Blocked by either clause ⇒ surface to PM and retain (do not delete) — do not silently skip.

**These five guards gate eligibility judgment (dispatch-eligible at Phase 3d) — the resulting deletion at Phase 5 is EM-only**, per § Phase 5 intro, Subagent-scoped vs EM-only.

Git history remains the permanent record. The `cross-repo/archive/` path is git-tracked (per D5 — inbox + archive both have committed READMEs); `git log -- cross-repo/archive/<filename>` retrieves the full history.

### Phase 5d link-heal extension (cross-repo memos)

Add `cross-repo/archive/<basename>.md` to the path-rewrite ripgrep set alongside archived handoffs. Healing target: any cross-reference from wiki/DR to a now-deleted archived memo gets rewritten to the wiki/DR that absorbed it (with parenthetical `(formerly cross-repo/archive/<basename>.md @ <sha>)`). Cross-repo memos that were purely coordination records with no extraction will not have a rewrite target — those references should simply be deleted rather than repointed.

---

## Engine-enforced fate guards (apply-time, both classes)

Distinct from the dispositioning-agent-facing guards above (which gate what Phase 3d *proposes*), the claude-klabauter engine enforces two additional **hard, mechanical** delete guards at *act time* — keyed on the candidate's `distill_fate` stamp, re-run by the single dispatch authority `apply_disposal` (which re-evaluates `evaluate_candidate_detailed` at delete time, not stamp time; guard functions live in claude-klabauter's `coordinator_core/distill/delete_guard.py`). The guard set is **class-agnostic** — `evaluate_candidate_detailed` runs both guards for handoffs and cross-repo memos alike — but in practice only candidates carrying a `distill_fate` stamp are affected, and `distill_fate` is a **cross-repo-memo** field: memos get theirs at pickup-action time (per `skills/pickup/SKILL.md` § M3) and it is schema-validated on the `cross-repo-memo` schema only; the `handoff` schema carries no `distill_fate` rule, so handoffs are not fate-stamped and both guards no-op on them. These are NOT the "soft retain-reasons" the aggressive-by-default ruling forbids — they are mechanical guards the engine owns, not agent judgment.

**Negative-spec — mechanical re-evaluation stays separate from shard judgment, and must keep re-running at apply time.** On a run that split commitment-loop review across three specialist shards, the shards' own judgment flagged 5 open commitment loops; a separate assembler re-running `evaluate_candidate_detailed` over the literal guards found **16 more retains the shards missed** — 6 memos not literally `status: actioned`, 6 with `accepted`/`partial` dispositions whose `realized_by` did not resolve on disk, 4 cited in live prose outside a provenance tombstone. Judgment agents under-catch guard failures because they reason about meaning, not fields — a shard concluding "this loop reads closed" is not the same fact as "this loop's fields literally pass Guards 1–7." `apply_disposal` MUST keep re-running `evaluate_candidate_detailed` at apply time on every candidate, and a shard's own disposition (open/closed judgment, however careful) must never stand in for that mechanical re-check — the two are complementary layers, not substitutes, same shape as the scan-success gate composing with resume/retry above.

- **Guard 6 — `check_distill_fate`.** A candidate stamped `distill_fate: ratification` **refuses deletion unless its `in_repo_capture` path resolves on disk AND is non-empty** — re-checked at delete time. Fates `ephemeral`, `commitment`, and *absent* pass this guard. An **unrecognized** fate value **fails closed** (refuses deletion). This is how a gate-resolving/ratification memo is protected for free — the durable-capture pointer must actually exist and carry content before the source can be reaped.
- **Guard 7 — `check_harvest_provenance`.** A candidate stamped `distill_fate: commitment` is **blocked from deletion unless a `docs/wiki/**` or `docs/decisions/**` file cites it** (by the candidate's repo-relative path OR its bare basename). No-op for every non-commitment fate, so the routine `ephemeral` majority is untouched. This closes the hole where a `commitment` with `realized_by: inline` (or a bare code SHA) would pass with zero content-survival check.

**Provenance-citation form — how to make a harvested `commitment` actually deletable.** Guard 7 (harvest-provenance) and Guard 3 (`check_active_reference`) overlap, but match **different needles** — and that asymmetry is the lever. `check_active_reference` matches the candidate's **repo-relative path only**; `check_harvest_provenance` matches the repo-relative path **OR** the bare basename. So a provenance block citing a to-be-deleted `commitment` by its **full repo-relative path** satisfies Guard 7 *and* trips Guard 3 → retained (a safe direction — no delete hole); a citation by **bare basename only** satisfies Guard 7 (basename leg) but does NOT trip Guard 3 (which only matches the full path) → deletable. So **"harvested, therefore deletable" holds only when the provenance citation is by basename (or paraphrase), and the candidate's full repo-relative path appears _nowhere_ Guard 3 scans (`docs/`, `tasks/`, `archive/`).**

**Resolution — the standard `cross_repo_memo:` provenance block no longer defeats this.** `active_reference_guard` rg-scans the *whole* harvesting file, frontmatter included — it makes no structured-metadata-vs-prose distinction by itself. The `cross_repo_memo:` frontmatter schema (see § "Provenance frontmatter" above) records `path: cross-repo/archive/<name>.md` — the full repo-relative path — so a naive scan of any memo harvested with a standard provenance block would trip Guard 3 and retain it, basename-form prose notwithstanding. The compose is specified by the provenance-marker exclusion contract: a reference to a deletion candidate inside a recognized provenance-marker block (`archived_handoff:`, `cross_repo_memo:`) is a tombstone, not a live dependency, and is excluded from Guard 3's active-reference scan. Under that contract, a `commitment` memo cited only by its own `cross_repo_memo:` provenance block becomes deletable, while a citation of the same memo in prose body or non-provenance frontmatter still trips Guard 3 and retains it exactly as today. **Engine consumption is in-flight** — `active_reference_guard` (claude-klabauter `coordinator_core/distill/_common.py`) picks up this exclusion via a cross-repo proposal; until it ships, the safe-retention default described above still holds in practice.

---

## Pre-Phase-4 — Disposal Manifest Scan-Success Gate (break-class, mandatory)

**Coverage-% alone is necessary-not-sufficient for disposal.** A run where the Phase-1/2 scan wave mass-failed — a throttled Haiku wave, a rate-limit storm the Workflow's retry hasn't yet drained, a batch that silently errored — can still emit a Phase 3d deletion manifest listing sidecars, handoffs, and memos as delete-eligible, because Phase 3d's set-difference logic only sees "not referenced by a surviving nugget," and a plan/handoff/memo that was never scanned trivially satisfies "not referenced." **A mass-throttle run where scans failed cannot produce a deletion manifest** — the absence of a reference is not evidence of "already harvested," it's evidence of "never looked at."

**The gate:** before Phase 4 presents the deletion manifest for PM approval, Phase 0/Coordinator computes the Phase-1/2 **scan success-rate** — `(batches that returned a valid nugget file) / (batches dispatched)` — from the Workflow's per-batch journal (the same journal `resumeFromRunId` reads to find failed synths). If the success-rate falls below the threshold (default: 90%; conservative — tune only with a named reason), Phase 4 **suppresses the deletion manifest entirely** and instead reports: `"Disposal suppressed — scan success-rate <N>% (<failed>/<total> batches failed); re-invoke the Workflow with resumeFromRunId set to the wf_... runId from the failed invocation's tool result (NOT this pipeline's run_id, a distillation slug — passing the wrong id silently re-dispatches the whole scan wave) to drain the failed batches before requesting disposal."` The additive tier (wiki/DR writes from whichever batches DID succeed) is unaffected — those writes are provenance-stamped per-batch and stand on their own regardless of sibling-batch failure; only the disposal decision is gated on aggregate success, because disposal reasons from *absence* of a reference across the WHOLE scanned corpus, and a mass-failure corrupts that absence-as-evidence assumption for every artifact, not just the failed batches' own targets.

**Composes with C6 (Workflow resume/retry).** The Workflow's `resumeFromRunId` re-runs only failed synths, which shrinks the blast radius of any given throttle — but this gate is defense-in-depth regardless of how good the retry is: resume makes a throttle *non-fatal* (you can always re-run and eventually reach a clean scan), this gate makes empty-harvest disposal *impossible* (even before a retry, the manifest simply won't fire on a mass-failed wave). The two are complementary, not redundant: one shrinks the hazard window, the other makes the hazard's dangerous consequence structurally unreachable.

**Negative-spec — do not weaken this gate.** A run against a virgin repo with 89 artifacts of harvest debt hit exactly the failure this gate exists to prevent: the first workflow attempt hit a session limit and all 7 scan batches failed (0/7 success). Absence-of-reference reasoning over an unscanned corpus would have marked all 86 candidates delete-eligible — the difference between a rate-limit incident and a data-loss incident. Do NOT weaken this gate to a warning (a warning is skimmable and skimmed; the gate must suppress, not merely flag). Do NOT substitute a manifest's own self-reported coverage for scans that actually succeeded — Phase 3d's "N deletion-eligible candidates found" is not evidence of scan success, only the per-batch journal is (per the "re-derive from disk" rule above). The 0/7 → 86-candidate outcome is the reference case for why this gate is mandatory, not advisory.

**Re-derive from disk, don't trust the manifest column (per §38).** The scan success-rate is computed from the Workflow's own per-batch journal on disk — never inferred from Phase 3d's own self-report of "N deletion-eligible candidates found," which is exactly the kind of classifier-manifest trust §38 warns against. If the journal is unavailable or unreadable, fail loud (suppress disposal) rather than assume success.

**Apply-volume hard cap (engine-enforced, independent of the scan-success gate).** claude-klabauter's `verify_stamp_and_throttle` Gate 4b caps a single run at `MASS_THROTTLE_HARD_CAP=200` **applied** disposals — and the cap holds **even when a `mass-throttle-ack` is present**. A disposal set larger than 200 cannot be forced through in one run; it must split across multiple `/distill` runs. The ack acknowledges a large-but-normal wave; it does not override the hard ceiling.

---

## Pre-Phase-4 — Nugget Source Join-Integrity Gate (break-class, mandatory)

**Phase 5c's disposition is derived from "did this source produce nuggets?" — and that question is only answerable if `source` joins back to the batch's own file list.** `distill-harvest.workflow.js` returns nuggets whose `source` field is a string the scan agent wrote, not a value pinned to the batch's `files[]` enum. A source that fails to join a scanned path produces zero attributable nuggets and files as `EPHEMERAL` — *routine, nothing worth promoting* — for a file that may in fact have yielded harvested decisions. This is not a different failure mode from the scan-success gate above; it is the same rationale one layer down. **The absence of a reference is not evidence of "already harvested," it is evidence of "never looked at"** — that is the scan-success gate's claim. An unjoined source is a *third* case, distinct from both: looked at, harvested, and then lost at the join.

**Measured evidence (run `2026-08-06-14h38`).** 245 distinct nugget sources; 118 exact joins against the batch file list; 84 more recovered only by falling back to a basename match (the scan agent returned a bare filename where the batch handed it a full repo-relative path); 43 unjoinable by either form — an **unjoinable rate of 17.6%** (43/245). The unjoinable residue is `2026-07-09-wsc-<uuid>`-shaped wsc receipt IDs cited by the scan agent as if they were paths — no extension, no directory, not a member of any batch's `files[]` under either full-path or basename comparison.

**Why break-class and self-perpetuating.** Harvest debt is computed as *cohort minus rows logged `DISTILLED`/`PROMOTE`*. A source mislabelled `EPHEMERAL` at the join stays in the debt set forever, gets re-scanned every subsequent run, re-files as `EPHEMERAL` again, and the log accumulates contradictory rows for the same file across runs — an append-only log with no mechanism to reconcile them. This is the exact shape §38 warns against (trusting a classifier's self-report instead of re-deriving from disk), one layer below where that warning is written.

**The gate:** the Workflow returns `join_integrity: { batch_files, distinct_nugget_sources, exact_joins, repaired_joins, unjoinable_sources[], unjoinable_rate, threshold, verdict }`, verdict one of `clean` (unjoinable_rate 0) / `finding` (rate > 0, at or below `threshold`) / `failed` (rate above `threshold`; default threshold 10% of distinct nugget sources). On `failed`, the Workflow additionally returns `disposal_suppressed: true` + `disposal_suppressed_reason`, and Phase 4 suppresses the Phase 3d deletion manifest exactly as the scan-success gate does — the additive tier (wiki/DR writes from joinable sources) is unaffected; only disposal is gated. A `finding` verdict does not suppress disposal but MUST be surfaced at the Phase 4 gate alongside the manifest, naming the `unjoinable_sources[]` count and rate, so the PM sees the residue even below threshold.

**Negative-spec — do NOT repair the join downstream.** Phase 5c MUST NOT fall back to a basename join of its own to paper over a high unjoinable rate. The repair belongs at the boundary where the batch file list is still in scope — inside the Workflow, where `files[]` is authoritative — not in Phase 5c, which only sees whatever `source` string it was handed. Once `source` reaches Phase 5c, downstream consumers must be able to treat it as an exact path; re-deriving a fuzzy match at the log-writing boundary hides the defect instead of fixing it and produces a distillation log that is only correct by accident.

---

## Phase 4 — PM Gate: Atlas Staleness Advisory (sensor, non-blocking)

Before presenting the deletion manifest at the Phase 4 PM gate, `/distill` runs a **read-only atlas staleness check** and, if warranted, surfaces a one-line advisory. **`/distill` is the sensor; `/architecture-audit` is the actuator** — distill NEVER invokes the audit, NEVER blocks on the result, and NEVER writes the atlas. The advisory simply lets the PM choose to refresh the architecture map *before* the source material being mapped is buried. The two skills stay separate (no fusion, no breadcrumb lay-up). This is the third read-only consumer of the sensor, after `/architecture-audit` Step 1 and `/workweek-complete`.

**Procedure:**

1. **Run the sensor:** `bin/check-atlas-watch-drift.py` (engine-resident, resolved at invocation time via the `resolve-coordinator-bin` snippet, not a DoE-claude-local path; pure read, always exits 0; emits one `FRESH|DRIFT|MISSING|STALE <system> …` line per atlas page).
2. **Map this run's churn to atlas systems** via a **simple keyword/path-prefix map** (explicitly NOT a pluggable predicate framework). **The churn set is the file paths the run's RIPE plans actually MODIFIED** — read from each ripe plan's `File Lists` / `## Files` section (or the commit range that shipped it), NOT the plan's own `docs/plans/…` filename — **plus subsystem references in the archived handoffs being processed.** Match those modified-file paths against the path-prefix column below. (Maintenance: keep the 7 rows reconciled with the atlas system pages `check-atlas-watch-drift.py` enumerates from `docs/architecture/systems/*.md` — when a system page is added, add a row.) Seed map (heuristic — extend as systems are added):

   | Atlas system | Path-prefix / keyword signals |
   |---|---|
   | `coordinator-pipeline` | `skills/`, `pipelines/`, `commands/` (pipeline orchestration) |
   | `coordinator-skills` | `skills/<name>/SKILL.md` (skill bodies specifically) |
   | `coordinator-runtime` | `bin/`, `hooks/`, `lib/`, `snippets/` |
   | `support-reviewers` | `agents/` (reviewer personas) |
   | `ci-validation` | `.github/`, `validate-*.py`, `check-*.py`, `run-all-checks` |
   | `deep-research` | `coordinator/pipelines/deep-research/` |
   | `example-game-repo-plugins` | `plugins/example-game-workbench-repo/`, `game-dev/`, `example-game-repo-control/` |

3. **Surface the advisory (non-blocking):** for each churned system whose sensor line is `DRIFT` or `STALE`, emit at the gate:
   > _Good cause to run `/architecture-audit` on `<system(s)>` before deletion — `last_mapped`/`last_attested` is staler than the material this run buries._

   The PM may proceed or pause to refresh. Either way distill continues only on the existing Phase 4 approval — this adds a decision item to the gate, not a new halt.
4. **No-map path — fail-loud-soft (observability).** When the run's churn maps to **no** atlas system, do NOT go silent — emit one line at the gate:
   > _churn touched `<top-level paths>`; no atlas-system mapping — advisory skipped._

   A silent no-map would make the advisory toothless-by-omission (the exact "detect-then-silently-pick is a footgun" failure). The degradation to status-quo is fine; it must be **observable**, not invisible. (A missed/`FRESH` mapping is silent — only the no-map case emits the skipped-line.)

---

## Phase 5 — Apply, Trim + Archive, Delete, Heal

**Harvest-debt drain ordering contract (the plan-priority rule).** The session-init sweep has already moved terminal plans to `archive/specs/` — the MOVE is decoupled from `/distill`. What `/distill` Phase 5 does is drain the harvest debt: plans in `archive/specs/` not yet logged as `DISTILLED`/`PROMOTE` in `state/distillation-log.md` are the un-harvested set, and knowledge-harvest (§ 5a) is the heaviest, most-likely-to-be-skipped sub-step — so it runs **first and is banked (committed or staged) before any ephemera deletion**. The order is: (1) apply wiki/DR writes, (2) **harvest the ripe-plan cohort from `archive/specs/` (§ 5a) and commit that**, (3) only then delete scaffolding/handoffs/memos — **step 3's `git rm` execution is EM-only, per § Phase 5 intro, Subagent-scoped vs EM-only**. A budget-truncated run must drain harvest debt before the disposal tier — the cheap mechanical deletion never preempts the expensive knowledge-harvest. This directly counters the "apply-agent silently drops the transform when budget tightens" failure noted under § 5a Apply-agent slice rubric.

Phase 5 has four major sub-steps. They run in order; each depends on the prior.

**Subagent-scoped vs EM-only, same seam as `/update-docs` Phase 12/Phase 9.** Phase 5's knowledge-harvest work (§ 5a re-homing, Decision Rationale extraction, spec trim-in-place edits; § 5b provenance-frontmatter writes; § 5c distillation-log row append) is ordinary file-write work and MAY be dispatched to a subagent. **Every disposal leg that removes a tracked file from the working tree — `git rm` of scaffolding per the § Phase 3d `deletions:`/`deletion_groups:` manifest, the § 5d `rm -rf` of stale `tasks/<dir>/` trees, and both sidecar-reap ops (`bin/reap-integrated-review-findings.py`, `bin/reap-stale-subagent-sidecars.py`) — is EM-only.** The destructive-git-action lock default-denies `git rm` for subagents; a subagent brief that asks for it cannot succeed, it can only hand the deletion back to the EM after burning a dispatch on a contradiction static in the text. Mirrors `/update-docs`' own resolution of the identical hazard at its Phase 12/Phase 9 seam (`commands/update-docs.md`) — read there for the pattern, do not edit it from here. If Phase 5 work is sliced across dispatches, the disposal sub-steps stay with the EM; only the additive/harvest sub-steps above are dispatch-eligible.

### 5a. Spec Knowledge Harvest — Structural Rubric

Canonical specs in the harvest-debt set (`archive/specs/**/*.md` not yet logged as `DISTILLED`/`PROMOTE` in `state/distillation-log.md`) are read for knowledge extraction. The specs are already at their final `archive/specs/YYYY-MM/<name>.md` location — the session-init sweep handled the move. `/distill`'s job here is trimming post-review scaffolding from the archived copy and writing wiki/DR content — **the MOVE is a done fact; this sub-step is purely knowledge-harvest and trim-in-place**. (Month-foldering keeps `archive/specs/` navigable as it grows past ~100 entries; the `YYYY-MM` segment is derived mechanically from the leading `YYYY-MM-DD` of the spec filename.)

**ALLOWLIST sections — survive verbatim:**
- Goal
- Premise
- Acceptance Criteria
- File Lists
- Decision Records / Decisions Made
- Function Signatures / API Contracts
- Sequencing
- Out-of-Scope
- Risks (if normative — i.e., describes a constraint the implementation must respect)

**`SHIPPED: X (was: Y)` annotation note (supports plan D6):** When a `/workstream-complete` reconciliation pass has corrected an ALLOWLIST section in place, lines carrying the `SHIPPED: X (was: Y)` annotation will appear. Phase 1 extracts these as a `[DECISION]` nugget whose decision is the **shipped shape `X`**; the `(was: Y)` half is inline supersession provenance, not a competing live decision. The loop closes by construction: because the corrected line's decision text is already the shipped shape, what crystallizes into the wiki is `X` — never the forecast `Y`. (Note: Phase 1's standalone `[SUPERSEDED]` nugget class is triggered by a *later artifact reversing an earlier one* — it is NOT auto-derived from the inline `(was:)` syntax of a single corrected line; do not rely on that tagging. The optional `superseded_by:` field on a `[DECISION]` nugget is the closest existing hook if a Haiku extractor chooses to record the supersession explicitly.) No new phase or special instruction is required.

**DENYLIST sections — strip after re-homing + rationale extraction:**
- "Reviewer Plan"
- "the Staff Engineer Round N Findings"
- "the Data Science Reviewer/the Game Dev Reviewer Findings"
- "Integrator Triage"
- "Docs-Checker Pass"
- "Open Questions (resolved)"
- "Scope-Expansion Side-Channel" / "Heavy-Investment Pass" wrappers
- `## Deviations` — drop fate: `[EPHEMERAL]`. **Exception: re-homing step is skipped for this section only** (see bounded clause under Re-homing step below).

**MIDDLE — keep + flag for EM eyeball in dry-run:** any section heading not matching either list above. Do not auto-strip; surface in dry-run for EM decision.

**Re-homing step (mandatory before any DENYLIST section is stripped):**

For every DENYLIST section, scan it for content introducing a constraint, AC, or decision that does not appear in any ALLOWLIST section. Each such item must be re-homed into the appropriate ALLOWLIST section (typically Acceptance Criteria or Decisions Made) before the wrapper is stripped. Re-homing produces a diff in the trim preview that the EM reviews at Phase 4. Do not strip before the EM has approved the re-homing diff.

**Bounded re-homing exemption — `## Deviations` only:** The re-homing scan is skipped ONLY for sections whose heading EXACTLY matches `## Deviations` (the audit-only, intentionally non-crystallized section). The crystallized equivalent of every deviation already lives in the corrected ALLOWLIST sections' `SHIPPED: X (was: Y)` annotations — re-homing would produce duplicate provenance. ALL OTHER DENYLIST sections retain the unconditional re-homing scan above. This is a single-heading exemption, not a general "audit-style sections skip re-homing" policy; future section types do not fall through it.

**Decision Rationale extraction (required, not optional — per the Data Science Reviewer F3):**

Re-homing handles structural items (constraints, ACs, decisions stated as such). It does NOT capture conversational *why-we-chose-X-over-Y* rationale that lives in review threads — exactly the kind of question retrieval most often surfaces. Before stripping any DENYLIST section, extract decision rationale into a dedicated `## Decision Rationale` section of the archived spec (or a sibling `archive/specs/<name>-rationale.md` if the spec is long). Format: one paragraph per decision, naming the alternatives considered and why this one won, citing reviewer findings by reference if relevant. This section is indexed by RAG and is retrievable by future EMs without `git show`.

**Procedure:**
1. Capture `last_sha` of original verbose form before any mutation: `git log -1 --format=%H -- <path>`.
2. Stage re-homing additions into ALLOWLIST sections (do not yet strip DENYLIST). EM reviews and approves the re-homing diff.
3. Extract Decision Rationale from DENYLIST sections (still in place) into `## Decision Rationale` section.
4. Strip DENYLIST sections — runs only after steps 2 + 3 are complete and EM-approved.
5. Review MIDDLE sections for EM approval.
6. Trim the archived spec in-place at `archive/specs/YYYY-MM/<name>.md` — the session-init sweep already placed it there; no move is required. Derive the `YYYY-MM/` subdir from the spec's `YYYY-MM-DD` filename prefix when verifying the path.

**Apply-agent slice rubric:** When dispatching apply-agents in Phase 5, slice "mv files" steps separately from "transform contents" steps. Bundling them in a single agent brief lets the apply-agent silently drop the transform when its budget tightens (mv work is mechanical and visibly succeeds; content transforms are higher-risk and quietly skipped). One agent per slice — keep mv-only briefs and content-transform briefs in separate dispatches.

---

### 5b. Provenance Frontmatter on Wiki Entries

Every wiki entry produced by or updated during a distill run that summarizes a now-archived spec must carry provenance frontmatter:

```yaml
provenance:
  - archived_spec: archive/specs/YYYY-MM/<slug>.md
    original_path: docs/plans/YYYY-MM-DD-<slug>.md
    last_verbose_sha: acc49ed5
    distilled: 2026-04-29
```

`archived_spec:` carries the **month-foldered** post-move path (`archive/specs/YYYY-MM/<name>.md`); `original_path:` retains the **pre-move** `docs/plans/` path verbatim (it is correct as a historical reference and is NOT a link-heal target — see § 5d carve-out).

**Retrieval recipes (in order of preference):**
1. Read the trimmed archived spec at `archive/specs/YYYY-MM/<name>.md` — covers structure, decisions, and rationale.
2. For verbose original (review history, integrator chatter): `git show <last_verbose_sha>:<original_path>`.

**The YAML block above must land on disk as real frontmatter, not merely be produced as agent output.** A run whose wiki entries carried this lineage only as an HTML comment — no YAML frontmatter at all — kept the lineage but broke both the machine-readability contract and the `git show`/`original_path` retrieval recipe above; nothing in the pipeline caught it at the time, a downstream human did. The per-section human-readable spec-backlink comment was never the defect and stays required alongside the frontmatter — being the *only* record of lineage was the defect.

**Enforcement point and its limit.** Both Wave 2 synth briefs require this YAML provenance frontmatter (the four fields above, plus the run id) on every wiki file created or updated, in addition to the per-section comment. `SYNTH_SCHEMA` (`distill-harvest.workflow.js`) carries a required `provenance` object per returned wiki file with the same fields, and the run returns `provenance_completeness: { files, complete, missing_fields: [{wiki_path, fields}], omitted_with_reason: [...] }`. Where SHA evidence is thin, the correct action is to **omit the field with a stated reason, never guess a plausible SHA** — a fabricated retrieval recipe is worse than an absent one, because it fails only at the moment someone needs it. **This enforcement validates the *returned* provenance objects — it does not prove the frontmatter reached disk.** That gap stays an EM-side verification: eyeball `provenance_completeness` against the actual wiki files at Phase 4/5, don't take a clean `complete` count as proof the bytes landed.

---

### 5c. Distillation Log — Schema-Pinned, Append-Only

Path: `state/distillation-log.md` (per-project). Created on first distill run; populated with new rows on every subsequent run. **Schema-of-record: `coordinator/schemas/distillation-log.schema.md`** — this section summarizes the line-oriented markdown row/header shape practiced by every real on-disk log in the fleet; that file is authoritative on any conflict.

**Row producer: `distill-harvest.workflow.js`, not the EM.** The Workflow returns `distillation_log_rows: [{path, disposition, fate}]`, one entry per batch file — `SKIP` for a file whose batch never scanned, `DISTILLED` if a nugget sourced from that file survived synth with a non-SKIP op, `EPHEMERAL` otherwise. The EM's Phase 5c job is to **append those rows verbatim** — the append-only contract above is unchanged, but the EM does not derive the disposition, it transcribes what the Workflow already computed. A run whose durable bookkeeping depends on the EM remembering to hand-reconstruct dispositions from the Workflow journal is one forgotten step from a corpus that never converges: the harvest-debt drain relies on rows being both correct and actually written, and hand-derivation is the exact single point of failure this producer contract removes. **Hand-derivation is a fallback, not a parallel option** — reserved for a run that predates `distillation_log_rows[]` or bypasses the Workflow entirely, and any run that hand-derives MUST say so explicitly in its report (which rows, and that they were not Workflow-sourced).

**Header — executor MUST preserve verbatim when writing to the log:**

```
# Distillation Log
# Append-only. Each row = one distilled source artifact.
# Columns: run | path | disposition | fate
```

**Row format — one line per distilled artifact:**

```
- <path> -> <disposition>, <fate> (run: <run-id>)
```

- **`<path>`** — repo-relative path to the source artifact that was distilled.
- **`->`** — literal **ASCII** two-character arrow (hyphen + greater-than). **NEVER** the Unicode arrow glyph `→` — a reader that only matches `→` silently matches zero rows against every real on-disk log and no-ops.
- **`<disposition>`** — enum, one of: `DISTILLED`, `PROMOTE`, `EPHEMERAL`, `SKIP`, `PRESERVE`. `DISTILLED` and `PROMOTE` count as harvested for harvest-debt purposes; `EPHEMERAL`, `SKIP`, and `PRESERVE` indicate the artifact was reviewed but not harvested.
- **`<fate>`** — free-form prose fragment describing what became of the artifact post-review (e.g. `deleted (orphaned)`, `retained (active-ref)`), comma-separated after the disposition. MUST be domain-prose using CONTEXT.md vocabulary, not a process tag.
  - Bad:  "scaffolding"
  - Good: "integrator triage resolving async-run wrapper conflict in port-patterns FastMCP transport"
  - Minimum: ≥8 words. If CONTEXT.md exists, ≥1 CONTEXT.md term required.
- **`(run: <run-id>)`** — trailing parenthetical, literal `run: ` prefix followed by the run identifier (e.g. `2026-07-08-10h09`, or `2026-07-12-pass1` for sub-run labeling within a single calendar day).

Example (verified against this repo's real on-disk log):

```
- archive/completed/2026-07/2026-07-05-coordinator-maximalist-install-shape-afd4f7.md -> DISTILLED, deleted (orphaned) (run: 2026-07-08-10h09)
```

**Legacy pipe-delimited rows are read-compatible, not to be rewritten.** A prior draft of this section pinned a `| date | action | path | last_sha | belongs_to_spec | reason |` pipe-table shape that was never grounded in a real on-disk log and has been corrected (see `coordinator/schemas/distillation-log.schema.md` § Negative-spec). Where a pre-existing pipe-delimited log (or individual legacy rows) is found in the wild across the fleet, treat it as valid legacy history — read-compatible for harvest-debt purposes, never bulk-rewritten to the bullet shape by `/distill`.

**Append-only contract:** Read existing rows first. Append new rows. NEVER rewrite existing rows. Row count is monotonically non-decreasing; strictly increases on any run that deletes scaffolding or archives a spec. This is an AC.

**Mirroring:** For highest-value scaffolds (the canonical spec itself), the distillation log row is also mirrored into the wiki provenance frontmatter as redundancy.

**Why prose-shaped fate fields:** The log itself becomes index-bait. RAG indexes the on-disk filesystem; a log row reading "scaffolding" is invisible to retrieval, but a row reading "integrator triage resolving async-run wrapper conflict in port-patterns FastMCP transport" surfaces on a query about that conflict and gives the future EM a path back to the source artifact's git history (a `last_sha`-shaped detail is common convention inside the fate prose, though not itself a schema column). The log carries history forward into the retrieval surface — cheapest mitigation for the "git history is out-of-band for RAG" recall hole.

**Vocabulary discipline AC (per the Data Science Reviewer F2) — mechanically enforced, not asserted.** The fate-prose bullets above (≥8 words, ≥1 CONTEXT.md term) are enforced **in-Workflow**, over the Wave-1 scan agent's own output: the scan agent returns `file_fates[]` (one fate-prose string per batch file), and `distill-harvest.workflow.js` mechanically checks each entry — word count ≥ 8, and, only when the run supplies `contextTerms`, ≥ 1 matching term. The Workflow returns a `fate_prose_enforcement` report alongside `distillation_log_rows[]`, per-row pass/fail plus the reason.

**`'unavailable'` is a distinct verdict, never a silent pass.** When the run supplies no `contextTerms`, the term-count check reports `'unavailable'`, not `pass` — the pipeline's own rule that "found nothing and looked at nothing are different verdicts" applies here identically: a repo where no context vocabulary was supplied has not been checked for drift, and reporting it as clean would misrepresent that as validated discipline.

**A row failing enforcement gets a loud placeholder fate, never a plausible-looking one.** `fate: "[FATE-PROSE-ENFORCEMENT-FAILED: <reason>]"` (or equivalent unmistakable marker) — not a shortened-but-still-readable fallback that could pass a human skim as legitimate domain prose. Enforcement failure is reported in `fate_prose_enforcement`, and the row is still written and still counts for the append-only row-count invariant — **enforcement failure reports but does not gate disposal.** It is a quality signal for EM eyeball at Phase 4, not a suppression condition like the join-integrity or scan-success gates above.

---

### 5d. Link-Healing Pass — Expanded Coverage + No-Rewrite Classes

After specs are moved and scaffolding is deleted, stale references exist across the codebase. The link-heal pass finds and rewrites them.

**Targets to rewrite:**
- Canonical spec path (`docs/plans/<plan-name>.md`, with or without `§` section refs) → month-foldered `archive/specs/YYYY-MM/<new>.md`
- **Pre-existing flat archived-spec references** (`archive/specs/<name>.md`, from before month-foldering) → `archive/specs/YYYY-MM/<name>.md`. **`spec_backlink:` frontmatter/field references are a NAMED non-hyperlink heal-target class** — they are NOT markdown links, so the generic ripgrep link-set misses them; grep `spec_backlink:\s*archive/specs/` explicitly and rewrite each to the foldered path.
- Deleted stub paths (`tasks/<feature>/stubs/*.md`) → wiki target with parenthetical `(formerly tasks/<feature>/stubs/P1-A.md @ <sha>)`
- Intra-spec references inside the archived spec itself pointing to sibling stubs that were just deleted (second pass on the trimmed spec after archival)

**Carve-out — paths that legitimately RETAIN the flat/pre-move form (do NOT rewrite):** `original_path:` lines (intentionally the pre-move `docs/plans/…` path), `provenance:` blocks, `state/distillation-log.md` rows, and `git show <sha>:<original_path>` retrieval-recipe lines. (Note: `archived_spec:` is NOT in this carve-out for a different reason — post-migration it already carries the month-foldered path, so it is not a stale ref needing either rewrite or exemption.) These intentionally preserve the pre-move path as a historical reference (per § 5b). Scope the heal to **link contexts** (markdown link targets + `spec_backlink:`); exclude provenance/log/recipe lines as an architectural carve-out, not a glob afterthought.

**No-rewrite classes (provenance) — never rewritten by the broad-sweep path-heal executor:**

- **Historical logs** — `state/week-changelog/*`, `wsc/*.json` receipts, `review-trail/findings/*`. Every row in these surfaces is a point-in-time record of what was true *at the time it was written*; rewriting a stale path inside one of them doesn't correct history, it falsifies it. The correct action on a hit inside one of these surfaces is to leave it untouched, exactly as `original_path:`/`provenance:`/distillation-log rows are already excluded above.
- **Inbox-path provenance** — any field recording the historical inbox path a cross-repo memo or artifact arrived at (e.g. a `from_inbox:`-shaped provenance value), even after the memo has since moved to `archive/`. The provenance value documents where the artifact WAS when the event it records happened, not where it lives now.
- **Bare `source_memo:` basenames** — a `source_memo:` field citing a memo by basename alone (no path prefix) is a point-in-time attribution, not a live link; rewriting it to a current path implies a lookup guarantee the bare-basename convention was never designed to provide.

These three classes extend the existing `original_path:`/`provenance:`/log-row carve-out above under one principle, not three separate ad-hoc exclusions: **anything whose job is to record what was true historically must never be mutated by a sweep whose job is to keep what's true NOW correct.**

**Active-ref scope deliberately stops at `docs/` + `tasks/` + `archive/`.** The link-heal ripgrep sweep (tooling note below) is scoped to those three trees plus `.claude/` and plugin dirs for *code* references — it does NOT walk `state/` for rewrite purposes. `state/` is load-bearing session substrate (per § state/ vs tasks/ — load-bearing substrate vs ephemera, in the global doctrine already loaded into this session), and the no-rewrite classes above live there precisely because they are historical-record surfaces the broad sweep must never touch. If a `state/`-rooted file needs a genuine path correction, that is a surgical, hand-authored edit — never a byproduct of `/distill`'s bulk link-heal.

**Tooling:** `ripgrep --multiline --multiline-dotall` covering file types `md, json, yaml, yml, ps1, sh, py, ts, js, txt`. Scan: `.claude/`, `tasks/`, `docs/`, `archive/`, plugin dirs, repo root configs.

**Pre-deletion active-reference check.** Before `rm -rf` any `tasks/<dir>/` — **EM-only, per § Phase 5 intro** — grep references first; shipped-status alone does not mean unreferenced. Halt deletion on any live cite.

**Anchor the link-heal regex around path boundaries.** Sed-style rewrites over-rewrite `original_path:` and other frontmatter fields where the literal old path is semantically correct; anchor the pattern or restore frontmatter post-sweep.

**Heal-log:** Under a `## Manual Review` section in `state/distillation-log.md`, write EVERY unmatched-but-suspicious hit — anything containing `docs/plans/`, `tasks/<feature>/stubs/`, or the deleted-path basenames — for EM eyeball. The EM reviews the Manual Review section before declaring the run complete.

---

## tasks/ vs state/ — aggressive sweep boundary

**`state/`** — load-bearing session substrate (queues, trackers, ledgers, handoffs, review-trail, recheck markers, etc.). **Never swept by `/distill`.** Surgical edits only, each named per-surface (e.g. `coordinator:learn-lessons` writes new per-entry YAML files under `state/lessons/`; no archival by this command). If a path begins with `state/`, it is out of scope — full stop. **Named exception:** `state/subagent-share/<session-id>/*.md` review-findings sidecars carrying a `## Integrator Dispositions` block (i.e., already integrated into a plan by the review-integrator) ARE reaped by `/distill` Phase 5 step 10 via `bin/reap-integrated-review-findings.py` (§ Phase 5 in `PIPELINE.md`) — a surgical, named, post-integration reap of one artifact class, not a directory purge, and history is preserved via `git rm`. Per § Phase 5 intro (Subagent-scoped vs EM-only), this reap's `git rm` leg is **EM-only**.

**Named exception: `state/subagent-share/<session-id>/*.md` sidecars of every identity-typed kind** (run-report, review-findings, staff-eng-review, assessment/prior-art-checker/docs-checker/plan-coverage-checker spawns, and any other `report_sidecar`-eligible type — not run-report sidecars only). These are tracked deliverable docs, not ephemera — a sidecar is shareable-by-path and read later by whichever session requested it, so a "cadence sweep of a known folder" gate on `status:` alone is wrong: `complete` means *the executor is done writing*, not *the requesting-lead session has consumed it*. Deleting a `complete` sidecar while its requesting-lead session is still in flight breaks the handoff mid-read. `/distill` Phase 5 sweeps this tree via the shipped op `bin/reap-stale-subagent-sidecars.py` (engine-resident, invoked alongside the `bin/reap-integrated-review-findings.py` step above), which gates deletion on **session liveness AND an age floor, plus a status carve-out — never `status:` in isolation**: per session-id directory, if the requesting-lead session is still live (`coordinator_core.session.liveness.session_live`, the same liveness surface `bin/reap-orphaned-in-flight-handoffs.py` gates on — never mtime/pid) every sidecar under it is preserved regardless of status or age; otherwise each file is reaped only once it is past the age floor (default 14 days, `--age-floor-days` override) AND its `status:` is NOT `blocked`/`thrashing` (those two statuses are preserved unconditionally — unresolved work, same as the review-findings precedent). Tracked sidecars are removed via `git rm` + a scoped commit (history-preserving); untracked strays via plain delete. `--dry-run` reports would-reap/would-preserve without mutating anything. This op is built and live, not pending. A plain `status:`-only sweep remains explicitly out of scope (see anti-scope note above) and MUST NOT be substituted for the liveness/age-gated op. Per § Phase 5 intro (Subagent-scoped vs EM-only), this reap's `git rm`/commit leg is **EM-only**.

**`tasks/`** — Tasks-API UUID flight-recorder dirs, dated reports, dated topic dirs, and loose scratch. `/distill` sweeps here aggressively (eligibility below is judgment/dispatch-eligible; per § Phase 5 intro, the actual delete/`git rm` execution stays EM-only):

- **Dated reports** (`*-YYYY-MM-DD*.md`) older than 14 days → eligible for deletion after the Phase 3d manifest confirms no live cross-references (per active-reference check in § 5d).
- **Dated topic directories** (`<topic>-YYYY-MM-DD/`) with no git activity in the last 14 days → eligible for deletion after active-reference check.
- **Loose scratch files** (`tasks/scratch/*.{py,log,txt,sh}`) older than 7 days → delete (no active-reference check required; scratch files are not cited by name in authoritative surfaces).
- **UUID flight-recorder dirs** — managed by the Tasks API; `/distill` does **NOT** touch them. UUID-shaped directory names (36-char hex with dashes) are excluded from all sweep passes by pattern.
- **Frontmatter `status: superseded` or `status: archived`** on any `tasks/*.md` → archive immediately regardless of age (no 14-day wait).

**Hard constraint — `state/scratch/<managed-namespace>/`** (deep-architecture-survey, bug-blitz, artifact-distillation): these roots live under `state/` precisely because they are sustained cross-session work products, not ephemera. `/distill` MUST NEVER touch them. Only loose `tasks/scratch/*` files are fair game for aggressive sweep; the managed-namespace roots under `state/scratch/` are categorically protected by the `state/` no-touch rule above.

---

## Post-Ship Cleanup

After canonical outputs are committed, delete the working-notes scratch directory (`state/scratch/artifact-distillation/<date>-pass<N>/`). Optionally write a one-line breadcrumb at `state/scratch/artifact-distillation/<date>-receipt.txt` referencing the canonical commit SHA. Working notes leaking post-ship as untracked files is noise; commit-then-delete is a two-step waste.

---

## Negative AC — Silent-Loss Guard (Set-Diff Form)

**Dry-run emits a content-drop diff.** The halt-condition is set-diff, not raw match.

An AC-shaped token line (`MUST`, `SHALL`, `AC:`, `Decision:`, `Constraint:`) in the drop-list halts dry-run ONLY if no semantically-equivalent line exists in the re-homed additions OR in surviving ALLOWLIST sections.

**Implementation:** Normalize whitespace and lowercase the token-bearing lines. Compute the set-diff of drop-tokens vs kept-tokens. Halt on non-empty difference.

This prevents the muscle-memory bypass where every distill halts on review noise and operators default to `--allow-drop`. The halt fires only on genuine content loss.

**`## Deviations` section exemption (heading-classifier, not token-pattern):** AC-shaped token lines (`deviation`, `reason`, `commit` column headers; any `MUST`/`SHALL`/`Decision:` text inside the table) that appear inside a `## Deviations` section do NOT trigger a halt. The exemption is anchored on the section-heading classifier — once the heading `## Deviations` is detected, all lines within that section are excluded from the set-diff scan. Rationale: the `deviation` annotation has a kept equivalent in the corrected ALLOWLIST section's `SHIPPED: X (was: Y)` annotation; the `reason` and `commit` columns are intentionally non-crystallized audit provenance and are exempt from the halt scan by heading classifier. This prevents spurious halts when `/distill` drops the ephemeral audit table.

**False-halt mode:** Word-order-permuted equivalent lines will register as differing and trigger a halt. When this happens, the EM eyeballs the diff, confirms semantic equivalence, and proceeds with `--allow-drop` on that specific run. This is acceptable because the EM still sees the diff — the bypass becomes an inspection, not a rubber-stamp.

---

## Validation Prerequisite

Before declaring W4 production-ready, the rubric (steps 5a–5d + the negative AC set-diff logic) must be dry-run tested against a verbose, real-world spec produced by a full plan→review×2→chunk→enrich→review pipeline. The dry-run must show: (i) trim preview with diff of re-homed constraints, (ii) provenance block, (iii) deletion list for scaffolding, (iv) rewrite list for code/wiki references, (v) manual-review hits. This is a prerequisite AC; do not declare distill production-ready until it passes.

---

## Acceptance Criteria

- `/distill --dry-run` on a repo with a real spec + stubs shows: (i) trim preview with diff of re-homed constraints, (ii) provenance block, (iii) deletion list for scaffolding, (iv) rewrite list for code/wiki references, (v) manual-review hits.
- After real `/distill`: canonical spec at `archive/specs/`, stubs gone, wiki has provenance frontmatter, distillation-log appended.
- `git show <last_verbose_sha>:<original path>` retrieves verbose original.
- Post-distill `rg -F '<old-spec-path>'` returns zero hits across the entire repo.
- **Negative AC (silent-loss guard):** dry-run emits a content-drop diff. Halt-condition is set-diff, not raw match: an AC-shaped token line (`MUST`, `SHALL`, `AC:`, `Decision:`, `Constraint:`) in the drop-list halts dry-run only if no semantically-equivalent line exists in the re-homed additions OR in surviving ALLOWLIST sections. Cheap implementation: normalize whitespace + lowercase the token-bearing lines, set-diff drop-tokens vs kept-tokens, halt on non-empty difference. This prevents the muscle-memory bypass where every distill halts and operators default to `--allow-drop`. Word-order-permuted equivalent lines may trigger false halts; use `--allow-drop` after EM eyeballs the diff and confirms no semantic loss (see set-diff section). **`## Deviations` exemption:** AC-shaped token lines inside a `## Deviations` section are excluded from the set-diff scan by section-heading classifier — the `deviation` annotation has a kept equivalent in the corrected ALLOWLIST section's `SHIPPED: X (was: Y)` annotation; the `reason` and `commit` columns are intentionally non-crystallized audit, exempt from the halt scan.
- **Validation prerequisite:** rubric is dry-run tested against a verbose, real-world spec before declaring distill production-ready.
- Distillation log `state/distillation-log.md` row count is monotonically non-decreasing; strictly increases on any run that deletes scaffolding or archives a spec; schema header preserved verbatim; reason fields are domain-prose (≥8 words; ≥1 CONTEXT.md term when CONTEXT.md exists).
- Wiki provenance frontmatter includes `archived_spec`, `original_path`, `last_verbose_sha`, `distilled` — as real YAML frontmatter, not an HTML comment. Enforced via `SYNTH_SCHEMA`'s required per-file `provenance` object and the run's `provenance_completeness` report (§ 5b); that enforcement validates the *returned* objects, not that the frontmatter reached disk — confirming it landed is an EM-side check, not fully discharged by the mechanical enforcement alone.
- `## Decision Rationale` section present in archived spec (or sibling rationale file) for every spec that had DENYLIST content; rationale covers alternatives-considered + why this won per reviewer finding.
- Link-heal pass rewrites all three target types; `## Manual Review` section in distillation log captures unmatched-but-suspicious hits.
- **Vocabulary discipline AC (the Data Science Reviewer F2):** /distill manual-review log on a CONTEXT.md-bearing repo flags ≥1 vocabulary-drift hit on sampled executor output OR attests zero drift after sampling N≥3 modules.
- **Phase 2.5 exists** in `PIPELINE.md` as a defined phase with model assignment (Sonnet, parallel by topic-cluster) and dispatch instructions. Phase 2.5 runs after all Phase 2 topic-cluster agents complete and before Phase 3a dispatches.
- **Convergence threshold enforced:** Phase 2.5 emits a judgment proposal only when `convergence_count >= MIN_CONVERGENCE` across distinct plans (one finding per plan). The `--min-convergence=N` argument gates promotion; it is not advisory. Zero proposals when threshold not reached is correct behaviour, not a failure.
- **Update path is topic-key join, no re-`git show`:** when an existing `docs/wiki/codebase-judgment/<topic>.md` entry is present, Phase 2.5 matches new live findings against the existing topic key only — it does NOT re-`git show` prior `source_findings[*].sha` refs. The topic key is the stable join identifier. Full contract: `PIPELINE.md § D8`.
- **`judgment_provenance:` frontmatter on promoted entries:** every new `docs/wiki/codebase-judgment/<topic>.md` carries a `judgment_provenance:` frontmatter block (NOT `provenance:` — that key is taken by Phase 5b's archived-spec schema). Schema includes `kind`, `convergence_count`, `source_findings` (sidecar path + plan + reviewer + finding ID + SHA), `promoted`, `last_refreshed`. Full schema: `PIPELINE.md § Phase 2.5 — Frontmatter schema`.
- **Negative AC — `escalated-disagree` findings excluded:** a finding listed in the sidecar's appended `## Integrator Dispositions` bulk block under the `escalated-disagree:` bucket does NOT count toward convergence. Phase 2.5 reads the YAML `dispositions:` block at the END of the sidecar (per review-integrator agent prompt § Sidecar Disposition Annotation — single bulk block, not per-finding inline annotation) before Phase 5 deletes it. Validated via fixture where one of three matching findings is listed under `escalated-disagree:`; convergence count must be 2, no promotion.
- **Prior-art-checker dogfood:** dispatching prior-art-checker on a synthetic plan whose claim-shape matches a seeded judgment entry must produce a sidecar containing a Compatible-but-relevant or Conflict bucket entry referencing the `docs/wiki/codebase-judgment/` file by path. This is the end-to-end behaviour test confirming cached Opus-tier judgment surfaces to future plan authors.
- **AC11 — schema_version: 1 on every manifest:** every `dispositions:` (Phase 2), `dr_dedup:` (Phase 3b), `directory_entries:` (Phase 3c), and `deletions:` (Phase 3d) manifest carries `schema_version: 1` as its first key. Consumers must fail-loud on unknown forward versions. (The former Phase 2.7-QG verdict file is retired along with the Haiku wave it belonged to — the coverage gate is now a mechanical in-Workflow set-diff with no schema'd manifest of its own; its output is a `log()` line, see § Phase Overview.)
<!-- AC12-AC14 live in agent-prompts/phase-3d.md and tests/phase3d-fixtures/, not in this file's AC list — do not re-add them here. -->
- **AC15 — backward-compat (schema_version: 1):** Phase 5 consuming a `schema_version: 1` Phase 3d manifest (only `deletions:`, no `deletion_groups:`) succeeds — backward-compat invariant. A `schema_version: 2` manifest with `deletion_groups:` is the new canonical shape; the absence of that key on a v1 manifest is not an error.
- **AC16 — scout YAML block:** Phase 1 scout output includes a fenced YAML block with `artifact_paths:` list under each group section heading (EPHEMERAL / ALREADY_CAPTURED cluster sections). Phase 5 reads `artifact_paths:` from this YAML block — not from Markdown prose or glob — when expanding `deletion_groups:` entries in Phase 3d manifests.
- **AC17 — fanout sentinel:** if Phase 3d fanout fragments (`phase3d-fragment-*.md`) exist at the scratch path but no canonical assembled manifest is present at the canonical path, Phase 5 aborts with named error: "fanout assembly incomplete — N fragments found, no canonical manifest." Applies only when Phase 0 engaged Workflow-fanout mode (`N > 500` deletion-eligible candidates).
- **AC18 — disposal manifest scan-success gate (break-class):** a run whose Phase-1/2 scan success-rate falls below the threshold (default 90%) MUST NOT produce a Phase 3d deletion manifest — Phase 4 suppresses disposal entirely and reports the failed/total batch count + a `resumeFromRunId` remediation. Coverage-% alone (how much of the corpus the manifest claims to cover) is insufficient; the gate is on scans that actually succeeded, not on the manifest's self-reported completeness. See § Pre-Phase-4 — Disposal Manifest Scan-Success Gate.
- **AC19 — link-heal no-rewrite classes (provenance):** the § 5d link-heal pass MUST NOT rewrite: historical logs (`state/week-changelog/*`, `wsc/*.json` receipts, `review-trail/findings/*`), inbox-path provenance, or bare `source_memo:` basenames — these are point-in-time records, not live references. Active-ref scope for rewrite purposes is `docs/` + `tasks/` + `archive/` only. See § 5d. Link-Healing Pass — Expanded Coverage + No-Rewrite Classes.
- **AC20 — nugget source join-integrity gate (break-class):** a run whose `join_integrity.verdict` is `failed` (unjoinable rate above threshold, default 10% of distinct nugget sources) MUST NOT produce a Phase 3d deletion manifest — Phase 4 suppresses disposal entirely (`disposal_suppressed: true` + `disposal_suppressed_reason`) exactly as AC18's scan-success gate does; the additive tier is unaffected. A `finding` verdict (rate > 0, at or below threshold) does not suppress disposal but MUST be surfaced at the Phase 4 gate with the `unjoinable_sources[]` count and rate. See § Pre-Phase-4 — Nugget Source Join-Integrity Gate.
- **AC21 — distillation-log rows are Workflow-produced, not hand-derived:** `state/distillation-log.md` rows for a run that invoked `distill-harvest.workflow.js` MUST be `distillation_log_rows[]` entries appended verbatim, not EM-derived dispositions. A run that hand-derives rows (predates or bypasses the Workflow) MUST say so explicitly in its report, naming which rows were hand-derived. See § 5c — named producer.
- **Correction — the replay oracle for the join-integrity gate is the JOIN, not the dispositions.** Replaying run `2026-08-06-14h38`'s journal must reproduce 245 distinct nugget sources / 118 exact / 202 joined after repair / 43 unjoinable — that arithmetic is a pure function of the journal and is the correct regression oracle for AC20. The 182 `DISTILLED` / 69 `EPHEMERAL` / 6 `SKIP` rows that run actually logged are **NOT** a pure function of the journal — 20 joined sources were logged `EPHEMERAL` or `SKIP` under EM judgement, and a strict "nugget survived synth" rule reproduces 173 `DISTILLED`, not 182. This corrects nothing above (AC20/AC21 stand); it pins that any future AC citing those three disposition counts as a mechanical oracle would be pinning hand-assembly, not Workflow output.

---

## Relationship to Other Commands

| Command | When to use |
|---------|-------------|
| `/distill` | Extract knowledge into wiki docs, trim + archive canonical specs, delete scaffolding |
| `/update-docs` Phase 8b | Bulk prune without knowledge extraction — runs unconditionally under conservative thresholds (`pipelines/update-docs/artifact-pruning.md`) |

**Two meanings of "archive" — the load-bearing division.** "Archive" names two distinct lifecycles, and the two commands own one each:

- **Knowledge-archival (`/distill` owns the harvest; session-init sweep owns the move).** The session-init sweep performs the programmatic relocation — moving terminal plans (`status: implemented`/`superseded`/`abandoned`) from `docs/plans/` to `archive/specs/YYYY-MM/` as a cheap, unconditional mechanical step decoupled from any knowledge-extraction budget. `/distill` then drains harvest debt: for each RIPE plan in `archive/specs/` not yet in the distill-log, it trims the archived copy to its canonical skeleton and extracts knowledge into wiki/DR. Re-homing constraints (§ 5a) MUST precede trimming — this extraction-coupled discipline cannot be automated away. The trimmed spec is itself a canonical shape (RAG-greppable structure), complementary to the wiki's narrative.
- **Age-archival (`/update-docs` Phase 8b owns it).** Time-thresholded janitorial pruning of aged, non-knowledge-bearing artifacts. No extraction, no trim — just bulk cleanup once material crosses an age line.

The two are complementary, and the lineage is already partially documented: `/distill` extracts knowledge into wiki *before* the source material gets pruned (see § "For bulk pruning…" above) — filesystem hygiene is a distinct lifecycle from knowledge extraction (`/distill`) and artifact pruning (`/update-docs` Phase 8b). Run `/distill` when there's wiki-worthy knowledge in the artifacts about to age out; rely on `/update-docs` Phase 8b for routine bulk pruning.

**Ordering hazard (same shape as the cross-repo-memo 90d floor):** `/update-docs` Phase 8b age-deletes plans older than its retention floor. That floor MUST exceed the `/distill` cadence — otherwise age-archival could `git rm` a RIPE-but-unharvested plan before knowledge-archival extracts it (git history survives, but the wiki/DR promotion never runs). See `pipelines/update-docs/artifact-pruning.md` § Scope (plans row).

**Prior-art-checker:** Phase 2.5 judgment entries are written to `docs/wiki/codebase-judgment/`. Prior-art-checker consults this subdirectory (via recursive `docs/wiki/**/*.md` glob) on every plan check, so future plans receive cached Opus-tier judgment at Sonnet cost with zero additional wiring. See `agents/prior-art-checker.md` and `docs/wiki/prior-art-checker.md`.

The standalone `coordinator:artifact-consolidation` skill is absorbed into `/update-docs` Phase 8b; existing references should point at `pipelines/update-docs/artifact-pruning.md`.
