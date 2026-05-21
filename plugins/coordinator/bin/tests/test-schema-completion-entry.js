'use strict';
/**
 * test-schema-completion-entry.js — integration smoke test for completion-entry schema.
 *
 * Verifies that bin/lib/schema.js loadSchemas() picks up the new completion-entry schema
 * and that valid/invalid sample entries behave correctly under the validator.
 *
 * Run with: node --test bin/tests/test-schema-completion-entry.js
 *
 * Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 1
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const { loadSchemas, matchSchemaForPath, validateFrontmatter } = require('../lib/schema.js');

const SCHEMAS_DIR = path.resolve(__dirname, '../../schemas');
const SCHEMAS = loadSchemas(SCHEMAS_DIR);

// ---------------------------------------------------------------------------
// Schema discovery
// ---------------------------------------------------------------------------

describe('completion-entry schema — discovery', () => {
  it('loadSchemas picks up completion-entry schema', () => {
    const names = Object.keys(SCHEMAS).filter(k => k !== '_byGlob');
    assert.ok(
      names.includes('completion-entry'),
      `completion-entry schema not found; schemas present: ${names.join(', ')}`
    );
  });

  it('schema has required fields: title, created, nature', () => {
    const schema = SCHEMAS['completion-entry'];
    assert.ok(schema.required, 'schema.required block missing');
    assert.ok('title' in schema.required, 'title not in required');
    assert.ok('created' in schema.required, 'created not in required');
    assert.ok('nature' in schema.required, 'nature not in required');
  });

  it('schema has optional fields including nature_inferred', () => {
    const schema = SCHEMAS['completion-entry'];
    assert.ok(schema.optional, 'schema.optional block missing');
    assert.ok('nature_inferred' in schema.optional, 'nature_inferred not in optional');
    assert.ok('chain' in schema.optional, 'chain not in optional');
    assert.ok('status' in schema.optional, 'status not in optional');
    assert.ok('commits' in schema.optional, 'commits not in optional');
  });

  it('applies_to glob matches archive/completed/YYYY-MM/*.md paths', () => {
    const match = matchSchemaForPath('archive/completed/2026-05/2026-05-19-installer-redesign-abc123.md', SCHEMAS);
    assert.ok(match !== null, 'expected a schema match for completion-entry path');
    assert.equal(match.schemaName, 'completion-entry');
  });

  it('applies_to glob does NOT match flat-root archive/completed/2026-05.md (legacy monolith shape)', () => {
    // Legacy monoliths live at archive/completed/YYYY-MM.md (no subdir) — the glob
    // archive/completed/*/*.md requires TWO path components after the prefix, so flat
    // files at archive/completed/YYYY-MM.md correctly produce no match.
    // Note: archive/completed/legacy/*.md DOES match (legacy/ is the first * segment);
    // exclusion of legacy entries from query results is a bin/query-completions concern,
    // not a schema-glob concern.
    const noMatch = matchSchemaForPath('archive/completed/2026-05.md', SCHEMAS);
    assert.equal(noMatch, null, 'flat legacy monolith path should not match completion-entry glob');
  });
});

// ---------------------------------------------------------------------------
// Valid entry — nature: bugfix, chain: null, status: pending-release
// ---------------------------------------------------------------------------

describe('completion-entry schema — valid entries', () => {
  const schema = SCHEMAS['completion-entry'];

  it('minimal valid entry (bugfix, no chain, pending-release) passes', () => {
    const fm = {
      title: 'Fix session-end crash on empty touched.txt',
      created: '2026-05-19',
      nature: 'bugfix',
    };
    const result = validateFrontmatter(fm, schema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('valid entry with chain: null passes (null permitted on optional chain field)', () => {
    const fm = {
      title: 'Rewrote session-end Step 2.6 for per-entry completion log',
      created: '2026-05-19',
      nature: 'roadmap',
      chain: null,
      status: 'pending-release',
    };
    const result = validateFrontmatter(fm, schema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('valid entry with chain set to a plan path passes', () => {
    const fm = {
      title: 'Implemented completion-entry schema and smoke tests',
      created: '2026-05-19',
      nature: 'infra',
      chain: 'docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md',
      commits: ['abc123def456', '789abcdef012'],
      status: 'pending-release',
      chain_terminal: true,
      nature_inferred: false,
    };
    const result = validateFrontmatter(fm, schema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('all four nature enum values are individually valid', () => {
    const schema = SCHEMAS['completion-entry'];
    for (const nature of ['roadmap', 'bugfix', 'tech-debt', 'infra']) {
      const fm = { title: `Test entry`, created: '2026-05-19', nature };
      const result = validateFrontmatter(fm, schema);
      assert.ok(result.ok, `nature: ${nature} should be valid, got: ${JSON.stringify(result.errors)}`);
    }
  });

  it('valid entry with status: released (post-merge state) passes', () => {
    const fm = {
      title: 'Ship Phase 1 completion log',
      created: '2026-05-19',
      nature: 'roadmap',
      status: 'released',
      released_in: 'v2.1.0',
      released_at: '2026-05-20',
      released_sha: 'deadbeef12345678',
    };
    const result = validateFrontmatter(fm, schema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// Invalid entries — enum violations, missing required fields
// ---------------------------------------------------------------------------

describe('completion-entry schema — invalid entries', () => {
  const schema = SCHEMAS['completion-entry'];

  it('nature: other (not in enum) fails validation', () => {
    const fm = {
      title: 'Some work',
      created: '2026-05-19',
      nature: 'other',   // invalid — not in [roadmap, bugfix, tech-debt, infra]
    };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false, 'Expected validation failure for nature: other');
    const natureErr = result.errors.find(e => e.field === 'nature');
    assert.ok(natureErr, `Expected nature error, got: ${JSON.stringify(result.errors)}`);
    assert.match(natureErr.error, /invalid enum value/);
    assert.match(natureErr.hint, /roadmap/);
  });

  it('missing title fails with required-field error', () => {
    const fm = {
      created: '2026-05-19',
      nature: 'bugfix',
      // title omitted
    };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'title');
    assert.ok(err, `Expected title error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /missing/);
  });

  it('missing created fails with required-field error', () => {
    const fm = {
      title: 'Some work',
      nature: 'bugfix',
      // created omitted
    };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'created');
    assert.ok(err, `Expected created error, got: ${JSON.stringify(result.errors)}`);
  });

  it('missing nature fails with required-field error', () => {
    const fm = {
      title: 'Some work',
      created: '2026-05-19',
      // nature omitted
    };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'nature');
    assert.ok(err, `Expected nature error, got: ${JSON.stringify(result.errors)}`);
  });

  it('invalid status enum value fails', () => {
    const fm = {
      title: 'Some work',
      created: '2026-05-19',
      nature: 'bugfix',
      status: 'done',    // invalid — not in [pending-release, released]
    };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'status');
    assert.ok(err, `Expected status error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.hint, /pending-release/);
  });

  it('invalid created date format fails', () => {
    const fm = {
      title: 'Some work',
      created: '19-05-2026',  // wrong format
      nature: 'bugfix',
    };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'created');
    assert.ok(err, `Expected created date error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.hint, /YYYY-MM-DD/);
  });
});
