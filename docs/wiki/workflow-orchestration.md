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

The **Workflow tool** is a deterministic multi-agent orchestration primitive. The EM writes a small JavaScript script encoding the *shape* of a multi-phase job — which agents fan out in parallel, which gates are serial, what halts the run — and the harness executes it in the background across many subagents, returning only structured verdicts.

This wiki is coordinator methodology: **when and why** to reach for a workflow, and how it maps onto the gate-graph and wave-map discipline (`dispatching-parallel-agents.md`, `skills/execute-plan/SKILL.md`). The **API surface — every script hook (`agent`, `parallel`, `pipeline`, `phase`, `log`, schemas, `resumeFromRunId`), the concurrency cap, the cache-window semantics — belongs to the `Workflow` tool description.** Read that for the *how*, this for the *when*. Do not invent semantics that diverge from it.

---

## The problem it solves: EM-as-serial-orchestrator

When the EM dispatches one wave, waits, verifies, commits, and dispatches the next — all in its own context — it becomes the single point of compaction failure for the whole plan. The EM compacts mid-execution and loses the wave map, the gate state, and which chunks already shipped. Recovery is expensive and error-prone: re-dispatching over partial work, colliding with landed commits.

A workflow moves orchestration *out* of the compaction-prone context. The wave map lives in a script the harness executes; the EM holds only the final structured result.

> This is the fan-out-default reflex escalated one level: fan-out asks *"can this be N smaller agents?"*; a workflow asks *"and should the orchestration of those N agents outlive my context window?"*

---

## The antipattern: hand-orchestration, and the four false rationalizations

The failure this doctrine exists to stop: **the EM hand-orchestrates executor dispatches — serial `Agent` calls, or `parallel` waves it drives itself — instead of authoring a background Workflow**, burning its own context window holding the wave-map, wave results, and per-chunk commit bookkeeping across compaction boundaries. Four rationalizations talk the EM out of the Workflow in the moment. **All four are false:**

1. *"I need EM eyes on each wave — a Workflow takes me out of the loop."* A Workflow returns each phase's structured results; the EM reads them between phases and decides what happens next. You see everything, you just don't hold the transcripts.
2. *"I control the commits — a Workflow would commit for me."* Workflow executors author but return their work **without committing** (§ Commit discipline inside workflows). The EM commits each phase serially from the returned manifest. Commit control never leaves the EM.
3. *"A downstream step is EM-inline regardless, so the whole thing might as well stay hand-orchestrated."* An EM-inline step downstream does not preclude a Workflow for the *dispatched* chunks — scope the Workflow to those, run the inline step after it returns.
4. *"It's small — a few dispatches, one uncompacted pass, not worth scripting."* For plan execution, the vehicle is a Workflow regardless of chunk count; the smallest Workflow is a one-`agent()` script. The gate is whether the work is bounded, enumerated plan execution — not whether it "feels big enough."

What a Workflow removes is the context-window burn of the EM holding the wave-map and bookkeeping across compaction. Nothing else is surrendered.

**What qualifies as a carve-out.** A legitimate carve-out names a *shape a Workflow cannot express* — a mid-run pause for genuine interactive PM input gating the very next dispatch, or a tool only the main loop can call. None of the four above name such a shape; each is answered by scoping or restructuring the Workflow. Nor does a content-dependent wave graph qualify: a Workflow script is plain JS and computes the next fan-out from the prior phase's returned results, or the EM re-plans from the returned manifest and fires a fresh phase. **The carve-out test is self-graded by the same agent that wants to skip the Workflow** — the hazard the `When to EM-Inline` checklist guards against (`docs/wiki/agent-dispatch-economics.md`); the non-qualifying enumeration above is this doctrine's equivalent guard.

