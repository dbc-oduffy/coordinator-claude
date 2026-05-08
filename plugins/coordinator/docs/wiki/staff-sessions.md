---
title: Staff Sessions
system: staff-sessions
status: distilled
distilled_from:
  - archive/specs/2026-03-22-staff-sessions.md
  - plugins/coordinator-claude/coordinator/skills/requesting-staff-session/SKILL.md
distilled_at: 2026-05-06
distilled_run: 2026-05-06-13h00
---

# Staff Sessions

## Overview

A **staff session** is an Agent Teams-based collaborative planning or review pattern: 2-5 persona reviewers debate in parallel via SendMessage, then a synthesizer (Opus teammate) cross-references positions and produces a single canonical artifact. PM-gated: only invoke when the PM explicitly asks. Reserved for genuinely architectural decisions; routine workflow changes go through `/review-dispatch` with a single reviewer.

## Architecture

### Tier composition

| Tier | Shape | When |
|------|-------|------|
| Lightweight | Falls through to `/review-dispatch` (single reviewer) | Tradeoff-free quality fixes |
| Standard | 2 debaters + synthesizer (3 total) | Default for architectural questions |
| Full | 3-5 debaters + synthesizer (4-6 total) | Multi-domain or irreversible structural choices |

Default standard pairings: the Staff Engineer + the Ambition Advocate (architecture / cross-cutting), the Game Dev Reviewer + the Staff Engineer (game dev), the Front-End Reviewer + the UX Reviewer (frontend), the Data Science Reviewer + the Staff Engineer (data).

### When a single reviewer is the right tool instead

The default for any review is `/review-dispatch` with one reviewer. Staff session is the exception, not the menu. If you can't articulate why a single reviewer would miss something a panel would catch, you don't need a staff session.

| Situation | Right tool | Why |
|-----------|------------|-----|
| Quick sanity check on a plan or code | `/review-dispatch` (single reviewer) | One smart reviewer is enough for gut-checks |
| Routine workflow / doctrine / process change | `/review-dispatch` (single reviewer) | Reversible, low blast radius — single perspective is correct |
| Single-skill or single-command edit | `/review-dispatch` (single reviewer) | Scoped artifact; one expert lens fits |
| Post-execution code review | `/review-dispatch` | Sequential by design (evolved artifact) |
| Per-stub reviews during enrichment | single reviewer | Too heavy for individual stubs |
| Genuinely architectural decision crossing two domains, with real cost in being wrong | **Standard** staff session (2 debaters + the Ambition Advocate) — *PM authorization required* | Two domain experts debate, the Ambition Advocate synthesizes |
| Cross-cutting work touching three+ domains where each lens is irreplaceable | **Full** staff session (3-5 debaters + the Ambition Advocate) — *PM authorization required* | Each domain expert brings a lens no other can substitute |

The bar for even *asking* the PM whether a staff session is warranted: the work is genuinely architectural — cross-system design, irreversible structural choice, multi-domain tradeoff with real cost in being wrong. If you're tempted to recommend one for a one-afternoon process change, you're miscalibrated; do the lighter thing instead.

### Modes

One command (`/staff-session`), two modes:

- **Plan mode** — craft a detailed plan from objectives. Ceiling: 10 min.
- **Review mode** — critique an existing artifact. Ceiling: 8 min.

Team lifecycle, blocking chain, and synthesis pattern are structurally identical across modes — splitting into two commands would duplicate ~80% of logic.

### Synthesizer is a teammate, not the EM

When the team spawns, the EM is freed. The Ambition Advocate (Opus) does cross-referencing as synthesizer and teammate, blocked on all debaters via `blockedBy`. Same pattern as research pipelines.

### Output is a reviewed plan

Staff session output IS a reviewed plan. The `/enrich-and-review` Phase 0 gate accepts the regex match `Staff session ({participants}) — debated and synthesized` as proof of review.

## Key Patterns

### Debate message protocol

Categories: `POSITION`, `CHALLENGE`, `CONCESSION`, `QUESTION`, `DONE`.

Volume governance: max 4 messages per peer, max 12 total per debater.

**Wake-up mechanism:** `blockedBy` is a file-based polling gate, not an event trigger. Each debater MUST send `DONE` to the synthesizer to wake it.

### Self-governance timing

