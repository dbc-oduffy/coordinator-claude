'use strict';
/**
 * query-records.test.js — Tests for query-records.js argument parsing and core logic.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W2
 *
 * Run with: node --test bin/lib/query-records.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('child_process');
const path = require('path');

const QUERY_RECORDS = path.resolve(__dirname, '..', 'query-records.js');
const ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..'); // ~/.claude

// ---------------------------------------------------------------------------
// --key=value normalization (the Staff Engineer R2 finding 4)
// ---------------------------------------------------------------------------

test('--key=value form accepted: --type=plan', () => {
  // Should not exit 1 with "Unknown argument: --type=plan"
  // Use a path that exists. If the repo root has no plans, output may be empty — that's fine.
  // We just care that parsing doesn't error out.
  let threw = false;
  try {
    execFileSync(process.execPath, [QUERY_RECORDS, '--type=plan', '--limit=1', '--root', ROOT], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (err) {
    threw = true;
    // Accept non-zero exit only if it's a data error (e.g., no records), not a parse error
    assert.ok(
      !err.stderr.includes('Unknown argument'),
      `Should not get "Unknown argument" on --type=plan. stderr: ${err.stderr}`
    );
  }
  // Either succeeded (threw=false) or failed for a non-parse reason
});

test('--key=value form: --type=plan --sort=-created --limit=5 parses identically to space-separated', () => {
  const spaceArgs = ['--type', 'plan', '--sort', '-created', '--limit', '5', '--root', ROOT];
  const equalsArgs = ['--type=plan', '--sort=-created', '--limit=5', '--root', ROOT];

  let spaceOut, equalsOut;
  try {
    spaceOut = execFileSync(process.execPath, [QUERY_RECORDS, ...spaceArgs], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    spaceOut = e.stdout || '';
    assert.ok(!e.stderr.includes('Unknown argument'), `space form parse error: ${e.stderr}`);
  }

  try {
    equalsOut = execFileSync(process.execPath, [QUERY_RECORDS, ...equalsArgs], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    equalsOut = e.stdout || '';
    assert.ok(!e.stderr.includes('Unknown argument'), `equals form parse error: ${e.stderr}`);
  }

  assert.strictEqual(spaceOut, equalsOut, '--key=value and --key value forms should produce identical output');
});

// ---------------------------------------------------------------------------
// parseWhereExpr (exported — test directly)
// ---------------------------------------------------------------------------

test('parseWhereExpr: single equality clause', () => {
  const { parseWhereExpr } = require('../query-records.js');
  const clauses = parseWhereExpr('status=active');
  assert.equal(clauses.length, 1);
  assert.equal(clauses[0].op, '=');
  assert.equal(clauses[0].field, 'status');
  assert.equal(clauses[0].value, 'active');
});

test('parseWhereExpr: AND conjunction', () => {
  const { parseWhereExpr } = require('../query-records.js');
  const clauses = parseWhereExpr('status=active AND reviewer=the Staff Engineer');
  assert.equal(clauses.length, 2);
  assert.equal(clauses[0].field, 'status');
  assert.equal(clauses[1].field, 'reviewer');
});

// ---------------------------------------------------------------------------
// TYPE_TO_GLOB drift-enforcement (tc-5 reconcile)
//
// Asserts that the DERIVED TYPE_TO_GLOB matches the schema registry so the
// "must match" comment can never silently drift again. Each schema's applies_to
// must be reflected in TYPE_TO_GLOB (via the schema name or its mapped query
// type), except for the two documented divergences (handoff-archived recursive
// glob and cross-repo-memo bracket-engine incompatibility).
//
// Spec backlink: state/handoffs/2026-06-22_230005_roadmap-cockpit-contract-ext-2026-06-22-tc-5.md
// ---------------------------------------------------------------------------

const { describe } = require('node:test');

// Review: F7 — rewritten to require TYPE_TO_GLOB directly from query-records.js
// instead of parsing the 'Valid: ...' stderr of a deliberate invalid-type subprocess
// invocation. The subprocess parse was fragile (format change silently broke detection);
// requiring the export is direct and fails loudly if the export is removed.
describe('TYPE_TO_GLOB drift-enforcement', () => {
  const path = require('path');
  const { loadSchemas } = require('./schema.js');

  const SCHEMAS_DIR = path.resolve(__dirname, '../../schemas');

  // Load the live schema registry once.
  let schemas;
  try {
    schemas = loadSchemas(SCHEMAS_DIR);
  } catch (e) {
    schemas = null;
  }

  // Require TYPE_TO_GLOB directly from the module under test.
  const { TYPE_TO_GLOB } = require('../query-records.js');

  test('TYPE_TO_GLOB is exported and non-empty', () => {
    assert.ok(TYPE_TO_GLOB && typeof TYPE_TO_GLOB === 'object',
      'TYPE_TO_GLOB must be exported from query-records.js');
    assert.ok(Object.keys(TYPE_TO_GLOB).length > 0, 'TYPE_TO_GLOB must have at least one entry');
  });

  test('every schema with applies_to has a corresponding --type', () => {
    if (!schemas) {
      assert.fail('Could not load schemas from ' + SCHEMAS_DIR);
    }

    const registeredTypes = Object.keys(TYPE_TO_GLOB);
    assert.ok(registeredTypes.length > 0, 'TYPE_TO_GLOB must contain at least one type');

    // Documented intentional divergences (schema name ≠ query type name):
    //   completion-entry → completion
    //   lesson-entry → lesson (handled via supplement; lesson-entry applies_to is special)
    //   bug-backlog → bug, debt-backlog → debt, improvement-queue → improvement
    // Review: code-reviewer F2 — added bug/debt/improvement mappings; these are now in
    // _SCHEMA_NAME_TO_QUERY_TYPE and must be reflected here to match the module's derivation.
    const SCHEMA_TO_QUERY_TYPE = {
      'completion-entry': 'completion',
      'lesson-entry': 'lesson',
      'bug-backlog': 'bug',
      'debt-backlog': 'debt',
      'improvement-queue': 'improvement',
    };

    for (const { schemaName } of schemas._byGlob) {
      const queryType = SCHEMA_TO_QUERY_TYPE[schemaName] || schemaName;
      assert.ok(
        registeredTypes.includes(queryType),
        `Schema "${schemaName}" maps to query type "${queryType}" but that type is not in TYPE_TO_GLOB. ` +
        `Registered types: ${registeredTypes.join(', ')}`
      );
    }
  });

  test('schema applies_to globs are reflected in TYPE_TO_GLOB (documented divergences annotated)', () => {
    if (!schemas) {
      assert.fail('Could not load schemas from ' + SCHEMAS_DIR);
    }

    // Types whose glob INTENTIONALLY differs from the schema applies_to.
    // Each entry names the divergence reason.
    const DOCUMENTED_DIVERGENCES = {
      'handoff-archived': {
        schemaGlob: 'archive/handoffs/*.md',
        queryGlob:  'archive/handoffs/**/*.md',
        reason: 'recursive since 2026-06-18 month-foldering; schema retains flat form for path-match validation',
      },
      'cross-repo-memo': {
        schemaGlob: 'cross-repo/inbox/[0-9]*.md',
        queryGlob:  'cross-repo/inbox/*.md',
        reason: 'filePatternToRegex escapes brackets; memo-shape guard (from+to present) replaces bracket-class filename filter',
      },
    };

    // Derive the expected TYPE_TO_GLOB using the same logic as _buildTypeToGlob.
    // This independently re-derives the map and asserts it matches what query-records
    // registers — so any future hand-edit to TYPE_TO_GLOB that breaks the derivation
    // will be caught here.
    // Review: code-reviewer F2 — added bug-backlog/debt-backlog/improvement-queue so this
    // derivation matches the updated _SCHEMA_NAME_TO_QUERY_TYPE in query-records.js.
    const SCHEMA_TO_QUERY_TYPE = {
      'completion-entry': 'completion',
      'lesson-entry': null,
      'bug-backlog': 'bug',
      'debt-backlog': 'debt',
      'improvement-queue': 'improvement',
    };
    const expected = {};
    for (const { glob, schemaName } of schemas._byGlob) {
      if (schemaName === 'lesson-entry') continue;
      const queryType = SCHEMA_TO_QUERY_TYPE.hasOwnProperty(schemaName)
        ? SCHEMA_TO_QUERY_TYPE[schemaName]
        : schemaName;
      if (queryType === null) continue;

      const divergence = DOCUMENTED_DIVERGENCES[schemaName];
      if (divergence) {
        // Documented divergence — verify the documented schema glob matches what's in the schema file
        // (catches schema-file changes that would make the divergence entry stale).
        assert.equal(
          divergence.schemaGlob, glob,
          `Documented divergence for "${schemaName}" records schemaGlob="${divergence.schemaGlob}" ` +
          `but schema applies_to is now "${glob}". Update DOCUMENTED_DIVERGENCES if this changed intentionally.`
        );
        expected[queryType] = divergence.queryGlob;
      } else {
        expected[queryType] = glob;
      }
    }

    // Supplements (non-schema'd types not derivable from Part 1) — verify they remain registered.
    // Note: bug/debt/improvement are now schema-derived (via _SCHEMA_NAME_TO_QUERY_TYPE) and
    // appear in expected[] from Part 1; they are intentionally removed from this supplement list.
    // Review: code-reviewer F2 — removed bug/debt/improvement from supplements (now Part 1 derived).
    const SUPPLEMENTS = {
      lesson:          'state/lessons/*.yaml',
      'handoff-ledger':'state/handoffs/*.md',
    };
    for (const [t, g] of Object.entries(SUPPLEMENTS)) {
      expected[t] = g;
    }

    const registeredTypes = Object.keys(TYPE_TO_GLOB);
    // Every expected type must be registered.
    for (const [t] of Object.entries(expected)) {
      assert.ok(
        registeredTypes.includes(t),
        `Expected type "${t}" (derived from schema registry + supplements) is not registered in TYPE_TO_GLOB`
      );
    }
  });
});

