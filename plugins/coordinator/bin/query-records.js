#!/usr/bin/env node
'use strict';
/**
 * query-records.js — Frontmatter-indexed query CLI for coordinator tracked records.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W2 (Query Tool)
 *
 * Usage:
 *   query-records --type <handoff|decision|plan|review|worker-run|lesson>
 *                 [--where "<expr>"]
 *                 [--sort "<field>|-<field>"]
 *                 [--limit N]
 *                 [--since "Nd"|"Nw"|"Nm"|"YYYY-MM-DD"]
 *                 [--root <path>]
 *                 [--format markdown-list|json|paths]
 *
 * --where expression syntax (single-level AND conjunctions only, no OR, no parens):
 *   field=value, field!=value, field in (a,b,c), field<value, field>value,
 *   field<=value, field>=value
 *   Expressions may be joined with " AND " or " and ".
 *
 * --since 14d is sugar for created>=<today minus 14d>.
 *   Accepts: Nd (days), Nw (weeks), Nm (months≈30d), or YYYY-MM-DD.
 *
 * Lesson type is special: parses tasks/lessons.md entries.
 *   --where "tier=universal" matches entries tagged [universal].
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { loadSchemas, parseFrontmatter } = require('./lib/schema.js');

// ---------------------------------------------------------------------------
// Schema-to-glob mapping (must match schema applies_to)
// ---------------------------------------------------------------------------
const TYPE_TO_GLOB = {
  handoff:    'tasks/handoffs/*.md',
  decision:   'docs/decisions/*.md',
  plan:       'docs/plans/*.md',
  review:     'tasks/reviews/*.md',
  'worker-run': 'tasks/worker-runs/*.md',
  lesson:     'tasks/lessons.md', // special
};

// Markdown-list format columns per type (field name → label)
const TYPE_DISPLAY = {
  handoff:    (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'}`,
  decision:   (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'}`,
  plan:       (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'}`,
  review:     (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — reviewer: ${fm.reviewer || '?'}, findings: ${fm.findings_count ?? '?'}`,
  'worker-run': (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — worker: ${fm.worker || '?'}, findings: ${fm.findings_count ?? '?'}`,
  lesson:     (p, fm) => `- **${fm.title || p}** [${fm.tier || 'untagged'}]`,
};

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = argv.slice(2);
  const opts = {
    type: null,
    where: null,
    sort: null,
    limit: 50,
    since: null,
    root: null,
    format: 'markdown-list',
  };

  // Review: patrik R2 finding 4 — normalize --key=value form to --key value before dispatch.
  // Operators (hand invocation) naturally reach for --sort=-created; the callout consumer
  // builds space-separated args, so production paths were unaffected. Both forms now work.
  const normalizedArgs = [];
  for (const a of args) {
    if (a.startsWith('--') && a.includes('=')) {
      const eqIdx = a.indexOf('=');
      normalizedArgs.push(a.slice(0, eqIdx), a.slice(eqIdx + 1));
    } else {
      normalizedArgs.push(a);
    }
  }

  for (let i = 0; i < normalizedArgs.length; i++) {
    const a = normalizedArgs[i];
    if (a === '--type')   { opts.type   = normalizedArgs[++i]; }
    else if (a === '--where')  { opts.where  = normalizedArgs[++i]; }
    else if (a === '--sort')   { opts.sort   = normalizedArgs[++i]; }
    else if (a === '--limit')  { opts.limit  = parseInt(normalizedArgs[++i], 10); }
    else if (a === '--since')  { opts.since  = normalizedArgs[++i]; }
    else if (a === '--root')   { opts.root   = normalizedArgs[++i]; }
    else if (a === '--format') { opts.format = normalizedArgs[++i]; }
    else {
      process.stderr.write(`Unknown argument: ${a}\n`);
      process.exit(1);
    }
  }

  if (!opts.type) {
    process.stderr.write('--type is required\n');
    process.exit(1);
  }
  if (!TYPE_TO_GLOB[opts.type]) {
    process.stderr.write(`Unknown type: ${opts.type}. Valid: ${Object.keys(TYPE_TO_GLOB).join(', ')}\n`);
    process.exit(1);
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
// Since helper
// ---------------------------------------------------------------------------
function parseSince(since) {
  if (!since) return null;
  const isoRe = /^\d{4}-\d{2}-\d{2}$/;
  if (isoRe.test(since)) return since;

  const relRe = /^(\d+)(d|w|m)$/;
  const m = relRe.exec(since);
  if (!m) {
    process.stderr.write(`Invalid --since value: ${since}\n`);
    process.exit(1);
  }
  const n = parseInt(m[1], 10);
  const unit = m[2];
  const days = unit === 'd' ? n : unit === 'w' ? n * 7 : n * 30;
  const dt = new Date();
  dt.setDate(dt.getDate() - days);
  return dt.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// Where expression parser
// ---------------------------------------------------------------------------
const OPS = ['!=', '<=', '>=', '<', '>', '=', ' in '];

function parseWhereExpr(expr) {
  // Split on " AND " or " and " (case-insensitive), outside parens
  const clauses = expr.split(/\s+and\s+/i).map(s => s.trim()).filter(Boolean);
  return clauses.map(parseClause);
}

function parseClause(clause) {
  // Check "in" operator first (field in (a,b,c))
  const inRe = /^(\w+)\s+in\s*\(([^)]*)\)$/i;
  const inM = inRe.exec(clause);
  if (inM) {
    const values = inM[2].split(',').map(s => s.trim());
    return { field: inM[1], op: 'in', values };
  }

  for (const op of ['!=', '<=', '>=', '<', '>', '=']) {
    const idx = clause.indexOf(op);
    if (idx !== -1) {
      const field = clause.slice(0, idx).trim();
      const value = clause.slice(idx + op.length).trim();
      return { field, op, value };
    }
  }

  process.stderr.write(`Cannot parse where clause: "${clause}"\n`);
  process.exit(1);
}

function compareValues(a, b) {
  // Try numeric comparison first
  const na = Number(a), nb = Number(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  // Fall back to string comparison (handles ISO dates lexicographically)
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

function matchesClause(fm, clause) {
  const rawVal = fm[clause.field];
  const fmVal = rawVal === undefined || rawVal === null ? '' : String(rawVal);

  switch (clause.op) {
    case '=':   return fmVal === clause.value;
    case '!=':  return fmVal !== clause.value;
    case 'in':  return clause.values.includes(fmVal);
    case '<':   return compareValues(fmVal, clause.value) < 0;
    case '>':   return compareValues(fmVal, clause.value) > 0;
    case '<=':  return compareValues(fmVal, clause.value) <= 0;
    case '>=':  return compareValues(fmVal, clause.value) >= 0;
    default:    return false;
  }
}

function matchesWhere(fm, clauses) {
  return clauses.every(c => matchesClause(fm, c));
}

// ---------------------------------------------------------------------------
// Glob file walker (no external deps)
// ---------------------------------------------------------------------------
function walkGlob(root, globPattern) {
  // Convert glob to a simple two-part: prefix dir + filename pattern
  // Our globs are always "some/path/*.md" — handle that form.
  const normalised = globPattern.replace(/\\/g, '/');
  const parts = normalised.split('/');
  const filePattern = parts[parts.length - 1];
  const dirParts = parts.slice(0, -1);

  const dir = path.join(root, ...dirParts);
  if (!fs.existsSync(dir)) return [];

  const stat = fs.statSync(dir);
  if (!stat.isDirectory()) {
    // It's a file path directly (e.g., tasks/lessons.md)
    return fs.existsSync(path.join(root, normalised)) ? [path.join(root, normalised)] : [];
  }

  const fileRe = filePatternToRegex(filePattern);
  return fs.readdirSync(dir)
    .filter(f => fileRe.test(f))
    .map(f => path.join(dir, f));
}

function filePatternToRegex(pattern) {
  let re = '';
  for (const c of pattern) {
    if (c === '*') re += '[^/]*';
    else if (c === '?') re += '[^/]';
    else if ('.+^${}()|[]\\'.includes(c)) re += '\\' + c;
    else re += c;
  }
  return new RegExp('^' + re + '$');
}

// ---------------------------------------------------------------------------
// Lesson parser
// ---------------------------------------------------------------------------
/**
 * Parse tasks/lessons.md into a list of record objects.
 * Each entry is a bold-title line followed by body text until the next entry.
 * Returns [{title, tier, body, path}].
 */
