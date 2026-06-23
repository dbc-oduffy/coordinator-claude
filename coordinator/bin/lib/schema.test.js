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
  it('state/handoffs/foo.md → handoff schema', () => {
    const match = matchSchemaForPath('state/handoffs/foo.md', SCHEMAS);
    assert.ok(match !== null, 'expected a match');
    assert.equal(match.schemaName, 'handoff');
  });

  it('state/handoffs/sub/foo.md → no match (single-star glob)', () => {
    const match = matchSchemaForPath('state/handoffs/sub/foo.md', SCHEMAS);
    assert.equal(match, null, 'sub-path should not match single-star glob');
  });

  it('docs/plans/2026-05-01-foo.md → plan schema', () => {
    const match = matchSchemaForPath('docs/plans/2026-05-01-foo.md', SCHEMAS);
    assert.ok(match !== null);
    assert.equal(match.schemaName, 'plan');
  });

  it('state/reviews/2026-05-01-review.md → review schema', () => {
    const match = matchSchemaForPath('state/reviews/2026-05-01-review.md', SCHEMAS);
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

  // ---------------------------------------------------------------------------
  // Leading HTML comment tolerance — seed-handoff templates lead with <!-- ... -->
  // ---------------------------------------------------------------------------

  it('(a) single-line leading comment then frontmatter: parses correctly', () => {
    const content = `<!-- Seed comment: replace before use -->\n---\ntitle: Seeded handoff\ncreated: 2026-06-15\n---\n# Body\n`;
    const { frontmatter, body } = parseFrontmatter(content);
    assert.ok(frontmatter !== null, 'frontmatter should not be null with leading comment');
    assert.equal(frontmatter.title, 'Seeded handoff');
    assert.equal(frontmatter.created, '2026-06-15');
    assert.ok(body.includes('# Body'), 'body should contain the markdown body');
  });

  it('(b) multi-line leading comment then frontmatter: parses correctly', () => {
    const content = [
      '<!-- ',
      '  This is a multi-line seed comment.',
      '  Replace all placeholders before committing.',
      '-->',
      '---',
      'title: Multi-line comment handoff',
      'created: 2026-06-15',
      '---',
      '# Body text',
    ].join('\n') + '\n';
    const { frontmatter, body } = parseFrontmatter(content);
    assert.ok(frontmatter !== null, 'frontmatter should not be null with multi-line leading comment');
    assert.equal(frontmatter.title, 'Multi-line comment handoff');
    assert.ok(body.includes('# Body text'));
  });

  it('(c) leading comment then NO frontmatter: returns frontmatter:null', () => {
    const content = `<!-- Seed comment: replace before use -->\n# Just a heading\nNo frontmatter here.\n`;
    const { frontmatter, body } = parseFrontmatter(content);
    assert.equal(frontmatter, null, 'frontmatter should be null when no --- block follows comment');
    // body is the original content (no-frontmatter path preserves original)
    assert.ok(body.includes('# Just a heading'));
  });

  it('(d) regression: no comment, frontmatter at line 1 still works', () => {
    const content = `---\ntitle: Regression test\ncreated: 2026-05-01\n---\n# Regression body\n`;
    const { frontmatter, body } = parseFrontmatter(content);
    assert.ok(frontmatter !== null, 'standard frontmatter must still parse without comment prefix');
    assert.equal(frontmatter.title, 'Regression test');
    assert.ok(body.includes('# Regression body'));
  });

  it('(e) leading comment then bare HR then markdown prose: returns frontmatter:null (P1 regression guard)', () => {
    // A bare --- HR after a leading comment must NOT be parsed as frontmatter.
    // parseYaml is lenient and returns {} for prose, which the empty-object guard
    // now catches. This test was failing before the Finding 1 fix was applied.
    const content = [
      '<!-- seed -->',
      '---',
      '# Heading',
      'body prose',
      '---',
      'rest',
    ].join('\n') + '\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.equal(frontmatter, null, 'HR-after-comment must yield null frontmatter, not empty {}');
  });

  it('(f) two consecutive leading comments then frontmatter: parses correctly', () => {
    // The comment-skip loop must iterate more than once to handle consecutive comments.
    const content = [
      '<!-- A -->',
      '<!-- B -->',
      '---',
      'title: X',
      '---',
      '# Body',
    ].join('\n') + '\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null, 'two consecutive comments then frontmatter must parse');
    assert.equal(frontmatter.title, 'X');
  });

  it('unclosed <!-- comment: returns frontmatter:null safely (no hang)', () => {
    const content = `<!-- Unclosed comment\n---\ntitle: Trap\n---\n# Body\n`;
    const { frontmatter } = parseFrontmatter(content);
    assert.equal(frontmatter, null, 'unclosed HTML comment must return null frontmatter');
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
      predecessor: 'state/handoffs/2026-04-30-prev.md',
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
// validateFrontmatter — handoff category + summary (cutoff-gated cross-field rules)
// Spec backlink: docs/plans/2026-05-29-handoff-schema-category-summary.md § Chunk 1
// ---------------------------------------------------------------------------

describe('validateFrontmatter — handoff category + summary cutoff rules', () => {
  const handoffSchema = SCHEMAS['handoff'];

  // Base valid post-cutoff handoff with all required + new fields.
  function basePostCutoff(overrides = {}) {
    return Object.assign({
      title: 'Post-cutoff handoff',
      created: '2026-05-29',
      branch: 'work/striker/2026-05-29',
      status: 'active',
      predecessor: null,
      category: 'infra',
      summary: 'Schema extended with category and summary fields for handoff enrichment',
    }, overrides);
  }

  it('legacy handoff (created < 2026-05-29) without category or summary passes', () => {
    const fm = {
      title: 'Legacy handoff',
      created: '2026-05-28',
      branch: 'work/striker/2026-05-28',
      status: 'active',
      predecessor: null,
      // category and summary intentionally absent
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Legacy handoff without category/summary should pass (pre-cutoff), got: ${JSON.stringify(result.errors)}`);
  });

  it('pre-cutoff handoff (created: 2026-05-01) without category passes', () => {
    const fm = {
      title: 'Old handoff',
      created: '2026-05-01',
      branch: 'work/striker/2026-05-01',
      status: 'consumed',
      predecessor: null,
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Pre-cutoff handoff without category should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('post-cutoff handoff (created >= 2026-05-29) without category FAILS', () => {
    const fm = basePostCutoff({ category: undefined });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Post-cutoff handoff without category should fail');
    const err = result.errors.find(e => e.field === 'category');
    assert.ok(err, `Expected category error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required for handoffs created on or after 2026-05-29/);
  });

  it('post-cutoff handoff without summary FAILS', () => {
    const fm = basePostCutoff({ summary: undefined });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Post-cutoff handoff without summary should fail');
    const err = result.errors.find(e => e.field === 'summary');
    assert.ok(err, `Expected summary error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required for handoffs created on or after 2026-05-29/);
  });

  it('post-cutoff handoff with 121-char summary FAILS', () => {
    const longSummary = 'A'.repeat(121);
    const fm = basePostCutoff({ summary: longSummary });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, '121-char summary should fail');
    const err = result.errors.find(e => e.field === 'summary');
    assert.ok(err, `Expected summary length error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /exceeds 120 characters/);
  });

  it('post-cutoff handoff with valid category + ≤120-char summary PASSES', () => {
    const result = validateFrontmatter(basePostCutoff(), handoffSchema);
    assert.ok(result.ok, `Valid post-cutoff handoff with category + summary should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('post-cutoff handoff with exactly 120-char summary PASSES', () => {
    const exactly120 = 'B'.repeat(120);
    const fm = basePostCutoff({ summary: exactly120 });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Exactly-120-char summary should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('category enum validation still fires (invalid category value fails)', () => {
    const fm = basePostCutoff({ category: 'typo-category' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Invalid category enum value should fail');
    const err = result.errors.find(e => e.field === 'category');
    assert.ok(err, `Expected category enum error, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — handoff supersedes: kind-gate rule
// A supersedes: field is permitted only on kind: spinoff install/orientation batons.
// Distinct from the terminal memo superseded_by: coupling in the memo block.
// ---------------------------------------------------------------------------

describe('validateFrontmatter — handoff supersedes kind-gate', () => {
  const handoffSchema = SCHEMAS['handoff'];

  // Helper: base valid kind: spinoff handoff with all post-cutoff required fields.
  // post-cutoff created date: includes category+summary to satisfy the 2026-05-29 cutoff rules (independent of the supersedes kind-gate under test)
  function baseSpinoff(overrides = {}) {
    return Object.assign({
      title: 'Spinoff install baton',
      created: '2026-05-29',
      branch: 'work/striker/2026-05-29',
      status: 'active',
      predecessor: null,
      kind: 'spinoff',
      category: 'infra',
      summary: 'Install orientation spinoff with supersession',
    }, overrides);
  }

  it('kind: spinoff WITH supersedes: passes (valid conditional-live supersession)', () => {
    const fm = baseSpinoff({ supersedes: 'foo-orientation' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `kind:spinoff + supersedes should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  it('kind: spinoff-roadmap WITH supersedes: FAILS (supersedes not permitted on spinoff-roadmap)', () => {
    const fm = {
      title: 'Roadmap stub',
      created: '2026-05-29',
      branch: 'work/striker/2026-05-29',
      status: 'active',
      predecessor: null,
      kind: 'spinoff-roadmap',
      roadmap_id: 'rm-001',
      tc_id: 'tc-001',
      wave: 1,
      blocks: [],
      blocked_by: [],
      category: 'infra',
      summary: 'Roadmap stub that should not carry supersedes',
      supersedes: 'foo-orientation',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-roadmap + supersedes should fail');
    const err = result.errors.find(e => e.field === 'supersedes');
    assert.ok(err, `Expected supersedes error, got: ${JSON.stringify(result.errors)}`);
    // Review: code-reviewer — exercise the interpolated current-kind in the error message, not just the base text
    assert.match(err.error, /permitted only when kind=spinoff \(current kind: spinoff-roadmap\)/);
    assert.match(err.hint, /conditional-live/);
  });

  it('kind absent WITH supersedes: FAILS (supersedes not permitted when kind is not spinoff)', () => {
    // Review: code-reviewer — exercises the fm.kind !== 'spinoff' branch for kind-absent/other-kind
    const fm = {
      title: 'Recovery baton',
      created: '2026-05-29',
      branch: 'work/striker/2026-05-29',
      status: 'active',
      predecessor: null,
      kind: 'recovery',
      category: 'infra',
      summary: 'Recovery baton that should not carry supersedes',
      supersedes: 'foo-orientation',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'non-spinoff kind + supersedes should fail');
    const err = result.errors.find(e => e.field === 'supersedes');
    assert.ok(err, `Expected supersedes error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /permitted only when kind=spinoff/);
  });

  it('baton WITHOUT supersedes: is unaffected by the new rule (passes)', () => {
    const fm = baseSpinoff();  // no supersedes field
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Baton without supersedes should be unaffected, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — cross-repo-memo summary length rule
// Spec backlink: docs/plans/2026-05-29-handoff-schema-category-summary.md § Chunk 1
// ---------------------------------------------------------------------------

describe('validateFrontmatter — cross-repo-memo summary length rule', () => {
  const memoSchema = SCHEMAS['cross-repo-memo'];

  function baseMemo(overrides = {}) {
    return Object.assign({
      title: 'Test memo',
      from: 'claude-central-em',
      to: 'project-rag-em',
      created: '2026-05-29',
      status: 'open',
      delivery_mode: 'receiver-repo',
    }, overrides);
  }

  it('post-cutoff memo with 121-char summary FAILS', () => {
    const longSummary = 'C'.repeat(121);
    const fm = baseMemo({ summary: longSummary });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, '121-char memo summary should fail');
    const err = result.errors.find(e => e.field === 'summary');
    assert.ok(err, `Expected summary length error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /exceeds 120 characters/);
  });

  it('post-cutoff memo with ≤120-char summary PASSES', () => {
    const fm = baseMemo({ summary: 'Notify project-rag-em about revised plugin extract doctrine' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Valid memo with short summary should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('post-cutoff memo without summary PASSES (summary is optional)', () => {
    const fm = baseMemo();
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Memo without summary should pass (optional field), got: ${JSON.stringify(result.errors)}`);
  });

  it('pre-cutoff memo (created < 2026-05-22) with long summary is grandfathered (passes)', () => {
    const fm = {
      title: 'Old memo',
      from: 'claude-central-em',
      to: 'holodeck-em',
      created: '2026-05-21',
      status: 'open',
      delivery_mode: 'receiver-repo',
      summary: 'D'.repeat(121),  // would fail if validated, but pre-cutoff grandfather fires
    };
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Pre-cutoff memo with long summary should be grandfathered, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — cross-repo-memo in_progress claim-state rule
// Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C2
// ---------------------------------------------------------------------------

describe('validateFrontmatter — cross-repo-memo in_progress claim-state', () => {
  const memoSchema = SCHEMAS['cross-repo-memo'];

  function baseMemo(overrides = {}) {
    return Object.assign({
      title: 'Test memo',
      from: 'claude-central-em',
      to: 'project-rag-em',
      created: '2026-06-21',
      status: 'open',
      delivery_mode: 'receiver-repo',
    }, overrides);
  }

  it('in_progress WITH picked_up_by PASSES', () => {
    const fm = baseMemo({ status: 'in_progress', picked_up_by: 'sid-abc', picked_up_at: '2026-06-21T10:00:00Z' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `in_progress with picked_up_by should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('in_progress WITHOUT picked_up_by FAILS (cross-field rule)', () => {
    const fm = baseMemo({ status: 'in_progress' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'in_progress without picked_up_by should fail');
    const err = result.errors.find(e => e.field === 'picked_up_by');
    assert.ok(err, `Expected picked_up_by error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required when status=in_progress/);
  });

  it('in_progress with EMPTY-STRING picked_up_by FAILS (trim guard)', () => {
    const fm = baseMemo({ status: 'in_progress', picked_up_by: '' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'in_progress with empty picked_up_by should fail');
    assert.ok(result.errors.find(e => e.field === 'picked_up_by'), `Expected picked_up_by error, got: ${JSON.stringify(result.errors)}`);
  });

  it('in_progress with WHITESPACE-ONLY picked_up_by FAILS (trim guard)', () => {
    const fm = baseMemo({ status: 'in_progress', picked_up_by: '   ' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'in_progress with whitespace-only picked_up_by should fail');
    assert.ok(result.errors.find(e => e.field === 'picked_up_by'), `Expected picked_up_by error, got: ${JSON.stringify(result.errors)}`);
  });

  it('open memo without the new claim fields PASSES (back-compat)', () => {
    const fm = baseMemo();
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `open memo without claim fields should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('actioned memo without the new claim fields PASSES (back-compat)', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'accepted' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `actioned memo should pass, got: ${JSON.stringify(result.errors)}`);
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

  it('reviewer: code-reviewer passes (Sonnet merge-gate reviewer)', () => {
    const fm = {
      title: 'code-reviewer slice review',
      created: '2026-06-15',
      reviewer: 'code-reviewer',
      target: 'structured-queue-medium-rollout — slice A',
      findings_count: 10,
    };
    const result = validateFrontmatter(fm, reviewSchema);
    assert.ok(result.ok, `code-reviewer should be a valid reviewer enum value, got: ${JSON.stringify(result.errors)}`);
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

  // kind enum — optional field; absent is valid (back-compat); present must be ask|consult|fyi.
  // Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § C3 + § Pinned interface
  it('kind: ask passes', () => {
    const fm = baseMemo({ kind: 'ask' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `kind:ask should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('kind: consult passes', () => {
    const fm = baseMemo({ kind: 'consult' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `kind:consult should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('kind: fyi passes', () => {
    const fm = baseMemo({ kind: 'fyi' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `kind:fyi should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('kind absent (undefined) passes — back-compat, pre-2026-05-30 memos are valid', () => {
    const fm = baseMemo();   // no kind field
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `absent kind should pass (back-compat), got: ${JSON.stringify(result.errors)}`);
  });

  it('kind: bogus fails with clear enum error', () => {
    const fm = baseMemo({ kind: 'bogus' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'invalid kind should fail');
    const err = result.errors.find(e => e.field === 'kind');
    assert.ok(err, `Expected kind error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /invalid enum value "bogus"/);
    assert.match(err.hint, /ask, consult, fyi/);
  });

  it('kind: ack fails (ack is receipt-state, not a sender-declared kind)', () => {
    const fm = baseMemo({ kind: 'ack' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'kind:ack should fail');
    const err = result.errors.find(e => e.field === 'kind');
    assert.ok(err, `Expected kind error for ack, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.hint, /ack.*not a kind|not a kind.*ack/i);
  });

  it('kind: ask on a pre-cutoff memo is still grandfathered (grandfather fires first, kind not checked)', () => {
    // Pre-cutoff memos skip ALL cross-field rules — kind validation is one of them.
    const fm = {
      title: 'Old memo',
      from: 'claude-central-em',
      to: 'holodeck-em',
      created: '2026-05-21',
      status: 'open',
      delivery_mode: 'receiver-repo',
      kind: 'bogus',  // would fail for post-cutoff memos, but grandfather fires first
    };
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `Pre-cutoff memo should pass regardless of kind value, got: ${JSON.stringify(result.errors)}`);
  });

  it('matchSchemaForPath routes cross-repo/inbox/YYYY-MM-DD-topic.md to cross-repo-memo schema', () => {
    const match = matchSchemaForPath('cross-repo/inbox/2026-05-23-test-topic.md', SCHEMAS);
    assert.ok(match !== null, 'expected a match for cross-repo/inbox/ dated memo path');
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
    assert.ok(_matchGlob('state/handoffs/*.md', 'state/handoffs/foo.md'));
  });

  it('* does not match across directories', () => {
    assert.ok(!_matchGlob('state/handoffs/*.md', 'state/handoffs/sub/foo.md'));
  });

  it('** matches across directories', () => {
    assert.ok(_matchGlob('tasks/**/*.md', 'tasks/handoffs/sub/foo.md'));
  });

  it('exact path matches itself', () => {
    assert.ok(_matchGlob('state/lessons.md', 'state/lessons.md'));
  });

  it('? matches a single non-separator char', () => {
    assert.ok(_matchGlob('tasks/?.md', 'tasks/a.md'));
    assert.ok(!_matchGlob('tasks/?.md', 'tasks/ab.md'));
  });

  it('Windows backslash paths are normalised', () => {
    assert.ok(_matchGlob('state/handoffs/*.md', 'state\\handoffs\\foo.md'));
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
    const result = _parseYaml('schema: handoff\napplies_to: "state/handoffs/*.md"\n');
    assert.equal(result.schema, 'handoff');
    assert.equal(result.applies_to, 'state/handoffs/*.md');
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

  // Regression: skipPast must consume the same lines parseList does when a list
  // block contains an indented comment between items. If the two functions
  // disagree on the line count, the key AFTER the list is dropped or misparsed.
  // Guards the skipPast indent/trim handling (original bug used raw.trimEnd().startsWith('#'),
  // which misses indented comments; trim refactored in 0ba69974). Verified falsifiable:
  // against the pre-fix skipPast this case returns target_surfaces=undefined, trailing_key=undefined.
  it('keeps the key following a list that contains an indented comment', () => {
    const yaml = [
      'target_surfaces:',
      '  - alpha',
      '  # indented comment between list items',
      '  - beta',
      'trailing_key: kept',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.deepEqual(result.target_surfaces, ['alpha', 'beta'], 'list contents');
    assert.equal(result.trailing_key, 'kept', 'trailing key survived list-skip');
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — nested object (loe / chain_loe in completion-entry)
// ---------------------------------------------------------------------------

describe('validateFrontmatter — nested object (completion-entry loe)', () => {
  const baseFm = { title: 'x', created: '2026-05-28', nature: 'infra' };
  const schema = SCHEMAS['completion-entry'];

  it('accepts a well-formed loe object', () => {
    const fm = { ...baseFm, loe: { agent_dispatches: 5, opus_dispatches: 1, em_tokens: 12000, tshirt: 'M' } };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, true, JSON.stringify(result.errors));
  });

  it('accepts legacy all-null loe (Phase 1 entries)', () => {
    const fm = { ...baseFm, loe: { agent_dispatches: null, opus_dispatches: null, em_tokens: null, tshirt: null } };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, true, JSON.stringify(result.errors));
  });

  it('accepts em_tokens: null but rejects em_tokens as string', () => {
    const okFm = { ...baseFm, loe: { agent_dispatches: 5, opus_dispatches: 1, em_tokens: null, tshirt: 'M' } };
    assert.equal(validateFrontmatter(okFm, schema).ok, true);
    const badFm = { ...baseFm, loe: { agent_dispatches: 5, opus_dispatches: 1, em_tokens: 'lots', tshirt: 'M' } };
    const badResult = validateFrontmatter(badFm, schema);
    assert.equal(badResult.ok, false);
    assert.equal(badResult.errors[0].field, 'loe.em_tokens');
    assert.match(badResult.errors[0].error, /number or null/);
  });

  it('rejects a bad tshirt enum value with dotted field path', () => {
    const fm = { ...baseFm, loe: { agent_dispatches: 5, opus_dispatches: 1, em_tokens: null, tshirt: 'XXXL' } };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    assert.equal(result.errors[0].field, 'loe.tshirt');
    assert.match(result.errors[0].error, /invalid enum value/);
    assert.match(result.errors[0].hint, /XS, S, M, L, XL/);
  });

  it('rejects a string where a sub-field expects a number', () => {
    const fm = { ...baseFm, loe: { agent_dispatches: 'five', opus_dispatches: 0, em_tokens: null, tshirt: 'S' } };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    assert.equal(result.errors[0].field, 'loe.agent_dispatches');
    assert.match(result.errors[0].error, /expected number/);
  });

  it('rejects an array where an object is expected', () => {
    const fm = { ...baseFm, loe: [] };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    assert.equal(result.errors[0].field, 'loe');
    assert.match(result.errors[0].error, /expected object, got array/);
  });

  it('rejects a scalar where an object is expected', () => {
    const fm = { ...baseFm, loe: 'broken' };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    assert.equal(result.errors[0].field, 'loe');
    assert.match(result.errors[0].error, /expected object, got string/);
  });

  it('allows loe to be entirely absent (optional field)', () => {
    const result = validateFrontmatter({ ...baseFm }, schema);
    assert.equal(result.ok, true);
  });

  it('validates chain_loe with the same shape', () => {
    const fm = { ...baseFm, chain_loe: { sessions: 6, agent_dispatches: 87, opus_dispatches: 12, em_tokens: 1847000, tshirt: 'XL' } };
    assert.equal(validateFrontmatter(fm, schema).ok, true);
    const badFm = { ...baseFm, chain_loe: { sessions: 6, agent_dispatches: 87, opus_dispatches: 12, em_tokens: null, tshirt: 'GIGA' } };
    const badResult = validateFrontmatter(badFm, schema);
    assert.equal(badResult.ok, false);
    assert.equal(badResult.errors[0].field, 'chain_loe.tshirt');
    assert.match(badResult.errors[0].error, /invalid enum value/);
    assert.match(badResult.errors[0].hint, /XS, S, M, L, XL/);
  });

  it('rejects non-null wrong type on number-or-null sub-fields (F3 coverage)', () => {
    // agent_dispatches is declared number-or-null — null passes, but a string
    // must fail. This guards the schema-accuracy fix per code-reviewer F3.
    const fm = { ...baseFm, loe: { agent_dispatches: 'lots', opus_dispatches: 0, em_tokens: null, tshirt: 'S' } };
    const result = validateFrontmatter(fm, schema);
    assert.equal(result.ok, false);
    assert.equal(result.errors[0].field, 'loe.agent_dispatches');
    assert.match(result.errors[0].error, /number or null/);
  });
});
