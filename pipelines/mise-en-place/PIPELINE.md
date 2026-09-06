# Mise-en-Place

> Referenced by `/mise-en-place`. This is a pipeline definition, not an invocable skill.

## Overview

Everything in its place before the fire gets lit. This pipeline front-loads all context gathering and planning so the execution phase is uninterrupted autonomous flow through a backlog of scoped work.

**Core principle:** Prep all context, lay out every step in a compaction-proof flight recorder, then execute the full sequence without stopping for permission. The PM authorized the run when they invoked this command.

**Anti-stall rule:** Once Phase 5 begins, NEVER pause to ask the PM a question, offer a choice, or wait for input. The base model's instinct to confirm is the enemy here — if you pause mid-run, the tail phase (shutdown/hibernate) never triggers, and the machine stays on indefinitely burning energy. Status updates are output-only; they do not expect or wait for a response. If you catch yourself composing a question between items, suppress it and proceed. The only exception is the "When to Stop" criteria below — genuine blockers, not comfort-check-ins.

### Tail Modes

The tail action after execution depends on how the PM invoked the skill:

| Mode | Trigger | Tail action |
|------|---------|-------------|
| **Standard** (default) | No special flags | EM-serial per-wave commits + push only (no `/update-docs`) |
| **Hibernate** | PM says "overnight", "hibernate", "shutdown", "go to bed", or similar | verify push, then hibernate PC (no `/update-docs`) |

**Default to standard.** If the PM doesn't specify a mode, run standard. Don't ask — the PM can always invoke `/workday-complete` separately afterward. The EM confirms the mode in Phase 4 ("Tail: EM-serial per-wave commits + push only — straight shot, work stays on branch").

**Standard/Hibernate is orthogonal to the run-level verdict.** Tail mode governs the machine action at the end of the run; it does not say anything about how much of the backlog got executed. § Phase 6 below governs that separately via the COMPLETE / CONTINUANCE terminal.

**Why no merge-to-main from mise-en-place?** This skill runs autonomously, often with the PM away from the terminal. Claude cannot verify all externalities — CI may fail, behavioral regressions may be subtle, colleagues may be affected. Merging unsupervised work to main violates the safety principle of matching blast radius to confidence level. The PM merges to main when they return, after reviewing the branch. Use `/workday-complete` or `/merge-to-main` interactively when the PM is present.

**Announce at start:** "I'm running `/mise-en-place` to prep and execute a straight shot through the backlog."

## What Mise IS NOT

Mise is not "plan-as-you-go autonomy." It is not a license to live-assemble specs or research a downstream contract mid-run — that requires EM judgment, reviewer dispatch, and PM alignment; it is session-EM territory, not autonomous-execution territory. A gated, once-built foundation wave (readiness criterion 2) is legal.

The coordinator system optimizes for first-pass correctness: planning happens deeply BEFORE the run, so executors only type. If a planned wave produces a decision/artifact that is still *undecided* and later waves depend on it for their own definition, the run is not ready for mise — it is ready for a planning session.

## When to Use

- You have 2+ items that are **mise-grade** by the readiness criteria below
- The PM wants autonomous execution of mechanical work with minimal interruption
- The PM wants the backlog cleared — whether they're watching, stepping away, or wrapping up for the day

## Readiness Criteria — All Items Must Pass

A mise-grade item meets ALL of the following:

