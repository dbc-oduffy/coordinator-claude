# Contributing to coordinator-claude

Thanks for your interest in contributing! This project is community-first and we welcome improvements.

## Patches and Hotwires — Send Them Back (Even Rough)

Installation and setup lean on agents on purpose. A script-only install turned into whack-a-mole: it worked on the author's machine and broke in small, machine-specific ways on everyone else's. Handing the install to an agent that can read errors and adapt is how we route around that — but it means *your* machine is where the remaining rough edges get found.

So: **if something doesn't work, patch it. Hotwire whatever you need to get running locally — you have our blessing.** Then send the fix back. Three ways, in rough order of preference:

1. **Open a PR** with your patch (see [How to Contribute](#how-to-contribute) below).
2. **Open an issue** describing what broke and what you changed.
3. **Leave a note** — a paragraph pasted into an issue is plenty.

**Don't polish it, and don't worry about whether the code is "good."** We mean that literally. In an agentic world the valuable part is the *what, how, and why*: what you were trying to fix, how you worked around it, and why the original failed on your setup. A throwaway hack carries all three — far more than a one-line bug report ever could — and we can generalize a proper fix from it. A rough patch you actually sent beats a clean one you didn't.

The agent that did your install is well-placed to write this up — it has the error in context and made the fix. Ask it to draft the PR or issue for you.

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
   - To check specifically that plugin names in docs stay in sync with the marketplace registry (`.claude-plugin/marketplace.json`): `python .github/scripts/check-plugin-doc-drift.py`
5. **Submit a PR** with a clear description of what and why

## Pull Request Policy

`main` is protected. All changes land via PR.

- **Maintainer approval required.** Every PR needs an approving review from @dbc-oduffy before it can merge. Approvals are dismissed when new commits are pushed, and the last push must be approved.
- **CI must pass.** Validation runs automatically on every PR.
- **No force pushes, no branch deletion, conversations must be resolved.**

Maintainer self-merges (admin override on the maintainer's own PRs) are allowed — the PR ceremony itself is the speedbump.

## Conventions

### Skills
- One directory per skill under `skills/`
- Must have a `SKILL.md` with YAML frontmatter (`name`, `description`)
- Follow the existing skill structure — see `skills/validate/SKILL.md` for a minimal, well-formed example to model yours on

### Agents
- One `.md` file per agent under `agents/`
- Must have YAML frontmatter with `name`, `description`, `model` (opus/sonnet/haiku)
- Agent descriptions should define behavioral characteristics, not just capabilities

### Commands
- One `.md` file per command under `commands/`
- Must be registered in the coordinator README skill count

### Validation
- All PRs must pass CI validation (runs automatically)
- If you add a new component, update the README inventory counts
- Cross-references must resolve — the `validate-references.py` script checks this

## Code of Conduct

Be kind, be constructive, be specific. We're all here to make human-AI collaboration better.

## Extension How-Tos

### How to Add a Command

Commands live at `commands/<name>.md`. Each file needs YAML frontmatter:

```yaml
---
name: /your-command
description: One-line summary shown in the skill inventory
---
```

Body: write the command as a numbered checklist the EM follows. Cross-reference skills it calls. After adding, bump the command count in `README.md` (search for "commands" in the inventory table).

### How to Add a Skill

Skills live at `skills/<name>/SKILL.md`. The directory name is the skill's identifier.

Frontmatter shape:

```yaml
---
name: skill-name
description: What the skill does (one sentence)
---
```

See `skills/validate/SKILL.md` for a minimal working example — read a couple of existing `SKILL.md` files before writing your first skill.

After adding, update the skill inventory in `README.md`.

### How to Add a Reviewer

Reviewer agents live at `agents/<name>.md`. Required frontmatter:

```yaml
---
name: Reviewer Name
description: Domain and judgment posture
model: opus  # reviewers use opus; workers use sonnet
---
```

After writing the agent file:

1. Sync the `reviewer-calibration` snippet into your new file:
   `bin/verify-snippet-sync reviewer-calibration --fix`
2. If your reviewer fires hooks or references other agents, add a tripwire entry in `docs/wiki/coordinator-tripwires.md` (search "Tripwires" for the pattern).
3. Register the reviewer in `README.md` under the agents inventory.

### How to Test Install Changes

Install the plugins from your working clone with the native CLI, then run the post-restart wiring.
Here — unlike the user-facing install — you **do** register the clone directory, because as a
contributor you want the installed runtime to reflect your uncommitted local edits:

```bash
claude plugin marketplace add /path/to/coordinator-claude   # clone-bound on purpose (dev loop)
claude plugin install coordinator@coordinator-claude
# then, in a fresh Claude Code session:
#   /coordinator:install --check-only      # report what would change, no mutation
```

> A clone-bound (directory-source) marketplace resolves from this path on every load and is **not**
> copied into `~/.claude` — exactly what you want while iterating, but it means moving or deleting
> the clone orphans the plugins. That is why the user-facing playbook
> ([`docs/agent-install.md`](docs/agent-install.md)) registers the public GitHub repo instead. When
> you are done developing, re-add from GitHub (`claude plugin marketplace add dbc-oduffy/coordinator-claude`)
> to return to a self-contained install.

Verify that the plugins resolve under `~/.claude/plugins/cache/coordinator-claude/` and that `/coordinator:install` reports a clean status table (env var, machine-local, hooks). `/coordinator:install --check-only` is the read-only way to inspect the result without mutating state.

On Windows: run the CLI in Git Bash; the platform-specific wiring (path translation, the `python3` App-Execution-Alias shim) lives in `lib/install-substrate.py`, exercised by `/coordinator:install` Phase 3.

### Prompt Style Rules

All agent and skill prompts follow the conventions in `docs/wiki/rag-bait-conventions.md`. Key requirements:

- Module/file-top purpose docstrings
- Function-level purpose lines on non-trivial public sections
- Spec backlinks to the plan that introduced the component
- Vocabulary from `CONTEXT.md` (if present) — no synonyms

Coordinator behavioral doctrine is the authority agent prompts reference by inclusion, not by reinventing it in each prompt file — see the shared snippets synced into agent frontmatter (§ How to Add a Reviewer above) for the pattern.

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

- [ ] Frontmatter is complete and valid (`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/lint-frontmatter"`)
- [ ] Reviewer agents: `bin/verify-snippet-sync reviewer-calibration --fix` run and diff is clean
- [ ] New component is registered in the README inventory count
- [ ] Cross-references (file paths, skill names, command names) resolve — `python .github/scripts/run-all-checks.py` passes
- [ ] No hardcoded local paths; build-for-someone-else's-machine rule followed
- [ ] If the component fires hooks: tripwire added to `docs/wiki/coordinator-tripwires.md`
- [ ] If the component is a reviewer: upstream pre-flight wired into the producer skill

## Questions?

Open an issue with the `question` label. We're happy to help.
