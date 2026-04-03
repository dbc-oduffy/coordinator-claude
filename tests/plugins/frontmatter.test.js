const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { fileExists, dirExists, listFiles, listDirs, getPlugins } = require('./helpers/fs');
const { extractFrontmatter } = require('./helpers/frontmatter');

const VALID_MODEL_SHORTNAMES = ['opus', 'sonnet', 'haiku'];

function isValidModel(value) {
  if (VALID_MODEL_SHORTNAMES.includes(value)) return true;
  if (value.includes('claude-')) return true;
  return false;
}

const plugins = getPlugins();

describe('frontmatter validation', () => {
  for (const plugin of plugins) {
    // --- agents/ ---
    const agentsDir = path.join(plugin.dir, 'agents');
    if (dirExists(agentsDir)) {
      const agentFiles = listFiles(agentsDir, '.md');
      for (const file of agentFiles) {
        const filePath = path.join(agentsDir, file);

        describe(`[${plugin.name}] agent: ${file}`, () => {
          it('has valid frontmatter', () => {
            const fm = extractFrontmatter(filePath);
            assert.ok(fm, `Missing or unparseable frontmatter in ${filePath}`);
          });

          it('has non-empty description', () => {
            const fm = extractFrontmatter(filePath);
            assert.ok(fm, `No frontmatter to check description in ${filePath}`);
            assert.equal(typeof fm.attrs.description, 'string', `description must be a string in ${filePath}`);
            assert.ok(fm.attrs.description.trim().length > 0, `description must not be empty in ${filePath}`);
          });

          it('model field is valid (if present)', () => {
            const fm = extractFrontmatter(filePath);
            if (!fm || fm.attrs.model === undefined) return;
            assert.equal(typeof fm.attrs.model, 'string', `model must be a string in ${filePath}`);
            assert.ok(
              isValidModel(fm.attrs.model),
              `Invalid model "${fm.attrs.model}" in ${filePath}. Must be one of [${VALID_MODEL_SHORTNAMES.join(', ')}] or contain "claude-".`
            );
          });
        });
      }
    }

    // --- commands/ ---
    const commandsDir = path.join(plugin.dir, 'commands');
    if (dirExists(commandsDir)) {
      const commandFiles = listFiles(commandsDir, '.md');
      for (const file of commandFiles) {
        const filePath = path.join(commandsDir, file);

        describe(`[${plugin.name}] command: ${file}`, () => {
          it('has valid frontmatter', () => {
            const fm = extractFrontmatter(filePath);
            assert.ok(fm, `Missing or unparseable frontmatter in ${filePath}`);
          });

          it('has non-empty description', () => {
            const fm = extractFrontmatter(filePath);
            assert.ok(fm, `No frontmatter to check description in ${filePath}`);
            assert.equal(typeof fm.attrs.description, 'string', `description must be a string in ${filePath}`);
            assert.ok(fm.attrs.description.trim().length > 0, `description must not be empty in ${filePath}`);
          });
        });
      }
    }

    // --- skills/ ---
    const skillsDir = path.join(plugin.dir, 'skills');
    if (dirExists(skillsDir)) {
      const skillDirs = listDirs(skillsDir);
      for (const skillName of skillDirs) {
        const skillMdPath = path.join(skillsDir, skillName, 'SKILL.md');

        describe(`[${plugin.name}] skill: ${skillName}`, () => {
          it('SKILL.md exists', () => {
            assert.ok(fileExists(skillMdPath), `SKILL.md missing for skill "${skillName}" in ${plugin.name}`);
          });

          it('SKILL.md has valid frontmatter', () => {
            if (!fileExists(skillMdPath)) return;
            const fm = extractFrontmatter(skillMdPath);
            assert.ok(fm, `Missing or unparseable frontmatter in ${skillMdPath}`);
          });

          it('SKILL.md has non-empty description', () => {
            if (!fileExists(skillMdPath)) return;
            const fm = extractFrontmatter(skillMdPath);
            assert.ok(fm, `No frontmatter to check description in ${skillMdPath}`);
            assert.equal(typeof fm.attrs.description, 'string', `description must be a string in ${skillMdPath}`);
            assert.ok(fm.attrs.description.trim().length > 0, `description must not be empty in ${skillMdPath}`);
          });
        });
      }
    }
  }
});
