#!/usr/bin/env node
'use strict';
/**
 * normalize-handoff-frontmatter.js — backfill and canonicalize active handoff frontmatter.
 *
 * Spec backlink: docs/plans/2026-05-29-handoff-tracker-renderer.md § Chunk 5
 *
 * Operates exclusively on `tasks/handoffs/*.md` in the repo root (NEVER
 * `archive/handoffs/` — archived files are immutable history).
 *
 * Normalizations applied:
 *   - `created` → strip any ISO time component; keep bare `YYYY-MM-DD`
 *   - `pickup_ready: "true"` / `pickup_ready: "false"` → unquoted bare bool
 *   - `category:` backfilled as `uncategorized` when absent (optional keyword
 *     heuristic applied — see matchCategory)
 *   - `summary:` backfilled from the H1/title (truncated to ≤120 chars) when absent
 *
 * IMPORTANT: only the four field names above are touched. Key order and all
 * other frontmatter content are preserved byte-for-byte.
 *
 * Usage:
 *   normalize-handoff-frontmatter.js [--write] [--root <path>]
 *
 * --write applies changes to disk (default is dry-run: print diff summary, no writes).
 * Exit codes: 0 always (non-empty stdout summarises changes).
 */

const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ---------------------------------------------------------------------------
// Frontmatter text helpers (minimal regex-based; preserves key order)
// ---------------------------------------------------------------------------

/**
 * splitFrontmatter — split a file's content into YAML frontmatter text and body.
 * Returns null when the file has no valid frontmatter block.
 *
 * Intentionally kept as a simple text split (not a full YAML parse) so we can
 * reconstruct the file with byte-identical whitespace outside the changed fields.
 */
function splitFrontmatter(content) {
  if (!content.startsWith('---')) return null;
  const afterFirst = content.slice(3);
  const firstNewline = afterFirst.indexOf('\n');
  if (firstNewline === -1) return null;
  const rest = afterFirst.slice(firstNewline + 1);
  // [ \t]* — NOT \s* which would eat body blank lines.
  const closeRe = /^---[ \t]*$/m;
  const closeMatch = closeRe.exec(rest);
  if (!closeMatch) return null;
  const fmText = rest.slice(0, closeMatch.index);
  // Everything after `---` (including the newline that follows it).
  const bodyWithLeadingNewline = rest.slice(closeMatch.index + closeMatch[0].length);
  return { fmText, bodyWithLeadingNewline };
}

/**
 * readFmField — return the raw value string for `key:` in frontmatter text,
 * or null when the key is absent.
 */
function readFmField(fmText, key) {
  const re = new RegExp(`^${key}:\\s*(.*?)\\s*$`, 'm');
  const m = re.exec(fmText);
  return m ? m[1].trim() : null;
}

/**
 * replaceFmField — replace the value of an existing `key:` line in frontmatter text.
 * Returns the updated frontmatter text.
 *
 * Negative-spec: does NOT insert a new line when the key is absent — call
 * insertFmField for that.
 */
function replaceFmField(fmText, key, value) {
  const re = new RegExp(`^(${key}:\\s*).*$`, 'm');
  return fmText.replace(re, `$1${serializeYamlScalar(value)}`);
}

/**
 * insertFmField — append `key: value` to the end of the frontmatter block.
 * Used when the key is absent and we need to add it.
 */
function insertFmField(fmText, key, value) {
  const trimmed = fmText.replace(/\s+$/, '');
  return `${trimmed}\n${key}: ${serializeYamlScalar(value)}\n`;
}

/**
 * serializeYamlScalar — single-quote a value that contains YAML structural
 * characters; pass through safe values unquoted.
 *
 * Negative-spec: does NOT handle multi-line values; frontmatter fields
 * normalised by this script are all single-line scalars.
 */
