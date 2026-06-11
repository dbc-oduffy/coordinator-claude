---
kind: wiki
title: Sub-plan Delegation — EM-held Decomposition vs Spinoff Forks
status: active
created: 2026-05-18
tags: [sub-plan-delegation, planning, decomposition]
related:
  - docs/wiki/writing-plans.md
  - docs/wiki/spinoff-handoffs.md
---

# Sub-plan Delegation

> Pattern for decomposing large planning tasks when the EM wants to hold the problem space rather than fork ownership to an independent workstream.

## Sub-plan vs Spinoff — The Deciding Question

**Sub-plan:** the EM retains the problem. The master plan frames the whole, sub-plans are dispatched pipelines, and the EM merges the outputs. All sub-plans share a single session's integration point.

**Spinoff:** the EM hands off the problem. The forked workstream has `predecessor: none`, its own authoring session, and its own `/pickup` / `/handoff` chain. The original session does not integrate spinoff output — the spinoff author does.

Choose sub-plan delegation when:
- the problem space is too large for one plan but the EM can stay present to integrate
- sub-problems are parallel and their outputs converge at a defined seam
- the decomposition is the insight — losing it to a spinoff means starting cold on integration

Choose a spinoff when:
- the scope balloons such that integration cannot happen in-session
- the sub-problem has diverged into its own domain the EM cannot hold
- PM authorizes a new independent workstream — see `coordinator/CLAUDE.md § Handoff Lineage` and `docs/wiki/spinoff-handoffs.md`

## Master Plan Shape

The master plan is a framing + decomposition document, **not an implementation plan**.

Required sections:

1. **Problem frame.** One paragraph: what we're building and why, with enough context that a sub-plan author can write a grounded spec.
2. **Decomposition.** Numbered list of sub-plans with clear scope boundaries. Each sub-plan must be independent enough to dispatch in parallel OR must declare an explicit dependency (`sub-plan N must land before sub-plan M`).
3. **Integration contract.** What the EM will do with the sub-plan outputs — merge into a single artifact, write a synthesizing plan, dispatch an executor wave, etc. Name the output file each dependent sub-plan consumes.
4. **Cross-links to sub-plans.** Once authored, each sub-plan path appears here.

The master plan does NOT carry implementation detail. That lives in the sub-plans.

## Sub-plan Shape

Each sub-plan is a full plan in the sense of `docs/wiki/writing-plans.md` — it carries all the substrate-verification discipline: claims, `file:line` citations, pre-dispatch verification, executor constraints.

Additional requirements for sub-plans:

- **Back-link to master:** frontmatter `master_plan: docs/plans/<master-plan-slug>.md`
- **Scope boundary declaration:** one sentence naming what this sub-plan does NOT cover (prevents drift into sibling territory)
- **Output contract:** what the sub-plan produces and where the EM should look for it

## Integration — EM as Convergence Point

After each sub-plan's executor pipeline completes:

1. EM reads the sub-plan's output against the integration contract in the master plan.
2. If the output is on-spec, EM merges it into the master deliverable.
3. If the output drifts outside the sub-plan's declared scope boundary, EM corrects scope before merging — do NOT absorb drift silently.
4. When all sub-plans are integrated, EM marks the master plan complete or authors a synthesizing follow-on plan.

EM never delegates integration. The value of sub-plan delegation over spinoffs is precisely that one session holds the full picture.

## Failure Modes

**Sub-plan scope drift.** A sub-plan author expands scope beyond the declared boundary. Caught at integration. Fix: scope correction in the sub-plan before the executor wave ships.

**Accidental spinoff.** A sub-plan grows until the EM can no longer integrate it in-session. At that point the sub-plan has effectively become a spinoff. Recognize the signal and escalate — see § When to Escalate below.

**Master plan as implementation plan.** The master carries too much detail and becomes a duplicate of the sub-plans. The master's job is framing + decomposition, not specifying every file touch.

**Unordered fan-out on dependent sub-plans.** Parallel dispatch of sub-plans that share a seam produces collisions. The integration contract must declare ordering explicitly when sub-plans are not independent.

## When to Escalate Sub-plan → Spinoff

Escalate when any of the following is true:
- The integration step cannot complete in-session (scope balloons mid-wave)
- The EM can no longer hold the problem space for a sub-plan's domain
- A sub-plan's output requires a second full plan-enrich-review cycle before the EM can integrate

Escalation procedure: author a spinoff for the sub-plan that outgrew its bounds (`/spinoff <slug>`), PM-authorize per spinoff doctrine, update the master plan to note the fork. Do not attempt to integrate in-session what the session cannot hold.

## Cross-links

- `docs/wiki/writing-plans.md` — full plan doctrine; sub-plans must satisfy it
- `docs/wiki/spinoff-handoffs.md` — when to fork rather than hold
- `coordinator/CLAUDE.md § Plan-First Workflow` — plan-skill invocation, dispatch defaults
- `coordinator/CLAUDE.md § Handoff Lineage` — spinoff frontmatter and PM-auth gate
