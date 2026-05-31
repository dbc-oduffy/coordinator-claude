'use strict';
/**
 * query-records.test.js — Tests for cross-repo-memo type, includeUnparseable flag,
 * and the archive/handoffs ledger glob fix.
 *
 * Spec backlink: docs/plans/2026-05-29-query-records-cross-repo-memo-and-includeunparseable.md
 *
 * Covers:
 *   1. --type cross-repo-memo finds inbox memos and filters on status=open
 *   2. Non-memo-shaped file (README.md fixture, no from/to) is silently skipped
 *   3. includeUnparseable: true returns a parseError record for an invalid-frontmatter fixture
 *      while default (false) still skips it
 *   4. handoff-ledger query globs archive/handoffs (not tasks/handoffs/archive)
 *
 * Run with: node --test bin/query-records.test.js
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

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
// 4. handoff-ledger archive glob: archive/handoffs/ (not tasks/handoffs/archive/)
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
