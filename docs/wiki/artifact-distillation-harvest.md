# Artifact Distillation & Harvest

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-05/2026-05-27-cqcs-cluster5-phase-completeness.md, archive/specs/2026-05/2026-05-28-distill-structured-manifests.md, archive/specs/2026-06/2026-06-18-distill-plan-priority-atlas-gate-archive-foldering.md, archive/specs/2026-06/2026-06-15-workstream-complete-self-clean.md, cross-repo/archive/2026-07-12-example-cockpit-repo-em-distill-memory-not-durable-capture.md, cross-repo/archive/2026-07-12-project-rag-em-distill-workflow-fanout-pattern.md, 2026-07-12-claude-klabauter-em-distill-ceremony-mechanical-substrate.md, 2026-07-12-claude-klabauter-em-distill-normalizer-mapping-gap.md -->

`/distill` and its sibling harvest/cleanup ceremonies (plan-priority atlas gate, archive foldering, workstream-complete self-clean) turn ripe archived artifacts — specs, plans, memos — into durable knowledge (archived handoffs are excluded: not a cohort, not a knowledge source, no distill fate) (wiki guides, Decision Records) while disposing safely of what's already captured. This guide consolidates the architectural decisions and hard-won gotchas behind that pipeline.

## Overview

The pipeline runs roughly: **Phase 0** (dedup/overlap check) → **Phase 1** (nugget extraction, ID-pinned) → **Clustering** (topic grouping) → **Phase 2** (synthesis into guides/DRs) → **Phase 3b/4/5** (quality gates, atlas-drift advisory, PM approval, disposal). Two related ceremonies feed and depend on it: the **plan-priority atlas gate** (which archived specs are ripe to harvest) and **archive foldering** (where terminal artifacts land once harvested).

## Key Decisions

<!-- src: plan12-028, plan12-032, plan12-033 -->
### Nugget ID pinning and manifest schema

- **DR-1 (nugget IDs pinned at Phase 1, not Clustering):** Phase 1 emits `id: <batch>-<n>` per nugget at extraction time. Clustering may re-key IDs for human-readable tables, but the canonical ID — the one that travels through YAML end-to-end — is assigned at Phase 1. This reversed an earlier substrate where IDs were assigned at Clustering (format `batch-N/nugget-M`, re-keyed to `K-001`/`D-001`/`A-001`), which made disposition-maps unstable because nugget identity wasn't fixed until mid-pipeline.
- **DR-5 (manifest schema versioning):** Manifests carry `schema_version: 1` as their first key. Unknown forward-version consumption is fail-loud; matching-version consumption is silent. Integer versioning — semver is YAGNI at this scope.
- **DR-6 (agent-prompts split):** `pipelines/artifact-distillation/agent-prompts.md` was decomposed into per-phase fragments (`agent-prompts/<phase>.md`); the original path is now a thin index. PM-waived re-review on this split.

<!-- src: plan12-029, plan12-030, plan12-031 -->
### Apply-agent slicing and quality-gate semantics

- **DR-2 (apply-agent A/B/C slicing preserved):** A PM intuition that per-slice apply felt inefficient was addressed by adding manifest-driven done-conditions per slice, not by re-slicing the work. Don't re-architect the slicing in response to a vague efficiency complaint — add verifiable done-conditions instead.
- **DR-3 (Phase 1.5 disposition — investigate before deciding):** Run the diagnostic chunk first. If Phase 1.5 turns out non-functional, a new manifest-driven quality gate subsumes it (consolidate). If Phase 1.5 is doing real work, the new QG is additive — different altitude: 1.5 checks Phase 1 internal consistency, the new QG checks Phase 1→2 coverage.
- **DR-4 (different failure modes need different gates):** Opus contradiction-escalation output *replaces* source nuggets — a semantic transformation, so it needs a Sonnet fidelity check. Phase 2 synthesis *transforms* nuggets into deltas — a mechanical mapping, so it needs an ID set-diff, not a fidelity re-read.

<!-- src: plan12-034, plan12-035 -->
### Root problem: no machine-checkable contracts past Phase 2

The unifying finding behind the manifest rebuild: two separate PM intuitions ("apply feels inefficient" and "completeness checks are missing") pointed at the same underlying gap — the pipeline had no machine-checkable contract past Phase 2, so neither slicing correctness nor synthesis completeness could be verified mechanically. Concretely this showed up as format-fragility between Phase 3b and 5 (prose tables parsed with `awk`), unverified coverage across Phase 1→2→5 (no per-nugget receipt of what got folded vs dropped), and link-heal residuals only caught by manual post-run inspection. The manifest/ID-pinning work above is the direct fix.

