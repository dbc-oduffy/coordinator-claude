'use strict';
/**
 * coordinator-initiative.test.js — Tests for the coordinator-initiative bash CLI.
 *
 * Covers:
 *   1. create happy path — writes state/initiatives/<id>.yaml, exits 0, prints path
 *   2. create with optional fields (--owner, --target-date) — correct YAML shape
 *   3. id-collision case — non-zero exit + remediation message mentioning attach/--force
 *   4. attach happy path — injects initiative: FK into artifact frontmatter (absent key)
 *   5. attach idempotent — replaces existing initiative: FK in frontmatter
 *   6. list-unattached happy path — passes through to query-records --unattached, exits 0
 *
 * Test-isolation: COORDINATOR_INITIATIVE_ROOT env var overrides the central-seam
 * resolution (coordinator_state_root --central) so no live example-orchestration-hub/state config is needed.
 *
 * Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C2 (AC3)
 *
 * Run with: node --test coordinator/bin/lib/coordinator-initiative.test.js
 */

const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const COORDINATOR_INITIATIVE = path.resolve(__dirname, '..', 'coordinator-initiative');

// ---------------------------------------------------------------------------
// Fixture setup (synchronous, run once at module load — node:test lacks beforeAll)
// ---------------------------------------------------------------------------

let tmpRoot;
let initiativesDir;
let setupError = null;

try {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'coord-init-test-'));
  initiativesDir = path.join(tmpRoot, 'initiatives');
  fs.mkdirSync(initiativesDir, { recursive: true });
} catch (err) {
  setupError = err;
}

/**
 * Invoke coordinator-initiative with COORDINATOR_INITIATIVE_ROOT override set to
 * the temp fixture initiatives dir. Any additional env overrides can be passed via opts.env.
 * Returns spawnSync result: { status, stdout, stderr, error }.
 */
function runInit(args, opts = {}) {
  return spawnSync('bash', [COORDINATOR_INITIATIVE, ...args], {
    encoding: 'utf8',
    env: {
      ...process.env,
      COORDINATOR_INITIATIVE_ROOT: initiativesDir,
      ...(opts.env || {}),
    },
  });
}

// ---------------------------------------------------------------------------
// Guard: fixture must be created before any test runs.
// ---------------------------------------------------------------------------

test('fixture setup: temp dir and initiatives dir created', () => {
  assert.ok(!setupError, `temp fixture setup threw: ${setupError}`);
  assert.ok(fs.existsSync(tmpRoot), 'tmpRoot must exist');
  assert.ok(fs.existsSync(initiativesDir), 'initiativesDir must exist');
});

// ---------------------------------------------------------------------------
// 1. create — happy path (required fields only)
// ---------------------------------------------------------------------------

describe('create: happy path (required fields)', () => {
  const id = 'test-initiative-alpha';

  test('exits 0 and prints the written YAML path', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', id, '--label', 'Test Initiative Alpha']);
    assert.strictEqual(
      result.status, 0,
      `create should exit 0; stderr: ${result.stderr}`
    );
    const printed = result.stdout.trim();
    assert.ok(
      printed.endsWith(`${id}.yaml`),
      `stdout should end with ${id}.yaml; got: ${printed}`
    );
  });

  test('written YAML file exists and contains required fields', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const yamlPath = path.join(initiativesDir, `${id}.yaml`);
    assert.ok(fs.existsSync(yamlPath), `${yamlPath} must exist after create`);
    const content = fs.readFileSync(yamlPath, 'utf8');
    assert.ok(content.includes(`id: "${id}"`), `YAML must contain id field; got:\n${content}`);
    assert.ok(content.includes('label: "Test Initiative Alpha"'), `YAML must contain label; got:\n${content}`);
    assert.ok(content.includes('status: active'), `YAML must contain status: active; got:\n${content}`);
    assert.ok(content.includes('owner: null'), `YAML must contain owner: null; got:\n${content}`);
    assert.ok(content.includes('target_date: null'), `YAML must contain target_date: null; got:\n${content}`);
  });
});

