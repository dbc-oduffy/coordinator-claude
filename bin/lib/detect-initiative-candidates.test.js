'use strict';
/**
 * detect-initiative-candidates.test.js — Tests for detect-initiative-candidates.
 *
 * Verifies:
 *   1. Cluster output for each signal (tag, directory, keyword)
 *   2. DR-209 ≥3-items floor (clusters below threshold are not surfaced)
 *   3. Zero writes (test-enforced by spying on fs write methods)
 *
 * Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C4 (AC5)
 *
 * Run with: node --test bin/lib/detect-initiative-candidates.test.js
 */

const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const DETECT = path.resolve(__dirname, '..', 'detect-initiative-candidates');
const { detectCandidates, MIN_CLUSTER_SIZE } = require(DETECT);

// ---------------------------------------------------------------------------
// Cluster output — signal: tag
// ---------------------------------------------------------------------------

describe('detectCandidates — tag signal', () => {
  test('clusters records sharing a single string tag', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'Alpha', tags: 'auth' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'Beta',  tags: 'auth' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'Gamma', tags: 'auth' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'auth');
    assert.ok(cluster, 'should produce a tag cluster for "auth"');
    assert.strictEqual(cluster.items.length, 3, 'cluster must contain all 3 records');
  });

  test('clusters records sharing a tag from an array', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'Alpha', tags: ['auth', 'perf'] } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'Beta',  tags: ['auth'] } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'Gamma', tags: ['auth', 'ui'] } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'auth');
    assert.ok(cluster, 'should produce a tag cluster for "auth" from array tags');
    assert.strictEqual(cluster.items.length, 3);
  });

  test('clusters records sharing .topic field', () => {
    const records = [
      { path: 'state/improvement-queue/a.yaml', frontmatter: { title: 'A', topic: 'observability' } },
      { path: 'state/improvement-queue/b.yaml', frontmatter: { title: 'B', topic: 'observability' } },
      { path: 'state/improvement-queue/c.yaml', frontmatter: { title: 'C', topic: 'observability' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'observability');
    assert.ok(cluster, 'should produce a tag cluster from .topic field');
    assert.strictEqual(cluster.items.length, 3);
  });

  // Review: code-reviewer — F10 (nit): add .areas field test; _normalizeTags uses short-circuit
  // `fm.tags || fm.topic || fm.areas` so only the first truthy field is read (intentional
  // exclusive-alternatives design — a record contributes tags from one field only).
  test('clusters records sharing .areas field (when .tags and .topic are absent)', () => {
    const records = [
      { path: 'state/improvement-queue/a.yaml', frontmatter: { title: 'A', areas: 'platform' } },
      { path: 'state/improvement-queue/b.yaml', frontmatter: { title: 'B', areas: 'platform' } },
      { path: 'state/improvement-queue/c.yaml', frontmatter: { title: 'C', areas: 'platform' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'platform');
    assert.ok(cluster, 'should produce a tag cluster from .areas field when .tags and .topic are absent');
    assert.strictEqual(cluster.items.length, 3);
  });

  test('.tags short-circuits .areas (exclusive-alternatives design)', () => {
    // _normalizeTags uses `fm.tags || fm.topic || fm.areas` — when .tags is truthy, .areas is
    // never read. This is intentional: a record with both .tags and .areas only contributes
    // the .tags signal (exclusive-alternatives, not union). This test confirms that behaviour.
    const records = [
      { path: 'state/improvement-queue/a.yaml', frontmatter: { title: 'A', tags: 'backend', areas: 'platform' } },
      { path: 'state/improvement-queue/b.yaml', frontmatter: { title: 'B', tags: 'backend', areas: 'platform' } },
      { path: 'state/improvement-queue/c.yaml', frontmatter: { title: 'C', tags: 'backend', areas: 'platform' } },
    ];
    const result = detectCandidates(records);
    // 'backend' cluster (from .tags) should appear.
    const backendCluster = result.find(c => c.signal === 'tag' && c.value === 'backend');
    assert.ok(backendCluster, '.tags field must produce a cluster when truthy');
    // 'platform' cluster (from .areas) must NOT appear because .tags short-circuited it.
    const platformCluster = result.find(c => c.signal === 'tag' && c.value === 'platform');
    assert.ok(!platformCluster, '.areas must not produce a cluster when .tags is already truthy (exclusive-alternatives)');
  });

  test('suggestedLabel is Title Case humanized from tag', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'A', tags: 'auth-service' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'B', tags: 'auth-service' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'C', tags: 'auth-service' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'auth-service');
    assert.ok(cluster, 'tag cluster must exist');
    assert.strictEqual(cluster.suggestedLabel, 'Auth Service', 'label must be Title Case humanized');
  });

  test('cluster items include path and title', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'Alpha', tags: 'perf' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'Beta',  tags: 'perf' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'Gamma', tags: 'perf' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'perf');
    assert.ok(cluster, 'tag cluster must exist');
    const item = cluster.items.find(i => i.path === 'state/bug-backlog/a.yaml');
    assert.ok(item, 'item must include the path');
    assert.strictEqual(item.title, 'Alpha', 'item must include the title');
  });
});

