---
description: Execute a PM-approved implementation plan directly in the coordinator session
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — Direct In-Session Plan Execution

Run a PM-approved implementation plan to completion without stopping for permission between tasks. The PM's approval of the plan is the authorization — this command executes it diligently and in its entirety, then tails with the `coordinator:finishing-a-development-branch` skill.

**Core principle:** Write-ahead every task (both plan document on disk AND task list via TaskUpdate), execute autonomously, stop only when your judgment says the plan itself is in trouble — not when a task is merely hard.

**When to use `/delegate-execution` instead:** If the plan contains enriched stubs with known file paths, exact line numbers, and code sketches, dispatch Sonnet executors via `/delegate-execution` — execution is cheap when the blueprint is complete. Use `/execute-plan` for plans that require EM-level judgment, have accumulated conversation context, or are mid-size with straightforward steps that don't need separate executor dispatch.

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
4. **If no concerns:** Announce _"I'm running `/execute-plan` to implement this plan."_ and continue to Phase 2.

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

## Phase 4: Finish the Branch

After all tasks are complete and verified:

Announce: _"I'm using the coordinator:finishing-a-development-branch skill to complete this work."_

Invoke the `coordinator:finishing-a-development-branch` skill. Follow it exactly — it verifies tests, presents the 4 structured options, and executes the PM's choice. This is a required sub-skill, not optional.

---

## Failure Modes

| Situation | Action |
|---|---|
| Plan path not provided | Report usage and stop |
| Plan file not found | Report the path that was tried and stop |
| Plan has no concerns but looks unreviewed | Surface the observation; proceed only if PM confirms |
| Task fails with fixable error (type error, import, lint) | Fix immediately, continue |
| Task fails with structural error after 2 attempts | Stop, record what was tried, consult PM |
| Verification step in plan fails | Stop and report — do not skip verifications |
| Plan's approach is invalidated mid-execution | Stop, record `Tried/Failed`, flag for PM to update plan |
| Tests fail at Phase 4 (finishing) | The `finishing-a-development-branch` skill owns this — follow its protocol |

---

## Relationship to Other Commands

- **`/delegate-execution`** — use this instead when the plan consists of enriched stubs with exact code sketches, file paths, and line numbers. Executor dispatch is cheaper for well-specified mechanical work. `/execute-plan` is for EM-level execution where conversation context or judgment matters.
- **`/enrich-and-review`** — should be run before `/delegate-execution`; not required before `/execute-plan` (plans that route here are typically less chunked).
- **`/review-dispatch`** — optional post-execution quality pass on the implemented work. If the plan called for it, route through `/review-dispatch` before invoking the finishing skill.
- **`coordinator:writing-plans`** — creates the plan that this command executes. A plan produced by that skill is the ideal input here.
- **`coordinator:finishing-a-development-branch`** — always invoked at the end of this command. Not optional.
