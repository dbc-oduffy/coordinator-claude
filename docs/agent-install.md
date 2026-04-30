# Agent Install Playbook

> Audience: **Claude (or another coding agent), not a human.** A human pasted a one-liner into their session pointing you here. Your job: install the coordinator-claude plugin set into the user's Claude Code environment, validate it, and queue `/project-onboarding` as the next step after the user restarts Claude Code.

## What you are installing

`coordinator-claude` is a Claude Code plugin bundle. Installing means:

1. Cloning (or locating) the repo on the user's machine.
2. Copying plugin directories into `~/.claude/plugins/coordinator-claude/`.
3. Writing/merging three JSON config files: `~/.claude/plugins/known_marketplaces.json`, `~/.claude/plugins/installed_plugins.json`, `~/.claude/settings.json`.
4. Confirming with the user, restarting Claude Code, and running `/project-onboarding` to set up tracking infrastructure in the current project.

## Recommended path: run the installer

The repo ships `setup/install.sh` which does all of (2) and (3) correctly across macOS / Linux / Git Bash on Windows / WSL. Use it. Do not reinvent the JSON-merge logic — there are platform-specific path-translation traps it already handles.

```bash
# If the user hasn't cloned yet:
git clone https://github.com/dbc-oduffy/coordinator-claude.git ~/coordinator-claude
cd ~/coordinator-claude

# Interactive (recommended — let the user pick reviewers):
bash setup/install.sh

# Non-interactive defaults (coordinator + web-dev + data-science + remember):
bash setup/install.sh --non-interactive

# Explicit plugin list:
bash setup/install.sh --plugins coordinator,game-dev,remember
```

The installer prints a summary at the end. Read it. If it reports validation errors, surface them to the user verbatim — don't paper over.

### Plugin selection — what to recommend

Default `on`: `coordinator`, `web-dev`, `data-science`, `remember`. Default `off`: `game-dev` (Unreal Engine — only enable if the user works on UE projects). `notebooklm` is an opt-in add-on that requires Node 18+ and is prompted separately.

If the user gave you any signal about their project type (web, ML, game, Unreal), pick accordingly. Otherwise ask once, briefly, before running the installer.

### Companion plugins (separate installs)

- **deep-research** — multi-agent research pipelines. Lives in its own repo: https://github.com/dbc-oduffy/deep-research-claude. Install separately if the user wants `/research`, `/repo-research`, `/structured-research`. Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `~/.claude/settings.json` env.
- **codex-plugin-cc** — Codex CLI integration. Optional. https://github.com/openai/codex-plugin-cc.
- **clangd-lsp**, **Context7** — optional, install on demand.

Mention these only if the user asks "what else?" or if their use case clearly needs them. Don't install them by default.

## Prerequisites you should check

Before running the installer, verify:

- **Claude Code CLI** on PATH: `claude --version`. If missing, link the user to https://docs.anthropic.com/en/docs/claude-code and stop.
- **Python 3** on PATH. The installer uses Python for JSON manipulation. If missing, link to https://python.org and stop.
- **jq** on PATH (`jq --version`). Hooks use it. If missing, the installer will warn and offer to continue — recommend installing it (`brew install jq` / `sudo apt install jq` / `winget install jqlang.jq`) but accept the user's call.
- **Node 18+** *only if* the user wants the NotebookLM add-on. Otherwise irrelevant.

The installer itself re-checks all of these and fails loudly on missing hard requirements. You don't need to be exhaustive — a quick sanity check before invoking it is sufficient.

## Manual install (fallback only)

Use only if `setup/install.sh` cannot run (no bash, sandboxed environment, etc.). The mechanical steps:

1. `mkdir -p ~/.claude/plugins/coordinator-claude`
2. `cp -r plugins/* ~/.claude/plugins/coordinator-claude/`
3. Copy `.claude-plugin/marketplace.json` into `~/.claude/plugins/coordinator-claude/.claude-plugin/marketplace.json`, rewriting each plugin's `source` field from `./plugins/<name>` to `./<name>` (flat layout).
4. Merge an entry into `~/.claude/plugins/known_marketplaces.json` for `coordinator-claude` pointing at the install dir.
5. Merge entries into `~/.claude/plugins/installed_plugins.json` (one per plugin, key `<name>@coordinator-claude`, with `installPath` and `version` from each plugin's `plugin.json`).
6. Merge `~/.claude/settings.json`: enable plugins under `enabledPlugins`, register the marketplace under `extraKnownMarketplaces`, and add `Edit` and `Write` to `permissions.allow` (background subagents need these — `defaultMode: dontAsk` does not propagate to them).

Schema reference: read `setup/install.sh` directly. It is the spec. On Windows (Git Bash / WSL), config files store **native** Windows paths (`C:\Users\...`), not POSIX (`/c/...`) — `install.sh::native_path` does this translation.

## After install — what to tell the user

The installer prints "restart Claude Code, then run /session-start." Override that with this:

> **Installed. Restart Claude Code, then run `/project-onboarding` to bootstrap tracking infrastructure in this project (tracker, tasks/, archive/). After that, `/session-start` orients each working session.**

`/project-onboarding` is the right immediate next step for a fresh project — `/session-start` assumes the orientation files already exist. For a project that already has coordinator scaffolding (re-installing on a known repo), `/session-start` is fine.

## Optional follow-ups to mention

- **Rename personas** if the user wants different names for reviewers: `bash setup/rename-personas.sh Patrik "Alex" Zolí "Jordan"`. Display-only — agent behaviour is unchanged.
- **Per-project config**: `.claude/coordinator.local.md` with `project_type: web|data-science|game|pure-docs` controls which domain reviewers activate. Without it, only the universal reviewers (Patrik, Zolí) run.
- **Plugin cache out of sync** after editing plugin source: `bash setup/dev-sync.sh`. Rare for end users — relevant if the user is contributing to the plugins themselves.
- **`remember` plugin on Windows** needs `bash setup/patch-remember-plugin.sh` after install if path resolution fails.

## Failure modes to watch for

- **`claude plugin install` from a directory marketplace** silently fails on some Claude Code versions. The JSON-merge approach in `install.sh` is the reliable path — don't suggest the CLI command.
- **`enabledPlugins` keys must be `<name>@coordinator-claude`**, not bare `<name>`. Common typo.
- **`extraKnownMarketplaces` is an object, not an array.** Each key is the marketplace name.
- **Path translation on Windows.** Forget native paths in JSON and Claude Code will fail to resolve plugins. The installer handles this; if you go manual, replicate it.

## Where the deeper docs live

- [docs/getting-started.md](getting-started.md) — first-run usage, per-project config, troubleshooting (audience: human, post-install).
- [docs/architecture.md](architecture.md) — how the system works.
- [docs/customization.md](customization.md) — adding skills, persona templates, CI checks.
- [setup/install.sh](../setup/install.sh) — canonical spec for what "installed" means.
