---
name: requesting-staff-session
description: "PM-GATED — only invoke on explicit PM authorization. Guides tier selection, team composition, and scoping. Never auto-recommend or invoke from a subagent."
version: 1.1.0
---

# Requesting a Staff Session

`/staff-session` is **PM-gated** — only the PM may authorize it. The EM does not propose staff sessions for routine workflow changes, doctrine tweaks, single-skill edits, or small process changes; for those, use `/review-dispatch` with one reviewer.

The bar for even *asking* the PM whether a staff session is warranted: the work is genuinely architectural — cross-system design, irreversible structural choice, multi-domain tradeoff with real cost in being wrong. If you're tempted to recommend one for a one-afternoon process change, you're miscalibrated; do the lighter thing instead.

When the PM has authorized a session, this skill guides tier selection, team composition, and scoping.

## Multi-Perspective Debate vs. Single-Reviewer Dispatch

`/staff-session` exists for work that benefits from **multi-perspective debate** — not just one reviewer's opinion, but positions challenged and refined by peers. Most reviews don't need that.

## When Staff Session Is the Right Tool

The default for any review is `/review-dispatch` with one reviewer. Staff session is the exception, not the menu.

| Situation | Right tool | Why |
|-----------|------------|-----|
| Quick sanity check on a plan or code | `/review-dispatch` (single reviewer) | One smart reviewer is enough for gut-checks; this is NOT a staff-session situation |
| Routine workflow / doctrine / process change | `/review-dispatch` (single reviewer) | Reversible, low blast radius — single perspective is correct |
| Single-skill or single-command edit | `/review-dispatch` (single reviewer) | Scoped artifact; one expert lens fits |
| Post-execution code review | `/review-dispatch` | Sequential by design (evolved artifact) |
| Per-stub reviews during enrichment | single reviewer | Too heavy for individual stubs |
| Genuinely architectural decision crossing two domains, with real cost in being wrong | **Standard** staff session (2 debaters + Zolí) — *PM authorization required* | Two domain experts debate, Zolí synthesizes |
| Cross-cutting work touching three+ domains where each lens is irreplaceable | **Full** staff session (3-5 debaters + Zolí) — *PM authorization required* | Each domain expert brings a lens no other can substitute |

If you can't articulate why a single reviewer would miss something a panel would catch, you don't need a staff session.

## When to Use Plan Mode vs Review Mode

| I need... | Mode |
|-----------|------|
| A detailed implementation plan crafted by staff engineers | `--mode plan` |
| Multi-perspective critique of an existing plan, spec, or code | `--mode review` |

**Plan mode** replaces the EM writing the plan. The EM writes objectives; the team writes the blueprint.

**Review mode** replaces the sequential `/review-dispatch` for pre-chunking plan review.

## Scoping Checklist

Before invoking `/staff-session`, the EM should have:

- [ ] PM-aligned objectives or the artifact to review
- [ ] Context files identified (related plans, key source files)
- [ ] Constraints noted (timeline, dependencies, boundaries)
- [ ] Tier selected based on the decision table above
- [ ] Team composition confirmed (or accept auto-selection)

## docs-checker Pre-Flight

For artifacts that cite external APIs — particularly C++ or Unreal Engine code — the EM should consider running the `docs-checker` agent before dispatching the Opus reviewer team. docs-checker verifies API names, signatures, and headers at Sonnet cost, so the staff reviewers spend their time on contested design decisions rather than mechanical lookups. The skip is an EM call and is silent — pure prose, in-repo-only references, and routine in-distribution code don't need it. **Skipping docs-checker does NOT extend to skipping the review itself — only the PM may waive a review on an EM plan.** Full EM decision rules: `docs/wiki/docs-checker-pre-review.md`. Mechanical flow: `commands/review-dispatch.md` Phase 2.7.

## 7-Teammate Cap

Agent Teams enforces a hard limit of 7 teammates per session. When a pipeline needs an extra step between existing phases (e.g., an atlas sketch between scouts and specialists), **dispatch it as a regular subagent — not a teammate.**

The EM is not freed during that subagent window, but the overhead is small: a focused subagent running one well-specified task completes quickly, and the EM resumes team coordination immediately after. This is preferable to restructuring the team composition or exceeding the cap.

**Pattern:** scouts (N teammates) → EM dispatches subagent for inter-phase work → specialists (M teammates). Total teammates: N + M, staying within 7.

## Anti-Pattern: Dedicated Mechanical-Merge Slots

**Do not allocate a team slot to an agent whose only job is dedup/concat/reformat.** Every slot in a 7-teammate session is precious; mechanical merge does not justify one.

When an agent's entire brief is "take these N specialist outputs and combine them," fold that work into the producers (via adversarial peer interaction) or the consumer that already has judgment (e.g., the Opus synthesizer or the EM). A team slot must justify itself with judgment work, not bookkeeping.

**Empirical basis:** In one measured pipeline run, the dedicated consolidator added 4+ minutes wall-clock and was beaten to completion by the downstream sweep that read raw specialist outputs directly.

If a consolidation step genuinely requires judgment (contradiction reconciliation, cross-domain synthesis, edge-case resolution), give it to the consumer-with-judgment rather than a dedicated consolidator slot.

## Example Invocations

```
# Standard plan session — auto-selects Patrik + Sid for architecture, Zolí synthesizes
/staff-session --mode plan --tier standard "Design the executor abort/escalation protocol"

# Standard review — explicit reviewers, Zolí synthesizes
/staff-session --mode review --tier standard --members "sid,patrik" docs/plans/2026-03-22-holodeck-refactor.md

# Full plan session — multi-domain debaters, Zolí synthesizes
/staff-session --mode plan --tier full --members "patrik,sid,camelia" "Design cross-system AI behavior pipeline"

# Lightweight — falls through to single-reviewer dispatch (no Zolí synthesis)
/staff-session --mode review --tier lightweight --members "patrik" docs/plans/quick-fix.md
```
