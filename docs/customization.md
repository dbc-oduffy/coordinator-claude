# Customization Guide

coordinator-claude is designed to be adapted. This guide covers the main customization paths.

## Renaming Personas

The personas (Patrik, Zolí, Sid, Palí, Fru, Camelia) are names for convenience. The behavioral descriptions are what actually matter. You can rename them to anything.

### Automated Rename

```bash
bash setup/rename-personas.sh [--dry-run] OLD NEW [OLD NEW ...]

# Examples:
bash setup/rename-personas.sh Patrik "Alex" Zolí "Jordan"
bash setup/rename-personas.sh --dry-run Camelia "DataBot"
```

The script renames two layers for each OLD → NEW pair:
1. **Display names** in prose (e.g., "Patrik" → "Alex" in system prompts and docs)
2. **Invocation slugs** (e.g., `patrik` → `alex` in `--members`, mapping tables, position filenames, `active_reviewers`)

Slugs are auto-derived: lowercase + strip accents (Zolí → zoli, Palí → pali).

What it does NOT touch:
- Agent filenames (`staff-eng.md`, `staff-game-dev.md`, etc.) — these are role-based infrastructure
- YAML `name:` fields — same reason
- `subagent_type` dispatch keys (`coordinator:staff-eng`, etc.) — infrastructure layer

### Persona Registry

| Persona | Plugin | Agent File | Role |
|---------|--------|-----------|------|
| Patrik | coordinator | `agents/staff-eng.md` | Code quality, architecture |
| Zolí | coordinator | `agents/ambition-advocate.md` | Ambition backstop to Patrik |
| Sid | game-dev | `agents/staff-game-dev.md` | Game dev, Unreal Engine |
| Palí | web-dev | `agents/senior-front-end.md` | Frontend, design systems |
| Fru | web-dev | `agents/staff-ux.md` | UX flow, trust signals |
| Camelia | data-science | `agents/staff-data-sci.md` | ML, data science, statistics |

### Manual Rename

If you prefer to rename manually:
1. Find references: `grep -r "OldName" plugins/`
2. Replace in prose only — skip YAML frontmatter blocks
3. Do NOT rename filenames (they are technical identifiers)

## Adding Domain Plugins

The game-dev plugin is a reference implementation. Follow the same structure to create your own domain plugin for any specialization (mobile, security, DevOps, etc.).

### Minimal Plugin Structure

```
plugins/my-domain/
├── agents/
│   └── my-reviewer.md     # Required: the reviewer agent
└── routing.md             # Required: routing fragment
```

### Agent File Template

```markdown
---
name: my-reviewer
description: "Use this agent when you need [domain] review. [1-2 examples]"
model: opus
access-mode: read-only
color: blue
tools: ["Read", "Grep", "Glob", "ToolSearch"]
---

This review is conducted as [Name], [description of persona and expertise].

## Core Philosophy

[What does this reviewer care about? What lens do they bring?]

## Review Standards

[What do they look for? What are their non-negotiables?]

## Output Format

**Return a `ReviewOutput` JSON block followed by your narrative.**

\`\`\`json
{
  "reviewer": "my-reviewer",
  "verdict": "APPROVED | APPROVED_WITH_NOTES | REQUIRES_CHANGES | REJECTED",
  "summary": "2-3 sentence overall assessment",
  "findings": [
    {
      "file": "relative/path/to/file",
      "line_start": 42,
      "line_end": 48,
      "severity": "critical | major | minor | nitpick",
      "category": "[your domain categories]",
      "finding": "Clear description of the issue",
      "suggested_fix": "Optional fix"
    }
  ]
}
\`\`\`

### Coverage Declaration (mandatory)

\`\`\`
## Coverage
- **Reviewed:** [areas examined]
- **Not reviewed:** [areas outside scope]
- **Confidence:** HIGH on findings 1-N; MEDIUM on finding M
- **Gaps:** [anything you couldn't assess and why]
\`\`\`

## Backstop Protocol

**Backstop partner:** Patrik
**Backstop question:** "Is this architecturally sound?"
```

### Routing Fragment Template

```markdown
# Routing Extension: my-domain

## Reviewers

### [Name] (my-reviewer)
- **Signals:** [comma-separated list of signals that trigger this reviewer]
- **Model:** opus
- **Effort:** Medium
- **Backstop:** Patrik (coordinator plugin — universal reviewer)
- **Agent file:** `agents/my-reviewer.md`
```

### Enable the Plugin

Add to `~/.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "my-domain@coordinator-claude": true
  }
}
```

Add to `~/.claude/plugins/installed_plugins.json`:

```json
{
  "my-domain@coordinator-claude": [{
    "scope": "user",
    "installPath": "/home/{USERNAME}/.claude/plugins/coordinator-claude/my-domain",
    "version": "1.0.0",
    "installedAt": "2026-01-01T00:00:00Z",
    "lastUpdated": "2026-01-01T00:00:00Z"
  }]
}
```

## Writing New Skills

Skills are codified behavioral protocols. The `coordinator:writing-skills` skill guides you through creating one with TDD principles.

### What a Skill Is

A skill is a SKILL.md file in `plugins/coordinator/skills/{skill-name}/` with:
- YAML frontmatter: `name` and `description` fields
- The behavioral protocol: step-by-step instructions for how to approach the work

Skills are loaded into context when the skill-discovery system identifies them as relevant. They're followed like a pilot follows a checklist — not internalized and improvised from.

### Skill File Template

```markdown
---
name: my-skill-name
description: "One-sentence description of when this skill applies and what it accomplishes."
---

# [Skill Name]

## When to Use This Skill

[Describe the situation — what triggers this skill? What problem does it solve?]

## Protocol

### Step 1: [First step]

[What to do. Be specific. This is a checklist, not prose.]

### Step 2: [Second step]

[...]

## Exit Criteria

Before considering the skill complete, verify:
- [ ] [Criterion 1]
- [ ] [Criterion 2]
```

## Per-Project Configuration

`.claude/coordinator.local.md` in your project root controls which domain plugins activate and how the coordinator behaves.

### Basic Configuration

```yaml
---
project_type: web
---
```

### Explicit Reviewer List

```yaml
---
active_reviewers:
  - patrik
  - pali
  - fru
---
```

### Project-Specific Instructions

After the YAML frontmatter, you can add markdown that gets injected into the coordinator's context for this project:

```yaml
---
project_type: web
---

## Project Context

This is a TypeScript/React application using Tailwind CSS and shadcn/ui components.

## Conventions

- All new components go in `src/components/`
- Use the design token system in `src/tokens/`
- PR title format: `feat: description` or `fix: description`
```

## Adding CI Checks

The CI system uses convention-based discovery — any `validate-*.py` or `check-*.py` script in `.github/scripts/` runs automatically.

To add a check:
1. Create `.github/scripts/validate-mycheck.py`
2. Script must exit 0 on success, non-zero on failure
3. Print human-readable error details, then a summary line
4. Add a step to `.github/workflows/validate-plugins.yml`

See existing scripts in `.github/scripts/` for patterns.

## Extending the Coordinator Prompt

The coordinator's behavior is shaped by:
1. `CLAUDE.md` (global, loaded by Claude Code)
2. `.claude/coordinator.local.md` (per-project, loaded by Claude Code)
3. `plugins/coordinator/hooks/scripts/coordinator-reminder.sh` (SessionStart hook)
4. `plugins/coordinator/em-operating-model.md` (for meta/infrastructure projects)

For most customization, `.claude/coordinator.local.md` is the right place. For changes that apply to all projects, update `CLAUDE.md` or the coordinator hooks.
