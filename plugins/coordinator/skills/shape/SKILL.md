---
name: shape
description: "Converge with the PM on the SHAPE of a problem (the PRD half) before any solutioning. Strategic, not tactical. Exit gate chains into coordinator:plan."
description-budget: 225
version: 1.0.0
---

# Shape

Converge with the PM on **what the problem actually is** before the EM goes solo on **how to solve it**. Plans fuse a PM-owned PRD half (the problem, what "solved" means) with an EM-owned SDD half (architecture, fix-locus, sequencing); the pipeline has rigor for the SDD half and almost none for the PRD half. `/shape` is that missing front-half: a short, collaborative problem-convergence beat whose only exit is a ratified problem-set that chains into `coordinator:plan`.

**`/shape` is a strategic ceremony, not a tactical clarification round.** It operates at the altitude of product intent, scope boundaries, and success criteria — the questions only the PM can resolve. Tactical uncertainties (naming, file structure, which test framework, commit shape, refactor mechanics) are EM remit and do NOT belong in a `/shape` exchange, no matter how genuinely unsure the EM is — resolving them is the EM's job (`global CLAUDE.md § PM Altitude`).

**Announce at start:** "Using `/shape` to converge on the problem before we plan a solution."

<!-- Instance-#1 extraction note (ceremony-calibration § Exception — low-invariant-risk + high-magnitude): this skill was extracted at instance #1 rather than #3 because (a) the failure it prevents — solutioning before problem-agreement, EM confidence coupled with helpfulness — is the same high-magnitude failure that produced the plan-coverage-checker 36/50 incident, (b) the pattern recurred informally for months before codification, and (c) it is an offer-shaped conversational skill with no autonomous writes, so a mis-codified invariant is cheap to correct. -->

## When NOT to invoke

- **Trivial work** (single-file change, obvious scope) → just do it.
- **PM doesn't know *what* to build / needs approaches explored** → `coordinator:brainstorming`. The discriminating test: *if the PM HAS a problem and wants confirmation you understood it (vs. not knowing what to build at all) → `coordinator:shape`, not `coordinator:brainstorming`.*
- **Problem already converged** (a prior `/shape`, an existing approved spec, a known next-step on a live workstream) → straight to `coordinator:plan`.

`/shape` and `coordinator:brainstorming` are siblings, not twins: brainstorming turns vague intent into a *design spec* (a solution artifact in `docs/specs/`); `/shape` converges on the *problem* (a problem-set in `docs/problems/`) and defers solutioning entirely. Both terminate in `coordinator:plan`.

<HARD-GATE>
Once `/shape` has started, do NOT invoke any implementation skill, write any code, scaffold anything, or dispatch any executor until the problem-set is written and PM-ratified. The only exit from `/shape` is a ratified problem-set that transitions to `coordinator:plan`.

This gate is about finishing what you started. If the problem was already converged (prior `/shape`, existing spec, known workstream next-step), skip `/shape` entirely and go straight to `coordinator:plan`. But once `/shape` starts, see it through.
</HARD-GATE>

## Process (lightweight — this is NOT brainstorming's full design dialogue)

1. **Restate the problem(s)** as received, in the PM's vocabulary, falsifiably. Not "I understand" — the actual problem, stated so the PM can catch a misread.
2. **Surface your single biggest uncertainty** per the forced-articulation contract below. This is the load-bearing step — do it honestly or the ceremony is theatre.
3. **PM corrects/confirms.** Iterate until convergence. The goal is a *shared mental model*; the written problem-set is its residue, not its substitute.
4. **If the PM has a proposed solution-shape**, reflect *that* back too and flag where you'd push back — but do NOT design. Solutioning is `coordinator:plan`'s job.
5. **On convergence**, write the problem-set artifact (below) and **chain into `coordinator:plan`** — the only valid exit.

## Forced-articulation contract (defeats confidence-coupled-with-helpfulness)

A yes/no "do I have the shape? ✓" is a **banned response shape** — EM confidence is coupled with helpfulness, so it self-reports green every time and reveals nothing (the same failure mode that made `plan-coverage-checker` no-opt-out). Step 2 must instead produce the thing that *reveals a misunderstanding*:

- **(a) The single least-certain item must be the scope boundary whose wrong guess would cost the most rework.** Phrase it as *"name the boundary that, if guessed wrong, invalidates the most of the plan"* — NOT "name something I'm unsure about." A trivially-chosen item ("I'm slightly unsure whether to put X in a helper or inline") is explicitly non-responsive. <!-- code-reviewer F4: aligned phrasing to match plan/SKILL.md canonical wording (third-person "guessed", "plan" not "work") -->
- **(b) State the probability-weighted consequence.** *"If I'm wrong about X, then Y and Z are rework."* A low-stakes selection self-evidently fails this test — the PM can see at a glance whether the stated consequence is credible.
- **(c) The surfaced uncertainty must be a PM-altitude question** — product intent, scope boundary, or success criteria. Tactical/EM-decided uncertainties (naming, test framework, commit shape, file structure) are **disqualified as off-altitude** — not merely low-stakes — regardless of how unsure you are, per `global CLAUDE.md § PM Altitude`. Resolving them is your job; surfacing them is noise.
- Also flag **any intent you inferred that the PM did not state** — inferred scope, inferred priority, inferred constraint.

This does not make the mechanism un-gameable in absolute terms (no self-report is), but it raises the cost of the dodge above the cost of honest articulation — the right bar for an offer-shaped mechanism, per `eager-agent-calibration.md § offer-shape`.

## The problem-set artifact

**Save to:** `docs/problems/YYYY-MM-DD-<slug>.md` (project directory; create `docs/problems/` if absent). Tiny by design — a bulleted problem list, not a design doc.

```markdown
---
title: <one-line problem title>
date: YYYY-MM-DD
ratified_by: <PM name>
ratified_date: YYYY-MM-DD
status: ratified
kind: problem-set
---

# <Problem title>

> Ratified by PM <name> <date>. Frozen before any solution. This is the external coverage oracle for plans that cite it.

## Problems

- **P1 — <short name>.** <The problem, stated falsifiably. What's wrong / missing / needed and why.>
- **P2 — …**

## Out of scope (architectural reasons)

- **<Thing we're explicitly NOT solving>** — <hard architectural reason, not "later".>
```

**Integrity marker:** `status: ratified` plus the `> Ratified by PM …` blockquote are what make this a real PM oracle rather than EM self-talk. A problem-set without ratification is `status: draft` and does NOT count as an oracle. Plans link it via the `problem_set:` frontmatter key.

## Transition

Once the PM ratifies the problem-set:

**REQUIRED SUB-SKILL:** Invoke `coordinator:plan`. The ratified problem-set is the input and becomes the plan's coverage oracle (`plan-coverage-checker` consumes it). Do NOT invoke any other skill — `coordinator:plan` is the only valid next step.

*Ceremony placement:* `/shape` is the third vertex beside `coordinator:brainstorming` (vague *what*) and straight-to-`coordinator:plan` (converged shape), per `ceremony-calibration.md`. <!-- code-reviewer F2: dropped dangling § anchor (vague-vs-concrete framing section does not exist in ceremony-calibration.md); keeping file reference, dropping dead section cite -->
