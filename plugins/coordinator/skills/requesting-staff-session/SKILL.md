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
