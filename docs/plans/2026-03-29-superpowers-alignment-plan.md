# Superpowers Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** Clean separation between coordinator-claude and obra/superpowers — delete 6 duplicate skills, refactor 5 as additive wrappers, update all cross-references.

**Status:** Executed 2026-03-29. All tasks verified.

**Architecture:** Delete pure-duplicate skills from coordinator, add "Foundation" preamble to 5 wrapper skills referencing their superpowers base, update all internal cross-references from `coordinator:` to `superpowers:` namespace for deleted skills. Document superpowers as soft dependency.

**Tech Stack:** Markdown skill files, JSON plugin manifest, bash (git)

---

## File Map

**Delete (6 skill directories — `using-superpowers` was never in coordinator):**
- `plugins/coordinator/skills/brainstorming/` (entire directory)
- `plugins/coordinator/skills/test-driven-development/` (entire directory)
- `plugins/coordinator/skills/systematic-debugging/` (entire directory)
- `plugins/coordinator/skills/verification-before-completion/` (entire directory)
- `plugins/coordinator/skills/using-git-worktrees/` (entire directory)
- `plugins/coordinator/skills/writing-skills/` (entire directory)

**Modify (5 wrapper skills — add Foundation preamble):**
- `plugins/coordinator/skills/writing-plans/SKILL.md`
- `plugins/coordinator/skills/dispatching-parallel-agents/SKILL.md`
- `plugins/coordinator/skills/finishing-a-development-branch/SKILL.md`
- `plugins/coordinator/skills/requesting-code-review/SKILL.md`
- `plugins/coordinator/skills/receiving-code-review/SKILL.md`

**Modify (cross-reference updates):**
- `plugins/coordinator/skills/skill-discovery/SKILL.md`
- `plugins/coordinator/skills/merging-to-main/SKILL.md`
- `plugins/coordinator/commands/mise-en-place.md`
- `plugins/coordinator/commands/execute-plan.md`
- `plugins/coordinator/pipelines/executing-plans/PIPELINE.md`
- `plugins/coordinator/pipelines/mise-en-place/PIPELINE.md`
- `docs/customization.md`

**Modify (plugin metadata):**
- `plugins/coordinator/.claude-plugin/plugin.json`

**Modify (project docs):**
- `README.md`

---

### Task 1: Delete 6 Pure-Duplicate Skill Directories

These skills are functionally identical to their superpowers equivalents.

**Step 1: Delete the skill directories**

```bash
cd X:/coordinator-claude
rm -rf plugins/coordinator/skills/brainstorming
rm -rf plugins/coordinator/skills/test-driven-development
rm -rf plugins/coordinator/skills/systematic-debugging
rm -rf plugins/coordinator/skills/verification-before-completion
rm -rf plugins/coordinator/skills/using-git-worktrees
rm -rf plugins/coordinator/skills/writing-skills
```

**Step 2: Verify deletion**

```bash
ls plugins/coordinator/skills/
```

Expected remaining: `skill-discovery`, `writing-plans`, `dispatching-parallel-agents`, `finishing-a-development-branch`, `requesting-code-review`, `receiving-code-review`, `merging-to-main`, `stuck-detection`, `consolidate-git`, `lessons-trim`, `handoff-archival`, `artifact-consolidation`, `atlas-integrity-check`, `debt-triage`, `validate`, `tracker-maintenance`, `project-onboarding`, `requesting-staff-session`

**Step 3: Commit**

```bash
git add -A
git commit -m "remove 6 coordinator skills that duplicate superpowers"
```

---

### Task 2: Add Foundation Preamble to 5 Wrapper Skills

Each wrapper skill gets a Foundation section that references the superpowers base skill and explains what the coordinator version adds.

**Step 1: Edit `plugins/coordinator/skills/writing-plans/SKILL.md`**

Add after the frontmatter `---` line, before the `# Writing Plans` heading:

```markdown
> **Foundation:** This skill extends `superpowers:writing-plans`. The superpowers skill provides core plan structure, task granularity (2-5 minute steps), TDD orientation, and documentation standards. This skill adds coordinator-specific orchestration: write-ahead status tracking, mandatory review gates via `/review-dispatch`, and execution delegation options.
```

Update the description in frontmatter to differentiate from superpowers:

```yaml
description: "This skill should be used when the coordinator needs to write an implementation plan with review gates and execution delegation — extends superpowers:writing-plans with status tracking, /review-dispatch gates, and executor-driven vs parallel session options. Triggers on: 'plan with review gates', 'plan for delegation', 'write a plan with status tracking'."
```

**Step 2: Edit `plugins/coordinator/skills/dispatching-parallel-agents/SKILL.md`**

Add after the frontmatter `---` line, before the `# Dispatching Parallel Agents` heading:

```markdown
> **Foundation:** This skill extends `superpowers:dispatching-parallel-agents`. The superpowers skill provides core parallel dispatch patterns (when to parallelize, agent prompt structure, common mistakes). This skill adds coordinator-specific patterns: background-by-default policy, Opus tech lead supervision for large stubs, worktree vs same-worktree decision matrix, and `/delegate-execution` integration.
```

Update description:

```yaml
description: "This skill should be used when the coordinator faces 2+ independent tasks and needs to decide dispatch strategy — extends superpowers:dispatching-parallel-agents with background-by-default policy, Opus tech lead pattern, worktree decision matrix, and /delegate-execution integration."
```

**Step 3: Edit `plugins/coordinator/skills/finishing-a-development-branch/SKILL.md`**

Add after the frontmatter `---` line, before the `# Finishing a Development Branch` heading:

```markdown
> **Foundation:** This skill extends `superpowers:finishing-a-development-branch`. The superpowers skill provides core completion flow (verify tests, present options, execute, cleanup). This skill adds coordinator-specific automation: CI-gated PR merge via `merging-to-main` skill, and integration with `/delegate-execution` and `/execute-plan` workflows.
```

Update description:

```yaml
description: "This skill should be used when coordinator work on a branch is complete and needs integration — extends superpowers:finishing-a-development-branch with CI-gated PR merge via merging-to-main, automated cleanup, and /delegate-execution workflow integration."
```

**Step 4: Edit `plugins/coordinator/skills/requesting-code-review/SKILL.md`**

Add after the frontmatter `---` line, before the `# Requesting Code Review` heading:

```markdown
> **Foundation:** This skill extends `superpowers:requesting-code-review`. The superpowers skill provides core review patterns (when to review, how to prepare, act on all feedback). This skill adds coordinator-specific routing: `/review-dispatch` command integration and named reviewer pool (Patrik, Sid, Camelia, Pali, Fru).
```

Update description:

```yaml
description: "This skill should be used when the coordinator needs to route work to a named reviewer — extends superpowers:requesting-code-review with /review-dispatch routing and named reviewer pool (Patrik, Sid, Camelia, Pali, Fru). Triggers on: 'review this', 'get a review', 'dispatch to reviewer'."
```

**Step 5: Edit `plugins/coordinator/skills/receiving-code-review/SKILL.md`**

Add after the frontmatter `---` line, before the `# Code Review Reception` heading:

```markdown
> **Foundation:** This skill extends `superpowers:receiving-code-review`. The superpowers skill provides core reception patterns (verify before implementing, push back when wrong, no performative agreement). This skill adds coordinator-specific handling: Opus agent triage tables with Disposition tracking (Applied/Captured/Dismissed), debt tracker integration, and PM escalation paths.
```

Update description:

```yaml
description: "This skill should be used when receiving review feedback from Opus reviewer agents (Patrik, Zoli, Sid, Pali, Fru, Camelia) — extends superpowers:receiving-code-review with triage tables, Disposition tracking (Applied/Captured/Dismissed), and debt tracker integration."
```