// ---------------------------------------------------------------------------
// 2. create — with optional fields
// ---------------------------------------------------------------------------

describe('create: optional fields (--owner, --target-date)', () => {
  const id = 'test-initiative-with-opts';

  test('creates YAML with owner and target_date populated', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit([
      'create',
      '--id', id,
      '--label', 'Initiative With Options',
      '--owner', 'doe-claude-em',
      '--target-date', '2026-12-31',
    ]);
    assert.strictEqual(result.status, 0, `create should exit 0; stderr: ${result.stderr}`);

    const yamlPath = path.join(initiativesDir, `${id}.yaml`);
    assert.ok(fs.existsSync(yamlPath), `${yamlPath} must exist`);
    const content = fs.readFileSync(yamlPath, 'utf8');
    assert.ok(content.includes('owner: "doe-claude-em"'), `YAML must contain owner; got:\n${content}`);
    assert.ok(content.includes('target_date: "2026-12-31"'), `YAML must contain target_date; got:\n${content}`);
  });
});

// ---------------------------------------------------------------------------
// 3. id-collision case — FAIL-LOUD requirement
// ---------------------------------------------------------------------------

describe('create: id-collision case', () => {
  const id = 'collision-test-initiative';

  test('first create succeeds (exit 0)', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', id, '--label', 'Collision Test']);
    assert.strictEqual(result.status, 0, `first create should exit 0; stderr: ${result.stderr}`);
  });

  test('second create on same id exits non-zero', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', id, '--label', 'Collision Test Again']);
    assert.notStrictEqual(
      result.status, 0,
      `second create on id '${id}' must exit non-zero (id collision)`
    );
  });

  test('collision error output mentions the id', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', id, '--label', 'Collision Test Again']);
    const combined = (result.stderr || '') + (result.stdout || '');
    assert.ok(
      combined.includes(id),
      `collision output must mention the colliding id '${id}'; got:\n${combined}`
    );
  });

  test('collision error output includes remediation (attach or --force)', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', id, '--label', 'Collision Test Again']);
    const combined = (result.stderr || '') + (result.stdout || '');
    assert.ok(
      combined.includes('attach') || combined.includes('--force'),
      `collision output must include remediation mentioning 'attach' or '--force'; got:\n${combined}`
    );
  });

  test('--force overwrites the existing initiative (exits 0)', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', id, '--label', 'Collision Test Forced', '--force']);
    assert.strictEqual(result.status, 0, `create with --force should exit 0; stderr: ${result.stderr}`);
    const yamlPath = path.join(initiativesDir, `${id}.yaml`);
    const content = fs.readFileSync(yamlPath, 'utf8');
    assert.ok(
      content.includes('"Collision Test Forced"'),
      `--force must overwrite label; got:\n${content}`
    );
  });
});

// ---------------------------------------------------------------------------
// 4. attach — happy path (frontmatter without existing initiative key)
// ---------------------------------------------------------------------------

describe('attach: inject initiative FK into frontmatter (absent key)', () => {
  const initId = 'attach-test-initiative';
  const fixtureArtifact = path.join(tmpRoot, 'fixture-no-initiative.md');

  const ARTIFACT_WITHOUT_INITIATIVE = `---
title: Fixture Artifact
created: 2026-01-01
status: open
---

Artifact body goes here.
`;

  test('setup: create initiative and write fixture artifact', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const cr = runInit(['create', '--id', initId, '--label', 'Attach Test Initiative']);
    assert.strictEqual(cr.status, 0, `create for attach test must exit 0; stderr: ${cr.stderr}`);
    fs.writeFileSync(fixtureArtifact, ARTIFACT_WITHOUT_INITIATIVE);
    assert.ok(fs.existsSync(fixtureArtifact), 'fixture artifact must exist');
  });

  test('attach exits 0', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['attach', fixtureArtifact, initId]);
    assert.strictEqual(result.status, 0, `attach must exit 0; stderr: ${result.stderr}`);
  });

  test('attach writes initiative: FK to frontmatter', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const content = fs.readFileSync(fixtureArtifact, 'utf8');
    assert.ok(
      content.includes(`initiative: ${initId}`),
      `frontmatter must contain initiative: ${initId}; got:\n${content}`
    );
  });

  test('attach preserves existing frontmatter fields', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const content = fs.readFileSync(fixtureArtifact, 'utf8');
    assert.ok(content.includes('title: Fixture Artifact'), `title must be preserved; got:\n${content}`);
    assert.ok(content.includes('created: 2026-01-01'), `created must be preserved; got:\n${content}`);
    assert.ok(content.includes('status: open'), `status must be preserved; got:\n${content}`);
  });

  test('attach preserves artifact body after frontmatter', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const content = fs.readFileSync(fixtureArtifact, 'utf8');
    assert.ok(
      content.includes('Artifact body goes here.'),
      `body content must be preserved; got:\n${content}`
    );
  });
});