// ---------------------------------------------------------------------------
// Cluster output — signal: directory
// ---------------------------------------------------------------------------

describe('detectCandidates — directory signal', () => {
  test('clusters records from the same parent directory', () => {
    const records = [
      { path: 'state/debt-backlog/item-0.yaml', frontmatter: { title: 'Debt 0' } },
      { path: 'state/debt-backlog/item-1.yaml', frontmatter: { title: 'Debt 1' } },
      { path: 'state/debt-backlog/item-2.yaml', frontmatter: { title: 'Debt 2' } },
      { path: 'state/debt-backlog/item-3.yaml', frontmatter: { title: 'Debt 3' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'directory' && c.value === 'state/debt-backlog');
    assert.ok(cluster, 'should produce a directory cluster for state/debt-backlog');
    assert.strictEqual(cluster.items.length, 4);
  });

  test('records from different directories are NOT merged into one directory cluster', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml',        frontmatter: { title: 'Bug A' } },
      { path: 'state/bug-backlog/b.yaml',        frontmatter: { title: 'Bug B' } },
      { path: 'state/bug-backlog/c.yaml',        frontmatter: { title: 'Bug C' } },
      { path: 'state/improvement-queue/x.yaml',  frontmatter: { title: 'Imp X' } },
    ];
    const result = detectCandidates(records);
    const bugCluster = result.find(c => c.signal === 'directory' && c.value === 'state/bug-backlog');
    assert.ok(bugCluster, 'bug-backlog cluster must exist');
    // improvement-queue has only 1 item — should not cluster
    const impCluster = result.find(c => c.signal === 'directory' && c.value === 'state/improvement-queue');
    assert.ok(!impCluster, 'improvement-queue has only 1 item — must NOT produce a directory cluster');
  });

  test('suggestedLabel is Title Case of the directory basename', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'A' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'B' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'C' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'directory' && c.value === 'state/bug-backlog');
    assert.ok(cluster, 'directory cluster must exist');
    assert.strictEqual(cluster.suggestedLabel, 'Bug Backlog', 'label must be humanized basename');
  });
});

// ---------------------------------------------------------------------------
// Cluster output — signal: keyword
// ---------------------------------------------------------------------------

