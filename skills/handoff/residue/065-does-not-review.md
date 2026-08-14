---
segment_id: does-not-review
case: shared
class: protected
order: 65
---

## `/handoff` Does Not Review

**No review step lives here, by ruling.** The reason is structural, not budgetary: the diff a handoff
writes is **in flight**, and an in-flight diff is the state least worth reviewing — findings against
half-finished work are noise the successor must re-adjudicate against whatever they actually finish.
Read that as a reason **not** to review, not a deferral this skill needs to justify.

Review ownership stays where it sits: `/workstream-complete`, `/quick-wrap`, and
`/workweek-complete`'s parallel gate, each firing against a settled diff. Do not reintroduce a
conditional version ("only when the diff contains code") — considered and rejected; the objection is
to reviewing in-flight work at all, not to the cost of reviewing docs.
