const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { PLUGINS_ROOT, fileExists, dirExists, readJson, getDirectoryMarketplaces } = require('./helpers/fs');

const installed = readJson(path.join(PLUGINS_ROOT, 'installed_plugins.json'));
const knownMarketplaces = readJson(path.join(PLUGINS_ROOT, 'known_marketplaces.json'));
const directoryMarketplaces = getDirectoryMarketplaces();

// Build a map of marketplace name -> set of plugin names declared in its marketplace.json
const marketplacePluginSets = new Map();
for (const mp of directoryMarketplaces) {
  const mpJsonPath = path.join(mp.installLocation, '.claude-plugin', 'marketplace.json');
  if (fileExists(mpJsonPath)) {
    const mpJson = readJson(mpJsonPath);
    const names = new Set((mpJson.plugins || []).map(p => p.name));
    marketplacePluginSets.set(mp.name, names);
  }
}

describe('Cross-reference integrity', () => {

  describe('Plugin keys reference valid marketplaces', () => {
    for (const [pluginKey] of Object.entries(installed.plugins)) {
      const parts = pluginKey.split('@');
      if (parts.length < 2) continue;
      const marketplaceName = parts.slice(1).join('@');

      // Only test directory marketplaces
      const isDirectory = directoryMarketplaces.some(mp => mp.name === marketplaceName);
      if (!isDirectory) continue;

      it(`${pluginKey} references marketplace "${marketplaceName}" which exists in known_marketplaces.json`, () => {
        assert.ok(
          knownMarketplaces[marketplaceName],
          `Marketplace "${marketplaceName}" referenced by "${pluginKey}" not found in known_marketplaces.json`
        );
      });
    }
  });

  describe('Plugins have matching entries in marketplace.json', () => {
    for (const [pluginKey] of Object.entries(installed.plugins)) {
      const parts = pluginKey.split('@');
      if (parts.length < 2) continue;
      const pluginName = parts[0];
      const marketplaceName = parts.slice(1).join('@');

      const isDirectory = directoryMarketplaces.some(mp => mp.name === marketplaceName);
      if (!isDirectory) continue;

      it(`${pluginKey} has a matching entry in ${marketplaceName}/marketplace.json`, () => {
        const pluginSet = marketplacePluginSets.get(marketplaceName);
        assert.ok(
          pluginSet,
          `Could not load marketplace.json for "${marketplaceName}"`
        );
        assert.ok(
          pluginSet.has(pluginName),
          `Plugin "${pluginName}" not found in ${marketplaceName}/.claude-plugin/marketplace.json plugins array`
        );
      });
    }
  });

  describe('Install paths for directory marketplace plugins exist on disk', () => {
    for (const [pluginKey, entries] of Object.entries(installed.plugins)) {
      const parts = pluginKey.split('@');
      if (parts.length < 2) continue;
      const marketplaceName = parts.slice(1).join('@');

      const isDirectory = directoryMarketplaces.some(mp => mp.name === marketplaceName);
      if (!isDirectory) continue;

      for (const entry of entries) {
        it(`${pluginKey} installPath exists: ${entry.installPath}`, () => {
          assert.ok(
            dirExists(entry.installPath),
            `installPath does not exist: ${entry.installPath}`
          );
        });
      }
    }
  });

  describe('Hook script references resolve to existing files', () => {
    for (const [pluginKey, entries] of Object.entries(installed.plugins)) {
      for (const entry of entries) {
        const hooksJsonPath = path.join(entry.installPath, 'hooks', 'hooks.json');
        if (!fileExists(hooksJsonPath)) continue;

        const hooksData = readJson(hooksJsonPath);
        const hooksObj = hooksData.hooks || hooksData;

        for (const [eventType, matcherGroups] of Object.entries(hooksObj)) {
          if (!Array.isArray(matcherGroups)) continue;

          for (const matcherGroup of matcherGroups) {
            const hookList = matcherGroup.hooks || [];
            for (const hook of hookList) {
              if (!hook.command) continue;

              // Replace ${CLAUDE_PLUGIN_ROOT} with actual plugin path
              const expanded = hook.command.replace(/\$\{CLAUDE_PLUGIN_ROOT\}/g, entry.installPath);

              // Extract the file path from the command string.
              // Handles several shapes:
              //   bash <script>  /  sh <script>  /  node <script>  /  python <script>
              //   pwsh -File <script>  /  pwsh -NonInteractive -File <script>
              //   Compound commands joined with || or && — validate the first branch only.
              //   Redirections (2>/dev/null, etc.) are stripped before parsing.
              const firstBranch = expanded.split(/\s*\|\|\s*|\s*&&\s*/)[0].trim();
              const noRedirects = firstBranch.replace(/\s*\d*>[&\d]?\S*/g, '').trim();
              const stripped = noRedirects.replace(/"/g, '');
              const tokens = stripped.split(/\s+/).filter(Boolean);
              const interpreters = ['bash', 'sh', 'node', 'python', 'python3'];
              let scriptPath;
              if (tokens[0] === 'pwsh') {
                // pwsh -File <script>  or  pwsh -NonInteractive -File <script>
                const fileIdx = tokens.findIndex(t => t.toLowerCase() === '-file');
                scriptPath = fileIdx !== -1 ? tokens[fileIdx + 1] : undefined;
              } else if (interpreters.includes(tokens[0])) {
                scriptPath = tokens[1];
              } else {
                scriptPath = tokens[0];
              }

              if (!scriptPath) continue;

              // Normalize path separators for Windows
              const normalizedPath = path.resolve(scriptPath);

              it(`${pluginKey} [${eventType}] hook script exists: ${normalizedPath}`, () => {
                assert.ok(
                  fileExists(normalizedPath),
                  `Hook script not found: ${normalizedPath} (from command: "${hook.command}")`
                );
              });
            }
          }
        }
      }
    }
  });
});
