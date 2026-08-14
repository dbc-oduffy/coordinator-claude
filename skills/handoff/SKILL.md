---
name: handoff
description: "Mid-workstream save-state under context pressure — always a continuation."
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session Handoff — Save State for Next Session

> **Handoff is involuntary by definition — with exactly two sanctioned deliberate triggers.** The
> baseline is context pressure forcing a stop mid-workstream before the next action can land.
> Reaching for `/handoff` because the work *feels* like a good place to pause is the
> disqualifier. Workstreams end via `/workday-complete`, `/merge-to-main`, or `/quick-wrap` —
> never via handoff. **Exception 1 — plan→execute execution handoff:** review-integration done
> and the plan stamped `execution_authorized_at`; legitimate independent of context pressure.
> **Exception 2 — review-owed close handoff** (§ Step 0), which still requires genuine context
> pressure. Both are gated triggers, not a general license.

> **Continuation vs. fork.** This skill writes a *continuation* — work this session was doing
> that someone resumes. A *different* mid-session topic for someone to pick up cold is
> `/spinoff` (`kind: spinoff`, `predecessor: none`). **The next *phase* of the same multi-phase
> workstream (research → goal-setting → plan → execute → verify) is a continuation, not a
> fork**, even when the phase boundary reads as a new topic. Never redirect a phase-transition
> handoff to `/spinoff`.

The assembler computes the mechanical spine — deliverable/initiative id inheritance, frontmatter
scaffolding, `handoff_phase` stamping, tracker refresh, and (on a clean chain) predecessor
archival — into one decision object per handoff. What follows is the judgment residue it cannot
resolve for you: it narrows the evidence, you decide.

Compute via
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/baton-assemble" brief handoff <artifact-path>`.

**`<artifact-path>` is the artifact this handoff is written FROM — on the plan→execute trigger
that is the PLAN, not a handoff.** Passing a handoff, or nothing (self-resolves to the held
handoff), falls through silently to the predecessor's id or a fresh mint. Plan and executing
handoff then carry different `deliverable_id`s, and close-out reports a fully-shipped plan as
entirely unshipped. Right on an ordinary continuation; wrong and silent at the plan→execute seam
(calibration: wiki).

Feed resolutions back via `apply --decisions '<json>'`: a JSON object mapping each
`judgment_points[].id` to `{"disposition": "<value>"}`, values taken from that point's own
`dispositions[].value` in the same `brief` output. `{"value": "<v>"}` is an accepted equivalent;
a `decision_note` sibling key is carried through.

**`apply` is the single route out — never hand-execute the directive list.**
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/baton-assemble" apply handoff <artifact-path> --decisions '<json>'`
— same `<artifact-path>` as `brief`, plus the resolutions above (calibration: wiki).

The remaining procedure detail — body authoring, `distill_fate`/`d5` release, next-steps
durability, `carried_items` minting and its disposition gate, dirty-tree case-(c) and safe-commit
grouping, supersession, orientation refresh — arrives with this invocation, scoped to the case
resolved here. It lives in `coordinator/skills/handoff/residue/`; you should not need to open it.

---

## Step 0: Trigger Check — Is Context Pressure Actually Forcing This?

Before writing anything, confirm at least one trigger fires and no NO-test trips (full gate,
NO-tests, YES-tests: wiki). The PRIMARY question is whether the current session can still take
its next action; if it can, you are not handing off, you are deferring — a doctrine violation
regardless of how "tidy" the current state looks. If nothing fires, STOP and take the next
action in this session instead.

**Inverted antipattern:** picking up a handoff this session does not license appending a
progress block to the predecessor's (now `status: claimed`) body instead of writing a successor.
A claimed handoff is paper trail — the pickup index treats it as historical, so stapled-in
progress is invisible to the next opener. About to edit a `status: claimed` body to record what
you just did? STOP and run this skill from the top.
