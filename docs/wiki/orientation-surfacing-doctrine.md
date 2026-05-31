---
title: Orientation Surfacing Doctrine
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Orientation Surfacing Doctrine

**Purpose:** Rules for filtering and structuring orientation surfaces — the lists the EM reads at session start to choose work. Applies to `/session-start`, `/workday-start`, and any primary-list filter in a handoff index.

---

## Overview

An orientation surface is a list the EM reads at the start of a session to choose work. The filter on that surface has two distinct jobs:

1. **Reduce noise** — hide low-priority items of the SAME category as actionable items.
2. **Surface different categories distinctly** — items that need different action (gated/blocked/awaiting-external-signal) should never share the same filter threshold as actionable items.

Conflating the two produces silent burial. A `awaiting_gate` handoff is a different category of work from a `ready_to_fire` handoff. If both are sorted by "days since last touch" and only items older than 14 days surface, the EM sees neither — and a 13-day-old gate burns down without anyone noticing.

**Incident (2026-05-15):** `awaiting_gate` handoffs were filtered behind a 14-day staleness gate. The PM needed cross-workstream context that never crossed the threshold. The skill cited the spec faithfully, but the EM obeyed the filter too literally — the filter was structurally wrong, not just miscalibrated.

---

## The Rule

Items of a DIFFERENT category must surface as their OWN subsection with a **count-always** pattern — the count appears even when zero, so the EM knows the category exists and was checked:

```
## Primary actionable: 3
- 2026-05-17 auth-refactor (ready_to_fire)
- 2026-05-16 billing-fix (ready_to_fire)
- 2026-05-15 onboarding-rework (in_flight)

## Gated (awaiting external signal): 1
- 2026-05-09 jetbrains-roadmap (gate: project-rag Stream D ships, ~2026-05-20)

## Stale (>14 days, manual triage): 0
```

Items of the SAME category at lower priority MAY fold behind a threshold — e.g., `ready_to_fire` items older than 30 days collapse into a "manual triage" tab. The threshold compresses same-category noise; it must not compress cross-category signal.

---

## Test for the Rule

For any new filter on an orientation surface, ask:

> "Does this filter remove items the EM would take DIFFERENT action on than the surfaced items?"

- **Yes** → those items need their own subsection. The filter is structurally wrong.
- **No** → the filter is fine; it only compresses same-category noise.

Apply this test when designing a filter, not only when debugging a burial.

---

## Six Days, Not Fourteen

For gates with calendar-day cadence (PR review, cross-repo merges, external release), 14 days is too long — one working week is the natural drift threshold.

**Six days = "this should have moved by now."**

A gate that has not moved in six days warrants a nudge in the orientation surface, not silence. Fourteen days means the EM may have gone two full workweeks without noticing a stalled dependency.

---

## Anti-Pattern: Threshold Tuning

If you find yourself adjusting a staleness threshold when buried items keep reappearing, the threshold is not the problem — the categories are.

"Tuning the threshold" is the same shape as the resolved-terminal-states graveyard pattern: the right answer is structural visibility (a dedicated subsection), not a better number. If the threshold needs to differ per category, the categories are different and need different surfaces.

---

## Applying to New Surfaces

When adding a filter to any orientation surface (new `/workday-start` step, new handoff index, new task-list preamble):

1. Enumerate the deployment states or item categories the surface will touch.
2. Group them: same-action categories share a threshold; different-action categories get separate subsections.
3. Write the subsection headers first, with zero-count placeholders, before writing the filter logic. This surfaces the category model before implementation details obscure it.
4. Run the test from "Test for the Rule" against every filter predicate before shipping.

If a surface produces a single undifferentiated list, treat that as a design smell — it means either (a) all items are truly same-category (uncommon) or (b) the categories were collapsed without applying the test (common).

---

## Orientation Budget Compatibility

These rules operate within the boot-time orientation budget. Surfacing extra subsections does not violate the budget — zero-count subsections are one line each, and a gated item with its gate condition is rarely more than two lines. The cost of structural visibility is negligible; the cost of silent burial is a missed dependency.

---

## Related

- → `docs/wiki/tiered-context-loading.md` (boot-time orientation budget and tier discipline)
- → `coordinator/CLAUDE.md` § Session Orientation (the `/session-start` is PM-invoked rule and quick-orient boot)
- → `coordinator/CLAUDE.md` § Handoff Lineage (handoff frontmatter `deployment_state` enum: `awaiting_gate | ready_to_fire | in_flight | shipped | abandoned`)
