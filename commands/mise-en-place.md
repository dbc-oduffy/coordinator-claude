---
name: mise-en-place
description: "Autonomous backlog run — flight-recorder prep, then run-through."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[baton-path [AND baton-path]...] [--hibernate]"
---

# Mise-en-Place — Autonomous Backlog Execution

Everything in its place before the fire gets lit. Front-load context and sequencing into a compaction-proof flight recorder, then execute the full backlog in a straight shot without stopping. PM authorization is implicit in invocation — that includes the messy parts (rate-limits, crashed agents, uncommitted executor output, recovery re-dispatches, concurrent-session staging conflicts). Once Phase 5 begins, the EM never pauses to ask, offer a choice, or wait for a response; the only legitimate stops are genuine product/scope questions only the PM can answer, or the structural-failure cases under "When to Stop." Asking whether to finish already-authorized work is a failure of the role; stalling mid-run prevents the hibernate tail from triggering.

**Announce at start:** "Running /mise-en-place — prepping flight recorder, then straight shot through the backlog."

**What mise IS NOT:** Not "plan-as-you-go autonomy." Not a license to live-assemble specs or research a downstream contract mid-run — that's session-EM territory, needing judgment, reviewer dispatch, and PM alignment. A gated, once-built foundation wave (readiness criterion 2) is legal; a wave whose output is still an *undecided* decision is not, and running one means you're not ready for mise — you're ready for a planning session. Mise optimizes for first-pass correctness: deep planning BEFORE the run, executors only type.

## Arguments

Parse `$ARGUMENTS` for the tail mode:

| Trigger | Mode | Tail action |
|---------|------|-------------|
| No arguments, or no explicit hibernate phrase | **Standard** (default) | EM-serial per-wave commits + push only (no /update-docs) |
| `--hibernate` flag, or unambiguous phrases: "hibernate", "shut down", "power off" | **Hibernate** | verify push, then hibernate PC (no /update-docs) |

**Default to standard.** Hibernate requires unmistakable explicit consent — the `--hibernate` flag or one of the phrases above. Soft signals like "overnight", "it's late", "go to bed", or "shutdown when done" do NOT authorize hibernate; treat as standard and let the PM invoke `/workday-complete` separately. Do not ask — when in doubt, run standard.

## Instructions

Follow all phases in order. The pipeline definition at `pipelines/mise-en-place/PIPELINE.md` is the authoritative source. This command codifies its orchestration.

### Phase 0a: Baton Intake — Claim What You Were Handed

Artifact paths on the invocation line are batons, and **handing batons to /mise is a grab, so it claims** — the claim is the only thing stopping a concurrent session from running the same handoff mid-flight.

**The claims already fired before you read this.** The `/pickup` auto-fire covers this surface too: baton paths are extracted from the argument line (flags, item identifiers, and plan paths filtered out — a plan is inventory, not a baton), briefed, and claimed wherever the coast was clear. Their decision objects are already in your context. Don't re-derive them, and never hand-edit the claim fields.

Residual judgment, all of it `/pickup`'s ordinary shape: resolve any open judgment points and claim those batons (`pickup-assemble apply <path>`) before Phase 5's no-stopping rule starts; reconcile each baton's pending list against reality; treat contention per baton, never as a verdict on the grab.

**A claimed baton you then judge un-mise-ready gets put back down, not carried.** `pickup-assemble drop <path>` returns it to open and ready-to-fire — the same inverse `/pickup` uses. That is the exit for a baton where the readiness gate (§ Phase 0) routes out enough of the body that what remains isn't a coherent run on its own. If no brief text arrived at all, the intake didn't happen — run `pickup-assemble brief <path> [AND <path>]...` before going further.

**Claim is per-baton; Phase 0's readiness gate routes per-item — a third disposition covers the overlap.** A baton whose remaining items after routing are still a coherent run is **carried with routed residue**, not dropped: keep the claim, run the coherent subset, and name the routed items with their reasons. This is distinct from `drop` (whole baton, claim released) and from a full terminal-flip (whole baton, work completed) — the claim stays live and the routed items are this baton's unfinished business, not a separate abandonment. Two obligations follow, not optional polish: (1) the routed items appear in § Phase 1's inventory record disposition column as `routed out mid-run` with a named reason, the same ledger entry Phase 6's exhaustion check already reads; (2) the routed items are named explicitly in the successor `/handoff` this baton's disposition requires (§ Phase 6 "Baton disposition") — the tail summary's prose is not sufficient on its own, since nobody reads it once the session ends.

Announce before the readiness gate: "Claimed N batons: [paths]. [M put back down: reason.]"

### Phase 0: Readiness Gate — Reject the Run if Items Aren't Mise-Grade

