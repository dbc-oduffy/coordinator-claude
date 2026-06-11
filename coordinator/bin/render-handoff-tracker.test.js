'use strict';
/**
 * render-handoff-tracker.test.js — Tests for the handoff tracker renderer.
 *
 * Spec backlink: docs/plans/2026-05-29-handoff-tracker-renderer.md
 *
 * Covers:
 *   1. Table shape correct (expected headers, expected column count in rows)
 *   2. Terminal-state handoffs excluded (shipped/abandoned deployment_state, consumed status)
 *   3. Bad-frontmatter fixture yields a ⚠ PARSE-ERROR row (not dropped) — AC8
 *   4. Workstream-count math ("2 of 3") — live + archived denominator
 *   5. Null-workstream handoff renders "standalone" (no seq, no shared null bucket)
 *   6. Roadmap-kind row shows tc_id and blocked_by columns
 *   7. Memo table shows open memos only (actioned excluded)
 *
 * Run with: node --test bin/render-handoff-tracker.test.js
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');

// We import the renderer as a library (renderRepoSection, buildWorkstreamIndex, etc.)
const {
  renderRepoSection,
  buildWorkstreamIndex,
  workstreamSeq,
  isActive,
} = require('./render-handoff-tracker.js');

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

let tmpRoot;

function writeFile(absPath, content) {
  fs.mkdirSync(path.dirname(absPath), { recursive: true });
  fs.writeFileSync(absPath, content, 'utf8');
}

/**
 * Write a handoff fixture at state/handoffs/<filename>.
 * `fields` is an object whose entries are written as YAML frontmatter.
 */
function writeHandoff(filename, fields, body = '') {
  const dir = path.join(tmpRoot, 'state', 'handoffs');
  fs.mkdirSync(dir, { recursive: true });
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    if (Array.isArray(v)) {
      lines.push(`${k}:`);
      for (const item of v) lines.push(`  - ${item}`);
    } else {
      lines.push(`${k}: ${v}`);
    }
  }
  lines.push('---', '', body || '# Handoff body');
  writeFile(path.join(dir, filename), lines.join('\n'));
}

/**
 * Write an archived handoff at archive/handoffs/<filename>.
 */
function writeArchivedHandoff(filename, fields, body = '') {
  const dir = path.join(tmpRoot, 'archive', 'handoffs');
  fs.mkdirSync(dir, { recursive: true });
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    if (Array.isArray(v)) {
      lines.push(`${k}:`);
      for (const item of v) lines.push(`  - ${item}`);
    } else {
      lines.push(`${k}: ${v}`);
    }
  }
  lines.push('---', '', body || '# Archived handoff body');
  writeFile(path.join(dir, filename), lines.join('\n'));
}

/**
 * Write a cross-repo memo at cross-repo/inbox/<filename>.
 */
function writeMemo(filename, fields) {
  const dir = path.join(tmpRoot, 'cross-repo', 'inbox');
  fs.mkdirSync(dir, { recursive: true });
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    lines.push(`${k}: "${v}"`);
  }
  lines.push('---', '', 'Memo body.');
  writeFile(path.join(dir, filename), lines.join('\n'));
}

// ---------------------------------------------------------------------------
// Setup: build a rich fixture repo tree
// ---------------------------------------------------------------------------