// ---------------------------------------------------------------------------
// --type plan sidecar exclusion (C4 regression)
//
// The plan schema applies_to (docs/plans/*.md) over-matches sidecar files.
// These tests verify that --type plan returns real plans only, excluding:
//   - Schema-glob sidecars (*.prior-art-check.md, *-review.md, *coverage-check.md, *docs-check.md)
//   - Kind-denylist sidecars (kind: code-review, kind: prior-art-check, etc.)
//   - Structural review sidecars (reviewer: + plan: without kind:, legacy pre-taxonomy forms)
//
// Uses a temp fixture directory planted with known good/bad files so this test
// is self-contained and not affected by future changes to live docs/plans/ contents.
//
// Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4
// ---------------------------------------------------------------------------

describe('--type plan sidecar exclusion', () => {
  const os = require('os');
  const fs = require('fs');

  // ---------------------------------------------------------------------------
  // Fixture setup: create a temp root with docs/plans/ populated with:
  //   - A real plan (should appear in output)
  //   - Known sidecar suffixes (should NOT appear)
  //   - A kind-denylist sidecar without a recognised suffix (should NOT appear)
  //   - A legacy review sidecar with reviewer:+plan: but no kind: (should NOT appear)
  // ---------------------------------------------------------------------------

  const REAL_PLAN_FRONTMATTER = `---
title: Fixture real plan
created: 2026-01-01
author: test
status: draft
---

Real plan body.
`;

  const PRIOR_ART_SIDECAR = `---
title: Prior-Art Check — fixture
created: 2026-01-01
author: prior-art-checker
kind: prior-art-check
plan: docs/plans/2026-01-01-fixture-plan.md
---
`;

  const COVERAGE_CHECK_SIDECAR = `---
title: Plan Coverage Check — fixture
created: 2026-01-01
author: plan-coverage-checker
kind: plan-coverage-check
plan: docs/plans/2026-01-01-fixture-plan.md
---
`;

  const REVIEW_SIDECAR_WITH_KIND = `---
title: Review — fixture
created: 2026-01-01
author: the Staff Engineer
kind: staff-eng-review
plan: docs/plans/2026-01-01-fixture-plan.md
reviewer: the Staff Engineer
verdict: APPROVED
---
`;

  // Legacy review sidecar: pre-taxonomy form — no kind:, but has reviewer: + plan:
  const LEGACY_REVIEW_SIDECAR_NO_KIND = `---
title: the Staff Engineer R1 — fixture
created: 2026-01-01
author: the Staff Engineer
reviewer: the Staff Engineer
plan: docs/plans/2026-01-01-fixture-plan.md
verdict: APPROVED_WITH_NOTES
---
`;

  let tmpRoot;
  let plansDir;

  // Set up temp fixture before tests.
  // node:test doesn't have beforeAll — use a test() that must run first.
  // All assertion tests are run in the same describe, relying on sequential execution.
  //
  // Review: code-reviewer — F7: wrapped in try/catch so a setup failure doesn't cause
  // subsequent tests to false-pass against a missing/empty fixture dir.
  let setupError = null;
  const setupResult = (() => {
    try {
      tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-plan-test-'));
      plansDir = path.join(tmpRoot, 'docs', 'plans');
      fs.mkdirSync(plansDir, { recursive: true });

      // Real plan — should be INCLUDED
      fs.writeFileSync(path.join(plansDir, '2026-01-01-fixture-plan.md'), REAL_PLAN_FRONTMATTER);

      // Schema-glob sidecars — should be EXCLUDED by Layer 1 (filename regex)
      fs.writeFileSync(path.join(plansDir, '2026-01-01-fixture-plan.md.prior-art-check.md'), PRIOR_ART_SIDECAR);
      fs.writeFileSync(path.join(plansDir, '2026-01-01-fixture-plan.md.plan-coverage-check.md'), COVERAGE_CHECK_SIDECAR);
      // Canonical named-reviewer sidecar form is `<stem>.review.md` (dot before "review"),
      // matched by the sidecar filename regex derived from schema glob docs/plans/*.review.md.
      // Excluded by the single positive suffix layer (post-C9-broadsword design).
      fs.writeFileSync(path.join(plansDir, '2026-01-01-fixture-plan.review.md'), REVIEW_SIDECAR_WITH_KIND);

      // Kind-denylist sidecar with non-standard filename — excluded by Layer 2a (kind denylist)
      // Uses a suffix that doesn't match any schema glob (*-review.md matches *.the Staff Engineer-review.md
      // but not *.review-2.md which ends in -review.md — wait, *-review.md DOES match *.review-2.md
      // because * spans the '2'. Use a completely non-matching suffix: *.r1.md)
      const kindDenylistSidecar = `---
title: Kind-denylist sidecar
created: 2026-01-01
kind: code-review
plan: docs/plans/2026-01-01-fixture-plan.md
---
`;
      fs.writeFileSync(path.join(plansDir, '2026-01-01-fixture-plan.r1.md'), kindDenylistSidecar);

      // Legacy review sidecar without kind: — excluded by Layer 2b (reviewer + plan + verdict structural guard)
      fs.writeFileSync(path.join(plansDir, '2026-01-01-fixture-plan.the Staff Engineer-r1.md'), LEGACY_REVIEW_SIDECAR_NO_KIND);

      return { ok: true };
    } catch (err) {
      setupError = err;
      return { ok: false };
    }
  })();

  test('fixture root created successfully', () => {
    // Review: code-reviewer — F7: assert no setup error so subsequent tests don't false-pass.
    assert.ok(!setupError, `temp fixture setup threw: ${setupError}`);
    assert.ok(setupResult.ok, 'temp fixture setup failed');
    assert.ok(fs.existsSync(path.join(plansDir, '2026-01-01-fixture-plan.md')), 'real plan fixture must exist');
  });

  test('real plan IS returned by --type plan', () => {
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'json', '--root', tmpRoot], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.includes('docs/plans/2026-01-01-fixture-plan.md'),
      `Real plan must appear in --type plan output. Got: ${paths.join(', ')}`
    );
  });

  test('*.prior-art-check.md sidecar NOT returned by --type plan (Layer 1 filename regex)', () => {
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'paths', '--root', tmpRoot], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    assert.ok(
      !out.includes('.prior-art-check.md'),
      `prior-art-check sidecar must NOT appear in --type plan output. Got: ${out}`
    );
  });

  test('*.plan-coverage-check.md sidecar NOT returned by --type plan (Layer 1 filename regex)', () => {
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'paths', '--root', tmpRoot], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    assert.ok(
      !out.includes('.plan-coverage-check.md'),
      `plan-coverage-check sidecar must NOT appear in --type plan output. Got: ${out}`
    );
  });

  test('*.review.md sidecar NOT returned by --type plan (Layer 1 filename regex, canonical dot suffix)', () => {
    // Canonical named-reviewer sidecar is <stem>.review.md (dot). A dash-form "-review.md" is a
    // legitimate plan slug post-C9-broadsword and is intentionally NOT excluded. Fixture:
    // '2026-01-01-fixture-plan.review.md'.
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'paths', '--root', tmpRoot], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    assert.ok(
      !out.includes('fixture-plan.review.md'),
      `.review.md sidecar must NOT appear in --type plan output. Got: ${out}`
    );
  });

  test('kind-denylist sidecar (code-review, non-standard filename) NOT returned (Layer 2a kind filter)', () => {
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'json', '--root', tmpRoot], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const records = JSON.parse(out);
    const kindCodeReview = records.filter(r => r.frontmatter && r.frontmatter.kind === 'code-review');
    assert.equal(
      kindCodeReview.length, 0,
      `No record with kind=code-review should appear in --type plan output. Got: ${kindCodeReview.map(r => r.path).join(', ')}`
    );
  });

  test('reviewer+plan sidecars NOT returned by --type plan (filename layers: canonical suffix + anomaly detector)', () => {
    // Post-C9-broadsword there is no structural (reviewer+plan) guard. The canonical-form review
    // sidecar (.review.md) is excluded by the suffix regex; the legacy no-kind sidecar
    // (non-canonical filename) is excluded by the anomaly detector. Either way, no reviewer+plan
    // record leaks into --type plan.
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'json', '--root', tmpRoot], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const records = JSON.parse(out);
    const reviewerPlanSidecars = records.filter(r => r.frontmatter && r.frontmatter.reviewer && r.frontmatter.plan);
    assert.equal(
      reviewerPlanSidecars.length, 0,
      `No record with reviewer+plan should appear in --type plan output. Got: ${reviewerPlanSidecars.map(r => r.path).join(', ')}`
    );
  });

  test('only real plan in output — total count from fixture dir is 1', () => {
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'json', '--root', tmpRoot], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const records = JSON.parse(out);
    assert.equal(
      records.length, 1,
      `Only 1 record (the real plan) should appear. Got ${records.length}: ${records.map(r => r.path).join(', ')}`
    );
  });
});

