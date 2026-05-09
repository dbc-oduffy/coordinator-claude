---
kind: wiki
title: Spinoff Handoffs — Mid-session Forks vs Continuations
status: active
created: 2026-05-06
sources:
  - archive/handoffs/2026-05-05_104957_spinoff-formalization.md
tags: [spinoff-handoffs]
---

# Spinoff Handoffs

A **spinoff** is mid-session fork: *"I'm working on X, but topic Y came up that deserves its own session — here's a self-contained spec for Y, written so you can pick it up cold without my context."* It is distinct from a continuation handoff, a plan, and a queue entry.

The metaphor is the TV-series sense: same universe, separate series. The word reads naturally as both noun and verb.

## Handoff No-Successor Gate — Step 0

Before writing ANY handoff (spinoff or continuation), run Step 0: the successor-work check. The gate is binary.

**NO-tests — any one of these → STOP, do not write a handoff:**

1. The workstream's next action is `/merge-to-main`, or the terminal PR is already merged with no follow-up commits expected.
2. Work is described in your head as "shipped," "complete on branch ready for merge," or "ready for the merge gate." That phrasing IS the disqualifier — write a commit message, not a handoff.
3. All in-flight chunks of the active plan have landed and the plan doc is marked complete.

**YES-tests** (only consulted if ALL NO-tests fail):
- In-progress edits not yet at a stopping point, AND a successor session must resume them
- A plan in flight with remaining unexecuted chunks (not chunks that just landed in this session)

**When to write a commit-and-stop instead of a handoff:**
"Shipped" work that needs no successor → `/workday-complete` week-changelog or commit-and-stop. A completed workstream does not need a `tasks/handoffs/` entry.

Source: `archive/specs/2026-05-07-handoff-no-successor-gate.md` (status: complete, 2026-05-07).

## When to spinoff

Three signals indicate a spinoff is the right shape:

1. The current session's bandwidth is already spent on its primary mandate.
2. The new topic deserves a full session of attention rather than being squeezed into a tail.
3. The PM observes the same need and asks (or you anticipate they would).

Continuing a session past the point where focus has split empirically produces neither workstream cleanly. Spinning off both gets a fresh context.

## Spinoff vs handoff vs plan vs queue entry

| Artifact | Timing | Predecessor | Purpose |
|---|---|---|---|
| `/handoff` | end-of-current-session | the just-finished session | continuation |
| `/spinoff` | mid-session | none (fork) | self-contained spec for a different workstream |
| plan (`docs/plans/`) | pre-execution | n/a | EM's design for work the EM intends to dispatch |
| queue entry | non-urgent | n/a | one-line pointer awaiting triage |

A spinoff matches a real handoff in detail: load-bearing context, references, acceptance criteria, anti-scope. It is **not** a one-line queue entry — it must be pickup-able cold.

## Frontmatter schema

```yaml
kind: spinoff
status: active
predecessor: none           # always — spinoffs have no continuity ancestor
authoring_session: <one-line description>   # replaces predecessor link as audit trail back to origin
workstream: <slug>          # required, so /pickup can group them
```

`predecessor: none` is load-bearing. The "Single Predecessor, No Adjacency-Inference" rule (in coordinator/CLAUDE.md) requires every handoff to have a single named predecessor or `none`. Spinoffs are always `none`; the audit trail back to origin lives in `authoring_session`.

## Pickup-side and workday-start handling

- **`/pickup` with `kind: spinoff`** prepends a one-line banner: *"This is a spinoff workstream — predecessor is none; treat the handoff body as ground-truth spec and proceed."*
- **`/workday-start`** lists spinoffs separately from active handoffs in the orientation cache.
- **Stale spinoff nudge:** a spinoff that hasn't been picked up after N days (default 14) gets a heads-up nudge in `/workday-start`.

## Why this exists as a formal pattern

Three pre-formalization signals motivated it (see [DR-013](#dr-013)):

1. **Recurring pattern** — real instances were executed within 3 minutes of each other by concurrent EMs.
2. **Ad-hoc shape leaks** — the validator rejected `status: orphan-promotion` as an invalid enum because the ersatz form leaked into a real frontmatter.
3. **PM friction** — verbal description was needed each time.

## Decision Records

### DR-013 — Formalize the pattern as `coordinator:spinoff` skill

**Status:** accepted
**Decision:** Replace ad-hoc "ersatz-handoff" / "orphan-promotion handoff" naming with `kind: spinoff`; ship a skill that drafts the spec.
**Consequences:** Validator enum gains `spinoff`; pickup banner; workday-start segregation; stale nudge.
**Source:** `archive/handoffs/2026-05-05_104957_spinoff-formalization.md`

### DR-014 — `predecessor: none` always, audit trail in `authoring_session`

**Status:** accepted
**Decision:** Spinoffs never carry a predecessor link — they are forks, not continuations. The `authoring_session` field carries the audit trail back to origin.
**Consequences:** `/pickup` banner can be deterministic; lineage rules treat spinoffs as roots.
