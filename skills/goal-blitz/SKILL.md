---
name: goal-blitz
description: "PM-GATED. The VP-Product Reviewer (VP Product) sets, critiques and ratifies OKRs for every goal-seed or goal-setting sizing at once, in one background wave. Or named seeds."
description-budget: 320
version: 1.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "Workflow", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[<seed-id> ...] [--interaction-mode hands-on|pm|ceo]"
---

# Goal-blitz — a repo's worth of OKRs, one ratification

Batches `coordinator:goal-setting`: the VP-Product Reviewer (`coordinator:vp-product`, Opus, effort high) sets each OKR
from the seed's context, a second the VP-Product Reviewer pass critiques it, the VP-Product Reviewer integrates, a blitz-em checks
readiness, and the VP-Product Reviewer ratifies the whole set once at the end. A seed's own objective is input the VP-Product Reviewer may refine. Nothing reaches `state/goals/` before
that ratification. The wave fires from the top-level EM
only (`A-SKILL-PHASE-NAMES-ITS-ACTOR`).

---

## Two modes

**Sweep** (default, no args): every goal-seed baton (`kind: goal-seed`) at `deployment_state: awaiting_gate`
and every `route: goal-setting` sizing at `status: sized` or `routed`; landing stamps a consumed
sizing `routed` with its `goal_id`. **Targeted** (`<seed-id> ...`): only the ids you pass; check
`unmatched_targets` — a quietly dropped target is worse than a refusal.

**Not for:** one goal → `coordinator:goal-setting`; still deciding what to build →
`coordinator:shape`; ratified goals ready for roadmaps → `coordinator:roadmap-planning`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

**Host shapes.** Calls below are Shape W; on POSIX: `coordinator-invoke <op> '<json>'` (Shape B).

---

## The flow

**This runs at Sonnet**; Opus-tier judgment happens INSIDE the workflow. Args and result shapes:
`${CLAUDE_PLUGIN_ROOT}/skills/goal-blitz/goal-blitz-contract.json`.

### 0. Preflight

Resolve the launcher per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. Unresolved —
**stop and report**; never fabricate a fire or result. Scaffold `state/goal-blitz/<run-id>/`
(`<run-id>`: this run's UTC start, `YYYYMMDDTHHMMSSZ`).

### 1. Emit the fire — never hand-write the args

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/goal-blitz/emit-goal-fire.py" \
        --repo-root <abs> --trail-dir <abs trail> --provision-sidecar-cli <abs> \
        --interaction-mode <mode> [--targets <seed-id> ...]

It freezes `<trail>/candidates.json`, binds the args via `workflow.bind_args` into
`<trail>/goal-blitz.fire.mjs`, and prints one `Workflow({ scriptPath })` line.
`--interaction-mode` is recorded as-is and never changes the ratifier. Pass `--no-plugin-agents`
where `coordinator:*` types do not resolve. Empty candidate set: report and stop.

**Never hand-type an args object** (`A-HAND-TYPED-WAVE-ARG-IS-AN-UNARCHIVED-FIRE`). An emitted
fire is a SNAPSHOT: RE-EMIT after any workflow fix, never re-fire as found. Resolve
`${CLAUDE_PLUGIN_ROOT}`; never pass a repo-relative path to a workflow.

### 2. Fire and wait

Fire the printed line; do not read the trail mid-wave. Keep the task output file the completion
notification names — it is the lander's input.

### 3. Ratify — once, at the end

The workflow ratifies nothing; it returns ready drafts in `awaitingRatification`. The ratifier is
**the VP-Product Reviewer** (`coordinator:vp-product`) for every `interactionMode`; the result's `approver` reports `vp-product`. No PM or APM path ships.

Dispatch the VP-Product Reviewer **once**, at its own pinned effort (an override is refused), over the whole set. Give
it each ready draft's path (`<trail>/<seed-id>.goal-draft.yaml`) and critique; ask per draft for
ratified or declined in the VP-Product Reviewer's own words. Write each answer **verbatim** into
`<trail>/ratification.json`, shaped `{seed_id: {verdict, ratifier: "vp-product", utterance}}`.
Never infer, backfill or paraphrase one. `pulled` and `rework` drafts are reported with their
reasons, not asked about.

### 4. Land

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/goal-blitz/land-goals.py" \
        --repo-root <abs> --trail-dir <abs trail> <workflow-result.json>

It lands only drafts with a recorded the VP-Product Reviewer ratification, through goal-setting's own CLIs, then makes
one scoped commit of the files it wrote (`--no-commit` lists them instead), and refuses a ready
draft with no ratification record. A CLI failure mid-landing rolls back every path the run wrote:
fix the cause and re-run. **Read its exit code and stderr; never route around a refusal.** Then
commit the trail's record files (`candidates.json`, `ratification.json`, drafts, critiques) by
pathspec.

### 5. Chain — by mode

**pm or ceo: chain, never ask.** The PM's ask to execute is the chain ack: invoke
`coordinator:plan-blitz` over the landed roadmap-seed batons, then execute, reporting each landing
in one line. (`roadmap-blitz` takes only a sizing with `xl_exit: roadmap`, which a seed is not.)

**hands-on: offer, and wait** — _"{N} goal(s) landed with {M} roadmap-seed stub(s). Want me to
chain into `/roadmap-planning` now, or review the stubs first?"_ Stubs stay `awaiting_gate` until
the PM answers.

---

## Rules

**Review fires unconditionally; the VP-Product Reviewer ratifies once, at the end** (`A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ`).
Never write `state/goals/` by hand or before ratification — `land-goals.py` is the only writer. A
`rework` draft routes, it does not halt.

**Anti-scope:** does not edit `goal-setting`, ratify on the VP-Product Reviewer's behalf, author roadmaps, invoke
`/roadmap-planning`, or change effort pins.
