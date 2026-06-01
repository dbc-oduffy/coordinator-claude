---
status: draft
kind: plan
---

# Fixture Plan — Acceptance Oracle Gate Tests

> Synthetic plan used exclusively by `tests/acceptance-oracle/run-tests.sh`.
> Not a real workstream plan; all criteria are designed to exercise specific gate behaviours.

## Acceptance Criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|----|-------------------|---------------------|---------------|--------|
| 1 | Phrase "Acceptance Oracle" is present in writing-plans.md (single-path grep match). | `grep:Acceptance Oracle@plugins/coordinator/docs/wiki/writing-plans.md` | gate-bound | ☐ |
| 2 | Token DEFINITELY_NOT_PRESENT_TOKEN is absent from writing-plans.md (grep should find nothing → red). | `grep:DEFINITELY_NOT_PRESENT_TOKEN@plugins/coordinator/docs/wiki/writing-plans.md` | gate-bound | ☐ |
| 3 | Commit 79ff46da (Task 1 writing-plans.md commit) is present in local history (cited SHA resolves). | `cited:79ff46da8e5c8b567e2f3a1ecc3e7b89f7b7742b` | gate-bound | ☐ |
| 4 | A non-existent SHA resolves — it should not (cited SHA that does not exist → red). | `cited:0000000000000000000000000000000000000000` | gate-bound | ☐ |
| 5 | Quality criterion: the fixture is well-shaped for human review — no mechanical test can confirm this. | `reviewer-judgment` | reviewer-judgment | ☐ |
| 6 | "Acceptance Oracle" must appear in BOTH writing-plans.md AND coordinator/CLAUDE.md (multi-path all-must-match; second path lacks the phrase → red). | `grep:Acceptance Oracle@plugins/coordinator/docs/wiki/writing-plans.md,plugins/coordinator/CLAUDE.md` | gate-bound | ☐ |
| 7 | A shell script that exits 0 must register green (sh: prefix smoke — PASS path). | `sh:plugins/coordinator/tests/acceptance-oracle/fixture-sh-pass.sh` | gate-bound | ☐ |
| 8 | A shell script that exits 1 must register red (sh: prefix smoke — FAIL path). | `sh:plugins/coordinator/tests/acceptance-oracle/fixture-sh-fail.sh` | gate-bound | ☐ |
| 9 | bash: alias must also work — exits 0 → green. | `bash:plugins/coordinator/tests/acceptance-oracle/fixture-sh-pass.sh` | gate-bound | ☐ |
