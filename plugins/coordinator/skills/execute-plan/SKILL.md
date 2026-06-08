---
name: execute-plan
description: Execute a PM-approved implementation plan directly in the coordinator session
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — Direct In-Session Plan Execution

Run a PM-approved implementation plan to completion without stopping for permission between tasks. The PM's approval of the plan is the authorization — this command executes it diligently and in its entirety, commits the work, and reports. It does **not** chain into branch disposition (merge / PR / keep): finishing a development branch involves the PM-gated `/merge-to-main` and is a separate decision. The natural next step after a plan is executed is `/workstream-complete` (cap the workstream — lessons, docs, workstream-complete review), which execute-plan offers but does not auto-invoke. See Phase 4.

**Core principle:** Write-ahead every task (both plan document on disk AND task list via TaskUpdate), execute autonomously, stop only when your judgment says the plan itself is in trouble — not when a task is merely hard.

**Stance — execute = restructure-then-dispatch.** Executing a plan is not "type the plan's steps." It is: read the plan, build the dispatch-gate graph (Phase 1.5), and then **decompose into per-chunk dispatches** — one executor per chunk, fanned out in parallel where the gates allow and run in sequence where they don't. Decomposition is unconditional; parallelism is only the time-overlap axis. **A serial chain is still N dispatches (a fresh agent per chunk, EM-verify between), never one long-lived executor walking the chain** — that bundling is the failure this skill exists to prevent. This whole shape is the fan-out methodology execution follows (`docs/wiki/dispatching-parallel-agents.md` § Executing a Fan-Out Wave), not a separate command, and it governs serial waves as much as parallel ones (serial = depth-1 cohorts). Execution owns the judgment of restructuring the plan into the right wave shape; fan-out owns the mechanical dispatch underneath. The default outcome of executing is a dispatched wave.

**Self-execute vs. dispatch is a token-economics call, not a vibe.** A Sonnet executor burns ~¼ the tokens of an Opus EM doing the same edits, and finishes faster — so dispatch wins on the axis that matters almost every time, and self-executing inline is the rare carve-out, justified only when you can name why it is genuinely cheaper *here* (loci already loaded, tight cross-file coherence on a small surface). Ground that against the `When to EM-Inline` checklist in `docs/wiki/agent-dispatch-economics.md`; the full criterion lives at Phase 1.5 § Self-execute escape hatch. If the plan contains enriched stubs with known file paths, exact line numbers, and code sketches, the dispatch is even cheaper — fan out Sonnet executors per `docs/wiki/delegate-execution.md`.

---

## Arguments

`$ARGUMENTS` is the path to the plan document to execute — e.g., `tasks/my-feature/todo.md` or an absolute path. The file must be readable and contain a structured implementation plan.

If no path is provided, report: _"Usage: /execute-plan <plan-path>. Provide the path to the plan document you want to execute."_ and stop.

---

## Phase 1: Load and Review

1. Read the plan document at `$ARGUMENTS` in full
2. Review it critically — identify any gaps, ambiguities, or concerns:
   - Missing file paths or unclear scope?
   - Steps that assume context not captured in the plan?
   - Dependencies on external state that may have changed?
   - Anything that would require an architectural decision mid-execution?
3. **If concerns exist:** Surface them to the PM before proceeding. Do not start implementation on an unclear plan.
4. **If no concerns:** Announce _"I'm running `/execute-plan` to implement this plan."_ and continue to Phase 1.5.

---

## Phase 1.5: Dispatch-Gate Graph

<!-- spec-backlink: docs/plans/2026-05-27-fan-out-default-doctrine.md § Chunk 5b — responsibility-split table; the mechanical steps (overlap pass, scoped-prompt emission) route to the helper + fan-out skill; budget-sizing and gate-type discrimination are EM-judgment steps retained here -->