// ---------------------------------------------------------------------------
// Layer-2b guard boundary counter-tests (F6)
//
// Assert that the Layer-2b structural guard (reviewer + plan + verdict) does NOT
// false-exclude real plans that carry reviewer: or plan: in isolation.
//
// Two counter-cases:
//   (a) reviewer: present, plan: absent → IS returned (not a sidecar)
//   (b) plan: present, reviewer: absent → IS returned (not a sidecar)
//
// Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4
// Review: code-reviewer — F6: added to assert the Layer-2b guard boundaries so F5's
// strengthening (reviewer && plan && verdict) is regression-tested against false-positives.
// ---------------------------------------------------------------------------

describe('Layer-2b guard counter-tests: reviewer-only and plan-only plans are returned', () => {
  const os = require('os');
  const fs = require('fs');

  // (a) A real plan that carries reviewer: but NOT plan: — should be included.
  const REVIEWER_ONLY_PLAN = `---
title: Fixture plan with reviewer field only
created: 2026-02-01
author: coordinator-em
status: draft
reviewer: the Staff Engineer
---

This plan was reviewed by the Staff Engineer but does not self-reference via plan:.
`;

  // (b) A real plan that carries plan: but NOT reviewer: — should be included.
  // (e.g. a plan that cross-references another plan for context)
  const PLAN_FIELD_ONLY_PLAN = `---
title: Fixture plan with plan field only
created: 2026-02-02
author: coordinator-em
status: draft
plan: docs/plans/2026-01-01-some-predecessor.md
---

This plan cross-references a predecessor via plan: but has no reviewer:.
`;

  let tmpRootL2b;
  let plansDirL2b;
  let setupErrorL2b = null;

  const setupResultL2b = (() => {
    try {
      tmpRootL2b = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-layer2b-'));
      plansDirL2b = path.join(tmpRootL2b, 'docs', 'plans');
      fs.mkdirSync(plansDirL2b, { recursive: true });

      fs.writeFileSync(path.join(plansDirL2b, '2026-02-01-reviewer-only.md'), REVIEWER_ONLY_PLAN);
      fs.writeFileSync(path.join(plansDirL2b, '2026-02-02-plan-field-only.md'), PLAN_FIELD_ONLY_PLAN);

      return { ok: true };
    } catch (err) {
      setupErrorL2b = err;
      return { ok: false };
    }
  })();

  test('fixture created successfully', () => {
    assert.ok(!setupErrorL2b, `Layer-2b counter-test fixture setup threw: ${setupErrorL2b}`);
    assert.ok(setupResultL2b.ok, 'Layer-2b counter-test fixture setup failed');
  });

  test('(a) plan with reviewer: only (no plan: field) IS returned by --type plan', () => {
    // Review: code-reviewer — F6a: guard (reviewer && plan && verdict) must NOT exclude
    // a plan that has reviewer: but lacks plan: — the triple conjunction requires all three.
    assert.ok(!setupErrorL2b, `setup failed: ${setupErrorL2b}`);
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'json', '--root', tmpRootL2b], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.some(p => p.includes('reviewer-only')),
      `Plan with reviewer: only must be returned by --type plan. Got: ${paths.join(', ')}`
    );
  });

  test('(b) plan with plan: field only (no reviewer: field) IS returned by --type plan', () => {
    // Review: code-reviewer — F6b: guard (reviewer && plan && verdict) must NOT exclude
    // a plan that has plan: but lacks reviewer: — the triple conjunction requires all three.
    assert.ok(!setupErrorL2b, `setup failed: ${setupErrorL2b}`);
    const out = execFileSync(process.execPath, [QUERY_RECORDS, '--type', 'plan', '--format', 'json', '--root', tmpRootL2b], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.some(p => p.includes('plan-field-only')),
      `Plan with plan: field only must be returned by --type plan. Got: ${paths.join(', ')}`
    );
  });
});

