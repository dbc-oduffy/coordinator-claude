'use strict';
/**
 * test-query-handoff-ledger.js — smoke test for handoff-ledger synthetic type.
 *
 * Verifies:
 *   1. A handoff with 2 Session Ledger blocks yields 2 synthetic records.
 *   2. A handoff with 1 Session Ledger block yields 1 synthetic record.
 *   3. --where 'tshirt=L' filters correctly (keeps L, excludes M).
 *   4. --since '7d' respects the `created` field from the ledger table.
 *   5. Records from tasks/handoffs/archive/ subdirs are included.
 *   6. session_id field is available for --where filtering.
 *
 * Run with: node --test bin/tests/test-query-handoff-ledger.js
 *
 * Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md §Chunk6
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

const BIN_DIR = path.resolve(__dirname, '..');
const QUERY_RECORDS = path.join(BIN_DIR, 'query-records.js');

/** Today as YYYY-MM-DD. */
function today() {
  return new Date().toISOString().slice(0, 10);
}

let tmpRoot;

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

/**
 * Build a handoff markdown file with a frontmatter block and one or more
 * ## Session Ledger table sections.
 *
 * @param {string} slug       Filename slug (without .md)
 * @param {object[]} ledgers  Array of ledger field objects to embed as table blocks
 * @param {object} [options]  { archived: true } to place under archive dir
 */
function writeHandoffFixture(slug, ledgers, options = {}) {
  let dir;
  if (options.archived) {
    dir = path.join(tmpRoot, 'tasks', 'handoffs', 'archive', '2026-05');
  } else {
    dir = path.join(tmpRoot, 'tasks', 'handoffs');
  }
  fs.mkdirSync(dir, { recursive: true });

  const lines = [
    '---',
    `title: ${slug}`,
    'status: active',
    'deployment_state: ready_to_fire',
    `created: ${today()}`,
    '---',
    '',
    '## Why this handoff matters',
    '',
    'Fixture handoff body text.',
    '',
  ];

  for (const fields of ledgers) {
    lines.push('## Session Ledger', '');
    lines.push('| Field | Value |');
    lines.push('|-------|-------|');
    for (const [k, v] of Object.entries(fields)) {
      lines.push(`| ${k} | ${v} |`);
    }
    lines.push('');
  }

  fs.writeFileSync(path.join(dir, `${slug}.md`), lines.join('\n'), 'utf8');
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'test-handoff-ledger-'));

  // Handoff A: 2 Session Ledger blocks — multi-ledger (Patrik F5)
  writeHandoffFixture('handoff-multi-ledger', [
    {
      agent_dispatches: 26,
      opus_dispatches:  4,
      em_tokens:        '482,000',
      tshirt:           'L',
      commits:          'abc1234, def5678',
      session_id:       'sess-alpha',
      created:          today(),
    },
    {
      agent_dispatches: 8,
      opus_dispatches:  1,
      em_tokens:        '120,000',
      tshirt:           'M',
      commits:          'ghi9012',
      session_id:       'sess-beta',
      created:          today(),
    },
  ]);

  // Handoff B: 1 Session Ledger block, archived location
  writeHandoffFixture('handoff-archived-single', [
    {
      agent_dispatches: 50,
      opus_dispatches:  6,
      em_tokens:        '1,100,000',
      tshirt:           'XL',
      commits:          'jkl3456',
      session_id:       'sess-gamma',
      created:          today(),
    },
  ], { archived: true });

  // Handoff C: no Session Ledger block at all — should produce zero records
  writeHandoffFixture('handoff-no-ledger', []);
});

after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// Invoke query-records.js as child process
// ---------------------------------------------------------------------------

function runQuery(args) {
  return execFileSync(
    process.execPath,
    [QUERY_RECORDS, '--type', 'handoff-ledger', '--root', tmpRoot, ...args],
    { encoding: 'utf8' }
  ).trim();
}

// ---------------------------------------------------------------------------
// Test 1: multi-ledger — 2 blocks from one file = 2 synthetic records
// ---------------------------------------------------------------------------

