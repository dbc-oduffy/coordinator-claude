#!/usr/bin/env node
'use strict';
/**
 * query-records.js — Frontmatter-indexed query CLI for coordinator tracked records.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W2 (Query Tool)
 * Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md §Chunk6
 *
 * Usage:
 *   query-records --type <handoff|handoff-archived|decision|plan|review|lesson|handoff-ledger>
 *                 [--where "<expr>"]
 *                 [--sort "<field>|-<field>"]
 *                 [--limit N]
 *                 [--since "Nd"|"Nw"|"Nm"|"YYYY-MM-DD"]
 *                 [--older-than "Nd"|"Nw"|"Nm"|"YYYY-MM-DD"]
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
 * --older-than 14d is the inverse: created<<today minus 14d>.
 *   Use for stale-flag queries like "awaiting_gate items older than 14 days."
 *   Same parser as --since (Nd/Nw/Nm/YYYY-MM-DD).
 *
 * Lesson type is special: parses state/lessons.md entries.
 *   --where "tier=universal" matches entries tagged [universal].
 *
 * Inline consumed marker: bodies containing `<!-- consumed: YYYY-MM-DD [notes] -->`
 * are normalized as if frontmatter set `status: consumed` and
 * `deployment_state: shipped` (with `consumed_at` / `shipped_in` derived from
 * the marker). Existing terminal frontmatter values (`superseded`, `abandoned`)
 * are preserved.
 *
 * handoff-ledger synthetic type: parses `## Session Ledger` markdown table blocks
 * from handoff bodies (both state/handoffs/*.md and archive/handoffs/**) and
 * returns one synthetic record per block. A handoff with N Session Ledger blocks
 * yields N records, disambiguated by path fragment (#ledger-0, #ledger-1, ...).
 * All standard query expressions (--where, --since, --sort) apply to synthetic
 * record fields (agent_dispatches, opus_dispatches, em_tokens, tshirt, commits,
 * session_id, created).
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { loadSchemas, parseFrontmatter, _parseYaml } = require('./lib/schema.js');
const { TERMINAL_STATUS, TERMINAL_DEPLOYMENT, CONSUMED_MARKER_RE } = require('./lib/consumed-marker.js');
// Review: Patrik F3 — import shared constants/regex so read-time and write-time
// paths (normalize-consumed-frontmatter.js) stay greppably aligned.
// Review: Patrik F4 — CONSUMED_MARKER_RE now uses lazy `(.*?)\s*-->` capture so
// `>` characters in notes (e.g. "shipped via PR > main") are captured correctly.

// ---------------------------------------------------------------------------
// Schema-to-glob mapping (must match schema applies_to)
// ---------------------------------------------------------------------------
const TYPE_TO_GLOB = {
  handoff:            'state/handoffs/*.md',
  'handoff-archived': 'archive/handoffs/*.md',  // post-/pickup home; used by /distill enumeration
  decision:           'docs/decisions/*.md',
  plan:               'docs/plans/*.md',
  review:             'state/reviews/*.md',
  lesson:             'state/lessons.md', // special
  completion:         'archive/completed/*/*.md', // per-entry completion log (Phase 1)
  // handoff-ledger: synthetic type — parses ## Session Ledger table blocks from handoff bodies.
  // Globs BOTH live and archived handoff directories; parser runs instead of standard frontmatter path.
  // archive glob: archive/handoffs/**/*.md (added in queryRecords())
  // Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md §Chunk6
  'handoff-ledger':   'state/handoffs/*.md', // primary glob; archive glob added in queryRecords()
  // cross-repo-memo: glob deliberately differs from schema's applies_to bracket form
  // `cross-repo/inbox/[0-9]*.md` — filePatternToRegex (this file, ~line 350) escapes `[`/`]` as
  // literals so a bracket class matches nothing here (divergent from schema.js globToRegex which
  // passes brackets through). Memo-shape guard (from+to present) replaces the bracket-class
  // filename filter.
  'cross-repo-memo':  'cross-repo/inbox/*.md',
  // Directory-form queue types (per-entry YAML files, no --- delimiters).
  // Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C6
  debt:               'state/debt-backlog/*.yaml',
  bug:                'state/bug-backlog/*.yaml',
  improvement:        'state/improvement-queue/*.yaml',
};

