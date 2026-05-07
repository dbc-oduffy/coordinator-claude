'use strict';
/**
 * validate-frontmatter-schema.test.js — integration tests for the PreToolUse
 * frontmatter validator hook.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1/Validator/Tests
 *
 * Each test spawns the hook script as a subprocess with stdin piped JSON and
 * asserts stdout / exit code. This mirrors exactly how the Claude runtime
 * invokes the hook, making these true end-to-end integration tests.
 */

const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const HOOK_SCRIPT = path.join(__dirname, 'validate-frontmatter-schema.js');

/**
 * Spawn the hook with the given payload (object → JSON string piped to stdin).
 * Returns { stdout, stderr, exitCode }.
 *
 * Tests that assert on permissionDecision: 'deny' need the hook running in
 * strict mode (the default mode is warn, which emits additionalContext rather
 * than deny). Pass { strict: true } to flip COORDINATOR_SCHEMA_STRICT=1 in the
 * child env.
 */
function runHook(payload, opts = {}) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    if (opts.strict) env.COORDINATOR_SCHEMA_STRICT = '1';
    const child = spawn(process.execPath, [HOOK_SCRIPT], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });

    child.on('close', exitCode => resolve({ stdout, stderr, exitCode }));
    child.on('error', reject);

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

/**
 * Create a temp directory (auto-cleaned at process exit).
 * Returns the directory path.
 */
function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'fmhook-test-'));
}

/**
 * Build a minimal Write payload.
 */
function writePayload(filePath, content, cwd) {
  return {
    tool_name: 'Write',
    tool_input: { file_path: filePath, content },
    session_id: 'test-session',
    cwd: cwd || os.tmpdir(),
  };
}

/**
 * Build a minimal Edit payload.
 */
function editPayload(filePath, oldString, newString, cwd) {
  return {
    tool_name: 'Edit',
    tool_input: { file_path: filePath, old_string: oldString, new_string: newString },
    session_id: 'test-session',
    cwd: cwd || os.tmpdir(),
  };
}

// The schemas dir lives relative to this file
const SCHEMAS_DIR = path.join(__dirname, '../../schemas');

