'use strict';
/**
 * test-canonical-structure-manifest.js — unit test for canonical-structure.yaml (coordinator root)
 *
 * Verifies:
 *   (a) The manifest parses without error as valid YAML with the expected shape.
 *   (b) Every non-null `schema:` value in an entry names an existing file in schemas/.
 *
 * Run with: node --test bin/tests/test-canonical-structure-manifest.js
 *
 * Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 1
 *
 * NOTE: This test does NOT load canonical-structure.yaml via loadSchemas() — that function
 * is for frontmatter-schema files. canonical-structure.yaml is a data manifest with a
 * different shape (entries: list). It is parsed here directly via the same _parseYaml
 * helper used by schema.js, available as a test-surface export.
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

// Resolve paths relative to this file's location.
const COORDINATOR_ROOT = path.resolve(__dirname, '../../');
const MANIFEST_PATH = path.join(COORDINATOR_ROOT, 'canonical-structure.yaml');
const SCHEMAS_DIR = path.join(COORDINATOR_ROOT, 'schemas');

// ---------------------------------------------------------------------------
// Minimal YAML parser (inline — avoids adding a dependency; mirrors the logic
// in bin/lib/schema.js but is independently re-implemented here so the test
// does not depend on schema.js internals changing).
// Handles: scalar strings, list-of-mappings (- key: val), one level of indent.
// ---------------------------------------------------------------------------

/**
 * Parse the canonical-structure.yaml manifest.
 * Returns the top-level object; entries is a list of entry objects.
 */
function parseManifest(yamlText) {
  const lines = yamlText.split('\n');
  const result = { entries: [] };
  let currentEntry = null;
  let inEntries = false;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const trimmed = raw.trimEnd();

    // Skip blank lines and comment-only lines
    if (trimmed === '' || trimmed.trimStart().startsWith('#')) continue;

    const indent = raw.length - raw.trimStart().length;
    const stripped = trimmed.trimStart();

    // Top-level key: entries:
    if (indent === 0 && stripped === 'entries:') {
      inEntries = true;
      continue;
    }

    if (!inEntries) continue;

    // New list entry (- path: ...)
    if (indent === 2 && stripped.startsWith('- ')) {
      if (currentEntry) result.entries.push(currentEntry);
      currentEntry = {};
      // Parse the inline key-value after '- '
      const kv = stripped.slice(2); // strip '- '
      const colonIdx = kv.indexOf(':');
      if (colonIdx !== -1) {
        const key = kv.slice(0, colonIdx).trim();
        const val = kv.slice(colonIdx + 1).trim();
        currentEntry[key] = parseScalar(val);
      }
      continue;
    }

    // Continuation key-value within current entry (indent 4)
    if (indent === 4 && currentEntry !== null) {
      // code-review F5: manifest uses '|' (literal block scalar), not '>'.
      // The previous '>' branch never fired. Handle both '|' and '>' so the
      // parser is robust to either block-scalar style in the manifest YAML.
      // findKeyAtLine() was dead code — removed.
      if (stripped.includes(':')) {
        const colonIdx = stripped.indexOf(':');
        const key2 = stripped.slice(0, colonIdx).trim();
        const afterColon = stripped.slice(colonIdx + 1).trim();
        if (afterColon === '|' || afterColon === '>') {
          // Block scalar — collect subsequent indented lines as the value.
          const blockLines = [];
          let j = i + 1;
          while (j < lines.length) {
            const bRaw = lines[j];
            const bIndent = bRaw.length - bRaw.trimStart().length;
            if (bIndent <= 4 && bRaw.trim() !== '') break;
            if (bRaw.trim() !== '') blockLines.push(bRaw.trim());
            j++;
          }
          currentEntry[key2] = blockLines.join('\n');
          i = j - 1;
          continue;
        }
      }

      const colonIdx = stripped.indexOf(':');
      if (colonIdx !== -1) {
        const key = stripped.slice(0, colonIdx).trim();
        const val = stripped.slice(colonIdx + 1).trim();
        currentEntry[key] = parseScalar(val);
      }
      continue;
    }
  }

  // Push final entry
  if (currentEntry) result.entries.push(currentEntry);
  return result;
}

/**
 * Parse a scalar YAML value: null, quoted string, or bare string.
 */
