#!/usr/bin/env node
'use strict';
/**
 * plan-status-transition.js — atomic plan-lifecycle frontmatter transition (stamp-implemented).
 *
 * Purpose: the authorized writer of a plan's `status:` frontmatter field when a plan
 * finishes execution. Mirrors the arg-parsing/verb shape of handoff-transition.js /
 * memo-transition.js but is deliberately thin — a plan's lifecycle has exactly one
 * mutating transition today (flip to `implemented`), not the multi-verb machinery
 * handoffs/memos need.
 *
 * Usage:
 *   plan-status-transition.js stamp-implemented --plan <path>
 *
 * The `stamp-implemented` verb performs an atomic replace-not-append flip of the
 * plan's `status:` field to `implemented`:
 *   - status ∈ {draft, reviewed, approved, executing} → replaced with 'implemented'
 *   - status ∈ {implemented, superseded, abandoned, deferred} → NO-OP, exit 0
 *     (idempotent re-run + respects terminal/deferred states — does not resurrect
 *     a plan someone deliberately marked abandoned/deferred/superseded)
 *
 * Halt-safety note: this CLI does NOT special-case 'executing' — executing→implemented
 * DOES flip here. Any halt-mid-execution safety property belongs at the calling seam
 * (the thing that decides whether it's safe to declare a plan done), not this writer.
 *
 * Exit codes:
 *   0 — transition applied OR already-at-target/terminal no-op
 *   1 — error (bad args, missing --plan, file not found, missing/unparseable frontmatter)
 *
 * Frontmatter primitives are REQUIRED from bin/lib/schema.js (the reconciled shared
 * write-side module) — this is the first consumer of that shared surface; no local copy.
 *
 * Spec backlink: docs/plans referenced by the dispatching chunk (C1).
 */

const fs = require('fs');
const path = require('path');

const { splitFrontmatter, readFmField, replaceFmField } = require(path.join(__dirname, 'lib', 'schema.js'));

const TERMINAL_STATUSES = new Set(['implemented', 'superseded', 'abandoned', 'deferred']);
const FLIPPABLE_STATUSES = new Set(['draft', 'reviewed', 'approved', 'executing']);

function fail(msg) {
  process.stderr.write(`plan-status-transition: ${msg}\n`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const verb = args.length > 0 ? args[0] : null;
  const opts = { verb, plan: null };
  for (let i = 1; i < args.length; i++) {
    const a = args[i];
    const nextVal = () => { if (i + 1 >= args.length) fail('flag requires a value: ' + a); return args[++i]; };
    if (a === '--plan') opts.plan = nextVal();
    else fail(`unknown argument: ${a}`);
  }
  return opts;
}

function stampImplemented(opts) {
  if (!opts.plan) fail('stamp-implemented requires --plan <path>');
  if (!fs.existsSync(opts.plan)) fail(`plan not found: ${opts.plan}`);

  const original = fs.readFileSync(opts.plan, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.plan}`);

  const status = readFmField(split.fmText, 'status');
  if (status === null) fail(`no "status" field found in frontmatter of ${opts.plan}`);

  if (TERMINAL_STATUSES.has(status)) {
    process.stdout.write(`plan-status-transition: ${opts.plan} status "${status}" is terminal/deferred — no-op\n`);
    process.exit(0);
  }

  if (!FLIPPABLE_STATUSES.has(status)) {
    fail(`unexpected current status "${status}" for stamp-implemented — expected one of: ${[...FLIPPABLE_STATUSES].join(', ')}`);
  }

  const fmText = replaceFmField(split.fmText, 'status', 'implemented');

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.plan, rebuilt);
  process.stdout.write(`plan-status-transition: ${opts.plan} status "${status}" → implemented\n`);
  process.exit(0);
}

function main() {
  const opts = parseArgs(process.argv);
  switch (opts.verb) {
    case 'stamp-implemented':
      stampImplemented(opts);
      break;
    default:
      fail(`unknown verb: ${opts.verb || '(none)'} — supported: stamp-implemented`);
  }
}

main();
