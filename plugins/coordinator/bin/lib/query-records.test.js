'use strict';
/**
 * query-records.test.js — Tests for query-records.js argument parsing and core logic.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W2
 *
 * Run with: node --test bin/lib/query-records.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('child_process');
const path = require('path');

const QUERY_RECORDS = path.resolve(__dirname, '..', 'query-records.js');
const ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..'); // ~/.claude

// ---------------------------------------------------------------------------
// --key=value normalization (patrik R2 finding 4)
// ---------------------------------------------------------------------------

test('--key=value form accepted: --type=plan', () => {
  // Should not exit 1 with "Unknown argument: --type=plan"
  // Use a path that exists. If the repo root has no plans, output may be empty — that's fine.
  // We just care that parsing doesn't error out.
  let threw = false;
  try {
    execFileSync(process.execPath, [QUERY_RECORDS, '--type=plan', '--limit=1', '--root', ROOT], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (err) {
    threw = true;
    // Accept non-zero exit only if it's a data error (e.g., no records), not a parse error
    assert.ok(
      !err.stderr.includes('Unknown argument'),
      `Should not get "Unknown argument" on --type=plan. stderr: ${err.stderr}`
    );
  }
  // Either succeeded (threw=false) or failed for a non-parse reason
});

test('--key=value form: --type=plan --sort=-created --limit=5 parses identically to space-separated', () => {
  const spaceArgs = ['--type', 'plan', '--sort', '-created', '--limit', '5', '--root', ROOT];
  const equalsArgs = ['--type=plan', '--sort=-created', '--limit=5', '--root', ROOT];

  let spaceOut, equalsOut;
  try {
    spaceOut = execFileSync(process.execPath, [QUERY_RECORDS, ...spaceArgs], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    spaceOut = e.stdout || '';
    assert.ok(!e.stderr.includes('Unknown argument'), `space form parse error: ${e.stderr}`);
  }

  try {
    equalsOut = execFileSync(process.execPath, [QUERY_RECORDS, ...equalsArgs], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    equalsOut = e.stdout || '';
    assert.ok(!e.stderr.includes('Unknown argument'), `equals form parse error: ${e.stderr}`);
  }

  assert.strictEqual(spaceOut, equalsOut, '--key=value and --key value forms should produce identical output');
});

// ---------------------------------------------------------------------------
// parseWhereExpr (exported — test directly)
// ---------------------------------------------------------------------------

test('parseWhereExpr: single equality clause', () => {
  const { parseWhereExpr } = require('../query-records.js');
  const clauses = parseWhereExpr('status=active');
  assert.equal(clauses.length, 1);
  assert.equal(clauses[0].op, '=');
  assert.equal(clauses[0].field, 'status');
  assert.equal(clauses[0].value, 'active');
});

test('parseWhereExpr: AND conjunction', () => {
  const { parseWhereExpr } = require('../query-records.js');
  const clauses = parseWhereExpr('status=active AND reviewer=patrik');
  assert.equal(clauses.length, 2);
  assert.equal(clauses[0].field, 'status');
  assert.equal(clauses[1].field, 'reviewer');
});
