---
name: writing-skills
description: Use when creating new skills, editing existing skills, or verifying skills work before deployment
version: 1.0.0
---

# Writing Skills

## Overview

**Writing skills IS Test-Driven Development applied to process documentation.** Skills live at `${CLAUDE_PLUGIN_ROOT}/skills/{skill-name}/SKILL.md`.

Write pressure scenarios with subagents (test cases), watch them fail (baseline), write the skill, watch tests pass, refactor to close loopholes.

**Core principle:** If you didn't watch an agent fail without the skill, you don't know if the skill teaches the right thing.

**REQUIRED BACKGROUND:** Understand `coordinator:test-driven-development` first — this skill adapts that cycle to documentation. For Anthropic's official guidance see `anthropic-best-practices.md`.

## What is a Skill?

A reference guide for proven techniques, patterns, or tools. Skills are reusable; they are NOT narratives about how you solved a problem once.

## TDD Mapping

| TDD Concept | Skill Creation |
|-------------|----------------|
| Test case | Pressure scenario with subagent |
| Production code | SKILL.md |
| RED | Agent violates rule without skill (baseline) |
| GREEN | Agent complies with skill present |
| Refactor | Close loopholes while maintaining compliance |

## When to Create a Skill

**Anti-proliferation gate — check FIRST.** Search the skills directory for related names. If a related skill exists, **extend it**. New files need justification.

**Create when:** the technique wasn't intuitively obvious, you'd reference it across projects, the pattern applies broadly, no existing skill covers the territory.

**Don't create for:** one-off solutions, well-documented standard practices, project-specific conventions (use CLAUDE.md), mechanical constraints enforceable with regex/validation.

## Skill Types

- **Technique** — concrete method with steps (`condition-based-waiting`, `root-cause-tracing`)
- **Pattern** — way of thinking (`flatten-with-flags`, `test-invariants`)
- **Reference** — API docs, syntax guides

## Directory Structure

```
skills/
  skill-name/
    SKILL.md              # Main reference (required)
    supporting-file.*     # Heavy reference or reusable tools only
```

Flat namespace, all skills searchable. Inline principles, concepts, and short code patterns (<50 lines). Separate files for heavy reference (100+ lines) or reusable scripts/templates.

## SKILL.md Structure

**Frontmatter:**
- Only `name` and `description` supported. Max 1024 chars total.
- `name`: letters, numbers, hyphens only.
- `description`: third-person, **describes ONLY when to use, NOT what it does** — start with "Use when..."

```markdown
---
name: skill-name-with-hyphens
description: Use when [specific triggering conditions and symptoms]
---

# Skill Name

## Overview
What is this? Core principle in 1-2 sentences.

## When to Use
Bullet list with symptoms/use cases. When NOT to use.

## Core Pattern (techniques/patterns)
Before/after comparison.

## Quick Reference
Table or bullets for scanning.

## Implementation
Inline code OR link to file.

## Common Mistakes
What goes wrong + fixes.
```

## Claude Search Optimization

**Description = When to Use, NOT What the Skill Does.** Empirically: descriptions that summarize workflow create a shortcut Claude takes instead of reading the skill body. A description saying "code review between tasks" caused Claude to do ONE review even though the skill flowchart specified TWO. When changed to just triggering conditions, Claude correctly read the flowchart.

```yaml
# BAD: workflow summary creates shortcut
description: Use when executing plans - dispatches subagent per task with code review between tasks

# GOOD: triggering conditions only
description: Use when executing implementation plans with independent tasks
```

**Keyword coverage** — use words Claude would search for: error messages ("Hook timed out"), symptoms ("flaky", "hanging"), synonyms ("timeout/hang/freeze"), tool names.

**Descriptive naming** — active voice, verb-first. `creating-skills` not `skill-creation`. `condition-based-waiting` not `async-test-helpers`.

**Token efficiency** — frequently-loaded skills should be <200 words total; others <500. Move flag details to `--help`. Cross-reference rather than duplicate. Compress examples ruthlessly. Verify with `wc -w`.

**Cross-referencing other skills** — name only with explicit requirement marker:
- ✅ `**REQUIRED BACKGROUND:** Use coordinator:test-driven-development`
- ❌ `@skills/...` syntax force-loads files immediately, burning context.