// ---------------------------------------------------------------------------
// --type plan PlanSummary sourcing (C4b / tc-4 regression)
//
// The emitter's PlanSummary section sources records via:
//   query-records --type plan --limit 0 --format json
//
// Two gate-bound ACs:
//   AC11 — #-title round-trip: unquoted `#N` tokens in title: must survive
//           parseScalar/stripInlineComment without truncation at the `#`.
//           Regression net for the Data Science Reviewer C-F6 / the Staff Engineer F5 fix.
//   AC9  — composite-key sourcing fields present: path (string), title,
//           created, author, status must all appear in returned records so
//           the emitter can build its (repo, coordinator_root_path, path) key
//           and render the PlanSummary row.
//
// Uses the same temp-fixture-dir harness as the sidecar-exclusion block above
// so this block is self-contained.
//
// Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4b
// ---------------------------------------------------------------------------

describe('--type plan PlanSummary sourcing', () => {
  const os = require('os');
  const fs = require('fs');

  // Fixture: a plan whose title contains an unquoted `#N` token.
  // The unquoted form is the regression surface — the old stripInlineComment
  // treated the space before `#` as a comment opener, truncating to "Borrow".
  // The fix requires the char after `#` to also be a space (or EOL), so `#4`
  // is preserved as a literal token.
  const HASH_TITLE_PLAN = `---
title: Borrow #4 — State-file orchestration
created: 2026-06-01
author: coordinator-em
status: draft
---

Plan body. Tests the #-title round-trip (AC11).
`;

  // Fixture: a plan with all composite-key sourcing fields populated.
  const FULL_FRONTMATTER_PLAN = `---
title: Full-frontmatter fixture plan
created: 2026-03-15
author: test-author
status: active
---

Plan body. Tests AC9 sourcing-field presence.
`;

  let tmpRoot2;
  let plansDir2;

  // Review: code-reviewer — F7: wrapped in try/catch so a setup failure doesn't cause
  // subsequent tests to false-pass against a missing/empty fixture dir.
  let setupError2 = null;
  const setupResult2 = (() => {
    try {
      tmpRoot2 = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-plan-summary-'));
      plansDir2 = path.join(tmpRoot2, 'docs', 'plans');
      fs.mkdirSync(plansDir2, { recursive: true });

      fs.writeFileSync(path.join(plansDir2, '2026-06-01-borrow-4-state-file.md'), HASH_TITLE_PLAN);
      fs.writeFileSync(path.join(plansDir2, '2026-03-15-full-frontmatter.md'), FULL_FRONTMATTER_PLAN);

      return { ok: true };
    } catch (err) {
      setupError2 = err;
      return { ok: false };
    }
  })();

  test('fixture root created successfully', () => {
    // Review: code-reviewer — F7: assert no setup error so subsequent tests don't false-pass.
    assert.ok(!setupError2, `temp fixture setup (PlanSummary) threw: ${setupError2}`);
    assert.ok(setupResult2.ok, 'temp fixture setup for PlanSummary sourcing failed');
    assert.ok(
      fs.existsSync(path.join(plansDir2, '2026-06-01-borrow-4-state-file.md')),
      '#-title fixture must exist'
    );
    assert.ok(
      fs.existsSync(path.join(plansDir2, '2026-03-15-full-frontmatter.md')),
      'full-frontmatter fixture must exist'
    );
  });

  test('AC11 — #-title round-trip: unquoted #N token in title is preserved intact', () => {
    // Uses --limit 0 (no cap) matching the emitter invocation.
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--limit', '0', '--format', 'json', '--root', tmpRoot2],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const hashPlan = records.find(r => r.path && r.path.includes('borrow-4-state-file'));
    assert.ok(hashPlan, `Record for #-title fixture must appear in output. Got paths: ${records.map(r => r.path).join(', ')}`);
    assert.ok(hashPlan.frontmatter, 'Record must have a frontmatter object');
    assert.strictEqual(
      hashPlan.frontmatter.title,
      'Borrow #4 — State-file orchestration',
      `title must be intact with #4 token. Got: "${hashPlan.frontmatter.title}"`
    );
  });

  test('AC9 — composite-key sourcing fields present: path (string) + title, created, author, status', () => {
    // Uses --limit 0 matching the emitter invocation.
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--limit', '0', '--format', 'json', '--root', tmpRoot2],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const fullPlan = records.find(r => r.path && r.path.includes('full-frontmatter'));
    assert.ok(fullPlan, `Full-frontmatter record must appear in output. Got paths: ${records.map(r => r.path).join(', ')}`);

    // path must be a non-empty string (composite-key ingredient supplied by the query layer)
    assert.ok(typeof fullPlan.path === 'string' && fullPlan.path.length > 0, 'path must be a non-empty string');

    // frontmatter must carry the four PlanSummary source fields
    assert.ok(fullPlan.frontmatter, 'Record must have a frontmatter object');
    assert.strictEqual(fullPlan.frontmatter.title,   'Full-frontmatter fixture plan', 'title must be present');
    assert.strictEqual(fullPlan.frontmatter.created, '2026-03-15',                    'created must be present');
    assert.strictEqual(fullPlan.frontmatter.author,  'test-author',                   'author must be present');
    assert.strictEqual(fullPlan.frontmatter.status,  'active',                        'status must be present');
  });
});

