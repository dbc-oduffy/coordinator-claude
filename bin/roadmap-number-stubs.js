#!/usr/bin/env node
'use strict';
/**
 * roadmap-number-stubs.js — authoring-helper CLI for roadmap stub topological linearization.
 *
 * Purpose: thin CLI wrapper over topoNumber (constructive) and checkDependencyOrder
 * (verification) from bin/lib/roadmap-graph.js. Provides two modes:
 *
 *   Default mode  — read a small edges file the author writes from clusters.md BEFORE
 *                   stubs exist; print a label → (stub number, sprint, wave) mapping
 *                   table for the author to transcribe into stub frontmatter. Stub
 *                   numbers are emitted zero-padded to ≥2 digits (width = max(2,
 *                   digits of the highest stub number in the set), e.g. 04, 12).
 *
 *   --check mode  — verify that stubs ALREADY ON DISK for a given roadmap_id have
 *                   dependency-monotone (sprint, wave) ordering. Shares the
 *                   checkDependencyOrder code path with audit-roadmap.sh Audit 5.
 *
 * Domain vocabulary: stub, sprint, wave, topological linearization, blocked_by edge,
 * dependency-monotone, (sprint, wave) slot, roadmap_id, spinoff-roadmap.
 *
 * Spec backlink: docs/plans/2026-06-28-roadmap-stub-numbering-dependency-order.md § C2
 *
 * Node built-ins only; CommonJS. No external dependencies. Guards CLI entry behind
 * `require.main === module` so the module is safely require()-able in tests.
 */

// verify-no-console-flash: allow — on-demand roadmap authoring helper, not session-hot-path

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const { topoNumber, checkDependencyOrder, RoadmapCycleError } =
  require('./lib/roadmap-graph.js');

// ---------------------------------------------------------------------------
// Root resolution
// ---------------------------------------------------------------------------

/**
 * Resolve repo root robustly: git rev-parse first, fall back to the parent of
 * the `bin/` directory that contains this script (handles detached / non-git runs).
 */
function resolveRoot() {
  try {
    return execSync('git rev-parse --show-toplevel', { encoding: 'utf8' }).trim();
  } catch (_) {
    // Fall back: this file lives at <root>/plugins/.../bin/roadmap-number-stubs.js
    // so __dirname is <root>/plugins/.../bin — walk up to repo root heuristically.
    return path.resolve(__dirname, '../../../../');
  }
}

// ---------------------------------------------------------------------------
// Edges-file parsing
// ---------------------------------------------------------------------------

/**
 * Parse an edges file.
 * Accepts two forms:
 *   (a) JSON array of {from, to} objects — detected by a successful JSON.parse.
 *   (b) Line form: "A <- B" meaning "A blocked_by B" (→ {from:'A', to:'B'}).
 *       Blank lines and lines starting with '#' are ignored.
 *       A line with no '<-' and non-empty content is treated as an isolated node.
 * Returns { edges: [{from, to}], isolatedNodes: string[] }.
 */
function parseEdgesFile(content) {
  const trimmed = content.trim();

  // Attempt JSON parse first.
  if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
    try {
      const parsed = JSON.parse(trimmed);
      const arr = Array.isArray(parsed) ? parsed : [parsed];
      const edges = arr.map(function(e, i) {
        if (typeof e.from !== 'string' || typeof e.to !== 'string') {
          throw new Error('JSON entry ' + i + ' missing string "from" or "to" field');
        }
        return { from: e.from, to: e.to };
      });
      return { edges: edges, isolatedNodes: [] };
    } catch (jsonErr) {
      process.stderr.write('ERROR: file looks like JSON but failed to parse: ' + jsonErr.message + '\n');
      process.exit(1);
    }
  }

  // Line form parsing.
  const edges = [];
  const isolatedNodes = [];
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const arrowIdx = line.indexOf('<-');
    if (arrowIdx !== -1) {
      const lhs = line.slice(0, arrowIdx).trim();
      const rhs = line.slice(arrowIdx + 2).trim();
      if (!lhs || !rhs) {
        process.stderr.write('WARNING: malformed edge line ' + (i + 1) + ': "' + raw + '" — skipped\n');
        continue;
      }
      edges.push({ from: lhs, to: rhs });
    } else {
      // Bare label — isolated node.
      isolatedNodes.push(line);
    }
  }
  return { edges: edges, isolatedNodes: isolatedNodes };
}

