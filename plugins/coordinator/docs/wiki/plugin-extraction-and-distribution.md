# Plugin Extraction and Distribution

**Provenance:** consolidated 2026-05-05 from `tasks/lesson-triage-2026-05-05/SYNTHESIS.md` §B4. Source extracts: coord E13/E15, project-rag E12/E29/E30/E31, holodeck E38.

When extracting a plugin from its source repo into a standalone distributable, "it works on my machine" is not the bar. External consumers run from a clean profile, on different OSes, with different drive layouts, against fresh `~/.claude.json` state. The extraction is incomplete until each of the surfaces below is verified.

## The 10-Item Checklist

### 1. Source-repo cleanup

Sweep the source repo for orphan plugin trees, install scripts, local configs, and stale tool-name references that survive the extraction. The plugin's old in-repo location often leaves debris that misleads future readers and breaks reproducibility.

### 2. Plugin generalization — `${CLAUDE_PLUGIN_ROOT}`, not hardcoded paths

The plugin's own commands, hooks, and skills must resolve their install dir via `${CLAUDE_PLUGIN_ROOT}`, never via hardcoded sibling-repo paths. Hardcoded paths embed the author's machine layout into the shipped artifact and break on every external consumer.

### 3. Env/config rename to neutral names (with deprecation fallback)

Brand-bound env vars, paths, and config keys (`HOLODECK_*`, `DRONESIM_*`, etc.) get renamed to neutral names. Keep a deprecation fallback that reads the old name and emits a one-line warning so existing consumers don't break overnight.

### 4. Runtime detachment — sever venv dependency on source repo

If the plugin's MCP server runs from a source tree (`pip install -e <source-path>`), document this explicitly. The runtime version is the checked-out branch HEAD, **not** what `pip show <pkg>` reports — which is often a separately-installed wheel. Conflating the two leads to "install v0.2.3" being a near-no-op when the consumer's MCP entry already points at source-path. Surface the source-path-vs-wheel distinction in install docs.

### 5. Doc sync

Update READMEs, install instructions, and any cross-repo references that pointed at the old location. Stale doc references → repoint to existing surfaces when content is already covered; create new pages only when genuinely missing (don't default to "create the missing doc" for every broken link).

### 6. Marketplace.json + per-user `~/.claude.json` mcpServers cleanup

Easy to forget: the per-user `~/.claude.json` `mcpServers` registration AND the marketplace.json entry both auto-register the now-deleted server file. Both need to be cleaned up at extraction time, otherwise `claude mcp list` carries dead entries until the next user notices and asks.

### 7. Plugin enablement is **per-project**, not user-global

Plugin enablement (`enabledPlugins["<name>@<marketplace>"]`) belongs in `<project>/.claude/settings.local.json`, not `~/.claude/settings.json`. The marketplace and install record stay user-global, but the install record uses `scope:"project"` with `projectPath` so a second project on the same machine appends a separate record rather than overwriting the first.

Writing enablement to `~/.claude/settings.json` surfaces the plugin's slash commands in every project on the machine — not just the one that opted in. Mirrors the same wrong-shape failure as writing MCP server args to top-level `mcpServers` instead of `projects[<root>].mcpServers`.

### 8. Plugin installers must register enablement, not just MCP wiring

A Claude Code plugin distributed via shell installer must touch **three** files for slash commands and agents to surface:

- `~/.claude/settings.json` (or `<project>/.claude/settings.local.json`) — `enabledPlugins`
- `~/.claude/plugins/known_marketplaces.json`
- `~/.claude/plugins/installed_plugins.json`

Registering only the MCP server in `~/.claude.json` is necessary but not sufficient. Test installs from a profile that has never run `/plugin install` to catch this — installs that happen to work on the author's profile rely on a one-time manual `/plugin install` long forgotten.

### 9. Plugin disable ≠ uninstall

Setting `enabledPlugins.foo: false` leaves the cache intact (`~/.claude/plugins/cache/<marketplace>/<plugin>/`) and a re-enable instantly resurrects the plugin. For a true uninstall when `claude plugin uninstall` reports "not found in installed plugins" (cache-only loads), `rm -rf` the cache dir AND delete the `enabledPlugins` key from every project's settings.json.

### 10. Plugin hooks belong in `hooks/hooks.json`, not user-scope `settings.json`

A SessionStart/PreToolUse/etc. hook registered in `~/.claude/settings.json` works on the author's machine but doesn't follow the plugin to marketplace consumers — install lays down the script but never registers the event. Always ship `hooks/hooks.json` alongside the script in the plugin tree so install auto-wires it. User-scope settings is for non-plugin overrides only.

## Test From a Clean Profile

The single highest-leverage validation: run the install script from a profile that has never used Claude Code before. Anything that "just worked" on the author's machine from prior manual setup will fail loudly. This catches gaps 1, 6, 8, 9, and 10 in one pass.