before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'test-handoff-tracker-'));

  // ---- Active handoffs (should appear) ----

  // H1: plain session-handoff, active, with workstream
  writeHandoff('2026-05-01_120000_h1.md', {
    title: 'Active handoff alpha',
    created: '2026-05-01',
    status: 'active',
    deployment_state: 'ready_to_fire',
    workstream: 'ws-alpha',
  });

  // H2: recovery kind, active, same workstream
  writeHandoff('2026-05-02_120000_h2.md', {
    title: 'Recovery handoff alpha',
    created: '2026-05-02',
    status: 'active',
    kind: 'recovery',
    deployment_state: 'awaiting_gate',
    workstream: 'ws-alpha',
  });

  // H3: active, NO workstream → standalone
  writeHandoff('2026-05-03_120000_h3.md', {
    title: 'Standalone handoff no-ws',
    created: '2026-05-03',
    status: 'active',
    deployment_state: 'ready_to_fire',
    // intentionally no workstream field
  });

  // ---- Terminal-state handoffs (should NOT appear) ----

  // H4: deployment_state=shipped → excluded
  writeHandoff('2026-05-04_120000_h4-shipped.md', {
    title: 'Shipped handoff',
    created: '2026-05-04',
    status: 'active',
    deployment_state: 'shipped',
    workstream: 'ws-alpha',
  });

  // H5: deployment_state=abandoned → excluded
  writeHandoff('2026-05-05_120000_h5-abandoned.md', {
    title: 'Abandoned handoff',
    created: '2026-05-05',
    status: 'active',
    deployment_state: 'abandoned',
    workstream: 'ws-alpha',
  });

  // H6: status=consumed → excluded
  writeHandoff('2026-05-06_120000_h6-consumed.md', {
    title: 'Consumed handoff',
    created: '2026-05-06',
    status: 'consumed',
    deployment_state: 'ready_to_fire',
    workstream: 'ws-alpha',
  });

  // H7: status=superseded → excluded
  writeHandoff('2026-05-07_120000_h7-superseded.md', {
    title: 'Superseded handoff',
    created: '2026-05-07',
    status: 'superseded',
    deployment_state: 'ready_to_fire',
    workstream: 'ws-alpha',
  });

  // ---- Bad-frontmatter fixture (should yield PARSE-ERROR row) ----

  // H8: no frontmatter block at all
  writeFile(
    path.join(tmpRoot, 'state', 'handoffs', '2026-05-08_bad-frontmatter.md'),
    'This file has no frontmatter block.\n\nJust body text with no --- delimiters.'
  );

  // ---- Spinoff (spinoff kind) ----

  writeHandoff('2026-05-10_120000_s1-spinoff.md', {
    title: 'Spinoff beta',
    created: '2026-05-10',
    status: 'active',
    kind: 'spinoff',
    deployment_state: 'ready_to_fire',
    workstream: 'ws-beta',
    predecessor: 'none',
    authoring_session: 'sess-abc',
  });

  // ---- Roadmap spinoff (spinoff-roadmap kind) ----

  writeHandoff('2026-05-11_120000_s2-roadmap.md', {
    title: 'Roadmap ticket tc-05',
    created: '2026-05-11',
    status: 'active',
    kind: 'spinoff-roadmap',
    deployment_state: 'ready_to_fire',
    workstream: 'roadmap-ws-tc-05',
    predecessor: 'none',
    roadmap_id: 'roadmap-2026-05',
    tc_id: 'tc-05',
    sprint: '2',
    wave: '1',
    cost: 'T1',
    // blocked_by as YAML list
  });
  // Re-write with proper YAML list for blocked_by
  writeHandoff('2026-05-11_120000_s2-roadmap.md', {
    title: 'Roadmap ticket tc-05',
    created: '2026-05-11',
    status: 'active',
    kind: 'spinoff-roadmap',
    deployment_state: 'ready_to_fire',
    workstream: 'roadmap-ws-tc-05',
    predecessor: 'none',
    roadmap_id: 'roadmap-2026-05',
    tc_id: 'tc-05',
    sprint: '2',
    wave: '1',
    cost: 'T1',
    blocked_by: ['tc-03', 'tc-04'],
  });

  // ---- Archived handoffs for workstream-seq denominator ----
  // ws-alpha should have: h1 (live active), h2 (live active), h4 (live shipped),
  // h5 (live abandoned), h6 (live consumed), h7 (live superseded) = 6 live
  // + 1 archived below = 7 total for ws-alpha denominator
  writeArchivedHandoff('2026-04-30_120000_h0-archived.md', {
    title: 'Archived ws-alpha handoff',
    created: '2026-04-30',
    status: 'consumed',
    deployment_state: 'shipped',
    workstream: 'ws-alpha',
  });

  // ---- Cross-repo memos ----

  // Memo 1: open — should appear
  writeMemo('2026-05-20-memo-open.md', {
    title: 'Open memo for testing',
    from: 'repo-a-em',
    to: 'central-em',
    status: 'open',
    created: '2026-05-20',
    delivery_mode: 'receiver-repo',
  });

  // Memo 2: actioned — should NOT appear (filtered by status=open check)
  writeMemo('2026-05-21-memo-actioned.md', {
    title: 'Actioned memo for testing',
    from: 'repo-b-em',
    to: 'central-em',
    status: 'actioned',
    created: '2026-05-21',
    delivery_mode: 'receiver-repo',
  });
});

