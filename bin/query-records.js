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
 * Lesson type is special: queries state/lessons/*.yaml (one YAML file per lesson).
 *   --where "scope=universal" filters lessons by stored scope field.
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
const { execSync, execFileSync } = require('child_process');
const { loadSchemas, parseFrontmatter, _parseYaml, validateFrontmatter, matchSchemaForPath } = require('./lib/schema.js');
const { TERMINAL_STATUS, TERMINAL_DEPLOYMENT, CONSUMED_MARKER_RE } = require('./lib/consumed-marker.js');
// C6 GAP1 — batch corpus sweep reuses the SAME reachability rule kernel the
// C2 write-time hook applies (not just _resolveTarget — the whole rule set,
// including the kind:recovery same-repo-only carve-out). Fail-open on load
// error, matching every other optional-lib guard in this file's siblings.
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2, § C6 (GAP1)
let _checkLineageReachability = null;
let _buildGitHistoryCache = null;
try {
  ({
    checkLineageReachability: _checkLineageReachability,
    buildGitHistoryCache: _buildGitHistoryCache,
  } = require('./lib/walk-handoff-dag.js'));
} catch (err) {
  process.stderr.write(`query-records: cannot load walk-handoff-dag lib (${err && err.message}) — lineage-reachability sweep disabled (never block on infra)\n`);
}
// Review: the Staff Engineer F3 — import shared constants/regex so read-time and write-time
// paths (normalize-consumed-frontmatter.js) stay greppably aligned.
// Review: the Staff Engineer F4 — CONSUMED_MARKER_RE now uses lazy `(.*?)\s*-->` capture so
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
// Supplement-only types — schema/*.yaml exists but handled via supplement or special path:
//   lesson:          schema is lesson-entry; query type uses a different key and a fixed path.
//   handoff-ledger:  synthetic; parses ## Session Ledger table blocks, not frontmatter.
// Review: code-reviewer F1 — corrected stale claim "no schemas/*.yaml"; bug-backlog.yaml,
// debt-backlog.yaml, and improvement-queue.yaml exist in coordinator/schemas/. They are now
// mapped in _SCHEMA_NAME_TO_QUERY_TYPE so Part 1 derives bug/debt/improvement directly —
// Part 2 supplement entries for those three types have been removed.
//
// Spec backlink: docs/plans/2026-06-22-authorized-blanket-orphan-capture-not-sibling-sweep.md
// (tc-5 reconcile — derive-A-from-B implementation)
// ---------------------------------------------------------------------------

// Schemas dir is co-located with the coordinator plugin root.
const _SCHEMAS_DIR = path.resolve(__dirname, '..', 'schemas');

// Schema name → query-type name mappings (five mismatched pairs: schema name ≠ query --type name).
// null means explicitly excluded from Part 1 derivation (handled in supplement instead).
// Review: code-reviewer F2/F3 — added bug-backlog/debt-backlog/improvement-queue so Part 1
// derives map['bug']/map['debt']/map['improvement'] directly; no longer a separate inverse.
const _SCHEMA_NAME_TO_QUERY_TYPE = {
  'completion-entry': 'completion',
  'lesson-entry':     null,        // lesson is a non-standard type; handled in supplement below
  'bug-backlog':      'bug',
  'debt-backlog':     'debt',
  'improvement-queue':'improvement',
};

// Glob overrides: schema applies_to cannot be used verbatim for these types.
// Each entry explains the engine incompatibility or intentional divergence.
const _GLOB_OVERRIDES = {
  'handoff-archived': 'archive/handoffs/**/*.md', // recursive since 2026-06-18 month-foldering; schema stays flat for path-match validation
  'cross-repo-memo':  'cross-repo/inbox/*.md',    // filePatternToRegex escapes brackets; memo-shape guard replaces bracket-class filename filter
};

// Types included in the --unattached multi-type union lens.
//
// Purpose: `query-records --unattached` (no --type) returns every record across
// these types whose initiative frontmatter is null/absent, spanning queues +
// roadmap spinoff-stubs + handoffs + plans.
//
// Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C3 (AC4)
const UNATTACHED_TYPES = ['bug', 'debt', 'improvement', 'roadmap', 'handoff', 'plan'];

/**
 * Build the sidecar exclusion regexes for --type plan queries.
 *
 * Purpose: `plan` schema applies_to (docs/plans/*.md) over-matches sidecar files
 * (*.review.md, *.prior-art-check.md, *.plan-coverage-check.md, *.docs-check.md).
 * These have their own schema types and must NOT appear in --type plan results.
 *
 * Single positive layer — filename regex derived from the canonical sidecar suffix
 * set pinned in the four sidecar schema applies_to globs (tc-1 C3). After the C9
 * broadsword port all sidecar files are in canonical form, so the regex layer is
 * sufficient and exhaustive. An anomaly detector in queryRecords() handles any
 * future non-conforming file via warn + exclude (see the --type plan filter block).
 *
 * Retired (tc-1 C4):
 *   Layer 2 kind-fallback denylist — dead code after C9 broadsword (all irregular
 *   filename forms folded to canonical suffix). Derived from _byKind; not needed.
 *   Conservative-exclude .md. heuristic — also dead after broadsword.
 *
 * Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C4
 * Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4
 * (sidecar exclusion at the producer layer so all consumers see real plans only)
 *
 * @param {object} schemas  Result of loadSchemas() — has ._byGlob.
 * @returns {{ regexes: RegExp[] }}
 */
function _buildPlanSidecarRegexes(schemas) {
  const regexes = [];
  const PLAN_DIR_PREFIX = 'docs/plans/';

  // Single positive layer: collect filename regexes for every docs/plans/* sidecar schema.
  for (const { glob, schemaName } of schemas._byGlob) {
    if (schemaName === 'plan') continue;  // the plan schema itself — not a sidecar
    if (!glob.startsWith(PLAN_DIR_PREFIX)) continue;  // only care about docs/plans/
    // Extract the filename pattern portion (after docs/plans/) and compile to regex.
    const filenamePart = glob.slice(PLAN_DIR_PREFIX.length);
    regexes.push(filePatternToRegex(filenamePart));
  }

  return { regexes };
}

// _PLAN_SIDECAR_DATA is declared via destructuring from _buildTypeToGlob() below.
// Defined here as a forward-reference comment; the actual binding is at module startup
// after _buildTypeToGlob() is called. See: const { ..., planSidecarData: _PLAN_SIDECAR_DATA }.

