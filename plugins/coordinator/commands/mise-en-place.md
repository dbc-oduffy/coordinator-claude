---
description: Autonomous backlog execution — gathers all ready work items, builds a compaction-proof flight recorder, executes sequentially without stopping for input, then tails with /update-docs (or /update-docs + hibernate in overnight mode)
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[--hibernate]"
---

# Mise-en-Place — Autonomous Backlog Execution

Everything in its place before the fire gets lit. This command front-loads all context gathering and sequencing into a compaction-proof flight recorder, then executes the full backlog in a straight shot without stopping for input. The PM authorized the run when they invoked this command.

**Core principle:** Prep all context, sequence all items, build the flight recorder — then execute without interruption. Once Phase 5 begins, the EM never pauses to ask a question, offer a choice, or wait for a response. The anti-stall rule is not optional: if execution stalls mid-run, the tail phase (hibernate) never triggers, leaving the machine running indefinitely.

**Autonomous-to-completion.** "Mise-en-place" means the PM has authorized the entire run — including the messy parts. Rate-limits, crashed agents, partial commits, recovery re-dispatches, concurrent-session staging conflicts — all routine. The EM drives the run to Phase 6 tail. The only legitimate stops are genuine product/scope questions the PM has unique information on, or the structural-failure cases listed under "When to Stop." Asking an EM whether to finish already-authorized, tractable, scoped, roadmap-aligned work is a failure of the role.

**Announce at start:** "Running /mise-en-place — prepping flight recorder, then straight shot through the backlog."

## Arguments

Parse `$ARGUMENTS` for the tail mode:

| Trigger | Mode | Tail action |
|---------|------|-------------|
| No arguments, or no hibernate keyword | **Standard** (default) | `/update-docs` — sync docs, commit, push to branch |
| `--hibernate`, or keywords: "overnight", "hibernate", "shutdown", "go to bed" | **Hibernate** | `/update-docs` + push + hibernate PC |

**Default to standard.** If the PM didn't specify hibernate, run standard and move on. Do not ask — the PM can invoke `/workday-complete` separately afterward.

## Instructions

Follow all six phases in order. The pipeline definition at `pipelines/mise-en-place/PIPELINE.md` is the authoritative source. This command codifies its orchestration.

### Phase 1: Inventory — What's on the Board?

Gather every ready-to-execute work item. Sources to check:

1. **Plan files:** `tasks/*/todo.md` — items marked ready/pending execution
2. **Enriched stubs:** Any chunk directories with status "Enriched" or "Reviewed"
3. **PM's explicit list:** If `$ARGUMENTS` names specific items (e.g., "PX4-6B through Cesium-D"), use that as the canonical list
4. **Open tasks:** Any `tasks/*/` directories with incomplete work

