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
// Schema-to-glob mapping — DERIVED from the schema registry (Option b).
//
// TYPE_TO_GLOB is built at startup from loadSchemas() so that adding a new
// schemas/*.yaml file automatically makes a new --type available with no
// manual duplication. The prior "must match" comment and hand-maintained list
// are replaced by this derivation. Drift is enforced by the test in
// bin/lib/query-records.test.js (describe 'TYPE_TO_GLOB drift-enforcement').
//
// Key-name mapping (schema name → query --type):
//   Schema key-name  = query-type name for all schemas EXCEPT:
//     completion-entry → completion  (legacy --type name predates the schema rename)
//     lesson-entry     → lesson      (same reason)
//
// Deliberate glob overrides (documented per-type below):
//   handoff-archived: schema applies_to = 'archive/handoffs/*.md' (flat).
//                     TYPE_TO_GLOB uses 'archive/handoffs/**/*.md' (recursive) since
//                     2026-06-18 month-foldering (archive/handoffs/YYYY-MM/). The schema
//                     retains the flat form for path-match validation; the query side
//                     intentionally widens to recursive to find month-foldered handoffs.
//   cross-repo-memo:  schema applies_to = 'cross-repo/inbox/[0-9]*.md' (bracket char-class).
//                     TYPE_TO_GLOB uses 'cross-repo/inbox/*.md' — filePatternToRegex (this
//                     file) escapes '['/']' as literals so the bracket class would match nothing.
//                     A memo-shape guard (from+to present, queryRecords ~L650) replaces the
//                     bracket-class filename filter. The two glob engines are incompatible for
//                     this pattern; the override is permanent, not a sync failure.
//
// Non-schema'd types (no schemas/*.yaml — declared explicitly as supplements):
//   lesson:          special inline-tag-per-entry type; schema is lesson-entry but
//                    the query type uses a different key and a fixed path.
//   handoff-ledger:  synthetic; parses ## Session Ledger table blocks, not frontmatter.
//   debt / bug / improvement: directory-of-YAML queue types (state/<type>-*/*.yaml).
//
// Spec backlink: docs/plans/2026-06-22-authorized-blanket-orphan-capture-not-sibling-sweep.md
// (tc-5 reconcile — derive-A-from-B implementation)
// ---------------------------------------------------------------------------

// Schemas dir is co-located with the coordinator plugin root.
const _SCHEMAS_DIR = path.resolve(__dirname, '..', 'schemas');

// Query-type name → schema name mappings (for the two mismatched pairs).
const _SCHEMA_NAME_TO_QUERY_TYPE = {
  'completion-entry': 'completion',
  'lesson-entry':     null,        // lesson is a non-standard type; handled in supplement below
};

// Glob overrides: schema applies_to cannot be used verbatim for these types.
// Each entry explains the engine incompatibility or intentional divergence.
const _GLOB_OVERRIDES = {
  'handoff-archived': 'archive/handoffs/**/*.md', // recursive since 2026-06-18 month-foldering; schema stays flat for path-match validation
  'cross-repo-memo':  'cross-repo/inbox/*.md',    // filePatternToRegex escapes brackets; memo-shape guard replaces bracket-class filename filter
};

/**
 * Build the sidecar exclusion data for --type plan queries.
 *
 * Purpose: `plan` schema applies_to (docs/plans/*.md) over-matches sidecar files
 * (*.prior-art-check.md, *.plan-coverage-check.md, *-review.md, *docs-check.md).
 * These have their own schema types and must NOT appear in --type plan results.
 *
 * Two-layer exclusion (both are needed):
 *   Layer 1 — filename regex: catches well-formed sidecar filenames whose suffix
 *     matches a schema applies_to pattern (e.g. *.prior-art-check.md). Derived from
 *     every docs/plans/* schema except the plan schema itself.
 *   Layer 2 — kind denylist: catches irregular sidecar filename forms (*.review-2.md,
 *     *.patrik-r1.md, *.plan-coverage-check.TIMESTAMP.md) that don't match the schema
 *     glob but DO carry a kind: field mapping to a sidecar schema. Derived from
 *     _byKind for every non-plan docs/plans/* schema.
 *
 * Conservative-exclude heuristic (warn-not-fail by design): a file that passes BOTH
 * layers but contains an embedded plan extension (.md. in the basename) is treated as
 * an UNREGISTERED sidecar — a stderr warning is emitted and the file is excluded
 * conservatively. The tool does NOT exit on this condition; it excludes and warns.
 * Review: code-reviewer — F3: framing changed from "Fail-loud guarantee" to
 * "conservative-exclude heuristic (warn-not-fail by design)" to match actual behavior.
 *
 * Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4
 * (sidecar exclusion at the producer layer so all consumers see real plans only)
 *
 * @param {object} schemas  Result of loadSchemas() — has ._byGlob and ._byKind.
 * @returns {{ regexes: RegExp[], kinds: Set<string> }}
 */