This phase is the EM's named responsibility at the seam between plan-approved and first executor dispatch. It applies whether execution is direct (Phase 3 of this skill) or via dispatched executors per `docs/wiki/delegate-execution.md` — the gate-graph is identical in either case; only the executor identity differs.

**Three real gate types** determine what can run concurrently vs. must be serial (narrative causality, aesthetic ordering, and "I'd rather review A before B" are NOT gates):
- **File-write overlap** — two tasks edit the same path.
- **Output-consumption** — Task B reads a file Task A writes.
- **Contract-change dependency** — Task A bumps a schema, helper signature, or shared surface Task B depends on; promote shared-API work to a predecessor wave.

**Output-consumption and contract-change gate *verification*, not *authoring*.** When B's only dependency on A is consuming its output or contract, B can be *authored* concurrently with A if the interface is pinned (the full signature written down, precise enough to author against without asking the producer) — only B's green-verification waits for A to land. File-write overlap is the sole unconditional serial gate. Default to concurrent-with-pinned-interface, verify-at-merge: pin the interface, fan out producer + consumers in one wave, verify at merge (at agent speed, per-dispatch serialization outweighs the occasional merge-point mismatch). Hard gate: no pinnable interface → no concurrent authoring. Fall back to the predecessor-wave shape only when the interface can't be confidently pinned, or per-chunk blast-radius isolation is worth the serialization on a high-stakes surface.

