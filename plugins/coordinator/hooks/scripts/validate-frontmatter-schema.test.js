'use strict';
/**
 * validate-frontmatter-schema.test.js — integration tests for the PreToolUse
 * frontmatter validator hook.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W1/Validator/Tests
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
 */
function runHook(payload) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [HOOK_SCRIPT], {
      stdio: ['pipe', 'pipe', 'pipe'],
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

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
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

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
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

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
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

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
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