Workflow doctrine concentrates at `/execute-plan` rather than blanket-covering every dispatch shape (§ The base Workflow tool's opt-in gate). The multi-wave nudge hook is a bounded, offer-shaped burst nudge, not an enforcement backstop.

---

## The three load-bearing differentiators

1. **Control flow is code, not EM discipline.** Gates are literal `if` statements executed deterministically (`if (divergences.length) return { halted: 'port-divergence', ... }`), not the EM *remembering* to check between waves. **Why it matters:** a compacted EM forgets a gate; a script cannot.

2. **Subagent transcripts never enter the EM context.** Each agent's reasoning stays inside the workflow; the EM receives a small schema-validated result object. **Why it matters:** this is what makes a workflow survive EM compaction — if the EM is summarized mid-run, the workflow keeps executing and re-invokes it at completion. N can be large without context pressure.

3. **Resumable.** `resumeFromRunId` replays cached successful phases and re-runs only from an edited or failed phase forward (same-session only; same script + same args → 100% cache hit). **Why it matters:** a phase that halts on a real fork is fixed and resumed without re-paying the successful phases.

**Fleet-quota discipline is yours, not the tool's.** The fleet shares one account/IP rate-limit budget across independent sessions — a wipeout is usually *fleet-wide* (several `/update-docs` + `/architecture-*` + `/distill` at once), not one workflow's burst. Resume already makes a throttle **non-fatal for correctness**: the journaled wave returns for free, so a wipeout costs wall-clock and retries, not data. It does not prevent the throttle. Cross-session quota governance has no clean primitive — independent Claude processes cannot see each other's budget — and building it is disproportionate to a transient, recoverable failure. The control is launch discipline: **stagger concurrent workflow-heavy sessions rather than firing them all at once**, the same reflex as not running `make -j1000`.

**The journaled-scan-then-synth shape is the shared resume primitive.** Run a cheap, mechanical, near-free scan wave first and journal it; run the expensive agentic synth wave after. On a rate-limit wipeout `resumeFromRunId` re-runs only the failed synth agents — the cheap wave returns from cache. This makes the cheap wave durable independent of the EM's own context survival. `/distill` and `/architecture-survey` both run this shape and differ only in concurrency posture: `/distill` uses the plain cap of `min(16, cores-2)`; `/architecture-survey` uses a LOW cap (~4) plus exponential backoff, because its fan-out trips an **account-level** rate limit that stays hot for minutes regardless of the cap — arrival-rate-triggered, not concurrency-triggered.

**Staging a Workflow rebuild that depends on a cross-team engine capability:** split the plan so doctrine-side chunks proceed immediately and only the engine-dependent chunks wait on the go-signal. Do not block the doctrine side on the engine team's delivery. Where the rebuild adds a structural-mapping fallback, gate that fallback on the project's own semantic index being absent — when a richer semantic index exists, prefer it.

---

## The Workflow vehicle rewrites the dispatched agent's tool surface

A dispatched agent's `tools:` frontmatter is an enforced allowlist under plain `Agent` dispatch —
but not under Workflow, where the vehicle rewrites the surface in both directions at once.
Reported: a `coordinator:` agent dispatched via `Workflow.agent()` received exactly `Read, Write,
Bash, StructuredOutput` against a definition declaring more. `ToolSearch` and `Task*` were
**removed**; `StructuredOutput` was **added** (the Workflow tool's own doc: a schema'd `agent()`
call forces emission through a `StructuredOutput` tool — retry-cap failure mode below). A reader
who knows only "tools get removed" will mis-model the add side.

That surface figure is an agent's self-report, not an attempted call, and is not to be cited as a
measurement (`SELF-REPORTED-TOOL-SURFACE-IS-NOT-EVIDENCE`). The `StructuredOutput` add is
independently documented; the Bash narrowing below has its own empirical evidence.

**Bash narrowing has a demonstrated correctness cost.** A Workflow-dispatched
`coordinator:executor` was denied `pnpm vitest`/`pnpm run typecheck` by its Bash allowlist, wrote
41 tests it could not run, and honestly reported every AC "PASS (by inspection)." The EM then ran
the suite: 40/41 passed, and the one failure was a real defect inspection couldn't catch. Treat
"PASS (by inspection)" as unverified — the EM runs the tests before trusting the chunk (see
`/execute-plan`'s EM-verify step).

**Plain `Agent` is the contrast, not a second instance.** Three definitions probed empirically
under plain `Agent` each received their own declaration minus platform variance — the allowlist
holds there, and Bash arrives unconfined. So the rewrite is a property of this vehicle, and a
chunk that needs its declared surface intact is a reason to prefer plain dispatch. Carried over
from plain `Agent` and therefore not vehicle-specific: `ToolSearch` and declared MCP tools are not
received on either path (DR-168, rule 3).

---

## Reading a Workflow failure — verify disk before re-dispatch

A Workflow reporting a failure has almost always **already persisted its executors' file edits** — the general "files persist before failure" crash-doctrine applies here too. Two failure shapes recur, both more benign than the verdict string reads:

- **StructuredOutput retry-cap exhaustion.** A schema'd `agent()` that fails to emit conformant JSON five times surfaces as `parallel[N] failed` — but the executor's disk edits landed *before* the final emission failed. The failure is the structured-output emission, not the task. Check the executor's write-files before assuming loss.
- **Session/usage-limit death.** Every `agent()` errors with "hit your session limit" and `subagent_tokens=0` / `tool_uses=0` — no partial disk writes at all. Verify clean, then re-run with `resumeFromRunId` once the limit resets; no agent was cached, so the whole wave re-runs safely. Do NOT hand-finish or re-plan around a limit-death.

**`git status` is the arbiter, not the workflow's verdict string.** Verify what landed, then resume — never re-dispatch from scratch over partial work. Manual reads on a shared tree use `git --no-optional-locks status`; the flag sits between `git` and the subcommand or the invocation hard-fails. `git diff --cached` / `git ls-files -m` need no such flag.

---

## The base Workflow tool's opt-in gate — no contradiction to override

The base **Workflow tool description** (the Anthropic tool surface, not coordinator doctrine) gates invocation on explicit user opt-in:

> "ONLY call this tool when the user has explicitly opted into multi-agent orchestration. […] the user must request that scale, not have it inferred. […] For any other task — even one that would clearly benefit from parallelism — do NOT call this tool."

**A `/execute-plan` invocation IS that opt-in.** The base tool's own description lists *"the user invoked a skill or slash command whose instructions tell you to call Workflow"* as a valid opt-in source, alongside `ultracode` and an explicit request. On this path the base gate and coordinator doctrine are not in tension, and there is nothing to override.

**A background Workflow is a bounded-plan-execution vehicle, not a general-dispatch reflex.** Workflows are *safe* pointed at a bounded, enumerated problem (a plan's fixed chunk set) and *dangerous* pointed at an open-ended one (systematic debugging, loop-until-dry) whose fan-out has no natural bound. Ad-hoc work reverts to base-harness backgrounded agents, which are self-limiting.

**The `nudge-multiwave-workflow` hook is a bounded offer, not an enforcement backstop.** It fires once per session on a detected multi-wave burst, names what a Workflow gives (compaction survival, deterministic gates, transcripts out of the EM's context), and blesses the ad-hoc alternative for genuinely non-plan work. It never overrides the base gate: outside `/execute-plan` there is no standing opt-in to substitute for, so ad-hoc bursts still need the PM's explicit ask.

Do **not** read that offer as license to skip a Workflow when actually executing a plan. That path's opt-in is settled by the skill invocation itself, independent of whether the hook fires. A hand-dispatched plan execution that skipped `/execute-plan` is what forces forensic concurrent-branch collision reconstruction — a sibling session sweeping the EM's uncommitted executor edits, a schema regen clobbered.

### The burst-offer nudge, concretely

**Threshold and copy.** `COORDINATOR_MULTIWAVE_NUDGE_THRESHOLD` is **4**. The offer copy leads with the alternative, not the violation: *"You've hand-dispatched N executors in quick succession, and you may want to consider a background Workflow instead … If this is ad-hoc parallel work, backgrounded agents are the right tool — carry on. You're the EM; judge the fit. (Once per session.)"*

**The execute-plan seam discriminator.** Inside `/execute-plan` the default is **one Workflow for the whole plan**, not one per wave. Segment into per-wave scripts only on a named structural reason: interface-unpinnability (the next wave's shape depends on inspecting the previous wave's *content*), or an explicit named EM branch. *"I want eyes between waves"* is **not** a valid reason — the EM reads results between phases without needing a fresh script boundary.

**Width is a checkable line, not a vibe.** A single `parallel([...])` wave with more than 5 write-capable executors chunks into sub-waves of 5. Count the array length. This bounds *concurrency within one barrier*, not the total number of chunks a plan can have.

**A Workflow script's own programmatic fan-out is its own risk surface.** `parallel`/loop constructs can launch far more concurrent agents than a human-authored wave ever would; the width rule binds the script, not just the EM.

---

## When to reach for it

**Executing a plan via `/execute-plan`? Reach for a Workflow.** The threshold is not "more than one wave" — it is *any* plan executed through the skill, including a single-wave, single-`agent()` plan. No separate PM ask, no "is it big enough" gate. Likewise for migrations, audits, and exhaustive review sweeps run through a plan.

**Decision rule:** executing a plan via `/execute-plan` ⇒ author a Workflow. The Workflow tool is present in every session; there is no availability gate to clear.

Worth reaching for on small work too: a single-dispatch job — the canonical code-reviewer call — is a fine one-`agent()` Workflow. The payoff isn't scale, it's that the dispatch and its transcript stay out of your context window.

## When it's still overkill

A Workflow is the wrong tool ONLY for work that is not executing a plan:

- A quick one-file fix not routed through `/execute-plan`.
- A single read-only scout or one-off confirmation `Agent` dispatch.
- Anything with no plan and no chunk decomposition.

**A single-wave *plan* is not overkill** — it is a one-`agent()` Workflow.

---

## The chunking rule: keep each agent task ≤ ~10 minutes

A workflow does not repeal fan-out sizing discipline — it *carries* it into each phase. **A >10-min single-agent task is a signal the phase was under-decomposed:** the long task compacts the *agent* and yields degraded results. Split it. Three splits that recur:

- **Fat authoring agent → lean foundation + parallel suites.** One "author all the tests" agent becomes a lean `conftest`+fixtures foundation phase, then N parallel authoring agents each reusing the foundation's harness.
- **Risky build → probe-gate then author.** Split into a transport-*probe* phase (a serial gate halting the run if infeasible) and an *author* phase that runs only if the probe returns green.
- **Verification → parallel lenses.** One verification agent becomes N agents on disjoint lenses (lifecycle / parity / hygiene).

**Coupling exception.** A tightly-coupled shared file is the one case where keeping a ~10-min unit whole beats splitting it — splitting a shared pytest `conftest` across parallel authors races the file. Coupling rules out concurrency, not decomposition (`dispatching-parallel-agents.md § Coupling Rules Out Concurrency`).

**Width is a distinct axis from duration.** A wave can satisfy the ≤10-min ceiling on every agent and still be too wide (§ The burst-offer nudge, concretely).

---

## Multi-plan execution: model the cross-plan DAG as memoized promises

Executing more than one plan as a single Workflow at max parallel is not N sequential wave-barriers — model the **full cross-plan DAG as memoized per-node promises** (each node `await`s its deps, then dispatches) and `Promise.all` them. Every chunk fires the instant its true deps clear, with no artificial wave boundaries, so the scheduler fills the concurrency cap optimally.

Two structural rules keep this collision-free without worktrees:

- **One executor per HOT file.** A file touched by multiple chunks gets a *single* executor doing ALL its edits, sequenced after that file's latest dep. This is coupling-rules-out-concurrency applied across plans; it structurally prevents concurrent write-collisions on the shared tree.
- **Split a chunk by file-owner when a shared-file edit would force a cycle.** If C1's edit to a shared file is needed by C8 but C9 also owns that file and needs C8, author the load-bearing artifact as a standalone file so the circular edge dissolves.

**Write-disjoint plans parallelize; an overlapping plan sequences after them.** Have a scout verify write-scopes are actually disjoint — that disjointness is what licenses running them fully parallel. A plan overlapping the others sequences **after** they land, never concurrently. This buys a second-order benefit beyond avoiding the collision: the overlapping plan's dependent chunks verify against real shipped interfaces rather than authoring against a guessed one.

### Convergence: getting from N plans to one dispatchable shape

The DAG does not exist on arrival — N independently-authored plans need a convergence pass before any of the above applies.

**The conductor artifact is the output of convergence, and it is not a tenth plan.** When N plans converge, write a **sequencing layer** — `docs/plans/<date>-<slug>.md` with `type: conductor` frontmatter and a `governs:` list of the plans or handoffs it sequences. A picking-up session reads the conductor instead of all N plans and knows it is overseeing one transformation, not N races; the governed plans remain the authoritative chunk bodies. **Phase-boundary cadence:** one background Workflow per phase, then an EM commit, then optionally a `/handoff` — never one session holding the whole campaign. A compaction or crash then costs one phase, not the campaign.

**Unify a duplicated mechanism before dispatch.** Two independently-authored plans can each design and build *the same* mechanism over the same files — fired in parallel they clobber each other, fired serially the second is wasted work. Adjudicate into a single canonical spec that both plans consume; a reviewer dispatch is the right tool, and the verdict should be a synthesis (one spec as base plus named absorptions from the other), never an arbitrary pick. Build the seam **once**, in a foundation phase; both consumers append to it.

**Shared citations are not shared writes.** A naive grep for a filename across N plans massively over-reports contention — files appearing as claimants of 4-6 plans routinely have exactly one *writer*, the rest citations. Only actual write-targets serialize; serializing on a citation costs parallelism for nothing.

**A foundation phase is legitimate when built once, sequenced first, and closed by an explicit live gate — not a file-existence check.** The gate runs a real dispatch and includes a **negative leg**: an ineligible consumer receives nothing and is not blocked. The negative leg catches a gate that widened too far or crashed silently on a lookup miss. **Delivery is not compliance:** proving a contract *arrived* in a child prompt is not proving the child behaved under it. If a mechanism claims to be canonical and non-optional, the gate must observe behaviour, not just presence. What does not belong in a foundation phase is an artifact whose content is an undecided decision — the discriminator is decided-but-unbuilt (legal) vs. undecided (belongs in planning, not execution).

**Partition by surface family first — it is what licenses the wide fan-out.** Plans often partition almost perfectly by the surface family they touch, colliding only on a small shared substrate. Find that partition before dispatch and treat the residual collisions as the thing needing explicit ownership, rather than serializing everything defensively. Worktree-per-agent is the wrong mitigation at this scale — hundreds of worktrees is not viable, and the collisions are structural rather than incidental.

**A single-owner assignment table is the concrete artifact for residual collisions.** One row per contended write-target: file | claimants | owner and ordering rule. Where two plans must both touch a file, the row names which lands first and why — a full rewrite lands before a one-line re-locate; a strip lands before the sync that would re-paste what was stripped.

---

## Model selection: Sonnet by default, Opus is PM-gated

**Every workflow `agent()` call MUST pass `model: 'sonnet'` explicitly.** The Workflow tool's default — omit `model` and inherit the session model — is a token-burn trap in an Opus session: every un-modeled agent runs on Opus, ~4x cost per agent-call. Do NOT rely on the tool's "omitting is almost always correct" guidance; it is wrong for the fan-out executor path, where the whole point is cheap parallel Sonnet workers.

**Opus for a workflow agent is rare and PM-gated.** Before launching any workflow that sets `model: 'opus'` (or an Opus-tier override) on ANY `agent()` call, surface the intent and get explicit approval, naming which agents and why Sonnet was insufficient. The default fan-out — porters, executors, per-wave commit agents, mechanical verifiers — is Sonnet, full stop.

**Negative-spec:** an un-modeled `agent()` in an Opus session is a defect, not a shortcut. The omission is invisible in the script and surfaces only as burn.

**The tool boundary enforces this.** The PreToolUse hook `hooks/scripts/block-workflow-unmodeled-agent.py` (tripwire `BLOCK-WORKFLOW-UNMODELED-AGENT`) gates every `Workflow` launch in an Opus-tier session: any `agent(` call with no `model:` set DENIES the launch, pre-filling the `model: 'sonnet'` fix rather than just naming the violation. Mixed coverage (some calls modeled, some not) is allowed with an advisory warning. It validates the resume path (`scriptPath`/`name`) by reading the file, not just an inline `script` string, and attributes `model:` per call-site via balanced-paren extraction rather than a global token tally. Escape hatch for the rare PM-approved Opus case: `COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD=1`. → `docs/wiki/coordinator-tripwires.md § BLOCK-WORKFLOW-UNMODELED-AGENT`.

The hook stays self-contained pure bash/awk rather than calling the engine's own validator. That is a local choice — a lightweight tripwire that should not gain a hard dependency of its own — not an instance of a blanket no-external-engine principle; coordinator-claude declares a hard runtime dependency on the engine (`docs/install/agent-install-manifest.json`, `direct_deps`, `severity: "hard"`), and most state-mutating skills call into it.

---

## Commit discipline inside workflows

**Workflow agents author but do NOT commit; the EM commits from the returned manifest.** Every executor brief carries the instruction verbatim ("Do NOT git commit — EM commits from your returned manifest"). This keeps two doctrines intact:

- The **concurrent-EM scoped-commit doctrine** (global `CLAUDE.md` § Concurrent-EM Git Operations) — commits stay explicit-path, owner-attributed, EM-driven.
- **No parallel-agent git-index races** — N agents committing concurrently against one working tree is a corruption surface.

The EM commits from the returned manifest after the run, verifying staging with `git diff --cached` before and `git show --stat HEAD` after. Do not introduce agent self-commit inside the workflow as a convenience.

**Per-wave commit staging computes its path list from executor reports, never hardcoded paths.** If a workflow commits per wave (a `commitWave` step) rather than deferring to the EM, the path list MUST be the *union of files each executor REPORTS editing*, with any that `git --no-optional-locks status` shows clean or absent dropped. A `commitWave` hardcoding broad paths (a directory, `install.md`) absorbs a concurrent EM's uncommitted work into your commit on a shared `work/*` branch — the hazard scoped commits exist to prevent.

---

## Annotated script skeleton

**One line stamps this skeleton — no boilerplate to hand-write.** `coordinator-doc-new --type workflow --name <kebab> --description "<line>" --phase "Title::Detail" [--phase ...] --out <path.mjs>` writes a conformant, green-by-construction `Workflow` script with the `meta`/`phases` shape below pre-filled from your `--phase` args.

The shape below shows the load-bearing pieces: `meta` with `phases`, a shared brief constant, a serial gate that halts on failure, a `parallel` fan-out, a probe-then-author gate, and `.filter(Boolean)` on parallel results.

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

- **Every `agent()` call passes `model: 'sonnet'`** — see § Model selection.
- **Every `agent()` call passes a `schema`** — the result is validated at the tool-call layer, so the model retries on mismatch and the EM receives structured data, not prose to parse. **EXCEPTION — a review/verify stage is the one place a schema of findings is WRONG.** A `schema:` return is an inline-return mechanism: right for an *executor* stage, wrong for a *review* stage, whose findings must land on its sidecar (`state/subagent-share/<session-id>/<provision_key>.md`) so `review-integrator` can consume them — its intake hard-stops unconditionally on inline findings (`agents/review-integrator.md` § Intake precondition; `review-integration-doctrine.md` § Reviewer self-persists). For a review phase, dispatch `agentType: 'coordinator:code-reviewer'` and return the `DONE: <path> | verdict | findings: N` pointer string, not a findings array. **Never `agent(reviewPrompt, {schema: FINDINGS_SCHEMA})`** — the natural reach produces exactly the artifact the integrator forbids.
- **Halts return a structured object** naming `phase_reached` and `halted:` — the EM reads which gate fired, fixes, and resumes via `resumeFromRunId`.
- **`agentType: 'coordinator:executor'`** routes each agent through the coordinator executor. Other coordinator agent types compose the same way.
- **Schema-validated ≠ functionally verified — command-shaped ACs need execution-time invocation.** A `schema:` return guarantees the result's *shape*, not that the artifact *works*: an AC reading "a command can scaffold X" passes every shape check while the CLI's dispatch branch is missing, and the crash stays invisible behind a green checkmark until a downstream repo hits it. **Any AC phrased as a command/CLI capability ("a command can do X", "type Z scaffolds", "X is invocable") must be verified by literally invoking the delivered command** — assert exit 0 plus expected output — inside the phase that claims it, folded into that phase's returned schema-validated result rather than trusting a registry, manifest, or file-touch. Registry-driven CLIs (a known-types table plus a dispatch `if/elif` chain) also carry a standing registration↔dispatch parity test as the regression net; `coordinator/bin/coordinator-doc-new-emitter-parity.test.py` is the shipped exemplar.

### Sidecar provisioning: automatic on `/execute-plan`, manual everywhere else

On the `/execute-plan` chunk-executor path the harness auto-provisions each per-chunk sidecar and passes `sidecar_path:` in the dispatch brief. The script author writes nothing.

**A hand-written Workflow must pre-provision.** Sidecars are provisioned by a hook matched on the `Agent` tool, and a Workflow script's `agent()` call is not an `Agent` tool call, so the hook never fires. Any `report_sidecar:`-eligible type dispatched from a hand-written Workflow arrives with no `sidecar_path:`, and an agent whose contract says the path is spawn-provided is entitled to refuse rather than invent one — a whole wave of refusals at full token cost. Pre-provision each path and inject it into the brief as `sidecar_path:`:

```
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/provision-sidecar" \
    --agent-type <subagent_type> --provision-key <slice-id>
```

It prints one repo-relative path on stdout and fails loud — non-zero, empty stdout, named precondition on stderr — when it cannot. The CLI resolves the template from `report_type_map:` in `coordinator/subagent-sandbox-policy.yaml`, so a pre-provisioned reviewer gets `## Findings`, the same heading the hook-mediated path produces and the one `review-integrator` reads. `review-wave.mjs` survives without this only because it hands each agent an explicit `$FINDINGS_DIR` output path in the prompt; do not generalize from it.


## Workflow-script authoring gotchas — JS parse/runtime traps

A Workflow script is plain JavaScript executed by the harness, so ordinary JS-authoring traps bite at parse or runtime and nothing persists. Three recur:

- **`args` arrives as a JSON *string*, not a parsed array.** The `args` global reaches the script as a raw JSON string even when passed as a JSON array in the tool call — `args.filter(...)` / `pipeline(args, ...)` throw "expects an array". Guard at the top: `const X = Array.isArray(args) ? args : JSON.parse(args)`.
- **`${...}` in a brief template literal is JS interpolation, not prose.** Accidental prose like `${REPO-relative dirs}` throws "Unexpected token" at parse time and nothing persists. Keep `${VAR}` to real interpolations and rewrite any incidental `${` in brief prose. (`$?` alone is fine; `${` is not.)
- **The model-guard counts the `agent(` token inside STRINGS too.** `block-workflow-unmodeled-agent.py` counts the literal `agent(` substring across the whole script with comments stripped but string literals intact, and its balanced-paren attribution desyncs on parens inside string literals — prose using the literal token in a brief trips a false "un-modeled agent" block even when the one real call has `model: 'sonnet'`. Keep script *prose* free of the literal `agent(` token; write "agent-call" or "dispatch".

---

## The Workflow script is the wave-map

The decomposition contract is not a separate document the EM authors and then transcribes — **the script's own `phase()`/`agent()` calls ARE the wave-map.** There is no prior artifact to "map onto"; authoring the script *is* authoring the decomposition. The plan's `## Tasks` spine (or, on the rare hand-orchestrated carve-out, a dispatch TSV) gives the chunk set; the script is where that set becomes an executable, gate-respecting, crash-durable wave-map:

| Wave-map concept | Workflow encoding |
| --- | --- |
| A wave in the wave-map | A `phase()` group |
| A chunk (one agent) | One `agent()` call, labelled |
| A **serial gate** (file-overlap / output-consumption / contract-change) | An `await` boundary + an `if (...) return { halted }` |
| A **parallel wave** (no overlap) | A `parallel([...])` barrier |
| An item-by-item pipeline with no barrier between stages | `pipeline(items, stage1, stage2, ...)` |
| The EM committing from executor output | The EM committing from the workflow's returned manifest |

**Five disciplines live on the wave-map itself**, and there is no second table to keep in sync with it: (1) the **gate-kind discriminator** — serial vs. parallel, per the table above; (2) **disjoint-write-target expansion** — which files each chunk owns; (3) **agent-count ≥ spine-task-count** — no chunk of the plan's `## Tasks` spine silently absorbed into another agent's dispatch; (4) **re-split above the ceiling** — § The chunking rule, checked before dispatch; (5) **one chunk per dispatch**, enforced by the label convention below.

**The chunk-label convention, and the static-checkability tradeoff it restores.** A free-form JavaScript script is not statically checkable the way a grep-parseable table is: nothing stops an `agent()` call from quietly doing the work of two chunks, and nothing external can count "one `agent()` per chunk-id" without a convention to grep for. This is a real trade — some static checkability for the Workflow model's structural per-dispatch guarantee (transcripts leave the EM's context, gates are literal code, the run survives compaction). To restore the check, **every `agent()` call in a plan-execution Workflow script MUST carry a greppable chunk label**: a `// chunk: <id>` comment immediately above the call, or an equivalent `label:` / `phase:` value encoding the chunk-id verbatim. This is the signal `classify-dispatch-shape.py` reads on the Workflow path when checking for an under-decomposed dispatch.

**Named carve-out: single-chunk inline-EM needs no wave-map.** The requirement binds **multi-chunk dispatch**. A single-chunk plan the EM executes itself inline — no dispatch at all — is exempt; there is no wave to map when there is no fan-out. This is not a loophole for working a multi-chunk plan's chunks one at a time inline.

**Crash-recovery is a triple surface, not just `resumeFromRunId`.** In the order a resuming EM should read them: (1) **git-log-by-chunk-id** — `git log --oneline --grep '<chunk-id>:'` tells you which chunks already shipped, because the commit-subject convention `<chunk-id>: <summary>` makes every landed chunk greppable independent of the workflow's own state; (2) **`resumeFromRunId`** — replays cached successful phases from the engine's cache, same-session only; (3) **the Task-list flight recorder** — the EM's own per-conversation task list, which persists through compaction and survives a fully dead run or a new session where the resume cache expired. The three are independent and complementary: git-log survives into a new session and a new run; `resumeFromRunId` is cheapest but session-scoped; the task list is the EM's memory of *why* a chunk was sequenced where it was.

---

## Gotcha — schema-valid is not semantically valid for inventory-shaped batches

A schema-validated `agent()` result can be **schema-valid but semantically empty**: every field present and type-correct, the record carrying no real data. An inventory-batch phase returns a conformant empty record, the run "passes" its schema gate, and the loss surfaces only when a coverage diff catches it — by which point the dropped record may well have been the most load-bearing family in the corpus.

`schema:` proves *shape*, not *content non-emptiness*. A batch or inventory phase whose job is enumerating or extracting a corpus needs an explicit **coverage check** as part of its own gate — a count/diff against an expected baseline, or a non-empty assertion per expected family — because an empty-but-valid record is precisely the failure schema validation is structurally blind to.

---

## See also

- `dispatching-parallel-agents.md` — the ad-hoc fan-out methodology a workflow escalates *from*; § Executing a Fan-Out Wave is the manual path, this wiki the scripted one.
- `skills/execute-plan/SKILL.md` — Phase 1.5 (Dispatch-Gate Graph) and Phase 1.6 (wave-map authoring).
- The `Workflow` tool description (EM tool surface) — authoritative API, cache-window, and resume semantics.
- Global CLAUDE.md § Fan-out dispatch extras — the parent fan-out doctrine.