// ---------------------------------------------------------------------------
// 5. attach — idempotent (replaces existing initiative: FK)
// ---------------------------------------------------------------------------

describe('attach: replace existing initiative FK (idempotent)', () => {
  const initId1 = 'attach-idempotent-init-1';
  const initId2 = 'attach-idempotent-init-2';
  const fixtureArtifact = path.join(tmpRoot, 'fixture-with-initiative.md');

  const ARTIFACT_WITH_INITIATIVE = `---
title: Fixture With Initiative
created: 2026-01-02
initiative: ${initId1}
status: active
---

Body text.
`;

  test('setup: create both initiatives and write fixture artifact with pre-set initiative FK', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    runInit(['create', '--id', initId1, '--label', 'Idempotent Test 1']);
    runInit(['create', '--id', initId2, '--label', 'Idempotent Test 2']);
    fs.writeFileSync(fixtureArtifact, ARTIFACT_WITH_INITIATIVE);
  });

  test('re-attach to a different initiative exits 0', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['attach', fixtureArtifact, initId2]);
    assert.strictEqual(result.status, 0, `re-attach must exit 0; stderr: ${result.stderr}`);
  });

  test('re-attach replaces the initiative FK with the new id', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const content = fs.readFileSync(fixtureArtifact, 'utf8');
    assert.ok(
      content.includes(`initiative: ${initId2}`),
      `frontmatter must contain updated initiative: ${initId2}; got:\n${content}`
    );
  });

  test('re-attach does not leave the old initiative FK in frontmatter', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const content = fs.readFileSync(fixtureArtifact, 'utf8');
    // initId1 ends without a digit, initId2 ends with -2; check the exact FK line is gone.
    // `initiative: attach-idempotent-init-1` must not appear (only `initiative: attach-idempotent-init-2` should).
    assert.ok(
      !content.includes(`initiative: ${initId1}\n`) && !content.includes(`initiative: ${initId1}\r`),
      `old initiative FK '${initId1}' must not remain in frontmatter; got:\n${content}`
    );
  });
});

// ---------------------------------------------------------------------------
// attach — negative tests (F6: missing cases)
// ---------------------------------------------------------------------------

// Review: code-reviewer — F6 (P2): attach to nonexistent initiative id → non-zero + stderr mentions 'create'
describe('attach: nonexistent initiative id exits non-zero', () => {
  const fixtureArtifact = path.join(tmpRoot, 'attach-neg-nonexistent.md');

  const ARTIFACT_WITH_FM = `---
title: Negative Test Artifact
status: open
---

Body.
`;

  test('setup: write fixture artifact', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    fs.writeFileSync(fixtureArtifact, ARTIFACT_WITH_FM);
    assert.ok(fs.existsSync(fixtureArtifact), 'fixture artifact must exist');
  });

  test('attach to nonexistent initiative id exits non-zero', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['attach', fixtureArtifact, 'this-id-does-not-exist-xyz']);
    assert.notStrictEqual(
      result.status, 0,
      `attach to nonexistent id must exit non-zero; stderr: ${result.stderr}`
    );
  });

  test('attach to nonexistent initiative id mentions "create" in stderr', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['attach', fixtureArtifact, 'this-id-does-not-exist-xyz']);
    assert.ok(
      (result.stderr || '').includes('create'),
      `error output must mention 'create' for remediation; got: ${result.stderr}`
    );
  });
});

