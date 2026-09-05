---
kind: wiki
title: Roadmap Stub Numbering — Dependency-Order Invariant
status: active
created: 2026-06-28
spec-backlink: docs/plans/2026-06-28-roadmap-stub-numbering-dependency-order.md
tags: [roadmap-numbering, roadmap-planning, dependency-order]
---

<!-- Purpose: States the stub-numbering invariant for coordinator roadmaps, enumerates the
enforcement surfaces (audit gate + authoring helper), documents the sibling audit-roadmap.py
coverage/concurrency audits and their authoring gotchas, and scopes the gate's guarantee honestly
(what edges it checks, what prose/ceremony it does not). Consumed by:
skills/roadmap-planning/SKILL.md (Step 2.1.5 + Phase 2 exit gate), spinoff-handoffs.md § Wave vs sprint. -->

# Roadmap Stub Numbering — Dependency-Order Invariant

Stub numbers in a coordinator roadmap (`<slug>-N`) are a **topological linearization** of the `blocks`/`blocked_by` dependency DAG. This note states the invariant, enumerates the enforcement surfaces, and scopes the gate's guarantee honestly.

## The Invariant

For every dependency edge `A blocked_by B` in the roadmap:

1. **Number order:** `number(B) < number(A)` — a lower stub number never depends on a higher one.
2. **Execution-slot order (strict):** `(sprint(B), wave(B)) <_lex (sprint(A), wave(A))` — the `(sprint, wave)` execution slot is **strictly** dependency-monotone. A dependency and its dependent in the **same** `(sprint, wave)` slot is itself a violation, because `blocked_by` is a hard ship-first gate and wave members dispatch concurrently with file-disjoint scope by construction.
3. **No cycles:** a DAG cycle fails loud (`RoadmapCycleError`). A cycle is an authoring bug to surface — never linearize around it.

**Wave is sprint-LOCAL.** `wave: N` within sprint 2 is a later execution slot than `wave: N` within sprint 1. The dependency-monotone rule applies to the full lexicographic `(sprint, wave)` tuple, not to bare wave number.

**Why it matters.** Every human and EM reading a STUB-INDEX reasonably assumes `<slug>-N` never depends on `<slug>-M` for `M > N`. A scheduler or pickup-EM running stubs in numeric order that encounters an unsatisfied dependency either stalls or — worse — collides with a live peer executing the real owner, as in the originating `ccos-6 blocked_by ccos-4` incident.

## What Counts as a `blocked_by` Edge (and What Doesn't)

The invariant only linearizes edges that genuinely exist, so mis-declaring one corrupts the numbering. Over-declaring `blocked_by` inverts the failure mode of a missing edge: it over-serializes the critical path and invites a factually-wrong `gate_dependency` rationale.