// ---------------------------------------------------------------------------
// Node-set derivation
// ---------------------------------------------------------------------------

/**
 * Derive the full node set from edges (union of all labels) plus any explicit
 * isolated nodes. Preserves first-seen order for stable tie-breaking.
 */
function deriveNodes(edges, isolatedNodes) {
  const seen = new Set();
  const nodes = [];
  function add(label) {
    if (!seen.has(label)) {
      seen.add(label);
      nodes.push(label);
    }
  }
  for (const e of edges) {
    add(e.to);   // dependency (ships first) — add before dependent for topo order
    add(e.from); // dependent
  }
  for (const n of isolatedNodes) {
    add(n);
  }
  return nodes;
}

// ---------------------------------------------------------------------------
// Default mode — constructive linearization
// ---------------------------------------------------------------------------

/**
 * Run topoNumber on the parsed edges and print the mapping table.
 * Table format (one row per label, topological order — dependencies before dependents):
 *   <label>  →  stub N  sprint 1  wave W
 */
function runDefaultMode(edgesFilePath) {
  let content;
  try {
    content = fs.readFileSync(edgesFilePath, 'utf8');
  } catch (err) {
    process.stderr.write('ERROR: cannot read edges file "' + edgesFilePath + '": ' + err.message + '\n');
    process.exit(2);
  }

  const { edges, isolatedNodes } = parseEdgesFile(content);
  const nodes = deriveNodes(edges, isolatedNodes);

  if (nodes.length === 0) {
    process.stderr.write('ERROR: no nodes derived from edges file — is the file empty or malformed?\n');
    process.exit(2);
  }

  let result;
  try {
    result = topoNumber(nodes, edges);
  } catch (err) {
    if (err instanceof RoadmapCycleError) {
      process.stderr.write('ERROR: dependency cycle detected — cycle nodes: ' + err.cycle.join(', ') + '\n');
      process.stderr.write('Fix the cycle before numbering stubs.\n');
      process.exit(1);
    }
    throw err;
  }

  // Print header
  process.stdout.write('# Roadmap stub linearization\n');
  process.stdout.write('# Transcribe these values into stub frontmatter (number, sprint, wave).\n');
  process.stdout.write('# Dependencies appear before their dependents.\n');
  process.stdout.write('# Stub numbers are zero-padded to ≥2 digits — use the padded form in frontmatter and filenames.\n');
  process.stdout.write('#\n');
  process.stdout.write('# label                    stub#  sprint  wave\n');
  process.stdout.write('# ' + '-'.repeat(52) + '\n');

  const maxNum = Math.max(...result.order.map(function(l) { return result.number[l]; }));
  const width = Math.max(2, String(maxNum).length);
  const padLabel = 26;
  for (const label of result.order) {
    const num = result.number[label];
    const sw = result.sprintWave[label];
    const numPad = String(num).padStart(width, '0');
    const labelPad = label.length < padLabel ? label + ' '.repeat(padLabel - label.length) : label;
    process.stdout.write(labelPad + '  ' + numPad + '      ' + sw.sprint + '       ' + sw.wave + '\n');
  }
}

// ---------------------------------------------------------------------------
// --check mode — dependency-order verification against stubs on disk
// ---------------------------------------------------------------------------

/**
 * Enumerate stubs for a given roadmap_id (live + archived spinoff-roadmap stubs),
 * parse their frontmatter, build the stubs array, and call checkDependencyOrder.
 * Mirrors the idiom used in audit-roadmap.sh Audits 1 and 4.
 */