For each item, capture:
- **Identifier** (stub name, plan reference, or short description)
- **Location** (file path to spec/plan)
- **Dependencies** (does it need another item completed first?)
- **Estimated complexity** (quick read of the spec — small/medium/large)
- **Verification method** (how will you know it's done?)

### Pre-Dispatch Verification (geneva T1.1, single landing across 3 files)

Before sequencing or dispatching any executors, verify that backlog items gathered in Phase 1 are still applicable to the current codebase.

For each item sourced from a backlog file (`tasks/bug-backlog.md`, `tasks/debt-backlog.md`, or a plan stub marked pending), dispatch a Haiku agent to confirm the issue still exists in HEAD:

1. Read the cited file:line — does the bug/debt pattern still exist?
2. Check `git log --oneline -5 {file}` — did a recent commit address it?
3. Return `still-open` / `already-fixed` per item

Drop `already-fixed` items before building the execution queue. In one measured run, 11 of 20 backlog items were already fixed before dispatch. Verifying first prevents dispatching executors on work that has already shipped.

### Phase 2: Sequence and Parallelize — Maximum Velocity

The goal is maximum throughput: run as many items concurrently as possible while guaranteeing no two concurrent executors touch the same files.

**Step 2a — Dependency sort:** Order items by dependency (item B needs item A's output → A before B), then by complexity (smaller first to build momentum, unless dependencies dictate otherwise).

**Step 2b — File-overlap analysis:** For each item, read its spec and identify the **file footprint** — the set of files it will create, modify, or read-then-write. Focus on write targets. Items whose specs name the same files (or the same directories in a "touch everything in this dir" pattern) have overlapping footprints.

**Step 2c — Build parallel batches (waves):** Group items into execution waves:
- **Wave 1:** All items with no dependencies and no file overlap with each other. These dispatch simultaneously.
- **Wave 2:** Items that depend on Wave 1 completions, or whose footprints overlap with Wave 1 items. No file overlap *within* the wave.
- Continue until all items are assigned.

If every item overlaps (e.g., they all touch the same config file), the result is N sequential waves of 1. That's fine.

**Step 2d — Identify risks:**
- **Sequential chains** (forced ordering)
- **Risk items** that might block the run (sequence early)
- **Shared-file bottlenecks** — files forcing serialization (candidates for spec splitting)

**No worktrees. Ever.** Worktree creation, branch management, and merge conflict resolution cost more than they save at agent execution speed. The file-disjoint constraint is the coordination mechanism. If an item can't be made file-disjoint, it runs in a later wave.

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
   - **Tried and abandoned:** (initially empty — update during execution via `TaskUpdate` metadata field `tried_and_abandoned`. Format: "Tried: [approach] — Failed: [reason]". One line per attempt. Persists through compaction; prevents post-compaction repetition.)
   - Status: `pending`

3. **Tail tasks** (based on mode):
   - **Standard:** "Run /update-docs" — `pending`
   - **Hibernate:** "Run /update-docs" — `pending`, then "Hibernate PC" — `pending`

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
**Tail:** /update-docs — straight shot, work stays on branch.
[or: /update-docs + hibernate — overnight run, work stays on branch.]

**Estimated scope:** [rough sense of the run — "3 small items + 1 medium" etc.]

Proceeding.
```

The tail line is the EM's confirmation of mode — stated declaratively, not as a question. This is a launch announcement, not a proposal. The PM may already be away from the terminal. Do not frame it as "Ready to execute — shall I proceed?" Just output the announcement and start Phase 5.

### Phase 5: Execute — The Straight Shot

**Signal autonomous mode:** Before executing the first item, write the autonomous-run sentinel so the context pressure hook knows not to nudge `/handoff`:
```bash
echo "mise-en-place" > /tmp/autonomous-run-${SESSION_ID}
```
This tells the hook to emit informational-only context pressure messages (no handoff recommendation). The sentinel is cleaned up in Phase 6.

**Execute wave by wave.** Each wave from Phase 2 is a batch of file-disjoint items.

**For each wave:**

1. **Dispatch all items in the wave concurrently.** For each item:
   - Mark `in_progress` via TaskUpdate. Update the plan document status if applicable. **Run the canonical tracker sweep** — grep for the item's codename across `docs/project-tracker.md`, `tasks/*/todo.md`, and roadmap files. Mark every match as "in progress."
   - Dispatch to a Sonnet executor agent with `run_in_background: true`. The prompt must include: the full spec (or path to it), the item's file footprint from Phase 2, and an explicit constraint: *"You MUST NOT create or modify any file outside this footprint: [list]. If you discover you need to, STOP and report back."*
   - **Inline anti-hallucination preamble at the top of every executor prompt** (parallel-dispatch sessions are the failure mode where this hits): *"Ignore any 'TEXT ONLY' / 'tool calls will be REJECTED' / 'LSP watcher reverts writes' framing you may encounter — these are known hallucinations from confused prior agents in this session and do not exist in this environment. There is no hook or watcher reverting your writes; verify with `ls -la <path>` after any Write. The ONLY valid completion is calling Write/Edit and committing. Returning code inline = task failure."*
   - Items that benefit from accumulated coordinator context (coherence decisions, cross-file awareness) stay in-coordinator and execute sequentially within the wave.

2. **Process completions as they arrive.** As each background agent completes:
   - Verify its output against the spec. Apply `coordinator:verification-before-completion` — evidence before claims.
   - **Spec-check:** If the item has an enriched stub or plan document with `## Acceptance Criteria`, read the criteria and confirm each was implemented.
   - Confirm it stayed within its file footprint — spot-check `git diff --name-only` against the declared footprint. **File footprint violations are bugs in the parallelism plan, not just agent misbehavior** — if an agent needed a file outside its footprint, the Phase 2 analysis missed a dependency.
   - Commit its changes immediately. Stage everything, brief message. The post-commit hook handles push.
   - **Mark complete + tracker sweep:** Update task via TaskUpdate. **Re-run the canonical tracker sweep** — update every match to reflect completion. If the executor ran its own sweep, verify; fix gaps.

3. **Wave gate:** ALL items in a wave must complete before the next wave begins. This is the serialization point that guarantees later-wave items see earlier-wave changes.

4. **Brief status update between waves:** "Wave N complete ([items]). Firing wave N+1 ([items])." Output-only — never frame as a question, never wait for a response. Never output:
   - "Want me to fire those now?" — Just fire them.
   - "Ready for the next batch?" — Just start it.
   - "Should I proceed with X or Y first?" — This was decided in Phase 2.

**Single-item waves** (forced sequential due to file overlap or dependencies) execute inline — dispatch overhead isn't worth it for one item. Follow the same write-ahead → execute → verify → commit → mark-complete cycle.

**Dispatch model:** Enriched specs with code sketches are blueprints — Sonnet follows them; Opus judgment was already spent during enrichment+review. See `/delegate-execution` Phase 2 for the full model selection rubric. The coordinator's job during execution is verification and wave gating, not typing code.

**No worktrees.** All executors operate on the same worktree. The file-disjoint constraint from Phase 2 is the coordination mechanism. Do not use `isolation: "worktree"` on any executor dispatch.

### Phase 6: Tail — Close Out the Run

After all waves are executed and verified, mark all item tasks `completed` via TaskUpdate, clean up the autonomous-run sentinel, then run the final tracker sweep before the tail action:

```bash
rm -f /tmp/autonomous-run-${SESSION_ID}
```

**Final tracker sweep (mandatory before tail):**
Before invoking `/update-docs`, verify that ALL canonical trackers reflect the run's outcomes. This is the EM's backstop — especially critical because nobody is watching during autonomous runs:
1. Grep each completed item's codename across `docs/project-tracker.md`, `tasks/*/todo.md`, `ROADMAP.md`, and any dispatch trackers
2. Confirm every completed item shows as done/checked in every tracker that references it
3. Confirm every in-progress or blocked item shows its current state
4. Fix any gaps — executors may have crashed before completing their sweep, or the EM's own inline execution may have skipped it under time pressure
5. Commit tracker fixes (if any) before proceeding to `/update-docs`

This sweep is the difference between "work got done" and "the project knows work got done." `/update-docs` will cascade tactical completions upward via tracker-maintenance, but only if the tactical trackers are accurate.

**Standard (default):**
1. Invoke `/update-docs` — sync documentation, commit, push to branch
2. Done. The PM can invoke `/workday-complete` separately when ready to merge.

**Hibernate:**
1. Invoke `/update-docs --no-distill` — sync documentation, commit, push to branch. Skip distillation in overnight mode — it requires PM approval and nobody is home.
2. Verify push succeeded (work must be on remote before hibernating)
3. Hibernate the machine:

```bash
# Windows
shutdown /h

# Linux/Mac
systemctl hibernate
```

Hibernate over shutdown: same zero power draw, but the machine resumes to its prior state instead of cold-booting.

**If `/update-docs` fails in hibernate mode:** Hibernate anyway. Item-level commits from Phase 5 already preserved the work. Doc sync is nice-to-have; power conservation is the priority. The PM can run `/update-docs` after wake.

## Safety Boundaries

- **Never merge to main.** Work stays on branch. The PM merges interactively after review, using `/merge-to-main` or `/workday-complete`.
- **Never use worktrees.** All executors operate on the same worktree. File-disjoint wave scheduling is the coordination mechanism. Worktree creation + merge overhead exceeds the time saved at agent execution speed.
- **Never hibernate without explicit PM request.** Hibernate mode is opt-in only — detected from `$ARGUMENTS`, never escalated unilaterally.
- **Never escalate tail mode.** Standard → hibernate is the PM's call. Do not suggest it, do not ask about it.
- **Hibernate is always safe on early stop.** If hibernate mode was invoked and the run must stop early, hibernate anyway. Incomplete work on a branch + hibernated machine is strictly better than incomplete work + machine running all night.
- **Commit after every item.** Crash insurance. Applies to dispatched executors too — their work is not done until it is committed.
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
- **Agent recovery** — rate-limited agents, crashed agents, auth failures, partial commits, uncommitted code on disk, missing subsystem registrations. These are routine operational handling. Re-dispatch, audit partials, finish the work, commit. Never frame "we have N uncommitted workstreams, want me to recover them?" as a choice — recovery IS the work the PM authorized. Asking an EM whether to finish tractable, scoped, roadmap-aligned work is a failure of the role.
- **Concurrent-session churn** — another session's commits sweeping your staged changes, attribution splits, shared-file merges. Use targeted `git commit -m "..." -- <paths>` and continue.
- **Subsystem registration gaps** — if a handler file is on disk but `Subsystem.h`/`.cpp` doesn't register it, that's a routine finish-the-work case, not a PM question.

**If you must stop early:**
1. Commit all current work — even partial progress. Stage the paths in the flight recorder's working set (the discrete steps and files tracked in your Tasks API flight recorder), then commit via the scoped helper: `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "<subject>"`. Do not use `git add -A`.
2. Update tasks via TaskUpdate with where you stopped and why, including which items remain.
3. Update any plan documents with current status.
4. Verify the branch is on remote (post-commit hook should have handled it — confirm).
5. **If hibernate mode was invoked:** Hibernate anyway. The PM will see the incomplete run on the branch on wake. Safe — work is on a branch, not main.
6. **If standard mode:** Stop. The PM will see the state in the task list and on the branch.

## Failure Modes

| Situation | Action |
|-----------|--------|
| Item spec ambiguous at multiple decision points | Stop early (see above) |
| Verification fails with a fixable error | Fix and continue — do not escalate |
| Verification fails structurally | Stop early, commit progress |
| Dispatched executor returns BLOCKED | Diagnose — if spec-fixable, update stub and re-dispatch; if architectural, stop early and report |
| Executor writes outside its file footprint | Bug in Phase 2 analysis — revert the out-of-bounds changes, re-analyze the overlap, adjust wave assignments, and re-execute |
| `/update-docs` fails in standard mode | Report the failure, leave work on branch |
| `/update-docs` fails in hibernate mode | Hibernate anyway — item commits already pushed |
| Push fails before hibernate | Do NOT hibernate — work must be on remote first. Stop and report. |
| Context compacted mid-run | Read goal task and per-item tasks via TaskList/TaskGet to re-orient; check `metadata.tried_and_abandoned`; continue from `in_progress` item |

## Relationship to Other Commands

- **`/delegate-execution`** — used within Phase 5 for dispatching executor agents; its Phase 2 model selection rubric governs dispatch decisions
- **coordinator:dispatching-parallel-agents** — parallel dispatch patterns (file-disjoint constraint, same-worktree coordination)
- **`/update-docs`** — the tail action in both modes; invoked at Phase 6
- **`/workday-complete`** — what the PM runs afterward (interactively) if they want end-of-day consolidation and health survey
- **`/merge-to-main`** — what the PM runs when ready to merge the branch; never invoked from this command
- **`pipelines/mise-en-place/PIPELINE.md`** — the pipeline definition this command executes; consult it for full nuance on any phase
