---
segment_id: diff-sequencing
surface: diff
class: protected
order: 50
---

**`--surface diff`:**
- **Plan-bearing work → the execute-review stage.** A diff produced by `/execute-plan` is reviewed
  per executor group inside that same emitted workflow, every reviewer applying its own
  findings. See
  `coordinator/skills/execute-plan/SKILL.md` and `coordinator/skills/review/SKILL.md` § A.3. This
  skill's outgoing branch is not the dispatch vehicle for that review; nothing here re-partitions
  or re-dispatches it.
- **Ad hoc diff review (`/review-code`, no plan/no slice partition) → in order; a chatty run reviews in one parallel wave (§ A.3).**
  Reviewer 1 applies and verifies before Reviewer 2 is dispatched.
- _Frozen weekly diff at `/workweek-complete` Step 7?_
  → Exit this skill; use `coordinator:parallel-code-review`.
