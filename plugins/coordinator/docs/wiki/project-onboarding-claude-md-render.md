---
title: Project Onboarding — CLAUDE.md Render Procedure
status: active
kind: procedure-wiki
created: 2026-05-30
---

# Project Onboarding — CLAUDE.md Render Procedure

**Purpose:** Full procedure for constructing substitution values and calling `render-template.sh` when generating a project's `CLAUDE.md` during `/project-onboarding` Phase 3a. Referenced from `skills/project-onboarding/SKILL.md § 3a`.

---

## Substitution Construction

`templates/CLAUDE.md.template` contains ONLY literal `{{KEY}}` substitutions — no conditionals. Construct all values before calling the helper.

### 1. `GLOBAL_EXTENDS_LINE`

- If `~/.claude/CLAUDE.md` exists: set to `Extends global \`~/.claude/CLAUDE.md\`.`
- If no global CLAUDE.md exists: set to empty string `""`

### 2. `PROJECT_TYPE_BLOCK`

Concatenate block bodies for each selected type (in selection order); blank line between multiple blocks.

**`game-dev` block:**
```
## Unreal Engine Conventions

- **Engine version:** UE5.x (specify)
- **Build command:** <!-- e.g., UnrealBuildTool invocation -->
- **Cook command:** <!-- platform-specific cook -->
- **Blueprint vs C++:** <!-- project policy on when to use each -->
- **Naming conventions:** <!-- UE naming standards: A_ for assets, BP_ for blueprints, etc. -->
- **Key modules:** <!-- list primary C++ modules -->
```

**`web-dev` block:**
```
## Web Development

- **Framework:** <!-- e.g., Next.js, React, Vue, Svelte -->
- **Dev server:** <!-- e.g., npm run dev, port -->
- **Component conventions:** <!-- file structure, naming, styling approach -->
- **State management:** <!-- e.g., Zustand, Redux, signals -->
- **CSS approach:** <!-- e.g., Tailwind, CSS Modules, styled-components -->
- **Key routes/pages:** <!-- list primary routes -->
```

**`data-science` block:**
```
## Data Science Conventions

- **Notebook conventions:** <!-- naming, cell organization, output clearing policy -->
- **Data pipelines:** <!-- tools, orchestration, storage locations -->
- **Model versioning:** <!-- MLflow, DVC, manual, etc. -->
- **Environment management:** <!-- conda, venv, poetry -->
- **Key datasets:** <!-- list primary data sources -->
```

**`general` type:** no block body — `PROJECT_TYPE_BLOCK` is empty string `""`.

**Multi-type projects** (e.g., `game-dev` + `data-science`): concatenate both block bodies with a blank line between them.

## 3. Render Helper Call

```bash
bash "$HOME/.claude/plugins/coordinator/bin/render-template.sh" \
  "$HOME/.claude/plugins/coordinator/skills/project-onboarding/templates/CLAUDE.md.template" \
  -o CLAUDE.md \
  PROJECT_NAME="<derived-name>" \
  PROJECT_TYPE="<type>" \
  SUBTYPES="<comma-separated-list-or-empty>" \
  GLOBAL_EXTENDS_LINE="<line-or-empty>" \
  PROJECT_TYPE_BLOCK="<concatenated-blocks-or-empty>"
```

The helper substitutes all `{{KEY}}` placeholders, exits non-zero if any remain (template/key drift guard). Use absolute `$HOME`-anchored paths — relative paths resolve against the project root, not the plugin directory. Leave `<!-- Fill in -->` comments as-is; they are prompts for the PM.

## 4. Runtime Conventions Section

Populate the `## Runtime conventions` section bullets from the Phase 1 marker-scan output — one bullet per detected stack line. If the script reported "no known stack markers", replace the placeholder bullets with `- <!-- no runtime markers detected; PM to fill -->`. Do not edit other `<!-- Fill in -->` placeholders.
