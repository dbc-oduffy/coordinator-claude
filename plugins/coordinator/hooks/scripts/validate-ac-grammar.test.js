'use strict';
/**
 * validate-ac-grammar.test.js — integration tests for the PreToolUse
 * AC-grammar validator hook.
 *
 * Spec backlink: plugins/coordinator-claude/coordinator/docs/plans/2026-06-09-plan-coverage-rework-burden-reduction.md § C1 Test surface
 *
 * Each test spawns the hook script as a subprocess with stdin piped JSON and
 * asserts stdout / exit code. This mirrors exactly how the Claude runtime
 * invokes the hook, making these true end-to-end integration tests.
 *
 * The hook is exercised via spawnSync with { input: <json>, encoding: 'utf8' };
 * strict mode is toggled via env { ...process.env, COORDINATOR_AC_GRAMMAR_STRICT: '1' }.
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const HOOK_SCRIPT = path.join(__dirname, 'validate-ac-grammar.js');

/**
 * Spawn the hook with the given payload (object → JSON string piped to stdin).
 * Returns { stdout, stderr, status }.
 *
 * Pass { strict: true } to set COORDINATOR_AC_GRAMMAR_STRICT=1 in the child env.
 * The flag is explicitly removed from non-strict invocations so a parent env
 * with the flag set does not flip non-strict tests into deny mode.
 */
function runHook(payload, opts = {}) {
  const env = { ...process.env };
  if (opts.strict) {
    env.COORDINATOR_AC_GRAMMAR_STRICT = '1';
  } else {
    delete env.COORDINATOR_AC_GRAMMAR_STRICT;
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
      file_path: filePath || 'docs/plans/2026-06-09-test-plan.md',
      content,
    },
    session_id: 'test-session',
    agent_id: 'test-agent',
  };
}

/**
 * Build an Edit payload for a plan-shaped path.
 */
function editPlanPayload(oldString, newString, filePath) {
  return {
    tool_name: 'Edit',
    tool_input: {
      file_path: filePath || 'docs/plans/2026-06-09-test-plan.md',
      old_string: oldString,
      new_string: newString,
    },
    session_id: 'test-session',
    agent_id: 'test-agent',
  };
}

// ---------------------------------------------------------------------------
// Inline fixtures — plan body fragments used across tests
// ---------------------------------------------------------------------------

/**
 * A minimal plan body with a valid AC table. All four rows use correct S1-S4
 * typed-prefix grammar. Hook should be silent (no output).
 */
const VALID_AC_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| AC | Description | Test | Binding-Class |',
  '|---|---|---|---|',
  '| AC-1 | Hook emits no output on valid rows | `node:validate-ac-grammar.test.js` | gate-bound |',
  '| AC-2 | Non-plan path is silent | `grep:COORDINATOR_AC_GRAMMAR_STRICT@validate-ac-grammar.js` | gate-bound |',
  '| AC-3 | Strict mode emits deny | `node:validate-ac-grammar.test.js` | gate-bound |',
  '| AC-4 | Reviewer judgment row | reviewer judges UX quality | reviewer-judgment |',
  '',
].join('\n');

/**
 * A plan body where one AC Test cell uses the broken whole-cell wrap + inline
 * "in" connector shape: `` `grep:foo` in `bar.md` ``.
 * Hook should emit additionalContext with the corrected `grep:foo@bar.md`.
 */
const BROKEN_INLINE_IN_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| AC | Description | Test | Binding-Class |',
  '|---|---|---|---|',
  '| AC-1 | Valid row | `node:validate-ac-grammar.test.js` | gate-bound |',
  '| AC-2 | Broken inline-in connector | `grep:foo` in `bar.md` | gate-bound |',
  '',
].join('\n');

/**
 * A plan body where one AC Test cell uses whole-cell wrap but has trailing
 * prose after the typed-prefix value.
 * Hook should emit additionalContext with an S4 rewrite suggestion.
 */
const WHOLE_CELL_TRAILING_PROSE_PLAN = [
  '# Test plan',
  '',
  '## Acceptance Criteria',
  '',
  '| AC | Description | Test | Binding-Class |',
  '|---|---|---|---|',
  '| AC-1 | Valid row | `node:validate-ac-grammar.test.js` | gate-bound |',
  '| AC-2 | Whole-cell wrap with trailing prose | `grep:foo@bar.md` and also manual check | gate-bound |',
  '',
].join('\n');

/**
 * A plan body with NO ## Acceptance Criteria section at all.
 * Hook should be silent.
 */
