---
segment_id: plan-preflight-check2b-headline-claim-placement
surface: plan
class: droppable
order: 4
---

**Check 2b — Headline-claim placement (design-lens judgment)** _(runs independently)_

**Negative-spec — do NOT offer any `## Acceptance Criteria` table shape**, bindable
(`ID | Criterion | Test | Binding-Class | Status`) or the retired 3-column prose form
(`ID | Criterion | Status`) alike, typed `Test` cells (`grep:` / `cited:` / `pytest:` / `bats:` /
`sh:`), `Binding-Class`, or `pending realization`. A criterion that must be discharged is a
`## Tasks` spine row, inheriting the five-value disposition vocabulary and the close-out gate;
everything else is the plan's `prime_exit_criterion` and its falsifier delta. A reviewer who
offers a checklist table is briefing plan authors toward a mechanism that does not exist on disk.

The reviewer's **substantive design-lens job is the point of this check**: is the plan's
headline claim — the positive statement of the plan's behaviour landing end-to-end — actually
stated somewhere a reader meets it, rather than left implicit or scattered across filter-shaped
preconditions? That judgment does not depend on any AC table being present. If a reviewed plan
carries no `prime_exit_criterion`, or one that reads as a narrowing clause rather than a positive
statement of the headline behaviour, that is the finding — ask whether the headline claim
belongs in `prime_exit_criterion`, never ask for a table row. A legacy plan that still carries an
`## Acceptance Criteria` table (forward-only; not migrated) gets the same judgment applied to its
rows as evidence, not treated as the shape to reproduce.
