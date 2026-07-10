'use strict';
/**
 * normalize-consumed-frontmatter.test.js — unit tests for the shipped_in write-path gate.
 *
 * Purpose: normalizeOne() inserts free-text `notes` captured from a
 * `<!-- consumed: YYYY-MM-DD [notes] -->` body marker directly into
 * `shipped_in:` with (pre-C4b) zero shape check. This suite proves the write
 * path now refuses a non-conforming value rather than writing prose straight
 * into a field the rest of the pipeline treats as a validated SHA/token.
 *
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C4b
 *
 * Test runner: node:test (built-in, no external deps required).
 * Run: node plugins/coordinator/bin/normalize-consumed-frontmatter.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { normalizeOne } = require('./normalize-consumed-frontmatter');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

function makeTmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'normalize-consumed-fm-'));
}

function writeFixture(dir, name, marker) {
  const content = `---\nstatus: active\ndeployment_state: in_flight\nconsumed_at: 2026-06-14\n---\n\n# Body content\n\n<!-- consumed: 2026-06-14 ${marker} -->\n`;
  const p = path.join(dir, name);
  fs.writeFileSync(p, content, 'utf8');
  return p;
}

// ---------------------------------------------------------------------------
// Positive: bare SHA / sanctioned token notes get written to shipped_in as before
// ---------------------------------------------------------------------------

test('bare SHA marker notes are written to shipped_in', () => {
  const dir = makeTmpDir();
  const p = writeFixture(dir, 'sha.md', 'abc1234f');
  const out = normalizeOne(p);
  assert.ok(out, 'normalizeOne should report a change');
  assert.match(out.rebuilt, /shipped_in: abc1234f/);
});

test('sanctioned substantively-shipped-no-commit token marker notes are written to shipped_in', () => {
  const dir = makeTmpDir();
  const p = writeFixture(dir, 'token.md', 'substantively-shipped-no-commit:2026-07-08');
  const out = normalizeOne(p);
  assert.ok(out, 'normalizeOne should report a change');
  assert.match(out.rebuilt, /shipped_in:.*substantively-shipped-no-commit:2026-07-08/);
});

// ---------------------------------------------------------------------------
// Negative: prose / annotated-SHA notes must NOT be written unvalidated
// ---------------------------------------------------------------------------

test('prose rationale marker notes do NOT get written to shipped_in (write-path gated)', () => {
  const dir = makeTmpDir();
  const p = writeFixture(dir, 'prose.md', 'shipped as part of the bigger refactor no single commit');
  const out = normalizeOne(p);
  // status/deployment_state/consumed_at still flip — only the shipped_in insert is refused.
  if (out) {
    assert.doesNotMatch(out.rebuilt, /shipped_in:/, 'shipped_in must not be written from unvalidated prose');
  }
});

test('annotated-SHA marker notes ("[~/.claude] f4f150a1d") do NOT get written to shipped_in', () => {
  const dir = makeTmpDir();
  const p = writeFixture(dir, 'annotated.md', '[~/.claude] f4f150a1d');
  const out = normalizeOne(p);
  if (out) {
    assert.doesNotMatch(out.rebuilt, /shipped_in:/, 'shipped_in must not be written from an annotated SHA');
  }
});

test('malformed shipped_in refusal is recorded in changes[] for visibility', () => {
  const dir = makeTmpDir();
  const p = writeFixture(dir, 'prose2.md', 'shipped elsewhere, see chat');
  const out = normalizeOne(p);
  assert.ok(out, 'other fields (status/consumed_at) still change, so normalizeOne must still report');
  const noted = out.changes.some(c => /shipped_in/i.test(c) && /refus|reject|skip|invalid/i.test(c));
  assert.ok(noted, `Expected a refusal note in changes[], got: ${JSON.stringify(out.changes)}`);
});

// ---------------------------------------------------------------------------
// C1c regression: migration onto schema.js shared FM primitives must not
// change normalization output byte-for-byte (pinned pre-migration snapshot).
// ---------------------------------------------------------------------------

test('normalizeOne output is byte-identical to the pre-migration snapshot (bare SHA case)', () => {
  const dir = makeTmpDir();
  const p = writeFixture(dir, 'sha-snapshot.md', 'abc1234f');
  const out = normalizeOne(p);
  assert.ok(out, 'normalizeOne should report a change');
  const expected =
    '---\n' +
    'status: consumed\n' +
    'deployment_state: shipped\n' +
    'consumed_at: 2026-06-14\n' +
    'shipped_in: abc1234f\n' +
    '---\n' +
    '\n' +
    '# Body content\n' +
    '\n' +
    '<!-- consumed: 2026-06-14 abc1234f -->\n';
  assert.equal(out.rebuilt, expected);
});
