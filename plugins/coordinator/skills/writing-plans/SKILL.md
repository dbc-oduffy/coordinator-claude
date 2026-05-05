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

## Scope Mode (required header field)

Every plan declares one scope mode. The mode shapes review depth, acceptable tradeoffs, and what counts as "done." Don't skip — pick one before drafting tasks.

| Mode | Use when | Rules | Evidence bar |
|------|----------|-------|--------------|
| **prototype** | Learning, demo, throwaway | Mark shortcuts; prefer reversible changes; no broad refactors unless forced | Demo path + known-limitations list |
| **production-patch** | Small safe fix, bug | Minimal diff; no opportunistic refactors; preserve existing behavior unless explicitly changed | Targeted tests + reviewer + low blast radius |
| **feature** | User-visible work | Acceptance criteria required; demo path required; product-risk review required | Acceptance criteria satisfied or explicitly waived |
| **architecture** | Structural/cross-cutting change | Alternatives considered; migration + rollback plan; blast-radius analysis; staff-session likely | Tests + architectural review + risk ledger |
| **spike** | Discovery, "is this feasible?" | Throwaway code allowed; answer the learning question; do not polish unless asked | Findings + recommendation + next step |

If you can't pick confidently, the scope is under-specified — push back to the PM (see "Definition of Ready" below) before drafting tasks.

## Definition of Ready (pre-drafting gate)

Before writing tasks, confirm each item or explicitly waive it. If multiple are missing, recommend brainstorming or a spike instead of a plan.

