# Design: Superpowers Alignment

**Date:** 2026-03-29
**Status:** Implemented 2026-03-29
**Goal:** Clean separation between coordinator-claude and obra/superpowers plugins, with superpowers as a soft dependency providing the development discipline layer.

## Problem

Coordinator-claude ships 12 skills that duplicate superpowers v5.0.6 skills. Both plugins are installed simultaneously, causing:

1. **Duplicate triggers** — Claude sees `superpowers:brainstorming` and `coordinator:brainstorming` with overlapping trigger phrases, wasting system prompt space and creating ambiguity
2. **Maintenance burden** — Improvements to superpowers require manual backport to coordinator copies
3. **Unclear ownership** — No clear boundary between "development discipline" (superpowers) and "orchestration" (coordinator)

## Design

### Ownership Principle

**Superpowers** owns generic development discipline — TDD, debugging, verification, planning fundamentals, git workflows, skill authoring.

**Coordinator** owns orchestration — reviewer personas, research pipelines, staff sessions, enrichment/execution delegation, PM-EM dynamic, project health.

Where coordinator needs to extend a superpowers skill (e.g., adding review-dispatch routing to code review), it provides an **additive wrapper skill** with a distinct name and distinct triggers.

### Skill Disposition

#### Category 1: Delete (7 pure duplicates)

These coordinator skills are functionally identical to their superpowers counterparts. Delete them; superpowers owns the capability.

| Coordinator Skill | Superpowers Equivalent | Why Delete |
|---|---|---|
| `brainstorming` | `superpowers:brainstorming` | Superpowers version is more mature (has visual companion, spec self-review gate) |
| `test-driven-development` | `superpowers:test-driven-development` | Identical content, pronoun differences only |
| `systematic-debugging` | `superpowers:systematic-debugging` | Identical content, pronoun differences only |
| `verification-before-completion` | `superpowers:verification-before-completion` | Identical content |
| `using-git-worktrees` | `superpowers:using-git-worktrees` | Identical mechanics |
| `writing-skills` | `superpowers:writing-skills` | Tool/path differences only (TaskCreate vs TodoWrite) |
| `using-superpowers` | `superpowers:using-superpowers` | Already only exists in superpowers (loaded via SessionStart hook) |

#### Category 2: Rename and Refactor as Additive Wrappers (5 coordinator extensions)

These skills have genuine coordinator-specific additions beyond the superpowers base. Rename to avoid collision; restructure to invoke the superpowers base skill first, then layer coordinator additions.

| Current Name | New Name | Coordinator-Specific Additions |
|---|---|---|
| `writing-plans` | `writing-plans` (keep name) | Status write-ahead protocol, mandatory `/review-dispatch` gate, executor-driven vs parallel execution options, plan destination conventions |
| `dispatching-parallel-agents` | `dispatching-parallel-agents` (keep name) | Background-by-default policy, Opus tech lead supervision pattern, worktree vs same-worktree decision matrix, `/delegate-execution` integration |
| `finishing-a-development-branch` | `finishing-a-development-branch` (keep name) | CI-gated PR merge via `merging-to-main`, automated cleanup |
| `requesting-code-review` | `requesting-code-review` (keep name) | `/review-dispatch` routing, named reviewer pool (Patrik, Sid, Camelia, Pali, Fru) |
| `receiving-code-review` | `receiving-code-review` (keep name) | Opus agent triage tables, Disposition tracking (Applied/Captured/Dismissed), debt tracker integration |

**Naming decision:** Keep the same names. The skills are namespaced by plugin (`coordinator:writing-plans` vs `superpowers:writing-plans`). The differentiation comes from trigger descriptions — coordinator versions trigger on orchestration-specific phrases; superpowers versions trigger on generic phrases. Claude resolves which to use based on context.

**Wrapper pattern:** Each coordinator skill opens with an instruction to build on the superpowers base:

```markdown
## Foundation

This skill extends `superpowers:writing-plans`. The superpowers skill provides the core
plan structure, task granularity, and documentation standards. This skill adds
coordinator-specific orchestration: review gates, execution delegation, and status tracking.

When invoked, apply the superpowers base skill's plan format, then layer the extensions below.
```

#### Category 3: No Change (superpowers-only)

| Skill | Owner | Notes |
|---|---|---|
| `subagent-driven-development` | superpowers | Coordinator uses `/delegate-execution` command instead |
| `executing-plans` | superpowers | Coordinator uses `/execute-plan` command instead |

### Cross-Reference Updates

Internal references throughout coordinator commands, pipelines, and skills must be updated:

**References to deleted skills — redirect to superpowers:**
- `coordinator:brainstorming` -> `superpowers:brainstorming`
- `coordinator:test-driven-development` -> `superpowers:test-driven-development`
- `coordinator:systematic-debugging` -> `superpowers:systematic-debugging`
- `coordinator:verification-before-completion` -> `superpowers:verification-before-completion`
- `coordinator:using-git-worktrees` -> `superpowers:using-git-worktrees`
- `coordinator:writing-skills` -> `superpowers:writing-skills`

**References to renamed skills — update to new names:**
- The 5 wrapper skills keep their names, so references like `coordinator:writing-plans` remain valid.

**Files requiring updates** (from grep):
- `skills/brainstorming/SKILL.md` — DELETED (references `coordinator:writing-plans` — handled by superpowers version)
- `skills/writing-skills/SKILL.md` — DELETED (references `coordinator:test-driven-development`)
- `skills/systematic-debugging/SKILL.md` — DELETED (references `coordinator:test-driven-development`)
- `skills/skill-discovery/SKILL.md` — Update all skill references to use correct plugin prefix
- `skills/dispatching-parallel-agents/SKILL.md` — Update `coordinator:using-git-worktrees` reference
- `skills/merging-to-main/SKILL.md` — Update references to deleted skills
- `commands/mise-en-place.md` — Update references to deleted skills
- `commands/execute-plan.md` — References are to kept skills (no change needed)
- `pipelines/executing-plans/PIPELINE.md` — Update references to deleted skills
- `pipelines/mise-en-place/PIPELINE.md` — Update references to deleted skills

### Soft Dependency Documentation

**plugin.json** — Add informational field:
```json
{
  "recommendedPlugins": ["superpowers"],
  "recommendedPluginNote": "Superpowers provides the development discipline layer (TDD, debugging, planning, verification). Coordinator extends these with orchestration capabilities."
}
```

**README.md** — Add prerequisites section documenting that superpowers should be installed for the full experience.

### What This Does NOT Change

- No changes to coordinator agents, commands, hooks, or pipelines (beyond cross-reference updates)
- No changes to non-coordinator plugins (web-dev, game-dev, data-science, deep-research, etc.)
- No changes to superpowers plugin itself
- The `using-superpowers` SessionStart hook (from superpowers marketplace plugin) continues to function independently

## Success Criteria

1. Zero duplicate skill names between coordinator and superpowers when both installed
2. All coordinator commands/pipelines reference the correct plugin prefix for each skill
3. Coordinator wrapper skills clearly build on superpowers base
4. README documents superpowers as recommended companion plugin
