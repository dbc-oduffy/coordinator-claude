# Getting Started with coordinator-claude

This guide walks you through installing the coordinator-claude plugins and running your first session.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and authenticated
- A Claude API key or Claude Pro/Team subscription
- Python 3 (for the install script's JSON handling)
- [jq](https://jqlang.github.io/jq/) — used by hook scripts for JSON parsing (`brew install jq` / `sudo apt install jq` / `winget install jqlang.jq`). Basic hooks degrade gracefully without it, but the executor-exit-watchdog requires jq.

### Optional: Temporal Memory

The [remember plugin](https://github.com/anthropics/claude-plugins-official) (`claude-plugins-official` marketplace) adds automatic session-by-session memory — Haiku summarizes what happened in rolling daily/weekly/archive files under `.remember/`. The coordinator's `/update-docs` and `/workday-complete` commands integrate with it when present (cross-referencing activity against the project tracker, enriching the completed archive audit). Without it, those steps are silently skipped — no core functionality depends on it.

To install: `claude plugin install remember` from the `claude-plugins-official` marketplace. On Windows, run `bash setup/patch-remember-plugin.sh` after installing to fix path resolution for the plugin-cache layout.

## Installation

### Automated (recommended)

```bash
git clone https://github.com/oduffy-delphi/coordinator-claude.git
cd coordinator-claude
bash setup/install.sh
```

The install script handles:
- Plugin selection (interactive — choose which reviewers to enable)
- Copying plugins to `~/.claude/plugins/coordinator-claude/`
- JSON registration (`known_marketplaces.json`, `installed_plugins.json`, `settings.json`)
- Platform detection (macOS, Linux, Windows/Git Bash, WSL)

Use `--non-interactive` for unattended installs (installs coordinator + deep-research + web-dev + data-science).
Use `--plugins coordinator,game-dev` to specify an explicit plugin list.

### Persona Customization

After installation, you can rename the reviewer personas:

```bash
bash setup/rename-personas.sh Patrik "Alex" Zolí "Jordan"
```

This renames display names in prose — agent behavior is defined by descriptions, not names. See [docs/customization.md](customization.md) for details.

<details>
<summary>Manual Installation</summary>

#### Step 1: Clone the repository

```bash
git clone https://github.com/oduffy-delphi/coordinator-claude.git
cd coordinator-claude
```

#### Step 2: Create the plugins directory

```bash
mkdir -p ~/.claude/plugins/coordinator-claude
```

#### Step 3: Copy plugins

```bash
cp -r plugins/* ~/.claude/plugins/coordinator-claude/
```

#### Step 4: Register the marketplace

Add an entry to `~/.claude/plugins/known_marketplaces.json` (create if it doesn't exist):

```json
{
  "coordinator-claude": {
    "source": {
      "source": "directory",
      "path": "/home/{USERNAME}/.claude/plugins/coordinator-claude"
    },
    "installLocation": "/home/{USERNAME}/.claude/plugins/coordinator-claude",
    "lastUpdated": "2026-03-20T00:00:00.000Z"
  }
}
```

Replace paths with your actual home directory.

#### Step 5: Register plugins

Create or edit `~/.claude/plugins/installed_plugins.json`:

```json
{
  "version": 2,
  "plugins": {
    "coordinator@coordinator-claude": [{
      "scope": "user",
      "installPath": "/home/{USERNAME}/.claude/plugins/coordinator-claude/coordinator",
      "version": "1.3.0",
      "installedAt": "2026-03-20T00:00:00Z",
      "lastUpdated": "2026-03-20T00:00:00Z"
    }],
    "web-dev@coordinator-claude": [{
      "scope": "user",
      "installPath": "/home/{USERNAME}/.claude/plugins/coordinator-claude/web-dev",
      "version": "1.3.0",
      "installedAt": "2026-03-20T00:00:00Z",
      "lastUpdated": "2026-03-20T00:00:00Z"
    }],
    "data-science@coordinator-claude": [{
      "scope": "user",
      "installPath": "/home/{USERNAME}/.claude/plugins/coordinator-claude/data-science",
      "version": "1.3.0",
      "installedAt": "2026-03-20T00:00:00Z",
      "lastUpdated": "2026-03-20T00:00:00Z"
    }],
    "game-dev@coordinator-claude": [{
      "scope": "user",
      "installPath": "/home/{USERNAME}/.claude/plugins/coordinator-claude/game-dev",
      "version": "1.3.0",
      "installedAt": "2026-03-20T00:00:00Z",
      "lastUpdated": "2026-03-20T00:00:00Z"
    }],
    "deep-research@coordinator-claude": [{
      "scope": "user",
      "installPath": "/home/{USERNAME}/.claude/plugins/coordinator-claude/deep-research",
      "version": "1.0.0",
      "installedAt": "2026-03-20T00:00:00Z",
      "lastUpdated": "2026-03-20T00:00:00Z"
    }],
    "notebooklm@coordinator-claude": [{
      "scope": "user",
      "installPath": "/home/{USERNAME}/.claude/plugins/coordinator-claude/notebooklm",
      "version": "1.0.0",
      "installedAt": "2026-03-20T00:00:00Z",
      "lastUpdated": "2026-03-20T00:00:00Z"
    }]
  }
}
```

> **Note:** `game-dev` and `notebooklm` are included but disabled by default (see Step 6). `deep-research` requires the Agent Teams experimental flag — see [README prerequisites](../README.md#prerequisites).

#### Step 6: Enable plugins

Create or edit `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Edit",
      "Write"
    ]
  },
  "enabledPlugins": {
    "coordinator@coordinator-claude": true,
    "deep-research@coordinator-claude": true,
    "web-dev@coordinator-claude": true,
    "data-science@coordinator-claude": true,
    "game-dev@coordinator-claude": false,
    "notebooklm@coordinator-claude": false
  },
  "extraKnownMarketplaces": {
    "coordinator-claude": {
      "source": {
        "source": "directory",
        "path": "/home/{USERNAME}/.claude/plugins/coordinator-claude"
      }
    }
  }
}
```

> **Important:** The `permissions.allow` array is required for background subagents. Without it, executor and enricher agents cannot write files — `defaultMode: "dontAsk"` only applies to the interactive session, not background agents.
>
> `extraKnownMarketplaces` is an **object**, not an array. Each key is a marketplace name with a nested `source` object.

#### Step 7: Restart Claude Code

Changes take effect on the next session start. Open a new terminal or restart Claude Code.

</details>

## First Run

Start a Claude Code session in any project directory and run:

```
/session-start
```

This orients the session: loads orientation documents, surfaces pending work, and sets up the EM operating mode.

### What to expect

On first run, `/session-start` will:
1. Check for orientation documents (repo map, DIRECTORY.md)
2. Report any pending handoffs
3. Set the EM role and load pipeline awareness
4. Offer to help you choose what to work on

If this is a brand new project, run `/project-onboarding` to bootstrap the tracking infrastructure (tracker, tasks directory, archive).

## Per-Project Configuration

Create `.claude/coordinator.local.md` in your project root to configure which domain plugins activate:

```yaml
---
project_type: web
---
```

Valid `project_type` values:
- `web` — activates Palí (frontend) + Fru (UX) reviewers
- `data-science` — activates Camelia (ML/data) reviewer
- `game` — activates Sid (Unreal Engine) reviewer
- `pure-docs` — documentation projects, coordinator only

Without a config file, the coordinator defaults to core-only mode (Patrik + Zolí universal reviewers).

You can also explicitly list reviewers:

```yaml
---
active_reviewers:
  - patrik
  - sid
  - camelia
---
```

## Troubleshooting

### Plugins not showing as skills/commands

1. Check `enabledPlugins` in `settings.json` — must be `true`
2. Check `installed_plugins.json` — must have entry with correct `installPath`
3. Verify the install path exists and contains the plugin files
4. Restart Claude Code (changes take effect on next session)

### `claude plugin install` fails silently

This is a known issue with directory-based local marketplaces. Use the manual JSON entries described in Steps 5-6 instead.

### Plugin cache out of sync

Claude Code caches plugins by version at `~/.claude/plugins/cache/`. If you edit plugin source files, the cache won't update automatically.

**Quick fix** — run the dev-sync script:
```bash
bash setup/dev-sync.sh              # sync all plugins
bash setup/dev-sync.sh coordinator   # sync one plugin
```

**Alternative** — bump the `version` in the plugin's `.claude-plugin/plugin.json`. Claude Code creates a fresh cache on next session start when it sees a new version.

**Nuclear option** — delete the cache directory to force a full rebuild:
```bash
rm -rf ~/.claude/plugins/cache/coordinator-claude
```

## Next Steps

- Read [docs/architecture.md](architecture.md) to understand how the system works
- Read [docs/customization.md](customization.md) to learn how to adapt personas and add skills
- Try `/review-dispatch` to route code to a reviewer
- Try `/deep-research` for multi-agent codebase or internet research
- Try `/delegate-execution` to dispatch an executor agent on a well-specified task
