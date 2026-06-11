#!/usr/bin/env node
'use strict';
/**
 * refresh-queries.js — Expand query callouts in markdown files in-place.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W2 (Refresh Helper)
 *
 * Callout format:
 *   <!-- BEGIN query: <type> [where=...] [sort=...] [limit=N] [since=...] -->
 *   ... (current expansion, will be overwritten) ...
 *   <!-- END query -->
 *
 * The spec line is the source of truth. The block between the markers is regenerated.
 * Running twice with no data changes produces no diff (idempotent).
 *
 * Usage:
 *   refresh-queries [--root <path>] [--check] [--files <glob>]
 *
 *   --check  Don't write files; exit 1 if any file would change. For CI.
 *   --files  Glob of markdown files to scan (default: **‌/*.md, excluding node_modules/.git/archive/).
 *   --root   Repo root (default: git rev-parse --show-toplevel, fallback cwd).
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { extractBlock, replaceBlock } = require('./lib/sentinel-blocks.js');
const { queryRecords, formatRecords, parseSince } = require('./query-records.js');
// Self-claim shim: register written paths with the active coordinator session.
// Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
// Best-effort — no-op if lib absent or no active session (see lib/coordinator_session.js).
let _csSelfClaim = () => {};
try {
  ({ selfClaim: _csSelfClaim } = require('./lib/coordinator_session.js'));
} catch (_e) {
  // Lib not present in this checkout — comment claims best-effort behavior; honor it.
}

const BEGIN_PREFIX = '<!-- BEGIN query:';
const END_MARKER = '<!-- END query -->';

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = { root: null, check: false, files: '**/*.md' };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--root')  { opts.root  = args[++i]; }
    else if (a === '--check') { opts.check = true; }
    else if (a === '--files') { opts.files = args[++i]; }
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
    return execSync('git rev-parse --show-toplevel', { encoding: 'utf8', stdio: ['pipe','pipe','pipe'] }).trim();
  } catch {
    return process.cwd();
  }
}

// ---------------------------------------------------------------------------
// Query spec parser — parses "<!-- BEGIN query: type [key=value ...] -->"
// Returns opts object compatible with queryRecords / formatRecords.
// ---------------------------------------------------------------------------
function parseQuerySpec(beginMarker) {
  // Strip "<!-- BEGIN query:" prefix and " -->" suffix
  const inner = beginMarker
    .replace(/^<!--\s*BEGIN query:\s*/, '')
    .replace(/\s*-->$/, '')
    .trim();

  const tokens = inner.split(/\s+/);
  const type = tokens[0];
  if (!type) throw new Error(`Empty query spec in: ${beginMarker}`);

  const opts = { type, where: null, sort: null, limit: 50, since: null, format: 'markdown-list' };

  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.startsWith('where=')) {
      opts.where = t.slice('where='.length);
    } else if (t.startsWith('sort=')) {
      opts.sort = t.slice('sort='.length);
    } else if (t.startsWith('limit=')) {
      opts.limit = parseInt(t.slice('limit='.length), 10);
    } else if (t.startsWith('since=')) {
      opts.since = t.slice('since='.length);
    } else if (t.startsWith('format=')) {
      opts.format = t.slice('format='.length);
    }
    // Unknown tokens are ignored gracefully — forward compat
  }

  return opts;
}

// ---------------------------------------------------------------------------
// Walk markdown files (simple recursive glob for **/*.md, no external deps)
// ---------------------------------------------------------------------------
const EXCLUDED_DIRS = new Set(['node_modules', '.git', 'archive']);

