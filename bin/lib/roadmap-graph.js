'use strict';
/**
 * roadmap-graph.js — graph primitives for roadmap stub topological linearization.
 *
 * Purpose: provides a constructive topological linearization of the blocks/blocked_by DAG
 * (topoNumber) and a fail-loud verification gate for dependency-monotone (sprint, wave)
 * ordering (checkDependencyOrder). Used by roadmap-number-stubs.js (authoring CLI) and
 * audit-roadmap.sh Audit 5 (dependency-order gate).
 *
 * Domain vocabulary: stub, sprint, wave, topological linearization, blocked_by edge,
 * dependency-monotone, (sprint, wave) slot.
 *
 * Spec backlink: docs/plans/2026-06-28-roadmap-stub-numbering-dependency-order.md § C1
 *
 * No external dependencies — uses only Node built-ins. CommonJS module.exports shape
 * (same as schema.js) — consumed via require() from both shell-wrapper scripts and tests.
 */

// ---------------------------------------------------------------------------
// RoadmapCycleError
// ---------------------------------------------------------------------------

/**
 * Thrown by topoNumber when the blocked_by graph contains a cycle.
 * .cycle carries the array of node labels that form the detected cycle set.
 * Cycles are authoring bugs to surface, never to linearize around.
 */
class RoadmapCycleError extends Error {
  constructor(cycle) {
    super(`Roadmap dependency cycle detected among nodes: ${cycle.join(', ')}`);
    this.name = 'RoadmapCycleError';
    /** @type {string[]} */
    this.cycle = cycle;
  }
}

// ---------------------------------------------------------------------------
// topoNumber — constructive topological linearization (Kahn's algorithm)
// ---------------------------------------------------------------------------

/**
 * Produce a dependency-monotone topological linearization of a stub DAG.
 *
 * Wave is longest-path depth from a root (a node with no blocked_by edges),
 * bucketed as single-sprint: sprint=1, wave=depth+1 (depth 0 → wave 1).
 * This guarantees (sprint, wave) is strictly monotone along every declared edge
 * by construction. Multi-sprint sprint assignment is author-driven and verified
 * by audit-roadmap.sh Audit 5; this helper is constructive for single-sprint only.
 *
 * Tie-breaking within a ready-set (same Kahn's layer): the optional tieBreak
 * comparator is applied; default is stable original nodes-array index order.
 *
 * @param {string[]} nodes
 *   Provisional stub cluster labels.
 * @param {{from: string, to: string}[]} edges
 *   Each entry encodes "from blocked_by to" — 'to' must ship first and therefore
 *   receives the lower number. The precedence arrow in the DAG is to → from.
 * @param {(a: string, b: string) => number} [tieBreak]
 *   Optional comparator for deterministic tie-breaking within a ready set.
 *   Default: stable original nodes-array index order.
 * @returns {{ order: string[], number: Object.<string,number>, sprintWave: Object.<string,{sprint:number,wave:number}> }}
 *   order      — labels in topological linearization order (dependencies before dependents).
 *   number     — 1-based position of each label in the linearization.
 *   sprintWave — per-label { sprint: 1, wave: depth+1 }; dependency-monotone by construction.
 * @throws {RoadmapCycleError} if the blocked_by graph contains a cycle.
 */