- **Floor:** 3 min AND 1 peer exchange round.
- **Diminishing returns:** last 2 exchanges produced no position changes.
- **Ceiling:** plan mode 10 min, review mode 8 min. Steps 1-6 of convergence may extend 1-2 min past ceiling; no new `CHALLENGE` accepted after ceiling.

### Convergence protocol

1. Send `CONVERGING` to all peers.
2. Wait ~20s for final challenges.
3. Answer final challenges.
4. Write position to `{scratch-dir}/{persona-slug}-position.md`.
5. Mark task completed.
6. Send `DONE` to synthesizer.

### All debaters are Opus

Debate requires judgment, not retrieval. Cost is ~3 Opus × 8-10 min ceiling — comparable to sequential review.

### Scoping checklist

Before invoking `/staff-session`, the EM should have:

- [ ] PM-aligned objectives (plan mode) or the artifact to review (review mode)
- [ ] Context files identified (related plans, key source files)
- [ ] Constraints noted (timeline, dependencies, boundaries)
- [ ] Tier selected based on the decision table above
- [ ] Team composition confirmed (or accept auto-selection)

### docs-checker pre-flight

For artifacts that cite external APIs — particularly C++ or Unreal Engine code — the EM should consider running the `docs-checker` agent before dispatching the Opus reviewer team. docs-checker verifies API names, signatures, and headers at Sonnet cost, so the staff reviewers spend their time on contested design decisions rather than mechanical lookups. The skip is an EM call and is silent — pure prose, in-repo-only references, and routine in-distribution code don't need it. **Skipping docs-checker does NOT extend to skipping the review itself — only the PM may waive a review on an EM plan.** Full EM decision rules: [docs-checker-pre-review](docs-checker-pre-review.md). Mechanical flow: `commands/review-dispatch.md` Phase 2.7.

### 7-teammate cap

Agent Teams enforces a hard limit of 7 teammates per session. When a pipeline needs an extra step between existing phases (e.g., an atlas sketch between scouts and specialists), **dispatch it as a regular subagent — not a teammate.**

The EM is not freed during that subagent window, but the overhead is small: a focused subagent running one well-specified task completes quickly, and the EM resumes team coordination immediately after. This is preferable to restructuring the team composition or exceeding the cap.

**Pattern:** scouts (N teammates) → EM dispatches subagent for inter-phase work → specialists (M teammates). Total teammates: N + M, staying within 7.

The related antipattern — allocating a team slot to an agent whose only job is mechanical merge/dedup/concat — has its own home in [dispatching-parallel-agents § Anti-Pattern: Dedicated Mechanical-Merge Slots](dispatching-parallel-agents.md).

## Example invocations

```
# Standard plan session — auto-selects Staff Engineer + Game Dev Reviewer for architecture, Ambition Advocate synthesizes
/staff-session --mode plan --tier standard "Design the executor abort/escalation protocol"

# Standard review — explicit reviewers, Ambition Advocate synthesizes
/staff-session --mode review --tier standard --members "staff-game-dev,staff-eng" docs/plans/2026-03-22-holodeck-refactor.md

# Full plan session — multi-domain debaters, Ambition Advocate synthesizes
/staff-session --mode plan --tier full --members "staff-eng,staff-game-dev,staff-data-sci" "Design cross-system AI behavior pipeline"

# Lightweight — falls through to single-reviewer dispatch (no Ambition Advocate synthesis)
/staff-session --mode review --tier lightweight --members "staff-eng" docs/plans/quick-fix.md
```

## Gotchas

- **Backstop protocols suspended during staff sessions.** Parallel debate serves the same multi-perspective challenge function; double-counting wastes tokens.
- **No simulated-PM agent.** Push-for-more is a synthesizer prompt lens; if a business perspective is needed, the Ambition Advocate is the closest fit.
- **Reuses existing reviewer agents** with a tool-list addition (`SendMessage`, `TaskUpdate`, `TaskList`, `TaskGet`). These tools are no-op outside Agent Teams; non-team dispatches via `/review-dispatch` are behaviorally unchanged.
- **PM-gated, never EM-initiated.** If the EM thinks a staff session is warranted, ask first. NEVER invoke from a subagent.

## Reference

- Related: [reviewer-routed-workers](reviewer-routed-workers.md)
- Source plan: `archive/specs/2026-03-22-staff-sessions.md`