// Review: code-reviewer — F3/F6 (P1/P2): attach to frontmatter-less artifact exits non-zero
describe('attach: frontmatter-less artifact exits non-zero', () => {
  const noFrontmatterArtifact = path.join(tmpRoot, 'attach-neg-no-frontmatter.md');
  const initId = 'frontmatter-test-init';

  const ARTIFACT_NO_FM = `This file has no YAML frontmatter.

Just plain markdown content.
`;

  test('setup: create initiative and write frontmatter-less artifact', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const cr = runInit(['create', '--id', initId, '--label', 'Frontmatter Test Init']);
    assert.strictEqual(cr.status, 0, `create must exit 0; stderr: ${cr.stderr}`);
    fs.writeFileSync(noFrontmatterArtifact, ARTIFACT_NO_FM);
    assert.ok(fs.existsSync(noFrontmatterArtifact), 'no-frontmatter artifact must exist');
  });

  test('attach to artifact with no frontmatter exits non-zero', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['attach', noFrontmatterArtifact, initId]);
    assert.notStrictEqual(
      result.status, 0,
      `attach to frontmatter-less artifact must exit non-zero; stderr: ${result.stderr}`
    );
  });
});

// Review: code-reviewer — F2 (P1): traversal id '../evil' → non-zero exit
describe('create: traversal id rejected at parse time', () => {
  test('id containing .. exits non-zero', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', '../evil', '--label', 'Traversal Test']);
    assert.notStrictEqual(
      result.status, 0,
      `create with traversal id '../evil' must exit non-zero; stderr: ${result.stderr}`
    );
  });

  test('traversal id error mentions the invalid id', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', '../evil', '--label', 'Traversal Test']);
    const combined = (result.stderr || '') + (result.stdout || '');
    assert.ok(
      combined.includes('invalid') || combined.includes('rejected') || combined.includes('match'),
      `error output must mention invalid id shape; got:\n${combined}`
    );
  });

  test('id with leading dot exits non-zero', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', '.hidden', '--label', 'Hidden Test']);
    assert.notStrictEqual(
      result.status, 0,
      `create with leading-dot id must exit non-zero; stderr: ${result.stderr}`
    );
  });

  test('id with slash exits non-zero', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const result = runInit(['create', '--id', 'path/inject', '--label', 'Slash Test']);
    assert.notStrictEqual(
      result.status, 0,
      `create with slash in id must exit non-zero; stderr: ${result.stderr}`
    );
  });
});

// ---------------------------------------------------------------------------
// 6. list-unattached — happy path (wraps query-records --unattached)
// ---------------------------------------------------------------------------

describe('list-unattached: happy path', () => {
  test('exits 0 with a minimal --root (no records = empty result)', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    // Build a minimal state tree so query-records --unattached has something to scan.
    const listRoot = path.join(tmpRoot, 'list-root');
    fs.mkdirSync(path.join(listRoot, 'state', 'handoffs'), { recursive: true });
    fs.mkdirSync(path.join(listRoot, 'docs', 'plans'), { recursive: true });

    const result = runInit(['list-unattached', '--root', listRoot]);
    assert.strictEqual(
      result.status, 0,
      `list-unattached should exit 0 with empty results; stderr: ${result.stderr}`
    );
  });

  test('does not emit coordinator-initiative error messages when query-records succeeds', () => {
    assert.ok(!setupError, 'fixture setup must succeed');
    const listRoot = path.join(tmpRoot, 'list-root');
    const result = runInit(['list-unattached', '--root', listRoot]);
    assert.ok(
      !(result.stderr || '').includes('coordinator-initiative list-unattached:'),
      `list-unattached must not emit coordinator-initiative-level errors; stderr: ${result.stderr}`
    );
  });
});
