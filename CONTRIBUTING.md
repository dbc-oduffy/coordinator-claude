# Contributing to coordinator-claude

Thanks for your interest in contributing! This project is community-first and we welcome improvements.

## What We're Looking For

- **New skills** — codified workflows for development patterns we haven't covered
- **Domain plugins** — new reviewer personas and routing rules for your domain (mobile, DevOps, security, etc.)
- **Bug fixes** — in validation scripts, skill logic, or documentation
- **Documentation** — clarifications, examples, tutorials
- **CI improvements** — new validation checks, better error messages

## How to Contribute

1. **For substantial changes, open an issue first** to discuss direction. Drive-by typo fixes and obvious bugs don't need this; new skills, agent behavior changes, or pipeline restructures do. Saves both of us from a PR that gets closed because it's heading somewhere we don't want to go.
2. **Fork the repo** and create a feature branch
3. **Make your changes** — follow existing conventions (frontmatter format, file naming, directory structure)
4. **Run validation** locally: `python .github/scripts/run-all-checks.py`
5. **Submit a PR** with a clear description of what and why

## Pull Request Policy

`main` is protected. All changes land via PR.

- **Maintainer approval required.** Every PR needs an approving review from @dbc-oduffy before it can merge. Approvals are dismissed when new commits are pushed, and the last push must be approved.
- **CI must pass.** Validation runs automatically on every PR.
- **No force pushes, no branch deletion, conversations must be resolved.**

Maintainer self-merges (admin override on the maintainer's own PRs) are allowed — the PR ceremony itself is the speedbump.

## Conventions

### Skills
- One directory per skill under `plugins/coordinator/skills/`
- Must have a `SKILL.md` with YAML frontmatter (`name`, `description`)
- Follow the existing skill structure — see `plugins/coordinator/skills/writing-skills/SKILL.md` for the meta-skill that guides skill authoring

### Agents
- One `.md` file per agent under `plugins/{plugin}/agents/`
- Must have YAML frontmatter with `name`, `description`, `model` (opus/sonnet/haiku)
- Agent descriptions should define behavioral characteristics, not just capabilities

### Commands
- One `.md` file per command under `plugins/coordinator/commands/`
- Must be registered in the coordinator README skill count

### Validation
- All PRs must pass CI validation (runs automatically)
- If you add a new component, update the README inventory counts
- Cross-references must resolve — the `validate-references.py` script checks this

## Code of Conduct

Be kind, be constructive, be specific. We're all here to make human-AI collaboration better.

## Extension How-Tos

### How to Add a Command

Commands live at `plugins/coordinator/commands/<name>.md`. Each file needs YAML frontmatter:

```yaml
---
name: /your-command
description: One-line summary shown in the skill inventory
---
```

Body: write the command as a numbered checklist the EM follows. Cross-reference skills it calls. After adding, bump the command count in `plugins/coordinator/README.md` (search for "commands" in the inventory table).

### How to Add a Skill

Skills live at `plugins/coordinator/skills/<name>/SKILL.md`. The directory name is the skill's identifier.

Frontmatter shape:

```yaml
---
name: skill-name
description: What the skill does (one sentence)
---
```

See `plugins/coordinator/skills/validate/SKILL.md` for a minimal working example. The meta-skill that guides skill authoring is `plugins/coordinator/skills/validate/SKILL.md` — read it before writing your first skill.

After adding, update the skill inventory in `plugins/coordinator/README.md`.

### How to Add a Reviewer

Reviewer agents live at `plugins/coordinator/agents/<name>.md`. Required frontmatter:

```yaml
---
name: Reviewer Name
description: Domain and judgment posture
model: opus  # reviewers use opus; workers use sonnet
---
```

After writing the agent file:

1. Sync the `reviewer-calibration` snippet into your new file:
   `bash plugins/coordinator/bin/verify-calibration-sync.sh --fix`
2. If your reviewer fires hooks or references other agents, add a tripwire comment block in `plugins/coordinator/CLAUDE.md` (search "Tripwires" for the pattern).
3. Register the reviewer in `plugins/coordinator/README.md` under the agents inventory.

### How to Test Installer Changes

Use a scratch directory so you don't corrupt your live install:

```bash
mkdir /tmp/test-install && cd /tmp/test-install
bash /path/to/coordinator-claude/setup/install.sh --non-interactive
```

Verify that `~/.claude/plugins/coordinator-claude/` was created with the expected structure and that `~/.claude/settings.json` contains the expected hook entries.

On Windows: run the same command in Git Bash. See `setup/install.sh` for the platform detection logic.

### Prompt Style Rules

All agent and skill prompts follow the conventions in `docs/wiki/rag-bait-conventions.md`. Key requirements:

- Module/file-top purpose docstrings
- Function-level purpose lines on non-trivial public sections
- Spec backlinks to the plan that introduced the component
- Vocabulary from `CONTEXT.md` (if present) — no synonyms

The coordinator CLAUDE.md (`plugins/coordinator/CLAUDE.md`) is the authority on behavioral rules; agent prompts reference it by inclusion, not by reinventing it.

### Compatibility Rules

This project uses semantic versioning for the plugin bundle. A change is a **major-version bump** when it:

- Removes or renames a command that users may have scripted
- Changes required frontmatter fields in a way that breaks existing agent files
- Alters the `coordinator-safe-commit` or `coordinator-auto-push` calling convention
- Changes the install path or settings.json schema

Minor bumps: new commands, new reviewers, new skills, behavioral changes that don't break existing invocations. Patch bumps: documentation, script fixes, style.

The current version compatibility row lives in `README.md` (search "tested with Claude Code"). Update it on every release.

### Review Checklist for New Agent/Skill PRs

Before submitting a PR that adds or modifies an agent, skill, or command:

- [ ] Frontmatter is complete and valid (`bash plugins/coordinator/bin/lint-frontmatter.sh`)
- [ ] Reviewer agents: `verify-calibration-sync.sh --fix` run and diff is clean
- [ ] New component is registered in the README inventory count
- [ ] Cross-references (file paths, skill names, command names) resolve — `python .github/scripts/run-all-checks.py` passes
- [ ] No hardcoded local paths; build-for-someone-else's-machine rule followed
- [ ] If the component fires hooks: tripwire added to `plugins/coordinator/CLAUDE.md`
- [ ] If the component is a reviewer: upstream pre-flight wired into the producer skill

## Questions?

Open an issue with the `question` label. We're happy to help.
