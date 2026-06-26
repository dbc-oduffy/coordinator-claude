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
 *   7. --type improvement returns record with proposed_target in markdown-list output
 *   8. liveness-records: plan + decision single-axis liveness; handoff/memo tc-0 regressions
 *   9. plan-sidecar-exclusion: review-N iteration sidecars excluded; all sidecar suffix types excluded
 *
 * Review: code-reviewer slice-B F5 — Covers: list updated to include liveness-records and
 *   plan-sidecar-exclusion suites.
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
    source: 'daily-review/patrik/2026-06-15',
    status: 'open',
    severity: 'P2',
    title: 'Fan-out overlap pass verifies interface presence, not correctness',
    body: 'Structural gap in fan-out dispatch gate.',
    risk: 'Wrong interface pin causes divergent executor outputs.',
    suggested_action: 'Add correctness check to fan-out gate.',
  });
  writeYamlQueueFixture('debt-backlog', 'DSR-2026-06-15-2.yaml', {
    id: 'DSR-2026-06-15-2',
    created: '2026-06-15',
    source: 'daily-review/patrik/2026-06-15',
    status: 'deferred',
    title: 'Second debt item for filter testing',
    body: 'Another debt item.',
    risk: 'Minor risk.',
    suggested_action: 'Investigate later.',
  });

  // Bug-backlog fixtures — whole-file YAML (no --- delimiters)
  writeYamlQueueFixture('bug-backlog', 'BS-2026-06-14-1.yaml', {
    id: 'BS-2026-06-14-1',
    created: '2026-06-14',
    system: 'setup/publish',
    severity: 'P1',
    status: 'open',
    title: 'publish.sh Phase 4 audit skips unchanged files',
    body: 'Personal data audit only covers newly-synced files.',
  });
  writeYamlQueueFixture('bug-backlog', 'BS-2026-06-14-2.yaml', {
    id: 'BS-2026-06-14-2',
    created: '2026-06-14',
    system: 'coordinator/auto-push',
    severity: 'P2',
    status: 'open',
    title: 'Auto-push skips dirty working tree warning',
    body: 'When working tree is dirty auto-push proceeds without warning.',
  });

  // Improvement-queue fixtures — whole-file YAML (no --- delimiters)
  writeYamlQueueFixture('improvement-queue', 'b7e3d2f1-2026-06-15.yaml', {
    id: 'b7e3d2f1-2026-06-15',
    created: '2026-06-15',
    from_repo: 'coordinator-claude',
    title: 'Promote persona-name word-boundary patterns into REVIEW_PATTERNS',
    body: 'The current patterns miss persona names mid-sentence.',
    surface: 'setup/publish.sh:88-95',
    proposed_target: 'setup/publish.sh (REVIEW_PATTERNS array)',
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

  // F2 fixture: legacy undated plan — triggers the anomaly-detector warn path.
  // No date-prefix → does NOT match CANONICAL_PLAN_RE → excluded with stderr warning.
  // Review: code-reviewer slice-B F2 — anomaly-detector positive path fixture.
  writePlanFixture('legacy-undated-plan.md', {
    title: 'Legacy undated plan (no date prefix)',
    status: 'draft',
  });

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
    assert.equal(first.frontmatter.source, 'daily-review/patrik/2026-06-15');
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
    assert.equal(records[0].frontmatter.system, 'setup/publish');
  });

  it('--where severity=P2 returns only the P2 bug', () => {
    const raw = runQuery('bug', ['--where', 'severity=P2', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 P2 bug; got ${records.length}: ${raw}`);
    assert.equal(records[0].frontmatter.system, 'coordinator/auto-push');
  });

  it('markdown-list format includes severity and system fields', () => {
    const raw = runQuery('bug', ['--where', 'severity=P1', '--format', 'markdown-list']);
    assert.ok(raw.includes('P1'), `Expected severity P1 in output: ${raw}`);
    assert.ok(raw.includes('(system:'), `Expected "(system:..." in output: ${raw}`);
    assert.ok(raw.includes('setup/publish'), `Expected system name in output: ${raw}`);
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

  it('proposed_target field is parsed and available for filtering', () => {
    const raw = runQuery('improvement', ['--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(
      records[0].frontmatter.proposed_target,
      'setup/publish.sh (REVIEW_PATTERNS array)',
      `Expected proposed_target field; got: ${JSON.stringify(records[0].frontmatter)}`
    );
  });

  it('markdown-list format includes proposed_target in (target: ...) suffix', () => {
    const raw = runQuery('improvement', ['--format', 'markdown-list']);
    assert.ok(raw.includes('(target:'), `Expected "(target:..." in markdown output: ${raw}`);
    assert.ok(raw.includes('REVIEW_PATTERNS'), `Expected proposed_target value in output: ${raw}`);
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
// Spec backlink: docs/plans/2026-06-25-qffs-tc-1-records-consolidation.md § C4
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
// AC5 oracle:            node plugins/coordinator-claude/coordinator/bin/query-records.test.js -t liveness-queues
//
// Verifies the tc-2 liveness mapping table (canonical-artifact-shapes.md § tc-2):
//   debt/bug/improvement:
//     open      → LIVE
//     deferred  → BLOCKED
//     closed    → DONE
//     wontfix   → DONE   (wontfix is formally bug-only but tested on all queue types)
//   lesson:
//     open      → LIVE   (default when no resolution marker found)
//     resolved  → DONE   (derived from prose resolution tokens)
//
// Regression guards: confirms tc-1 plan/decision liveness is undisturbed so a future
// edit cannot silently clobber those branches.
//   plan:     deferred → BLOCKED; implemented → DONE
//   decision: accepted → DONE
//
// Spec backlink: docs/plans/2026-06-25-qffs-tc-2-queues-lessons-consolidation.md § C9 / AC5
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

  // --- Lesson: derived status → liveness (D3 — status set by parseLessonsFile) ---
  // 'open' = default when no resolution marker found in prose body.
  // 'resolved' = set when body carries Resolved / SUPERSEDES / → RESOLVED tokens.

  it('lesson status=open → LIVE (no resolution marker found)', () => {
    assert.equal(liveness({ status: 'open' }, 'lesson'), 'LIVE');
  });

  it('lesson status=resolved → DONE (prose resolution marker found)', () => {
    assert.equal(liveness({ status: 'resolved' }, 'lesson'), 'DONE');
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
// Spec backlink: docs/plans/2026-06-25-qffs-tc-1-records-consolidation.md § C9b
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
// Spec backlink: docs/plans/2026-06-25-qffs-tc-2-queues-lessons-consolidation.md § C4
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
// Spec backlink: docs/plans/2026-06-25-qffs-tc-2-queues-lessons-consolidation.md § D3
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