// Markdown-list format columns per type (field name → label)
const TYPE_DISPLAY = {
  handoff:           (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.deployment_state || fm.status || 'unknown'}`,
  'handoff-archived':(p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'}${fm.shipped_in ? ` (shipped: ${fm.shipped_in})` : ''}`,
  decision:          (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'}`,
  plan:              (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'}`,
  review:            (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — reviewer: ${fm.reviewer || '?'}, findings: ${fm.findings_count ?? '?'}`,
  lesson:            (p, fm) => `- **${fm.title || p}** [${fm.tier || 'untagged'}]`,
  completion:        (p, fm) => `- **${fm.title}** [${fm.nature}] (chain: ${fm.chain || 'none'}) — ${fm.commits?.join(', ') || 'no-commit'}`,
  'handoff-ledger':  (p, fm) => `- [${p}] tshirt=${fm.tshirt || '?'} agents=${fm.agent_dispatches ?? '?'} opus=${fm.opus_dispatches ?? '?'} session=${fm.session_id || '?'} created=${fm.created || '?'}`,
  'cross-repo-memo': (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'} (from ${fm.from || '?'})`,
  debt:        (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.severity || 'P?'} ${fm.status || 'unknown'} (source: ${fm.source || '?'})`,
  bug:         (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.severity || 'P?'} ${fm.status || 'unknown'} (system: ${fm.system || '?'})`,
  improvement: (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'} (target: ${fm.proposed_target || '?'})`,
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
    olderThan: null,
    root: null,
    format: 'markdown-list',
    includeUnparseable: false,
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
    else if (a === '--older-than') { opts.olderThan = normalizedArgs[++i]; }
    else if (a === '--root')   { opts.root   = normalizedArgs[++i]; }
    else if (a === '--format') { opts.format = normalizedArgs[++i]; }
    else if (a === '--include-unparseable') { opts.includeUnparseable = true; }
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

// parseOlderThan returns the cutoff date (ISO YYYY-MM-DD) for "created<cutoff".
// Same parser shape as parseSince — Nd/Nw/Nm or YYYY-MM-DD literal.
// "--older-than 14d" means: records whose `created` is strictly before <today minus 14 days>.
function parseOlderThan(olderThan) {
  if (!olderThan) return null;
  const isoRe = /^\d{4}-\d{2}-\d{2}$/;
  if (isoRe.test(olderThan)) return olderThan;

  const relRe = /^(\d+)(d|w|m)$/;
  const m = relRe.exec(olderThan);
  if (!m) {
    process.stderr.write(`Invalid --older-than value: ${olderThan}\n`);
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
/**
 * Expand a glob pattern against the filesystem rooted at `root`.
 * Handles wildcards in both directory and filename segments (e.g. archive/completed/*-/*.md).
 * Each segment is matched independently; only `*` and `?` wildcards are recognised.
 */
function walkGlob(root, globPattern) {
  const normalised = globPattern.replace(/\\/g, '/');

  // Latent-bug fix (2026-05-19): original implementation treated the glob as a
  // literal dir prefix + filename wildcard, failing silently when any intermediate
  // directory segment contained a `*` (e.g. archive/completed/*/*.md). Replaced
  // with a recursive segment-walker that handles wildcards at any path depth.
  // Fix scope: this function only; no new abstractions. Spec: Chunk 2 notes.
  const parts = normalised.split('/');
  return walkSegments(root, parts);
}

/**
 * Recursively expand glob segments against the filesystem.
 * Supports `*`, `?`, and `**` (globstar — matches zero or more path segments).
 * @param {string} base  Absolute directory to search within.
 * @param {string[]} segments  Remaining glob path segments (may contain `*`/`?`/`**`).
 * @returns {string[]} Absolute paths of matching files.
 */
function walkSegments(base, segments) {
  if (segments.length === 0) return [];
  if (!fs.existsSync(base)) return [];

  const [head, ...tail] = segments;
  const isLast = tail.length === 0;

  // Globstar `**` — matches zero or more directory levels.
  // Expands to: try zero-levels (skip `**` and continue with tail at same base),
  // then enumerate entries and recurse with `**` still in front for deeper descent.
  if (head === '**') {
    const results = [];
    // Zero-level match: skip `**` and continue matching tail at current base
    if (tail.length > 0) {
      results.push(...walkSegments(base, tail));
    }
    // One-or-more-levels: descend into each subdirectory with `**` still leading
    let entries;
    try { entries = fs.readdirSync(base); } catch { return results; }
    for (const entry of entries) {
      const next = path.join(base, entry);
      try {
        if (fs.statSync(next).isDirectory()) {
          results.push(...walkSegments(next, segments)); // keep `**` to recurse deeper
        }
      } catch { /* skip */ }
    }
    return results;
  }

  // Literal segment — fast path (guard statSync with existsSync to avoid ENOENT throw)
  if (!head.includes('*') && !head.includes('?')) {
    const next = path.join(base, head);
    if (!fs.existsSync(next)) return [];
    if (isLast) {
      try { return !fs.statSync(next).isDirectory() ? [next] : []; } catch { return []; }
    }
    try { return fs.statSync(next).isDirectory() ? walkSegments(next, tail) : []; } catch { return []; }
  }

  // Wildcard segment — enumerate directory entries that match
  const headRe = filePatternToRegex(head);
  let entries;
  try { entries = fs.readdirSync(base); } catch { return []; }

  const results = [];
  for (const entry of entries) {
    if (!headRe.test(entry)) continue;
    const next = path.join(base, entry);
    if (isLast) {
      // Last segment — must be a file
      try { if (!fs.statSync(next).isDirectory()) results.push(next); } catch { /* skip */ }
    } else {
      // Intermediate segment — must be a directory
      try { if (fs.statSync(next).isDirectory()) results.push(...walkSegments(next, tail)); } catch { /* skip */ }
    }
  }
  return results;
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
// Inline consumed-marker normalization
// ---------------------------------------------------------------------------
// Meets EMs where they are: many shipped handoffs carry `<!-- consumed: YYYY-MM-DD
// [notes] -->` in the body but their frontmatter `status` was never flipped, so
// they keep surfacing in ready_to_fire / status=active queries. Treat the body
// marker as authoritative for status/deployment_state when frontmatter lags.
// CONSUMED_MARKER_RE, TERMINAL_STATUS, TERMINAL_DEPLOYMENT imported from
// lib/consumed-marker.js (shared with normalize-consumed-frontmatter.js).

function applyConsumedMarker(frontmatter, body) {
  if (!body) return;
  const m = CONSUMED_MARKER_RE.exec(body);
  if (!m) return;
  const date = m[1];
  const notes = (m[2] || '').trim();

  if (!TERMINAL_STATUS.has(frontmatter.status)) {
    frontmatter.status = 'consumed';
  }
  if (!TERMINAL_DEPLOYMENT.has(frontmatter.deployment_state)) {
    frontmatter.deployment_state = 'shipped';
  }
  if (!frontmatter.consumed_at) frontmatter.consumed_at = date;
  if (!frontmatter.shipped_in && notes) frontmatter.shipped_in = notes;
}

// ---------------------------------------------------------------------------
// Lesson parser
// ---------------------------------------------------------------------------
/**
 * Parse state/lessons.md into a list of record objects.
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
// Handoff-ledger parser
// ---------------------------------------------------------------------------
/**
 * Parse all `## Session Ledger` table blocks from a handoff body.
 * Returns one synthetic record per block, with path fragment #ledger-N to
 * disambiguate multiple blocks in one file (Patrik F5 multi-ledger requirement).
 *
 * Session Ledger table shape (from skills/handoff/SKILL.md §Session Ledger):
 *   | Field            | Value      |
 *   |------------------|------------|
 *   | agent_dispatches | 26         |
 *   | opus_dispatches  | 4          |
 *   | em_tokens        | 482,000    |
 *   | tshirt           | L          |
 *   | commits          | abc1, def2 |
 *   | session_id       | <em_sid>   |
 *   | created          | 2026-05-19 |
 *
 * @param {string} filePath  Absolute path to the handoff file.
 * @param {string} relPath   Repo-relative path (for record path field).
 * @param {string} content   Full file content.
 * @returns {{ path: string, frontmatter: object }[]}
 */
function parseHandoffLedger(filePath, relPath, content) {
  const records = [];
  const lines = content.split('\n');

  // State machine: scan for "## Session Ledger" headings, then parse the
  // table rows that follow until a blank line or next heading.
  let blockIdx = -1;
  let inTable = false;
  let currentFields = null;

  const flushBlock = () => {
    if (currentFields && Object.keys(currentFields).length > 0) {
      blockIdx++;
      // Normalise numeric string fields to their raw string value (matchesClause
      // uses compareValues which handles numeric coercion at comparison time).
      // Normalise comma-separated em_tokens: strip commas so numeric comparison works.
      if (typeof currentFields.em_tokens === 'string') {
        currentFields.em_tokens = currentFields.em_tokens.replace(/,/g, '');
      }
      records.push({
        path: `${relPath}#ledger-${blockIdx}`,
        frontmatter: currentFields,
      });
    }
    currentFields = null;
    inTable = false;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Detect "## Session Ledger" heading (exact or with trailing whitespace/punctuation)
    if (/^##\s+Session Ledger\s*$/.test(trimmed)) {
      // Flush any previous block before starting a new one
      flushBlock();
      currentFields = {};
      inTable = false;
      continue;
    }

    if (currentFields === null) continue; // not inside a ledger block yet

    // Blank line ends the table only AFTER we have started seeing table rows.
    // The blank line between the heading and the table header is part of markdown
    // formatting and must not terminate the block prematurely.
    // A next heading always ends the block regardless.
    if (/^#+\s/.test(trimmed)) {
      flushBlock();
      continue;
    }
    if (trimmed === '' && inTable) {
      flushBlock();
      continue;
    }
    if (trimmed === '' && !inTable) {
      // blank line before table rows — skip, stay in block
      continue;
    }

    // Skip the separator row (|---|---|)
    if (/^\|[-\s|]+\|$/.test(trimmed)) continue;

    // Parse a table row: | Field | Value |
    const rowMatch = trimmed.match(/^\|([^|]+)\|([^|]+)\|/);
    if (rowMatch) {
      inTable = true;
      const field = rowMatch[1].trim().toLowerCase().replace(/[\s-]+/g, '_');
      const value = rowMatch[2].trim();
      // Skip the header row (Field | Value)
      if (field === 'field' && value.toLowerCase() === 'value') continue;
      currentFields[field] = value;
    } else if (inTable) {
      // Non-table content after table rows started — end of block
      flushBlock();
    }
  }

  // Flush final block if file ends while inside a ledger
  flushBlock();

  return records;
}

// ---------------------------------------------------------------------------
// Main query function (exported for use by refresh-queries)
// ---------------------------------------------------------------------------
function queryRecords(opts, root) {
  const glob = TYPE_TO_GLOB[opts.type];

  let records;

  if (opts.type === 'lesson') {
    const lessonsPath = path.join(root, 'state', 'lessons.md');
    const parsed = parseLessonsFile(lessonsPath);
    records = parsed.map(r => ({ path: r.path, frontmatter: r.frontmatter }));
  } else if (opts.type === 'handoff-ledger') {
    // Synthetic type: parse ## Session Ledger blocks from handoff bodies.
    // Crawl BOTH live handoffs (state/handoffs/*.md) and archived handoffs
    // (archive/handoffs/**/*.md) since the query surface spans the full chain.
    const liveFiles = walkGlob(root, 'state/handoffs/*.md');
    const archiveFiles = walkGlob(root, 'archive/handoffs/**/*.md');
    const allFiles = [...liveFiles, ...archiveFiles];
    records = [];
    for (const file of allFiles) {
      let content;
      try { content = fs.readFileSync(file, 'utf8'); } catch { continue; }
      const relPath = path.relative(root, file).replace(/\\/g, '/');
      const ledgerRecords = parseHandoffLedger(file, relPath, content);
      records.push(...ledgerRecords);
    }
  } else {
    let files = walkGlob(root, glob);
    // Absence-as-signal: completion queries skip the legacy/ monolith bucket.
    // Glob `archive/completed/*/*.md` matches `archive/completed/legacy/<month>.md`
    // because legacy is a valid `*` segment; the migration helper preserves these
    // pre-Phase-1 monoliths but they are not per-entry records and must not pollute
    // results.
    if (opts.type === 'completion') {
      files = files.filter(f => !f.replace(/\\/g, '/').includes('/archive/completed/legacy/'));
    }
    records = [];
    for (const file of files) {
      let content;
      try { content = fs.readFileSync(file, 'utf8'); } catch { continue; }
      const relPath = path.relative(root, file).replace(/\\/g, '/');
      // .yaml files are whole-file frontmatter (no --- delimiters); .md files use the
      // standard parseFrontmatter delimiter-aware path.
      // Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C6
      let frontmatter, body;
      if (path.extname(file) === '.yaml') {
        try {
          frontmatter = _parseYaml(content);
          body = '';
        } catch {
          frontmatter = null;
          body = content;
        }
      } else {
        ({ frontmatter, body } = parseFrontmatter(content));
      }
      if (!frontmatter) {
        // includeUnparseable opt-in: return a stub record with parseError instead of silently skipping.
        // Default OFF (false) preserves the existing silent-skip for all current consumers.
        if (opts.includeUnparseable) {
          records.push({ path: relPath, frontmatter: null, parseError: 'no frontmatter block found' });
        }
        continue;
      }
      // cross-repo-memo memo-shape guard: skip files whose frontmatter lacks the
      // expected memo fields (from + to). This silently excludes README.md and any
      // non-memo files that land in the inbox without being fail-loud — fail-loud is
      // HANDOFF-ONLY; memos use plain queryRecords filtering via this guard.
      if (opts.type === 'cross-repo-memo') {
        if (!frontmatter.from || !frontmatter.to) continue;
      }
      applyConsumedMarker(frontmatter, body);
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

  // Apply --older-than as created< filter (inverse of --since).
  // Records lacking `created` are excluded — same convention as --since.
  const olderThan = parseOlderThan(opts.olderThan);
  if (olderThan) {
    records = records.filter(r => {
      const c = r.frontmatter.created;
      if (!c) return false;
      return String(c) < olderThan;
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
