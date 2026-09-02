---
segment_id: diff-sequencing
surface: diff
class: protected
order: 50
---

**`--surface diff`:**
- **In-session code reviews → sequential (HARD RULE).** Integrate Reviewer 1's findings via `coordinator:review-integrator` BEFORE dispatching Reviewer 2.
  _See CLAUDE.md § Review Sequencing._
- **Merge-gate parallel carve-out applies ONLY at `/workweek-complete` Step 7** on a frozen weekly diff with orthogonal lenses + no-rewrite synthesizer. Does NOT apply to mid-session, `/merging-to-main`, or `/workday-complete` reviews.
  _See CLAUDE.md § Review Sequencing ¶ exception (merge-gate code review on frozen diff)._
- _Frozen weekly diff at `/workweek-complete` Step 7?_
  → Exit this skill; use `coordinator:parallel-code-review`.
