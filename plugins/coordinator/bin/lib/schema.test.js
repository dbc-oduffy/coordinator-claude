'use strict';
/**
 * schema.test.js — unit tests for bin/lib/schema.js
 *
 * Run with: node --test bin/lib/schema.test.js
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1 Tests
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
  it('loads all eight schemas', () => {
    const names = Object.keys(SCHEMAS).filter(k => k !== '_byGlob');
    assert.ok(names.includes('handoff'), 'handoff schema missing');
    assert.ok(names.includes('handoff-archived'), 'handoff-archived schema missing');
    assert.ok(names.includes('decision'), 'decision schema missing');
    assert.ok(names.includes('plan'), 'plan schema missing');
    assert.ok(names.includes('review'), 'review schema missing');
    assert.ok(names.includes('lesson-entry'), 'lesson-entry schema missing');
    assert.ok(names.includes('completion-entry'), 'completion-entry schema missing');
    assert.ok(names.includes('cross-repo-memo'), 'cross-repo-memo schema missing');
    // code-review F13: the count 8 names the schemas enumerated by the includes() checks
    // above: handoff, handoff-archived, decision, plan, review, lesson-entry,
    // completion-entry, cross-repo-memo. Update this comment (not just the count) when
    // a schema is added or removed, so the assertion stays self-documenting.
    assert.equal(names.length, 8, `expected 8 schemas, got ${names.length}`);
  });

  it('_byGlob index has an entry per applies_to schema', () => {
    assert.ok(SCHEMAS._byGlob.length >= 4, '_byGlob should have at least 4 glob entries');
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
// validateFrontmatter — plan schema (status enum incl. superseded)
// ---------------------------------------------------------------------------

describe('validateFrontmatter — plan', () => {
  const planSchema = SCHEMAS['plan'];

  it('valid plan with status: superseded and superseded_by passes', () => {
    const fm = {
      title: 'multi-uplugin build pipeline',
      created: '2026-05-04',
      author: 'em',
      status: 'superseded',
      superseded_by: 'docs/plans/2026-05-04-multi-uplugin-build-pipeline.md',
    };
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('valid plan with status: deferred passes', () => {
    const fm = {
      title: 'backlog plan parked for now',
      created: '2026-05-04',
      author: 'em',
      status: 'deferred',
    };
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok);
  });

  it('valid plan with status: abandoned still passes', () => {
    const fm = {
      title: 'uplugin modules restore',
      created: '2026-05-03',
      author: 'em',
      status: 'abandoned',
    };
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok);
  });

  it('invalid status enum fails', () => {
    const fm = {
      title: 'foo',
      created: '2026-05-04',
      author: 'em',
      status: 'cancelled',
    };
    const result = validateFrontmatter(fm, planSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'status');
    assert.ok(err);
    assert.match(err.hint, /superseded/);
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
      deciders: ['pm', 'staff-eng'],
    };
    const result = validateFrontmatter(fm, decisionSchema);
    assert.ok(result.ok);
  });

  it('deciders as scalar (not list) fails', () => {
    const fm = {
      title: 'Use Node over shell',
      created: '2026-05-01',
      status: 'accepted',
      deciders: 'pm',
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
// validateFrontmatter — cross-repo-memo schema
// Spec backlink: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Chunk 1
// ---------------------------------------------------------------------------

describe('validateFrontmatter — cross-repo-memo', () => {
  const memoSchema = SCHEMAS['cross-repo-memo'];

  // Helper: build a minimal valid post-cutoff memo frontmatter
  function baseMemo(overrides = {}) {
    return Object.assign({
      title: 'Test memo',
      from: 'claude-central-em',
      to: 'project-rag-em',
      created: '2026-05-22',
      status: 'open',
      delivery_mode: 'receiver-repo',
    }, overrides);
  }

  it('valid status:action_taken with action_taken_at and decision:accepted passes', () => {
    const fm = baseMemo({
      status: 'action_taken',
      action_taken_at: '2026-05-23T10:00:00Z',
      decision: 'accepted',
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('invalid status:action_taken without decision fails with clear error', () => {
    const fm = baseMemo({
      status: 'action_taken',
      action_taken_at: '2026-05-23T10:00:00Z',
      // decision omitted
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => /decision/.test(e.field));
    assert.ok(err, `Expected decision field error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required when status=action_taken/);
  });

  it('invalid status:action_taken without action_taken_at fails', () => {
    const fm = baseMemo({
      status: 'action_taken',
      decision: 'accepted',
      // action_taken_at omitted
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => /action_taken_at/.test(e.field));
    assert.ok(err, `Expected action_taken_at error, got: ${JSON.stringify(result.errors)}`);
  });

  it('invalid status:closed without closed_at fails', () => {
    const fm = baseMemo({
      status: 'closed',
      action_taken_at: '2026-05-23T10:00:00Z',
      decision: 'accepted',
      // closed_at omitted
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => /closed_at/.test(e.field));
    assert.ok(err, `Expected closed_at error, got: ${JSON.stringify(result.errors)}`);
  });

  it('valid status:closed with all required lifecycle fields passes', () => {
    const fm = baseMemo({
      status: 'closed',
      action_taken_at: '2026-05-23T10:00:00Z',
      decision: 'accepted',
      closed_at: '2026-05-24T09:00:00Z',
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('valid delivery_mode:central-only without machine-local mapping passes (to: is enough)', () => {
    const fm = baseMemo({
      delivery_mode: 'central-only',
      // to: is set in baseMemo — no machine-local mapping requirement
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('pre-cutoff created:2026-05-21 memo is skipped (returns ok without cross-field validation)', () => {
    // Deliberately invalid cross-field state — would fail if validated.
    // Since created < 2026-05-22, the grandfather rule fires and skips all rules.
    const fm = {
      title: 'Old memo',
      from: 'claude-central-em',
      to: 'holodeck-em',
      created: '2026-05-21',
      status: 'action_taken',
      delivery_mode: 'receiver-repo',
      // Intentionally missing action_taken_at and decision — should be skipped
    };
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Pre-cutoff memo should pass (grandfathered), got: ${JSON.stringify(result.errors)}`);
  });

  it('post-cutoff created:2026-05-22 memo with full valid frontmatter passes', () => {
    const fm = baseMemo({
      created: '2026-05-22',
      status: 'open',
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('status:superseded without superseded_by fails', () => {
    const fm = baseMemo({
      status: 'superseded',
      // superseded_by omitted
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'superseded_by');
    assert.ok(err, `Expected superseded_by error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required when status=superseded/);
  });

  it('status:superseded with superseded_by passes', () => {
    const fm = baseMemo({
      status: 'superseded',
      superseded_by: 'archive/cross-repo/2026-05-23-topic-v2.md',
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  // code-review F1 (downgraded): 'actioned' is the simple-model terminal — decision
  // is OPTIONAL. No required-field rule for actioned (unlike grandfathered action_taken).
  it('status:actioned without decision passes (simple-model terminal, decision optional)', () => {
    const fm = baseMemo({
      status: 'actioned',
      action_taken_at: '2026-05-24T10:00:00Z',
      // decision intentionally omitted — optional for actioned
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Expected ok for actioned without decision, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('status:actioned with optional decision also passes', () => {
    const fm = baseMemo({
      status: 'actioned',
      action_taken_at: '2026-05-24T10:00:00Z',
      decision: 'accepted',
    });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Expected ok for actioned with decision, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('matchSchemaForPath routes cross-repo/YYYY-MM-DD-topic.md to cross-repo-memo schema', () => {
    const match = matchSchemaForPath('cross-repo/2026-05-23-test-topic.md', SCHEMAS);
    assert.ok(match !== null, 'expected a match for cross-repo/ dated memo path');
    assert.equal(match.schemaName, 'cross-repo-memo');
  });

  it('matchSchemaForPath does NOT route cross-repo/README.md to cross-repo-memo schema (digit-prefix glob)', () => {
    const match = matchSchemaForPath('cross-repo/README.md', SCHEMAS);
    assert.equal(match, null, 'cross-repo/README.md must not match the digit-prefixed glob');
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
      '- **[obsolete] Another bad tag** — not in enum.',
    ].join('\n');
    const result = validateLessonsFile(content, lessonSchema);
    assert.equal(result.ok, false);
    assert.ok(result.errors.length >= 2);
  });

  it('digit-containing bracket tokens are prose, not candidate tags', () => {
    // Version refs, codecs, doc-tier refs, footnotes, citation keys, section
    // refs, and wikilinks on an entry line are NOT tags — a real tag (or its
    // typo) is pure lowercase alpha. None of these should produce a violation.
    const content = [
      '- **Prose-heavy entry** — uses [v2], [h264], [tier-1], [1], [11] and [[wikilink]].',
    ].join('\n');
    const result = validateLessonsFile(content, lessonSchema);
    assert.ok(result.ok, `digit/bracket prose must not flag, got: ${JSON.stringify(result.errors)}`);
  });

  it('uppercase-cased tag typo ([Universal]) is the accepted miss — slips silently', () => {
    // Documented tradeoff: catching this requires allowing uppercase-initial
    // tokens, which re-introduces citation-key ([Smith2020]) false positives.
    // This test is a tripwire: if a future change starts catching it, decide
    // deliberately rather than by accident.
    const content = ['- **[Universal] cased typo** — slips by design.'].join('\n');
    const result = validateLessonsFile(content, lessonSchema);
    assert.ok(result.ok, `[Universal] is the accepted miss and must not flag, got: ${JSON.stringify(result.errors)}`);
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

  // Bracket character-class passthrough tests.
  // Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
  it('[0-9]* bracket-class glob matches a dated memo filename', () => {
    assert.ok(_matchGlob('cross-repo/[0-9]*.md', 'cross-repo/2026-05-23-test-topic.md'),
      'digit-prefixed dated memo should match');
  });

  it('[0-9]* bracket-class glob does NOT match cross-repo/README.md', () => {
    assert.ok(!_matchGlob('cross-repo/[0-9]*.md', 'cross-repo/README.md'),
      'README.md must not match digit-prefixed glob');
  });

  it('[0-9]* bracket-class glob does NOT match cross-repo/topic-only.md (no leading digit)', () => {
    assert.ok(!_matchGlob('cross-repo/[0-9]*.md', 'cross-repo/topic-only.md'),
      'non-digit-prefixed file must not match');
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
