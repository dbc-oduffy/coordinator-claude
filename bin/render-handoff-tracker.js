#!/usr/bin/env node
'use strict';
/**
 * render-handoff-tracker.js — Assemble a per-repo (or DoE-aggregated) handoff/spinoff/memo
 * tracker markdown from frontmatter-indexed records.
 *
 * Spec backlink: docs/plans/2026-05-29-handoff-tracker-renderer.md
 * Purpose: Render a durable markdown tracker (state/handoff-tracker.md per repo,
 *   ~/.claude/state/doe-handoff-tracker.md for DoE aggregation) by querying the
 *   query-records.js engine for active handoffs, spinoffs, and cross-repo memos.
 *
 * Negative-spec: does NOT glob handoff files directly — that bypasses applyConsumedMarker
 *   and loses completion-pruning (the PM's #1 constraint: completed items never appear).
 * Negative-spec: does NOT archive, move, or mutate any handoff/memo file.
 * Negative-spec: does NOT git add/commit.
 * Negative-spec: --all-repos does NOT use the repo-registry.md active-block for paths —
 *   it uses machine-local `repos.*` keys (the per-machine path source), consistent with
 *   cross-repo-memo's receiver-resolution model. repos absent on this machine are skipped.
 *
 * Usage:
 *   render-handoff-tracker [--root <path>] [--stdout] [--all-repos]
 *
 *   --root <path>   Repo root to query (default: git toplevel / cwd). Per-repo mode.
 *   --stdout        Print instead of writing tracker file (dry-run / ad-hoc).
 *   --all-repos     DoE mode: read all repos.* from machine-local, concatenate under
 *                   ## <shortname> headings, write to ~/.claude/state/doe-handoff-tracker.md.
 *                   Repos absent on disk are skipped with a note.
 *
 * Output paths:
 *   Per-repo: <root>/state/handoff-tracker.md
 *   DoE:      ~/.claude/state/doe-handoff-tracker.md
 *
 * Run with: node bin/render-handoff-tracker.js [flags]
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');
const { queryRecords } = require('./query-records.js');

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = { root: null, stdout: false, allRepos: false };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--root') { opts.root = args[++i]; }
    else if (a === '--stdout') { opts.stdout = true; }
    else if (a === '--all-repos') { opts.allRepos = true; }
    else {
      process.stderr.write(`Unknown argument: ${a}\n`);
      process.exit(1);
    }
  }
  return opts;
}

// ---------------------------------------------------------------------------
// Root detection
// ---------------------------------------------------------------------------
function detectRoot(specified) {
  if (specified) return path.resolve(specified);
  try {
    return execSync('git rev-parse --show-toplevel', {
      encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  } catch {
    return process.cwd();
  }
}

// ---------------------------------------------------------------------------
// Per-repo state root — resolves via the per-repo seam (C4)
//
// Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4
// For per-repo mode: if the given repo root IS the meta-repo (~/.claude), the handoff
// state lives in example-orchestration-hub (same as the central seam). Otherwise it lives in <root>/state.
// Mirrors the shell coordinator_state_root (no --central) taxonomy.
// ---------------------------------------------------------------------------
function resolvePerRepoStateRoot(root) {
  // Canonicalize both sides for comparison (resolve symlinks / relative segments).
  // path.resolve is synchronous and works cross-platform without spawning a process.
  const resolvedRoot = path.resolve(root);
  const metaRepo = path.resolve(path.join(os.homedir(), '.claude'));
  if (resolvedRoot === metaRepo) {
    // Meta-repo: per-repo state lives in example-orchestration-hub (same target as central).
    return resolveCentralStateRoot();
  }
  // Sibling repo: per-repo state stays in <root>/state.
  return path.join(root, 'state');
}

// ---------------------------------------------------------------------------
// Central state root — resolves via machine-local repos.example_orchestration_hub_repo (C3)
//
// Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C3
// The central coordinator state (doe-handoff-tracker.md etc.) lives in the example-orchestration-hub
// sibling-repo's state/ dir rather than ~/.claude/state/ after migration.
// Falls back to ~/.claude for backward compat on machines without example_orchestration_hub_repo registered.
// ---------------------------------------------------------------------------
function resolveCentralStateRoot() {
  // Locate machine-local CLI (same search order as readMachineLocalRepos)
  const machinelocalCandidates = [
    path.join(__dirname, '..', '..', '..', '..', 'bin', 'machine-local'),
    path.join(os.homedir(), '.claude', 'bin', 'machine-local'),
  ];
  const mlCli = machinelocalCandidates.find(p => { try { return fs.existsSync(p); } catch { return false; } });

  if (mlCli) {
    try {
      const example_orchestration_hubRoot = execSync(
        `${JSON.stringify(mlCli)} get repos.example_orchestration_hub_repo`,
        { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] },
      ).trim();
      if (example_orchestration_hubRoot) return path.join(example_orchestration_hubRoot, 'state');
    } catch {
      // machine-local not configured on this machine — fall through to legacy path
    }
  }

  // Backward-compat fallback for machines without example_orchestration_hub_repo registered.
  return path.join(os.homedir(), '.claude', 'state');
}

// ---------------------------------------------------------------------------
// machine-local repo iteration (for --all-repos)
// ---------------------------------------------------------------------------
/**
 * Read machine-local registry.local.toml directly and extract repos.* keys.
 * Falls back to shelling out to `machine-local keys` if TOML parse is not
 * feasible (Python 3.10 or missing file). Returns [{key, shortname, repoPath}].
 *
 * Shell-out is the canonical contract per machine-local-registry.md §8(a):
 * "shell-out is the only contract" for consumers — we shell out here.
 */