- [ ] **Product objective** is one clear sentence.
- [ ] **User/stakeholder** is identified (who benefits, who's affected).
- [ ] **Acceptance criteria** are testable.
- [ ] **Non-goals** are explicit (what this *won't* do, to head off scope creep).
- [ ] **Scope mode** is selected (see table above).
- [ ] **Open product decisions** are resolved or intentionally deferred — not hidden inside an implementation request.
- [ ] **Verification method** is known (tests? manual demo? both?).

If two or more checkboxes can't be filled honestly, the plan isn't ready. Surface to the PM with a specific ask, not a draft full of TBDs.

## Domain Language

Read `CONTEXT.md` if present at the project root; if absent, proceed silently — do not flag, suggest, or scaffold. Use canonical terms throughout the plan — and for any term on the `_Avoid_:` lists, substitute the canonical term silently. If the plan introduces a new domain term that will recur across sessions, append it to `CONTEXT.md` as part of the plan-writing pass.

## Codebase Research (before file mapping)

<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
**Project-rag is project-scoped.** It indexes ONE specific codebase, configured at install time. Before reaching for `mcp__*project-rag*` tools, confirm they index the codebase you're investigating — not a different project on the same machine. If your target codebase doesn't have a project-rag index (no `Saved/ProjectRag/` marker at its root, no `--project-root` argument pointing at it in the MCP config), skip this preamble entirely and use grep/Explore.

**If MCP tools matching `mcp__*project-rag*` are available AND they index the codebase you're investigating, prefer them over grep/Explore for any code-shaped lookup.** Symbol-shaped questions ("where is X defined", "find the function that does Y") → `project_cpp_symbol` / `project_semantic_search`. Subsystem-shaped questions ("how does X work") → `project_subsystem_profile`. Impact questions ("what breaks if I change X") → `project_referencers` with depth=2. Stale RAG still beats grep on structure. Fall through to grep/Explore only if RAG returns nothing AND staleness is plausible.
<!-- END project-rag-preamble -->

Before defining the file structure, check what's already been documented about the relevant systems. Read these if they exist (skip silently if they don't):

1. `tasks/architecture-atlas/systems-index.md` → relevant system pages in `tasks/architecture-atlas/systems/`
2. `docs/wiki/DIRECTORY_GUIDE.md` → relevant wiki guides in `docs/wiki/`
3. `tasks/repomap.md` (or task-scoped variant)

This gives you the structural context to make informed file-mapping decisions without redundant grep discovery. Use Glob/Grep after this to fill specific gaps — exact line numbers, recent additions not yet in the atlas, etc.

## Negative-Search Before Drafting

Before committing to a prescribed shape, run a negative search to surface prior decisions that argue against what the plan proposes to introduce or restore.

1. **Identify the central nouns/abstractions** the prescription introduces or restores (e.g., a pattern name, an architectural layer, a specific tool or verb).

2. **Search for those nouns paired with prohibition vocabulary.** Grep `tasks/lessons.md` and `docs/wiki/` for each noun alongside: `do not`, `never`, `tear down`, `deprecated`, `forbidden`, `removed`, `do NOT`. `bin/query-records` is also useful here for frontmatter-indexed records.

3. **If a prohibition exists, the plan must do one of two things:**
   - **(a)** Acknowledge the prior decision in §1 Objective and explicitly justify the reversal — with reasoning that engages the original argument, not merely reasserts the new direction.
   - **(b)** Recuse the prescription and choose a different shape that does not conflict with the prior decision.

4. **Reversal-verb hint:** If §1 Objective uses any of `restore`, `reintroduce`, `reconstitute`, `undo`, `re-add`, or `bring back`, the plan author should *consider suggesting* a staff-session to the PM before approval. This is a suggestion only — the PM owns the call. Frame it as: "This plan reverses prior direction; PM may want a staff-session before approving execution."

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

**Scope mode:** [prototype | production-patch | feature | architecture | spike]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

## Acceptance Criteria

- [ ] [Testable criterion 1]
- [ ] [Testable criterion 2]
- [ ] [Testable criterion 3]

## Non-Goals

- [Explicitly out of scope — heads off mid-stream scope creep]

---
```

**Why these fields are required:**
- **Scope mode** routes review depth and the evidence bar. Reviewers and `/merge-to-main` read it.
- **Acceptance criteria** are what reviewers check against and what the ship verdict scores. Without them, "done" reduces to "the agent says it implemented it."
- **Non-goals** are the most-skipped field and the single highest source of scope drift. Spend 30 seconds on them.

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

## Shared-State Pre-Flight Gate

Before a plan changes the semantics of a shared symbol — a state enum, gameplay tag, public field, or exported function signature — include a reverse-reference scan in the plan: list every consumer found via grep, IDE rename-preview, or equivalent tool. Plans that mutate shared contracts without enumerating consumers are incomplete and risk silent breakage across subsystems with no obvious compile-time signal.

**Checklist:** For each shared symbol the plan mutates, add a subsection that names every file/component that reads or depends on it. If the scan is non-trivial, make it an explicit plan step, not an assumption.

## Data Before Dispatch

Before writing a plan or dispatching agents on a debugging or fix task, identify and run the smallest diagnostic that exposes ground truth — a test runner, curl probe, `git show`, or single inspect call. Target: < 60 seconds. This is the cheapest step in any plan and prevents hours of hypothesis-driven agent rework.

**Framing rule:** Hypothesis-driven dispatch without diagnostic data is a stuck-detection trigger. If you find yourself writing a plan section that says "the cause is probably X," stop and run the diagnostic first. (geneva T1.2, paired across writing-plans + systematic-debugging)

## Hard Constraints for Executor-Bound Plans

These apply to any plan that will be handed to an executor agent. Violations here are the most common source of scope bleed and unauthorized work.

### (a) Executor specs must include explicit file-scope constraints

"Restructure the cheatsheets" or "fix the auth module" is insufficient — an executor without a scope constraint will modify adjacent files, run scripts, and create unauthorized commits. Every executor-bound stub MUST include a constraint block:

```markdown
**Scope constraint:** Only edit files matching `<pattern>`. Do NOT modify files outside that scope. Do NOT run scripts beyond `<allowed list>`. Do NOT create commits.
```

Name the allowed paths explicitly. If the stub says "update the config files," list them by path — don't rely on the executor to infer scope.

### (b) Orchestrator agents in plans must be read-only planners

The Agent tool is single-level nesting — subagents cannot spawn further subagents. When a plan calls for an agent that decomposes work and "dispatches sub-tasks," that agent MUST be configured as a read-only planner:

- No `Agent` tool in its `allowed-tools`
- No `execute-*` tools either (omni-tool gravity: if the tool is present, the agent will use it)
- Sub-task dispatch happens back at the EM level, not nested inside the orchestrator

If a plan step says "an orchestrator agent will analyze and dispatch," rewrite it: "orchestrator agent analyzes and returns a briefing; EM dispatches sub-tasks based on briefing."

### (c) Cross-plan reconciliation is a separate pass

When plan A depends on plan B — shared paths, asset names, API contracts — a reviewer of A in isolation cannot see contradictions with B. Plans that interlock require an explicit cross-plan reconciliation step:

- Read both plans' cross-references side by side
- Verify mount paths, asset names, and assumed APIs align
- Document any conflicts before execution begins

**In the plan document itself:** If interlocking plans exist, add a `**Depends on:**` line in the header and a reconciliation checklist as the final pre-execution step. Do not leave this implicit.

### (d) Tool resolution in teammate prompts

When a plan step dispatches a teammate agent that needs MCP tools, use graduated ToolSearch in the teammate's prompt — never hardcode a single tool name prefix. MCP tool names vary across teammate spawn contexts (e.g., `mcp__notebooklm__*` vs `mcp__plugin_notebooklm_notebooklm__*`).

**Graduated resolution order:** `select:exact` → `+prefix` keyword fallback → graceful failure message. Any teammate prompt that names an MCP tool should follow this pattern; hardcoding a single prefix is a silent failure waiting for the next spawn context change.


## Lessons Learned

**Default to subagent dispatch over a new RPC verb when *adding* internal operations.** When a plan proposes a new tool/verb/handler/CLI-job, ask first: can a subagent compose this from existing primitives via `execute_python_code` + `inspect` + extant MCP verbs? If yes, the plan should propose the dispatch path, not the new verb. The new verb earns its place only on (a) C++-only capability, (b) transactional state coupling that primitive composition cannot preserve, or (c) cross-call editor-state invisible in tool signatures. **Never default to dispatch over an existing verb without explicit retire-justification** — prior surface is the proven path.

Tag: `[universal]` — applies to any project_type using the coordinator pipeline.

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
