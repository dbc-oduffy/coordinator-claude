'use strict';
/**
 * query-records.test.js — Tests for cross-repo-memo type, includeUnparseable flag,
 * the archive/handoffs ledger glob fix, and YAML-backed queue types (debt/bug/improvement).
 *
 * Spec backlink: docs/plans/2026-05-29-query-records-cross-repo-memo-and-includeunparseable.md
 * Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C6
 *
 * Covers:
 *   1. --type cross-repo-memo finds inbox memos and filters on status=open
 *   2. Non-memo-shaped file (README.md fixture, no from/to) is silently skipped
 *   3. includeUnparseable: true returns a parseError record for an invalid-frontmatter fixture
 *      while default (false) still skips it
 *   4. handoff-ledger query globs archive/handoffs (not state/handoffs/archive)
 *   5. --type debt finds state/debt-backlog/*.yaml files (whole-file YAML, no --- delimiters)
 *   6. --type bug with --where severity=P1 returns matching subset
 *   7. --type improvement returns record with proposed_action in markdown-list output
 *   8. liveness-records: plan + decision single-axis liveness; handoff/memo tc-0 regressions
 *   9. plan-sidecar-exclusion: review-N iteration sidecars excluded; all sidecar suffix types excluded
 *  10. roadmap: glob fix (state/roadmap/<slug>/OVERVIEW.md) + normalizeRoadmapStatus direct table tests
 *      (approved/draft/in-review/unknown — the three map entries e2e does not reach)
 *  11. liveness-parity: contract enum values agree with liveness() SSOT
 *  12. plan-readme-exclusion: README.md silently excluded from --type plan
 *  13. liveness-queues-e2e: queryRecords() injects liveness for queue + lesson types
 *  14. parseLessonsFile: inner-star title repair + count oracle
 *
 * Review: code-reviewer slice-B F5 — Covers: list updated to include liveness-records and
 *   plan-sidecar-exclusion suites.
 * Review: code-reviewer slice-1 F6 — Covers: list extended with missing suites 10-14.
 *
 * Run with: node --test bin/query-records.test.js
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync, spawnSync } = require('child_process');

const BIN_DIR = path.resolve(__dirname);
const QUERY_RECORDS = path.join(BIN_DIR, 'query-records.js');

let tmpRoot;

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function writeFile(absPath, content) {
  fs.mkdirSync(path.dirname(absPath), { recursive: true });
  fs.writeFileSync(absPath, content, 'utf8');
}

/** Write a cross-repo-memo fixture with valid memo shape (from + to fields). */
function writeMemoFixture(filename, fields) {
  const inboxDir = path.join(tmpRoot, 'cross-repo', 'inbox');
  fs.mkdirSync(inboxDir, { recursive: true });
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    lines.push(`${k}: ${v}`);
  }
  lines.push('---', '', 'Memo body.');
  writeFile(path.join(inboxDir, filename), lines.join('\n'));
}

/**
 * Write a YAML-queue fixture (whole-file YAML, no --- delimiters) to a state/<dir>/ path.
 * models the per-entry files for debt-backlog, bug-backlog, improvement-queue types.
 */
function writeYamlQueueFixture(dir, filename, fields) {
  const queueDir = path.join(tmpRoot, 'state', dir);
  fs.mkdirSync(queueDir, { recursive: true });
  const lines = [];
  for (const [k, v] of Object.entries(fields)) {
    if (typeof v === 'string' && v.includes('\n')) {
      lines.push(`${k}: |`);
      for (const bodyLine of v.split('\n')) {
        lines.push(`  ${bodyLine}`);
      }
    } else {
      lines.push(`${k}: ${JSON.stringify(v)}`);
    }
  }
  writeFile(path.join(queueDir, filename), lines.join('\n') + '\n');
}

/** Write a docs/plans/ fixture (canonical plan or sidecar shape). */
function writePlanFixture(filename, fields) {
  const plansDir = path.join(tmpRoot, 'docs', 'plans');
  fs.mkdirSync(plansDir, { recursive: true });
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    lines.push(`${k}: ${v}`);
  }
  lines.push('---', '', '# Plan fixture body');
  writeFile(path.join(plansDir, filename), lines.join('\n'));
}

/**
 * Write a roadmap OVERVIEW fixture at state/roadmap/<slug>/OVERVIEW.md.
 * The new canonical glob `state/roadmap/*\/OVERVIEW.md` matches only this file,
 * NOT sidecars (OVERVIEW.the Director of Engineering-review.md, STUB-INDEX.md, etc.) in the same dir.
 * Spec backlink: docs/plans/2026-06-27-emit-new-record-types-producer-wiring.md § A3 (chunk A3)
 */
function writeRoadmapFixture(slug, fields, { sidecarFilename } = {}) {
  const roadmapDir = path.join(tmpRoot, 'state', 'roadmap', slug);
  fs.mkdirSync(roadmapDir, { recursive: true });
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    lines.push(`${k}: ${v}`);
  }
  lines.push('---', '', '# Roadmap OVERVIEW fixture');
  writeFile(path.join(roadmapDir, 'OVERVIEW.md'), lines.join('\n'));
  // Write a sidecar to confirm it is NOT included in query results.
  if (sidecarFilename) {
    writeFile(path.join(roadmapDir, sidecarFilename), '# Sidecar — must not appear in roadmap query\n');
  }
}

/** Write a handoff-ledger fixture under archive/handoffs/ (flat). */
function writeArchiveHandoffFixture(filename, ledgerFields) {
  const dir = path.join(tmpRoot, 'archive', 'handoffs');
  fs.mkdirSync(dir, { recursive: true });
  const lines = [
    '---',
    'title: archive-handoff-fixture',
    'status: consumed',
    `created: ${new Date().toISOString().slice(0, 10)}`,
    '---',
    '',
    '## Session Ledger',
    '',
    '| Field | Value |',
    '|-------|-------|',
  ];
  for (const [k, v] of Object.entries(ledgerFields)) {
    lines.push(`| ${k} | ${v} |`);
  }
  lines.push('');
  writeFile(path.join(dir, filename), lines.join('\n'));
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'test-query-records-'));

  // Memo A — open, valid memo shape
  writeMemoFixture('2026-05-28-memo-alpha.md', {
    title: 'Alpha memo',
    from: 'repo-a',
    to: 'repo-b',
    status: 'open',
    created: '2026-05-28',
  });

  // Memo B — actioned, valid memo shape
  writeMemoFixture('2026-05-29-memo-beta.md', {
    title: 'Beta memo',
    from: 'repo-c',
    to: 'repo-b',
    status: 'actioned',
    created: '2026-05-29',
  });

  // Non-memo file in inbox: README.md — has frontmatter but no from/to
  writeMemoFixture('README.md', {
    title: 'Cross-repo inbox README',
    description: 'Explains the inbox convention',
  });

  // Invalid-frontmatter file — no --- block at all
  writeFile(
    path.join(tmpRoot, 'cross-repo', 'inbox', 'bad-frontmatter.md'),
    'This file has no frontmatter block at all.\n\nJust body text.'
  );

  // Archive handoff with a Session Ledger — under archive/handoffs/ (canonical flat path)
  writeArchiveHandoffFixture('2026-05-20-archived-session.md', {
    agent_dispatches: 10,
    opus_dispatches: 2,
    em_tokens: '200,000',
    tshirt: 'M',
    commits: 'abc1234',
    session_id: 'sess-archive-test',
    created: new Date().toISOString().slice(0, 10),
  });

  // Debt-backlog fixtures — whole-file YAML (no --- delimiters)
  writeYamlQueueFixture('debt-backlog', 'DSR-2026-06-15-1.yaml', {
    id: 'DSR-2026-06-15-1',
    created: '2026-06-15',
    source: 'daily-review/the Staff Engineer/2026-06-15',
    status: 'open',
    severity: 'P2',
    title: 'Fan-out overlap pass verifies interface presence, not correctness',
    body: 'Structural gap in fan-out dispatch gate.',
    risk: 'Wrong interface pin causes divergent executor outputs.',
    proposed_action: 'Add correctness check to fan-out gate.',
  });
  writeYamlQueueFixture('debt-backlog', 'DSR-2026-06-15-2.yaml', {
    id: 'DSR-2026-06-15-2',
    created: '2026-06-15',
    source: 'daily-review/the Staff Engineer/2026-06-15',
    status: 'deferred',
    title: 'Second debt item for filter testing',
    body: 'Another debt item.',
    risk: 'Minor risk.',
    proposed_action: 'Investigate later.',
  });

  // Bug-backlog fixtures — whole-file YAML (no --- delimiters)
  // Review: code-reviewer Slice-C — (C-F4) bug-backlog schema requires `surface`, not `system`.
  writeYamlQueueFixture('bug-backlog', 'BS-2026-06-14-1.yaml', {
    id: 'BS-2026-06-14-1',
    created: '2026-06-14',
    surface: 'setup/publish',
    severity: 'P1',
    status: 'open',
    title: 'publish.sh Phase 4 audit skips unchanged files',
    body: 'Personal data audit only covers newly-synced files.',
  });
  writeYamlQueueFixture('bug-backlog', 'BS-2026-06-14-2.yaml', {
    id: 'BS-2026-06-14-2',
    created: '2026-06-14',
    surface: 'coordinator/auto-push',
    severity: 'P2',
    status: 'open',
    title: 'Auto-push skips dirty working tree warning',
    body: 'When working tree is dirty auto-push proceeds without warning.',
  });

  // Improvement-queue fixtures — whole-file YAML (no --- delimiters)
  // Review: code-reviewer Slice-C — (C-F4) improvement-queue schema requires `proposed_action`,
  //   not `proposed_target`; fixture corrected to match schema.
  writeYamlQueueFixture('improvement-queue', 'b7e3d2f1-2026-06-15.yaml', {
    id: 'b7e3d2f1-2026-06-15',
    created: '2026-06-15',
    from_repo: 'coordinator-claude',
    title: 'Promote persona-name word-boundary patterns into REVIEW_PATTERNS',
    body: 'The current patterns miss persona names mid-sentence.',
    surface: 'setup/publish.sh:88-95',
    proposed_action: 'setup/publish.sh (REVIEW_PATTERNS array)',
    change_kind: 'script-edit',
    status: 'open',
  });

  // docs/plans/ fixtures for plan-sidecar-exclusion tests (C9b)
  // Canonical plan — should appear in --type plan results.
  writePlanFixture('2026-06-25-test-plan-fixture.md', {
    title: 'Test plan fixture',
    status: 'draft',
    created: '2026-06-25',
  });
  // Canonical review sidecar (*.review.md) — excluded by sidecar regex layer.
  writePlanFixture('2026-06-25-test-plan-fixture.review.md', {
    schema: 'review-sidecar',
    plan: 'docs/plans/2026-06-25-test-plan-fixture.md',
    reviewer: 'patrik',
    verdict: 'approved',
    created: '2026-06-25',
  });
  // Review iteration sidecar (*.review-2.md, tc-1 C9b) — must be excluded silently,
  // with NO anomaly warning. This is the canonical form for a second distinct-reviewer
  // sidecar on the same plan.
  writePlanFixture('2026-06-25-test-plan-fixture.review-2.md', {
    schema: 'review-sidecar',
    plan: 'docs/plans/2026-06-25-test-plan-fixture.md',
    reviewer: 'zoli',
    verdict: 'approved',
    created: '2026-06-25',
  });

  // F3 fixtures: other sidecar suffix types — must all be EXCLUDED from --type plan.
  // Review: code-reviewer slice-B F3 — adds fixtures for all four sidecar suffix types so the
  // sidecar exclusion test covers the full set, not just .review.md.
  writePlanFixture('2026-06-25-test-plan-fixture.prior-art-check.md', {
    plan: 'docs/plans/2026-06-25-test-plan-fixture.md',
    created: '2026-06-25',
    author: 'prior-art-checker',
    status: 'pending',
  });
  writePlanFixture('2026-06-25-test-plan-fixture.plan-coverage-check.md', {
    plan: 'docs/plans/2026-06-25-test-plan-fixture.md',
    created: '2026-06-25',
    author: 'plan-coverage-checker',
    verdict: 'INCOMPLETE',
  });
  writePlanFixture('2026-06-25-test-plan-fixture.docs-check.md', {
    artifact: 'docs/plans/2026-06-25-test-plan-fixture.md',
    created: '2026-06-25',
    checker: 'docs-checker',
  });

  // docs/plans/README.md — directory-index file; must be SILENTLY excluded from --type plan
  // with NO anomaly-detector warning. Regression fixture for example-initiative example-workstream example-repo Ask 4.
  writeFile(path.join(tmpRoot, 'docs', 'plans', 'README.md'),
    '# Plans\n\nDirectory index for docs/plans/.\n');

  // F2 fixture: legacy undated plan — triggers the anomaly-detector warn path.
  // No date-prefix → does NOT match CANONICAL_PLAN_RE → excluded with stderr warning.
  // Review: code-reviewer slice-B F2 — anomaly-detector positive path fixture.
  writePlanFixture('legacy-undated-plan.md', {
    title: 'Legacy undated plan (no date prefix)',
    status: 'draft',
  });

  // Roadmap fixture — slug with status: final-approved (coordinator:roadmap-planning lifecycle)
  // which MUST be normalized to 'active' by normalizeRoadmapStatus() before returning.
  // Includes a sidecar to assert it is excluded by the OVERVIEW.md-only glob.
  writeRoadmapFixture('test-roadmap-2026-06-27', {
    roadmap_id: 'test-roadmap-2026-06-27',
    title:      'Test roadmap fixture',
    created:    '2026-06-27',
    status:     'final-approved',
  }, { sidecarFilename: 'OVERVIEW.the Director of Engineering-review.md' });

  // F2/F6/F3 fixture: state/lessons.md with 4 entries (2 with inner * in title, 2 plain).
  // Used by parseLessonsFile inner-star repair tests and liveness-queues-e2e lesson assertion.
  // Review: code-reviewer slice-B F2 + F6 — controlled lessons fixture.
  writeFile(path.join(tmpRoot, 'state', 'lessons.md'), [
    '**Fan-out overlap pass verifies plugins/*/ not correctness** [universal] (2026-06-10) — Glob path in title.',
    '- **Use *italic* formatting in lesson bodies** [project] (2026-06-11) — Italic span in title.',
    '**Normal lesson without inner stars** [universal] (2026-06-12) — Plain entry.',
    '- **Another plain lesson entry** [project] (2026-06-13) — Second plain entry.',
  ].join('\n') + '\n');
});

