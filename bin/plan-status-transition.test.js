'use strict';
/**
 * plan-status-transition.test.js — unit tests for the stamp-implemented CLI verb.
 *
 * Purpose: status-matrix coverage of plan-status-transition.js's stamp-implemented
 * transition — every source status either flips to 'implemented' or is a respected
 * no-op, plus idempotency and the missing-frontmatter error path.
 *
 * Note: executing→implemented DOES flip at this CLI level (asserted below). Any
 * halt-safety property for 'executing' plans belongs at a higher seam and is out
 * of scope for this CLI's tests.
 *
 * Test runner: node:test (built-in, no external deps required).
 * Run: node coordinator/bin/plan-status-transition.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const CLI = path.join(__dirname, 'plan-status-transition.js');

function makeTmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'plan-status-transition-'));
}

function writePlan(dir, name, status) {
  const content = `---\ntitle: Test plan\ncreated: 2026-07-09\nauthor: test\nstatus: ${status}\n---\n\n# Body\n\nSome content.\n`;
  const p = path.join(dir, name);
  fs.writeFileSync(p, content, 'utf8');
  return p;
}

function runCli(args) {
  try {
    const stdout = execFileSync('node', [CLI, ...args], { encoding: 'utf8' });
    return { code: 0, stdout };
  } catch (e) {
    return { code: e.status, stdout: e.stdout ? e.stdout.toString() : '', stderr: e.stderr ? e.stderr.toString() : '' };
  }
}

function readStatus(p) {
  const content = fs.readFileSync(p, 'utf8');
  const m = content.match(/^status: (.*)$/m);
  return m ? m[1] : null;
}

// ---------------------------------------------------------------------------
// Status matrix: flip cases
// ---------------------------------------------------------------------------

for (const src of ['draft', 'reviewed', 'approved', 'executing']) {
  test(`stamp-implemented flips status "${src}" → implemented`, () => {
    const dir = makeTmpDir();
    const p = writePlan(dir, 'plan.md', src);
    const result = runCli(['stamp-implemented', '--plan', p]);
    assert.equal(result.code, 0, `expected exit 0, got ${result.code}, stderr: ${result.stderr}`);
    assert.equal(readStatus(p), 'implemented');
  });
}

test('stamp-implemented flips a YAML-quoted status value (A-F3 — readFmField is quote-aware)', () => {
  const dir = makeTmpDir();
  const p = path.join(dir, 'plan.md');
  const content = '---\ntitle: Test plan\ncreated: 2026-07-09\nauthor: test\nstatus: "draft"\n---\n\n# Body\n\nSome content.\n';
  fs.writeFileSync(p, content, 'utf8');
  const result = runCli(['stamp-implemented', '--plan', p]);
  assert.equal(result.code, 0, `expected exit 0, got ${result.code}, stderr: ${result.stderr}`);
  assert.equal(readStatus(p), 'implemented');
});

test('stamp-implemented DOES flip "executing" → implemented at CLI level (halt-safety is a seam concern, not tested here)', () => {
  const dir = makeTmpDir();
  const p = writePlan(dir, 'plan.md', 'executing');
  const result = runCli(['stamp-implemented', '--plan', p]);
  assert.equal(result.code, 0);
  assert.equal(readStatus(p), 'implemented');
});

// ---------------------------------------------------------------------------
// Status matrix: no-op (terminal/deferred) cases
// ---------------------------------------------------------------------------

for (const src of ['implemented', 'superseded', 'abandoned', 'deferred']) {
  test(`stamp-implemented is a no-op for terminal/deferred status "${src}"`, () => {
    const dir = makeTmpDir();
    const p = writePlan(dir, 'plan.md', src);
    const result = runCli(['stamp-implemented', '--plan', p]);
    assert.equal(result.code, 0, `expected exit 0, got ${result.code}, stderr: ${result.stderr}`);
    assert.equal(readStatus(p), src, 'status must remain unchanged');
  });
}

// ---------------------------------------------------------------------------
// Idempotency: double-invoke
// ---------------------------------------------------------------------------

test('stamp-implemented is idempotent across a double-invoke', () => {
  const dir = makeTmpDir();
  const p = writePlan(dir, 'plan.md', 'approved');
  const first = runCli(['stamp-implemented', '--plan', p]);
  assert.equal(first.code, 0);
  assert.equal(readStatus(p), 'implemented');

  const second = runCli(['stamp-implemented', '--plan', p]);
  assert.equal(second.code, 0, `expected exit 0 on second invoke, got ${second.code}, stderr: ${second.stderr}`);
  assert.equal(readStatus(p), 'implemented');
});

// ---------------------------------------------------------------------------
// Error paths
// ---------------------------------------------------------------------------

test('stamp-implemented fails with non-zero exit and stderr on missing --plan', () => {
  const result = runCli(['stamp-implemented']);
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /--plan/);
});

test('stamp-implemented fails with non-zero exit on nonexistent plan file', () => {
  const result = runCli(['stamp-implemented', '--plan', '/nonexistent/path/plan.md']);
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /not found/);
});

test('stamp-implemented fails with non-zero exit on unparseable frontmatter', () => {
  const dir = makeTmpDir();
  const p = path.join(dir, 'no-frontmatter.md');
  fs.writeFileSync(p, '# Just a body\n\nNo frontmatter here.\n', 'utf8');
  const result = runCli(['stamp-implemented', '--plan', p]);
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /no parseable YAML frontmatter/);
});

test('stamp-implemented fails with non-zero exit on missing "status" field', () => {
  const dir = makeTmpDir();
  const p = path.join(dir, 'no-status.md');
  fs.writeFileSync(p, '---\ntitle: Test\ncreated: 2026-07-09\nauthor: test\n---\n\nBody.\n', 'utf8');
  const result = runCli(['stamp-implemented', '--plan', p]);
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /no "status" field/);
});

test('stamp-implemented fails on unknown verb', () => {
  const dir = makeTmpDir();
  const p = writePlan(dir, 'plan.md', 'draft');
  const result = runCli(['bogus-verb', '--plan', p]);
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /unknown verb/);
});