1. **The decisions are made.** No open PM-level or architectural fork remains inside the item — acceptance criteria are explicit and verifiable. A Sonnet executor is expected to resolve local implementation detail (naming, ordering, mechanics) from a bounded spec; what disqualifies an item is an undecided *decision*, not an unwritten *line*. A PM-authorized plan does not need an enricher pass to clear this bar, and its stamp clears a NAMED open decision that carries all three of (a) an owning chunk, (b) stated settling criteria, and (c) a written obligation to record the rationale — that is decided-how-to-decide, a bounded spec. **The stamp is not a blanket exemption:** an unowned open fork inside a stamped plan still disqualifies the item, and a stamped-but-forked plan walking straight through this gate is the failure this qualification exists to stop.
2. **Downstream contracts are sequenced, not absent.** A foundation wave is legal, provided it is (a) built exactly once — no two items independently building the same mechanism, (b) sequenced first, and (c) closed by an explicit live gate before consumers fire (the nine-baton conductor's W0/W0.4 is the reference: the seam was built once, and the gate was a live smoke proving the mechanism reached a real consumer, not merely that files existed). What still disqualifies: a foundation artifact whose *content* is itself an undecided decision — research output, or "a wiki page that tells later waves what to build" where the what is not yet settled. The discriminator: **decided-but-unbuilt is legal; undecided is not.**
3. **Pure-executor agent type.** A Sonnet executor (or coordinator-inline) can complete it given the spec — not enricher, not reviewer, not staff-session, not live-MCP authoring.
4. **File footprint declarable and data-reachable.** Files-to-be-written can be named in advance, AND the data the change needs is confirmed available at the layer being changed.
5. **Verification is mechanical.** Tests pass, signatures match, AC checked off — not "the reviewer agrees."

## Don't Use When

The EM routes an item out of a /mise run — not the whole run — if it exhibits these patterns:

- **A foundation item whose output is itself an undecided decision** — research stubs, brainstorming stubs, or a reference doc whose content isn't yet settled. A once-built, gated foundation (readiness criterion 2) is NOT this pattern — don't conflate the two.
- **Mixed agent types in the planned waves** — enricher + executor + MCP-author together signals the work isn't ready.
- Items carrying an open PM-level or architectural fork — marked `Pending Review` or with reviewer findings not yet resolved into a decision.
- Vague, unverifiable acceptance criteria ("improves the system") rather than checkable ones.
- Items requiring `manage_*` MCP tools in a live editor — those need an interactive EM-driven flow.
- Only one item — use `/execute-plan` directly.
- Items aren't scoped yet — use `coordinator:plan` or `coordinator:brainstorming` first.
- Iterative PM judgment expected throughout.

**If any item fails, route it out and proceed on the remainder** rather than declining the entire run. A failing item is either decided-but-unbuilt (assign it to a gated foundation phase) or carrying an undecided fork (route out of scope with a named reason — planning session, /enrich-and-review, `/review` (plans) or `/review-code` (code), /staff-session, executor dispatch via `/delegate-execution`). Report the routing, not a refusal. Reserve an outright decline for when the routed residue isn't a coherent run on its own, or when routing an item would itself require a PM decision.

## The Process

### Phase 0a: Baton Intake — Claim What You Were Handed

Artifact paths on the invocation line are batons, and **handing batons to /mise is a grab, so it claims.** The claim is a mutual-exclusion check: /mise's file-disjoint wave model coordinates executors *within* a run and gives nothing across sessions, so an unclaimed-baton run is unsafe no matter how clean the wave map is.

**The claims already fired** — the `/pickup` auto-fire covers this surface, extracting baton paths from the argument line (flags, item identifiers, and plan paths filtered out; a plan is inventory input, not an artifact with a claim), briefing each, and claiming wherever the coast was clear. No separate claim mechanism exists here, and there is no hand-edit path to the lifecycle frontmatter.

Residual judgment, all of it `/pickup`'s ordinary shape: resolve open judgment points and claim those batons (`pickup-assemble apply <path>`) before Phase 5's no-stopping rule begins; reconcile each pending list against reality; treat contention per baton — N batons is N independent dispositions, and one standing down never blocks a sibling. Convergence into a single wave map is Phase 2e's job, strictly downstream of N separate claims.

**A claimed baton judged un-mise-ready gets put back down, not carried** — `pickup-assemble drop <path>` returns it to open and ready-to-fire, the same inverse `/pickup` uses, and the run proceeds on the remainder. Announce before Phase 0: "Claimed N batons: [paths]. [M put back down: reason.]"

### Phase 0: Readiness Gate

**Bypass condition.** If the session was opened from a handoff (or the PM's invocation explicitly references one) and that handoff asserts **executability** for the queued items — that a Sonnet executor can finish them from the spec — **skip Phase 0 entirely** and proceed to Phase 1. The bypass is valid when the handoff names the items in scope and asserts that in its body. **`pickup_ready` is not mise-ready and never satisfies this**: it means a session can usefully pick the baton up, which stays true of a baton whose gate is shut — picking it up and discovering the shut gate is a legitimate outcome. **`deployment_state: awaiting_gate`, or a stop condition stated anywhere in the body, disqualifies the bypass regardless of what any other field asserts** — a handoff whose frontmatter and body disagree is resolved in favour of the body. Re-running the gate after a verified handoff is wasted context — large backlogs can blow the EM's window on stub reading alone, which is the failure mode this bypass exists to prevent. Announce the bypass: "Phase 0 bypassed — handoff at <path> asserts executability for [items]." If unsure whether the handoff covers all queued items, do NOT bypass.

**Otherwise:** before inventory, before announcement, before any flight-recorder work — apply the readiness criteria above to every candidate item. A failing item routes out of the run (see the command file for the routing-report format) rather than blocking Phase 1 — reserve stopping the whole run for when the routed residue isn't coherent, or when routing itself would need a PM decision.

### Phase 1: Inventory — What's on the Board?

**Bandwidth rule:** The EM does NOT read every stub. For runs with >3 items (or PM-flagged "many items"), dispatch a Sonnet inventory scout with `run_in_background: true` to produce a structured table at `state/mise-inventory/<run-id>.md` (one row per item: identifier | spec path | one-line summary | declared file footprint | dependencies | verification | complexity | disposition).

**The record MUST open with frontmatter carrying `run_id:` and `start_sha:`** — `start_sha` being `git rev-parse HEAD` at the moment Phase 1 opens, captured by the EM and passed into the scout's brief (the scout cannot know the run's own starting point). This is not bookkeeping: § Phase 6's review-scale verdict is computed over `<start_sha>..HEAD` and reads that field off this record. A record without it downgrades Phase 6 from a computed verdict to an unresolved judgment point. The `spec path` column is load-bearing for the same reason — the verdict's `baton_count` is derived by counting distinct top-level artifacts (`docs/plans/*.md`, `state/handoffs/*.md`, `tasks/*/todo.md`) in that column, so a row whose spec path is elided costs the run a baton in its own review sizing. **The `Footprint` column is load-bearing in the same literal way** — Phase 5 mints the dispatch spine from it, reading only backticked repo-relative paths, so a footprint written as prose stops the mint rather than degrading it. Write the paths in backticks; prose may surround them. **Not `tasks/` — this record is a CONTINUANCE input (§ Phase 6), therefore load-bearing substrate, and `tasks/` is swept aggressively** (project `CLAUDE.md`, state-vs-tasks split). It also carries the run's **authorization basis** — which plans or items the PM named at invocation, and when — not just the chunk table; this is the corroborating detail a later auditor reads alongside the sentinel (`docs/wiki/plan-execute-session-split.md` EXCEPTION 3). The scout writes to disk and returns `DONE: <path>`; the EM reads the table from disk and works from it for Phase 2 sequencing. The full spec text stays out of the EM's context until the executors load it. **Scope the scout off the working tree.** It reasons from the named specs, never from "what is uncommitted" — a shared tree routinely carries a hundred-plus dirty paths from live peer sessions, and an unscoped read attributes their work to this run. The same footprint discipline § Phase 6's anti-vacuity gate spells out applies here, one phase earlier, where the misattribution enters the ledger rather than the verdict.

**Disposition column — live, not a snapshot.** The `disposition` column is UPDATED AT EACH WAVE GATE (§ Phase 5, wave-gate commit step) as items resolve, not written once by the scout and left stale. Phase 6's exhaustion check reads this column directly — a mechanical read of the on-disk ledger, never EM recollection. Each row's disposition is one of the CLOSED SET § Phase 6 defines.

Sources the scout (or the EM, for ≤3-item runs) checks:

1. **Plan files:** `tasks/*/todo.md` — items marked ready/pending execution
2. **Enriched stubs:** Any chunk directories with status "Enriched" or "Reviewed"
3. **PM's explicit list:** If the PM named specific items (e.g., "PX4-6B through Cesium-D"), use that as the canonical list
4. **Open tasks:** Any `tasks/*/` directories with incomplete work
5. **Claimed batons:** If Phase 0a ran, its claimed set is canonical and already reconciled — inventory the work *inside* those batons (plans, spines, next-step queues), and do not re-resolve the artifacts themselves

### Phase 2: Sequence and Parallelize — Maximum Velocity

The goal is maximum throughput: run as many items concurrently as possible while guaranteeing no two concurrent executors touch the same files.

**Step 2a — Dependency sort:** Order items by dependency (item B needs item A's output → A before B), then by complexity (smaller first to build momentum, unless dependencies dictate otherwise).

**Step 2b — File-overlap analysis:** For each item, read its spec and identify the **file footprint** — the set of files it will create, modify, or read-then-write. This doesn't need to be exhaustive; focus on write targets. Items whose specs name the same files (or the same directories in a "touch everything in this dir" pattern) have overlapping footprints.

**A well-formed file list can still be unbuildable.** For any consumer-layer item (UI component, CLI surface, renderer, or any layer consuming data produced elsewhere), a cheap pre-flight before dispatch: confirm the data the change needs actually reaches that layer. If it must be plumbed from a producer layer, that producer layer is part of the footprint. Tell: spec describes a display/consume change but names no producer file.

**Step 2c — Build parallel batches:** Group items into execution waves:
- **Wave 1:** All items with no dependencies and no file overlap with each other. These dispatch simultaneously.
- **Wave 2:** Items that depend on Wave 1 completions, or items whose footprints overlap with Wave 1 items. Again, no file overlap *within* the wave.
- Continue until all items are assigned to a wave.

If every item overlaps with every other item (e.g., they all touch the same config file), the result is N waves of 1 — purely sequential. That's fine; the analysis cost is trivial and the answer is honest.

**Step 2d — Identify risks:**
- **Sequential chains** where one item's output feeds the next (forced ordering)
- **Risk items** that might block the run if they fail (sequence these early)
- **Shared-file bottlenecks** — files that force serialization across many items (note these; they're candidates for splitting the item's spec to isolate the shared-file edit)

**Step 2e — Multi-plan convergence (when the input is N plans, not N items).** Steps 2a-2d sequence a flat item list. When the readiness gate instead clears N whole plans/batons converging on shared surfaces, run this branch before dispatch. It is Phase-2 prep work — EM/Opus judgment, including a reviewer dispatch to adjudicate a duplicate mechanism, is in-bounds here; autonomy still begins at Phase 5, not before.

- **Write-claimant table.** Enumerate every file with more than one *writing* claimant across the plans.
- **One owner per contended file**, with an explicit ordering rule wherever two plans must both touch it. Reproduce the shape of the nine-baton conductor's hot-file table — one row per file: file | claimants | owner/rule.
- **Detect duplicate mechanism** — two plans independently designing the same thing. This is the failure that motivates this branch. Resolution is adjudication (a single canonical spec both plans then consume), never letting both build it.
- **Shared citations are not shared writes.** A naive grep over-reports contention; only actual write-targets serialize.
- **Partition by surface family into phases**, each ending at a gate and a commit boundary. A 2e phase is realized as one or more Phase-5 waves; the wave, not the phase, is the actual commit boundary.
- **Output a conductor document** at `docs/plans/<date>-<slug>.md` with `type: conductor` frontmatter and a `governs:` list of the plans/handoffs it sequences. It is a sequencing layer, not another plan — the governed plans remain the authoritative chunk bodies, and a picking-up session reads the conductor instead of all N plans.
- **DAG/hot-file execution mechanics (Phase 5 consumes these inputs):** model the full cross-plan DAG as memoized per-node promises — each node awaits its deps, then dispatches, and every chunk fires the instant its true deps clear rather than serializing behind artificial wave boundaries. Two structural rules keep this collision-free without worktrees: **one executor per HOT file** (a file touched by multiple chunks gets a single executor doing ALL its edits, sequenced after that file's latest dep), and **split a chunk by file-owner** when a shared-file edit would otherwise force a dependency cycle.

**No worktrees. Ever.** Worktree creation, branch management, and merge conflict resolution cost more time than they save at agent execution speed. The file-disjoint constraint is the coordination mechanism — if it's upheld, parallel executors on the same worktree cannot conflict. If an item can't be made file-disjoint, it runs in a later wave.

### Phase 3: Flight Recorder — Compaction-Proof State

**This is the critical step.** Build a task list (TaskCreate) that persists through context compaction and allows the run to continue without re-reading everything. See `commands/mise-en-place.md` for the TaskCreate-availability fallback (same run, already covered).

Create tasks with this structure:

1. **Goal task** — titled with the full scope of the run, including:
   - What items are being executed (full list with identifiers)
   - That this is a mise-en-place straight shot
   - The tail mode: standard (EM-serial per-wave commits + push only) or hibernate (verify push, then hibernate)

2. **Per-item tasks** — one for each work item, with:
   - Item identifier and file path to spec
   - Key details from the spec (enough to execute without re-reading if compacted)
   - **Wave assignment** and **file footprint** (from Phase 2 — which wave, which files this item touches)
   - Verification criteria
   - **Tried and abandoned:** (initially empty — update during execution via `TaskUpdate` metadata field `tried_and_abandoned`. Format: "Tried: [approach] — Failed: [reason]". One line per attempt. Persists through compaction and prevents post-compaction repetition.)
   - Status: `pending`

3. **Tail tasks** (based on mode):
   - **Standard:** (no tail task — wave gates already commit + push, once per wave, EM-serial)
   - **Hibernate:** "Verify all pushes succeeded" — `pending`, then "Hibernate PC" — `pending`

**The flight recorder must contain enough context to resume cold.** After compaction, you may have lost the conversation but the task list survives. Write it like a handoff to a stranger. This is not only compaction insurance — it is the CONTINUANCE terminal's substrate (§ Phase 6): if the run stops at context pressure with backlog remaining, the successor's handoff resumes from exactly this record, so "resume cold" and "resume after a continuance handoff" are the same read.

**Anti-amnesia rule:** If you abandon an approach during execution, update the task's `metadata.tried_and_abandoned` field via TaskUpdate to include what you tried and why it failed BEFORE trying something new. After compaction, always read task metadata and descriptions (TaskGet) for "Tried and abandoned" notes before starting work — do not retry approaches that are recorded as failed.

### Phase 4: Confirm and Fire

Present the plan to the PM:

```
## Mise-en-Place — Ready to Fire

**Items queued:** [N items]
[Numbered list with identifiers and one-line descriptions]

**Sequence:** [any dependency notes]
**Tail:** EM-serial per-wave commits + push only — work stays on branch. PM runs `/update-docs` separately when ready.
[or: verify push + hibernate — overnight run, work stays on branch.]

**Estimated scope:** [rough sense of the run — "3 small items + 1 medium" etc.]

Ready to execute the full sequence. Proceeding.
```

The tail line is the EM's confirmation of mode — stated declaratively, not as a question. If the PM didn't specify hibernate, default to standard and move on.

This is a launch announcement, not a proposal. Output it and immediately begin Phase 5. Do NOT wait for a response — the PM may already be away from the terminal.

### Phase 5: Execute — The Straight Shot

**Default execution vehicle: ONE background Workflow for the whole run.** It carries the Phase-2e cross-plan DAG across every wave — executors, verifiers, and the per-wave commit phase alike — not one Workflow per wave and never a hand-typed sequence of dispatch calls. Every `agent()` call passes `model: 'sonnet'` explicitly; width ceiling ≤5 write-capable executors per barrier; a `/handoff` may still be elected at a wave boundary.

**Do not hand-author the script — mint the spine and let the emitter write it.** A mise run has no plan spine, which is why this path exists: `python coordinator/bin/emit-dispatch-workflow.py --inventory state/mise-inventory/<run-id>.md` mints a schema-valid spine beside the record (item-id → chunk-id, footprint → `writes`, no `deliverable_id`) and emits from it, so the emitter derives the wave shape, the per-wave commit pathspecs and the terminal test phase. Fire the emitted path with `Workflow({scriptPath: ...})` in this session; `--fire` is the headless/cron route and spawns a detached child. Hand-authoring instead costs roughly 4x (`A-HAND-AUTHORED-WORKFLOW-COSTS-4X-THE-PLAN-EXECUTION`). The minted spine is derived, not authored: the next mint overwrites it, so a coordination fact belongs in the inventory record. **Minting refuses rather than guesses** — a row whose disposition is neither live nor in § Phase 6's closed set, and a live row whose Footprint cell names no backticked repo-relative path, both stop the mint naming the row. Fix the record; do not work around it.

**Why the vehicle is not a preference: hand-dispatch spends the one resource a mise run cannot replace.** Every `Agent` call the EM issues puts the brief, the completion notification, and the follow-up reasoning through the EM's own context. A mise run is *defined* by having more backlog than context — so the orchestration method that burns context fastest is the one that must not be reachable by default. A six-item run hand-dispatched eight times — four executors, four verifiers — costs ~430k subagent tokens with every brief and every completion landing in the EM's window; the Workflow path keeps all of it out. **There is no single-wave carve-out.** A one-wave run is precisely the case where a Workflow is cheapest to author, and "only one wave" is not a shape a Workflow cannot express — the only carve-out this doctrine recognizes (`docs/wiki/workflow-orchestration.md` § What qualifies as a carve-out). A default that degrades to discretion under load is not a default, and the EM is under load at exactly the moment Phase 5 opens.

**Verifiers ride inside the Workflow.** A Workflow-internal `agent()` reaches `report_type_map` through `provision-sidecar` (`coordinator_core.subagent_sandbox.engine.load_policy` — the second consumer named in `coordinator/subagent-sandbox-policy.yaml`'s header), so a typed sidecar is available on the Workflow path where no `Agent`-tool hook fires. The script calls `provision-sidecar --agent-type <type>` for any phase whose `report_type_map` row is not `run-report`. Verifying per item outside the Workflow is what halves the context saving, and it is not forced by the mechanism.

**Wave semantics are unchanged; only the vehicle is.** The wave gate, the footprint constraint, the DONE-summary contract and the Haiku-verifier protocol below are the semantics each Workflow phase implements — read them as the phase spec, not as a description of the EM typing dispatch calls.

**Signal autonomous mode:** Before executing the first item, write the autonomous-run sentinel so the context pressure hook knows not to nudge `/handoff`. The CLI below resolves the session id itself (same resolver the consumer hook uses) and refuses to write an empty-suffix sentinel:
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/misc-session-and-guards" autonomous-sentinel enable --mode mise-en-place
```
This tells the hook to emit informational-only context pressure messages (no handoff recommendation). The sentinel is cleaned up in Phase 6 via the same CLI's `disable` action.

**The `--mode` field is load-bearing semantics, not a label.** The sentinel's content distinguishes a `/mise` run's sentinel from an `/autonomous` run's sentinel for any reader that inspects content — today's readers check only presence, but the mode field is what makes that content-sensitive reading possible. `/mise` and `/autonomous` are genuinely decoupled AT THE POSTURE LAYER: under `mode: mise-en-place`, the run's posture is hand-off-at-pressure (the CONTINUANCE terminal, § Phase 6 below); under `mode: autonomous`, it is ride-compaction. `/autonomous` + `/mise` composes when the PM invokes both explicitly — neither command implies the other.

**Execute wave by wave.** Each wave from Phase 2 is a batch of file-disjoint items:

**Bandwidth rule:** /mise backgrounds executors by default — single-item waves included. The EM steers many items; pulling each executor's transcript into context burns the window before the run finishes. Executors do their own verification but NEVER commit — git is the wave's dedicated commit phase alone (§ Phase 5, step 3). Verifiers (Haiku) check the result against the still-uncommitted working tree; once every item in a wave has a PASS verdict, that phase commits the wave's whole changed-path set in a single scoped commit. The EM reads only one-screen DONE summaries and PASS/FAIL verdicts from disk.

**For each wave:**

1. **Dispatch all items in the wave concurrently.** For each item:
   - Mark `in_progress` via TaskUpdate. Update plan document status if applicable.
   - Dispatch to a Sonnet executor agent with `run_in_background: true` and `mode: "auto"`. The prompt must include the full spec (or path to it), the item's file footprint from Phase 2, the footprint constraint, the self-verify constraint (verification is the executor's job — it never invokes git), and the DONE-summary constraint. See the command file for verbatim wording.
   - Items that benefit from accumulated coordinator context (coherence decisions, cross-file awareness) stay in-coordinator and execute sequentially within the wave — rare exception, not default.

2. **Process completions via Haiku verifiers.** As each background executor reports DONE:
   - **Idle without DONE is not a completion or stall signal — it's uninformative.** Check DISK first (`tasks/mise-done/<item-id>.md`, `git log`, `git status`); if inconclusive, `SendMessage` a status ping rather than re-dispatching. **NEVER spawn a second agent onto a live agent's footprint — hard rule**, it breaks the file-disjointness invariant the wave model depends on.
   - Read only the DONE summary file. Do NOT pull the executor's transcript into context.
   - Dispatch a Haiku verifier with `run_in_background: true` to read the DONE summary + spec + the item's still-uncommitted working-tree diff (there is no commit to inspect — the executor never commits) and write a verdict at `tasks/mise-verify/<item-id>.md` ending with `STATUS: PASS` (or `FOOTPRINT-VIOLATION` | `AC-MISS` | `VERIFICATION-CMD-FAILED` | `NEEDS-EM`). Verifiers are wave-scoped — batch them and gate the wave on all PASS.
   - On any non-PASS verdict, the EM decides re-dispatch / revert / defer / early-stop from the verdict + diff alone.
   - Mark complete via TaskUpdate on PASS.

3. **Wave gate:** ALL items in a wave must complete before the next wave begins. This is the serialization point that guarantees later-wave items see earlier-wave changes. Once every item has a PASS verdict, the wave's whole changed-path set commits in a single scoped commit, never `git add -A`. The post-commit hook pushes automatically. This is the only commit point in Phase 5.

   **The commit is a phase inside the Workflow, not an EM step between Workflows** — that is what lets one Workflow span the whole run. It dispatches `coordinator:git-commit-agent` against the wave's recomputed pathspec, committing through **`ceremony.commit_v2`** — that and a plain scoped `git commit -m ... -- <paths>` are the whole of `block_subagent_commit`'s allow surface, which reads literal top-level argv. Do not reach for `ceremony.scoped_git_commit`: the op is deleted, and killed names live on in the guard's own prose long after the file is gone. Because neither live route re-asserts the branch the way the EM-side wave-commit op does, **the commit phase's prompt names the expected branch and requires the agent to verify it read-only before committing** — a peer flipping the branch mid-run is not theoretical on this tree. **Do not add a ledger call to the commit phase** — `ceremony.commit_v2` writes the commit-ledger row itself, so a per-caller call is a duplicate row, not a gap being filled.

   **The mise directive set is bookkeeping, not a commit, and stays with the EM outside the Workflow:** `backlog-grind-assemble apply mise-en-place --run-id <id>` with **no** `--wave-path` runs the directives and builds no commit directive. Do not reach for the `--wave-path` form from inside a Workflow, and do not ask for the commit guard to admit `apply` as an argv shape — top-level argv cannot distinguish a committing run from a bookkeeping one, which is why that widening is refused.

4. **Brief status update between waves:** "Wave N complete ([items]). Firing wave N+1 ([items])." Output-only — do NOT frame as a question, do NOT wait for a response.

**Single-item waves** (forced sequential due to file overlap or dependencies) still background per the bandwidth rule above — dispatch overhead is the accepted cost, not a reason to inline. Follow the same write-ahead → execute → verify → EM-commit → mark-complete cycle — the EM still does the commit, even for a wave of one.

**Dispatch model:** Enriched specs with code sketches are blueprints — Sonnet follows them; Opus judgment was already spent during enrichment+review. Default is always Sonnet; dispatched executors are never Opus, even for a very large stub with natural seams (that case gets a dedicated Opus tech-lead agent coordinating Sonnet executors, not an Opus executor). The coordinator's job during execution is verification and wave gating, not typing code.

### Phase 6: Tail — Close Out the Run

**Backlog-exhaustion check (run FIRST, before anything else in this phase).** Running this tail is CLOSURE, not COMPLETION — nothing above proves the Phase-1 backlog is exhausted. The check reads the C1a disposition ledger in the Phase-1 inventory record (`state/mise-inventory/<run-id>.md`, § Phase 1 above) — a mechanical read, never EM recollection — and resolves to exactly one of two named terminals:

- **`COMPLETE`** — every item in the ledger carries a CLOSED disposition: executed-and-PASSed, explicitly routed out at Phase 0, dropped as `already-fixed` at Pre-Dispatch Verification, put back down at Phase 0a, or routed out mid-run with a named reason. (Items routed out at Phase 0 run *before* Phase 1 inventory, so they're absent from the Phase-1 table by construction — the denominator is "Phase-1 inventory plus Phase-0a batons put back down", not the Phase-1 inventory alone.)
- **`CONTINUANCE`** — any item's disposition is non-terminal (still `pending`/`in_progress` in the ledger). Non-failure, and for a large run the EXPECTED ending — not an apology, not an error.

**The check SELECTS a terminal; it does not GATE the tail.** Both terminals run the identical tail below (sentinel cleanup, anti-vacuity gate, diff freeze, verification pass, tracker sweep, baton disposition, routing to the capping ceremony) — a run that stops mid-backlog still needs the full tail, or its diff is left on the branch with nothing routing it to review. The difference is terminal wording plus, for `CONTINUANCE`, one extra artifact (below).

**Complete-word guard — canonical sentence:** "The run-level verdict line MUST read exactly COMPLETE or CONTINUANCE; the word 'complete' may not appear as the run's disposition unless the exhaustion check passed. Item-level, wave-level and task-level uses of 'completed' (TaskUpdate, tracker sweep, baton disposition) are unaffected." Mark all item tasks `completed` via TaskUpdate as usual — that per-item use of the word is untouched by this guard; only the run-level verdict line is constrained.

**`CONTINUANCE` requires a handoff** naming three things, because re-derivation cost is what a mid-backlog stop otherwise burns: (1) the exact invocation to resume with; (2) a Phase-0-bypass assertion for the remaining items (they already passed the readiness gate — the successor must not re-run it); (3) the pre-computed wave map for the remaining items, so the successor doesn't re-derive Phases 0-2. Author it via `/handoff` at the terminal — this is the EM electing a PM-gated continuity artifact at a sanctioned decision point, not a plan-authored one. **In hibernate mode, author and commit the handoff BEFORE `shutdown /h`** — otherwise the successor artifact dies with the session. Hibernate-on-early-stop (§ Safety Boundaries below) governs WHETHER the machine hibernates; the exhaustion check governs WHAT TERMINAL WORDING the tail summary uses before it does — an early stop under hibernate mode still runs the exhaustion check, still elects `CONTINUANCE` if the backlog isn't exhausted, authors+commits the handoff, THEN hibernates.

**Inventory-record archival — the run that wrote the record closes it.** Nothing else prunes `state/mise-inventory/`, so absent this step it accumulates one record per run forever, and every downstream reader that has to answer "which record is the current run's" is left guessing among N. On a `COMPLETE` terminal, close this run's record the way every structured queue in this repo closes — `git mv state/mise-inventory/<run-id>.md archive/mise-inventory/<YYYY-MM>/`, staged into the tail commit, never a delete and never an inline status edit. **The minted spine and its emitted script archive with it** — `<run-id>.spine.md` and the `.workflow.mjs`/receipt beside it are this run's derived artifacts and have no reader once it closes. **A `CONTINUANCE` record stays in place**: it is exactly what the successor handoff above points at, and the successor archives it when its own terminal resolves `COMPLETE`.

That leaves one residue this step cannot reach — a run that died before its tail, whose record no session will ever close. **Phase 1 sweeps those**: before writing this run's record, archive by the same `git mv` every record in `state/mise-inventory/` that is neither this run's nor named by an open handoff. A record whose only claimant is an ended session is history, not state.

After the exhaustion check resolves, mark all item tasks as `completed` via TaskUpdate, clean up the autonomous-run sentinel via:
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/misc-session-and-guards" autonomous-sentinel disable
```
then freeze the run's diff and route review to the capping ceremony (see below), then execute the tail action based on mode, closing with the resolved `COMPLETE` or `CONTINUANCE` verdict line.

**Review is owed to the capping ceremony, and `/mise` does not run one.**

`/mise` has no review gate of its own. `/workstream-complete` owns review: it picks the scale from diff shape and runs it over the **chain diff** — this run's work plus its ancestry, a range that strictly contains this run's own. Reviewing here as well means reviewing a subset, at a scale chosen by the narrower ceremony, and gating the run on it.

The field evidence that used to justify a Phase-6 review argues the other way once read closely (2026-08-04): a run-scoped review over a 5027-LOC diff returned **zero** findings, while the chain-scoped partitioned review over the same work plus its ancestry returned **eight**, across three of four slices. The run-scoped pass was not a weaker version of the right review — it was looking at a different, smaller thing, and it was the one that found nothing.

What `/mise` owes instead is the **routing obligation**: a run does not end with its diff unreviewed by anyone. The tail routes to a ceremony that reviews — `/workstream-complete` to cap, or `/handoff` naming review-and-cap as the successor's remit — and names which in the tail summary. "The PM will run it later" is not a discharge.

Per-item Haiku verifiers cover footprint + AC compliance only. They are not a review pass; they are why deferring review to the capping ceremony does not mean shipping unexamined work in the interim.

Freeze the run's diff before routing, so the capping ceremony inherits a materialized artifact instead of re-deriving a range across a shared branch: `<claude-klabauter-bin>/freeze-review-diff.py --range "<start_sha>..HEAD" --slice-id "mise-<run-id>"` (resolve `<claude-klabauter-bin>` via the `resolve-claude-klabauter-bin` snippet). Take `<start_sha>` from the inventory record's frontmatter (§ Phase 1).

**A guard refusal is never answered by narrowing.** On a shared `work/*` branch the foreign-session guard will refuse a trail record spanning peer commits. Slice instead — `--paths` scoped to the run's own footprint, plus per-slice records over the run's own commits (`<sha>~1..<sha>` — `~1`, never `^`: cmd.exe eats a literal `^` in argv on Windows) — never shrink the range to whatever the guard accepts. Where a slice legitimately excludes ceremony bookkeeping (review-trail JSON, subagent sidecars, memo/handoff frontmatter), state the exclusion and its LOC in the tail summary: a silent narrowing reads as coverage.


**Baton disposition (whenever Phase 0a ran):** a claim is an obligation, so no baton this run claimed is left claimed by an ended session. Batons this run claimed and completed are concluded through `/workstream-complete`; **there is no manual terminal-flip verb, and `pickup-assemble apply` is not one** — every verb it can reach is claim-side, so running it on a finished baton re-claims it instead of closing it, silently deepening the strand it was meant to clear. `pickup-assemble drop <path>` anything unstarted. Archiving is the boot sweep's job. State each disposition in the tail summary.

**A third disposition covers the overlap between per-baton claiming and per-item routing: carried with routed residue.** A baton whose remaining items after Phase 0 routing are still a coherent run keeps its claim — it is neither dropped (whole baton, claim released) nor terminal-flipped (whole baton, work done); the routed items are that baton's unfinished business. Two obligations follow: the routed items appear in the § Phase 1 disposition ledger as `routed out mid-run` with a named reason (the same entry the exhaustion check reads), and they are named per baton in the run's single successor handoff — the tail summary's prose does not survive the session.

**Succession is N→1, and this is the only place it is written down.** However many mid-stream batons the run holds, `/handoff` authors **one** successor — the same single handoff § Phase 6's `CONTINUANCE` terminal calls for, not one per baton. Do not read the per-baton framing of the dispositions above as licensing a successor apiece: Phase 0a's "N batons is N independent dispositions" governs *claiming*, and convergence into one wave map at Phase 2e is what a single successor then resumes.

This is a ratified engine property, not a recipe convenience — `resolve_lineage` returns a single `output_path`, so N→1 fan-in is the only cardinality it can express, and fan-out was considered and **retired** by engine ruling (claude-klabauter, `state/roadmap/sedge-2026-08-06/COORDINATOR-RESOLUTIONS.md` § Resolution 1). The reasoning binds the sentence: the baton is the unit of **work-continuity**, one per session, and deliverable close-out lives in an off-artifact ledger rather than on the succession edge. Deliverable survival is therefore guaranteed by that ledger, never by successor multiplicity — which is why one successor is correct rather than merely tolerable.

> **What batons 2..N get.** The engine narrates the drop rather than hiding it: on a fan-in,
> `brief()` raises the `j-fan-in-cardinality` judgment point naming every predecessor and which
> one's `deliverable_id` survives, and the successor carries the fan-in set as a
> `additional_predecessors:` down-edge (written unconditionally, matching the `continued_into`
> up-edges stamped on each predecessor), so every dropped leg stays reachable from both ends.
> What the successor does NOT carry is the non-primary `deliverable_id`s — those survive in the
> off-artifact deliverable ledger, never on the succession edge. **The tail summary must still
> name the non-primary batons explicitly**, because the successor's filename and `deliverable_id`
> derive from the primary alone and the summary is where an operator reads the run's own account
> of them.


**Standard (default):**
1. Report the run-level verdict resolved by the backlog-exhaustion check above — COMPLETE or CONTINUANCE, per the canonical sentence — never a bare "done" standing in for it. Per-wave commits already pushed. The PM runs `/update-docs` (and later `/workday-complete` or `/merge-to-main`) separately when ready to integrate. Rationale: `/update-docs` now absorbs the tracker-maintenance, handoff-archival, and atlas-integrity-check subroutines inline, making it a heavier operation than it was when /mise tailed it automatically. PM-gated invocation is the right shape.

**Hibernate:**
1. Verify push — resolve the current branch via the settings-home `coordinator-current-branch` forwarder (never a hand-rolled claude-klabauter-root resolution ladder), then check the branch is fully pushed:

   `git log "origin/$("${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-current-branch")..HEAD" 2>/dev/null`

   Output should be empty for all session work.
2. If unpushed commits remain, push explicitly. If push fails, do NOT hibernate — stop and report.
3. Hibernate the machine (platform-specific — run only the one matching this machine, never both):

```bash
shutdown /h   # Windows
```

On Linux/Mac, the equivalent is a different command entirely — there is no cross-platform hibernate invocation:

```bash
systemctl hibernate   # Linux/Mac
```

Hibernate over shutdown: same zero power draw, but the machine resumes to its prior state instead of cold-booting. Lower blast radius if something needs attention.

## When to Stop the Run

Apply the same judgment as `/execute-plan`:

**Stop and report when:**
- An item's spec is ambiguous enough that continuing means guessing at multiple points
- Verification fails structurally (not a fixable error, but an approach problem)
- An item's scope is significantly larger than the spec suggested
- A breaking change invalidates assumptions in remaining items
- 2+ items have accumulated workarounds suggesting the approach is off

**Do NOT stop for:**
- Routine fixable errors — fix and continue
- Minor ambiguity resolvable with one judgment call — make the call, note it
- A single item being harder than expected — push through
- Wanting to "check in" — the PM authorized the full run

**Non-failure early stop:**
- **Context exhaustion with backlog remaining.** Every row above is a failure; this one is not — its whole purpose is to give the benign, expected stop a sanctioned shape. Do not route it through the failure-framed steps below. Instead: run the full Phase 6 tail (§ Phase 6 above — anti-vacuity gate, diff freeze, end-of-run verification, tracker sweep, baton disposition, routing to the capping ceremony), let the backlog-exhaustion check resolve CONTINUANCE, and author the handoff CONTINUANCE requires. This is the sanctioned move for the large-run case, not the exception.

**If you must stop:**
1. Commit all current work — even partial progress — via the named wave-commit op (§ Phase 5, wave gate), scoped to the flight recorder's working set with one `--wave-path` per path. Never `git add -A`/`.`/`commit -a`: on a shared branch that sweeps another session's uncommitted files into this run's commit.
2. Update tasks via TaskUpdate with where you stopped and why, including which items remain.
3. Update any plan documents with current status.
4. Push is automatic via post-commit hook, but verify the branch is on remote.
5. **If hibernate mode was invoked:** Presume the PM is away. Hibernate the machine. The PM will see the incomplete run on the branch when they wake up. Incomplete work on a branch is safe — it's not on main, colleagues aren't affected, and it's better than leaving a power-hungry PC running overnight waiting for input that won't come.
6. **If standard mode:** Just stop. The PM will see the state in the task list and on the branch.

This failure-framed path is distinct from context exhaustion above: a genuine failure stops short of the tail, while context exhaustion still runs the full tail and resolves CONTINUANCE.

## Safety Boundaries

- **Never merge to main from mise-en-place.** Work stays on branch. The PM merges interactively after review.
- **Never use worktrees.** All executors operate on the same worktree. File-disjoint wave scheduling is the coordination mechanism. Worktree creation + merge overhead exceeds the time saved at agent execution speed.
- **Never hibernate without explicit PM request.** Hibernate mode is opt-in only.
- **Never escalate tail mode without PM request.** Standard → hibernate escalation is PM's call. Don't ask, don't suggest.
- **Hibernate is always safe on early stop.** If hibernate mode was invoked and the run must stop early, hibernate anyway. Incomplete work on a branch + hibernated machine is strictly better than incomplete work + machine running all night.
- **Commit after every wave.** Crash insurance. Executors never commit — a dispatched item's work is not done until the EM has committed it as part of its wave's single EM-serial commit (§ Phase 5, wave gate).
- **Write-ahead status on everything.** If the session dies, the plan shows exactly where execution stopped.
- **Push is automatic** via post-commit hook — crash insurance is always active. Verify remote state before hibernate.

## Integration

**Required workflow skills:**
- **`/execute-plan`** — Pattern for executing individual plan items
- Evidence before claims on each item — no verification claim without the mechanical check that backs it (see Phase 5 Haiku-verifier protocol above)
- **`/update-docs`** — NO LONGER auto-invoked. PM runs separately after `/mise` completes.

**Optional workflow skills:**
- Parallel dispatch patterns (file-disjoint constraint, same-worktree — see Phase 2 above)

**Called by:** PM directly — whether they're watching, stepping away, or wrapping up for the day

**Pairs with:**
- **coordinator:plan** — Creates the scoped items this skill executes
- **`/workstream-start`** — Often follows workstream-start when the PM reviews the backlog and decides to straight-shot it