<!-- src: plan19-007, plan19-008, plan19-009 -->
### Archive foldering and harvest decoupling

- **Move/harvest coupling is decoupled:** Terminal-plan MOVE (status-predicate driven, lossless `git mv`) is a cheap programmatic sweep, fully decoupled from harvest. `/distill` harvests the ripe cohort directly **from** `archive/specs/` rather than depending on a prior move step. Archive-foldering, the plan-delivery-audit oracle, and four-fate classification are reused unchanged.
- **KD1–KD5 (architectural spine):** KD1 — harvest budget-first over ephemera. KD2 — plan end-state trims to *both* `archive/specs/YYYY-MM/` (git-recoverable) *and* wiki/DR (durable knowledge), never delete-to-git-only. KD3 — the atlas is sensor-only: non-blocking advisory, no actuation. KD4 — knowledge-archival (`/distill`) is a distinct concern from age-archival (`/update-docs`); don't conflate them. KD5 — archives are month-foldered: `archive/specs/YYYY-MM/` and `archive/handoffs/YYYY-MM/`.
- **Ripeness predicate (canonical oracle = plan-delivery-audit skill):** RIPE (harvest) = `status: implemented|shipped` AND ACs pass at HEAD. PARTIAL (skip) = implemented but ACs fail or are absent. IN-FLIGHT (skip) = `in-progress|draft|reviewed`. ABANDONED (skip) = `superseded|abandoned|cancelled`. Explicitly excluded from the predicate: `SHIPPED:` annotations (Phase 1 only, not a status field), `status: consumed` (0/117 plans observed — effectively dead), and `## Deviations` sections (a dead surface, don't harvest from it).

<!-- src: plan19-010, plan19-011 -->
### Atlas drift gate — reused, non-blocking, observably graceful

`check-atlas-watch-drift.py` enumerates `docs/architecture/systems/*.md` (7 systems), runs each system's `<name>.watch.sh`, and walks `last_attested` against `--stale-days N` (default 30) to flag STALE. Atlas frontmatter carries two clocks: `last_mapped:` and `last_attested:`. At Phase 4, `/distill` maps churn to atlas systems; on DRIFT/STALE it emits a non-blocking advisory ("consider `/architecture-audit` before deletion"). When churn maps to **no** atlas system at all, the gate must not silently no-op — it emits an explicit "churn touched `<paths>`; no atlas-system mapping — advisory skipped" message. Degrading gracefully is fine; degrading *silently* is not — the no-map path has to stay observable or the gate is toothless-by-omission.

<!-- src: plan18-004 -->
### Default disposition is delete

`/distill` is record-keeping only, not an archival vault. Default disposition for artifacts once their knowledge is captured is **delete** — the commit log is the recovery substrate, not a growing pile of `archive/` directories. Don't retain "just in case."

<!-- src: memo03-009 -->
### Memory pointers are not durable capture

`~/.claude/memory/*.md` entries do **not** satisfy an "already-captured" or "extraction-artifact-present" check. Memory is a lossy recall index for session continuity, not a system-of-record. Durable capture means in-repo only: `docs/decisions/`, `docs/wiki/`, `state/cross-repo-commitments/`, or a canonical plan/spec. Delete-guards must exclude memory as a captured-evidence source, and should carry a mechanical downgrade-to-RETAIN check when memory is the only "capture" found. (Finding #12 of the distill dogfood-improvements review; adopted.)

<!-- src: memo02-001 -->
### Triage ceremony lives in claude-klabauter, not in the skill body

The deterministic `memo.triage` partition (classifying memos for disposition) lives in claude-klabauter as a `COMPUTE_ONLY` op — a sibling of `records.query` / `deliverable.rollup` — invoked by `/distill` through the standard `coordinator_core` dispatch surface, which emits triage JSON for the skill to consume. It is explicitly **not** inline classification logic embedded in the `/distill` skill body. This is Decision-0 under the cross-repo-op-ownership discriminator: mechanical/deterministic compute belongs in the engine (claude-klabauter), not hand-authored in skill prose.

<!-- src: memo02-002, memo02-003, memo02-011 -->
### Disposal safety and immutability rules

- **Disposal gates on scan success-rate, not coverage-% alone.** A mass-throttle or partial-failure harvest run must not be allowed to dispose artifacts on an empty/failed scan. This re-derives terminal status from disk rather than trusting a coverage percentage that could be computed against a broken run (finding #8, re-deriving `cleanup-sweep-hazards.md` §38/§44 mandate).
- **No-rewrite classes are explicit.** `/distill` §5d must never rewrite: historical logs (`state/week-changelog/*`, `wsc/*.json` receipts, `review-trail/findings/*`), inbox-path provenance, or bare `source_memo:` basenames. Active-ref scope deliberately stops at `docs/`, `tasks/`, `archive/` — it does not reach into point-in-time state records. This mirrors `cleanup-sweep-hazards.md` #45's "point-in-time state record → LEAVE" class.
- **§7 disposition-mapping covers all 7 live-log action types**, verified against claude-klabauter's real 392-row corpus and captured as DR-053: `distill-harvest → DISTILLED` (keyed on `belongs_to_spec`), `DELETE → EPHEMERAL` (explicit enum), and `DELETE-GROUP` plus run-event rows skip with an explicit reason (these are spec-disposition-only log intent, not harvestable content).

<!-- distilled: run 2026-08-06-14h38; sources: c2-026, c2-027 -->
### Artifact identity — mint seam and derived lifecycle state

- **c2-026 — path-independent minted IDs, single reconciled seam.** Every lifecycle artifact type mints a stable, path-independent ID (`hnd-` for handoffs, `cmp-` for completions) through one reconciled mint seam, not per-type ad hoc ID generation. Handoff ancestry carries ID-based companion fields (`predecessor_id`, `origin_handoff_id`) alongside the human-legible path fields, so lineage references survive archival moves and renames — a path-based reference alone breaks the moment `archive/` foldering or a rename touches the file.
- **c2-027 — `Resolves:` trailer, lifecycle state derived not stored.** A new `Resolves: <artifact-id>` git commit-trailer convention, plus a parser and the stateless `rollup-derive.sh` primitive, let lifecycle state be **derived on read** from whether an artifact's resolving commits reached `origin/main` — never stored as a field that can drift from reality. This honors the canonical-artifact-shapes negative-spec (no stored status field to go stale). The primitive's 4-token contract explicitly propagates an `unknown-error` outcome rather than collapsing an unreachable `origin/main` check into a false "not-shipped" — a fail-loud vs. silent-wrong distinction.

<!-- distilled: run 2026-08-06-14h38; source: c9-002 -->
<!-- src: c9-002 -->
### Schema-enforced evidence home for spike verdicts

Spike verdict records moved to `docs/research/spike-verdicts/` under a dedicated schema.
`discharged_by` is required and non-null whenever `gated_route` is non-empty, making a record
with live routing intent structurally unwritable until it names what discharges it — the schema
enforces the invariant rather than relying on review discipline. Out-of-enum `kind` is a hard
deny, not a warning.

This landed alongside three break-class fixes surfaced by the same schema tightening: a spurious
`kind` collision, a boundary test fixture that had gone disarmed, and a cockpit summary enum that
was silently dropping archived records. The general lesson: tightening a schema on an artifact
class is itself a good moment to re-run everything that reads that class end-to-end — schema
enforcement surfaces pre-existing silent-drop bugs in downstream consumers, not just malformed
new writes.

## Patterns

<!-- src: memo03-012 -->
### Background Workflow + journal-resume for large harvest debt

For large harvest backlogs (observed: 188+ specs), a foreground single-session run is fragile against rate-limiting. The resilient pattern: run as a background Workflow with journal-resume, splitting expensive extraction (Haiku, fanned out ×16, cached) from cheap synthesis (Sonnet, one agent per topic/file, ×109 observed). `resumeFromRunId` caches the extraction wave so a resume only re-runs failed syntheses, not the whole extraction pass. This pattern survived two rate-limit wipeouts in practice. Concrete threshold: default to the background Workflow (not serial fan-out) above ~30 specs; keep one-agent-owns-one-output-file; maintain a harvest-debt ledger assertion so backlog size is always known, not rediscovered.

<!-- src: plan12-001, plan12-003, plan12-004 -->
### Cross-pipeline edge-case family: partial/stale coverage

Three independent skills share a variant of the same under-handled edge case, which is worth recognizing as a family rather than three unrelated bugs:

1. `/architecture-survey` Phase 0 refresh — when churn since the last survey exceeds 50%, the refresh is a partial bootstrap, not a true incremental update; the fix is to emit a warning suggesting a full audit pass rather than silently treating it as current.
2. `/distill` Phase 0 — filename-stem overlap check: compare proposed guide name stems against existing `docs/wiki/` filenames (after normalization) and surface near-duplicate collisions at the Phase 4 PM gate, rather than silently creating a near-duplicate guide.
3. `/bug-blitz` Phase 1 — stale-backlog guidance: a bug backlog's header SHA attribution is more trustworthy than a stale `OPEN` status field; emit guidance when backlog age exceeds a threshold rather than trusting the status field at face value.

The common shape: a pipeline phase assumes its input is fresh/complete, and needs an explicit staleness/overlap check rather than silent pass-through.

<!-- distilled: run 2026-08-06-14h38; source: c1-001 -->
<!-- src: c1-001 -->
### Emission-conformance fixture: a five-part shape for cross-repo emitter contracts

An emission-conformance fixture materializes as a triple, not a single artifact: a
byte-reproducible normative fixture, a generator (runs the live emitter against a frozen fixture
corpus with provenance normalization), and a drift-runner with an mtime guard — complemented by a
shared contract doc, for five parts total. This is the second observed instance of the Step Zero
NDJSON pattern (see `2026-07-04-2026-07-04-doe-emission-conformance-fixture-12d565.md`), useful
precedent when standing up conformance oracles for other emitters.

The cockpit emitter is stateful — wall-clock, host, git SHA all vary run-to-run — so its
conformance oracle must **normalize-then-compare**, never raw byte-compare. Any emitter with
non-deterministic fields (timestamps, hostnames, commit SHAs, PIDs) needs the same treatment:
strip/normalize the volatile fields before diffing against the frozen fixture, or the drift-runner
will false-positive on every run.

<!-- distilled: run 2026-08-06-14h38; source: c8-009 -->
<!-- src: c8-009 -->
### Candidate-restatement generator — pre-computed slot, not a grep the acting agent remembers

`claude-klabauter` pre-computes, ahead of dispatch, a candidate-restatement check for each Wave-2
synthesis target: given the target wiki file and the incoming nugget text, it finds lines in the
existing file that already state an adjacent/overlapping claim. The result ships as a filled
`candidate_restatements` slot on the routing record/brief handed to the acting agent, rather than
leaving "check for self-contradiction" as an instruction the agent has to remember to execute via
its own grep. Wired into two seams: `/distill` Wave-2 synthesis dispatch (this document's own
pipeline) and executor-brief dispatch generally.

This is the general pattern for preventing self-contradiction through **computed injection**:
push a check that's easy to forget as a live step into a precomputed field the consuming agent
must dispose of (amend in place, note why both coexist, or confirm the list is empty) — same
shape as the `candidate_restatements: []` field on this very guide's own routing record.

<!-- distilled: run 2026-08-06-14h38; source: c8-046 -->
<!-- src: c8-046 -->
### Freshness gates catch real drift, not just theoretical drift

The freshness gate for the generated artifact-shape-contract found real drift on its first
production run — not a false-positive shakeout. Treat this as validation that mechanical
freshness/staleness checks (see the atlas drift gate above, and the Phase 0 overlap check) are
worth the authoring cost even before they've accumulated a track record: a gate that catches
drift on run one is doing its job, not miscalibrated.

## Gotchas

- **Don't trust `status:` fields over derived signal when they can drift** — e.g. bug-backlog `OPEN` status vs. header SHA attribution; SHA attribution wins.
- **`## Deviations` sections are a dead surface** — do not harvest from them even if present in older archived plans.
- **`status: consumed` is effectively unused** (0/117 plans observed) — don't build harvest logic that assumes it's a live signal.
- **Memory-pointer "capture" is a false negative for delete-guards** — always verify durable in-repo capture exists before treating memory as evidence an artifact's knowledge was already extracted.
- **Nugget ID stability matters more than it looks** — if IDs are re-keyed mid-pipeline (as the old Clustering-assigned scheme did), disposition-maps and coverage receipts silently desync from the nuggets they're supposed to track.

## Reference

| Ceremony / Gate | Owner | Failure mode it guards | Blocking? |
|---|---|---|---|
| Phase 0 filename-stem overlap check | `/distill` | Near-duplicate wiki guides | Surfaced at Phase 4 PM gate |
| Atlas drift gate | `/distill` Phase 4 | Deleting content atlas hasn't re-mapped | Non-blocking advisory |
| Ripeness predicate | plan-delivery-audit skill | Harvesting non-ripe/partial plans | Blocking (oracle) |
| `memo.triage` op | claude-klabauter (`COMPUTE_ONLY`) | Inline classification drift in skill prose | N/A (dispatch surface) |
| Disposal success-rate gate | `/distill` disposal manifest | Mass-throttle disposing on empty scan | Blocking |
| Opus fidelity check | Phase 3b (contradiction-escalation) | Semantic drift on nugget replacement | Blocking |
| Phase 2 ID set-diff | Phase 3b (synthesis) | Mechanical coverage gaps nugget→delta | Blocking |
