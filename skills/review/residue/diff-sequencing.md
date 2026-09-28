---
segment_id: diff-sequencing
surface: diff
class: protected
order: 50
---

**`--surface diff`:**
- **Plan-bearing work → the execute-review stage.** A diff produced by `/execute-plan` is reviewed
  as stages of that same emitted workflow: one parallel wave of slice-owning reviewers plus
  whole-diff findings-only lenses, then exactly one integration pass. See
  `coordinator/skills/execute-plan/SKILL.md` and `coordinator/skills/review/SKILL.md` § A.3. This
  skill's outgoing branch is not the dispatch vehicle for that review; nothing here re-partitions
  or re-dispatches it.
- **Ad hoc diff review (`/review-code`, no plan/no slice partition) → sequential.** Reviewer 1
  applies and verifies its own findings ledger before Reviewer 2 is dispatched — there is no slice
  partition here to make concurrent writes disjoint.
- _Frozen weekly diff at `/workweek-complete` Step 7?_
  → Exit this skill; use `coordinator:parallel-code-review`.