after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// Invoke query-records.js as child process
// ---------------------------------------------------------------------------

function runQuery(type, args) {
  return execFileSync(
    process.execPath,
    [QUERY_RECORDS, '--type', type, '--root', tmpRoot, ...args],
    { encoding: 'utf8' }
  ).trim();
}

// ---------------------------------------------------------------------------
// 1. cross-repo-memo: finds inbox memos, status filter works
// ---------------------------------------------------------------------------

describe('cross-repo-memo — basic query', () => {
  it('finds both well-formed memos (2 records)', () => {
    const raw = runQuery('cross-repo-memo', ['--format', 'json']);
    const records = JSON.parse(raw);
    // README.md and bad-frontmatter.md must be excluded by the memo-shape guard
    assert.equal(records.length, 2, `Expected 2 memo records, got ${records.length}: ${raw}`);
  });

  it('--where status=open returns only the open memo', () => {
    const raw = runQuery('cross-repo-memo', ['--where', 'status=open', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 open memo, got ${records.length}: ${raw}`);
    assert.equal(records[0].frontmatter.status, 'open');
    assert.equal(records[0].frontmatter.title, 'Alpha memo');
  });

  it('--where status=actioned returns only the actioned memo', () => {
    const raw = runQuery('cross-repo-memo', ['--where', 'status=actioned', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 actioned memo, got ${records.length}: ${raw}`);
    assert.equal(records[0].frontmatter.from, 'repo-c');
  });

  it('from field is available for --where filtering', () => {
    const raw = runQuery('cross-repo-memo', ['--where', 'from=repo-a', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 record with from=repo-a, got ${records.length}`);
    assert.equal(records[0].frontmatter.title, 'Alpha memo');
  });
});

// ---------------------------------------------------------------------------
// 2. cross-repo-memo: non-memo-shaped files are silently skipped
// ---------------------------------------------------------------------------

describe('cross-repo-memo — memo-shape guard', () => {
  it('README.md (no from/to) is silently excluded', () => {
    const raw = runQuery('cross-repo-memo', ['--format', 'json']);
    const records = JSON.parse(raw);
    const paths = records.map(r => r.path);
    const hasReadme = paths.some(p => p.includes('README'));
    assert.ok(!hasReadme, `README.md should be excluded by memo-shape guard; got: ${paths.join(', ')}`);
  });

  it('total count does not include README or bad-frontmatter', () => {
    const raw = runQuery('cross-repo-memo', ['--format', 'json']);
    const records = JSON.parse(raw);
    // Only 2 valid memos (alpha + beta); README.md and bad-frontmatter.md excluded
    assert.equal(records.length, 2, `Expected exactly 2 records; got ${records.length}`);
  });
});

// ---------------------------------------------------------------------------
// 3. includeUnparseable flag
// ---------------------------------------------------------------------------

describe('includeUnparseable — opt-in mode', () => {
  it('default (false): bad-frontmatter.md is silently skipped', () => {
    const raw = runQuery('cross-repo-memo', ['--format', 'json']);
    const records = JSON.parse(raw);
    const hasBad = records.some(r => r.path && r.path.includes('bad-frontmatter'));
    assert.ok(!hasBad, `bad-frontmatter.md should not appear without --include-unparseable`);
  });

  it('--include-unparseable: bad-frontmatter.md appears with parseError field', () => {
    const raw = runQuery('cross-repo-memo', ['--include-unparseable', '--format', 'json']);
    const records = JSON.parse(raw);
    const badRecord = records.find(r => r.path && r.path.includes('bad-frontmatter'));
    assert.ok(badRecord, `Expected bad-frontmatter.md record with --include-unparseable; records: ${JSON.stringify(records.map(r => r.path))}`);
    assert.ok(typeof badRecord.parseError === 'string' && badRecord.parseError.length > 0,
      `Expected parseError string on unparseable record; got: ${JSON.stringify(badRecord)}`);
    assert.equal(badRecord.frontmatter, null, `Expected frontmatter=null on unparseable record`);
  });

  it('--include-unparseable: well-formed memos still appear normally', () => {
    const raw = runQuery('cross-repo-memo', ['--include-unparseable', '--format', 'json']);
    const records = JSON.parse(raw);
    const validMemos = records.filter(r => r.frontmatter !== null && r.frontmatter.from);
    assert.equal(validMemos.length, 2, `Expected 2 valid memo records alongside unparseable; got ${validMemos.length}`);
  });

  it('--include-unparseable via opts object (library call): works without CLI flag', () => {
    // Verify the option works when passed via opts directly (not just CLI).
    // We require the module and call queryRecords() programmatically.
    const { queryRecords } = require('./query-records.js');
    const opts = {
      type: 'cross-repo-memo',
      where: null,
      sort: null,
      limit: 50,
      since: null,
      olderThan: null,
      root: null,
      format: 'markdown-list',
      includeUnparseable: true,
    };
    const records = queryRecords(opts, tmpRoot);
    const badRecord = records.find(r => r.path && r.path.includes('bad-frontmatter'));
    assert.ok(badRecord, `Library call: expected bad-frontmatter.md with includeUnparseable:true`);
    assert.ok(badRecord.parseError, `Library call: expected parseError on unparseable record`);
  });
});

// ---------------------------------------------------------------------------
// 4. handoff-ledger archive glob: archive/handoffs/ (not state/handoffs/archive/)
// ---------------------------------------------------------------------------

describe('handoff-ledger — archive/handoffs/ glob', () => {
  it('archives under archive/handoffs/ are included in the ledger query', () => {
    const raw = runQuery('handoff-ledger', ['--format', 'json']);
    const records = JSON.parse(raw);
    const fromArchive = records.filter(r => r.path.includes('archive/handoffs/'));
    assert.ok(fromArchive.length >= 1,
      `Expected at least 1 ledger record from archive/handoffs/; got: ${JSON.stringify(records.map(r => r.path))}`);
  });

  it('archived ledger record has expected tshirt and session_id fields', () => {
    const raw = runQuery('handoff-ledger', ['--format', 'json']);
    const records = JSON.parse(raw);
    const archived = records.find(r => r.path.includes('2026-05-20-archived-session'));
    assert.ok(archived, `Expected archived session record; paths: ${records.map(r => r.path).join(', ')}`);
    assert.equal(archived.frontmatter.tshirt, 'M');
    assert.equal(archived.frontmatter.session_id, 'sess-archive-test');
  });

  it('--where tshirt=M finds the archived ledger record', () => {
    const raw = runQuery('handoff-ledger', ['--where', 'tshirt=M', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.ok(records.length >= 1, `Expected at least 1 tshirt=M record from archive; got: ${raw}`);
    const archived = records.find(r => r.path.includes('2026-05-20-archived-session'));
    assert.ok(archived, `Expected archived session record in tshirt=M results`);
  });
});

// ---------------------------------------------------------------------------
// 4b. formatRecords linkCtx — fragment-suffixed synthetic paths (Finding 1, P1)
// Review: code-reviewer — Finding 1. research-claim and handoff-ledger records carry a
// "<real-path>#claim-N" / "#ledger-N" .path — a URL fragment, not a filesystem path
// segment. Regression coverage for the refresh-queries.js-style callout embedding
// (linkCtx supplied) from a non-root-depth file, for both synthetic types.
// ---------------------------------------------------------------------------

describe('formatRecords — linkCtx with fragment-suffixed synthetic paths', () => {
  it('handoff-ledger: linkPath is relative-to-fromDir with #ledger-N fragment preserved', () => {
    const { queryRecords: qr, formatRecords: fr } = require('./query-records.js');
    const records = qr({
      type: 'handoff-ledger', where: null, sort: null, limit: 50,
      since: null, olderThan: null, root: null, format: 'markdown-list',
    }, tmpRoot);
    const archived = records.find(r => r.path.includes('2026-05-20-archived-session'));
    assert.ok(archived, `Expected archived ledger record; paths: ${records.map(r => r.path).join(', ')}`);
    assert.match(archived.path, /#ledger-\d+$/, `Expected #ledger-N suffix on .path; got: ${archived.path}`);

    // Simulate a callout embedded from a file two directories deep (state/roadmap/<x>/STUB-INDEX.md),
    // matching the refresh-queries.js non-root-depth case Finding 1 calls out.
    const fromDir = path.join(tmpRoot, 'state', 'roadmap', 'some-slug');
    const out = fr([archived], { format: 'markdown-list', type: 'handoff-ledger' }, { root: tmpRoot, fromDir });

    const hashIdx = archived.path.indexOf('#');
    const fragment = archived.path.slice(hashIdx);
    const pathPart = archived.path.slice(0, hashIdx);
    const expectedRelPath = path.relative(fromDir, path.join(tmpRoot, pathPart)).replace(/\\/g, '/');

    assert.ok(out.includes(fragment), `Expected fragment "${fragment}" preserved in output: ${out}`);
    assert.ok(out.includes(expectedRelPath), `Expected relative path "${expectedRelPath}" in output: ${out}`);
    // Corruption tell from the bug: path.resolve/relative treating "#ledger-N" as a literal
    // trailing path segment produces "../"-heavy garbage with the fragment fused into a
    // directory-looking segment rather than a clean trailing #fragment.
    assert.ok(!out.includes('#ledger-' + fragment.slice('#ledger-'.length) + '/'),
      `Fragment must not be embedded as a path segment: ${out}`);
  });

  it('research-claim: linkPath is relative-to-fromDir with #claim-N fragment preserved', () => {
    const claimsDir = path.join(tmpRoot, 'docs', 'research');
    fs.mkdirSync(claimsDir, { recursive: true });
    fs.writeFileSync(
      path.join(claimsDir, 'fragment-test.claims.json'),
      JSON.stringify([{ title: 'Claim zero', status: 'open' }], null, 2)
    );

    const { queryRecords: qr, formatRecords: fr } = require('./query-records.js');
    const records = qr({
      type: 'research-claim', where: null, sort: null, limit: 50,
      since: null, olderThan: null, root: null, format: 'markdown-list',
    }, tmpRoot);
    const claim = records.find(r => r.path.includes('fragment-test.claims.json'));
    assert.ok(claim, `Expected research-claim record; paths: ${records.map(r => r.path).join(', ')}`);
    assert.match(claim.path, /#claim-\d+$/, `Expected #claim-N suffix on .path; got: ${claim.path}`);

    const fromDir = path.join(tmpRoot, 'state', 'roadmap', 'some-slug');
    const out = fr([claim], { format: 'markdown-list', type: 'research-claim' }, { root: tmpRoot, fromDir });

    const hashIdx = claim.path.indexOf('#');
    const fragment = claim.path.slice(hashIdx);
    const pathPart = claim.path.slice(0, hashIdx);
    const expectedRelPath = path.relative(fromDir, path.join(tmpRoot, pathPart)).replace(/\\/g, '/');

    assert.ok(out.includes(fragment), `Expected fragment "${fragment}" preserved in output: ${out}`);
    assert.ok(out.includes(expectedRelPath), `Expected relative path "${expectedRelPath}" in output: ${out}`);
  });
});

// ---------------------------------------------------------------------------
// 5. cross-repo-memo: markdown-list format
// ---------------------------------------------------------------------------

describe('cross-repo-memo — markdown-list format', () => {
  it('markdown-list output has one line per memo (2 lines)', () => {
    const raw = runQuery('cross-repo-memo', ['--format', 'markdown-list']);
    const lines = raw.split('\n').filter(l => l.trim());
    assert.equal(lines.length, 2, `Expected 2 markdown lines; got ${lines.length}: ${raw}`);
  });

  it('each line includes status and from fields', () => {
    const raw = runQuery('cross-repo-memo', ['--format', 'markdown-list']);
    const lines = raw.split('\n').filter(l => l.trim());
    for (const line of lines) {
      assert.ok(line.includes('(from '), `Expected "(from ...)" in line: ${line}`);
    }
  });
});

// ---------------------------------------------------------------------------
// 6. test_query_debt_basic — YAML-backed debt-backlog type
// Review: code-reviewer slice-B F8 — renumbered from duplicate "5." to "6."
// Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C6
// ---------------------------------------------------------------------------

describe('debt — basic query (YAML whole-file frontmatter)', () => {
  it('test_query_debt_basic: --type debt finds both debt fixture records', () => {
    const raw = runQuery('debt', ['--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 2, `Expected 2 debt records; got ${records.length}: ${raw}`);
  });

  it('title field is parsed correctly from whole-file YAML', () => {
    const raw = runQuery('debt', ['--format', 'json']);
    const records = JSON.parse(raw);
    const first = records.find(r => r.frontmatter && r.frontmatter.id === 'DSR-2026-06-15-1');
    assert.ok(first, `Expected DSR-2026-06-15-1 record; got: ${JSON.stringify(records.map(r => r.frontmatter && r.frontmatter.id))}`);
    assert.equal(first.frontmatter.source, 'daily-review/the Staff Engineer/2026-06-15');
    assert.equal(first.frontmatter.severity, 'P2');
  });

  it('--where status=open returns only the open debt item', () => {
    const raw = runQuery('debt', ['--where', 'status=open', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 open debt item; got ${records.length}: ${raw}`);
    assert.equal(records[0].frontmatter.id, 'DSR-2026-06-15-1');
  });

  it('markdown-list format includes severity and source fields', () => {
    const raw = runQuery('debt', ['--where', 'status=open', '--format', 'markdown-list']);
    assert.ok(raw.includes('P2'), `Expected severity P2 in output: ${raw}`);
    assert.ok(raw.includes('(source:'), `Expected "(source:..." in output: ${raw}`);
  });
});

// ---------------------------------------------------------------------------
// 7. test_query_bug_severity — YAML-backed bug-backlog type with --where filter
// Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C6
// ---------------------------------------------------------------------------

describe('bug — severity filter (YAML whole-file frontmatter)', () => {
  it('test_query_bug_severity: --type bug returns both fixture records', () => {
    const raw = runQuery('bug', ['--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 2, `Expected 2 bug records; got ${records.length}: ${raw}`);
  });

  it('--where severity=P1 returns only the P1 bug', () => {
    const raw = runQuery('bug', ['--where', 'severity=P1', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 P1 bug; got ${records.length}: ${raw}`);
    assert.equal(records[0].frontmatter.id, 'BS-2026-06-14-1');
    // Review: code-reviewer Slice-C — (C-F4) schema field is `surface`, not `system`.
    assert.equal(records[0].frontmatter.surface, 'setup/publish');
  });

  it('--where severity=P2 returns only the P2 bug', () => {
    const raw = runQuery('bug', ['--where', 'severity=P2', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 P2 bug; got ${records.length}: ${raw}`);
    assert.equal(records[0].frontmatter.surface, 'coordinator/auto-push');
  });

  it('markdown-list format includes severity and surface fields', () => {
    const raw = runQuery('bug', ['--where', 'severity=P1', '--format', 'markdown-list']);
    assert.ok(raw.includes('P1'), `Expected severity P1 in output: ${raw}`);
    // Review: code-reviewer Slice-C — (C-F4) TYPE_DISPLAY corrected to use `surface`.
    assert.ok(raw.includes('(surface:'), `Expected "(surface:..." in output: ${raw}`);
    assert.ok(raw.includes('setup/publish'), `Expected surface name in output: ${raw}`);
  });
});

// ---------------------------------------------------------------------------
// 8. test_query_improvement_basic — YAML-backed improvement-queue type
// Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C6
// ---------------------------------------------------------------------------

describe('improvement — basic query (YAML whole-file frontmatter)', () => {
  it('test_query_improvement_basic: --type improvement finds the fixture record', () => {
    const raw = runQuery('improvement', ['--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 improvement record; got ${records.length}: ${raw}`);
  });

  it('proposed_action field is parsed and available for filtering', () => {
    const raw = runQuery('improvement', ['--format', 'json']);
    const records = JSON.parse(raw);
    // Review: code-reviewer Slice-C — (C-F4) schema field is `proposed_action`, not `proposed_target`.
    assert.equal(
      records[0].frontmatter.proposed_action,
      'setup/publish.sh (REVIEW_PATTERNS array)',
      `Expected proposed_action field; got: ${JSON.stringify(records[0].frontmatter)}`
    );
  });

  it('markdown-list format includes proposed_action in (action: ...) suffix', () => {
    const raw = runQuery('improvement', ['--format', 'markdown-list']);
    // Review: code-reviewer Slice-C — (C-F4) TYPE_DISPLAY corrected to use `proposed_action`.
    assert.ok(raw.includes('(action:'), `Expected "(action:..." in markdown output: ${raw}`);
    assert.ok(raw.includes('REVIEW_PATTERNS'), `Expected proposed_action value in output: ${raw}`);
  });

  it('from_repo field is parsed correctly from whole-file YAML', () => {
    const raw = runQuery('improvement', ['--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records[0].frontmatter.from_repo, 'coordinator-claude',
      `Expected from_repo=coordinator-claude; got: ${records[0].frontmatter.from_repo}`);
  });
});

// ---------------------------------------------------------------------------
// liveness-records — plan + decision single-axis liveness (tc-1 C4)
//
// Run this group alone:  node --test --test-name-pattern liveness-records bin/query-records.test.js
//
// Verifies the frozen tc-0 liveness mapping table (transcribed verbatim):
//   plan:     draft|reviewed|approved|executing → LIVE
//             deferred                          → BLOCKED
//             implemented|abandoned|superseded  → DONE
//   decision: proposed                          → LIVE
//             accepted|deprecated|superseded    → DONE
//
// CONSTRAINT: plan/decision liveness is PURE single-axis — deployment_state MUST be
// ignored even when present on the frontmatter object. This test asserts that
// explicitly (cross-axis contamination gate).
//
// Regression coverage: spot-checks the tc-0 handoff two-axis and memo single-axis
// rules to confirm they are NOT disturbed by the tc-1 additions.
//
// Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C4
// ---------------------------------------------------------------------------

describe('liveness-records', () => {
  const { liveness } = require('./query-records.js');

  // --- Plan: single-axis status → liveness mapping ---

  it('plan status=draft → LIVE', () => {
    assert.equal(liveness({ status: 'draft' }, 'plan'), 'LIVE');
  });

  it('plan status=reviewed → LIVE', () => {
    assert.equal(liveness({ status: 'reviewed' }, 'plan'), 'LIVE');
  });

  it('plan status=approved → LIVE', () => {
    assert.equal(liveness({ status: 'approved' }, 'plan'), 'LIVE');
  });

  it('plan status=executing → LIVE', () => {
    assert.equal(liveness({ status: 'executing' }, 'plan'), 'LIVE');
  });

  it('plan status=deferred → BLOCKED', () => {
    assert.equal(liveness({ status: 'deferred' }, 'plan'), 'BLOCKED');
  });

  it('plan status=implemented → DONE', () => {
    assert.equal(liveness({ status: 'implemented' }, 'plan'), 'DONE');
  });

  it('plan status=abandoned → DONE', () => {
    assert.equal(liveness({ status: 'abandoned' }, 'plan'), 'DONE');
  });

  it('plan status=superseded → DONE', () => {
    assert.equal(liveness({ status: 'superseded' }, 'plan'), 'DONE');
  });

  // --- Cross-axis contamination gate: deployment_state MUST be ignored for plan ---

  it('plan with deployment_state=awaiting_gate still resolves LIVE (single-axis, not two-axis)', () => {
    assert.equal(liveness({ status: 'draft', deployment_state: 'awaiting_gate' }, 'plan'), 'LIVE');
  });

  it('plan status=implemented with deployment_state=ready_to_fire → DONE (deployment_state ignored)', () => {
    assert.equal(liveness({ status: 'implemented', deployment_state: 'ready_to_fire' }, 'plan'), 'DONE');
  });

  it('plan status=deferred with deployment_state=shipped → BLOCKED (deployment_state ignored)', () => {
    assert.equal(liveness({ status: 'deferred', deployment_state: 'shipped' }, 'plan'), 'BLOCKED');
  });

  // --- Decision: single-axis status → liveness mapping ---

  it('decision status=proposed → LIVE', () => {
    assert.equal(liveness({ status: 'proposed' }, 'decision'), 'LIVE');
  });

  it('decision status=accepted → DONE', () => {
    assert.equal(liveness({ status: 'accepted' }, 'decision'), 'DONE');
  });

  it('decision status=deprecated → DONE', () => {
    assert.equal(liveness({ status: 'deprecated' }, 'decision'), 'DONE');
  });

  it('decision status=superseded → DONE', () => {
    assert.equal(liveness({ status: 'superseded' }, 'decision'), 'DONE');
  });

  // --- Cross-axis contamination gate: deployment_state MUST be ignored for decision ---

  it('decision with deployment_state=awaiting_gate still resolves LIVE (single-axis)', () => {
    assert.equal(liveness({ status: 'proposed', deployment_state: 'awaiting_gate' }, 'decision'), 'LIVE');
  });

  it('decision status=accepted with deployment_state=in_flight → DONE (deployment_state ignored)', () => {
    assert.equal(liveness({ status: 'accepted', deployment_state: 'in_flight' }, 'decision'), 'DONE');
  });

  // --- Regression: tc-0 handoff two-axis rule must be undisturbed ---

  it('handoff two-axis: status=consumed → DONE regardless of deployment_state (tc-0 regression)', () => {
    assert.equal(liveness({ status: 'consumed', deployment_state: 'in_flight' }, 'handoff'), 'DONE');
  });

  it('handoff two-axis: deployment_state=awaiting_gate → BLOCKED with active status (tc-0 regression)', () => {
    assert.equal(liveness({ status: 'active', deployment_state: 'awaiting_gate' }, 'handoff'), 'BLOCKED');
  });

  it('handoff two-axis: deployment_state=shipped → DONE with active status (tc-0 regression)', () => {
    assert.equal(liveness({ status: 'active', deployment_state: 'shipped' }, 'handoff'), 'DONE');
  });

  it('handoff-archived uses same two-axis rule (tc-0 regression)', () => {
    assert.equal(liveness({ status: 'active', deployment_state: 'awaiting_gate' }, 'handoff-archived'), 'BLOCKED');
    assert.equal(liveness({ status: 'superseded', deployment_state: 'ready_to_fire' }, 'handoff-archived'), 'DONE');
  });

  // --- Regression: tc-0 memo single-axis rule must be undisturbed ---

  it('memo: status=actioned → DONE (tc-0 regression)', () => {
    assert.equal(liveness({ status: 'actioned' }, 'cross-repo-memo'), 'DONE');
  });

  it('memo: status=open → LIVE (tc-0 regression)', () => {
    assert.equal(liveness({ status: 'open' }, 'cross-repo-memo'), 'LIVE');
  });

  it('memo: status=reviewed (back-compat alias) → DONE (tc-0 regression)', () => {
    assert.equal(liveness({ status: 'reviewed' }, 'cross-repo-memo'), 'DONE');
  });
});

// ---------------------------------------------------------------------------
// liveness-queues — queue + lesson liveness mapping (tc-2 C9)
//
// Run this group alone:  node --test --test-name-pattern liveness-queues bin/query-records.test.js
// AC5 oracle:            node plugins/coordinator/bin/query-records.test.js -t liveness-queues
//
// Verifies the tc-2 liveness mapping table (canonical-artifact-shapes.md § tc-2):
//   debt/bug/improvement:
//     open      → LIVE
//     deferred  → BLOCKED
//     closed    → DONE
//     wontfix   → DONE   (wontfix is formally bug-only but tested on all queue types)
//   lesson (C3b — stored-status, read from YAML frontmatter):
//     applied | closed | resolved → DONE
//     deferred                    → BLOCKED
//     open | triaged | unknown    → LIVE
//
// Regression guards: confirms tc-1 plan/decision liveness is undisturbed so a future
// edit cannot silently clobber those branches.
//   plan:     deferred → BLOCKED; implemented → DONE
//   decision: accepted → DONE
//
// Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § C9 / AC5
// ---------------------------------------------------------------------------

describe('liveness-queues', () => {
  const { liveness } = require('./query-records.js');

  // --- Debt: single-axis queue status → liveness ---

  it('debt status=open → LIVE', () => {
    assert.equal(liveness({ status: 'open' }, 'debt'), 'LIVE');
  });

  it('debt status=deferred → BLOCKED', () => {
    assert.equal(liveness({ status: 'deferred' }, 'debt'), 'BLOCKED');
  });

  it('debt status=closed → DONE', () => {
    assert.equal(liveness({ status: 'closed' }, 'debt'), 'DONE');
  });

  it('debt status=wontfix → DONE (mapped same as closed for queue types)', () => {
    assert.equal(liveness({ status: 'wontfix' }, 'debt'), 'DONE');
  });

  // --- Bug: single-axis queue status → liveness ---

  it('bug status=open → LIVE', () => {
    assert.equal(liveness({ status: 'open' }, 'bug'), 'LIVE');
  });

  it('bug status=deferred → BLOCKED', () => {
    assert.equal(liveness({ status: 'deferred' }, 'bug'), 'BLOCKED');
  });

  it('bug status=closed → DONE', () => {
    assert.equal(liveness({ status: 'closed' }, 'bug'), 'DONE');
  });

  it('bug status=wontfix → DONE (bug-domain extension — conscious rejection)', () => {
    assert.equal(liveness({ status: 'wontfix' }, 'bug'), 'DONE');
  });

  // --- Improvement: single-axis queue status → liveness ---

  it('improvement status=open → LIVE', () => {
    assert.equal(liveness({ status: 'open' }, 'improvement'), 'LIVE');
  });

  it('improvement status=deferred → BLOCKED', () => {
    assert.equal(liveness({ status: 'deferred' }, 'improvement'), 'BLOCKED');
  });

  it('improvement status=closed → DONE', () => {
    assert.equal(liveness({ status: 'closed' }, 'improvement'), 'DONE');
  });

  it('improvement status=wontfix → DONE', () => {
    assert.equal(liveness({ status: 'wontfix' }, 'improvement'), 'DONE');
  });

  // --- Lesson: stored-status → liveness (C3b — status read from YAML frontmatter) ---
  // Review: code-reviewer Slice-B — (B-F2) rewrite from "derived-from-prose" framing to
  // "stored-status" framing. Lesson liveness is no longer computed from prose markers;
  // it is read from the YAML frontmatter `status` field written by coordinator-lesson-add.
  // Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3b.
  //   applied | closed | resolved  → DONE  (terminal — wiki/doc edit committed and archived)
  //   deferred                     → BLOCKED (explicitly parked with PM auth)
  //   open | triaged | unknown     → LIVE  (triaged = routing decision made, edit in-flight)

  it('lesson status=open → LIVE (stored status: open = not yet routed)', () => {
    assert.equal(liveness({ status: 'open' }, 'lesson'), 'LIVE');
  });

  it('lesson status=resolved → DONE (stored status: resolved = back-compat alias for applied)', () => {
    assert.equal(liveness({ status: 'resolved' }, 'lesson'), 'DONE');
  });

  // Review: code-reviewer Slice-B — (B-F3) add unit cases for the full lesson status enum.
  it('lesson status=applied → DONE (preferred terminal status — wiki edit committed)', () => {
    assert.equal(liveness({ status: 'applied' }, 'lesson'), 'DONE');
  });

  it('lesson status=closed → DONE (back-compat alias for applied)', () => {
    assert.equal(liveness({ status: 'closed' }, 'lesson'), 'DONE');
  });

  it('lesson status=triaged → LIVE (routing decision made, edit in-flight)', () => {
    assert.equal(liveness({ status: 'triaged' }, 'lesson'), 'LIVE');
  });

  it('lesson status=deferred → BLOCKED (explicitly parked with PM auth)', () => {
    assert.equal(liveness({ status: 'deferred' }, 'lesson'), 'BLOCKED');
  });

  // --- TC-1 regression guards: plan/decision liveness undisturbed ---
  // These assertions prevent a future edit from silently clobber-ing tc-1 branches.

  it('plan status=deferred → BLOCKED (tc-1 regression guard)', () => {
    assert.equal(liveness({ status: 'deferred' }, 'plan'), 'BLOCKED');
  });

  it('plan status=implemented → DONE (tc-1 regression guard)', () => {
    assert.equal(liveness({ status: 'implemented' }, 'plan'), 'DONE');
  });

  it('decision status=accepted → DONE (tc-1 regression guard)', () => {
    assert.equal(liveness({ status: 'accepted' }, 'decision'), 'DONE');
  });
});

// ---------------------------------------------------------------------------
// plan-sidecar-exclusion — review-N iteration sidecars (tc-1 C9b)
//
// Verifies that <stem>.review-N.md files (second/Nth distinct-reviewer sidecars)
// are excluded from --type plan results WITHOUT triggering the anomaly warn path.
//
// Fixtures (written in before()):
//   docs/plans/2026-06-25-test-plan-fixture.md          — canonical plan (must be INCLUDED)
//   docs/plans/2026-06-25-test-plan-fixture.review.md   — canonical review sidecar (must be EXCLUDED)
//   docs/plans/2026-06-25-test-plan-fixture.review-2.md — iteration sidecar (must be EXCLUDED, no warn)
//
// Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C9b
// ---------------------------------------------------------------------------

describe('plan-sidecar-exclusion — review-N iteration sidecars (C9b)', () => {
  // Run query-records capturing both stdout and stderr (needed to verify absence of anomaly warn).
  function runQueryWithStderr(type, args) {
    const result = spawnSync(
      process.execPath,
      [QUERY_RECORDS, '--type', type, '--root', tmpRoot, ...args],
      { encoding: 'utf8' }
    );
    return { stdout: (result.stdout || '').trim(), stderr: result.stderr || '' };
  }

  it('.review-2.md is excluded from --type plan results', () => {
    const { stdout } = runQueryWithStderr('plan', ['--format', 'json']);
    const records = JSON.parse(stdout || '[]');
    const paths = records.map(r => r.path);
    const hasReview2 = paths.some(p => p.includes('.review-2.md'));
    assert.ok(!hasReview2,
      `Expected .review-2.md to be excluded from --type plan; got paths: ${paths.join(', ')}`);
  });

  it('.review-2.md exclusion does NOT produce an anomaly warning on stderr', () => {
    const { stderr } = runQueryWithStderr('plan', ['--format', 'json']);
    // Anomaly detector writes "unclassified docs/plans file <basename> —" to stderr.
    // A .review-2.md file must NOT trigger this warning — it is a recognized sidecar form.
    const hasAnomaly = stderr.includes('.review-2.md');
    assert.ok(!hasAnomaly,
      `Expected no anomaly warning for .review-2.md; got stderr: ${stderr}`);
  });

  it('canonical .review.md sidecar is still excluded (sidecar-regex-layer regression)', () => {
    const { stdout } = runQueryWithStderr('plan', ['--format', 'json']);
    const records = JSON.parse(stdout || '[]');
    const paths = records.map(r => r.path);
    const hasReviewSidecar = paths.some(p => /\.review\.md$/.test(p));
    assert.ok(!hasReviewSidecar,
      `Expected .review.md to be excluded from --type plan; got paths: ${paths.join(', ')}`);
  });

  it('canonical plan is still included in --type plan results', () => {
    const { stdout } = runQueryWithStderr('plan', ['--format', 'json']);
    const records = JSON.parse(stdout || '[]');
    const hasPlan = records.some(r =>
      r.path && r.path.includes('2026-06-25-test-plan-fixture.md') && !r.path.includes('review')
    );
    assert.ok(hasPlan,
      `Expected canonical plan to be included in --type plan; got paths: ${records.map(r => r.path).join(', ')}`);
  });
});

// ---------------------------------------------------------------------------
// plan-sidecar-exclusion: full sidecar suffix coverage (F3)
//
// Verifies that ALL four sidecar suffix types are excluded from --type plan,
// not just .review.md. The canonical plan count (1) must be unchanged with
// all four sidecar fixtures present in docs/plans/.
//
// Fixtures (written in before()):
//   2026-06-25-test-plan-fixture.prior-art-check.md   — EXCLUDED
//   2026-06-25-test-plan-fixture.plan-coverage-check.md — EXCLUDED
//   2026-06-25-test-plan-fixture.docs-check.md          — EXCLUDED
//
// Review: code-reviewer slice-B F3 — adds coverage for all sidecar suffix types.
// ---------------------------------------------------------------------------

describe('plan-sidecar-exclusion — full sidecar suffix coverage (F3)', () => {
  function runPlanJson() {
    const result = spawnSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--root', tmpRoot, '--format', 'json'],
      { encoding: 'utf8' }
    );
    return JSON.parse((result.stdout || '').trim() || '[]');
  }

  it('.prior-art-check.md is excluded from --type plan results', () => {
    const records = runPlanJson();
    const paths = records.map(r => r.path);
    const hasPac = paths.some(p => p.includes('.prior-art-check.md'));
    assert.ok(!hasPac,
      `Expected .prior-art-check.md to be excluded from --type plan; got paths: ${paths.join(', ')}`);
  });

  it('.plan-coverage-check.md is excluded from --type plan results', () => {
    const records = runPlanJson();
    const paths = records.map(r => r.path);
    const hasPcc = paths.some(p => p.includes('.plan-coverage-check.md'));
    assert.ok(!hasPcc,
      `Expected .plan-coverage-check.md to be excluded from --type plan; got paths: ${paths.join(', ')}`);
  });

  it('.docs-check.md is excluded from --type plan results', () => {
    const records = runPlanJson();
    const paths = records.map(r => r.path);
    const hasDc = paths.some(p => p.includes('.docs-check.md'));
    assert.ok(!hasDc,
      `Expected .docs-check.md to be excluded from --type plan; got paths: ${paths.join(', ')}`);
  });

  it('canonical plan count is 1 with all sidecar suffix fixtures present', () => {
    const records = runPlanJson();
    // Only 2026-06-25-test-plan-fixture.md is a canonical plan.
    // All sidecar variants + legacy-undated-plan.md are excluded.
    const canonicalPlans = records.filter(r =>
      r.path && r.path.endsWith('2026-06-25-test-plan-fixture.md')
    );
    assert.equal(canonicalPlans.length, 1,
      `Expected exactly 1 canonical plan record; got: ${records.map(r => r.path).join(', ')}`);
  });
});

// ---------------------------------------------------------------------------
// anomaly-detector positive path (F2)
//
// Verifies that a docs/plans file with no date-prefix is:
//   (a) ABSENT from --type plan results
//   (b) triggers the "unclassified docs/plans file" stderr warning
//
// Fixture: legacy-undated-plan.md (written in before()) — no YYYY-MM-DD prefix,
// so it matches neither a canonical sidecar suffix NOR CANONICAL_PLAN_RE.
//
// Review: code-reviewer slice-B F2 — anomaly-detector positive path test.
// ---------------------------------------------------------------------------

describe('anomaly-detector — unclassifiable docs/plans file (F2)', () => {
  function runPlanWithStderr() {
    const result = spawnSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--root', tmpRoot, '--format', 'json'],
      { encoding: 'utf8' }
    );
    return {
      records: JSON.parse((result.stdout || '').trim() || '[]'),
      stderr: result.stderr || '',
    };
  }

  it('legacy-undated-plan.md is absent from --type plan results', () => {
    const { records } = runPlanWithStderr();
    const paths = records.map(r => r.path);
    const hasLegacy = paths.some(p => p.includes('legacy-undated-plan.md'));
    assert.ok(!hasLegacy,
      `Expected legacy-undated-plan.md to be excluded from --type plan; got paths: ${paths.join(', ')}`);
  });

  it('legacy-undated-plan.md triggers the anomaly-detector stderr warning', () => {
    const { stderr } = runPlanWithStderr();
    // The anomaly detector writes: "query-records: unclassified docs/plans file <basename> — excluded..."
    assert.ok(
      stderr.includes('legacy-undated-plan.md'),
      `Expected anomaly warning mentioning "legacy-undated-plan.md" on stderr; got: ${stderr}`
    );
    assert.ok(
      stderr.includes('unclassified docs/plans file'),
      `Expected "unclassified docs/plans file" in stderr anomaly message; got: ${stderr}`
    );
  });
});

// ---------------------------------------------------------------------------
// plan-readme-exclusion — docs/plans/README.md is silently excluded (readme regression)
//
// Regression coverage for example-initiative example-workstream example-repo Ask 4: README.md under docs/plans/
// slips through the canonical sidecar-suffix layer AND through CANONICAL_PLAN_RE, which
// would fire the anomaly-detector warn path and surface a noisy stderr warning.
// The fix adds an explicit basename README check BEFORE the anomaly detector so README.md
// is excluded silently — same as a recognized sidecar, not as an unclassifiable file.
//
// Run this group alone:  node --test --test-name-pattern readme bin/query-records.test.js
//
// Fixture (written in before()): docs/plans/README.md — plain directory-index markdown,
//   no frontmatter required. Must NOT appear in --type plan results; must NOT emit an
//   anomaly-detector warning on stderr.
// ---------------------------------------------------------------------------

describe('plan-readme-exclusion — README.md is silently excluded from --type plan (readme)', () => {
  function runPlanWithStderr() {
    const result = spawnSync(
      process.execPath,
      [QUERY_RECORDS, '--type', 'plan', '--root', tmpRoot, '--format', 'json'],
      { encoding: 'utf8' }
    );
    return {
      records: JSON.parse((result.stdout || '').trim() || '[]'),
      stderr: result.stderr || '',
    };
  }

  it('readme: README.md is absent from --type plan results', () => {
    const { records } = runPlanWithStderr();
    const paths = records.map(r => r.path);
    const hasReadme = paths.some(p => /README\.md$/i.test(p));
    assert.ok(!hasReadme,
      `Expected docs/plans/README.md to be excluded from --type plan results; got paths: ${paths.join(', ')}`);
  });

  it('readme: README.md exclusion does NOT trigger the anomaly-detector stderr warning', () => {
    const { stderr } = runPlanWithStderr();
    // The anomaly detector writes "unclassified docs/plans file README.md —" to stderr.
    // README.md must be excluded BEFORE the anomaly path fires, so no such warning appears.
    const hasReadmeAnomaly = stderr.includes('README.md') && stderr.includes('unclassified docs/plans file');
    assert.ok(!hasReadmeAnomaly,
      `Expected no anomaly warning for README.md; got stderr: ${stderr}`);
  });

  it('readme: legacy-undated-plan.md still fires the anomaly warning (anomaly path intact)', () => {
    // Confirm the README exclusion does not disable the anomaly detector for genuinely
    // unclassifiable files (e.g. legacy-undated-plan.md with no date prefix).
    const { stderr } = runPlanWithStderr();
    assert.ok(
      stderr.includes('legacy-undated-plan.md') && stderr.includes('unclassified docs/plans file'),
      `Expected anomaly warning for legacy-undated-plan.md to still fire; got stderr: ${stderr}`
    );
  });

  it('readme: canonical plan is still included after README fixture is present', () => {
    const { records } = runPlanWithStderr();
    const hasPlan = records.some(r =>
      r.path && r.path.includes('2026-06-25-test-plan-fixture.md') && !r.path.includes('review')
    );
    assert.ok(hasPlan,
      `Expected canonical plan to still appear in --type plan with README.md fixture present; got paths: ${records.map(r => r.path).join(', ')}`);
  });
});

// ---------------------------------------------------------------------------
// liveness-queues-e2e — queryRecords() injects liveness for queue + lesson (F3)
//
// Run this group alone:  node --test --test-name-pattern liveness-queues bin/query-records.test.js
//
// Verifies the post-processing at query-records.js:~1008 that injects the
// synthetic `liveness` field into frontmatter for ALL types, making
// --where liveness= work end-to-end for queue and lesson types.
//
// Fixtures used:
//   DSR-2026-06-15-2 (debt, status=deferred)  → liveness=BLOCKED
//   state/lessons.md (4 entries, status=open) → liveness=LIVE
//
// Review: code-reviewer slice-B F3 — e2e integration assertion for liveness injection.
// Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § C4
// ---------------------------------------------------------------------------

describe('liveness-queues-e2e — queryRecords injects liveness for queue+lesson types (F3)', () => {
  it('deferred debt surfaces liveness=BLOCKED via --where liveness=BLOCKED (F3)', () => {
    const raw = runQuery('debt', ['--where', 'liveness=BLOCKED', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.ok(records.length >= 1,
      `Expected at least 1 BLOCKED debt record; got: ${raw}`);
    const deferred = records.find(r => r.frontmatter && r.frontmatter.id === 'DSR-2026-06-15-2');
    assert.ok(deferred,
      `Expected DSR-2026-06-15-2 (status=deferred) to appear under liveness=BLOCKED; got: ${JSON.stringify(records.map(r => r.frontmatter && r.frontmatter.id))}`);
    assert.equal(deferred.frontmatter.liveness, 'BLOCKED',
      `Expected liveness=BLOCKED on deferred debt record; got: ${deferred.frontmatter.liveness}`);
  });

  it('--type lesson --format json records carry a liveness field (F3)', () => {
    const raw = runQuery('lesson', ['--format', 'json']);
    const records = JSON.parse(raw);
    assert.ok(records.length >= 1,
      `Expected at least 1 lesson record from state/lessons.md fixture; got: ${raw}`);
    for (const r of records) {
      assert.ok(Object.prototype.hasOwnProperty.call(r.frontmatter, 'liveness'),
        `Expected liveness field on lesson record ${r.path}; got: ${JSON.stringify(r.frontmatter)}`);
      assert.ok(['LIVE', 'BLOCKED', 'DONE'].includes(r.frontmatter.liveness),
        `Expected liveness to be LIVE|BLOCKED|DONE on ${r.path}; got: ${r.frontmatter.liveness}`);
    }
  });
});

// ---------------------------------------------------------------------------
// parseLessonsFile — inner-star repair + count oracle (F2 / F6)
//
// Verifies the D3 entryRe fix that allows single * inside bold titles:
//   Old regex: /^\s*[-*]?\s*\*\*([^*]+)\*\*/ — drops entries with inner *
//   New regex: /^\s*[-*]?\s*\*\*((?:[^*]|\*(?!\*))+)\*\*/ — permits single inner *
//
// Fixture (written in before()): state/lessons.md with 4 entries:
//   Entry 1: title contains plugins/*/ glob path (inner *)
//   Entry 2: title contains *italic* span (inner *)
//   Entry 3+4: plain titles without inner *
//
// F6: asserts parsed-entry count == bold-title count for the controlled fixture.
//
// Review: code-reviewer slice-B F2 + F6 — inner-star repair coverage.
// Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § D3
// ---------------------------------------------------------------------------

describe('parseLessonsFile — inner-star repair + count oracle (F2 / F6)', () => {
  const { queryRecords: qr } = require('./query-records.js');
  const lessonOpts = {
    type: 'lesson',
    where: null,
    sort: null,
    limit: 50,
    since: null,
    olderThan: null,
    root: null,
    format: 'json',
    includeUnparseable: false,
  };

  it('all 4 fixture entries parse — inner-* entries are NOT dropped (F2)', () => {
    const records = qr(lessonOpts, tmpRoot);
    assert.equal(records.length, 4,
      `Expected 4 lesson records (including inner-* entries); got ${records.length}: ` +
      records.map(r => r.frontmatter.title).join(', '));
  });

  it('title with plugins/*/ glob path is preserved verbatim (F2)', () => {
    const records = qr(lessonOpts, tmpRoot);
    const globEntry = records.find(r => r.frontmatter.title.includes('plugins/*/'));
    assert.ok(globEntry,
      `Expected entry with plugins/*/ in title; got titles: ${records.map(r => r.frontmatter.title).join(' | ')}`);
    assert.ok(globEntry.frontmatter.title.includes('plugins/*/'),
      `Expected plugins/*/ preserved verbatim; got: ${globEntry.frontmatter.title}`);
  });

  it('title with *italic* span is preserved verbatim (F2)', () => {
    const records = qr(lessonOpts, tmpRoot);
    const italicEntry = records.find(r => r.frontmatter.title.includes('*italic*'));
    assert.ok(italicEntry,
      `Expected entry with *italic* in title; got titles: ${records.map(r => r.frontmatter.title).join(' | ')}`);
    assert.ok(italicEntry.frontmatter.title.includes('*italic*'),
      `Expected *italic* preserved verbatim; got: ${italicEntry.frontmatter.title}`);
  });

  it('parsed-entry count equals bold-title count in controlled fixture (F6)', () => {
    // Ground truth: count lines matching the entry-RE prefix in the controlled fixture.
    const lessonsContent = fs.readFileSync(path.join(tmpRoot, 'state', 'lessons.md'), 'utf8');
    const boldTitleCount = lessonsContent.split('\n')
      .filter(l => /^\s*[-*]?\s*\*\*/.test(l)).length;
    const records = qr(lessonOpts, tmpRoot);
    assert.equal(records.length, boldTitleCount,
      `Parsed-entry count (${records.length}) must equal bold-title count (${boldTitleCount}) in controlled fixture`);
  });
});

// ---------------------------------------------------------------------------
// validate-all-queue-coverage — --validate-all --type <short-name> regression
//
// Regression pin for the bug where --validate-all --type debt (and bug/improvement)
// silently skipped validation and exited 0, because typeToSchemaName['debt'] was
// undefined — the short alias was absent from _buildTypeToSchemaNameMap which only
// iterated schema._byGlob entries (long names: debt-backlog/bug-backlog/improvement-queue).
//
// Also guards the BULK path: --validate-all (no --type) must still exit nonzero
// on the same invalid fixture without double-validating (each file reported once).
//
// Run this group alone:
//   node --test --test-name-pattern='validate-all-queue-coverage' bin/query-records.test.js
//
// Fixtures: isolated tmp dir (separate from the main tmpRoot) to control exactly
// which files exist so the invalid-file count can be asserted precisely.
//
// Spec backlink: Chunk A fix for _buildTypeToSchemaNameMap short-alias gap +
//   seenGlobs dedup in validateAllRecords.
// ---------------------------------------------------------------------------

describe('validate-all-queue-coverage', () => {
  let vaRoot;

  before(() => {
    vaRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'test-va-queue-'));

    // Plant one INVALID debt-backlog entry: status='invalid-status' is not in
    // the enum [open, closed, deferred], and proposed_action is missing (required field).
    // Either violation alone would produce verdict='drift'.
    const debtDir = path.join(vaRoot, 'state', 'debt-backlog');
    fs.mkdirSync(debtDir, { recursive: true });
    fs.writeFileSync(
      path.join(debtDir, 'DSR-INVALID-fixture.yaml'),
      [
        'id: DSR-INVALID-fixture',
        'created: 2026-06-26',
        'source: test-fixture',
        'status: invalid-status',   // not in enum → drift
        'title: Invalid debt fixture for validate-all test',
        'body: This entry has an invalid status to trigger drift.',
        'risk: None — test only.',
        // proposed_action intentionally omitted (required field) → additional drift
      ].join('\n') + '\n',
      'utf8'
    );

    // Review: code-reviewer Slice-C — (C-F1) Plant one INVALID bug-backlog entry:
    // `surface` is a required field (schema: bug-backlog.yaml); omitting it → drift.
    // status='bogus-status' is also not in the enum → additional drift signal.
    const bugDir = path.join(vaRoot, 'state', 'bug-backlog');
    fs.mkdirSync(bugDir, { recursive: true });
    fs.writeFileSync(
      path.join(bugDir, 'BS-INVALID-fixture.yaml'),
      [
        'id: BS-INVALID-fixture',
        'created: 2026-06-26',
        'severity: P2',
        'status: bogus-status',     // not in enum [open, closed, deferred, wontfix] → drift
        'title: Invalid bug fixture for validate-all test',
        'body: This entry has an invalid status to trigger drift.',
        // surface intentionally omitted (required field) → additional drift
      ].join('\n') + '\n',
      'utf8'
    );

    // Review: code-reviewer Slice-C — (C-F1) Plant one INVALID improvement-queue entry:
    // `proposed_action` is a required field (schema: improvement-queue.yaml); omitting it → drift.
    // change_kind='not-a-real-kind' is also not in the enum → additional drift signal.
    const iqDir = path.join(vaRoot, 'state', 'improvement-queue');
    fs.mkdirSync(iqDir, { recursive: true });
    fs.writeFileSync(
      path.join(iqDir, 'IQ-INVALID-fixture.yaml'),
      [
        'id: IQ-INVALID-fixture',
        'created: 2026-06-26',
        'from_repo: test-fixture',
        'surface: bin/query-records.js',
        'status: open',
        'title: Invalid improvement fixture for validate-all test',
        'body: This entry has a missing required field to trigger drift.',
        'change_kind: not-a-real-kind', // not in enum → drift
        // proposed_action intentionally omitted (required field) → additional drift
      ].join('\n') + '\n',
      'utf8'
    );
  });

  after(() => {
    fs.rmSync(vaRoot, { recursive: true, force: true });
  });

  // Helper: run query-records CLI and return { status, stdout, stderr }.
  function runValidate(args) {
    const result = spawnSync(
      process.execPath,
      [QUERY_RECORDS, '--validate-all', '--root', vaRoot, ...args],
      { encoding: 'utf8' }
    );
    return {
      status: result.status,
      stdout: result.stdout || '',
      stderr: result.stderr || '',
    };
  }

  it('--validate-all --type debt exits non-zero on invalid debt entry (regression pin)', () => {
    // Today this exits 0 (the bug) — after the fix it must exit 1.
    const { status, stdout } = runValidate(['--type', 'debt']);
    const ledger = JSON.parse(stdout || '[]');
    assert.ok(ledger.length >= 1,
      `Expected at least 1 ledger entry from --type debt; got: ${stdout}`);
    const driftEntry = ledger.find(e => e.verdict === 'drift');
    assert.ok(driftEntry,
      `Expected a drift entry for the invalid fixture; got ledger: ${JSON.stringify(ledger)}`);
    // Review: code-reviewer Slice-C — (C-F2) ledger must emit canonical long-form schema name,
    //   not the short alias ('debt'); scoped --type debt must also emit 'debt-backlog'.
    assert.equal(driftEntry.type, 'debt-backlog',
      `Expected type 'debt-backlog' in drift entry; got '${driftEntry.type}'`);
    assert.equal(status, 1,
      `Expected exit code 1 from --validate-all --type debt on invalid entry; got ${status}. ` +
      `Ledger: ${JSON.stringify(ledger)}`);
  });

  // Review: code-reviewer Slice-C — (C-F1) Regression pin for --type bug short-alias fix.
  it('--validate-all --type bug exits non-zero on invalid bug entry (regression pin)', () => {
    const { status, stdout } = runValidate(['--type', 'bug']);
    const ledger = JSON.parse(stdout || '[]');
    assert.ok(ledger.length >= 1,
      `Expected at least 1 ledger entry from --type bug; got: ${stdout}`);
    const driftEntry = ledger.find(e => e.verdict === 'drift');
    assert.ok(driftEntry,
      `Expected a drift entry for the invalid bug fixture; got ledger: ${JSON.stringify(ledger)}`);
    // Review: code-reviewer Slice-C — (C-F2) canonical long-form type must be emitted.
    assert.equal(driftEntry.type, 'bug-backlog',
      `Expected type 'bug-backlog' in drift entry; got '${driftEntry.type}'`);
    assert.equal(status, 1,
      `Expected exit code 1 from --validate-all --type bug on invalid entry; got ${status}. ` +
      `Ledger: ${JSON.stringify(ledger)}`);
  });

  // Review: code-reviewer Slice-C — (C-F1) Regression pin for --type improvement short-alias fix.
  it('--validate-all --type improvement exits non-zero on invalid improvement entry (regression pin)', () => {
    const { status, stdout } = runValidate(['--type', 'improvement']);
    const ledger = JSON.parse(stdout || '[]');
    assert.ok(ledger.length >= 1,
      `Expected at least 1 ledger entry from --type improvement; got: ${stdout}`);
    const driftEntry = ledger.find(e => e.verdict === 'drift');
    assert.ok(driftEntry,
      `Expected a drift entry for the invalid improvement fixture; got ledger: ${JSON.stringify(ledger)}`);
    // Review: code-reviewer Slice-C — (C-F2) canonical long-form type must be emitted.
    assert.equal(driftEntry.type, 'improvement-queue',
      `Expected type 'improvement-queue' in drift entry; got '${driftEntry.type}'`);
    assert.equal(status, 1,
      `Expected exit code 1 from --validate-all --type improvement on invalid entry; got ${status}. ` +
      `Ledger: ${JSON.stringify(ledger)}`);
  });

  it('--validate-all (bulk, no --type) exits non-zero on invalid debt entry', () => {
    // Regression guard: the bulk path must still catch the invalid file after the fix.
    const { status, stdout } = runValidate([]);
    const ledger = JSON.parse(stdout || '[]');
    const driftEntries = ledger.filter(e => e.verdict === 'drift');
    assert.ok(driftEntries.length >= 1,
      `Expected at least 1 drift entry from bulk --validate-all; got: ${stdout}`);
    assert.equal(status, 1,
      `Expected exit code 1 from bulk --validate-all on invalid entry; got ${status}. ` +
      `Ledger: ${JSON.stringify(ledger)}`);
  });

  it('bulk --validate-all reports the invalid debt file exactly once (no double-validation)', () => {
    // Guards against the double-validation hazard: debt and debt-backlog both resolve
    // to state/debt-backlog/*.yaml — without seenGlobs dedup each file is reported twice.
    const { stdout } = runValidate([]);
    const ledger = JSON.parse(stdout || '[]');
    const fixtureEntries = ledger.filter(e =>
      e.path && e.path.includes('DSR-INVALID-fixture.yaml')
    );
    assert.equal(fixtureEntries.length, 1,
      `Expected exactly 1 ledger entry for DSR-INVALID-fixture.yaml (no double-validation); ` +
      `got ${fixtureEntries.length}: ${JSON.stringify(fixtureEntries)}`);
    // Review: code-reviewer Slice-C — (C-F2) bulk path must also emit the canonical long-form type.
    assert.equal(fixtureEntries[0].type, 'debt-backlog',
      `Expected type 'debt-backlog' in bulk ledger entry; got '${fixtureEntries[0].type}'`);
  });
});

// ---------------------------------------------------------------------------
// lineage-reachability — batch sweep (C6 GAP1)
//
// Review: code-reviewer F2 — validateAllRecords' reachability integration
// (query-records.js ~1743-1763) had zero test coverage: no fixture exercised
// _checkLineageReachability being called for qtype 'handoff'/'handoff-archived',
// no assertion of the 'drift' verdict + 'lineage-reachability' error-message
// prefix, and no assertion that the kind:recovery same-repo-only carve-out
// survives the BATCH-SWEEP call path (only the write-time hook path was
// covered, by c2-lineage-reachability.test.js).
//
// Fixtures: isolated tmp dir with real git init (the git-history tier needs a
// real repo to query) — a state/handoffs/*.md and an archive/handoffs/*.md
// record each carrying an unresolvable predecessor (→ drift), a predecessor
// resolving via the git-history tier (→ ok), and a kind:recovery record with
// an unreachable predecessor SHA (→ ok, same-repo-only carve-out).
//
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2, § C6 (GAP1)
// ---------------------------------------------------------------------------

describe('lineage-reachability — batch sweep (C6 GAP1)', () => {
  let lrRoot;

  function git(args) {
    return execFileSync('git', args, { cwd: lrRoot, encoding: 'utf8' });
  }

  function writeHandoff(relPath, fm) {
    const abs = path.join(lrRoot, relPath);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    const lines = ['---'];
    Object.keys(fm).forEach(k => {
      const v = fm[k];
      lines.push(v === null ? `${k}: null` : `${k}: ${v}`);
    });
    lines.push('---', '', `# ${path.basename(relPath)}`, '');
    fs.writeFileSync(abs, lines.join('\n'), 'utf8');
    return abs;
  }

  function runValidate(args) {
    const result = spawnSync(
      process.execPath,
      [QUERY_RECORDS, '--validate-all', '--root', lrRoot, ...args],
      { encoding: 'utf8' }
    );
    return {
      status: result.status,
      stdout: result.stdout || '',
      stderr: result.stderr || '',
    };
  }

  before(() => {
    lrRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'test-lineage-reachability-'));
    git(['init', '-q']);
    git(['config', 'user.email', 'test@example.com']);
    git(['config', 'user.name', 'Test']);

    // A live state/handoffs/ record with an unresolvable predecessor.
    writeHandoff('state/handoffs/2026-07-08_000001_live-dangling.md', {
      title: 'live-dangling',
      created: '2026-07-08',
      branch: 'test-branch',
      status: 'active',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Lineage-reachability batch-sweep fixture — live dangling predecessor.',
      predecessor: 'state/handoffs/this-path-provably-never-existed.md',
    });

    // An archive/handoffs/ record with an unresolvable predecessor.
    writeHandoff('archive/handoffs/2026-07-08_000002_archived-dangling.md', {
      title: 'archived-dangling',
      created: '2026-07-08',
      branch: 'test-branch',
      status: 'consumed',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Lineage-reachability batch-sweep fixture — archived dangling predecessor.',
      predecessor: 'state/handoffs/this-other-path-also-never-existed.md',
    });

    // A record whose predecessor resolves via the git-history tier: commit a
    // handoff, then git-rm it, so it's disk-absent but git-reachable.
    const removedRel = 'state/handoffs/2026-07-08_000003_git-history-target.md';
    writeHandoff(removedRel, {
      title: 'git-history-target',
      created: '2026-07-08',
      branch: 'test-branch',
      status: 'consumed',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Lineage-reachability batch-sweep fixture — git-history-only target (removed on disk).',
      predecessor: 'none',
    });
    git(['add', removedRel]);
    git(['commit', '-q', '-m', 'add git-history-target']);
    git(['rm', '-q', removedRel]);
    git(['commit', '-q', '-m', 'remove git-history-target']);

    writeHandoff('state/handoffs/2026-07-08_000004_git-history-referencer.md', {
      title: 'git-history-referencer',
      created: '2026-07-08',
      branch: 'test-branch',
      status: 'active',
      kind: 'session-handoff',
      category: 'infra',
      summary: 'Lineage-reachability batch-sweep fixture — references a git-history-only predecessor.',
      predecessor: path.basename(removedRel),
    });

    // A kind:recovery record with an unreachable predecessor SHA — must stay
    // 'ok' via the same-repo-only foreign-baton carve-out, surviving the
    // batch-sweep call path (not just the write-time hook path).
    writeHandoff('state/handoffs/2026-07-08_000005_recovery-carveout.md', {
      title: 'recovery-carveout',
      created: '2026-07-08',
      branch: 'test-branch',
      status: 'active',
      kind: 'recovery',
      category: 'infra',
      summary: 'Lineage-reachability batch-sweep fixture — kind:recovery unreachable SHA carve-out.',
      predecessor: 'deadbeefcafefeed1234567890abcdef12345678',
    });
  });

  after(() => {
    fs.rmSync(lrRoot, { recursive: true, force: true });
  });

  it('a live state/handoffs/ record with an unresolvable predecessor → drift with lineage-reachability error', () => {
    const { stdout } = runValidate(['--type', 'handoff']);
    const ledger = JSON.parse(stdout || '[]');
    const entry = ledger.find(e => e.path && e.path.includes('live-dangling'));
    assert.ok(entry, `Expected a ledger entry for live-dangling.md; got: ${stdout}`);
    assert.equal(entry.verdict, 'drift');
    assert.ok(
      entry.errors.some(err => err.error && err.error.includes('lineage-reachability')),
      `Expected a lineage-reachability error; got: ${JSON.stringify(entry.errors)}`
    );
  });

  it('an archive/handoffs/ record with an unresolvable predecessor → drift with lineage-reachability error', () => {
    const { stdout } = runValidate(['--type', 'handoff-archived']);
    const ledger = JSON.parse(stdout || '[]');
    const entry = ledger.find(e => e.path && e.path.includes('archived-dangling'));
    assert.ok(entry, `Expected a ledger entry for archived-dangling.md; got: ${stdout}`);
    assert.equal(entry.verdict, 'drift');
    assert.ok(
      entry.errors.some(err => err.error && err.error.includes('lineage-reachability')),
      `Expected a lineage-reachability error; got: ${JSON.stringify(entry.errors)}`
    );
  });

  it('a predecessor resolving via the git-history tier → ok (not flagged as corruption)', () => {
    const { stdout } = runValidate(['--type', 'handoff']);
    const ledger = JSON.parse(stdout || '[]');
    const entry = ledger.find(e => e.path && e.path.includes('git-history-referencer'));
    assert.ok(entry, `Expected a ledger entry for git-history-referencer.md; got: ${stdout}`);
    assert.equal(entry.verdict, 'ok',
      `Expected verdict 'ok' for a git-history-resolvable predecessor; got errors: ${JSON.stringify(entry.errors)}`);
  });

  it('a kind:recovery record with an unreachable predecessor SHA → ok (same-repo-only carve-out survives batch sweep)', () => {
    const { stdout } = runValidate(['--type', 'handoff']);
    const ledger = JSON.parse(stdout || '[]');
    const entry = ledger.find(e => e.path && e.path.includes('recovery-carveout'));
    assert.ok(entry, `Expected a ledger entry for recovery-carveout.md; got: ${stdout}`);
    assert.equal(entry.verdict, 'ok',
      `Expected verdict 'ok' for a kind:recovery unreachable-SHA predecessor; got errors: ${JSON.stringify(entry.errors)}`);
  });
});

// ---------------------------------------------------------------------------
// liveness-parity — SSOT contract parity: liveness() MUST agree with the
// published artifact-shape-contract.schema.json liveness_mapping (tc-4 B1 + v1.4.0)
//
// Run this group alone:
//   node --test --test-name-pattern parity bin/query-records.test.js
//
// Invariant: for every single-axis type in liveness_mapping.types that has a
// mapping object, for each (status → expected) pair in that mapping,
// liveness({status: status}, type) === expected.
//
// Covered types (all single-axis types with a mapping in the contract):
//   roadmap, tracker, health-status, cross-repo-memo, plan, decision,
//   improvement-queue (mapped as 'improvement'), bug-backlog (mapped as 'bug'),
//   debt-backlog (mapped as 'debt'), lesson.
//
// The three new types (roadmap, tracker, health-status) from the prior-chunk
// additions are the primary regression target.  The existing types are asserted
// as regression guards to prevent the contract ↔ implementation from silently
// diverging on any axis.
//
// Spec backlink: bin/emit-artifact-shape-contract.js (LIVENESS_MAPPING § types)
// Contract SSOT: artifact-shape-contract/artifact-shape-contract.schema.json
// ---------------------------------------------------------------------------

describe('liveness-parity — contract agrees with liveness() SSOT (parity)', () => {
  const { liveness } = require('./query-records.js');
  const contractPath = require('path').join(__dirname, '..', 'artifact-shape-contract', 'artifact-shape-contract.schema.json');
  const contract = JSON.parse(require('fs').readFileSync(contractPath, 'utf8'));
  const livenessMapping = contract.liveness_mapping;

  // Map from contract type key → query-records.js --type alias.
  // The contract uses canonical long-form names; query-records.js uses short aliases
  // for the queue types.  Explicit mapping only where they differ.
  const CONTRACT_TYPE_TO_QR_TYPE = {
    'improvement-queue': 'improvement',
    'bug-backlog':       'bug',
    'debt-backlog':      'debt',
    'lesson':            'lesson',
    // All others: contract key == query-records type
  };

  function qrType(contractTypeKey) {
    return CONTRACT_TYPE_TO_QR_TYPE[contractTypeKey] || contractTypeKey;
  }

  // Collect all single-axis types that have a mapping object.
  const singleAxisTypes = Object.entries(livenessMapping.types)
    .filter(([, rule]) => rule.combination_rule === 'single-axis' && rule.mapping);

  // Verify each (type, status, expected) triple.
  for (const [contractKey, rule] of singleAxisTypes) {
    for (const [statusValue, expected] of Object.entries(rule.mapping)) {
      it(`parity: ${contractKey} status=${statusValue} → ${expected}`, () => {
        const type = qrType(contractKey);
        const actual = liveness({ status: statusValue }, type);
        assert.equal(
          actual,
          expected,
          `liveness({status: ${JSON.stringify(statusValue)}}, ${JSON.stringify(type)}) ` +
          `returned ${JSON.stringify(actual)}, contract says ${JSON.stringify(expected)}`
        );
      });
    }
  }

  // Explicit coverage check: confirm the three new types are present in the contract
  // so a future contract-schema-only removal doesn't silently shrink coverage.
  it('parity: contract includes roadmap liveness mapping', () => {
    assert.ok(
      livenessMapping.types.roadmap && livenessMapping.types.roadmap.mapping,
      'Expected roadmap with a mapping object in contract liveness_mapping'
    );
  });

  it('parity: contract includes tracker liveness mapping', () => {
    assert.ok(
      livenessMapping.types.tracker && livenessMapping.types.tracker.mapping,
      'Expected tracker with a mapping object in contract liveness_mapping'
    );
  });

  it('parity: contract includes health-status liveness mapping', () => {
    assert.ok(
      livenessMapping.types['health-status'] && livenessMapping.types['health-status'].mapping,
      'Expected health-status with a mapping object in contract liveness_mapping'
    );
  });

  // decision-guide: consolidated/distilled DR corpus container (2026-06-27).
  // Spec backlink: cross-repo/inbox/2026-06-27-example-stats-repo-decision-records-fleet-share.md § Q2
  it('parity: contract includes decision-guide liveness mapping', () => {
    assert.ok(
      livenessMapping.types['decision-guide'] && livenessMapping.types['decision-guide'].mapping,
      'Expected decision-guide with a mapping object in contract liveness_mapping'
    );
  });

  it('parity: decision-guide status=active → LIVE', () => {
    assert.equal(
      liveness({ status: 'active' }, 'decision-guide'),
      'LIVE',
      'decision-guide active should resolve LIVE'
    );
  });

  it('parity: decision-guide status=archived → DONE', () => {
    assert.equal(
      liveness({ status: 'archived' }, 'decision-guide'),
      'DONE',
      'decision-guide archived should resolve DONE'
    );
  });

  it('parity: decision-guide unknown status → LIVE (open posture)', () => {
    assert.equal(
      liveness({ status: 'unknown-value' }, 'decision-guide'),
      'LIVE',
      'decision-guide unknown status should resolve LIVE (open posture)'
    );
  });
});

// ---------------------------------------------------------------------------
// roadmap — glob fix (state/roadmap/*/OVERVIEW.md) + status normalization
// ---------------------------------------------------------------------------
// Root-cause fix for chunk A3: the flat glob `state/roadmap/*.md` matched nothing
// (records live nested at state/roadmap/<slug>/OVERVIEW.md); fixed to
// `state/roadmap/*/OVERVIEW.md`. Sidecars in the same dir are excluded by the
// OVERVIEW.md-only glob (not a denylist — structural exclusion).
//
// Status normalization (the Director of Engineering F6): coordinator:roadmap-planning uses a richer lifecycle
// vocabulary (e.g. `final-approved`) not in the contract enum. normalizeRoadmapStatus()
// maps these values BEFORE liveness() and validateFrontmatter() see the status.
//
// Spec backlink: docs/plans/2026-06-27-emit-new-record-types-producer-wiring.md § A3 (chunk A3)
// ---------------------------------------------------------------------------

describe('roadmap — glob fix and status normalization', () => {
  it('test_query_roadmap_basic: --type roadmap returns ≥1 record (the OVERVIEW fixture)', () => {
    const raw = runQuery('roadmap', ['--format', 'json']);
    const records = JSON.parse(raw);
    assert.ok(records.length >= 1, `Expected ≥1 roadmap record, got ${records.length}: ${raw}`);
  });

  it('status final-approved is normalized to active (contract-enum conformant)', () => {
    const raw = runQuery('roadmap', ['--format', 'json']);
    const records = JSON.parse(raw);
    const fixture = records.find(r => r.path.includes('test-roadmap-2026-06-27'));
    assert.ok(fixture, 'Expected to find test-roadmap-2026-06-27 fixture');
    assert.equal(
      fixture.frontmatter.status,
      'active',
      `Expected status normalized to "active", got "${fixture.frontmatter.status}"`
    );
  });

  it('normalized status active → liveness LIVE', () => {
    const raw = runQuery('roadmap', ['--format', 'json']);
    const records = JSON.parse(raw);
    const fixture = records.find(r => r.path.includes('test-roadmap-2026-06-27'));
    assert.ok(fixture, 'Expected to find test-roadmap-2026-06-27 fixture');
    assert.equal(
      fixture.frontmatter.liveness,
      'LIVE',
      `Expected liveness LIVE after normalization, got "${fixture.frontmatter.liveness}"`
    );
  });

  it('sidecar OVERVIEW.the Director of Engineering-review.md is NOT included in roadmap query results', () => {
    const raw = runQuery('roadmap', ['--format', 'json']);
    const records = JSON.parse(raw);
    const hasSidecar = records.some(r => r.path.includes('the Director of Engineering-review'));
    assert.ok(!hasSidecar, 'Sidecar OVERVIEW.the Director of Engineering-review.md should not appear in roadmap query');
  });

  it('--where status=active returns the normalized fixture', () => {
    const raw = runQuery('roadmap', ['--where', 'status=active', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.ok(records.length >= 1, `Expected ≥1 active roadmap record after normalization, got ${records.length}`);
    assert.ok(
      records.every(r => r.frontmatter.status === 'active'),
      'All returned records should have status=active'
    );
  });

  // Review: code-reviewer slice-1 F1+F3+F5 — replaced two indirect/bypassing tests with
  // direct table tests. Prior tests imported queryRecords (dead binding) or ran a full
  // e2e query then checked liveness() indirectly, giving zero coverage to the
  // approved/draft/in-review map entries. normalizeRoadmapStatus is now exported so
  // each non-identity entry gets its own assertion on the mutated frontmatter.
  it('normalizeRoadmapStatus: approved → active', () => {
    const { normalizeRoadmapStatus } = require('./query-records.js');
    const fm = { status: 'approved' };
    normalizeRoadmapStatus(fm, 'roadmap');
    assert.equal(fm.status, 'active', 'approved should map to active');
  });

  it('normalizeRoadmapStatus: draft → planning', () => {
    const { normalizeRoadmapStatus } = require('./query-records.js');
    const fm = { status: 'draft' };
    normalizeRoadmapStatus(fm, 'roadmap');
    assert.equal(fm.status, 'planning', 'draft should map to planning');
  });

  it('normalizeRoadmapStatus: in-review → planning', () => {
    const { normalizeRoadmapStatus } = require('./query-records.js');
    const fm = { status: 'in-review' };
    normalizeRoadmapStatus(fm, 'roadmap');
    assert.equal(fm.status, 'planning', 'in-review should map to planning');
  });

  it('normalizeRoadmapStatus: unknown value → active (safe default)', () => {
    const { normalizeRoadmapStatus } = require('./query-records.js');
    const fm = { status: 'some-unknown-roadmap-state' };
    normalizeRoadmapStatus(fm, 'roadmap');
    assert.equal(fm.status, 'active', 'unknown roadmap status should fall back to active');
  });
});
