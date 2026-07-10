'use strict';
/**
 * walk-handoff-dag.test.js — unit tests for bin/lib/walk-handoff-dag.js
 *
 * Run with: node --test bin/lib/walk-handoff-dag.test.js
 *
 * Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C0
 *
 * Test coverage:
 *   - interface: all three exports exist with correct signatures
 *   - forward fan-in diamond dedup: A←B, A←C, D←{B,C} — each node visited once
 *   - single-node back-compat: predecessor:none → just that node, terminatedEarly=''
 *   - reverse-membership hit + miss
 *   - forked_from INCLUDED in reverse / EXCLUDED in forward (edgeKinds param)
 *   - lineage-cycle: back-edge detection emits 'lineage-cycle'
 *   - missing-link: emits 'missing-link' without dropping resolvable ancestors
 *   - opts.exclude: drops excluded paths from liveSet before the membership scan (AC1)
 */

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { execFileSync } = require('child_process');

const {
  handoffEdges,
  walkForward,
  referencedBy,
  _resolveTarget,
  checkLineageReachability,
} = require('./walk-handoff-dag.js');

// ---------------------------------------------------------------------------
// Fixture builder — creates temporary handoff markdown files with frontmatter
// ---------------------------------------------------------------------------

var tmpDir = null;

function makeTmpDir() {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'walk-handoff-dag-test-'));
}

function cleanupTmpDir() {
  if (tmpDir && fs.existsSync(tmpDir)) {
    // Node 16+ rmSync with recursive
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch (_) {}
  }
}

/**
 * Write a handoff fixture file. Returns the absolute path.
 * @param {string} name       Filename (no extension).
 * @param {Object} fm         Frontmatter fields to emit.
 * @returns {string}          Absolute path of written file.
 */