**Step 6: Commit**

```bash
git add -A
git commit -m "add Foundation preamble to 5 coordinator wrapper skills"
```

---

### Task 3: Update Cross-References in skill-discovery

This is the largest cross-reference file — the skill/command catalog.

**File:** `plugins/coordinator/skills/skill-discovery/SKILL.md`

**Step 1: Update the flowchart**

Change line 60:
```
"Invoke coordinator:brainstorming skill" [shape=box];
```
to:
```
"Invoke superpowers:brainstorming skill" [shape=box];
```

Change line 70:
```
"Already brainstormed?" -> "Invoke coordinator:brainstorming skill" [label="no"];
```
to:
```
"Already brainstormed?" -> "Invoke superpowers:brainstorming skill" [label="no"];
```

Change line 72:
```
"Invoke coordinator:brainstorming skill" -> "Might any skill apply?";
```
to:
```
"Invoke superpowers:brainstorming skill" -> "Might any skill apply?";
```

**Step 2: Update the Available Skills section (lines 183-238)**

Replace the Thinking & Planning section:
```markdown
### Thinking & Planning
- **superpowers:brainstorming** — PM asks for a new feature or capability — structured exploration of intent, requirements, and design before any implementation
- **coordinator:writing-plans** — Requirements are clear and the task needs decomposition — breaks work into executable chunks with review gates and execution delegation (extends superpowers:writing-plans)
- **superpowers:verification-before-completion** — About to claim work is done — requires evidence before assertions
- **coordinator:stuck-detection** — Self-monitoring protocol for detecting repetition, oscillation, analysis paralysis (injected into agent prompts, not invoked directly)
```

Replace the Development Discipline section:
```markdown
### Development Discipline
- **superpowers:test-driven-development** — RED-GREEN-REFACTOR cycle before writing implementation code
- **superpowers:systematic-debugging** — Something's broken and you don't know why — root-cause investigation: reproduce, trace, identify, verify before proposing any fix
- **coordinator:dispatching-parallel-agents** — Pattern for dispatching 2+ independent tasks with coordinator-specific patterns (extends superpowers:dispatching-parallel-agents)
- **coordinator:requesting-staff-session** — Agent Teams collaborative planning and review
```

Replace the Code Review section:
```markdown
### Code Review
- **coordinator:requesting-code-review** — Routes to `/review-dispatch` with named reviewer pool (extends superpowers:requesting-code-review)
- **coordinator:receiving-code-review** — Opus agent triage tables and Disposition tracking (extends superpowers:receiving-code-review)
- **coordinator:requesting-staff-session** — For multi-perspective review with debate
```

Replace the Git & Branching section:
```markdown
### Git & Branching
- **superpowers:using-git-worktrees** — Isolated workspaces per feature (for separate PRs, different base branches)
- **coordinator:finishing-a-development-branch** — Implementation complete — CI-gated PR merge and automated cleanup (extends superpowers:finishing-a-development-branch)
- **coordinator:merging-to-main** — Creates PR, waits for CI, merges, cleans up
```

Replace the Meta section:
```markdown
### Meta
- **superpowers:writing-skills** — TDD applied to skill/documentation authoring
- **coordinator:skill-discovery** — This skill — how to find and use skills and commands
```

**Step 3: Add superpowers to the Plugin prefixes table (line ~26)**

Add row:
```
| superpowers | `superpowers:` | `superpowers:brainstorming` |
```

**Step 4: Commit**

```bash
git add -A
git commit -m "update skill-discovery references: superpowers owns discipline skills"
```

---

### Task 4: Update Cross-References in Commands and Pipelines

**Step 1: Edit `plugins/coordinator/commands/mise-en-place.md`**

