'use strict';
/**
 * normalize-handoff-frontmatter.test.js — unit tests for the active-handoff normalizer.
 *
 * Spec backlink: docs/plans/2026-05-29-handoff-tracker-renderer.md § Chunk 5
 *
 * Test runner: node:test (built-in, no external deps required).
 * Run: node plugins/coordinator-claude/coordinator/bin/normalize-handoff-frontmatter.test.js
 */

const { test } = require('node:test');
const assert   = require('node:assert/strict');
const fs       = require('node:fs');
const os       = require('node:os');
const path     = require('node:path');

const {
  normalizeOne,
  splitFrontmatter,
  readFmField,
  matchCategory,
} = require('./normalize-handoff-frontmatter');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'handoff-normalizer-'));
}

function writeFixture(dir, name, content) {
  const p = path.join(dir, name);
  fs.writeFileSync(p, content, 'utf8');
  return p;
}

function applyWrite(filePath) {
  // Run normalizeOne and if there are changes, write them back.
  const out = normalizeOne(filePath);
  if (out) fs.writeFileSync(filePath, out.rebuilt, 'utf8');
  return out;
}

// ---------------------------------------------------------------------------
// Test fixtures — drift inputs
// ---------------------------------------------------------------------------

const FIXTURE_ISO_DATE = `---
title: Headless-extractor phase-3 fan-out
created: 2026-05-28T11:16:48Z
branch: work/striker/2026-05-26to28
status: active
pickup_ready: true
deployment_state: ready_to_fire
---

# Headless-extractor phase-3 fan-out

Body text here.
`;

const FIXTURE_QUOTED_PICKUP_TRUE = `---
title: Portability-guard system
created: 2026-05-20
branch: work/striker/2026-05-20
status: active
pickup_ready: "true"
deployment_state: awaiting_gate
gate_dependency: some gate
---

# Portability-guard system

Body.
`;

const FIXTURE_QUOTED_PICKUP_FALSE = `---
title: Portability-guard system
created: 2026-05-20
branch: work/striker/2026-05-20
status: active
pickup_ready: "false"
deployment_state: awaiting_gate
---

# Portability-guard system

Body.
`;

const FIXTURE_MISSING_CATEGORY_SUMMARY = `---
title: My plain handoff
created: 2026-05-29
branch: work/striker/2026-05-29
status: active
deployment_state: ready_to_fire
---

# Session Handoff — My plain handoff

Body content.
`;

// Already fully clean — should produce zero changes.
const FIXTURE_CLEAN = `---
title: Already normalised handoff
created: 2026-05-29
branch: work/striker/2026-05-29
status: active
pickup_ready: true
deployment_state: ready_to_fire
category: uncategorized
summary: Already normalised handoff
---

# Already normalised handoff

Body.
`;

// Both ISO date AND quoted pickup_ready drift at once.
const FIXTURE_BOTH_DRIFTS = `---
title: Dual-drift handoff
created: 2026-05-28T20:22:28Z
branch: work/striker/2026-05-26to28
status: active
pickup_ready: "true"
deployment_state: ready_to_fire
---

# Dual-drift handoff

Body.
`;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('splitFrontmatter — parses valid frontmatter block', () => {
  const content = `---\ntitle: Test\ncreated: 2026-05-01\n---\n\n# Body\n`;
  const result = splitFrontmatter(content);
  assert.ok(result !== null, 'should return an object');
  assert.ok(result.fmText.includes('title: Test'));
  assert.ok(result.bodyWithLeadingNewline.includes('# Body'));
});

test('splitFrontmatter — returns null for content without frontmatter', () => {
  const content = `# Just a heading\n\nNo frontmatter here.\n`;
  assert.equal(splitFrontmatter(content), null);
});

test('readFmField — reads a field from frontmatter text', () => {
  const fm = `title: My Title\ncreated: 2026-05-01\nstatus: active\n`;
  assert.equal(readFmField(fm, 'title'), 'My Title');
  assert.equal(readFmField(fm, 'created'), '2026-05-01');
  assert.equal(readFmField(fm, 'missing'), null);
});

