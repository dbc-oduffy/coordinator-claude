'use strict';
/**
 * normalize-handoff-frontmatter.strang07-c7.test.js — DR-210/DR-215 facade routing tests (C7).
 *
 * Spec backlinks:
 *   DR-210 strang-07 C7 (JS-side facade shim for handoff.normalize)
 *   docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C1 (DR-215 repoint)
 *
 * DR-215 repoint: fake coordinator_core.invoke replaces fake coordinator_core.client.
 * seamPresent() now probes coordinator_core.invoke importability.
 * Dispatch uses coordinator_core.invoke with --repo flag (spawn-per-call).
 *
 * AC coverage:
 *   T1 — seam-absent  → legacy JS core runs (handoff normalized on disk, exit 0).
 *   T2 — seam-present + invoke exits non-zero (State-3) → non-zero exit, NO legacy fallback.
 *   T3 — seam-present + invoke exits 0 (State-2) → exit 0, no legacy fallback.
 *   T4 — grep-gate: resolveExampleOrchestrationHubRoot() body contains no 'machine-local get' invocation.
 *
 * Review: code-reviewer — F6: corrected test numbering (T4 was inserted after T2 without
 * renumbering; old T4 is now T3, old T3 is now T4); AC-coverage comment updated to include T4.
 *
 * CWD discipline:
 *   All subprocess invocations run from TMP_BASE (neutral directory, no coordinator_core).
 *   EXAMPLE_ORCHESTRATION_HUB_ROOT is always overridden via env so the test is hermetic.
 *
 * Test runner: node:test (built-in, no external deps required).
 * Run: node coordinator/bin/normalize-handoff-frontmatter.strang07-c7.test.js
 */

const { test } = require('node:test');
const assert   = require('node:assert/strict');
const fs       = require('node:fs');
const os       = require('node:os');
const path     = require('node:path');
const { spawnSync } = require('node:child_process');

const SCRIPT   = path.join(__dirname, 'normalize-handoff-frontmatter.js');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a disposable temp directory for a test. */
function makeTmpDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), `strang07-c7-${prefix}-`));
}

/**
 * Build a minimal fake coordinator_core.invoke package (DR-215 replacement for
 * the retired coordinator_core.client).
 *
 * The __main__.py is written to `<root>/coordinator_core/invoke/__main__.py`
 * so `python3 -m coordinator_core.invoke` invokes it.
 *
 * The normalize-handoff-frontmatter.js dispatch calls spawnSync directly with
 * coordinator_core.invoke (not via cc_invoke), so no JSON-RPC envelope is needed
 * here — the script checks result.status directly, not cc_invoke's parsed result.
 *
 * When `sentinel` is a non-empty string, the invoke stub writes a file at that
 * path on invocation — provides positive proof of native-path selection.
 *
 * popup-safe-env-suppressed: writes pure python; no subprocess calls.
 */
function buildFakeInvoke(root, exitCode, sentinel) {
  fs.mkdirSync(path.join(root, 'coordinator_core', 'invoke'), { recursive: true });
  fs.writeFileSync(path.join(root, 'coordinator_core', '__init__.py'), '', 'utf8');
  fs.writeFileSync(path.join(root, 'coordinator_core', 'invoke', '__init__.py'), '', 'utf8');
  const lines = ['import sys'];
  if (sentinel) {
    lines.push(`import pathlib; pathlib.Path(${JSON.stringify(sentinel)}).touch()`);
  }
  lines.push(`sys.exit(${exitCode})`);
  fs.writeFileSync(
    path.join(root, 'coordinator_core', 'invoke', '__main__.py'),
    lines.join('\n') + '\n',
    'utf8'
  );
}

/**
 * Build a minimal fake repo rooted at `root` with one drifted handoff.
 * The handoff has an ISO timestamp on `created` so normalizeOne() will
 * detect drift and emit at least one change line.
 * Returns the path to the handoff file.
 */
function buildFakeRepo(root) {
  const handoffsDir = path.join(root, 'state', 'handoffs');
  fs.mkdirSync(handoffsDir, { recursive: true });
  const handoffPath = path.join(handoffsDir, '2026-07-05-test-facade.md');
  fs.writeFileSync(handoffPath, [
    '---',
    'title: Test facade handoff',
    'created: 2026-07-05T12:00:00Z',
    'pickup_ready: "false"',
    '---',
    '',
    '# Test facade handoff',
    '',
    'Body content.',
    '',
  ].join('\n'), 'utf8');
  return handoffPath;
}

