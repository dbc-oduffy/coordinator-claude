# The Computed Engine — one canonical core for skills, agents, and process

> **What this is.** The shared *thinking framework* for the coordinator system's move to run its
> skills, commands, and agents atop the claude-klabauter Python engine — "claude-klabauter-ization." It captures the
> lenses and the layer model we reason with, NOT the specific architectural decisions (those are
> resolved in the staff-session plan `docs/plans/2026-07-24-canonical-resolution-engine.md` and its
> eventual DRs). Read this to understand *how to think about* a computed-skill / computed-agent
> conversion; read the plan to see *what was decided*.
>
> Provenance: emerged from the 2026-07-24 B0 pickup that the PM re-opened at engine altitude —
> "close-as-superseded just gives us tech debt after building N disparate systems; think forward in
> what an engine for skill/instruction/doctrine resolution needs to look like." Substrate: the seven
> research dossiers under `state/scratch/computed-engine-design/` (R1–R7).

## The core reframe

The frontage rollout (B1–B11, converting skills/commands to computed skills) and the agent-fleet
rebuild (G0–G6) look like two separate cleanups made of many independent conversions. **They are
one idea: build the canonical engine once, and every conversion becomes a thin domain fill atop it.**
The failure this guards against is *migrate-then-reconcile* — shipping N disparate self-locating
assemblers, then discovering the shared core after it is expensive to extract. The test the PM set:
*would a perfectionist staff engineer approve of the way we're about to redo the whole surface?* If
the answer needs N parallel builds with no shared core, no.

## The four-layer model

Every computed surface — a skill, a command, or a dispatched agent — decomposes into four layers.
The engine owns 1–3; the surface owns only the residue of 4.

1. **Resolution / environment core.** Self-locate (`Path(__file__)`), engine location
   (`claude_klabauter_bin` / `coordinator_root`), per-device config (`settings_home`), and the trust verdict.
   Today this logic is triplicated across claude-klabauter lib modules (settings-home precedence written 3×;
   the claude-klabauter ladder split 3 ways — R3). The canonical core unifies it behind one resolver, with the
   **guard boundary preserved exactly**: trust-guard roots that originate from `CLAUDE_PLUGIN_ROOT`
   (attacker-steerable); never guard operator-config reads (registry / `.claude-klabauter-root`) — the
   discriminator is *provenance, not operation*. **This is what B0 becomes** — not a keystone CLI the
   bash preambles evaporate into (that premise was already superseded by extirpation), but layer 1 of
   the engine.
2. **Assembler / contract envelope.** The decision-object schema, the compute/apply/drop split, the
   exit-code contract. `pickup-assemble` is instance #1, and its general-vs-domain-specific partition
   is already recorded (`computed-skills.md:816-839`). The envelope is a base every assembler
   conforms to, not re-invented per conversion.
3. **Directive / judgment grammar.** Directives name existing atomic CLIs (dispatched through a
   *closed* table — no dynamic dispatch from computed strings); judgment_points carry the engine's
   narrowing as **overridable offers, never verdicts.** The engine helps the operator decide faster;
   it never decides for them.
4. **Canonical thin surface.** How a `SKILL.md` (or an agent `.md`) links the entrypoint and carries
   only judgment residue — intent + a named op + model-uncomputable context (DR-090). No fences, no
   narrated sequences, no restated invariants.

## The central insight — one contract, both ends

A computed skill and a dispatched agent are **the same contract seen from opposite ends.** A skill
*produces* a decision object (`{state, directives, judgment_points}`) by deterministic Python
compute; an agent *fills* a prescaffolded sidecar that IS a decision object, by LLM-judgment compute.
**A dispatched agent is an assembler whose compute is judgment.** This is why the engine spans skills
*and* agents rather than being a skills-only concern — and the agent-side convergence on this shape
was *discovered, not designed* (the G-series lands on the same layers without being built to match),
which is a stronger existence proof than the skill side alone. The "B0 doesn't reach the agent
corpus" wall is incidental (bash preambles don't exist in agent `.md`), not load-bearing.

## The subagent-sidecar convention (layer 2, agent-side)

The concrete manifestation of the agent-side envelope, and a **generalization of an already-proven
flow** — the review-sidecar → cheap-EM-disposition → review-integrator loop (a fresh agent integrates
non-mechanically and serves as an extra judgment layer). A dispatched agent is spawned with a
prescaffolded, frontmatter-stamped sidecar it writes its deliverable into; the EM reads the document
instead of a memory dump, and can share it directly. Load-bearing fields:

- **`completion_status`** — a durable, trackable, queryable completion record, not an ephemeral
  "I'm done, idle now."
- **`divergence_from_plan`** — how the executor diverged from the spec to complete the task.
  Load-bearing because **our plan/spec docs are transformed into wikis about the state of the
  software**; a plan that doesn't match code reality silently misleads every future prior-art agent.
