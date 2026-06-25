'use strict';
/**
 * validate-ac-chunk-ownership.test.js — integration tests for the PreToolUse
 * AC-chunk-ownership validator hook.
 *
 * Spec backlink: docs/plans/2026-06-15-ac-chunk-owner-coverage-validator.md § C1
 *
 * Each test spawns the hook script as a subprocess with stdin piped JSON and
 * asserts stdout / exit code. This mirrors exactly how the Claude runtime
 * invokes the hook, making these true end-to-end integration tests.
 *
 * The hook is exercised via spawnSync with { input: <json>, encoding: 'utf8' };
 * strict mode is toggled via env { ...process.env, COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT: '1' }.
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const HOOK_SCRIPT = path.join(__dirname, 'validate-ac-chunk-ownership.js');

/**
 * Spawn the hook with the given payload (object → JSON string piped to stdin).
 * Returns { stdout, stderr, status }.
 *
 * Pass { strict: true } to set COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT=1 in the child env.
 * The flag is explicitly removed from non-strict invocations so a parent env
 * with the flag set does not flip non-strict tests into deny mode.
 */
function runHook(payload, opts = {}) {
  const env = { ...process.env };
  if (opts.strict) {
    env.COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT = '1';
  } else {
    delete env.COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT;
  }
  return spawnSync(process.execPath, [HOOK_SCRIPT], {
    input: JSON.stringify(payload),
    encoding: 'utf8',
    env,
  });
}

/**
 * Build a Write payload for a plan-shaped path with the given markdown body.
 * Defaults to a path under docs/plans/ so the hook's path gate admits it.
 */
function writePlanPayload(content, filePath) {
  return {
    tool_name: 'Write',
    tool_input: {
      file_path: filePath || 'docs/plans/2026-06-15-test-plan.md',
      content,
    },
    session_id: 'test-session',
    agent_id: 'test-agent',
  };
}

// ---------------------------------------------------------------------------
// Inline fixtures — plan body fragments used across tests
// ---------------------------------------------------------------------------

/**
 * A plan with an AC path that NO chunk's write-files owns.
 * AC1 row cites tests/test_unowned.py; no chunk writes that path.
 * Hook should emit additionalContext (unowned path warning).
 *
 * AC: unowned-emits-warn
 */
const UNOWNED_AC_PATH_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC1 | Tests the unowned path | `pytest:tests/test_unowned.py` | gate-bound | realized |',
  '| AC2 | Owned path | `pytest:src/test_owned.py` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | src/test_owned.py | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Same plan but the chunk's write-files expanded to include the AC test path.
 * Hook should be silent (zero violations).
 *
 * AC: owned-passes-clean
 */
const OWNED_AC_PATH_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC1 | Tests an owned path | `pytest:tests/test_owned.py` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | tests/test_owned.py | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan where AC path is matched by a glob pattern in write-files.
 * write-files cell: tests/**\/*.py
 * AC path: tests/sub/test_foo.py
 *
 * AC: glob-match-owns
 */
const GLOB_MATCH_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC3 | Glob match | `pytest:tests/sub/test_foo.py` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | tests/**/*.py | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan where AC path is matched by a directory-prefix in write-files.
 * write-files cell: tests/
 * AC path: tests/test_foo.py
 *
 * AC: directory-prefix-owns
 */
const DIRECTORY_PREFIX_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC4 | Directory prefix | `pytest:tests/test_foo.py` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | tests/ | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan with cargo: rows and cited: rows that are 40-char git SHAs.
 * Both should be silently skipped (no chunk-ownership check possible).
 * The only path-bearing rows are cited: with a real path, but we pair them with a chunk
 * that owns that path — the cargo: and git-SHA cited: rows must not be flagged.
 *
 * AC: skips-non-path-rows
 */
const SKIP_NON_PATH_ROWS_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  // cargo: has no path — must be silently skipped
  '| AC5a | Cargo row | `cargo:my_crate::test_function` | gate-bound | realized |',
  // cited: with a 40-char SHA — must be silently skipped
  '| AC5b | Cited SHA row | `cited:aabbccddee00112233445566778899aabbccddee` | gate-bound | realized |',
  // cited: with a real path — owned by C1 below
  '| AC5c | Cited path row | `cited:src/lib.rs` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | src/lib.rs | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan with NO ## Dispatch Ledger section.
 * Hook should be silent (skip silently when ledger absent).
 *
 * AC: no-ledger-skips-silently
 */