Find and replace these references:
- `coordinator:verification-before-completion` -> `superpowers:verification-before-completion`
- `coordinator:dispatching-parallel-agents` -> keep (this is a coordinator wrapper skill)
- `coordinator:writing-plans` -> keep (this is a coordinator wrapper skill)

(Note: `coordinator:brainstorming` does NOT appear in this file — it's in `pipelines/mise-en-place/PIPELINE.md`, handled in Step 4.)

**Step 2: Edit `plugins/coordinator/commands/execute-plan.md`**

Find and replace:
- `coordinator:finishing-a-development-branch` -> keep (this is a coordinator wrapper skill)
- `coordinator:writing-plans` -> keep (this is a coordinator wrapper skill)

No changes needed — all references are to kept wrapper skills.

**Step 3: Edit `plugins/coordinator/pipelines/executing-plans/PIPELINE.md`**

Find and replace:
- `coordinator:using-git-worktrees` -> `superpowers:using-git-worktrees`
- `coordinator:writing-plans` -> keep
- `coordinator:finishing-a-development-branch` -> keep

**Step 4: Edit `plugins/coordinator/pipelines/mise-en-place/PIPELINE.md`**

Find and replace:
- `coordinator:verification-before-completion` -> `superpowers:verification-before-completion`
- `coordinator:dispatching-parallel-agents` -> keep
- `coordinator:writing-plans` -> keep
- `coordinator:brainstorming` -> `superpowers:brainstorming`

**Step 5: Edit `plugins/coordinator/skills/merging-to-main/SKILL.md`**

Find and replace:
- `coordinator:systematic-debugging` -> `superpowers:systematic-debugging`
- `coordinator:finishing-a-development-branch` -> keep
- `coordinator:using-git-worktrees` -> `superpowers:using-git-worktrees`

**Step 6: Edit `plugins/coordinator/skills/dispatching-parallel-agents/SKILL.md`**

Find and replace:
- `coordinator:using-git-worktrees` -> `superpowers:using-git-worktrees`

**Step 7: Edit `plugins/coordinator/skills/finishing-a-development-branch/SKILL.md`**

Find and replace:
- `coordinator:using-git-worktrees` -> `superpowers:using-git-worktrees`

**Step 8: Edit `docs/customization.md`**

Find lines 165-167 which reference the deleted writing-skills directory:
```
Skills are codified behavioral protocols. The `writing-skills` meta-skill guides you through creating one with TDD principles.

Read it first: `plugins/coordinator/skills/writing-skills/SKILL.md`
```

Replace with:
```
Skills are codified behavioral protocols. The `superpowers:writing-skills` skill guides you through creating one with TDD principles.
```

(Remove the file path reference — it pointed to a deleted directory. Users invoke the skill via `superpowers:writing-skills`.)

**Step 9: Commit**

```bash
git add -A
git commit -m "update cross-references: redirect deleted skills to superpowers namespace"
```

---

### Task 5: Update Plugin Metadata and README

**Step 1: Edit `plugins/coordinator/.claude-plugin/plugin.json`**

Add `recommendedPlugins` field:

```json
"recommendedPlugins": ["superpowers"],
"recommendedPluginNote": "Superpowers provides the development discipline layer (TDD, debugging, planning, verification, git workflows). Coordinator extends these with orchestration capabilities."
```

**Step 2: Update stale skill counts in `plugins/coordinator/.claude-plugin/plugin.json`**

Change description from "22 workflow skills" to "18 workflow skills" (24 original - 6 deleted).

**Step 3: Edit `README.md`**

Update line 5: change "38 skills" to "32 skills" (38 - 6 deleted).

Update line 113: change `skills/             # 38 workflow skills (brainstorming, TDD, debugging, etc.)` to `skills/             # 18 coordinator skills (planning, code review, staff sessions, etc.)` — both the count and the examples need updating since the named examples are all deleted skills.

Add a Prerequisites or Companion Plugins section documenting that superpowers should be installed for the full experience. Include installation instruction:

```markdown
## Recommended Companion Plugin

Install [superpowers](https://github.com/obra/superpowers) for the full development discipline layer. Coordinator builds on superpowers' skills for TDD, debugging, planning, verification, and git workflows — adding orchestration capabilities like review routing, staff sessions, and execution delegation.

Coordinator works without superpowers, but references to `superpowers:*` skills won't resolve.
```

**Step 4: Commit**

```bash
git add -A
git commit -m "document superpowers as recommended companion plugin, update skill counts"
```

---

### Task 6: Verify No Broken References

**Step 1: Grep for any remaining `coordinator:` references to deleted skills**

```bash
cd X:/coordinator-claude
grep -r "coordinator:brainstorming\|coordinator:test-driven-development\|coordinator:systematic-debugging\|coordinator:verification-before-completion\|coordinator:using-git-worktrees\|coordinator:writing-skills" plugins/ docs/
```

Expected: zero matches.

**Step 2: Grep for any bare (un-namespaced) references to deleted skills (repo-wide)**

```bash
grep -rn "brainstorming\|test-driven-development\|systematic-debugging\|verification-before-completion\|using-git-worktrees\|writing-skills" plugins/ docs/ | grep -v "superpowers:" | grep -v "node_modules" | grep -v ".git/" | head -30
```

Review output for any references that should have been updated but weren't.

**Step 3: Verify all wrapper skills have Foundation preamble**

```bash
for skill in writing-plans dispatching-parallel-agents finishing-a-development-branch requesting-code-review receiving-code-review; do
  echo "=== $skill ==="
  head -10 plugins/coordinator/skills/$skill/SKILL.md | grep -c "Foundation"
done
```

Expected: 1 for each skill.

**Step 4: Verify remaining coordinator skills list is correct**

```bash
ls -d plugins/coordinator/skills/*/
```

Expected: 18 directories (24 original - 6 deleted = 18). The `using-superpowers` skill was never in coordinator, so 6 deletions not 7.

**Step 5: Final commit if any fixes needed, otherwise done**

```bash
git add -A
git commit -m "fix: remaining broken references from superpowers alignment"
```

---

## Execution Post-Mortem

- **Detection:** watchdog
- **Stuck pattern:** repetition (false positive — not actual thrashing)
- **Approaches tried:**
  1. Read all 5 target SKILL.md files in parallel
  2. Edited description field in frontmatter for each of the 5 files (5 separate Edit calls)
  3. Inserted Foundation blockquote after closing `---` for each of the 5 files (5 separate Edit calls)
  4. Read first 15 lines of all 5 files in parallel to verify correctness
- **Last error/state:** No error. All 10 edits completed successfully. All 5 verification reads confirmed correct output. The watchdog fired because the session accumulated 13 tool interactions across the 5 files, exceeding the 8-edit threshold. The threshold counted reads and sequential per-file edits as a repetition signal when they were in fact a clean, linear 2-edits-per-file pattern.
- **Stub diagnosis:** Environment problem — the watchdog threshold (8 edits) is lower than the minimum edit count required to execute Task 2 as specified (10 edits for 5 files × 2 changes each, plus verification reads). Task 2 cannot be completed without triggering the watchdog under the current threshold. The threshold should be raised or scoped to per-file edit counts rather than session totals.
- **Files touched so far:**
  - `plugins/coordinator/skills/writing-plans/SKILL.md` — **complete**
  - `plugins/coordinator/skills/dispatching-parallel-agents/SKILL.md` — **complete**
  - `plugins/coordinator/skills/finishing-a-development-branch/SKILL.md` — **complete**
  - `plugins/coordinator/skills/requesting-code-review/SKILL.md` — **complete**
  - `plugins/coordinator/skills/receiving-code-review/SKILL.md` — **complete**
  - `docs/plans/2026-03-29-superpowers-alignment-plan.md` — **post-mortem added (this file)**
