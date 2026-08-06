---
title: Workflow Orchestration — Scripted Multi-Agent Execution
created: 2026-07-03
type: doctrine
related:
  - plugins/coordinator/docs/wiki/dispatching-parallel-agents.md
  - plugins/coordinator/skills/execute-plan/SKILL.md
---

<!--
Purpose: Coordinator methodology for the Workflow tool — deterministic, compaction-surviving
multi-agent orchestration. WHEN and WHY to escalate from serial/ad-hoc fan-out to a scripted
workflow, and how the script maps onto the existing gate-graph/ledger discipline.
Negative-spec: NOT a JavaScript/API tutorial (the Workflow tool description owns the API surface);
a Workflow is the DEFAULT vehicle for executing a plan (any wave count) — ad-hoc
`Agent` dispatch remains only for genuinely non-plan work (quick fixes, scouts, single
confirmations); NOT a license to weaken concurrent-EM commit doctrine.
Domain vocab: workflow, phase, fan-out, gate, EM-as-serial-orchestrator, compaction-survival,
resumability, deterministic gate, chunking rule, manifest-commit.
-->

# Workflow Orchestration — Scripted Multi-Agent Execution


The **Workflow tool** is a deterministic multi-agent orchestration primitive. The EM writes a small JavaScript script that encodes the *shape* of a multi-phase job — which agents fan out in parallel, which gates are serial, what conditions halt the run — and the harness executes it in the background across many subagents, returning only structured verdicts to the EM.

This wiki is coordinator methodology: **when and why** to reach for a workflow, and how it maps onto the gate-graph and wave-map discipline you already run (`dispatching-parallel-agents.md`, `skills/execute-plan/SKILL.md`). The **API surface — every script hook (`agent`, `parallel`, `pipeline`, `phase`, `log`, schemas, `resumeFromRunId`), the concurrency cap, and the cache-window semantics — is owned by the `Workflow` tool description in the EM's tool surface.** Read that for the *how*; read this for the *when*. Do not invent semantics that diverge from the tool description.

---

## The problem it solves: EM-as-serial-orchestrator

The anti-pattern this names is **EM-as-serial-orchestrator**. When the EM dispatches one wave, waits, verifies, commits, and dispatches the next — all in its own context — it becomes the single point of compaction failure for the whole plan. For any plan of more than one wave this risks degrading: the EM compacts mid-execution and loses the wave map, the gate state, and which chunks already shipped. Recovery is expensive and error-prone (re-dispatching over partial work, conflicting with landed commits).

A workflow moves the orchestration *out* of the compaction-prone context. The wave map lives in a script the harness executes; the EM holds only the final structured result.

> This is the fan-out-default reflex (global CLAUDE.md § Fan-out dispatch extras; `dispatching-parallel-agents.md`) escalated one level: fan-out asks *"can this be N smaller agents?"*; a workflow asks *"and should the orchestration of those N agents outlive my context window?"*

---

## The antipattern: hand-orchestration, and the four false rationalizations

The recurring failure this doctrine exists to stop: **the EM hand-orchestrates executor dispatches (serial `Agent` calls, or `parallel` waves it drives itself) instead of authoring a background Workflow** — burning its own context window holding the wave-map, wave results, and per-chunk commit bookkeeping across compaction boundaries. Four rationalizations talk the EM out of the Workflow in the moment, and **all four are false:**

1. *"I need EM eyes on each wave — a Workflow takes me out of the loop."* **False.** A Workflow returns each phase's structured results to the EM; the EM reads them between phases and decides what happens next. You see everything on the flip-side, exactly as you would hand-orchestrating — you just don't hold the transcripts in your context.
2. *"I control the commits — a Workflow would commit for me."* **False.** Workflow executors author but return their work **without committing** (§ Commit discipline inside workflows); the EM commits each phase serially from the returned manifest. Commit control never leaves the EM.
3. *"A downstream step is EM-inline regardless, so the whole thing might as well stay hand-orchestrated."* **False.** An EM-inline step downstream does not preclude a Workflow for the *dispatched* chunks — scope the Workflow to those chunks and run the EM-inline step after it returns. The presence of one inline step is not license to hand-orchestrate the rest.
4. *"It's small — just a few dispatches, one uncompacted pass, not worth scripting."* **False, for plan execution specifically.** When you are executing a plan via `/execute-plan`, a Workflow is the vehicle regardless of chunk count — the smallest Workflow is a one-`agent()` script, and skipping it to hand-dispatch "just this once" reintroduces the EM-as-serial-orchestrator failure this section names. The gate is whether the work is bounded, enumerated plan execution, not whether it "feels big enough" to script.

What a Workflow actually removes is the one thing that genuinely hurts: the context-window burn of the EM holding the wave-map and bookkeeping in its own head across compaction. Nothing else is surrendered.

**What actually qualifies as a carve-out.** A legitimate carve-out names a *shape a Workflow cannot express* — e.g. a mid-run pause for genuine interactive PM input that gates the very next dispatch, or a tool only the main-loop (EM) can call. None of the four rationalizations above name such a shape; each is answered by scoping or restructuring the Workflow, not by abandoning it. Nor does a content-dependent wave graph qualify — where the shape of the next wave depends on inspecting the previous wave's *content*: a Workflow script is plain JS and computes the next fan-out from the prior phase's returned results (loops/conditionals over `agent()` results), or the EM re-plans from the returned manifest and fires a fresh phase. **The carve-out test is self-graded by the same agent that wants to skip the Workflow** — this is exactly the hazard the `When to EM-Inline` checklist guards against for the self-execute escape hatch (`docs/wiki/agent-dispatch-economics.md`); the explicit non-qualifying enumeration above is this doctrine's equivalent guard.

