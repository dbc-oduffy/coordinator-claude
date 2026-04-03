const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { fileExists, dirExists, readJson, listFiles, listDirs, getPlugins } = require('./helpers/fs');

const plugins = getPlugins();

describe('plugin directory structure', () => {
  for (const plugin of plugins) {
    const pluginJsonPath = path.join(plugin.dir, '.claude-plugin', 'plugin.json');

    describe(`plugin: ${plugin.name}`, () => {
      it('plugin.json exists and is valid JSON', () => {
        assert.ok(fileExists(pluginJsonPath), `plugin.json missing: ${pluginJsonPath}`);
        const data = readJson(pluginJsonPath);
        assert.ok(data, `plugin.json parsed to falsy value: ${pluginJsonPath}`);
      });

      describe('plugin.json required fields', () => {
        it('has name (string)', () => {
          const data = readJson(pluginJsonPath);
          assert.equal(typeof data.name, 'string', `name must be a string in ${pluginJsonPath}`);
        });

        it('has version (string)', () => {
          const data = readJson(pluginJsonPath);
          assert.equal(typeof data.version, 'string', `version must be a string in ${pluginJsonPath}`);
        });

        it('has description (string)', () => {
          const data = readJson(pluginJsonPath);
          assert.equal(typeof data.description, 'string', `description must be a string in ${pluginJsonPath}`);
        });
      });

      it('plugin.json name matches expected name', () => {
        const data = readJson(pluginJsonPath);
        assert.equal(
          data.name,
          plugin.name,
          `plugin.json name "${data.name}" does not match expected name "${plugin.name}"`
        );
      });

      describe('optional directories', () => {
        const agentsDir = path.join(plugin.dir, 'agents');
        const commandsDir = path.join(plugin.dir, 'commands');
        const skillsDir = path.join(plugin.dir, 'skills');
        const hooksDir = path.join(plugin.dir, 'hooks');

        it('agents/ contains at least one .md file (when present)', () => {
          if (!dirExists(agentsDir)) return;
          const mdFiles = listFiles(agentsDir, '.md');
          assert.ok(mdFiles.length > 0, `agents/ directory exists but contains no .md files: ${agentsDir}`);
        });

        it('commands/ contains at least one .md file (when present)', () => {
          if (!dirExists(commandsDir)) return;
          const mdFiles = listFiles(commandsDir, '.md');
          assert.ok(mdFiles.length > 0, `commands/ directory exists but contains no .md files: ${commandsDir}`);
        });

        it('skills/ subdirectories each contain SKILL.md (when present)', () => {
          if (!dirExists(skillsDir)) return;
          const subdirs = listDirs(skillsDir);
          for (const subdir of subdirs) {
            const skillMd = path.join(skillsDir, subdir, 'SKILL.md');
            assert.ok(fileExists(skillMd), `skills/${subdir}/ is missing SKILL.md: ${skillMd}`);
          }
        });

        it('hooks/ contains hooks.json and scripts/ subdirectory (when present)', () => {
          if (!dirExists(hooksDir)) return;
          const hooksJsonPath = path.join(hooksDir, 'hooks.json');
          assert.ok(fileExists(hooksJsonPath), `hooks/ directory exists but hooks.json is missing: ${hooksJsonPath}`);
          const scriptsDir = path.join(hooksDir, 'scripts');
          assert.ok(dirExists(scriptsDir), `hooks/ directory exists but scripts/ subdirectory is missing: ${scriptsDir}`);
        });
      });
    });
  }
});