after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// Test 1: Table shape correct
// ---------------------------------------------------------------------------

describe('render-handoff-tracker — table shape', () => {
  it('output contains the Handoffs section header', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('## Handoffs'), `Expected "## Handoffs" section; got:\n${md.slice(0, 300)}`);
  });

  it('output contains the Spinoffs section header', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('## Spinoffs'), `Expected "## Spinoffs" section`);
  });

  it('output contains the Cross-Repo Memos section header', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('## Cross-Repo Memos'), `Expected "## Cross-Repo Memos" section`);
  });

  it('Handoffs table has expected header columns', () => {
    const md = renderRepoSection(tmpRoot);
    // The header line must contain File, Created, State, Category, Summary, Workstream-Seq
    const handoffsIdx = md.indexOf('## Handoffs');
    assert.ok(handoffsIdx >= 0, 'No Handoffs section');
    const after = md.slice(handoffsIdx);
    const headerLine = after.split('\n').find(l => l.startsWith('| File'));
    assert.ok(headerLine, `Expected handoff table header starting with "| File"; section:\n${after.slice(0, 300)}`);
    for (const col of ['Created', 'State', 'Category', 'Summary', 'Workstream-Seq']) {
      assert.ok(headerLine.includes(col), `Missing column "${col}" in header: ${headerLine}`);
    }
  });

  it('Spinoffs table has expected header columns including tc_id and blocked_by', () => {
    const md = renderRepoSection(tmpRoot);
    const spinoffsIdx = md.indexOf('## Spinoffs');
    assert.ok(spinoffsIdx >= 0);
    const after = md.slice(spinoffsIdx);
    const headerLine = after.split('\n').find(l => l.startsWith('| File'));
    assert.ok(headerLine, `Expected spinoff table header; section:\n${after.slice(0, 300)}`);
    // roadmap spinoff exists in fixtures — tc_id and blocked_by must appear
    assert.ok(headerLine.includes('tc_id'), `Expected tc_id in spinoff header: ${headerLine}`);
    assert.ok(headerLine.includes('blocked_by'), `Expected blocked_by in spinoff header: ${headerLine}`);
  });

  it('Memos table has expected header columns', () => {
    const md = renderRepoSection(tmpRoot);
    const memosIdx = md.indexOf('## Cross-Repo Memos');
    assert.ok(memosIdx >= 0);
    const after = md.slice(memosIdx);
    const headerLine = after.split('\n').find(l => l.startsWith('| File'));
    assert.ok(headerLine, `Expected memos table header; section:\n${after.slice(0, 300)}`);
    for (const col of ['From', 'To', 'Status', 'Summary']) {
      assert.ok(headerLine.includes(col), `Missing column "${col}" in memo header: ${headerLine}`);
    }
  });
});

// ---------------------------------------------------------------------------
// Test 2: Terminal-state handoffs excluded
// ---------------------------------------------------------------------------