function topoNumber(nodes, edges, tieBreak) {
  // Build original-index map for stable default tie-break
  const nodeIndex = new Map();
  nodes.forEach(function(n, i) { nodeIndex.set(n, i); });

  const defaultTieBreak = function(a, b) { return nodeIndex.get(a) - nodeIndex.get(b); };
  const cmp = tieBreak || defaultTieBreak;

  // Adjacency and in-degree maps.
  // Edge "from blocked_by to" → precedence: to must precede from.
  // successors[to] contains from; inDegree[from] incremented per dependency.
  const inDegree = new Map();
  const successors = new Map();

  for (const n of nodes) {
    inDegree.set(n, 0);
    successors.set(n, []);
  }

  for (const edge of edges) {
    const from = edge.from;
    const to = edge.to;
    // Guard: handle nodes that appear in edges but not in the nodes array
    if (!inDegree.has(from)) inDegree.set(from, 0);
    if (!successors.has(to)) successors.set(to, []);
    inDegree.set(from, (inDegree.get(from) || 0) + 1);
    successors.get(to).push(from);
  }

  // Kahn's algorithm: process nodes with in-degree 0, reduce successors
  let ready = [];
  for (const n of nodes) {
    if ((inDegree.get(n) || 0) === 0) {
      ready.push(n);
    }
  }

  const order = [];
  // Longest-path depth from any root; initialized to 0 for all nodes.
  // Computed incrementally as Kahn's processes in topological order:
  // when 'node' is processed, all paths leading to 'node' have been accounted for,
  // so depth[succ] = max(depth[succ], depth[node] + 1) is safe.
  const depth = new Map();
  for (const n of nodes) depth.set(n, 0);

  while (ready.length > 0) {
    // Deterministic selection: sort the ready set, take the first element.
    // Sorting the full ready array on every iteration is O(r log r) per step
    // but correct and sufficient for the small roadmap graphs this serves.
    ready.sort(cmp);
    const node = ready.shift();
    order.push(node);

    for (const succ of (successors.get(node) || [])) {
      // Longest-path depth update
      const candidate = (depth.get(node) || 0) + 1;
      if (candidate > (depth.get(succ) || 0)) {
        depth.set(succ, candidate);
      }
      const newDeg = (inDegree.get(succ) || 0) - 1;
      inDegree.set(succ, newDeg);
      if (newDeg === 0) {
        ready.push(succ);
      }
    }
  }

  // Cycle detection: Kahn's consumes all nodes iff the graph is acyclic.
  // Any node still unreached has a cycle in its predecessor chain.
  if (order.length < nodes.length) {
    const consumed = new Set(order);
    const cycle = nodes.filter(function(n) { return !consumed.has(n); });
    throw new RoadmapCycleError(cycle);
  }

  // Build output: 1-based number, single-sprint wave = depth + 1
  const number = {};
  const sprintWave = {};
  order.forEach(function(label, i) {
    number[label] = i + 1;
    sprintWave[label] = { sprint: 1, wave: (depth.get(label) || 0) + 1 };
  });

  return { order: order, number: number, sprintWave: sprintWave };
}

// ---------------------------------------------------------------------------
// checkDependencyOrder — fail-loud verification gate for authored stubs
// ---------------------------------------------------------------------------

/**
 * Verify that stub numbers and (sprint, wave) slots are dependency-monotone
 * across all declared blocked_by edges in the provided stub set.
 *
 * Invariant (must hold for every edge A blocked_by B, B ships first):
 *   number(B) < number(A)                           [strict]
 *   (sprint(B), wave(B)) <_lex (sprint(A), wave(A)) [strict; equal tuples are violations]
 *
 * A dependency and its dependent sharing the same (sprint, wave) slot is a violation:
 * blocked_by is a hard gate, and wave members dispatch concurrently and are
 * file-disjoint by construction, so cohabiting the same slot is structurally unsound.
 *
 * Missing sprint on either endpoint of a dependency edge is a fail-loud violation
 * of its own class ('missing-sprint') — not silently coerced into a comparison.
 * This upholds the detect-then-fail-loud-on-ambiguity doctrine.
 *
 * Edges pointing to stub_ids outside the provided set are reported as 'unresolved'
 * (not silently dropped) so that typo'd edges cannot hide.
 *
 * All violations are collected without short-circuiting — every offending edge is reported.
 *
 * @param {{ stub_id: string, number?: number, sprint?: number, wave?: number, blocked_by?: string[] }[]} stubs
 *   Array of stub descriptors. If 'number' is absent, it is derived by parsing the
 *   trailing -<N> integer from stub_id (format: <slug>-<N>).
 * @returns {{ ok: boolean, violations: any[], unresolved: any[], cycle: string[]|null }}
 *   ok         — true iff violations is empty AND unresolved is empty AND cycle is null.
 *   violations — list of ordering violations (number-order, same-or-inverted-slot, missing-sprint).
 *   unresolved — blocked_by edges pointing to stub_ids not in the provided set.
 *   cycle      — array of stub_ids forming a cycle, or null if acyclic.
 */