const NO_LEDGER_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC6 | Some criterion | `pytest:tests/test_foo.py` | gate-bound | realized |',
  '',
  '## Problem',
  '',
  'No dispatch ledger here.',
  '',
].join('\n');

/**
 * Plan with NO ## Acceptance Criteria section.
 * Hook should be silent (skip silently when AC section absent).
 *
 * AC: no-ac-table-skips-silently
 */
const NO_AC_TABLE_PLAN = [
  '# Test plan',
  '',
  '## Problem',
  '',
  'No acceptance criteria section.',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | src/lib.rs | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan where AC path is matched by a bracket-class glob in write-files.
 * write-files cell: tests/[fb]oo.py
 * AC path: tests/foo.py
 * Tests the fix for Slice A F2 ([...] glob bracket class support).
 *
 * AC: bracket-glob-owns
 */
const BRACKET_GLOB_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC1 | Bracket glob match | `pytest:tests/foo.py` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | tests/[fb]oo.py | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan where the AC test cell uses sh: with an env-var path ($HOME/...).
 * The hook must skip silently (no violation emitted) — ambiguous extraction.
 * Tests the fix for Slice A F5 (ADVISORY not WARN for ambiguous sh:/bash: tokens).
 *
 * AC: sh-env-var-skips-silently
 */
const SH_ENV_VAR_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC1 | Shell command with env-var path | `sh:$HOME/run-tests.sh` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | src/lib.rs | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan with a malformed AC table (truncated header — no Binding-Class column).
 * The hook must exit 0 with no additionalContext (defensive parse, AC14).
 *
 * AC: malformed-plan-no-throw
 */
const MALFORMED_AC_HEADER_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  // Truncated header: only two columns, no Binding-Class
  '| ID | Criterion |',
  '|---|---|',
  '| AC1 | Some criterion |',
  '',
  '## Dispatch Ledger',
  '',
  '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
  '|---|---|---|---|---|---|---|---|',
  '| 1 | C1 | Do work | src/lib.rs | none | parallel | 5 | pending |',
  '',
].join('\n');

/**
 * Plan with a malformed Dispatch Ledger (missing write-files column).
 * The hook must exit 0 with no additionalContext (defensive parse, AC14).
 *
 * AC: malformed-plan-no-throw (ledger variant)
 */
