# Getting Started with coordinator-claude

This guide is for humans who want to drive the install themselves or read what's happening under the hood. The first-class install path is to paste the prompt from the [README Quick Start](../README.md#quick-start) into Claude Code and let your agent do it — agents follow [docs/agent-install.md](agent-install.md), which points back here for the manual fallback.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and authenticated
- A Claude API key or Claude Pro/Team subscription
- Python 3 (for the install script's JSON handling)
- [jq](https://jqlang.github.io/jq/) — used by hook scripts for JSON parsing (`brew install jq` / `sudo apt install jq` / `winget install jqlang.jq`). Basic hooks degrade gracefully without it.

## Installation

### Automated (recommended)

```bash
git clone https://github.com/dbc-oduffy/coordinator-claude.git
cd coordinator-claude
bash setup/install.sh
```

The install script handles:
- Plugin selection (interactive — choose which reviewers to enable)
- Copying plugins to `~/.claude/plugins/coordinator-claude/`
- JSON registration (`known_marketplaces.json`, `installed_plugins.json`, `settings.json`)
- Platform detection (macOS, Linux, Windows/Git Bash, WSL)

#### Quick Start with profiles

Use `--profile` for the most common install configurations:

```bash
# Minimal: coordinator workflow only — no domain reviewers
bash setup/install.sh --profile core --non-interactive

# Standard: coordinator + web-dev + data-science reviewers (recommended for most teams)
bash setup/install.sh --profile standard --non-interactive

# Full: all plugins including deep-research and game-dev
bash setup/install.sh --profile full --non-interactive
```

| Profile | Plugins installed | When to use |
|---------|------------------|-------------|
| `core` | `coordinator` | Minimal footprint; add reviewers later |
| `standard` | `coordinator`, `web-dev`, `data-science` | Most web/backend teams; excludes deep-research (requires Agent Teams flag) |
| `full` | `coordinator`, `deep-research`, `web-dev`, `data-science`, `game-dev` | Full feature set; requires Claude Pro/Team for Agent Teams |

> **Note:** `standard` deliberately excludes `deep-research` because it dispatches Agent Teams, which requires an experimental Claude Code flag most users don't have enabled yet. Opt in via `--profile full` or explicit `--plugins` when you're ready.

#### Fine-grained control

For custom plugin selections, use `--plugins` directly:

```bash
bash setup/install.sh --plugins coordinator,game-dev --non-interactive
```

Use `--non-interactive` for unattended installs.

### Naming Reviewers (optional)

After installation, you can optionally bind personal names to role labels:

```bash
bash setup/name-personas.sh "the Staff Engineer" "Alex" "the Ambition Advocate" "Jordan"
```

This replaces role labels in prose with your chosen names — agent behavior is defined by descriptions, not names. See [docs/customization.md](customization.md) for the full role table and details.

<details>
<summary>Manual Installation</summary>

#### Step 1: Clone the repository

```bash
git clone https://github.com/dbc-oduffy/coordinator-claude.git
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
- `web` — activates the Front-End Reviewer (`web-dev:senior-front-end`) + the UX Reviewer (`web-dev:staff-ux`)
- `data-science` — activates the Data Science Reviewer (`data-science:staff-data-sci`)
- `game` — activates the Game Dev Reviewer (`game-dev:staff-game-dev`)
- `pure-docs` — documentation projects, coordinator only

Without a config file, the coordinator defaults to core-only mode — the Staff Engineer (`coordinator:staff-eng`), the Ambition Advocate (`coordinator:ambition-advocate`), and the VP-Product Reviewer (`coordinator:vp-product`) as universal reviewers.

You can also explicitly list reviewers:

```yaml
---
active_reviewers:
  - staff-eng
  - staff-game-dev
  - staff-data-sci
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
- Try `/research` for multi-agent codebase or internet research (deep-research plugin)
- Try `/execute-plan` to run a PM-approved plan directly in-session