describe('render-handoff-tracker — terminal-state exclusion', () => {
  it('shipped handoff title does not appear in output', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(!md.includes('Shipped handoff'), `"Shipped handoff" should be excluded; found in output`);
  });

  it('abandoned handoff title does not appear in output', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(!md.includes('Abandoned handoff'), `"Abandoned handoff" should be excluded`);
  });

  it('consumed handoff title does not appear in output', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(!md.includes('Consumed handoff'), `"Consumed handoff" should be excluded`);
  });

  it('superseded handoff title does not appear in output', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(!md.includes('Superseded handoff'), `"Superseded handoff" should be excluded`);
  });

  it('active handoffs DO appear in output', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('Active handoff alpha'), `"Active handoff alpha" should appear`);
    assert.ok(md.includes('Recovery handoff alpha'), `"Recovery handoff alpha" should appear`);
  });
});

// ---------------------------------------------------------------------------
// Test 3: Bad-frontmatter yields PARSE-ERROR row (AC8)
// ---------------------------------------------------------------------------

describe('render-handoff-tracker — AC8 parse-error fail-loud', () => {
  it('PARSE-ERROR marker appears for bad-frontmatter fixture', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('⚠ PARSE-ERROR'), `Expected "⚠ PARSE-ERROR" row; output snippet:\n${md.slice(0, 500)}`);
  });

  it('PARSE-ERROR row contains the bad-frontmatter filename', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(
      md.includes('bad-frontmatter'),
      `Expected bad-frontmatter path in PARSE-ERROR row; output snippet:\n${md.slice(0, 500)}`
    );
  });
});

// ---------------------------------------------------------------------------
// Test 4: Workstream-seq math ("N of M")
// ---------------------------------------------------------------------------

describe('render-handoff-tracker — workstream-seq math', () => {
  it('buildWorkstreamIndex counts live + archived for ws-alpha denominator', () => {
    const wsMap = buildWorkstreamIndex(tmpRoot);
    const alphaDates = wsMap.get('ws-alpha');
    assert.ok(alphaDates, 'ws-alpha should be in the workstream index');
    // Live: h1(05-01), h2(05-02), h4(05-04), h5(05-05), h6(05-06), h7(05-07) = 6
    // Archived: h0(04-30) = 1
    // Total = 7
    assert.equal(alphaDates.length, 7, `Expected 7 ws-alpha entries (6 live + 1 archived); got ${alphaDates.length}: ${alphaDates.join(', ')}`);
  });

  it('workstreamSeq returns "N of 7" for ws-alpha entries', () => {
    const wsMap = buildWorkstreamIndex(tmpRoot);
    const seq = workstreamSeq(wsMap, 'ws-alpha', '2026-05-01');
    assert.ok(typeof seq === 'string' && seq.endsWith('of 7'),
      `Expected "N of 7" for ws-alpha 2026-05-01; got: ${seq}`);
  });

  it('workstreamSeq returns "3 of 7" for 2026-05-02 in ws-alpha (third slot after archived 04-30 + 05-01)', () => {
    const wsMap = buildWorkstreamIndex(tmpRoot);
    // Dates sorted ascending: 04-30(archived), 05-01, 05-02, 05-04, 05-05, 05-06, 05-07
    // 2026-05-02 is index 2 (0-based) → rank 3
    const seq = workstreamSeq(wsMap, 'ws-alpha', '2026-05-02');
    assert.equal(seq, '3 of 7', `Expected "3 of 7" for 2026-05-02 in ws-alpha; got: ${seq}`);
  });

  it('rendered output contains "of 7" for ws-alpha rows', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('of 7'), `Expected "of 7" in rendered output for ws-alpha rows; output:\n${md.slice(0, 800)}`);
  });
});

// ---------------------------------------------------------------------------
// Test 5: Null-workstream renders "standalone" (no seq, no null bucket)
// ---------------------------------------------------------------------------