// ---------------------------------------------------------------------------
// T1 — seam-absent → legacy JS core runs
//
// EXAMPLE_ORCHESTRATION_HUB_ROOT points to an empty directory.  coordinator_core.client is not
// importable from it so seamPresent() returns false and legacy_normalize() runs.
//
// Proof: the handoff file is updated on disk (drift normalized), exit 0.
// ---------------------------------------------------------------------------

test('T1 strang07-c7: seam-absent → legacy core runs, handoff normalized', () => {
  const tmpBase    = makeTmpDir('absent');
  const maAbsent   = path.join(tmpBase, 'example-orchestration-hub-absent');
  const repoRoot   = path.join(tmpBase, 'repo');

  fs.mkdirSync(maAbsent, { recursive: true });
  const handoffPath = buildFakeRepo(repoRoot);

  const before = fs.readFileSync(handoffPath, 'utf8');

  // Run from tmpBase (neutral CWD) with EXAMPLE_ORCHESTRATION_HUB_ROOT pointing to empty dir.
  const result = spawnSync(
    process.execPath,
    [SCRIPT, '--write', '--root', repoRoot],
    {
      cwd: tmpBase,
      env: { ...process.env, EXAMPLE_ORCHESTRATION_HUB_ROOT: maAbsent },
    }
  );

  const after = fs.readFileSync(handoffPath, 'utf8');

  // Clean up.
  fs.rmSync(tmpBase, { recursive: true, force: true });

  assert.strictEqual(result.status, 0, `exit code should be 0, got ${result.status}; stderr: ${result.stderr?.toString()}`);
  assert.notStrictEqual(before, after, 'handoff file should have been modified by legacy_normalize');
  // Confirm the ISO timestamp was stripped (drift indicator).
  assert.ok(!after.includes('2026-07-05T12:00:00Z'), 'ISO timestamp should have been stripped');
  assert.ok(after.includes('created: 2026-07-05'), 'bare date should be present after normalization');
});

// ---------------------------------------------------------------------------
// T2 — seam-present + invoke exits non-zero (State-3) → non-zero, no fallback
//
// EXAMPLE_ORCHESTRATION_HUB_ROOT points to a dir with coordinator_core.invoke whose __main__.py
// exits 3 and writes a sentinel file on invocation.
//
// Proof:
//   a) script exits non-zero (propagates invoke exit code — normalize-handoff-frontmatter.js
//      calls spawnSync directly, not via cc_invoke, so exits 3 not 2).
//   b) sentinel file IS written (native path reached, NOT legacy).
//   c) handoff file is NOT modified (legacy_normalize never ran).
// ---------------------------------------------------------------------------

