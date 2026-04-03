const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { REPO_ROOT, fileExists, dirExists, readJson, getMarketplace } = require('./helpers/fs');

const marketplace = getMarketplace();

describe('marketplace structural integrity', () => {
  it('marketplace.json exists', () => {
    assert.ok(marketplace, 'No .claude-plugin/marketplace.json found at repo root');
  });

  if (!marketplace) return;

  const { data, path: metadataPath } = marketplace;

  describe('required fields', () => {
    it('has name (string)', () => {
      assert.equal(typeof data.name, 'string', `name must be a string in ${metadataPath}`);
    });

    it('has owner.name (string)', () => {
      assert.ok(data.owner, `owner is missing in ${metadataPath}`);
      assert.equal(typeof data.owner.name, 'string', `owner.name must be a string in ${metadataPath}`);
    });

    it('has metadata.description (string)', () => {
      assert.ok(data.metadata, `metadata is missing in ${metadataPath}`);
      assert.equal(typeof data.metadata.description, 'string', `metadata.description must be a string in ${metadataPath}`);
    });

    it('has metadata.version (string)', () => {
      assert.ok(data.metadata, `metadata is missing in ${metadataPath}`);
      assert.equal(typeof data.metadata.version, 'string', `metadata.version must be a string in ${metadataPath}`);
    });

    it('has plugins (non-empty array)', () => {
      assert.ok(Array.isArray(data.plugins), `plugins must be an array in ${metadataPath}`);
      assert.ok(data.plugins.length > 0, `plugins array must not be empty in ${metadataPath}`);
    });
  });

  describe('plugin entries', () => {
    if (!Array.isArray(data.plugins)) return;

    for (const plugin of data.plugins) {
      const pluginLabel = plugin.name || '(unnamed)';

      describe(`plugin entry: ${pluginLabel}`, () => {
        it('has name (string)', () => {
          assert.equal(typeof plugin.name, 'string', `plugin entry missing name in ${metadataPath}`);
        });

        it('has description (string)', () => {
          assert.equal(typeof plugin.description, 'string', `plugin entry "${pluginLabel}" missing description in ${metadataPath}`);
        });

        it('has source (string or object)', () => {
          const t = typeof plugin.source;
          assert.ok(
            t === 'string' || t === 'object',
            `plugin entry "${pluginLabel}" source must be string or object, got ${t}`
          );
        });

        if (typeof plugin.source === 'string') {
          it('source path resolves to existing directory', () => {
            const pluginDir = path.resolve(REPO_ROOT, plugin.source);
            assert.ok(
              dirExists(pluginDir),
              `plugin source directory missing: ${pluginDir} (from entry "${pluginLabel}")`
            );
          });
        }
      });
    }
  });
});