/**
 * Build TYPE_TO_GLOB from the schema registry plus explicit supplements, and
 * derive the plan-sidecar exclusion regexes in the same pass (schemas loaded once).
 *
 * Returns { typeToGlob, planSidecarData } so callers can destructure both
 * without a second loadSchemas() call.
 *
 * typeToGlob: replaces the prior hand-maintained TYPE_TO_GLOB literal with a
 *   derivation so adding schemas/*.yaml automatically makes --type available.
 *
 * planSidecarData: { regexes } — single positive layer for sidecar exclusion (tc-1 C4).
 *   Filename-only regexes for every docs/plans/* sidecar schema except 'plan' itself.
 *   Used by queryRecords() alongside the anomaly detector (warn + exclude) for defense
 *   in depth against future non-conforming files.
 *   Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C4
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

  // lesson: per-entry YAML type. One YAML file per lesson under state/lessons/*.yaml.
  // Query type key is 'lesson', not 'lesson-entry'. Source was state/lessons.md
  // (inline-tag-per-entry); migrated to per-file YAML in C3b.
  // Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3b.
  map['lesson'] = 'state/lessons/*.yaml';

  // handoff-ledger: synthetic type — parses ## Session Ledger table blocks from
  // handoff bodies. Primary glob here; archive glob added in queryRecords() at runtime.
  // Spec backlink: docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md §Chunk6
  map['handoff-ledger'] = 'state/handoffs/*.md';

  // Note: bug/debt/improvement are now derived from _SCHEMA_NAME_TO_QUERY_TYPE in Part 1.
  // Review: code-reviewer F2 — removed supplement entries for bug/debt/improvement; they are
  // now mapped in _SCHEMA_NAME_TO_QUERY_TYPE so Part 1 produces map['bug']/['debt']/['improvement']
  // directly. This closes the accidental bug-backlog/debt-backlog/improvement-queue alias keys.

  // --- Part 3: derive plan-sidecar exclusion data ---
  // Build the sidecar exclusion data in the same pass so schemas are loaded only once.
  // Returns { regexes: RegExp[] } — single positive layer (tc-1 C4).
  const planSidecarData = _buildPlanSidecarRegexes(schemas);

  return { typeToGlob: map, planSidecarData, schemas };
}

const { typeToGlob: TYPE_TO_GLOB, planSidecarData: _PLAN_SIDECAR_DATA, schemas: _MODULE_SCHEMAS } =
  _buildTypeToGlob(_SCHEMAS_DIR);

/**
 * Map a query --type name to the canonical schema name (derived from _SCHEMA_NAME_TO_QUERY_TYPE).
 * Used by the generalized sibling-exclusion filter to compare matchSchemaForPath results.
 *
 * Five types where schema name differs from query type name:
 *   'completion'  → schema name 'completion-entry'  (legacy rename; query type predates schema)
 *   'bug'         → schema name 'bug-backlog'        (applies_to: state/bug-backlog/*.yaml)
 *   'debt'        → schema name 'debt-backlog'       (applies_to: state/debt-backlog/*.yaml)
 *   'improvement' → schema name 'improvement-queue'  (applies_to: state/improvement-queue/*.yaml)
 * Fifth divergence: lesson → lesson-entry; handled by its own code path, never reaches this function.
 *
 * Spec backlink: docs/plans/2026-06-30-deep-research-queryable-index-layer.md § P1-1
 * // C1-fix: bug/debt/improvement mappings now derived from _SCHEMA_NAME_TO_QUERY_TYPE (2026-07-04)
 * // — sibling-exclusion filter was silently dropping all backlog records due to schema-name mismatch.
 * Review: code-reviewer F2/F4/F5 — derived from _SCHEMA_NAME_TO_QUERY_TYPE (single source of truth);
 * corrected docstring to say "Five types"; added note on lesson fifth-divergence handled elsewhere.
 */

// Derived inverse of _SCHEMA_NAME_TO_QUERY_TYPE: queryType → schemaName.
// Built once at module load so the two can never silently drift.
const _QUERY_TYPE_TO_SCHEMA_NAME = Object.fromEntries(
  Object.entries(_SCHEMA_NAME_TO_QUERY_TYPE)
    .filter(([, queryType]) => queryType !== null)
    .map(([schemaName, queryType]) => [queryType, schemaName])
);

