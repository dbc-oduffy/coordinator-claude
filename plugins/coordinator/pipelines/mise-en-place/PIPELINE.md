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
| **Standard** (default) | No special flags | `/update-docs` — sync docs, commit, push to branch |
| **Hibernate** | PM says "overnight", "hibernate", "shutdown", "go to bed", or similar | `/update-docs` + push to branch + hibernate PC |

**Default to standard.** If the PM doesn't specify a mode, run standard. Don't ask — the PM can always invoke `/workday-complete` separately afterward. The EM confirms the mode in Phase 4 ("Tail: /update-docs — straight shot, work stays on branch").

**Why no merge-to-main from mise-en-place?** This skill runs autonomously, often with the PM away from the terminal. Claude cannot verify all externalities — CI may fail, behavioral regressions may be subtle, colleagues may be affected. Merging unsupervised work to main violates the safety principle of matching blast radius to confidence level. The PM merges to main when they return, after reviewing the branch. Use `/workday-complete` or `/merge-to-main` interactively when the PM is present.

**Announce at start:** "I'm running `/mise-en-place` to prep and execute a straight shot through the backlog."

## What Mise IS NOT

Mise is not "plan-as-you-go autonomy." It is not a license to live-assemble specs, research contracts that downstream items will consume, or run a "foundations wave" whose output becomes reference material for later waves. Those activities require EM judgment, reviewer dispatch, and PM alignment — they are session-EM territory, not autonomous-execution territory.

The coordinator system optimizes for first-pass correctness: planning happens deeply BEFORE the run, so executors only type. If a planned wave produces decisions/artifacts that later waves depend on for their own definition, the run is not ready for mise — it is ready for a planning session.

## When to Use

- You have 2+ items that are **mise-grade** by the readiness criteria below
- The PM wants autonomous execution of mechanical work with minimal interruption
- The PM wants the backlog cleared — whether they're watching, stepping away, or wrapping up for the day

## Readiness Criteria — All Items Must Pass

A mise-grade item meets ALL of the following:

1. **Reviewed and sealed.** Spec has been through enrichment + reviewer; findings integrated. No "executor types it, then we review."
2. **No downstream contract.** Output is not reference material later waves consume to define their own behavior.
3. **Pure-executor agent type.** A Sonnet executor (or coordinator-inline) can complete it given the spec — not enricher, not reviewer, not staff-session, not live-MCP authoring.
4. **File footprint declarable.** Files-to-be-written can be named in advance.
5. **Verification is mechanical.** Tests pass, signatures match, AC checked off — not "the reviewer agrees."

## Don't Use When

The EM must REJECT a /mise run if any candidate item exhibits these patterns:

- **"Wave 1: foundations"** — wiki pages, contract definitions, schema authoring, research outputs, or any artifact later waves consume as reference. Foundations belong in a planning session, not a mise.
- **Mixed agent types in the planned waves** — enricher + executor + MCP-author together signals the work isn't ready.
- Items marked `Pending Review` or with open reviewer findings.
- Vague acceptance criteria ("improves the system") rather than verifiable ones.
- Items requiring `manage_*` MCP tools in a live editor — those need an interactive EM-driven flow.
- Research/brainstorming stubs whose output is "a decision."
- Only one item — use `/execute-plan` directly.
- Items aren't scoped yet — use `coordinator:writing-plans` or `coordinator:brainstorming` first.
- Iterative PM judgment expected throughout.

**If even one item fails, decline the entire run** rather than fragmenting it on the fly. Output a clear refusal naming each disqualifying item, the reason, and the recommended next step (planning session, /enrich-and-review, /review-dispatch, /staff-session, /delegate-execution). The PM decides whether to pull the failed items or defer the mise.

## The Process

### Phase 0: Readiness Gate