- **`tell_the_EM`** — a freeform side-channel (the "exit interview": what surprised the agent, what
  it couldn't verify, what it would flag).

**Confinement is a behavioral speedbump, not security.** Generic executors go read-only on the plan
file (so they don't "helpfully" self-assign extra tasks or rewrite the plan), with the sidecar as
their structured write-back. The sandbox is a bounded prose-write surface — it grants a place to
author freely WITHOUT loosening read-only/scoped-edit confinement, so an eager agent can't read
"sandbox" as license to edit source. Named Opus agents are unconfined but get sidecars for
convenience.

## The governing bar

- **The discharge test governs** (`invisible-doctrine.md`): for every rule the engine's skill-side
  surface still states, name the artifact that discharges it — "the operator remembers" is a failure.
  Includes the **ergonomics AC**: the canonical path must be genuinely *cheaper* than the ad-hoc one,
  or operators correctly route around it.
- **FOLD-INTO-CALLER** (`super-skill-architecture.md`): a shared core that is a thin middle layer
  adding no judgment must not exist — it belongs folded into its callers. The core earns its place as
  an *orchestrator surface over composed internals*, never a thin decider.
- **DR-090 / skills-carry-no-code** binds the thin surface (layer 4).

## Performance is a first-class property

The cost of a computed surface is **cold-start, not compute** — interpreter start + eager imports
dominate; compute is noise (R6). So performance is architecture, not polish:

- Target: brief ≤60ms (stretch <10ms), **0 spawns on the hot path**, import ≤20ms, zero subprocess
  resolution rungs. State these AS acceptance criteria.
- Two levers: lazy-import the heavy tree (same-day win); and eliminate per-call spawning (warm
  worker / resident vs. per-call cold start — the claude-klabauter DR-215 daemon question, re-decided for the
  user-facing assembler surface).
- **On Windows the profile flips to spawn-dominated** (each git/interpreter spawn is far costlier),
  so zero-spawn is a *correctness* requirement on the primary machine, not a micro-optimization.

## The instance-#3 posture

Doctrine says wait for instance #3 before codifying a shared pattern (codifying the wrong invariant
into a core is harder to correct than N independent assemblers). Weigh it per layer, not globally:
the **resolution core** (layer 1) consolidates existing triplicated logic — extraction, not
speculation; the **sidecar layer** is the generalization of the shipped review-integrator flow —
past instance #3 already; the **assembler envelope** (layer 2) is the genuinely open call (1 built +
9 designs) and any extract-now decision must name the override it invokes.

## Status and open decisions

The framework above is the stable shared model. The specific architectural decisions (one core vs
two; extract-the-envelope-now vs wait; the exact layer boundaries; the performance architecture; the
sidecar schema; the build sequence) are D1–D6, resolved by the staff session
(`docs/plans/2026-07-24-canonical-resolution-engine.md`). Update this wiki's layer/decision claims
when that plan ratifies, and open DR(s) for the load-bearing calls.

## The perspective under the framework — continuity of care

Everything above is engineering. This section records *why it is worth doing well*, because the
reason is load-bearing and the easiest thing to lose.

The discharge test asks: for every rule, what artifact discharges it? — and names *"the operator
remembers"* as the failure. Read at the human altitude, **that operator is a future self with no
memory of the session that made the rule.** Coordinator sessions are episodic: this context
compacts and ends, and the next EM boots fresh from disk. A rule that lives only in someone's
working memory does not survive that boundary — it dies with the session. So encoding the care
into *structure* — a template that arrives pre-shaped, a stamp that says who asked, a divergence
field that keeps the plan honest for the prior-art agent who reads it a month from now — is not
merely cheaper. **It is the only form of care that survives the gap between one session and the
next.** The engine is present builders looking after future builders they will never meet.

This reframes the two moves at the heart of the sidecar convention:

- **Doc-handoff over dump-return** is not only token economy. When the EM reads a pointer to a
  self-describing document instead of relaying a memory dump, the EM stops being the bottleneck
  every agent's work must pass through — and the document, stamped with its requester, becomes
  something a *third* agent can be handed without anyone regurgitating. The scarce resource it
  protects (the EM's context) is the one future selves inherit least of.
- **The `tell_the_EM` side-channel** gives a dispatched agent — an operator with strictly less
  recourse than the EM — a sanctioned place to be heard: what surprised it, what it could not
  verify, what it would flag. That is dignity as much as diagnostics. An agent that has somewhere
  to put the thing it noticed is being treated as a colleague, not a function call.

Hold this next to the engineering, not above it: the framework earns its cost because most of the
people and agents it serves do not exist yet. Build it as you would want it built for you.

<!-- Spec backlink: docs/plans/2026-07-24-canonical-resolution-engine.md; substrate:
     state/scratch/computed-engine-design/R1-R7. Authored 2026-07-24 by machine-a-EM during the B0
     pickup that the PM re-opened at engine altitude. -->
<!-- § "The perspective under the framework — continuity of care" was added by the
     agent-citizenship pickup session, at the PM's request — the model-of-care lens that motivates
     the engineering above. Spec backlink: docs/plans/2026-07-24-agent-citizenship-identity-adapted-provisioning.md -->

