#!/usr/bin/env node
'use strict';
/**
 * stamp-shipped-in.js — insert `shipped_in: <SHA>` into a handoff's frontmatter.
 *
 * Purpose: single-shot CLI invoked by coordinator-archive-stamp.sh at archive time
 * to stamp the workstream commit SHA into the handoff before `git mv` crosses the
 * state/ → archive/ boundary. Idempotent: skips silently when `shipped_in:` is
 * already present.
 *
 * Spec backlink: archive/completed/2026-06/2026-06-15-shipped-in-archive-stamping-a62b94.md § Chunk C1
 *
 * Usage:
 *   stamp-shipped-in.js --handoff <path> --sha <SHA>
 *
 * Exit codes:
 *   0 — success (field inserted or already present)
 *   1 — error (missing args, missing frontmatter, I/O failure)
 *
 * Write-side YAML frontmatter primitives (splitFrontmatter, readFmField,
 * insertFmField, serializeYamlScalar) are canonicalized in bin/lib/schema.js —
 * required below rather than duplicated locally.
 *
 * # `-in-SHA defense (the Staff Engineer F0 fix from normalize-consumed-frontmatter.js:127-130):
 *   SHA values containing `#` are YAML-quoted by serializeYamlScalar to prevent
 *   silent truncation (`shipped_in: abc123 #comment` → `shipped_in: abc123`).
 */

const fs = require('fs');
const path = require('path');
const { splitFrontmatter, readFmField, insertFmField } = require(path.join(__dirname, 'lib', 'schema.js'));

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = argv.slice(2);
  let handoffPath = null;
  let sha = null;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--handoff') {
      handoffPath = args[++i];
    } else if (a === '--sha') {
      sha = args[++i];
    } else if (a === '--help' || a === '-h') {
      process.stdout.write(
        'Usage: stamp-shipped-in.js --handoff <path> --sha <SHA>\n' +
        '\n' +
        'Inserts `shipped_in: <SHA>` into handoff frontmatter if absent.\n' +
        'Idempotent. Exit 0 on success or already-present; non-zero on error.\n'
      );
      process.exit(0);
    } else {
      process.stderr.write(`Unknown argument: ${a}\n`);
      process.exit(1);
    }
  }

  if (!handoffPath || !sha) {
    process.stderr.write(
      'Usage: stamp-shipped-in.js --handoff <path> --sha <SHA>\n' +
      'Error: --handoff and --sha are required.\n'
    );
    process.exit(1);
  }

  return { handoffPath, sha };
}

function main() {
  const { handoffPath, sha } = parseArgs(process.argv);

  let content;
  try {
    content = fs.readFileSync(handoffPath, 'utf8');
  } catch (err) {
    process.stderr.write(`stamp-shipped-in: cannot read "${handoffPath}": ${err.message}\n`);
    process.exit(1);
  }

  const split = splitFrontmatter(content);
  if (!split) {
    process.stderr.write(
      `stamp-shipped-in: "${handoffPath}" has no valid YAML frontmatter block.\n`
    );
    process.exit(1);
  }

  const existing = readFmField(split.fmText, 'shipped_in');
  if (existing !== null) {
    // key present (even if empty-valued) — idempotent no-op
    process.stderr.write(`stamp-shipped-in: shipped_in already present in "${handoffPath}" — skipping.\n`);
    process.exit(0);
  }

  // Insert `shipped_in:` after `consumed_at:` if present, else end of frontmatter.
  // This matches the placement logic in normalize-consumed-frontmatter.js:208.
  const newFmText = insertFmField(split.fmText, 'shipped_in', sha, 'consumed_at');

  const fmTextNormalized = newFmText.endsWith('\n') ? newFmText : newFmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmTextNormalized}---${split.bodyWithLeadingNewline}`;

  try {
    fs.writeFileSync(handoffPath, rebuilt, 'utf8');
  } catch (err) {
    process.stderr.write(`stamp-shipped-in: cannot write "${handoffPath}": ${err.message}\n`);
    process.exit(1);
  }

  process.stderr.write(`stamp-shipped-in: stamped shipped_in: ${sha} into "${handoffPath}".\n`);
  process.exit(0);
}

main();
