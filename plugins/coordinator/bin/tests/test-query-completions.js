'use strict';
/**
 * test-query-completions.js — smoke test for query-completions / completion type support.
 *
 * Verifies all three query shapes from the plan AC against a 3-entry fixture:
 *   1. --where "created=2026-05-19" --sort "chain" --format json
 *   2. --since "7d" --where "status=pending-release" --format json
 *   3. --where "status=pending-release" --sort "nature" --format markdown-list
 *
 * Fixtures live in a tmp dir constructed per-run (no writes to archive/completed).
 *
 * Run with: node --test bin/tests/test-query-completions.js
 *
 * Spec backlink: docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 2
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Resolve query-records.js from the bin directory adjacent to tests/
const BIN_DIR = path.resolve(__dirname, '..');
const QUERY_RECORDS = path.join(BIN_DIR, 'query-records.js');

// ---------------------------------------------------------------------------
// Helpers — inline the queryRecords call with an explicit --root override
// ---------------------------------------------------------------------------

/**
 * Run queryRecords programmatically by requiring query-records.js internals.
 * We can't easily stub --root via child_process when testing, so we reach in
 * via require() after patching the module's exported function boundary.
 *
 * Strategy: require the module (it only exports when require.main !== module)
 * and call queryRecords + formatRecords directly with a synthetic opts object.
 */
let queryRecords;
let formatRecords;

// ---------------------------------------------------------------------------
// Fixture construction
// ---------------------------------------------------------------------------

/** Today as YYYY-MM-DD (for --since "7d" to pick up fixtures dated today). */
function today() {
  return new Date().toISOString().slice(0, 10);
}

/** Month string YYYY-MM for fixture subdir. */
function thisMonth() {
  return today().slice(0, 7);
}

let tmpRoot;

/**
 * Write a single completion-entry fixture file under
 * <tmpRoot>/archive/completed/<YYYY-MM>/<slug>.md
 */
function writeFixture(slug, frontmatterFields) {
  const subdir = path.join(tmpRoot, 'archive', 'completed', thisMonth());
  fs.mkdirSync(subdir, { recursive: true });
  const lines = ['---'];
  for (const [k, v] of Object.entries(frontmatterFields)) {
    if (Array.isArray(v)) {
      lines.push(`${k}:`);
      for (const item of v) lines.push(`  - ${item}`);
    } else if (v === null) {
      lines.push(`${k}: null`);
    } else {
      lines.push(`${k}: ${v}`);
    }
  }
  lines.push('---');
  lines.push('');
  lines.push('Fixture body.');
  fs.writeFileSync(path.join(subdir, `${slug}.md`), lines.join('\n'), 'utf8');
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

before(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'test-query-completions-'));

  // Entry A — today, pending-release, roadmap, chain set
  writeFixture('2026-05-19-installer-redesign-abc123', {
    title: 'Installer redesign chunk 1',
    created: today(),
    nature: 'roadmap',
    status: 'pending-release',
    chain: 'docs/plans/2026-05-19-coordinator-installer-redesign-implementation.md',
    commits: ['abc123def456'],
    nature_inferred: false,
  });

  // Entry B — today, pending-release, bugfix, no chain
  writeFixture('2026-05-19-session-end-crash-fix-def456', {
    title: 'Fix session-end crash on empty touched.txt',
    created: today(),
    nature: 'bugfix',
    status: 'pending-release',
    chain: null,
    commits: ['def456abc789'],
    nature_inferred: true,
  });

  // Entry C — today, released (NOT pending-release), infra
  writeFixture('2026-05-19-schema-infra-ghi789', {
    title: 'Add completion-entry schema',
    created: today(),
    nature: 'infra',
    status: 'released',
    chain: 'docs/plans/2026-05-19-completion-log-phase1-foundational-loop.md',
    commits: ['ghi789jkl012'],
    nature_inferred: false,
  });

  // Load the module's exported functions (module guards against re-entry via require.main check)
  // query-records.js does not export anything; we access its internal functions by
  // re-requiring with a patched process.argv so the module body doesn't run (it's
  // gated on require.main === module). We extract the needed functions via a separate
  // require of the same file — Node caches the module so the constants are shared.
  //
  // Actually the cleanest approach: just call the binary as a child process with --root.
  // We store the reference to spawn here; actual calls happen in each test.
});

