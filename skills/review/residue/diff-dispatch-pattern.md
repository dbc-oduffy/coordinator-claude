---
segment_id: diff-dispatch-pattern
surface: diff
class: protected
order: 40
---

**Pattern B — unnamed Sonnet `code-reviewer` (`--surface diff` only):** dispatch `coordinator:code-reviewer` (background, UNNAMED — no `name:` param), brief includes the frozen `$DIFF_PATH` per A.1 above; the reviewer's provisioned `review-findings` sidecar path is already in the brief. It returns the same `DONE:` pointer form. There is exactly one `coordinator:code-reviewer` — no `-selfpersist` variant, no claim marker.
