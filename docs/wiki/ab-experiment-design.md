---
kind: wiki
title: A/B Experiment Design — Sidecar Lifecycle, Power, and Grading Scope
status: active
created: 2026-05-18
last_updated: 2026-05-18
sources:
  - coordinator-improvement-queue 2026-05-16 (project-rag)
tags: [experiments, ab-test, bootstrap, sidecar, lifecycle, grading]
---

# A/B Experiment Design

> Lesson surface: 2026-05-16, project-rag — three independently-discovered failure modes from in-tree A/B harnesses, folded into one wiki because they co-occur and the rules are mutually reinforcing.

A/B harnesses look clean — flip a flag, run two banks, compare. In practice the harness's lifecycle, statistical shape, and grading scope can each silently invert the verdict. Rules below are named by failure shape so the next instance is recognisable before it ships.

---

## 1. Kill the Sidecar Between Legs

**Failure shape.** The feature reads config from `os.environ` (or any in-process snapshot) at sidecar spawn. Harness flips the env var between legs but reuses the same sidecar. Leg B's process still runs leg A's environment — measured "B" is a second draw from A. No loud failure, just a quiet null because no toggle happened in the system under test.

**Rule.** Kill the sidecar between legs. Tear down and respawn is the default; reuse is the exception and must be justified by showing the feature re-reads config every request, not at process start. If in doubt, add a leg-B-only canary value and assert the sidecar logs it before counting any B trial.

---

## 2. Treat CI-Half-Width-Sized Lift As Underpowered, Not Null

**Failure shape.** Bank size N ≤ 15. Bootstrap CI half-width on the metric is ≈ the lift you're trying to detect. The two legs' CIs overlap heavily; classical "fail to reject null" framing reports the experiment as negative. But the null was wrong — a real lift of that magnitude is exactly what an underpowered bank looks like. Repeated underpowered runs accumulate as evidence-of-absence in lessons and decision records when they are nothing of the sort.

**Rule.** Closure shape is **Policy B′**: the gate is **non-overlap of the bootstrap CIs**, not p-values or point estimates. Below a **±0.025 diagnostic floor** the experiment is declared **underpowered**, not negative — handed back for larger N, tighter measurement, or a different metric. Underpowered verdicts never close a hypothesis; they only justify redesign. → [`test-design-discipline`](./test-design-discipline.md) for the broader "don't ratify null when you couldn't have seen the signal" pattern.

---

## 3. Grade Wiki and Impl Halves Together

**Failure shape.** The change under test has a wiki-section-canonical-home component (doctrine, prompt fragment, agent rubric) **and** an impl-chunk component (code, hook, config). The grading rubric only inspects one half — usually the impl chunks, because that's where the diff lives. The wiki side is unmeasured. A run can score "B wins on impl" while the wiki section it depends on still says the A thing, leaving the integrated system in an A/B chimera that ratifies the wrong direction.

**Rule.** Author-before bank discipline must grade wiki-section-canonical-homes alongside impl chunks whenever both exist. The grading manifest enumerates **both** surfaces; partial grading is a pipeline failure, not a degraded-OK result. If the wiki half cannot be graded in this run, the bank is mis-scoped — split it, don't ship half a verdict. → [`verification-before-completion`](./verification-before-completion.md) for the general "verify the surface you actually changed" rule, and [`dogfooding-doctrine`](./dogfooding-doctrine.md) for the related fix-through discipline on capabilities under test.

---

## Cross-References

- [`dogfooding-doctrine`](./dogfooding-doctrine.md) — fix-through validation; A/B is one shape of dogfood.
- [`test-design-discipline`](./test-design-discipline.md) — power, null-result hygiene, real-shell semantics.
- [`verification-before-completion`](./verification-before-completion.md) — grading scope must match change scope.