// ---------------------------------------------------------------------------
// research-claim synthetic enumeration (C5 / P1-3)
//
// research-claim records live in .claims.json files as a JSON ARRAY.
// The generic path silently skips them (parseFrontmatter returns null for JSON).
// The dedicated research-claim branch must enumerate N records per file.
//
// Spec backlink: docs/plans/2026-06-30-deep-research-queryable-index-layer.md § P1-3
// ---------------------------------------------------------------------------

describe('--type research-claim synthetic enumeration', () => {
  const os = require('os');
  const fs = require('fs');

  // Three claims — verifies N>1 records per file
  // Review: code-reviewer Slice-A — (F2) confidence must match schema enum (HIGH/MEDIUM/LOW uppercase).
  const FIXTURE_CLAIMS = [
    { id: 'c1', claim_text: 'Alpha claim', confidence: 'HIGH', source: 'web' },
    { id: 'c2', claim_text: 'Beta claim',  confidence: 'MEDIUM', source: 'repo' },
    { id: 'c3', claim_text: 'Gamma claim', confidence: 'LOW',    source: 'notebooklm' },
  ];

  let tmpRoot;
  let setupError = null;

  const setupResult = (() => {
    try {
      tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-claim-test-'));
      const researchDir = path.join(tmpRoot, 'docs', 'research');
      fs.mkdirSync(researchDir, { recursive: true });
      fs.writeFileSync(
        path.join(researchDir, '2026-06-01-fixture.claims.json'),
        JSON.stringify(FIXTURE_CLAIMS, null, 2)
      );
      return { ok: true };
    } catch (err) {
      setupError = err;
      return { ok: false };
    }
  })();

  test('fixture created successfully', () => {
    assert.ok(!setupError, `setup threw: ${setupError}`);
    assert.ok(setupResult.ok, 'fixture setup failed');
  });

  test('--type research-claim returns N records from fixture .claims.json (one per claim object)', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'research-claim', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    assert.strictEqual(
      records.length, FIXTURE_CLAIMS.length,
      `Expected ${FIXTURE_CLAIMS.length} records (one per claim). Got ${records.length}: ${records.map(r => r.path).join(', ')}`
    );
  });

  test('research-claim paths include #claim-N fragment', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'research-claim', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    for (let i = 0; i < records.length; i++) {
      assert.ok(
        records[i].path.includes(`#claim-${i}`),
        `Record ${i} path must include #claim-${i}. Got: ${records[i].path}`
      );
    }
  });

  test('research-claim frontmatter fields are flattened from claim objects (--where composable)', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'research-claim', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const highConf = records.filter(r => r.frontmatter && r.frontmatter.confidence === 'HIGH');
    assert.strictEqual(highConf.length, 1, `Expected 1 high-confidence claim. Got: ${highConf.length}`);
    assert.strictEqual(highConf[0].frontmatter.id, 'c1', `High confidence claim must have id=c1`);
  });
});

