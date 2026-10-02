---
segment_id: does-not-review
case: shared
class: protected
order: 65
---

## `/handoff` Does Not Review

**No review step lives here, by ruling.** The diff a handoff writes is **in flight**, and findings against half-finished work are noise the successor must re-adjudicate.

Review ownership stays where it sits: `/workstream-complete`, `/quick-wrap`, and
`/workweek-complete`'s parallel gate, each firing against a settled diff. Do not reintroduce a
conditional version ("only when the diff contains code") — considered and rejected; the objection is
to reviewing in-flight work at all, not to the cost of reviewing docs.
