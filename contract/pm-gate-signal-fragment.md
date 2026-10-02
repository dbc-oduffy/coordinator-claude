# PM-gate-signal fragment

`pm-gate-signal-fragment.json` is the four-leg rule behind `detect-pm-gate-signal` — three
detection legs and one judgment leg — deciding **which stubs need a `pm-gates.md` row** at
`roadmap-planning` Step 2.5. DoE owns the rule; a consumer reads the legs from here and never re-derives
them, on the `review-roster-fragment` precedent.

Doctrine source: `docs/wiki/planning/roadmap-planning-residue.md` § "pm-gates.md — detection rule and
template", and `skills/roadmap-planning/SKILL.md` step 2.5. This fragment is the machine-readable
projection of those two; they stay the prose source of record.

## The detector recommends; it never decides

`emits: "recommendation"` and `exhaustive: false` are the load-bearing fields, and a consumer that
ignores them builds the wrong thing.

The census types Step 2.5 MIXED for a reason: detecting the signal is mechanical, **authoring the
gate question is not**. The detector's output is a candidate stub_id list that feeds an
`advisory` judgment point — never a finished `pm-gates.md`. And the rule is explicitly open: the
author adds rows manually for product-coupled questions the detector does not trip. A manual row
is a normal outcome, not a detector failure, so nothing may treat the detected set as closed or
reconcile a manual row away as spurious.

The reverse is what would actually break: `audit-roadmap` Audits 3 and 4 cross-check both
directions at Phase 2 close, so a row emitted with no stub referencing it back blocks the close
with exit 1 just as a missed gate does. Emit candidates, not rows.

## Why the legs have different precision

`pm-prefix` is unambiguous — the author typed the prefix to mean this. `user-facing` is a
high-precision term lookup, and so is `named-stakeholder`'s mechanical floor within its own
narrow reach. `decision-approval-policy-scope` is deliberately low-precision: `policy` and `scope` fire on ordinary prose like "out of scope."

That asymmetry is intentional and must not be tuned away. The two failures are not symmetric — a
missed PM gate blocks a roadmap close at Audit 3 and costs a round trip with the PM, while an
over-fired candidate costs the author one dismissal at authoring time. `precision` exists so a
consumer can ORDER or annotate candidates, never so it can drop the low-precision leg.

## `named-stakeholder` is a judgment leg with a mechanical floor

Three of the four legs are detection. This one is not, and building it as a matcher is the
mistake the fragment exists to prevent.

Who a gate is addressed to is frequently a peer **team** rather than a role word — "coordinate
with the engine team", "ask whoever owns the ingest path". Resolving that takes knowledge of
the fleet and of who is actually on the hook for the thing, and no term list holds it. So the leg
carries `judgment_required: true` and `surfaces_as: "judgment_point"`: the floor's role words fire
mechanically, and everything past them surfaces as an offer to the EM rather than a silent yes or
no. A consumer that implements the floor and reports the leg done has closed a judgment call by
omission — the four-part rule would be three parts and a matcher.

The floor is deliberately not extended into peer-team or person names, by roster or by inference.
A hardcoded fleet roster decays the first time a repo is added or renamed, and the failure is
invisible in the worst way: a gate silently addressed to nobody, on a stub that reads as gated.

## Scanned fields

`gate_notes` is the field this rule is really about (renamed from `blocking_notes`, DR-190 §13 —
the old name claimed a gating role this field never had). `blocking_notes` stays scanned as a
deprecated alias during the migration window: it still validates on existing records and on
not-yet-re-vendored writers, so the corpus carries it and a detector that skips it misses live
stubs. `gate_dependency` is a separate deprecated predecessor — nothing authors new values into
it either, but it still validates on existing records, so the corpus carries it and a detector
that skips it misses live stubs.

`blocked_by` is excluded by design. It holds resolvable slugs rather than prose, and scanning it
would trip the `scope` token on any stub_id containing that substring — a false gate on a field
whose whole purpose is being machine-resolvable.

## Changing it

Adding a term widens what fires; removing one silently narrows it, and the loss shows up as a
blocked roadmap close weeks later rather than as a test failure. `tests/test_supplied_fragments.py`
pins the leg ids, the `PM `-prefix leg's exact term (Audit 3 keys on that literal prefix), the
deprecated-field scan, and the `blocked_by` exclusion.