function _buildPlanSidecarRegexes(schemas) {
  const regexes = [];
  const PLAN_DIR_PREFIX = 'docs/plans/';

  // Collect sidecar schema names (every docs/plans/* schema except 'plan').
  const sidecarSchemaNames = new Set();
  for (const { glob, schemaName } of schemas._byGlob) {
    if (schemaName === 'plan') continue;  // the plan schema itself — not a sidecar
    if (!glob.startsWith(PLAN_DIR_PREFIX)) continue;  // only care about docs/plans/
    sidecarSchemaNames.add(schemaName);
    // Extract the filename pattern portion (after docs/plans/) and compile to regex.
    const filenamePart = glob.slice(PLAN_DIR_PREFIX.length);
    regexes.push(filePatternToRegex(filenamePart));
  }

  // Layer 2: build a set of kind values that belong to sidecar schemas.
  // This catches irregular sidecar filename forms (*.review-2.md, *.patrik-r1.md,
  // *.plan-coverage-check.TIMESTAMP.md) that don't match the glob but do carry kind:.
  //
  // Review: code-reviewer — F4: coupling constraint documented below.
  // Layer 2 only catches sidecar kinds from schemas that ALSO have an applies_to
  // under docs/plans/ — a sidecar schema whose applies_to points elsewhere (e.g. a
  // hypothetical state/ sidecar schema) would NOT contribute to this denylist, because
  // the loop above skips non-plans-dir globs. A future schema with sidecar-kind values
  // but a non-plans glob needs explicit handling here or a separate Layer-2 mechanism.
  const kinds = new Set();
  for (const [kindValue, schemaName] of Object.entries(schemas._byKind)) {
    if (sidecarSchemaNames.has(schemaName)) {
      kinds.add(kindValue);
    }
  }

  return { regexes, kinds };
}

// _PLAN_SIDECAR_DATA is declared via destructuring from _buildTypeToGlob() below.
// Defined here as a forward-reference comment; the actual binding is at module startup
// after _buildTypeToGlob() is called. See: const { ..., planSidecarData: _PLAN_SIDECAR_DATA }.

/**
 * Build TYPE_TO_GLOB from the schema registry plus explicit supplements, and
 * derive the plan-sidecar exclusion regexes in the same pass (schemas loaded once).
 *
 * Returns { typeToGlob, planSidecarRegexes } so callers can destructure both
 * without a second loadSchemas() call.
 *
 * typeToGlob: replaces the prior hand-maintained TYPE_TO_GLOB literal with a
 *   derivation so adding schemas/*.yaml automatically makes --type available.
 *
 * planSidecarRegexes: filename-only regexes for every docs/plans/* sidecar schema.
 *   Used by queryRecords() to exclude sidecar files from --type plan results.
 *   Derived from every docs/plans/* schema OTHER than the plan schema itself.
 *   Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4
 */