const MALFORMED_LEDGER_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| ID | Criterion | Test | Binding-Class | Status |',
  '|---|---|---|---|---|',
  '| AC1 | Some criterion | `pytest:tests/test_foo.py` | gate-bound | realized |',
  '',
  '## Dispatch Ledger',
  '',
  // Malformed ledger: missing write-files column entirely
  '| dispatch # | chunk-id | gate-kind | status |',
  '|---|---|---|---|',
  '| 1 | C1 | none | pending |',
  '',
].join('\n');

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('validate-ac-chunk-ownership hook', () => {

  // -------------------------------------------------------------------------
  // AC1: Unowned AC path triggers WARN (additionalContext emission).
  // -------------------------------------------------------------------------
  it('unowned-emits-warn — unowned AC path triggers additionalContext', () => {
    const { stdout, status } = runHook(writePlanPayload(UNOWNED_AC_PATH_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.ok(stdout.length > 0, 'should emit output when an AC path has no chunk owner');

    const parsed = JSON.parse(stdout);
    const ctx = parsed.hookSpecificOutput.additionalContext;
    assert.ok(typeof ctx === 'string', 'should emit additionalContext (warn-mode envelope)');
    assert.ok(
      ctx.includes('tests/test_unowned.py'),
      `additionalContext should name the unowned path, got: ${ctx}`
    );
    assert.ok(
      ctx.includes('AC1'),
      `additionalContext should reference the AC row ID, got: ${ctx}`
    );
  });

  // -------------------------------------------------------------------------
  // AC2: Owned AC path → silent (zero violations).
  // -------------------------------------------------------------------------
  it('owned-passes-clean — chunk owns the AC path → no output', () => {
    const { stdout, status } = runHook(writePlanPayload(OWNED_AC_PATH_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'should emit no output when all AC paths are owned');
  });

  // -------------------------------------------------------------------------
  // AC3: Glob-match ownership via write-files entry tests/**/*.py.
  // -------------------------------------------------------------------------
  it('glob-match-owns — write-files glob pattern owns the AC path', () => {
    const { stdout, status } = runHook(writePlanPayload(GLOB_MATCH_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'glob-owned path should produce no output');
  });

  // -------------------------------------------------------------------------
  // AC4: Directory-prefix ownership via write-files entry tests/.
  // -------------------------------------------------------------------------
  it('directory-prefix-owns — write-files directory prefix owns the AC path', () => {
    const { stdout, status } = runHook(writePlanPayload(DIRECTORY_PREFIX_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'directory-prefix-owned path should produce no output');
  });

  // -------------------------------------------------------------------------
  // AC5: cargo: and git-SHA cited: rows are silently skipped.
  // -------------------------------------------------------------------------
  it('skips-non-path-rows — cargo: and SHA cited: rows produce no violation', () => {
    const { stdout, status } = runHook(writePlanPayload(SKIP_NON_PATH_ROWS_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'cargo: and git-SHA cited: rows must be silently skipped');
  });

  // -------------------------------------------------------------------------
  // AC6: Plan without ## Dispatch Ledger → silent exit 0.
  // -------------------------------------------------------------------------
  it('no-ledger-skips-silently — plan without Dispatch Ledger → no output', () => {
    const { stdout, status } = runHook(writePlanPayload(NO_LEDGER_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'should emit no output when Dispatch Ledger section is absent');
  });

  // -------------------------------------------------------------------------
  // AC7: Plan without ## Acceptance Criteria → silent exit 0.
  // -------------------------------------------------------------------------
  it('no-ac-table-skips-silently — plan without AC section → no output', () => {
    const { stdout, status } = runHook(writePlanPayload(NO_AC_TABLE_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'should emit no output when Acceptance Criteria section is absent');
  });

  // -------------------------------------------------------------------------
  // AC12: Default mode is WARN (additionalContext); strict mode emits deny.
  // -------------------------------------------------------------------------
  it('strict-mode-emits-deny — COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT=1 triggers deny envelope', () => {
    const { stdout, status } = runHook(writePlanPayload(UNOWNED_AC_PATH_PLAN), { strict: true });
    assert.equal(status, 0, 'hook must always exit 0 even in strict mode');
    assert.ok(stdout.length > 0, 'should emit output in strict mode when unowned path found');

    const parsed = JSON.parse(stdout);
    assert.equal(
      parsed.hookSpecificOutput.permissionDecision,
      'deny',
      'strict mode should emit permissionDecision: "deny"'
    );
    assert.ok(
      typeof parsed.hookSpecificOutput.permissionDecisionReason === 'string',
      'strict mode should include permissionDecisionReason'
    );
    assert.ok(
      parsed.hookSpecificOutput.permissionDecisionReason.includes('tests/test_unowned.py'),
      `permissionDecisionReason should name the unowned path, got: ${parsed.hookSpecificOutput.permissionDecisionReason}`
    );
  });

  // -------------------------------------------------------------------------
  // AC13: Non-plan path → silent exit 0 (path gate).
  // -------------------------------------------------------------------------
  it('non-plan-path-silent — non-plan path triggers no output', () => {
    const payload = writePlanPayload(UNOWNED_AC_PATH_PLAN, 'src/some-code.js');
    const { stdout, status } = runHook(payload);
    assert.equal(status, 0, 'hook must always exit 0 for non-plan path');
    assert.equal(stdout, '', 'non-plan path must produce no output (path gate)');
  });

  // -------------------------------------------------------------------------
  // AC14: Malformed AC table header → exit 0, no additionalContext.
  // -------------------------------------------------------------------------
  it('malformed-plan-no-throw — malformed AC table header: exit 0, no output', () => {
    const { stdout, status } = runHook(writePlanPayload(MALFORMED_AC_HEADER_PLAN));
    assert.equal(status, 0, 'hook must always exit 0 on malformed plan');
    assert.equal(stdout, '', 'malformed AC header should not trigger output — defensive parse');
  });

  // -------------------------------------------------------------------------
  // AC14 (ledger variant): Malformed Dispatch Ledger → exit 0, no additionalContext.
  // -------------------------------------------------------------------------
  it('malformed-plan-no-throw — malformed ledger (missing write-files column): exit 0, no output', () => {
    const { stdout, status } = runHook(writePlanPayload(MALFORMED_LEDGER_PLAN));
    assert.equal(status, 0, 'hook must always exit 0 on malformed ledger');
    assert.equal(stdout, '', 'malformed ledger should produce no output — defensive parse');
  });

  // -------------------------------------------------------------------------
  // F2 fix: bracket-class glob [fb]oo.py owns tests/foo.py.
  // Review: code-reviewer Slice A F2 — [, ] were escaped in the general regex-escape pass,
  // breaking bracket-class glob support. Fixed to exclude [ and ] from escape set.
  // -------------------------------------------------------------------------
  it('bracket-glob-owns — bracket-class glob pattern in write-files owns AC path', () => {
    const { stdout, status } = runHook(writePlanPayload(BRACKET_GLOB_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'bracket-class glob-owned path should produce no output');
  });

  // -------------------------------------------------------------------------
  // F5 fix: sh: with env-var path ($HOME/...) is skipped silently (ADVISORY, not WARN).
  // Review: code-reviewer Slice A F5 — plan § Design says ambiguous shell-token extraction
  // emits ADVISORY, not WARN. Env-var paths are unresolvable; return [] not [pathToken].
  // -------------------------------------------------------------------------
  it('sh-env-var-skips-silently — sh: with $HOME path is skipped (no violation)', () => {
    const { stdout, status } = runHook(writePlanPayload(SH_ENV_VAR_PLAN));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(stdout, '', 'sh: with $HOME path is ambiguous and must be skipped silently');
  });

  // -------------------------------------------------------------------------
  // Combinator ownership cases.
  // Spec: check-acceptance-oracle.sh combinator grammar (shipped 2026-06-22).
  // -------------------------------------------------------------------------

  // CO1: pytest:tests/a.py AND pytest:tests/b.py → both paths must be checked.
  // When both paths are owned, hook is silent. When one is unowned, hook emits.
  it('combinator-AND-both-paths-extracted — pytest:a.py AND pytest:b.py extracts both paths', () => {
    // Both paths owned → silent.
    const bothOwnedPlan = [
      '# Test plan',
      '',
      '## Acceptance Criteria',
      '',
      '| ID | Criterion | Test | Binding-Class | Status |',
      '|---|---|---|---|---|',
      '| AC1 | Combinator both owned | pytest:tests/a.py AND pytest:tests/b.py | gate-bound | realized |',
      '',
      '## Dispatch Ledger',
      '',
      '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
      '|---|---|---|---|---|---|---|---|',
      '| 1 | C1 | Do work | tests/a.py, tests/b.py | none | parallel | 5 | pending |',
      '',
    ].join('\n');
    const { stdout: outBoth, status: sBoth } = runHook(writePlanPayload(bothOwnedPlan));
    assert.equal(sBoth, 0, 'must exit 0');
    assert.equal(outBoth, '', 'both paths owned — must be silent');

    // Only one path owned → violation for unowned path.
    const oneUnownedPlan = [
      '# Test plan',
      '',
      '## Acceptance Criteria',
      '',
      '| ID | Criterion | Test | Binding-Class | Status |',
      '|---|---|---|---|---|',
      '| AC1 | Combinator one unowned | pytest:tests/a.py AND pytest:tests/b.py | gate-bound | realized |',
      '',
      '## Dispatch Ledger',
      '',
      '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
      '|---|---|---|---|---|---|---|---|',
      '| 1 | C1 | Do work | tests/a.py | none | parallel | 5 | pending |',
      '',
    ].join('\n');
    const { stdout: outOne, status: sOne } = runHook(writePlanPayload(oneUnownedPlan));
    assert.equal(sOne, 0, 'must exit 0');
    assert.ok(outOne.length > 0, 'one unowned path must emit output');
    const parsed = JSON.parse(outOne);
    const ctx = parsed.hookSpecificOutput.additionalContext;
    assert.ok(ctx.includes('tests/b.py'), `must name the unowned path tests/b.py, got: ${ctx}`);
  });

  // -------------------------------------------------------------------------
  // F8: Combinator where all operands extract zero file paths (e.g. cargo:foo AND cargo:bar)
  // must be silently skipped regardless of ledger contents.
  // Review: code-reviewer F8 — add ownership test for all-zero-path combinator.
  // -------------------------------------------------------------------------
  it('combinator-zero-path — cargo:foo AND cargo:bar (no file paths) is silently skipped', () => {
    const plan = [
      '# Test plan',
      '',
      '## Acceptance Criteria',
      '',
      '| ID | Criterion | Test | Binding-Class | Status |',
      '|---|---|---|---|---|',
      '| AC1 | Cargo combinator (no paths) | cargo:foo AND cargo:bar | gate-bound | realized |',
      '',
      '## Dispatch Ledger',
      '',
      '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
      '|---|---|---|---|---|---|---|---|',
      '| 1 | C1 | Do work | src/lib.rs | none | parallel | 5 | pending |',
      '',
    ].join('\n');
    const { stdout, status } = runHook(writePlanPayload(plan));
    assert.equal(status, 0, 'hook must always exit 0');
    assert.equal(
      stdout, '',
      'cargo:foo AND cargo:bar extracts zero file paths — must be silently skipped regardless of ledger'
    );
  });

  // CO2: Mixed-prefix combinator grep:X@docs/a.md AND bash:tests/b.sh
  // → grep extracts docs/a.md, bash extracts tests/b.sh; both must be checked.
  it('combinator-mixed-prefix-both-paths — grep:X@docs/a.md AND bash:tests/b.sh extracts both paths', () => {
    const bothOwnedPlan = [
      '# Test plan',
      '',
      '## Acceptance Criteria',
      '',
      '| ID | Criterion | Test | Binding-Class | Status |',
      '|---|---|---|---|---|',
      '| AC1 | Mixed prefix combinator | grep:X@docs/a.md AND bash:tests/b.sh | gate-bound | realized |',
      '',
      '## Dispatch Ledger',
      '',
      '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
      '|---|---|---|---|---|---|---|---|',
      '| 1 | C1 | Do work | docs/a.md, tests/b.sh | none | parallel | 5 | pending |',
      '',
    ].join('\n');
    const { stdout, status } = runHook(writePlanPayload(bothOwnedPlan));
    assert.equal(status, 0, 'must exit 0');
    assert.equal(stdout, '', 'both paths owned — must be silent');

    // Now omit docs/a.md from write-files → should emit violation for docs/a.md.
    const missingGrepPlan = [
      '# Test plan',
      '',
      '## Acceptance Criteria',
      '',
      '| ID | Criterion | Test | Binding-Class | Status |',
      '|---|---|---|---|---|',
      '| AC1 | Mixed prefix combinator | grep:X@docs/a.md AND bash:tests/b.sh | gate-bound | realized |',
      '',
      '## Dispatch Ledger',
      '',
      '| dispatch # | chunk-id | one-line brief | write-files | gate-kind | runs | est-min | status |',
      '|---|---|---|---|---|---|---|---|',
      '| 1 | C1 | Do work | tests/b.sh | none | parallel | 5 | pending |',
      '',
    ].join('\n');
    const { stdout: outMissing, status: sMissing } = runHook(writePlanPayload(missingGrepPlan));
    assert.equal(sMissing, 0, 'must exit 0');
    assert.ok(outMissing.length > 0, 'must emit output when grep path unowned');
    const parsed = JSON.parse(outMissing);
    const ctx = parsed.hookSpecificOutput.additionalContext;
    assert.ok(ctx.includes('docs/a.md'), `must name unowned grep path docs/a.md, got: ${ctx}`);
  });

});

