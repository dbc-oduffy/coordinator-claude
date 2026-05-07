# Safety — What the Installer Does and How to Undo It

This document tells you exactly what `setup/install.sh` changes on your machine, what it does *not* do, how to verify an installation, and how to reverse it completely. Every claim in this document cites a specific file or command in the repo.

---

## 1. What the installer changes

Source: `setup/install.sh`.

### Plugin files copied

The installer copies local plugin directories from the repo into your Claude user config folder:

```
~/.claude/plugins/coordinator-claude/<plugin-name>/
```

Default-on plugins copied: `coordinator`, `web-dev`, `data-science`, `deep-research`. Optional plugins (`game-dev`) require interactive selection or `--plugins game-dev`. The `notebooklm` add-on is npm-sourced and is *not* copied — it is registered via the marketplace manifest only.

If a plugin directory already exists at the destination, the installer backs it up before overwriting:

```
~/.claude/plugins/coordinator-claude/<plugin-name>.bak
```

Source: `copy_plugins()` function, `setup/install.sh` lines 579–639.

### Marketplace manifest written

```
~/.claude/plugins/coordinator-claude/.claude-plugin/marketplace.json
```

This file tells Claude Code where to find the installed plugins. It is generated from `<repo>/.claude-plugin/marketplace.json` with source paths rewritten to the flat install layout.

Source: `copy_marketplace_manifest()`, `setup/install.sh` lines 641–710.

### JSON config files edited

Three files in `~/.claude/` are modified. Each is backed up to `<filename>.bak` before any write:

| File | What changes |
|------|-------------|
| `~/.claude/plugins/known_marketplaces.json` | Adds a `"coordinator-claude"` entry pointing to the install directory |
| `~/.claude/plugins/installed_plugins.json` | Adds `<plugin-name>@coordinator-claude` entries with version and install path |
| `~/.claude/settings.json` | Adds `enabledPlugins` entries, adds `extraKnownMarketplaces` entry, appends `"Edit"` and `"Write"` to `permissions.allow` if not already present |

Source: `register_marketplace()`, `register_installed_plugins()`, `register_settings()`, `setup/install.sh` lines 725–932.

### Permissions added to settings.json

The installer adds `"Edit"` and `"Write"` to `permissions.allow` in `~/.claude/settings.json` to allow background subagents to use file-write tools. It only appends entries that are not already present. The installer prints which permissions were appended.

Source: `register_settings()`, `setup/install.sh` lines 897–931.

### Hooks registered (coordinator plugin)

The coordinator plugin ships a `hooks.json` at:

```
~/.claude/plugins/coordinator-claude/coordinator/hooks/hooks.json
```

Claude Code reads this automatically when the plugin is enabled. No separate hook registration step is required. The hooks registered are:

| Event | Hook script | Purpose |
|-------|------------|---------|
| `SessionStart` | `project-rag-detect.sh` / `.ps1` | Detect project-RAG index |
| `SessionStart` | `scripts/session-init.sh` | Load session state |
| `SessionStart` | `scripts/coordinator-reminder.sh` | Surface coordinator instructions |
| `SessionStart` | `scripts/project-orientation.sh` | Load project orientation cache |
| `SessionStart` | `scripts/ue-knowledge-distrust.sh` | Unreal Engine knowledge advisory |
| `PreToolUse` (Bash) | `scripts/validate-commit.sh` | Block disallowed commit patterns |
| `PreToolUse` (Bash) | `scripts/block-no-verify.sh` | Block `--no-verify` commits |
| `PreToolUse` (Bash) | `scripts/block-off-daily-branch.sh` | Enforce daily-branch discipline |
| `PreToolUse` (WebSearch/WebFetch) | `scripts/suggest-sonnet-research.sh` | Suggest research delegation |
| `PreToolUse` (Write/Edit/MultiEdit) | `scripts/validate-frontmatter-schema.js` | Validate frontmatter on writes |
| `PostToolUse` (Write/Edit) | `scripts/track-touched-files.sh` | Record files touched in session |
| `PostToolUse` (Read/Grep/Bash/Agent) | `scripts/track-tier-usage.sh` | Log context-tier usage |
| `PostToolUse` (ExitPlanMode) | `scripts/plan-persistence-check.sh` | Check plan was saved to disk |
| `PostToolUse` (Agent) | `scripts/agent-completion-log.sh` | Log agent completions |
| `PostToolUse` (Agent) | `scripts/track-dispatched-agents.sh` | Track dispatched agent IDs |
| `PostToolUse` (any) | `scripts/context-pressure-advisory.sh` | Monitor context window pressure |
| `PreCompact` | `scripts/context-pressure-precompact.sh` | Prompt handoff before compaction |

Source: `plugins/coordinator/hooks/hooks.json`.

### Optional add-ons

- **codex-review-gate skill** — bundled inside the coordinator plugin but stripped from the install by default. Enabled with `--enable-codex`. Removes `coordinator/skills/codex-review-gate/` from the install if not opted in. Source: `prompt_codex_addon()`, `setup/install.sh` lines 409–453.
- **notebooklm** — npm-sourced add-on. Not copied locally; registered in the marketplace manifest only. Enabled with `--install-notebooklm`. Requires Node.js 18+ and npm.

---

## 2. What the installer does NOT do

From `PRIVACY.md` (last updated 2026-04-02):

> This plugin does **not** collect, transmit, or store any user data. It has no analytics, telemetry, tracking, or external reporting of any kind.

Specifically, the installer does not:

- **Collect credentials** — no API keys, tokens, or authentication material are read or stored.
- **Start a background daemon** — no persistent process, service, or cron job is created.
- **Make network calls** — the installer is a local shell script; it copies files and edits JSON. The only network-capable step is the optional NotebookLM add-on, which requires `npx` at runtime (not at install time) and is opt-in.
- **Send telemetry** — no usage data, session data, or diagnostic pings leave your machine.
- **Modify project files** — all writes are confined to `~/.claude/`. Your project directories are untouched until you run `/project-onboarding` in a session, which writes into the project you explicitly open.

Source: `PRIVACY.md`; installer `main()` function, `setup/install.sh` lines 1070–1119.

---

## 3. How to audit the installation

Run these commands to inspect what the installer wrote. All commands read existing files and make no changes.

### Verify plugin directories exist

```bash
ls ~/.claude/plugins/coordinator-claude/
```

Expected output: one subdirectory per installed plugin (`coordinator`, `web-dev`, `data-science`, `deep-research`, and optionally `game-dev`), plus a `.claude-plugin/` directory.

### Inspect the marketplace manifest

```bash
cat ~/.claude/plugins/coordinator-claude/.claude-plugin/marketplace.json
```

### Check known_marketplaces.json

```bash
jq '.["coordinator-claude"]' ~/.claude/plugins/known_marketplaces.json
```

### Check installed_plugins.json

```bash
jq '.plugins | keys | map(select(endswith("@coordinator-claude")))' \
  ~/.claude/plugins/installed_plugins.json
```

### Check settings.json changes

```bash
# Enabled plugins
jq '.enabledPlugins | to_entries | map(select(.key | endswith("@coordinator-claude")))' \
  ~/.claude/settings.json

# Permissions added
jq '.permissions.allow' ~/.claude/settings.json

# Extra marketplace entry
jq '.extraKnownMarketplaces["coordinator-claude"]' ~/.claude/settings.json
```

### List installed hook scripts

```bash
ls ~/.claude/plugins/coordinator-claude/coordinator/hooks/scripts/
```

### Check for backup files (from collision handling)

```bash
ls ~/.claude/plugins/coordinator-claude/*.bak 2>/dev/null
ls ~/.claude/plugins/*.bak 2>/dev/null
```

---

## 4. How to uninstall

### Step 1 — Remove plugin files

```bash
rm -rf ~/.claude/plugins/coordinator-claude/
```

This removes all copied plugin directories and the marketplace manifest.

### Step 2 — Remove the known_marketplaces.json entry

```bash
jq 'del(.["coordinator-claude"])' ~/.claude/plugins/known_marketplaces.json \
  > /tmp/km.json && mv /tmp/km.json ~/.claude/plugins/known_marketplaces.json
```

### Step 3 — Remove installed_plugins.json entries

```bash
jq '.plugins |= with_entries(select(.key | endswith("@coordinator-claude") | not))' \
  ~/.claude/plugins/installed_plugins.json \
  > /tmp/ip.json && mv /tmp/ip.json ~/.claude/plugins/installed_plugins.json
```

### Step 4 — Remove settings.json entries

Remove the `enabledPlugins` entries and the `extraKnownMarketplaces` entry:

```bash
jq 'del(.enabledPlugins | to_entries | map(select(.key | endswith("@coordinator-claude"))) | .[])
  | del(.extraKnownMarketplaces["coordinator-claude"])' \
  ~/.claude/settings.json > /tmp/s.json && mv /tmp/s.json ~/.claude/settings.json
```

If you want to also remove the `"Edit"` and `"Write"` permissions the installer added (only if no other plugin or setting requires them):

```bash
jq '.permissions.allow |= map(select(. != "Edit" and . != "Write"))' \
  ~/.claude/settings.json > /tmp/s.json && mv /tmp/s.json ~/.claude/settings.json
```

### Step 5 — Restart Claude Code

Restart Claude Code to pick up the config changes. After restart, the plugins will no longer load.

### Disable without deleting

To stop the plugins loading without removing files, set each plugin to `false` in `enabledPlugins`:

```bash
jq '.enabledPlugins |= with_entries(
  if (.key | endswith("@coordinator-claude")) then .value = false else . end
)' ~/.claude/settings.json > /tmp/s.json && mv /tmp/s.json ~/.claude/settings.json
```

Then restart Claude Code.

---

## 5. Backup files

The installer creates `.bak` backups before every JSON config write and before overwriting an existing plugin directory.

| Backup path | Created when |
|-------------|-------------|
| `~/.claude/plugins/known_marketplaces.json.bak` | Always, on every install run that modifies this file |
| `~/.claude/plugins/installed_plugins.json.bak` | Always, on every install run that modifies this file |
| `~/.claude/settings.json.bak` | Always, on every install run that modifies this file |
| `~/.claude/plugins/coordinator-claude/<name>.bak` | Only when an existing plugin directory is overwritten (re-install or upgrade) |

**Retention policy:** Backups are not automatically cleaned up. Each re-run of the installer overwrites the `.bak` with the state from *before that run*, so only one generation of backup is kept. To restore from a backup:

```bash
# Restore a JSON config file (example: settings.json)
cp ~/.claude/settings.json.bak ~/.claude/settings.json

# Restore a plugin directory (example: coordinator)
rm -rf ~/.claude/plugins/coordinator-claude/coordinator
mv ~/.claude/plugins/coordinator-claude/coordinator.bak \
   ~/.claude/plugins/coordinator-claude/coordinator
```

Source: `copy_plugins()` lines 607–614, `register_marketplace()` / `register_installed_plugins()` / `register_settings()` — each calls `shutil.copy2(file, file + ".bak")` before the atomic write.