function runCheckMode(runId) {
  const root = resolveRoot();
  const qrPath = path.join(root, 'plugins/coordinator/bin/query-records.js');

  if (!fs.existsSync(qrPath)) {
    process.stderr.write('ERROR: query-records.js not found at ' + qrPath + '\n');
    process.stderr.write('Run from a repo that contains the coordinator plugin.\n');
    process.exit(2);
  }

  // Review: code-reviewer (F2/P2) — parallel existence guard for schema.js; qrPath already
  // gets a clean stderr+exit(2) treatment above; schema.js deserves the same rather than an
  // unhandled require() throw with a raw stack trace.
  const schemaPath = path.join(root, 'plugins/coordinator/bin/lib/schema.js');
  if (!fs.existsSync(schemaPath)) {
    process.stderr.write('ERROR: schema.js not found at ' + schemaPath + '\n');
    process.stderr.write('Run from a repo that contains the coordinator plugin.\n');
    process.exit(2);
  }

  const { parseFrontmatter } = require(schemaPath);

  // Enumerate live stubs
  let livePaths = [];
  let archPaths = [];
  try {
    const liveOut = execSync(
      'node ' + JSON.stringify(qrPath) +
      ' --type handoff' +
      ' --where ' + JSON.stringify('kind=spinoff-roadmap AND roadmap_id=' + runId) +
      ' --format paths' +
      ' --root ' + JSON.stringify(root),
      { encoding: 'utf8' }
    ).trim();
    if (liveOut) livePaths = liveOut.split('\n').filter(Boolean);
  // Review: code-reviewer (F6/nit) — bare catch silently treats an invocation failure as
  // "no stubs", enabling a silent false-pass. Surface the error while preserving continue-with-
  // what-we-have semantics (don't abort — the archived query may still yield stubs).
  } catch (err) { process.stderr.write('WARNING: query-records live query failed: ' + err.message + '\n'); }

  try {
    const archOut = execSync(
      'node ' + JSON.stringify(qrPath) +
      ' --type handoff-archived' +
      ' --where ' + JSON.stringify('kind=spinoff-roadmap AND roadmap_id=' + runId) +
      ' --format paths' +
      ' --root ' + JSON.stringify(root),
      { encoding: 'utf8' }
    ).trim();
    if (archOut) archPaths = archOut.split('\n').filter(Boolean);
  } catch (err) { process.stderr.write('WARNING: query-records archived query failed: ' + err.message + '\n'); }

  const allPaths = livePaths.concat(archPaths);

  if (allPaths.length === 0) {
    process.stdout.write('No spinoff-roadmap stubs found for roadmap_id=' + runId + '\n');
    process.stdout.write('(Nothing to check — create stubs first, then re-run --check.)\n');
    process.exit(0);
  }

  // Parse each stub's frontmatter to build the stubs array for checkDependencyOrder.
  const stubs = [];
  for (const relPath of allPaths) {
    const absPath = path.isAbsolute(relPath) ? relPath : path.join(root, relPath);
    let content;
    try {
      content = fs.readFileSync(absPath, 'utf8');
    } catch (err) {
      process.stderr.write('WARNING: cannot read stub file "' + absPath + '": ' + err.message + '\n');
      continue;
    }
    const parsed = parseFrontmatter(content);
    const fm = parsed.frontmatter || {};
    stubs.push({
      stub_id:   fm.stub_id   || '',
      number:    fm.number    != null ? Number(fm.number)    : undefined,
      sprint:    fm.sprint    != null ? Number(fm.sprint)    : undefined,
      wave:      fm.wave      != null ? Number(fm.wave)      : undefined,
      blocked_by: Array.isArray(fm.blocked_by) ? fm.blocked_by : (fm.blocked_by ? [fm.blocked_by] : []),
    });
  }

  const result = checkDependencyOrder(stubs);

  if (result.ok) {
    process.stdout.write('OK: dependency order is valid for roadmap_id=' + runId + '\n');
    process.stdout.write('  ' + stubs.length + ' stub(s) checked; all (sprint, wave) slots are dependency-monotone.\n');
    process.exit(0);
  }

  // Print violations
  if (result.cycle) {
    process.stderr.write('FAIL: dependency cycle detected among stub_ids: ' + result.cycle.join(', ') + '\n');
  }

  for (const v of result.violations) {
    if (v.reason === 'missing-sprint') {
      process.stderr.write(
        'FAIL [missing-sprint]: edge ' + v.from + ' blocked_by ' + v.to +
        ' — sprint absent on ' + v.which + '\n'
      );
    } else if (v.reason === 'number-order') {
      process.stderr.write(
        'FAIL [number-order]: ' + v.from + ' (#' + v.numberA + ') blocked_by ' + v.to +
        ' (#' + v.numberB + ') — dependency must have a lower number\n'
      );
    } else if (v.reason === 'same-or-inverted-slot') {
      process.stderr.write(
        'FAIL [same-or-inverted-slot]: ' + v.from +
        ' (sprint=' + v.slotA.sprint + ', wave=' + v.slotA.wave + ') blocked_by ' +
        v.to + ' (sprint=' + v.slotB.sprint + ', wave=' + v.slotB.wave + ')' +
        ' — dependency must occupy an earlier (sprint, wave) slot\n'
      );
    } else {
      process.stderr.write('FAIL [' + v.reason + ']: ' + v.from + ' → ' + v.to + '\n');
    }
  }

  for (const u of result.unresolved) {
    process.stderr.write(
      'FAIL [unresolved-edge]: ' + u.from + ' blocked_by ' + u.to +
      ' — no stub with that stub_id found in roadmap_id=' + runId + '\n'
    );
  }

  process.exit(1);
}

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------

