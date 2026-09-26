---
segment_id: diff-dispatch-pattern
surface: diff
class: protected
order: 40
---

**Pattern B — unnamed Sonnet `code-reviewer` (`--surface diff` only):** dispatch `coordinator:code-reviewer` (background, UNNAMED — no `name:` param), brief includes the frozen `$DIFF_PATH` per A.1 above; the reviewer's provisioned `review-findings` sidecar path is already in the brief. When the review is plan-scoped, the brief also includes the output of `pm-brief.py render --for reviewer <plan>`, pasted as rendered and never summarised — the PM's verbatim intent, not this pattern's own paraphrase of it. It returns the same `DONE:` pointer form. There is exactly one `coordinator:code-reviewer` — no `-selfpersist` variant, no claim marker.
