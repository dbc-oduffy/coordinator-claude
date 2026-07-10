---
name: distill
description: "Distill session artifacts into evergreen wiki + decisions; trim + archive canonical specs; delete scaffolding. Upstream of /update-docs pruning."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--dry-run] [--no-delete] [--min-convergence=N] [path]"
---

# Distill — Artifact Distillation Pipeline

Extract knowledge from accumulated session artifacts into evergreen wiki documents. Trim and archive canonical specs; delete scaffolding; write or update wiki entries. The archive is the long-term record; the wiki is the navigable present.

**Scope discipline — record-keeping, not cleanup.** `/distill` exists to capture the *shape* of what shipped, was decided, or happened, and canonicalize it into wiki form for future prior-art-checkers (any agent may consume). Concision and trimming serve **clarity**, not cleanliness — `/distill` is NOT a disposal route for trash the EM didn't delete at workstream-complete time. Three disposal mechanisms are distinct and non-substitutable:

- **Layer 1 (mechanical, age-gated)** — `bin/cruft-sweep.sh` (name + age + fingerprint anchors).
- **Layer 2 (on-demand judgment scan)** — `/cruft-sweep` skill (registry-diff + confirm-needed names).
- **Layer 3 (front-line judgment, fresh context)** — EM self-clean at `/workstream-complete` Step 2.67 (this session's transient scratch the EM authored — runs first in lifecycle order, before Layers 1 and 2 ever see the residue).

`/distill` and `/update-docs` are NOT a substitute for any of those layers — they extract knowledge and index canonical artifacts. → `docs/wiki/cruft-sweep-cadence.md` § Three-layer design.

**Plan files are a high-value distillation source alongside wiki entries and archived handoffs.** Terminal plan documents are moved to `archive/specs/` by the session-init sweep; `/distill` reads them from there as harvest debt. Plans — especially those with `(was: <plan-forecast>)` ALLOWLIST corrections from `/workstream-complete` Step 2.4 (and, on historical plans, `## Deviations` audit tables) — carry the shipped-vs-forecast reality that future prior-art-checkers consume. The four-fate table below describes the plan cohort as sourced from `archive/specs/` (already relocated by the sweep); the table treats plans as one of four equal categories, but plans + divergence corrections are the source future prior-art-checkers will read most often.

**Four categories, four fates:**

| Artifact | Fate | Rationale |
|---|---|---|
| Canonical plan / spec (`archive/specs/**/*.md`) — **RIPE only** | **Harvest knowledge → record in distill-log** | The session-init sweep already moved terminal plans (`status: implemented`/`superseded`/`abandoned`) from `docs/plans/` to `archive/specs/YYYY-MM/`. `/distill` reads the un-harvested subset (plans in `archive/specs/` minus paths already in `docs/wiki/.distill-log.md` — the "harvest debt") and extracts knowledge into wiki/DR. **Only RIPE (delivered) plans are harvested** — ripeness classified by the `plan-delivery-audit` Oracle (`skills/plan-delivery-audit/SKILL.md:128-136`): `status: implemented`/`shipped` + ACs-pass-at-HEAD → RIPE. PARTIAL and ABANDONED plans are SKIP (un-harvested, retained in `archive/specs/`); IN-FLIGHT plans are not in this cohort (they stay in `docs/plans/`, not yet swept) — see `PIPELINE.md` § Phase 0 ripeness gate. |
| Enriched stubs, reviewer outputs, integrator triage, docs-checker reports | **Delete** | Pure scaffolding. Recoverable from git via distillation log. |
| Wiki entries (`docs/wiki/*.md`) | **Write/update** | What-and-why summary. Carries provenance frontmatter. |
| Archived handoffs (`archive/handoffs/*.md`) — added 2026-05-08 | **Resolved/shipped → Extract → delete (opt-out via `--no-delete`). Unresolved / abandoned / missing-`shipped_in:` → Retain un-harvested (SKIP).** | Post-`/pickup` paper trail. Extract-eligible only when `status: consumed` AND `shipped_in:` present AND NOT `deployment_state: abandoned` (no supersession lineage); superseded / abandoned / missing-`shipped_in:` handoffs are retained un-harvested, not extracted or deleted. Harvest gate composes with (and is stricter than) the Phase 5 delete-guard #2 (`shipped_in:` required for deletion) — it gates *harvest*, not just deletion. See § Handoff distillation below. |

**Reference:** Full pipeline design in `${CLAUDE_PLUGIN_ROOT}/pipelines/artifact-distillation/PIPELINE.md`. Agent prompt templates in `agent-prompts/` (per-phase fragments); thin index at `agent-prompts.md`.

**Out-of-scope actions for all dispatched agents in this pipeline:** DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find yourself reaching for a merge, STOP and surface the question to the EM in your final reply. The EM merges via `/merge-to-main`; distill agents do not.

**Announce at start:** "I'm running `/distill` to extract knowledge from [N artifacts / artifacts in path] into wiki documents."

**For bulk pruning without knowledge extraction:** that lives in `/update-docs` Phase 8b (`pipelines/update-docs/artifact-pruning.md`) — runs unconditionally on every `/update-docs` invocation under conservative thresholds. `/distill` extracts knowledge into wiki *before* the source material gets pruned. Use `/distill` when you want the knowledge before discarding the source; rely on `/update-docs` Phase 8b for the raw cleanup.

---

## Arguments

`$ARGUMENTS` may include any combination of:

**`--dry-run`**
Run Phases 0-3d only. Preview extraction results and the deletion manifest, but apply nothing to disk. Presents the summary at Phase 4 and stops. Use to verify what would be extracted before committing.

**`--no-delete`**
Apply wiki updates (Phases 0-5 write steps), but skip scaffolding deletion AND skip trimming specs in `archive/specs/` (specs already moved there by the session-init sweep remain un-trimmed). Wiki writes still apply.

**`--allow-drop`**
Bypass the negative-AC halt for this run after EM eyeballs the diff and confirms no semantic loss. Logs the bypass to distillation-log.md Manual Review section for audit.
<!-- Review: the Staff Engineer R3 — F3: --allow-drop was referenced in the set-diff section but absent from Arguments; F6: dropped stale "Previously:" migration commentary from --no-delete -->

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

```
Phase 0 (Coordinator) → Phase 1 (Haiku ×N, parallel) → Phase 1.5 (Haiku ×N, QG)
  → [Clustering] → Phase 2 (Sonnet ×M, parallel) → Phase 2.5 (Sonnet ×K, parallel)
  → Phase 2.7-QG (Haiku ×M, parallel by cluster — coverage gate)
  → Phase 3a (Sonnet ×C, parallel by cluster) → [cross-cluster-check] → [Esc: Opus + fidelity-check (Sonnet), if needed]
  → Phase 3b (Sonnet, single) → Phase 3c (Coordinator, mechanical) → Phase 3d (Sonnet, single)
  → Phase 4 (PM gate) → Phase 5 (Coordinator, apply + trim/archive + delete scaffolding)
```

| Phase | Model | Purpose |
|-------|-------|---------|
| **Phase 0** | Coordinator | Inventory artifacts, catalog formats, read existing wiki, group into batches, generate run ID |
| **Phase 1** | Haiku (parallel) | Scan each batch — extract knowledge nuggets (`[DECISION]`, `[KNOWLEDGE]`, `[EPHEMERAL]`, `[AMBIGUOUS]`) |
| **Phase 1.5** | Haiku (parallel) | Quality gate — verify Phase 1 coverage, template compliance, and path spot-checks |
| **Clustering** | Coordinator or Haiku | Regroup nuggets from input-batch ordering to output-topic ordering |
| **Phase 2** | Sonnet (parallel) | One agent per guide topic — synthesize nuggets into guide content and decision records; emits `dispositions:` YAML frontmatter covering all assigned nugget IDs (schema: `agent-prompts/phase-2.md`) |
| **Phase 2.5** | Sonnet (parallel) | Mine reviewer sidecars for cross-spec convergence patterns; emit promotion proposals to scratch (`state/scratch/artifact-distillation/{run-id}/judgment-proposals.md`). Full contract: `PIPELINE.md § Phase 2.5`. |
| **Phase 2.7-QG** | Haiku (parallel by cluster) | Coverage gate — set-diff of `dispositions:` nugget IDs vs. assigned nugget IDs; PASS continues pipeline; FAIL triggers Phase 2 re-run (retry cap: 2 per cluster) |
| **Phase 3a** | Sonnet (parallel by cluster) | Contradiction detection — one agent per topic cluster; coordinator cross-cluster check post-3a; Opus escalation if unresolvable contradictions found, followed by Sonnet fidelity-check verifying all source nugget IDs cited |
| **Phase 3b** | Sonnet (single) | Decision-record dedup — collect all Phase 2 DRs, produce deduplicated canonical set + `dr_dedup:` YAML manifest (schema: `agent-prompts/phase-3b.md`) |
| **Phase 3c** | Coordinator (mechanical) | `DIRECTORY_GUIDE.md` assembly — read Phase 2 frontmatter + Phase 0 wiki inventory, write `directory_entries:` YAML manifest + prose preview; no subagent |
| **Phase 3d** | Sonnet (single) | Deletion manifest — per-file `deletions:` YAML block and (schema v2) grouped `deletion_groups:` sibling key; >50-row self-check switches bulk EPHEMERAL/ALREADY_CAPTURED to grouped form; prose table is derived PM-readable view. Full schema: `agent-prompts/phase-3d.md` |
| **Phase 4** | Coordinator | PM approval gate — present deletion manifest + DIRECTORY_GUIDE.md preview, wait for explicit approval |
| **Phase 5** | Coordinator | Apply wiki writes via manifest-driven done-conditions (file-path set-diff vs. `git diff --stat`); **drain harvest debt from `archive/specs/` first and bank it (harvest-debt drain contract, see § Phase 5 intro)** — including **Decision Rationale extraction** (§ 5a, required); delete scaffolding via YAML `deletions:` manifest; update distillation log; run link-heal pass |
<!-- Review: the Staff Engineer R3 — F1: Phase 5 row omitted Decision Rationale extraction; an executor scanning the overview without reading 5a could miss it -->

**If `--dry-run`:** Phases 4-5 are skipped. The pipeline stops after Phase 3d and presents the summary.

**If `--no-delete`:** Phase 5 applies wiki writes and commits, but skips scaffolding deletion and spec archival.

---

## Handoff distillation (added 2026-05-08)

Spec backlink: `archive/specs/2026-05/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` § Phase 4.

### Input enumeration

Distill enumerates archived handoffs via:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
"$_cc_root/bin/query-records.sh" --type handoff-archived --format paths
```

NOT a raw `find archive/handoffs/ -name '*.md'`. Using `query-records` preserves frontmatter validation (each handoff is checked against `schemas/handoff-archived.yaml`) and provenance metadata (workstream, predecessor, deployment_state). Same enumeration discipline as `--type plan` for `docs/plans/`.

### Extraction targets

| Source content | Target | Notes |
|---|---|---|
| Substantive `## Key Decisions Made` section with reasoning | DR in `docs/decisions/` | Existing pattern (Phase 5b provenance frontmatter applies) |
| Reusable cross-cutting patterns / lessons | Wiki entry in `docs/wiki/` | New `archived_handoff:` provenance key — see schema below |
| Neither (only mechanical sections like `## Files Modified`) | No extraction | Eligible for delete under Phase 5 safety guards |

**Scaffolding new DRs:** use `coordinator-doc-new --type decision --title "<title>" --out docs/decisions/DR-<NNN>-<slug>.md` to generate conformant frontmatter (`id`, `title`, `created`, `status`, `deciders`) from `schemas/decision.yaml`. The canonical identity key is `id`; the canonical temporal key is `created` (not `date`).

### Provenance frontmatter — new `archived_handoff:` key

Per DR-053, `archived_handoff:` is a **new top-level key**, NOT a sub-key under `provenance:` (that key is taken by Phase 5b's archived-spec schema as a list-of-objects with `path` + `last_verbose_sha`; collision would break schema-based dispatch).

```yaml
archived_handoff:
  - path: archive/handoffs/2026-05-04_140000_some-workstream.md
    workstream: some-workstream
    last_verbose_sha: a1b2c3d
    distilled: 2026-05-08
```

Sibling key to `provenance:` (specs) and `judgment_provenance:` (codebase-judgment entries).

### Delete safety (mandatory; opt-out is `--no-delete`)

**Doctrine reversal — confirmed opt-out 2026-05-08.** The prior `/workday-complete` line ("Delete handoffs. Never deleted — archived only after `/distill` with PM approval") is reversed. New policy: `/distill` deletes by default after extraction; `--no-delete` overrides for specific runs.

A handoff is eligible for delete in Phase 5 ONLY if all four guards pass:

1. **Extraction-artifact present.** At least one DR (in `docs/decisions/`) or wiki entry (in `docs/wiki/`) was written this run referencing the source via `archived_handoff:` provenance frontmatter, OR the handoff is empirically content-free (only `## Files Modified This Session`, no decisions / blockers / next-steps).
2. **`shipped_in:` present.** A handoff in `archive/handoffs/` lacking `shipped_in:` (commit SHA or PR ref) cannot be deleted — surface to PM with the missing-paper-trail diagnosis. This catches handoffs that were archived but whose work did not actually ship; deleting would erase the only record of the orphan workstream. `shipped_in:` is set by `/pickup` (rare — only when the SHA is known) or by the picking-up session's `/handoff` or `/workstream-complete` (normal case).
3. **Active-reference check (per `docs/wiki/cleanup-sweep-hazards.md` §1).** Ripgrep `archive/handoffs/<basename>.md` references across `docs/`, `tasks/`, `archive/specs/`, and plugin sources. Any active reference (i.e., not in another to-be-deleted file) blocks deletion of that handoff. Cleanup is higher-risk than it looks — a citation from an active spec must not silently dangle.
4. **Distillation-log row.** Same ≥8-word domain-prose requirement as existing scaffolding rows (per Phase 5c). Reason field describes why the handoff content was decision-bearing or content-free.

Git history remains the permanent paper trail. Use `git show <last_verbose_sha>:<original-path>` to recover the verbose handoff text.

### Phase 5d link-heal extension

Add `archive/handoffs/<basename>.md` to the path-rewrite ripgrep set. Healing target: any cross-reference from wiki/DR to a now-deleted archived handoff gets rewritten to the wiki/DR that absorbed it (with parenthetical `(formerly archive/handoffs/<basename>.md @ <sha>)`).

---

## Cross-repo archive distillation (added 2026-05-23)

Spec backlink: `archive/specs/2026-05/2026-05-23-cross-repo-inbox-archive-restructure.md` § D3 + § Chunk E.

### Input enumeration

Distill enumerates closed cross-repo memos via a direct glob — `cross-repo/archive/*.md` — filtered to files whose frontmatter carries `status: actioned`. There is no `query-records` type for cross-repo memos; use Glob + frontmatter parse directly (the same approach as the workday-start surface query uses for inbox memos).

Do NOT enumerate `cross-repo/inbox/*.md` — active memos in the inbox are never distillation candidates; they are in-flight channel traffic, not closed historical artifacts.

### Extraction targets

| Source content | Target | Notes |
|---|---|---|
| Cross-repo decisions with lasting architectural significance | DR in `docs/decisions/` | E.g. "project-rag confirmed co-located archive over top-level archive/cross-repo/" — rare |
| Cross-cutting patterns surfaced in a memo thread | Wiki entry in `docs/wiki/` | E.g. a sequence of memos that converged on a new installation discipline |
| Neither (routine actioned memos with no evergreen content) | No extraction | Eligible for delete under Phase 5 safety guards |

**Scaffolding new DRs:** same as handoff distillation — `coordinator-doc-new --type decision --title "<title>" --out docs/decisions/DR-<NNN>-<slug>.md`; canonical keys are `id` and `created`.

**Extraction is rare.** Most cross-repo memos are coordination records — they do not contain architectural decisions worth promoting. The overwhelming majority are `→ DELETE` (routine coordination extracted to `[EPHEMERAL]`). The distill agent must resist the impulse to force-promote; only genuinely evergreen cross-repo decisions earn wiki or DR entries.

### Provenance frontmatter — `cross_repo_memo:` key

Wiki or DR entries promoted from a cross-repo memo carry:

```yaml
cross_repo_memo:
  - path: cross-repo/archive/2026-05-23-gate-check-fix.md
    from: project-rag-em
    to: claude-central-em
    distilled: 2026-05-23
```

Sibling key to `archived_handoff:` (handoff distillation) and `provenance:` (archived-spec distillation). Do NOT use `provenance:` — that key is taken by Phase 5b's archived-spec schema.

### Delete safety (same four guards as handoff distillation)

A cross-repo archive memo is eligible for delete in Phase 5 ONLY if all four guards pass:

1. **Extraction-artifact present OR empirically content-free.** At least one DR or wiki entry was written this run referencing the source via `cross_repo_memo:` provenance frontmatter, OR the memo is routine coordination with no decisions or patterns (the common case — classify as `[EPHEMERAL]`).
2. **`status: actioned` confirmed.** A memo without `status: actioned` is not yet closed channel traffic — do NOT delete. Surface to PM with a "memo not yet actioned" note.
3. **Active-reference check.** Ripgrep the memo filename across `docs/`, `tasks/`, `archive/`, and plugin sources. Any live cite blocks deletion — the memo is still being referenced.
4. **Distillation-log row.** Same ≥8-word domain-prose requirement as existing scaffolding rows (per Phase 5c). Reason field describes the memo content or states "routine coordination, no evergreen content."

Git history remains the permanent record. The `cross-repo/archive/` path is git-tracked (per D5 — inbox + archive both have committed READMEs); `git log -- cross-repo/archive/<filename>` retrieves the full history.

### Phase 5d link-heal extension (cross-repo memos)

Add `cross-repo/archive/<basename>.md` to the path-rewrite ripgrep set alongside archived handoffs. Healing target: any cross-reference from wiki/DR to a now-deleted archived memo gets rewritten to the wiki/DR that absorbed it (with parenthetical `(formerly cross-repo/archive/<basename>.md @ <sha>)`). Cross-repo memos that were purely coordination records with no extraction will not have a rewrite target — those references should simply be deleted rather than repointed.

---

## Phase 4 — PM Gate: Atlas Staleness Advisory (sensor, non-blocking)

Before presenting the deletion manifest at the Phase 4 PM gate, `/distill` runs a **read-only atlas staleness check** and, if warranted, surfaces a one-line advisory. **`/distill` is the sensor; `/architecture-audit` is the actuator** — distill NEVER invokes the audit, NEVER blocks on the result, and NEVER writes the atlas. The advisory simply lets the PM choose to refresh the architecture map *before* the source material being mapped is buried. The two skills stay separate (no fusion, no breadcrumb lay-up). Doctrine source for the sensor/actuator split: `docs/wiki/atlas-watch-script-convention.md` (this is a third read-only consumer of the sensor, after `/architecture-audit` Step 1 and `/workweek-complete`); DR-153, DR-154.

**Procedure:**

1. **Run the sensor:** `bash ${CLAUDE_PLUGIN_ROOT}/bin/check-atlas-watch-drift.sh` (pure read, always exits 0; emits one `FRESH|DRIFT|MISSING|STALE <system> …` line per atlas page).
2. **Map this run's churn to atlas systems** via a **simple keyword/path-prefix map** (explicitly NOT a pluggable predicate framework — aligns with `atlas-watch-script-convention.md` non-goal). **The churn set is the file paths the run's RIPE plans actually MODIFIED** — read from each ripe plan's `File Lists` / `## Files` section (or the commit range that shipped it), NOT the plan's own `docs/plans/…` filename — **plus subsystem references in the archived handoffs being processed.** Match those modified-file paths against the path-prefix column below. (Maintenance: keep the 7 rows reconciled with the atlas system pages `check-atlas-watch-drift.sh` enumerates from `docs/architecture/systems/*.md` — when a system page is added, add a row.) Seed map (heuristic — extend as systems are added):

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

**Harvest-debt drain ordering contract (the plan-priority rule).** The session-init sweep has already moved terminal plans to `archive/specs/` — the MOVE is decoupled from `/distill`. What `/distill` Phase 5 does is drain the harvest debt: plans in `archive/specs/` not yet in `docs/wiki/.distill-log.md` are the un-harvested set, and knowledge-harvest (§ 5a) is the heaviest, most-likely-to-be-skipped sub-step — so it runs **first and is banked (committed or staged) before any ephemera deletion**. The order is: (1) apply wiki/DR writes, (2) **harvest the ripe-plan cohort from `archive/specs/` (§ 5a) and commit that**, (3) only then delete scaffolding/handoffs/memos. A budget-truncated run must drain harvest debt before the disposal tier — the cheap mechanical deletion never preempts the expensive knowledge-harvest. This directly counters the "apply-agent silently drops the transform when budget tightens" failure noted under § 5a Apply-agent slice rubric.

Phase 5 has four major sub-steps. They run in order; each depends on the prior.

### 5a. Spec Knowledge Harvest — Structural Rubric

Canonical specs in the harvest-debt set (`archive/specs/**/*.md` not yet in `docs/wiki/.distill-log.md`) are read for knowledge extraction. The specs are already at their final `archive/specs/YYYY-MM/<name>.md` location — the session-init sweep handled the move. `/distill`'s job here is trimming post-review scaffolding from the archived copy and writing wiki/DR content — **the MOVE is a done fact; this sub-step is purely knowledge-harvest and trim-in-place**. (Month-foldering keeps `archive/specs/` navigable as it grows past ~100 entries; the `YYYY-MM` segment is derived mechanically from the leading `YYYY-MM-DD` of the spec filename.)

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
<!-- Review: deviation-reconciliation plan D6, refined per session-end code-reviewer Finding 7 — corrected line crystallizes shipped shape X; (was: Y) is inline supersession provenance. Phase 1 [SUPERSEDED] class = cross-artifact reversal, not inline-(was:) parsing. Spec: archive/specs/2026-05-26-session-end-deviation-reconciliation-gate.md § D6 -->

**DENYLIST sections — strip after re-homing + rationale extraction:**
- "Reviewer Plan"
- "the Staff Engineer Round N Findings"
- "the Data Science Reviewer/the Game Dev Reviewer Findings"
- "Integrator Triage"
- "Docs-Checker Pass"
- "Open Questions (resolved)"
- "Scope-Expansion Side-Channel" / "Heavy-Investment Pass" wrappers
- `## Deviations` — drop fate: `[EPHEMERAL]`. **Exception: re-homing step is skipped for this section only** (see bounded clause under Re-homing step below).
<!-- Review: deviation-reconciliation plan Chunk 2 — ## Deviations is audit-only, intentionally non-crystallized; the crystallized equivalent lives in the corrected ALLOWLIST sections' SHIPPED: X (was: Y) annotations; defined in docs/wiki/plan-deviation-reconciliation.md -->

**MIDDLE — keep + flag for EM eyeball in dry-run:** any section heading not matching either list above. Do not auto-strip; surface in dry-run for EM decision.

**Re-homing step (mandatory before any DENYLIST section is stripped):**

For every DENYLIST section, scan it for content introducing a constraint, AC, or decision that does not appear in any ALLOWLIST section. Each such item must be re-homed into the appropriate ALLOWLIST section (typically Acceptance Criteria or Decisions Made) before the wrapper is stripped. Re-homing produces a diff in the trim preview that the EM reviews at Phase 4. Do not strip before the EM has approved the re-homing diff.

**Bounded re-homing exemption — `## Deviations` only:** The re-homing scan is skipped ONLY for sections whose heading EXACTLY matches `## Deviations` (the audit-only, intentionally non-crystallized section defined in `docs/wiki/plan-deviation-reconciliation.md`). The crystallized equivalent of every deviation already lives in the corrected ALLOWLIST sections' `SHIPPED: X (was: Y)` annotations — re-homing would produce duplicate provenance. ALL OTHER DENYLIST sections retain the unconditional re-homing scan above. This is a single-heading exemption, not a general "audit-style sections skip re-homing" policy; future section types do not fall through it. The wiki (`plan-deviation-reconciliation.md`) defines exactly one heading — `## Deviations` — with no variants; the exemption does NOT auto-follow the wiki, so if heading variants are ever added there, this clause must be updated in lockstep.
<!-- Review: deviation-reconciliation plan Chunk 2 AC4 — first exception to the unconditional re-homing rule; pinned to exact heading match only. Forward-maintenance note added per session-end code-reviewer Finding 1. -->

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
<!-- Review: the Staff Engineer R3 — F0: steps 2+3 both operate on the pre-strip spec; step 3 sources rationale FROM DENYLIST sections, so stripping (step 4) must follow both; preconditions made explicit -->

---

### 5b. Provenance Frontmatter on Wiki Entries

Every wiki entry produced by or updated during a distill run that summarizes a now-archived spec must carry provenance frontmatter:

```yaml
provenance:
  - archived_spec: archive/specs/2026-04/2026-04-29-port-patterns-implementation.md
    original_path: docs/plans/2026-04-29-port-patterns-implementation.md
    last_verbose_sha: acc49ed5
    distilled: 2026-04-29
```

`archived_spec:` carries the **month-foldered** post-move path (`archive/specs/YYYY-MM/<name>.md`); `original_path:` retains the **pre-move** `docs/plans/` path verbatim (it is correct as a historical reference and is NOT a link-heal target — see § 5d carve-out).

**Retrieval recipes (in order of preference):**
1. Read the trimmed archived spec at `archive/specs/YYYY-MM/<name>.md` — covers structure, decisions, and rationale.
2. For verbose original (review history, integrator chatter): `git show <last_verbose_sha>:<original_path>`.

---

### 5c. Distillation Log — Schema-Pinned, Append-Only

Path: `state/distillation-log.md` (per-project). Created on first distill run; populated with new rows on every subsequent run.

**Schema header — executor MUST preserve verbatim when writing to the log:**

```
# Distillation Log
# Append-only. Each row = one deleted scaffold OR one archived spec.
# Columns: date | action | path | last_sha | belongs_to_spec | reason
#
# `reason` field MUST be domain-prose using CONTEXT.md vocabulary, not a process tag.
#   Bad:  "scaffolding"
#   Good: "integrator triage resolving async-run wrapper conflict in port-patterns FastMCP transport"
# Minimum: ≥8 words. If CONTEXT.md exists, ≥1 CONTEXT.md term required.
```

**Append-only contract:** Read existing rows first. Append new rows. NEVER rewrite existing rows. Row count is monotonically non-decreasing; strictly increases on any run that deletes scaffolding or archives a spec. This is an AC.
<!-- Review: the Staff Engineer R3 — F5: "strictly increase" fails on a no-op run; reworded to monotonically non-decreasing with strict increase on runs that actually act -->

**Mirroring:** For highest-value scaffolds (the canonical spec itself), the distillation log row is also mirrored into the wiki provenance frontmatter as redundancy.

**Why prose-shaped reason fields:** The log itself becomes index-bait. RAG indexes the on-disk filesystem; a log row reading "scaffolding" is invisible to retrieval, but a row reading "integrator triage resolving async-run wrapper conflict in port-patterns FastMCP transport" surfaces on a query about that conflict and gives the future EM a `last_sha` to retrieve the verbose original. The log carries history forward into the retrieval surface — cheapest mitigation for the "git history is out-of-band for RAG" recall hole.

**Vocabulary discipline AC (per the Data Science Reviewer F2):** On a CONTEXT.md-bearing repo, the manual-review log section of `state/distillation-log.md` must either flag ≥1 vocabulary-drift hit in sampled executor output OR explicitly attest zero drift after sampling N≥3 modules. Without this, vocabulary discipline is aspirational rather than validated.

---

### 5d. Link-Healing Pass — Expanded Coverage

After specs are moved and scaffolding is deleted, stale references exist across the codebase. The link-heal pass finds and rewrites them.

**Targets to rewrite:**
- Canonical spec path (`docs/plans/foo.md`, with or without `§` section refs) → month-foldered `archive/specs/YYYY-MM/<new>.md`
- **Pre-existing flat archived-spec references** (`archive/specs/<name>.md`, from before month-foldering) → `archive/specs/YYYY-MM/<name>.md`. **`spec_backlink:` frontmatter/field references are a NAMED non-hyperlink heal-target class** — they are NOT markdown links, so the generic ripgrep link-set misses them; grep `spec_backlink:\s*archive/specs/` explicitly and rewrite each to the foldered path.
- Deleted stub paths (`tasks/<feature>/stubs/*.md`) → wiki target with parenthetical `(formerly tasks/<feature>/stubs/P1-A.md @ <sha>)`
- Intra-spec references inside the archived spec itself pointing to sibling stubs that were just deleted (second pass on the trimmed spec after archival)

**Carve-out — paths that legitimately RETAIN the flat/pre-move form (do NOT rewrite):** `original_path:` lines (intentionally the pre-move `docs/plans/…` path), `provenance:` blocks, `state/distillation-log.md` rows, and `git show <sha>:<original_path>` retrieval-recipe lines. (Note: `archived_spec:` is NOT in this carve-out for a different reason — post-migration it already carries the month-foldered path, so it is not a stale ref needing either rewrite or exemption.) These intentionally preserve the pre-move path as a historical reference (per § 5b). Scope the heal to **link contexts** (markdown link targets + `spec_backlink:`); exclude provenance/log/recipe lines as an architectural carve-out, not a glob afterthought.

**Tooling:** `ripgrep --multiline --multiline-dotall` covering file types `md, json, yaml, yml, ps1, sh, py, ts, js, txt`. Scan: `.claude/`, `tasks/`, `docs/`, `archive/`, plugin dirs, repo root configs.

**Pre-deletion active-reference check.** Before `rm -rf` any `tasks/<dir>/`, grep references first; shipped-status alone does not mean unreferenced. Halt deletion on any live cite.

**Anchor the link-heal regex around path boundaries.** Sed-style rewrites over-rewrite `original_path:` and other frontmatter fields where the literal old path is semantically correct; anchor the pattern or restore frontmatter post-sweep.
<!-- Review: the Staff Engineer R3 — F4: plain --multiline does not make . match newlines; --multiline-dotall required for cross-line patterns -->

**Heal-log:** Under a `## Manual Review` section in `state/distillation-log.md`, write EVERY unmatched-but-suspicious hit — anything containing `docs/plans/`, `tasks/<feature>/stubs/`, or the deleted-path basenames — for EM eyeball. The EM reviews the Manual Review section before declaring the run complete.

---

## tasks/ vs state/ — aggressive sweep boundary

Spec backlink: `archive/specs/2026-06/2026-06-08-tasks-state-folder-split.md` § C5.

**`state/`** — load-bearing session substrate (queues, trackers, ledgers, handoffs, review-trail, recheck markers, etc.). **Never swept by `/distill`.** Surgical edits only, each named per-surface (e.g. `coordinator:learn-lessons` writes `state/lessons.md`; no archival by this command). If a path begins with `state/`, it is out of scope — full stop.

**`tasks/`** — Tasks-API UUID flight-recorder dirs, dated reports, dated topic dirs, and loose scratch. `/distill` sweeps here aggressively:

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
<!-- Review: deviation-reconciliation plan Chunk 2 AC5 — heading-classifier exemption prevents spurious halt on intentionally dropped ## Deviations table; equivalent crystallized content is in ALLOWLIST SHIPPED annotations -->

**False-halt mode:** Word-order-permuted equivalent lines will register as differing and trigger a halt. When this happens, the EM eyeballs the diff, confirms semantic equivalence, and proceeds with `--allow-drop` on that specific run. This is acceptable because the EM still sees the diff — the bypass becomes an inspection, not a rubber-stamp.
<!-- Review: the Staff Engineer R3 — F2: set-diff normalization is weaker than the plan's 'semantically-equivalent line' intent; word-order permutations register as different and trigger spurious halts -->

---

## Validation Prerequisite

Before declaring W4 production-ready, the rubric (steps 5a–5d + the negative AC set-diff logic) must be dry-run tested against `docs/plans/2026-04-29-port-patterns-implementation.md` — a verbose, real-world spec produced by a full plan→review×2→chunk→enrich→review pipeline. The dry-run must show: (i) trim preview with diff of re-homed constraints, (ii) provenance block, (iii) deletion list for scaffolding, (iv) rewrite list for code/wiki references, (v) manual-review hits. This is a prerequisite AC; do not declare distill production-ready until it passes.

---

## Acceptance Criteria

- `/distill --dry-run` on a repo with a real spec + stubs shows: (i) trim preview with diff of re-homed constraints, (ii) provenance block, (iii) deletion list for scaffolding, (iv) rewrite list for code/wiki references, (v) manual-review hits.
- After real `/distill`: canonical spec at `archive/specs/`, stubs gone, wiki has provenance frontmatter, distillation-log appended.
- `git show <last_verbose_sha>:<original path>` retrieves verbose original.
- Post-distill `rg -F '<old-spec-path>'` returns zero hits across the entire repo.
- **Negative AC (silent-loss guard):** dry-run emits a content-drop diff. Halt-condition is set-diff, not raw match: an AC-shaped token line (`MUST`, `SHALL`, `AC:`, `Decision:`, `Constraint:`) in the drop-list halts dry-run only if no semantically-equivalent line exists in the re-homed additions OR in surviving ALLOWLIST sections. Cheap implementation: normalize whitespace + lowercase the token-bearing lines, set-diff drop-tokens vs kept-tokens, halt on non-empty difference. This prevents the muscle-memory bypass where every distill halts and operators default to `--allow-drop`. Word-order-permuted equivalent lines may trigger false halts; use `--allow-drop` after EM eyeballs the diff and confirms no semantic loss (see set-diff section). **`## Deviations` exemption:** AC-shaped token lines inside a `## Deviations` section are excluded from the set-diff scan by section-heading classifier — the `deviation` annotation has a kept equivalent in the corrected ALLOWLIST section's `SHIPPED: X (was: Y)` annotation; the `reason` and `commit` columns are intentionally non-crystallized audit, exempt from the halt scan.
- **Validation prerequisite:** rubric is dry-run tested against `docs/plans/2026-04-29-port-patterns-implementation.md` (verbose, real-world) before declaring distill production-ready.
- Distillation log `state/distillation-log.md` row count is monotonically non-decreasing; strictly increases on any run that deletes scaffolding or archives a spec; schema header preserved verbatim; reason fields are domain-prose (≥8 words; ≥1 CONTEXT.md term when CONTEXT.md exists).
- Wiki provenance frontmatter includes `archived_spec`, `original_path`, `last_verbose_sha`, `distilled`.
- `## Decision Rationale` section present in archived spec (or sibling rationale file) for every spec that had DENYLIST content; rationale covers alternatives-considered + why this won per reviewer finding.
- Link-heal pass rewrites all three target types; `## Manual Review` section in distillation log captures unmatched-but-suspicious hits.
- **Vocabulary discipline AC (the Data Science Reviewer F2):** /distill manual-review log on a CONTEXT.md-bearing repo flags ≥1 vocabulary-drift hit on sampled executor output OR attests zero drift after sampling N≥3 modules.
- **Phase 2.5 exists** in `PIPELINE.md` as a defined phase with model assignment (Sonnet, parallel by topic-cluster) and dispatch instructions. Phase 2.5 runs after all Phase 2 topic-cluster agents complete and before Phase 3a dispatches.
- **Convergence threshold enforced:** Phase 2.5 emits a judgment proposal only when `convergence_count >= MIN_CONVERGENCE` across distinct plans (one finding per plan). The `--min-convergence=N` argument gates promotion; it is not advisory. Zero proposals when threshold not reached is correct behaviour, not a failure.
- **Update path is topic-key join, no re-`git show`:** when an existing `docs/wiki/codebase-judgment/<topic>.md` entry is present, Phase 2.5 matches new live findings against the existing topic key only — it does NOT re-`git show` prior `source_findings[*].sha` refs. The topic key is the stable join identifier. Full contract: `PIPELINE.md § D8`.
- **`judgment_provenance:` frontmatter on promoted entries:** every new `docs/wiki/codebase-judgment/<topic>.md` carries a `judgment_provenance:` frontmatter block (NOT `provenance:` — that key is taken by Phase 5b's archived-spec schema). Schema includes `kind`, `convergence_count`, `source_findings` (sidecar path + plan + reviewer + finding ID + SHA), `promoted`, `last_refreshed`. Full schema: `PIPELINE.md § Phase 2.5 — Frontmatter schema`.
- **Negative AC — `escalated-disagree` findings excluded:** a finding listed in the sidecar's appended `## Integrator Dispositions` bulk block under the `escalated-disagree:` bucket does NOT count toward convergence. Phase 2.5 reads the YAML `dispositions:` block at the END of the sidecar (per review-integrator agent prompt § Sidecar Disposition Annotation — single bulk block, not per-finding inline annotation) before Phase 5 deletes it. Validated via fixture where one of three matching findings is listed under `escalated-disagree:`; convergence count must be 2, no promotion.
- **Prior-art-checker dogfood:** dispatching prior-art-checker on a synthetic plan whose claim-shape matches a seeded judgment entry must produce a sidecar containing a Compatible-but-relevant or Conflict bucket entry referencing the `docs/wiki/codebase-judgment/` file by path. This is the end-to-end behaviour test confirming cached Opus-tier judgment surfaces to future plan authors.
- **AC11 — schema_version: 1 on every manifest:** every `dispositions:` (Phase 2), `dr_dedup:` (Phase 3b), `directory_entries:` (Phase 3c), `deletions:` (Phase 3d), and Phase 2.7-QG verdict file carries `schema_version: 1` as its first key. Consumers must fail-loud on unknown forward versions, per DR-5 in `docs/plans/2026-05-28-distill-structured-manifests.md`.
<!-- AC12-AC14 are agent-prompt-scoped or test-scoped; see agent-prompts/phase-3d.md (AC2) and tests/phase3d-fixtures/ (AC11/12/14). This file mirrors plan-level ACs that are command-surface-relevant. -->
- **AC15 — backward-compat (schema_version: 1):** Phase 5 consuming a `schema_version: 1` Phase 3d manifest (only `deletions:`, no `deletion_groups:`) succeeds — backward-compat invariant. A `schema_version: 2` manifest with `deletion_groups:` is the new canonical shape; the absence of that key on a v1 manifest is not an error. Spec backlink: `docs/plans/2026-06-14-distill-phase3d-output-budget.md` § AC15.
- **AC16 — scout YAML block:** Phase 1 scout output includes a fenced YAML block with `artifact_paths:` list under each group section heading (EPHEMERAL / ALREADY_CAPTURED cluster sections). Phase 5 reads `artifact_paths:` from this YAML block — not from Markdown prose or glob — when expanding `deletion_groups:` entries in Phase 3d manifests. Spec backlink: `docs/plans/2026-06-14-distill-phase3d-output-budget.md` § AC16.
- **AC17 — fanout sentinel:** if Phase 3d fanout fragments (`phase3d-fragment-*.md`) exist at the scratch path but no canonical assembled manifest is present at the canonical path, Phase 5 aborts with named error: "fanout assembly incomplete — N fragments found, no canonical manifest." Applies only when Phase 0 engaged Workflow-fanout mode (`N > 500` deletion-eligible candidates). Spec backlink: `docs/plans/2026-06-14-distill-phase3d-output-budget.md` § AC17.

---

## Relationship to Other Commands

| Command | When to use |
|---------|-------------|
| `/distill` | Extract knowledge into wiki docs, trim + archive canonical specs, delete scaffolding |
| `/update-docs` Phase 8b | Bulk prune without knowledge extraction — runs unconditionally under conservative thresholds (`pipelines/update-docs/artifact-pruning.md`) |

**Two meanings of "archive" — the load-bearing division.** "Archive" names two distinct lifecycles, and the two commands own one each:

- **Knowledge-archival (`/distill` owns the harvest; session-init sweep owns the move).** The session-init sweep performs the programmatic relocation — moving terminal plans (`status: implemented`/`superseded`/`abandoned`) from `docs/plans/` to `archive/specs/YYYY-MM/` as a cheap, unconditional mechanical step decoupled from any knowledge-extraction budget. `/distill` then drains harvest debt: for each RIPE plan in `archive/specs/` not yet in the distill-log, it trims the archived copy to its canonical skeleton and extracts knowledge into wiki/DR. Re-homing constraints (§ 5a) MUST precede trimming — this extraction-coupled discipline cannot be automated away. The trimmed spec is itself a canonical shape (RAG-greppable structure), complementary to the wiki's narrative.
- **Age-archival (`/update-docs` Phase 8b owns it).** Time-thresholded janitorial pruning of aged, non-knowledge-bearing artifacts. No extraction, no trim — just bulk cleanup once material crosses an age line.

The two are complementary, and the lineage is already partially documented: `/distill` extracts knowledge into wiki *before* the source material gets pruned (see § "For bulk pruning…" above), and `docs/wiki/cruft-sweep-cadence.md` frames "filesystem hygiene is a distinct lifecycle from knowledge extraction (`/distill`) and artifact pruning (`/update-docs` Phase 8b)." Run `/distill` when there's wiki-worthy knowledge in the artifacts about to age out; rely on `/update-docs` Phase 8b for routine bulk pruning.

**Ordering hazard (same shape as the cross-repo-memo 90d floor):** `/update-docs` Phase 8b age-deletes plans older than its retention floor. That floor MUST exceed the `/distill` cadence — otherwise age-archival could `git rm` a RIPE-but-unharvested plan before knowledge-archival extracts it (git history survives, but the wiki/DR promotion never runs). See `pipelines/update-docs/artifact-pruning.md` § Scope (plans row).

**Prior-art-checker:** Phase 2.5 judgment entries are written to `docs/wiki/codebase-judgment/`. Prior-art-checker consults this subdirectory (via recursive `docs/wiki/**/*.md` glob) on every plan check, so future plans receive cached Opus-tier judgment at Sonnet cost with zero additional wiring. See `agents/prior-art-checker.md` and `docs/wiki/prior-art-checker.md`.

_Update 2026-05-06:_ The standalone `coordinator:artifact-consolidation` skill was absorbed into `/update-docs` Phase 8b. Existing references should point at `pipelines/update-docs/artifact-pruning.md`.
