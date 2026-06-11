const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const { PLUGINS_ROOT, dirExists, readJson, listFiles, getDirectoryMarketplaces } = require('./helpers/fs');

const marketplaces = getDirectoryMarketplaces();

// Allowlist of plausible MCP server commands
const ALLOWED_COMMANDS = new Set([
  'node', 'npx', 'python', 'python3', 'uvx', 'uv', 'bash', 'sh',
  'deno', 'bun', 'docker', 'podman', 'cargo', 'go', 'ruby', 'php',
  'pipx', 'tsx', 'ts-node', 'pnpm', 'yarn', 'bunx', 'cmd',
]);

/**
 * Find all .mcp.json files in a directory (root + one level deep).
 */
function findMcpConfigs(dir) {
  const results = [];
  if (!dirExists(dir)) return results;

  // Check root
  const rootMcp = path.join(dir, '.mcp.json');
  try {
    if (fs.statSync(rootMcp).isFile()) results.push(rootMcp);
  } catch { /* not found */ }

  // Check one level deep
  let entries;
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return results;
  }

  for (const entry of entries) {
    const subdir = path.join(dir, entry);
    try {
      if (!fs.statSync(subdir).isDirectory()) continue;
    } catch {
      continue;
    }
    const subMcp = path.join(subdir, '.mcp.json');
    try {
      if (fs.statSync(subMcp).isFile()) results.push(subMcp);
    } catch { /* not found */ }
  }

  return results;
}

/**
 * Check if a command looks like a valid executable name:
 * non-empty string, no path separators, no whitespace-only.
 */
function isPlausibleCommand(cmd) {
  if (typeof cmd !== 'string') return false;
  if (cmd.trim().length === 0) return false;
  if (cmd.includes('/') || cmd.includes('\\')) return false;
  return true;
}

/**
 * Extract server entries from an .mcp.json config.
 * Handles both formats:
 *   1. Wrapped:  { mcpServers: { name: { ... } } }
 *   2. Flat:     { name: { command: "...", args: [...] } }
 */
function extractServers(config) {
  if (config.mcpServers && typeof config.mcpServers === 'object' && !Array.isArray(config.mcpServers)) {
    return { format: 'wrapped', servers: config.mcpServers };
  }
  // Flat format — every top-level key is a server entry
  return { format: 'flat', servers: config };
}

describe('MCP server configuration (.mcp.json)', () => {
  for (const marketplace of marketplaces) {
    const marketplaceDir = marketplace.source.path;
    const metadataPath = path.join(marketplaceDir, '.claude-plugin', 'marketplace.json');

    let marketplaceData;
    try {
      marketplaceData = readJson(metadataPath);
    } catch {
      // Skip if marketplace.json is unreadable; marketplace.test.js covers that
      continue;
    }

    if (!Array.isArray(marketplaceData.plugins)) continue;

    for (const plugin of marketplaceData.plugins) {
      const pluginLabel = plugin.name || '(unnamed)';
      const pluginDir = path.resolve(marketplaceDir, plugin.source);

      if (!dirExists(pluginDir)) continue; // plugin-structure.test.js covers this

      const mcpFiles = findMcpConfigs(pluginDir);
      if (mcpFiles.length === 0) continue; // No .mcp.json — nothing to test

      for (const mcpPath of mcpFiles) {
        const relPath = path.relative(PLUGINS_ROOT, mcpPath);

        describe(`${pluginLabel} — ${relPath}`, () => {
          let config;

          it('parses as valid JSON', () => {
            config = readJson(mcpPath);
            assert.ok(config, `parsed to falsy value: ${mcpPath}`);
          });

          it('has server entries (mcpServers object or flat format)', () => {
            config = readJson(mcpPath);
            const { servers } = extractServers(config);
            assert.ok(
              servers && typeof servers === 'object' && !Array.isArray(servers),
              `expected server entries to be a non-array object in ${mcpPath}`
            );
            assert.ok(
              Object.keys(servers).length > 0,
              `expected at least one server entry in ${mcpPath}`
            );
          });

          describe('server entries', () => {
            let servers;
            try {
              const parsed = readJson(mcpPath);
              servers = extractServers(parsed).servers;
            } catch {
              return;
            }

            if (!servers || typeof servers !== 'object' || Array.isArray(servers)) return;

            for (const [serverName, serverConfig] of Object.entries(servers)) {
              describe(`server: ${serverName}`, () => {
                // Servers are either stdio (command+args) or remote (type+url)
                const isRemote = serverConfig.type === 'http' || serverConfig.type === 'sse' || serverConfig.url;

                if (isRemote) {
                  it('remote server has url (non-empty string)', () => {
                    assert.equal(
                      typeof serverConfig.url, 'string',
                      `server "${serverName}" url must be a string in ${mcpPath}`
                    );
                    assert.ok(
                      serverConfig.url.trim().length > 0,
                      `server "${serverName}" url must be non-empty in ${mcpPath}`
                    );
                  });
                } else {
                  it('has command (non-empty string)', () => {
                    assert.equal(
                      typeof serverConfig.command, 'string',
                      `server "${serverName}" command must be a string in ${mcpPath}`
                    );
                    assert.ok(
                      serverConfig.command.trim().length > 0,
                      `server "${serverName}" command must be non-empty in ${mcpPath}`
                    );
                  });

                  it('has args (array)', () => {
                    assert.ok(
                      Array.isArray(serverConfig.args),
                      `server "${serverName}" args must be an array in ${mcpPath}`
                    );
                  });

                  it('command is a plausible executable name', () => {
                    const cmd = serverConfig.command;
                    assert.ok(
                      isPlausibleCommand(cmd),
                      `server "${serverName}" command "${cmd}" does not look like a valid executable (no path separators, non-empty) in ${mcpPath}`
                    );
                  });
                }
              });
            }
          });
        });
      }
    }
  }
});
