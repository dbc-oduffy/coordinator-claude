# Contributing to coordinator-claude

Thanks for your interest in contributing! This project is community-first and we welcome improvements.

## What We're Looking For

- **New skills** — codified workflows for development patterns we haven't covered
- **Domain plugins** — new reviewer personas and routing rules for your domain (mobile, DevOps, security, etc.)
- **Bug fixes** — in validation scripts, skill logic, or documentation
- **Documentation** — clarifications, examples, tutorials
- **CI improvements** — new validation checks, better error messages

## How to Contribute

1. **Fork the repo** and create a feature branch
2. **Make your changes** — follow existing conventions (frontmatter format, file naming, directory structure)
3. **Run validation** locally: `python .github/scripts/run-all-checks.py`
4. **Submit a PR** with a clear description of what and why

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