**Bypass condition.** If the session was opened from a handoff (or the PM's invocation explicitly references one) and that handoff states the queued items have already been gated as mise-ready, **skip Phase 0 entirely** and proceed to Phase 1. The bypass is valid when the handoff names the items in scope and asserts mise-readiness in unambiguous terms. Re-running the gate after a verified handoff is wasted context — large backlogs can blow the EM's window on stub reading alone, which is the failure mode this bypass exists to prevent. Announce the bypass: "Phase 0 bypassed — handoff at <path> verified mise-readiness for [items]." If unsure whether the handoff covers all queued items, do NOT bypass.

**Otherwise:** before inventory, before announcement, before any flight-recorder work — apply the readiness criteria above to every candidate item. If any item fails, output the refusal block (see the command file for format) and stop. Do not proceed to Phase 1.

### Phase 1: Inventory — What's on the Board?

**Bandwidth rule:** The EM does NOT read every stub. For runs with >3 items (or PM-flagged "many items"), dispatch a Sonnet inventory scout with `run_in_background: true` to produce a structured table at `tasks/mise-inventory-<timestamp>.md` (one row per item: identifier | spec path | one-line summary | declared file footprint | dependencies | verification | complexity). The scout writes to disk and returns `DONE: <path>`; the EM reads the table from disk and works from it for Phase 2 sequencing. The full spec text stays out of the EM's context until the executors load it.

Sources the scout (or the EM, for ≤3-item runs) checks:

1. **Plan files:** `tasks/*/todo.md` — items marked ready/pending execution
2. **Enriched stubs:** Any chunk directories with status "Enriched" or "Reviewed"
3. **PM's explicit list:** If the PM named specific items (e.g., "PX4-6B through Cesium-D"), use that as the canonical list
4. **Open tasks:** Any `tasks/*/` directories with incomplete work

### Phase 2: Sequence and Parallelize — Maximum Velocity

The goal is maximum throughput: run as many items concurrently as possible while guaranteeing no two concurrent executors touch the same files.

**Step 2a — Dependency sort:** Order items by dependency (item B needs item A's output → A before B), then by complexity (smaller first to build momentum, unless dependencies dictate otherwise).

**Step 2b — File-overlap analysis:** For each item, read its spec and identify the **file footprint** — the set of files it will create, modify, or read-then-write. This doesn't need to be exhaustive; focus on write targets. Items whose specs name the same files (or the same directories in a "touch everything in this dir" pattern) have overlapping footprints.

**Step 2c — Build parallel batches:** Group items into execution waves:
- **Wave 1:** All items with no dependencies and no file overlap with each other. These dispatch simultaneously.
- **Wave 2:** Items that depend on Wave 1 completions, or items whose footprints overlap with Wave 1 items. Again, no file overlap *within* the wave.
- Continue until all items are assigned to a wave.

If every item overlaps with every other item (e.g., they all touch the same config file), the result is N waves of 1 — purely sequential. That's fine; the analysis cost is trivial and the answer is honest.

**Step 2d — Identify risks:**
- **Sequential chains** where one item's output feeds the next (forced ordering)
- **Risk items** that might block the run if they fail (sequence these early)
- **Shared-file bottlenecks** — files that force serialization across many items (note these; they're candidates for splitting the item's spec to isolate the shared-file edit)

**No worktrees. Ever.** Worktree creation, branch management, and merge conflict resolution cost more time than they save at agent execution speed. The file-disjoint constraint is the coordination mechanism — if it's upheld, parallel executors on the same worktree cannot conflict. If an item can't be made file-disjoint, it runs in a later wave.

### Phase 3: Flight Recorder — Compaction-Proof State

**This is the critical step.** Build a task list (TaskCreate) that persists through context compaction and allows the run to continue without re-reading everything.

Create tasks with this structure:

1. **Goal task** — titled with the full scope of the run, including:
   - What items are being executed (full list with identifiers)
   - That this is a mise-en-place straight shot
   - The tail mode: standard (`/update-docs`) or hibernate (`/update-docs` + hibernate)

2. **Per-item tasks** — one for each work item, with:
   - Item identifier and file path to spec
   - Key details from the spec (enough to execute without re-reading if compacted)
   - **Wave assignment** and **file footprint** (from Phase 2 — which wave, which files this item touches)
   - Verification criteria
   - **Tried and abandoned:** (initially empty — update during execution via `TaskUpdate` metadata field `tried_and_abandoned`. Format: "Tried: [approach] — Failed: [reason]". One line per attempt. Persists through compaction and prevents post-compaction repetition.)
   - Status: `pending`

3. **Tail tasks** (based on mode):
   - **Standard:** "Run /update-docs" — `pending`
   - **Hibernate:** "Run /update-docs" — `pending`, then "Hibernate PC" — `pending`

**The flight recorder must contain enough context to resume cold.** After compaction, you may have lost the conversation but the task list survives. Write it like a handoff to a stranger.

**Anti-amnesia rule:** If you abandon an approach during execution, update the task's `metadata.tried_and_abandoned` field via TaskUpdate to include what you tried and why it failed BEFORE trying something new. After compaction, always read task metadata and descriptions (TaskGet) for "Tried and abandoned" notes before starting work — do not retry approaches that are recorded as failed.

### Phase 4: Confirm and Fire

Present the plan to the PM:

```
## Mise-en-Place — Ready to Fire

**Items queued:** [N items]
[Numbered list with identifiers and one-line descriptions]

**Sequence:** [any dependency notes]
**Tail:** /update-docs — straight shot, work stays on branch.
[or: /update-docs + hibernate — overnight run, work stays on branch.]

**Estimated scope:** [rough sense of the run — "3 small items + 1 medium" etc.]

Ready to execute the full sequence. Proceeding.
```

The tail line is the EM's confirmation of mode — stated declaratively, not as a question. If the PM didn't specify hibernate, default to `/update-docs` and move on.

This is a launch announcement, not a proposal. Output it and immediately begin Phase 5. Do NOT wait for a response — the PM may already be away from the terminal.

### Phase 5: Execute — The Straight Shot

**Signal autonomous mode:** Before executing the first item, write the autonomous-run sentinel so the context pressure hook knows not to nudge `/handoff`:
```bash
echo "mise-en-place" > /tmp/autonomous-run-${SESSION_ID}
```
This tells the hook to emit informational-only context pressure messages (no handoff recommendation). The sentinel is cleaned up in Phase 6.

**Execute wave by wave.** Each wave from Phase 2 is a batch of file-disjoint items:

**Bandwidth rule:** /mise backgrounds executors by default — single-item waves included. The EM steers many items; pulling each executor's transcript into context burns the window before the run finishes. Executors do their own verification-and-commit; verifiers (Haiku, also backgrounded) check the result; the EM reads only one-screen DONE summaries and PASS/FAIL verdicts from disk.

**For each wave:**

1. **Dispatch all items in the wave concurrently.** For each item:
   - Mark `in_progress` via TaskUpdate. Update plan document status if applicable.
   - Dispatch to a Sonnet executor agent with `run_in_background: true` and `mode: "acceptEdits"`. The prompt must include the full spec (or path to it), the item's file footprint from Phase 2, the footprint constraint, the self-verify-and-commit constraint, and the DONE-summary constraint. See the command file for verbatim wording.
   - Items that benefit from accumulated coordinator context (coherence decisions, cross-file awareness) stay in-coordinator and execute sequentially within the wave — rare exception, not default.

2. **Process completions via Haiku verifiers.** As each background executor reports DONE:
   - Read only the DONE summary file. Do NOT pull the executor's transcript into context.
   - Dispatch a Haiku verifier with `run_in_background: true` to read the DONE summary + spec + commit diff and write a verdict at `tasks/mise-verify/<item-id>.md` ending with `STATUS: PASS` (or `FOOTPRINT-VIOLATION` | `AC-MISS` | `VERIFICATION-CMD-FAILED` | `NEEDS-EM`). Verifiers are wave-scoped — batch them and gate the wave on all PASS.
   - On any non-PASS verdict, the EM decides re-dispatch / revert / defer / early-stop from the verdict + diff alone.
   - Mark complete via TaskUpdate on PASS.

3. **Wave gate:** ALL items in a wave must complete before the next wave begins. This is the serialization point that guarantees later-wave items see earlier-wave changes.

4. **Brief status update between waves:** "Wave N complete ([items]). Firing wave N+1 ([items])." Output-only — do NOT frame as a question, do NOT wait for a response.

**Single-item waves** (forced sequential due to file overlap or dependencies) execute inline — dispatch overhead isn't worth it for one item. Follow the same write-ahead → execute → verify → commit → mark-complete cycle.

**Dispatch model:** Enriched specs with code sketches are blueprints — Sonnet follows them; Opus judgment was already spent during enrichment+review. See `/delegate-execution` Phase 2 for the full model selection rubric. The coordinator's job during execution is verification and wave gating, not typing code.

### Phase 6: Tail — Close Out the Run

After all waves are executed and verified, mark all item tasks as `completed` via TaskUpdate, clean up the autonomous-run sentinel, then execute the tail action based on mode:

```bash
rm -f /tmp/autonomous-run-${SESSION_ID}
```

**Standard (default):**
1. Invoke `/update-docs` — sync documentation, commit, push to branch (includes artifact distillation if thresholds are met)
2. Done. The PM can invoke `/workday-complete` separately when they're ready to merge.

**Hibernate:**
1. Invoke `/update-docs --no-distill` — sync documentation, commit, push to branch. Skip distillation in overnight mode — it requires PM approval at Phase 4 and nobody's home.
2. Verify push succeeded (work must be on remote before hibernating)
3. Hibernate:

```bash
# Windows
shutdown /h

# Linux/Mac
systemctl hibernate
```

Hibernate over shutdown: same zero power draw, but the machine resumes to its prior state instead of cold-booting. Lower blast radius if something needs attention.

**If `/update-docs` fails in hibernate mode:** Still hibernate. The work is already committed and pushed from Phase 5 item-level commits. Doc sync is nice-to-have; power conservation is the priority. The PM can run `/update-docs` after wake.

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

**If you must stop:**
1. Commit all current work — even partial progress. Stage everything.
2. Update tasks via TaskUpdate with where you stopped and why, including which items remain.
3. Update any plan documents with current status.
4. Push is automatic via post-commit hook, but verify the branch is on remote.
5. **If hibernate mode was invoked:** Presume the PM is away. Hibernate the machine. The PM will see the incomplete run on the branch when they wake up. Incomplete work on a branch is safe — it's not on main, colleagues aren't affected, and it's better than leaving a power-hungry PC running overnight waiting for input that won't come.
6. **If standard mode:** Just stop. The PM will see the state in the task list and on the branch.

## Safety Boundaries

- **Never merge to main from mise-en-place.** Work stays on branch. The PM merges interactively after review.
- **Never use worktrees.** All executors operate on the same worktree. File-disjoint wave scheduling is the coordination mechanism. Worktree creation + merge overhead exceeds the time saved at agent execution speed.
- **Never hibernate without explicit PM request.** Hibernate mode is opt-in only.
- **Never escalate tail mode without PM request.** Standard → hibernate escalation is PM's call. Don't ask, don't suggest.
- **Hibernate is always safe on early stop.** If hibernate mode was invoked and the run must stop early, hibernate anyway. Incomplete work on a branch + hibernated machine is strictly better than incomplete work + machine running all night.
- **Commit after every item.** If the session crashes, work is preserved. This applies to dispatched agents too — an executor's work is not "done" until it's committed.
- **Write-ahead status on everything.** If the session dies, the plan shows exactly where execution stopped.
- **Push is automatic** via post-commit hook — crash insurance is always active. Verify remote state before hibernate.

## Integration

**Required workflow skills:**
- **`/execute-plan`** — Pattern for executing individual plan items
- **coordinator:verification-before-completion** — Evidence before claims on each item
- **`/update-docs`** — Tail action after all items complete (both modes)

**Optional workflow skills:**
- **coordinator:dispatching-parallel-agents** — Parallel dispatch patterns (file-disjoint constraint, same-worktree)

**Called by:** PM directly — whether they're watching, stepping away, or wrapping up for the day

**Pairs with:**
- **coordinator:writing-plans** — Creates the scoped items this skill executes
- **`/session-start`** — Often follows session-start when the PM reviews the backlog and decides to straight-shot it
