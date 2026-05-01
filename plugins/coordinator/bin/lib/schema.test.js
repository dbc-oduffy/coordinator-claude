'use strict';
/**
 * schema.test.js — unit tests for bin/lib/schema.js
 *
 * Run with: node --test bin/lib/schema.test.js
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W1 Tests
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const {
  loadSchemas,
  matchSchemaForPath,
  parseFrontmatter,
  validateFrontmatter,
  validateLessonsFile,
  _parseYaml,
  _matchGlob,
} = require('./schema.js');

const SCHEMAS_DIR = path.resolve(__dirname, '../../schemas');

// Load schemas once at module scope — shared across all describe blocks.
// This avoids needing before() hooks and is safe because loadSchemas is pure.
const SCHEMAS = loadSchemas(SCHEMAS_DIR);

// ---------------------------------------------------------------------------
// loadSchemas / matchSchemaForPath
// ---------------------------------------------------------------------------

describe('loadSchemas', () => {
  it('loads all six schemas', () => {
    const names = Object.keys(SCHEMAS).filter(k => k !== '_byGlob');
    assert.ok(names.includes('handoff'), 'handoff schema missing');
    assert.ok(names.includes('decision'), 'decision schema missing');
    assert.ok(names.includes('plan'), 'plan schema missing');
    assert.ok(names.includes('review'), 'review schema missing');
    assert.ok(names.includes('worker-run'), 'worker-run schema missing');
    assert.ok(names.includes('lesson-entry'), 'lesson-entry schema missing');
    assert.equal(names.length, 6, `expected 6 schemas, got ${names.length}`);
  });

  it('_byGlob index has an entry per applies_to schema', () => {
    assert.ok(SCHEMAS._byGlob.length >= 5, '_byGlob should have at least 5 glob entries');
  });
});

describe('matchSchemaForPath', () => {
  it('tasks/handoffs/foo.md → handoff schema', () => {
    const match = matchSchemaForPath('tasks/handoffs/foo.md', SCHEMAS);
    assert.ok(match !== null, 'expected a match');
    assert.equal(match.schemaName, 'handoff');
  });

  it('tasks/handoffs/sub/foo.md → no match (single-star glob)', () => {
    const match = matchSchemaForPath('tasks/handoffs/sub/foo.md', SCHEMAS);
    assert.equal(match, null, 'sub-path should not match single-star glob');
  });

  it('docs/plans/2026-05-01-foo.md → plan schema', () => {
    const match = matchSchemaForPath('docs/plans/2026-05-01-foo.md', SCHEMAS);
    assert.ok(match !== null);
    assert.equal(match.schemaName, 'plan');
  });

  it('tasks/reviews/2026-05-01-review.md → review schema', () => {
    const match = matchSchemaForPath('tasks/reviews/2026-05-01-review.md', SCHEMAS);
    assert.ok(match !== null);
    assert.equal(match.schemaName, 'review');
  });

  it('tasks/worker-runs/2026-05-01-run.md → worker-run schema', () => {
    const match = matchSchemaForPath('tasks/worker-runs/2026-05-01-run.md', SCHEMAS);
    assert.ok(match !== null);
    assert.equal(match.schemaName, 'worker-run');
  });

  it('docs/wiki/some-guide.md → no match', () => {
    const match = matchSchemaForPath('docs/wiki/some-guide.md', SCHEMAS);
    assert.equal(match, null);
  });
});

// ---------------------------------------------------------------------------
// parseFrontmatter
// ---------------------------------------------------------------------------

describe('parseFrontmatter', () => {
  it('parses standard frontmatter block', () => {
    const content = `---\ntitle: Test\ncreated: 2026-05-01\n---\n# Body\n`;
    const { frontmatter, body } = parseFrontmatter(content);
    assert.equal(frontmatter.title, 'Test');
    assert.equal(frontmatter.created, '2026-05-01');
    assert.ok(body.includes('# Body'));
  });

  it('returns null frontmatter when no delimiter present', () => {
    const content = `# Just markdown\nNo frontmatter here.\n`;
    const { frontmatter, body } = parseFrontmatter(content);
    assert.equal(frontmatter, null);
    assert.equal(body, content);
  });

  it('parses list fields', () => {
    const content = `---\ntitle: A\ndeciders:\n  - alice\n  - bob\n---\nbody\n`;
    const { frontmatter } = parseFrontmatter(content);
    assert.deepEqual(frontmatter.deciders, ['alice', 'bob']);
  });

  it('parses null/string-or-null field', () => {
    const content = `---\ntitle: A\npredecessor: null\n---\n`;
    const { frontmatter } = parseFrontmatter(content);
    assert.equal(frontmatter.predecessor, null);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — handoff schema
// ---------------------------------------------------------------------------

describe('validateFrontmatter — handoff', () => {
  const handoffSchema = SCHEMAS['handoff'];

  it('valid handoff frontmatter passes', () => {
    const fm = {
      title: 'Test handoff',
      created: '2026-05-01',
      branch: 'work/57754134/2026-05-01-test',
      status: 'active',
      predecessor: null,
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('missing branch fails with field-level error', () => {
    const fm = {
      title: 'Test handoff',
      created: '2026-05-01',
      status: 'active',
      predecessor: null,
      // branch omitted
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false);
    const branchErr = result.errors.find(e => e.field === 'branch');
    assert.ok(branchErr, `Expected branch error, got: ${JSON.stringify(result.errors)}`);
    assert.match(branchErr.error, /missing/);
  });

  it('wrong status enum value fails', () => {
    const fm = {
      title: 'Test handoff',
      created: '2026-05-01',
      branch: 'work/test',
      status: 'open',    // invalid — not in [active, consumed, superseded]
      predecessor: null,
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false);
    const statusErr = result.errors.find(e => e.field === 'status');
    assert.ok(statusErr, `Expected status error, got: ${JSON.stringify(result.errors)}`);
    assert.match(statusErr.hint, /active/);
  });

  it('null predecessor passes (string-or-null)', () => {
    const fm = {
      title: 'Test',
      created: '2026-05-01',
      branch: 'work/test',
      status: 'consumed',
      predecessor: null,
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok);
  });

  it('string predecessor passes (string-or-null)', () => {
    const fm = {
      title: 'Test',
      created: '2026-05-01',
      branch: 'work/test',
      status: 'consumed',
      predecessor: 'tasks/handoffs/2026-04-30-prev.md',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok);
  });

  it('invalid date format fails', () => {
    const fm = {
      title: 'Test',
      created: '01-05-2026',   // wrong format
      branch: 'work/test',
      status: 'active',
      predecessor: null,
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false);
    const dateErr = result.errors.find(e => e.field === 'created');
    assert.ok(dateErr, 'Expected created date error');
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — decision schema (list-of-string)
// ---------------------------------------------------------------------------

describe('validateFrontmatter — decision', () => {
  const decisionSchema = SCHEMAS['decision'];

  it('valid decision with list deciders passes', () => {
    const fm = {
      title: 'Use Node over shell',
      created: '2026-05-01',
      status: 'accepted',
      deciders: ['donal', 'patrik'],
    };
    const result = validateFrontmatter(fm, decisionSchema);
    assert.ok(result.ok);
  });

  it('deciders as scalar (not list) fails', () => {
    const fm = {
      title: 'Use Node over shell',
      created: '2026-05-01',
      status: 'accepted',
      deciders: 'donal',
    };
    const result = validateFrontmatter(fm, decisionSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'deciders');
    assert.ok(err);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — review schema (findings_count: number)
// ---------------------------------------------------------------------------

describe('validateFrontmatter — review', () => {
  const reviewSchema = SCHEMAS['review'];

  it('valid review passes', () => {
    const fm = {
      title: 'R1 safe-commit review',
      created: '2026-05-01',
      reviewer: 'patrik',
      target: 'bin/coordinator-safe-commit',
      findings_count: 7,
    };
    const result = validateFrontmatter(fm, reviewSchema);
    assert.ok(result.ok);
  });

  it('invalid reviewer enum fails', () => {
    const fm = {
      title: 'R1',
      created: '2026-05-01',
      reviewer: 'unknown-reviewer',
      target: 'bin/foo',
      findings_count: 0,
    };
    const result = validateFrontmatter(fm, reviewSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'reviewer');
    assert.ok(err);
  });
});

// ---------------------------------------------------------------------------
// validateLessonsFile
// ---------------------------------------------------------------------------

describe('validateLessonsFile', () => {
  const lessonSchema = SCHEMAS['lesson-entry'];

  it('one untagged + one [universal] entry passes', () => {
    const content = [
      '# Lessons',
      '',
      '- **Always commit small chunks** — keeps diffs reviewable.',
      '',
      '- **[universal] Schema what you query** — YAGNI for schemas.',
      '',
    ].join('\n');
    const result = validateLessonsFile(content, lessonSchema);
    assert.ok(result.ok, `Expected ok, got: ${JSON.stringify(result.errors)}`);
  });

  it('[project] tag is also valid', () => {
    const content = [
      '- **[project] Repo-specific tip** — only relevant here.',
    ].join('\n');
    const result = validateLessonsFile(content, lessonSchema);
    assert.ok(result.ok);
  });

  it('[whatever] invalid tag fails', () => {
    const content = [
      '- **[whatever] Bad tag** — this tag is not in the enum.',
    ].join('\n');
    const result = validateLessonsFile(content, lessonSchema);
    assert.equal(result.ok, false);
    assert.ok(result.errors.length > 0);
    assert.match(result.errors[0].error, /unknown tag/);
    assert.match(result.errors[0].hint, /universal/);
  });

  it('multiple invalid tags in same file accumulate errors', () => {
    const content = [
      '- **[deprecated] Old tag** — was once allowed.',
      '- **[tier-1] Another bad tag** — not in enum.',
    ].join('\n');
    const result = validateLessonsFile(content, lessonSchema);
    assert.equal(result.ok, false);
    assert.ok(result.errors.length >= 2);
  });

  it('empty file passes', () => {
    const result = validateLessonsFile('', lessonSchema);
    assert.ok(result.ok);
  });
});

// ---------------------------------------------------------------------------
// _matchGlob — unit tests for the glob matcher
// ---------------------------------------------------------------------------

describe('_matchGlob', () => {
  it('* matches a single path segment', () => {
    assert.ok(_matchGlob('tasks/handoffs/*.md', 'tasks/handoffs/foo.md'));
  });

  it('* does not match across directories', () => {
    assert.ok(!_matchGlob('tasks/handoffs/*.md', 'tasks/handoffs/sub/foo.md'));
  });

  it('** matches across directories', () => {
    assert.ok(_matchGlob('tasks/**/*.md', 'tasks/handoffs/sub/foo.md'));
  });

  it('exact path matches itself', () => {
    assert.ok(_matchGlob('tasks/lessons.md', 'tasks/lessons.md'));
  });

  it('? matches a single non-separator char', () => {
    assert.ok(_matchGlob('tasks/?.md', 'tasks/a.md'));
    assert.ok(!_matchGlob('tasks/?.md', 'tasks/ab.md'));
  });

  it('Windows backslash paths are normalised', () => {
    assert.ok(_matchGlob('tasks/handoffs/*.md', 'tasks\\handoffs\\foo.md'));
  });
});

// ---------------------------------------------------------------------------
// _parseYaml — basic sanity on internal parser
// ---------------------------------------------------------------------------

describe('_parseYaml', () => {
  it('parses simple key-value pairs', () => {
    const result = _parseYaml('schema: handoff\napplies_to: "tasks/handoffs/*.md"\n');
    assert.equal(result.schema, 'handoff');
    assert.equal(result.applies_to, 'tasks/handoffs/*.md');
  });

  it('parses nested required block', () => {
    const yaml = [
      'required:',
      '  title: string',
      '  status:',
      '    type: enum',
      '    values: [active, consumed]',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.equal(result.required.title, 'string');
    assert.equal(result.required.status.type, 'enum');
    assert.deepEqual(result.required.status.values, ['active', 'consumed']);
  });

  it('parses list items', () => {
    const yaml = 'items:\n  - foo\n  - bar\n';
    const result = _parseYaml(yaml);
    assert.deepEqual(result.items, ['foo', 'bar']);
  });
});
