#!/usr/bin/env node
'use strict';
/**
 * lint-frontmatter.js — walk every schema'd path glob and validate frontmatter.
 *
 * Purpose: hard-fail belt for CI / /validate / /workday-complete. Any tracked record
 * that fails its schema is surfaced here; exits non-zero if any violations exist.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W1 Hard-fail Gate
 *
 * Usage:
 *   node bin/lint-frontmatter.js [--root <path>] [--schema <name>] [--list-schemas] [--json]
 *
 * Options:
 *   --root <path>      Repo root to walk. Defaults to git rev-parse --show-toplevel, then cwd.
 *   --schema <name>    Only check one schema by name.
 *   --list-schemas     Print schema names + globs and exit 0.
 *   --json             Emit JSON output: {ok, violations: [{file, schema, errors}]}.
 *
 * Exit codes:
 *   0  — all files valid (or --list-schemas)
 *   1  — one or more violations found
 *   2  — usage/configuration error
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const {
  loadSchemas,
  matchSchemaForPath,
  parseFrontmatter,
  validateFrontmatter,
  validateLessonsFile,
} = require('./lib/schema.js');

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { root: null, schema: null, listSchemas: false, json: false };
  for (let i = 2; i < argv.length; i++) {
    switch (argv[i]) {
      case '--root':       args.root = argv[++i]; break;
      case '--schema':     args.schema = argv[++i]; break;
      case '--list-schemas': args.listSchemas = true; break;
      case '--json':       args.json = true; break;
      default:
        process.stderr.write(`Unknown argument: ${argv[i]}\n`);
        process.exit(2);
    }
  }
  return args;
}

// ---------------------------------------------------------------------------
// Repo root detection
// ---------------------------------------------------------------------------

function findRepoRoot(hint) {
  if (hint) return path.resolve(hint);
  try {
    const result = execSync('git rev-parse --show-toplevel', { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] });
    return result.trim();
  } catch {
    return process.cwd();
  }
}

// ---------------------------------------------------------------------------
// File walker — finds all files matching a glob pattern under repoRoot.
// Only matches at the single-dir depth implied by the glob (not recursive
// unless the glob contains **).
// ---------------------------------------------------------------------------

function collectFilesForGlob(repoRoot, glob) {
  const { matchSchemaForPath: _match, _matchGlob } = require('./lib/schema.js');
  // Determine the fixed prefix directory from the glob (up to first *, **, or ?)
  const parts = glob.split('/');
  const fixedParts = [];
  for (const p of parts) {
    if (p.includes('*') || p.includes('?')) break;
    fixedParts.push(p);
  }

  const baseDir = path.join(repoRoot, ...fixedParts);
  const results = [];

  if (!fs.existsSync(baseDir)) return results;

  // Determine how deep to walk: if glob has ** we walk recursively; otherwise one level
  const hasDoubleStar = glob.includes('**');

  walkDir(baseDir, repoRoot, glob, hasDoubleStar, results);
  return results;
}

function walkDir(dir, repoRoot, glob, recursive, results) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    const repoRel = path.relative(repoRoot, fullPath).replace(/\\/g, '/');

    if (entry.isDirectory()) {
      if (recursive) {
        walkDir(fullPath, repoRoot, glob, recursive, results);
      }
    } else if (entry.isFile()) {
      if (globMatchesPath(glob, repoRel)) {
        results.push({ fullPath, repoRel });
      }
    }
  }
}

function globMatchesPath(glob, repoRel) {
  // Re-use the internal glob logic from schema.js via the exported _matchGlob
  const schema = require('./lib/schema.js');
  return schema._matchGlob(glob, repoRel);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const args = parseArgs(process.argv);
  const repoRoot = findRepoRoot(args.root);

  // Resolve schemas directory relative to this script's location
  const schemasDir = path.resolve(__dirname, '../schemas');

  if (!fs.existsSync(schemasDir)) {
    process.stderr.write(`schemas directory not found: ${schemasDir}\n`);
    process.exit(2);
  }

  const schemas = loadSchemas(schemasDir);

  // --list-schemas
  if (args.listSchemas) {
    const names = Object.keys(schemas).filter(k => k !== '_byGlob');
    const colW = Math.max(...names.map(n => n.length)) + 2;
    process.stdout.write(`Schemas (${names.length}) — loaded from ${schemasDir}\n`);
    for (const name of names) {
      const s = schemas[name];
      const glob = s.applies_to || '(no glob)';
      const mode = s.match_mode ? `[${s.match_mode}]` : '';
      process.stdout.write(`  ${name.padEnd(colW)}${glob}  ${mode}\n`);
    }
    process.exit(0);
  }

  // Determine which schemas to check
  const schemasToCheck = args.schema
    ? schemas[args.schema]
      ? [{ name: args.schema, schema: schemas[args.schema] }]
      : (() => { process.stderr.write(`Unknown schema: ${args.schema}\n`); process.exit(2); })()
    : Object.keys(schemas).filter(k => k !== '_byGlob').map(k => ({ name: k, schema: schemas[k] }));

  const violations = [];

  for (const { name, schema } of schemasToCheck) {
    const glob = schema.applies_to;
    if (!glob) continue;

    const isLessonSchema = schema.match_mode === 'inline-tag-per-entry';
    const files = collectFilesForGlob(repoRoot, glob);

    for (const { fullPath, repoRel } of files) {
      let content;
      try {
        content = fs.readFileSync(fullPath, 'utf8');
      } catch {
        violations.push({ file: repoRel, schema: name, errors: [{ field: '(read)', error: 'could not read file', hint: fullPath }] });
        continue;
      }

      if (isLessonSchema) {
        const result = validateLessonsFile(content, schema);
        if (!result.ok) {
          violations.push({ file: repoRel, schema: name, errors: result.errors });
        }
      } else {
        const { frontmatter } = parseFrontmatter(content);
        const result = validateFrontmatter(frontmatter, schema);
        if (!result.ok) {
          violations.push({ file: repoRel, schema: name, errors: result.errors });
        }
      }
    }
  }

  // Output
  if (args.json) {
    process.stdout.write(JSON.stringify({ ok: violations.length === 0, violations }, null, 2) + '\n');
  } else {
    if (violations.length === 0) {
      process.stdout.write(`lint-frontmatter: all files valid (root: ${repoRoot})\n`);
    } else {
      process.stdout.write(`lint-frontmatter: ${violations.length} violation(s) (root: ${repoRoot})\n\n`);
      for (const v of violations) {
        process.stdout.write(`  ${v.file}  [${v.schema}]\n`);
        for (const e of v.errors) {
          const loc = e.line ? `:${e.line}` : '';
          process.stdout.write(`    - ${e.field}${loc}: ${e.error}\n`);
          if (e.hint) {
            process.stdout.write(`      hint: ${e.hint}\n`);
          }
        }
      }
    }
  }

  process.exit(violations.length > 0 ? 1 : 0);
}

main();
