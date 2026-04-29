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

**Todo Emission:** Alongside every plan, emit `tasks/<feature-name>/todo.md` using the template at `coordinator/skills/writing-plans/feature-todo-template.md`. Update `todo.md` at task transitions — not at end of session.

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## Codebase Research (before file mapping)

Before defining the file structure, check what's already been documented about the relevant systems. Read these if they exist (skip silently if they don't):

1. `tasks/architecture-atlas/systems-index.md` → relevant system pages in `tasks/architecture-atlas/systems/`
2. `docs/guides/DIRECTORY_GUIDE.md` → relevant wiki guides in `docs/guides/`
3. `tasks/repomap.md` (or task-scoped variant)

This gives you the structural context to make informed file-mapping decisions without redundant grep discovery. Use Glob/Grep after this to fill specific gaps — exact line numbers, recent additions not yet in the atlas, etc.

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

## Plan Document Format (v2 Template)

**Every plan MUST use the v2 template** at `coordinator/skills/writing-plans/plan-template-v2.md`.

The template includes:
- **YAML frontmatter** (`confidence`, `status`) — the single source of truth for machine-readable plan state.
- **Prose `**Status:**` and `**Confidence:**` lines** — human-readable mirrors of the frontmatter values.
- **Six required sections:** `## Assumptions`, `## Verified Facts`, `## Open Questions (Blocking)`, `## Open Questions (Non-blocking)`, `## Risks`, `## Execution Phases`.

**Confidence values:** `Low` / `Medium` / `High` — always accompanied by a one-line rationale (e.g., "minimal project context" or "all key files read, API signatures confirmed").

**Status values (frontmatter enum):**
- `draft` — plan being written or under review; not ready for execution.
- `ready` — enriched, reviewed, all blocking questions resolved; ready for executor dispatch.
- `executing` — executor sessions active or partially complete.
- `done` — all phases complete.

The `Status:` prose line is part of the write-ahead protocol — it gets updated at every phase transition (review, enrichment, execution) so that crashed sessions leave unambiguous state. The frontmatter `status` field is the authoritative machine-readable value; `/update-docs` reads it. If both exist and conflict, frontmatter wins and the prose line is rewritten to match.

**Prose → enum mapping table** (used by `/update-docs` Phase 3 when reading legacy v1 plans without frontmatter):

| Prose `**Status:**` string (examples) | Frontmatter enum |
|---------------------------------------|-----------------|
| "Pending review" | `draft` |
| "APPROVED_WITH_NOTES — ready for enrichment" | `draft` |
| "Enriched — pending review" | `draft` |
| "Ready for executor dispatch" | `ready` |
| "Execution complete — Wave N pending …" | `executing` |
| "Complete" / "Done" | `done` |

## v1 → v2 Workflow

Plan writing follows a two-version lifecycle. The version is captured in the filename suffix, not in the frontmatter (filename is canonical; `/update-docs` can derive version from filename regex if needed).

**Write v1 (draft, low confidence):**
- `confidence: low` in frontmatter.
- All unverified items live in `## Assumptions` — nothing hidden inside implementation prose.
- At least one blocking question listed in `## Open Questions (Blocking)`.
- `status: draft`.
- Save as `docs/plans/YYYY-MM-DD-feature-v1.md`.

**When blocking questions exist:** dispatch enrichers (or the EM resolves via codebase research) to verify assumptions and answer blocking questions. Do not advance to v2 until `## Open Questions (Blocking)` is empty.

**Write v2 (verified, medium-or-higher confidence):**
- `confidence: medium` minimum (use `high` when all major unknowns are resolved).
- `## Verified Facts` populated with evidence — e.g., "FooClass::Bar exists at Source/Foo.h:42".
- `## Open Questions (Blocking)` is empty (all resolved).
- `## Risks` is filled with specific context: `[domain context] → [failure mode] → [detection method]`. Vague risks ("might break something") are not acceptable.
- `## Execution Phases` present with gate markers.
- `status: ready`.
- Save as `docs/plans/YYYY-MM-DD-feature-v2.md`.

**Version naming and rollover:**
- v1 is never overwritten — it is the epistemic record of what was assumed before verification.
- v1 → v2 is the assumption-to-verified transition. Post-execution amendments beyond v2 are rare.
- If a material architectural change is discovered mid-execution, start a new plan file rather than creating v3. The filename suffix increments with each new file; the frontmatter `status` resets to `draft` on the new file.

**Pattern credit:** adapted from AuraMCP 2026-04. Source: Aura Q12 findings, §4.1 of `docs/active/2026-04-14-aura-lessons-synthesis.md` (2026-04-14).

> "Each version of the plan reflects what I've verified, not what I've assumed. The open questions and risks sections are where my uncertainty lives explicitly — not hidden inside the implementation."

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
