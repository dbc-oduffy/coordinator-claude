Part of [`PIPELINE.md`](PIPELINE.md); phases still run in its strict sequence.

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