- A **hard `blocked_by`** edge means *B must ship before A can start* — a ship-first gate, and the only thing Audit 5 orders around.
- **File-overlap on DISJOINT fields/keys** — two stubs editing the same file but different keys (e.g. one edits a JSON enum, another a different enum in the same schema) — is **merge-coordination, not a dependency.** Record it as a **Soft-seams** entry, never a `blocked_by`. File-overlap gates concurrent WAVE dispatch (two stubs can't be typed into one file at once), NOT sequential stub-pickup order.
- When you do write a `gate_dependency` rationale, name the ACTUAL shared surface. "Shared status-enum" is wrong if the gating cluster touches `deployment_state`, not `status` — the Director of Engineering caught exactly this inversion, where a soft file-overlap seam had been encoded as a hard `blocked_by` with a mislabelled rationale.

## Enforcement Surfaces

Three surfaces provide defense-in-depth:

| Surface | Role |
|---|---|
| claude-klabauter `coordinator/bin/audit-roadmap.py` **Audit 5** | Fail-loud verification gate — exits 1 naming every offending edge; runs at Phase 2 close; blocks the close on any violation, unresolved edge, or cycle (its stdout phrases this as "Phase 3 dispatch is blocked" — claude-klabauter-resident wording for the same verdict) |
| `claude-klabauter coordinator_core.roadmap.graph` — `topoNumber` | Constructs the topological linearization (Kahn's algorithm + longest-path-depth wave assignment) for a given nodes+edges input; wave = `depth + 1` within a single sprint; deterministic tie-break within a topo layer |
| `claude-klabauter coordinator_core.roadmap.graph` — `checkDependencyOrder` | Verifies strict `(sprint, wave) <_lex` monotonicity over DECLARED edges; reports violations, unresolved edges (edges to stub_ids outside the provided set), and cycles as distinct classes; missing `sprint` field on either endpoint is a fail-loud own violation class, never silently coerced |
| claude-klabauter `coordinator/bin/roadmap-number-stubs` | Authoring helper CLI — input: provisional-label dependency list; output: `label → (stub_id N, sprint, wave)` mapping the author transcribes into frontmatter. **Constructive for single-sprint linearization** (`wave = depth + 1`); for multi-sprint roadmaps, emits the topological order as a basis for author-assigned sprint values, and Audit 5 verifies the resulting `(sprint, wave)` monotonicity. `--check <run-id>` mode runs `checkDependencyOrder` over authored stubs on disk |

### `audit-roadmap.py` Beyond Audit 5 — Coverage and Concurrency Audits

Audit 5 is the numbering gate proper, but two sibling `audit-roadmap.py` audits gate the *reconciliation table* and *wave concurrency*, and each has a silent-failure trap the author must author around.

**Audit 1 — stub-coverage.** Counts `KEEP` + `MERGE` verdicts in the reconciliation table and asserts the count equals stubs on disk. Two traps produce a false `stub-coverage mismatch`:

- **Verdict must sit in the 3rd pipe-delimited column.** Audit 1 anchors `KEEP`/`MERGE` to the 3rd table cell; a 2-column `| Cluster | Verdict |` layout silently counts 0 verdicts → false `stub-coverage mismatch: N stubs, 0 expected`. Use `| # | Cluster | Verdict | Rationale |` (verdict in col 3) — the roadmap-planning template shows this 3-column shape for exactly this reason.
- **A C0 design-spine cluster realized AS the OVERVIEW produces no stub.** Listing it `KEEP` causes an off-by-one coverage FAIL. Give C0 a distinct verdict token — **`OVERVIEW`** — that the `KEEP` regex won't match (matching the mcollab-roadmap convention where C0 is simply not a counted verdict row). Honest, not audit-gaming: C0's disposition genuinely differs from a stub-producing KEEP.

**Audit 2 — ready_to_fire uniqueness.** Enforces ≤1 `ready_to_fire` stub per `(roadmap_id, sprint, wave)` slot. Genuinely-parallel independent starters (`blocked_by: []`) therefore each need a **DISTINCT wave number** — NOT all wave 1 — which superficially conflicts with the "5 parallel stubs = 1 wave × 5 parallel" mental model. This is where `topoNumber`'s *deterministic tie-break within a topo layer* earns its keep: same-depth (independent) starters share the `wave = depth + 1` floor but are spread across distinct waves to satisfy Audit 2. Concurrency is preserved because `/mise-en-place` filters `ready_to_fire` across the whole SPRINT (not per-wave), so distinct-wave starters still fire together. For independent starters the wave number is a **pickup-staging slot**; it is a hard ordering gate only where `blocked_by` edges exist (Audit 5 strict monotonicity).

## Scope Honesty — What the Gate Can and Cannot Catch

The gate **enforces ordering over DECLARED `blocked_by` edges** and catches late-edge inversions at re-audit. It **cannot discover an undeclared or missing dependency** — a dependency that was never expressed as a `blocked_by` edge in stub frontmatter is invisible to the gate.

The originating incident (`ccos-6 blocked_by ccos-4` ordering gap) involved a **missing** edge (the dependency was implicit in the design but never declared), not a mis-ordered declared one. The gate would not have caught it. **Discovering undeclared/missing dependencies remains a human and OVERVIEW-review responsibility** — the gate is a structural backstop for authored edges, not a substitute for deliberate dependency analysis at roadmap-authoring time.

**Prose labels are equally invisible to the gate.** `audit-roadmap.py` and `lint-frontmatter` verify the `blocks`/`blocked_by` graph EDGES — never the prose stub-id↔cluster labels an author writes into stub bodies. When Phase 2 stub authoring is fanned out to N agents that each see only their own cluster, those prose cross-references drift: agents conflate cluster-number with stub-number whenever the mapping is not 1:1 (e.g. C7=pcli-03, C3=pcli-04). The edges stay correct while the prose points a context-less downstream EM at the wrong sibling stub. Observed on `pcli-2026-07-09` — four stubs (pcli-01/03/06/07) carried scrambled sibling descriptions, and backtick-wrapped refs evaded both the stub-set reviewer's grep and the first fix pass, requiring a full grep-sweep of every `<slug>-0N (Cn …)` pairing against the canonical map to clear. **Mitigation:** hand every fan-out agent the canonical cluster↔stub map, and grep-sweep the prose labels against it as a Phase 2 exit step — the audits will not do it for you.

## Roadmap Stubs Are Plan-Seeds, Not `/mise-en-place` Candidates

A `kind: spinoff-roadmap` stub is a **plan-SEED**, not a reviewed plan. Its ceremony ladder is `stub → /pickup → coordinator:plan → review → execute`. `/mise-en-place` explicitly excludes plan-as-you-go work and waves that produce decisions other waves depend on (`mise-en-place.md` line 14); a stub opening with a probe or a contested fork — e.g. a DANGER probe that can invalidate a PM decision — is the textbook not-ready-for-mise case. Plan+review each stub first, and run `/mise-en-place` only over the resulting reviewed plan-chunks — never over raw stubs. `roadmap-planning` authors stubs and stops; it never picks its own stubs back up, and never runs `coordinator:plan` or `/mise-en-place` over them. Plan+review each stub first, in the session that picks it up, and run `/mise-en-place` only over the resulting reviewed plan-chunks.

## Forward-Looking Only

Existing roadmaps are **not renumbered** when the invariant is adopted. Renumbering breaks every in-flight handoff, claim, and commit reference that uses the original stub codes. The authoring helper and audit gate apply to roadmaps authored or re-gated after this invariant was introduced.

## See Also

- `skills/roadmap-planning/SKILL.md` — Step 2.1.5 (dependency-order numbering step), Step 2.4 (wave assignment rationale), Phase 2 exit gate (Audit 5 required green before the stubs are handed forward), the 3-column reconciliation-table template (Audit 1), and § After Phase 2 (why there is no execution phase).
- `spinoff-handoffs.md` § Wave vs sprint — wave is sprint-LOCAL; the `(sprint, wave)` tuple is the correct dependency-monotone comparand.
- `mise-en-place.md` line 14 — exclusion of plan-as-you-go / decision-producing waves that makes raw spinoff-roadmap stubs ineligible for `/mise-en-place`.