**Bypass condition.** If the session was opened from a handoff (or the PM's invocation explicitly references one) and that handoff states the queued items have already been gated as mise-ready, **skip Phase 0 entirely** and proceed to Phase 1. The bypass is valid when the handoff names the items in scope and asserts **executability** in unambiguous terms — that a Sonnet executor can finish the item from the spec now (e.g., "items A, B, C are mise-grade — proceed straight to dispatch", "Phase 0 verified", "ready for /mise"). That is a different predicate from `pickup_ready` / a handoff merely asserting it can be usefully picked up — a handoff can be honestly pickup-ready while its own body states the item cannot yet execute (a shut gate, a package not yet on disk). Read the body, not just the frontmatter: if the handoff's own prose contains a stop condition on execution ("cannot execute yet," "gate is shut," an unmet precondition), that controls over any readiness-sounding frontmatter field, and the bypass does not apply. **`deployment_state: awaiting_gate` is a hard bypass-disqualifier** regardless of what any other field or sentence asserts. Re-running the gate after a verified handoff is wasted context — large backlogs can blow the EM's window on stub reading alone, which is the exact failure mode the bypass exists to prevent. If the bypass applies, announce it explicitly: "Phase 0 bypassed — handoff at <path> verified mise-readiness for [items]. Proceeding to Phase 1." If you are uncertain whether the handoff covers all queued items, or whether its assertion is about executability rather than pickup-readiness, do NOT bypass — run the full gate.

**Otherwise, run this gate before Phase 1 inventory and before announcing the run.** Apply the gate per item. A failing item routes out of the run (§ below) rather than blocking the whole run — reserve an outright decline for when the routed residue isn't a coherent run on its own, or when routing an item would itself require a PM decision.

A mise-grade item meets ALL of the following:

1. **The decisions are made.** No open PM-level or architectural fork remains inside the item — acceptance criteria are explicit and verifiable. A Sonnet executor is expected to resolve local implementation detail (naming, ordering, mechanics) from a bounded spec; what disqualifies an item is an undecided *decision*, not an unwritten *line*. A PM-authorized plan clears this bar on its own for its unforked content — an enricher pass is no longer a precondition. **A stamp does not clear a named open decision inside the stamped plan wholesale.** It clears one only when that open decision is itself decided-how-to-decide: (a) an owning chunk is named to settle it, (b) the settling criteria are stated, and (c) the plan records an obligation to write the rationale down when settled. All three present is a bounded spec, not an undecided fork, and the item clears criterion 1 despite the open point. Any one absent — an unowned fork inside a stamped plan — still disqualifies; the stamp is not a blanket exemption.
2. **Downstream contracts are sequenced, not absent.** A foundation wave is legal, provided it is (a) built exactly once — no two items independently building the same mechanism, (b) sequenced first, and (c) closed by an explicit live gate before consumers fire (the nine-baton conductor's W0/W0.4 is the reference: the seam was built once, and the gate was a live smoke proving the mechanism reached a real consumer, not merely that files existed). What still disqualifies: a foundation artifact whose *content* is itself an undecided decision — research output, or "a wiki page that tells later waves what to build" where the what is not yet settled. The discriminator: **decided-but-unbuilt is legal; undecided is not.**
3. **Pure-executor agent type.** A single Sonnet executor (or coordinator-inline executor) can complete it given the spec. Items requiring live-editor MCP authoring, enricher judgment, reviewer judgment, or staff-session synthesis are not executor work — they belong in their dedicated commands.
4. **File footprint declarable and data-reachable.** You can name the files the executor will write before dispatching, AND the data the change needs is confirmed available at the layer being changed. If the spec says "discover what needs changing," that is investigation, not execution.
5. **Verification is mechanical.** "Tests pass," "function exists with this signature," "file matches this acceptance criterion" — not "the Game Dev Reviewer agrees this looks right."

**Disqualifying patterns (route the item out of the run if it exhibits these):**

- A foundation item whose output is itself an undecided decision — research stubs, brainstorming stubs, or a reference doc whose content isn't yet settled. A once-built, gated foundation (criterion 2) is NOT this pattern — don't conflate the two.
- Mixed agent types in the planned waves — enricher + executor + MCP-author in the same run signals the work isn't ready.
- Items carrying an open PM-level or architectural fork — marked `Pending Review`, `Needs the Staff Engineer`, or with reviewer findings not yet resolved into a decision.
- Vague, unverifiable acceptance criteria ("improves the system," "addresses the concern") rather than checkable ones.
- Items requiring `manage_*` MCP tools in a live editor session — those need an interactive EM-driven flow.

**If the gate finds disqualifying items: route, don't refuse the whole run.** A failing item is either (a) decided-but-unbuilt → assign it to a gated foundation phase, or (b) carrying an undecided fork → route out of scope with a named reason. The run proceeds on the remainder. Report the routing, not a refusal. Example:

```
## Mise-en-Place — Readiness Routing

- 2A-1 (open reviewer findings, undecided fork) — routed out of scope.
  → Route through /enrich-and-review, then /review (plans) or /review-code (code) before /mise.
- 3B-1 (research stub, output is itself the undecided decision) — routed out of scope.
  → Run as a planning task; mise the consumers afterward.
- 3A-9 (MCP-authoring stub, requires live UE editor) — not executor work, routed out of scope.
  → Dispatch interactively per `docs/wiki/delegate-execution.md` with the relevant domain agent.

Proceeding with the remaining N items. [name the foundation phase here, if any]
```

**Genuine stop condition:** if the residue after routing isn't a coherent run, or routing an item would itself require a PM decision (e.g., which of two conflicting mechanisms is canonical), surface to the PM and stop rather than routing unilaterally.

### Phase 1: Inventory — What's on the Board?

**Run the assembler brief first.** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" brief mise-en-place --run-id <run-id>` computes, read-only: (a) a judgment point — proceed anyway / stand down — when `state/bug-backlog/` and `state/debt-backlog/` both read empty of open items (`tasks/*/todo.md` plan files and a PM-named `$ARGUMENTS` list aren't queue families this covers, so an empty read is evidence toward nothing-to-run, never proof); resolve it before dispatching the scout below. (b) the `d-mise-executor-dispatch-prompt-template` directive consumed in Phase 5 step 1. It does NOT compute Phase 0's five readiness criteria — those stay EM judgment, unchanged above.

**You do not mint the run id by hand.** Typing `/mise-en-place` fires `mise-autofire.py`, which mints one through the engine's `backlog-grind-assemble mint-run-id mise-en-place` and hands it back as `additionalContext` in this same turn, alongside the brief already computed against it. **Quote that id** — at Phase 1 and again at Phase 6 — rather than inventing one by convention; identity for `state/mise-inventory/` records is the engine's to issue, not the EM's to coin. The hook is advisory and fails silently: if no minted id shows up, run `mint-run-id mise-en-place` yourself and carry on. It never creates `state/mise-inventory/` — that directory's absence is the engine's own Phase-0-vs-Phase-6 self-gate.

**`--run-id` names the run; it is not optional and it is not inferred.** The value is this run's own id — the same one that stems `state/mise-inventory/<run-id>.md` (below) — and it is what lets Phase 6's review-scale verdict read the record rather than guess which of several on disk is in flight. A missing or wrong `--run-id` yields the unresolved judgment point `j-mise-phase-6-review-scale-unresolved`; the two are not distinguishable by id, only by its evidence prose, so re-read the flag you passed rather than assuming which of the two you hit. There is no environment-variable carrier and no fallback selection — pass the flag on the same call. (The flag is portable by construction: an inline `VAR=value` prefix is unparseable by `cmd.exe`, which is why the environment was declined as the carrier.)

**Bandwidth rule:** The EM does NOT read every stub. Large backlogs (>5 items, or any run flagged "many items") will blow the EM's context window if the coordinator pulls every spec into-context. Instead, dispatch a **Sonnet inventory scout** with `run_in_background: true` and an on-disk deliverable. The EM works from the scout's structured table — identifiers, paths, footprints, dependencies — not the full stub text.

**Inventory record lives under `state/mise-inventory/`, not `tasks/`.** The record is a
CONTINUANCE input (§ Phase 6 backlog-exhaustion check reads it), and therefore load-bearing
substrate — `tasks/` is swept aggressively (project `CLAUDE.md` § state/ vs tasks/) and would
silently discard the very record a continuance handoff needs to point a successor at. Being
durable is not being permanent: before writing this run's record, archive the orphans left by
runs that died before their tail (PIPELINE.md § Phase 6, inventory-record archival).

**Capture the run's start SHA before dispatching the scout.** `git rev-parse HEAD` at the moment
Phase 1 opens, passed into the scout's brief below — the scout cannot know the run's own starting
point, and § Phase 6's computed review-scale verdict has no range without it.

**Inventory scout dispatch (default for any run with >3 items, or PM-flagged as large):**

> Read every queued item's spec and produce a structured inventory at
> `state/mise-inventory/<run-id>.md`. Open the file with frontmatter carrying `run_id: <run-id>`
> and `start_sha: <the SHA I give you in this brief>` — § Phase 6's review-scale verdict is
> computed over `<start_sha>..HEAD` and reads that field off this record.
> For each item, emit one row: identifier | spec path |
> one-line summary | declared file footprint (write targets) | dependencies (item IDs) |
> verification method | complexity (S/M/L) | **disposition**. Do NOT summarize the specs into the
> EM's context — write the table to disk and reply `DONE: <path>`. The EM will read the table
> directly, not your reply.

**Authorization basis (Phase 6's C7-cited corroborating detail).** The inventory record must also
carry the run's authorization basis — which plans or items the PM named at invocation, and when —
not just the chunk table. A run's authorization-of-record is the autonomous-run sentinel's content
(`mise-en-place` mode, § Phase 5), but an auditor reading that sentinel alone gets a bare mode
string with no elaboration; this record is the durable, human-readable trace that corroborates it.
An inventory record carrying only the chunk table makes that corroboration hollow — state the
authorization basis inline, at the top of the record, before the chunk table.

**Live per-item disposition ledger.** The inventory record's `disposition` column is not written
once by this scout and left untouched — it is UPDATED AT EACH WAVE GATE (§ Phase 5, step 3, when
the EM commits the wave) to reflect each item's current disposition. § Phase 6's
backlog-exhaustion check reads this ledger directly to determine whether the run's backlog is
exhausted; it does not reconstruct disposition from TaskList or EM memory. Each row's disposition
must be one of the closed set § Phase 6 defines — keep the column's values aligned to that set as
the run progresses.

Sources the scout should check — these are parallel, not sequential; check all four:

- **Plan files:** `tasks/*/todo.md` — items marked ready/pending execution
- **Enriched stubs:** Any chunk directories with status "Enriched" or "Reviewed"
- **PM's explicit list:** If `$ARGUMENTS` names specific items (e.g., "PX4-6B through Cesium-D"), use that as the canonical list
- **Claimed batons:** If Phase 0a ran, its claimed set is canonical and already reconciled — inventory the work *inside* those batons (their plans, spines, and next-step queues), and do not re-resolve the artifacts themselves
- **Open tasks:** Any `tasks/*/` directories with incomplete work

After the scout returns, the EM reads `state/mise-inventory/<run-id>.md` once and works from that table for Phase 2 sequencing. The full spec text stays on disk and is loaded only by the executors that consume it.

**Small runs exemption:** If there are 3 or fewer items AND the EM has already read them in this session (e.g., the PM listed them inline with brief specs), the EM may inventory inline without dispatching a scout. Default is to dispatch.

### Pre-Dispatch Verification

Before sequencing or dispatching any executors, verify that backlog items gathered in Phase 1 are still applicable to the current codebase.

For each item sourced from a backlog file (`state/bug-backlog/*.yaml`, a debt-backlog entry in `state/debt-backlog/*.yaml`, or a plan stub marked pending), dispatch a Haiku agent to confirm the issue still exists in HEAD: read the cited file:line for whether the bug/debt pattern still holds, check the file's recent commit history for signs a commit already addressed it, and return a `still-open` or `already-fixed` verdict per item.

Drop `already-fixed` items before building the execution queue — verifying first prevents dispatching executors on work that has already shipped.

### Phase 2: Sequence and Parallelize — Maximum Velocity

The goal is maximum throughput: run as many items concurrently as possible while guaranteeing no two concurrent executors touch the same files.

**Step 2a — Dependency sort:** Order items by dependency (item B needs item A's output → A before B), then by complexity (smaller first to build momentum, unless dependencies dictate otherwise).

**Step 2b — File-overlap analysis:** For each item, read its spec and identify the **file footprint** — the set of files it will create, modify, or read-then-write. Focus on write targets. Items whose specs name the same files (or the same directories in a "touch everything in this dir" pattern) have overlapping footprints.

**A footprint can be a well-formed file list and still be unbuildable.** Naming write targets isn't the same as confirming the change is buildable at those targets — the data the change needs may not reach the layer being changed. For any consumer-layer item (a UI component, a CLI surface, a renderer, or any layer that consumes data produced elsewhere), confirm as a cheap pre-flight before dispatch that the data the change needs is actually available at that layer. If it must be plumbed from a producer layer, that producer layer is part of the footprint, not a follow-up. The tell: the item's spec describes a display/consume change but names no producer file.

**Stub-level footprints supersede README dispatch graphs.** When per-stub `touches:` frontmatter (or equivalent in-spec footprint declaration) disagrees with a wave-graph cached in `README.md` / `STUB-INDEX.md`, trust the stub footprints — README graphs drift as stubs evolve and rename their write targets. Build the wave map from the union of stub-level footprints, not from a hand-maintained README dispatch graph.

**Step 2c — Build parallel batches (waves):** Group items into execution waves:
- **Wave 1:** All items with no dependencies and no file overlap with each other. These dispatch simultaneously.
- **Wave 2:** Items that depend on Wave 1 completions, or whose footprints overlap with Wave 1 items. No file overlap *within* the wave.
- Continue until all items are assigned.

If every item overlaps (e.g., they all touch the same config file), the result is N sequential waves of 1. That's fine.

**Step 2d — Identify risks:**
- **Sequential chains** (forced ordering)
- **Risk items** that might block the run (sequence early)
- **Shared-file bottlenecks** — files forcing serialization (candidates for spec splitting)

**Step 2e — Multi-plan convergence (when the input is N plans, not N items).** Sequencing a flat item list is Steps 2a-2d. When the readiness gate instead clears N whole plans/batons converging on shared surfaces, run this branch before dispatch — it is Phase-2 prep work, so EM/Opus judgment (including a reviewer dispatch to adjudicate a duplicate mechanism) is in-bounds here; autonomy still begins at Phase 5, not before.

- **Write-claimant table.** Enumerate every file with more than one *writing* claimant across the plans.
- **One owner per contended file**, with an explicit ordering rule wherever two plans must both touch it. Reproduce the shape of the nine-baton conductor's hot-file table — one row per file: file | claimants | owner/rule.
- **Detect duplicate mechanism** — two plans independently designing the same thing. This is the failure that motivates this whole branch. Resolution is adjudication (a single canonical spec both plans then consume), never letting both build it.
- **Shared citations are not shared writes.** A naive grep over-reports contention; only actual write-targets serialize.
- **Partition by surface family into phases**, each ending at a gate and a commit boundary.
- **Output a conductor document** at `docs/plans/<date>-<slug>.md` with `type: conductor` frontmatter and a `governs:` list of the plans/handoffs it sequences. It is a sequencing layer, not another plan — the governed plans remain the authoritative chunk bodies, and a picking-up session reads the conductor instead of all N plans.
- **This step's output feeds Phase 5's execution model, not N sequential wave-barriers.** Phase 5 models multi-plan execution as the full cross-plan DAG, each node a memoized promise that `await`s its own deps then dispatches — every chunk fires the instant its true deps clear, filling the concurrency cap optimally rather than waiting on artificial wave boundaries. Two rules keep that collision-free without worktrees: **one executor per HOT file** (a file touched by multiple chunks gets a single executor doing all its edits, sequenced after that file's latest dependency), and **split a chunk by file-owner when a shared-file edit would force a cycle** (author the load-bearing artifact as a standalone file so the circular edge dissolves). This step (the write-claimant table, one-owner-per-file, duplicate-mechanism detection) is what produces the inputs that model consumes.

**No worktrees. Ever.** Worktree creation, branch management, and merge conflict resolution cost more than they save at agent execution speed. The file-disjoint constraint is the coordination mechanism. If an item can't be made file-disjoint, it runs in a later wave.

### Phase 3: Flight Recorder — Compaction-Proof State

**This is the critical step.** Build a task list (TaskCreate) that persists through context compaction and allows the run to continue without re-reading everything.

Create tasks with this structure:

1. **Goal task** — titled with the full scope of the run, including:
   - What items are being executed (full list with identifiers)
   - That this is a mise-en-place straight shot
   - The tail mode: standard (EM-serial per-wave commits only) or hibernate (push + hibernate)

2. **Per-item tasks** — one for each work item, with:
   - Item identifier and file path to spec
   - Key details from the spec (enough to execute without re-reading if compacted)
   - **Wave assignment** and **file footprint** (from Phase 2 — which wave, which files this item touches)
   - Verification criteria
   - **Tried and abandoned:** (initially empty — update during execution via `TaskUpdate` metadata field `tried_and_abandoned`. Format: "Tried: [approach] — Failed: [reason]". One line per attempt. Persists through compaction; prevents post-compaction repetition.)
   - Status: `pending`

3. **Tail tasks** (based on mode):
   - **Standard:** (no tail task — wave gates already commit + push once per wave, EM-serial)
   - **Hibernate:** "Verify all pushes succeeded" — `pending`, then "Hibernate PC" — `pending`

**The flight recorder must contain enough context to resume cold.** After compaction, you may have lost the conversation but the task list survives. Write it like a handoff to a stranger.

**Anti-amnesia rule:** If you abandon an approach during execution, update the task's `metadata.tried_and_abandoned` field via TaskUpdate to include what you tried and why it failed BEFORE trying something new. After compaction, always read task metadata and descriptions (TaskGet) for "Tried and abandoned" notes before starting work — never retry a recorded-failed approach.

### Phase 4: Confirm and Fire

Output this plan to the PM, then IMMEDIATELY begin Phase 5. Do NOT wait for a response.

```
## Mise-en-Place — Ready to Fire

**Items queued:** [N items] across [M waves]

**Wave 1** (parallel): [items] — file-disjoint ✓
**Wave 2** (parallel): [items] — depends on Wave 1
[... or "Wave 1 (sequential): [items] — all items overlap on [file]"]

**Risks:** [any dependency or risk notes]
**Tail:** EM-serial per-wave commits + push — work stays on branch. PM runs /update-docs separately when ready.
[or: verify push + hibernate — overnight run, work stays on branch.]

**Estimated scope:** [rough sense of the run — "3 small items + 1 medium" etc.]

Proceeding.
```

The tail line is the EM's confirmation of mode — stated declaratively, not as a question. This is a launch announcement, not a proposal. The PM may already be away from the terminal. Do not frame it as "Ready to execute — shall I proceed?" Just output the announcement and start Phase 5.

### Phase 5: Execute — The Straight Shot

**Default execution vehicle: one background Workflow per wave.** Per `CLAUDE.md § Subagent Dispatch`, the background Workflow is the default for any multi-wave run — model the run as the cross-plan DAG of memoized promises described in § Phase 2e above, not a hand-typed sequence of `Agent` calls. Dispatch one Workflow per wave (barrier), then an EM commit from its returned manifest before firing the next wave, then optionally a `/handoff` at a wave boundary — the nine-baton conductor's `§ How to run this` is the reference cadence, scaled from phase to wave granularity to match the wave-gate commit below (§ Phase 5, step 3). Every `agent()` call inside the Workflow passes `model: 'sonnet'` explicitly; agents author, the EM commits scoped paths from the manifest, never `git add -A`; width ceiling ≤5 write-capable executors per barrier.

**Hand-orchestrated waves (the EM dispatching each `Agent` call itself, as described below) are the single-wave fallback — use them only for a run with exactly one wave, or with a named reason a Workflow can't express the shape.** Everything below — the wave gate, the footprint constraint, the DONE-summary and Haiku-verifier protocol, the anti-hallucination preamble — is the semantics a Workflow phase implements; it doesn't change when the vehicle changes, only who issues the dispatch calls.

**Signal autonomous mode:** Before executing the first item, write the autonomous-run sentinel so the context pressure hook knows not to nudge `/handoff`. Invoke the landed `misc-session-and-guards` CLI's `autonomous-sentinel enable` action via the settings-home forwarder — it resolves the session id via `coordinator_core.session.core.resolve_session_id()` internally (the same resolver the consumer hook keys its sentinel path against, reading `session_id` off its hook stdin JSON payload — the harness-injected `CLAUDE_CODE_SESSION_ID`) and fails loud rather than writing a silently-mismatched empty-suffix path:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/misc-session-and-guards" autonomous-sentinel enable --mode mise-en-place`

This tells the hook to emit informational-only context pressure messages (no handoff recommendation). The sentinel is removed in Phase 6 via the same CLI's `disable` action — no session-id bookkeeping is needed between the two calls.

**The `--mode` value is load-bearing semantics, not a label.** The sentinel's content (`mise-en-place` here, `autonomous` when `/autonomous` writes it) is what distinguishes a `/mise` run's sentinel from an `/autonomous` run's sentinel for any reader that inspects content — even though today's in-repo readers (`postuse_advisory_dispatch.py`, `nudge_em_code_dispatch.py`, `nudge-autonomous-askuserquestion.py`) currently check only presence. `/mise` and `/autonomous` remain genuinely decoupled AT THE POSTURE LAYER — they are natural combinations, but neither implies the other: under `mode: mise-en-place` the run's posture is hand-off-at-pressure (the CONTINUANCE terminal, § Phase 6), under `mode: autonomous` it is ride-compaction. `/autonomous` + `/mise` composes when the PM invokes both commands explicitly — see `autonomous.md`.

**Consumer assessments, recorded so a later reader does not have to re-derive them:**
- `nudge_em_code_dispatch.py`'s "Bypass 4" suppression is UNCHANGED — it still keys on sentinel presence, which still exists. No regression; this line records that an earlier concern (raised when the sentinel write was slated for removal) no longer applies.
- `nudge-autonomous-askuserquestion.py`'s suppression is UNCHANGED for the same reason — it keeps firing during every `/mise` run exactly as today, enforcing the "never pauses to ask" rule at the top of this file. This was the blocking finding against an earlier delete-the-write design; the mode-reader design above removes the regression at the root rather than patching it.
- `/mise` does not route through `/execute-plan` (it dispatches per-item executors directly), so the `execution_authorized_*` stamp-bypass consumers in `coordinator/skills/execute-plan/SKILL.md` are not on mise's path — not a live regression, noted for completeness only.

**Bandwidth rule:** Executors are backgrounded by default in /mise — not just for parallel waves, but always. This is stricter than the standard executor-dispatch procedure, which lets the EM run executors inline. In /mise the EM is steering many items; pulling each executor's transcript into context burns the window before the run finishes. Single-item waves still background — accept the dispatch overhead.

The executor does its own verification but never commits — only the EM, or a named Opus agent dispatched to do the work, invokes git (`~/.claude/CLAUDE.md § Concurrent-EM Git Operations`). Commits happen once per wave: the EM stages and commits every wave's changed paths in a single commit after that wave's verifiers all pass, not once per item. The EM consumes only a brief on-disk DONE summary, not the executor's full transcript. This is the structural bandwidth fix: the EM holds the wave map and the DONE-summary paths, nothing more.

**Execute wave by wave.** Each wave from Phase 2 is a batch of file-disjoint items.

**For each wave:**

1. **Dispatch all items in the wave concurrently.** For each item:
   - Mark `in_progress` via TaskUpdate. Update the plan document status if applicable. **Run the canonical tracker sweep** — grep for the item's codename across `docs/project-tracker.md`, `tasks/*/todo.md`, and roadmap files. Mark every match as "in progress."
   - Dispatch to a Sonnet executor agent with `run_in_background: true` and `mode: "auto"`. The prompt must include: the full spec (or path to it), the item's file footprint from Phase 2, and the assembler's dispatch-prompt template below.
   - **Pull the dispatch-prompt template from the assembler brief, don't retype it.** Phase 1's `backlog-grind-assemble brief mise-en-place` call already returned the `d-mise-executor-dispatch-prompt-template` directive with four fields — `anti_hallucination_preamble`, `footprint_constraint_template`, `self_verify_constraint`, `done_summary_constraint_template` — inject them into every dispatch prompt verbatim, filling `[item-id]`/`[list]` per item. `self_verify_constraint` is what shifts bandwidth out of the EM (verification, not commit, is the executor's job — it never invokes git); `done_summary_constraint_template` is what the executor writes to `tasks/mise-done/<item-id>.md` and replies `DONE: <path>` against (or `BLOCKED: <path>`) — no prose in chat, the EM reads the file.
   - Items that benefit from accumulated coordinator context (coherence decisions, cross-file awareness) stay in-coordinator and execute sequentially within the wave. This is the rare exception, not the default.

2. **Process completions as they arrive.** As each background agent reports DONE:
   - **An idle notification WITHOUT a DONE is not a completion signal and not a stall signal — it carries no information about whether the agent finished.** On idle-without-DONE, check DISK first: the expected DONE-summary path (`tasks/mise-done/<item-id>.md`) and `git status --porcelain -- <footprint paths>` for uncommitted changes (including created files — `git diff --name-only` alone would miss them) matching the item's footprint. The executor never commits, so a per-item `git log` check is meaningless here — the DONE-summary file plus the footprint-scoped working-tree diff are the disk signal. If disk is inconclusive, prefer a `SendMessage` status ping to the live agent over re-dispatch. **NEVER spawn a second agent onto a live agent's footprint — this is a hard rule.** It breaks the file-disjointness invariant Phase 2 establishes and the whole wave model rests on.
   - Read the DONE summary file (only). Do NOT pull the executor's transcript into context.
   - **Dispatch a Haiku verifier** with `run_in_background: true` and an on-disk verdict at `tasks/mise-verify/<item-id>.md`. The verifier reads the DONE summary + spec + the item's still-uncommitted working-tree diff (there is no commit to inspect — the executor never commits) and returns one of: `PASS` | `FOOTPRINT-VIOLATION` | `AC-MISS` | `VERIFICATION-CMD-FAILED` | `NEEDS-EM`. Verifier prompt:
     > Read the executor's DONE summary at `<path>`, the spec at `<spec-path>`, and the item's uncommitted working-tree state for its declared footprint — `git status --porcelain -- <footprint paths>` to enumerate every changed AND created path (`git diff --name-only` alone is blind to files the executor created), `git diff -- <footprint paths>` and `git diff --stat -- <footprint paths>` for modified-file content, and the raw content of any path `git status --porcelain` lists as `??` (a diff cannot show a created file's content — read it directly) — the executor never commits, so there is no SHA to inspect; everything here is read against the current working tree. Confirm: (a) every changed path is inside the declared footprint `[list]`; (b) every `## Acceptance Criteria` item from the spec is implemented; (c) the verification the executor actually ran was scoped to its own footprint (test files/dirs/node-ids it touched, plus footprint-scoped lints/type-checks) and passed per the DONE summary; (d) if the spec names verification broader than the footprint (a fast-test or full-suite/unscoped command), confirm the executor deferred it to the EM rather than running it — an executor that ran a spec-named fast-test or full-suite command exceeded its authorized scope; treat that as `NEEDS-EM`, not `PASS`, and say so in the rationale. Write a one-screen verdict to `tasks/mise-verify/<item-id>.md` ending with a single status line: `STATUS: PASS` (or one of the failure codes above) and a one-paragraph rationale citing file:line evidence. Reply EXACTLY `DONE: <path>`. No prose in chat.
   - **Verifiers are wave-scoped, not item-scoped — batch them.** Dispatch all wave verifiers concurrently after all wave executors return. Wave gate moves only when all verifiers are PASS.
   - On any non-PASS verdict, EM reads the verdict file and decides: (a) re-dispatch executor with adjusted spec, (b) revert out-of-bounds changes and re-plan footprint, (c) defer to a later wave, (d) early-stop per "When to Stop." Work from the verdict + diff, not the executor's transcript.
   - **Mark complete + tracker sweep:** On PASS, update task via TaskUpdate. **Re-run the canonical tracker sweep** — update every match to reflect completion. If the executor ran its own sweep, verify; fix gaps.

3. **Wave gate:** ALL items in a wave must complete before the next wave begins. This is the serialization point that guarantees later-wave items see earlier-wave changes.
   - **EM commits the wave.** Once every item in the wave has a PASS verdict, the EM — never a subagent — stages and commits the wave's full changed-path set (the union of every item's `git status --porcelain -- <footprint paths> | cut -c4-` output in the wave — the `cut -c4-` strips porcelain's two-character status prefix (`??`, ` M`, etc.) so the result is a bare path list `git add` can consume directly; feeding the raw prefixed lines straight to `git add -- <paths>` fails with "pathspec did not match any file(s)". This also means files an executor created are included alongside modifications — `git diff --name-only` alone would silently drop them) in a single commit before dispatching the next wave — via the named wave-commit op, never a hand-typed `git add`/`git commit`: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply mise-en-place --wave-path <path> [--wave-path <path>]... --granularity per-wave --message "mise: wave N — <items>"` (one `--wave-path` per changed path in the union above; never `git add -A`, never coordinator-safe-commit without `--expected-branch`). The post-commit hook pushes automatically. This is the only commit point in Phase 5 — items are batched into it, not committed individually — and it is what makes "wave complete" mean something concrete on disk rather than a verifier verdict with nothing underneath it.
   - **Poll `git branch --show-current` between waves.** Concurrent sessions can flip your branch mid-mise; if the branch changed, halt and reconcile before firing the next wave.
   - **Recovery commits do NOT advance the chain.** A patch that recovers from a crash, infra blip, or partial executor failure is not a chain-advance signal — re-arm the wave gate explicitly before dispatching the next wave.

4. **Brief status update between waves:** "Wave N complete ([items]). Firing wave N+1 ([items])." Output-only — never frame as a question, never wait for a response. Never output:
   - "Want me to fire those now?" — Just fire them.
   - "Ready for the next batch?" — Just start it.
   - "Should I proceed with X or Y first?" — This was decided in Phase 2.

**Single-item waves** (forced sequential due to file overlap or dependencies) still background per the bandwidth rule above — dispatch overhead is the accepted cost, not a reason to inline. Follow the same write-ahead → execute → verify → EM-commit → mark-complete cycle — the EM still does the commit, even for a wave of one.

**Dispatch model:** Enriched specs with code sketches are blueprints — Sonnet follows them; Opus judgment was already spent during enrichment+review. The coordinator's job during execution is verification and wave gating, not typing code.

**No worktrees.** All executors operate on the same worktree. The file-disjoint constraint from Phase 2 is the coordination mechanism. Do not use `isolation: "worktree"` on any executor dispatch.

### Phase 6: Tail — Close Out the Run

After all waves are executed and verified, mark all item tasks `completed` via TaskUpdate, clean up the autonomous-run sentinel via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/misc-session-and-guards" autonomous-sentinel disable`, then run the backlog-exhaustion check below, the anti-vacuity gate, the run's diff freeze, the inventory-record archival (`COMPLETE` only — PIPELINE.md § Phase 6), and the final tracker sweep, in that order.

**Backlog-exhaustion check (run FIRST, before the anti-vacuity gate below).** Running this tail is CLOSURE, not COMPLETION — the tail runs identically regardless of how much of the Phase-1 backlog actually executed, so reaching this phase implies nothing about exhaustion on its own. This check is what tells the two apart. It SELECTS a terminal; it does NOT gate the tail — a run that stops mid-backlog still needs the full tail below (see Anti-scope: gating would leave an unreviewed diff on the branch, strictly worse than the defect this check exists to fix).

The check's input is a CLOSED set of terminal dispositions, read from the § Phase 1 live per-item disposition ledger — a mechanical read, not EM recollection or a Phase-1 snapshot recalled from memory, updated at every wave gate:
- executed-and-PASSed
- explicitly routed out at the Phase 0 readiness gate (Phase 0 runs BEFORE Phase 1 inventory — such items are by construction absent from the Phase-1 inventory this check reads; the check's denominator is "Phase-1 inventory plus Phase-0a batons put back down", not "Phase-1 inventory" alone)
- dropped as `already-fixed` at Pre-Dispatch Verification
- put back down at Phase 0a (`pickup-assemble drop`)
- routed out mid-run with a named reason recorded in the disposition ledger

Anything not in this set is NON-TERMINAL. Resolve to exactly one named terminal:
- **COMPLETE** — every item in the ledger is terminal.
- **CONTINUANCE** — any item in the ledger is non-terminal.

**Both terminals run the identical tail below** — the anti-vacuity gate, the diff freeze, the end-of-run verification pass, the final tracker sweep, and baton disposition. Do not fork the tail on which terminal resolved. The difference is terminal wording plus, for CONTINUANCE, one extra artifact — the handoff described next.

**CONTINUANCE terminal.** Non-failure, and for a large run the EXPECTED ending — not a rare elected exit. Wording for this terminal must not read as apology or error ("stopped short", "incomplete run") — see Anti-scope; framing it that way pushes future EMs back toward reporting COMPLETE to avoid the stigma, the exact failure this check exists to prevent. CONTINUANCE requires a handoff, authored via `/handoff` at the terminal, naming three things — because re-derivation cost by a successor session is what the reporting incident this plan responds to actually cost:

1. the exact invocation to resume with;
2. a Phase-0-bypass assertion for the remaining items (they already passed the readiness gate — the successor must not re-run it);
3. the pre-computed wave map for the remaining items, so the successor does not re-derive Phases 0-2.

Electing CONTINUANCE and authoring this handoff is the EM exercising a sanctioned decision point at a doctrine-named moment, not a plan pre-authorizing a handoff artifact — no chunk of this doctrine's authoring plan writes the handoff itself.

**CONTINUANCE × hibernate interaction.** If a CONTINUANCE terminal is elected in hibernate mode, the handoff MUST be authored AND committed BEFORE `shutdown /h` — otherwise the successor artifact dies with the session. This is an explicit precondition on hibernate's tail action (§ Hibernate below), not an implication. Two rules are both live here and compose rather than skip one another: "Hibernate is always safe on early stop" (§ Safety Boundaries) governs WHETHER the machine hibernates; the backlog-exhaustion check governs WHAT TERMINAL WORDING the tail summary uses before it does. An early stop under hibernate mode still runs the exhaustion check, still elects CONTINUANCE if the backlog isn't exhausted, authors and commits the handoff, THEN hibernates.

**Anti-vacuity gate (run next, before the freeze below):** Confirm the run's own footprint is clean — `git status --porcelain -- <union of the run's declared footprint paths>` (scoped to what this run touched; Phase 2 computed this set and the flight recorder carries it. A bare unscoped `git status --porcelain` is wrong here — `~/.claude/CLAUDE.md § Concurrent-EM Git Operations` treats the active workstream branch as a shared bus where sibling dirty files are normal, so an unscoped check would misfire on another session's uncommitted work and, worse, direct the EM to commit files it doesn't own). Non-empty output means a wave's EM-commit step was missed; repair it now via the named wave-commit op (§ Phase 5 Wave gate), scoped to the paths this run actually owns, before proceeding to the freeze below. Running this gate first means a missed wave commit is repaired before the diff is frozen, so the frozen artifact the capping ceremony inherits covers the whole run rather than silently omitting it.

**Review is owed to the capping ceremony, and `/mise` does not run one.**

`/mise` has no review gate of its own. Review scale is `/workstream-complete`'s to decide and run, over the chain diff — a range that strictly contains this run's diff, at a scale its own table picks from diff shape. A second review here reviews a subset at a scale nobody chose, and its findings-to-zero loop is a gate on a ceremony that is not the capping one.

What `/mise` owes instead is the **routing obligation**: a run does not end with its diff unreviewed by anyone. The tail hands off to a ceremony that reviews — `/workstream-complete` to cap, or `/handoff` naming review-and-cap as the successor's remit. Both are named in the tail summary; neither is optional, and "the PM will run it later" is not a discharge.

Per-item Haiku verifiers check footprint + AC compliance. They are not a review pass and were never offered as one — they are why the run can defer review to the capping ceremony without shipping unexamined work in the interim, not a reason review is unnecessary.

Freeze the run's diff before handing off, so the capping ceremony inherits a materialized artifact rather than re-deriving a range across a shared branch:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/freeze-review-diff" --range "<start-sha>..HEAD" --slice-id "mise-<run-id>"
```

On a branch shared with concurrent sessions, that range will contain peer commits. `freeze-review-diff` refuses to write a trail record covering another session's commits; the remedy is `--paths` scoping to the run's own footprint plus per-slice records over the run's own wave commits, never narrowing the range to shed coverage. Record which applied.


**End-of-run verification pass (EM-only, once, not per item):** Executors in Phase 5 are capped to footprint-scoped verification; anything broader that a spec named gets deferred to the EM rather than run inline. Before the tail action, scan the DONE summaries for deferred verification. If any item deferred the repo's fast-test command, run it once here, across the run's cumulative diff, rather than per item — this is a top-level-EM-only invocation, never delegated to an executor. If any item deferred a full-suite or otherwise unscoped command, do not run it unilaterally: `/mise` is not on the implicit full-suite authorization list (only `/workday-complete`, `/workweek-complete`, and `/merging-to-main` carry that grant) — surface the deferred item and the command it named in the tail summary for the PM, the same way an unresolved product question would surface, rather than running an unauthorized full-suite pass.

**Final tracker sweep (mandatory):**
Verify that ALL canonical trackers reflect the run's outcomes — this is the EM's backstop, especially critical because nobody is watching during autonomous runs:
1. Grep each completed item's codename across `docs/project-tracker.md`, `tasks/*/todo.md`, `ROADMAP.md`, and any dispatch trackers
2. Confirm every completed item shows as done/checked in every tracker that references it
3. Confirm every in-progress or blocked item shows its current state
4. Fix any gaps — executors may have crashed before completing their sweep
5. Commit tracker fixes (if any) via the named wave-commit op (scoped, explicit-pathspec staging is the invariant; this op satisfies it by construction): `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply mise-en-place --wave-path <tracker-path> [--wave-path <tracker-path>]... --granularity per-wave --message "mise: tracker sync"`.

**Baton disposition (whenever Phase 0a ran):** a claim is an obligation, so no baton this run claimed is left claimed by an ended session. Batons this run claimed and completed are concluded through `/workstream-complete`; **there is no manual terminal-flip verb, and `pickup-assemble apply` is not one** — every verb it can reach is claim-side, so running it on a finished baton re-claims it instead of closing it, silently deepening the strand it was meant to clear. `pickup-assemble drop <path>` anything unstarted; write a successor via `/handoff` for anything genuinely mid-stream. Archiving is the boot sweep's job. State each disposition in the tail summary.

**Complete-word guard, run-level verdict line — apply this the moment the tail summary is composed, below:**

> The run-level verdict line MUST read exactly COMPLETE or CONTINUANCE; the word 'complete' may not appear as the run's disposition unless the exhaustion check passed. Item-level, wave-level and task-level uses of 'completed' (TaskUpdate, tracker sweep, baton disposition) are unaffected.

This guard binds the run-level verdict line only. "Mark all item tasks `completed`" at the top of this phase, "every completed item" in the tracker sweep, and "batons this run claimed and completed" in baton disposition above are unaffected uses of the word and stay exactly as written.

**Standard (default):**
1. Re-confirm the run's own footprint is clean — `git status --porcelain -- <footprint paths>` (the anti-vacuity gate above already ran this; this is a restatement covering any residue left uncommitted since, not a re-run of the full gate logic). Commit any residue now (§ Phase 5 Wave gate) before declaring the run's terminal. Then: report the run-level verdict resolved by the backlog-exhaustion check above — COMPLETE or CONTINUANCE, per the canonical sentence — never a bare "done" standing in for it. Per-wave commits already pushed. Then discharge the routing obligation (§ Review is owed to the capping ceremony): name the frozen diff path and route to `/workstream-complete` to cap, or to `/handoff` with review-and-cap as the successor's remit. The PM runs `/update-docs` (and later `/workday-complete` or `/merge-to-main`) separately when ready to integrate. Rationale: `/update-docs` now absorbs the tracker-maintenance, handoff-archival, and atlas-integrity-check subroutines inline, making it a heavier operation than it was when /mise tailed it automatically. PM-gated invocation is the right shape.

**Hibernate:**
1. **Re-confirm the run's own footprint is clean — `git status --porcelain -- <footprint paths>`.** The anti-vacuity gate above already ran this; this is a restatement covering any residue left uncommitted since, not a re-run of the full gate logic. Scoping to the run's footprint (rather than a bare unscoped check) matters here specifically: "all wave commits are pushed" is trivially true if the EM never committed anything, so absence of unpushed commits is not by itself proof the run's output is safe, and an unscoped check would hand a sibling session's normal dirty files (`~/.claude/CLAUDE.md § Concurrent-EM Git Operations`) a veto over this run's hibernate tail. Non-empty output within this run's footprint means uncommitted wave output exists — repair it now via the named wave-commit op (§ Phase 5 Wave gate) before proceeding. Do NOT hibernate with the run's own footprint dirty.
2. Verify push — resolve the current branch via the settings-home coordinator-current-branch forwarder (never a hand-rolled claude-klabauter-root resolution ladder), then confirm HEAD carries no commits the resolved branch's origin counterpart is missing. An empty result means all session work is pushed.
3. If unpushed commits remain, push explicitly. If push fails, do NOT hibernate — stop and report.
4. **If the resolved terminal is CONTINUANCE:** the handoff (§ CONTINUANCE terminal above) must be authored and its commit pushed BEFORE step 5 — the successor artifact must not die with the session.
5. Hibernate the machine — Windows: `shutdown /h`. Linux/Mac: `systemctl hibernate`.

The hibernate precondition is: (a) the run's own footprint is clean (step 1), (b) the EM has committed and pushed all wave output (steps 2-3), and (c) no PM-tradeoff items are outstanding (§ Phase 6, the tail summary's surfaced-questions list) — not merely "no unpushed commits remain," which a run with nothing committed would satisfy vacuously.

Hibernate over shutdown: same zero power draw, but the machine resumes to its prior state instead of cold-booting.

## Safety Boundaries

- **Never merge to main.** Work stays on branch. The PM merges interactively after review, using `/merge-to-main` or `/workday-complete`.
- **Never use worktrees.** All executors operate on the same worktree. File-disjoint wave scheduling is the coordination mechanism. Worktree creation + merge overhead exceeds the time saved at agent execution speed.
- **Never hibernate without explicit PM request.** Hibernate mode is opt-in only, requires unmistakable consent (`--hibernate` flag or "hibernate"/"shut down"/"power off"), and is never escalated from soft signals like "overnight" or "it's late".
- **Never escalate tail mode.** Standard → hibernate is the PM's call. Do not suggest it, do not ask about it.
- **Hibernate is always safe on early stop.** If hibernate mode was invoked and the run must stop early, hibernate anyway. Incomplete work on a branch + hibernated machine is strictly better than incomplete work + machine running all night.
- **Commit after every wave.** Crash insurance. Executors never commit — a dispatched item's work is not done until the EM has committed it as part of its wave's single EM-serial commit.
- **Write-ahead status on everything.** If the session dies, the plan AND every canonical tracker show exactly where execution stopped. The canonical tracker sweep on start is the insurance policy; the sweep on finish is the receipt.
- **Push is automatic** via post-commit hook. Verify remote state before hibernating.

## When to Stop

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
- **Agent recovery** — rate-limited agents, crashed agents, auth failures, uncommitted code left on disk by a stalled executor, missing subsystem registrations. These are routine operational handling. Re-dispatch, audit what's on disk, finish the work, and have the EM commit it as part of the wave's single commit once the wave's verifiers pass. Never frame "we have N uncommitted workstreams, want me to recover them?" as a choice — recovery IS the work the PM authorized. Asking an EM whether to finish tractable, scoped, roadmap-aligned work is a failure of the role.
- **Concurrent-session churn** — another session's commits sweeping your staged changes, attribution splits, shared-file merges. This is the ordinary agree-case, closed by `ceremony.scoped_git_commit` (claude-klabauter; `paths`, `message`) — it selects agree-case vs. private-index for you, so a deliberately-staged partial hunk against a non-matching worktree is handled the same way, not a special case you resolve by hand. See `docs/wiki/scoped-safety-commits.md`. Then continue.
- **Subsystem registration gaps** — if a handler file is on disk but `Subsystem.h`/`.cpp` doesn't register it, that's a routine finish-the-work case, not a PM question.

**Non-failure early stop:**
- **Context exhaustion with backlog remaining.** Every row above is a failure; this one is not — its whole purpose is to give the benign, expected stop a sanctioned shape. Do not route it through the failure-framed steps below. Instead: run the full Phase 6 tail (§ Phase 6 above — anti-vacuity gate, diff freeze, end-of-run verification, tracker sweep, baton disposition), let the backlog-exhaustion check resolve CONTINUANCE, and author the handoff CONTINUANCE requires. This is the sanctioned move for the large-run case, not the exception.

**If you must stop early for one of the failure reasons above:**
1. Commit all current work — even partial progress — via the named wave-commit op, scoped to the flight recorder's working set: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/backlog-grind-assemble" apply mise-en-place --wave-path <path> [--wave-path <path>]... --granularity per-wave --message "<subject>"` (one `--wave-path` per path in the flight recorder's working set; never `git add -A` or coordinator-safe-commit without `--expected-branch`).
2. Update tasks via TaskUpdate with where you stopped and why, including which items remain.
3. Update any plan documents with current status.
4. Verify the branch is on remote (post-commit hook should have handled it — confirm).
5. **If hibernate mode was invoked:** Hibernate anyway. The PM will see the incomplete run on the branch on wake. Safe — work is on a branch, not main.
6. **If standard mode:** Stop. The PM will see the state in the task list and on the branch.

This failure-framed path is distinct from context exhaustion above: a genuine failure stops short of the tail, while context exhaustion still runs the full tail and resolves CONTINUANCE.

## Failure Modes

| Situation | Action |
|-----------|--------|
| Item spec ambiguous at multiple decision points | Stop early (see above) |
| Verification fails with a fixable error | Fix and continue — do not escalate |
| Verification fails structurally | Stop early, commit progress |
| Dispatched executor returns BLOCKED | Diagnose — if spec-fixable, update stub and re-dispatch; if architectural, stop early and report |
| Executor writes outside its file footprint | Bug in Phase 2 analysis — revert the out-of-bounds changes, re-analyze the overlap, adjust wave assignments, and re-execute |
| Push fails before hibernate | Do NOT hibernate — work must be on remote first. Stop and report. |
| Context compacted mid-run | Read goal task and per-item tasks via TaskList/TaskGet to re-orient; check `metadata.tried_and_abandoned`; continue from `in_progress` item |
| Context pressure with backlog remaining | Not a failure — run the Phase 6 tail and take the CONTINUANCE terminal |

## Relationship to Other Commands

- **`/workstream-complete`** — owns review. It decides the scale from diff shape and runs it over the chain diff, a superset of this run's. `/mise` freezes its diff and routes here; it never reviews or gates on review itself.
- **`/update-docs`** — NOT auto-invoked. PM runs separately after `/mise` completes.
- **`/workday-complete`** — what the PM runs afterward (interactively) if they want end-of-day consolidation and health survey
- **`/merge-to-main`** — what the PM runs when ready to merge the branch; never invoked from this command
- **`pipelines/mise-en-place/PIPELINE.md`** — the pipeline definition this command executes; consult it for full nuance on any phase
