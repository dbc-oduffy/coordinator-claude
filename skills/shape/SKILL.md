---
name: shape
description: "Converge with the PM on a problem's shape. Size first if unsized."
description-budget: 190
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Shape

Converge with the PM on **what the problem actually is** before the EM goes solo on **how to
solve it**. Plans fuse a PM-owned PRD half (the problem, what "solved" means) with an EM-owned
SDD half (architecture, fix-locus, sequencing); `/shape` is the missing rigor for the PRD half: a
short, collaborative beat whose only exit is a ratified problem-set that altitude-routes to the
horizon-appropriate downstream ceremony (`coordinator:plan`, `coordinator:roadmap-planning`, or
`coordinator:goal-setting`).

**Strategic ceremony, not tactical clarification.** Operates at the altitude of product intent,
scope boundaries, and success criteria — questions only the PM can resolve. Tactical
uncertainties (naming, file structure, test framework, commit shape, refactor mechanics) are EM
remit and do NOT belong in a `/shape` exchange (`global CLAUDE.md § PM Altitude`).

**Announce:** "Using `/shape` to converge on the problem before we plan a solution."

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

## When NOT to invoke

- **Trivial work** (single-file change, obvious scope) → just do it.
- **PM doesn't know *what* to build / needs approaches explored** → `coordinator:brainstorming`.
  Discriminator: PM *has* a problem and wants confirmation you understood it → `/shape`.
- **Problem already converged** (a prior `/shape`, an approved spec, a known next-step on a live
  workstream) → straight to the downstream skill (§ Transition).

Brainstorming yields a *design spec* (`docs/specs/`); `/shape` converges on the *problem*
(`docs/problems/`) and defers solutioning.

## Conform intake — an incoming sizing-object (`route: shape`)

`coordinator:sizing` routes here when: (a) large size with unclear JTBD, or (b) a well-trodden
problem/solution space where the ask wants a step-change. Name the firing condition if the sizing
exchange shows it; else state both as possible. A large-but-clear ask skips shape. Shape keeps its
own § Transition routing — sizing routes INTO shape, it does not route downstream. This is a
receive-and-use-if-present detent: `/shape` runs exactly as today with no sizing-object present,
and sizing never gates or refuses a bare `/shape` invocation.

## Routed elsewhere

`/shape` refuses a live plan, dispatch or spec-dispatch sizing-object and names its wave fire.
Live: `status: routed`, nothing shipped (`A-ROUTED-SIZING-IS-NOT-A-LIVE-ASK`). The fire is the
baton's `plan_blitz_hold_cite`, else the existing baton's `Workflow` line (never a second
`emit-wave-fire`), else the engine-ask submission `Workflow({name: "coordinator:engine-ask",
args: {sizing: "<path>"}})`, with `emit-wave-fire --from-sizing` only when the engine refuses it. No problem-set, no PM ask; fire that line and end the turn. `A-ROUTED-SIZING-NEVER-ENTERS-SHAPE`.
A bare `/shape` and a `route: shape` object are unaffected.

<HARD-GATE>
Once `/shape` has started, do NOT invoke any implementation skill, write code, scaffold anything,
or dispatch an executor until the problem-set is written and PM-ratified. The only exit is a
ratified problem-set that transitions via § Transition. If the problem was already converged,
skip `/shape` entirely. Once started, see it through.
</HARD-GATE>

## Process (lightweight — not brainstorming's full design dialogue)

1. **Restate the problem(s)** as received, in the PM's vocabulary, falsifiably, so the PM can
   catch a misread. With a `route: shape` sizing-object, open from its `intent` verbatim.
2. **Surface your single biggest uncertainty** per the contract below — the load-bearing step.
3. **PM corrects/confirms.** Iterate to a shared mental model; the problem-set is its residue,
   not its substitute.
4. **A PM-proposed solution-shape:** reflect it back and flag pushback; do NOT design
   (`coordinator:plan`'s job).
5. **On convergence**, scaffold the problem-set (below), fill it, ratify with the PM, and chain
   (§ Transition).

## Forced-articulation contract

A yes/no "do I have the shape? ✓" is a **banned response shape**: EM confidence self-reports
green every time. Step 2 must instead produce the thing that *reveals a misunderstanding*:

- **(a)** The least-certain item must be the scope boundary whose wrong guess costs the most rework —
  *"name the boundary that, if guessed wrong, invalidates the most of the plan"*.
- **(b)** State the probability-weighted consequence: *"If I'm wrong about X, then Y and Z are rework."* A low-stakes
  selection fails this.
- **(c)** Must be a PM-altitude question (product intent, scope boundary, success criteria);
  tactical uncertainties are disqualified as off-altitude (`global CLAUDE.md § PM Altitude`) — resolve them.
- Also flag any intent you inferred that the PM did not state — scope, priority, constraint.

## The problem-set artifact

**Scaffold via** (POSIX form; PowerShell: Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
`coordinator-doc-new --type problem-set --title "<problem title>"`
— emits `docs/problems/YYYY-MM-DD-<slug>.md`, `status: draft`, canonical skeleton. A bulleted
problem list, not a design doc.

**Fill and ratify:**
1. List problems under `## Problems` (numbered, NOT prioritized — no `P<n>` prefix).
2. List non-goals under `## Out of scope (architectural reasons)` with hard architectural
   reasons, not "later."
3. On PM convergence (the PM's own statement in conversation is the evidence): flip `status: draft → ratified`, fill `ratified_by`, `ratified_date`,
   `estimated_horizon` (scout-set), stamp `> Ratified by PM <name> <date>`.

A `status: draft` problem-set is not an oracle. Plans link it via `problem_set:`.

## Transition

At ratification, dispatch `coordinator:sizing-scout` over the problem-set and read
`estimated_horizon` from the sizing-scout's report; state it in the ratification ask and route by it.
Never pick a rung silently. Work shape is scope, not calendar time (`A-PM-ASK-STATES-SCOPE-NOT-HUMAN-TIME-GUESSES-OR-RULED-CONCERNS`).

| `estimated_horizon` | Work shape | Downstream ceremony |
|---|---|---|
| `session` | One or two sessions | `coordinator:plan` — the problem-set becomes the plan's coverage oracle (`plan-coverage-checker`). |
| `week` | Several plans, one workstream | `coordinator:roadmap-planning` — seeds sprint-sized stubs. |
| `initiative` | Multiple workstreams | `coordinator:goal-setting` — seeds an OKR-shaped goal artifact; may fan out 1→N goal-seed stubs. |

**Precedence:** a PM axiom/directive naming a downstream skill, or a forced-articulation tier flag
that resolves the horizon unambiguously, overrides the router; the router is the default for
ambiguous or undirected convergence.