function _buildTypeToGlob(schemasDir) {
  let schemas;
  try {
    schemas = loadSchemas(schemasDir);
  } catch (e) {
    // Review: F5 — distinguish a genuinely absent schemas dir (legitimate test isolation)
    // from any other error. Only the absent-dir case falls back silently; real errors
    // (permissions, malformed YAML, unexpected FS state) must be rethrown so they don't
    // silently produce an empty TYPE_TO_GLOB that passes all type validation.
    const isMissingDir = !require('fs').existsSync(schemasDir);
    if (!isMissingDir) {
      throw e;
    }
    schemas = { _byGlob: [], _byKind: {} };
  }

  const map = {};

  // --- Part 1: derive from schema applies_to ---
  for (const { glob, schemaName } of schemas._byGlob) {
    // Skip lesson-entry — it is handled in the supplement below (special inline-tag path).
    if (schemaName === 'lesson-entry') continue;

    // Map schema name to query type name (fall back to schema name as-is).
    const queryType = _SCHEMA_NAME_TO_QUERY_TYPE.hasOwnProperty(schemaName)
      ? _SCHEMA_NAME_TO_QUERY_TYPE[schemaName]
      : schemaName;

    if (queryType === null) continue; // explicitly excluded (handled in supplement)

    // Apply glob override if present; otherwise use schema applies_to verbatim.
    map[queryType] = _GLOB_OVERRIDES.hasOwnProperty(schemaName)
      ? _GLOB_OVERRIDES[schemaName]
      : glob;
  }

  // --- Part 2: explicit supplements for non-schema'd and special-cased types ---

  // lesson: inline-tag-per-entry type. The lesson-entry schema uses match_mode:
  // inline-tag-per-entry rather than a standard path glob, so query-records uses
  // a fixed path. Query type key is 'lesson', not 'lesson-entry'.
  map['lesson'] = 'state/lessons.md';

  // handoff-ledger: synthetic type — parses ## Session Ledger table blocks from
  // handoff bodies. Primary glob here; archive glob added in queryRecords() at runtime.
  // Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md §Chunk6
  map['handoff-ledger'] = 'state/handoffs/*.md';

  // Directory-form queue types (per-entry YAML files, no --- delimiters).
  // Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C6
  map['debt']        = 'state/debt-backlog/*.yaml';
  map['bug']         = 'state/bug-backlog/*.yaml';
  map['improvement'] = 'state/improvement-queue/*.yaml';

  // --- Part 3: derive plan-sidecar exclusion data ---
  // Build the sidecar exclusion data in the same pass so schemas are loaded only once.
  // Returns { regexes: RegExp[], kinds: Set<string> }.
  const planSidecarData = _buildPlanSidecarRegexes(schemas);

  return { typeToGlob: map, planSidecarData };
}

