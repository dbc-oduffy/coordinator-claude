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
 * Spec backlink: docs/plans/2026-06-15-shipped-in-archive-stamping.md § Chunk C1
 *
 * Usage:
 *   stamp-shipped-in.js --handoff <path> --sha <SHA>
 *
 * Exit codes:
 *   0 — success (field inserted or already present)
 *   1 — error (missing args, missing frontmatter, I/O failure)
 *
 * Primitives lifted from normalize-consumed-frontmatter.js:
 *   splitFrontmatter, readFmField, insertFmField, serializeYamlScalar.
 *
 * # `-in-SHA defense (Patrik F0 fix from normalize-consumed-frontmatter.js:127-130):
 *   SHA values containing `#` are YAML-quoted by serializeYamlScalar to prevent
 *   silent truncation (`shipped_in: abc123 #comment` → `shipped_in: abc123`).
 */

const fs = require('fs');

// ---------------------------------------------------------------------------
// YAML frontmatter primitives (lifted from normalize-consumed-frontmatter.js)
// ---------------------------------------------------------------------------

/**
 * splitFrontmatter — parse a YAML frontmatter block from file content.
 * Returns { fmText, bodyWithLeadingNewline } or null if no valid frontmatter.
 */
function splitFrontmatter(content) {
  if (!content.startsWith('---')) return null;
  const afterFirst = content.slice(3);
  const firstNewline = afterFirst.indexOf('\n');
  if (firstNewline === -1) return null;
  const rest = afterFirst.slice(firstNewline + 1);
  // [ \t]* (not \s*) — \s eats newlines and would consume the body's leading blank line.
  const closeRe = /^---[ \t]*$/m;
  const closeMatch = closeRe.exec(rest);
  if (!closeMatch) return null;
  const fmText = rest.slice(0, closeMatch.index);
  const bodyStart = closeMatch.index + closeMatch[0].length;
  // Preserve everything after the closing --- including the trailing newline,
  // so the reassembled file is byte-identical except for the frontmatter edits.
  const bodyWithLeadingNewline = rest.slice(bodyStart);
  return { fmText, bodyWithLeadingNewline };
}

/**
 * readFmField — read a single-line YAML frontmatter field value by key.
 * Returns the trimmed value string, or null if the key is absent.
 * Assumes the key is not a prefix of any other frontmatter key in the schema.
 */
function readFmField(fmText, key) {
  const re = new RegExp(`^${key}:\\s*(.*?)\\s*$`, 'm');
  const m = re.exec(fmText);
  return m ? m[1].trim() : null;
}

/**
 * serializeYamlScalar — single-quote a YAML scalar value when it contains
 * characters that YAML would misinterpret as structure.
 *
 * # `-in-SHA defense (Patrik F0): unquoted values containing `#` are silently
 * truncated by YAML parsers (`shipped_in: abc123 #42` → `abc123`). Single-quote
 * the value when structural YAML characters are present; escape internal
 * single quotes by doubling (`'` → `''`).
 */
function serializeYamlScalar(value) {
  const needsQuoting = /[#:{}\[\],&*!|>"'%@`]/.test(value) ||
                       value.startsWith('-') ||
                       value.startsWith('?') ||
                       value.startsWith(' ');
  if (!needsQuoting) return value;
  return `'${value.replace(/'/g, "''")}'`;
}

/**
 * insertFmField — insert `key: value` immediately after the line matching `afterKey:`.
 * If afterKey is not present, appends to end of frontmatter.
 */
function insertFmField(fmText, key, value, afterKey) {
  const afterRe = new RegExp(`^${afterKey}:.*$`, 'm');
  const m = afterRe.exec(fmText);
  if (m) {
    const insertAt = m.index + m[0].length;
    return fmText.slice(0, insertAt) + `\n${key}: ${serializeYamlScalar(value)}` + fmText.slice(insertAt);
  }
  // Fallback: append (preserve trailing newline structure)
  const trimmed = fmText.replace(/\s+$/, '');
  return `${trimmed}\n${key}: ${serializeYamlScalar(value)}\n`;
}

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
  const rebuilt = `---\n${fmTextNormalized}---${split.bodyWithLeadingNewline}`;

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