describe('render-handoff-tracker — null-workstream standalone', () => {
  it('standalone handoff appears in handoffs table', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('Standalone handoff no-ws'), `Expected standalone handoff title in output`);
  });

  it('standalone handoff shows "standalone" in seq column (not "null" or empty)', () => {
    const md = renderRepoSection(tmpRoot);
    // Find the row for the standalone handoff — it should contain 'standalone'
    const lines = md.split('\n');
    const row = lines.find(l => l.includes('Standalone handoff no-ws'));
    assert.ok(row, `Expected a row containing "Standalone handoff no-ws"`);
    assert.ok(row.includes('standalone'), `Expected "standalone" in the row; got: ${row}`);
  });

  it('null-workstream handoff does not contribute to any workstream in wsMap', () => {
    const wsMap = buildWorkstreamIndex(tmpRoot);
    // The standalone handoff (h3) has no workstream field — should not appear under any key
    // Check that there is no "undefined" or "null" key
    assert.ok(!wsMap.has(undefined), 'wsMap should not have undefined key');
    assert.ok(!wsMap.has(null), 'wsMap should not have null key');
    assert.ok(!wsMap.has(''), 'wsMap should not have empty-string key');
  });
});

// ---------------------------------------------------------------------------
// Test 6: Roadmap-kind row shows tc_id and blocked_by
// ---------------------------------------------------------------------------

describe('render-handoff-tracker — roadmap spinoff columns', () => {
  it('tc_id "tc-05" appears in spinoffs table', () => {
    const md = renderRepoSection(tmpRoot);
    const spinoffsIdx = md.indexOf('## Spinoffs');
    const spinoffsSection = md.slice(spinoffsIdx);
    assert.ok(spinoffsSection.includes('tc-05'), `Expected tc_id "tc-05" in Spinoffs section; got:\n${spinoffsSection.slice(0, 400)}`);
  });

  it('blocked_by values appear in spinoffs table', () => {
    const md = renderRepoSection(tmpRoot);
    const spinoffsIdx = md.indexOf('## Spinoffs');
    const spinoffsSection = md.slice(spinoffsIdx);
    assert.ok(
      spinoffsSection.includes('tc-03') || spinoffsSection.includes('tc-04'),
      `Expected blocked_by "tc-03, tc-04" in Spinoffs section; got:\n${spinoffsSection.slice(0, 400)}`
    );
  });

  it('roadmap spinoff title appears in spinoffs table', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(md.includes('Roadmap ticket tc-05'), `Expected roadmap spinoff title in output`);
  });
});

// ---------------------------------------------------------------------------
// Test 7: Memo table shows open memos only
// ---------------------------------------------------------------------------

describe('render-handoff-tracker — open memos only', () => {
  it('open memo title appears in memos table', () => {
    const md = renderRepoSection(tmpRoot);
    const memosIdx = md.indexOf('## Cross-Repo Memos');
    const memosSection = md.slice(memosIdx);
    assert.ok(memosSection.includes('Open memo for testing'), `Expected open memo title; got:\n${memosSection.slice(0, 400)}`);
  });

  it('actioned memo title does NOT appear in memos table', () => {
    const md = renderRepoSection(tmpRoot);
    assert.ok(!md.includes('Actioned memo for testing'), `"Actioned memo for testing" should be excluded`);
  });

  it('isActive helper: active/ready_to_fire returns true', () => {
    assert.ok(isActive({ status: 'active', deployment_state: 'ready_to_fire' }));
  });

  it('isActive helper: consumed returns false', () => {
    assert.ok(!isActive({ status: 'consumed', deployment_state: 'shipped' }));
  });

  it('isActive helper: abandoned returns false', () => {
    assert.ok(!isActive({ status: 'active', deployment_state: 'abandoned' }));
  });

  it('isActive helper: null frontmatter returns false', () => {
    assert.ok(!isActive(null));
  });
});