→ Full taxonomy and rationale: `docs/wiki/dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy (incl. Author vs. verify) and § Peer-Scope Prohibition in Parallel-Wave Prompts.

**EM-judgment step 1 — Gate-type discrimination (helper cannot do this):** Classify every task-pair relationship as one of the three gate types above, or as truly independent. The helper detects file-write overlap automatically; output-consumption and contract-change dependencies require EM reading the plan's per-task scope. Do not outsource this classification — the helper sees file paths, not semantic contracts.

**Build the wave shape from the file-write graph, NOT from the plan's section/phase/cluster structure.** Plans are written for *readers* — grouped by theme, by subsystem, by narrative arc. Those are reader-axes, not dispatch-axes. The mechanical step at the top of ledger construction (Phase 1.6) is: enumerate every write-target the plan touches, group by *write-overlap*, then map chunks onto the resulting lanes. A plan with 6 thematic clusters across ~6 disjoint file-lanes is **one parallel wave of ~6 lanes**, not 6 sequential phases — even if the plan document presents the clusters as Phases 1–6. **Recurring failure mode** (2026-06-02): mapping the plan's narrative phases directly onto execution phases and serializing them; the only Phase-1 ordering that ever mattered was a single upstream commit, and the rest were independent file-lanes that should have run concurrently. Recheck before dispatching: of the gates you imposed, which are file-write overlap, output-consumption, or contract-change — and which are theme/phase/cluster? Strip everything that isn't a real gate.

**EM-judgment step 2 — Budget-sizing (helper cannot do this):** Aim for ~5–10 min per executor on a single coherent surface, 15 min hard ceiling. **Rule of thumb: a series of small-remit executors beats one executor with a large remit — in parallel where the gates allow, in sequence where they don't.** The budget axis is **orthogonal** to the parallelism gates above: file-overlap answers *can these run concurrently*, NOT *how many dispatches*. When overlap (or output-consumption, or contract-change) forces serial execution, walk each serial position and apply the budget check independently — `"can't parallelize" ≠ "one dispatch."` Over-budget coupled work chunks into a **fresh agent per chunk** (`dispatch B2 → EM verifies → dispatch fresh C1 → EM verifies → dispatch fresh C2/D`), never one agent handed chunk after chunk. One long-lived agent grinding a sequence is the overload in slow motion — context accumulation, growing blast radius, degrading judgment. → `docs/wiki/dispatching-parallel-agents.md` § Coupling Rules Out Concurrency, Not Decomposition.

**Mechanical step — follow the fan-out methodology:** Once gate-type discrimination and budget-sizing are done, **follow the canonical fan-out methodology** at `docs/wiki/dispatching-parallel-agents.md` § Executing a Fan-Out Wave. Fan-out is a methodology execution follows, **not a skill to invoke** — there is no `/fan-out` command. This Phase 1.5 *is* the plan-mediated entry to that methodology.

Compile the wave spec (one TSV row per chunk: `<chunk-id>\t<brief>\t<comma-separated-files>`) from the gate-graph analysis above, then walk the methodology's steps: **Step 0.5** fan-out suitability gate (HARD STOP — re-chunk any fat chunk before dispatch), **Step 1** run `fan-out-dispatch.sh` for the overlap pass + scoped-prompt compilation (hard-stop on collision), **Step 2** organic ramp, **Step 3** dispatch the compiled blocks via `Agent` (`mode: "acceptEdits"`, all concurrent), **Step 4** EM-serial commit. **Do NOT duplicate wave-map logic here** — the helper + the wiki methodology are the single source for that ceremony.

**Self-execute escape hatch — gated on token-economics, not vibe.** The default is to dispatch: a Sonnet executor burns roughly a quarter of the tokens an Opus EM would on the same edits, and finishes faster, so dispatch is cheaper on the axis that matters almost every time. **Self-execute (the EM runs Phase 3's tasks inline instead of dispatching) only when you can articulate why it is genuinely cheaper *here*** — e.g. the loci are already loaded in your context and re-loading them into N executors would cost more than typing, or cross-file coherence across a small surface is the dominating constraint. Ground that articulation against the concrete `When to EM-Inline` checklist in `docs/wiki/agent-dispatch-economics.md` (fix-locus ≤3 files / <60s on a >30k-file repo / mechanical / context-already-loaded / mid-edit-hazard) — "articulably cheaper" is self-graded by the same agent that wants to skip the work, so the checklist is the guard against rationalizing it. **Self-execute is the one path that skips the Step 0.5 suitability gate** (the EM holds the gate in its own judgment instead), so the bar is high. The gate-graph still applies either way — it sequences Phase 3's tasks even when one executor (the EM) runs them all. Self-executed chunks still appear in the Phase 1.6 ledger as `inline (EM)` rows — one row per chunk, never a bundle.

---

## Phase 1.6: Dispatch Ledger — Mandatory Pre-Dispatch Gate

<!-- spec-backlink: this skill's 2026-05-30 failure — gate graph correctly produced 4 chunks (1 / 3b / 2 / 3a); EM narrated "delegate the chunker to a focused executor" then dispatched "3b + 3a + 2" as ONE 23-minute executor. The prose rule in Phase 1.5 ("can't parallelize ≠ one dispatch") was present and ignored; this ledger converts it into a mechanical artifact where the bundle is malformed on its face. -->

**Before issuing *any* `Agent` call, WRITE a dispatch ledger INTO the plan document on disk** — a `## Dispatch Ledger` section, one row per chunk from the Phase 1.5 gate graph. **This is a disk write, not a chat emission.** A ledger narrated to chat is ephemeral and the EM can rationalize around it mid-flow; a ledger written into the plan file is the contract the EM dispatches against — crash-durable, PM-visible, and re-readable after compaction. It is the same write-ahead discipline as Phase 3a, applied to the dispatch decomposition. The failure it prevents: the EM narrates an intent ("I'll delegate the chunker to a focused executor") and then silently bundles several gate-graph chunks into one open-ended dispatch because they happen to be serial. A ledger on disk makes that bundle visibly malformed before it is dispatched — and keeps it malformed where chat scrollback would have buried it.

Edit the plan document (the file at `$ARGUMENTS`) to add:

```markdown
## Dispatch Ledger

| dispatch # | chunk-id | one-line brief | write-files | runs | est-min | status |
|---|---|---|---|---|---|---|
| 1 | … | … | … | inline (EM) / parallel / after #N | … | pending |
```