test('T2 strang07-c7: seam-present forced-fail → non-zero exit, no legacy fallback', () => {
  const tmpBase      = makeTmpDir('present-fail');
  const maFail       = path.join(tmpBase, 'example-orchestration-hub-present-fail');
  const repoRoot     = path.join(tmpBase, 'repo');
  const sentinelPath = path.join(tmpBase, 'native-called');

  fs.mkdirSync(maFail, { recursive: true });
  buildFakeInvoke(maFail, 3, sentinelPath);
  const handoffPath = buildFakeRepo(repoRoot);

  const before = fs.readFileSync(handoffPath, 'utf8');

  const result = spawnSync(
    process.execPath,
    [SCRIPT, '--write', '--root', repoRoot],
    {
      cwd: tmpBase,
      env: { ...process.env, EXAMPLE_ORCHESTRATION_HUB_ROOT: maFail },
    }
  );

  const after = fs.readFileSync(handoffPath, 'utf8');

  // Review: code-reviewer F2 — assert sentinel BEFORE cleanup; remove || true (was vacuous:
  // tmpBase was deleted before the check, so existsSync always returned false, and || true
  // made the whole expression unconditionally true — provided no positive proof of native path).
  assert.notStrictEqual(result.status, 0, `exit code should be non-zero (State-3 hard-fail), got ${result.status}`);
  assert.ok(fs.existsSync(sentinelPath), 'native-path sentinel must exist — client was invoked via native path (NOT legacy)');
  assert.strictEqual(before, after, 'handoff file should NOT be modified — legacy_normalize must not run on State-3');

  // Clean up.
  fs.rmSync(tmpBase, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// T3 — seam-present + invoke exits 0 (State-2 happy path) → exit 0, no legacy fallback
//
// EXAMPLE_ORCHESTRATION_HUB_ROOT points to a dir with coordinator_core.invoke whose __main__.py
// exits 0 and writes a sentinel file on invocation.
//
// Proof:
//   a) script exits 0 (invoke success propagated).
//   b) sentinel file IS written (native path reached, NOT legacy).
//   c) handoff file is NOT modified (legacy_normalize never ran on State-2).
//
// Review: code-reviewer F3 — State-2 happy-path coverage missing; closes the gap between
// "routing doesn't crash on State-2" and "routing delivers a correct op call on State-2".
// Review: code-reviewer F6 — renumbered from T4 to T3 (correct file-order position).
// ---------------------------------------------------------------------------

test('T3 strang07-c7: seam-present + client exits 0 (State-2) → exit 0, no legacy fallback', () => {
  const tmpBase      = makeTmpDir('present-ok');
  const maOk         = path.join(tmpBase, 'example-orchestration-hub-present-ok');
  const repoRoot     = path.join(tmpBase, 'repo');
  const sentinelPath = path.join(tmpBase, 'native-called');

  fs.mkdirSync(maOk, { recursive: true });
  buildFakeInvoke(maOk, 0, sentinelPath);   // invoke exits 0, writes sentinel
  const handoffPath = buildFakeRepo(repoRoot);

  const before = fs.readFileSync(handoffPath, 'utf8');

  const result = spawnSync(
    process.execPath,
    [SCRIPT, '--write', '--root', repoRoot],
    {
      cwd: tmpBase,
      env: { ...process.env, EXAMPLE_ORCHESTRATION_HUB_ROOT: maOk },
    }
  );

  // Capture observable state BEFORE cleanup.
  const sentinelExists = fs.existsSync(sentinelPath);
  const after          = fs.readFileSync(handoffPath, 'utf8');

  // Clean up.
  fs.rmSync(tmpBase, { recursive: true, force: true });

  assert.strictEqual(result.status, 0,
    `exit code should be 0 (State-2 success), got ${result.status}; stderr: ${result.stderr?.toString()}`);
  assert.ok(sentinelExists,
    'native-path sentinel must exist — invoke was reached via native path (NOT legacy)');
  assert.strictEqual(before, after,
    'handoff file should NOT be modified — legacy_normalize must not run on State-2');
});

// ---------------------------------------------------------------------------
// T4 — grep-gate: resolveExampleOrchestrationHubRoot body contains no 'machine-local get' call
//
// Design pin 4 / P3 cold-fallback constraint: JS cold-fallback MUST resolve
// EXAMPLE_ORCHESTRATION_HUB_ROOT via direct file read, NEVER via the machine-local CLI.
//
// Review: code-reviewer F6 — renumbered from T3 to T4 (correct file-order position).
// ---------------------------------------------------------------------------

test('T4 strang07-c7: grep-gate — no machine-local get in resolveExampleOrchestrationHubRoot', () => {
  const src = fs.readFileSync(SCRIPT, 'utf8');
  // Extract the resolveExampleOrchestrationHubRoot function body for scoped grep.
  // We locate the function declaration and scan up to the next top-level function.
  const fnStart = src.indexOf('function resolveExampleOrchestrationHubRoot(');
  assert.ok(fnStart !== -1, 'resolveExampleOrchestrationHubRoot function must exist in script');

  // Find the next top-level function after resolveExampleOrchestrationHubRoot.
  const tail = src.slice(fnStart);
  // Next top-level `function ` declaration (not inside a nested block).
  const nextFn = /\nfunction /.exec(tail.slice(1));
  const fnBody = nextFn ? tail.slice(0, nextFn.index + 1) : tail;

  assert.ok(
    !fnBody.includes('machine-local get'),
    'resolveExampleOrchestrationHubRoot must NOT contain "machine-local get" (Design pin 4 / P3 cold-fallback)'
  );
});