Workflow doctrine concentrates at `/execute-plan` rather than blanket-covering every dispatch
shape (§ The base Workflow tool's opt-in gate below), and the multi-wave nudge hook is a bounded,
offer-shaped burst nudge, not an enforcement backstop.


---

## The three load-bearing differentiators

A workflow differs from plain `Agent`-tool dispatch in three ways — each is a property with a *why it matters*:

1. **Control flow is code, not EM discipline.** Gates are literal `if` statements executed deterministically (`if (divergences.length) return { halted: 'port-divergence', ... }`) — not the EM *remembering* to check between waves. **Why it matters:** a compacted EM forgets to check a gate; a script cannot. The gate fires whether or not the EM's context survived.

2. **Subagent transcripts never enter the EM context.** Each agent's reasoning stays inside the workflow; the EM receives only a small schema-validated result object. **Why it matters:** this is what makes a workflow *survive EM compaction* — if the EM is summarized mid-run, the workflow keeps executing and re-invokes the EM at completion. The EM never carries N agent transcripts, so N can be large without context pressure.

3. **Resumable.** `resumeFromRunId` replays cached successful phases and re-runs only from an edited or failed phase forward (per the Workflow tool description: same-session only; same script + same args → 100% cache hit). **Why it matters:** a phase that halts on a real fork (a transport probe fails, a divergence is found) is fixed and resumed without re-paying the successful phases — the expensive early fan-out is not redone.

**Fleet-quota discipline (the throttle is your discipline, not the tool's job).** The fleet shares one account/IP rate-limit budget across independent sessions — a rate-limit wipeout is usually *fleet-wide* (N concurrent workflow-heavy sessions, e.g. several `/update-docs` + `/architecture-*` + `/distill` at once), not one workflow's burst. Resume (differentiator 3) already makes any throttle **non-fatal for correctness** — the journaled scan wave returns for free, so a wipeout costs wall-clock and retries, not data. What resume does *not* do is prevent the throttle. Cross-session quota governance has no clean primitive (independent Claude processes can't see each other's budget) and building it is disproportionate to a transient, recoverable failure. The actual control is launch discipline: **stagger concurrent workflow-heavy sessions rather than firing them all at once** — the same reflex as not running `make -j1000`. Rely on resume+retry for integrity, on your own staggering for throughput; do not build fleet governance to compensate for a busy fleet.

<!-- distilled: run 2026-08-06-14h38; source: c4-059 -->
**Shared resume primitive — `/distill` and `/architecture-survey` (2026-07-12).** Both ceremonies were rebuilt off their prior fragile, hand-orchestrated fan-out and onto ONE shared resumable-background-Workflow shape rather than each reinventing: a cheap-scan-journaled wave (mechanical/structural, near-free) runs before the fragile-synth wave (the expensive agentic/analytical work), and `resumeFromRunId` re-runs only the failed synth/analysis agents from that journal on a rate-limit wipeout — the cheap wave's output returns from cache for free. This is the same journaled-scan-then-synth shape named in § Reading a Workflow failure above, applied at the ceremony level: the journal dissolves the old hand-orchestrated fan-out's single point of failure (an EM holding the whole scan+synth wave map in context) by making the cheap wave durable and resumable independent of the EM's own context survival. The two ceremonies differ only in concurrency posture, driven by a differing constraint: `/distill` runs a plain concurrency cap of `min(16, cores-2)` (no account-cooldown pressure observed); `/architecture-survey` runs a LOW cap (~4) plus exponential backoff, because its fan-out previously tripped an **account-level** rate limit that stays hot for minutes regardless of the cap (arrival-rate-triggered, not just concurrency-triggered). Both plans' doctrine rewrites (distill C7, survey C6) reference this note rather than duplicating the primitive.


**Workflow-native migration pattern (survey-rebuild).** The `/architecture-survey` rebuild is
the reference case for migrating a command off pre-Workflow agentic dispatch and onto
background-Workflow + deterministic-extraction tooling owned by a separate compute engine:

- The prior implementation dispatched ad-hoc agentic subprocesses for structural mapping; this
  caused a sustained account rate-limit incident and was the forcing function for the rebuild.
- The rebuild plan was staged: doctrine-side chunks (preamble tier-variant, Phase-0 scale, the
  Workflow rebuild itself, a condense helper) are executable independent of the engine side;
  later chunks are gated on the engine team delivering the deterministic-extraction ops plus an
  agreed strawman I/O contract. This is the general shape for any doctrine-side Workflow rebuild
  that depends on an engine-side capability landing first — split into what you can build now vs.
  what waits on a cross-team contract.
- **Fallback scoping:** the engine-cartography structural-mapping fallback is gated on the
  project's own semantic index being absent — when a richer semantic index exists, the survey
  should prefer it; the engine-cartography path exists specifically for the index-absent case,
  not as a general-purpose replacement.

When staging a Workflow rebuild that depends on a cross-team engine contract, don't block the
doctrine-side chunks on the engine team's delivery — split the plan so doctrine-side chunks
proceed immediately and only the engine-dependent chunks wait on the go-signal.

---

## Reading a Workflow failure — verify disk before re-dispatch

A Workflow that reports a failure has almost always **already persisted the executors' file edits** — the general "files persist before failure" crash-doctrine (coordinator CLAUDE.md § Verifying Executor Output After Crash) applies to the Workflow path too. Two failure shapes recur, and both are more benign than the verdict string reads:

- **StructuredOutput retry-cap exhaustion (2026-07-09).** A schema'd `agent()` that fails to emit conformant JSON five times surfaces as `parallel[N] failed` — but the executor's disk edits landed *before* the final JSON emission failed. The failure is the structured-output emission, not the task. `git status`/`git diff` the executor's write-files before assuming loss or re-dispatching.
- **Session/usage-limit death (2026-07-14).** When a background Workflow hits the account session limit, *every* `agent()` errors with "hit your session limit" and `subagent_tokens=0` / `tool_uses=0` — no partial disk writes at all. This is the most benign failure mode: verify clean (`git status`), then re-run with `resumeFromRunId` once the limit resets — no agent was cached (all errored), so the whole wave re-runs safely. Do NOT hand-finish or re-plan around a limit-death.

The rule under both: **`git status` is the arbiter, not the workflow's verdict string.** Verify what actually landed, then resume — never re-dispatch from scratch over partial work.

---

## The base Workflow tool's opt-in gate — no contradiction to override

The base **Workflow tool description** (the Anthropic tool surface, not coordinator doctrine) gates invocation on explicit user opt-in, verbatim:

> "ONLY call this tool when the user has explicitly opted into multi-agent orchestration. […] the user must request that scale, not have it inferred. […] For any other task — even one that would clearly benefit from parallelism — do NOT call this tool."

**A `/execute-plan` invocation IS that opt-in — satisfied by the skill invocation itself, no override needed.** Workflow doctrine concentrates at `/execute-plan` (§ When to reach for it): when the PM invokes `/execute-plan`, that invocation is the standing, explicit user opt-in the base tool asks for — the base Workflow tool's own description lists *"the user invoked a skill or slash command whose instructions tell you to call Workflow"* as a valid opt-in source, alongside `ultracode` and an explicit request. On this path the base gate and coordinator doctrine were never in tension: the skill invocation satisfies the base tool's own stated condition, so there is nothing to override.

**A background Workflow is a bounded-plan-execution vehicle, not a general-dispatch reflex. Workflows are *safe* pointed at a bounded, enumerated problem (a plan's fixed chunk set); *dangerous* pointed at an open-ended one (systematic debugging, loop-until-dry) whose fan-out has no natural bound. Workflow doctrine concentrates at /execute-plan. Ad-hoc work reverts to base-harness backgrounded agents (self-limiting). The one dispatch-time surface that survives is a retuned burst offer — bounded (once per session, burst-triggered), offer-shaped (leads with what a Workflow gives, blesses the ad-hoc alternative), not an authorization override.**

**The `nudge-multiwave-workflow` hook is that retuned offer, not an enforcement backstop.** Where the 2026-07-09 hardening treated the hook as the "intentional, PM-directed backstop of the workflow-by-default decision" — a directive positioned to contradict and override the base tool's opt-in language — the hook is now a bounded, offer-shaped nudge: it fires once per session on a detected multi-wave burst, names what a Workflow gives (compaction survival, deterministic gates, transcripts out of the EM's context), and blesses the ad-hoc alternative for genuinely non-plan work. It never claims to override the base gate, because outside `/execute-plan` there is no standing opt-in to substitute for — ad-hoc bursts still need the PM's explicit ask or revert to base-harness backgrounded `Agent` dispatch, which is self-limiting on its own.

Do **not** read the retuned offer as license to skip a Workflow when actually executing a plan via `/execute-plan`: that path's opt-in is settled by the skill invocation itself (previous paragraph), independent of whether the hook happens to fire. A hand-dispatched plan execution that skipped `/execute-plan` entirely once forced a forensic concurrent-branch collision reconstruction (a sibling session swept the EM's uncommitted executor edits, a schema regen got clobbered) — the cautionary case for that failure mode; a Workflow authored via `/execute-plan` would have made it moot.

### The burst-offer nudge, concretely


**Threshold and copy.** `COORDINATOR_MULTIWAVE_NUDGE_THRESHOLD` is **4**, not 3 — bumped 2026-07-14 per PM calibration ("approximately four agents in quick succession"). The approved offer copy leads with the alternative, not the violation (design-as-offers): *"You've hand-dispatched N executors in quick succession, and you may want to consider a background Workflow instead … If this is ad-hoc parallel work, backgrounded agents are the right tool — carry on. You're the EM; judge the fit. (Once per session.)"*

**The execute-plan seam discriminator.** Inside `/execute-plan`, the default is **one Workflow for the whole plan**, not one Workflow per wave. Segment into per-wave scripts only on a named structural reason — interface-unpinnability (the next wave's shape depends on inspecting the previous wave's *content*, per § The antipattern's carve-out test) or an explicit named EM branch. *"I want eyes between waves"* is explicitly **not** a valid reason to segment — the whole point of a Workflow is that the EM reads results between phases without needing a fresh script boundary to do it.

**A scope note this doctrine's earlier hardening didn't cover.** The original hardening reasoned about the EM hand-orchestrating dispatches; it never reasoned about a Workflow script's *own* programmatic fan-out (`parallel`/loop constructs) overwhelming rate limits by launching far more concurrent agents than a human-authored wave ever would. That's a distinct risk surface, named here as a forward amendment rather than a rewrite of the original incident account.

**Within-wave width is a checkable line, not a vibe.** A single `parallel([...])` wave with more than 5 write-capable executors chunks into sub-waves of 5. This is a countable rule (count the `parallel` array length), not an appetite judgment — and it is deliberately not a flat cap on total agent count across a run (PM-affirmed): it bounds *concurrency within one barrier*, not the total number of chunks a plan can have.

---

## When to reach for it

**Executing a plan via `/execute-plan`? Reach for a Workflow.** The threshold is not "more than one wave" — it is *any* plan you execute through the skill, including a single-wave, single-`agent()` plan: the `/execute-plan` invocation is the standing opt-in, no separate PM ask, no "is it big enough" gate. Also reach for it for migrations, audits, and exhaustive review sweeps run through a plan — anything one context can't hold.

**Decision rule:** executing a plan via `/execute-plan` ⇒ author a Workflow. The work that stays ad-hoc `Agent` dispatch is genuinely non-plan work (a quick one-file fix, a single confirmation dispatch, a read-only scout) — see § When it's still overkill. The Workflow tool is a standard Claude Code capability present in every session — there is no "is it available" gate to clear.

Worth reaching for even on the small stuff: a single-dispatch job — the canonical code-reviewer call is the everyday example — is still a fine candidate for a tiny one-`agent()` Workflow, not just the big multi-wave fan-outs. The payoff isn't scale, it's that the dispatch and its transcript stay out of your context window, which is one of your most precious resources; a Workflow protects it even when there's only one agent to run.

## When it's still overkill

Match machinery to scale — but "scale" is now *"is this plan execution?"*, not wave count. A Workflow is the wrong tool ONLY for work that is not executing a plan:

- A quick one-file fix you are not routing through `/execute-plan`.
- A single read-only scout or a one-off confirmation `Agent` dispatch.
- Anything with no plan and no chunk decomposition.

**A single-wave *plan* is NOT overkill** — it is a one-`agent()` Workflow. The prior "a single ad-hoc parallel wave is overkill" carve-out is **retired for plan execution**; it survives only for the genuinely non-plan cases above.

---

## The chunking rule: keep each agent task ≤ ~10 minutes

A workflow does not repeal the fan-out sizing discipline — it *carries* it into each phase. Keep every `agent()` task ≤ ~10 minutes. **A >10-min single-agent task is a signal the phase was under-decomposed** — the long task compacts the *agent* and yields degraded results, exactly the failure the fan-out-default reflex exists to prevent. Split it.

The pcore-03 dogfood re-chunk is the canonical illustration:
- **C5 fat-agent → 1 lean foundation + 4 parallel suites.** The original C5 ("author all contract tests") was one oversized agent; it split into a lean `conftest`+fixtures foundation phase, then 4 parallel test-authoring agents (ping / wire / coverage-parity / handoff-parity) each reusing the foundation's harness.
- **C8 → probe-gate then author.** "MCP shim" split into a transport-*probe* phase (a serial gate that halts the run if the transport is infeasible) and a shim-*author* phase that runs only if the probe returns green.
- **C9 → 3 parallel verification lenses** (lifecycle / parity+wire / shim+dogfood+hygiene).

**Coupling exception.** A tightly-coupled shared file is the one case where keeping a ~10-min unit whole beats splitting it. In pcore-03, the `conftest.py` + fixtures were authored by a *single* foundation agent precisely because splitting a shared pytest `conftest` across parallel authors would race the file. Coupling rules out concurrency, not decomposition (`dispatching-parallel-agents.md § Coupling Rules Out Concurrency`).

**Width, not just per-agent duration, is a checkable line.** A single `parallel([...])` wave with more than 5 write-capable executors chunks into sub-waves of 5 (§ The burst-offer nudge, concretely). This is a distinct axis from the ≤10-min-per-agent rule above — a wave can satisfy the duration ceiling on every agent and still be too *wide*.

---

## Multi-plan execution: model the cross-plan DAG as memoized promises

Executing more than one plan as a single Workflow at "max parallel" is not N sequential wave-barriers — model the **full cross-plan DAG as memoized per-node promises** (each node `await`s its deps, then dispatches) and `Promise.all` them. Every chunk fires the instant its true deps clear, with no artificial wave boundaries, so the scheduler fills the concurrency cap optimally.

Two structural rules keep this collision-free without worktrees:

- **One executor per HOT file.** A file touched by multiple chunks gets a *single* executor doing ALL its edits, sequenced after that file's latest dep. This is the coupling-rules-out-concurrency discipline (§ The chunking rule) applied across plans — it structurally prevents concurrent write-collisions on the shared tree.
- **Split a chunk by file-owner when a shared-file edit would force a cycle.** If chunk C1's edit to a shared file is needed by C8, but C9 also owns that file and needs C8, author the load-bearing artifact as a standalone file so the circular edge dissolves.

**Precedent: an overlapping plan sequences after two disjoint ones, not concurrently with them (2026-07-16).**
<!-- distilled: run 2026-07-22-23h55; source: b2-007 -->
Three plans (A, B, C) were candidates for the same DAG. A scout verified B and C's write-scopes
were fully disjoint (B: `coordinator/…` only; C: `coordinator_core/…` only) — that disjointness is
what licensed running B ∥ C fully parallel per the one-executor-per-HOT-file rule above. Plan A
overlapped *both* B (install surfaces) and C (query-records) and was additionally unauthorized and
gapped — two independent reasons it does not join the parallel pair. A was sequenced **after**
B+C landed rather than run concurrently with either. This produced a second-order benefit beyond
avoiding the write collision: landing C first meant A's own dependent task (reconciling against
C's query-records interface) could verify against C's *actual shipped* `records_query.py` rather
than authoring against a guessed interface — sequencing an overlapping plan after its disjoint
peers turns a guess into a verification. The general lesson: when a scout confirms two plans are
write-disjoint, parallelize them; an overlapping third plan sequences after both, and doing so
often lets its downstream chunks verify against real shipped code instead of a prediction.

### Convergence: getting from N plans to one dispatchable shape

Everything above this point assumes the DAG already exists. It doesn't, on arrival — N
independently-authored plans need a convergence pass *before* any of it applies. A nine-plan
campaign over largely-shared surfaces had to derive this pass from scratch; it generalizes.

**The conductor artifact is the output of convergence, and it is not a tenth plan.** When N
plans converge, write a **sequencing layer** — `docs/plans/<date>-<slug>.md` with `type:
conductor` frontmatter and a `governs:` list of the plans or handoffs it sequences — rather than
another plan. Its job is that a picking-up session reads the conductor instead of all N plans
and knows it is overseeing one transformation, not N races; the governed plans remain the
authoritative chunk bodies. **Phase-boundary cadence:** one background Workflow per phase, then
an EM commit, then optionally a `/handoff` — never one session holding the whole campaign. This
keeps a compaction or crash costing one phase, not the campaign, and keeps any single EM
overseeing dozens of agents rather than hundreds.

**Duplicate-mechanism build is the expensive failure mode, and it is not hypothetical.** Two
independently-authored plans can each design and build *the same* mechanism over the same
files — fired in parallel they clobber each other; fired serially the second is wasted work. A
nine-baton campaign hit this directly: two plans each specified the same prompt-injection seam
across the same three files, ~18 references apiece. **The resolution is adjudication into a
single canonical spec that both plans then consume** — a reviewer dispatch is the right tool
(the campaign used the eng-director persona; the verdict was a synthesis, one plan's spec as
base plus named absorptions from the loser, not an arbitrary pick). The seam is then built
**once**, in a foundation phase, and both consumers append data to it. General rule: when two
plans build the same mechanism, unify before dispatch — never let both build it, and never pick
one arbitrarily without reading what the loser specified that the winner missed.

**Shared citations are not shared writes — verify the claim before serializing on it.** A naive
grep for a filename across N plans massively over-reports contention. In the campaign, files
that appeared as claimants of 4-6 plans turned out to have exactly one *writer*; the rest were
citations. Only actual write-targets serialize — serializing on a citation costs parallelism for
nothing that needed protecting.

**A foundation phase is legitimate when built once, sequenced first, and closed by an explicit
live gate — not a file-existence check.** The nine-baton campaign's gate ran one real dispatch
and confirmed the injected block reached a child prompt before its first tool call, and
deliberately included a *negative leg* — an ineligible consumer received nothing and was not
blocked. The negative leg is what catches a gate that widened too far or crashed silently on a
lookup miss. **Delivery is not compliance:** that gate proved the seam's contract *arrived* in a
child prompt; the child then had to distinguish it from its own system-level instructions and
decline to act on it. A gate that only proves arrival has not proven behaviour — if a mechanism
claims to be canonical and non-optional, the gate must observe behaviour under it, not just
presence in the prompt. What still does *not* belong in a foundation phase: an artifact whose
content is an undecided decision. The discriminator is decided-but-unbuilt (foundation-phase
legal) vs. undecided (belongs in a planning session, not execution).

**Partition by surface family first — it is what licenses the wide fan-out.** The structural
insight that made the nine-plan campaign tractable: plans often partition almost perfectly by
the surface family they touch, colliding only on a small shared substrate. Find that partition
before dispatch; it is what licenses a wide parallel fan-out, with the residual collisions
treated as the thing needing explicit ownership rather than serializing everything defensively.
Worktree-per-agent is the wrong mitigation at this scale — hundreds of worktrees is not viable,
and the collisions are structural rather than incidental, so a structural fix (the ownership
table below) is both cheaper and permanent.

**Single-owner assignment table is the concrete artifact for residual collisions.** One row per
contended write-target: file | claimants | owner and ordering rule. This is the applied form of
the one-executor-per-HOT-file rule above (§ Two structural rules) — where two plans must both
touch a file, the row names which lands first and why (a full rewrite lands before a one-line
re-locate; a strip lands before the sync that would otherwise re-paste what was stripped).

---

## Model selection: Sonnet by default, Opus is PM-gated

**Every workflow `agent()` call MUST pass `model: 'sonnet'` explicitly.** The Workflow tool's default — omit `model` and inherit the session model — is a token-burn trap in an Opus session: every un-modeled agent runs on Opus (~4x cost per agent-call). Do NOT rely on the tool's "omitting is almost always correct" guidance — that description is wrong for the fan-out executor path, where the whole point is cheap parallel Sonnet workers, not Opus.

**Opus for a workflow agent is rare and PM-gated.** Before launching any workflow that sets `model: 'opus'` (or an Opus-tier override) on ANY `agent()` call, surface the intent to the PM and get explicit approval. Name which agent(s) you want on Opus and why Sonnet was insufficient. The default fan-out — porters, executors, per-wave commit agents, mechanical verifiers — is Sonnet, full stop.

**Negative-spec:** an un-modeled `agent()` in an Opus session is a defect, not a shortcut. The omission is invisible in the script and only surfaces as burn. The PM directive explicitly overrides the Workflow tool's own "inherit is almost always correct" claim for this path.

**The gap is now closed at the tool boundary.** The PreToolUse hook `hooks/scripts/block-workflow-unmodeled-agent.py` (tripwire `BLOCK-WORKFLOW-UNMODELED-AGENT`) gates every `Workflow` launch in an Opus-tier session: if the inline `script` has any `agent(` call with no `model:` set, the launch is DENIED — offers-not-nags, pre-filling the `model: 'sonnet'` fix rather than just naming the violation. Mixed coverage (some calls modeled, some not) is allowed with an advisory warning, not denied. Escape hatch for the rare PM-approved Opus-`agent()` case: `COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD=1`. → `docs/wiki/coordinator-tripwires.md § BLOCK-WORKFLOW-UNMODELED-AGENT`.

**Two bypass holes in that hook were fixed — worth knowing if you ever touch the hook itself.** Hole 1: a `Workflow` launch by `scriptPath`/`name` (the resume path) skipped validation entirely, because the hook only inspected an inline `script` string — fixed by reading the file at `tool_input.scriptPath` and running the same validation on its contents. Hole 2: the original substring-count of the literal `agent(` token vs. the count of `model:` occurrences was unsafe in the "more `model:` than `agent(`" direction (over-counts pass silently) — fixed with per-call-site model attribution via balanced-paren extraction, so each `agent(` call is checked against *its own* options object, not a global tally. Wiring the hook to an external engine's own validator was **declined at the time** — the fix stayed self-contained pure bash/awk. The stated reason (coordinator must not runtime-depend on an external engine package) is superseded: coordinator-claude has since declared a hard runtime dependency on the coordinator engine (`docs/install/agent-install-manifest.json`, `direct_deps` entry for the engine, `severity: "hard"`) — most state-mutating skills call into it, and only pure-prompt flows are exempt. This hook's own self-containment stands as a local, narrower choice (a lightweight tripwire that shouldn't gain a hard dependency of its own), not as an instance of a blanket no-external-engine principle.

---

## Commit discipline inside workflows

**Workflow agents author but do NOT commit; the EM commits from the returned manifest.** Every executor brief in a workflow carries the instruction verbatim ("Do NOT git commit — EM commits from your returned manifest"). This keeps two doctrines intact:

- The **concurrent-EM scoped-commit doctrine** (global `CLAUDE.md` § Concurrent-EM Git Operations) — commits stay explicit-path, owner-attributed, and EM-driven.
- **No parallel-agent git-index races** — N agents committing concurrently against one working tree is a corruption surface.

The workflow returns a structured manifest of what each agent wrote; the EM commits from it after the run, applying the concurrent-EM scoped-commit discipline (verify staging with `git diff --cached` before, landing with `git show --stat HEAD` after). Do not introduce agent self-commit inside the workflow as a convenience.

**Per-wave commit staging computes the path list from executor reports, never hardcoded paths (2026-07-09).** If a workflow commits per wave (a `commitWave` step) rather than deferring all commits to the EM, the commit path list MUST be the *union of the files each executor REPORTS editing*, with any that `git status` shows clean/absent dropped. A `commitWave` that hardcodes broad paths (a directory, `install.md`) will absorb a concurrent EM's uncommitted work into your commit on a shared `work/*` branch — the same concurrent-EM hazard scoped commits exist to prevent.

---

## Annotated script skeleton

**One line stamps this skeleton for you — no boilerplate to hand-write.** `coordinator-doc-new --type workflow --name <kebab> --description "<line>" --phase "Title::Detail" [--phase ...] --out <path.mjs>` writes a conformant, green-by-construction `Workflow` script — the `meta`/`phases` shape below, pre-filled from your `--phase` args — so you (should!) start from a valid script rather than re-deriving it each time.

The shape below is distilled from a real multi-wave dogfood run. It shows the load-bearing pieces: `meta` with `phases`, a shared brief constant, a serial gate that halts on failure, a `parallel` fan-out, a probe-then-author gate, and `.filter(Boolean)` on parallel results.

```javascript
export const meta = {
  name: 'my-multi-wave-job',
  description: 'One line — shown in the permission dialog',
  phases: [                                  // one entry per phase() call
    { title: 'foundation', detail: 'lean shared substrate (single agent — coupled)' },
    { title: 'fan-out',    detail: 'parallel x4: independent suites off the foundation' },
    { title: 'gate-probe', detail: 'serial gate — halt the run if infeasible' },
  ],
}

// Shared brief: repo, branch, the "do NOT commit" instruction, the ≤10-min ceiling.
const COMMON = 'Repo: /path. Do NOT git commit (EM commits from your returned manifest). ' +
  'No out-of-scope edits. Keep your task under ~10 minutes; if bigger, do the core and report what remains.'

// Phase 1 — coupled foundation: ONE agent (splitting would race the shared file).
phase('foundation')
// chunk: C-foundation
const foundation = await agent(COMMON + '\n\nAuthor the shared harness ...',
  { schema: FOUND_SCHEMA, agentType: 'coordinator:executor', phase: 'foundation', model: 'sonnet' })
if (!foundation || !foundation.smoke_ok)     // <-- deterministic gate, not EM memory
  return { phase_reached: 'foundation', halted: 'foundation-smoke-failed', foundation }

// Phase 2 — fan-out: N independent agents in parallel; filter(Boolean) drops dead agents.
phase('fan-out')
const results = (await parallel(SUITES.map(s => () => {
  // chunk: ${s.id}
  return agent(COMMON + '\n\n' + s.brief + '\nReuse: ' + foundation.harness_api,
    { schema: TEST_SCHEMA, agentType: 'coordinator:executor', phase: 'fan-out', label: s.id, model: 'sonnet' })
}))).filter(Boolean)
if (results.some(r => r.failed > 0))         // <-- gate on the aggregate result
  return { phase_reached: 'fan-out', halted: 'suites-red', foundation, results }

// Phase 3 — probe-then-author gate: the probe halts the run before expensive authoring.
phase('gate-probe')
// chunk: C-gate-probe
const probe = await agent(COMMON + '\n\nProbe ONLY — author no product files ...',
  { schema: PROBE_SCHEMA, agentType: 'coordinator:executor', phase: 'gate-probe', model: 'sonnet' })
if (!probe || !probe.transport_ok)
  return { phase_reached: 'gate-probe', halted: 'transport-fork', foundation, results, probe }

return { done: true, foundation, results, probe }
```

Notes on the shape:
- **Every `agent()` call passes `model: 'sonnet'`** — the Workflow default inherits the session model, so an un-modeled agent in an Opus session runs on Opus (~4x cost). Sonnet is the workflow default; Opus is PM-gated (see § Model selection: Sonnet by default, Opus is PM-gated).
- **Every `agent()` call passes a `schema`** — the result is validated at the tool-call layer, so the model retries on mismatch (per the Workflow tool description) and the EM receives structured data, not prose to parse. **EXCEPTION — a review/verify stage is the one place a schema of findings is WRONG.** A `schema:` return is an inline-return mechanism: correct for an *executor* stage (structured data the EM consumes), but a *review* stage's findings must land on its spawn-provisioned sidecar (`state/subagent-share/<session-id>/<provision_key>.md`) so `review-integrator` can consume them — its intake hard-stops unconditionally on inline findings (`agents/review-integrator.md` § Intake precondition; `review-integration-doctrine.md` § Reviewer self-persists). So for a review/verify phase: dispatch `agentType: 'coordinator:code-reviewer'` (its sidecar is provisioned at spawn — `report_sidecar:`-eligible, no self-scaffold — and it returns a `DONE: <path> | verdict | findings: N` pointer — return THAT pointer string, not a findings array); a bare `agent()` has no such provisioning path and cannot substitute. **Never `agent(reviewPrompt, {schema: FINDINGS_SCHEMA})`** — the natural reach produces exactly the inline artifact the integrator forbids.
- **Halts return a structured object** naming `phase_reached` and `halted:` — the EM reads which gate fired and why, then fixes and resumes via `resumeFromRunId`.
- **`agentType: 'coordinator:executor'`** routes each agent through the coordinator executor (self-contained brief, auto). Other coordinator agent types (`coordinator:code-reviewer`, etc.) compose the same way.
- **Schema-validated ≠ functionally verified — command-shaped ACs need execution-time invocation.** A `schema:` return guarantees the result's *shape* matches, not that the delivered artifact *works*. A past incident is the canonical case: the AC read "a command can scaffold X," the manifest-registration half landed and passed every schema/shape check, but the CLI's dispatch branch was missing — nobody ran the command, so the crash stayed invisible behind a green checkmark for days until a downstream repo hit it. **Any AC phrased as a command/CLI capability ("a command can do X", "type Z scaffolds", "the migrated CLI behaves like the original", "X is invocable") must be verified by literally invoking the delivered command** (assert exit 0 + schema-valid/expected output) inside the phase that claims it — for a self-marking Workflow phase, fold the invocation into that phase's returned, schema-validated result, rather than trusting a registry/manifest/file-touch alone. Registry-driven CLIs (a known-types table plus a dispatch `if/elif` chain) should also carry a standing registration↔dispatch parity test as the regression net — `coordinator/bin/coordinator-doc-new-emitter-parity.test.py` is the shipped exemplar.

**Flight-sidecar handling is auto-provisioned, not hand-injected.** An earlier version of this doctrine required the workflow-script author to manually scaffold and inject each chunk's sidecar path — that gap is closed. On the current `/execute-plan` chunk-executor path the harness auto-provisions the per-chunk sidecar and passes `sidecar_path:` in the dispatch brief — the workflow-script author no longer hand-scaffolds it.

## Workflow-script authoring gotchas — JS parse/runtime traps

A Workflow script is plain JavaScript executed by the harness, so ordinary JS-authoring traps bite at parse or runtime and nothing persists. Three recur:

- **`args` arrives as a JSON *string*, not a parsed array (2026-07-09).** The Workflow tool's `args` global reaches the script as a raw JSON string even when passed as a JSON array in the tool call — `args.filter(...)` / `pipeline(args, ...)` throw "expects an array". Guard at the top: `const X = Array.isArray(args) ? args : JSON.parse(args)`.
- **`${...}` in a brief template literal is JS interpolation, not prose (2026-07-12).** Executor briefs authored as JS template literals evaluate every `${...}` as an interpolation expression. Accidental prose like `${REPO-relative dirs}` throws "Unexpected token" at parse time — nothing persists. Keep `${VAR}` to real interpolations (`${REPO}`, `${COMMON}`) and rewrite any incidental `${` in brief prose. (`$?` alone is fine; `${` is not.)
- **The model-guard substring-counts the `agent(` token inside STRINGS too (2026-07-13).** `block-workflow-unmodeled-agent.py` counts the literal `agent(` substring across the whole script (comments stripped, string literals NOT), and its balanced-paren attribution desyncs on parens inside string literals — so prose like "every agent-call" written with the literal token in a brief or PIN string trips a false "un-modeled agent" block even when the one real call has `model: 'sonnet'`. Keep workflow-script *prose* free of the literal `agent(` token (write "agent-call" / "dispatch"); only the real call carries it, with `model:` inline.

---

## The Workflow Script Is the Wave-Map

The decomposition contract is not a separate document the EM authors and then transcribes into a
workflow — **the Workflow script's own `phase()`/`agent()` calls ARE the wave-map.** There is no
prior artifact to "map onto"; authoring the script *is* authoring the decomposition. The plan's
`## Tasks` spine (or, on the rare hand-orchestrated carve-out, a hand-orchestrated dispatch TSV) gives
the chunk set; the Workflow script is where that chunk set becomes an executable, gate-respecting,
crash-durable wave-map:

| Wave-map concept | Workflow encoding |
| --- | --- |
| A wave in the wave-map | A `phase()` group |
| A chunk (one agent) | One `agent()` call, labelled |
| A **serial gate** (file-overlap / output-consumption / contract-change) | An `await` boundary + an `if (...) return { halted }` |
| A **parallel wave** (no overlap) | A `parallel([...])` barrier |
| An item-by-item pipeline with no barrier between stages | `pipeline(items, stage1, stage2, ...)` |
| The EM committing from executor output | The EM committing from the workflow's returned manifest |

<!-- distilled: run 2026-08-06-14h38; source: c5-010 -->
**The five disciplines that relocated onto the wave-map when the plan-body `## Dispatch Ledger`
markdown table was retired (2026-07-13).** That table was self-perpetuating duplication of the
Workflow script's own wave-map — a second place to keep the same decomposition in sync. Retiring
it moved five load-bearing disciplines onto the script/TSV itself, not into thin air: (1) the
**gate-kind discriminator** (serial vs. parallel, § table above); (2) **disjoint-write-target
expansion** (which files each chunk owns); (3) **agent-count ≥ spine-task-count** (no chunk of
the plan's `## Tasks` spine silently absorbed into another agent's dispatch); (4) **est-min > 15
re-split** (§ The chunking rule's ≤10-min ceiling, checked before dispatch); (5) **one-chunk-per-
dispatch** (the `// chunk:` label convention below is the mechanical enforcement of this one).
Recovery for a dropped ledger is covered by § Crash-recovery below (git-log-by-chunk-id replaces
re-read-after-compaction).

**The required chunk-label convention (and the static-checkability tradeoff it restores).** A
retired plan-body markdown table was grep-parseable — a script could parse `| N | chunk-id |` rows
and a regex could catch one dispatch row silently spanning two chunk-ids. A free-form JavaScript
Workflow script is **not** statically checkable in the same way by default: nothing stops an
`agent()` call from quietly doing the work of two chunks, and nothing external can count "one
`agent()` per chunk-id" without a convention to grep for. This wiki does not present the
script-as-wave-map model as strictly loss-free — moving from a grep-parseable table to a script
trades away some static checkability in exchange for the Workflow model's structural
per-`agent()`-dispatch guarantee (transcripts leave the EM's context, gates are literal code, the
run survives compaction).

To restore the mechanical check, **every `agent()` call in a plan-execution Workflow script MUST
carry a greppable chunk label** — a `// chunk: <id>` comment immediately above the call, or an
equivalent `label:` / `phase:` option value that encodes the chunk-id verbatim. This is what makes
"one `agent()` dispatch per chunk-id" mechanically greppable again, and it is the signal the
`classify-dispatch-shape.py` observer reads on the
Workflow path when checking for an under-decomposed dispatch.

**Named carve-out: single-chunk inline-EM needs no wave-map.** The wave-map requirement (Workflow
script or, on the rare hand-orchestrated path, a hand-orchestrated dispatch TSV) binds **multi-chunk
dispatch**. A single-chunk plan the EM executes itself inline — no dispatch at all — is explicitly
exempted; there is no wave to map when there is no fan-out. This is not a loophole for skipping the
wave-map on a multi-chunk plan by working the chunks one at a time inline — it is a carve-out for
the genuinely single-chunk case only.

**Crash-recovery is a triple surface, not just `resumeFromRunId`.** § Reading a Workflow failure
above covers `git status` as arbiter and `resumeFromRunId` as the resume mechanism; the full
recovery surface has a third leg. In order of how a resuming EM should read them: (1)
**git-log-by-chunk-id** — `git log --oneline --grep '<chunk-id>:'` tells you which chunks already
shipped, because the commit-subject convention (§ Commit discipline: `<chunk-id>: <summary>`) makes
every landed chunk greppable independent of the workflow's own state; (2) **`resumeFromRunId`** —
replays cached successful phases from the workflow engine's own cache, same-session only; (3)
**the Task-list flight recorder** — the EM's own per-conversation task list persists through
compaction and survives even a fully dead workflow run or a new session where `resumeFromRunId`'s
cache window has expired. The three are independent and complementary, not redundant: git-log
survives to a new session and a new workflow run; `resumeFromRunId` is the cheapest but
session-scoped; the task list is the EM's own memory of *why* a chunk was sequenced where it was.

---

## Gotcha — schema-valid is not semantically valid for inventory-shaped batches

<!-- distilled: run 2026-08-06-14h38; source: c7-049 -->
A schema-validated `agent()` result can be **schema-valid but semantically empty** — every field
present and type-correct, yet the record carries no real data. An inventory-batch phase silently
returned a schema-conformant but empty record this way, and the loss went undetected until a
coverage diff caught it: the empty record happened to correspond to the single most load-bearing
family in the corpus, so the run "passed" its schema gate while dropping its most important
output.

This sharpens the same point made in § Annotated script skeleton's schema-validated-≠-functionally-verified note, for the inventory/batch-scan shape specifically: `schema:` proves *shape*, not
*content non-emptiness*. A batch/inventory phase whose job is enumerating or extracting a
corpus needs an explicit **coverage check** (count/diff against an expected baseline, or a
non-empty assertion per expected family) as part of the phase's own gate — not just schema
validation — because an empty-but-valid record is exactly the failure mode schema validation is
structurally blind to.

---

## Dogfood precedent

A dogfood run is the reference case: after the EM manually dispatched the first two waves
serially (and hit compaction risk holding the wave map), the remaining pipeline — contract-test
gate → veneer flips → MCP shim probe/author → parallel closeout — ran as a single background
workflow. The workflow also caught a real bug in its lead phase: a UDS socket path exceeding the
macOS 104-char `sun_path` limit, fixed and verified before any downstream phase ran.

---

## See also

- `dispatching-parallel-agents.md` — the ad-hoc fan-out methodology a workflow escalates *from*; § Executing a Fan-Out Wave is the manual path, this wiki is the scripted-orchestration path.
- `skills/execute-plan/SKILL.md` — Phase 1.5 (Dispatch-Gate Graph) and Phase 1.6 (wave-map authoring); names workflows as a multi-wave execution vehicle.
- The `Workflow` tool description (EM tool surface) — authoritative API + cache-window + resume semantics.
- Global CLAUDE.md § Fan-out dispatch extras — the parent fan-out doctrine.
