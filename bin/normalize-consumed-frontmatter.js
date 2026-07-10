#!/usr/bin/env node
'use strict';
/**
 * normalize-consumed-frontmatter.js — flip frontmatter to match `<!-- consumed: ... -->` body markers.
 *
 * Belt-and-suspenders companion to query-records.js: query-records normalizes
 * marker-bearing records at read time, but the on-disk frontmatter is what an
 * EM sees first. Drift between marker and frontmatter is a confusion source —
 * this script eliminates it.
 *
 * For each record whose body contains `<!-- consumed: YYYY-MM-DD [notes] -->`:
 *   - `status: active` (or anything non-terminal) → `status: consumed`
 *   - `deployment_state: {ready_to_fire,awaiting_gate,in_flight}` → `shipped`
 *   - inserts `consumed_at:` if absent (date from marker)
 *   - inserts `shipped_in:` if absent and marker carries CONFORMING notes
 *     (a bare hex SHA or the sanctioned substantively-shipped-no-commit:<YYYY-MM-DD>
 *     token — see SHIPPED_IN_RE below). Non-conforming notes (prose, annotated
 *     SHAs) are refused, not written; the refusal is recorded in `changes[]` so
 *     the run's stdout summary surfaces it instead of silently dropping it.
 *   - strips `gate_dependency:` (only meaningful while awaiting_gate)
 *
 * Historical note: gate_dependency content is dropped on flip; if retros need
 * this signal in the future, encode it in the body marker's [notes] (the
 * shipped_in field captures it from there).
 * Review: the Staff Engineer F2 — document the loss-of-history tradeoff so future readers
 * don't ask the same question the Staff Engineer did.
 *
 * Terminal states (`superseded`, `abandoned`) are preserved.
 *
 * Only git-tracked files are modified — untracked drafts (e.g. stubs with a
 * consumed-marker placeholder) are silently skipped.
 * Review: the Staff Engineer F5 — gate walkDir results on `git ls-files` to prevent silent
 * rewrites of untracked draft files.
 *
 * Usage:
 *   normalize-consumed-frontmatter.js [--dry-run] [--root <path>]
 *                                     [--type handoff|plan|decision|review]
 *
 * Default scans handoff + plan + decision + review.
 * Exit codes: 0 = no drift OR drift fixed; 0 with non-empty stdout summarizes changes.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { TERMINAL_STATUS, TERMINAL_DEPLOYMENT, CONSUMED_MARKER_RE } = require('./lib/consumed-marker');
// Review: the Staff Engineer F3 — import shared constants/regex so write-time and read-time
// paths stay greppably aligned without copy-paste drift.
const { splitFrontmatter, readFmField, serializeYamlScalar, replaceFmField, insertFmField, removeFmField } = require('./lib/schema');
// C1c: FM read/write primitives moved to the shared schema.js module (canonical
// reconciliation of 5 divergent copies — see schema.js for the boundary-lookahead
// and quoting-shape rationale). Local copies removed; this file now consumes them.
// removeFmField's local copy (unbounded `^key:.*` — no boundary lookahead) was
// migrated onto the shared boundary-safe implementation 2026-07-09 (code-reviewer B-F1).

// C4b: shipped_in shape guard, mirrored verbatim from the schema.js cross-field
// rule (Rule A3a-2b, bin/lib/schema.js) so the write-time path here and the
// validate-time path there stay in agreement. Accepts a bare hex SHA (7-64
// chars) OR the sanctioned substantively-shipped-no-commit:<YYYY-MM-DD> token.
// Whole-value ($-anchored) match — no accept-anything-after-the-colon.
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C4b
const SHIPPED_IN_RE = /^([0-9a-fA-F]{7,64}|substantively-shipped-no-commit:\d{4}-\d{2}-\d{2})$/;

// RAG-bait: scan top-level archive/handoffs/ only. tasks/handoffs/archive/ is a
//           grandfathered example-game-repo-specific path (read-only per
//           spinoff-handoffs.md:341-342) — do NOT add it here.
const TYPE_TO_GLOB = {
  handoff:  ['state/handoffs', 'archive/handoffs'],
  plan:     'docs/plans',
  decision: 'docs/decisions',
  review:   'state/reviews',
};

function parseArgs(argv) {
  const opts = { dryRun: false, root: null, types: Object.keys(TYPE_TO_GLOB) };
  const args = argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--dry-run') opts.dryRun = true;
    else if (a === '--root') opts.root = args[++i];
    else if (a === '--type') opts.types = [args[++i]];
    else {
      process.stderr.write(`Unknown argument: ${a}\n`);
      process.exit(1);
    }
  }
  return opts;
}

function detectRoot(specified) {
  if (specified) return path.resolve(specified);
  try {
    return execSync('git rev-parse --show-toplevel', { encoding: 'utf8', stdio: ['pipe','pipe','pipe'] }).trim();
  } catch {
    return process.cwd();
  }
}

function normalizeOne(filePath) {
  const original = fs.readFileSync(filePath, 'utf8');
  const split = splitFrontmatter(original);
  if (!split) return null;

  const markerMatch = CONSUMED_MARKER_RE.exec(split.bodyWithLeadingNewline);
  if (!markerMatch) return null;

  const date = markerMatch[1];
  const notes = (markerMatch[2] || '').trim();

  const currentStatus = readFmField(split.fmText, 'status');
  const currentDeployment = readFmField(split.fmText, 'deployment_state');
  const currentConsumedAt = readFmField(split.fmText, 'consumed_at');
  const currentShippedIn = readFmField(split.fmText, 'shipped_in');

  const changes = [];
  let fmText = split.fmText;

  if (currentStatus && !TERMINAL_STATUS.has(currentStatus)) {
    fmText = replaceFmField(fmText, 'status', 'consumed');
    changes.push(`status: ${currentStatus} → consumed`);
  } else if (!currentStatus) {
    fmText = insertFmField(fmText, 'status', 'consumed', 'title');
    changes.push('status: (missing) → consumed');
  }

  if (currentDeployment && !TERMINAL_DEPLOYMENT.has(currentDeployment)) {
    fmText = replaceFmField(fmText, 'deployment_state', 'shipped');
    changes.push(`deployment_state: ${currentDeployment} → shipped`);
  }

  if (!currentConsumedAt) {
    fmText = insertFmField(fmText, 'consumed_at', date, 'status');
    changes.push(`consumed_at: + ${date}`);
  }

  // gate_dependency is only meaningful while deployment_state is awaiting_gate.
  // Once flipped to shipped, the field is stale noise — strip it.
  const currentGateDep = readFmField(fmText, 'gate_dependency');
  if (currentGateDep !== null) {
    fmText = removeFmField(fmText, 'gate_dependency');
    changes.push(`gate_dependency: stripped (was "${currentGateDep.slice(0, 60)}${currentGateDep.length > 60 ? '…' : ''}")`);
  }

  if (!currentShippedIn && notes) {
    // Review: C4b — gate the write through the same shape guard schema.js
    // enforces at validate-time. A live unvalidated write path here previously
    // inserted free-text `notes` straight into shipped_in with zero shape
    // check; refuse (do not write) a non-conforming value instead.
    if (SHIPPED_IN_RE.test(notes)) {
      fmText = insertFmField(fmText, 'shipped_in', notes, 'consumed_at');
      changes.push(`shipped_in: + ${notes.slice(0, 60)}${notes.length > 60 ? '…' : ''}`);
    } else {
      changes.push(`shipped_in: refused — marker notes "${notes.slice(0, 60)}${notes.length > 60 ? '…' : ''}" do not match a commit SHA or the substantively-shipped-no-commit:<YYYY-MM-DD> token; not written`);
    }
  }

  if (changes.length === 0) return null;

  const fmTextNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmTextNormalized}---${split.bodyWithLeadingNewline}`;
  return { rebuilt, changes };
}

function walkDir(absDir) {
  if (!fs.existsSync(absDir)) return [];
  const stat = fs.statSync(absDir);
  if (!stat.isDirectory()) return [];
  // Depth-1 recursion: top-level *.md (flat handoffs + no-date install batons)
  // AND one level into month-subdirs (archive/handoffs/YYYY-MM/*.md, added by the
  // 2026-06-18 month-foldering migration). state/handoffs and the plan/decision/
  // review dirs are flat, so the subdir descent is a harmless no-op there.
  const out = [];
  for (const f of fs.readdirSync(absDir)) {
    const full = path.join(absDir, f);
    let st;
    try { st = fs.statSync(full); } catch { continue; }
    if (st.isDirectory()) {
      for (const sub of fs.readdirSync(full)) {
        if (sub.endsWith('.md')) out.push(path.join(full, sub));
      }
    } else if (f.endsWith('.md')) {
      out.push(full);
    }
  }
  return out;
}

/**
 * getTrackedFiles — returns the set of git-tracked file paths (absolute) in a
 * given directory. Falls back to returning all files (no filter) when git is
 * unavailable, since detectRoot() already fell back to cwd.
 *
 * Review: the Staff Engineer F5 — gate walkDir results on git ls-files so untracked drafts
 * with a consumed-marker stub are not silently rewritten.
 */
