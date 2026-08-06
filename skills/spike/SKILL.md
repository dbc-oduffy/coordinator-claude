---
name: spike
description: "Bounded spike — fuse web research with local study to a verdict."
triggers:
  - /spike
  - spike <mechanism>
  - prove this works
  - derisk the mechanism
argument-hint: "<mechanism-or-question>"
---

# /spike — Mechanism-Derisking Investigation

Prove — or disprove — that a specific mechanism is viable before a plan commits to it. **A spike is binary, same shape as `/dogfood`: either the mechanism converges to a viable verdict, or the session switches gears to a not-viable verdict.** There is no third outcome, and there is no open-ended "keep researching" path — that shape belongs to `coordinator:research`.

**One-line niche:** *"prove a mechanism is viable before a plan commits to it."*

Distinct from siblings (see the plan's Problem section for the full contrast table):
- **`coordinator:research`** — web/repo/structured deep research: broad, not binary, does NOT run code on this machine.
- **`coordinator:systematic-debugging`** — backward-looking (why did ONE known thing break).
- **`coordinator:dogfood`** — smoke-driven fix-through on a thing already built.
- **`coordinator:shape`** — problem-shaping (what to build), not mechanism-proving (can we build it this way).

**Announce at start:** "Running `/spike <mechanism>` — bounded derisking investigation. Binary outcome: viable or not-viable."

## Binary Converge/Switch Framing

Modeled directly on `/dogfood`'s binary discipline — this skill does not re-derive the
convergence-signal / switch-gears taxonomy, it reuses it with the verdict relabeled:

- **§2 "Fix-Through" ↔ spike's "Prove-Through."** A spike does not stop at "well, it's uncertain" — it drives to a concrete verdict the same way `/dogfood` drives to a concrete convergence signal. The forbidden middle ground is the spike analog of file-and-defer: an investigation that peters out into "inconclusive, revisit later" without a declared verdict has not spiked, it has stalled.
- **§3 The Convergence Signal.** A spike's convergence signal is the completed two-part evidence (§ Mandatory Two-Part Investigation below) plus a declared binary verdict — not a vibes-check impression from reading some docs.
- **§4 When to Switch Gears.** A spike switches gears (verdict: not-viable) when the empirical probe demonstrates the mechanism does not hold, or when the research half surfaces a structural blocker (licensing, deprecated API, architecture mismatch) that no further probing will resolve. Switch-gears is a legitimate spike outcome, not a spike failure — the whole point of spiking cheaply is to catch this before a plan and its chunks are drafted around a mechanism that doesn't work.

## Mandatory Two-Part Investigation (DEC-1)

**Both halves are required.** A spike missing either half has mis-built the primitive:

1. **External web research** — how do others solve this problem, what do the official API docs say, what are the known pitfalls and gotchas. This is the same kind of lookup `coordinator:research` does, scoped narrowly to the mechanism in question rather than run as an open-ended deep-research pipeline.
2. **Local empirical study** — install the dependency, run the probe, measure. This is the half `coordinator:research` structurally cannot do (it does not run code on this machine). Installing a package and observing whether it imports, timing an operation, exercising an API against the real local environment — these are the spike's load-bearing evidence, not a nice-to-have.

**Anti-scope: a web-only investigation is `/research` wearing a spike costume.** If a spike produces only research findings with no empirical measurement, it has not spiked — dispatch `coordinator:research` instead, or finish the empirical half before declaring a verdict.

## Throwaway-Probe Discipline (DEC-3)

Probe scripts written during the empirical half are **derisking scaffolding, not durable test artifacts.** They are NOT committed to the persistent test suite. Once the probe has produced its measurement and the verdict is recorded, the probe script is discarded — it served its purpose (answering "does this work") and has no ongoing regression-guard value (that's what the plan's own tests will do, once the plan is drafted around a proven mechanism).

**Anti-scope: do NOT commit probe scaffolding to the test suite.** A spike that adds its probe scripts to the persistent suite has confused the throwaway derisking scaffold with a durable test — see the plan's Anti-scope list.

## Durable Output — the Verdict Record

The single durable artifact a spike produces is a **verdict record**, written to
`docs/research/spike-verdicts/YYYY-MM-DD-<mechanism-slug>.md` and validated against
`spike-result.schema.json`. It is no longer a `state/handoffs/` artifact and it carries no
lifecycle fields (no `status`, no `deployment_state`, no `pickup_ready`) — because a verdict
record is **evidence, not a baton**. A handoff is a unit of work waiting to be picked up and
carried forward; a verdict record is a settled finding about whether a mechanism works. Evidence
is read and cited, never picked up, so it does not belong on a surface built for pickup.

The verdict record carries:
- **Research findings** (external web research half)
- **Empirical measurements** (local probe half)
- **Binary verdict** — `viable` or `not-viable`
- **Gated route** (`gated_route`) — the downstream plan/chunk/decision this verdict gates, when
  the spike was reached via the plan-trampoline path (see § Trampoline below), since it is the
  field that carries the deferred plan-authoring intent across the loop-back
- **Discharge target** (`discharged_by`) — see § Steady-State Discharge Discipline immediately
  below; required and non-null whenever `gated_route` is a non-empty string

Probes are throwaway; the verdict record is durable. This partition (throwaway probe vs. durable
verdict) is the artifact `coordinator:plan` consumes and the audit trail a reviewer or future EM
reads.

### Steady-State Discharge Discipline — a Live Routing Intent May Not Leave the Session Unlanded

A spike verdict record may **not** exit its authoring session carrying a live, unlanded routing
intent. If `gated_route` names a downstream plan, chunk, or decision, that intent gets written
onto a real target *before the session ends* — onto the plan the spike gates, onto an existing
baton already carrying the work, or, for a verdict reached via `coordinator:shape`, onto a
PM-facing surface — and `discharged_by` names that target. A record whose `gated_route` is
non-empty but whose `discharged_by` is null or missing does not validate; the schema will not
accept it. There is no such thing as a record that exits its authoring session promising to be
picked up later.

**Why this is the load-bearing correction here, stated plainly:** `state/handoffs/` plus
`pickup_ready` was a bad carrier of routing intent, but it was the *only* carrier that crossed a
session boundary — `coordinator:pickup` and `coordinator:workday-start` enumerate that folder at
session start, and nothing enumerates `docs/research/spike-verdicts/` there. Relocating the
verdict record off `state/handoffs/` without also closing the discharge gap would trade a noisy
failure mode for a silent one: an undischarged routing intent used to sit visibly in the pickup
queue, burning a session's worth of attention before anyone noticed it — annoying, but findable.
Move it to a folder nobody sweeps at session start and the same undischarged intent becomes
invisible instead, which is strictly worse. The reason this can't regress to the old failure mode
is not "the authoring session is expected to discharge its own intent" — that expectation was
checked against the real corpus and does not hold. Of the five verdict records in existence when
this discipline was written, exactly one had been discharged by its authoring session or the one
after it; four had not. The reason it can't regress is structural instead: the schema makes
`discharged_by` required and non-null whenever `gated_route` is a non-empty string, so a record
carrying a live, unlanded routing intent is simply unwritable.

## Invoke Gating — DEC-4 Structural Split, Not Runtime Self-Classification

`coordinator:spike` has exactly one invocation surface reached via two paths, and the gating is **structural**, not a runtime self-classification the skill makes about itself:

- **Research-heavy variant — PM-gated.** Parity with `/research` and `/staff-session`: it can spend web-research tokens, so it follows the same gate — **"PM-gated, never EM-initiated"** and **"NEVER invoke from a subagent."** A bare `/spike <mechanism>` invocation — no structural signal present — is ALWAYS this variant. Full stop.
- **Plan-trampoline path — EM-reachable, no PM round-trip.** When `coordinator:plan` Branch B substrate verification finds a plan resting on an unproven mechanism gate (the eighth verification dimension — see `coordinator/skills/plan/SKILL.md`, wired by C2), it is substrate verification of the plan's own footing, not new scope — gating it behind a PM-ask would defeat the token-saving purpose the trampoline exists for.

**The discriminator is structural, not self-asserted:** the trampoline path is EM-reachable *only* when the Branch B entry path carries an explicit `trampoline: true`-style signal. `/spike` REQUIRES that signal to skip the PM-gate. A bare invocation without the signal is ALWAYS PM-gated — this is **detect-then-fail-loud**, not detect-then-silently-pick. The skill must never decide at invocation time "I'm probably the trampoline variant" from context clues; the absence of the structural signal is dispositive, full stop.

**Anti-scope: do NOT make the plan-trampoline path PM-gated** (that defeats its purpose) **and do NOT let the discriminator be a runtime self-classification** (that is the detect-then-silently-pick footgun the coordinator doctrine names).

## Exit Routing — Binary Verdict Routes the Exit

Exit routing is greppable and mechanical, following the same precedent as `coordinator:shape`'s `<HARD-GATE>` exit-routing block (`coordinator/skills/shape/SKILL.md:27`): **"the only exit from `/shape` is a ratified problem-set that transitions to the horizon-appropriate downstream ceremony via the altitude-router."** The concrete outcome-routes-the-exit mechanics live in `/shape`'s own § Transition (`coordinator/skills/shape/SKILL.md:62-76`), which routes on `estimated_horizon` and states "never pick a rung silently" — the same discipline this skill applies to its binary verdict. A spike's exit is not an EM judgment call once the verdict is in — the verdict IS the router.

| Verdict | Exit route |
|---|---|
| **viable** | → `coordinator:plan` (fresh plan authored around the now-proven mechanism), OR resume the trampolined plan if this spike was reached via the trampoline path (Branch B re-enters with the eighth dimension GREEN — the verdict record at `docs/research/spike-verdicts/` is the evidence; NOT a full seven-dimension checklist re-run) |
| **not-viable** | → `coordinator:shape` / PM for a mechanism reconsider — the mechanism as investigated does not hold, and picking a different mechanism is a problem-shaping question, not a spike question |

### The `plan⇄spike` back-edge

Routing is the load-bearing part of this skill (analogy: `/shape` routes to plan/roadmap/goal by horizon). The **plan⇄spike back-edge** is the wired connection between `coordinator:plan` Branch B (which can trampoline into a spike on an unproven mechanism gate) and this skill's viable-verdict exit (which can resume the trampolined plan). C2 wires the Branch B side; this document is the spike-side half of the same edge, and both sides must cite the literal phrase **plan⇄spike back-edge** so the edge is grep-assertable from either file. The resume path cites the verdict record at its `docs/research/spike-verdicts/` path, not a `state/handoffs/` path — the record itself moved, but the back-edge it carries did not.

## Distinguishing `/spike` From `scope_mode: spike` (DEC-6)

`coordinator:spike` (this skill, a new invocation) and `scope_mode: spike` (an existing plan-header enum value, described below) are **complementary, not colliding — do not conflate them.**

The plan-header enum value `scope_mode: spike` describes a property of a *plan document* whose mode is discovery: "Discovery, is this feasible? — Throwaway code allowed — Findings + recommendation + next step." That is a mode a plan carries once it exists.

`coordinator:spike` is a distinct *invocation* that runs **upstream of** a plan and produces a verdict record that gates whether/how a plan gets drafted at all. Relationship: a `/spike` verdict typically gates a subsequent plan that carries `scope_mode: feature` or `scope_mode: architecture` — because the spike already de-risked the mechanism, the plan doesn't need to be discovery-flavored itself. Occasionally the follow-on plan still carries `scope_mode: spike` if it remains exploratory on a *different* axis than the one the spike already resolved (e.g. the spike de-risked the dependency-install mechanism but the resulting plan is still discovery-flavored on the UX shape). They coexist with distinct meanings at distinct pipeline positions; this skill does NOT supersede the enum value.

## DEC-5/DEC-6 Platform-Vocabulary Collision Note — RECONCILED

Verb-collision check (DEC-5): `spike` collides with no existing coordinator skill/command and no native Claude Code primitive (native command list includes `/plan`, `/review`, `/debug`, `/doctor` — no conflict). We ship the namespaced `coordinator:spike`.

The one real collision the DEC-5 grep initially missed is the `scope_mode: spike` plan-header enum value — see § Distinguishing above. This is **RECONCILED, not a bare "cleared"**: both tokens are named, both meanings are documented side-by-side, and the relationship between them (upstream invocation vs. downstream plan property) is spelled out rather than asserted away. This distinction matters institutionally — see `~/.claude/CLAUDE.md § Fan-out dispatch extras`: an insufficiently thorough clearance check lets a verb collision surface post-ship.

## Destructive-Action Prohibition (write-capable autonomous skill)

`/spike` writes files (probe scripts during the investigation, the verdict record at the end) and is capable of autonomous multi-pass operation. The following are out of scope for this skill, no exceptions: `rm -rf`, `git reset --hard`, `git push --force`, `git rebase`, deleting files outside the spike's own scratch/probe directory, `gh pr merge`, `--no-verify` / `--no-gpg-sign`, hibernate/shutdown/power-off, killing other processes. Do not propose; do not request authorization mid-run for these — they are simply not available actions inside a spike.

## Out of Scope

- **Retrofitting historical spikes into verdict records.** Existing spikes (cockpit's delphi-cockpit crypto gates, the sensor-daemon bake-off, the CLI-auth capture spike) stay as-was; they contribute reference material folded into wiki documentation, not a retroactive migration.
- **Editing the `/research` or `/dogfood` skill bodies.** This skill defines its boundary against them by citation, not by editing their bodies.
- **A generic pipeline-graph engine.** The `shape → spike → plan` edges are wired point-to-point in the affected skills (this file, `plan/SKILL.md` via C2, `pickup/SKILL.md` via C3), not abstracted into a routing framework.
- **A central PM-gated-skills registry file.** The PM-gate for the research-heavy variant is documented here and cross-referenced from discovery surfaces (C5's job) using the same per-skill mechanism other gated skills use — not a new central registry.
- **A new `deployment_state` enum value.** `spike-before-plan` (C3's job, `coordinator:pickup` routing) is a handoff body directive, not a new enum value, absent a reviewer-justified reason.
- **A new primary manifest docType row beyond the verdict-record schema itself.** The verdict record is registered as its own schema (see § Durable Output above) — a terminal, evidence-only artifact, not a handoff-shaped fork.

## Discovery-Surface Integration

Registering `/spike` on the surfaces agents actually touch (`/workstream-start` mention, the PM-gated-skills registration for the research-heavy variant, pipeline-graph cross-refs) is C5's job, not this document's. This skill body is the authoring surface C5 links to.

## Test Surface

**No runtime test for this skill body.** A skill body is prose-doctrine, not executable code — there is no invocation harness in this repo that runs a skill end-to-end as a unit test (the same reason `/dogfood`, `/shape`, and `/plan` carry no runtime test of their own bodies). The frontmatter validates via `yaml.safe_load` the same way sibling skills' frontmatter does (`name`, `description`, `description-budget`, `triggers`, `argument-hint` parse and are present; no unknown top-level keys) — confirmed clean at C1 authoring. The AC3 exit-routing grep-assert (both `viable → coordinator:plan` / `not-viable → coordinator:shape` wording, and the `plan⇄spike` back-edge phrase, greppable from both this file and `plan/SKILL.md`) is C2's test surface, verified cross-file at C2's execution.