describe('detectCandidates — keyword signal', () => {
  test('clusters records sharing a significant title keyword', () => {
    const records = [
      { path: 'docs/plans/a.md', frontmatter: { title: 'Refactor query pipeline' } },
      { path: 'docs/plans/b.md', frontmatter: { title: 'Refactor schema validation' } },
      { path: 'docs/plans/c.md', frontmatter: { title: 'Refactor coordinator dispatch' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'keyword' && c.value === 'refactor');
    assert.ok(cluster, 'should produce a keyword cluster for "refactor"');
    assert.strictEqual(cluster.items.length, 3);
  });

  test('stop words are excluded from keyword clustering', () => {
    // "this", "with", "from" are stop words — should not produce clusters
    const records = [
      { path: 'docs/plans/a.md', frontmatter: { title: 'Fix this with that' } },
      { path: 'docs/plans/b.md', frontmatter: { title: 'Update this from that' } },
      { path: 'docs/plans/c.md', frontmatter: { title: 'Change this via that' } },
    ];
    const result = detectCandidates(records);
    const stopCluster = result.find(c => c.signal === 'keyword' && (c.value === 'this' || c.value === 'that' || c.value === 'with'));
    assert.ok(!stopCluster, 'stop words must not produce keyword clusters');
  });

  test('words under 4 chars are excluded from keyword clustering', () => {
    // "add", "fix", "new" are under 4 chars
    const records = [
      { path: 'docs/plans/a.md', frontmatter: { title: 'Add api endpoint' } },
      { path: 'docs/plans/b.md', frontmatter: { title: 'Add api route' } },
      { path: 'docs/plans/c.md', frontmatter: { title: 'Add api schema' } },
    ];
    const result = detectCandidates(records);
    // "add" is 3 chars, so excluded; "api" is 3 chars, also excluded
    const shortCluster = result.find(c => c.signal === 'keyword' && (c.value === 'add' || c.value === 'api'));
    assert.ok(!shortCluster, 'sub-4-char words must not produce keyword clusters');
  });
});

// ---------------------------------------------------------------------------
// DR-209 ≥3-items floor
// ---------------------------------------------------------------------------

describe('detectCandidates — ≥3-items floor (DR-209)', () => {
  test('MIN_CLUSTER_SIZE is exactly 3', () => {
    assert.strictEqual(MIN_CLUSTER_SIZE, 3, 'DR-209 mandates a floor of 3');
  });

  test('cluster of exactly 1 item is NOT surfaced', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'Alpha', tags: 'lone' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'lone');
    assert.ok(!cluster, 'cluster of 1 must NOT surface (below ≥3 floor)');
  });

  test('cluster of exactly 2 items is NOT surfaced', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'Alpha', tags: 'perf' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'Beta',  tags: 'perf' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'perf');
    assert.ok(!cluster, 'cluster of 2 must NOT surface (below ≥3 floor)');
  });

  test('cluster of exactly 3 items IS surfaced (boundary at floor)', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'Alpha', tags: 'perf' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'Beta',  tags: 'perf' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'Gamma', tags: 'perf' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'perf');
    assert.ok(cluster, 'cluster of exactly 3 must surface (at the floor boundary)');
  });

  test('cluster of 4 items IS surfaced (above floor)', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'A', tags: 'logging' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'B', tags: 'logging' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'C', tags: 'logging' } },
      { path: 'state/bug-backlog/d.yaml', frontmatter: { title: 'D', tags: 'logging' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'logging');
    assert.ok(cluster, 'cluster of 4 must surface (above floor)');
    assert.strictEqual(cluster.items.length, 4);
  });

  test('empty input returns no candidates', () => {
    const result = detectCandidates([]);
    assert.deepStrictEqual(result, [], 'empty input must return empty array');
  });

  // Review: code-reviewer — F5 (P2): rewritten from vacuous assert.ok(true) with genuinely-disjoint
  // fixtures (no shared keyword above ≥3 floor, split across 3 directories, no shared tag).
  test('records with no shared signal return no candidates', () => {
    const records = [
      // Three different directories, three different tags, no shared title keyword ≥4 chars
      // above the floor. "Database", "Network", "Memory" do not overlap; tags xq/yq/zq
      // are distinct; each item is in its own directory.
      { path: 'state/bug-backlog/a.yaml',       frontmatter: { title: 'Database migration error', tags: 'xq' } },
      { path: 'state/debt-backlog/b.yaml',       frontmatter: { title: 'Network timeout handler', tags: 'yq' } },
      { path: 'state/improvement-queue/c.yaml',  frontmatter: { title: 'Memory allocation failure', tags: 'zq' } },
    ];
    const result = detectCandidates(records);
    // No tag cluster (tags xq/yq/zq all distinct).
    // No directory cluster (3 different directories, each with only 1 item — below ≥3 floor).
    // No keyword cluster (no word appears in ≥3 titles: "database"/"network"/"memory"/"migration"/
    //   "timeout"/"handler"/"allocation"/"failure" each appear only once).
    assert.strictEqual(result.length, 0, `expected no candidates; got: ${JSON.stringify(result)}`);
  });
});

// ---------------------------------------------------------------------------
// Zero writes — test-enforced guarantee
// ---------------------------------------------------------------------------
//
// The structural backstop is that detect-initiative-candidates accepts no
// --output argument and opens no write handles. These tests spy on the fs
// module's write methods to verify detectCandidates() calls none of them.
// ---------------------------------------------------------------------------