function _queryTypeToSchemaName(qtype) {
  return _QUERY_TYPE_TO_SCHEMA_NAME[qtype] || qtype;
}

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
  // Review: code-reviewer Slice-C — (C-F4) bug used fm.system but schema field is `surface`;
  //   improvement used fm.proposed_target but schema field is `proposed_action`.
  bug:         (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.severity || 'P?'} ${fm.status || 'unknown'} (surface: ${fm.surface || '?'})`,
  improvement: (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'} (action: ${fm.proposed_action || '?'})`,
  // Schema-backed sidecar types (C4 — Spec backlink:
  // docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C4)
  'review-sidecar':      (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — reviewer: ${fm.reviewer || '?'}, verdict: ${fm.verdict || '?'}`,
  'prior-art-check':     (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — plan: ${fm.plan || '?'}, status: ${fm.status || '?'}`,
  'plan-coverage-check': (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — plan: ${fm.plan || '?'}, status: ${fm.status || '?'}`,
  'docs-check-sidecar':  (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — artifact: ${fm.artifact || '?'}, checked: ${fm.claims_checked ?? '?'}, verified: ${fm.verified ?? '?'}, incorrect: ${fm.incorrect ?? '?'}`,
  'integration-summary': (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — plan: ${fm.plan || '?'}, status: ${fm.status || '?'}`,
  'problem-set':         (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — status: ${fm.status || '?'}`,
  'archived-memo':       (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — from: ${fm.from || '?'} → to: ${fm.to || '?'}, status: ${fm.status || '?'}`,
  // Consolidated/distilled terminal shape of a DR corpus (container; sibling of per-file decision).
  // Spec backlink: cross-repo/inbox/2026-06-27-example-stats-repo-decision-records-fleet-share.md § Q2
  'decision-guide':      (p, fm) => `- [${fm.title || path.basename(p)}](${p}) — ${fm.status || 'unknown'}${fm.decision_count ? ` (${fm.decision_count} DRs)` : ''}`,
  // Review: code-reviewer Slice-A — (F3) deep-research types: without entries, markdown-list
  // falls back to bare path rendering (no pipeline/score/claim text / count context).
  'research-synthesis':  (p, fm) => `- [${fm.title || p}](${p}) — pipeline: ${fm.pipeline || '?'}, score: ${fm.coverage_score ?? '?'}`,
  'research-claim':      (p, fm) => `- ${fm.claim_text || p} [${fm.confidence || '?'}] (${fm.type || '?'})`,
  'coverage-audit':      (p, fm) => `- [${path.basename(p)}](${p}) — present: ${fm.present_count ?? '?'}, absent: ${fm.absent_count ?? '?'}`,
  'gap-report':          (p, fm) => `- [${path.basename(p)}](${p}) — gaps: ${fm.gap_count ?? '?'}, score: ${fm.coverage_score ?? '?'}, deepening: ${fm.deepening_recommended}`,
};

// ---------------------------------------------------------------------------
// Fleet aggregator — three-rung registry resolution
// ---------------------------------------------------------------------------
/**
 * Resolve a repo root via the three-rung chain defined in machine-local-registry.md § 5:
 *   Rung 1: machine-local get repos.<name>  (primary)
 *   Rung 2: sibling-relative ../<sibling>/  (fallback when rung 1 is cleanly absent)
 *   Rung 3: null                            (neither resolves → caller skips gracefully)
 *
 * Spec backlink: archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk A1
 * Spec backlink: plugins/coordinator/docs/wiki/machine-local-registry.md § 5
 *
 * @param {string} repoName     Bare key after "repos." prefix (e.g. "coordinator_claude").
 * @param {string} currentRoot  Absolute path of the invoking repo root (for rung-2 sibling calc).
 * @returns {{ root: string, rung: number }|null}  null when neither rung resolves.
 */
function resolveRepoRoot(repoName, currentRoot) {
  // Rung 1: machine-local get repos.<name>
  // Review: code-reviewer ROBUSTNESS — use execFileSync (no shell) to eliminate
  //   shell-injection shape on repoName; warn on non-rc1 exits so operational
  //   failures (Python crash, malformed TOML) surface instead of silently falling
  //   through to rung-2 and potentially resolving the wrong path.
  try {
    const result = execFileSync(
      'machine-local', ['get', `repos.${repoName}`],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    );
    const resolved = result.trim();
    if (resolved) {
      return { root: path.resolve(resolved), rung: 1 };
    }
  } catch (e) {
    // rc=1 → cleanly absent key; fall through to rung 2.
    if (e && e.status !== 1) {
      // rc≠1 → operational failure (Python crash, malformed TOML, missing binary);
      // warn so the caller can detect infra issues rather than silently resolving
      // against the wrong path via rung-2 sibling fallback.
      process.stderr.write(
        `query-records: resolveRepoRoot: machine-local exited ${e.status} for repos.${repoName} — operational failure, falling through to sibling-relative rung\n`
      );
    }
    // All errors: fall through to rung 2 as best-effort.
  }

  // Rung 2: sibling-relative fallback.
  // Derive sibling dir name: key underscores → hyphens (the documented convention:
  // machine-local-registry.md § Ergonomic helpers — "Hyphens in keys are normalized
  // to underscores", so the reverse is underscores → hyphens for sibling lookup).
  const siblingName = repoName.replace(/_/g, '-');
  const siblingPath = path.resolve(currentRoot, '..', siblingName);
  if (fs.existsSync(siblingPath)) {
    return { root: siblingPath, rung: 2 };
  }

  // Rung 3: neither resolves.
  return null;
}

/**
 * Enumerate the repos.* namespace from the machine-local registry.
 * Returns an array of bare key names (e.g. ["coordinator_claude", "project_rag", ...]).
 *
 * Test-isolation hook: if env QUERY_RECORDS_FLEET_REPOS is set (comma-separated list of
 * repo names), that list is used directly and machine-local keys is not called. This allows
 * tests to fixture specific repo names without touching the real registry.
 *
 * @returns {string[]}  Bare repo key names (part after "repos.").
 */
function enumerateRegistryRepos() {
  // Test-isolation: QUERY_RECORDS_FLEET_REPOS=name1,name2 overrides registry enumeration.
  const envOverride = process.env.QUERY_RECORDS_FLEET_REPOS;
  if (envOverride) {
    return envOverride.split(',').map(s => s.trim()).filter(Boolean);
  }

  try {
    // Review: code-reviewer F9 — use execFileSync (no shell) for consistency with resolveRepoRoot.
    // The 'keys' subcommand takes no user-supplied args so shell-injection is nil in practice,
    // but the inconsistency within the same file (where execFileSync was chosen explicitly for
    // robustness) creates a reading hazard for injection-shape auditors.
    const output = execFileSync('machine-local', ['keys'], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return output
      .split('\n')
      .map(l => l.trim())
      .filter(l => l.startsWith('repos.'))
      .map(l => l.slice('repos.'.length));
  } catch {
    return [];
  }
}

/**
 * Fleet aggregator — queries every repo in the machine-local repos registry and
 * unions the per-repo results into a single annotated fleet view (JSON).
 *
 * Registry-resolution is three-rung per machine-local-registry.md § 5.
 * Absent per-repo queue dirs are tolerated (walkGlob returns [] for missing dirs).
 * Absent/unresolvable repo roots are skipped gracefully with a note in `skipped`.
 *
 * Output shape:
 *   {
 *     repos: [{ repo, root, rung, records: [{ repo, path, frontmatter }] }],
 *     skipped: [{ repo, reason }]
 *   }
 *
 * Spec backlink: archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk A1 / AC1
 *
 * @param {object} opts         Parsed CLI options (--type required; --root ignored in fleet mode).
 * @param {string} currentRoot  Absolute path of the invoking repo (used for rung-2 sibling calc).
 * @returns {{ repos: object[], skipped: object[] }}
 */
function queryFleet(opts, currentRoot) {
  const repoNames = enumerateRegistryRepos();

  const repos = [];
  const skipped = [];

  for (const repoName of repoNames) {
    const resolution = resolveRepoRoot(repoName, currentRoot);

    if (!resolution) {
      // Rung 3: neither machine-local nor sibling-relative resolved.
      const remediationKey = `repos.${repoName}`;
      const remediationDir = repoName.replace(/_/g, '-');
      const reason =
        `root not resolvable via machine-local (repos.${repoName}) or ` +
        `sibling-relative (../${remediationDir}/); ` +
        `set: machine-local set ${remediationKey} /path/to/${remediationDir}`;
      skipped.push({ repo: repoName, reason });
      process.stderr.write(
        `query-records --fleet: skipping repo "${repoName}" — ${reason}\n`
      );
      continue;
    }

    const { root: repoRoot, rung } = resolution;

    // Guard: resolved root must exist on disk (handles stale rung-1 registry entries).
    if (!fs.existsSync(repoRoot)) {
      const reason = `resolved root does not exist on disk: ${repoRoot} (rung ${rung})`;
      skipped.push({ repo: repoName, reason });
      process.stderr.write(
        `query-records --fleet: skipping repo "${repoName}" — ${reason}\n`
      );
      continue;
    }

    // Run the per-repo query. queryRecords already handles absent queue dirs gracefully
    // (walkGlob returns [] when the target directory does not exist) — this satisfies the
    // "absent per-repo queue dir → tolerate, skip, continue — never crash" requirement.
    let records;
    try {
      records = queryRecords(opts, repoRoot);
    } catch (e) {
      // Unexpected error querying this repo — skip gracefully, note it.
      const reason = `query error: ${e.message}`;
      skipped.push({ repo: repoName, reason });
      process.stderr.write(
        `query-records --fleet: skipping repo "${repoName}" — ${reason}\n`
      );
      continue;
    }

    // Annotate each record with the repo name and include in the fleet view.
    const annotated = records.map(r => ({ repo: repoName, ...r }));
    repos.push({ repo: repoName, root: repoRoot, rung, records: annotated });
  }

  return { repos, skipped };
}

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
    fleet: false,
    validateAll: false,
    unattached: false,
  };

  // Review: the Staff Engineer R2 finding 4 — normalize --key=value form to --key value before dispatch.
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
    else if (a === '--fleet' || a === '--all-repos') { opts.fleet = true; }
    else if (a === '--validate-all') { opts.validateAll = true; }
    else if (a === '--unattached') { opts.unattached = true; }
    else {
      process.stderr.write(`Unknown argument: ${a}\n`);
      process.exit(1);
    }
  }

  // --type is required for normal query and fleet mode; optional for --validate-all
  // (when absent in --validate-all mode, all types are validated) and for --unattached
  // (when absent in --unattached mode, all UNATTACHED_TYPES are queried).
  if (!opts.validateAll && !opts.unattached && !opts.type) {
    process.stderr.write('--type is required\n');
    process.exit(1);
  }
  if (opts.type && !TYPE_TO_GLOB[opts.type]) {
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
// Cross-type liveness predicate
// ---------------------------------------------------------------------------
// Purpose: compute a single LIVE / BLOCKED / DONE derived state from the
// per-type enums already on disk.  The predicate is purely a read-time
// computation — no frontmatter field is added to artifacts (D2 rationale).
//
// Spec backlink: docs/wiki/canonical-artifact-shapes.md § The Cross-Type
//   Liveness Predicate (KEYSTONE); docs/plans/2026-06-25-example-initiative-tc-0-canonical-
//   baton-shape.md § Chunk C3.
//
// HARD CONSTRAINT: TERMINAL_STATUS ({consumed,superseded}) and TERMINAL_DEPLOYMENT
//   ({shipped,abandoned}) are imported from lib/consumed-marker.js — the single
//   source of truth.  Do NOT re-literal these sets here.

// Review: code-reviewer F10 — hoisted from inside queryRecords/validateAllRecords to module
// scope; avoids re-declaration on each function call and eliminates DRY violation between
// the two inner-function const declarations that must be kept in sync manually.
const _CANONICAL_PLAN_RE = /^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$/;
const _REVIEW_ITERATION_RE = /\.review-\d+\.md$/;

// Memo-specific terminal statuses (back-compat aliases included).
// These are separate from TERMINAL_STATUS because the memo enum is independent
// of the handoff lifecycle.  The authoritative enum lives in schemas/cross-repo-memo.yaml.
const _MEMO_TERMINAL_STATUS = new Set([
  'actioned',
  'reviewed',       // back-compat
  'action_taken',   // back-compat
  'closed',         // back-compat
  'superseded',     // back-compat
]);

// Review: code-reviewer S2-F1 — _MEMO_LIVE_STATUS was declared but never referenced;
// the open-posture comment in the liveness() cross-repo-memo branch already documents
// that unknown values default LIVE. Dead code with a false allowlist-contract implication.
/**
 * Compute the canonical liveness derived state for a frontmatter record.
 *
 * @param {object} fm   Frontmatter object (already mutated by applyConsumedMarker
 *                      when called from the record loop).
 * @param {string} type Query --type string (e.g. 'handoff', 'cross-repo-memo').
 * @returns {'LIVE'|'BLOCKED'|'DONE'}
 *
 * Implemented: handoff, handoff-archived, cross-repo-memo, plan, decision,
 *   debt, bug, improvement, lesson.
 * Other types resolve via a graceful default using TERMINAL_STATUS so the
 * field is always populated and --where liveness= always works.
 * Review: code-reviewer slice-B F1 — extended to include tc-2 types (debt, bug, improvement, lesson).
 */
function liveness(fm, type) {
  const status = fm.status ? String(fm.status) : '';
  const deploymentState = fm.deployment_state ? String(fm.deployment_state) : '';

  // --- Handoff two-axis combination rule ---
  // DONE if status ∈ TERMINAL_STATUS OR deployment_state ∈ TERMINAL_DEPLOYMENT;
  // else BLOCKED if deployment_state == 'awaiting_gate';
  // else LIVE.
  // (handoff-archived uses the same schema — identical rule.)
  if (type === 'handoff' || type === 'handoff-archived') {
    if (TERMINAL_STATUS.has(status) || TERMINAL_DEPLOYMENT.has(deploymentState)) {
      return 'DONE';
    }
    if (deploymentState === 'awaiting_gate') {
      return 'BLOCKED';
    }
    return 'LIVE';
  }

  // --- Memo single-axis rule ---
  // open / in_progress → LIVE; actioned + back-compat aliases → DONE.
  if (type === 'cross-repo-memo') {
    if (_MEMO_TERMINAL_STATUS.has(status)) return 'DONE';
    // open / in_progress → LIVE; unknown values default LIVE (open posture)
    return 'LIVE';
  }

  // --- Plan single-axis rule (tc-1 C4) ---
  // PURE single-axis: deployment_state is IGNORED for plan (plans have no deployment_state).
  // Frozen mapping (transcribed verbatim from tc-0 doctrine table):
  //   draft|reviewed|approved|executing → LIVE
  //   deferred                          → BLOCKED
  //   implemented|abandoned|superseded  → DONE
  // Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § Inherited doctrine
  if (type === 'plan') {
    if (status === 'deferred') return 'BLOCKED';
    if (status === 'implemented' || status === 'abandoned' || status === 'superseded') return 'DONE';
    // draft|reviewed|approved|executing → LIVE; unknown values → LIVE (open posture)
    return 'LIVE';
  }

  // --- Decision single-axis rule (tc-1 C4) ---
  // PURE single-axis: deployment_state is IGNORED for decision (decisions have no deployment_state).
  // Frozen mapping (transcribed verbatim from tc-0 doctrine table):
  //   proposed                   → LIVE
  //   accepted|deprecated|superseded → DONE
  // Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § Inherited doctrine
  if (type === 'decision') {
    if (status === 'accepted' || status === 'deprecated' || status === 'superseded') return 'DONE';
    // proposed → LIVE; unknown values → LIVE (open posture)
    return 'LIVE';
  }

  // --- Queue types: debt / bug / improvement (tc-2) ---
  // Liveness table (canonical-artifact-shapes.md § tc-2, implemented this session):
  //   open      → LIVE
  //   deferred  → BLOCKED
  //   closed    → DONE
  //   wontfix   → DONE  (wontfix is formally bug-only but mapped here for all queue types)
  // Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § C4.
  if (type === 'debt' || type === 'bug' || type === 'improvement') {
    if (status === 'closed' || status === 'wontfix') return 'DONE';
    if (status === 'deferred') return 'BLOCKED';
    // open (or unknown) → LIVE (open posture)
    return 'LIVE';
  }

  // --- Lesson liveness (C3b, stored-status mapping) ---
  // Status is stored in YAML frontmatter — not derived from prose markers.
  //   applied | closed | resolved → DONE
  //   deferred                    → BLOCKED
  //   open | triaged | unknown    → LIVE  (triaged = in-triage, not blocked)
  // Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3b.
  if (type === 'lesson') {
    if (status === 'applied' || status === 'closed' || status === 'resolved') return 'DONE';
    if (status === 'deferred') return 'BLOCKED';
    // open | triaged | unknown → LIVE
    return 'LIVE';
  }

  // --- Roadmap single-axis rule (example-initiative example-workstream example-repo Ask 1) ---
  // shipped | archived → DONE
  // planning | active | blocked → LIVE (blocked = in-flight, NOT done)
  // unknown values → LIVE (open posture)
  // Review: code-reviewer F17 — NEGATIVE SPEC: roadmap status='blocked' (in-flight dependency
  // block) maps to liveness LIVE, NOT to liveness BLOCKED. The liveness enum value BLOCKED is
  // reserved for handoffs awaiting a gate (deployment_state: awaiting_gate). A --where
  // liveness=BLOCKED filter will NOT return blocked roadmap items by design.
  if (type === 'roadmap') {
    if (status === 'shipped' || status === 'archived') return 'DONE';
    // planning | active | blocked → LIVE
    return 'LIVE';
  }

  // --- Tracker single-axis rule (example-initiative example-workstream example-repo Ask 5 promote) ---
  // archived → DONE; active → LIVE; unknown → LIVE
  if (type === 'tracker') {
    if (status === 'archived') return 'DONE';
    return 'LIVE';
  }

  // --- Health-status single-axis rule (example-initiative example-workstream example-repo Ask 5 promote) ---
  // Liveness keys on fm.status (lifecycle), NOT on fm.health (posture).
  // archived → DONE; active → LIVE; unknown → LIVE
  if (type === 'health-status') {
    if (status === 'archived') return 'DONE';
    return 'LIVE';
  }

  // --- Decision-guide single-axis rule ---
  // Consolidated/distilled terminal shape of a DR corpus (container document).
  // Liveness keys on document currency (status), NOT per-decision lifecycle.
  // Spec backlink: cross-repo/inbox/2026-06-27-example-stats-repo-decision-records-fleet-share.md § Q2
  if (type === 'decision-guide') {
    if (status === 'archived') return 'DONE';
    return 'LIVE';
  }

  // --- Graceful default for remaining types (tc-3 will wire their enums) ---
  // Uses TERMINAL_STATUS so any type carrying 'consumed' or 'superseded' resolves
  // DONE.  Types without a status (e.g. handoff-ledger) resolve LIVE.  This is
  // intentionally permissive — the design-complete mapping in the doctrine wiki
  // is the authoritative spec; tc-3 will wire their enums explicitly.
  if (TERMINAL_STATUS.has(status)) return 'DONE';
  return 'LIVE';
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
// Roadmap status normalization
// ---------------------------------------------------------------------------
// coordinator:roadmap-planning uses a richer lifecycle vocabulary (e.g. `final-approved`,
// `draft`, `in-review`, `approved`) that is NOT in the contract enum
// [planning, active, blocked, shipped, archived]. Rather than rewrite roadmap
// OVERVIEW frontmatter (owned by coordinator:roadmap-planning), we normalize at the
// query/validate layer before enum-validation fires.
//
// ORDERING (the Director of Engineering F6): must run BEFORE validateFrontmatter in validateAllRecords AND
// before liveness() in queryRecords — both callers invoke normalizeRoadmapStatus()
// immediately after applyConsumedMarker().
//
// Map: roadmap-planning lifecycle → nearest contract enum value.
// Unmapped values → 'active' (open posture, safe default).
// Spec backlink: docs/plans/2026-06-27-emit-new-record-types-producer-wiring.md § A3 (chunk A3)
const _ROADMAP_STATUS_MAP = {
  // roadmap-planning terminal-approved forms → active (approved + in-progress)
  'final-approved': 'active',
  'approved':       'active',
  // draft / in-review → planning (pre-approval)
  'draft':          'planning',
  'in-review':      'planning',
  // contract values pass through unchanged (identity; listed for clarity)
  'planning':       'planning',
  'active':         'active',
  'blocked':        'blocked',
  'shipped':        'shipped',
  'archived':       'archived',
};

/**
 * Normalize roadmap frontmatter status to the contract enum in-place.
 * No-op for non-roadmap types.
 * @param {object} frontmatter  Frontmatter object (mutated in place).
 * @param {string} type         Query type string (e.g. 'roadmap').
 */
function normalizeRoadmapStatus(frontmatter, type) {
  if (type !== 'roadmap') return;
  const raw = frontmatter.status;
  if (raw === undefined || raw === null) return;
  const mapped = _ROADMAP_STATUS_MAP[String(raw)];
  // mapped is the contract-conformant value; unmapped falls back to 'active'.
  frontmatter.status = mapped !== undefined ? mapped : 'active';
}

// ---------------------------------------------------------------------------
// Lesson parser (C3b: per-file YAML format)
// ---------------------------------------------------------------------------
/**
 * Parse a single lesson YAML file into a record object.
 * Fields (title/scope/created/evidence/target_wiki/status/from_repo) are read
 * directly from YAML frontmatter — not regex-derived from prose markers.
 * Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3b.
 * @param {string} filePath  Absolute path to a state/lessons/<id>.yaml file.
 * @param {string} root      Repo root (used to build the repo-relative record path).
 * @returns {{ path: string, frontmatter: object } | null}
 */
function parseLessonsFile(filePath, root) {
  if (!fs.existsSync(filePath)) return null;
  let content;
  try { content = fs.readFileSync(filePath, 'utf8'); } catch { return null; }
  let frontmatter;
  try { frontmatter = _parseYaml(content); } catch { return null; }
  if (!frontmatter) return null;
  const relPath = path.relative(root, filePath).replace(/\\/g, '/');
  return { path: relPath, frontmatter };
}

// ---------------------------------------------------------------------------
// Handoff-ledger parser
// ---------------------------------------------------------------------------
/**
 * Parse all `## Session Ledger` table blocks from a handoff body.
 * Returns one synthetic record per block, with path fragment #ledger-N to
 * disambiguate multiple blocks in one file (the Staff Engineer F5 multi-ledger requirement).
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
    // Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3b.
    // Source: state/lessons/*.yaml (one YAML file per lesson; fields from frontmatter).
    const lessonFiles = walkGlob(root, 'state/lessons/*.yaml');
    records = [];
    for (const file of lessonFiles) {
      const r = parseLessonsFile(file, root);
      if (r) records.push(r);
    }
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
  } else if (opts.type === 'research-claim') {
    // Synthetic type: docs/research/*.claims.json — N claim objects per file → N records.
    // Mirrors the handoff-ledger pattern (N synthetic records per source file).
    // The generic path calls parseFrontmatter which finds nothing in JSON files and
    // silently skips them; this dedicated branch parses the JSON array directly.
    // Spec backlink: docs/plans/2026-06-30-deep-research-queryable-index-layer.md § P1-3
    const claimGlob = TYPE_TO_GLOB['research-claim'] || 'docs/research/*.claims.json';
    const claimFiles = walkGlob(root, claimGlob);
    records = [];
    for (const file of claimFiles) {
      let content;
      try { content = fs.readFileSync(file, 'utf8'); } catch { continue; }
      const relPath = path.relative(root, file).replace(/\\/g, '/');
      let claims;
      // Review: code-reviewer Slice-A — (F4) silent parse failure hides producer bugs;
      // warn to stderr (matches --type plan anomaly-detector posture).
      try { claims = JSON.parse(content); } catch (e) { process.stderr.write(`query-records: failed to parse claims JSON: ${relPath}: ${e.message}\n`); continue; }
      if (!Array.isArray(claims)) continue;
      for (let idx = 0; idx < claims.length; idx++) {
        const claim = claims[idx];
        if (!claim || typeof claim !== 'object') continue;
        // Flatten each claim's fields as frontmatter so --where/--since/--sort compose on them.
        records.push({
          path: `${relPath}#claim-${idx}`,
          frontmatter: { ...claim },
        });
      }
    }
  } else {
    let files = walkGlob(root, glob);
    // Generalized sibling-exclusion: drop files whose best-match schema (from the
    // specificity-sorted _byGlob in schema.js) differs from this query type's own schema.
    // Purpose: prevents broader globs from over-matching co-located more-specific siblings.
    // Example: research-synthesis (docs/research/*.md) must not return coverage-audit
    //   (docs/research/*-coverage-audit.md) or gap-report (docs/research/*-gap-report.md) files.
    // Applies generically to ANY type with co-located sibling schemas — not hardcoded to research.
    // The plan type's existing suffix-regex exclusion provides complementary defense in depth;
    // both filters coexist and the plan sidecar block remains for its anomaly-detector logic.
    // Spec backlink: docs/plans/2026-06-30-deep-research-queryable-index-layer.md § P1-1
    if (_MODULE_SCHEMAS && _MODULE_SCHEMAS._byGlob && _MODULE_SCHEMAS._byGlob.length > 0) {
      const expectedSchemaName = _queryTypeToSchemaName(opts.type);
      files = files.filter(f => {
        const rel = path.relative(root, f).replace(/\\/g, '/');
        const m = matchSchemaForPath(rel, _MODULE_SCHEMAS);
        return !(m && m.schemaName !== expectedSchemaName);
      });
    }
    // Absence-as-signal: completion queries skip the legacy/ monolith bucket.
    // Glob `archive/completed/*/*.md` matches `archive/completed/legacy/<month>.md`
    // because legacy is a valid `*` segment; the migration helper preserves these
    // pre-Phase-1 monoliths but they are not per-entry records and must not pollute
    // results.
    if (opts.type === 'completion') {
      files = files.filter(f => !f.replace(/\\/g, '/').includes('/archive/completed/legacy/'));
    }
    // Sidecar exclusion for --type plan — single positive suffix layer + anomaly detector.
    //
    // After the tc-1 C9 broadsword port ALL sidecar files are in canonical suffix form
    // (*.review.md, *.prior-art-check.md, *.plan-coverage-check.md, *.docs-check.md),
    // so a single filename-regex layer derived from the sidecar schema applies_to globs
    // is sufficient and exhaustive. The former Layer-2 kind-fallback denylist and the
    // .md.-embedding heuristic are retired (dead code after C9).
    //
    // Anomaly detector (the Staff Engineer F2 / detect-then-fail-loud doctrine): any docs/plans/*.md
    // matching NEITHER a canonical sidecar suffix NOR the canonical plan filename pattern
    // (YYYY-MM-DD-<slug>.md) is excluded with a stderr warning — warn-not-block posture,
    // never silently include on uncertainty. Provides defense-in-depth for future
    // non-conforming files without requiring a new denylist entry.
    //
    // Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C4
    // Review: code-reviewer slice-B F6 — _PLAN_SIDECAR_DATA is always truthy (object); dead guard removed.
    if (opts.type === 'plan') {
      const { regexes: sidecarRegexes } = _PLAN_SIDECAR_DATA;
      // Canonical plan filename: YYYY-MM-DD-<slug>.md where slug is lowercase alpha/digits/hyphens.
      // Review: code-reviewer F10 — use module-scope _CANONICAL_PLAN_RE / _REVIEW_ITERATION_RE.
      // Recognized REVIEW sidecar iteration form: <stem>.review-N.md (N = one or more digits).
      // Second/Nth distinct-reviewer sidecars carry the reviewer in frontmatter; the numeric suffix
      // disambiguates the file on disk (e.g. <stem>.review-2.md for the second reviewer).
      // Excluded silently — same treatment as *.review.md from the sidecar regex layer — NOT
      // routed through the anomaly-warn path.
      // Spec backlink: docs/plans/2026-06-25-example-initiative-tc-1-records-consolidation.md § C9b
      files = files.filter(f => {
        const basename = path.basename(f);
        // Single positive layer: exclude files whose basename matches a canonical sidecar suffix.
        if (sidecarRegexes.some(re => re.test(basename))) return false;
        // Recognized REVIEW sidecar iteration (.review-N.md): exclude silently, no anomaly warn.
        if (_REVIEW_ITERATION_RE.test(basename)) return false;
        // Directory-index README.md: silently excluded — not a plan record, not an anomaly.
        // Spec backlink: example-initiative example-workstream example-repo Ask 4 (README slips through _CANONICAL_PLAN_RE
        // and would trigger the anomaly-warn path; excluded here before that check fires).
        if (/^readme\.md$/i.test(basename)) return false;
        // Anomaly detector: exclude anything that is neither sidecar nor canonical plan.
        if (!_CANONICAL_PLAN_RE.test(basename)) {
          process.stderr.write(
            `query-records: unclassified docs/plans file ${basename} — excluded from --type plan; ` +
            `conform to canonical plan or sidecar shape\n`
          );
          return false;
        }
        return true;
      });
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
      normalizeRoadmapStatus(frontmatter, opts.type);
      // Inject synthetic liveness field so --where liveness= and --format json
      // both work without modifying matchesClause or formatRecords.
      // Spec backlink: docs/wiki/canonical-artifact-shapes.md § C3
      frontmatter.liveness = liveness(frontmatter, opts.type);
      records.push({ path: relPath, frontmatter });
    }
  }

  // Review: code-reviewer S2-F2 — lesson and handoff-ledger branches did not inject
  // frontmatter.liveness; the else branch injects per-record inside its loop. Add a
  // shared post-processing step so --where liveness= and --format json work for ALL
  // three paths. The graceful default in liveness() means handoff-ledger records
  // (no status) resolve LIVE, matching the documented graceful default.
  if (opts.type === 'lesson' || opts.type === 'handoff-ledger' || opts.type === 'research-claim') {
    for (const r of records) {
      if (r.frontmatter) r.frontmatter.liveness = liveness(r.frontmatter, opts.type);
    }
  }

  // Apply --unattached predicate: keep only records where initiative is null/absent.
  // absent≡null per spec: a missing initiative field is treated identically to initiative:null.
  // Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C3 (AC4)
  if (opts.unattached) {
    records = records.filter(r => {
      if (!r.frontmatter) return false;
      const init = r.frontmatter.initiative;
      return init === null || init === undefined;
    });
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
// Unattached multi-type union lens
// ---------------------------------------------------------------------------
/**
 * Multi-type unattached lens: union --unattached results across all UNATTACHED_TYPES.
 *
 * Returns every record whose initiative frontmatter is null/absent, spanning
 * queues (bug/debt/improvement) + roadmap spinoff-stubs + handoffs + plans.
 * Set-difference computed in place; no new store.
 *
 * Each returned record is annotated with `_type` (the source query type) so
 * formatRecords can apply the correct per-type display function.
 *
 * --sort and --limit are applied to the union (not per-type) so the final
 * result is globally ordered and capped.  Per-type queryRecords calls suppress
 * sort+limit to avoid premature truncation and redundant sorting.
 *
 * Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C3 (AC4)
 *
 * @param {object} opts   Parsed CLI options (unattached:true, type:null).
 * @param {string} root   Repo root (absolute path).
 * @returns {{ path: string, frontmatter: object, _type: string }[]}
 */
function queryUnattachedAll(opts, root) {
  const all = [];

  for (const qtype of UNATTACHED_TYPES) {
    // Suppress per-type sort and limit so both are applied once to the union.
    const typeOpts = { ...opts, type: qtype, limit: 0, sort: null };
    let records;
    try {
      records = queryRecords(typeOpts, root);
    } catch (e) {
      // Tolerate absent type directories or other per-type errors — continue.
      // Review: code-reviewer — F7 (P2): emit a warning so operators can diagnose missing types.
      // Matches the pattern used by queryFleet for similar per-type errors.
      process.stderr.write(`query-records --unattached: skipping type "${qtype}" — ${e.message}\n`);
      continue;
    }
    for (const r of records) {
      all.push({ ...r, _type: qtype });
    }
  }

  // Apply --sort to the union.
  if (opts.sort) {
    const desc = opts.sort.startsWith('-');
    const field = desc ? opts.sort.slice(1) : opts.sort;
    all.sort((a, b) => {
      const av = a.frontmatter ? (a.frontmatter[field] ?? '') : '';
      const bv = b.frontmatter ? (b.frontmatter[field] ?? '') : '';
      const cmp = compareValues(String(av), String(bv));
      return desc ? -cmp : cmp;
    });
  }

  // Apply --limit to the union.
  if (opts.limit && opts.limit > 0) {
    return all.slice(0, opts.limit);
  }
  return all;
}

// ---------------------------------------------------------------------------
// Output formatting
// ---------------------------------------------------------------------------
/**
 * Format queried records for output (markdown-list / json / paths).
 *
 * Spec backlink: cross-repo/inbox/2026-07-01-refresh-queries-relative-path-bug.md
 *
 * @param {object[]} records  Query results; each record's `.path` is repo-root-relative.
 * @param {object} opts       Parsed query-spec opts (format/type).
 * @param {object} [linkCtx]  { root, fromDir } — when both are provided, markdown-list link
 *   targets are rewritten via path.relative(fromDir, path.resolve(root, r.path)) so they
 *   resolve correctly regardless of how deep the embedding file (fromDir) lives relative to
 *   repo root (root) — link resolution is relative to the containing file's directory, not
 *   repo root. Absent (undefined) preserves the prior repo-root-relative behavior — used by
 *   the query-records CLI's own stdout output, which has no "containing file" to be
 *   depth-correct against. Fragment-suffixed synthetic paths (`research-claim`,
 *   `handoff-ledger` — `.path` = "<real-path>#claim-N" / "#ledger-N") are handled: the
 *   `#fragment` is split off before path.resolve/relative and reattached after, since
 *   path.resolve/relative have no concept of URL fragments and would otherwise corrupt
 *   the link target. Review: code-reviewer — Finding 1 (P1).
 */
function formatRecords(records, opts, linkCtx) {
  switch (opts.format) {
    case 'json':
      return JSON.stringify(records, null, 2);
    case 'paths':
      return records.map(r => r.path).join('\n');
    case 'markdown-list':
    default: {
      // When opts.type is set, use a single display function for all records.
      // When opts.type is null (multi-type --unattached lens), use per-record _type lookup
      // so each record renders with its own type's display format.
      const globalDisplayFn = opts.type ? TYPE_DISPLAY[opts.type] : null;
      return records.map(r => {
        const fn = globalDisplayFn
          || (r._type && TYPE_DISPLAY[r._type])
          || ((p, fm) => `- [${fm.title || p}](${p})`);
        // Negative-spec: do NOT hard-code a repo-root-relative prefix here — the embedding
        // file's depth varies per callout location (docs/roadmap/STUB-INDEX.md vs.
        // state/roadmap/<x>/STUB-INDEX.md), so a single fixed prefix cannot be correct for
        // all of them. path.relative recomputes per fromDir, per record.
        //
        // Review: code-reviewer — Finding 1 (P1). r.path for synthetic types (research-claim,
        // handoff-ledger) is "<real-path>#claim-N" / "#ledger-N" — a URL fragment, not a
        // filesystem path segment. path.resolve/relative have no fragment concept and would
        // treat "#ledger-0" as a literal trailing path component, corrupting the link. Split
        // off the fragment before resolve/relative and reattach it to the computed link.
        let linkPath = r.path;
        if (linkCtx && linkCtx.root && linkCtx.fromDir) {
          const hashIdx = r.path.indexOf('#');
          const pathPart = hashIdx === -1 ? r.path : r.path.slice(0, hashIdx);
          const fragment = hashIdx === -1 ? '' : r.path.slice(hashIdx);
          linkPath = path.relative(linkCtx.fromDir, path.resolve(linkCtx.root, pathPart)).replace(/\\/g, '/') + fragment;
        }
        return fn(linkPath, r.frontmatter);
      }).join('\n');
    }
  }
}

// ---------------------------------------------------------------------------
// Conformance signal — batch validate-all mode
// ---------------------------------------------------------------------------
/**
 * Build a reverse map from query-type name → schema name using the same logic
 * as _buildTypeToGlob Part 1 (but producing the schema name, not the glob).
 *
 * Types without a schema (lesson, handoff-ledger, debt, bug, improvement) will
 * be absent from the returned map; the caller skips them via `if (!schemaName)`.
 *
 * Spec backlink: archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk A2
 *
 * @param {object} schemas  Result of loadSchemas() — has ._byGlob.
 * @returns {object}  { [queryType]: schemaName }
 */
function _buildTypeToSchemaNameMap(schemas) {
  const map = {};
  for (const { schemaName } of schemas._byGlob) {
    // Use the same name-mapping as _buildTypeToGlob Part 1:
    // 'lesson-entry' → null (skip); 'completion-entry' → 'completion'; others → identity.
    const queryType = _SCHEMA_NAME_TO_QUERY_TYPE.hasOwnProperty(schemaName)
      ? _SCHEMA_NAME_TO_QUERY_TYPE[schemaName]
      : schemaName;
    if (queryType === null) continue; // lesson-entry: skip (special inline-tag type)
    map[queryType] = schemaName;
  }

  // Short-form queue-type aliases (debt/bug/improvement) are added to TYPE_TO_GLOB in
  // _buildTypeToGlob Part 2 as UX convenience keys, but they have no corresponding
  // schema entry — schemas use the long names (debt-backlog/bug-backlog/improvement-queue).
  // Without the entries below, --validate-all --type debt silently skips validation
  // because typeToSchemaName['debt'] is undefined and the guard `if (!schemaName) continue`
  // fires. Map them explicitly so the scoped path resolves to the correct schema.
  //
  // Double-validation hazard: in bulk --validate-all (no --type), TYPE_TO_GLOB contains
  // both 'debt-backlog' AND 'debt' (same glob). Both would now resolve to a schema.
  // validateAllRecords() guards against this with a seenGlobs Set — the long key processes
  // first (it appears earlier in TYPE_TO_GLOB), marks the glob seen, and the short alias
  // is skipped when its turn arrives.
  map['debt']        = 'debt-backlog';
  map['bug']         = 'bug-backlog';
  map['improvement'] = 'improvement-queue';

  return map;
}

/**
 * Batch conformance validator — walks every record of every registry type (or just
 * the scoped type when opts.type is set) and runs each through validateFrontmatter
 * (which internally calls applyCrossFieldRules). Emits a per-record drift ledger.
 *
 * Persistent counterpart to the ephemeral per-write warn-hook (A2 design).
 *
 * Interface contract (pinned — A3b authors validate-handoff.js wrapper against this):
 *   CLI: --validate-all [--type <type>] [--root <path>]
 *   Exit code: nonzero when ANY record has verdict='drift'.
 *   Output: JSON array of { type, path, verdict: 'ok'|'drift', errors: [...] } to stdout.
 *
 * Spec backlink: archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk A2 / AC2
 * Design decision: D4 — general --validate-all is the single corpus validation source of truth;
 *   validate-handoff.js (A3b) wraps this, not a parallel implementation.
 * Design decision: D5 — reuses schema.js validateFrontmatter + applyCrossFieldRules;
 *   no forked schema loader.
 *
 * Negative-spec: does NOT change existing query / fleet behavior.
 *
 * @param {object} opts  Parsed CLI options (validateAll:true; type optional).
 * @param {string} root  Repo root to validate against (absolute path).
 * @returns {{ ledger: object[], hasDrift: boolean }}
 */
function validateAllRecords(opts, root) {
  // Load schemas fresh (single source of truth — schema loader is not forked).
  const schemas = loadSchemas(_SCHEMAS_DIR);
  const typeToSchemaName = _buildTypeToSchemaNameMap(schemas);

  // Types to validate: all known query types when --type is absent; single type when present.
  const typesToValidate = opts.type ? [opts.type] : Object.keys(TYPE_TO_GLOB);

  const ledger = [];
  let hasDrift = false;

  // C6 GAP1 perf (code-reviewer F5) — prime the git-history cache lazily, at
  // most ONCE per validateAllRecords invocation, on first use by the
  // reachability sweep loop below. Deferred (not primed unconditionally here)
  // so a --type run that never reaches handoff/handoff-archived (the only
  // qtypes that call checkLineageReachability) never pays the prime-pass cost.
  // null sentinel distinguishes "not yet primed" from "primed, git failed" —
  // both fall back to per-call resolution in checkLineageReachability's
  // gitHistoryCache-absent path (buildGitHistoryCache returns null on git
  // failure, which is passed straight through unchanged).
  let _gitHistoryCache;
  let _gitHistoryCachePrimed = false;
  function getGitHistoryCache() {
    if (!_gitHistoryCachePrimed) {
      _gitHistoryCachePrimed = true;
      _gitHistoryCache = _buildGitHistoryCache ? _buildGitHistoryCache(root) : null;
    }
    return _gitHistoryCache;
  }

  // Glob-level dedup: short aliases (debt/bug/improvement) and their long counterparts
  // (debt-backlog/bug-backlog/improvement-queue) both resolve to the same glob.  In bulk
  // mode (typesToValidate = Object.keys(TYPE_TO_GLOB)) both keys iterate; without dedup
  // each file would be validated twice.  Long-name keys appear earlier in TYPE_TO_GLOB
  // (schema-derived, Part 1) than short aliases (supplement, Part 2), so they win the
  // first-seen slot and short aliases are skipped harmlessly.
  const seenGlobs = new Set();

  for (const qtype of typesToValidate) {
    // Skip synthetic / non-frontmatter types — covers: lesson (supplement-only, no per-record
    // schema), handoff-ledger (no schema), lesson-entry (null mapped — whole-file validator),
    // and any other type that has no schema entry.
    // Review: code-reviewer Slice-C — (C-F3) the explicit lesson/handoff-ledger guard below
    //   was unreachable because both are caught here: neither resolves in typeToSchemaName.
    const schemaName = typeToSchemaName[qtype];
    if (!schemaName) continue;

    const schema = schemas[schemaName];
    if (!schema) continue;

    const glob = TYPE_TO_GLOB[qtype];
    if (!glob) continue;

    // Dedup: skip if this glob has already been processed (handles short/long alias pairs).
    if (seenGlobs.has(glob)) continue;
    seenGlobs.add(glob);

    // research-claim: synthetic JSON-array type — each .claims.json file is a JSON array;
    // emit one ledger entry per claim object. Mirrors the queryRecords research-claim branch.
    // Must be handled before the generic walkGlob+parseFrontmatter path because parseFrontmatter
    // returns null for JSON content, which would silently skip all claims.
    // Spec backlink: docs/plans/2026-06-30-deep-research-queryable-index-layer.md § P1-3
    if (qtype === 'research-claim') {
      const claimFiles = walkGlob(root, glob);
      for (const file of claimFiles) {
        const relPath = path.relative(root, file).replace(/\\/g, '/');
        let content;
        try { content = fs.readFileSync(file, 'utf8'); } catch { continue; }
        let claims;
        // Review: code-reviewer Slice-A — (F4) silent parse failure hides producer bugs;
        // warn to stderr (matches --type plan anomaly-detector posture).
        try { claims = JSON.parse(content); } catch (e) { process.stderr.write(`query-records: failed to parse claims JSON: ${relPath}: ${e.message}\n`); continue; }
        if (!Array.isArray(claims)) continue;
        for (let idx = 0; idx < claims.length; idx++) {
          const claim = claims[idx];
          if (!claim || typeof claim !== 'object') continue;
          const result = validateFrontmatter(claim, schema);
          const verdict = result.ok ? 'ok' : 'drift';
          if (!result.ok) hasDrift = true;
          ledger.push({ type: schemaName, path: `${relPath}#claim-${idx}`, verdict, errors: result.errors || [] });
        }
      }
      continue; // handled above; skip the generic parseFrontmatter path
    }

    let files = walkGlob(root, glob);
    // Generalized sibling-exclusion: drop files whose best-match schema differs from this
    // type's schema. Prevents research-synthesis from validating coverage-audit/gap-report
    // siblings that share the docs/research/*.md glob. Mirrors the queryRecords sibling-exclusion.
    // Spec backlink: docs/plans/2026-06-30-deep-research-queryable-index-layer.md § P1-1
    files = files.filter(f => {
      const rel = path.relative(root, f).replace(/\\/g, '/');
      const m = matchSchemaForPath(rel, schemas);
      return !(m && m.schemaName !== schemaName);
    });

    for (const file of files) {
      const relPath = path.relative(root, file).replace(/\\/g, '/');
      let content;
      try { content = fs.readFileSync(file, 'utf8'); } catch { continue; }

      // Parse frontmatter — .yaml files are whole-file YAML; .md files use --- delimiters.
      let frontmatter;
      if (path.extname(file) === '.yaml') {
        try { frontmatter = _parseYaml(content); } catch { frontmatter = null; }
      } else {
        ({ frontmatter } = parseFrontmatter(content));
      }

      if (!frontmatter) {
        // No parseable frontmatter — skip silently (same posture as queryRecords).
        continue;
      }

      // cross-repo-memo: apply the same memo-shape guard as queryRecords (from+to required).
      if (qtype === 'cross-repo-memo' && (!frontmatter.from || !frontmatter.to)) continue;

      // plan type: exclude sidecar files (reuse _PLAN_SIDECAR_DATA) and legacy non-plan files.
      if (qtype === 'plan') {
        const basename = path.basename(file);
        const { regexes: sidecarRegexes } = _PLAN_SIDECAR_DATA;
        // Review: code-reviewer F10 — use module-scope _CANONICAL_PLAN_RE / _REVIEW_ITERATION_RE.
        if (sidecarRegexes.some(re => re.test(basename))) continue;
        if (_REVIEW_ITERATION_RE.test(basename)) continue;
        // Directory-index README.md: silently excluded — not a plan record (mirrors queryRecords logic).
        if (/^readme\.md$/i.test(basename)) continue;
        if (!_CANONICAL_PLAN_RE.test(basename)) continue;
      }

      // completion type: skip the legacy/ monolith bucket (same as queryRecords).
      if (qtype === 'completion') {
        if (file.replace(/\\/g, '/').includes('/archive/completed/legacy/')) continue;
      }

      // Roadmap status normalization — must run before validateFrontmatter so
      // coordinator:roadmap-planning lifecycle values (e.g. 'final-approved') are
      // mapped to contract-enum values before the enum-validation gate fires.
      // Normalization runs at the same gate position (before validateFrontmatter)
      // as in queryRecords; applyConsumedMarker is not applicable in this path.
      // Review: code-reviewer slice-1 F4 — prior comment claimed consumed-marker ordering
      // parity but validateAllRecords never calls applyConsumedMarker; rewording clarifies.
      // Spec backlink: § A3 (chunk A3).
      normalizeRoadmapStatus(frontmatter, qtype);

      // Run through validateFrontmatter — which internally calls applyCrossFieldRules.
      const result = validateFrontmatter(frontmatter, schema);
      let errors = result.errors || [];
      let recordOk = result.ok;

      // C6 GAP1 — lineage-reachability sweep (handoff + handoff-archived only).
      // Same rule kernel the C2 write-time hook applies (walk-handoff-dag.js
      // checkLineageReachability) — reuses _resolveTarget's git-history-aware
      // three-tier resolution, not a live∪archive-on-disk-only check, so an
      // archive-relocation-stranded predecessor is NOT flagged as corruption
      // (cockpit F1/F3). handoffDir is the record's OWN containing directory
      // (path.dirname(file)) — correct for both flat state/handoffs/ and
      // month-foldered archive/handoffs/YYYY-MM/ records, since a record's
      // relative predecessor is conventionally resolved relative to repoRoot
      // by _resolveTarget's candidate search regardless of the passed dir.
      // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2, § C6 (GAP1)
      if (_checkLineageReachability && (qtype === 'handoff' || qtype === 'handoff-archived')) {
        const reachabilityViolations = _checkLineageReachability(
          frontmatter, root, path.dirname(file), relPath, getGitHistoryCache()
        );
        if (reachabilityViolations.length > 0) {
          recordOk = false;
          errors = errors.concat(reachabilityViolations.map(v => ({
            field: v.field,
            error: `lineage-reachability: "${v.value}" — ${v.reason}`,
          })));
        }
      }

      const verdict = recordOk ? 'ok' : 'drift';
      if (!recordOk) hasDrift = true;

      // Review: code-reviewer Slice-C — (C-F2) emit canonical long-form schema name in BOTH
      //   bulk and scoped modes; using qtype emitted 'debt' in scoped mode but 'debt-backlog'
      //   in bulk (long key wins seenGlobs race), breaking the A3b validate-handoff.js contract.
      ledger.push({
        type: schemaName,
        path: relPath,
        verdict,
        errors,
      });
    }
  }

  return { ledger, hasDrift };
}

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------
if (require.main === module) {
  const opts = parseArgs(process.argv);

  if (opts.fleet) {
    // Fleet mode: union per-repo query results across the machine-local repos registry.
    // --root is ignored (fleet mode resolves roots via the registry).
    // Output is always JSON (fleet view is a machine-readable contract surface).
    //
    // Test-isolation hook: QUERY_RECORDS_FLEET_CURRENT_ROOT overrides the git-root
    // discovery used as the rung-2 sibling-relative base. Allows tests to create
    // fixture repos as siblings of a temp dir without touching the real registry.
    const currentRoot = process.env.QUERY_RECORDS_FLEET_CURRENT_ROOT
      ? path.resolve(process.env.QUERY_RECORDS_FLEET_CURRENT_ROOT)
      : detectRoot(null);
    const fleetResult = queryFleet(opts, currentRoot);
    process.stdout.write(JSON.stringify(fleetResult, null, 2) + '\n');
  } else if (opts.validateAll) {
    // Batch conformance mode — walk every record of every type (or the scoped type)
    // and emit a machine-readable drift ledger. Exit nonzero on any drift.
    // Output: JSON array of { type, path, verdict, errors[] } to stdout.
    //
    // Interface contract (A3b pins this):
    //   --validate-all [--type <type>] [--root <path>]
    //   exit 0: no drift; exit 1: at least one drift record.
    //
    // Spec backlink: archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk A2
    const root = detectRoot(opts.root);
    const { ledger, hasDrift } = validateAllRecords(opts, root);
    process.stdout.write(JSON.stringify(ledger, null, 2) + '\n');
    if (hasDrift) process.exit(1);
  } else if (opts.unattached && !opts.type) {
    // Multi-type unattached lens: union --unattached results across all UNATTACHED_TYPES.
    // --type absent triggers the spanning union; --type present uses the single-type path.
    // Spec backlink: docs/plans/2026-07-04-initiative-govern-sweep-prioritize-doe-d.md § C3 (AC4)
    const root = detectRoot(opts.root);
    const records = queryUnattachedAll(opts, root);
    // opts.type is null here; formatRecords uses per-record _type for markdown-list.
    const output = formatRecords(records, opts);
    if (output) {
      process.stdout.write(output + '\n');
    }
  } else {
    const root = detectRoot(opts.root);
    const records = queryRecords(opts, root);
    const output = formatRecords(records, opts);
    if (output) {
      process.stdout.write(output + '\n');
    }
  }
}

// Review: F7 — export TYPE_TO_GLOB so the drift-enforcement test can require it
// directly instead of parsing the 'Valid: ...' stderr of a deliberate invalid-type run.
// Review: code-reviewer slice-1 F1 — export normalizeRoadmapStatus for direct unit testing of
// each non-identity map entry (approved/draft/in-review/unknown) that e2e tests do not cover.
module.exports = { queryRecords, formatRecords, parseSince, parseWhereExpr, TYPE_TO_GLOB, liveness, validateAllRecords, normalizeRoadmapStatus, queryUnattachedAll, UNATTACHED_TYPES };