## Flowcharts

Use ONLY for: non-obvious decision points, process loops where you might stop too early, "when to use A vs B" decisions. Never for reference material (use tables), code examples (use markdown), or linear instructions (use numbered lists). See `@graphviz-conventions.dot`.

## Code Examples

One excellent example beats many mediocre ones. Choose the most relevant language; complete, runnable, well-commented explaining WHY, from a real scenario. Don't implement in 5+ languages, don't write fill-in-the-blank templates, don't write contrived examples.

## Common Footguns

**`allowed-tools` must be a YAML list, not a scalar.** `allowed-tools: Write` silently passes YAML parsing but fails schema check. Correct form:
```yaml
allowed-tools:
  - Write
```

**`access-mode: read-only` silently overrides the tools list.** An agent with `Write` in `tools:` but `access-mode: read-only` cannot write — the deliverable disappears. Default agents that produce file output to `access-mode: read-write`.

**Prompts live in one place.** A driver/skill/command MUST `@`-reference the canonical prompt template, never inline its body. Drift between inlined copy and template is a silent correctness bug.

**Hook authoring** — see `coordinator/docs/hook-authoring-notes.md` for SubagentStop agent_type gating and stderr-as-error-channel footguns.

## The Iron Law

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

Applies to NEW skills AND EDITS. Wrote skill before testing? Delete it, start over. Same for edits. No exceptions for "simple additions," "just adding a section," "documentation updates," or "I'm confident it's good." Deploying untested skills = deploying untested code.

For the rationalization table (8 common excuses for skipping testing) and the full RED-GREEN-REFACTOR cycle with anti-patterns, see `skill-bulletproofing.md` in this directory.

## Companion Files

- `skill-bulletproofing.md` — rationalization defense, loophole closing, RED-GREEN-REFACTOR cycle, anti-patterns
- `testing-skills-with-subagents.md` — complete testing methodology with pressure scenarios
- `persuasion-principles.md` — persuasion techniques for descriptions and agent compliance prompts
- `examples/CLAUDE_MD_TESTING.md` — archived test design for compliance under pressure

## STOP: Before Moving to the Next Skill

After writing ANY skill, complete the deployment checklist before moving on. Do NOT batch skill creation without testing each. Use TaskCreate for each checklist item.

## Skill Creation Checklist

**RED — Write Failing Test:**
- [ ] Create pressure scenarios (3+ combined pressures for discipline skills)
- [ ] Run WITHOUT skill — document baseline verbatim
- [ ] Identify patterns in rationalizations/failures

**GREEN — Write Minimal Skill:**
- [ ] Name: letters, numbers, hyphens only
- [ ] Frontmatter: name + description, max 1024 chars
- [ ] Description starts "Use when...", third person, specific triggers
- [ ] Keywords throughout (errors, symptoms, tools)
- [ ] Address specific baseline failures from RED
- [ ] One excellent example (not multi-language)
- [ ] Run WITH skill — verify agents comply

**REFACTOR — Close Loopholes:**
- [ ] Identify new rationalizations from testing
- [ ] Add explicit counters (discipline skills)
- [ ] Build rationalization table; create red flags list
- [ ] Re-test until bulletproof

**Quality:**
- [ ] Flowchart only if decision non-obvious
- [ ] Quick reference table
- [ ] Common mistakes section
- [ ] No narrative storytelling

**Dependency discipline (hard-dep vs soft-dep):**
- [ ] For each external reference (other skills, setup commands, scaffold artifacts), classify: would this skill produce *wrong* output without the reference, or just *less-sharp* output?
- [ ] Hard-dep (wrong without it) → keep an explicit pointer (`Run /X first if not configured`)
- [ ] Soft-dep (less-sharp without it) → swap explicit pointer for vague prose referencing the *output* (`if a project tracker exists`, `any CLAUDE.md conventions`); never name the producing skill
- [ ] Default to soft-dep when uncertain — cargo-cult expansion of setup pointers compounds across the corpus

**Deployment:**
- [ ] Commit and push to your fork (if configured)
- [ ] Consider contributing back via PR

## The Bottom Line

Same Iron Law as TDD. Same cycle: RED → GREEN → REFACTOR. Same benefits: better quality, fewer surprises, bulletproof results.
