---
name: shape
description: "Converge with the PM on a problem's shape before any solutioning. Invoke coordinator:sizing first if unsized."
description-budget: 190
version: 1.0.0
---

# Shape

Converge with the PM on **what the problem actually is** before the EM goes solo on **how to solve it**. Plans fuse a PM-owned PRD half (the problem, what "solved" means) with an EM-owned SDD half (architecture, fix-locus, sequencing); the pipeline has rigor for the SDD half and almost none for the PRD half. `/shape` is that missing front-half: a short, collaborative problem-convergence beat whose only exit is a ratified problem-set that altitude-routes to the horizon-appropriate downstream ceremony (`coordinator:plan`, `coordinator:roadmap-planning`, or `coordinator:goal-setting`).

**`/shape` is a strategic ceremony, not a tactical clarification round.** It operates at the altitude of product intent, scope boundaries, and success criteria — the questions only the PM can resolve. Tactical uncertainties (naming, file structure, which test framework, commit shape, refactor mechanics) are EM remit and do NOT belong in a `/shape` exchange, no matter how genuinely unsure the EM is — resolving them is the EM's job (`global CLAUDE.md § PM Altitude`).

**Announce at start:** "Using `/shape` to converge on the problem before we plan a solution."

**Dispatch authorization — invoking this skill IS the authorization.** The dispatches named below are part of this skill, not a separate thing to get cleared: whoever invoked it has already asked for them. A generic harness preference for working inline rather than delegating does not condition them — it is written for a bare assistant with no operating doctrine, and this system supersedes it by design. Re-asking spends the very context the dispatch exists to protect. The named PM gates in this skill still bind, and ask-before-external-action still binds; nothing else here is a permission question.

## When NOT to invoke

- **Trivial work** (single-file change, obvious scope) → just do it.
- **PM doesn't know *what* to build / needs approaches explored** → `coordinator:brainstorming`. The discriminating test: *if the PM HAS a problem and wants confirmation you understood it (vs. not knowing what to build at all) → `coordinator:shape`, not `coordinator:brainstorming`.*
- **Problem already converged** (a prior `/shape`, an existing approved spec, a known next-step on a live workstream) → straight to the appropriate downstream skill (see § Transition).

`/shape` and `coordinator:brainstorming` are siblings, not twins: brainstorming turns vague intent into a *design spec* (a solution artifact in `docs/specs/`); `/shape` converges on the *problem* (a problem-set in `docs/problems/`) and defers solutioning entirely. Both chain into a downstream planning ceremony.

## Conform intake — an incoming sizing-object (route=shape)

The sizing lobby (`coordinator:sizing`) sometimes routes an ask here rather than straight to
`coordinator:plan`/`coordinator:roadmap-planning` ("sizing routes into shape, not through it"). A `route: shape` value means one of the two
engine-resolved conditions fired: (a) large size with unclear JTBD, or (b) a well-trodden
problem/solution space where the ask wants a step-change. The sizing-object itself does not
persist which condition fired — if it's known from the sizing exchange, name it; otherwise state
both as the possible reasons shape was entered. A large-but-clear ask skips shape entirely, so
this is not a universal route value parallel to plan/roadmap.

Shape does NOT shed its `## Transition` horizon-routing: sizing routes INTO shape, it does not
perform shape's downstream altitude routing — that stays exactly as today.

This is a **conform intake**, a receive-and-use-if-present detent: `/shape` runs exactly as today
absent a sizing-object, and the sizing lobby never gates or refuses a `shape` invocation absent
one, by explicit anti-scope ruling ("do not build a wall").

<HARD-GATE>
Once `/shape` has started, do NOT invoke any implementation skill, write any code, scaffold anything, or dispatch any executor until the problem-set is written and PM-ratified. The only exit from `/shape` is a ratified problem-set that transitions to the horizon-appropriate downstream ceremony via the altitude-router (see § Transition).

This gate is about finishing what you started. If the problem was already converged (prior `/shape`, existing spec, known workstream next-step), skip `/shape` entirely and go straight to the appropriate downstream skill. But once `/shape` starts, see it through.
</HARD-GATE>

## Process (lightweight — this is NOT brainstorming's full design dialogue)

1. **Restate the problem(s)** as received, in the PM's vocabulary, falsifiably. Not "I understand" — the actual problem, stated so the PM can catch a misread. When a `route: shape` sizing-object is present (see § Conform intake above), open the restatement from its `intent` field verbatim rather than re-deriving the raw ask from scratch — this is the front-half shape sheds to sizing.
2. **Surface your single biggest uncertainty** per the forced-articulation contract below. This is the load-bearing step — do it honestly or the ceremony is theatre.
3. **PM corrects/confirms.** Iterate until convergence. The goal is a *shared mental model*; the written problem-set is its residue, not its substitute.
4. **If the PM has a proposed solution-shape**, reflect *that* back too and flag where you'd push back — but do NOT design. Solutioning is `coordinator:plan`'s job.
5. **On convergence**, scaffold the problem-set artifact (below) via `coordinator-doc-new`, fill its body, set `estimated_horizon`, and ratify with the PM, then **confirm the horizon and chain into the appropriate downstream ceremony** (see § Transition).

