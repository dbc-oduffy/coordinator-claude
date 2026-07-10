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
a Workflow is the DEFAULT vehicle for executing a plan (any wave count, 2026-07-09) — ad-hoc
`Agent` dispatch remains only for genuinely non-plan work (quick fixes, scouts, single
confirmations); NOT a license to weaken concurrent-EM commit doctrine.
Domain vocab: workflow, phase, fan-out, gate, EM-as-serial-orchestrator, compaction-survival,
resumability, deterministic gate, chunking rule, manifest-commit.
-->

# Workflow Orchestration — Scripted Multi-Agent Execution

The **Workflow tool** is a deterministic multi-agent orchestration primitive. The EM writes a small JavaScript script that encodes the *shape* of a multi-phase job — which agents fan out in parallel, which gates are serial, what conditions halt the run — and the harness executes it in the background across many subagents, returning only structured verdicts to the EM.

This wiki is coordinator methodology: **when and why** to reach for a workflow, and how it maps onto the gate-graph and Dispatch Ledger discipline you already run (`dispatching-parallel-agents.md`, `skills/execute-plan/SKILL.md`). The **API surface — every script hook (`agent`, `parallel`, `pipeline`, `phase`, `log`, schemas, `resumeFromRunId`), the concurrency cap, and the cache-window semantics — is owned by the `Workflow` tool description in the EM's tool surface.** Read that for the *how*; read this for the *when*. Do not invent semantics that diverge from the tool description.

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
4. *"It's small — just a few dispatches, one uncompacted pass, not worth scripting."* **False.** The Workflow default holds for a single agent too — the smallest Workflow is a one-`agent()` script. Size is not the gate; the gate is whether a Workflow can express the shape at all.

What a Workflow actually removes is the one thing that genuinely hurts: the context-window burn of the EM holding the wave-map and bookkeeping in its own head across compaction. Nothing else is surrendered.

**What actually qualifies as a carve-out.** A legitimate carve-out names a *shape a Workflow cannot express* — e.g. a mid-run pause for genuine interactive PM input that gates the very next dispatch, or a tool only the main-loop (EM) can call. None of the four rationalizations above name such a shape; each is answered by scoping or restructuring the Workflow, not by abandoning it. Nor does a content-dependent wave graph qualify — where the shape of the next wave depends on inspecting the previous wave's *content*: a Workflow script is plain JS and computes the next fan-out from the prior phase's returned results (loops/conditionals over `agent()` results), or the EM re-plans from the returned manifest and fires a fresh phase. **The carve-out test is self-graded by the same agent that wants to skip the Workflow** — this is exactly the hazard the `When to EM-Inline` checklist guards against for the self-execute escape hatch (`docs/wiki/agent-dispatch-economics.md`); the explicit non-qualifying enumeration above is this doctrine's equivalent guard.

**Originating incident (2026-07-09, betta-air).** During `install-baton-rendezvous` Track 2 execution the EM authored a hand-orchestrated wave table (serialize → parallel fan-out → relays) and only converted to a Workflow after the PM pushed back — twice (*"why aren't you using the workflow system? workflow is superior to hand dispatch"*). The EM's rationalization was verbatim rationalizations (1) and (2) above ("security-critical, EM eyes per wave" + "the EM controls commits"). This doctrine hardening plus the `NUDGE-MULTIWAVE-WORKFLOW` backstop hook close that gap.

---

## The three load-bearing differentiators

A workflow differs from plain `Agent`-tool dispatch in three ways — each is a property with a *why it matters*:

1. **Control flow is code, not EM discipline.** Gates are literal `if` statements executed deterministically (`if (divergences.length) return { halted: 'port-divergence', ... }`) — not the EM *remembering* to check between waves. **Why it matters:** a compacted EM forgets to check a gate; a script cannot. The gate fires whether or not the EM's context survived.

2. **Subagent transcripts never enter the EM context.** Each agent's reasoning stays inside the workflow; the EM receives only a small schema-validated result object. **Why it matters:** this is what makes a workflow *survive EM compaction* — if the EM is summarized mid-run, the workflow keeps executing and re-invokes the EM at completion. The EM never carries N agent transcripts, so N can be large without context pressure.

