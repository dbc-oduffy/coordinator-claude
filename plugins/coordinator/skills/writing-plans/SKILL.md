---
name: writing-plans
description: "This skill should be used when requirements are clear and the task needs decomposition into executable chunks — before touching code. Triggers on: 'write a plan', 'break this down', 'plan the implementation'."
version: 1.0.0
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## File Structure

Before defining tasks, map out which files will be created or modified and what each is responsible for:

- Design units with clear boundaries and well-defined interfaces
- Prefer smaller, focused files over large ones doing too much
- Files that change together should live together — split by responsibility, not technical layer
- In existing codebases, follow established patterns; include splits for unwieldy files when reasonable

This structure informs task decomposition — each task should produce self-contained changes.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Status:** Pending review

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

The `Status:` field is part of the write-ahead protocol — it gets updated at every phase transition (review, enrichment, execution) so that crashed sessions leave unambiguous state. See ARCHITECTURE.md § "The Write-Ahead Status Protocol" for the full state machine.

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits

## Plan Review Gate (Mandatory)

After saving the plan, it MUST go through one review cycle before execution. This catches structural problems while they're cheap to fix — before enrichment and execution invest real work.

1. Route the plan through `/review-dispatch` — the plan document is the artifact
2. **Dispatch the review-integrator agent** to apply findings to the plan. Do not integrate findings manually — the review-integrator handles this. Your job after dispatch:
   - Review the integrator's escalation list (usually 0 items)
   - Spot-check the diff to verify findings were applied correctly
   - If you disagree with how a finding was applied, change that specific part — don't re-integrate the whole review yourself
   - Only skip integration of an item if: (a) requires PM input, or (b) you genuinely disagree (flag to PM with reasoning)
3. Add a review status marker to the plan document header:

```markdown
**Review:** Reviewed by [reviewer name] on [date]. Ready for execution.
```

4. Only after review is complete, proceed to the execution handoff below.

**PM Override:** If the PM explicitly says to skip review (e.g., "ship it", "straight to execution"), skip this gate and note in the header:

```markdown
**Review:** Skipped per PM direction. Proceed to execution.
```

## Execution Handoff

After the plan is reviewed (or review is explicitly skipped), offer execution choice:

**"Plan reviewed and saved to `docs/plans/<filename>.md`. Two execution options:**

**1. Executor-Driven (this session)** - I dispatch Executor agents per task via `/delegate-execution`, code review via `/review-dispatch` between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session and run /execute-plan, batch execution with checkpoints

**Which approach?"**

**If Executor-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use `/delegate-execution` to dispatch Executor agents
- Stay in this session
- Fresh Executor agent per task + code review via `/review-dispatch`

**If Parallel Session chosen:**
- Guide them to open new session in worktree
- **REQUIRED SUB-SKILL:** New session uses /execute-plan