function checkDependencyOrder(stubs) {
  const violations = [];
  const unresolved = [];

  // Build stub map and resolve number from stub_id if not explicitly provided
  const stubMap = new Map();
  for (const stub of stubs) {
    let num = stub.number != null ? stub.number : null;
    if (num == null) {
      const m = /[-_](\d+)$/.exec(stub.stub_id);
      num = m ? parseInt(m[1], 10) : null;
    }
    // Store resolved number alongside original fields
    stubMap.set(stub.stub_id, Object.assign({}, stub, { _num: num }));
  }

  // Verify every declared blocked_by edge
  for (const stub of stubs) {
    const A = stubMap.get(stub.stub_id);
    const blockedBy = stub.blocked_by || [];

    for (const depId of blockedBy) {
      if (!stubMap.has(depId)) {
        // Edge to a stub not in the provided set — unresolved, not silently dropped
        unresolved.push({ from: stub.stub_id, to: depId, reason: 'unresolved-edge' });
        continue;
      }

      const B = stubMap.get(depId);

      // Missing-sprint: fail-loud as its own violation class.
      // Do NOT fall through to ordering checks when sprint is absent on either end.
      const aMissingS = A.sprint == null;
      const bMissingS = B.sprint == null;
      if (aMissingS || bMissingS) {
        violations.push({
          from: A.stub_id,
          to: B.stub_id,
          reason: 'missing-sprint',
          which: (aMissingS && bMissingS) ? 'both' : (aMissingS ? 'A' : 'B'),
        });
        continue;
      }

      // number-order check: number(B) < number(A) [strict]
      if (A._num != null && B._num != null) {
        if (!(B._num < A._num)) {
          violations.push({
            from: A.stub_id,
            to: B.stub_id,
            reason: 'number-order',
            numberA: A._num,
            numberB: B._num,
          });
        }
      }

      // (sprint, wave) strict lexicographic check.
      // Equal tuples are violations (same-slot dependency + dependent is forbidden).
      // Skip if wave is absent on either side (wave-absent is not sprint-absent;
      // wave-absent means the stub is not yet assigned a slot — we report only what
      // we can check rather than inventing a missing-wave violation class here,
      // since the plan spec names missing-sprint as the explicit fail-loud class).
      const aHasW = A.wave != null;
      const bHasW = B.wave != null;
      if (aHasW && bHasW) {
        const slotOk =
          B.sprint < A.sprint ||
          (B.sprint === A.sprint && B.wave < A.wave);
        if (!slotOk) {
          violations.push({
            from: A.stub_id,
            to: B.stub_id,
            reason: 'same-or-inverted-slot',
            slotA: { sprint: A.sprint, wave: A.wave },
            slotB: { sprint: B.sprint, wave: B.wave },
          });
        }
      }
    }
  }

  // Cycle detection over the blocked_by graph (DFS, within the provided stub set only)
  const cycleNodes = _detectCycles(stubs, stubMap);

  const ok = violations.length === 0 && unresolved.length === 0 && cycleNodes === null;

  return { ok: ok, violations: violations, unresolved: unresolved, cycle: cycleNodes };
}

// ---------------------------------------------------------------------------
// Internal: DFS cycle detection
// ---------------------------------------------------------------------------

/**
 * Detect cycles in the blocked_by graph using recursive DFS with three-colour marking.
 * Only traverses edges where both endpoints are in stubMap (the provided set).
 * Returns an array of stub_ids forming the cycle set, or null if acyclic.
 *
 * @param {any[]} stubs
 * @param {Map} stubMap
 * @returns {string[]|null}
 */
function _detectCycles(stubs, stubMap) {
  var WHITE = 0, GRAY = 1, BLACK = 2;
  var color = new Map();
  for (var i = 0; i < stubs.length; i++) {
    color.set(stubs[i].stub_id, WHITE);
  }

  var cycleFound = null;

  function dfs(id, path) {
    if (cycleFound) return;
    color.set(id, GRAY);
    path.push(id);

    var stub = stubMap.get(id);
    var deps = stub.blocked_by || [];
    for (var j = 0; j < deps.length; j++) {
      var depId = deps[j];
      if (!stubMap.has(depId)) continue; // unresolved edge — skip
      if (cycleFound) return;
      var c = color.get(depId);
      if (c === GRAY) {
        // Back edge found — extract the cycle from the current DFS path
        var cycleStart = path.indexOf(depId);
        cycleFound = path.slice(cycleStart);
        return;
      }
      if (c === WHITE) {
        dfs(depId, path);
      }
    }

    path.pop();
    color.set(id, BLACK);
  }

  for (var k = 0; k < stubs.length; k++) {
    if (cycleFound) break;
    if (color.get(stubs[k].stub_id) === WHITE) {
      dfs(stubs[k].stub_id, []);
    }
  }

  return cycleFound || null;
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = {
  RoadmapCycleError: RoadmapCycleError,
  topoNumber: topoNumber,
  checkDependencyOrder: checkDependencyOrder,
};