function getTrackedFiles(absDir, root) {
  try {
    const relDir = path.relative(root, absDir).replace(/\\/g, '/');
    const out = execSync(`git ls-files "${relDir}"`, {
      encoding: 'utf8',
      cwd: root,
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
    if (!out) return new Set();
    return new Set(
      out.split('\n').map(f => path.resolve(root, f))
    );
  } catch {
    // git unavailable — no filter applied (detectRoot already fell back to cwd)
    return null;
  }
}

function main() {
  const opts = parseArgs(process.argv);
  const root = detectRoot(opts.root);
  const results = [];

  for (const type of opts.types) {
    const globs = Array.isArray(TYPE_TO_GLOB[type]) ? TYPE_TO_GLOB[type] : [TYPE_TO_GLOB[type]];
    for (const glob of globs) {
      const dir = path.join(root, glob);
      const tracked = getTrackedFiles(dir, root);
      for (const file of walkDir(dir)) {
        // Review: the Staff Engineer F5 — skip untracked files silently (tracked===null means
        // git is unavailable, so we process all files as a fallback).
        if (tracked !== null && !tracked.has(file)) continue;
        let out;
        try {
          out = normalizeOne(file);
        } catch (err) {
          // Review: the Staff Engineer F1 — block-scalar field detected; fail loud with filename.
          process.stderr.write(`ERROR ${path.relative(root, file).replace(/\\/g, '/')}: ${err.message}\n`);
          process.exitCode = 1;
          continue;
        }
        if (!out) continue;
        results.push({ file: path.relative(root, file).replace(/\\/g, '/'), changes: out.changes });
        if (!opts.dryRun) {
          fs.writeFileSync(file, out.rebuilt, 'utf8');
        }
      }
    }
  }

  if (results.length === 0) {
    process.stderr.write('No drift between body markers and frontmatter.\n');
    return;
  }

  const verb = opts.dryRun ? 'Would update' : 'Updated';
  for (const r of results) {
    process.stdout.write(`${verb} ${r.file}\n`);
    for (const c of r.changes) process.stdout.write(`  ${c}\n`);
  }
  process.stdout.write(`\n${verb.toLowerCase()} ${results.length} file(s).\n`);
}

if (require.main === module) main();

module.exports = { normalizeOne, serializeYamlScalar };
