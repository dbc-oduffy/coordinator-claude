---
segment_id: plan-preflight-check4-sufficiency
surface: plan
class: protected
order: 6
---

**Check 4 — Sufficiency (does the spine reach the prime exit criterion?)** _(runs independently of Checks 1, 2, 2b, and 3)_

A magnitude question: if every chunk executes perfectly, does the falsifier go green? Estimate the distance the spine closes against the baseline-to-target distance the prime exit criterion demands.

**Distinct from divergence** (`coordinator/docs/wiki/coordinator-tripwires/a-green-plan-is-not-a-delivered-plan.md`): sufficiency is right direction, wrong size.

Verdict is one of `sufficient` / `insufficient` / `cannot-tell` — always stated, never omitted.

| Verdict | Meaning |
|---|---|
| `sufficient` | The spine's delivered magnitude, taken at face value, closes the falsifier's baseline-to-target distance. |
| `insufficient` | Names the shortfall in the prime exit criterion's own units where they exist — e.g. "closes ~15 of the ~205 required." |
| `cannot-tell` | Itself a finding: a plan whose delivered magnitude cannot be reasoned about before execution is a plan nobody can steer. |

**Routing is the point.** `insufficient` and `cannot-tell` are RE-PLAN triggers, not findings to note and pass. Resizing upward via the `plan⇄sizing` return edge is unremarkable but never the default (a check that routinely returns `insufficient` inflates sizes). Narrowing the prime exit criterion to fit the spine is
forbidden — that is the vacuous AC one altitude up.