3. **Resumable.** `resumeFromRunId` replays cached successful phases and re-runs only from an edited or failed phase forward (per the Workflow tool description: same-session only; same script + same args → 100% cache hit). **Why it matters:** a phase that halts on a real fork (a transport probe fails, a divergence is found) is fixed and resumed without re-paying the successful phases — the expensive early fan-out is not redone.

---

## When to reach for it

**Executing a plan? The answer is always a Workflow.** As of the 2026-07-09 doctrine hardening the threshold is not "more than one wave" — it is *any* plan you execute via `/execute-plan`, including a single-wave, single-`agent()` plan. A `/execute-plan` invocation is the standing opt-in: no separate PM ask, no "is it big enough" gate. Also reach for it for migrations, audits, and exhaustive review sweeps — anything one context can't hold.

**Decision rule:** you are executing a plan ⇒ author a Workflow. Full stop. The only work that stays ad-hoc `Agent` dispatch is genuinely non-plan work (a quick one-file fix, a single confirmation dispatch, a read-only scout) — see § When it's still overkill. The Workflow tool is a standard Claude Code capability present in every session — there is no "is it available" gate to clear.

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

---

## Model selection: Sonnet by default, Opus is PM-gated

**Every workflow `agent()` call MUST pass `model: 'sonnet'` explicitly.** The Workflow tool's default — omit `model` and inherit the session model — is a token-burn trap in an Opus session: every un-modeled agent runs on Opus (~4x cost per agent-call). Do NOT rely on the tool's "omitting is almost always correct" guidance — that description is wrong for the fan-out executor path, where the whole point is cheap parallel Sonnet workers, not Opus.

**Opus for a workflow agent is rare and PM-gated.** Before launching any workflow that sets `model: 'opus'` (or an Opus-tier override) on ANY `agent()` call, surface the intent to the PM and get explicit approval. Name which agent(s) you want on Opus and why Sonnet was insufficient. The default fan-out — porters, executors, per-wave commit agents, mechanical verifiers — is Sonnet, full stop.

**Negative-spec:** an un-modeled `agent()` in an Opus session is a defect, not a shortcut. The omission is invisible in the script and only surfaces as burn — there is no warning, no gate, and no retry. The PM directive (2026-07-04) explicitly overrides the Workflow tool's own "inherit is almost always correct" claim for this path.

---

## Commit discipline inside workflows

**Workflow agents author but do NOT commit; the EM commits from the returned manifest.** Every executor brief in a workflow carries the instruction verbatim ("Do NOT git commit — EM commits from your returned manifest"). This keeps two doctrines intact:

- The **concurrent-EM scoped-commit doctrine** (coordinator CLAUDE.md § Concurrent-EM Git Operations) — commits stay explicit-path, owner-attributed, and EM-driven.
- **No parallel-agent git-index races** — N agents committing concurrently against one working tree is a corruption surface.

The workflow returns a structured manifest of what each agent wrote; the EM commits from it after the run, applying the concurrent-EM scoped-commit discipline (verify staging with `git diff --cached` before, landing with `git show --stat HEAD` after). Do not introduce agent self-commit inside the workflow as a convenience.

---

## Annotated script skeleton

The shape below is distilled from the pcore-03 dogfood run (`wf_95ffdde0-060`). It shows the load-bearing pieces: `meta` with `phases`, a shared brief constant, a serial gate that halts on failure, a `parallel` fan-out, a probe-then-author gate, and `.filter(Boolean)` on parallel results.

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
const foundation = await agent(COMMON + '\n\nAuthor the shared harness ...',
  { schema: FOUND_SCHEMA, agentType: 'coordinator:executor', phase: 'foundation', model: 'sonnet' })
if (!foundation || !foundation.smoke_ok)     // <-- deterministic gate, not EM memory
  return { phase_reached: 'foundation', halted: 'foundation-smoke-failed', foundation }