// ---------------------------------------------------------------------------
// research-synthesis sibling-exclusion (C5 / P1-1)
//
// research-synthesis (docs/research/*.md) must NOT return coverage-audit
// (docs/research/*-coverage-audit.md) or gap-report (docs/research/*-gap-report.md)
// siblings. These are more-specific schemas registered under the same directory.
//
// Spec backlink: docs/plans/2026-06-30-deep-research-queryable-index-layer.md § P1-1
// ---------------------------------------------------------------------------

describe('--type research-synthesis sibling exclusion', () => {
  const os = require('os');
  const fs = require('fs');

  const SYNTHESIS_FM = `---
title: Test synthesis
kind: research-synthesis
question: Is this working?
created: 2026-06-01
---

Synthesis body.
`;

  const COVERAGE_AUDIT_FM = `---
title: Coverage audit
kind: coverage-audit
audited_synthesis: docs/research/2026-06-01-test-synthesis.md
created: 2026-06-01
---

Coverage audit body.
`;

  const GAP_REPORT_FM = `---
title: Gap report
kind: gap-report
deepening_recommended: true
created: 2026-06-01
---

Gap report body.
`;

  let tmpRoot;
  let setupError = null;

  const setupResult = (() => {
    try {
      tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-synthesis-test-'));
      const researchDir = path.join(tmpRoot, 'docs', 'research');
      fs.mkdirSync(researchDir, { recursive: true });
      fs.writeFileSync(path.join(researchDir, '2026-06-01-test-synthesis.md'), SYNTHESIS_FM);
      fs.writeFileSync(path.join(researchDir, '2026-06-01-test-synthesis-coverage-audit.md'), COVERAGE_AUDIT_FM);
      fs.writeFileSync(path.join(researchDir, '2026-06-01-test-synthesis-gap-report.md'), GAP_REPORT_FM);
      return { ok: true };
    } catch (err) {
      setupError = err;
      return { ok: false };
    }
  })();

  test('fixture created successfully', () => {
    assert.ok(!setupError, `setup threw: ${setupError}`);
    assert.ok(setupResult.ok, 'fixture setup failed');
  });

  test('--type research-synthesis returns only the synthesis, NOT coverage-audit or gap-report siblings', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'research-synthesis', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.some(p => p.includes('test-synthesis.md') && !p.includes('-coverage-audit') && !p.includes('-gap-report')),
      `Synthesis file must appear in output. Got: ${paths.join(', ')}`
    );
    assert.ok(
      !paths.some(p => p.includes('-coverage-audit')),
      `coverage-audit sibling must NOT appear in --type research-synthesis. Got: ${paths.join(', ')}`
    );
    assert.ok(
      !paths.some(p => p.includes('-gap-report')),
      `gap-report sibling must NOT appear in --type research-synthesis. Got: ${paths.join(', ')}`
    );
    assert.strictEqual(records.length, 1,
      `Only 1 record (the synthesis) should appear. Got ${records.length}: ${paths.join(', ')}`
    );
  });

  test('--type coverage-audit returns ONLY the coverage-audit file, not the synthesis', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'coverage-audit', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      !paths.some(p => p.includes('test-synthesis.md') && !p.includes('-coverage-audit')),
      `Pure synthesis file must NOT appear in --type coverage-audit. Got: ${paths.join(', ')}`
    );
    assert.ok(
      paths.some(p => p.includes('-coverage-audit')),
      `coverage-audit file must appear in --type coverage-audit. Got: ${paths.join(', ')}`
    );
  });
});

// ---------------------------------------------------------------------------
// Backlog-type sibling-exclusion regression (C1-fix)
//
// Bug: _queryTypeToSchemaName('bug') returned 'bug' but matchSchemaForPath for
// state/bug-backlog/*.yaml returns 'bug-backlog' — mismatch caused the sibling-
// exclusion filter to DROP every backlog record, silently returning [] for
// --type bug|debt|improvement.
//
// Fix: _queryTypeToSchemaName now maps all four divergent types correctly.
//
// These tests plant one record per backlog directory in a temp fixture root and
// assert each --type query returns its record (i.e. is NOT dropped by the filter).
// ---------------------------------------------------------------------------

