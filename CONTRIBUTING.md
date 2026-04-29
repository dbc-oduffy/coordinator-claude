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

## Questions?

Open an issue with the `question` label. We're happy to help.