// Phase 2 — fan-out: N independent agents in parallel; filter(Boolean) drops dead agents.
phase('fan-out')
const results = (await parallel(SUITES.map(s => () =>
  agent(COMMON + '\n\n' + s.brief + '\nReuse: ' + foundation.harness_api,
    { schema: TEST_SCHEMA, agentType: 'coordinator:executor', phase: 'fan-out', label: s.id, model: 'sonnet' }))
)).filter(Boolean)
if (results.some(r => r.failed > 0))         // <-- gate on the aggregate result
  return { phase_reached: 'fan-out', halted: 'suites-red', foundation, results }

// Phase 3 — probe-then-author gate: the probe halts the run before expensive authoring.
phase('gate-probe')
const probe = await agent(COMMON + '\n\nProbe ONLY — author no product files ...',
  { schema: PROBE_SCHEMA, agentType: 'coordinator:executor', phase: 'gate-probe', model: 'sonnet' })
if (!probe || !probe.transport_ok)
  return { phase_reached: 'gate-probe', halted: 'transport-fork', foundation, results, probe }

return { done: true, foundation, results, probe }
```

Notes on the shape:
- **Every `agent()` call passes `model: 'sonnet'`** — the Workflow default inherits the session model, so an un-modeled agent in an Opus session runs on Opus (~4x cost). Sonnet is the workflow default; Opus is PM-gated (see § Model selection: Sonnet by default, Opus is PM-gated).
- **Every `agent()` call passes a `schema`** — the result is validated at the tool-call layer, so the model retries on mismatch (per the Workflow tool description) and the EM receives structured data, not prose to parse.
- **Halts return a structured object** naming `phase_reached` and `halted:` — the EM reads which gate fired and why, then fixes and resumes via `resumeFromRunId`.
- **`agentType: 'coordinator:executor'`** routes each agent through the coordinator executor (self-contained brief, auto). Other coordinator agent types (`coordinator:code-reviewer`, etc.) compose the same way.

---

## Mapping onto the Dispatch Ledger

A workflow does not replace the gate-graph/ledger discipline — it is the **carrier** of it:

| Ledger / gate-graph concept | Workflow encoding |
| --- | --- |
| A wave in the Dispatch Ledger | A `phase()` group |
| A chunk row (one agent) | One `agent()` call, labelled |
| A **serial gate** (file-overlap / output-consumption / contract-change) | An `await` boundary + an `if (...) return { halted }` |
| A **parallel wave** (no overlap) | A `parallel([...])` barrier |
| An item-by-item pipeline with no barrier between stages | `pipeline(items, stage1, stage2, ...)` |
| The EM committing from executor output | The EM committing from the workflow's returned manifest |

Author the ledger first (it is the plan artifact and the review oracle); the ledger's wave map then transcribes directly into workflow phases.

---

## Dogfood precedent

**`wf_95ffdde0-060`** — the pcore-03 beachhead remainder. After the EM manually dispatched the first two waves serially (and hit compaction risk holding the wave map), the remaining pipeline — contract-test gate → veneer flips → MCP shim probe/author → parallel closeout — ran as a single background workflow (waves C5–C9). The workflow also caught a real bug in its lead phase: a UDS socket path exceeding the macOS 104-char `sun_path` limit, fixed and verified before any downstream phase ran. Run id: `wf_95ffdde0-060`. Plan ledger (durable, `~/.claude` meta-repo only — not present in the OSS coordinator publish): `docs/plans/2026-07-02-pcore-03-beachhead-coordinator-core.md § Dispatch Ledger`. Script (session-local, ephemeral): `projects/-Users-example-operator--claude/57804be4-.../workflows/scripts/pcore-03-beachhead-remainder-wf_95ffdde0-060.js`.

---

## See also

- `dispatching-parallel-agents.md` — the ad-hoc fan-out methodology a workflow escalates *from*; § Executing a Fan-Out Wave is the manual path, this wiki is the scripted-orchestration path.
- `skills/execute-plan/SKILL.md` — Phase 1.5 (Dispatch-Gate Graph) and Phase 1.6 (Dispatch Ledger); names workflows as a multi-wave execution vehicle.
- The `Workflow` tool description (EM tool surface) — authoritative API + cache-window + resume semantics.
- Global CLAUDE.md § Fan-out dispatch extras — the parent fan-out doctrine.
