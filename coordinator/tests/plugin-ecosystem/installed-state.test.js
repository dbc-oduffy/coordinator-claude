const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { PLUGINS_ROOT, fileExists, dirExists, readJson, listFiles, getDirectoryMarketplaces, isCachePath } = require('./helpers/fs');

const installedPath = path.join(PLUGINS_ROOT, 'installed_plugins.json');
const knownPath = path.join(PLUGINS_ROOT, 'known_marketplaces.json');
const installed = readJson(installedPath);
const knownMarketplaces = readJson(knownPath);

describe('installed_plugins.json structure', () => {

  it('has a numeric version field', () => {
    assert.equal(typeof installed.version, 'number', 'version should be a number');
  });

  it('has a plugins object', () => {
    assert.equal(typeof installed.plugins, 'object', 'plugins should be an object');
    assert.ok(!Array.isArray(installed.plugins), 'plugins should not be an array');
  });

  describe('Each plugin entry has a valid installPath on disk', () => {
    for (const [pluginKey, entries] of Object.entries(installed.plugins)) {
      for (const entry of entries) {
        const skipCacheCheck = isCachePath(entry.installPath);
        const testFn = skipCacheCheck ? it.skip : it;
        testFn(`${pluginKey} installPath exists: ${entry.installPath}`, () => {
          assert.ok(
            dirExists(entry.installPath),
            `installPath does not exist on disk: ${entry.installPath}`
          );
        });
      }
    }
  });

  describe('Each plugin entry has valid ISO timestamps', () => {
    for (const [pluginKey, entries] of Object.entries(installed.plugins)) {
      for (const entry of entries) {
        it(`${pluginKey} has valid installedAt timestamp`, () => {
          assert.equal(typeof entry.installedAt, 'string', `installedAt should be a string for ${pluginKey}`);
          const parsed = Date.parse(entry.installedAt);
          assert.ok(!Number.isNaN(parsed), `installedAt is not a valid ISO timestamp: "${entry.installedAt}"`);
        });

        it(`${pluginKey} has valid lastUpdated timestamp`, () => {
          assert.equal(typeof entry.lastUpdated, 'string', `lastUpdated should be a string for ${pluginKey}`);
          const parsed = Date.parse(entry.lastUpdated);
          assert.ok(!Number.isNaN(parsed), `lastUpdated is not a valid ISO timestamp: "${entry.lastUpdated}"`);
        });
      }
    }
  });

  describe('Each plugin entry has a valid scope', () => {
    for (const [pluginKey, entries] of Object.entries(installed.plugins)) {
      for (const entry of entries) {
        // Cache-rooted entries (plugins/cache/...) can transiently carry scope="local"
        // when the harness re-syncs after a stale-marketplace install; skip them here
        // for the same reason installPath existence is skipped for cache paths.
        // Non-cache entries with scope="local" are source-is-live plugins (direct installs
        // under plugins/ rather than plugins/cache/) — "local" is a valid harness scope.
        const skipCacheCheck = isCachePath(entry.installPath);
        const testFn = skipCacheCheck ? it.skip : it;
        testFn(`${pluginKey} scope is "project", "user", or "local"`, () => {
          assert.ok(
            entry.scope === 'project' || entry.scope === 'user' || entry.scope === 'local',
            `Invalid scope "${entry.scope}" for ${pluginKey} — expected "project", "user", or "local"`
          );
        });
      }
    }
  });

  describe('Project-scoped entries have a projectPath field', () => {
    for (const [pluginKey, entries] of Object.entries(installed.plugins)) {
      for (const entry of entries) {
        if (entry.scope !== 'project') continue;

        it(`${pluginKey} (project-scoped) has projectPath`, () => {
          assert.ok(
            entry.projectPath,
            `Project-scoped plugin "${pluginKey}" is missing projectPath`
          );
          assert.equal(
            typeof entry.projectPath, 'string',
            `projectPath should be a string for ${pluginKey}`
          );
        });
      }
    }
  });
});

describe('known_marketplaces.json structure', () => {

  it('parses as a non-null object', () => {
    assert.equal(typeof knownMarketplaces, 'object', 'known_marketplaces.json should be an object');
    assert.ok(knownMarketplaces !== null, 'known_marketplaces.json should not be null');
    assert.ok(!Array.isArray(knownMarketplaces), 'known_marketplaces.json should not be an array');
  });

  describe('Each marketplace entry has required fields', () => {
    for (const [name, entry] of Object.entries(knownMarketplaces)) {
      it(`${name} has a source object with a source field`, () => {
        assert.equal(typeof entry.source, 'object', `${name}.source should be an object`);
        assert.ok(entry.source !== null, `${name}.source should not be null`);
        assert.equal(typeof entry.source.source, 'string', `${name}.source.source should be a string`);
      });

      it(`${name} has a string installLocation`, () => {
        assert.equal(
          typeof entry.installLocation, 'string',
          `${name}.installLocation should be a string`
        );
      });

      const skipCacheCheck = isCachePath(entry.installLocation);
      const testFn = skipCacheCheck ? it.skip : it;
      testFn(`${name} installLocation exists on disk: ${entry.installLocation}`, () => {
        assert.ok(
          dirExists(entry.installLocation),
          `installLocation does not exist on disk: ${entry.installLocation}`
        );
      });
    }
  });
});
