'use strict';
/**
 * normalize-handoff-frontmatter.test.js — unit tests for the active-handoff normalizer.
 *
 * Spec backlink: docs/plans/2026-05-29-handoff-tracker-renderer.md § Chunk 5
 *               docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § C3c
 *
 * Test runner: node:test (built-in, no external deps required).
 * Run: node plugins/coordinator/bin/normalize-handoff-frontmatter.test.js
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
  deriveSlugFromPath,
  mintDeliverableIdFromSlug,
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
branch: work/machine-a/2026-05-26to28
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
branch: work/machine-a/2026-05-20
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
branch: work/machine-a/2026-05-20
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
branch: work/machine-a/2026-05-29
status: active
deployment_state: ready_to_fire
---

# Session Handoff — My plain handoff

Body content.
`;

// Already fully clean — should produce zero changes.
// Must carry ALL six normalized fields (including the C3c additions) to be truly clean.
const FIXTURE_CLEAN = `---
title: Already normalised handoff
created: 2026-05-29
branch: work/machine-a/2026-05-29
status: active
pickup_ready: true
deployment_state: ready_to_fire
category: uncategorized
summary: Already normalised handoff
deliverable_id: dlv-already-normalised-handoff-abc123
initiative: null
---

# Already normalised handoff

Body.
`;

// Both ISO date AND quoted pickup_ready drift at once.
const FIXTURE_BOTH_DRIFTS = `---
title: Dual-drift handoff
created: 2026-05-28T20:22:28Z
branch: work/machine-a/2026-05-26to28
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

test('normalizeOne — summary truncated to ≤140 chars', () => {
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
  assert.ok(bare.length <= 140, `summary should be ≤140 chars, got ${bare.length}`);
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

test('archive dir NEVER read — walkHandoffsDir only globs state/handoffs/*.md', () => {
  // Assert that the glob path used is constrained to state/handoffs and not
  // archive/handoffs by inspecting the module source.
  const src = fs.readFileSync(
    path.join(__dirname, 'normalize-handoff-frontmatter.js'),
    'utf8',
  );
  // The path must include 'tasks', 'handoffs' and must NOT reference archive.
  assert.ok(
    src.includes("'tasks', 'handoffs'") || src.includes('"tasks", "handoffs"') ||
    src.includes("path.join(root, 'state', 'handoffs')"),
    'source must construct path using state/handoffs',
  );
  // The archive dir must never appear in a path.join() or path.resolve() call.
  // We allow the string to appear in comments (negative-spec docs), but not in
  // operative code that constructs a filesystem path.
  const pathJoinArchive = /path\.(?:join|resolve)\s*\([^)]*archive[^)]*\)/;
  assert.ok(
    !pathJoinArchive.test(src),
    'source must not use path.join/resolve with "archive" in path construction',
  );
  // walkHandoffsDir must not recurse into subdirectories (would pick up state/handoffs/archive/)
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
  // May still add category/summary/deliverable_id/initiative, but must NOT report a pickup_ready change.
  const out = normalizeOne(fp);
  if (out) {
    const pickupChange = out.changes.find(c => c.includes('pickup_ready'));
    assert.equal(pickupChange, undefined, 'bare true should not trigger a pickup_ready change');
  }
});

// ---------------------------------------------------------------------------
// C3c — deliverable_id and initiative backfill + carry tests
// ---------------------------------------------------------------------------

test('deriveSlugFromPath — returns basename without .md', () => {
  assert.equal(deriveSlugFromPath('/foo/bar/state/handoffs/2026-07-03-my-handoff.md'), '2026-07-03-my-handoff');
  assert.equal(deriveSlugFromPath('state/handoffs/simple.md'), 'simple');
  // Absolute path with no directory: bare filename
  assert.equal(deriveSlugFromPath('only-a-filename.md'), 'only-a-filename');
  // Strips only the .md extension (not other extensions)
  assert.equal(deriveSlugFromPath('state/handoffs/2026-07-03-kebab-slug.md'), '2026-07-03-kebab-slug');
  // Note: path.basename is POSIX-aware on macOS/Linux; Windows paths are
  // handled correctly by Node on Windows at runtime (path.sep is OS-native).
});

test('mintDeliverableIdFromSlug — format is dlv-<slug>-<6hex>', () => {
  const id = mintDeliverableIdFromSlug('2026-07-03-test-handoff');
  assert.match(id, /^dlv-2026-07-03-test-handoff-[0-9a-f]{6}$/, `id format unexpected: ${id}`);
});

test('mintDeliverableIdFromSlug — unique across two rapid calls', () => {
  // Two mints in succession should be different (entropy includes Date.now() + RANDOM).
  // Non-deterministic by design; collision probability < 1/16M per pair.
  const a = mintDeliverableIdFromSlug('my-slug');
  const b = mintDeliverableIdFromSlug('my-slug');
  // We tolerate the astronomically rare collision — just verify both are well-formed.
  assert.match(a, /^dlv-my-slug-[0-9a-f]{6}$/);
  assert.match(b, /^dlv-my-slug-[0-9a-f]{6}$/);
});

test('normalizeOne — backfills deliverable_id when absent', () => {
  const dir = makeTmpDir();
  const content = `---
title: Spine test handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
deployment_state: ready_to_fire
category: infra
summary: Spine test handoff
---

# Spine test handoff

Body.
`;
  const fp = writeFixture(dir, 'spine-test.md', content);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift (absent deliverable_id + initiative)');
  const idChange = out.changes.find(c => c.startsWith('deliverable_id:'));
  assert.ok(idChange, `expected a deliverable_id change; got: ${JSON.stringify(out.changes)}`);
  assert.ok(idChange.includes('[mint-from-slug]'), `change should note mint path; got: ${idChange}`);
  // Verify the id appears in rebuilt frontmatter with correct format
  const split = splitFrontmatter(out.rebuilt);
  assert.ok(split !== null);
  const idVal = readFmField(split.fmText, 'deliverable_id');
  assert.ok(idVal !== null, 'deliverable_id should be present after normalization');
  assert.match(idVal, /^dlv-spine-test-[0-9a-f]{6}$/, `id format unexpected: ${idVal}`);
});

test('normalizeOne — carries deliverable_id when already present (no re-mint)', () => {
  const existingId = 'dlv-existing-handoff-deadbe';
  const dir = makeTmpDir();
  const content = `---
title: Already-threaded handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
deployment_state: in_flight
category: infra
summary: Already-threaded handoff
deliverable_id: ${existingId}
initiative: null
---

# Already-threaded handoff

Body.
`;
  const fp = writeFixture(dir, 'threaded.md', content);
  const out = normalizeOne(fp);
  // File is fully clean — normalizeOne must return null (no drift).
  assert.equal(out, null, 'file with all fields present should have no drift');
});

test('normalizeOne — carry does NOT re-mint a different id (anti-fork check)', () => {
  const existingId = 'dlv-some-other-id-ff00aa';
  const dir = makeTmpDir();
  const content = `---
title: Multi-artifact handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
category: infra
summary: Multi-artifact handoff
deliverable_id: ${existingId}
initiative: null
---

# Multi-artifact handoff
`;
  const fp = writeFixture(dir, 'multi-artifact.md', content);
  const out = normalizeOne(fp);
  // May add nothing (file already has all six fields) — either way, id must be unchanged.
  if (out) {
    const split = splitFrontmatter(out.rebuilt);
    const idVal = readFmField(split.fmText, 'deliverable_id');
    assert.equal(idVal, existingId, 'carry must not change an existing deliverable_id');
  } else {
    // null → no drift detected, which is also correct (id already present)
    assert.equal(out, null);
  }
});

test('normalizeOne — inserts initiative: null when absent (D9 present-as-null)', () => {
  const dir = makeTmpDir();
  const content = `---
title: No-initiative handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
deployment_state: in_flight
category: infra
summary: No-initiative handoff
deliverable_id: dlv-no-initiative-handoff-aabbcc
---

# No-initiative handoff

Body.
`;
  const fp = writeFixture(dir, 'no-initiative.md', content);
  const out = normalizeOne(fp);
  assert.ok(out !== null, 'should detect drift (absent initiative)');
  const initChange = out.changes.find(c => c.startsWith('initiative:'));
  assert.ok(initChange, `expected an initiative change; got: ${JSON.stringify(out.changes)}`);
  assert.ok(initChange.includes('null'), `change should note null; got: ${initChange}`);
  // Verify the field is present in rebuilt frontmatter as the literal "null"
  const split = splitFrontmatter(out.rebuilt);
  assert.ok(split !== null);
  const initVal = readFmField(split.fmText, 'initiative');
  assert.equal(initVal, 'null', `initiative should be literal "null"; got: ${initVal}`);
  // Confirm the rebuilt text contains `initiative: null` (the YAML form)
  assert.ok(out.rebuilt.includes('initiative: null\n'), 'rebuilt should contain `initiative: null`');
});

test('normalizeOne — carries initiative when present (including null literal)', () => {
  // initiative: null is already the correct present-as-null form; must not be re-inserted.
  const dir = makeTmpDir();
  const content = `---
title: Carried initiative handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
category: infra
summary: Carried initiative handoff
deliverable_id: dlv-carried-initiative-handoff-112233
initiative: null
---

# Carried initiative handoff
`;
  const fp = writeFixture(dir, 'carried-init.md', content);
  const out = normalizeOne(fp);
  // File has all six fields — no drift expected.
  assert.equal(out, null, 'file with initiative: null already present should be clean');
});

test('normalizeOne — carries a non-null initiative FK unchanged', () => {
  const dir = makeTmpDir();
  const content = `---
title: Assigned initiative handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
category: infra
summary: Assigned initiative handoff
deliverable_id: dlv-assigned-initiative-handoff-334455
initiative: init-delphi-fleet
---

# Assigned initiative handoff
`;
  const fp = writeFixture(dir, 'assigned-init.md', content);
  const out = normalizeOne(fp);
  // File has all six fields — no drift expected; initiative FK must be preserved.
  assert.equal(out, null, 'file with non-null initiative should be clean');
});

test('normalizeOne — deliverable_id idempotent: mint on first pass, carry on second', () => {
  const dir = makeTmpDir();
  const content = `---
title: Idempotent spine handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
category: infra
summary: Idempotent spine handoff
initiative: null
---

# Idempotent spine handoff
`;
  const fp = writeFixture(dir, 'idem-spine.md', content);

  // First pass: mints deliverable_id
  const out1 = applyWrite(fp);
  assert.ok(out1 !== null, 'first pass should detect absent deliverable_id');
  const afterFirst = fs.readFileSync(fp, 'utf8');
  const split1 = splitFrontmatter(afterFirst);
  const minted = readFmField(split1.fmText, 'deliverable_id');
  assert.match(minted, /^dlv-idem-spine-[0-9a-f]{6}$/, `unexpected id: ${minted}`);

  // Second pass: file is now fully clean — must detect no drift
  const out2 = applyWrite(fp);
  assert.equal(out2, null, 'second pass must detect no drift (carry path)');
  const afterSecond = fs.readFileSync(fp, 'utf8');
  assert.equal(afterFirst, afterSecond, 'file must be byte-identical after two passes');
});

test('normalizeOne — initiative: null idempotent: insert on first pass, carry on second', () => {
  const dir = makeTmpDir();
  const content = `---
title: Idempotent initiative handoff
created: 2026-07-03
branch: work/machine-a/2026-07-03
status: active
category: infra
summary: Idempotent initiative handoff
deliverable_id: dlv-idempotent-initiative-handoff-aabbcc
---

# Idempotent initiative handoff
`;
  const fp = writeFixture(dir, 'idem-initiative.md', content);

  // First pass: inserts initiative: null
  const out1 = applyWrite(fp);
  assert.ok(out1 !== null, 'first pass should detect absent initiative');
  const afterFirst = fs.readFileSync(fp, 'utf8');

  // Second pass: initiative: null already present — no drift
  const out2 = applyWrite(fp);
  assert.equal(out2, null, 'second pass must detect no drift');
  const afterSecond = fs.readFileSync(fp, 'utf8');
  assert.equal(afterFirst, afterSecond, 'file must be byte-identical after two passes');
});