## Forced-articulation contract (defeats confidence-coupled-with-helpfulness)

A yes/no "do I have the shape? ✓" is a **banned response shape** — EM confidence is coupled with helpfulness, so it self-reports green every time and reveals nothing (the same failure mode that made `plan-coverage-checker` no-opt-out). Step 2 must instead produce the thing that *reveals a misunderstanding*:

- **(a) The single least-certain item must be the scope boundary whose wrong guess would cost the most rework.** Phrase it as *"name the boundary that, if guessed wrong, invalidates the most of the plan"* — NOT "name something I'm unsure about." A trivially-chosen item ("I'm slightly unsure whether to put X in a helper or inline") is explicitly non-responsive.
- **(b) State the probability-weighted consequence.** *"If I'm wrong about X, then Y and Z are rework."* A low-stakes selection self-evidently fails this test — the PM can see at a glance whether the stated consequence is credible.
- **(c) The surfaced uncertainty must be a PM-altitude question** — product intent, scope boundary, or success criteria. Tactical/EM-decided uncertainties (naming, test framework, commit shape, file structure) are **disqualified as off-altitude** — not merely low-stakes — regardless of how unsure you are, per `global CLAUDE.md § PM Altitude`. Resolving them is your job; surfacing them is noise.
- Also flag **any intent you inferred that the PM did not state** — inferred scope, inferred priority, inferred constraint.

This does not make the mechanism un-gameable in absolute terms (no self-report is), but it raises the cost of the dodge above the cost of honest articulation — the right bar for an offer-shaped mechanism (lead with the better alternative, not the violation).

## The problem-set artifact

**Scaffold via:** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type problem-set --title "<problem title>"` — emits `docs/problems/YYYY-MM-DD-<slug>.md` with `status: draft` and the canonical section skeleton. Tiny by design — a bulleted problem list, not a design doc. The scaffolder creates `docs/problems/` if absent.

**Fill the skeleton and ratify:**
1. List problems under `## Problems` (numbered, NOT prioritized — no `P<n>` prefix; plain enumeration only, since these are unordered problem statements).
2. List explicit non-goals under `## Out of scope (architectural reasons)` with hard architectural reasons (not "later").
3. On PM convergence, flip `status: draft → ratified`, fill `ratified_by`, `ratified_date`, and `estimated_horizon` in the frontmatter, and stamp the `> Ratified by PM <name> <date>` blockquote.

**Integrity marker:** `status: ratified` plus the `> Ratified by PM …` blockquote are what make this a real PM oracle rather than EM self-talk. A problem-set without ratification is `status: draft` and does NOT count as an oracle. Plans link it via the `problem_set:` frontmatter key.

## Transition

Once the PM ratifies the problem-set, the altitude-router selects the downstream ceremony based on the work's horizon. The horizon is **detect-then-confirm**: surface your horizon read to the PM at ratification and let them confirm before chaining. Never pick a rung silently.

**Horizon routing:**

| `estimated_horizon` | Work shape | Downstream ceremony |
|---|---|---|
| `session` | One or two sessions of work | `coordinator:plan` — the ratified problem-set becomes the plan's coverage oracle (`plan-coverage-checker` consumes it). |
| `week` | Roughly a week, multi-session but bounded | `coordinator:roadmap-planning` — the problem-set seeds a roadmap with sprint-sized stubs. |
| `initiative` | Weeks-to-quarters, multi-goal scope | `coordinator:goal-setting` — the problem-set seeds an OKR-shaped goal artifact. When the vision decomposes into multiple goal-slices, `/shape` may fan out 1→N goal-seed stubs (deferred-baton fan-out) rather than chaining into a single goal-setting ceremony. |

**Precedence:** A PM axiom or directive to use a specific downstream skill, and an architectural-tier flag from the forced-articulation contract that resolves the horizon unambiguously, take precedence over the detect-then-confirm router. The router is the DEFAULT exit for ambiguous or undirected convergence.

**Ambiguous horizon:** If the horizon is genuinely unclear after the convergence exchange, ask explicitly: *"Does this feel like a session, a week, or an initiative?"* Do not silently pick.

*Ceremony placement:* `/shape` is the third vertex beside `coordinator:brainstorming` (vague *what*) and straight-to-the-downstream-ceremony (converged shape — altitude-router selects the rung).