// We need a real repo root so the hook can match repoRelative paths.
// hooks/scripts/ is 5 levels below ~/.claude:
//   ~/.claude/plugins/coordinator-claude/coordinator/hooks/scripts
// so ../../../../../ resolves to ~/.claude.
const CLAUDE_ROOT = path.resolve(__dirname, '../../../../../');

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('validate-frontmatter-schema hook', () => {

  // -------------------------------------------------------------------------
  // Allow: valid handoff Write content passes
  // -------------------------------------------------------------------------
  test('Allow — valid handoff Write', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'handoffs', 'test-valid.md');
    const content = [
      '---',
      'title: Test Handoff',
      'created: 2026-05-01',
      'branch: work/57754134/2026-05-01',
      'status: active',
      'predecessor: null',
      '---',
      '# Body',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'should emit no JSON on pass');
  });

  // -------------------------------------------------------------------------
  // Block (Write): missing required field 'branch'
  // -------------------------------------------------------------------------
  test('Block (Write) — handoff missing branch field', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'handoffs', 'test-missing-branch.md');
    const content = [
      '---',
      'title: Test Handoff',
      'created: 2026-05-01',
      'status: active',
      'predecessor: null',
      '---',
      '# Body',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should emit deny JSON');

    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    assert.ok(
      parsed.hookSpecificOutput.permissionDecisionReason.includes('branch'),
      `reason should mention "branch", got: ${parsed.hookSpecificOutput.permissionDecisionReason}`
    );
  });

  // -------------------------------------------------------------------------
  // Block (Write): plan with invalid status enum
  // -------------------------------------------------------------------------
  test('Block (Write) — plan with invalid status enum', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'test-bad-status.md');
    const content = [
      '---',
      'title: Some Plan',
      'created: 2026-05-01',
      'author: EM',
      'status: invented',
      '---',
      '# Plan',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should emit deny JSON');

    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    // Reason should mention the enum values
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('draft') || reason.includes('approved') || reason.includes('enum'),
      `reason should mention enum values or "enum", got: ${reason}`
    );
  });

  // -------------------------------------------------------------------------
  // Allow: Write to non-schema'd wiki path
  // -------------------------------------------------------------------------
  test('Allow — Write to non-schema\'d wiki path', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'wiki', 'some-guide.md');
    const content = '# A wiki guide\n\nNo frontmatter required here.';

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'should emit no JSON for non-schema\'d path');
  });

  // -------------------------------------------------------------------------
  // Allow: Edit with old_string not matching the existing file → fall through
  // -------------------------------------------------------------------------
  test('Allow — Edit with old_string mismatch falls through silent', async () => {
    // Point at a non-existent handoff file under CLAUDE_ROOT so path matching picks up
    // the handoff schema. Since the file doesn't exist, current content is '', and
    // old_string won't match '' → fall-through silent (let Edit fail on its own merits).
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'handoffs', 'nonexistent-mismatch.md');
    const payload = editPayload(
      filePath,
      'THIS STRING DOES NOT EXIST IN ANY FILE',
      'replacement',
      CLAUDE_ROOT
    );

    const { stdout, exitCode } = await runHook(payload);
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'should emit no JSON on mismatch fall-through');
  });

  // -------------------------------------------------------------------------
  // Block: missing frontmatter on a schema'd file
  // -------------------------------------------------------------------------
  test('Block — missing frontmatter on schema\'d handoff path', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'handoffs', 'test-no-fm.md');
    const content = '# No frontmatter here at all\n\nJust regular markdown.';

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should emit deny JSON');

    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.toLowerCase().includes('frontmatter') || reason.includes('title') || reason.includes('branch'),
      `reason should mention missing frontmatter or required fields, got: ${reason}`
    );
  });

  // -------------------------------------------------------------------------
  // Smoke (lessons): valid + invalid tag entry → deny on bad tag
  // -------------------------------------------------------------------------
  test('Smoke (lessons) — invalid tag entry triggers deny', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Good Lesson [universal]** — This is fine.',
      '  Always do the right thing.',
      '',
      '- **Bad Lesson [whatever]** — This tag is not in the allowed list.',
      '  Some detail here.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should emit deny JSON for bad tag');

    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('whatever'),
      `reason should mention the bad tag "whatever", got: ${reason}`
    );
  });

  // -------------------------------------------------------------------------
  // Allow: lessons file with only valid tags
  // -------------------------------------------------------------------------
  test('Allow — lessons file with only valid [universal] tags', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Good Lesson [universal]** — This is universally applicable.',
      '  Always do the right thing.',
      '',
      '- **Project Lesson [project]** — Project-specific note.',
      '  Some detail.',
      '',
      '- **Untagged Lesson** — No tag, which is allowed.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'should emit no JSON for valid lessons');
  });

  // -------------------------------------------------------------------------
  // Edge: malformed JSON stdin → silent exit 0
  // -------------------------------------------------------------------------
  test('Edge — malformed JSON stdin exits 0 silent', async () => {
    const result = await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [HOOK_SCRIPT], { stdio: ['pipe', 'pipe', 'pipe'] });
      let stdout = '';
      child.stdout.on('data', d => { stdout += d.toString(); });
      child.on('close', exitCode => resolve({ stdout, exitCode }));
      child.on('error', reject);
      child.stdin.write('NOT JSON {{{');
      child.stdin.end();
    });

    assert.equal(result.exitCode, 0, 'should exit 0 on malformed input');
    assert.equal(result.stdout, '', 'should emit nothing on malformed input');
  });

  // -------------------------------------------------------------------------
  // Regression — model-ID literal in inline backticks must NOT register as a
  // tag. Repro for the P1 bug where `claude-opus-4-7[1m]` blocked subsequent
  // edits with a schema error because the strip-noise pass missed it.
  // -------------------------------------------------------------------------
  test('Regression — model-ID in single backticks is not a tag', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Model lesson [universal]** — the model is `claude-opus-4-7[1m]` for tasks.',
      '  Detail line.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `model-ID in backticks must not trigger validation, got: ${stdout}`);
  });

  // -------------------------------------------------------------------------
  // Regression — array-ish prose like `arr[0]` inside a code span must NOT
  // register as a tag.
  // -------------------------------------------------------------------------
  test('Regression — array-ish prose in code span is not a tag', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Indexing lesson [project]** — when we read `arr[0]` we expect element zero.',
      '  Indexing is zero-based.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `array-ish prose in code span must not trigger validation, got: ${stdout}`);
  });

  // -------------------------------------------------------------------------
  // Regression — mixed/nested backtick runs (e.g. ``weird`code`` containing a
  // single backtick inside a double-backtick span) must still strip cleanly.
  // -------------------------------------------------------------------------
  test('Regression — mixed nested backticks strip cleanly', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Nested lesson [universal]** — see ``weird`code`` and `arr[0]` together.',
      '  Both should be stripped.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `nested backticks must strip cleanly, got: ${stdout}`);
  });

  // -------------------------------------------------------------------------
  // Regression — legitimate [universal] / [project] tags still detected
  // alongside code-span dirt on the same line.
  // -------------------------------------------------------------------------
  test('Regression — legitimate tag still detected alongside code-span dirt', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Bad tag with code [whatever]** — uses model `claude-opus-4-7[1m]`.',
      '  This [whatever] tag is invalid; the [1m] in backticks is not a tag.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should still detect the legitimate bad tag');
    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('whatever'),
      `reason should mention bad tag "whatever", got: ${reason}`
    );
    assert.ok(
      !reason.includes('1m'),
      `reason must NOT mention "1m" (model-ID inside backticks), got: ${reason}`
    );
  });

  // -------------------------------------------------------------------------
  // Edge: missing file_path → silent exit 0
  // -------------------------------------------------------------------------
  test('Edge — missing file_path exits 0 silent', async () => {
    const payload = {
      tool_name: 'Write',
      tool_input: { content: '# hello' },
      session_id: 'test',
      cwd: CLAUDE_ROOT,
    };

    const { stdout, exitCode } = await runHook(payload);
    assert.equal(exitCode, 0);
    assert.equal(stdout, '');
  });

});