test('matchCategory — only emits schema-valid enum values', () => {
  // Every return MUST be in schemas/handoff.yaml category enum:
  // [roadmap, infra, bug, docs, research, refactor, uncategorized].
  const VALID = new Set(['roadmap', 'infra', 'bug', 'docs', 'research', 'refactor', 'uncategorized']);
  // Mapped category signals
  assert.equal(matchCategory('Roadmap sprint 4 planning'), 'roadmap');
  assert.equal(matchCategory('Refactor — consolidate retrieval helpers'), 'refactor');
  assert.equal(matchCategory('Fix regression bug in parser'), 'bug');
  assert.equal(matchCategory('Spike: investigate embed footprint'), 'research');
  assert.equal(matchCategory('Update docs and wiki'), 'docs');
  assert.equal(matchCategory('Install hook pipeline hardening'), 'infra');
  // Kind/lifecycle words are NOT categories → uncategorized (the safe default)
  assert.equal(matchCategory('Spinoff — retrieval helpers'), 'uncategorized');
  assert.equal(matchCategory('Recovery Track 1 — verify flip'), 'uncategorized');
  assert.equal(matchCategory('Release v0.3.0 shipped'), 'uncategorized');
  assert.equal(matchCategory('Some random title'), 'uncategorized');
  assert.equal(matchCategory(''), 'uncategorized');
  assert.equal(matchCategory(null), 'uncategorized');
  // Exhaustive guard: a spread of titles never escapes the enum
  for (const t of ['', 'x', 'review', 'planning', 'weekly gate', 'release', 'spinoff', 'roadmap', 'bug', 'docs']) {
    assert.ok(VALID.has(matchCategory(t)), `matchCategory(${JSON.stringify(t)}) escaped the enum: ${matchCategory(t)}`);
  }
});

test('normalizeOne — strips ISO time from created field', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'iso-date.md', FIXTURE_ISO_DATE);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift');
  const change = out.changes.find(c => c.startsWith('created:'));
  assert.ok(change, `expected a created: change; got: ${JSON.stringify(out.changes)}`);
  assert.ok(out.rebuilt.includes('created: 2026-05-28\n'),
    'rebuilt content should have bare date');
  assert.ok(!out.rebuilt.includes('T11:16:48'),
    'rebuilt content must not include time component');
});

test('normalizeOne — unquotes pickup_ready: "true"', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'quoted-true.md', FIXTURE_QUOTED_PICKUP_TRUE);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift');
  const change = out.changes.find(c => c.includes('pickup_ready'));
  assert.ok(change, `expected a pickup_ready change; got: ${JSON.stringify(out.changes)}`);
  assert.ok(out.rebuilt.includes('pickup_ready: true\n'),
    'rebuilt content should have unquoted true');
  assert.ok(!out.rebuilt.includes('"true"'),
    'rebuilt content must not include quoted "true"');
});

test('normalizeOne — unquotes pickup_ready: "false"', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'quoted-false.md', FIXTURE_QUOTED_PICKUP_FALSE);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift');
  assert.ok(out.rebuilt.includes('pickup_ready: false\n'),
    'rebuilt should have unquoted false');
  assert.ok(!out.rebuilt.includes('"false"'),
    'rebuilt must not include quoted "false"');
});

test('normalizeOne — backfills category and summary when absent', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'missing-cat-sum.md', FIXTURE_MISSING_CATEGORY_SUMMARY);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift (missing category + summary)');
  const catChange = out.changes.find(c => c.startsWith('category:'));
  const sumChange = out.changes.find(c => c.startsWith('summary:'));
  assert.ok(catChange, `expected category change; got: ${JSON.stringify(out.changes)}`);
  assert.ok(sumChange, `expected summary change; got: ${JSON.stringify(out.changes)}`);
  assert.ok(out.rebuilt.includes('category:'), 'rebuilt should contain category field');
  assert.ok(out.rebuilt.includes('summary:'), 'rebuilt should contain summary field');
});

test('normalizeOne — handles both ISO date and quoted pickup_ready drifts together', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'both-drifts.md', FIXTURE_BOTH_DRIFTS);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift');
  const dateChange = out.changes.find(c => c.startsWith('created:'));
  const pickupChange = out.changes.find(c => c.includes('pickup_ready'));
  assert.ok(dateChange, 'should report created drift');
  assert.ok(pickupChange, 'should report pickup_ready drift');
  assert.ok(out.rebuilt.includes('created: 2026-05-28\n'));
  assert.ok(out.rebuilt.includes('pickup_ready: true\n'));
});

test('normalizeOne — already-clean file returns null (idempotent)', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'clean.md', FIXTURE_CLEAN);
  const out = normalizeOne(fp);
  assert.equal(out, null, 'clean file should produce no changes');
});

test('normalizeOne — returns null for file with no frontmatter', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'no-fm.md', '# Just a heading\n\nNo frontmatter.\n');
  const out = normalizeOne(fp);
  assert.equal(out, null, 'file without frontmatter should be skipped');
});

test('normalizeOne — summary truncated to ≤120 chars', () => {
  const longTitle = 'A'.repeat(150);
  const content = `---\ntitle: ${longTitle}\ncreated: 2026-05-29\nstatus: active\n---\n\n# ${longTitle}\n`;
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'long-title.md', content);
  const out = normalizeOne(fp);
  assert.ok(out !== null);
  const split = splitFrontmatter(out.rebuilt);
  assert.ok(split !== null);
  const summaryVal = readFmField(split.fmText, 'summary');
  assert.ok(summaryVal !== null);
  // Strip quotes if serialized with single-quoting
  const bare = summaryVal.replace(/^'|'$/g, '').replace(/''/g, "'");
  assert.ok(bare.length <= 120, `summary should be ≤120 chars, got ${bare.length}`);
  assert.ok(bare.endsWith('...'), 'truncated summary should end with ...');
});

