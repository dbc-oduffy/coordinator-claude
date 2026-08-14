---
segment_id: plan-preflight-check2b-ac-shape-offer
surface: plan
class: droppable
order: 4
---

**Check 2b — Acceptance-criteria shape (offer, not block)** _(runs independently; offer-shaped)_

**Negative-spec — do NOT offer the bindable-table form (`ID | Criterion | Test | Binding-Class | Status`), typed `Test` cells (`grep:` / `cited:` / `pytest:` / `bats:` / `sh:`), `Binding-Class`, or `pending realization`.** That whole shape belonged to the acceptance oracle, which is retired — not just removed but deliberately not replaced with any new done-time gate, and not to be rebuilt as a cheaper version of the same mechanism (delete, don't rewrite). A reviewer who offers it is briefing plan authors toward a mechanism that does not exist on disk. Acceptance criteria are **not mechanically gated** — see `docs/wiki/writing-plans.md` § Acceptance Criteria (optional).

When the reviewed plan's `## Acceptance Criteria` section is present in any shape, NOTICE only whether the criteria read as binary pass/fail, and offer at most the documented optional form — do NOT block.

Offer: _"Acceptance criteria are an optional reviewer's design lens in `ID | Criterion | Status` form (`docs/wiki/writing-plans.md`). No gate reads them; nothing here needs to change for a tool's benefit. This is just a heads-up before the reviewer reads the criteria as a design lens."_

The reviewer's **substantive design-lens job is the point of this check** — evaluating whether the criteria are testable-shaped, complete, and correctly scoped. That judgment is what replaced the oracle, and it is not a mechanical shape nudge. If the plan carries no AC section at all, skip this check silently: plans are not required to carry one.
