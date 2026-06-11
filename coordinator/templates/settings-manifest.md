# Settings Manifest — Machine-Specific Configuration

> Companion to `settings.json`. Read this at orient time to understand what's
> portable, what's machine-specific, and what gates each setting.
>
> **Executable truth lives in `bin/platform-localize.sh`** — the
> `plugin_infra_requirements` dict is the canonical mapping of plugin →
> registry key. This manifest is the human/EM-readable context around it.

## Architecture

```
settings.json          (tracked)    — union of what ALL machines need
settings.local.json    (gitignored) — per-machine overrides, auto-generated
known_marketplaces.json (gitignored) — CC plugin discovery cache (bug #51806)
registry.local.toml    (gitignored) — per-machine repo paths and values
```

`settings.local.json` takes precedence over `settings.json` (Claude Code
Local > User scope). The `platform-localize.sh` SessionStart hook generates
it from what's actually present on this machine.

## Plugin Infrastructure Requirements

Each plugin below requires specific infrastructure to be useful. The hook
reads `machine-local/registry.local.toml` keys to determine availability.
If the registry key is empty, the plugin is disabled via `settings.local.json`.

| Plugin | Marketplace | Registry Key | Infrastructure |
|--------|-------------|-------------|----------------|
| *(none by default)* | | | |

The coordinator's core plugins (coordinator, deep-research, web-dev,
data-science) are universally available — they live under `~/.claude/plugins/`
and have no external infrastructure dependency.

**To add a gated plugin:** see `bin/platform-localize.sh` §
`plugin_infra_requirements` for the extension point and step-by-step
instructions.

## Marketplace Registration

Directory-source marketplaces require absolute paths that differ per machine.
The `platform-localize.sh` hook discovers marketplace directories by scanning
`~/.claude/plugins/` for directories containing `.claude-plugin/`, then writes
correct absolute paths to:
- `settings.local.json` → `extraKnownMarketplaces` (the documented mechanism)
- `known_marketplaces.json` (the file CC actually reads — bug #51806)

## Environment Variables

| Variable | In `settings.json` | Purpose | Machine-specific? |
|----------|--------------------|---------|--------------------|
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | `"1"` | Agent Teams + deep-research | No — all machines |
| `CLAUDE_CODE_USE_POWERSHELL_TOOL` | `"0"` | Suppress PowerShell tool flash | No — `"0"` is safe everywhere. Disables the tool on Windows; no-op on Mac/Linux |
| `CLAUDE_HOME` | *(not in settings.json)* | Override `~/.claude` root | Yes — `platform-localize.sh` honors it. Default: `$HOME/.claude` |

## Adding a New Machine

1. Clone / sync `~/.claude` via git
2. Create `machine-local/registry.local.toml` — populate repo paths for
   repos present on this machine (empty string for absent repos)
3. Start a Claude Code session — `platform-localize.sh` fires automatically:
   - Generates `settings.local.json` with correct paths and plugin overrides
   - Patches `known_marketplaces.json`
4. Restart Claude Code (env vars + plugin enablements read at boot)

## Adding a New Gated Plugin

When a new plugin depends on machine-specific infrastructure:

1. Add the plugin to `settings.json` `enabledPlugins` as `true` (the base default)
2. Add a key declaration (empty string) to `machine-local/registry.toml` (tracked). Per-machine values go in `registry.local.toml` via `machine-local set <key> <path>`
3. If the marketplace is external (not under `~/.claude/plugins/`), also add to `external_marketplaces` in `bin/platform-localize.sh`
4. Add the mapping to `bin/platform-localize.sh` `plugin_infra_requirements`
5. Add a row to this manifest's Infrastructure Requirements table
6. On machines that have the infrastructure: `machine-local set <key> <path>`
7. On machines that don't: leave the key empty — the hook disables the plugin
