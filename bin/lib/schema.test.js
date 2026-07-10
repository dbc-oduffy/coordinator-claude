'use strict';
/**
 * schema.test.js — unit tests for bin/lib/schema.js
 *
 * Run with: node --test bin/lib/schema.test.js
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1 Tests
 * This file covers multiple schema test suites; each block carries its own per-block spec backlink.
 * (Former file-level backlink docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C2 covered
 * only the deliverable-type suite; the origin-axis suite added 2026-07-07 has its own inline backlink.)
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
  validateFrontmatterDispatch,
  validateLessonsFile,
  validateRecord,
  testNegativeCorpus,
  _parseYaml,
  parseYaml,
  parseYamlBlock,
  _matchGlob,
  _isJsonSchemaBacked,
  matchSchema,
  checkReferentialIntegrity,
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
    // W1 ccos-1: count includes both .yaml and .schema.json files (dual-format loader).
    const fs = require('fs');
    const path = require('path');
    const schemasDir = path.join(__dirname, '../../schemas');
    const yamlCount = fs.readdirSync(schemasDir).filter(f => f.endsWith('.yaml')).length;
    const jsonSchemaCount = fs.readdirSync(schemasDir).filter(f => f.endsWith('.schema.json')).length;
    assert.equal(names.length, yamlCount + jsonSchemaCount,
      `loaded ${names.length} schema names but ${yamlCount} .yaml + ${jsonSchemaCount} .schema.json files on disk (duplicate schema: name?)`);
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

  it('post-cutoff handoff with 141-char summary FAILS', () => {
    const longSummary = 'A'.repeat(141);
    const fm = basePostCutoff({ summary: longSummary });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, '141-char summary should fail');
    const err = result.errors.find(e => e.field === 'summary');
    assert.ok(err, `Expected summary length error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /exceeds 140 characters/);
  });

  it('post-cutoff handoff with valid category + ≤140-char summary PASSES', () => {
    const result = validateFrontmatter(basePostCutoff(), handoffSchema);
    assert.ok(result.ok, `Valid post-cutoff handoff with category + summary should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('post-cutoff handoff with exactly 140-char summary PASSES', () => {
    const exactly140 = 'B'.repeat(140);
    const fm = basePostCutoff({ summary: exactly140 });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Exactly-140-char summary should pass, got: ${JSON.stringify(result.errors)}`);
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
// validateFrontmatter — handoff shipped_in shape guard (C4b)
// Mirrors realized_by's /^[0-9a-fA-F]{7,64}$/ regex: shipped_in must be a bare
// hex SHA OR the sanctioned `substantively-shipped-no-commit:<YYYY-MM-DD>`
// token — prose rationale and annotated SHAs (e.g. "[~/.claude] f4f150a1d")
// are rejected. Mechanizes pickup Step 3f (stealth-skip / rationale-prose
// defer detection).
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C4b
// ---------------------------------------------------------------------------

describe('validateFrontmatter — handoff shipped_in shape guard (C4b)', () => {
  const handoffSchema = SCHEMAS['handoff'];

  function baseShipped(overrides = {}) {
    return Object.assign({
      title: 'Post-cutoff shipped handoff',
      created: '2026-05-29',
      branch: 'work/machine-a/2026-05-29',
      status: 'consumed',
      predecessor: null,
      category: 'infra',
      summary: 'Shipped handoff exercising the shipped_in shape guard',
      deployment_state: 'shipped',
    }, overrides);
  }

  it('bare 7-char hex SHA PASSES', () => {
    const fm = baseShipped({ shipped_in: 'abc1234' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Bare SHA should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('bare 40-char hex SHA PASSES', () => {
    const fm = baseShipped({ shipped_in: 'a'.repeat(40) });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Full 40-char SHA should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('substantively-shipped-no-commit:<YYYY-MM-DD> token PASSES', () => {
    const fm = baseShipped({ shipped_in: 'substantively-shipped-no-commit:2026-07-08' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Sanctioned stealth-skip token should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('annotated SHA "[~/.claude] f4f150a1d" FAILS', () => {
    const fm = baseShipped({ shipped_in: '[~/.claude] f4f150a1d' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Annotated SHA should fail strict regex');
    const err = result.errors.find(e => e.field === 'shipped_in');
    assert.ok(err, `Expected shipped_in error, got: ${JSON.stringify(result.errors)}`);
  });

  it('prose rationale FAILS', () => {
    const fm = baseShipped({ shipped_in: 'shipped as part of the bigger refactor, no single commit' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Prose rationale should fail');
    const err = result.errors.find(e => e.field === 'shipped_in');
    assert.ok(err, `Expected shipped_in error, got: ${JSON.stringify(result.errors)}`);
  });

  it('token with trailing prose suffix FAILS (whole-value match, not accept-anything-after-colon)', () => {
    const fm = baseShipped({ shipped_in: 'substantively-shipped-no-commit:2026-07-08 because reasons' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Token with trailing prose must fail — whole-value pattern match');
    const err = result.errors.find(e => e.field === 'shipped_in');
    assert.ok(err, `Expected shipped_in error, got: ${JSON.stringify(result.errors)}`);
  });

  it('token with malformed date (non-ISO) FAILS', () => {
    const fm = baseShipped({ shipped_in: 'substantively-shipped-no-commit:07-08-2026' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Non-ISO date suffix must fail');
    const err = result.errors.find(e => e.field === 'shipped_in');
    assert.ok(err, `Expected shipped_in error, got: ${JSON.stringify(result.errors)}`);
  });

  it('token with no date suffix FAILS', () => {
    const fm = baseShipped({ shipped_in: 'substantively-shipped-no-commit:' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Token without a date suffix must fail');
    const err = result.errors.find(e => e.field === 'shipped_in');
    assert.ok(err, `Expected shipped_in error, got: ${JSON.stringify(result.errors)}`);
  });

  it('pre-cutoff handoff (created < 2026-05-29) with shipped_in ABSENT PASSES (requirement-exemption, not shape-exemption)', () => {
    const fm = {
      title: 'Legacy shipped handoff',
      created: '2026-05-01',
      branch: 'work/machine-a/2026-05-01',
      status: 'consumed',
      predecessor: null,
      deployment_state: 'shipped',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Pre-cutoff shipped handoff without shipped_in should pass (Rule A3a-2b requirement is date-gated), got: ${JSON.stringify(result.errors)}`);
  });

  it('pre-cutoff handoff (created < 2026-05-29) with malformed shipped_in SET is REJECTED (pattern is a shape guard, not date-gated — only the requirement is)', () => {
    const fm = {
      title: 'Legacy shipped handoff',
      created: '2026-05-01',
      branch: 'work/machine-a/2026-05-01',
      status: 'consumed',
      predecessor: null,
      deployment_state: 'shipped',
      shipped_in: 'not a sha at all, just legacy prose',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Pre-cutoff malformed shipped_in, when SET, must fail shape validation — the date gate exempts the requirement, not the value shape');
    const err = result.errors.find(e => e.field === 'shipped_in');
    assert.ok(err, `Expected shipped_in shape error, got: ${JSON.stringify(result.errors)}`);
  });

  it('shipped_in absent (non-shipped deployment_state) is unaffected by the shape guard', () => {
    const fm = baseShipped({ deployment_state: 'in_flight', shipped_in: undefined });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Non-shipped handoff without shipped_in should pass, got: ${JSON.stringify(result.errors)}`);
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
      stub_id: 'rm-1',
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
      to: 'example-game-repo-em',
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
      from: 'example-game-repo-em',
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
      to: 'example-game-repo-em',
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
      to: 'example-game-repo-em',
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
  // lesson-entry.yaml migrated to match_mode: whole-document-yaml (per-file YAML
  // records), so it no longer carries the legacy inline-tag config. These tests
  // exercise validateLessonsFile()'s inline-tag logic directly against a fixed
  // synthetic fixture, decoupled from the live schema. See schemas/lesson-entry.yaml.
  const lessonSchema = {
    match_mode: 'inline-tag-per-entry',
    tag_enum: { values: ['universal', 'project'], untagged_allowed: true },
  };

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

  // Dotfile-exclusion invariant tests.
  // Wildcards at a path-segment start must not match dot-prefixed basenames, mirroring
  // Unix shell / pathlib.Path.glob semantics. Dot-prefixed files are control/config
  // artifacts, not corpus records.
  it('*.json does NOT match a dot-prefixed basename', () => {
    assert.ok(
      !_matchGlob('state/review-trail/*.json', 'state/review-trail/.weekly-reviewer-scopes.json'),
      '*.json must not match .weekly-reviewer-scopes.json (dotfile-exclusion invariant)'
    );
  });

  it('*.json STILL matches a normal basename', () => {
    assert.ok(
      _matchGlob('state/review-trail/*.json', 'state/review-trail/20260627T120301Z.json'),
      '*.json must match a normal timestamped record'
    );
  });

  it('bare * at segment start does not match a dotfile', () => {
    assert.ok(!_matchGlob('state/x/*', 'state/x/.hidden'), 'bare * must not match .hidden');
    assert.ok(_matchGlob('state/x/*', 'state/x/visible'), 'bare * must match visible');
  });

  it('? at segment start does not match a leading dot', () => {
    assert.ok(!_matchGlob('dir/?ile', 'dir/.ile'), '? must not match leading dot');
    assert.ok(_matchGlob('dir/?ile', 'dir/file'), '? must match a normal char');
  });

  it('explicit bracket class [0-9]* still matches dated files and not dotfiles', () => {
    assert.ok(
      _matchGlob('cross-repo/inbox/[0-9]*.md', 'cross-repo/inbox/2026-06-27-x.md'),
      '[0-9]* must match digit-prefixed dated file'
    );
    assert.ok(
      !_matchGlob('cross-repo/inbox/[0-9]*.md', 'cross-repo/inbox/.hidden.md'),
      '[0-9]* must not match .hidden.md'
    );
  });

  it('mid-segment * still matches across a dot inside a filename (dot not at segment start)', () => {
    assert.ok(
      _matchGlob('docs/plans/*.md', 'docs/plans/foo.bar.md'),
      '*.md must match foo.bar.md (dot mid-name, not at segment start)'
    );
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

// parseYaml — PUBLIC export used by whole-document-yaml mode in
// validate-frontmatter-schema.js. Guards that the export name is callable and
// produces the same result as the internal parser / parseYamlBlock alias.
describe('parseYaml (public export for whole-document-yaml consumers)', () => {
  it('is exported as a callable function', () => {
    assert.equal(typeof parseYaml, 'function');
  });

  it('parses a bare-YAML queue entry the same as _parseYaml', () => {
    const entry = [
      'created: 2026-07-01',
      'title: "Test entry"',
      'status: open',
    ].join('\n');
    assert.deepEqual(parseYaml(entry), _parseYaml(entry));
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
// parseScalar #-truncation fix (the Data Science Reviewer C-F6 / the Staff Engineer F5)
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
    // ccos-1 W4d: loe.tshirt is now anyOf[enum, null] (null-tolerant for legacy
    // all-null Phase-1 entries), so a bad value reports the anyOf message rather
    // than the dialect's "invalid enum value". Intent preserved: rejected + allowed
    // values surfaced in the hint.
    assert.match(result.errors[0].error, /does not match any allowed schema/);
    assert.match(result.errors[0].hint, /XS\/S\/M\/L\/XL/);
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
    // ccos-1 W4d: chain_loe.tshirt is anyOf[enum, null] (see loe.tshirt note above).
    assert.match(badResult.errors[0].error, /does not match any allowed schema/);
    assert.match(badResult.errors[0].hint, /XS\/S\/M\/L\/XL/);
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
      'docs/plans/2026-06-23-my-plan.the Director of Engineering-review.md',
      { kind: 'review-sidecar' },
      SCHEMAS
    );
    assert.ok(result !== null, 'expected a match');
    assert.equal(result.schemaName, 'review-sidecar',
      `expected review-sidecar, got ${result && result.schemaName}`);
  });

  it('kind-wins-over-glob: staff-eng-review kind also resolves to review-sidecar schema', () => {
    const result = matchSchema(
      'docs/plans/2026-06-23-my-plan.the Staff Engineer-review.md',
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
    const globMatch = matchSchemaForPath('docs/plans/2026-06-23-my-plan.the Director of Engineering-review.md', SCHEMAS);
    // The glob still matches plan (unchanged path-only resolution)
    assert.ok(globMatch !== null, 'glob should still match plan by path');
    assert.equal(globMatch.schemaName, 'plan', 'glob alone resolves to plan');

    // But matchSchema with kind: review-sidecar overrides to the correct schema
    const kindMatch = matchSchema(
      'docs/plans/2026-06-23-my-plan.the Director of Engineering-review.md',
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
  // review-sidecar(3), the Staff Engineer-review(3), substrate-adjudication(1), plan-rereview(1).
  // Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 2

  const LEGACY_REVIEW_KINDS = [
    'the Staff Engineer-review',
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
      'docs/plans/2026-06-23-my-plan.the Staff Engineer-review.md',
      { kind: 'staff-eng-review' },
      SCHEMAS
    );
    assert.ok(result !== null, 'staff-eng-review should match');
    assert.equal(result.schemaName, 'review-sidecar',
      `staff-eng-review must resolve to review-sidecar, got ${result && result.schemaName}`);
  });

  it('role-based canonical kind "eng-director-review" resolves to review-sidecar schema', () => {
    const result = matchSchema(
      'docs/plans/2026-06-23-my-plan.the Director of Engineering-review.md',
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

// ---------------------------------------------------------------------------
// validateRecord — JSON Schema subset validator (W1 ccos-1 dual-context entry)
// Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1
// ---------------------------------------------------------------------------

describe('validateRecord — inline JSON Schema object (shape validation)', () => {
  // A minimal inline schema used across sub-tests.
  const minimalSchema = {
    'x-schema-name': null,  // no cross-field rules for this schema
    'type': 'object',
    'required': ['name', 'version'],
    'properties': {
      'name': { 'type': 'string' },
      'version': { 'type': 'integer' },
      'notes': { 'anyOf': [{ 'type': 'string' }, { 'type': 'null' }] }
    }
  };

  it('valid record passes', () => {
    const record = { name: 'test', version: 1, notes: 'ok' };
    const result = validateRecord(record, minimalSchema);
    assert.ok(result.ok, `Expected ok, got errors: ${JSON.stringify(result.errors)}`);
  });

  it('null notes passes (anyOf nullable)', () => {
    const record = { name: 'test', version: 1, notes: null };
    const result = validateRecord(record, minimalSchema);
    assert.ok(result.ok, `Null value for anyOf nullable field should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('missing required field fails', () => {
    const record = { name: 'test' };  // version missing
    const result = validateRecord(record, minimalSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'version');
    assert.ok(err, `Expected version error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required field missing/);
  });

  it('wrong type for field fails', () => {
    const record = { name: 42, version: 1 };  // name should be string
    const result = validateRecord(record, minimalSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'name');
    assert.ok(err, `Expected name type error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /expected string, got number/);
  });

  it('notes with wrong type (not string or null) fails anyOf', () => {
    const record = { name: 'test', version: 1, notes: 42 };
    const result = validateRecord(record, minimalSchema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'notes');
    assert.ok(err, `Expected notes anyOf error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not match any allowed schema/);
  });
});

describe('validateRecord — enum, format, additionalProperties, $defs/$ref', () => {
  it('enum validation rejects unlisted value', () => {
    const schema = {
      'type': 'object',
      'required': ['status'],
      'properties': {
        'status': { 'enum': ['active', 'consumed'] }
      }
    };
    const result = validateRecord({ status: 'invalid' }, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'status');
    assert.ok(err, `Expected status enum error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /invalid enum value "invalid"/);
  });

  it('enum validation accepts listed value', () => {
    const schema = {
      'type': 'object',
      'required': ['status'],
      'properties': {
        'status': { 'enum': ['active', 'consumed'] }
      }
    };
    const result = validateRecord({ status: 'active' }, schema);
    assert.ok(result.ok, `Expected ok, got: ${JSON.stringify(result.errors)}`);
  });

  it('format: date rejects non-ISO date', () => {
    const schema = {
      'type': 'object',
      'properties': {
        'created': { 'type': 'string', 'format': 'date' }
      }
    };
    const result = validateRecord({ created: '01-05-2026' }, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'created');
    assert.ok(err, `Expected date format error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /invalid date format/);
  });

  it('format: date accepts valid ISO date', () => {
    const schema = {
      'type': 'object',
      'properties': {
        'created': { 'type': 'string', 'format': 'date' }
      }
    };
    const result = validateRecord({ created: '2026-06-27' }, schema);
    assert.ok(result.ok, `Expected ok, got: ${JSON.stringify(result.errors)}`);
  });

  it('additionalProperties: false rejects undeclared key', () => {
    const schema = {
      'type': 'object',
      'properties': {
        'name': { 'type': 'string' }
      },
      'additionalProperties': false
    };
    const result = validateRecord({ name: 'test', extra: 'surprise' }, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'extra');
    assert.ok(err, `Expected extra field error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /additional property "extra" not allowed/);
  });

  it('in-file $ref via $defs resolves correctly', () => {
    const schema = {
      'type': 'object',
      'required': ['item'],
      'properties': {
        'item': { '$ref': '#/$defs/Item' }
      },
      '$defs': {
        'Item': { 'type': 'string' }
      }
    };
    // String value — should pass
    const passResult = validateRecord({ item: 'hello' }, schema);
    assert.ok(passResult.ok, `In-file $ref: expected ok, got: ${JSON.stringify(passResult.errors)}`);

    // Number value — should fail
    const failResult = validateRecord({ item: 42 }, schema);
    assert.equal(failResult.ok, false);
    const err = failResult.errors.find(e => e.field === 'item');
    assert.ok(err, `In-file $ref: expected item type error, got: ${JSON.stringify(failResult.errors)}`);
    assert.match(err.error, /expected string, got number/);
  });

  it('cross-file $ref throws fail-loud error', () => {
    const schema = {
      'type': 'object',
      'properties': {
        'data': { '$ref': './other.schema.json#/definitions/Data' }
      }
    };
    assert.throws(
      () => validateRecord({ data: 'value' }, schema),
      (err) => {
        return err instanceof Error && /cross-file \$ref|not supported/.test(err.message);
      },
      'Cross-file $ref must throw fail-loud error'
    );
  });

  it('pattern: string value matching the regex PASSES', () => {
    const schema = {
      'type': 'object',
      'properties': {
        'code': { 'type': 'string', 'pattern': '^[A-Z]{3}-\\d{4}$' }
      }
    };
    const result = validateRecord({ code: 'ABC-1234' }, schema);
    assert.ok(result.ok, `Expected ok, got: ${JSON.stringify(result.errors)}`);
  });

  it('pattern: string value NOT matching the regex is REJECTED', () => {
    const schema = {
      'type': 'object',
      'properties': {
        'code': { 'type': 'string', 'pattern': '^[A-Z]{3}-\\d{4}$' }
      }
    };
    const result = validateRecord({ code: 'abc-12' }, schema);
    assert.equal(result.ok, false);
    const err = result.errors.find(e => e.field === 'code');
    assert.ok(err, `Expected code pattern error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not match required pattern/);
  });

  it('pattern: non-string value is unaffected (pattern only applies to strings)', () => {
    const schema = {
      'type': 'object',
      'properties': {
        'count': { 'pattern': '^[A-Z]{3}-\\d{4}$' }
      }
    };
    const result = validateRecord({ count: 42 }, schema);
    assert.ok(result.ok, `Non-string value should be unaffected by pattern, got: ${JSON.stringify(result.errors)}`);
  });
});

describe('validateRecord — hybrid: shape + cross-field rules', () => {
  // Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 3
  // Proves that validateRecord applies BOTH the JSON Schema shape subset AND CROSS_FIELD_RULES.

  // Minimal handoff JSON Schema with x-schema-name: 'handoff' to trigger the handoff
  // cross-field rules. Shape-only validation would not catch the cross-field violation.
  const handoffJsonSchema = {
    'x-schema-name': 'handoff',
    'type': 'object',
    'required': ['title', 'created', 'branch', 'status', 'predecessor'],
    'properties': {
      'title': { 'type': 'string' },
      'created': { 'type': 'string', 'format': 'date' },
      'branch': { 'type': 'string' },
      'status': { 'type': 'string' },
      'predecessor': { 'anyOf': [{ 'type': 'string' }, { 'type': 'null' }] },
      'deployment_state': { 'type': 'string' },
      'gate_dependency': { 'anyOf': [{ 'type': 'string' }, { 'type': 'null' }] },
      'category': { 'type': 'string' },
      'summary': { 'type': 'string' }
    }
  };

  it('shape-clean record with cross-field violation (awaiting_gate + no gate_dependency) FAILS', () => {
    const record = {
      title: 'W1 test handoff',
      created: '2026-06-27',
      branch: 'work/test/2026-06-27',
      status: 'active',
      predecessor: null,
      deployment_state: 'awaiting_gate',
      // gate_dependency intentionally absent — should fire cross-field rule H-CROSS-1
    };

    const result = validateRecord(record, handoffJsonSchema);
    assert.equal(result.ok, false, 'Cross-field violation should make the record fail');
    const crossErr = result.errors.find(e => e.field === 'gate_dependency');
    assert.ok(crossErr, `Expected gate_dependency cross-field error, got: ${JSON.stringify(result.errors)}`);
    assert.match(crossErr.error, /required when deployment_state=awaiting_gate/,
      'Error must come from the handoff cross-field rule, not the shape validator');
  });

  it('shape-clean record with no cross-field violations PASSES', () => {
    const record = {
      title: 'W1 test handoff',
      created: '2026-05-01',
      branch: 'work/test/2026-05-01',
      status: 'active',
      predecessor: null,
      // No deployment_state or cross-field-triggering fields
    };
    const result = validateRecord(record, handoffJsonSchema);
    assert.ok(result.ok, `Shape-clean record with no cross-field issues should pass: ${JSON.stringify(result.errors)}`);
  });

  it('shape violation AND cross-field violation both appear in errors', () => {
    const record = {
      title: 42,   // wrong type — shape violation
      created: '2026-06-27',
      branch: 'work/test/2026-06-27',
      status: 'active',
      predecessor: null,
      deployment_state: 'awaiting_gate',
      // gate_dependency absent — cross-field violation
    };
    const result = validateRecord(record, handoffJsonSchema);
    assert.equal(result.ok, false);
    const shapeErr = result.errors.find(e => e.field === 'title');
    const crossErr = result.errors.find(e => e.field === 'gate_dependency');
    assert.ok(shapeErr, `Expected shape error on title, got: ${JSON.stringify(result.errors)}`);
    assert.ok(crossErr, `Expected cross-field error on gate_dependency, got: ${JSON.stringify(result.errors)}`);
  });
});

describe('validateRecord — dual-context (producer and consumer agree)', () => {
  // Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 7
  // Proves that producer (string-name path, cache-backed) and consumer (inline schema object)
  // both call validateRecord against the SAME .schema.json fixture and produce identical verdicts.

  it('string-name path and inline-object path agree on valid and invalid records', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ccos1-dc-test-'));
    try {
      const schema = {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        'x-schema-name': 'ccos1-dc-test-record',
        'type': 'object',
        'required': ['name', 'version'],
        'properties': {
          'name': { 'type': 'string' },
          'version': { 'type': 'integer' },
          'label': { 'anyOf': [{ 'type': 'string' }, { 'type': 'null' }] }
        }
      };
      const schemaPath = path.join(tmpDir, 'ccos1-dc-test-record.schema.json');
      fs.writeFileSync(schemaPath, JSON.stringify(schema), 'utf8');

      // Populate the module-level JSON schema cache (string-name path).
      loadSchemas(tmpDir);

      // Valid record — both paths must agree: ok:true.
      const validRecord = { name: 'coordinator', version: 1, label: null };
      const producerResult = validateRecord(validRecord, 'ccos1-dc-test-record');
      const consumerResult = validateRecord(validRecord, schema);
      assert.ok(producerResult.ok, `Producer (string-name) should accept valid record: ${JSON.stringify(producerResult.errors)}`);
      assert.ok(consumerResult.ok, `Consumer (inline) should accept valid record: ${JSON.stringify(consumerResult.errors)}`);
      assert.equal(producerResult.ok, consumerResult.ok, 'Producer and consumer must agree on valid record');

      // Invalid record (missing required field) — both must agree: ok:false.
      const invalidRecord = { name: 'coordinator' };  // version missing
      const producerReject = validateRecord(invalidRecord, 'ccos1-dc-test-record');
      const consumerReject = validateRecord(invalidRecord, schema);
      assert.equal(producerReject.ok, false, 'Producer should reject record missing required field');
      assert.equal(consumerReject.ok, false, 'Consumer should reject record missing required field');
      assert.equal(producerReject.ok, consumerReject.ok, 'Producer and consumer must agree on invalid record');

      // Both report the same missing field.
      const pErr = producerReject.errors.find(e => e.field === 'version');
      const cErr = consumerReject.errors.find(e => e.field === 'version');
      assert.ok(pErr, `Producer: expected version error, got: ${JSON.stringify(producerReject.errors)}`);
      assert.ok(cErr, `Consumer: expected version error, got: ${JSON.stringify(consumerReject.errors)}`);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('unknown schema name returns error (not found in cache)', () => {
    const result = validateRecord({ name: 'test' }, 'nonexistent-schema-xyz-9999');
    assert.equal(result.ok, false, 'Unknown schema name should fail');
    const err = result.errors.find(e => e.field === '(schema)');
    assert.ok(err, `Expected (schema) error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /not found in cache/);
  });
});

describe('testNegativeCorpus — AC5b oracle (negative regression sweep)', () => {
  // Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 6
  // Runs the full negative-corpus regression sweep and asserts 30/30 pass.

  it('all 30 negative fixtures are correctly rejected by the rebuilt validator', () => {
    const fixturesDir = path.resolve(__dirname, '../tests/fixtures/validator-negative');
    const schemasDir = path.resolve(__dirname, '../../schemas');
    const { passed, failed, total, results } = testNegativeCorpus(fixturesDir, schemasDir);

    // Report any failures for easy diagnosis.
    for (const r of results) {
      if (!r.pass) {
        process.stderr.write(
          `CORPUS-FAIL: ${r.fixture} — expected ok:${r.expected_ok}, got ok:${r.result_ok}\n` +
          `  errors: ${JSON.stringify(r.errors)}\n`
        );
      }
    }

    assert.equal(total, 30, `Expected 30 fixtures in index, found ${total}`);
    assert.equal(failed, 0,
      `${failed} fixture(s) not rejected as expected — see CORPUS-FAIL lines above`);
    assert.equal(passed, 30, `Expected 30/30 pass, got ${passed}/30`);
  });
});

describe('loadSchemas — applies_to non-string fails loud (W1 fix)', () => {
  // Spec backlink: improvement-queue 2026-06-27-coordinator-schema-js-loadschemas-does-n
  // Previously: an array applies_to was pushed directly to _byGlob, causing
  // `pattern.replace is not a function` deep in globToRegex at match time.
  // Now: throws at load time with a clear error naming the schema.

  it('loadSchemas throws on array applies_to (fail-loud at load time)', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'schema-test-array-applies-'));
    try {
      // Write a schema with applies_to as an inline YAML list.
      // The YAML parser will parse "[a, b]" as an array.
      const schemaYaml = [
        'schema: bad-schema',
        'applies_to: [docs/foo/*.md, docs/bar/*.md]',
        'required:',
        '  title: string',
      ].join('\n') + '\n';
      fs.writeFileSync(path.join(tmpDir, 'bad-schema.yaml'), schemaYaml, 'utf8');

      assert.throws(
        () => loadSchemas(tmpDir),
        (err) => {
          return err instanceof Error &&
            /applies_to must be a string/.test(err.message) &&
            /bad-schema/.test(err.message);
        },
        'loadSchemas must throw on array applies_to with a clear error naming the schema'
      );
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('loadSchemas does NOT throw when applies_to is a valid string glob', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'schema-test-good-applies-'));
    try {
      const schemaYaml = [
        'schema: good-schema',
        'applies_to: "docs/foo/*.md"',
        'required:',
        '  title: string',
      ].join('\n') + '\n';
      fs.writeFileSync(path.join(tmpDir, 'good-schema.yaml'), schemaYaml, 'utf8');

      let schemas;
      assert.doesNotThrow(() => {
        schemas = loadSchemas(tmpDir);
      }, 'loadSchemas must not throw on valid string applies_to');
      assert.ok(schemas['good-schema'], 'good-schema should be loaded');
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});

describe('loadSchemas — dual-format loader (.yaml + .schema.json)', () => {
  // Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 4
  // Verifies that loadSchemas reads BOTH .yaml and .schema.json files from the same directory.

  it('loads a .schema.json file alongside .yaml files', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'schema-test-dual-'));
    try {
      // Write a YAML schema
      const yamlSchema = [
        'schema: yaml-record',
        'applies_to: "state/yaml-records/*.md"',
        'required:',
        '  title: string',
      ].join('\n') + '\n';
      fs.writeFileSync(path.join(tmpDir, 'yaml-record.yaml'), yamlSchema, 'utf8');

      // Write a JSON Schema
      const jsonSchema = {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        'x-schema-name': 'json-record',
        'type': 'object',
        'required': ['id'],
        'properties': { 'id': { 'type': 'string' } }
      };
      fs.writeFileSync(
        path.join(tmpDir, 'json-record.schema.json'),
        JSON.stringify(jsonSchema),
        'utf8'
      );

      const schemas = loadSchemas(tmpDir);

      assert.ok(schemas['yaml-record'], 'yaml-record schema must be loaded');
      assert.ok(schemas['json-record'], 'json-record schema must be loaded from .schema.json');
      assert.ok(schemas['json-record']['x-schema-name'], 'json-record must retain its x-schema-name property');
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('x-schema-name in .schema.json overrides filename stem as the schema name', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'schema-test-name-'));
    try {
      const jsonSchema = {
        'x-schema-name': 'canonical-name',
        'type': 'object'
      };
      fs.writeFileSync(
        path.join(tmpDir, 'filename-stem.schema.json'),
        JSON.stringify(jsonSchema),
        'utf8'
      );

      const schemas = loadSchemas(tmpDir);
      assert.ok(schemas['canonical-name'], 'x-schema-name must take precedence over filename stem');
      assert.equal(schemas['filename-stem'], undefined, 'filename stem must NOT be used as the key when x-schema-name is present');
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});

// ---------------------------------------------------------------------------
// validateRecord — schema-version gate (W2 ccos-1)
// Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2
// Convention doc: docs/wiki/schema-version-gate.md
//
// Gate semantics:
//   warn-on-newer-read  (mode='read', default): record.schema_version major >
//     schema.x-schema-version major → ok:true + result.warnings entry.
//   refuse-on-newer-write (mode='write'): same condition → ok:false + result.errors entry.
//   missing version on either side → no-op (backward-compatible).
//   equal version or same major → no gate (passes cleanly).
//   schema major > record major → no gate (schema is already ahead, expected in reader-first ordering).
// ---------------------------------------------------------------------------

describe('validateRecord — schema-version gate (W2)', () => {
  // Helper: minimal valid JSON Schema with an optional x-schema-version.
  function makeVersionedSchema(xSchemaVersion) {
    const s = {
      'type': 'object',
      'required': ['name'],
      'properties': { 'name': { 'type': 'string' } }
    };
    if (xSchemaVersion !== undefined) s['x-schema-version'] = xSchemaVersion;
    return s;
  }

  // (a) newer-read warns (not fails)
  it('warn-on-newer-read: record major > schema major in read mode → ok:true + warning', () => {
    const schema = makeVersionedSchema('1.0.0');
    const record = { name: 'test', schema_version: '2.0.0' };
    const result = validateRecord(record, schema, { mode: 'read' });
    assert.ok(result.ok,
      `Expected ok:true (warn-on-newer-read must not fail), got errors: ${JSON.stringify(result.errors)}`);
    assert.ok(Array.isArray(result.warnings) && result.warnings.length > 0,
      `Expected at least one warning, got: ${JSON.stringify(result.warnings)}`);
    const w = result.warnings.find(w => w.field === 'schema_version');
    assert.ok(w, `Expected schema_version warning entry, got: ${JSON.stringify(result.warnings)}`);
    assert.match(w.error, /major.*exceeds|exceeds.*major/,
      'Warning message must name the major-version mismatch');
  });

  // (b) newer-write refuses
  it('refuse-on-newer-write: record major > schema major in write mode → ok:false + error', () => {
    const schema = makeVersionedSchema('1.0.0');
    const record = { name: 'test', schema_version: '2.0.0' };
    const result = validateRecord(record, schema, { mode: 'write' });
    assert.equal(result.ok, false,
      'refuse-on-newer-write must fail (ok:false) when record major exceeds schema major');
    assert.ok(Array.isArray(result.errors) && result.errors.length > 0,
      `Expected at least one error, got: ${JSON.stringify(result.errors)}`);
    const e = result.errors.find(e => e.field === 'schema_version');
    assert.ok(e, `Expected schema_version error entry, got: ${JSON.stringify(result.errors)}`);
    assert.match(e.hint, /refuse-on-newer-write/,
      'Error hint must name refuse-on-newer-write so the fix is clear');
  });

  // (c) missing-version is a no-op
  it('missing x-schema-version in schema: no gate fires → ok:true, no warnings', () => {
    const schema = makeVersionedSchema(undefined);  // no x-schema-version
    const record = { name: 'test', schema_version: '2.0.0' };
    const result = validateRecord(record, schema, { mode: 'read' });
    assert.ok(result.ok,
      `Expected ok:true (no schema version → gate is opt-in), got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [],
      'Expected no warnings when schema lacks x-schema-version');
  });

  it('missing schema_version in record: no gate fires → ok:true, no warnings', () => {
    const schema = makeVersionedSchema('1.0.0');
    const record = { name: 'test' };  // no schema_version field
    const result = validateRecord(record, schema, { mode: 'read' });
    assert.ok(result.ok,
      `Expected ok:true (no record version → gate is opt-in), got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [],
      'Expected no warnings when record lacks schema_version');
  });

  // (d) equal-version passes
  it('equal version (same major.minor.patch): ok:true, no warnings', () => {
    const schema = makeVersionedSchema('1.2.3');
    const record = { name: 'test', schema_version: '1.2.3' };
    const result = validateRecord(record, schema, { mode: 'read' });
    assert.ok(result.ok,
      `Expected ok:true for equal version, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [],
      'Expected no warnings for equal version');
  });

  // (e) same major, higher minor/patch: gate does NOT fire (minor/patch is backward-compat)
  it('same major, higher minor in record: no gate (minor-patch change is backward-compatible)', () => {
    const schema = makeVersionedSchema('1.0.0');
    const record = { name: 'test', schema_version: '1.5.2' };
    const result = validateRecord(record, schema, { mode: 'read' });
    assert.ok(result.ok,
      `Expected ok:true for same-major minor bump, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [],
      'Expected no warnings for same-major version where only minor/patch differs');
  });

  // (f) schema major NEWER than record major: no gate (reader-first: consumer already widened)
  it('schema has higher major than record: no gate (schema is ahead, reader-first ordering)', () => {
    const schema = makeVersionedSchema('2.0.0');
    const record = { name: 'test', schema_version: '1.0.0' };
    const result = validateRecord(record, schema, { mode: 'read' });
    assert.ok(result.ok,
      `Expected ok:true when schema is newer than record, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [],
      'Expected no warnings when schema major is ahead of record major');
  });

  // (g) default mode (no options arg) behaves as 'read': newer record warns but does not fail
  it('default mode (no options arg) is read: newer record → ok:true + warning', () => {
    const schema = makeVersionedSchema('1.0.0');
    const record = { name: 'test', schema_version: '3.0.0' };
    const result = validateRecord(record, schema);  // no options — defaults to mode='read'
    assert.ok(result.ok,
      `Expected ok:true in default (read) mode, got errors: ${JSON.stringify(result.errors)}`);
    assert.ok(Array.isArray(result.warnings) && result.warnings.length > 0,
      'Expected a warning in default (read) mode when record major exceeds schema major');
  });

  // (h) result.warnings is always present (empty array) even when no gate fires
  it('result.warnings is always an array even when the gate does not fire', () => {
    const schema = makeVersionedSchema('1.0.0');
    const record = { name: 'test' };  // no schema_version
    const result = validateRecord(record, schema);
    assert.ok(Array.isArray(result.warnings),
      'result.warnings must always be an array (present even when empty)');
  });

  // (i) write-mode refuse fires before shape/cross-field: version error is the only error
  it('refuse-on-newer-write returns only the version error (shape/cross-field not run)', () => {
    const schema = makeVersionedSchema('1.0.0');
    // Record is also shape-invalid (name is a number) AND missing required field —
    // but in write mode the version gate fires first and returns immediately.
    const record = { name: 42, schema_version: '2.0.0' };  // name is wrong type too
    const result = validateRecord(record, schema, { mode: 'write' });
    assert.equal(result.ok, false);
    // Only the version error — not the name-type error
    assert.equal(result.errors.length, 1,
      `Expected exactly 1 error (version gate only), got: ${JSON.stringify(result.errors)}`);
    assert.equal(result.errors[0].field, 'schema_version',
      'The sole error must be the schema_version version-gate error');
  });
});

// ---------------------------------------------------------------------------
// W2.5 pilot migration — docs-check-sidecar .schema.json
//
// Proves that a .schema.json schema:
//   (a) has applies_to registered in _byGlob so matchSchemaForPath resolves it,
//   (b) is tagged with _isJsonSchema so the dispatch can route correctly,
//   (c) validates via the JSON path (validateFrontmatterDispatch → validateRecord),
//       not the .yaml-dialect path (validateFrontmatter).
//
// Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2.5
// ---------------------------------------------------------------------------

describe('W2.5 pilot: docs-check-sidecar .schema.json — path routing + JSON validation', () => {
  // matchSchemaForPath must resolve the docs/plans/*.docs-check.md glob to the
  // docs-check-sidecar schema now that it is JSON-Schema-backed.
  it('matchSchemaForPath routes docs/plans/*.docs-check.md to docs-check-sidecar (JSON Schema-backed)', () => {
    const match = matchSchemaForPath('docs/plans/2026-06-27-foo.docs-check.md', SCHEMAS);
    assert.ok(match !== null, 'expected a match for docs/plans/*.docs-check.md path');
    assert.equal(match.schemaName, 'docs-check-sidecar',
      `expected docs-check-sidecar, got ${match && match.schemaName}`);
    // The schema object must carry the JSON-Schema-backed marker.
    assert.ok(_isJsonSchemaBacked(match.schema),
      'docs-check-sidecar schema must be flagged as JSON-Schema-backed by loadSchemas');
  });

  // validateFrontmatterDispatch must route to the JSON path (not YAML-dialect)
  // and accept a well-formed docs-check-sidecar record.
  it('valid record with artifact passes via JSON path (validateFrontmatterDispatch)', () => {
    const match = matchSchemaForPath('docs/plans/2026-06-27-foo.docs-check.md', SCHEMAS);
    assert.ok(match, 'precondition: schema must resolve');
    const fm = {
      artifact: 'docs/plans/2026-06-27-ccos-1-dual-context-validator.md',
      checker: 'docs-checker',
      claims_checked: 8,
      verified: 7,
      unverified: 1,
      incorrect: 0,
      auto_fixed: 0,
      status: 'reviewed',
      created: '2026-06-27',
    };
    const result = validateFrontmatterDispatch(fm, match.schema);
    assert.ok(result.ok, `Expected ok for valid docs-check-sidecar record, got: ${JSON.stringify(result.errors)}`);
  });

  // The required field artifact must be enforced via the JSON path.
  it('docs-check-sidecar record WITHOUT artifact FAILS (required field via JSON path)', () => {
    const match = matchSchemaForPath('docs/plans/2026-06-27-foo.docs-check.md', SCHEMAS);
    assert.ok(match, 'precondition: schema must resolve');
    const fm = { checker: 'docs-checker', claims_checked: 5, verified: 4 }; // artifact absent
    const result = validateFrontmatterDispatch(fm, match.schema);
    assert.equal(result.ok, false, 'record without required artifact must fail via JSON path');
    const err = result.errors && result.errors.find(e => e.field === 'artifact' || /artifact/.test(e.field));
    assert.ok(err, `Expected artifact required-field error, got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /required field missing/);
  });

  // YAML-dialect schemas must NOT be mistakenly flagged as JSON-Schema-backed.
  // Regression guard: _isJsonSchemaBacked must return false for .yaml schemas.
  it('_isJsonSchemaBacked returns false for a .yaml-dialect schema (review-trail)', () => {
    // review-trail is a ccos-1 kept-.yaml exception (validates .json records, not
    // markdown frontmatter) — a stable example of a .yaml-dialect schema. (handoff
    // was migrated to .schema.json in ccos-1 W4d, so it is no longer a .yaml example.)
    const yamlSchema = SCHEMAS['review-trail'];
    assert.ok(yamlSchema, 'precondition: review-trail schema must be loaded');
    assert.equal(_isJsonSchemaBacked(yamlSchema), false,
      'review-trail (.yaml) schema must NOT be flagged as JSON-Schema-backed');
  });

  // Review: code-reviewer (A-F7) — handoff is now JSON-backed (.schema.json in ccos-1 W4d);
  // using it to test the YAML-dialect path was exercising the wrong code path.
  // Switch to review-trail which is a kept-.yaml schema (validates .json records, YAML dialect).
  it('validateFrontmatterDispatch falls through to YAML-dialect path for .yaml schemas (review-trail)', () => {
    const reviewTrailSchema = SCHEMAS['review-trail'];
    assert.ok(reviewTrailSchema, 'precondition: review-trail schema must be loaded');
    assert.equal(_isJsonSchemaBacked(reviewTrailSchema), false,
      'precondition: review-trail must be a .yaml-dialect schema');
    // A valid review-trail record — must pass through the YAML path unchanged.
    // workstream is string-or-null in the YAML schema; use a string value to stay
    // within the well-tested path (null handling is covered by separate type tests).
    const fm = {
      sha_range: 'abc123..def456',
      reviewer: 'code-reviewer',
      scope: 'bin/lib/schema.js',
      scope_kind: 'file',
      verdict: 'WARN',
      diff_loc: 42,
      session_id: 'test-session-1',
      workstream: 'ccos-1',
    };
    const result = validateFrontmatterDispatch(fm, reviewTrailSchema);
    assert.ok(result.ok, `YAML-dialect dispatch via review-trail: expected ok, got: ${JSON.stringify(result.errors)}`);
  });

  // Review: code-reviewer (A-F7) — add assertion that handoff (now JSON-backed) routes to the JSON path.
  it('validateFrontmatterDispatch routes handoff (.schema.json-backed) to JSON-Schema path', () => {
    const handoffSchema = SCHEMAS['handoff'];
    assert.ok(handoffSchema, 'precondition: handoff schema must be loaded');
    assert.equal(_isJsonSchemaBacked(handoffSchema), true,
      'precondition: handoff must be JSON-Schema-backed after ccos-1 W4d migration');
    // A valid handoff record — must validate via the JSON-Schema path.
    const fm = {
      title: 'Test handoff',
      created: '2026-05-01',
      branch: 'work/test/2026-05-01',
      status: 'active',
      predecessor: null,
    };
    const result = validateFrontmatterDispatch(fm, handoffSchema);
    assert.ok(result.ok, `JSON-Schema dispatch via handoff: expected ok, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// Review: code-reviewer (A-F9/F16) — forward-safety regression tests
// ---------------------------------------------------------------------------

describe('validateRecord — invalid schemaOrName arg type (A-F9)', () => {
  // validateRecord must reject non-string, non-object schemaOrName values explicitly.
  // A number (or boolean/array) passed as schemaOrName should return {ok: false} with
  // a clear error, not throw or confabulate a false-positive.
  it('number schemaOrName returns ok:false with clear error (not throw)', () => {
    const result = validateRecord({ field: 'value' }, 42);
    assert.equal(result.ok, false, 'expected ok:false for number schemaOrName');
    assert.ok(Array.isArray(result.errors) && result.errors.length > 0,
      'expected non-empty errors array');
    const err = result.errors[0];
    assert.match(err.error, /schemaOrName must be/,
      `expected error naming the arg constraint, got: ${err.error}`);
  });

  it('boolean schemaOrName returns ok:false with clear error (not throw)', () => {
    const result = validateRecord({ field: 'value' }, true);
    assert.equal(result.ok, false, 'expected ok:false for boolean schemaOrName');
    assert.ok(Array.isArray(result.errors) && result.errors.length > 0,
      'expected non-empty errors array');
  });
  // Note: typeof [] === 'object' in JS, so arrays fall into the object-schema branch
  // and are treated as an (empty) schema — not covered by the schemaOrName guard.
  // The guard covers number, boolean, and other non-string/non-object primitives.
});

describe('validateJsonSchemaNode — anyOf + required sibling validation (A-F16 / regression net for A-F1)', () => {
  // Regression net: a schema node with BOTH anyOf AND required on the same node must
  // validate BOTH constraints. Before A-F1 fix, anyOf matched → early-return skipped required.
  it('anyOf matches AND required fields present → ok (no errors)', () => {
    // Schema: value must match anyOf [{type: string},{type: null}] AND have required keys.
    // Record: valid string value with required key present.
    const schema = {
      '$schema': 'https://json-schema.org/draft/2020-12/schema',
      'x-schema-name': 'test-anyof-required',
      'type': 'object',
      'anyOf': [{ 'type': 'object' }],
      'required': ['name'],
      'properties': {
        'name': { 'type': 'string' }
      }
    };
    const record = { name: 'alice' };
    const result = validateRecord(record, schema);
    assert.ok(result.ok, `expected ok:true when anyOf matches and required satisfied, got: ${JSON.stringify(result.errors)}`);
  });

  it('anyOf matches BUT required field absent → errors (sibling required must fire)', () => {
    // This is the regression case: before A-F1, anyOf match caused early-return,
    // and the required check for "name" was silently skipped → false-ok.
    const schema = {
      '$schema': 'https://json-schema.org/draft/2020-12/schema',
      'x-schema-name': 'test-anyof-required-miss',
      'type': 'object',
      'anyOf': [{ 'type': 'object' }],
      'required': ['name'],
      'properties': {
        'name': { 'type': 'string' }
      }
    };
    const record = { other_field: 'value' }; // name is absent
    const result = validateRecord(record, schema);
    assert.equal(result.ok, false,
      'expected ok:false when anyOf matches but required field "name" is absent (A-F1 regression guard)');
    const nameErr = result.errors && result.errors.find(e => /name/.test(e.field));
    assert.ok(nameErr,
      `expected a required-field error for "name", got: ${JSON.stringify(result.errors)}`);
    assert.match(nameErr.error, /required field missing/);
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

// ---------------------------------------------------------------------------
// Parser correctness — drift fixture golden assertions (C1 dual-yaml-parser option-d)
//
// These were migrated from schema-differential.test.js as SINGLE-PARSER golden
// assertions against schema.js's corrected behavior. The drift cases (previously
// expected-red) are now expected-green after the four drift fixes.
//
// Spec backlink: docs/plans/2026-06-27-watchdog-timeout-portability-primitive.md
// Fixes applied: drift-1 (parseInlineList fail-loud), drift-2 (parseScalar single-quote escape),
//                drift-3 (parseYamlLines blank-line-before-nested-block), drift-5 (isStringOrNull bare-string spec).
// ---------------------------------------------------------------------------

describe('parser correctness — drift-1: parseInlineList', () => {
  // (a) Empty inline list [] → [] (must NOT throw).
  // blocks:/blocked_by:[] are pervasive in roadmap handoffs.
  it('(a) empty inline list [] parses to []', () => {
    const result = _parseYaml('blocks: []\n');
    assert.deepEqual(result.blocks, [], 'empty inline list must parse to []');
  });

  // (b) Populated inline list [a, b] → ['a', 'b'].
  it('(b) populated inline list [a, b] → [\'a\', \'b\']', () => {
    const result = _parseYaml('tags: [a, b]\n');
    assert.deepEqual(result.tags, ['a', 'b'], 'populated inline list must parse correctly');
  });

  // (c) Malformed inline list [a, , c] → throws (empty gap between commas).
  // Mirrors schema_loader.py A-F4: fail loud on null/empty items from trailing-comma gaps.
  it('(c) malformed inline list [a, , c] throws (empty gap)', () => {
    assert.throws(
      () => _parseYaml('tags: [a, , c]\n'),
      (err) => err instanceof Error && /malformed inline list/i.test(err.message),
      'malformed inline list with gap must throw'
    );
  });

  // Guard: trailing-comma malformed [a, b, ] also throws (trailing gap).
  it('(c2) malformed inline list [a, b, ] throws (trailing comma)', () => {
    assert.throws(
      () => _parseYaml('tags: [a, b, ]\n'),
      (err) => err instanceof Error && /malformed inline list/i.test(err.message),
      'trailing-comma inline list must throw'
    );
  });
});

describe('parser correctness — drift-2: parseScalar single-quote escape', () => {
  // (d) Single-quote escape 'it''s' → it's.
  // Mirrors schema_loader.py _parse_scalar `inner.replace("''", "'")`.
  it("(d) 'it''s' → \"it's\" (YAML single-quote escape ''→')", () => {
    const result = _parseYaml("title: 'it''s here'\n");
    assert.equal(result.title, "it's here", "single-quote escape '' must unescape to '");
  });

  // Guard: double-quoted strings are unaffected by the single-quote fix.
  it('double-quoted strings unaffected', () => {
    const result = _parseYaml('title: "plain double-quoted"\n');
    assert.equal(result.title, 'plain double-quoted');
  });

  // Guard: unquoted strings with no '' sequence unaffected.
  it('unquoted string with no escape sequence unaffected', () => {
    const result = _parseYaml('title: plain value\n');
    assert.equal(result.title, 'plain value');
  });
});

describe('parser correctness — drift-3: blank line before nested block', () => {
  // (e) Blank line between key and its indented nested block — nested block must be
  // correctly attached, not severed. YAML does not end a nested mapping on a blank line.
  // Mirrors schema_loader.py A-F6 fix.
  it('(e) blank line between key and nested block — nested block attached correctly', () => {
    const yaml = [
      'top_key:',
      '',   // blank line between key and nested block
      '  nested_key: nested_value',
      'sibling: present',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.deepEqual(result.top_key, { nested_key: 'nested_value' },
      'blank line must not sever the nested block from its key');
    assert.equal(result.sibling, 'present', 'sibling key after nested block must be retained');
  });

  // Guard: key with NO following indented block correctly gets null.
  it('key with genuinely null value (no following indented block) → null', () => {
    const yaml = 'nullable_key:\nother: val\n';
    const result = _parseYaml(yaml);
    assert.equal(result.nullable_key, null, 'key with no following block must be null');
    assert.equal(result.other, 'val');
  });

  // Guard: comment between key and nested block also advances past.
  it('comment-only line between key and nested block — nested block attached', () => {
    const yaml = [
      'block_key:',
      '  # comment-only line',
      '  nested: value',
    ].join('\n');
    const result = _parseYaml(yaml);
    assert.deepEqual(result.block_key, { nested: 'value' },
      'comment-only line between key and nested block must not sever it');
  });
});

describe('parser correctness — drift-5: isStringOrNull honors bare-string spec', () => {
  // (f) review-trail schema has workstream: string-or-null as a BARE STRING spec value.
  // A null workstream must validate ok — not be flagged as "required field missing".
  // Pre-fix: the isStringOrNull check only fired for {type:'string-or-null'} objects,
  // missing the bare-string form, so null was treated as missing.
  it('(f) bare-string spec string-or-null with null value validates ok (workstream: null)', () => {
    const reviewTrailSchema = SCHEMAS['review-trail'];
    const fm = {
      sha_range: 'abc123..def456',
      reviewer: 'code-reviewer',
      scope: 'bin/lib/schema.js',
      scope_kind: 'single-file',
      verdict: 'PASS',
      diff_loc: 42,
      session_id: 'ses-20260101-abc',
      workstream: null,  // null is valid — workstream is string-or-null
    };
    const result = validateFrontmatter(fm, reviewTrailSchema);
    assert.ok(result.ok, `workstream:null must validate ok with bare string-or-null spec, got: ${JSON.stringify(result.errors)}`);
  });

  // Guard: a string workstream still validates ok.
  it('bare-string spec string-or-null with string value still validates ok', () => {
    const reviewTrailSchema = SCHEMAS['review-trail'];
    const fm = {
      sha_range: 'abc123..def456',
      reviewer: 'code-reviewer',
      scope: 'bin/lib/schema.js',
      scope_kind: 'single-file',
      verdict: 'PASS',
      diff_loc: 42,
      session_id: 'ses-20260101-abc',
      workstream: 'my-workstream',
    };
    const result = validateFrontmatter(fm, reviewTrailSchema);
    assert.ok(result.ok, `workstream:string must still validate ok, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — skill schema (C2 coverage)
// ---------------------------------------------------------------------------

describe('validateFrontmatter — skill schema', () => {
  // Spec backlink: docs/plans/2026-06-27-ccos-10-skill-manifest-schema.md § C2
  //
  // Three tests (positive + two negative):
  //   Positive — every live SKILL.md in the corpus validates clean.
  //   Negative — (a) missing required `name` is rejected; (b) unknown key is
  //               rejected (exercises additionalProperties:false).
  // Review: code-reviewer Slice B — (F3) comment said "Two assertions" but there are three it-blocks
  //
  // Negative fixtures live under bin/tests/fixtures/ (outside the production
  // skills glob) so lint-frontmatter.js never collects them as real violations.
  // validateFrontmatterDispatch is called directly on parsed frontmatter — the
  // fixture files are never placed where the live lint gate would find them.

  const SKILLS_DIR = path.resolve(__dirname, '../../skills');

  it('positive — all live SKILL.md files in the corpus validate clean against the skill schema', () => {
    const skillSchema = SCHEMAS['skill'];
    assert.ok(skillSchema, 'precondition: skill schema must be loaded by loadSchemas');
    const skillDirs = fs.readdirSync(SKILLS_DIR).filter(d =>
      fs.statSync(path.join(SKILLS_DIR, d)).isDirectory()
    );
    const failures = [];
    let checked = 0; // Review: code-reviewer Slice B — (F1) corpus-count floor: fail loud if SKILLS_DIR is empty/mislocated
    for (const dir of skillDirs) {
      const skillPath = path.join(SKILLS_DIR, dir, 'SKILL.md');
      if (!fs.existsSync(skillPath)) continue;
      const content = fs.readFileSync(skillPath, 'utf8');
      const { frontmatter } = parseFrontmatter(content);
      const result = validateFrontmatterDispatch(frontmatter, skillSchema);
      checked++;
      if (!result.ok) {
        failures.push({ file: skillPath, errors: result.errors });
      }
    }
    for (const f of failures) {
      process.stderr.write(
        `SKILL-CORPUS-FAIL: ${f.file}\n  errors: ${JSON.stringify(f.errors)}\n`
      );
    }
    assert.ok(checked >= 30,
      `corpus-count floor: expected ≥30 SKILL.md files validated, got ${checked} — check SKILLS_DIR path`);
    assert.equal(failures.length, 0,
      `${failures.length} SKILL.md file(s) failed validation — see SKILL-CORPUS-FAIL lines above`);
  });

  it('negative — (a) SKILL.md frontmatter missing required name field is REJECTED', () => {
    const skillSchema = SCHEMAS['skill'];
    assert.ok(skillSchema, 'precondition: skill schema must be loaded by loadSchemas'); // Review: code-reviewer Slice B — (F2) match the positive test's guard
    const fixturePath = path.resolve(__dirname, '../tests/fixtures/skill-negative-missing-name.md');
    const content = fs.readFileSync(fixturePath, 'utf8');
    const { frontmatter } = parseFrontmatter(content);
    const result = validateFrontmatterDispatch(frontmatter, skillSchema);
    assert.equal(result.ok, false, 'skill missing name field must be rejected');
    const nameErr = result.errors && result.errors.find(e => e.field === 'name');
    assert.ok(nameErr, `Expected name required-field error, got: ${JSON.stringify(result.errors)}`);
    assert.match(nameErr.error, /required field missing/);
  });

  it('negative — (b) SKILL.md frontmatter with unknown key is REJECTED (additionalProperties: false)', () => {
    const skillSchema = SCHEMAS['skill'];
    assert.ok(skillSchema, 'precondition: skill schema must be loaded by loadSchemas'); // Review: code-reviewer Slice B — (F2) match the positive test's guard
    const fixturePath = path.resolve(__dirname, '../tests/fixtures/skill-negative-unknown-key.md');
    const content = fs.readFileSync(fixturePath, 'utf8');
    const { frontmatter } = parseFrontmatter(content);
    const result = validateFrontmatterDispatch(frontmatter, skillSchema);
    assert.equal(result.ok, false, 'skill with unknown key must be rejected');
    const addErr = result.errors && result.errors.find(e => /additional property/.test(e.error));
    assert.ok(addErr, `Expected additional-properties error, got: ${JSON.stringify(result.errors)}`);
    assert.ok(/unknown_extra_field/.test(addErr.error), // Review: code-reviewer Slice B — (F5) confirm the error names the actual offending key
      `Expected error to name 'unknown_extra_field', got: ${addErr.error}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — spinoff forked_from kind-gate (AC2)
//
// forked_from is a lineage/render-only field permitted only on kind=spinoff.
// Governed by a NEW dedicated kind-gate (see CROSS_FIELD_RULES.handoff in schema.js).
// Rule A3a-3 is UNCHANGED — it governs only the primary predecessor field.
//
// Tests:
//   (1) kind=spinoff + predecessor=none + forked_from → PASSES (valid spinoff with fork ancestry)
//   (2) kind=spinoff + non-none predecessor + forked_from → FAILS on A3a-3 (predecessor check
//       unchanged) — demonstrates A3a-3 still fires even when forked_from is present
//   (3) kind=session-handoff + forked_from → FAILS on new forked_from kind-gate
//   (4) kind=spinoff without forked_from → PASSES (forked_from is optional)
//
// Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C1 (AC2)
// ---------------------------------------------------------------------------

describe('validateFrontmatter — spinoff forked_from kind-gate', () => {
  const handoffSchema = SCHEMAS['handoff'];

  // Helper: base valid kind=spinoff handoff (post-cutoff required fields included).
  function baseSpinoffForForkedFrom(overrides = {}) {
    return Object.assign({
      title: 'Spinoff with fork ancestry',
      created: '2026-06-29',
      branch: 'work/striker/2026-06-29',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff',
      category: 'infra',
      summary: 'Spinoff baton that records its branch-point ancestry',
    }, overrides);
  }

  it('spinoff forked_from positive: kind=spinoff + predecessor=none + forked_from PASSES (valid spinoff with fork ancestry)', () => {
    const fm = baseSpinoffForForkedFrom({
      forked_from: 'state/handoffs/2026-06-28-parent-baton.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `kind:spinoff + predecessor:none + forked_from should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  it('spinoff forked_from A3a-3-still-fires: kind=spinoff + non-none predecessor + forked_from FAILS on predecessor rule (A3a-3 unchanged)', () => {
    // Demonstrates that adding forked_from does NOT weaken A3a-3 — a spinoff with a
    // non-none predecessor is still rejected even when forked_from is present.
    const fm = baseSpinoffForForkedFrom({
      predecessor: 'state/handoffs/2026-06-27-actual-predecessor.md',
      forked_from: 'state/handoffs/2026-06-28-branch-point.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff with non-none predecessor (even with forked_from) should fail A3a-3');
    const predErr = result.errors && result.errors.find(e => e.field === 'predecessor');
    assert.ok(predErr, `Expected predecessor (A3a-3) error, got: ${JSON.stringify(result.errors)}`);
    assert.match(predErr.error, /must be "none" or null for kind=spinoff/);
  });

  it('spinoff forked_from kind-gate: kind=session-handoff + forked_from FAILS on new kind-gate', () => {
    const fm = {
      title: 'Session continuation baton',
      created: '2026-06-29',
      branch: 'work/striker/2026-06-29',
      status: 'active',
      predecessor: 'state/handoffs/2026-06-28-prior.md',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Normal session continuation that should not carry forked_from',
      forked_from: 'state/handoffs/2026-06-28-branch-point.md',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'session-handoff with forked_from should fail the kind-gate');
    const forkErr = result.errors && result.errors.find(e => e.field === 'forked_from');
    assert.ok(forkErr, `Expected forked_from kind-gate error, got: ${JSON.stringify(result.errors)}`);
    assert.match(forkErr.error, /permitted only when kind=spinoff \(current kind: session-handoff\)/);
  });

  it('spinoff forked_from optional: kind=spinoff without forked_from PASSES (field is optional)', () => {
    const fm = baseSpinoffForForkedFrom(); // no forked_from
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Spinoff without forked_from should pass (it is optional), got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — additional_predecessors validation (AC3)
//
// additional_predecessors is an optional array-of-string for fan-in merge edges.
// Cross-field rules enforce:
//   — array-of-string shape (belt-and-suspenders; JSON Schema covers the primary check)
//   — no duplicate entries within the array (self-reference guard)
//   — no entry duplicating the primary predecessor field (prevents LoE double-count)
//
// Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C1 (AC3)
// ---------------------------------------------------------------------------

describe('validateFrontmatter — additional_predecessors validation', () => {
  const handoffSchema = SCHEMAS['handoff'];

  // Helper: base valid session-handoff with additional_predecessors (fan-in merge point).
  function baseFanInHandoff(overrides = {}) {
    return Object.assign({
      title: 'Fan-in merge handoff',
      created: '2026-06-29',
      branch: 'work/striker/2026-06-29',
      status: 'active',
      predecessor: 'state/handoffs/2026-06-28-primary.md',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Session handoff that merges two parallel workstreams',
    }, overrides);
  }

  it('additional_predecessors validation valid: valid array-of-string passes', () => {
    const fm = baseFanInHandoff({
      additional_predecessors: ['state/handoffs/2026-06-28-secondary.md'],
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Valid additional_predecessors should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('additional_predecessors validation self-ref: duplicate entry in array is REJECTED', () => {
    const fm = baseFanInHandoff({
      additional_predecessors: [
        'state/handoffs/2026-06-28-secondary.md',
        'state/handoffs/2026-06-28-secondary.md', // duplicate
      ],
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Duplicate entry in additional_predecessors should be rejected');
    const apErr = result.errors && result.errors.find(e => e.field === 'additional_predecessors');
    assert.ok(apErr, `Expected additional_predecessors error, got: ${JSON.stringify(result.errors)}`);
    assert.match(apErr.error, /duplicate entry/);
  });

  it('additional_predecessors validation predecessor-duplication: entry equal to predecessor field is REJECTED', () => {
    const primaryPred = 'state/handoffs/2026-06-28-primary.md';
    const fm = baseFanInHandoff({
      predecessor: primaryPred,
      additional_predecessors: [primaryPred], // duplicates the primary predecessor
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'additional_predecessors entry duplicating predecessor should be rejected');
    const apErr = result.errors && result.errors.find(e => e.field === 'additional_predecessors');
    assert.ok(apErr, `Expected additional_predecessors error, got: ${JSON.stringify(result.errors)}`);
    assert.match(apErr.error, /duplicates the primary predecessor field/);
  });

  it('additional_predecessors validation non-array: non-array value is REJECTED', () => {
    // Non-array is caught by the JSON Schema type check (type: array) in validateJsonSchemaNode.
    // Confirm the combined validator rejects it.
    const fm = baseFanInHandoff({
      additional_predecessors: 'state/handoffs/2026-06-28-secondary.md', // string, not array
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Non-array additional_predecessors should be rejected');
    // Error may come from JSON Schema type check or the cross-field belt-and-suspenders check.
    const hasApErr = result.errors && result.errors.some(e => e.field === 'additional_predecessors' || /additional_predecessors/.test(e.field));
    assert.ok(hasApErr, `Expected additional_predecessors type error, got: ${JSON.stringify(result.errors)}`);
  });

  it('additional_predecessors validation absent: handoff without additional_predecessors passes (field is optional)', () => {
    const fm = baseFanInHandoff(); // no additional_predecessors
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff without additional_predecessors should pass, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// predecessor back-compat (AC10)
//
// Existing handoffs that carry no new fields (additional_predecessors, forked_from)
// validate identically to pre-change behavior. The new fields are optional and absent
// in the existing corpus — no regressions.
//
// Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C1 (AC10)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Deliverable-spine identity field cross-field rules (2026-07-03)
//
// Tests for the carry-not-remint guard (deliverable_id must begin 'dlv-') and
// the initiative FK non-empty guard.
//
// Spec backlink: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § D1, D2, D3
// ---------------------------------------------------------------------------

describe('validateFrontmatter — deliverable-spine cross-field rules on handoff', () => {
  const handoffSchema = SCHEMAS['handoff'];

  function baseHandoff(overrides) {
    return {
      title: 'Test handoff',
      created: '2026-07-03',
      branch: 'work/striker/2026-07-03',
      status: 'active',
      predecessor: 'state/handoffs/2026-07-02-prior.md',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Test handoff for deliverable-spine field validation',
      ...overrides,
    };
  }

  it('deliverable_id absent: handoff without deliverable_id validates clean (optional field)', () => {
    const fm = baseHandoff();
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff without deliverable_id should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('deliverable_id null: explicit null is valid (pre-backfill artifact)', () => {
    const fm = baseHandoff({ deliverable_id: null });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff with deliverable_id: null should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('deliverable_id valid: "dlv-example-initiative-3" is accepted', () => {
    const fm = baseHandoff({ deliverable_id: 'dlv-example-initiative-3' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff with valid deliverable_id should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('deliverable_id valid: "dlv-fleet-spine-abc123" is accepted', () => {
    const fm = baseHandoff({ deliverable_id: 'dlv-fleet-spine-abc123' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff with valid deliverable_id should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('deliverable_id invalid: no "dlv-" prefix is REJECTED (carry-not-remint guard)', () => {
    const fm = baseHandoff({ deliverable_id: 'abc-fleet-1a2b3c' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'deliverable_id without dlv- prefix should be rejected');
    const err = result.errors && result.errors.find(e => e.field === 'deliverable_id');
    assert.ok(err, `Expected deliverable_id error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not begin with "dlv-"/);
  });

  it('initiative absent: handoff without initiative validates clean (optional field)', () => {
    const fm = baseHandoff();
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff without initiative should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('initiative null: explicit null is valid (no initiative)', () => {
    const fm = baseHandoff({ initiative: null });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff with initiative: null should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('initiative valid: non-empty string initiative FK is accepted', () => {
    const fm = baseHandoff({ initiative: 'delphi-pro-launch' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Handoff with valid initiative should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('initiative invalid: empty string is REJECTED (FK non-empty guard)', () => {
    const fm = baseHandoff({ initiative: '' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Empty initiative string should be rejected');
    const err = result.errors && result.errors.find(e => e.field === 'initiative');
    assert.ok(err, `Expected initiative error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /non-empty string/);
  });

  it('initiative invalid: whitespace-only string is REJECTED', () => {
    const fm = baseHandoff({ initiative: '   ' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Whitespace-only initiative should be rejected');
    const err = result.errors && result.errors.find(e => e.field === 'initiative');
    assert.ok(err, `Expected initiative error. Got: ${JSON.stringify(result.errors)}`);
  });
});

describe('validateFrontmatter — deliverable-spine cross-field rules on plan', () => {
  const planSchema = SCHEMAS['plan'];

  function basePlan(overrides) {
    return {
      title: 'Test plan',
      created: '2026-07-03',
      author: 'claude-central-em',
      status: 'draft',
      ...overrides,
    };
  }

  it('plan without deliverable-spine fields validates clean (all optional)', () => {
    const fm = basePlan();
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok, `Plan without spine fields should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('plan with valid deliverable_id validates clean', () => {
    const fm = basePlan({ deliverable_id: 'dlv-fleet-spine-1a2b3c' });
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok, `Plan with valid deliverable_id should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('plan with deliverable_id missing dlv- prefix is REJECTED', () => {
    const fm = basePlan({ deliverable_id: 'plan-fleet-spine' });
    const result = validateFrontmatter(fm, planSchema);
    assert.equal(result.ok, false, 'Plan deliverable_id without dlv- prefix should be rejected');
    const err = result.errors && result.errors.find(e => e.field === 'deliverable_id');
    assert.ok(err, `Expected deliverable_id error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not begin with "dlv-"/);
  });

  it('plan with valid plan_id validates clean', () => {
    const fm = basePlan({ plan_id: 'pln-fleet-spine-abc123' });
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok, `Plan with valid plan_id should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('plan with plan_id missing pln- prefix is REJECTED', () => {
    const fm = basePlan({ plan_id: 'plan-abc123' });
    const result = validateFrontmatter(fm, planSchema);
    assert.equal(result.ok, false, 'Plan plan_id without pln- prefix should be rejected');
    const err = result.errors && result.errors.find(e => e.field === 'plan_id');
    assert.ok(err, `Expected plan_id error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not begin with "pln-"/);
  });

  it('plan with null plan_id is valid (pre-backfill)', () => {
    const fm = basePlan({ plan_id: null });
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok, `Plan with plan_id: null should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('plan with valid initiative FK validates clean', () => {
    const fm = basePlan({ initiative: 'delphi-pro-launch' });
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok, `Plan with valid initiative should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('plan with empty initiative FK is REJECTED', () => {
    const fm = basePlan({ initiative: '' });
    const result = validateFrontmatter(fm, planSchema);
    assert.equal(result.ok, false, 'Empty initiative on plan should be rejected');
    const err = result.errors && result.errors.find(e => e.field === 'initiative');
    assert.ok(err, `Expected initiative error. Got: ${JSON.stringify(result.errors)}`);
  });

  it('plan with all spine fields (deliverable_id, plan_id, initiative, caption, status_reason, owner) validates clean', () => {
    const fm = basePlan({
      deliverable_id: 'dlv-delphi-pro-a1b2c3',
      plan_id: 'pln-fleet-spine-d4e5f6',
      initiative: 'delphi-pro-launch',
      caption: 'Ship the Delphi Pro billing flow',
      status_reason: null,
      owner: 'claude-central-em',
    });
    const result = validateFrontmatter(fm, planSchema);
    assert.ok(result.ok, `Plan with all spine fields should pass. Errors: ${JSON.stringify(result.errors)}`);
  });
});

describe('validateFrontmatter — predecessor back-compat', () => {
  const handoffSchema = SCHEMAS['handoff'];

  it('predecessor back-compat: session-handoff without new fields validates clean (back-compat)', () => {
    const fm = {
      title: 'Legacy session handoff without new fields',
      created: '2026-06-29',
      branch: 'work/striker/2026-06-29',
      status: 'active',
      predecessor: 'state/handoffs/2026-06-28-prior.md',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Existing-style handoff with no additional_predecessors or forked_from',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Legacy handoff without new fields should validate clean, got: ${JSON.stringify(result.errors)}`);
  });

  it('predecessor back-compat: spinoff with predecessor=none and NO new fields validates clean', () => {
    const fm = {
      title: 'Legacy spinoff without new fields',
      created: '2026-06-29',
      branch: 'work/striker/2026-06-29',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff',
      category: 'infra',
      summary: 'Existing-style spinoff with no forked_from or additional_predecessors',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Legacy spinoff without new fields should validate clean, got: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — spinoff-goal and spinoff-roadmap-creator kind taxonomy (C1b)
//
// Tests the ladder kind taxonomy extension:
//   (a) kind:spinoff-roadmap-creator validates; existing kinds still validate
//   (b) predecessor semantics — spinoff-goal/spinoff-roadmap-creator require predecessor:none
//   (c) spinoff-roadmap-creator with graph primitives (blocks/blocked_by/roadmap_id) is rejected
//
// Spec backlink: coordinator/schemas/handoff.schema.json § kind enum
// Spec backlink: coordinator/bin/lib/schema.js § CROSS_FIELD_RULES['handoff'] Rule A3a-3
// ---------------------------------------------------------------------------
describe('validateFrontmatter — spinoff-goal and spinoff-roadmap-creator kind taxonomy (C1b)', () => {
  const handoffSchema = SCHEMAS['handoff'];

  // Helper: base valid spinoff-goal stub (post-cutoff required fields).
  function baseSpinoffGoal(overrides) {
    return Object.assign({
      title: 'Goal-scoped spinoff baton',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff-goal',
      category: 'roadmap',
      summary: 'Spinoff goal baton forked from current session',
    }, overrides);
  }

  // Helper: base valid spinoff-roadmap-creator stub (post-cutoff required fields).
  function baseSpinoffRoadmapCreator(overrides) {
    return Object.assign({
      title: 'Roadmap-creator session spinoff',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff-roadmap-creator',
      category: 'roadmap',
      summary: 'Session that will produce the roadmap stubs',
    }, overrides);
  }

  // (a) kind:spinoff-roadmap-creator validates cleanly
  it('(a) kind=spinoff-roadmap-creator with predecessor:none PASSES (valid ladder kind)', () => {
    const fm = baseSpinoffRoadmapCreator();
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `kind:spinoff-roadmap-creator + predecessor:none should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  // (a) kind:spinoff-goal validates cleanly
  it('(a) kind=spinoff-goal with predecessor:none PASSES (valid ladder kind)', () => {
    const fm = baseSpinoffGoal();
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `kind:spinoff-goal + predecessor:none should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  // (a) existing kind:spinoff still validates cleanly (no regression)
  it('(a) existing kind=spinoff still validates cleanly (back-compat, no regression)', () => {
    const fm = {
      title: 'Ordinary spinoff',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff',
      category: 'infra',
      summary: 'Ordinary spinoff back-compat check after C1b extension',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `kind:spinoff should still validate cleanly, got: ${JSON.stringify(result.errors)}`);
  });

  // (b) spinoff-goal with predecessor:none validates
  it('(b) spinoff-goal predecessor:none validates (correct shape)', () => {
    const fm = baseSpinoffGoal({ predecessor: 'none' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `spinoff-goal + predecessor:none should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  // (b) spinoff-goal with a non-none predecessor FAILS (A3a-3 extended)
  it('(b) spinoff-goal with non-none predecessor FAILS (A3a-3 predecessor rule)', () => {
    const fm = baseSpinoffGoal({ predecessor: 'state/handoffs/2026-07-06-prior.md' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-goal with non-none predecessor should fail');
    const predErr = (result.errors || []).find(e => e.field === 'predecessor');
    assert.ok(predErr, `Expected predecessor error, got: ${JSON.stringify(result.errors)}`);
    assert.match(predErr.error, /must be "none" or null for kind=spinoff-goal/);
  });

  // (b) spinoff-roadmap-creator with predecessor:none validates
  it('(b) spinoff-roadmap-creator predecessor:none validates (correct shape)', () => {
    const fm = baseSpinoffRoadmapCreator({ predecessor: 'none' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `spinoff-roadmap-creator + predecessor:none should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  // (b) spinoff-roadmap-creator with a non-none predecessor FAILS (A3a-3 extended)
  it('(b) spinoff-roadmap-creator with non-none predecessor FAILS (A3a-3 predecessor rule)', () => {
    const fm = baseSpinoffRoadmapCreator({ predecessor: 'state/handoffs/2026-07-06-prior.md' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-roadmap-creator with non-none predecessor should fail');
    const predErr = (result.errors || []).find(e => e.field === 'predecessor');
    assert.ok(predErr, `Expected predecessor error, got: ${JSON.stringify(result.errors)}`);
    assert.match(predErr.error, /must be "none" or null for kind=spinoff-roadmap-creator/);
  });

  // (c) spinoff-roadmap-creator with blocks set is rejected by the graph-primitive gate
  it('(c) spinoff-roadmap-creator with blocks set is REJECTED by graph-primitive gate', () => {
    const fm = baseSpinoffRoadmapCreator({ blocks: ['some-roadmap-1'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-roadmap-creator + blocks should fail the graph-primitive gate');
    const graphErr = (result.errors || []).find(e => e.field && e.field.includes('blocks'));
    assert.ok(graphErr, `Expected graph-primitive error on blocks, got: ${JSON.stringify(result.errors)}`);
    assert.match(graphErr.error, /permitted only when kind=spinoff-roadmap/);
  });

  // (c) spinoff-roadmap-creator with blocked_by set is rejected by the graph-primitive gate
  it('(c) spinoff-roadmap-creator with blocked_by set is REJECTED by graph-primitive gate', () => {
    const fm = baseSpinoffRoadmapCreator({ blocked_by: ['some-roadmap-0'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-roadmap-creator + blocked_by should fail the graph-primitive gate');
    const graphErr = (result.errors || []).find(e => e.field && e.field.includes('blocked_by'));
    assert.ok(graphErr, `Expected graph-primitive error on blocked_by, got: ${JSON.stringify(result.errors)}`);
    assert.match(graphErr.error, /permitted only when kind=spinoff-roadmap/);
  });

  // (c) spinoff-roadmap-creator with roadmap_id set is rejected by the graph-primitive gate
  it('(c) spinoff-roadmap-creator with roadmap_id set is REJECTED by graph-primitive gate', () => {
    const fm = baseSpinoffRoadmapCreator({ roadmap_id: 'my-roadmap' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-roadmap-creator + roadmap_id should fail the graph-primitive gate');
    const graphErr = (result.errors || []).find(e => e.field && e.field.includes('roadmap_id'));
    assert.ok(graphErr, `Expected graph-primitive error on roadmap_id, got: ${JSON.stringify(result.errors)}`);
    assert.match(graphErr.error, /permitted only when kind=spinoff-roadmap/);
  });

  // (c) spinoff-goal with graph-primitive fields is rejected
  // Review: code-reviewer — F2: spinoff-goal graph-primitive gate was unasserted; pinning all three fields (2026-07-07)
  it('(c) spinoff-goal with blocks set is REJECTED by graph-primitive gate', () => {
    const fm = baseSpinoffGoal({ blocks: ['some-roadmap-1'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-goal + blocks should fail the graph-primitive gate');
    const graphErr = (result.errors || []).find(e => e.field && e.field.includes('blocks'));
    assert.ok(graphErr, `Expected graph-primitive error on blocks, got: ${JSON.stringify(result.errors)}`);
    assert.match(graphErr.error, /permitted only when kind=spinoff-roadmap/);
  });

  it('(c) spinoff-goal with blocked_by set is REJECTED by graph-primitive gate', () => {
    const fm = baseSpinoffGoal({ blocked_by: ['some-roadmap-0'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-goal + blocked_by should fail the graph-primitive gate');
    const graphErr = (result.errors || []).find(e => e.field && e.field.includes('blocked_by'));
    assert.ok(graphErr, `Expected graph-primitive error on blocked_by, got: ${JSON.stringify(result.errors)}`);
    assert.match(graphErr.error, /permitted only when kind=spinoff-roadmap/);
  });

  it('(c) spinoff-goal with roadmap_id set is REJECTED by graph-primitive gate', () => {
    const fm = baseSpinoffGoal({ roadmap_id: 'my-roadmap' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-goal + roadmap_id should fail the graph-primitive gate');
    const graphErr = (result.errors || []).find(e => e.field && e.field.includes('roadmap_id'));
    assert.ok(graphErr, `Expected graph-primitive error on roadmap_id, got: ${JSON.stringify(result.errors)}`);
    assert.match(graphErr.error, /permitted only when kind=spinoff-roadmap/);
  });

  // (d) predecessor:null is equivalent to predecessor:'none' for new fork kinds
  // Review: code-reviewer — F4: predecessor:null path was never asserted for new kinds; pinning both (2026-07-07)
  it('(d) spinoff-goal with predecessor:null PASSES (null is equivalent to none)', () => {
    const fm = baseSpinoffGoal({ predecessor: null });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `spinoff-goal + predecessor:null should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  it('(d) spinoff-roadmap-creator with predecessor:null PASSES (null is equivalent to none)', () => {
    const fm = baseSpinoffRoadmapCreator({ predecessor: null });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `spinoff-roadmap-creator + predecessor:null should be valid, got: ${JSON.stringify(result.errors)}`);
  });

  // (e) forked_from is blocked on spinoff-goal and spinoff-roadmap-creator (negative-spec pin)
  // Review: code-reviewer — F3: forked_from kind-gate asymmetry for new kinds was undocumented and untested;
  // pinning the rejection behavior (spinoff-goal/spinoff-roadmap-creator excluded by design — PM-directive origin) (2026-07-07)
  it('(e) spinoff-goal with forked_from is REJECTED by forked_from kind-gate (spinoff-only)', () => {
    const fm = baseSpinoffGoal({ forked_from: 'state/handoffs/2026-07-06-parent.md' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-goal with forked_from should fail the kind-gate');
    const forkErr = (result.errors || []).find(e => e.field === 'forked_from');
    assert.ok(forkErr, `Expected forked_from kind-gate error, got: ${JSON.stringify(result.errors)}`);
    assert.match(forkErr.error, /permitted only when kind=spinoff/);
  });

  it('(e) spinoff-roadmap-creator with forked_from is REJECTED by forked_from kind-gate (spinoff-only)', () => {
    const fm = baseSpinoffRoadmapCreator({ forked_from: 'state/handoffs/2026-07-06-parent.md' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'spinoff-roadmap-creator with forked_from should fail the kind-gate');
    const forkErr = (result.errors || []).find(e => e.field === 'forked_from');
    assert.ok(forkErr, `Expected forked_from kind-gate error, got: ${JSON.stringify(result.errors)}`);
    assert.match(forkErr.error, /permitted only when kind=spinoff/);
  });
});

// ---------------------------------------------------------------------------
// Origin-axis cross-field rules (2026-07-07) — C2 of spinoff-provenance-ancestry plan.
//
// Tests for Rules C2-1 through C2-5 on the handoff schema:
//   C2-1: Kind-prefixed id well-formedness (pln-, goal-, state/handoffs/ path, UUID non-empty)
//   C2-2: Explicit per-kind cardinality (scalar session/handoff/plan, array goal)
//   C2-3: Direct self-reference rejection (origin_handoff ≠ own path, best-effort via _filePath)
//   C2-4: predecessor:none invariant for spinoff kinds when origin_* fields are present
//   C2-5: forked_from / origin_handoff never-silently-disagree invariant (equality-when-both-set)
//
// The cardinality-mismatch cases in C2-2 are the load-bearing motivation for this rule set:
// an unexpected inline array in a scalar origin field silently returns zero rows in rag's
// scalar-column ingest filter (DR-014/DR-015). Both rejection directions are pinned:
//   - scalar field (origin_session/origin_handoff/origin_plan_id) carrying an array → REJECT
//   - array field (origin_goal_id) carrying a bare scalar → REJECT
//
// Spec backlink: docs/plans/2026-07-07-spinoff-provenance-ancestry.md § C2, § AC3
// ---------------------------------------------------------------------------

describe('validateFrontmatter — origin-axis cross-field rules (C2-1 through C2-5)', () => {
  const handoffSchema = SCHEMAS['handoff'];

  // Helper: base valid spinoff handoff carrying well-formed origin_* fields.
  // All four fields present + valid; predecessor:none (spinoff fork axiom).
  function baseSpinoffWithOrigin(overrides) {
    return Object.assign({
      title: 'Spinoff baton with full origin provenance',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff',
      category: 'roadmap',
      summary: 'Spinoff baton with well-formed origin_* provenance fields',
      origin_session: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      origin_handoff: 'state/handoffs/2026-07-06-parent-baton.md',
      origin_plan_id: 'pln-structured-originating-session-8b505c',
      origin_goal_id: ['goal-example-game-repo-shipping-velocity'],
    }, overrides);
  }

  // Helper: base valid non-spinoff handoff (session-handoff kind) without origin_* fields.
  // Used to test that origin_* rules fire correctly on both spinoff and non-spinoff kinds.
  function baseSessionHandoff(overrides) {
    return Object.assign({
      title: 'Normal session continuation',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'state/handoffs/2026-07-06-prior.md',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Normal session-handoff with optional origin_* fields',
    }, overrides);
  }

  // --- C2-1: Kind-prefixed id well-formedness ---

  it('C2-1 positive: well-formed origin_* fields on a spinoff PASS', () => {
    const fm = baseSpinoffWithOrigin();
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Well-formed origin_* spinoff should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-1 positive: origin_* fields absent (all undefined) — rules are no-ops', () => {
    const fm = baseSessionHandoff();
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Session-handoff without origin_* should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-1 positive: all origin_* fields explicitly null — pass (backfill=null policy)', () => {
    const fm = baseSpinoffWithOrigin({
      origin_session: null,
      origin_handoff: null,
      origin_plan_id: null,
      origin_goal_id: null,
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Spinoff with all origin_* null should pass (backfill policy). Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-1 negative: origin_plan_id without "pln-" prefix is REJECTED', () => {
    const fm = baseSpinoffWithOrigin({ origin_plan_id: 'plan-some-slug' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_plan_id without pln- prefix should be rejected');
    const err = (result.errors || []).find(e => e.field === 'origin_plan_id');
    assert.ok(err, `Expected origin_plan_id error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not begin with "pln-"/);
    assert.match(err.error, /C2-1/);
  });

  it('C2-1 negative: origin_handoff not a state/handoffs/ path is REJECTED', () => {
    const fm = baseSpinoffWithOrigin({ origin_handoff: 'archive/handoffs/2026-07-06-old.md' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_handoff not starting with state/handoffs/ should be rejected');
    const err = (result.errors || []).find(e => e.field === 'origin_handoff');
    assert.ok(err, `Expected origin_handoff error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not begin with "state\/handoffs\/"/);
    assert.match(err.error, /C2-1/);
  });

  it('C2-1 negative: origin_session empty string is REJECTED', () => {
    const fm = baseSpinoffWithOrigin({ origin_session: '   ' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Empty origin_session should be rejected');
    const err = (result.errors || []).find(e => e.field === 'origin_session');
    assert.ok(err, `Expected origin_session error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /non-empty string/);
    assert.match(err.error, /C2-1/);
  });

  it('C2-1 negative: origin_goal_id entry without "goal-" prefix is REJECTED', () => {
    // Negative-spec: 'gol-' prefix (rag example in old plan text) is NOT valid.
    const fm = baseSpinoffWithOrigin({ origin_goal_id: ['gol-legibility', 'goal-shipping-velocity'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_goal_id with gol- entry should be rejected');
    const err = (result.errors || []).find(e => e.field === 'origin_goal_id');
    assert.ok(err, `Expected origin_goal_id prefix error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not begin with "goal-"/);
    assert.match(err.error, /C2-1/);
  });

  it('C2-1 negative: origin_goal_id entry with "g-" prefix (old scheme) is REJECTED', () => {
    // Negative-spec: 'g-<slug>' is also not the goal-id scheme; must be 'goal-<slug>'.
    const fm = baseSpinoffWithOrigin({ origin_goal_id: ['g-legibility'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_goal_id with g- entry should be rejected');
    const err = (result.errors || []).find(e => e.field === 'origin_goal_id');
    assert.ok(err, `Expected origin_goal_id prefix error. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /does not begin with "goal-"/);
  });

  it('C2-1 positive: origin_goal_id with multiple valid goal- entries PASSES', () => {
    // Multi-goal forks are valid (roadmap serving multiple goals).
    const fm = baseSpinoffWithOrigin({
      origin_goal_id: ['goal-example-game-repo-shipping-velocity', 'goal-legibility-system'],
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Multi-goal origin_goal_id should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-1 positive: origin_goal_id empty array PASSES (zero tagged goals)', () => {
    const fm = baseSpinoffWithOrigin({ origin_goal_id: [] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Empty origin_goal_id array should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  // --- C2-2: Explicit per-kind cardinality ---
  // Load-bearing: an unexpected array in a scalar field silently returns zero rows in rag's
  // scalar-column filter. Both rejection directions are pinned (DR-014/DR-015).

  it('C2-2 negative: origin_session carrying an array is REJECTED (scalar-only field)', () => {
    // This is the cardinality-mismatch case that motivated Rule C2-2:
    // rag ingests origin_session as a scalar column; an array lands as a JSON string
    // in the filter predicate and silently returns zero rows.
    // Note: the JSON Schema layer also fires a type error; both errors are present.
    // We assert the C2-2 cross-field error specifically (contains "C2-2").
    const fm = baseSpinoffWithOrigin({ origin_session: ['a1b2c3d4-e5f6-7890-abcd-ef1234567890'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_session must be scalar — array must be rejected');
    const c22Err = (result.errors || []).find(
      e => e.field === 'origin_session' && e.error && e.error.includes('C2-2')
    );
    assert.ok(c22Err, `Expected C2-2 cardinality error on origin_session. Got: ${JSON.stringify(result.errors)}`);
    assert.match(c22Err.error, /scalar string \(not an array\)/);
  });

  it('C2-2 negative: origin_handoff carrying an array is REJECTED (scalar-only field)', () => {
    const fm = baseSpinoffWithOrigin({ origin_handoff: ['state/handoffs/2026-07-06-parent-baton.md'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_handoff must be scalar — array must be rejected');
    const c22Err = (result.errors || []).find(
      e => e.field === 'origin_handoff' && e.error && e.error.includes('C2-2')
    );
    assert.ok(c22Err, `Expected C2-2 cardinality error on origin_handoff. Got: ${JSON.stringify(result.errors)}`);
    assert.match(c22Err.error, /scalar string \(not an array\)/);
  });

  it('C2-2 negative: origin_plan_id carrying an array is REJECTED (scalar-only field)', () => {
    const fm = baseSpinoffWithOrigin({ origin_plan_id: ['pln-structured-originating-session-8b505c'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_plan_id must be scalar — array must be rejected');
    const c22Err = (result.errors || []).find(
      e => e.field === 'origin_plan_id' && e.error && e.error.includes('C2-2')
    );
    assert.ok(c22Err, `Expected C2-2 cardinality error on origin_plan_id. Got: ${JSON.stringify(result.errors)}`);
    assert.match(c22Err.error, /scalar string \(not an array\)/);
  });

  it('C2-2 negative: origin_goal_id carrying a bare scalar is REJECTED (array-only field)', () => {
    // This is the other cardinality-mismatch case: rag fans origin_goal_id entries into N
    // edge rows; a bare scalar bypasses the fan-out entirely.
    // Note: the JSON Schema layer also fires a type error; we assert the C2-2 cross-field
    // error specifically (contains "C2-2").
    const fm = baseSpinoffWithOrigin({ origin_goal_id: 'goal-example-game-repo-shipping-velocity' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_goal_id must be array — bare scalar must be rejected');
    const c22Err = (result.errors || []).find(
      e => e.field === 'origin_goal_id' && e.error && e.error.includes('C2-2')
    );
    assert.ok(c22Err, `Expected C2-2 cardinality error on origin_goal_id. Got: ${JSON.stringify(result.errors)}`);
    assert.match(c22Err.error, /not a bare scalar/);
  });

  it('C2-2 positive: origin_session as plain string PASSES (correct scalar cardinality)', () => {
    const fm = baseSpinoffWithOrigin({ origin_session: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `origin_session as string should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-2 positive: origin_goal_id as array PASSES (correct array cardinality)', () => {
    const fm = baseSpinoffWithOrigin({ origin_goal_id: ['goal-example-game-repo-shipping-velocity'] });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `origin_goal_id as array should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  // --- C2-3: Direct self-reference rejection ---
  // Best-effort: only fires when fm._filePath is injected by the caller.
  // "_filePath" is a validator-internal sentinel, never a YAML frontmatter field.

  it('C2-3 negative: origin_handoff equals own path (_filePath sentinel) is REJECTED', () => {
    const ownPath = 'state/handoffs/2026-07-07-my-spinoff.md';
    const fm = baseSpinoffWithOrigin({
      origin_handoff: ownPath,
      _filePath: ownPath,
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_handoff equalling own path should be rejected');
    const err = (result.errors || []).find(e => e.field === 'origin_handoff');
    assert.ok(err, `Expected self-reference error on origin_handoff. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /equals the record's own path/);
    assert.match(err.error, /C2-3/);
  });

  it('C2-3 positive: origin_handoff different from own path (_filePath sentinel) PASSES', () => {
    const fm = baseSpinoffWithOrigin({
      origin_handoff: 'state/handoffs/2026-07-06-parent-baton.md',
      _filePath: 'state/handoffs/2026-07-07-my-spinoff.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `origin_handoff pointing to a different path should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-3 positive: origin_handoff present but no _filePath sentinel — rule is no-op (skip)', () => {
    // Without _filePath, the self-reference check cannot fire — this is expected "partial"
    // acyclicity (full cycle detection is the walker's job).
    const fm = baseSpinoffWithOrigin({
      origin_handoff: 'state/handoffs/2026-07-07-same-as-own.md',
      // No _filePath injected
    });
    const result = validateFrontmatter(fm, handoffSchema);
    // C2-3 is a no-op without _filePath; the record passes because C2-1/C2-2 are satisfied by the well-formed `origin_handoff` value.
    assert.ok(result.ok, `origin_handoff without _filePath sentinel should pass (partial acyclicity skip). Errors: ${JSON.stringify(result.errors)}`);
  });

  // --- C2-4: predecessor:none invariant preserved for spinoff kinds ---

  it('C2-4 positive: spinoff with origin_* AND predecessor:none PASSES (correct combination)', () => {
    const fm = baseSpinoffWithOrigin({ predecessor: 'none' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Spinoff with origin_* + predecessor:none should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-4 positive: spinoff with origin_* AND predecessor:null PASSES (null is equivalent to none)', () => {
    const fm = baseSpinoffWithOrigin({ predecessor: null });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Spinoff with origin_* + predecessor:null should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-4 negative: spinoff with origin_* AND non-none predecessor is REJECTED', () => {
    // origin_* is the origin axis; predecessor is the continuation spine.
    // A spinoff kind must have predecessor:none regardless of origin_* presence.
    const fm = baseSpinoffWithOrigin({
      predecessor: 'state/handoffs/2026-07-06-prior.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Spinoff with origin_* + non-none predecessor should be rejected');
    const err = (result.errors || []).find(e => e.field === 'predecessor');
    assert.ok(err, `Expected predecessor invariant error. Got: ${JSON.stringify(result.errors)}`);
    // C2-4 fires; A3a-3 also fires — either error message is acceptable.
    const c24Err = (result.errors || []).find(
      e => e.field === 'predecessor' && e.error && e.error.includes('C2-4')
    );
    assert.ok(c24Err, `Expected C2-4 error on predecessor. Got: ${JSON.stringify(result.errors)}`);
    assert.match(c24Err.error, /predecessor:none invariant/);
  });

  it('C2-4 positive: spinoff-goal with origin_* AND predecessor:none PASSES', () => {
    const fm = Object.assign({
      title: 'Goal spinoff with origin provenance',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff-goal',
      category: 'roadmap',
      summary: 'Goal-scoped spinoff with origin provenance',
      origin_session: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      origin_plan_id: 'pln-structured-originating-session-8b505c',
      origin_goal_id: ['goal-example-game-repo-shipping-velocity'],
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `spinoff-goal with origin_* + predecessor:none should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-4 positive: spinoff-roadmap-creator with origin_* AND predecessor:none PASSES', () => {
    const fm = Object.assign({
      title: 'Roadmap-creator spinoff with origin provenance',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff-roadmap-creator',
      category: 'roadmap',
      summary: 'Roadmap-creator spinoff with origin provenance',
      origin_session: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      origin_plan_id: 'pln-structured-originating-session-8b505c',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `spinoff-roadmap-creator with origin_* + predecessor:none should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-4 positive: session-handoff with origin_* fields — C2-4 does NOT fire (non-spinoff kind)', () => {
    // C2-4 only applies to spinoff kinds; session-handoff is exempt.
    // origin_* are optional on any kind; C2-4 predecessor check is spinoff-only.
    const fm = baseSessionHandoff({
      origin_session: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      origin_plan_id: 'pln-some-plan-id',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `session-handoff with origin_* should not trigger C2-4. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-4 positive: spinoff with no origin_* fields — C2-4 does NOT fire (no origin axis present)', () => {
    // C2-4 only fires when at least one origin_* field is non-null.
    // A spinoff without origin_* is valid (backfill=null policy; fields are optional).
    const fm = {
      title: 'Ordinary spinoff without origin provenance',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff',
      category: 'roadmap',
      summary: 'Spinoff without origin_* fields — backfill=null case',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Spinoff without origin_* should pass (C2-4 no-ops). Errors: ${JSON.stringify(result.errors)}`);
  });

  // --- C2-5: forked_from / origin_handoff never-silently-disagree invariant ---
  // Equality-when-both-set, NO precedence, NO presence-coupling. forked_from is
  // spinoff-only (validation-illegal on spinoff-goal/spinoff-roadmap-creator);
  // origin_handoff is legal on all fork kinds. Enforce equality ONLY over the
  // both-present intersection — requiring forked_from whenever origin_handoff is
  // set would break the spinoff-goal/spinoff-roadmap-creator case.
  // Spec: state/review-trail/findings/2026-07-08-the Director of Engineering-origin-handoff-forked-from-reconciliation.md

  it('C2-5 positive: forked_from and origin_handoff both set and equal PASSES', () => {
    const fm = baseSpinoffWithOrigin({
      forked_from: 'state/handoffs/2026-07-06-parent-baton.md',
      origin_handoff: 'state/handoffs/2026-07-06-parent-baton.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `forked_from and origin_handoff equal should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  // Review: code-reviewer (F3) — positive test proving the backslash/forward-slash
  // normalisation actually fires and prevents a false-positive divergence report,
  // rather than only asserting the same-string equal case above.
  it('C2-5 positive: forked_from (backslashes) and origin_handoff (forward slashes) naming the SAME file PASSES (normalisation fires)', () => {
    const fm = baseSpinoffWithOrigin({
      forked_from: 'state\\handoffs\\2026-07-06-parent-baton.md',
      origin_handoff: 'state/handoffs/2026-07-06-parent-baton.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `forked_from and origin_handoff naming the same file via different slash directions should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-5 negative: forked_from and origin_handoff both set but DIFFERENT is REJECTED', () => {
    const fm = baseSpinoffWithOrigin({
      forked_from: 'state/handoffs/2026-07-06-parent-baton.md',
      origin_handoff: 'state/handoffs/2026-07-05-different-baton.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'forked_from and origin_handoff disagreeing should be rejected');
    const err = (result.errors || []).find(e => e.field === 'origin_handoff');
    assert.ok(err, `Expected C2-5 lineage-integrity error on origin_handoff. Got: ${JSON.stringify(result.errors)}`);
    assert.match(err.error, /lineage-integrity divergence/);
    assert.match(err.error, /C2-5/);
  });

  it('C2-5 positive: origin_handoff set + forked_from absent on kind=spinoff-goal PASSES (no coupling)', () => {
    const fm = Object.assign({
      title: 'Goal spinoff with origin_handoff but no forked_from',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff-goal',
      category: 'roadmap',
      summary: 'Goal-scoped spinoff — forked_from is validation-illegal on this kind',
      origin_session: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      origin_handoff: 'state/handoffs/2026-07-06-parent-baton.md',
      origin_plan_id: 'pln-structured-originating-session-8b505c',
      origin_goal_id: ['goal-example-game-repo-shipping-velocity'],
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `origin_handoff without forked_from on spinoff-goal should pass (no presence-coupling). Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C2-5 positive: forked_from set + origin_handoff absent on kind=spinoff PASSES', () => {
    const fm = {
      title: 'Spinoff with forked_from but no origin_handoff',
      created: '2026-07-07',
      branch: 'work/striker/2026-07-07',
      status: 'active',
      predecessor: 'none',
      kind: 'spinoff',
      category: 'roadmap',
      summary: 'Spinoff with only forked_from set — origin_handoff absent',
      forked_from: 'state/handoffs/2026-07-06-parent-baton.md',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `forked_from without origin_handoff should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  // --- C3: origin_* universal conflation rule (non-spinoff kinds) ---
  // C2-4 (above) rejects origin_* + real predecessor co-occurrence but is scoped to
  // spinoff kinds only. The doctrine ("origin_* is a DISTINCT axis, must not be
  // conflated") is universal — C3 extends the invariant to non-spinoff kinds
  // (session-handoff, recovery) via normalise(origin_handoff) === normalise(predecessor),
  // reusing C2-5's backslash-normalisation helper. origin_session/origin_plan_id/
  // origin_goal_id stay OUT — they are cross-entity refs, not state/handoffs/ paths,
  // so they cannot conflate with a handoff-path predecessor.
  // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C3

  it('C3 negative: session-handoff with origin_handoff === predecessor (conflated) is REJECTED', () => {
    const fm = baseSessionHandoff({
      predecessor: 'state/handoffs/2026-07-06-prior.md',
      origin_handoff: 'state/handoffs/2026-07-06-prior.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'session-handoff with origin_handoff equal to predecessor should be rejected');
    const err = (result.errors || []).find(
      e => e.field === 'origin_handoff' && e.error && e.error.includes('C3')
    );
    assert.ok(err, `Expected C3 conflation error on origin_handoff. Got: ${JSON.stringify(result.errors)}`);
  });

  it('C3 negative: recovery kind with origin_handoff === predecessor (conflated, backslash-normalised) is REJECTED', () => {
    const fm = {
      title: 'Recovery baton with conflated origin_handoff',
      created: '2026-07-08',
      branch: 'work/striker/2026-07-08',
      status: 'active',
      predecessor: 'state\\handoffs\\2026-07-06-crashed.md',
      kind: 'recovery',
      category: 'infra',
      summary: 'Recovery baton — origin_handoff conflated with predecessor via slash-direction mismatch',
      origin_handoff: 'state/handoffs/2026-07-06-crashed.md',
    };
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'recovery with origin_handoff normalising equal to predecessor should be rejected');
    const err = (result.errors || []).find(
      e => e.field === 'origin_handoff' && e.error && e.error.includes('C3')
    );
    assert.ok(err, `Expected C3 conflation error on origin_handoff. Got: ${JSON.stringify(result.errors)}`);
  });

  it('C3 positive: session-handoff with origin_handoff pointing at a DIFFERENT baton than predecessor PASSES', () => {
    const fm = baseSessionHandoff({
      predecessor: 'state/handoffs/2026-07-06-prior.md',
      origin_handoff: 'state/handoffs/2026-07-01-originating-session.md',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `session-handoff with distinct origin_handoff and predecessor should pass. Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C3 positive: session-handoff with origin_session/origin_plan_id/origin_goal_id set (cross-entity refs) — C3 does NOT fire', () => {
    // origin_session/origin_plan_id/origin_goal_id are cross-entity refs (not state/handoffs/
    // paths), so they cannot conflate with a handoff-path predecessor even if a caller
    // mistakenly expects them to participate in this rule.
    const fm = baseSessionHandoff({
      predecessor: 'state/handoffs/2026-07-06-prior.md',
      origin_session: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      origin_plan_id: 'pln-structured-originating-session-8b505c',
      origin_goal_id: ['goal-example-game-repo-shipping-velocity'],
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `session-handoff with only cross-entity origin_* fields should pass (C3 no-op). Errors: ${JSON.stringify(result.errors)}`);
  });

  it('C3 positive: spinoff kind is unaffected by C3 (spinoff kinds handled by C2-4, not C3)', () => {
    // Spinoff kinds already reject origin_* + non-none predecessor via C2-4. C3 targets
    // the non-spinoff scoping hole only — this pins that C3 does not double-fire or
    // otherwise interfere with the spinoff-kind path.
    const fm = baseSpinoffWithOrigin({ predecessor: 'none' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Spinoff with origin_* + predecessor:none should still pass under C3. Errors: ${JSON.stringify(result.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// validateFrontmatter — handoff predecessor_id / origin_handoff_id (C2)
// ID-companion field shape validation (JSON-Schema-backed pattern:
// ^hnd-[a-z0-9-]+-[0-9a-f]{6}$). Authored here per the "C3 owns the C2 ID-field-
// validation fixture" rule in docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C2.
// ---------------------------------------------------------------------------

describe('validateFrontmatter — handoff predecessor_id / origin_handoff_id shape (C2 fixture, authored by C3)', () => {
  const handoffSchema = SCHEMAS['handoff'];

  function baseHandoff(overrides = {}) {
    return Object.assign({
      title: 'ID-companion field shape test',
      created: '2026-07-08',
      branch: 'work/test/2026-07-08',
      status: 'active',
      predecessor: null,
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Exercises predecessor_id/origin_handoff_id shape validation',
    }, overrides);
  }

  it('well-formed predecessor_id (hnd-<slug>-<6hex>) PASSES', () => {
    const fm = baseHandoff({ predecessor: 'state/handoffs/2026-07-07-prior.md', predecessor_id: 'hnd-prior-baton-1a2b3c' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Well-formed predecessor_id should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('null predecessor_id PASSES (optional, string-or-null)', () => {
    const fm = baseHandoff({ predecessor_id: null });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Null predecessor_id should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('malformed predecessor_id (missing hex suffix) FAILS', () => {
    const fm = baseHandoff({ predecessor: 'state/handoffs/2026-07-07-prior.md', predecessor_id: 'hnd-prior-baton' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'Malformed predecessor_id (no 6-hex suffix) should fail shape validation');
  });

  it('malformed predecessor_id (wrong prefix) FAILS', () => {
    const fm = baseHandoff({ predecessor: 'state/handoffs/2026-07-07-prior.md', predecessor_id: 'pln-prior-baton-1a2b3c' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'predecessor_id with a non-hnd- prefix should fail shape validation');
  });

  it('well-formed origin_handoff_id PASSES', () => {
    const fm = baseHandoff({ origin_handoff: 'state/handoffs/2026-07-01-originator.md', origin_handoff_id: 'hnd-originator-baton-9f8e7d' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(result.ok, `Well-formed origin_handoff_id should pass, got: ${JSON.stringify(result.errors)}`);
  });

  it('malformed origin_handoff_id (uppercase hex) FAILS', () => {
    const fm = baseHandoff({ origin_handoff: 'state/handoffs/2026-07-01-originator.md', origin_handoff_id: 'hnd-originator-baton-9F8E7D' });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.equal(result.ok, false, 'origin_handoff_id with uppercase hex suffix should fail (pattern requires lowercase hex)');
  });
});

// ---------------------------------------------------------------------------
// checkReferentialIntegrity (C3) — resolver-seam existence + never-silently-
// disagree validation for local handoff-DAG ID refs (predecessor_id,
// origin_handoff_id). Separate exported function, NOT wired into
// CROSS_FIELD_RULES/validateFrontmatter/validateRecord — cadence gates call it
// explicitly. Scope: LOCAL handoff-DAG refs only; deliverable_id/initiative are
// deferred (central-state-plane, not local-scanned).
//
// Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C3
// ---------------------------------------------------------------------------

describe('checkReferentialIntegrity (C3)', () => {
  function baseRecord(overrides = {}) {
    return Object.assign({
      title: 'Referential integrity test fixture',
      predecessor: 'state/handoffs/2026-07-01-real-predecessor.md',
      predecessor_id: 'hnd-real-predecessor-1a2b3c',
    }, overrides);
  }

  it('(a) valid ID ref + resolver that finds it → ok (no errors, no warnings)', () => {
    const resolver = (id) => {
      if (id === 'hnd-real-predecessor-1a2b3c') return { path: 'state/handoffs/2026-07-01-real-predecessor.md' };
      return null;
    };
    const result = checkReferentialIntegrity(baseRecord(), resolver);
    assert.deepEqual(result.errors, [], `Expected no errors, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [], `Expected no warnings, got: ${JSON.stringify(result.warnings)}`);
  });

  it('(b) dangling ID ref + resolver, non-gate (strict absent/false) → warns, does NOT error', () => {
    const resolver = () => null; // nothing resolves — every ref is dangling
    const result = checkReferentialIntegrity(baseRecord(), resolver);
    assert.deepEqual(result.errors, [], `Expected no errors outside strict mode, got: ${JSON.stringify(result.errors)}`);
    assert.equal(result.warnings.length, 1, `Expected exactly one warning, got: ${JSON.stringify(result.warnings)}`);
    assert.equal(result.warnings[0].field, 'predecessor_id');
  });

  it('(c) dangling ID ref + resolver, gate/strict:true → errors (hard-block)', () => {
    const resolver = () => null;
    const result = checkReferentialIntegrity(baseRecord(), resolver, { strict: true });
    assert.equal(result.errors.length, 1, `Expected exactly one error under strict mode, got: ${JSON.stringify(result.errors)}`);
    assert.equal(result.errors[0].field, 'predecessor_id');
    assert.deepEqual(result.warnings, [], 'Strict mode should not also emit a warning for the same dangling ref');
  });

  it('(d) no resolver supplied → shape-only, no existence error even with an ID ref present', () => {
    const result = checkReferentialIntegrity(baseRecord()); // resolver omitted
    assert.deepEqual(result.errors, [], `Expected no errors with no resolver, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [], `Expected no warnings with no resolver, got: ${JSON.stringify(result.warnings)}`);
  });

  it('(d2) no resolver supplied + strict:true → still shape-only (resolver absence is not itself an error)', () => {
    const result = checkReferentialIntegrity(baseRecord(), null, { strict: true });
    assert.deepEqual(result.errors, [], `Expected no errors with no resolver even under strict, got: ${JSON.stringify(result.errors)}`);
  });

  it('(e) path/ID companion divergence: ID resolves to a DIFFERENT path than the path field names → flagged (error, regardless of strict)', () => {
    const resolver = (id) => {
      if (id === 'hnd-real-predecessor-1a2b3c') return { path: 'state/handoffs/2026-06-30-some-other-baton.md' };
      return null;
    };
    const result = checkReferentialIntegrity(baseRecord(), resolver); // non-strict
    assert.equal(result.errors.length, 1, `Expected divergence to be a hard error even outside strict, got: ${JSON.stringify(result.errors)}`);
    assert.match(result.errors[0].error, /never-silently-disagree/);
    assert.deepEqual(result.warnings, [], 'Divergence should not also be reported as a warning');
  });

  it('origin_handoff_id pair is checked independently of predecessor_id', () => {
    const fm = {
      title: 'Origin pair test',
      origin_handoff: 'state/handoffs/2026-06-01-originator.md',
      origin_handoff_id: 'hnd-originator-9f8e7d',
    };
    const resolver = () => null;
    const result = checkReferentialIntegrity(fm, resolver);
    assert.equal(result.warnings.length, 1);
    assert.equal(result.warnings[0].field, 'origin_handoff_id');
  });

  it('both predecessor_id and origin_handoff_id dangling → two independent warnings, one per field', () => {
    const fm = {
      title: 'Both pairs dangling',
      predecessor: 'state/handoffs/2026-07-01-real-predecessor.md',
      predecessor_id: 'hnd-real-predecessor-1a2b3c',
      origin_handoff: 'state/handoffs/2026-06-01-originator.md',
      origin_handoff_id: 'hnd-originator-9f8e7d',
    };
    const resolver = () => null;
    const result = checkReferentialIntegrity(fm, resolver);
    assert.equal(result.warnings.length, 2, `Expected two independent warnings, got: ${JSON.stringify(result.warnings)}`);
    const fields = result.warnings.map(w => w.field).sort();
    assert.deepEqual(fields, ['origin_handoff_id', 'predecessor_id']);
  });

  it('ID present but path field absent/null → no divergence check (nothing to compare against)', () => {
    const resolver = () => ({ path: 'state/handoffs/anything.md' });
    const fm = { title: 'ID-only, no path', predecessor: null, predecessor_id: 'hnd-real-predecessor-1a2b3c' };
    const result = checkReferentialIntegrity(fm, resolver);
    assert.deepEqual(result.errors, [], `Expected no divergence error when path field is null, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [], 'ID resolved successfully — no dangling warning either');
  });

  it('resolver returns a match with no path property → existence satisfied, divergence check skipped (nothing to compare)', () => {
    const resolver = () => ({}); // resolved, but no path info supplied
    const result = checkReferentialIntegrity(baseRecord(), resolver);
    assert.deepEqual(result.errors, [], `Expected no errors when resolver supplies no path, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [], 'Existence was satisfied — no dangling warning');
  });

  it('backslash-path normalisation: resolved path and companion path differ only by slash direction → treated as equal (matches C2-5 normalisation)', () => {
    const resolver = () => ({ path: 'state\\handoffs\\2026-07-01-real-predecessor.md' });
    const result = checkReferentialIntegrity(baseRecord(), resolver);
    assert.deepEqual(result.errors, [], `Backslash/forward-slash variants of the same path should not be flagged as divergent, got: ${JSON.stringify(result.errors)}`);
  });

  // Review: code-reviewer — "never both" in the JSDoc holds per-ID-ref only;
  // one pair dangling (non-strict → warning) and the other pair diverging
  // (→ error) can co-occur on the same return (Finding 3).
  it('mixed outcome: predecessor_id dangling (non-strict → warning) + origin_handoff_id diverging (→ error) on the same record simultaneously', () => {
    const fm = {
      title: 'Mixed dangling + diverging',
      predecessor: 'state/handoffs/2026-07-01-real-predecessor.md',
      predecessor_id: 'hnd-real-predecessor-1a2b3c',
      origin_handoff: 'state/handoffs/2026-06-01-originator.md',
      origin_handoff_id: 'hnd-originator-9f8e7d',
    };
    const resolver = (id) => {
      if (id === 'hnd-real-predecessor-1a2b3c') return null; // dangling
      if (id === 'hnd-originator-9f8e7d') return { path: 'state/handoffs/2026-06-30-some-other-baton.md' }; // diverges
      return null;
    };
    const result = checkReferentialIntegrity(fm, resolver); // non-strict
    assert.equal(result.warnings.length, 1, `Expected exactly one warning (dangling predecessor_id), got: ${JSON.stringify(result.warnings)}`);
    assert.equal(result.warnings[0].field, 'predecessor_id');
    assert.equal(result.errors.length, 1, `Expected exactly one error (diverging origin_handoff_id), got: ${JSON.stringify(result.errors)}`);
    assert.equal(result.errors[0].field, 'origin_handoff_id');
    assert.match(result.errors[0].error, /never-silently-disagree/);
  });

  it('deliverable_id and initiative are NOT existence-checked (deferred, central-state-plane scope)', () => {
    const fm = {
      title: 'Deferred-scope fields present',
      deliverable_id: 'dlv-nonexistent-000000',
      initiative: 'nonexistent-initiative',
    };
    const resolver = () => null; // would flag everything if these were in scope
    const result = checkReferentialIntegrity(fm, resolver);
    assert.deepEqual(result.errors, [], 'deliverable_id/initiative must not be existence-checked by this function (out of scope, first cut)');
    assert.deepEqual(result.warnings, [], 'deliverable_id/initiative must not be existence-checked by this function (out of scope, first cut)');
  });

  it('empty record (no ID refs at all) → no-op regardless of resolver/strict', () => {
    const result = checkReferentialIntegrity({ title: 'No refs' }, () => null, { strict: true });
    assert.deepEqual(result.errors, []);
    assert.deepEqual(result.warnings, []);
  });

  // Review: code-reviewer — pins the sentinel-as-absent path distinct from
  // predecessor: null (Finding 2). predecessor: 'none' is the canonical
  // spinoff sentinel; isSet() excludes it, so the divergence check is
  // skipped even though predecessor_id resolves to a real (non-none) path —
  // only the dangling/existence check runs.
  it("predecessor: 'none' (sentinel) + non-null predecessor_id, resolver resolves to a real path → no divergence error (sentinel-as-absent path skipped)", () => {
    const resolver = (id) => {
      if (id === 'hnd-real-predecessor-1a2b3c') return { path: 'state/handoffs/2026-07-01-real-predecessor.md' };
      return null;
    };
    const fm = { title: 'Sentinel predecessor with ID', predecessor: 'none', predecessor_id: 'hnd-real-predecessor-1a2b3c' };
    const result = checkReferentialIntegrity(fm, resolver);
    assert.deepEqual(result.errors, [], `Expected no divergence error when predecessor is the 'none' sentinel, got: ${JSON.stringify(result.errors)}`);
    assert.deepEqual(result.warnings, [], 'ID resolved successfully — no dangling warning either');
  });
});
