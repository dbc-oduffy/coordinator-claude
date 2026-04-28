---
name: requesting-staff-session
description: "Use when the PM asks for staff input on a plan or review, when the EM needs multi-perspective planning or critique, or when deciding between /staff-session and /review-dispatch. Guides tier selection, team composition, and scoping."
version: 1.0.0
---

# Requesting a Staff Session

Use `/staff-session` when the work benefits from **multi-perspective debate** — not just one reviewer's opinion, but positions challenged and refined by peers.

## When to Use Each Tier

| Situation | Tier | Why |
|-----------|------|-----|
| Quick sanity check on a plan or code | **Lightweight** → falls through to `/review-dispatch` | One smart reviewer is enough for gut-checks |
| Planning or reviewing where two perspectives would catch different things | **Standard** (2 debaters + Zolí synthesizer) | The default — two domain experts debate, Zolí synthesizes with ambition lens |
| Cross-cutting work touching multiple domains (UI + backend, game + infra) | **Full** (3-5 debaters + Zolí synthesizer) | Each domain expert brings irreplaceable lens; Zolí resolves contested topics |
| Post-execution code review | **Don't use staff session** — use `/review-dispatch` | Post-execution reviews are sequential by design (evolved artifact) |
| Per-stub reviews during enrichment | **Don't use staff session** — use single reviewer | Too heavy for individual stubs |

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
