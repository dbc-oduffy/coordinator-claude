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

## When to Use

- You have 2+ thoroughly-scoped work items ready for execution (plan stubs, enriched specs, well-defined tasks)
- The items are sequentially executable — each can be completed before moving to the next
- The PM wants autonomous execution with minimal interruption
- The PM wants the backlog cleared — whether they're watching, stepping away, or wrapping up for the day

**Don't use when:**
- Items aren't scoped yet — use `coordinator:writing-plans` or `coordinator:brainstorming` first
- Only one item to execute — use `/execute-plan` directly
- The work requires iterative PM judgment calls throughout

## The Process

### Phase 1: Inventory — What's on the Board?

Gather every ready-to-execute work item. Sources to check:

1. **Plan files:** `tasks/*/todo.md` — items marked ready/pending execution
2. **Enriched stubs:** Any chunk directories with status "Enriched" or "Reviewed"
3. **PM's explicit list:** If the PM named specific items (e.g., "PX4-6B through Cesium-D"), use that as the canonical list
4. **Open tasks:** Any `tasks/*/` directories with incomplete work

For each item, capture:
- **Identifier** (stub name, plan reference, or short description)
- **Location** (file path to spec/plan)
- **Dependencies** (does it need another item completed first?)
- **Estimated complexity** (quick read of the spec — small/medium/large)
- **Verification method** (how will you know it's done?)

### Phase 2: Sequence — Order of Operations

Sort items by dependency order, then by complexity (smaller items first to build momentum, unless dependencies dictate otherwise).

Identify:
- **Independent items** that could theoretically be parallelized (note but don't act yet)
- **Sequential chains** where one item's output feeds the next
- **Risk items** that might block the run if they fail

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

Ready to execute the full sequence. Proceeding unless you stop me.
```

The tail line is the EM's confirmation of mode — stated declaratively, not as a question. If the PM didn't specify hibernate, default to `/update-docs` and move on.

This is a launch announcement, not a proposal. Output it and immediately begin Phase 5. Do NOT wait for a response — the PM may already be away from the terminal.

### Phase 5: Execute — The Straight Shot

For each item in sequence:

1. **Write-ahead:** Mark item `in_progress` via TaskUpdate. Update plan document status if applicable.
2. **Execute:** Follow the spec. Use `/execute-plan` patterns for plan-based items, or direct implementation for simpler items.
3. **Verify:** Run the verification method identified in Phase 1. Apply `coordinator:verification-before-completion` — evidence before claims.
4. **Commit:** Commit at completion of each item. Stage everything, brief message. The post-commit hook handles push.
5. **Mark complete:** Update task via TaskUpdate. Update plan document if applicable.
6. **Brief status update:** One line — "[Item X] complete, moving to [Item Y]." Output-only — do NOT frame as a question, do NOT offer choices, do NOT wait for a response. Examples of what NEVER to output:
   - ~~"Want me to fire those now?"~~ — Just fire them.
   - ~~"Ready for the next batch?"~~ — Just start it.
   - ~~"Should I proceed with X or Y first?"~~ — You already sequenced this in Phase 2.
7. **Proceed immediately** to the next item. No pause, no polling for input.

**Dispatch threshold:** If an item is boilerplate-heavy and independent, dispatch to a Sonnet executor agent. Enriched specs with code sketches are blueprints — Sonnet follows them; Opus judgment was already spent during enrichment+review. Prefer sequential coordinator execution for items that benefit from accumulated context. See `/delegate-execution` Phase 2 for the full model selection rubric.

### Phase 6: Tail — Close Out the Run

After all items are executed and verified, mark all item tasks as `completed` via TaskUpdate, then execute the tail action based on mode:

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
- **coordinator:dispatching-parallel-agents** — If independent items can be parallelized
- **coordinator:using-git-worktrees** — If items need isolated workspaces

**Called by:** PM directly — whether they're watching, stepping away, or wrapping up for the day

**Pairs with:**
- **coordinator:writing-plans** — Creates the scoped items this skill executes
- **`/session-start`** — Often follows session-start when the PM reviews the backlog and decides to straight-shot it
