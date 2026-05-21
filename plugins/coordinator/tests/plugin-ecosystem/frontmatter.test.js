const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { PLUGINS_ROOT, fileExists, dirExists, readJson, listFiles, listDirs, getDirectoryMarketplaces } = require('./helpers/fs');
const { extractFrontmatter } = require('./helpers/frontmatter');

const VALID_MODEL_SHORTNAMES = ['opus', 'sonnet', 'haiku'];

function isValidModel(value) {
  if (VALID_MODEL_SHORTNAMES.includes(value)) return true;
  if (value.includes('claude-')) return true;
  return false;
}

const marketplaces = getDirectoryMarketplaces();

describe('frontmatter validation', () => {
  for (const marketplace of marketplaces) {
    const marketplaceDir = marketplace.source.path;
    const metadataPath = path.join(marketplaceDir, '.claude-plugin', 'marketplace.json');

    let plugins;
    try {
      const data = readJson(metadataPath);
      plugins = data.plugins || [];
    } catch {
      // marketplace.test.js covers structural issues; skip here
      continue;
    }

    for (const plugin of plugins) {
      const pluginDir = path.resolve(marketplaceDir, plugin.source);
      const pluginLabel = `${marketplace.name}/${plugin.name}`;

      // --- agents/ ---
      const agentsDir = path.join(pluginDir, 'agents');
      if (dirExists(agentsDir)) {
        const agentFiles = listFiles(agentsDir, '.md');
        for (const file of agentFiles) {
          const filePath = path.join(agentsDir, file);

          describe(`[${pluginLabel}] agent: ${file}`, () => {
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
              if (!fm || fm.attrs.model === undefined) return; // no model field — OK
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
      const commandsDir = path.join(pluginDir, 'commands');
      if (dirExists(commandsDir)) {
        const commandFiles = listFiles(commandsDir, '.md');
        for (const file of commandFiles) {
          const filePath = path.join(commandsDir, file);

          describe(`[${pluginLabel}] command: ${file}`, () => {
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
      const skillsDir = path.join(pluginDir, 'skills');
      if (dirExists(skillsDir)) {
        const skillDirs = listDirs(skillsDir);
        for (const skillName of skillDirs) {
          const skillMdPath = path.join(skillsDir, skillName, 'SKILL.md');

          describe(`[${pluginLabel}] skill: ${skillName}`, () => {
            it('SKILL.md exists', () => {
              assert.ok(fileExists(skillMdPath), `SKILL.md missing for skill "${skillName}" in ${pluginLabel}`);
            });

            it('SKILL.md has valid frontmatter', () => {
              if (!fileExists(skillMdPath)) return; // existence tested above
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
  }
});