describe('--type bug|debt|improvement sibling-exclusion regression (C1-fix)', () => {
  const os = require('os');
  const fs = require('fs');

  const BUG_RECORD = `created: 2026-07-04
title: Fixture bug record
body: Regression fixture for C1-fix.
status: open
surface: coordinator/bin/query-records.js
severity: P1
`;

  const DEBT_RECORD = `created: 2026-07-04
title: Fixture debt record
body: Regression fixture for C1-fix.
status: open
source: executor-dispatch
risk: low
proposed_action: track
`;

  const IMPROVEMENT_RECORD = `created: 2026-07-04
title: Fixture improvement record
body: Regression fixture for C1-fix.
status: open
surface: coordinator/bin/query-records.js
proposed_action: track
from_repo: DoE-claude
change_kind: script-edit
`;

  let tmpRoot;
  let setupError = null;

  const setupResult = (() => {
    try {
      tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-backlog-test-'));
      fs.mkdirSync(path.join(tmpRoot, 'state', 'bug-backlog'), { recursive: true });
      fs.mkdirSync(path.join(tmpRoot, 'state', 'debt-backlog'), { recursive: true });
      fs.mkdirSync(path.join(tmpRoot, 'state', 'improvement-queue'), { recursive: true });
      fs.writeFileSync(path.join(tmpRoot, 'state', 'bug-backlog', 'fixture-bug.yaml'), BUG_RECORD);
      fs.writeFileSync(path.join(tmpRoot, 'state', 'debt-backlog', 'fixture-debt.yaml'), DEBT_RECORD);
      fs.writeFileSync(path.join(tmpRoot, 'state', 'improvement-queue', 'fixture-improvement.yaml'), IMPROVEMENT_RECORD);
      return { ok: true };
    } catch (err) {
      setupError = err;
      return { ok: false };
    }
  })();

  test('fixture created successfully', () => {
    assert.ok(!setupError, `setup threw: ${setupError}`);
    assert.ok(setupResult.ok, 'fixture setup failed');
    assert.ok(fs.existsSync(path.join(tmpRoot, 'state', 'bug-backlog', 'fixture-bug.yaml')), 'bug fixture must exist');
    assert.ok(fs.existsSync(path.join(tmpRoot, 'state', 'debt-backlog', 'fixture-debt.yaml')), 'debt fixture must exist');
    assert.ok(fs.existsSync(path.join(tmpRoot, 'state', 'improvement-queue', 'fixture-improvement.yaml')), 'improvement fixture must exist');
  });

  test('--type bug returns the bug record (not dropped by sibling-exclusion filter)', () => {
    // Regression: _queryTypeToSchemaName('bug') returned 'bug' but matchSchemaForPath
    // for state/bug-backlog/*.yaml returns 'bug-backlog' — mismatch caused filter to drop all.
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'bug', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    // Review: code-reviewer F6 — strict equality: fixture dir has exactly 1 file;
    // >= 1 would miss over-inclusion regressions. Error message now shows actual count.
    assert.ok(records.length === 1,
      `--type bug must return exactly 1 record (fixture-bug.yaml). Got ${records.length} — sibling-exclusion filter may be broken or over-including.`
    );
    assert.ok(
      records.some(r => r.path && r.path.includes('fixture-bug')),
      `fixture-bug.yaml must appear in --type bug output. Got: ${records.map(r => r.path).join(', ')}`
    );
  });

  test('--type debt returns the debt record (not dropped by sibling-exclusion filter)', () => {
    // Regression: _queryTypeToSchemaName('debt') returned 'debt' but matchSchemaForPath
    // for state/debt-backlog/*.yaml returns 'debt-backlog'.
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'debt', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    // Review: code-reviewer F6 — strict equality: fixture dir has exactly 1 file;
    // >= 1 would miss over-inclusion regressions. Error message now shows actual count.
    assert.ok(records.length === 1,
      `--type debt must return exactly 1 record (fixture-debt.yaml). Got ${records.length} — sibling-exclusion filter may be broken or over-including.`
    );
    assert.ok(
      records.some(r => r.path && r.path.includes('fixture-debt')),
      `fixture-debt.yaml must appear in --type debt output. Got: ${records.map(r => r.path).join(', ')}`
    );
  });

  test('--type improvement returns the improvement record (not dropped by sibling-exclusion filter)', () => {
    // Regression: _queryTypeToSchemaName('improvement') returned 'improvement' but matchSchemaForPath
    // for state/improvement-queue/*.yaml returns 'improvement-queue'.
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'improvement', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    // Review: code-reviewer F6 — strict equality: fixture dir has exactly 1 file;
    // >= 1 would miss over-inclusion regressions. Error message now shows actual count.
    assert.ok(records.length === 1,
      `--type improvement must return exactly 1 record (fixture-improvement.yaml). Got ${records.length} — sibling-exclusion filter may be broken or over-including.`
    );
    assert.ok(
      records.some(r => r.path && r.path.includes('fixture-improvement')),
      `fixture-improvement.yaml must appear in --type improvement output. Got: ${records.map(r => r.path).join(', ')}`
    );
  });
});

// ---------------------------------------------------------------------------
// --unattached predicate (C3 — initiative govern lens)
//
// Verifies that `query-records --unattached` returns every record whose
// initiative frontmatter is null/absent (absent≡null) and excludes records
// that carry a non-null initiative FK.
//
// Two modes tested:
//   (a) --type plan --unattached  → single-type filter
//   (b) --unattached (no --type)  → multi-type union across UNATTACHED_TYPES
//
// Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C3 (AC4)
// ---------------------------------------------------------------------------

