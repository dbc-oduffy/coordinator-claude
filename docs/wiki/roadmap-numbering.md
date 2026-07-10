---
kind: wiki
title: Roadmap Stub Numbering — Dependency-Order Invariant
status: active
created: 2026-06-28
spec-backlink: docs/plans/2026-06-28-roadmap-stub-numbering-dependency-order.md
tags: [roadmap-numbering, roadmap-planning, dependency-order]
---

<!-- Purpose: States the stub-numbering invariant for coordinator roadmaps, enumerates the
enforcement surfaces (audit gate + authoring helper), and scopes the gate's guarantee honestly.
Consumed by: skills/roadmap-planning/SKILL.md (Step 2.1.5 + Phase 2 exit gate), spinoff-handoffs.md § Wave vs sprint. -->

# Roadmap Stub Numbering — Dependency-Order Invariant

Stub numbers in a coordinator roadmap (`<slug>-N`) are a **topological linearization** of the `blocks`/`blocked_by` dependency DAG. This note states the invariant, enumerates the enforcement surfaces, and scopes the gate's guarantee honestly.

## The Invariant

For every dependency edge `A blocked_by B` in the roadmap:

1. **Number order:** `number(B) < number(A)` — a lower stub number never depends on a higher one.
2. **Execution-slot order (strict):** `(sprint(B), wave(B)) <_lex (sprint(A), wave(A))` — the `(sprint, wave)` execution slot is **strictly** dependency-monotone. A dependency and its dependent in the **same** `(sprint, wave)` slot is itself a violation, because `blocked_by` is a hard ship-first gate and wave members dispatch concurrently with file-disjoint scope by construction.
3. **No cycles:** a DAG cycle fails loud (`RoadmapCycleError`). A cycle is an authoring bug to surface — never linearize around it.

**Wave is sprint-LOCAL.** `wave: N` within sprint 2 is a later execution slot than `wave: N` within sprint 1. The dependency-monotone rule applies to the full lexicographic `(sprint, wave)` tuple, not to bare wave number.

**Why it matters.** Every human and EM reading a STUB-INDEX reasonably assumes `<slug>-N` never depends on `<slug>-M` for `M > N`. A scheduler or pickup-EM running stubs in numeric order that encounters an unsatisfied dependency either stalls or — worse — collides with a live peer executing the real owner, as in the originating `ccos-6 blocked_by ccos-4` incident.

## Enforcement Surfaces

Three surfaces provide defense-in-depth:

| Surface | Role |
|---|---|
| `bin/audit-roadmap.sh` **Audit 5** | Fail-loud verification gate — exits 1 naming every offending edge; runs at Phase 2 close; blocks Phase 3 dispatch on any violation, unresolved edge, or cycle |
| `bin/lib/roadmap-graph.js` — `topoNumber` | Constructs the topological linearization (Kahn's algorithm + longest-path-depth wave assignment) for a given nodes+edges input; wave = `depth + 1` within a single sprint; deterministic tie-break within a topo layer |
| `bin/lib/roadmap-graph.js` — `checkDependencyOrder` | Verifies strict `(sprint, wave) <_lex` monotonicity over DECLARED edges; reports violations, unresolved edges (edges to stub_ids outside the provided set), and cycles as distinct classes; missing `sprint` field on either endpoint is a fail-loud own violation class, never silently coerced |
| `bin/roadmap-number-stubs.js` | Authoring helper CLI — input: provisional-label dependency list; output: `label → (stub_id N, sprint, wave)` mapping the author transcribes into frontmatter. **Constructive for single-sprint linearization** (`wave = depth + 1`); for multi-sprint roadmaps, emits the topological order as a basis for author-assigned sprint values, and Audit 5 verifies the resulting `(sprint, wave)` monotonicity. `--check <run-id>` mode runs `checkDependencyOrder` over authored stubs on disk |

## Scope Honesty — What the Gate Can and Cannot Catch

The gate **enforces ordering over DECLARED `blocked_by` edges** and catches late-edge inversions at re-audit. It **cannot discover an undeclared or missing dependency** — a dependency that was never expressed as a `blocked_by` edge in stub frontmatter is invisible to the gate.

The originating incident (`ccos-6 blocked_by ccos-4` ordering gap) involved a **missing** edge (the dependency was implicit in the design but never declared), not a mis-ordered declared one. The gate would not have caught it. **Discovering undeclared/missing dependencies remains a human and OVERVIEW-review responsibility** — the gate is a structural backstop for authored edges, not a substitute for deliberate dependency analysis at roadmap-authoring time.

## Forward-Looking Only

Existing roadmaps are **not renumbered** when the invariant is adopted. Renumbering breaks every in-flight handoff, claim, and commit reference that uses the original stub codes. The authoring helper and audit gate apply to roadmaps authored or re-gated after this invariant was introduced.

## See Also

- `skills/roadmap-planning/SKILL.md` — Step 2.1.5 (dependency-order numbering step), Step 2.4 (wave assignment rationale), Phase 2 exit gate (Audit 5 required green before Phase 3 dispatch).
- `spinoff-handoffs.md` § Wave vs sprint — wave is sprint-LOCAL; the `(sprint, wave)` tuple is the correct dependency-monotone comparand.