function writeFixture(name, fm) {
  var lines = ['---'];
  Object.keys(fm).forEach(function(k) {
    var v = fm[k];
    if (Array.isArray(v)) {
      lines.push(k + ':');
      v.forEach(function(item) { lines.push('  - ' + item); });
    } else if (v === null) {
      lines.push(k + ': null');
    } else {
      lines.push(k + ': ' + v);
    }
  });
  lines.push('---');
  lines.push('');
  lines.push('# ' + name);
  var filePath = path.join(tmpDir, name + '.md');
  fs.writeFileSync(filePath, lines.join('\n'), 'utf8');
  return filePath;
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('walk-handoff-dag exports', function() {
  it('exports handoffEdges as a function', function() {
    assert.strictEqual(typeof handoffEdges, 'function');
  });

  it('exports walkForward as a function', function() {
    assert.strictEqual(typeof walkForward, 'function');
  });

  it('exports referencedBy as a function', function() {
    assert.strictEqual(typeof referencedBy, 'function');
  });

  it('handoffEdges returns string array for known edge kinds', function() {
    var meta = { predecessor: 'some-handoff.md', additional_predecessors: ['a.md', 'b.md'], forked_from: 'fork.md' };
    var result = handoffEdges(meta, new Set(['predecessor', 'additional_predecessors', 'forked_from']));
    assert.ok(Array.isArray(result));
    assert.ok(result.includes('some-handoff.md'));
    assert.ok(result.includes('a.md'));
    assert.ok(result.includes('b.md'));
    assert.ok(result.includes('fork.md'));
    assert.strictEqual(result.length, 4);
  });

  it('handoffEdges excludes sentinel values (none, null, empty)', function() {
    var meta = { predecessor: 'none', additional_predecessors: [], forked_from: null };
    var result = handoffEdges(meta, new Set(['predecessor', 'additional_predecessors', 'forked_from']));
    assert.strictEqual(result.length, 0);
  });

  it('handoffEdges respects edgeKinds subset', function() {
    var meta = { predecessor: 'p.md', additional_predecessors: ['ap.md'], forked_from: 'ff.md' };
    // Only predecessor
    var r1 = handoffEdges(meta, new Set(['predecessor']));
    assert.deepStrictEqual(r1, ['p.md']);
    // Only forked_from
    var r2 = handoffEdges(meta, new Set(['forked_from']));
    assert.deepStrictEqual(r2, ['ff.md']);
    // predecessor + additional_predecessors (no forked_from)
    var r3 = handoffEdges(meta, new Set(['predecessor', 'additional_predecessors']));
    assert.ok(r3.includes('p.md'));
    assert.ok(r3.includes('ap.md'));
    assert.ok(!r3.includes('ff.md'));
  });

  it('walkForward returns {nodes, orderedPaths, terminatedEarly}', function() {
    makeTmpDir();
    try {
      var a = writeFixture('A', { title: 'A', kind: 'session-handoff', status: 'active', predecessor: 'none' });
      var result = walkForward(a, { edgeKinds: new Set(['predecessor']), handoffDir: tmpDir });
      assert.ok(result && typeof result === 'object');
      assert.ok('nodes' in result);
      assert.ok('orderedPaths' in result);
      assert.ok('terminatedEarly' in result);
    } finally {
      cleanupTmpDir();
    }
  });

  it('referencedBy returns {referenced, referencedBy}', function() {
    var result = referencedBy('/some/target.md', [], { edgeKinds: new Set(['predecessor']) });
    assert.ok(result && typeof result === 'object');
    assert.ok('referenced' in result);
    assert.ok('referencedBy' in result);
    assert.strictEqual(result.referenced, false);
    assert.deepStrictEqual(result.referencedBy, []);
  });
});

// ---------------------------------------------------------------------------
// single-node back-compat: predecessor:none → just that node, terminatedEarly=''
// ---------------------------------------------------------------------------

describe('single-node back-compat', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('predecessor:none → orderedPaths contains only start, terminatedEarly=""', function() {
    var a = writeFixture('A-root', { title: 'A-root', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var result = walkForward(a, { edgeKinds: new Set(['predecessor']), handoffDir: tmpDir });
    assert.strictEqual(result.orderedPaths.length, 1);
    assert.strictEqual(result.orderedPaths[0], a);
    assert.strictEqual(result.terminatedEarly, '');
    assert.ok(a in result.nodes);
  });
});

// ---------------------------------------------------------------------------
// Forward fan-in diamond dedup: A←B, A←C, D←{B,C}: each visited once
// orderedPaths length = 4
// terminatedEarly = '' (no cycles, no missing links)
// ---------------------------------------------------------------------------

describe('forward fan-in diamond dedup', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('A←B, A←C, D←{B,C}: each node visited exactly once, terminatedEarly=""', function() {
    // Build diamond fixture:
    //   D is the terminal (start point)
    //   D has two predecessors: B and C
    //   B's predecessor is A
    //   C's predecessor is A
    //   A has predecessor: none (root)
    // Walk: D → B → A (black), pop B (black), → C → A (black, skip), pop C (black), done
    // Expected orderedPaths: [D, B, A, C] — each appears once
    var aPath = writeFixture('A', { title: 'A', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var aName = path.basename(aPath);

    var bPath = writeFixture('B', { title: 'B', kind: 'session-handoff', status: 'active', predecessor: aName });
    var bName = path.basename(bPath);

    var cPath = writeFixture('C', { title: 'C', kind: 'session-handoff', status: 'active', predecessor: aName });
    var cName = path.basename(cPath);

    // D has predecessor=B and additional_predecessors=[C]
    var dPath = writeFixture('D', {
      title: 'D',
      kind: 'session-handoff',
      status: 'active',
      predecessor: bName,
      additional_predecessors: [cName],
    });

    var result = walkForward(dPath, {
      edgeKinds: new Set(['predecessor', 'additional_predecessors']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.terminatedEarly, '');

    // Each of A, B, C, D appears exactly once
    assert.strictEqual(result.orderedPaths.length, 4, 'should have exactly 4 paths (diamond dedup)');

    var uniquePaths = new Set(result.orderedPaths);
    assert.strictEqual(uniquePaths.size, 4, 'all 4 paths must be unique');

    // All four nodes must be present
    assert.ok(result.orderedPaths.includes(aPath), 'A must be present');
    assert.ok(result.orderedPaths.includes(bPath), 'B must be present');
    assert.ok(result.orderedPaths.includes(cPath), 'C must be present');
    assert.ok(result.orderedPaths.includes(dPath), 'D must be present');

    // D must be first (start path)
    assert.strictEqual(result.orderedPaths[0], dPath, 'D must be first in orderedPaths');
  });
});

// ---------------------------------------------------------------------------
// Reverse-membership: hit + miss
// ---------------------------------------------------------------------------

describe('reverse-membership hit and miss', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('target IS referenced by a node in liveSet → referenced=true, referencedBy non-empty', function() {
    var target = writeFixture('target', { title: 'target', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var targetName = path.basename(target);

    var ref = writeFixture('ref-a', { title: 'ref-a', kind: 'session-handoff', status: 'active', predecessor: targetName });

    var result = referencedBy(target, [ref], {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.referenced, true);
    assert.ok(result.referencedBy.includes(ref));
  });

  it('target is NOT referenced by any node in liveSet → referenced=false, referencedBy=[]', function() {
    var target = writeFixture('target-miss', { title: 'target-miss', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var unrelated = writeFixture('unrelated', { title: 'unrelated', kind: 'session-handoff', status: 'active', predecessor: 'none' });

    var result = referencedBy(target, [unrelated], {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.referenced, false);
    assert.deepStrictEqual(result.referencedBy, []);
  });

  it('empty liveSet → referenced=false', function() {
    var target = writeFixture('target-empty', { title: 'target-empty', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var result = referencedBy(target, [], { edgeKinds: new Set(['predecessor']) });
    assert.strictEqual(result.referenced, false);
  });
});

// ---------------------------------------------------------------------------
// forked_from: INCLUDED in reverse / EXCLUDED in forward
// ---------------------------------------------------------------------------

describe('forked_from edge-kind scoping', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('forked_from EXCLUDED from forward walk when not in edgeKinds', function() {
    var root = writeFixture('ff-root', { title: 'ff-root', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var rootName = path.basename(root);

    var spinoff = writeFixture('ff-spinoff', {
      title: 'ff-spinoff',
      kind: 'spinoff',
      status: 'active',
      predecessor: 'none',
      forked_from: rootName,
    });

    // Forward walk with only {predecessor} — forked_from NOT followed
    var result = walkForward(spinoff, {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
    });

    // Should only contain spinoff (predecessor=none terminates immediately)
    assert.strictEqual(result.orderedPaths.length, 1);
    assert.strictEqual(result.orderedPaths[0], spinoff);
    assert.ok(!result.orderedPaths.includes(root), 'forked_from root should NOT be visited when edgeKinds excludes forked_from');
  });

  it('forked_from INCLUDED in reverse-membership when in edgeKinds', function() {
    var root = writeFixture('ff-root-rev', { title: 'ff-root-rev', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var rootName = path.basename(root);

    var spinoff = writeFixture('ff-spinoff-rev', {
      title: 'ff-spinoff-rev',
      kind: 'spinoff',
      status: 'active',
      predecessor: 'none',
      forked_from: rootName,
    });

    // Reverse-membership with forked_from included
    var result = referencedBy(root, [spinoff], {
      edgeKinds: new Set(['predecessor', 'additional_predecessors', 'forked_from']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.referenced, true);
    assert.ok(result.referencedBy.includes(spinoff));
  });

  it('forked_from EXCLUDED from reverse-membership when not in edgeKinds', function() {
    var root = writeFixture('ff-root-rev-excl', { title: 'ff-root-rev-excl', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var rootName = path.basename(root);

    var spinoff = writeFixture('ff-spinoff-rev-excl', {
      title: 'ff-spinoff-rev-excl',
      kind: 'spinoff',
      status: 'active',
      predecessor: 'none',
      forked_from: rootName,
    });

    // Reverse-membership WITHOUT forked_from
    var result = referencedBy(root, [spinoff], {
      edgeKinds: new Set(['predecessor', 'additional_predecessors']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.referenced, false);
  });
});

// ---------------------------------------------------------------------------
// lineage-cycle: back-edge detection emits 'lineage-cycle'
// ---------------------------------------------------------------------------

describe('lineage-cycle back-edge detection', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('direct self-cycle emits terminatedEarly="lineage-cycle"', function() {
    // A points to itself: A.predecessor = A (a genuine back-edge)
    var aName = 'cycle-self';
    var aPath = path.join(tmpDir, aName + '.md');
    // Write with self-reference
    var content = [
      '---',
      'title: cycle-self',
      'kind: session-handoff',
      'status: active',
      'predecessor: ' + aName + '.md',
      '---',
      '',
      '# cycle-self',
    ].join('\n');
    fs.writeFileSync(aPath, content, 'utf8');

    var result = walkForward(aPath, {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.terminatedEarly, 'lineage-cycle');
    // The node itself should still have been visited
    assert.ok(result.orderedPaths.includes(aPath));
  });

  it('A→B→A cycle emits terminatedEarly="lineage-cycle" and still records A and B', function() {
    // A's predecessor = B, B's predecessor = A (mutual cycle)
    var aName = 'cycle-a';
    var bName = 'cycle-b';
    var aPath = path.join(tmpDir, aName + '.md');
    var bPath = path.join(tmpDir, bName + '.md');

    fs.writeFileSync(aPath, [
      '---', 'title: cycle-a', 'kind: session-handoff', 'status: active',
      'predecessor: ' + bName + '.md', '---', '', '# cycle-a',
    ].join('\n'), 'utf8');

    fs.writeFileSync(bPath, [
      '---', 'title: cycle-b', 'kind: session-handoff', 'status: active',
      'predecessor: ' + aName + '.md', '---', '', '# cycle-b',
    ].join('\n'), 'utf8');

    var result = walkForward(aPath, {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.terminatedEarly, 'lineage-cycle');
    // Both nodes recorded before the cycle was detected
    assert.ok(result.orderedPaths.includes(aPath), 'A should be in orderedPaths');
    assert.ok(result.orderedPaths.includes(bPath), 'B should be in orderedPaths');
  });
});

// ---------------------------------------------------------------------------
// missing-link: emits 'missing-link' without dropping resolvable ancestors
// ---------------------------------------------------------------------------

describe('missing-link handling', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('unresolvable secondary edge records missing-link, resolvable primary ancestor still visited', function() {
    // A is root (predecessor: none)
    var aPath = writeFixture('ml-A', { title: 'ml-A', kind: 'session-handoff', status: 'active', predecessor: 'none' });
    var aName = path.basename(aPath);

    // B has predecessor=A (resolvable) and additional_predecessors=[NONEXISTENT.md]
    var bPath = writeFixture('ml-B', {
      title: 'ml-B',
      kind: 'session-handoff',
      status: 'active',
      predecessor: aName,
      additional_predecessors: ['TOTALLY-NONEXISTENT-XYZ.md'],
    });

    var result = walkForward(bPath, {
      edgeKinds: new Set(['predecessor', 'additional_predecessors']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.terminatedEarly, 'missing-link');
    // B and A both visited despite the missing additional predecessor
    assert.ok(result.orderedPaths.includes(bPath), 'B must be visited');
    assert.ok(result.orderedPaths.includes(aPath), 'A must be visited (resolvable ancestor not dropped)');
    assert.strictEqual(result.orderedPaths.length, 2, 'only 2 nodes (B and A)');
  });

  it('missing-link on sole edge: start node still in result, terminatedEarly="missing-link"', function() {
    var cPath = writeFixture('ml-C', {
      title: 'ml-C',
      kind: 'session-handoff',
      status: 'active',
      predecessor: 'NONEXISTENT-SOLE-PREDECESSOR.md',
    });

    var result = walkForward(cPath, {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
    });

    assert.strictEqual(result.terminatedEarly, 'missing-link');
    assert.ok(result.orderedPaths.includes(cPath), 'start node must be in result even if its predecessor is missing');
    assert.strictEqual(result.orderedPaths.length, 1);
  });
});

// ---------------------------------------------------------------------------
// opts.exclude: excluded paths are dropped from liveSet before membership scan (AC1)
// ---------------------------------------------------------------------------

describe('referencedBy opts.exclude — exclusion set drops paths before scan', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('target referenced ONLY by excluded node → referenced=false (excluded successor drops)', function() {
    // Scenario: predecessor P is referenced only by its successor S.
    // When the handoff SKILL calls has-live-children(P, exclude=[S]), the result should
    // be referenced=false (safe to archive) because S is dropped before the scan.
    var pPath = writeFixture('excl-P', {
      title: 'excl-P',
      kind: 'session-handoff',
      status: 'active',
      predecessor: 'none',
    });
    var sPath = writeFixture('excl-S', {
      title: 'excl-S',
      kind: 'session-handoff',
      status: 'active',
      predecessor: path.basename(pPath),
    });

    // Without exclude: S references P → referenced=true
    var withoutExclude = referencedBy(pPath, [sPath], {
      edgeKinds: new Set(['predecessor', 'additional_predecessors', 'forked_from']),
      handoffDir: tmpDir,
    });
    assert.strictEqual(withoutExclude.referenced, true, 'without exclude: S should reference P');

    // With exclude=[sPath]: S is dropped → referenced=false (safe to archive)
    var withExclude = referencedBy(pPath, [sPath], {
      edgeKinds: new Set(['predecessor', 'additional_predecessors', 'forked_from']),
      handoffDir: tmpDir,
      exclude: [sPath],
    });
    assert.strictEqual(withExclude.referenced, false, 'with exclude=[S]: referenced should be false');
    assert.deepStrictEqual(withExclude.referencedBy, [], 'with exclude=[S]: referencedBy should be empty');
  });

  it('target referenced by two nodes; only one excluded → referenced=true (the other remains)', function() {
    var pPath = writeFixture('excl2-P', {
      title: 'excl2-P',
      kind: 'session-handoff',
      status: 'active',
      predecessor: 'none',
    });
    var pName = path.basename(pPath);

    var s1Path = writeFixture('excl2-S1', {
      title: 'excl2-S1',
      kind: 'session-handoff',
      status: 'active',
      predecessor: pName,
    });
    var s2Path = writeFixture('excl2-S2', {
      title: 'excl2-S2',
      kind: 'session-handoff',
      status: 'active',
      predecessor: pName,
    });

    // Exclude only S1; S2 still references P → referenced=true
    var result = referencedBy(pPath, [s1Path, s2Path], {
      edgeKinds: new Set(['predecessor', 'additional_predecessors', 'forked_from']),
      handoffDir: tmpDir,
      exclude: [s1Path],
    });
    assert.strictEqual(result.referenced, true, 'S2 still references P after S1 excluded');
    assert.ok(result.referencedBy.includes(s2Path), 'S2 must appear in referencedBy');
    assert.ok(!result.referencedBy.includes(s1Path), 'S1 must NOT appear (excluded)');
  });

  it('exclude as a Set<string> (not array) is accepted', function() {
    var pPath = writeFixture('excl3-P', {
      title: 'excl3-P',
      kind: 'session-handoff',
      status: 'active',
      predecessor: 'none',
    });
    var sPath = writeFixture('excl3-S', {
      title: 'excl3-S',
      kind: 'session-handoff',
      status: 'active',
      predecessor: path.basename(pPath),
    });

    // Pass exclude as a Set
    var result = referencedBy(pPath, [sPath], {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
      exclude: new Set([sPath]),
    });
    assert.strictEqual(result.referenced, false, 'Set-typed exclude should work the same as array');
  });

  it('empty exclude array → behaviour byte-identical to absent exclude (backward-compat)', function() {
    var pPath = writeFixture('excl4-P', {
      title: 'excl4-P',
      kind: 'session-handoff',
      status: 'active',
      predecessor: 'none',
    });
    var sPath = writeFixture('excl4-S', {
      title: 'excl4-S',
      kind: 'session-handoff',
      status: 'active',
      predecessor: path.basename(pPath),
    });

    var withEmpty = referencedBy(pPath, [sPath], {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
      exclude: [],
    });
    var withAbsent = referencedBy(pPath, [sPath], {
      edgeKinds: new Set(['predecessor']),
      handoffDir: tmpDir,
    });
    assert.strictEqual(withEmpty.referenced, withAbsent.referenced, 'empty exclude == absent exclude');
    assert.deepStrictEqual(withEmpty.referencedBy, withAbsent.referencedBy, 'referencedBy arrays match');
  });
});

// ---------------------------------------------------------------------------
// origin_handoff provenance edge-kind — isolation and explicit-walk tests
// Spec backlink: docs/plans/2026-07-07-spinoff-provenance-ancestry.md § C3
// ---------------------------------------------------------------------------

describe('origin_handoff provenance edge-kind', function() {
  before(function() { makeTmpDir(); });
  after(function() { cleanupTmpDir(); });

  it('(a) default edgeKinds walk over a node with origin_handoff returns ZERO origin edges', function() {
    // origin_handoff is a provenance field, not a continuity edge.
    // It must never appear in the default walk set; isolation is the whole point.
    var origin = writeFixture('oh-origin', {
      title:    'oh-origin',
      kind:     'session-handoff',
      status:   'active',
      predecessor: 'none',
    });
    var originName = path.basename(origin);

    var node = writeFixture('oh-node', {
      title:          'oh-node',
      kind:           'spinoff',
      status:         'active',
      predecessor:    'none',
      origin_handoff: originName,
    });

    // walkForward default: edgeKinds = new Set(['predecessor'])
    var fwd = walkForward(node, { handoffDir: tmpDir });
    assert.strictEqual(fwd.orderedPaths.length, 1, 'default walk must not follow origin_handoff');
    assert.ok(!fwd.orderedPaths.includes(origin), 'origin node must NOT be visited in default walk');

    // referencedBy default: edgeKinds = new Set(['predecessor','additional_predecessors','forked_from'])
    var rev = referencedBy(origin, [node], { handoffDir: tmpDir });
    assert.strictEqual(rev.referenced, false, 'default reverse-membership must not match origin_handoff');
    assert.deepStrictEqual(rev.referencedBy, []);
  });

  it('(b) explicit edgeKinds={origin_handoff} DOES traverse the origin_handoff edge', function() {
    var origin = writeFixture('oh-explicit-origin', {
      title:    'oh-explicit-origin',
      kind:     'session-handoff',
      status:   'active',
      predecessor: 'none',
    });
    var originName = path.basename(origin);

    var node = writeFixture('oh-explicit-node', {
      title:          'oh-explicit-node',
      kind:           'spinoff',
      status:         'active',
      predecessor:    'none',
      origin_handoff: originName,
    });

    // Forward walk with explicit {origin_handoff}
    var fwd = walkForward(node, {
      edgeKinds:  new Set(['origin_handoff']),
      handoffDir: tmpDir,
    });
    assert.ok(fwd.orderedPaths.includes(origin), 'origin node MUST be visited when edgeKinds={origin_handoff}');
    assert.strictEqual(fwd.orderedPaths.length, 2, 'node + origin, no more');

    // Reverse-membership with explicit {origin_handoff}
    var rev = referencedBy(origin, [node], {
      edgeKinds:  new Set(['origin_handoff']),
      handoffDir: tmpDir,
    });
    assert.strictEqual(rev.referenced, true, 'reverse-membership must find origin_handoff reference');
    assert.ok(rev.referencedBy.includes(node));
  });

  it('(c) origin_plan_id / origin_goal_id produce NO edges even when passed in edgeKinds', function() {
    // These are cross-entity refs (not handoff paths) and are NOT registered in EDGE_KIND_META.
    // handoffEdges must silently skip unregistered kinds; no edges should be emitted.
    var meta = {
      origin_plan_id: 'pln-abc123',
      origin_goal_id: 'gol-def456',
    };
    var edges = handoffEdges(meta, new Set(['origin_plan_id', 'origin_goal_id']));
    assert.deepStrictEqual(edges, [], 'unregistered origin_plan_id / origin_goal_id must yield zero edges');
  });
});

// ---------------------------------------------------------------------------
// _resolveTarget git-history tier (C2 F1) — hermetic scratch-git-repo coverage
//
// Review: code-reviewer F6 — c2-lineage-reachability.test.js's git-history
// test is environment-dependent (silent no-op in a fresh/shallow clone with
// no deleted archive/handoffs history) and its fallback comment claimed this
// file already covers _resolveTarget's git-history branch directly, which was
// false. This describe block makes that claim true: a throwaway scratch git
// repo (not this repo — fully hermetic, no dependency on DoE-claude's actual
// history) with a committed-then-removed file proves tier 3 resolves via
// `git log --all` regardless of CI clone depth or repo history contents.
//
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2 (F1)
// ---------------------------------------------------------------------------
describe('_resolveTarget git-history tier — hermetic scratch git repo', function() {
  var scratchRepo = null;

  function git(args) {
    return execFileSync('git', args, { cwd: scratchRepo, encoding: 'utf8' });
  }

  before(function() {
    scratchRepo = fs.mkdtempSync(path.join(os.tmpdir(), 'walk-handoff-dag-scratch-git-'));
    git(['init', '-q']);
    git(['config', 'user.email', 'test@example.com']);
    git(['config', 'user.name', 'Test']);

    // Commit a handoff-shaped file under state/handoffs/, then git-rm it —
    // disk-absent now, git-reachable via `git log --all -- <path>`.
    var handoffRelPath = path.join('state', 'handoffs', 'removed-handoff.md');
    var absPath = path.join(scratchRepo, handoffRelPath);
    fs.mkdirSync(path.dirname(absPath), { recursive: true });
    fs.writeFileSync(absPath, '---\ntitle: removed\n---\nbody\n', 'utf8');
    git(['add', handoffRelPath]);
    git(['commit', '-q', '-m', 'add removed-handoff.md']);
    git(['rm', '-q', handoffRelPath]);
    git(['commit', '-q', '-m', 'remove removed-handoff.md']);
  });

  after(function() {
    if (scratchRepo && fs.existsSync(scratchRepo)) {
      try { fs.rmSync(scratchRepo, { recursive: true, force: true }); } catch (_) {}
    }
  });

  it('returns the git-history sentinel for a path removed from disk but present in git history', function() {
    var handoffDir = path.join(scratchRepo, 'state', 'handoffs');
    var resolved = _resolveTarget('removed-handoff.md', handoffDir, scratchRepo);
    assert.strictEqual(resolved, 'git-history');
  });

  it('returns null for a path that never existed in disk or git history', function() {
    var handoffDir = path.join(scratchRepo, 'state', 'handoffs');
    var resolved = _resolveTarget('never-existed-handoff.md', handoffDir, scratchRepo);
    assert.strictEqual(resolved, null);
  });
});

// ---------------------------------------------------------------------------
// checkLineageReachability — WAIVED_DANGLING_PREDECESSORS (C6 GAP2)
//
// Review: code-reviewer F3 — zero test coverage for the waive-list. These
// tests exercise the real 5-entry waiver table (hardcoded here from
// walk-handoff-dag.js's WAIVED_DANGLING_PREDECESSORS — not re-exported,
// by design, since the waiver is an internal implementation detail of the
// rule kernel) via the exported checkLineageReachability entry point.
//
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C6 (GAP2)
// ---------------------------------------------------------------------------
describe('checkLineageReachability — WAIVED_DANGLING_PREDECESSORS (C6 GAP2)', function() {
  var REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
  var WAIVED_RECORD_PATH = 'archive/handoffs/2026-06-28_081122_d5714a02-8a54-4897-babf-457e5833ed9c.md';
  var WAIVED_PREDECESSOR = 'state/handoffs/2026-06-27_224629_roadmap-stub-numbering-dependency-order.md';

  it('(1) a real waived (recordRepoRelPath, predecessor) pair reports NO violation', function() {
    var frontmatter = { kind: 'session-handoff', predecessor: WAIVED_PREDECESSOR };
    var violations = checkLineageReachability(
      frontmatter,
      REPO_ROOT,
      path.join(REPO_ROOT, 'archive', 'handoffs'),
      WAIVED_RECORD_PATH
    );
    assert.deepStrictEqual(violations, [], 'waived pair must produce zero violations');
  });

  it('(2) same waived record path with a DIFFERENT unresolvable predecessor IS reported (value-scoped, not record-scoped)', function() {
    var frontmatter = {
      kind: 'session-handoff',
      predecessor: 'state/handoffs/this-path-provably-never-existed-anywhere.md',
    };
    var violations = checkLineageReachability(
      frontmatter,
      REPO_ROOT,
      path.join(REPO_ROOT, 'archive', 'handoffs'),
      WAIVED_RECORD_PATH
    );
    assert.strictEqual(violations.length, 1, 'a different unresolvable predecessor on the same record path must still violate');
    assert.strictEqual(violations[0].field, 'predecessor');
  });

  it('(3) a non-waived record with the same unresolvable target string as a waived value IS reported (keyed by the pair, not target alone)', function() {
    // WAIVED_PREDECESSOR is provably unresolvable in all three tiers (that is
    // exactly why it needed a waiver — see WAIVED_DANGLING_PREDECESSORS's
    // header comment). Reusing the same target string on a DIFFERENT,
    // non-waived record path must still violate: the waiver is keyed by the
    // (recordRepoRelPath, value) pair, not by the target value alone.
    var frontmatter = { kind: 'session-handoff', predecessor: WAIVED_PREDECESSOR };
    var violations = checkLineageReachability(
      frontmatter,
      REPO_ROOT,
      path.join(REPO_ROOT, 'archive', 'handoffs'),
      'archive/handoffs/some-other-record-not-in-the-waive-list.md'
    );
    assert.strictEqual(violations.length, 1, 'same target string on a non-waived record path must still violate');
    assert.strictEqual(violations[0].field, 'predecessor');
    assert.strictEqual(violations[0].value, WAIVED_PREDECESSOR);
  });
});
