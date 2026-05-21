const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { execSync } = require('child_process');
const { PLUGINS_ROOT, fileExists, dirExists, readJson, getDirectoryMarketplaces } = require('./helpers/fs');

const VALID_EVENT_TYPES = ['SessionStart', 'PreToolUse', 'PostToolUse', 'PreCompact', 'Notification', 'Stop'];

/**
 * Given a hook command string, substitute ${CLAUDE_PLUGIN_ROOT} and extract
 * the file path (if any). Commands may be prefixed with an executable like
 * "bash" or "node", so the path is the first token that looks like a file path
 * (contains a file extension).
 */
function resolveScriptPath(command, pluginDir) {
  const expanded = command.replace(/\$\{CLAUDE_PLUGIN_ROOT\}/g, pluginDir);
  const tokens = expanded.split(/\s+/);
  for (const token of tokens) {
    // Look for tokens with a file extension (e.g., .sh, .js, .py)
    if (/\.\w+$/.test(token) && !token.startsWith('-')) {
      return token;
    }
  }
  return null;
}

const marketplaces = getDirectoryMarketplaces();

describe('hook configuration and script validity', () => {
  for (const marketplace of marketplaces) {
    const marketplaceDir = marketplace.source.path;
    const metadataPath = path.join(marketplaceDir, '.claude-plugin', 'marketplace.json');

    let plugins;
    try {
      const data = readJson(metadataPath);
      plugins = data.plugins || [];
    } catch {
      continue;
    }

    for (const plugin of plugins) {
      const pluginDir = path.resolve(marketplaceDir, plugin.source);
      const pluginLabel = `${marketplace.name}/${plugin.name}`;
      const hooksJsonPath = path.join(pluginDir, 'hooks', 'hooks.json');

      if (!fileExists(hooksJsonPath)) continue;

      describe(`[${pluginLabel}] hooks.json`, () => {
        let hooksData;

        it('parses as valid JSON', () => {
          hooksData = readJson(hooksJsonPath);
          assert.ok(hooksData, `hooks.json parsed to falsy value in ${pluginLabel}`);
        });

        it('is an object', () => {
          hooksData = readJson(hooksJsonPath);
          assert.equal(typeof hooksData, 'object', `hooks.json must be an object in ${pluginLabel}`);
          assert.ok(!Array.isArray(hooksData), `hooks.json must not be an array in ${pluginLabel}`);
        });

        // The actual event types live under hooksData.hooks (if present) or at top level
        it('event types are valid', () => {
          hooksData = readJson(hooksJsonPath);
          const eventMap = hooksData.hooks || hooksData;
          const keys = Object.keys(eventMap).filter(k => k !== 'description' && k !== 'hooks');

          // If using the nested format (hooksData.hooks exists), validate those keys
          const keysToValidate = hooksData.hooks
            ? Object.keys(hooksData.hooks)
            : keys;

          for (const key of keysToValidate) {
            assert.ok(
              VALID_EVENT_TYPES.includes(key),
              `Invalid event type "${key}" in ${pluginLabel}. Valid types: ${VALID_EVENT_TYPES.join(', ')}`
            );
          }
        });

        // Validate individual hooks and their scripts
        describe('hook entries', () => {
          let eventMap;
          try {
            hooksData = readJson(hooksJsonPath);
            eventMap = hooksData.hooks || hooksData;
          } catch {
            return;
          }

          // Collect all hook objects from the (possibly nested) structure
          // Format: eventType -> array of matcher groups -> each has .hooks array
          const eventTypes = Object.keys(eventMap).filter(k => VALID_EVENT_TYPES.includes(k));

          for (const eventType of eventTypes) {
            const matcherGroups = eventMap[eventType];
            if (!Array.isArray(matcherGroups)) continue;

            for (let gi = 0; gi < matcherGroups.length; gi++) {
              const group = matcherGroups[gi];
              const matcherLabel = group.matcher !== undefined ? `matcher="${group.matcher}"` : `group[${gi}]`;

              // Hooks can be directly in the group array (flat) or nested under group.hooks
              const hookItems = Array.isArray(group.hooks) ? group.hooks :
                                (group.command ? [group] : []);

              for (let hi = 0; hi < hookItems.length; hi++) {
                const hook = hookItems[hi];
                const hookLabel = `${eventType} ${matcherLabel} hook[${hi}]`;

                describe(`[${pluginLabel}] ${hookLabel}`, () => {
                  it('has command (string)', () => {
                    assert.equal(
                      typeof hook.command, 'string',
                      `hook command must be a string: ${hookLabel} in ${pluginLabel}`
                    );
                  });

                  it('has timeout (positive number)', () => {
                    assert.equal(
                      typeof hook.timeout, 'number',
                      `hook timeout must be a number: ${hookLabel} in ${pluginLabel}`
                    );
                    assert.ok(
                      hook.timeout > 0,
                      `hook timeout must be positive: ${hookLabel} in ${pluginLabel} (got ${hook.timeout})`
                    );
                  });

                  it('referenced script file exists', () => {
                    if (typeof hook.command !== 'string') return;
                    const scriptPath = resolveScriptPath(hook.command, pluginDir);
                    if (!scriptPath) return; // no file path in command — OK (e.g., bare executable)
                    assert.ok(
                      fileExists(scriptPath),
                      `Script file not found: ${scriptPath} (from command "${hook.command}" in ${pluginLabel})`
                    );
                  });

                  it('script syntax is valid', () => {
                    if (typeof hook.command !== 'string') return;
                    const scriptPath = resolveScriptPath(hook.command, pluginDir);
                    if (!scriptPath) return;
                    if (!fileExists(scriptPath)) return;

                    if (scriptPath.endsWith('.sh')) {
                      try {
                        execSync(`bash -n "${scriptPath}"`, { stdio: 'pipe', timeout: 10000 });
                      } catch (e) {
                        if (e.status !== null) {
                          // bash -n returned an error — real syntax issue
                          const stderr = e.stderr ? e.stderr.toString().trim() : '';
                          assert.fail(`Bash syntax error in ${scriptPath}: ${stderr}`);
                        }
                        // e.status === null means bash not found or timeout — skip
                      }
                    } else if (scriptPath.endsWith('.js')) {
                      try {
                        execSync(`node --check "${scriptPath}"`, { stdio: 'pipe', timeout: 10000 });
                      } catch (e) {
                        if (e.status !== null) {
                          const stderr = e.stderr ? e.stderr.toString().trim() : '';
                          assert.fail(`Node syntax error in ${scriptPath}: ${stderr}`);
                        }
                      }
                    }
                    // Other extensions: no syntax check available, skip silently
                  });
                });
              }
            }
          }
        });
      });
    }
  }
});
