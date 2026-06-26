'use strict';
/**
 * schema.test.js — unit tests for bin/lib/schema.js
 *
 * Run with: node --test bin/lib/schema.test.js
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1 Tests
 * C2-tests spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C2
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const os = require('os');
const {
  loadSchemas,
  matchSchemaForPath,
  parseFrontmatter,
  validateFrontmatter,
  validateLessonsFile,
  _parseYaml,
  parseYamlBlock,
  _matchGlob,
  matchSchema,
} = require('./schema.js');

const SCHEMAS_DIR = path.resolve(__dirname, '../../schemas');

// Load schemas once at module scope — shared across all describe blocks.
// This avoids needing before() hooks and is safe because loadSchemas is pure.
const SCHEMAS = loadSchemas(SCHEMAS_DIR);

// ---------------------------------------------------------------------------
// loadSchemas / matchSchemaForPath
// ---------------------------------------------------------------------------

describe('loadSchemas', () => {
  it('loads every schema present in the schemas dir', () => {
    // Exclude internal index keys (_byGlob, and _byKind once the kind-discriminator lands).
    const names = Object.keys(SCHEMAS).filter(k => k !== '_byGlob' && k !== '_byKind');
    // Core long-lived schemas.
    for (const core of ['handoff', 'handoff-archived', 'decision', 'plan', 'review',
                         'lesson-entry', 'completion-entry', 'cross-repo-memo']) {
      assert.ok(names.includes(core), `${core} schema missing`);
    }
    // Deliverable-type-taxonomy additions (2026-06-23).
    for (const added of ['review-sidecar', 'prior-art-check', 'plan-coverage-check',
                         'docs-check-sidecar', 'integration-summary', 'problem-set', 'archived-memo']) {
      assert.ok(names.includes(added), `${added} schema missing`);
    }
    // Count is DERIVED from disk, not hard-coded — adding a schema no longer breaks this
    // test, and a mismatch also catches a duplicate `schema:` name collision across files.
    const fs = require('fs');
    const path = require('path');
    const yamlCount = fs.readdirSync(path.join(__dirname, '../../schemas'))
      .filter(f => f.endsWith('.yaml')).length;
    assert.equal(names.length, yamlCount,
      `loaded ${names.length} schema names but ${yamlCount} .yaml files on disk (duplicate schema: name?)`);
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

describe('matchSchema — unknown/null kind falls through to glob', () => {
  // S1-F3: an unknown kind value must fall through to glob-fallback rather than returning null.
  it('unknown kind falls through to glob: plan path with unknown kind → plan schema', () => {
    const result = matchSchema('docs/plans/2026-01-01-foo.md', { kind: 'completely-unknown-kind' }, SCHEMAS);
    assert.ok(result !== null, 'unknown kind must fall through to glob and return a match');
    assert.equal(result.schemaName, 'plan',
      `unknown kind on plan path must resolve to plan via glob, got ${result && result.schemaName}`);
  });

  // S1-F8: null kind must not be treated as a valid discriminator; must fall through to glob.
  it('null kind falls through to glob: plan path with kind:null → plan schema', () => {
    const result = matchSchema('docs/plans/2026-01-01-foo.md', { kind: null }, SCHEMAS);
    assert.ok(result !== null, 'null kind must fall through to glob and return a match');
    assert.equal(result.schemaName, 'plan',
      `null kind on plan path must resolve to plan via glob, got ${result && result.schemaName}`);
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
      branch: 'work/machine-a/2026-05-29',
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
      branch: 'work/machine-a/2026-05-28',
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
      branch: 'work/machine-a/2026-05-01',
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
      branch: 'work/machine-a/2026-05-29',
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
      branch: 'work/machine-a/2026-05-29',
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
      branch: 'work/machine-a/2026-05-29',
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

  it('actioned+accepted with realized_by but no picked_up_by PASSES (picked_up_by not mandated on actioned)', () => {
    // realized_by is required on actioned+accepted (2026-06-23 claim-of-record rule); picked_up_by is
    // preserved-not-mandated on the terminal flip, so its absence here must still validate.
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: 'inline' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `actioned memo should pass, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — cross-repo-memo realized_by claim-of-record rule
// Spec backlink: docs/plans/2026-06-23-memo-pickup-realization-claim-visibility.md § C1/C3
// ---------------------------------------------------------------------------

describe('validateFrontmatter — cross-repo-memo realized_by claim-of-record', () => {
  const memoSchema = SCHEMAS['cross-repo-memo'];

  function baseMemo(overrides = {}) {
    return Object.assign({
      title: 'Test memo',
      from: 'holodeck-em',
      to: 'claude-central-em',
      created: '2026-06-23',
      status: 'open',
      delivery_mode: 'receiver-repo',
    }, overrides);
  }

  it('(a) actioned+accepted with realized_by plan path PASSES', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: 'docs/plans/2026-06-23-foo.md' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `actioned+accepted with plan path should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('(b) actioned+accepted with realized_by "inline" PASSES', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: 'inline' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `actioned+accepted with inline sentinel should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('(c) actioned+accepted WITHOUT realized_by FAILS', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'accepted' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'actioned+accepted without realized_by should fail');
    const err = result.errors.find(e => e.field === 'realized_by');
    assert.ok(err, `Expected realized_by error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required when status=actioned and decision=accepted/);
  });

  it('(d) actioned+accepted with EMPTY-STRING and WHITESPACE-ONLY realized_by FAIL (trim guard)', () => {
    for (const v of ['', '   ']) {
      const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: v });
      const result = validateFrontmatter(fm, memoSchema);
      assert.equal(result.ok, false, `actioned+accepted with realized_by="${v}" should fail`);
      assert.ok(result.errors.find(e => e.field === 'realized_by'), `Expected realized_by error for "${v}", got: ${JSON.stringify(result.errors)}`);
    }
  });

  it('(e) actioned+declined WITHOUT realized_by PASSES (exemption — no work realized)', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'declined' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `actioned+declined should be exempt, got: ${JSON.stringify(result.errors)}`);
  });

  it('(f) actioned+accepted with created < 2026-05-22 PASSES (grandfather short-circuit)', () => {
    const fm = baseMemo({ created: '2026-05-21', status: 'actioned', decision: 'accepted' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `pre-cutoff actioned+accepted should be grandfathered, got: ${JSON.stringify(result.errors)}`);
  });

  it('(g) actioned+partial WITHOUT realized_by FAILS (partial also realizes work)', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'partial' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'actioned+partial without realized_by should fail');
    const err = result.errors.find(e => e.field === 'realized_by');
    assert.ok(err, `Expected realized_by error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required when status=actioned and decision=partial/);
  });

  it('(h) actioned+accepted with malformed realized_by (bare prose word) FAILS shape check', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: 'done' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, 'malformed realized_by should fail shape check');
    const err = result.errors.find(e => e.field === 'realized_by');
    assert.ok(err, `Expected realized_by shape error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /malformed realized_by/);
  });

  it('(i) actioned+accepted with realized_by tasks/<feature>/todo.md path PASSES (path shape)', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: 'tasks/memo-pickup/todo.md' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `path-shaped realized_by should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('(j) actioned+accepted with realized_by 7-char hex SHA PASSES (SHA shape)', () => {
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: 'a1b2c3d' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `SHA-shaped realized_by should pass, got: ${JSON.stringify(result.errors)}`);
  });

  // (j2) F1+F9 — SHA-256 64-char hex PASSES (widened upper bound: 7–64 hex chars).
  // Regex widened from /^[0-9a-f]{7,40}$/ → /^[0-9a-fA-F]{7,64}$/ for SHA-256 object names.
  it('(j2) actioned+accepted with 64-char hex SHA PASSES (SHA-256 upper bound)', () => {
    const sha256 = 'a'.repeat(64);
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: sha256 });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `64-char hex SHA should pass, got: ${JSON.stringify(result.errors)}`);
  });

  // (j3) F1+F9 — 65-char hex FAILS shape check (exceeds 64-char upper bound).
  it('(j3) actioned+accepted with 65-char hex SHA FAILS shape check (exceeds upper bound)', () => {
    const tooLong = 'a'.repeat(65);
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: tooLong });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, '65-char hex should fail shape check');
    const err = result.errors.find(e => e.field === 'realized_by');
    assert.ok(err, `Expected realized_by shape error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /malformed realized_by/);
  });

  // (f2) F2 — grandfather boundary: created: 2026-05-22 is NOT grandfathered (cutoff is strict <).
  // realized_by is required here; the test confirms the rule fires on the exact cutoff date.
  it('(f2) actioned+accepted with created 2026-05-22 FAILS (NOT grandfathered — cutoff is strict <)', () => {
    const fm = baseMemo({ created: '2026-05-22', status: 'actioned', decision: 'accepted' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.equal(result.ok, false, '2026-05-22 should NOT be grandfathered (cutoff is created < 2026-05-22)');
    const err = result.errors.find(e => e.field === 'realized_by');
    assert.ok(err, `Expected realized_by error for 2026-05-22 (not grandfathered), got: ${JSON.stringify(result.errors)}`);
  });

  // (e2) F3 — consult/fyi terminal path: absent decision is exempt from realized_by rule.
  // status=actioned without a decision field (consult/fyi terminal path) realizes no work → no realized_by required.
  it('(e2) actioned with NO decision field PASSES (consult/fyi terminal path — rule exempts absent decision)', () => {
    // consult/fyi path: the receiver marks actioned but has no work-realizing decision (accepted/partial).
    // The rule only fires when decision === 'accepted' || decision === 'partial'.
    const fm = baseMemo({ status: 'actioned' }); // no decision field at all
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `actioned with no decision should pass (consult/fyi path — not a work-realizing disposition), got: ${JSON.stringify(result.errors)}`);
  });

  // F4 — documents the deliberate '/' path permissiveness: 'see/above' passes.
  // The '/' check catches the common path case; a slash-containing prose value is a
  // pathological input not worth over-fitting against (realized_by is advisory attribution).
  it('(F4-doc) realized_by "see/above" PASSES (deliberate: / check is intentionally permissive)', () => {
    // This is a documenting test — the permissive '/' shape is intentional, not a bug.
    const fm = baseMemo({ status: 'actioned', decision: 'accepted', realized_by: 'see/above' });
    const result = validateFrontmatter(fm, memoSchema);
    assert.ok(result.ok, `realized_by with a slash is always accepted (deliberate permissiveness), got: ${JSON.stringify(result.errors)}`);
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

  it('status:actioned with decision:accepted and realized_by passes', () => {
    const fm = baseMemo({
      status: 'actioned',
      action_taken_at: '2026-05-24T10:00:00Z',
      decision: 'accepted',
      realized_by: 'inline',  // required on actioned+accepted (2026-06-23 claim-of-record rule)
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

// parseYamlBlock — PUBLIC export contract. handoff-transition.js depends on this
// name being a callable export; a reviewer edit once swapped the call site to
// `parseYamlBlock` before it was exported, crashing every cs_consume_handoff
// fleet-wide (cross-repo memo 2026-06-26). This guards the export contract.
describe('parseYamlBlock (public export)', () => {
  it('is exported as a callable function', () => {
    assert.equal(typeof parseYamlBlock, 'function');
  });

  it('parses a frontmatter block the same as the internal parser', () => {
    const block = 'status: consumed\ndeployment_state: in_flight\n';
    assert.deepEqual(parseYamlBlock(block), _parseYaml(block));
  });
});

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
// parseScalar #-truncation fix (Camelia C-F6 / Patrik F5)
//
// A `#` inside an unquoted YAML value must NOT be stripped when it is followed
// immediately by a non-space character (e.g. issue numbers, hashtags like #4).
// Only `\s#\s` and `\s#$` (space before `#`, space-or-EOL after `#`) are
// genuine trailing YAML comments.
//
// tc-5 spec backlink:
//   state/handoffs/2026-06-22_230005_roadmap-cockpit-contract-ext-2026-06-22-tc-5.md
// ---------------------------------------------------------------------------

describe('parseScalar #-truncation fix', () => {
  it('planted title "Borrow #4 widgets" round-trips intact through parseFrontmatter', () => {
    // The canonical planted-title test from the AC: unquoted `#4` must not be stripped.
    const content = '---\ntitle: Borrow #4 widgets\ncreated: 2026-06-22\n---\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null, 'frontmatter must parse');
    assert.equal(frontmatter.title, 'Borrow #4 widgets',
      `Expected full title "Borrow #4 widgets" but got "${frontmatter.title}" — ` +
      '#-truncation fix not applied');
  });

  it('quoted title "Borrow #4 widgets" round-trips intact (pre-fix baseline)', () => {
    // Double-quoted values were always safe; verify the fix did not break them.
    const content = '---\ntitle: "Borrow #4 widgets"\ncreated: 2026-06-22\n---\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null, 'frontmatter must parse');
    assert.equal(frontmatter.title, 'Borrow #4 widgets');
  });

  it('genuine trailing comment "value  # trailing note" is still stripped', () => {
    // Regression-guard: `\s#\s` must still be treated as a comment.
    const content = '---\nstatus: draft  # work in progress\ncreated: 2026-06-22\n---\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null);
    assert.equal(frontmatter.status, 'draft',
      'Trailing comment after space-#-space must still be stripped');
  });

  it('"issue #123 fixed" (unquoted #NNN) round-trips intact', () => {
    const content = '---\ntitle: issue #123 fixed\ncreated: 2026-06-22\n---\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null);
    assert.equal(frontmatter.title, 'issue #123 fixed');
  });

  it('"value  # comment" (space-#-space) is stripped even with preceding double-space', () => {
    const content = '---\ntitle: foo  # comment here\ncreated: 2026-06-22\n---\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null);
    assert.equal(frontmatter.title, 'foo');
  });

  it('"has#no-space" (no space before #) is never stripped', () => {
    const content = '---\ntitle: has#no-space\ncreated: 2026-06-22\n---\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null);
    assert.equal(frontmatter.title, 'has#no-space');
  });

  // Review: F2 — tab after '#' must also be treated as a comment opener.
  // 'value  #\ttab comment' → 'value'  (was preserved verbatim before this fix).
  it('"value  #\\ttab comment" (tab after #) is stripped as a comment', () => {
    const content = '---\nstatus: value  #\ttab comment\ncreated: 2026-06-22\n---\n';
    const { frontmatter } = parseFrontmatter(content);
    assert.ok(frontmatter !== null);
    assert.equal(frontmatter.status, 'value',
      'Tab after # must be treated as comment opener just like a space');
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

// ---------------------------------------------------------------------------
// C2-tests: matchSchema / _byKind index — RED-first regression net
//
// These tests will FAIL until C2-impl lands:
//   - matchSchema is not yet exported from schema.js (undefined → not a function)
//   - loadSchemas does not yet build _byKind or throw on duplicate kind ownership
//
// Purpose: encode AC1/AC2/AC3/F1/F5 oracle so the impl wave lands into a net.
// Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C2
// ---------------------------------------------------------------------------

describe('matchSchema — kind-wins-over-glob (AC1)', () => {
  // AC1: a file at a plan-glob path with kind: review-sidecar must resolve to
  // the review-sidecar schema, NOT the plan schema. This is the core design
  // decision — kind-first, glob-fallback.
  it('kind-wins-over-glob: review-sidecar sidecar at docs/plans/ resolves to review-sidecar schema', () => {
    // matchSchema is undefined until C2-impl — this throws "matchSchema is not a function"
    // which is the expected RED state.
    const result = matchSchema(
      'docs/plans/2026-06-23-my-plan.zoli-review.md',
      { kind: 'review-sidecar' },
      SCHEMAS
    );
    assert.ok(result !== null, 'expected a match');
    assert.equal(result.schemaName, 'review-sidecar',
      `expected review-sidecar, got ${result && result.schemaName}`);
  });

  it('kind-wins-over-glob: staff-eng-review kind also resolves to review-sidecar schema', () => {
    const result = matchSchema(
      'docs/plans/2026-06-23-my-plan.patrik-review.md',
      { kind: 'staff-eng-review' },
      SCHEMAS
    );
    assert.ok(result !== null, 'expected a match');
    assert.equal(result.schemaName, 'review-sidecar',
      `expected review-sidecar, got ${result && result.schemaName}`);
  });

  it('kind-wins-over-glob: kind match beats the broader plan glob at docs/plans/', () => {
    // docs/plans/*.md matches the PLAN schema by glob. A kind: review-sidecar
    // frontmatter field must override that and return review-sidecar instead.
    // This is the fight-the-hook fix: the file lives in docs/plans/ but is NOT
    // a plan; its kind: discriminator is the authoritative type signal.
    const globMatch = matchSchemaForPath('docs/plans/2026-06-23-my-plan.zoli-review.md', SCHEMAS);
    // The glob still matches plan (unchanged path-only resolution)
    assert.ok(globMatch !== null, 'glob should still match plan by path');
    assert.equal(globMatch.schemaName, 'plan', 'glob alone resolves to plan');

    // But matchSchema with kind: review-sidecar overrides to the correct schema
    const kindMatch = matchSchema(
      'docs/plans/2026-06-23-my-plan.zoli-review.md',
      { kind: 'review-sidecar' },
      SCHEMAS
    );
    assert.ok(kindMatch !== null, 'expected kind-match to return a result');
    assert.equal(kindMatch.schemaName, 'review-sidecar',
      'kind must win over the glob when frontmatter.kind is set');
  });
});

describe('matchSchema — kindless-plan-fallback (AC2)', () => {
  // AC2: a real plan with no kind: in frontmatter must still resolve to plan.yaml
  // via the existing glob mechanism (back-compat for all 174 existing plans).
  it('kindless-plan-fallback: plan without kind field resolves to plan schema via glob', () => {
    const result = matchSchema(
      'docs/plans/2026-01-01-real-plan.md',
      { title: 'a real plan', author: 'em', status: 'draft' },
      SCHEMAS
    );
    assert.ok(result !== null, 'expected a match for a plan path');
    assert.equal(result.schemaName, 'plan',
      `expected plan schema via glob fallback, got ${result && result.schemaName}`);
  });

  it('kindless-plan-fallback: null frontmatter falls back to glob (matchSchemaForPath parity)', () => {
    // matchSchemaForPath is equivalent to matchSchema(path, null, schemas).
    // The glob-fallback path must behave identically whether frontmatter is
    // null, undefined, or a frontmatter object with no kind: field.
    const viaNull = matchSchema('docs/plans/2026-01-01-foo.md', null, SCHEMAS);
    const viaMatchForPath = matchSchemaForPath('docs/plans/2026-01-01-foo.md', SCHEMAS);
    assert.ok(viaNull !== null, 'null frontmatter should fall back to glob');
    assert.equal(
      viaNull && viaNull.schemaName,
      viaMatchForPath && viaMatchForPath.schemaName,
      'matchSchema(path, null) must be identical to matchSchemaForPath(path)'
    );
  });

  it('kindless-plan-fallback: handoff without kind still resolves to handoff schema', () => {
    // Ensures the glob-fallback path works for non-plan schema families too.
    const result = matchSchema(
      'state/handoffs/2026-01-01-test.md',
      { title: 'test handoff', status: 'active' },
      SCHEMAS
    );
    assert.ok(result !== null, 'expected a match for handoff path');
    assert.equal(result.schemaName, 'handoff',
      `expected handoff via glob fallback, got ${result && result.schemaName}`);
  });
});

describe('matchSchema — per-type-clean-validate (AC3)', () => {
  // AC3: a review-sidecar frontmatter carrying ONLY its own type's fields
  // (no plan-schema fields like title/author/status enum) must pass
  // validateFrontmatter against the review-sidecar schema.
  //
  // This is the "no fight-the-hook" assertion: the sidecar validates cleanly
  // against ITS OWN schema without requiring plan-schema fields.
  it('per-type-clean-validate: review-sidecar fm with only plan: passes review-sidecar schema', () => {
    const reviewSidecarSchema = SCHEMAS['review-sidecar'];
    assert.ok(reviewSidecarSchema, 'review-sidecar schema must be loaded (C1 precondition)');

    // Only the minimal required field per the Execution Notes (required: plan only)
    const fm = { plan: 'docs/plans/2026-06-23-my-plan.md' };
    const result = validateFrontmatter(fm, reviewSidecarSchema);
    assert.ok(result.ok,
      `review-sidecar fm with only {plan:} should pass its own schema, got: ${JSON.stringify(result && result.errors)}`);
  });

  it('per-type-clean-validate: review-sidecar fm without plan: field FAILS (required field)', () => {
    // Negative: the one required field (plan:) must be enforced.
    const reviewSidecarSchema = SCHEMAS['review-sidecar'];
    assert.ok(reviewSidecarSchema, 'review-sidecar schema must be loaded (C1 precondition)');

    const fm = { reviewer: 'patrik', verdict: 'approve' }; // missing plan:
    const result = validateFrontmatter(fm, reviewSidecarSchema);
    assert.equal(result.ok, false,
      'review-sidecar without plan: field should fail');
    const err = result.errors && result.errors.find(e => e.field === 'plan');
    assert.ok(err, `Expected plan field error, got: ${JSON.stringify(result.errors)}`);
  });

  it('per-type-clean-validate: review-sidecar fm does NOT require plan-schema fields (title/author/status)', () => {
    // The anti-fight-the-hook assertion: a sidecar lacking title/author/status
    // must NOT fail against the review-sidecar schema. If it fails here, the
    // fight-the-hook defect has been re-created in the new schema.
    const reviewSidecarSchema = SCHEMAS['review-sidecar'];
    assert.ok(reviewSidecarSchema, 'review-sidecar schema must be loaded (C1 precondition)');

    const fm = { plan: 'docs/plans/2026-06-23-my-plan.md' };
    // Explicitly confirm title/author/status are NOT required by the schema
    const result = validateFrontmatter(fm, reviewSidecarSchema);
    assert.ok(result.ok,
      'review-sidecar schema MUST NOT require title/author/status — that recreates fight-the-hook');
  });
});

describe('matchSchema — legacy-kinds-resolve (AC for F1)', () => {
  // Legacy kind values from the disk census must all resolve to review-sidecar.
  // These legacy values stay as resolvers (no data migration, per Decision 2).
  // Full disk census (2026-06-23): plan-review(6), review(5), code-review(4),
  // review-sidecar(3), patrik-review(3), substrate-adjudication(1), plan-rereview(1).
  // Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 2

  const LEGACY_REVIEW_KINDS = [
    'patrik-review',
    'substrate-adjudication',
    'plan-rereview',
    // Additional census values (confirmed to be in kinds: list in review-sidecar.yaml)
    'plan-review',
    'review',
    'review-sidecar',
    'code-review',
  ];

  for (const kind of LEGACY_REVIEW_KINDS) {
    it(`legacy kind "${kind}" resolves to review-sidecar schema`, () => {
      const result = matchSchema(
        'docs/plans/2026-06-23-my-plan.some-suffix.md',
        { kind },
        SCHEMAS
      );
      assert.ok(result !== null,
        `expected a match for kind: ${kind}`);
      assert.equal(result.schemaName, 'review-sidecar',
        `kind "${kind}" must resolve to review-sidecar (legacy resolver), got ${result && result.schemaName}`);
    });
  }

  it('role-based canonical kind "staff-eng-review" resolves to review-sidecar schema', () => {
    const result = matchSchema(
      'docs/plans/2026-06-23-my-plan.patrik-review.md',
      { kind: 'staff-eng-review' },
      SCHEMAS
    );
    assert.ok(result !== null, 'staff-eng-review should match');
    assert.equal(result.schemaName, 'review-sidecar',
      `staff-eng-review must resolve to review-sidecar, got ${result && result.schemaName}`);
  });

  it('role-based canonical kind "eng-director-review" resolves to review-sidecar schema', () => {
    const result = matchSchema(
      'docs/plans/2026-06-23-my-plan.zoli-review.md',
      { kind: 'eng-director-review' },
      SCHEMAS
    );
    assert.ok(result !== null, 'eng-director-review should match');
    assert.equal(result.schemaName, 'review-sidecar',
      `eng-director-review must resolve to review-sidecar, got ${result && result.schemaName}`);
  });
});

// ---------------------------------------------------------------------------
// parseList — list-of-maps
//
// Spec backlink: bin/lib/schema.js parseList() / skipPast() fix for
// YAML list items that are mappings (e.g. provenance: - original_path: ...).
//
// Bug: parseList pushed only the scalar text of the '- ' line for mapping
// items, then broke on the continuation indented keys. skipPast also broke
// at the same nested line. After the last line of the nested block, the outer
// parseYamlLines resumed AT the continuation key and read it as a top-level key
// (last-wins clobber). This caused 'status: implemented' inside a provenance
// list to silently overwrite the real top-level 'status: proposed'.
// ---------------------------------------------------------------------------

describe('parseList — list-of-maps', () => {
  // Test 1: The reported bug. Top-level status must not be clobbered by a
  // status key nested inside a provenance list-of-maps block.
  it('(1) reported bug: provenance list-of-maps does not clobber top-level status', () => {
    const yaml = [
      'status: proposed',
      'provenance:',
      '  - original_path: docs/plans/foo.md',
      '    status: implemented',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.equal(result.status, 'proposed',
      `top-level status must be "proposed", not clobbered by nested "implemented"; got "${result.status}"`);
    assert.ok(Array.isArray(result.provenance), 'provenance must be an array');
    assert.equal(result.provenance.length, 1, 'provenance must have one item');
    assert.equal(result.provenance[0].original_path, 'docs/plans/foo.md',
      `provenance[0].original_path must be "docs/plans/foo.md", got "${result.provenance[0] && result.provenance[0].original_path}"`);
    assert.equal(result.provenance[0].status, 'implemented',
      `provenance[0].status must be "implemented", got "${result.provenance[0] && result.provenance[0].status}"`);
  });

  // Test 2: Multi-key mapping items: a list item with 3 keys parses all 3 into one object.
  it('(2) multi-key mapping item: 3 keys all parsed into one object', () => {
    const yaml = [
      'items:',
      '  - name: alpha',
      '    value: 1',
      '    label: first',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.ok(Array.isArray(result.items), 'items must be an array');
    assert.equal(result.items.length, 1);
    assert.equal(result.items[0].name, 'alpha');
    assert.equal(result.items[0].value, 1);
    assert.equal(result.items[0].label, 'first');
  });

  // Test 3: Multiple mapping items in one list.
  it('(3) multiple mapping items: two items each with 2 keys', () => {
    const yaml = [
      'entries:',
      '  - a: 1',
      '    b: 2',
      '  - a: 3',
      '    b: 4',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.ok(Array.isArray(result.entries), 'entries must be an array');
    assert.equal(result.entries.length, 2);
    assert.equal(result.entries[0].a, 1);
    assert.equal(result.entries[0].b, 2);
    assert.equal(result.entries[1].a, 3);
    assert.equal(result.entries[1].b, 4);
  });

  // Test 4: Scalar lists still work (regression guard).
  it('(4) scalar lists are unaffected — [x, y] parses to ["x", "y"]', () => {
    const yaml = 'tags:\n  - x\n  - y\n';
    const result = _parseYaml(yaml);
    assert.deepEqual(result.tags, ['x', 'y'], 'scalar list must still parse correctly');
  });

  it('(4b) bare "-" list item parses to null element', () => {
    const yaml = 'items:\n  -\n  - foo\n';
    const result = _parseYaml(yaml);
    assert.ok(Array.isArray(result.items), 'items must be an array');
    assert.equal(result.items[0], null, 'bare "-" must parse to null');
    assert.equal(result.items[1], 'foo');
  });

  // Test 5: A scalar whose value contains a colon (e.g. a URL) must NOT be
  // parsed as a mapping item. The discriminator checks for a key: shape, not
  // a bare presence of ':'.
  it('(5) URL-valued scalar list item is not misparsed as a mapping', () => {
    const yaml = [
      'links:',
      '  - http://example.com/path',
      '  - https://other.org/foo',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.ok(Array.isArray(result.links), 'links must be an array');
    assert.equal(result.links[0], 'http://example.com/path',
      'URL scalar must not be treated as a mapping item');
    assert.equal(result.links[1], 'https://other.org/foo');
  });
});

describe('loadSchemas — dup-kind-fail-loud (F5)', () => {
  // Decision 1: "Detect-then-silently-pick is a footgun" (CLAUDE.md).
  // loadSchemas MUST throw if two schemas declare the same kind: value.
  // A copy-paste duplicate (e.g. "foo" in both A.yaml and B.yaml) would otherwise
  // be a silent first-win, mis-routing a whole artifact family.
  // Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 1

  it('dup-kind-fail-loud: two schemas sharing the same kind: value causes loadSchemas to throw', () => {
    // Build a throwaway tmpdir with two minimal schemas both claiming kind "foo".
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'schema-test-dup-'));
    try {
      const schemaA = [
        'schema: schema-a',
        'applies_to: "docs/foo-a/*.md"',
        'kinds: [foo, unique-to-a]',
        'required:',
        '  plan: string',
      ].join('\n') + '\n';
      const schemaB = [
        'schema: schema-b',
        'applies_to: "docs/foo-b/*.md"',
        'kinds: [foo, unique-to-b]',  // "foo" is duplicated here
        'required:',
        '  plan: string',
      ].join('\n') + '\n';

      fs.writeFileSync(path.join(tmpDir, 'schema-a.yaml'), schemaA, 'utf8');
      fs.writeFileSync(path.join(tmpDir, 'schema-b.yaml'), schemaB, 'utf8');

      // loadSchemas must throw — detect-then-fail-loud on duplicate kind ownership.
      assert.throws(
        () => loadSchemas(tmpDir),
        (err) => {
          // The error must name the duplicate kind value so the author can find
          // the offending schema immediately.
          return err instanceof Error && /foo/.test(err.message);
        },
        'loadSchemas must throw when two schemas share a kind: value'
      );
    } finally {
      // Clean up tmpdir regardless of test outcome.
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('dup-kind-fail-loud: schemas with DISJOINT kinds do NOT throw (negative guard)', () => {
    // Ensure the throw only fires on actual duplicates, not on any multi-kind schema.
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'schema-test-nodup-'));
    try {
      const schemaA = [
        'schema: schema-a',
        'applies_to: "docs/foo-a/*.md"',
        'kinds: [alpha, beta]',
        'required:',
        '  plan: string',
      ].join('\n') + '\n';
      const schemaB = [
        'schema: schema-b',
        'applies_to: "docs/foo-b/*.md"',
        'kinds: [gamma, delta]',  // disjoint — no duplicate
        'required:',
        '  plan: string',
      ].join('\n') + '\n';

      fs.writeFileSync(path.join(tmpDir, 'schema-a.yaml'), schemaA, 'utf8');
      fs.writeFileSync(path.join(tmpDir, 'schema-b.yaml'), schemaB, 'utf8');

      // Must NOT throw — disjoint kinds are fine.
      let schemas;
      assert.doesNotThrow(() => {
        schemas = loadSchemas(tmpDir);
      }, 'loadSchemas must not throw when kind ownership is disjoint');

      assert.ok(schemas, 'schemas object should be returned');
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});