function parseScalar(val) {
  if (val === 'null' || val === '~' || val === '') return null;
  if ((val.startsWith("'") && val.endsWith("'")) ||
      (val.startsWith('"') && val.endsWith('"'))) {
    return val.slice(1, -1);
  }
  return val;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('canonical-structure manifest — file presence', () => {
  it('canonical-structure.yaml exists on disk (coordinator root)', () => {
    assert.ok(
      fs.existsSync(MANIFEST_PATH),
      `Manifest not found at: ${MANIFEST_PATH}`
    );
  });
});

describe('canonical-structure manifest — parse', () => {
  let manifest;

  it('manifest file is readable and non-empty', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    assert.ok(content.length > 0, 'manifest is empty');
    manifest = parseManifest(content);
  });

  it('manifest has an entries list', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    manifest = parseManifest(content);
    assert.ok(Array.isArray(manifest.entries), 'entries must be an array');
    assert.ok(manifest.entries.length > 0, 'entries must not be empty');
  });

  it('every entry has path, creation, schema, and readme keys', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    manifest = parseManifest(content);
    for (const entry of manifest.entries) {
      assert.ok('path' in entry, `entry missing path: ${JSON.stringify(entry)}`);
      assert.ok('creation' in entry, `entry missing creation: ${JSON.stringify(entry)}`);
      assert.ok('schema' in entry, `entry missing schema: ${JSON.stringify(entry)}`);
      assert.ok('readme' in entry, `entry missing readme: ${JSON.stringify(entry)}`);
    }
  });

  it('every creation value is "eager" or "lazy"', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    manifest = parseManifest(content);
    for (const entry of manifest.entries) {
      assert.ok(
        entry.creation === 'eager' || entry.creation === 'lazy',
        `entry "${entry.path}" has invalid creation "${entry.creation}" — must be eager or lazy`
      );
    }
  });
});

describe('canonical-structure manifest — schema references', () => {
  it('every non-null schema: value names an existing file in schemas/', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    const manifest = parseManifest(content);

    const missing = [];
    for (const entry of manifest.entries) {
      if (entry.schema === null) continue;
      const schemaFile = path.join(SCHEMAS_DIR, `${entry.schema}.yaml`);
      if (!fs.existsSync(schemaFile)) {
        missing.push(`"${entry.path}" references schema "${entry.schema}" but schemas/${entry.schema}.yaml does not exist`);
      }
    }

    assert.equal(
      missing.length, 0,
      `Missing schema files:\n  ${missing.join('\n  ')}`
    );
  });

  it('cross-repo/inbox/ entry exists and is eager with schema cross-repo-memo', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    const manifest = parseManifest(content);
    const entry = manifest.entries.find(e => e.path === 'cross-repo/inbox/');
    assert.ok(entry, 'cross-repo/inbox/ entry missing from manifest');
    assert.equal(entry.creation, 'eager', 'cross-repo/inbox/ must be eager');
    assert.equal(entry.schema, 'cross-repo-memo', 'cross-repo/inbox/ must reference cross-repo-memo schema');
    // code-review F5: assert readme is a non-empty multi-line string, not just non-null.
    // The '|' block-scalar branch now populates readme with newline-joined lines.
    assert.ok(typeof entry.readme === 'string' && entry.readme.length > 0,
      'cross-repo/inbox/ readme must be a non-empty string');
    assert.ok(entry.readme.includes('\n'),
      'cross-repo/inbox/ readme must be multi-line (block scalar should preserve newlines)');
  });

  it('cross-repo/archive/ entry exists and is lazy with null schema', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    const manifest = parseManifest(content);
    const entry = manifest.entries.find(e => e.path === 'cross-repo/archive/');
    assert.ok(entry, 'cross-repo/archive/ entry missing from manifest');
    assert.equal(entry.creation, 'lazy', 'cross-repo/archive/ must be lazy');
    assert.equal(entry.schema, null, 'cross-repo/archive/ must have null schema');
  });

  it('archive/cross-repo/ entry is removed from manifest (moved to cross-repo/archive/)', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    const manifest = parseManifest(content);
    const entry = manifest.entries.find(e => e.path === 'archive/cross-repo/');
    assert.equal(entry, undefined, 'archive/cross-repo/ must NOT appear in manifest — path moved to cross-repo/archive/');
  });

  it('existing lazy directory rows are all still lazy', () => {
    const content = fs.readFileSync(MANIFEST_PATH, 'utf8');
    const manifest = parseManifest(content);
    const expectedLazy = [
      'tasks/handoffs/',
      'archive/completed/',
      'docs/wiki/',
      'docs/plans/',
      'docs/research/',
      'tasks/review-trail/',
      'cross-repo/archive/',
    ];
    for (const p of expectedLazy) {
      const entry = manifest.entries.find(e => e.path === p);
      assert.ok(entry, `Expected lazy entry "${p}" not found in manifest`);
      assert.equal(
        entry.creation, 'lazy',
        `"${p}" should be lazy but got "${entry.creation}"`
      );
    }
  });
});
