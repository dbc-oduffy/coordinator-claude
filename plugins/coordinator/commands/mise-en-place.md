---
description: Autonomous backlog execution — gathers all ready work items, builds a compaction-proof flight recorder, executes sequentially without stopping for input, then tails with /update-docs (or /update-docs + hibernate in overnight mode)
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[--hibernate]"
---

# Mise-en-Place — Autonomous Backlog Execution

Everything in its place before the fire gets lit. This command front-loads all context gathering and sequencing into a compaction-proof flight recorder, then executes the full backlog in a straight shot without stopping for input. The PM authorized the run when they invoked this command.

**Core principle:** Prep all context, sequence all items, build the flight recorder — then execute without interruption. Once Phase 5 begins, the EM never pauses to ask a question, offer a choice, or wait for a response. The anti-stall rule is not optional: if execution stalls mid-run, the tail phase (hibernate) never triggers, leaving the machine running indefinitely.

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

### Phase 2: Sequence — Order of Operations

Sort items by dependency order, then by complexity (smaller items first to build momentum, unless dependencies dictate otherwise).

Identify:
- **Independent items** that could theoretically be parallelized (note but don't act yet — see dispatch threshold in Phase 5)
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

**Items queued:** [N items]
[Numbered list with identifiers and one-line descriptions]

**Sequence:** [any dependency or risk notes]
**Tail:** /update-docs — straight shot, work stays on branch.
[or: /update-docs + hibernate — overnight run, work stays on branch.]

**Estimated scope:** [rough sense of the run — "3 small items + 1 medium" etc.]

Proceeding.
```

The tail line is the EM's confirmation of mode — stated declaratively, not as a question. This is a launch announcement, not a proposal. The PM may already be away from the terminal. Do not frame it as "Ready to execute — shall I proceed?" Just output the announcement and start Phase 5.

### Phase 5: Execute — The Straight Shot

For each item in the sequenced order:

1. **Write-ahead:** Mark item `in_progress` via TaskUpdate. Update the plan document status if applicable.
2. **Execute:** Follow the spec. Use `/execute-plan` patterns for plan-based items, or direct implementation for simpler items.
3. **Verify:** Run the verification method identified in Phase 1. Apply `coordinator:verification-before-completion` — evidence before claims.
4. **Spec-check:** If the item has an enriched stub or plan document with `## Acceptance Criteria`, read the criteria and confirm each was implemented. For items without formal acceptance criteria (simple backlog items, one-liners), skip — the verification in step 3 suffices.
5. **Commit:** Commit at completion of each item. Stage everything, brief message. The post-commit hook handles push.
6. **Mark complete:** Update task via TaskUpdate. Update the plan document if applicable.
7. **Brief status update:** One line — "[Item X] complete, moving to [Item Y]." Output-only. These are progress breadcrumbs, not check-ins. Never output:
   - "Want me to fire those now?" — Just fire them.
   - "Ready for the next batch?" — Just start it.
   - "Should I proceed with X or Y first?" — This was decided in Phase 2.
8. **Proceed immediately** to the next item.

**Dispatch threshold:** Boilerplate-heavy independent items get dispatched to Sonnet executor agents — the enrichment pipeline was designed so execution is cheap. Items benefiting from accumulated context (coherence decisions, cross-file awareness) stay in-coordinator. See `/delegate-execution` Phase 2 for the full model selection rubric.

### Phase 6: Tail — Close Out the Run

After all items are executed and verified, mark all item tasks `completed` via TaskUpdate, then execute the tail action:

**Standard (default):**
1. Invoke `/update-docs` — sync documentation, commit, push to branch
2. Done. The PM can invoke `/workday-complete` separately when ready to merge.

**Hibernate:**
1. Invoke `/update-docs` — sync documentation, commit, push to branch
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
- **Never hibernate without explicit PM request.** Hibernate mode is opt-in only — detected from `$ARGUMENTS`, never escalated unilaterally.
- **Never escalate tail mode.** Standard → hibernate is the PM's call. Do not suggest it, do not ask about it.
- **Hibernate is always safe on early stop.** If hibernate mode was invoked and the run must stop early, hibernate anyway. Incomplete work on a branch + hibernated machine is strictly better than incomplete work + machine running all night.
- **Commit after every item.** Crash insurance. Applies to dispatched executors too — their work is not done until it is committed.
- **Write-ahead status on everything.** If the session dies, the plan shows exactly where execution stopped.
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

**If you must stop early:**
1. Commit all current work — even partial progress. Stage everything.
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
| `/update-docs` fails in standard mode | Report the failure, leave work on branch |
| `/update-docs` fails in hibernate mode | Hibernate anyway — item commits already pushed |
| Push fails before hibernate | Do NOT hibernate — work must be on remote first. Stop and report. |
| Context compacted mid-run | Read goal task and per-item tasks via TaskList/TaskGet to re-orient; check `metadata.tried_and_abandoned`; continue from `in_progress` item |

## Relationship to Other Commands

- **`/delegate-execution`** — used within Phase 5 for boilerplate-heavy independent items; its Phase 2 model selection rubric governs executor dispatch
- **`/update-docs`** — the tail action in both modes; invoked at Phase 6
- **`/workday-complete`** — what the PM runs afterward (interactively) if they want end-of-day consolidation and health survey
- **`/merge-to-main`** — what the PM runs when ready to merge the branch; never invoked from this command
- **`pipelines/mise-en-place/PIPELINE.md`** — the pipeline definition this command executes; consult it for full nuance on any phase