describe('detectCandidates — zero writes (test-enforced)', () => {
  const fs = require('fs');

  const syntheticRecords = () => Array.from({ length: 3 }, (_, i) => ({
    path: `state/bug-backlog/item-${i}.yaml`,
    frontmatter: { title: `Security bug ${i}`, tags: 'security' },
  }));

  test('detectCandidates does not call fs.writeFile', () => {
    const original = fs.writeFile;
    let called = false;
    fs.writeFile = function () { called = true; };
    try {
      detectCandidates(syntheticRecords());
    } finally {
      fs.writeFile = original;
    }
    assert.ok(!called, 'detectCandidates must NOT call fs.writeFile');
  });

  test('detectCandidates does not call fs.writeFileSync', () => {
    const original = fs.writeFileSync;
    let called = false;
    fs.writeFileSync = function () { called = true; };
    try {
      detectCandidates(syntheticRecords());
    } finally {
      fs.writeFileSync = original;
    }
    assert.ok(!called, 'detectCandidates must NOT call fs.writeFileSync');
  });

  test('detectCandidates does not call fs.open', () => {
    const original = fs.open;
    let called = false;
    fs.open = function () { called = true; };
    try {
      detectCandidates(syntheticRecords());
    } finally {
      fs.open = original;
    }
    assert.ok(!called, 'detectCandidates must NOT call fs.open');
  });

  test('detectCandidates does not call fs.openSync', () => {
    const original = fs.openSync;
    let called = false;
    fs.openSync = function () { called = true; };
    try {
      detectCandidates(syntheticRecords());
    } finally {
      fs.openSync = original;
    }
    assert.ok(!called, 'detectCandidates must NOT call fs.openSync');
  });

  test('detectCandidates does not call fs.createWriteStream', () => {
    const original = fs.createWriteStream;
    let called = false;
    fs.createWriteStream = function () { called = true; return original.apply(fs, arguments); };
    try {
      detectCandidates(syntheticRecords());
    } finally {
      fs.createWriteStream = original;
    }
    assert.ok(!called, 'detectCandidates must NOT call fs.createWriteStream');
  });
});

// ---------------------------------------------------------------------------
// Return shape contract
// ---------------------------------------------------------------------------

describe('detectCandidates — return shape', () => {
  test('each cluster has signal, value, suggestedLabel, items fields', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'A', tags: 'infra' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'B', tags: 'infra' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'C', tags: 'infra' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'infra');
    assert.ok(cluster, 'tag cluster must be present');
    assert.ok('signal'       in cluster, 'cluster must have signal field');
    assert.ok('value'        in cluster, 'cluster must have value field');
    assert.ok('suggestedLabel' in cluster, 'cluster must have suggestedLabel field');
    assert.ok('items'        in cluster, 'cluster must have items field');
    assert.ok(Array.isArray(cluster.items), 'items must be an array');
  });

  test('each item in a cluster has path and title fields', () => {
    const records = [
      { path: 'state/bug-backlog/a.yaml', frontmatter: { title: 'Alpha Issue', tags: 'infra' } },
      { path: 'state/bug-backlog/b.yaml', frontmatter: { title: 'Beta Issue',  tags: 'infra' } },
      { path: 'state/bug-backlog/c.yaml', frontmatter: { title: 'Gamma Issue', tags: 'infra' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'infra');
    assert.ok(cluster, 'tag cluster must be present');
    for (const item of cluster.items) {
      assert.ok('path'  in item, 'item must have path field');
      assert.ok('title' in item, 'item must have title field');
    }
  });

  test('item.path matches the source record path', () => {
    const records = [
      { path: 'state/bug-backlog/alpha.yaml', frontmatter: { title: 'Alpha', tags: 'network' } },
      { path: 'state/bug-backlog/beta.yaml',  frontmatter: { title: 'Beta',  tags: 'network' } },
      { path: 'state/bug-backlog/gamma.yaml', frontmatter: { title: 'Gamma', tags: 'network' } },
    ];
    const result = detectCandidates(records);
    const cluster = result.find(c => c.signal === 'tag' && c.value === 'network');
    assert.ok(cluster, 'tag cluster must be present');
    const itemPaths = cluster.items.map(i => i.path).sort();
    const srcPaths = records.map(r => r.path).sort();
    assert.deepStrictEqual(itemPaths, srcPaths, 'item paths must match source record paths');
  });
});