function readMachineLocalRepos() {
  // Locate machine-local CLI relative to this script's directory or ~/.claude/bin/
  const machinelocalCandidates = [
    path.join(__dirname, '..', '..', '..', '..', 'bin', 'machine-local'),
    path.join(os.homedir(), '.claude', 'bin', 'machine-local'),
  ];

  let machinelocalBin = null;
  for (const candidate of machinelocalCandidates) {
    if (fs.existsSync(candidate)) { machinelocalBin = candidate; break; }
  }

  if (!machinelocalBin) {
    process.stderr.write('render-handoff-tracker: machine-local CLI not found; --all-repos unavailable\n');
    return [];
  }

  let keysOutput;
  try {
    keysOutput = execSync(`bash "${machinelocalBin}" keys`, {
      encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  } catch (e) {
    process.stderr.write(`render-handoff-tracker: machine-local keys failed: ${e.message}\n`);
    return [];
  }

  const repos = [];
  for (const line of keysOutput.split('\n')) {
    const key = line.trim();
    if (!key.startsWith('repos.')) continue;
    // Derive shortname from key: repos.project_rag_ue_addon → project-rag-ue-addon
    const shortname = key.slice('repos.'.length).replace(/_/g, '-');
    let repoPath;
    try {
      repoPath = execSync(`bash "${machinelocalBin}" get ${key}`, {
        encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
      }).trim();
    } catch {
      continue;
    }
    repos.push({ key, shortname, repoPath });
  }
  return repos;
}

// ---------------------------------------------------------------------------
// Active-state filter (in-assembler — query-records has no NOT IN)
// ---------------------------------------------------------------------------
const TERMINAL_DEPLOYMENT = new Set(['shipped', 'abandoned']);
const TERMINAL_STATUS = new Set(['consumed', 'superseded']);

function isActive(fm) {
  if (!fm) return false; // parse-error records have null frontmatter — excluded from active set
  const ds = String(fm.deployment_state || '');
  const st = String(fm.status || '');
  if (TERMINAL_DEPLOYMENT.has(ds)) return false;
  if (TERMINAL_STATUS.has(st)) return false;
  return true;
}

// ---------------------------------------------------------------------------
// Date normalisation (bare YYYY-MM-DD or full ISO-8601)
// ---------------------------------------------------------------------------
function toIsoDate(val) {
  if (!val) return '';
  const s = String(val);
  // bare date or ISO-8601 — take first 10 chars
  return s.slice(0, 10);
}

// ---------------------------------------------------------------------------
// Workstream-seq denominator: count all handoffs (active + archived) sharing workstream
// ---------------------------------------------------------------------------
/**
 * Build a map of workstream slug → sorted array of created dates (ascending).
 * Denominator is total count across both active (type:handoff) and archived
 * (type:handoff-archived) records sharing the same workstream slug.
 * Archive read is COUNT-ONLY (no mutation).
 */
function buildWorkstreamIndex(root) {
  const baseOpts = {
    type: 'handoff',
    where: null, sort: null, limit: 0, since: null, olderThan: null,
    root: null, format: 'json', includeUnparseable: false,
  };

  const liveRecords = queryRecords({ ...baseOpts, type: 'handoff' }, root);
  const archivedRecords = queryRecords({ ...baseOpts, type: 'handoff-archived' }, root);
  const all = [...liveRecords, ...archivedRecords];

  // Map: workstream → sorted array of created dates (to compute rank)
  const wsMap = new Map(); // workstream slug → [ISO date string, ...]
  for (const r of all) {
    const fm = r.frontmatter;
    if (!fm) continue;
    const ws = fm.workstream;
    if (!ws) continue;
    const created = toIsoDate(fm.created);
    if (!wsMap.has(ws)) wsMap.set(ws, []);
    wsMap.get(ws).push(created);
  }
  // Sort each array ascending so rank = indexOf + 1
  for (const [, dates] of wsMap) {
    dates.sort();
  }
  return wsMap;
}

/**
 * Given a workstream slug and this record's created date, return "N of M" string.
 * N = 1-based rank (created-ascending). M = total count for that workstream.
 * Returns null if workstream is absent or M === 0.
 */
function workstreamSeq(wsMap, workstream, created) {
  if (!workstream) return null;
  const dates = wsMap.get(workstream);
  if (!dates || dates.length === 0) return null;
  const M = dates.length;
  const isoCreated = toIsoDate(created);
  // Find first matching index (stable — multiple files may share a date; rank ties ok)
  const N = dates.indexOf(isoCreated) + 1;
  if (N === 0) return `? of ${M}`;
  return `${N} of ${M}`;
}

// ---------------------------------------------------------------------------
// Markdown table helpers
// ---------------------------------------------------------------------------
function mdLink(text, target) {
  if (!text || !target) return text || '';
  return `[${text}](${target})`;
}

function cell(val) {
  if (val === null || val === undefined || val === '') return '';
  return String(val);
}

/**
 * Render a markdown table from headers and rows (array of arrays).
 * Padding is minimal (no column alignment) for machine-generated output.
 */
function renderTable(headers, rows) {
  if (rows.length === 0) return '_none_';
  const sep = headers.map(() => '---');
  const lines = [
    '| ' + headers.join(' | ') + ' |',
    '| ' + sep.join(' | ') + ' |',
    ...rows.map(r => '| ' + r.map(cell).join(' | ') + ' |'),
  ];
  return lines.join('\n');
}

// ---------------------------------------------------------------------------
// Per-record row builders
// ---------------------------------------------------------------------------

/**
 * Build a row for the Handoffs table (plain/recovery kind).
 * Columns: File, Created, Deployment State, Category, Summary, Workstream-Seq
 */
function handoffRow(r, wsMap) {
  const fm = r.frontmatter;
  if (!fm) {
    // parse-error row — fail-loud per AC8
    return [
      `⚠ PARSE-ERROR | ${r.path}`,
      '', '', '', '', '',
    ];
  }
  const filename = path.basename(r.path);
  const fileLink = mdLink(filename, r.path);
  const created = toIsoDate(fm.created);
  const ds = cell(fm.deployment_state);
  const category = fm.category ? String(fm.category) : '—';
  const summary = cell(fm.summary || fm.title);
  const ws = fm.workstream ? String(fm.workstream) : null;
  const seq = ws ? workstreamSeq(wsMap, ws, fm.created) : null;
  const seqDisplay = seq || (ws ? ws : 'standalone');
  return [fileLink, created, ds, category, summary, seqDisplay];
}

/**
 * Build a row for the Spinoffs table (spinoff / spinoff-roadmap kind).
 * Base columns: File, Created, Deployment State, Category, Summary, Workstream-Seq
 * Roadmap-kind additionally appends stub_id and blocked_by.
 */
function spinoffRow(r, wsMap, isRoadmap) {
  const fm = r.frontmatter;
  const filename = path.basename(r.path);
  const fileLink = mdLink(filename, r.path);
  const created = toIsoDate(fm.created);
  const ds = cell(fm.deployment_state);
  const category = fm.category ? String(fm.category) : '—';
  const summary = cell(fm.summary || fm.title);
  const ws = fm.workstream ? String(fm.workstream) : null;
  const seq = ws ? workstreamSeq(wsMap, ws, fm.created) : null;
  const seqDisplay = seq || (ws ? ws : 'standalone');
  const base = [fileLink, created, ds, category, summary, seqDisplay];
  if (isRoadmap) {
    base.push(cell(fm.stub_id));
    // blocked_by is a YAML list or string; normalise to display string
    const bb = fm.blocked_by;
    let bbDisplay = '';
    if (Array.isArray(bb)) bbDisplay = bb.join(', ');
    else if (bb) bbDisplay = String(bb);
    base.push(bbDisplay);
  }
  return base;
}

/**
 * Build a row for the Cross-Repo-Memos table.
 * Columns: File, Created, From, To, Status, Summary
 */
function memoRow(r) {
  const fm = r.frontmatter;
  const filename = path.basename(r.path);
  const fileLink = mdLink(filename, r.path);
  const created = toIsoDate(fm.created);
  return [
    fileLink,
    created,
    cell(fm.from),
    cell(fm.to),
    cell(fm.status),
    cell(fm.title),
  ];
}

// ---------------------------------------------------------------------------
// Group records by workstream, sort workstreams alphabetically, rows by created desc
// ---------------------------------------------------------------------------

/**
 * Sort and group records by workstream for table rendering.
 * Records lacking workstream are treated as standalone (NOT grouped).
 * Returns array of { workstream: string|null, rows: record[] }.
 */
function groupByWorkstream(records) {
  const grouped = new Map(); // workstream → records[]
  const standalones = []; // records with no workstream

  for (const r of records) {
    const fm = r.frontmatter;
    const ws = fm && fm.workstream ? String(fm.workstream) : null;
    if (!ws) {
      standalones.push(r);
    } else {
      if (!grouped.has(ws)) grouped.set(ws, []);
      grouped.get(ws).push(r);
    }
  }

  // Sort workstreams alphabetically
  const sortedWorkstreams = [...grouped.keys()].sort();

  const result = [];
  for (const ws of sortedWorkstreams) {
    const recs = grouped.get(ws);
    // Sort rows within workstream by created desc
    recs.sort((a, b) => {
      const da = toIsoDate(a.frontmatter && a.frontmatter.created);
      const db = toIsoDate(b.frontmatter && b.frontmatter.created);
      if (da < db) return 1;
      if (da > db) return -1;
      return 0;
    });
    result.push({ workstream: ws, rows: recs });
  }

  // Standalone records sorted by created desc, each rendered separately (no shared bucket)
  for (const r of standalones) {
    result.push({ workstream: null, rows: [r] });
  }

  return result;
}

// ---------------------------------------------------------------------------
// Per-repo section renderer
// ---------------------------------------------------------------------------

/**
 * Render the full tracker section for one repo root.
 * Returns a markdown string (no trailing newline).
 */
function renderRepoSection(root) {
  const wsMap = buildWorkstreamIndex(root);

  // --- Query active handoffs (includeUnparseable for fail-loud AC8) ---
  const allHandoffOpts = {
    type: 'handoff',
    where: null, sort: null, limit: 0, since: null, olderThan: null,
    root: null, format: 'json', includeUnparseable: true,
  };
  const allHandoffs = queryRecords(allHandoffOpts, root);

  // Split active handoffs by kind
  const activeHandoffs = []; // plain session-handoff + recovery, active
  const activeSpinoffs = []; // spinoff + spinoff-roadmap, active
  const parseErrors = [];   // frontmatter===null — always fail-loud

  for (const r of allHandoffs) {
    if (r.frontmatter === null) {
      // parse-error — include in handoffs table as fail-loud row
      parseErrors.push(r);
      continue;
    }
    // Active filter
    if (!isActive(r.frontmatter)) continue;
    const kind = r.frontmatter.kind ? String(r.frontmatter.kind) : '';
    if (kind === 'spinoff' || kind === 'spinoff-roadmap') {
      activeSpinoffs.push(r);
    } else {
      // plain session-handoff, recovery, or absent kind
      activeHandoffs.push(r);
    }
  }

  // --- Query open cross-repo memos (plain queryRecords, no includeUnparseable) ---
  const memoOpts = {
    type: 'cross-repo-memo',
    where: 'status=open', sort: null, limit: 0, since: null, olderThan: null,
    root: null, format: 'json', includeUnparseable: false,
  };
  // queryRecords where clause is parsed internally; pass as string field
  const memoOptsResolved = {
    ...memoOpts,
    where: null, // we'll filter manually to avoid requiring parseWhereExpr here
  };
  const allMemos = queryRecords(memoOptsResolved, root);
  // Include in_progress (claimed-at-pickup) memos alongside open ones — a claimed memo is
  // being handled, not free, but it must still appear on the status board with its state
  // (the Status column shows open vs in_progress). Excluding it would make the tracker
  // under-report the same way an unsurfaced in_progress memo makes the inbox look free.
  // Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C4
  // NOTE: these status values mirror the cross-repo-memo schema enum
  // (schemas/cross-repo-memo.yaml `status.values`) — keep in lockstep if the enum changes.
  const openMemos = allMemos.filter(r => r.frontmatter && (r.frontmatter.status === 'open' || r.frontmatter.status === 'in_progress'));

  // --- Render Handoffs table ---
  const handoffHeaders = ['File', 'Created', 'State', 'Category', 'Summary', 'Workstream-Seq'];
  const handoffErrorRows = parseErrors.map(r => handoffRow(r, wsMap));
  const handoffGroups = groupByWorkstream(activeHandoffs);
  const handoffBodyRows = [];
  for (const { rows } of handoffGroups) {
    for (const r of rows) {
      handoffBodyRows.push(handoffRow(r, wsMap));
    }
  }
  const allHandoffRows = [...handoffErrorRows, ...handoffBodyRows];

  // --- Render Spinoffs table ---
  const hasRoadmap = activeSpinoffs.some(r => r.frontmatter && r.frontmatter.kind === 'spinoff-roadmap');
  const spinoffHeaders = ['File', 'Created', 'State', 'Category', 'Summary', 'Workstream-Seq'];
  if (hasRoadmap) spinoffHeaders.push('stub_id', 'blocked_by');

  const spinoffGroups = groupByWorkstream(activeSpinoffs);
  const spinoffBodyRows = [];
  for (const { rows } of spinoffGroups) {
    for (const r of rows) {
      const isRoadmap = hasRoadmap; // render extra columns when ANY row is roadmap
      spinoffBodyRows.push(spinoffRow(r, wsMap, isRoadmap));
    }
  }

  // --- Render Memos table ---
  const memoHeaders = ['File', 'Created', 'From', 'To', 'Status', 'Summary'];
  const memoBodyRows = openMemos.map(r => memoRow(r));

  const generated = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

  const lines = [
    `<!-- generated: ${generated} — do not edit by hand; re-run render-handoff-tracker.js -->`,
    '',
    '## Handoffs',
    '',
    renderTable(handoffHeaders, allHandoffRows),
    '',
    '## Spinoffs',
    '',
    renderTable(spinoffHeaders, spinoffBodyRows),
    '',
    '## Cross-Repo Memos',
    '',
    renderTable(memoHeaders, memoBodyRows),
  ];
  return lines.join('\n');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
function main() {
  const opts = parseArgs(process.argv);

  if (opts.allRepos) {
    // DoE mode: iterate all machine-local repos.* paths
    const repos = readMachineLocalRepos();
    if (repos.length === 0) {
      process.stderr.write('render-handoff-tracker --all-repos: no repos.* keys found in machine-local\n');
      process.exit(1);
    }

    const sections = [];
    const skipped = [];

    for (const { shortname, repoPath } of repos) {
      if (!fs.existsSync(repoPath)) {
        skipped.push(`${shortname} (${repoPath} — not on disk)`);
        continue;
      }
      const section = renderRepoSection(repoPath);
      sections.push(`## ${shortname}\n\n_root: ${repoPath}_\n\n${section}`);
    }

    const generated = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
    const header = [
      `# DoE Handoff Tracker`,
      '',
      `_Generated: ${generated}_`,
      '',
    ].join('\n');

    let output = header + sections.join('\n\n---\n\n');
    if (skipped.length > 0) {
      output += '\n\n---\n\n## Skipped repos (not on disk)\n\n' +
        skipped.map(s => `- ${s}`).join('\n');
    }

    if (opts.stdout) {
      process.stdout.write(output + '\n');
    } else {
      const outPath = path.join(resolveCentralStateRoot(), 'doe-handoff-tracker.md');
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
      fs.writeFileSync(outPath, output + '\n', 'utf8');
      process.stdout.write(`Wrote DoE tracker → ${outPath}\n`);
    }

  } else {
    // Per-repo mode
    const root = detectRoot(opts.root);
    const section = renderRepoSection(root);

    const generated = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
    const header = [
      `# Handoff Tracker`,
      '',
      `_Generated: ${generated} | root: ${root}_`,
      '',
    ].join('\n');
    const output = header + section;

    if (opts.stdout) {
      process.stdout.write(output + '\n');
    } else {
      const outPath = path.join(resolvePerRepoStateRoot(root), 'handoff-tracker.md');
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
      fs.writeFileSync(outPath, output + '\n', 'utf8');
      process.stdout.write(`Wrote tracker → ${outPath}\n`);
    }
  }
}

if (require.main === module) {
  main();
}

module.exports = { renderRepoSection, buildWorkstreamIndex, workstreamSeq, isActive };