function parseLessonsFile(filePath) {
  if (!fs.existsSync(filePath)) return [];
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split('\n');
  const records = [];

  const entryRe = /^\s*[-*]?\s*\*\*([^*]+)\*\*/;
  const tagRe = /\[([^\]]+)\]/g;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m = entryRe.exec(line);
    if (!m) continue;

    const rawTitle = m[1].trim();

    // Extract tier tag from the line
    const tags = [];
    let tm;
    tagRe.lastIndex = 0;
    while ((tm = tagRe.exec(line)) !== null) {
      tags.push(tm[1]);
    }
    // Remove tags from title
    const title = rawTitle;
    const tier = tags.length > 0 ? tags[0] : null;

    // Slug for fragment links
    const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

    records.push({
      title,
      tier,
      path: filePath + '#' + slug,
      frontmatter: { title, tier: tier || 'untagged', created: null },
    });
  }

  return records;
}

// ---------------------------------------------------------------------------
// Main query function (exported for use by refresh-queries)
// ---------------------------------------------------------------------------
function queryRecords(opts, root) {
  const glob = TYPE_TO_GLOB[opts.type];

  let records;

  if (opts.type === 'lesson') {
    const lessonsPath = path.join(root, 'tasks', 'lessons.md');
    const parsed = parseLessonsFile(lessonsPath);
    records = parsed.map(r => ({ path: r.path, frontmatter: r.frontmatter }));
  } else {
    const files = walkGlob(root, glob);
    records = [];
    for (const file of files) {
      let content;
      try { content = fs.readFileSync(file, 'utf8'); } catch { continue; }
      const { frontmatter } = parseFrontmatter(content);
      if (!frontmatter) continue;
      const relPath = path.relative(root, file).replace(/\\/g, '/');
      records.push({ path: relPath, frontmatter });
    }
  }

  // Apply --since as created>= filter
  const since = parseSince(opts.since);
  if (since) {
    records = records.filter(r => {
      const c = r.frontmatter.created;
      if (!c) return false;
      return String(c) >= since;
    });
  }

  // Apply --where filter
  let whereClauses = [];
  if (opts.where) {
    whereClauses = parseWhereExpr(opts.where);
    records = records.filter(r => matchesWhere(r.frontmatter, whereClauses));
  }

  // Apply --sort
  if (opts.sort) {
    const desc = opts.sort.startsWith('-');
    const field = desc ? opts.sort.slice(1) : opts.sort;
    records.sort((a, b) => {
      const av = a.frontmatter[field] ?? '';
      const bv = b.frontmatter[field] ?? '';
      const cmp = compareValues(String(av), String(bv));
      return desc ? -cmp : cmp;
    });
  }

  // Apply --limit
  if (opts.limit && opts.limit > 0) {
    records = records.slice(0, opts.limit);
  }

  return records;
}

// ---------------------------------------------------------------------------
// Output formatting
// ---------------------------------------------------------------------------
function formatRecords(records, opts) {
  switch (opts.format) {
    case 'json':
      return JSON.stringify(records, null, 2);
    case 'paths':
      return records.map(r => r.path).join('\n');
    case 'markdown-list':
    default: {
      const displayFn = TYPE_DISPLAY[opts.type] || ((p, fm) => `- [${fm.title || p}](${p})`);
      return records.map(r => displayFn(r.path, r.frontmatter)).join('\n');
    }
  }
}

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------
if (require.main === module) {
  const opts = parseArgs(process.argv);
  const root = detectRoot(opts.root);

  const records = queryRecords(opts, root);
  const output = formatRecords(records, opts);

  if (output) {
    process.stdout.write(output + '\n');
  }
}

module.exports = { queryRecords, formatRecords, parseSince, parseWhereExpr };