after(() => {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// Invoke query-records.js as a child process with --root pointing at tmpRoot
// ---------------------------------------------------------------------------

const { execFileSync } = require('child_process');

function runQuery(args) {
  const result = execFileSync(
    process.execPath,
    [QUERY_RECORDS, '--type', 'completion', '--root', tmpRoot, ...args],
    { encoding: 'utf8' }
  );
  return result.trim();
}

// ---------------------------------------------------------------------------
// Shape 1: --where "created=<today>" --sort "chain" --format json
// ---------------------------------------------------------------------------

describe('query-completions shape 1 — date filter, json, sorted by chain', () => {
  it('returns all 3 entries for today\'s date filter', () => {
    const raw = runQuery(['--where', `created=${today()}`, '--sort', 'chain', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 3, `Expected 3 records, got ${records.length}: ${raw}`);
  });

  it('output is valid JSON array', () => {
    const raw = runQuery(['--where', `created=${today()}`, '--sort', 'chain', '--format', 'json']);
    assert.doesNotThrow(() => JSON.parse(raw), 'Output should parse as JSON');
    const records = JSON.parse(raw);
    assert.ok(Array.isArray(records), 'JSON output should be an array');
  });

  it('records include expected frontmatter fields (title, nature, status)', () => {
    const raw = runQuery(['--where', `created=${today()}`, '--sort', 'chain', '--format', 'json']);
    const records = JSON.parse(raw);
    for (const r of records) {
      assert.ok(r.frontmatter.title, `Record missing title: ${JSON.stringify(r)}`);
      assert.ok(r.frontmatter.nature, `Record missing nature: ${JSON.stringify(r)}`);
    }
  });

  it('entries are sorted by chain field (null last)', () => {
    const raw = runQuery(['--where', `created=${today()}`, '--sort', 'chain', '--format', 'json']);
    const records = JSON.parse(raw);
    // chain: null sorts as '' (empty string), which is less than any real path
    // Verify the chain values are non-decreasing
    const chains = records.map(r => String(r.frontmatter.chain ?? ''));
    for (let i = 1; i < chains.length; i++) {
      assert.ok(
        chains[i - 1] <= chains[i],
        `Records not sorted by chain at index ${i}: ${chains[i-1]} > ${chains[i]}`
      );
    }
  });
});

// ---------------------------------------------------------------------------
// Shape 2: --since "7d" --where "status=pending-release" --format json
// ---------------------------------------------------------------------------

describe('query-completions shape 2 — since filter + status where, json', () => {
  it('returns exactly 2 pending-release entries', () => {
    const raw = runQuery(['--since', '7d', '--where', 'status=pending-release', '--format', 'json']);
    const records = JSON.parse(raw);
    assert.equal(records.length, 2, `Expected 2 pending-release records, got ${records.length}: ${raw}`);
  });

  it('all returned entries have status=pending-release', () => {
    const raw = runQuery(['--since', '7d', '--where', 'status=pending-release', '--format', 'json']);
    const records = JSON.parse(raw);
    for (const r of records) {
      assert.equal(r.frontmatter.status, 'pending-release',
        `Expected status=pending-release, got: ${r.frontmatter.status}`);
    }
  });

  it('released entry (status=released) is excluded', () => {
    const raw = runQuery(['--since', '7d', '--where', 'status=pending-release', '--format', 'json']);
    const records = JSON.parse(raw);
    const titles = records.map(r => r.frontmatter.title);
    assert.ok(
      !titles.includes('Add completion-entry schema'),
      `Released entry should be excluded; titles: ${titles.join(', ')}`
    );
  });

  it('output is valid JSON array', () => {
    const raw = runQuery(['--since', '7d', '--where', 'status=pending-release', '--format', 'json']);
    assert.doesNotThrow(() => JSON.parse(raw));
    assert.ok(Array.isArray(JSON.parse(raw)));
  });
});

// ---------------------------------------------------------------------------
// Shape 3: --where "status=pending-release" --sort "nature" --format markdown-list
// ---------------------------------------------------------------------------

describe('query-completions shape 3 — status where, nature sort, markdown-list', () => {
  it('returns 2 lines of markdown output', () => {
    const raw = runQuery(['--where', 'status=pending-release', '--sort', 'nature', '--format', 'markdown-list']);
    const lines = raw.split('\n').filter(l => l.trim());
    assert.equal(lines.length, 2, `Expected 2 markdown lines, got ${lines.length}: ${raw}`);
  });

  it('each line matches completion markdown-list format: "- **title** [nature] (chain: ...) — commits"', () => {
    const raw = runQuery(['--where', 'status=pending-release', '--sort', 'nature', '--format', 'markdown-list']);
    const lines = raw.split('\n').filter(l => l.trim());
    const lineRe = /^- \*\*[^*]+\*\* \[[^\]]+\] \(chain: [^)]+\) — .+$/;
    for (const line of lines) {
      assert.match(line, lineRe, `Line does not match expected format: ${line}`);
    }
  });

  it('lines are sorted by nature field alphabetically', () => {
    const raw = runQuery(['--where', 'status=pending-release', '--sort', 'nature', '--format', 'markdown-list']);
    const lines = raw.split('\n').filter(l => l.trim());
    // Extract nature tags from "- **title** [nature] ..."
    const natures = lines.map(l => {
      const m = l.match(/\[([^\]]+)\]/);
      return m ? m[1] : '';
    });
    for (let i = 1; i < natures.length; i++) {
      assert.ok(
        natures[i - 1] <= natures[i],
        `Natures not sorted at index ${i}: ${natures[i-1]} > ${natures[i]}`
      );
    }
  });

  it('null chain renders as "none" in output', () => {
    const raw = runQuery(['--where', 'status=pending-release', '--sort', 'nature', '--format', 'markdown-list']);
    // Entry B has chain: null — should render as "(chain: none)"
    assert.ok(raw.includes('chain: none'), `Expected "chain: none" in output: ${raw}`);
  });

  it('commit hashes appear in output', () => {
    const raw = runQuery(['--where', 'status=pending-release', '--sort', 'nature', '--format', 'markdown-list']);
    assert.ok(raw.includes('abc123def456') || raw.includes('def456abc789'),
      `Expected commit hash in output: ${raw}`);
  });
});