const NO_AC_SECTION_PLAN = [
  '# Test plan',
  '',
  '## Problem',
  '',
  'Some problem description.',
  '',
  '## Solution',
  '',
  'Some solution.',
  '',
].join('\n');

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('validate-ac-grammar hook', () => {

  // -------------------------------------------------------------------------
  // Case 1: Plan path with valid S1-S4 cells → silent exit 0, empty stdout.
  // -------------------------------------------------------------------------
  it('Case 1 — plan path with valid S1-S4 cells → silent (no output)', () => {
    const { stdout, status } = runHook(writePlanPayload(VALID_AC_PLAN));
    assert.equal(status, 0, 'should exit 0 on valid AC rows');
    assert.equal(stdout, '', 'should emit no stdout when all AC cells are valid');
  });

  // -------------------------------------------------------------------------
  // Case 2: Plan path with `` `grep:foo` in `bar.md` `` (whole-cell wrap with
  // inline "in" connector) → additionalContext containing corrected `grep:foo@bar.md`.
  // -------------------------------------------------------------------------
  it('Case 2 — broken inline-in connector → additionalContext with corrected grep:foo@bar.md', () => {
    const { stdout, status } = runHook(writePlanPayload(BROKEN_INLINE_IN_PLAN));
    assert.equal(status, 0, 'should always exit 0 (mirrors validate-frontmatter-schema.js)');
    assert.ok(stdout.length > 0, 'should emit output when a broken AC cell is found');

    const parsed = JSON.parse(stdout);
    const ctx = parsed.hookSpecificOutput.additionalContext;
    assert.ok(typeof ctx === 'string', 'should emit additionalContext (warn-mode envelope)');
    assert.ok(
      ctx.includes('grep:foo@bar.md'),
      `additionalContext should include corrected form grep:foo@bar.md, got: ${ctx}`
    );
  });

  // -------------------------------------------------------------------------
  // Case 3: Plan path with whole-cell wrap + trailing prose → additionalContext
  // with S4 rewrite suggestion.
  // -------------------------------------------------------------------------
  it('Case 3 — whole-cell wrap with trailing prose → additionalContext with S4 rewrite', () => {
    const { stdout, status } = runHook(writePlanPayload(WHOLE_CELL_TRAILING_PROSE_PLAN));
    assert.equal(status, 0, 'should always exit 0');
    assert.ok(stdout.length > 0, 'should emit output for trailing-prose cell');

    const parsed = JSON.parse(stdout);
    assert.ok(
      parsed.hookSpecificOutput.additionalContext,
      'should emit additionalContext (warn-mode envelope, not deny)'
    );
    const ctx = parsed.hookSpecificOutput.additionalContext;
    // Review: code-reviewer — tighten assertion to match Case 2 precision; the
    // trailing 3 disjuncts made this noise-passing (any non-empty output would pass).
    assert.ok(
      ctx.includes('grep:foo@bar.md'),
      `additionalContext should include corrected form grep:foo@bar.md, got: ${ctx}`
    );
  });

  // -------------------------------------------------------------------------
  // Case 4: Non-plan path (e.g. src/foo.py) → silent exit 0.
  // -------------------------------------------------------------------------
  it('Case 4 — non-plan path → silent exit 0', () => {
    const payload = writePlanPayload(BROKEN_INLINE_IN_PLAN, 'src/foo.py');
    const { stdout, status } = runHook(payload);
    assert.equal(status, 0, 'should exit 0 for non-plan path');
    assert.equal(stdout, '', 'should emit no output for non-plan path (path gate)');
  });

  // -------------------------------------------------------------------------
  // Case 5: Plan path with no ## Acceptance Criteria section → silent exit 0.
  // -------------------------------------------------------------------------
  it('Case 5 — plan path with no ## Acceptance Criteria section → silent exit 0', () => {
    const { stdout, status } = runHook(writePlanPayload(NO_AC_SECTION_PLAN));
    assert.equal(status, 0, 'should exit 0 when no AC section present');
    assert.equal(stdout, '', 'should emit no output when AC section is absent');
  });

  // -------------------------------------------------------------------------
  // Case 6: Strict mode (COORDINATOR_AC_GRAMMAR_STRICT=1) on case 2 → deny envelope
  // (permissionDecision: "deny").
  // -------------------------------------------------------------------------
  it('Case 6 — strict mode on broken inline-in connector → deny envelope', () => {
    const { stdout, status } = runHook(writePlanPayload(BROKEN_INLINE_IN_PLAN), { strict: true });
    assert.equal(status, 0, 'should always exit 0 even in strict mode');
    assert.ok(stdout.length > 0, 'should emit output in strict mode when broken cell found');

    const parsed = JSON.parse(stdout);
    assert.equal(
      parsed.hookSpecificOutput.permissionDecision,
      'deny',
      'strict mode should emit permissionDecision: "deny" (not additionalContext)'
    );
    assert.ok(
      typeof parsed.hookSpecificOutput.permissionDecisionReason === 'string',
      'strict mode should include permissionDecisionReason'
    );
    assert.ok(
      parsed.hookSpecificOutput.permissionDecisionReason.includes('grep:foo@bar.md'),
      `permissionDecisionReason should include corrected form grep:foo@bar.md, got: ${parsed.hookSpecificOutput.permissionDecisionReason}`
    );
  });

  // -------------------------------------------------------------------------
  // Case 7a: AC table with only reviewer-judgment rows → silent exit 0.
  // Review: code-reviewer — gate-bound row count is zero when all rows are
  // reviewer-judgment; the hook must be silent in this case.
  // -------------------------------------------------------------------------
  it('Case 7a — reviewer-judgment-only AC table → silent (no output)', () => {
    const reviewerJudgmentPlan = [
      '# Test plan',
      '',
      '## Acceptance Criteria',
      '',
      '| AC | Description | Test | Binding-Class |',
      '|---|---|---|---|',
      '| AC-1 | UX quality | reviewer judges UX quality | reviewer-judgment |',
      '| AC-2 | Code style | reviewer judges style | reviewer-judgment |',
      '',
    ].join('\n');

    const { stdout, status } = runHook(writePlanPayload(reviewerJudgmentPlan));
    assert.equal(status, 0, 'should exit 0 when AC rows are all reviewer-judgment');
    assert.equal(stdout, '', 'should emit no output when no gate-bound rows are present');
  });

  // -------------------------------------------------------------------------
  // Case 7b: AC table inside a markdown code fence is NOT parsed as live.
  // Empirical incident 2026-06-09 (dogfood): plans demonstrating AC grammar
  // via a ```markdown code fence had their example rows shadow-parsed against
  // the live grammar gate. The hook must treat fenced content as illustrative.
  // -------------------------------------------------------------------------
  it('Case 7 — AC table inside a code fence is ignored', () => {
    const planWithFencedExample = `# Plan
\`\`\`markdown
## Acceptance Criteria

| ID | Criterion | Test | Binding-Class | Status |
|----|-----------|------|---------------|--------|
| AC1 | example | \`grep:foo\` in \`bar.md\` | gate-bound | pending |
\`\`\`

## Acceptance Criteria

| ID | Criterion | Test | Binding-Class | Status |
|----|-----------|------|---------------|--------|
| AC1 | live | \`grep:real@plugins/coordinator-claude/coordinator/CLAUDE.md\` | gate-bound | realized |
`;
    const { stdout, status } = runHook(writePlanPayload(planWithFencedExample));
    assert.equal(status, 0, 'should always exit 0');
    assert.equal(stdout, '', 'fenced example AC row must NOT trigger an offer; live row is valid');
  });

  // -------------------------------------------------------------------------
  // Case 8: Edit-tool path — edit replaces a valid Test cell with a broken one.
  // Review: code-reviewer — editPlanPayload helper was defined but never called;
  // this exercises the Edit branch (lines 536-549) end-to-end so the hook's
  // file-read + old_string match + prospectiveContent path is covered by tests.
  // -------------------------------------------------------------------------
  it('Case 8 — Edit-tool path: valid cell replaced with broken `grep:foo` in `bar.md` → additionalContext', () => {
    // Write a minimal plan file with a valid AC table into a temp directory.
    // The hook reads file_path from the payload, so we must supply a real path.
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ac-grammar-test-'));
    const planFile = path.join(tmpDir, 'docs', 'plans', '2026-06-09-test-plan.md');
    fs.mkdirSync(path.dirname(planFile), { recursive: true });

    const originalContent = [
      '# Test plan',
      '',
      '## Acceptance Criteria',
      '',
      '| AC | Description | Test | Binding-Class |',
      '|---|---|---|---|',
      '| AC-1 | Valid row | `node:validate-ac-grammar.test.js` | gate-bound |',
      '| AC-2 | Row being edited | `grep:real@actual.md` | gate-bound |',
      '',
    ].join('\n');

    fs.writeFileSync(planFile, originalContent, 'utf8');

    try {
      // The old_string is the valid cell; new_string is the broken inline-in form.
      // Pass cwd: tmpDir so the hook's git rev-parse falls back to tmpDir, making
      // toRepoRelative(planFile, tmpDir) resolve to 'docs/plans/...' which clears
      // the isPlanPath gate.
      const payload = {
        ...editPlanPayload(
          '`grep:real@actual.md`',
          '`grep:foo` in `bar.md`',
          planFile
        ),
        cwd: tmpDir,
      };

      const { stdout, status } = runHook(payload);
      assert.equal(status, 0, 'should always exit 0 on Edit path');
      assert.ok(stdout.length > 0, 'should emit output when Edit introduces a broken AC cell');

      const parsed = JSON.parse(stdout);
      const ctx = parsed.hookSpecificOutput.additionalContext;
      assert.ok(typeof ctx === 'string', 'should emit additionalContext (warn-mode envelope)');
      assert.ok(
        ctx.includes('grep:foo@bar.md'),
        `additionalContext should include corrected form grep:foo@bar.md, got: ${ctx}`
      );
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

});