**The invariant — one chunk per row, one chunk per dispatch:** the number of distinct dispatch-numbers (counting `inline (EM)` rows) **equals** the number of chunks. **If any single dispatch number spans more than one chunk-id, the ledger is malformed — STOP and split before dispatching.** "These chunks are serial, so one executor can just walk them in order" is the exact rationalization this gate rejects: serial coupling removes *concurrency*, never *decomposition* (Phase 1.5 EM-judgment step 2; wiki § Coupling Rules Out Concurrency).

**Disjoint-write-target expansion rule — applied AT ledger construction, not after PM prompting.** Before writing a row, list every path in `write-files` for that chunk. **If those paths split into K mutually-disjoint groups** (no path in group A is co-edited with any path in group B by the chunk's own logic), the chunk fans out into K rows — one per group — at ledger-write time. A plan-chunk like "C7 — update three docs (A.md, B.md, C.md)" with three independent docs is **C7a / C7b / C7c**, three parallel rows, not one row that walks them. The bar for keeping N disjoint write-targets in one row is *tight cross-file coherence* the chunk's own brief names (e.g. ".sh + .ps1 lockstep that must commit together"); thematic affinity ("they're all docs", "they're all install-surface") does NOT meet it. **If you find yourself writing "N parallel-safe chunks → N rows" and any of those rows has multiple disjoint write-targets internally, you have under-expanded — split now, before dispatch, not after the PM points it out.** Recurring failure (2026-06-02): 9 parallel-safe chunks dispatched as 9 executors when 3 of them each owned 3 disjoint surfaces — the correct shape was 17.

- **`runs` column** records each row's gate: `parallel` (same wave), `after #N` (serial — a fresh agent that fires only after dispatch #N has landed *and* the EM has verified it on disk), or `inline (EM)` (the token-economics self-execute carve-out).
- **`est-min` > 15 on any row → re-split that chunk before dispatch.** The per-executor ceiling is 15 min on one coherent surface; aim for 5–10.
- **A serial chain is N sequentially-dispatched rows** (`after #1`, `after #2`, …) — each a fresh agent on a clean context with EM verify-and-commit between, **never one long-lived executor**. This still routes through the fan-out methodology's Step 0.5 suitability gate (serial just means depth-1 cohorts); do not read a serial gate graph as an exemption from the methodology.
- **`status` column is write-ahead state, updated on disk as Phase 3 proceeds:** `pending` → `dispatched` → `verified` → `committed`. Edit the row in place at each transition — the same crash-insurance Edit Phase 3a does for task state. A post-compaction or post-crash agent re-reads this table to see exactly which chunks shipped and which are still owed.

**Runtime tripwire — the EM owns the clock.** If any dispatched executor runs past ~15 min wall-clock, that is a dispatch-sizing failure surfacing late: **stop it, recover partial work from disk (it persists — shared working tree), and re-split into fresh per-chunk dispatches** (add the split rows to the ledger on disk). Do not wait for it to finish, and do not wait for the PM to flag the runaway — a single executor at 20+ min is prima facie evidence the chunk was too big.

---

## Phase 2: Create Flight Recorder

Create a task list (TaskCreate) for this execution session:

- **One session-goal task** — titled with the overall objective and the plan path, so a post-compaction agent can re-orient without re-reading the conversation
- **One task per plan phase or major task** — enough granularity that "what is in progress" is unambiguous at any point
- **Mark the session-goal task `in_progress`** immediately via TaskUpdate

This flight recorder is your compaction insurance — tasks persist through compaction by design. Keep it current throughout execution.

---

## Phase 3: Execute All Tasks

**Default behavior: execute every task in sequence without stopping to ask permission.**

For each task in the plan:

### 3a. Write-Ahead (before starting the task)

Update BOTH:
1. **The plan document on disk** — mark the current task as `In progress (started YYYY-MM-DD HH:MM)`. Edit the file directly. This is crash insurance — if the session dies, the plan shows where execution stopped.
2. **Task list** — mark the corresponding task `in_progress` via TaskUpdate

### 3b. Execute

- Follow the plan's steps exactly — do not improvise or extend
- Run verifications as the plan specifies
- Fix routine errors (type errors, missing imports, lint) immediately and move on — these are expected noise, not blockers

### 3c. Mark Complete (after the task passes verification)

Update BOTH:
1. **The plan document on disk** — update the task to `Complete (YYYY-MM-DD HH:MM)`
2. **Task list** — mark the corresponding task `completed` via TaskUpdate

### 3d. Proceed

Move immediately to the next task. Do NOT pause to ask _"should I proceed?"_ or _"ready for feedback?"_ — brief status updates at natural milestones are fine (_"Phase 2 complete, moving to Phase 3"_), but these are informational, not permission requests.

---

## When to Stop and Reassess

Stop executing and consult the PM when, in your best judgment, there is genuine cause:

- **Accumulating patches** — 2+ workarounds or "good enough" fixes that suggest the plan's approach is off. Step back before the debt compounds.
- **Ambiguity spreading** — a gap in the spec has infected multiple tasks, and continuing means guessing at each one. Get clarity before proceeding.
- **Structural verification failure** — not a fixable error but repeated failures suggesting the approach is fundamentally wrong.
- **Scope surprise** — the work is significantly larger, riskier, or more invasive than the plan anticipated.
- **Breaking change discovered** — something in the codebase has changed since the plan was written that invalidates its assumptions.

**When you stop:** Record in both the plan document AND the relevant task's `metadata.tried_and_abandoned` field (via TaskUpdate) what approach was tried and why it failed. Format: `"Tried: [approach] — Failed: [reason]"`. This prevents a future session from retrying the same dead end.

**Do NOT stop for:**
- Routine fixable errors — fix them and move on
- Minor ambiguity resolvable with one reasonable judgment call — make the call, note it in your completion report
- Wanting to check in — that's not a reason to interrupt the PM's flow

---

## Phase 4: Finalize and Report

After all tasks are complete and verified. **Execute-plan ends here — it does not chain into branch disposition.** Implementing a plan is EM-remit engineering work; deciding what happens to the branch (merge / PR / keep) reaches the PM-gated `/merge-to-main` and is a separate, PM-invoked decision. Auto-chaining plan-execution into that flow would structurally drive every plan toward a gate the EM cannot fire — the conflict this phase exists to avoid.

### Phase 4a: Early Acceptance-Oracle Feedback (non-authoritative)

<!-- spec-backlink: archive/specs/2026-05-24-acceptance-oracle-with-teeth.md §2.3 — execute-plan Phase 4 early non-authoritative gate -->

Run the acceptance oracle as early advisory feedback. The plan path is `$ARGUMENTS` (the plan document this skill was invoked with).

```bash
bash check-acceptance-oracle.sh "$ARGUMENTS"
```

**This gate is advisory only at this surface** — the authoritative gate is at `coordinator:workstream-complete` Step 3.8. Do NOT hard-block here regardless of exit code.

- **Exit 0:** Log _"Acceptance oracle: all gate-bound tests pass."_ and continue to Phase 4b.
- **Non-zero exit:** Log the verdict from the script (it will name which rows are red), then continue to Phase 4b. Frame the output as early feedback: _"Acceptance oracle reports red tests — iterate on these before reaching /workstream-complete, where the gate is authoritative."_
- **Script not found or no plan path:** Skip silently and continue to Phase 4b.

### Phase 4b: Commit, Report, and Offer the Next Step

1. **Commit any uncommitted work** with a scoped, explicit-path commit (plain `git add -- <paths> && git commit`, per the concurrent-EM commit doctrine). Commits are EM-remit quick-saves; don't ask permission to commit.
2. **Report completion** — what landed, the acceptance-oracle verdict from Phase 4a, and the branch the work is committed on.
3. **Offer the natural next step as an offer, not an auto-invocation:**

   > _Plan executed and committed on `<branch>`. The natural next step is `/workstream-complete` to cap the workstream (lessons, docs, workstream-complete review). When you want to ship it, `/merge-to-main` or `/workday-complete` carries the branch to main._

   Do **not** invoke `/workstream-complete`, `/merge-to-main`, `/workday-complete`, or `coordinator:finishing-a-development-branch` automatically. `/merge-to-main` is keyword-gated (the PM invokes it by name); `/workstream-complete` vs `/handoff` vs `/workday-complete` depends on workstream state, which the PM picks. Naming the affordance keeps it discoverable without firing it — design-as-offers.

---

## Failure Modes

| Situation | Action |
|---|---|
| Multiple gate-graph chunks about to go to one executor | Malformed ledger (Phase 1.6) — STOP, one chunk per dispatch, split before dispatching |
| Wave shape mirrors the plan's section/phase/cluster structure | Theme is not a gate. Rebuild from the file-write graph per Phase 1.5; strip any gate that isn't write-overlap / output-consumption / contract-change |
| A ledger row has N internally-disjoint write-targets | Under-expanded. Split into N rows (Phase 1.6 disjoint-write-target expansion rule) before dispatching; thematic affinity is not a coherence reason |
| A dispatched executor runs past ~15 min wall-clock | Dispatch-sizing failure — stop it, recover partial work from disk, re-split into fresh per-chunk dispatches; don't wait for it or for the PM to flag it |
| Plan path not provided | Report usage and stop |
| Plan file not found | Report the path that was tried and stop |
| Plan has no concerns but looks unreviewed | Surface the observation; proceed only if PM confirms |
| Task fails with fixable error (type error, import, lint) | Fix immediately, continue |
| Task fails with structural error after 2 attempts | Stop, record what was tried, consult PM |
| Verification step in plan fails | Stop and report — do not skip verifications |
| Plan's approach is invalidated mid-execution | Stop, record `Tried/Failed`, flag for PM to update plan |
| Tests fail at Phase 4 | Report failures in the completion report; do not offer `/workstream-complete` as a clean next step until they're green. Fix routine failures and re-run; stop and consult the PM on structural failures |

---

## Relationship to Other Commands

- **Fan-out methodology (`docs/wiki/dispatching-parallel-agents.md` § Executing a Fan-Out Wave)** — the dispatch ceremony execution follows, **not a skill** (the `/fan-out` command was demoted 2026-05-30; the verb collided with native Claude Code vocabulary). Phase 1.5 is the plan-mediated entry to it; ad-hoc parallel work (≥2 tasks, no plan doc) follows the same methodology inline. Stance: **execute = restructure-then-dispatch; fan-out = the dispatch methodology**.
- **Executor dispatch (`docs/wiki/delegate-execution.md`)** — the model-selection rubric for the executors a fan-out dispatches; use when the plan consists of enriched stubs with exact code sketches, file paths, and line numbers. Dispatch is the default; self-execute inline only on the token-economics carve-out (see Phase 1.5 § Self-execute escape hatch).
- **`/enrich-and-review`** — should be run before executor dispatch; not required before `/execute-plan` (plans that route here are typically less chunked).
- **`/review-code`** — optional post-execution code quality pass on the implemented work. If the plan called for it, route through `/review-code` before reporting completion in Phase 4b.
- **`coordinator:plan`** — creates the plan that this command executes. A plan produced by that skill is the ideal input here.
- **`coordinator:workstream-complete`** — the natural next step after a plan is executed, offered (not auto-invoked) in Phase 4b. Caps the workstream: lessons, docs, workstream-complete review.
- **`coordinator:finishing-a-development-branch`** — **not** chained from here. Branch disposition (merge / PR / keep) is a separate, PM-invoked decision that reaches the keyword-gated `/merge-to-main`. The PM invokes it directly when ready to ship.