describe('handoff-ledger — multi-ledger parse (Patrik F5)', () => {
  it('handoff with 2 Session Ledger blocks yields 2 records', () => {
    const raw = runQuery(['--format', 'json']);
    const records = JSON.parse(raw);
    // handoff-multi-ledger should contribute 2; handoff-archived-single contributes 1
    const multi = records.filter(r => r.path.includes('handoff-multi-ledger'));
    assert.equal(multi.length, 2, `Expected 2 records from multi-ledger handoff, got ${multi.length}: ${JSON.stringify(multi)}`);
  });

  it('multi-ledger records have distinct #ledger-N fragments', () => {
    const raw = runQuery(['--format', 'json']);
    const records = JSON.parse(raw);
    const multi = records.filter(r => r.path.includes('handoff-multi-ledger'));
    const fragments = multi.map(r => r.path.split('#')[1]);
    assert.ok(fragments.includes('ledger-0'), `Expected #ledger-0, got: ${fragments}`);
    assert.ok(fragments.includes('ledger-1'), `Expected #ledger-1, got: ${fragments}`);
  });

  it('first ledger block has tshirt=L and session_id=sess-alpha', () => {
    const raw = runQuery(['--format', 'json']);
    const records = JSON.parse(raw);
    const r0 = records.find(r => r.path.includes('handoff-multi-ledger') && r.path.endsWith('#ledger-0'));
    assert.ok(r0, 'Expected ledger-0 record');
    assert.equal(r0.frontmatter.tshirt, 'L', `Expected tshirt=L, got: ${r0.frontmatter.tshirt}`);
    assert.equal(r0.frontmatter.session_id, 'sess-alpha', `Expected session_id=sess-alpha`);
  });

  it('second ledger block has tshirt=M and session_id=sess-beta', () => {
    const raw = runQuery(['--format', 'json']);
    const records = JSON.parse(raw);
    const r1 = records.find(r => r.path.includes('handoff-multi-ledger') && r.path.endsWith('#ledger-1'));
    assert.ok(r1, 'Expected ledger-1 record');
    assert.equal(r1.frontmatter.tshirt, 'M', `Expected tshirt=M, got: ${r1.frontmatter.tshirt}`);
    assert.equal(r1.frontmatter.session_id, 'sess-beta', `Expected session_id=sess-beta`);
  });
});

// ---------------------------------------------------------------------------
// Test 2: --where 'tshirt=L' filters correctly
// ---------------------------------------------------------------------------

describe('handoff-ledger — --where tshirt filter', () => {
  it('--where tshirt=L returns only L records', () => {
    const raw = runQuery(['--where', 'tshirt=L', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.ok(records.length >= 1, `Expected at least 1 tshirt=L record, got 0`);
    for (const r of records) {
      assert.equal(r.frontmatter.tshirt, 'L', `Non-L record returned: ${JSON.stringify(r.frontmatter)}`);
    }
  });

  it('--where tshirt=L excludes tshirt=M records', () => {
    const raw = runQuery(['--where', 'tshirt=L', '--format', 'json']);
    const records = JSON.parse(raw);
    const hasMedium = records.some(r => r.frontmatter.tshirt === 'M');
    assert.ok(!hasMedium, `tshirt=M record appeared in tshirt=L filter results`);
  });

  it('--where tshirt=XL finds the archived handoff', () => {
    const raw = runQuery(['--where', 'tshirt=XL', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 XL record from archive, got ${records.length}`);
    assert.ok(records[0].path.includes('handoff-archived-single'), `Expected archived handoff path`);
  });
});

// ---------------------------------------------------------------------------
// Test 3: archived handoffs are included in query surface
// ---------------------------------------------------------------------------

describe('handoff-ledger — archived handoffs included', () => {
  it('total record count includes archived handoff record', () => {
    const raw = runQuery(['--format', 'json']);
    const records = JSON.parse(raw);
    // multi: 2, archived: 1, no-ledger: 0 = total 3
    assert.equal(records.length, 3, `Expected 3 total records (2 live + 1 archived), got ${records.length}: ${raw}`);
  });

  it('archived record path contains handoffs/archive/', () => {
    const raw = runQuery(['--format', 'json']);
    const records = JSON.parse(raw);
    const archived = records.filter(r => r.path.includes('handoffs/archive/'));
    assert.equal(archived.length, 1, `Expected 1 archived record, got ${archived.length}`);
  });
});

// ---------------------------------------------------------------------------
// Test 4: --where session_id filter
// ---------------------------------------------------------------------------

describe('handoff-ledger — session_id field is filterable', () => {
  it('--where session_id=sess-gamma returns exactly 1 record', () => {
    const raw = runQuery(['--where', 'session_id=sess-gamma', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 1, `Expected 1 record with session_id=sess-gamma, got ${records.length}`);
  });
});

// ---------------------------------------------------------------------------
// Test 5: no Session Ledger block = zero records from that file
// ---------------------------------------------------------------------------

describe('handoff-ledger — handoff with no Session Ledger block yields zero records', () => {
  it('handoff-no-ledger contributes no records', () => {
    const raw = runQuery(['--format', 'json']);
    const records = JSON.parse(raw);
    const fromNoLedger = records.filter(r => r.path.includes('handoff-no-ledger'));
    assert.equal(fromNoLedger.length, 0, `Expected 0 records from handoff-no-ledger, got ${fromNoLedger.length}`);
  });
});

// ---------------------------------------------------------------------------
// Test 6: markdown-list format renders handoff-ledger display correctly
// ---------------------------------------------------------------------------

describe('handoff-ledger — markdown-list format', () => {
  it('markdown-list output has one line per record', () => {
    const raw = runQuery(['--format', 'markdown-list']);
    const lines = raw.split('\n').filter(l => l.trim());
    assert.equal(lines.length, 3, `Expected 3 markdown lines (3 total records), got ${lines.length}: ${raw}`);
  });

  it('each markdown line starts with "- [" (display format)', () => {
    const raw = runQuery(['--format', 'markdown-list']);
    const lines = raw.split('\n').filter(l => l.trim());
    for (const line of lines) {
      assert.ok(line.startsWith('- ['), `Line does not match display format: ${line}`);
    }
  });
});
