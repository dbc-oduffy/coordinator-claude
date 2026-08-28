---
segment_id: plan-preflight-check4-sufficiency
surface: plan
class: protected
order: 6
---

**Check 4 — Sufficiency (does the spine reach the prime exit criterion?)** _(runs independently of Checks 1, 2, 2b, and 3)_

This is a magnitude question, not a shape one: if every chunk in the spine executes exactly as
written and perfectly, does the falsifier go green? The baseline makes it answerable — there is a
measured start and a stated target, so estimate the distance the spine closes against the distance
the prime exit criterion demands.

**This is a different failure from divergence.** Divergence (see
`docs/wiki/coordinator-tripwires/a-green-plan-is-not-a-delivered-plan.md`, `pln-route-c-…`) is right
size, wrong direction — every AC passes and the falsifier still doesn't move. Sufficiency is right
direction, wrong size — the spine moves the falsifier the way it should, just not far enough. The
falsifier alone catches insufficiency only at close-out, after the whole execution is paid for; this
check exists to catch it before authoring the spine.

Verdict is one of `sufficient` / `insufficient` / `cannot-tell` — always stated, never omitted.

| Verdict | Meaning |
|---|---|
| `sufficient` | The spine's delivered magnitude, taken at face value, closes the falsifier's baseline-to-target distance. |
| `insufficient` | Names the shortfall in the prime exit criterion's own units where they exist — e.g. "closes ~15 of the ~205 required." |
| `cannot-tell` | Itself a finding: a plan whose delivered magnitude cannot be reasoned about before execution is a plan nobody can steer. |

**Routing is the point.** `insufficient` and `cannot-tell` are RE-PLAN triggers, not findings to
note and pass. Resizing upward via the `plan⇄sizing` return edge is natural and unremarkable —
never a failure, and equally never the default: most plans are sized about right, and a check that
routinely returns `insufficient` is a reviewer inflating sizes rather than estimating them.
Narrowing the prime exit criterion to fit the spine is forbidden — that is the vacuous AC one
altitude up.
