const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { PLUGINS_ROOT, fileExists, dirExists, readJson, getDirectoryMarketplaces } = require('./helpers/fs');

const marketplaces = getDirectoryMarketplaces();

describe('marketplace structural integrity', () => {
  for (const marketplace of marketplaces) {
    describe(`marketplace: ${marketplace.name}`, () => {
      const marketplaceDir = marketplace.source.path;
      const metadataPath = path.join(marketplaceDir, '.claude-plugin', 'marketplace.json');

      it('marketplace directory exists', () => {
        assert.ok(
          dirExists(marketplaceDir),
          `marketplace directory missing: ${marketplaceDir}`
        );
      });

      it('marketplace.json exists and is valid JSON', () => {
        assert.ok(
          fileExists(metadataPath),
          `marketplace.json missing: ${metadataPath}`
        );
        // readJson will throw on invalid JSON
        const data = readJson(metadataPath);
        assert.ok(data, `marketplace.json parsed to falsy value: ${metadataPath}`);
      });

      describe('marketplace.json required fields', () => {
        let data;

        it('has name (string)', () => {
          data = readJson(metadataPath);
          assert.equal(typeof data.name, 'string', `name must be a string in ${metadataPath}`);
        });

        it('has owner.name (string)', () => {
          data = readJson(metadataPath);
          assert.ok(data.owner, `owner is missing in ${metadataPath}`);
          assert.equal(typeof data.owner.name, 'string', `owner.name must be a string in ${metadataPath}`);
        });

        it('has metadata.description (string)', () => {
          data = readJson(metadataPath);
          assert.ok(data.metadata, `metadata is missing in ${metadataPath}`);
          assert.equal(typeof data.metadata.description, 'string', `metadata.description must be a string in ${metadataPath}`);
        });

        it('has metadata.version (string)', () => {
          data = readJson(metadataPath);
          assert.ok(data.metadata, `metadata is missing in ${metadataPath}`);
          assert.equal(typeof data.metadata.version, 'string', `metadata.version must be a string in ${metadataPath}`);
        });

        it('has plugins (non-empty array)', () => {
          data = readJson(metadataPath);
          assert.ok(Array.isArray(data.plugins), `plugins must be an array in ${metadataPath}`);
          assert.ok(data.plugins.length > 0, `plugins array must not be empty in ${metadataPath}`);
        });
      });

      describe('marketplace.json name matches known_marketplaces key', () => {
        it(`name field matches key "${marketplace.name}"`, () => {
          const data = readJson(metadataPath);
          assert.equal(
            data.name,
            marketplace.name,
            `marketplace.json name "${data.name}" does not match known_marketplaces key "${marketplace.name}"`
          );
        });
      });

      describe('plugin entries', () => {
        let data;
        try {
          data = readJson(metadataPath);
        } catch {
          // If marketplace.json is unreadable, earlier tests will catch it
          return;
        }

        if (!Array.isArray(data.plugins)) return;

        for (const plugin of data.plugins) {
          const pluginLabel = plugin.name || '(unnamed)';

          describe(`plugin entry: ${pluginLabel}`, () => {
            it('has name (string)', () => {
              assert.equal(typeof plugin.name, 'string', `plugin entry missing name in ${metadataPath}`);
            });

            it('has source (string)', () => {
              assert.equal(typeof plugin.source, 'string', `plugin entry "${pluginLabel}" missing source in ${metadataPath}`);
            });

            it('has description (string)', () => {
              assert.equal(typeof plugin.description, 'string', `plugin entry "${pluginLabel}" missing description in ${metadataPath}`);
            });

            it('source path resolves to existing directory', () => {
              assert.equal(typeof plugin.source, 'string', `plugin source must be a string`);
              const pluginDir = path.resolve(marketplaceDir, plugin.source);
              assert.ok(
                dirExists(pluginDir),
                `plugin source directory missing: ${pluginDir} (from entry "${pluginLabel}" in ${metadataPath})`
              );
            });
          });
        }
      });
    });
  }
});