/**
 * Parse argv and dispatch to the appropriate mode.
 * Guarded by require.main === module so this file is safely require()-able.
 */
function main(argv) {
  const args = argv.slice(2);

  if (args.length === 0) {
    process.stderr.write('Usage:\n');
    process.stderr.write('  roadmap-number-stubs.js <edges-file>      # linearize from edges file\n');
    process.stderr.write('  roadmap-number-stubs.js --check <run-id>  # verify stubs on disk\n');
    process.exit(2);
  }

  if (args[0] === '--check') {
    const runId = args[1];
    if (!runId) {
      process.stderr.write('ERROR: --check requires a <run-id> argument\n');
      process.exit(2);
    }
    // Review: code-reviewer (F4/P2) — allowlist slug guard prevents query-corruption via
    // AND-injection or YAML metacharacters in the --where argument. Detect-then-fail-loud.
    if (!/^[a-z0-9][a-z0-9-]*$/.test(runId)) {
      process.stderr.write('ERROR: <run-id> must match ^[a-z0-9][a-z0-9-]*$ (got: "' + runId + '")\n');
      process.exit(2);
    }
    runCheckMode(runId);
  } else if (args[0].startsWith('--')) {
    // Review: code-reviewer (F5/nit) — unknown --flag would fall through to runDefaultMode
    // and emit "cannot read edges file '--help'" — catch it early with a clear error.
    process.stderr.write('ERROR: unknown flag "' + args[0] + '"\n');
    process.stderr.write('Usage:\n');
    process.stderr.write('  roadmap-number-stubs.js <edges-file>      # linearize from edges file\n');
    process.stderr.write('  roadmap-number-stubs.js --check <run-id>  # verify stubs on disk\n');
    process.exit(2);
  } else {
    const edgesFilePath = args[0];
    runDefaultMode(edgesFilePath);
  }
}

if (require.main === module) {
  main(process.argv);
}

module.exports = { parseEdgesFile, deriveNodes };
