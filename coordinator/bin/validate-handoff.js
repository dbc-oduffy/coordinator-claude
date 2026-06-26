#!/usr/bin/env node
'use strict';
/**
 * validate-handoff.js — Thin wrapper over `query-records --validate-all` for the
 * full handoff corpus (state/handoffs/*.md + archive/handoffs/**\/*.md).
 *
 * Purpose: validates the handoff corpus against the canonical handoff schema,
 * emitting a per-record drift ledger (JSON array to stdout).
 *
 * Design decision D4 (archive/specs/2026-06/2026-06-25-qffs-tc-4-fleet-machinery-contract-emit.md § D4):
 *   The single source of truth for corpus validation is `query-records --validate-all`.
 *   This file is a THIN WRAPPER — NOT a standalone implementation. No parallel validation
 *   logic lives here. If you arrived here from the Ask-2 spinoff
 *   (state/handoffs/2026-06-24_075121_structured-handoff-schema-for-opticon.md) planning to
 *   build a second corpus validator — the Ask-2 AC5 is satisfied by this wrapper. Don't fork.
 *
 * Spec backlink: archive/specs/2026-06/2026-06-25-qffs-tc-4-fleet-machinery-contract-emit.md § Chunk A3b / AC5
 *
 * Usage:
 *   validate-handoff.js [--root <path>]
 *
 *   --root <path>  Override the repo root used for glob resolution (default: git rev-parse
 *                  --show-toplevel). Useful for test isolation against a fixture corpus.
 *
 * Output:
 *   JSON array of { type, path, verdict: 'ok'|'drift', errors: [...] } to stdout.
 *   Covers both active handoffs (type: 'handoff') and archived handoffs (type: 'handoff-archived').
 *
 * Exit codes:
 *   0 — no drift records in the corpus.
 *   1 — at least one drift record found.
 *
 * False-red design contract (negative-spec):
 *   The following legitimate corpus variants are NOT flagged as drift — per A3a schema guards:
 *   - kind: spinoff   with predecessor: none  → rule A3a-3 expects none/null for spinoffs; this is valid.
 *   - kind: recovery  with predecessor: null  → rule A3a-3 only fires for kind: spinoff; null is fine.
 *   - status: consumed without consumed_at    → rule A3a-1 is presence-guarded on consumed_at;
 *                                               post-cutoff handoffs consumed via a manual path
 *                                               (no cs_consume_handoff helper invocation) legitimately
 *                                               lack consumed_at and are NOT flagged.
 */

const path = require('path');
const { execSync } = require('child_process');
const { validateAllRecords } = require('./query-records.js');

// ---------------------------------------------------------------------------
// Argument parsing (minimal — passthrough for test isolation)
// ---------------------------------------------------------------------------
/**
 * Parse the --root <path> argument from argv.
 * @param {string[]} argv  process.argv
 * @returns {{ rootOverride: string|null }}
 */
function parseArgs(argv) {
  const args = argv.slice(2);
  let rootOverride = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--root' && args[i + 1]) {
      rootOverride = args[++i];
    }
  }
  return { rootOverride };
}

// ---------------------------------------------------------------------------
// Root resolution (mirrors detectRoot in query-records.js)
// ---------------------------------------------------------------------------
function resolveRoot(specified) {
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

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------
if (require.main === module) {
  const { rootOverride } = parseArgs(process.argv);
  const root = resolveRoot(rootOverride);

  // Validate active handoffs: state/handoffs/*.md
  const { ledger: ledgerActive, hasDrift: driftActive } = validateAllRecords(
    { validateAll: true, type: 'handoff' },
    root
  );

  // Validate archived handoffs: archive/handoffs/**/*.md
  const { ledger: ledgerArchived, hasDrift: driftArchived } = validateAllRecords(
    { validateAll: true, type: 'handoff-archived' },
    root
  );

  // Merge and emit the combined drift ledger.
  const ledger = [...ledgerActive, ...ledgerArchived];
  const hasDrift = driftActive || driftArchived;

  process.stdout.write(JSON.stringify(ledger, null, 2) + '\n');
  if (hasDrift) process.exit(1);
}
