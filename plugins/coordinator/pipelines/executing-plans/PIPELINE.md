# Executing Plans

> Referenced by `/execute-plan`. This is a pipeline definition, not an invocable skill.

## Overview

Load plan, review critically, execute tasks in batches, report for review between batches.

**Core principle:** Batch execution with checkpoints for architect review. If running in a Coordinator session, prefer executor-driven dispatch via `/delegate-execution` for better review integration.

**Announce at start:** "I'm running `/execute-plan` to implement this plan."

## The Process

### Step 1: Load and Review Plan
1. Read plan file
2. Review critically — identify any questions or concerns about the plan
3. If concerns: Raise them with your human partner before starting
4. If no concerns: Create task list (TaskCreate) and proceed

### Step 2: Execute Through the Entire Plan

**Default behavior: execute all tasks in sequence without stopping to ask permission between them.**

For each task:
1. **Write-ahead: Update the plan document itself** — mark the current phase/task as "In progress (started YYYY-MM-DD HH:MM)" in the plan file on disk. This is crash insurance — if the session dies, the plan shows where execution stopped rather than misleading "not started." Update task list via TaskUpdate simultaneously.
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. **Mark completed in both the plan document AND task list** — update the plan file to show "Complete (YYYY-MM-DD HH:MM)" for the task, and mark `completed` via TaskUpdate
5. Proceed immediately to the next task

Do NOT pause between tasks to ask "should I proceed?" or "ready for feedback?" — the PM authorized the plan when they approved it. Your job is to execute it diligently and in its entirety.

**Brief status updates** are fine at natural milestones (e.g., "Phase 2 complete, moving to Phase 3") but these are informational, not permission requests.

### Step 3: Complete Development

After all tasks complete and verified:
- Announce: "I'm using the coordinator:finishing-a-development-branch skill to complete this work."
- **REQUIRED SUB-SKILL:** Use coordinator:finishing-a-development-branch
- Follow that skill to verify tests, present options, execute choice

## When to Stop and Reassess

**Stop executing and consult the PM when, in your best judgment, there is genuine cause:**

- **Accumulating patches** — you've made 2+ workarounds or "good enough" fixes that suggest the plan's approach is off. Step back before the debt compounds.
- **Ambiguity is spreading** — a gap in the spec has infected multiple tasks, and continuing means guessing at each one. Get clarity before proceeding.
- **Verification fails structurally** — not a typo or import fix, but repeated failures that suggest the approach is wrong.
- **Scope surprise** — the work is significantly larger, riskier, or more invasive than the plan anticipated.
- **Breaking change discovered** — something in the codebase has changed since the plan was written that invalidates assumptions.
- **Recording what failed:** When you stop and reassess, record in both the plan document AND the task's `metadata.tried_and_abandoned` field (via TaskUpdate) what approach was tried and why it failed. Format: "Tried: [approach] — Failed: [reason]". This prevents future sessions or post-compaction agents from retrying the same dead end.

**Do NOT stop for:**
- Routine fixable errors (type errors, missing imports, lint failures) — fix them and move on
- Minor ambiguity you can resolve with one reasonable judgment call — make the call, note it in your completion report
- Feeling uncertain about the next task — read it, understand it, execute it
- Wanting to "check in" — that's not a reason to interrupt the PM's flow

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Execute autonomously through the full plan — don't stop for permission
- Stop when your judgment says the plan itself is in trouble, not when a task is merely hard
- Never start implementation on main/master branch without explicit user consent

## Integration

**Required workflow skills:**
- **superpowers:using-git-worktrees** - Use when branch-level isolation is needed (separate PRs, different base branches). NOT required for single-branch sequential execution — work directly in the current worktree.
- **coordinator:writing-plans** - Creates the plan this skill executes
- **coordinator:finishing-a-development-branch** - Complete development after all tasks
