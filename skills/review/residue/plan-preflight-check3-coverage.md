---
segment_id: plan-preflight-check3-coverage
surface: plan
class: protected
order: 5
---

**Check 3 — Plan internal completeness (plan-coverage-checker)** _(runs independently of Checks 1 and 2)_

| Plan shape | plan-coverage-checker? |
|---|---|
| Plan contains an audit/findings/issues table (any size) | **Run.** |
| Plan is greenfield design with no found-facts oracle | Skip — agent emits `SCOPE-MISMATCH`. |
| Plan is single-file mechanical fix | Skip. |
| Plan is doc redesign / wiki rewrite | Skip. |

Skip is silent — no flag, no justification.
