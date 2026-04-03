const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const { dirExists, readJson, getPlugins } = require('./helpers/fs');

const ALLOWED_COMMANDS = new Set([
  'node', 'npx', 'python', 'python3', 'uvx', 'uv', 'bash', 'sh',
  'deno', 'bun', 'docker', 'podman', 'cargo', 'go', 'ruby', 'php',
  'pipx', 'tsx', 'ts-node', 'pnpm', 'yarn', 'bunx', 'cmd',
]);

function findMcpConfigs(dir) {
  const results = [];
  if (!dirExists(dir)) return results;

  const rootMcp = path.join(dir, '.mcp.json');
  try { if (fs.statSync(rootMcp).isFile()) results.push(rootMcp); } catch {}

  let entries;
  try { entries = fs.readdirSync(dir); } catch { return results; }

  for (const entry of entries) {
    const subdir = path.join(dir, entry);
    try { if (!fs.statSync(subdir).isDirectory()) continue; } catch { continue; }
    const subMcp = path.join(subdir, '.mcp.json');
    try { if (fs.statSync(subMcp).isFile()) results.push(subMcp); } catch {}
  }
  return results;
}

function isPlausibleCommand(cmd) {
  if (typeof cmd !== 'string' || cmd.trim().length === 0) return false;
  if (cmd.includes('/') || cmd.includes('\\')) return false;
  return true;
}

function extractServers(config) {
  if (config.mcpServers && typeof config.mcpServers === 'object' && !Array.isArray(config.mcpServers)) {
    return { format: 'wrapped', servers: config.mcpServers };
  }
  return { format: 'flat', servers: config };
}

const plugins = getPlugins();

describe('MCP server configuration (.mcp.json)', () => {
  for (const plugin of plugins) {
    if (!dirExists(plugin.dir)) continue;

    const mcpFiles = findMcpConfigs(plugin.dir);
    if (mcpFiles.length === 0) continue;

    for (const mcpPath of mcpFiles) {
      const relPath = path.relative(plugin.dir, mcpPath);

      describe(`${plugin.name} — ${relPath}`, () => {
        let config;

        it('parses as valid JSON', () => {
          config = readJson(mcpPath);
          assert.ok(config, `parsed to falsy value: ${mcpPath}`);
        });

        it('has server entries', () => {
          config = readJson(mcpPath);
          const { servers } = extractServers(config);
          assert.ok(
            servers && typeof servers === 'object' && !Array.isArray(servers),
            `expected server entries to be a non-array object in ${mcpPath}`
          );
          assert.ok(Object.keys(servers).length > 0, `expected at least one server entry in ${mcpPath}`);
        });

        describe('server entries', () => {
          let servers;
          try {
            const parsed = readJson(mcpPath);
            servers = extractServers(parsed).servers;
          } catch { return; }

          if (!servers || typeof servers !== 'object' || Array.isArray(servers)) return;

          for (const [serverName, serverConfig] of Object.entries(servers)) {
            describe(`server: ${serverName}`, () => {
              const isRemote = serverConfig.type === 'http' || serverConfig.type === 'sse' || serverConfig.url;

              if (isRemote) {
                it('remote server has url (non-empty string)', () => {
                  assert.equal(typeof serverConfig.url, 'string', `server "${serverName}" url must be a string`);
                  assert.ok(serverConfig.url.trim().length > 0, `server "${serverName}" url must be non-empty`);
                });
              } else {
                it('has command (non-empty string)', () => {
                  assert.equal(typeof serverConfig.command, 'string', `server "${serverName}" command must be a string`);
                  assert.ok(serverConfig.command.trim().length > 0, `server "${serverName}" command must be non-empty`);
                });

                it('has args (array)', () => {
                  assert.ok(Array.isArray(serverConfig.args), `server "${serverName}" args must be an array`);
                });

                it('command is a plausible executable name', () => {
                  assert.ok(
                    isPlausibleCommand(serverConfig.command),
                    `server "${serverName}" command "${serverConfig.command}" does not look like a valid executable`
                  );
                });
              }
            });
          }
        });
      });
    }
  }
});
