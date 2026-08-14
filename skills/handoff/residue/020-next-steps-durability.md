---
segment_id: next-steps-durability
case: shared
class: protected
order: 20
---

## Recommended-Next-Steps Durability

These rules apply specifically to `## Recommended Next Steps` and `## In-Progress Work` — not to `## Current State` or `## Files Modified This Session`, which legitimately carry procedural detail because they describe what *is*, not what to *do*.

1. **No file paths or line numbers in next-steps prose.** They go stale within hours. Reference subsystems and concepts instead. _Exception:_ when the path IS the artifact (e.g., "the plan at `docs/plans/<plan-name>.md`"), that's an identifier, not a procedural step.
2. **Behavioral, not procedural.** Describe *what* the next session needs to accomplish, not *how*. The "how" goes stale; the "what" is durable.
3. **Each next step is independently verifiable.** The picker should be able to confirm "done" without reading this handoff again.
4. **Explicit out-of-scope line.** End every `## Recommended Next Steps` section with an "Out of scope for next session" line, so a fresh-eyed picker doesn't gold-plate or drift.

**Predecessor identification.** The predecessor is whatever handoff *this session was opened with* — period:

1. Session started with `/pickup <handoff>` — that file is the predecessor. Canonical signal.
2. The PM explicitly named a handoff at session start.
3. Neither? This handoff has **no predecessor** — omit the `Continuing from` preamble, write standalone.

**"Most recent file in `state/handoffs/`" is a facile signal — do not use it.** Concurrent sessions across machines routinely produce adjacent handoffs that have nothing to do with each other. Adjacency is not ancestry. Picking the most recent timestamp corrupts the audit trail and incorrectly archives active work belonging to other workstreams.