test('true idempotency — applying --write twice yields byte-identical files', () => {
  const dir = makeTmpDir();
  // Use the ISO-date fixture (has drift on first pass).
  const fp = writeFixture(dir, 'idempotent.md', FIXTURE_ISO_DATE);

  // First write pass: apply changes.
  const out1 = applyWrite(fp);
  assert.ok(out1 !== null, 'first pass should detect and apply changes');
  const afterFirst = fs.readFileSync(fp, 'utf8');

  // Second write pass: should detect no drift.
  const out2 = applyWrite(fp);
  assert.equal(out2, null, 'second pass should detect no drift (true idempotency)');
  const afterSecond = fs.readFileSync(fp, 'utf8');

  assert.equal(afterFirst, afterSecond, 'file contents must be byte-identical after two writes');
});

test('true idempotency — FIXTURE_BOTH_DRIFTS is idempotent after first write', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'idem-both.md', FIXTURE_BOTH_DRIFTS);

  applyWrite(fp);
  const afterFirst = fs.readFileSync(fp, 'utf8');

  const out2 = applyWrite(fp);
  assert.equal(out2, null, 'second pass must detect no drift');
  const afterSecond = fs.readFileSync(fp, 'utf8');
  assert.equal(afterFirst, afterSecond, 'must be byte-identical after two writes');
});

test('true idempotency — FIXTURE_MISSING_CATEGORY_SUMMARY is idempotent after first write', () => {
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'idem-cat-sum.md', FIXTURE_MISSING_CATEGORY_SUMMARY);

  applyWrite(fp);
  const afterFirst = fs.readFileSync(fp, 'utf8');

  const out2 = applyWrite(fp);
  assert.equal(out2, null, 'second pass must detect no drift');
  const afterSecond = fs.readFileSync(fp, 'utf8');
  assert.equal(afterFirst, afterSecond, 'must be byte-identical after two writes');
});

test('archive dir NEVER read — walkHandoffsDir only globs tasks/handoffs/*.md', () => {
  // Assert that the glob path used is constrained to tasks/handoffs and not
  // archive/handoffs by inspecting the module source.
  const src = fs.readFileSync(
    path.join(__dirname, 'normalize-handoff-frontmatter.js'),
    'utf8',
  );
  // The path must include 'tasks', 'handoffs' and must NOT reference archive.
  assert.ok(
    src.includes("'tasks', 'handoffs'") || src.includes('"tasks", "handoffs"') ||
    src.includes("path.join(root, 'tasks', 'handoffs')"),
    'source must construct path using tasks/handoffs',
  );
  // The archive dir must never appear in a path.join() or path.resolve() call.
  // We allow the string to appear in comments (negative-spec docs), but not in
  // operative code that constructs a filesystem path.
  const pathJoinArchive = /path\.(?:join|resolve)\s*\([^)]*archive[^)]*\)/;
  assert.ok(
    !pathJoinArchive.test(src),
    'source must not use path.join/resolve with "archive" in path construction',
  );
  // walkHandoffsDir must not recurse into subdirectories (would pick up tasks/handoffs/archive/)
  // Verify by checking that we use readdirSync (flat) not a recursive walk.
  assert.ok(
    src.includes('readdirSync'),
    'walkHandoffsDir must use flat readdirSync, not recursive walk',
  );
});

test('normalizeOne — preserves body content byte-for-byte', () => {
  const body = '\n# My Handoff\n\nSome body text.\n\n## Section\n\n- item 1\n- item 2\n';
  const content = `---\ntitle: My Handoff\ncreated: 2026-05-28T10:00:00Z\nstatus: active\n---${body}`;
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'body-preserve.md', content);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift on created');
  // Body (everything after the closing ---) must be untouched.
  assert.ok(out.rebuilt.includes(body),
    'body content must be preserved byte-for-byte');
});

test('normalizeOne — leaves bare pickup_ready: true unchanged', () => {
  const content = `---\ntitle: Clean bool\ncreated: 2026-05-29\nstatus: active\npickup_ready: true\n---\n\n# Clean bool\n`;
  const dir = makeTmpDir();
  const fp = writeFixture(dir, 'bare-bool.md', content);
  // May still add category/summary, but must NOT report a pickup_ready change.
  const out = normalizeOne(fp);
  if (out) {
    const pickupChange = out.changes.find(c => c.includes('pickup_ready'));
    assert.equal(pickupChange, undefined, 'bare true should not trigger a pickup_ready change');
  }
});