function serializeYamlScalar(value) {
  const needsQuoting = /[#:{}\[\],&*!|>"'%@`]/.test(value) ||
                       value.startsWith('-') ||
                       value.startsWith('?') ||
                       value.startsWith(' ');
  if (!needsQuoting) return value;
  return `'${value.replace(/'/g, "''")}'`;
}

// ---------------------------------------------------------------------------
// Category heuristic
// ---------------------------------------------------------------------------

/**
 * matchCategory — best-effort keyword match on a handoff title.
 * Returns one of the schema-valid category enum values, or 'uncategorized'
 * when no keyword fires.
 *
 * HARD CONSTRAINT: every return value MUST be a member of the category enum in
 * schemas/handoff.yaml — [roadmap, infra, bug, docs, research, refactor, uncategorized].
 * Emitting a value outside the enum makes the normalized file fail schema
 * validation (the validator enum-checks category whenever it is present).
 * Intentionally conservative — only unambiguous category signals are mapped;
 * kind/lifecycle words (spinoff, recovery, review, release) are NOT categories
 * and fall through to 'uncategorized', the safe default.
 */
function matchCategory(title) {
  const t = (title || '').toLowerCase();
  if (/\broadmap\b|\bsprint\b/.test(t))                                  return 'roadmap';
  if (/\brefactor\b|\bcleanup\b|\bconsolidat/.test(t))                   return 'refactor';
  if (/\bbug\b|\bhotfix\b|\bregression\b/.test(t))                       return 'bug';
  if (/\bresearch\b|\bspike\b|\binvestigat/.test(t))                     return 'research';
  if (/\bdoc(?:s|umentation)?\b|\bwiki\b/.test(t))                       return 'docs';
  if (/\binfra(?:structure)?\b|\binstall\b|\bhook\b|\bpipeline\b|\bci\b/.test(t)) return 'infra';
  return 'uncategorized';
}

// ---------------------------------------------------------------------------
// Per-file normalizer
// ---------------------------------------------------------------------------

/**
 * normalizeOne — compute the normalised content for a single file.
 * Returns `{ rebuilt, changes }` when drift is detected, or null when the
 * file is already clean (idempotent: second run always returns null).
 *
 * @param {string} filePath  Absolute path to the handoff file.
 * @returns {{ rebuilt: string, changes: string[] } | null}
 */
function normalizeOne(filePath) {
  const original = fs.readFileSync(filePath, 'utf8');
  const split = splitFrontmatter(original);
  if (!split) return null;

  let fmText = split.fmText;
  const changes = [];

  // ── 1. created: strip ISO time component ──────────────────────────────
  const createdRaw = readFmField(fmText, 'created');
  if (createdRaw) {
    // Matches `2026-05-28T11:16:48Z` or `2026-05-28T11:16:48` etc.
    const isoMatch = /^(\d{4}-\d{2}-\d{2})[T ]/.exec(createdRaw);
    if (isoMatch) {
      const bare = isoMatch[1];
      fmText = replaceFmField(fmText, 'created', bare);
      changes.push(`created: "${createdRaw}" → "${bare}"`);
    }
  }

  // ── 2. pickup_ready: unquote boolean strings ───────────────────────────
  const pickupRaw = readFmField(fmText, 'pickup_ready');
  if (pickupRaw !== null) {
    // Quoted `"true"` or `"false"` — strip quotes by writing the bare value.
    if (pickupRaw === '"true"' || pickupRaw === "'true'") {
      fmText = replaceFmField(fmText, 'pickup_ready', 'true');
      changes.push(`pickup_ready: ${pickupRaw} → true`);
    } else if (pickupRaw === '"false"' || pickupRaw === "'false'") {
      fmText = replaceFmField(fmText, 'pickup_ready', 'false');
      changes.push(`pickup_ready: ${pickupRaw} → false`);
    }
    // bare `true`/`false` already correct — no-op
  }

  // ── 3. category: backfill when absent ─────────────────────────────────
  const categoryRaw = readFmField(fmText, 'category');
  if (categoryRaw === null) {
    const title = readFmField(fmText, 'title') || '';
    const cat = matchCategory(title);
    fmText = insertFmField(fmText, 'category', cat);
    changes.push(`category: (absent) → ${cat}`);
  }

  // ── 4. summary: backfill when absent ──────────────────────────────────
  const summaryRaw = readFmField(fmText, 'summary');
  if (summaryRaw === null) {
    // Extract text from the first H1 in the body; fall back to `title:` field.
    let summaryText = '';
    const h1Match = /^#\s+(.+)$/m.exec(split.bodyWithLeadingNewline);
    if (h1Match) {
      summaryText = h1Match[1].trim();
    } else {
      summaryText = readFmField(fmText, 'title') || '';
    }
    // Truncate to ≤120 chars; strip inline markdown (bold, code, links).
    summaryText = summaryText
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')   // [text](url) → text
      .replace(/`([^`]+)`/g, '$1')               // `code` → code
      .replace(/\*\*([^*]+)\*\*/g, '$1')         // **bold** → bold
      .replace(/\*([^*]+)\*/g, '$1')             // *italic* → italic
      .trim();
    if (summaryText.length > 120) summaryText = summaryText.slice(0, 117) + '...';
    if (summaryText) {
      fmText = insertFmField(fmText, 'summary', summaryText);
      changes.push(`summary: (absent) → "${summaryText.slice(0, 60)}${summaryText.length > 60 ? '…' : ''}"`);
    }
  }

  if (changes.length === 0) return null;

  const fmTextNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `---\n${fmTextNormalized}---${split.bodyWithLeadingNewline}`;
  return { rebuilt, changes };
}

// ---------------------------------------------------------------------------
// CLI helpers
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  // Default: dry-run (--write must be explicit)
  const opts = { dryRun: true, root: null };
  const args = argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--write')   opts.dryRun = false;
    else if (a === '--dry-run') opts.dryRun = true;  // explicit no-op (already default)
    else if (a === '--root') opts.root = args[++i];
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
    return execSync('git rev-parse --show-toplevel', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  } catch {
    return process.cwd();
  }
}

function walkHandoffsDir(absDir) {
  // CONSTRAINT: active handoffs only — tasks/handoffs/*.md, NOT archive/handoffs/.
  // Flat glob only: no recursion into subdirectories, so tasks/handoffs/archive/
  // (the holodeck legacy pattern) is also excluded.
  if (!fs.existsSync(absDir)) return [];
  const stat = fs.statSync(absDir);
  if (!stat.isDirectory()) return [];
  return fs.readdirSync(absDir)
    .filter(f => f.endsWith('.md'))
    .map(f => path.join(absDir, f));
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

function main() {
  const opts = parseArgs(process.argv);
  const root = detectRoot(opts.root);
  const handoffsDir = path.join(root, 'tasks', 'handoffs');

  const files = walkHandoffsDir(handoffsDir);
  const results = [];

  for (const file of files) {
    let out;
    try {
      out = normalizeOne(file);
    } catch (err) {
      process.stderr.write(`ERROR ${path.relative(root, file).replace(/\\/g, '/')}: ${err.message}\n`);
      process.exitCode = 1;
      continue;
    }
    if (!out) continue;

    results.push({
      file: path.relative(root, file).replace(/\\/g, '/'),
      changes: out.changes,
    });

    if (!opts.dryRun) {
      fs.writeFileSync(file, out.rebuilt, 'utf8');
    }
  }

  if (results.length === 0) {
    process.stderr.write('No drift found in active handoffs.\n');
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

module.exports = { normalizeOne, splitFrontmatter, readFmField, replaceFmField, insertFmField, matchCategory };