const { typeToGlob: TYPE_TO_GLOB, planSidecarData: _PLAN_SIDECAR_DATA } =
  _buildTypeToGlob(_SCHEMAS_DIR);

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
  // Schema-backed sidecar types (C4 — Spec backlink:
  // docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4)
  'review-sidecar':      (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — reviewer: ${fm.reviewer || '?'}, verdict: ${fm.verdict || '?'}`,
  'prior-art-check':     (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — plan: ${fm.plan || '?'}, status: ${fm.status || '?'}`,
  'plan-coverage-check': (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — plan: ${fm.plan || '?'}, status: ${fm.status || '?'}`,
  'docs-check-sidecar':  (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — artifact: ${fm.artifact || '?'}, checked: ${fm.claims_checked ?? '?'}, verified: ${fm.verified ?? '?'}, incorrect: ${fm.incorrect ?? '?'}`,
  'integration-summary': (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — plan: ${fm.plan || '?'}, status: ${fm.status || '?'}`,
  'problem-set':         (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — status: ${fm.status || '?'}`,
  'archived-memo':       (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — from: ${fm.from || '?'} → to: ${fm.to || '?'}, status: ${fm.status || '?'}`,
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
    // Sidecar exclusion for --type plan — two layers.
    // The plan schema applies_to (docs/plans/*.md) over-matches sidecar files that live
    // alongside plans (*.prior-art-check.md, *.plan-coverage-check.md, *-review.md,
    // *docs-check.md). These have their own schema types and must NOT appear in plan
    // results. _PLAN_SIDECAR_DATA is derived from the schema registry at startup so
    // it stays in sync automatically as new sidecar schemas are added.
    //
    // Layer 1 (file walk): exclude files whose basename matches a sidecar schema glob.
    // Layer 2 (record loop): exclude records whose frontmatter kind: belongs to a sidecar
    //   schema — catches irregular filename forms (*.review-2.md, *.patrik-r1.md,
    //   *.plan-coverage-check.TIMESTAMP.md) that don't match the schema globs.
    //
    // Conservative-exclude heuristic (warn-not-fail by design): a file that passes
    // Layer 1 AND has an embedded '.md.' in its basename (which no real plan ever has)
    // is an UNREGISTERED sidecar shape — stderr warning emitted, file excluded. The
    // tool does NOT exit; it warns and excludes. See _buildPlanSidecarRegexes JSDoc.
    // Review: code-reviewer — F3: label changed from "Fail-loud guarantee" to match behavior.
    //
    // Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4
    if (opts.type === 'plan' && _PLAN_SIDECAR_DATA) {
      const { regexes: sidecarRegexes, kinds: sidecarKinds } = _PLAN_SIDECAR_DATA;
      if (sidecarRegexes.length > 0) {
        files = files.filter(f => {
          const basename = path.basename(f);
          // Layer 1a: check against every registered sidecar filename regex.
          if (sidecarRegexes.some(re => re.test(basename))) return false;

          // Layer 1b: heuristic for unregistered sidecar shapes — basenames that contain
          // '.md.' embed the plan filename (e.g. '2026-05-27-plan.md.new-sidecar.md').
          // A real plan filename never contains an embedded '.md.' sequence.
          if (basename.includes('.md.')) {
            process.stderr.write(
              `[query-records] WARNING: unregistered plan sidecar excluded: ${basename}\n` +
              `  Add a schema to schemas/ with applies_to: "docs/plans/*<suffix>.md" to silence this.\n`
            );
            return false; // exclude conservatively
          }
          return true; // passes filename check — kind check happens in record loop
        });
      }
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
      // Plan sidecar exclusion Layer 2: kind-based and structural filters.
      // Catches irregular sidecar filename forms that passed Layer 1 (filename regex).
      //
      // Layer 2a — kind denylist: if frontmatter kind: maps to a sidecar schema (e.g.
      //   *.review-2.md with kind: code-review, *.plan-coverage-check.TIMESTAMP.md with
      //   kind: plan-coverage-check), exclude it. Records with no kind: fall through.
      //
      // Layer 2b — structural review-sidecar guard: legacy review files authored before
      //   the kind: taxonomy (e.g. *.patrik-r1.md from 2026-05) carry reviewer: + plan:
      //   but no kind:. A real plan never references another plan in its own plan: field.
      //   Analogous to the cross-repo-memo from/to structural guard.
      if (opts.type === 'plan' && _PLAN_SIDECAR_DATA) {
        const kindVal = frontmatter.kind;
        if (kindVal && _PLAN_SIDECAR_DATA.kinds.has(String(kindVal))) continue;
        // Layer 2b: legacy review sidecar structural guard.
        // A real plan could theoretically carry both reviewer: and plan: fields (e.g. a
        // plan authored by a reviewer that cross-references another plan). To avoid
        // false-excluding such a plan, we additionally require a verdict: field —
        // review sidecars always carry verdict: (APPROVED / APPROVED_WITH_NOTES / REJECTED)
        // while real plans never do. The triple conjunction is tighter than reviewer+plan alone.
        // Review: code-reviewer — F5: strengthened from (reviewer && plan) to
        // (reviewer && plan && verdict) to avoid false-positive exclusion of a real plan
        // that legitimately carries both reviewer: and plan: without a verdict:.
        if (frontmatter.reviewer && frontmatter.plan && frontmatter.verdict) continue;
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

// Review: F7 — export TYPE_TO_GLOB so the drift-enforcement test can require it
// directly instead of parsing the 'Valid: ...' stderr of a deliberate invalid-type run.
module.exports = { queryRecords, formatRecords, parseSince, parseWhereExpr, TYPE_TO_GLOB };