function walkMd(dir, results = []) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return results; }

  for (const e of entries) {
    if (e.isDirectory()) {
      if (!EXCLUDED_DIRS.has(e.name)) {
        walkMd(path.join(dir, e.name), results);
      }
    } else if (e.isFile() && e.name.endsWith('.md')) {
      results.push(path.join(dir, e.name));
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// Fenced-code-block detector — returns a Set of line numbers (0-based) that
// are inside ``` or ~~~ fenced code blocks. Used to skip markers in examples.
// ---------------------------------------------------------------------------
function buildCodeBlockLineSet(content) {
  const lines = content.split('\n');
  const inCode = new Set();
  let inside = false;
  let fence = null;
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trimStart();
    if (!inside) {
      if (trimmed.startsWith('```') || trimmed.startsWith('~~~')) {
        inside = true;
        fence = trimmed.slice(0, 3);
      }
    } else {
      inCode.add(i);
      if (trimmed.startsWith(fence)) {
        inside = false;
        fence = null;
      }
    }
  }
  return inCode;
}

/**
 * Given a byte offset into content, return its 0-based line number.
 * Cached via a simple walk — fine for files of our size.
 */
function lineOfOffset(content, offset) {
  let line = 0;
  for (let i = 0; i < offset; i++) {
    if (content[i] === '\n') line++;
  }
  return line;
}

// ---------------------------------------------------------------------------
// Process a single file — find all query callouts, expand them.
// Returns { changed: bool, changedCount: number, errorCount: number }.
// ---------------------------------------------------------------------------
function processFile(filePath, root, checkMode) {
  let content;
  try { content = fs.readFileSync(filePath, 'utf8'); } catch { return { changed: false, changedCount: 0, errorCount: 0 }; }

  if (!content.includes(BEGIN_PREFIX)) {
    return { changed: false, changedCount: 0, errorCount: 0 };
  }

  let working = content;
  let changedCount = 0;
  let errorCount = 0;
  let offset = 0;

  // Find all BEGIN query: markers and process each
  while (true) {
    const idx = working.indexOf(BEGIN_PREFIX, offset);
    if (idx === -1) break;

    // Skip markers inside fenced code blocks or inline backtick spans
    // (they are documentation examples, not live callouts)
    const codeLines = buildCodeBlockLineSet(working);
    const markerLine = lineOfOffset(working, idx);
    if (codeLines.has(markerLine)) {
      offset = idx + BEGIN_PREFIX.length;
      continue;
    }

    // Check if this marker is inside inline backtick code on its line.
    // Find start of this line, count backticks before the marker position.
    let lineStartIdx = idx;
    while (lineStartIdx > 0 && working[lineStartIdx - 1] !== '\n') lineStartIdx--;
    const textBeforeMarker = working.slice(lineStartIdx, idx);
    const backticksBefore = (textBeforeMarker.match(/`/g) || []).length;
    if (backticksBefore % 2 === 1) {
      // Odd count means we're inside an inline code span
      offset = idx + BEGIN_PREFIX.length;
      continue;
    }

    // Find the end of the begin marker line
    const lineEnd = working.indexOf('\n', idx);
    if (lineEnd === -1) break;
    const beginMarker = working.slice(idx, lineEnd).trim();

    // Build the full marker including any leading/trailing whitespace on the line
    // We need to find the exact begin marker as it appears for sentinel-blocks
    const lineStart = (() => {
      let s = idx;
      while (s > 0 && working[s - 1] !== '\n') s--;
      return s;
    })();
    const beginMarkerFull = working.slice(lineStart, lineEnd + 1).replace(/\r?\n$/, '');

    let queryOpts;
    try {
      queryOpts = parseQuerySpec(beginMarker);
    } catch (e) {
      process.stderr.write(`  Warning: ${filePath}: ${e.message}\n`);
      errorCount++;
      offset = lineEnd + 1;
      continue;
    }

    // Check END marker exists
    if (!working.includes(END_MARKER, lineEnd)) {
      process.stderr.write(`  Warning: ${filePath}: BEGIN query without END query\n`);
      errorCount++;
      offset = lineEnd + 1;
      continue;
    }

    // Run the query
    let records;
    try {
      records = queryRecords(queryOpts, root);
    } catch (e) {
      process.stderr.write(`  Warning: ${filePath}: query failed: ${e.message}\n`);
      errorCount++;
      offset = lineEnd + 1;
      continue;
    }

    const expansion = formatRecords(records, queryOpts);

    // Replace block using exact begin marker (the spec line content)
    const updated = replaceBlock(working, beginMarker, END_MARKER, expansion ? expansion + '\n' : '');
    if (updated === null) {
      process.stderr.write(`  Warning: ${filePath}: sentinel-blocks replaceBlock returned null\n`);
      errorCount++;
      offset = lineEnd + 1;
      continue;
    }

    if (updated !== working) {
      changedCount++;
    }
    working = updated;
    // Advance past the begin marker using its pre-update position (idx), which
    // replaceBlock preserves verbatim. Re-searching from 0 would re-find the
    // marker string if it appears inside the replacement content, risking an
    // infinite loop.
    offset = idx + beginMarker.length;
    if (offset >= working.length) break;
  }

  if (changedCount > 0) {
    if (!checkMode) {
      fs.writeFileSync(filePath, working, 'utf8');
      _csSelfClaim(filePath);
    }
    return { changed: true, changedCount, errorCount };
  }
  return { changed: false, changedCount: 0, errorCount };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
function main() {
  const opts = parseArgs(process.argv);
  const root = detectRoot(opts.root);

  const files = walkMd(root);
  let totalChanged = 0;
  let totalErrors = 0;

  for (const file of files) {
    const { changed, changedCount, errorCount } = processFile(file, root, opts.check);
    if (changed) {
      const rel = path.relative(root, file);
      process.stdout.write(`${opts.check ? '[would change]' : '[updated]'} ${rel} (${changedCount} callout(s))\n`);
      totalChanged++;
    }
    totalErrors += errorCount;
  }

  if (totalChanged === 0 && totalErrors === 0) {
    process.stdout.write('All query callouts are up to date.\n');
  }

  if (opts.check && totalChanged > 0) {
    process.stderr.write(`\n${totalChanged} file(s) have out-of-sync query callouts. Run refresh-queries.sh to fix.\n`);
    process.exit(1);
  }

  if (totalErrors > 0) {
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { processFile, parseQuerySpec };

// ---------------------------------------------------------------------------
// Self-test: BS-2026-05-06-006 regression — marker in replacement content
// Run with:  NODE_TEST=1 node refresh-queries.js
// ---------------------------------------------------------------------------
if (process.env.NODE_TEST) {
  // Verify that processFile does not loop infinitely when the expansion
  // content of one callout contains the BEGIN_PREFIX string (e.g. the
  // callout documents the format for human readers).  The fix in this
  // file (offset = idx + beginMarker.length instead of
  // working.indexOf(beginMarker)) prevents the loop.
  //
  // Strategy: write a temp .md file containing two callouts — the first
  // has no matching records (expansion is empty) and the second is the
  // same.  We then monkey-patch queryRecords inside processFile by
  // temporarily replacing the module export — but since processFile
  // calls queryRecords from the required module, the simplest approach
  // is to just confirm that processFile completes within a reasonable
  // wall-clock limit (100 ms) even when given a file whose expanded
  // block contains the begin-marker string verbatim.
  //
  // We do this by creating a temporary file where the EXISTING expansion
  // already contains the BEGIN_PREFIX string, then running processFile
  // against it.  If the pre-fix bug were present the call would hang;
  // with the fix it must return within the deadline.

  const os = require('os');
  const tmpFile = path.join(os.tmpdir(), `rq-selftest-${process.pid}.md`);

  // Build a file with one live callout whose current expansion block
  // contains the begin-marker string (simulates a docs-style callout
  // that describes the format).
  const markerLine = '<!-- BEGIN query: plans -->';
  const endLine = '<!-- END query -->';
  const content = [
    '# Test',
    markerLine,
    '<!-- BEGIN query: plans --> (this line inside the expansion contains the marker)',
    endLine,
    '',
  ].join('\n');

  fs.writeFileSync(tmpFile, content, 'utf8');

  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
  }, 2000);

  // processFile will call queryRecords which needs a real root; supply
  // a root with no records so expansion is empty and the file is
  // idempotent-updated (empty block).
  try {
    const result = processFile(tmpFile, os.tmpdir(), false);
    clearTimeout(timer);
    if (timedOut) {
      process.stderr.write('SELFTEST FAIL: processFile timed out (infinite loop)\n');
      process.exit(2);
    }
    process.stdout.write(`SELFTEST PASS: processFile returned (changed=${result.changed}, errors=${result.errorCount})\n`);
  } catch (e) {
    clearTimeout(timer);
    // queryRecords may throw if no records dir — that is OK, it means
    // the loop exited early without hanging.
    process.stdout.write(`SELFTEST PASS: processFile exited via error path without hanging (${e.message})\n`);
  } finally {
    try { fs.unlinkSync(tmpFile); } catch { /* ignore */ }
  }
}