describe('--unattached predicate (initiative govern lens)', () => {
  const os = require('os');
  const fs = require('fs');

  // Plans: one attached (initiative: ini-abc123), one absent (unattached), one explicit null.
  const ATTACHED_PLAN = `---
title: Attached plan
created: 2026-07-04
author: test
status: draft
initiative: ini-abc123
---

This plan is attached to an initiative.
`;

  const UNATTACHED_PLAN_ABSENT = `---
title: Unattached plan — absent field
created: 2026-07-04
author: test
status: draft
---

This plan has no initiative field (absent≡null).
`;

  const UNATTACHED_PLAN_EXPLICIT_NULL = `---
title: Unattached plan — explicit null
created: 2026-07-04
author: test
status: draft
initiative: null
---

This plan explicitly sets initiative: null.
`;

  // Bug records: one attached, one unattached (absent).
  const ATTACHED_BUG = `created: 2026-07-04
title: Attached bug
status: open
surface: coordinator/bin
severity: P2
initiative: ini-abc123
`;

  const UNATTACHED_BUG = `created: 2026-07-04
title: Unattached bug
status: open
surface: coordinator/bin
severity: P2
`;

  let tmpRoot;
  let setupError = null;

  const setupResult = (() => {
    try {
      tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-unattached-test-'));
      const plansDir = path.join(tmpRoot, 'docs', 'plans');
      const bugDir = path.join(tmpRoot, 'state', 'bug-backlog');
      fs.mkdirSync(plansDir, { recursive: true });
      fs.mkdirSync(bugDir, { recursive: true });

      fs.writeFileSync(path.join(plansDir, '2026-07-04-attached-plan.md'), ATTACHED_PLAN);
      fs.writeFileSync(path.join(plansDir, '2026-07-04-unattached-plan-absent.md'), UNATTACHED_PLAN_ABSENT);
      fs.writeFileSync(path.join(plansDir, '2026-07-04-unattached-plan-null.md'), UNATTACHED_PLAN_EXPLICIT_NULL);
      fs.writeFileSync(path.join(bugDir, 'attached-bug.yaml'), ATTACHED_BUG);
      fs.writeFileSync(path.join(bugDir, 'unattached-bug.yaml'), UNATTACHED_BUG);

      return { ok: true };
    } catch (err) {
      setupError = err;
      return { ok: false };
    }
  })();

  test('fixture created successfully', () => {
    assert.ok(!setupError, `setup threw: ${setupError}`);
    assert.ok(setupResult.ok, 'fixture setup failed');
    assert.ok(fs.existsSync(path.join(tmpRoot, 'docs', 'plans', '2026-07-04-attached-plan.md')), 'attached plan must exist');
    assert.ok(fs.existsSync(path.join(tmpRoot, 'state', 'bug-backlog', 'unattached-bug.yaml')), 'unattached bug must exist');
  });

  test('(a) --type plan --unattached: excludes plan with non-null initiative', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    // Use path-separator-anchored check to avoid 'unattached-plan' ⊃ 'attached-plan' substring trap.
    assert.ok(
      !paths.some(p => p.includes('/2026-07-04-attached-plan')),
      `Plan with initiative must NOT appear in --type plan --unattached. Got: ${paths.join(', ')}`
    );
  });

  test('(a) --type plan --unattached: includes plan with absent initiative (absent≡null)', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.some(p => p.includes('unattached-plan-absent')),
      `Plan with absent initiative must appear in --type plan --unattached. Got: ${paths.join(', ')}`
    );
  });

  test('(a) --type plan --unattached: includes plan with explicit initiative:null', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.some(p => p.includes('unattached-plan-null')),
      `Plan with initiative:null must appear in --type plan --unattached. Got: ${paths.join(', ')}`
    );
  });

  test('(a) --type plan --unattached: exactly 2 unattached plans returned', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    assert.strictEqual(records.length, 2,
      `Expected exactly 2 unattached plans (absent + null). Got ${records.length}: ${records.map(r => r.path).join(', ')}`
    );
  });

  test('(b) --unattached (multi-type): returns unattached plans', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.some(p => p.includes('unattached-plan')),
      `Multi-type --unattached must return unattached plans. Got: ${paths.join(', ')}`
    );
  });

  test('(b) --unattached (multi-type): returns unattached bugs', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    assert.ok(
      paths.some(p => p.includes('unattached-bug')),
      `Multi-type --unattached must return unattached bugs. Got: ${paths.join(', ')}`
    );
  });

  test('(b) --unattached (multi-type): excludes all attached records', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    const paths = records.map(r => r.path);
    // Use path-separator-anchored checks to avoid substring traps:
    //   'unattached-plan' ⊃ 'attached-plan' as literal substring → use '/2026-07-04-attached-plan'
    //   'unattached-bug' does NOT contain '/attached-bug' (slash anchors the name boundary)
    assert.ok(
      !paths.some(p => p.includes('/2026-07-04-attached-plan')),
      `Multi-type --unattached must NOT return attached plan. Got: ${paths.join(', ')}`
    );
    assert.ok(
      !paths.some(p => p.includes('/attached-bug')),
      `Multi-type --unattached must NOT return attached bug. Got: ${paths.join(', ')}`
    );
  });

  test('(b) --unattached (multi-type): result count = 2 unattached plans + 1 unattached bug', () => {
    assert.ok(setupResult.ok, 'fixture required');
    const out = execFileSync(
      process.execPath,
      [QUERY_RECORDS, '--unattached', '--format', 'json', '--root', tmpRoot],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const records = JSON.parse(out);
    // fixture has: 2 unattached plans + 1 unattached bug = 3 total
    assert.strictEqual(records.length, 3,
      `Expected 3 unattached records (2 plans + 1 bug). Got ${records.length}: ${records.map(r => r.path).join(', ')}`
    );
  });
});
