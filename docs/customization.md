# Customization Guide

coordinator-claude is designed to be adapted. This guide covers the main customization paths.

## Naming Reviewer Roles

The system ships with role-based labels (the Staff Engineer, the Director of Engineering, etc.). The behavioral descriptions are what actually matter. Naming is optional — if you find it easier to think of reviewers by personal names, run the naming script once at install time.

### Automated Naming (optional)

```bash
bash setup/name-personas.sh [--dry-run] ROLE NAME [ROLE NAME ...]

# Examples:
bash setup/name-personas.sh "the Staff Engineer" "Alex" "the Director of Engineering" "Jordan"
bash setup/name-personas.sh --dry-run "the Data Science Reviewer" "DataBot"
```

The script binds names to role labels across all plugin files:
1. **Display names** in prose (e.g., "the Staff Engineer" → "Alex" in system prompts and docs)

Slugs are auto-derived: lowercase + strip articles and accents.

What it does NOT touch:
- Agent filenames (`staff-eng.md`, `staff-game-dev.md`, etc.) — these are role-based infrastructure
- YAML `name:` fields — same reason
- `subagent_type` dispatch keys (`coordinator:staff-eng`, etc.) — infrastructure layer

### Reviewer Roles

The publish repo ships with seven role-distinct reviewers. Names are optional — applied at install time via `setup/name-personas.sh` if the user opts in.

| Role label | Subagent slug | Plugin | Agent file | Focus |
|---|---|---|---|---|
| the Staff Engineer | `coordinator:staff-eng` | coordinator | `agents/staff-eng.md` | Code quality, architecture |
| the Director of Engineering | `coordinator:eng-director` | coordinator | `agents/eng-director.md` | Peer of the Staff Engineer in technical rigor; DoE altitude for cross-team / cross-repo / generic-substrate reviews. Three modes: standalone primary, backstop after the Staff Engineer, staff-session synthesizer. |
| the VP-Product Reviewer | `coordinator:vp-product` | coordinator | `agents/vp-product.md` | Scope challenger; refactor-vs-patch backstop |
| the Game Dev Reviewer | `game-dev:staff-game-dev` | game-dev | `agents/staff-game-dev.md` | Game dev, Unreal Engine |
| the Front-End Reviewer | `web-dev:senior-front-end` | web-dev | `agents/senior-front-end.md` | Frontend, design systems |
| the UX Reviewer | `web-dev:staff-ux` | web-dev | `agents/staff-ux.md` | UX flow, trust signals |
| the Data Science Reviewer | `data-science:staff-data-sci` | data-science | `agents/staff-data-sci.md` | ML, data science, statistics |

### Manual Naming

If you'd rather hand-edit (one role at a time, or with a pattern the script doesn't cover):

1. Find every occurrence of the articulated role label — the leading article is the sentinel that distinguishes a role reference from generic prose:
   ```bash
   grep -rn "the Staff Engineer" plugins/ docs/customization.md
   grep -rn "The Staff Engineer" plugins/ docs/customization.md   # sentence-initial
   ```
2. Replace the label with your chosen name in prose. The unarticulated form `Staff Engineer` (no leading article) appears in generic prose like "a senior staff engineer with exacting standards" — leave those alone; they're not role references.
3. Don't touch agent filenames (`staff-eng.md`, `staff-game-dev.md`, …), YAML `name:` fields, or `subagent_type:` dispatch keys (`coordinator:staff-eng`, …). All three are infrastructure and stay role-based even after you've named the persona.

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

**Backstop partner:** the Staff Engineer (`coordinator:staff-eng`)
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
- **Backstop:** the Staff Engineer (`coordinator:staff-eng`) (coordinator plugin — universal reviewer)
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

Skills are codified behavioral protocols. Reference: [`docs/wiki/writing-skills.md`](../docs/wiki/writing-skills.md) for conventions; [`docs/evolution/07-super-skills.md`](evolution/07-super-skills.md) for when to write a prose skill versus a decision-tree super-skill.

### What a Skill Is

A skill is a SKILL.md file in `plugins/coordinator/skills/{skill-name}/` with:
- YAML frontmatter: `name` and `description` fields (description ≤150 chars, or ≤175 with PM gate; longer requires explicit `description-budget: <N>` exemption — enforced by `bin/check-description-length.sh`, hard-gated in `/workday-complete` Step 0b)
- The behavioral protocol: step-by-step instructions for how to approach the work

Skills are loaded into context when the skill-discovery system identifies them as relevant. They're followed like a pilot follows a checklist — not internalized and improvised from. **Load-bearing skills** (the ones where skipping a step has expensive downstream consequences — plan, review, review-code) use the **super-skill shape**: a decision-tree router with named branches (triage / substrate / compose / exit), with long-form rationale moved out to a wiki page. Most skills stay prose.

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
  - staff-eng
  - senior-front-end
  - staff-ux
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
