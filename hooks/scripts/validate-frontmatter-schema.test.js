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
    // Pin the strict flag explicitly in both directions so a runner that
    // exports COORDINATOR_SCHEMA_STRICT globally can't flip non-strict tests
    // into deny mode (code-review F10).
    if (opts.strict) env.COORDINATOR_SCHEMA_STRICT = '1';
    else delete env.COORDINATOR_SCHEMA_STRICT;
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
//   ~/.claude/plugins/coordinator/hooks/scripts
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
    const filePath = path.join(CLAUDE_ROOT, 'state', 'handoffs', 'test-valid.md');
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
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates schema validation of a correctly-formed handoff.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', 'should emit no JSON on pass');
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // -------------------------------------------------------------------------
  // Block (Write): missing required field 'branch'
  // -------------------------------------------------------------------------
  test('Block (Write) — handoff missing branch field', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'handoffs', 'test-missing-branch.md');
    const content = [
      '---',
      'title: Test Handoff',
      'created: 2026-05-01',
      'status: active',
      'predecessor: null',
      '---',
      '# Body',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates that missing required field 'branch' emits a deny.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.ok(stdout.length > 0, 'should emit deny JSON');

      const parsed = JSON.parse(stdout);
      assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
      assert.ok(
        parsed.hookSpecificOutput.permissionDecisionReason.includes('branch'),
        `reason should mention "branch", got: ${parsed.hookSpecificOutput.permissionDecisionReason}`
      );
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
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
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates that an invalid status enum value emits a deny.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
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
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
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
    const filePath = path.join(CLAUDE_ROOT, 'state', 'handoffs', 'nonexistent-mismatch.md');
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
    const filePath = path.join(CLAUDE_ROOT, 'state', 'handoffs', 'test-no-fm.md');
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
  // Smoke (lessons): well-formed per-file YAML lesson record → SILENT.
  // Validates the whole-document-yaml path (lesson-entry schema) processes a
  // correctly-formed state/lessons/<slug>.yaml record without emitting any
  // validation output.
  // -------------------------------------------------------------------------
  test('Smoke (lessons) — well-formed per-file YAML lesson record is SILENT', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'lessons'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'lessons', '2026-01-01-smoke-test.yaml');
    const content = [
      'created: 2026-01-01',
      'title: "Smoke test lesson"',
      'body: "Always do the right thing."',
      'status: open',
      'scope: universal',
      'from_repo: coordinator-claude',
    ].join('\n');
    // Pre-create so C0a scaffold offer doesn't fire.
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `well-formed per-file YAML lesson must be SILENT, got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // -------------------------------------------------------------------------
  // Allow: lessons file with only valid tags
  // -------------------------------------------------------------------------
  test('Allow — lessons file with only valid [universal] tags', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'lessons.md');
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
    const filePath = path.join(CLAUDE_ROOT, 'state', 'lessons.md');
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
    const filePath = path.join(CLAUDE_ROOT, 'state', 'lessons.md');
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
    const filePath = path.join(CLAUDE_ROOT, 'state', 'lessons.md');
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
  // Lessons — per-file YAML lesson with invalid scope enum triggers deny.
  // Validates the whole-document-yaml branch detects a bad enum value on the
  // scope field (scope: bogus is not in [universal, project, wiki-only]).
  // -------------------------------------------------------------------------
  test('Lessons — per-file YAML lesson with invalid scope enum triggers deny', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'lessons'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'lessons', '2026-01-01-bad-scope.yaml');
    const content = [
      'created: 2026-01-01',
      'title: "Bad scope lesson"',
      'body: "This lesson has an invalid scope value."',
      'status: open',
      'scope: bogus',   // INVALID enum value — not in [universal, project, wiki-only]
      'from_repo: coordinator-claude',
    ].join('\n');
    // Pre-create so C0a scaffold offer doesn't fire.
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.ok(stdout.length > 0, 'should emit deny JSON for invalid scope enum');
      const parsed = JSON.parse(stdout);
      assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
      const reason = parsed.hookSpecificOutput.permissionDecisionReason;
      assert.ok(
        reason.includes('scope'),
        `reason should mention the invalid "scope" field, got: ${reason}`
      );
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
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

  // =========================================================================
  // Chunk 5 — design-as-offers hand-rolling catch
  // Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 5
  // =========================================================================

  // -------------------------------------------------------------------------
  // Offer (path-based): Write to state/memos/ → CLI offer emitted
  // -------------------------------------------------------------------------
  test('Offer — Write to state/memos/ emits cross-repo-memo CLI offer', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'memos', '2026-05-23-example-game-repo-to-addon.md');
    const content = [
      '# Memo: example-game-repo to addon',
      '',
      'To: project-rag-ue-addon-em',
      'From: example-game-repo-em',
      'Date: 2026-05-23',
      '',
      'Please update the schema.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0 (never block)');
    assert.ok(stdout.length > 0, 'should emit offer JSON');

    const parsed = JSON.parse(stdout);
    const ctx = parsed.hookSpecificOutput.additionalContext;
    assert.ok(typeof ctx === 'string', 'should emit additionalContext (warn mode)');
    assert.ok(
      ctx.includes('cross-repo-memo') && ctx.includes('--to'),
      `offer must mention 'cross-repo-memo --to', got: ${ctx}`
    );
  });

  // -------------------------------------------------------------------------
  // Offer (path-based, strict mode): Write to state/memos/ → deny in strict mode
  // -------------------------------------------------------------------------
  test('Offer — Write to state/memos/ emits deny in COORDINATOR_SCHEMA_STRICT=1 mode', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'memos', '2026-05-23-test.md');
    const content = '# Hand-rolled memo\n\nSome content.';

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0 even in strict mode');
    assert.ok(stdout.length > 0, 'should emit deny JSON in strict mode');

    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('cross-repo-memo') && reason.includes('--to'),
      `deny reason must mention 'cross-repo-memo --to', got: ${reason}`
    );
  });

  // -------------------------------------------------------------------------
  // Offer (content-based): Write with free-form To:/From: header → CLI offer
  // -------------------------------------------------------------------------
  test('Offer — Write with free-form To:/From: header emits cross-repo-memo CLI offer', async () => {
    // A file that doesn't match the /memos/ path heuristic but has a hand-rolled header
    const filePath = path.join(CLAUDE_ROOT, 'state', 'handoffs', 'accidentally-a-memo.md');
    const content = [
      'To: project-rag-ue-addon-em',
      'From: example-game-repo-em',
      'Date: 2026-05-23',
      '',
      '# Cross-repo request',
      'Please update the indexer.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0 (never block)');
    assert.ok(stdout.length > 0, 'should emit offer JSON for free-form header');

    const parsed = JSON.parse(stdout);
    const ctx = parsed.hookSpecificOutput.additionalContext;
    assert.ok(
      ctx.includes('cross-repo-memo') && ctx.includes('--to'),
      `offer must mention 'cross-repo-memo --to', got: ${ctx}`
    );
  });

  // -------------------------------------------------------------------------
  // Silent: correct Write to cross-repo/inbox/[0-9]*.md with valid frontmatter → no offer
  //
  // Negative-spec: a canonical receiver-surface write (inbox path) must stay SILENT
  // (the own-inbox guard and schema validator handle it — no routing-mismatch offer injected).
  // Updated in Chunk G: path changed from flat cross-repo/ to cross-repo/inbox/ (canonical
  // post-restructure). The routing-mismatch check explicitly excludes cross-repo/inbox/
  // so this test uses a temp dir with a matching to: → self (normal inbound shape).
  // -------------------------------------------------------------------------
  test('Silent — correct Write to cross-repo/inbox/[0-9]*.md with valid frontmatter emits no offer', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'inbox'), { recursive: true });
    const tmpBasename = path.basename(tmp);
    const thisEmId = `${tmpBasename}-em`;

    // Normal inbound: from=example-game-repo-em, to=<this-repo-em>. The own-inbox guard stays
    // silent (from != thisEmId). The routing check doesn't fire (canonical inbox path).
    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-example-game-repo-request.md');
    const content = [
      '---',
      'title: Update indexer schema',
      'from: example-game-repo-em',
      `to: ${thisEmId}`,
      'created: 2026-05-23',
      'status: open',
      'delivery_mode: receiver-repo',
      '---',
      '# Request',
      '',
      'Please update the indexer to handle the new blueprint schema.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp));
    assert.equal(exitCode, 0, 'should exit 0');
    // The canonical inbox path with valid frontmatter (correct inbound) must be silent.
    assert.equal(stdout, '', 'canonical cross-repo/inbox/ write with valid frontmatter must be silent');
  });

  // -------------------------------------------------------------------------
  // Silent: Write to cross-repo/README.md (non-digit prefix) → no offer, no schema hit
  // -------------------------------------------------------------------------
  test('Silent — Write to cross-repo/README.md is not caught by offer or schema', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'cross-repo', 'README.md');
    const content = '# Cross-repo\n\nInbound memos from other repos land here.';

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'README.md in cross-repo/ must be silent');
  });

  // =========================================================================
  // Lessons tag-detection: only tag-shaped tokens are candidate tags. Bracket
  // prose (wikilinks, section refs, footnotes, citation keys) must NOT trip the
  // validator. Repro for the 2026-05-23 noise where pre-existing bracket prose
  // on entry lines surfaced as "unknown tag" warnings.
  // =========================================================================

  // -------------------------------------------------------------------------
  // Non-tag bracket prose on an entry line must not register as a tag.
  // -------------------------------------------------------------------------
  test('Lessons — bracket prose ([[wikilink]], [11§L4], [1], [Smith2020]) is not a tag', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Wikilink entry [universal]** — see [[other-lesson]] for context.',
      '  Detail line.',
      '',
      '- **Section ref entry** — cross-refs [11§L4] in the doctrine.',
      '  Detail line.',
      '',
      '- **Footnote and citation entry** — per [1] and [Smith2020].',
      '  Detail line.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `bracket prose must not register as a tag, got: ${stdout}`);
  });

  // -------------------------------------------------------------------------
  // Lessons — per-file YAML lesson missing required 'status' triggers deny.
  // Validates the whole-document-yaml branch enforces required-field presence
  // for per-file lesson records.
  // -------------------------------------------------------------------------
  test('Lessons — per-file YAML lesson missing required "status" triggers deny', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'lessons'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'lessons', '2026-01-01-no-status.yaml');
    // Omit required field 'status'
    const content = [
      'created: 2026-01-01',
      'title: "Missing status lesson"',
      'body: "No status field present."',
      'scope: universal',
      'from_repo: coordinator-claude',
    ].join('\n');
    // Pre-create so C0a scaffold offer doesn't fire.
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.ok(stdout.length > 0, 'should emit deny JSON for missing required field');
      const parsed = JSON.parse(stdout);
      assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
      const reason = parsed.hookSpecificOutput.permissionDecisionReason;
      assert.ok(
        reason.includes('status'),
        `reason should mention the missing "status" field, got: ${reason}`
      );
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // =========================================================================
  // Lessons Edit operations — whole-document-yaml validates the full
  // prospective content (the result after applying the edit) against the
  // lesson-entry required:/optional: field schema.
  // =========================================================================

  // -------------------------------------------------------------------------
  // Edit producing a well-formed per-file YAML lesson → SILENT.
  // -------------------------------------------------------------------------
  test('Lessons — Edit producing well-formed per-file YAML lesson record is SILENT', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'lessons'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'lessons', '2026-01-01-edit-clean.yaml');
    // Existing file is a valid lesson record.
    const existing = [
      'created: 2026-01-01',
      'title: "Editable lesson"',
      'body: "Original body text."',
      'status: open',
      'scope: project',
      'from_repo: coordinator-claude',
    ].join('\n');
    fs.writeFileSync(filePath, existing, 'utf8');

    // Edit changes body — resulting record is still well-formed.
    const { stdout, exitCode } = await runHook(
      editPayload(filePath, 'body: "Original body text."', 'body: "Updated body text."', tmp),
      { strict: true }
    );
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `Edit producing a well-formed per-file YAML lesson must be SILENT, got: ${stdout}`);
  });

  // -------------------------------------------------------------------------
  // Edit producing a per-file YAML lesson with a bad scope enum → caught
  // (delta-scoping doesn't go blind — the resulting record is re-validated).
  // -------------------------------------------------------------------------
  test('Lessons — Edit producing a per-file YAML lesson with invalid scope is caught', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'lessons'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'lessons', '2026-01-01-edit-bad.yaml');
    const existing = [
      'created: 2026-01-01',
      'title: "Editable lesson"',
      'body: "Original body text."',
      'status: open',
      'scope: project',
      'from_repo: coordinator-claude',
    ].join('\n');
    fs.writeFileSync(filePath, existing, 'utf8');

    // Edit changes scope to an invalid enum value — resulting record must be caught.
    const { stdout, exitCode } = await runHook(
      editPayload(filePath, 'scope: project', 'scope: whatever', tmp),
      { strict: true }
    );
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should flag the invalid scope in the resulting record');
    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    assert.ok(
      parsed.hookSpecificOutput.permissionDecisionReason.includes('scope'),
      'reason should mention the invalid "scope" field'
    );
  });

  // =========================================================================
  // Own-inbox guard — cross-repo/inbox/[0-9]*.md outbound-in-own-inbox detection
  //
  // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk C (T2)
  // Prior spec: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 5
  // =========================================================================

  // Helper: build a canonical cross-repo inbox memo content string.
  function inboxMemoContent({ from, to, status = 'open' } = {}) {
    return [
      '---',
      'title: "Test memo"',
      `from: "${from}"`,
      `to: "${to}"`,
      'created: 2026-05-23',
      `status: ${status}`,
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Body text.',
    ].join('\n');
  }

  // -------------------------------------------------------------------------
  // DENY: from=<self>, to=<other> — outbound memo sitting in own inbox.
  //
  // We use a temp dir with a known basename so resolveRepoRoot falls back to cwd
  // (no .git present) and basename(cwd) == basename(tmp) → em-id = <tmp-basename>-em.
  // -------------------------------------------------------------------------
  test('Own-inbox guard — DENY: from=<self>, to=<other> in own cross-repo/inbox/', async () => {
    const tmp = makeTempDir();
    const basename = path.basename(tmp);
    const thisEmId = `${basename}-em`;
    const otherEmId = 'project-rag-em';

    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-outbound.md');
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'inbox'), { recursive: true });

    const content = inboxMemoContent({ from: thisEmId, to: otherEmId });
    const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp));

    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should emit deny JSON');
    const parsed = JSON.parse(stdout);
    assert.equal(
      parsed.hookSpecificOutput.permissionDecision,
      'deny',
      'should deny (not warn) for own-inbox outbound misplacement'
    );
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('cross-repo-memo') && reason.includes('--to'),
      `deny reason must mention 'cross-repo-memo --to', got: ${reason}`
    );
    assert.ok(
      reason.includes(thisEmId),
      `deny reason must name this repo's em-id (${thisEmId}), got: ${reason}`
    );
  });

  // -------------------------------------------------------------------------
  // SILENT: from=<other>, to=<self> — normal inbound memo. No deny, no offer.
  // -------------------------------------------------------------------------
  test('Own-inbox guard — SILENT: from=<other>, to=<self> (normal inbound)', async () => {
    const tmp = makeTempDir();
    const basename = path.basename(tmp);
    const thisEmId = `${basename}-em`;
    const senderEmId = 'example-game-repo-em';

    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-inbound.md');
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'inbox'), { recursive: true });

    const content = inboxMemoContent({ from: senderEmId, to: thisEmId });
    const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp));

    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'normal inbound memo must be silent');
  });

  // -------------------------------------------------------------------------
  // SILENT: from==to==<self> — self-receipt carve-out. No deny.
  // -------------------------------------------------------------------------
  test('Own-inbox guard — SILENT: from==to==<self> (self-receipt carve-out)', async () => {
    const tmp = makeTempDir();
    const basename = path.basename(tmp);
    const thisEmId = `${basename}-em`;

    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-self-receipt.md');
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'inbox'), { recursive: true });

    const content = inboxMemoContent({ from: thisEmId, to: thisEmId, status: 'actioned' });
    const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp));

    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'self-receipt (from==to==self) must be silent');
  });

  // -------------------------------------------------------------------------
  // ALLOW: COORDINATOR_OVERRIDE_OWN_INBOX=1 bypasses the guard entirely.
  // -------------------------------------------------------------------------
  test('Own-inbox guard — ALLOW: COORDINATOR_OVERRIDE_OWN_INBOX=1 bypasses deny', async () => {
    const tmp = makeTempDir();
    const basename = path.basename(tmp);
    const thisEmId = `${basename}-em`;
    const otherEmId = 'project-rag-em';

    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-override.md');
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'inbox'), { recursive: true });

    const content = inboxMemoContent({ from: thisEmId, to: otherEmId });
    const result = await new Promise((resolve, reject) => {
      const env = { ...process.env, COORDINATOR_OVERRIDE_OWN_INBOX: '1' };
      const child = require('node:child_process').spawn(process.execPath, [HOOK_SCRIPT], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env,
      });
      let stdout = '';
      let stderr = '';
      child.stdout.on('data', d => { stdout += d.toString(); });
      child.stderr.on('data', d => { stderr += d.toString(); });
      child.on('close', exitCode => resolve({ stdout, stderr, exitCode }));
      child.on('error', reject);
      child.stdin.write(JSON.stringify(writePayload(filePath, content, tmp)));
      child.stdin.end();
    });

    assert.equal(result.exitCode, 0, 'should exit 0');
    assert.equal(result.stdout, '', 'COORDINATOR_OVERRIDE_OWN_INBOX=1 must suppress the deny');
  });

  // -------------------------------------------------------------------------
  // DENY: example-game-repo alias case — basename=example-game-workbench-repo → example-game-repo-em.
  // Verifies the REPO_BASENAME_TO_EM_SHORTNAME alias map is exercised.
  // -------------------------------------------------------------------------
  test('Own-inbox guard — DENY: example-game-repo alias (example-game-workbench-repo → example-game-repo-em)', async () => {
    // Create a temp dir named "example-game-workbench-repo" to simulate the example-game-repo repo.
    // resolveRepoRoot will fall back to cwd (no .git present) → basename = "example-game-workbench-repo".
    const example_game_repoDir = path.join(os.tmpdir(), 'example-game-workbench-repo');
    fs.mkdirSync(path.join(example_game_repoDir, 'cross-repo', 'inbox'), { recursive: true });

    const thisEmId = 'example-game-repo-em'; // alias resolution: example-game-workbench-repo → example-game-repo-em
    const otherEmId = 'project-rag-em';

    const filePath = path.join(example_game_repoDir, 'cross-repo', 'inbox', '2026-05-23-example-game-repo-outbound.md');
    const content = inboxMemoContent({ from: thisEmId, to: otherEmId });

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, example_game_repoDir));

    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should emit deny JSON for example-game-repo alias case');
    const parsed = JSON.parse(stdout);
    assert.equal(
      parsed.hookSpecificOutput.permissionDecision,
      'deny',
      'example-game-repo alias must resolve correctly and trigger deny'
    );
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('example-game-repo-em'),
      `reason must name the resolved em-id (example-game-repo-em), got: ${reason}`
    );
  });

  // -------------------------------------------------------------------------
  // SILENT: write to cross-repo/archive/ must NOT trigger the own-inbox guard.
  //
  // archive/ holds closed actioned memos — not outbound writes. The guard regex
  // ^cross-repo/inbox/[0-9] must NOT match archive/ paths; this test confirms
  // isCanonicalInboxWrite is false for archive paths.
  //
  // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk C (T2)
  // -------------------------------------------------------------------------
  test('Own-inbox guard — SILENT: cross-repo/archive/ write does not trigger own-inbox guard', async () => {
    const tmp = makeTempDir();
    const basename = path.basename(tmp);
    const thisEmId = `${basename}-em`;
    const otherEmId = 'project-rag-em';

    const filePath = path.join(tmp, 'cross-repo', 'archive', '2026-05-23-actioned.md');
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'archive'), { recursive: true });

    // Even an "outbound" memo shape in archive/ must stay silent — archive/ is not inbox/.
    const content = inboxMemoContent({ from: thisEmId, to: otherEmId, status: 'actioned' });
    const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp));

    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'cross-repo/archive/ write must be silent (not own-inbox guard territory)');
  });

  // =========================================================================
  // Chunk G — Routing-mismatch memo-redirect offer
  // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk G
  // =========================================================================

  // -------------------------------------------------------------------------
  // Offer (routing mismatch): memo `to: example-game-repo-em` landing in central (~/.claude) → offer.
  // Signal (a): YAML frontmatter `to:` field present. Landing repo: .claude → claude-central-em.
  // to: example-game-repo-em ≠ claude-central-em → routing mismatch → offer.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — memo to: example-game-repo-em landing in central → offer', async () => {
    // Write a YAML-frontmatter memo addressed to example-game-repo-em into ~/.claude (central).
    // This simulates the live failure: addon-EM hand-writes a memo into central instead
    // of using the CLI to deliver to example-game-repo's inbox.
    const filePath = path.join(CLAUDE_ROOT, 'cross-repo', '2026-05-23-addon-to-example-game-repo.md');
    const content = [
      '---',
      'title: "Addon update"',
      'from: claude-central-em',
      'to: example-game-repo-em',
      'created: 2026-05-23',
      'status: open',
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Please consume the new schema.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0 (never block — offer shape)');
    assert.ok(stdout.length > 0, 'should emit routing-mismatch offer');
    const parsed = JSON.parse(stdout);
    const ctx = parsed.hookSpecificOutput.additionalContext;
    assert.ok(typeof ctx === 'string', 'should emit additionalContext (offer-shape)');
    assert.ok(
      ctx.includes('cross-repo-memo') && ctx.includes('--to'),
      `offer must mention 'cross-repo-memo --to', got: ${ctx}`
    );
    assert.ok(
      ctx.includes('example-game-repo-em'),
      `offer must name the resolved recipient (example-game-repo-em), got: ${ctx}`
    );
  });

  // -------------------------------------------------------------------------
  // Offer (hand-rolled path): state/memos/ with capitalized To:/From: headers → offer.
  // Signal (b): hasFreeFormMemoHeader() + memo-shaped path. Existing /memos/ path trigger
  // already confirmed by earlier test; this confirms it still fires in G's branch.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — state/memos/ with hand-rolled To:/From: headers → offer', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'memos', '2026-05-23-example-game-repo-reply.md');
    const content = [
      'To: claude-central-em',
      'From: example-game-repo-em',
      'Date: 2026-05-23',
      '',
      'Reply body.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'state/memos/ with hand-rolled headers must emit offer');
    const parsed = JSON.parse(stdout);
    // Path-based isMemoPathMislocated fires first; either way an offer is emitted.
    const output = parsed.hookSpecificOutput;
    const hasOffer = output.additionalContext || output.permissionDecision === 'deny';
    assert.ok(hasOffer, `should emit an offer or deny, got: ${JSON.stringify(output)}`);
  });

  // -------------------------------------------------------------------------
  // C3 (central-identity-flip): to: claude-central-em landing in DoE-claude → SILENT.
  // After C3, the central landing repo is DoE-claude (repos.doe_claude), NOT ~/.claude.
  // The hook path-anchors via machine-local, so a memo addressed to claude-central-em
  // landing in DoE-claude is a routing MATCH → SILENT.
  //
  // Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — C3: to: claude-central-em landing in DoE-claude → SILENT (new central)', async () => {
    // Use the actual DoE-claude repo root as the landing.
    // validate-frontmatter-schema.test.js is at coordinator/hooks/scripts/ (3 levels below repo root).
    const doeClaude = path.resolve(__dirname, '../../..');
    const filePath = path.join(doeClaude, 'cross-repo', '2026-07-04-example-game-repo-to-central.md');
    const content = [
      '---',
      'title: "Request for central"',
      'from: example-game-repo-em',
      'to: claude-central-em',
      'created: 2026-07-04',
      'status: open',
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Please seed the new doctrine.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, doeClaude));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'to: claude-central-em landing in DoE-claude must be SILENT (C3 routing match)');
  });

  // -------------------------------------------------------------------------
  // C3 (central-identity-flip): to: claude-central-em landing in ~/.claude → OFFER.
  // After C3, ~/.claude is no longer the central landing repo. A central-addressed memo
  // landing there is a routing mismatch → redirect offer fires.
  //
  // Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — C3: to: claude-central-em landing in ~/.claude → OFFER (no longer central)', async () => {
    // Inject a fake machine-local that exits 0 and prints the DoE-claude path.
    // This makes _DOE_CLAUDE_PATH deterministic on any machine (no live registration needed).
    // ~/.claude !== doePath → landing is correctly identified as non-central → offer fires.
    // Review: code-reviewer — F1: machine-local isolation for determinism on fresh machines / CI
    const doePath = path.resolve(__dirname, '../../..');
    const fakeMlDir = fs.mkdtempSync(path.join(os.tmpdir(), 'fake-ml-offer-'));
    const fakeMl = path.join(fakeMlDir, 'machine-local');
    fs.writeFileSync(fakeMl, '#!/bin/sh\nprintf "%s" "$_FAKE_ML_PATH"\n');
    fs.chmodSync(fakeMl, 0o755);

    try {
      const claudeMeta = path.join(os.homedir(), '.claude');
      const filePath = path.join(claudeMeta, 'cross-repo', '2026-07-04-wrong-central-landing.md');
      const content = [
        '---',
        'title: "Misrouted to ~/.claude"',
        'from: example-game-repo-em',
        'to: claude-central-em',
        'created: 2026-07-04',
        'status: open',
        'delivery_mode: receiver-repo',
        '---',
        '',
        'This should land in DoE-claude, not ~/.claude.',
      ].join('\n');

      const env = { ...process.env, PATH: `${fakeMlDir}:${process.env.PATH}`, _FAKE_ML_PATH: doePath };
      delete env.COORDINATOR_SCHEMA_STRICT;
      const runHookWithFakeML = (payload) => new Promise((resolve, reject) => {
        const child = spawn(process.execPath, [HOOK_SCRIPT], { stdio: ['pipe', 'pipe', 'pipe'], env });
        let stdout = ''; let stderr = '';
        child.stdout.on('data', d => { stdout += d.toString(); });
        child.stderr.on('data', d => { stderr += d.toString(); });
        child.on('close', exitCode => resolve({ stdout, stderr, exitCode }));
        child.on('error', reject);
        child.stdin.write(JSON.stringify(payload));
        child.stdin.end();
      });

      const { stdout, exitCode } = await runHookWithFakeML(writePayload(filePath, content, claudeMeta));
      assert.equal(exitCode, 0, 'should exit 0 (offer-shape, never block)');
      assert.ok(stdout.length > 0, 'should emit routing-mismatch offer (C3: ~/.claude is no longer central)');
      const parsed = JSON.parse(stdout);
      const ctx = parsed.hookSpecificOutput.additionalContext;
      assert.ok(typeof ctx === 'string', 'should emit additionalContext (offer-shape)');
      assert.ok(
        ctx.includes('cross-repo-memo') && ctx.includes('--to'),
        `offer must mention 'cross-repo-memo --to', got: ${ctx}`
      );
      assert.ok(
        ctx.includes('claude-central-em'),
        `offer must name the recipient (claude-central-em), got: ${ctx}`
      );
    } finally {
      try { fs.rmSync(fakeMlDir, { recursive: true }); } catch { /* ignore cleanup */ }
    }
  });

  // -------------------------------------------------------------------------
  // C3 (central-identity-flip): own-inbox central guard fires when
  // `from: claude-central-em` memo is written into DoE-claude's own cross-repo/inbox/.
  // After C3, DoE-claude IS the central repo, so thisEmId = 'claude-central-em'.
  // An outbound central memo (from: claude-central-em, to: <other>) in its own inbox
  // is caught by the own-inbox guard → DENY.
  //
  // Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3 (own-inbox guard fix)
  // -------------------------------------------------------------------------
  test('C3: own-inbox central guard — from: claude-central-em in DoE-claude inbox → DENY', async () => {
    // Inject a fake machine-local that exits 0 and prints the DoE-claude path.
    // This makes _DOE_CLAUDE_PATH deterministic on any machine (no live registration needed).
    // repoRoot === doeClaude === _DOE_CLAUDE_PATH → thisEmId = 'claude-central-em' → DENY fires.
    // Review: code-reviewer — F1: machine-local isolation for determinism on fresh machines / CI
    const doeClaude = path.resolve(__dirname, '../../..');
    const fakeMlDir = fs.mkdtempSync(path.join(os.tmpdir(), 'fake-ml-deny-'));
    const fakeMl = path.join(fakeMlDir, 'machine-local');
    fs.writeFileSync(fakeMl, '#!/bin/sh\nprintf "%s" "$_FAKE_ML_PATH"\n');
    fs.chmodSync(fakeMl, 0o755);

    try {
      const inboxPath = path.join(doeClaude, 'cross-repo', 'inbox', '2026-07-04-central-outbound.md');
      // Ensure the inbox directory exists so the hook can proceed.
      fs.mkdirSync(path.dirname(inboxPath), { recursive: true });

      const content = inboxMemoContent({ from: 'claude-central-em', to: 'example-game-repo-em' });
      const env = { ...process.env, PATH: `${fakeMlDir}:${process.env.PATH}`, _FAKE_ML_PATH: doeClaude };
      delete env.COORDINATOR_SCHEMA_STRICT;
      const runHookWithFakeML = (payload) => new Promise((resolve, reject) => {
        const child = spawn(process.execPath, [HOOK_SCRIPT], { stdio: ['pipe', 'pipe', 'pipe'], env });
        let stdout = ''; let stderr = '';
        child.stdout.on('data', d => { stdout += d.toString(); });
        child.stderr.on('data', d => { stderr += d.toString(); });
        child.on('close', exitCode => resolve({ stdout, stderr, exitCode }));
        child.on('error', reject);
        child.stdin.write(JSON.stringify(payload));
        child.stdin.end();
      });

      const { stdout, exitCode } = await runHookWithFakeML(writePayload(inboxPath, content, doeClaude));
      assert.equal(exitCode, 0, 'should exit 0 (hook never exits non-zero)');
      assert.ok(stdout.length > 0, 'should emit deny JSON (own-inbox guard caught outbound central memo)');
      const parsed = JSON.parse(stdout);
      assert.equal(
        parsed.hookSpecificOutput.permissionDecision,
        'deny',
        'own-inbox guard must deny outbound central memo in DoE-claude inbox'
      );
      const reason = parsed.hookSpecificOutput.permissionDecisionReason;
      assert.ok(
        typeof reason === 'string' && reason.includes('claude-central-em'),
        `deny reason must identify from-em (claude-central-em), got: ${reason}`
      );
    } finally {
      try { fs.rmSync(fakeMlDir, { recursive: true }); } catch { /* ignore cleanup */ }
    }
  });

  // -------------------------------------------------------------------------
  // C3 regression guard: machine-local failure → no central offer fires, no
  // own-inbox misfire. This guards against isolated hardening of either branch
  // that would produce false positives under machine-local unavailability.
  //
  // With _DOE_CLAUDE_PATH = null (machine-local rc=2):
  //   - Routing: `toIsCentral && _DOE_CLAUDE_PATH === null` → fail-open (no offer)
  //   - Own-inbox: thisEmId degrades to 'DoE-claude-em'; from: claude-central-em ≠ thisEmId → silent
  //
  // Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3 (fail-open coherence)
  // -------------------------------------------------------------------------
  test('C3: machine-local failure → no central offer, no own-inbox misfire', async () => {
    // Inject a fake machine-local that exits rc=2 (operational failure).
    const fakeMlDir = fs.mkdtempSync(path.join(os.tmpdir(), 'fake-ml-'));
    const fakeMl = path.join(fakeMlDir, 'machine-local');
    fs.writeFileSync(fakeMl, '#!/bin/sh\nexit 2\n');
    fs.chmodSync(fakeMl, 0o755);

    try {
      const doeClaude = path.resolve(__dirname, '../../..');
      const env = { ...process.env, PATH: `${fakeMlDir}:${process.env.PATH}` };
      const runHookWithEnv = (payload) => new Promise((resolve, reject) => {
        const { spawn } = require('node:child_process');
        const child = spawn(process.execPath, [HOOK_SCRIPT], { stdio: ['pipe', 'pipe', 'pipe'], env });
        let stdout = ''; let stderr = '';
        child.stdout.on('data', d => { stdout += d.toString(); });
        child.stderr.on('data', d => { stderr += d.toString(); });
        child.on('close', exitCode => resolve({ stdout, stderr, exitCode }));
        child.on('error', reject);
        child.stdin.write(JSON.stringify(payload));
        child.stdin.end();
      });

      // Scenario A: to: claude-central-em landing in DoE-claude → no offer (fail-open, not a false mismatch).
      const memoPath = path.join(doeClaude, 'cross-repo', '2026-07-04-ml-fail-central.md');
      const memoContent = [
        '---',
        'title: "Central memo under ML failure"',
        'from: example-game-repo-em',
        'to: claude-central-em',
        'created: 2026-07-04',
        'status: open',
        'delivery_mode: receiver-repo',
        '---',
        '',
        'Body.',
      ].join('\n');
      const { stdout: outA, stderr: errA } = await runHookWithEnv(writePayload(memoPath, memoContent, doeClaude));
      assert.equal(outA, '', `C3 ML-fail scenario A: no offer must fire when ML unavailable (got: ${outA})`);
      assert.ok(errA.includes('repos.doe_claude failed'), 'ML failure must produce a debug note on stderr');

      // Scenario B: from: claude-central-em in DoE-claude inbox → no deny misfire.
      // thisEmId degrades to 'DoE-claude-em' ≠ 'claude-central-em' → guard silent.
      const inboxPath2 = path.join(doeClaude, 'cross-repo', 'inbox', '2026-07-04-ml-fail-inbox.md');
      fs.mkdirSync(path.dirname(inboxPath2), { recursive: true });
      const inboxContent = inboxMemoContent({ from: 'claude-central-em', to: 'example-game-repo-em' });
      const { stdout: outB } = await runHookWithEnv(writePayload(inboxPath2, inboxContent, doeClaude));
      assert.equal(outB, '', `C3 ML-fail scenario B: own-inbox guard must not misfire when ML unavailable (got: ${outB})`);
    } finally {
      try { fs.rmSync(fakeMlDir, { recursive: true }); } catch { /* ignore cleanup */ }
    }
  });

  // -------------------------------------------------------------------------
  // Silent (correct inbound edit): example-game-repo EM edits a memo addressed to example-game-repo
  // in example-game-repo's own inbox (status: open → actioned) → SILENT.
  // Simulates the normal memo-lifecycle actioning step.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — correct inbound edit (to: matches landing repo) → SILENT', async () => {
    const tmp = makeTempDir();
    const tmpBasename = path.basename(tmp);
    const thisEmId = `${tmpBasename}-em`;
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'inbox'), { recursive: true });

    // Write initial file then Edit it (status change). The to: matches thisEmId.
    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-inbound-edit.md');
    const initial = [
      '---',
      'title: "Inbound memo"',
      'from: example-game-repo-em',
      `to: ${thisEmId}`,
      'created: 2026-05-23',
      'status: open',
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Body.',
    ].join('\n');
    fs.writeFileSync(filePath, initial, 'utf8');

    // Edit: flip status open → actioned (canonical receiver action).
    const payload = editPayload(filePath, 'status: open', 'status: actioned', tmp);
    const { stdout, exitCode } = await runHook(payload);

    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'correct inbound edit (to: == landing repo) must be SILENT');
  });

  // -------------------------------------------------------------------------
  // No routing-mismatch offer (M2 guard): docs/plans/ file with To:/From: example
  // quotes → no ROUTING-MISMATCH offer (Chunk G's branch does not fire on non-memo paths).
  //
  // Note: the pre-G Chunk 5 hasFreeFormMemoHeader() check may fire its own offer on
  // this content (To:/From: headers in a non-YAML file). That is existing behavior,
  // not Chunk G's responsibility. Chunk G's routing-mismatch check adds no SECOND offer.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — plan quoting To:/From: headers does not add routing-mismatch offer (M2 guard)', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'test-plan-with-memo-examples.md');
    const content = [
      '# Plan',
      '',
      '## Example memo format',
      '',
      'A memo looks like this:',
      '',
      'To: example-game-repo-em',
      'From: claude-central-em',
      '',
      'Body text here.',
      '',
      '## Analysis',
      '',
      'The above is just an example.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    // Chunk G's routing-mismatch check does NOT fire on docs/plans/ because:
    //   - No YAML `to:` field (signal a absent)
    //   - hasFreeFormMemoHeader() returns true BUT path is not memo-shaped
    //     (no /memos/ or /cross-repo/ segment — signal b absent)
    // Any output that IS present comes from the existing Chunk 5 content-based check
    // (hasFreeFormMemoHeader on any file with To:/From: headers — that is a separate concern).
    // What we verify: the output does NOT include a routing-mismatch offer message.
    if (stdout.length > 0) {
      const parsed = JSON.parse(stdout);
      const msg = parsed.hookSpecificOutput.additionalContext ||
                  parsed.hookSpecificOutput.permissionDecisionReason || '';
      assert.ok(
        !msg.includes('does not match the repo you are writing into'),
        `Chunk G routing-mismatch offer must NOT fire on a non-memo plan file, got: ${msg}`
      );
    }
    // If stdout is empty → fully silent (also correct).
  });

  // -------------------------------------------------------------------------
  // Silent (unresolvable to: M2 negative-spec): memo `to: nonexistent-em` → SILENT.
  // If to: doesn't end in -em or match a central alias → unresolvable → can't prove
  // mismatch → don't offer.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — unresolvable to: nonexistent-em → SILENT (M2 negative-spec)', async () => {
    // Write a YAML memo with a to: value that doesn't match the -em pattern (typo/unknown).
    const filePath = path.join(CLAUDE_ROOT, 'cross-repo', '2026-05-23-unknown-receiver.md');
    const content = [
      '---',
      'title: "Memo with unknown receiver"',
      'from: claude-central-em',
      'to: some-typo-without-em-suffix',
      'created: 2026-05-23',
      'status: open',
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Body.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'unresolvable to: must be SILENT (can\'t prove mismatch)');
  });

  // -------------------------------------------------------------------------
  // Silent (override): COORDINATOR_OVERRIDE_MEMO_REDIRECT=1 → routing check skipped.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — COORDINATOR_OVERRIDE_MEMO_REDIRECT=1 → SILENT', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'cross-repo', '2026-05-23-mismatch-override.md');
    const content = [
      '---',
      'title: "Mismatch but overridden"',
      'from: claude-central-em',
      'to: example-game-repo-em',
      'created: 2026-05-23',
      'status: open',
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Body.',
    ].join('\n');

    const result = await new Promise((resolve, reject) => {
      const env = { ...process.env, COORDINATOR_OVERRIDE_MEMO_REDIRECT: '1' };
      delete env.COORDINATOR_SCHEMA_STRICT;
      const child = require('node:child_process').spawn(process.execPath, [HOOK_SCRIPT], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env,
      });
      let stdout = '';
      let stderr = '';
      child.stdout.on('data', d => { stdout += d.toString(); });
      child.stderr.on('data', d => { stderr += d.toString(); });
      child.on('close', exitCode => resolve({ stdout, stderr, exitCode }));
      child.on('error', reject);
      child.stdin.write(JSON.stringify(writePayload(filePath, content, CLAUDE_ROOT)));
      child.stdin.end();
    });

    assert.equal(result.exitCode, 0, 'should exit 0');
    // The routing check is skipped; the write proceeds to schema validation. Since the
    // cross-repo path matches the cross-repo-memo schema, a schema violation may fire
    // (fields like delivery_mode). We only check that routing offer is NOT present.
    const output = result.stdout;
    if (output.length > 0) {
      const parsed = JSON.parse(output);
      const msg = parsed.hookSpecificOutput.additionalContext ||
                  parsed.hookSpecificOutput.permissionDecisionReason || '';
      assert.ok(
        !msg.includes('does not match the repo you are writing into'),
        `routing-mismatch offer must be absent when COORDINATOR_OVERRIDE_MEMO_REDIRECT=1, got: ${msg}`
      );
    }
    // If output is empty → routing check was silent, which is also correct.
  });

  // =========================================================================
  // whole-document-yaml mode — improvement-queue / bug-backlog / debt-backlog
  //
  // These three schemas use match_mode: whole-document-yaml. The hook must parse
  // the whole file as a bare YAML document (no --- fences) and validate its
  // required fields — without falsely warning "missing frontmatter".
  // =========================================================================

  // -------------------------------------------------------------------------
  // Allow: well-formed bare-YAML improvement-queue entry → SILENT.
  // All required fields present: created, title, body, status, surface,
  // proposed_action, from_repo, change_kind.
  // -------------------------------------------------------------------------
  test('whole-document-yaml — improvement-queue valid entry is SILENT (no missing-frontmatter warn)', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'improvement-queue'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'improvement-queue', '2026-07-01-test.yaml');

    const content = [
      'created: 2026-07-01',
      'title: "Test improvement entry"',
      'body: "Some improvement description."',
      'status: open',
      'surface: hooks/scripts/validate-frontmatter-schema.js',
      'proposed_action: "Add whole-document-yaml support"',
      'from_repo: coordinator-claude',
      'change_kind: hook-edit',
    ].join('\n');

    // Pre-create so C0a scaffold offer doesn't fire.
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `well-formed improvement-queue entry must be SILENT, got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // -------------------------------------------------------------------------
  // Block: bare-YAML improvement-queue entry MISSING a required field → deny.
  // Proves the branch validates content, not merely suppresses the warning.
  // -------------------------------------------------------------------------
  test('whole-document-yaml — improvement-queue entry missing "status" → required-field error', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'improvement-queue'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'improvement-queue', '2026-07-01-missing-status.yaml');

    // Omit required field `status`
    const content = [
      'created: 2026-07-01',
      'title: "Missing status field"',
      'body: "Entry without status."',
      'surface: bin/some-script.sh',
      'proposed_action: "Fix it"',
      'from_repo: coordinator-claude',
      'change_kind: hook-edit',
    ].join('\n');

    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'hook always exits 0');
      assert.ok(stdout.length > 0, 'missing required field must produce output');
      const parsed = JSON.parse(stdout);
      assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
      const reason = parsed.hookSpecificOutput.permissionDecisionReason;
      assert.ok(
        reason.includes('status'),
        `deny reason must mention the missing field "status", got: ${reason}`
      );
      // Must NOT say "missing frontmatter" — this is a content validation error, not a
      // parsing error. The whole-document-yaml branch must parse the file successfully
      // and validate its content, producing a field-level error rather than the generic
      // "no YAML frontmatter found" message.
      assert.ok(
        !reason.includes('no YAML frontmatter found'),
        `deny reason must NOT say "no YAML frontmatter found" for bare-YAML files, got: ${reason}`
      );
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // Note: CLI self-write exemption is not tested here because bin/cross-repo-memo
  // writes via Python open(path,"w") at bin/cross-repo-memo:444 (_write_file),
  // NOT the Claude Write tool. PreToolUse hooks fire on Claude Code tool invocations,
  // not on subprocess fs writes — the exemption is structural, not runtime-checkable.

  // =========================================================================
  // Default match_mode — non-.md applies_to schema with NO explicit match_mode
  //
  // review-trail.yaml declares applies_to: "state/review-trail/*.json" but does
  // NOT set match_mode. Before this fix, loadSchemas left match_mode undefined,
  // the hook's dispatch fell into the generic "missing frontmatter" else-branch
  // (validate-frontmatter-schema.js), and every required field on a valid
  // bare-JSON review-trail record was reported "missing" — a false positive on
  // every write to this class of record. bin/lib/schema.js now defaults
  // match_mode to whole-document-yaml at load time whenever applies_to targets
  // .yaml/.json and no explicit match_mode is set (applyDefaultMatchMode).
  //
  // Spec backlink: state/lessons/2026-07-09-idempotency-dedup-scans-must-resolve-the-d56041880cd8.yaml
  // =========================================================================

  test('default match_mode — review-trail (.json, no explicit match_mode) valid record is SILENT (no missing-frontmatter warn)', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'review-trail'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'review-trail', '2026-07-09-000000-test.json');

    const record = {
      sha_range: 'abc1234..def5678',
      reviewer: 'code-reviewer',
      scope: 'coordinator/bin/lib/schema.js',
      scope_kind: 'diff',
      verdict: 'approved',
      diff_loc: 42,
      session_id: 'test-session',
      workstream: null,
    };
    const content = JSON.stringify(record, null, 2);

    // Pre-create so C0a scaffold offer doesn't fire.
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `well-formed no-match_mode review-trail entry must be SILENT, got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  test('default match_mode — review-trail (.json, no explicit match_mode) entry missing "verdict" → required-field error, not "missing frontmatter"', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'review-trail'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'review-trail', '2026-07-09-000001-missing-verdict.json');

    // Omit required field `verdict`
    const record = {
      sha_range: 'abc1234..def5678',
      reviewer: 'code-reviewer',
      scope: 'coordinator/bin/lib/schema.js',
      scope_kind: 'diff',
      diff_loc: 42,
      session_id: 'test-session',
      workstream: null,
    };
    const content = JSON.stringify(record, null, 2);

    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'hook always exits 0');
      assert.ok(stdout.length > 0, 'missing required field must produce output');
      const parsed = JSON.parse(stdout);
      assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
      const reason = parsed.hookSpecificOutput.permissionDecisionReason;
      assert.ok(
        reason.includes('verdict'),
        `deny reason must mention the missing field "verdict", got: ${reason}`
      );
      // Must NOT say "missing frontmatter" — proves the default landed as
      // whole-document-yaml, not the generic no-match_mode else-branch that
      // flags every required field as absent regardless of actual content.
      assert.ok(
        !reason.includes('no YAML frontmatter found'),
        `deny reason must NOT say "no YAML frontmatter found" for a no-match_mode .json schema, got: ${reason}`
      );
      assert.ok(
        !/sha_range|reviewer|scope_kind/.test(reason),
        `deny reason must NOT list every required field as missing (all-missing false-positive), got: ${reason}`
      );
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  test('default match_mode — explicit match_mode still wins over the .yaml/.json default (review-findings stays no-frontmatter despite .md applies_to being the control case)', async () => {
    // Sanity control: an explicit match_mode (no-frontmatter, on review-findings.yaml)
    // must continue to be honored verbatim — the default only fills the gap when
    // match_mode is entirely absent. This mirrors the pre-existing no-frontmatter
    // suite below but is placed here to make the "explicit wins" invariant explicit
    // in the same block as the new default-application tests.
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'state', 'review-trail', 'findings'), { recursive: true });
    const filePath = path.join(tmp, 'state', 'review-trail', 'findings', '2026-07-09-test-finding.md');
    const content = '# Finding\n\nSome prose finding, deliberately no --- frontmatter block.\n';

    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, tmp), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `explicit no-frontmatter match_mode must remain SILENT, got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // =========================================================================
  // no-frontmatter mode — review-findings
  //
  // review-findings.yaml declares match_mode: no-frontmatter (schemas/review-findings.yaml)
  // because its records are deliberately bare prose artifacts (see
  // coordinator-doc-new's _scaffold_review_findings negative-spec). Before this
  // fix, the hook's generic "missing frontmatter" branch fired on every
  // code-reviewer Edit to these sidecars — a false-positive warning on every
  // review this session. The no-frontmatter branch must stay SILENT for any
  // schema-matched content with no --- block, without requiring one.
  //
  // Spec backlink: this test exercises the fix for the break-class bug fixed
  // in coordinator/hooks/scripts/validate-frontmatter-schema.js (schema.match_mode
  // === 'no-frontmatter' branch) and coordinator/schemas/review-findings.yaml.
  // =========================================================================

  test('no-frontmatter — review-findings Edit with no YAML frontmatter is SILENT (no missing-frontmatter warn)', async () => {
    const filePath = path.join(
      CLAUDE_ROOT, 'state', 'review-trail', 'findings',
      '2026-07-08-codereview-sliceTEST-no-frontmatter-mode.md'
    );
    const oldContent = [
      '# Code Review: Slice TEST -- coordinator/hooks/scripts/validate-frontmatter-schema.js',
      '',
      'Reviewer: code-reviewer',
      'Scope: coordinator/hooks/scripts/validate-frontmatter-schema.js',
      'Diff range: PLACEHOLDER',
      '',
      '## Findings',
      '',
      '<!-- FINDINGS -->',
      '',
    ].join('\n');
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, oldContent);
    try {
      const { stdout, exitCode } = await runHook(
        editPayload(filePath, '<!-- FINDINGS -->', 'P0: example finding — no issue, sample body.', CLAUDE_ROOT),
        { strict: true }
      );
      assert.equal(exitCode, 0, 'hook always exits 0');
      assert.equal(
        stdout, '',
        `review-findings Edit with no frontmatter must be SILENT even under strict mode, got: ${stdout}`
      );
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  test('no-frontmatter — review-findings Write with no YAML frontmatter is SILENT', async () => {
    const filePath = path.join(
      CLAUDE_ROOT, 'state', 'review-trail', 'findings',
      '2026-07-08-codereview-sliceTEST-no-frontmatter-write.md'
    );
    const content = [
      '# Code Review: Slice TEST -- some/path.js',
      '',
      'Reviewer: code-reviewer',
      'Scope: some/path.js',
      'Diff range: PLACEHOLDER',
      '',
      '## Findings',
      '',
      'P0: example finding.',
      '',
    ].join('\n');
    // Pre-create so the C0a scaffold offer doesn't fire (this test targets the
    // frontmatter-presence branch specifically, not the new-file scaffold offer).
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
      assert.equal(exitCode, 0, 'hook always exits 0');
      assert.equal(stdout, '', `review-findings Write with no frontmatter must be SILENT, got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // -------------------------------------------------------------------------
  // AC-9 negative cases: non-memo Writes with a `to:` YAML field → SILENT.
  //
  // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk G
  // Review: F4 — isThisAMemo gate fires on any YAML `to:`, so we prove SILENCE on
  // non-memo-shaped paths even when `to:` is present in frontmatter.
  // -------------------------------------------------------------------------

  // AC-9(a): Write to docs/plans/test.md with YAML `to: example-game-repo-em` → SILENT.
  //
  // F4 fix applied (code-reviewer 2026-05-23): isThisAMemo gate now requires
  // isMemoShapedPath for BOTH signals (yamlToValue AND hasFreeForm). A docs/plans/
  // path with YAML `to:` is NOT memo-shaped, so the routing check does not fire.
  // This catches the false-positive class on non-memo files that happen to use the
  // `to:` key in their own frontmatter.
  test('AC-9(a) (Chunk G/F4) — docs/plans/ Write with YAML to: example-game-repo-em → SILENT routing-wise (path not memo-shaped)', async () => {
    // Use complete plan frontmatter (author, status) so the plan schema doesn't itself
    // emit a missing-required-field warning. The assertion target here is the
    // routing-mismatch offer specifically, NOT general schema silence.
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'test.md');
    const content = [
      '---',
      'title: "Some plan"',
      'author: test',
      'created: 2026-05-23',
      'status: draft',
      'to: example-game-repo-em',
      '---',
      '',
      'Plan body — the YAML `to:` here must NOT trigger the cross-repo routing offer.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0 (never block — offer shape)');
    // The routing-mismatch offer message contains "does not match the repo you are writing into".
    // If stdout is empty OR if stdout exists but does NOT carry that routing-mismatch fragment,
    // F4 is satisfied — the routing check did not fire on this non-memo-shaped path.
    if (stdout.length > 0) {
      const parsed = JSON.parse(stdout);
      const msg = parsed.hookSpecificOutput?.additionalContext || '';
      assert.ok(
        !msg.includes('does not match the repo you are writing into'),
        `F4 fix: routing offer must NOT fire on docs/plans/ with YAML to:. Got: ${msg}`
      );
    }
  });

  // AC-9(b): Write to state/handoffs/2026-05-23-test.md with standard handoff
  // frontmatter (no `to:` field) → SILENT.
  // A canonical handoff has no `to:` YAML field — yamlToValue returns null →
  // isThisAMemo is false → routing check does not fire.
  test('AC-9(b) (Chunk G) — state/handoffs/ Write with standard handoff frontmatter (no to:) → SILENT', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'handoffs', '2026-05-23-test.md');
    const content = [
      '---',
      'title: "Handoff 2026-05-23"',
      'kind: handoff',
      'status: active',
      'created: 2026-05-23',
      'predecessor: none',
      'deployment_state: ready_to_fire',
      '---',
      '',
      'Handoff body.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    // No to: field → yamlToValue null → isThisAMemo false → routing check silent.
    if (stdout.length > 0) {
      const parsed = JSON.parse(stdout);
      const msg = parsed.hookSpecificOutput.additionalContext ||
                  parsed.hookSpecificOutput.permissionDecisionReason || '';
      assert.ok(
        !msg.includes('does not match the repo you are writing into'),
        `routing-mismatch offer must NOT fire on handoff without to: field, got: ${msg}`
      );
    }
    // stdout empty → fully silent; also correct.
  });

  // -------------------------------------------------------------------------
  // Schema glob-match: cross-repo/inbox/<digit>*.md triggers schema validation.
  //
  // MN5 (AC-4 glob-match requirement): confirms that the applies_to glob
  // "cross-repo/inbox/[0-9]*.md" in cross-repo-memo.yaml actually MATCHES a
  // real inbox path (not just that the own-inbox guard fires). Tests that
  // globToRegex handles the bracket+segment combination at the deeper path.
  //
  // We use an INVALID memo (missing required fields) so the validator returns a
  // schema-violation payload — proving the schema was matched and applied.
  //
  // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk C (MN5)
  // -------------------------------------------------------------------------
  test('Schema glob-match: cross-repo/inbox/<digit>*.md matches cross-repo-memo schema', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'cross-repo', 'inbox'), { recursive: true });

    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-schema-match-test.md');

    // Deliberately omit required fields (from, to, status) so the validator fires a violation.
    const invalidContent = [
      '---',
      'title: "Missing required fields"',
      'created: 2026-05-23',
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Body.',
    ].join('\n');

    // Run in strict mode so schema violations emit deny (not just additionalContext).
    const { stdout, exitCode } = await runHook(writePayload(filePath, invalidContent, tmp), { strict: true });

    assert.equal(exitCode, 0, 'hook must exit 0');
    assert.ok(stdout.length > 0, 'schema match must produce output (violation detected)');
    const parsed = JSON.parse(stdout);
    // A schema violation on a matched file produces a deny or warn payload.
    // The key check: output is non-empty → the glob matched and schema was applied.
    const output = parsed.hookSpecificOutput;
    const hasViolation =
      output.permissionDecision === 'deny' ||
      (output.additionalContext && output.additionalContext.includes('cross-repo-memo'));
    assert.ok(
      hasViolation,
      `cross-repo/inbox/<digit>*.md must match the cross-repo-memo schema and produce a violation for invalid content; got: ${JSON.stringify(output)}`
    );
  });

  // -------------------------------------------------------------------------
  // Regression — BS-2026-05-19-FRONTMATTER-HOOK-COMMENT-FALSE-POSITIVES
  //
  // Cross-repo memo from example-game-repo-em (2026-05-28): plan frontmatter containing
  // YAML `# comment` annotations on list items (or scalar values) produced
  // dirty scalars (e.g. "draft  # alpha") that failed enum validation, surfacing
  // as a "missing required key" warning on otherwise well-formed frontmatter.
  // The fix strips inline `# ...` comments in parseScalar respecting quoted spans.
  // -------------------------------------------------------------------------
  test('Regression — plan with inline # comments on list items + status passes silently', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'test-inline-comments.md');
    const content = [
      '---',
      'title: t',
      'created: 2026-05-28',
      'author: example-game-repo-em',
      'status: draft  # canonical starting state',
      'target_surfaces:',
      '  - /foo/path  # surface A',
      '  - /bar/path  # surface B',
      '---',
      '# Plan body',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates that inline YAML # comments are stripped correctly.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `well-formed plan with # comments must pass silently; got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  test('Regression — quoted "#" inside scalar is preserved (not treated as comment)', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'test-quoted-hash.md');
    const content = [
      '---',
      'title: "this # is part of the title"',
      'created: 2026-05-28',
      'author: example-game-repo-em',
      'status: draft',
      '---',
      '# body',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates that a quoted # is not treated as a YAML comment.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `quoted # must not be stripped as a comment; got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // Direct unit assertions for stripInlineComment edge cases.
  test('Unit — stripInlineComment edge cases', () => {
    const { _stripInlineComment: strip } = require('../../bin/lib/schema.js');
    assert.equal(strip(''), '', 'empty input');
    // `#` at column 0 followed by a non-space is NOT a comment opener (preserves
    // `#N`-style tokens — see d9532ec6 stripInlineComment #-truncation fix). A bare
    // `#bare` is a value, not a comment. A genuine column-0 comment requires a space
    // after the `#` (asserted separately below).
    // Bug-fix breadcrumb: the old expectation was `strip('#bare') === ''` — stale after
    // the d9532ec6 #-truncation semantics change. The IMPLEMENTATION is correct; only the
    // TEST assertion was wrong. Fixed here by asserting '#bare' (preserved, not stripped).
    assert.equal(strip('#bare'), '#bare', 'bare # at column 0 followed by non-space is preserved');
    assert.equal(strip('# real comment'), '', 'column-0 # followed by space is a comment → empty');
    assert.equal(strip('foo#bar'), 'foo#bar', '# inside bareword (no preceding space) preserved');
    assert.equal(strip('foo  # comment'), 'foo', 'whitespace-preceded # strips');
    assert.equal(strip('"foo # bar"'), '"foo # bar"', '# inside double-quoted preserved');
    assert.equal(strip("'foo # bar'"), "'foo # bar'", '# inside single-quoted preserved');
    assert.equal(strip("'it''s fine' # tail"), "'it''s fine'",
                 "single-quoted '' escape: # after the closed quote still strips correctly");
  });

  // Regression — quoted "#" inside an ENUM value is preserved (so the validator
  // sees the dirty enum value and fails it cleanly, rather than silently passing
  // a stripped value that happened to match a real enum).
  test('Regression — quoted "#" inside enum value fails enum (not silently stripped)', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'test-enum-quoted-hash.md');
    const content = [
      '---',
      'title: t',
      'created: 2026-05-28',
      'author: example-game-repo-em',
      'status: "draft # intended"',
      '---',
      '# body',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates that a quoted # in an enum value is preserved and fails validation.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.ok(stdout.length > 0, 'quoted # in enum value must fail enum, not silently pass');
      const parsed = JSON.parse(stdout);
      assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
      assert.ok(
        /invalid enum value/.test(parsed.hookSpecificOutput.permissionDecisionReason),
        `should report enum failure; got: ${parsed.hookSpecificOutput.permissionDecisionReason}`
      );
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // Regression — inline list with trailing # comment is parsed as a list, not
  // a string. Pre-strip in parseYamlLines handles the `[a, b]  # comment` shape
  // that endsWith(']') would otherwise miss.
  test('Regression — inline list with trailing # comment parses as list-of-string', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'handoffs', 'test-inline-list-comment.md');
    const content = [
      '---',
      'title: t',
      'created: 2026-05-28',
      'branch: work/test/2026-05-28',
      'status: active',
      'predecessor: null',
      'scope: ["foo/**", "bar/**"]  # trailing inline comment',
      '---',
      '# body',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates that an inline list with trailing # is parsed as a list.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    // Handoff schema has workstream as optional. The point of the test is that
    // pre-strip lets parseInlineList run (vs. parseScalar returning a string),
    // so the validator does not fire a "expected a list" violation.
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `inline list with trailing # must parse as a list; got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // =========================================================================
  // C3-tests — hook reorder regression net (Wave 1, RED-first)
  //
  // Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C3
  //
  // These four cases encode the AC5 oracle for the C3-impl hook reorder:
  //   build prospectiveContent → parseFrontmatter → matchSchema → tracked-ness gate.
  //
  // Cases 1-2 are GREEN NOW (regression guards — must stay green after C3-impl).
  // Cases 3-4 are RED NOW (new capability / fight-the-hook fix — must go green after C3-impl).
  //
  // "Verify RED for the right reason": cases 3-4 fail because the CURRENT hook is
  // glob-only (plan.yaml wins over kind: review-sidecar), NOT because of a test bug.
  // =========================================================================

  // -------------------------------------------------------------------------
  // C3-test-1 [GREEN NOW — regression guard]: silent-exit-preserved
  //
  // An Edit payload where old_string does NOT appear in the target file, on a path
  // that matches NO schema glob (docs/notes/random.md). Today the hook exits silent
  // at the schema-not-found gate (line 700, before building prospectiveContent).
  // After the C3-impl reorder the hook builds prospectiveContent first, reads the
  // file, and exits silent at the Edit file-not-found path (same observable outcome).
  //
  // This guard confirms the reorder preserves all silent-exit paths: a non-tracked
  // path with an unmatched old_string must NEVER emit output.
  // -------------------------------------------------------------------------
  test('C3-test-1 [GREEN guard] — silent-exit-preserved: Edit on non-tracked path with mismatched old_string stays silent', async () => {
    // docs/notes/ is not a schema-tracked directory (no schema applies_to covers it).
    // The file does not exist on disk → file-not-found silent path fires after reorder.
    // old_string mismatch would also fire silently if the file existed.
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'notes', 'random.md');
    const payload = editPayload(
      filePath,
      'THIS STRING DOES NOT EXIST IN ANY FILE',
      'replacement',
      CLAUDE_ROOT
    );

    const { stdout, exitCode } = await runHook(payload);
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'non-tracked path with old_string mismatch must always produce SILENT output');
  });

  // -------------------------------------------------------------------------
  // C3-test-2 [GREEN NOW — regression guard]: kindless-plan-unchanged
  //
  // A Write payload for docs/plans/2026-01-01-xyz.md with valid plan frontmatter
  // (title/created/author/status: draft) and NO kind: field. Today the hook resolves
  // to plan.yaml via path glob and validates clean. After C3-impl the hook parses
  // frontmatter first, sees no kind:, falls back to glob → still plan.yaml → still
  // validates clean. Back-compat for ~174 kind-less plans is automatic via fallback.
  // -------------------------------------------------------------------------
  test('C3-test-2 [GREEN guard] — kindless-plan-unchanged: Write of valid kindless plan stays silent', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', '2026-01-01-xyz.md');
    const content = [
      '---',
      'title: Test Plan',
      'created: 2026-01-01',
      'author: test-executor',
      'status: draft',
      '---',
      '# Plan body',
      '',
      'No kind: field — resolves to plan.yaml via path glob (back-compat).',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates that a kindless plan routes to plan.yaml and validates clean.
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
      assert.equal(exitCode, 0, 'should exit 0');
      assert.equal(stdout, '', `kindless plan with valid plan fields must produce no violation; got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // -------------------------------------------------------------------------
  // C3-test-3 [RED NOW — new capability]: kind-admitted-new-file
  //
  // EXPECTED TO FAIL against the CURRENT hook (glob-only routing).
  //
  // A Write for docs/plans/2026-06-23-kind-routing-test.md with kind: review-sidecar
  // and only {plan: "docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md"} in
  // frontmatter (no title/created/author/status). This path DOES match plan.yaml's
  // broad "docs/plans/*.md" glob; it does NOT match review-sidecar.yaml's more-specific
  // "docs/plans/*-review.md" glob. Today the hook first-matches plan.yaml → plan.yaml
  // requires title/created/author/status → emits a violation (stdout non-empty).
  //
  // After C3-impl: kind: review-sidecar is parsed BEFORE glob-matching →
  // matchSchema() routes to review-sidecar.yaml (kind-first) → review-sidecar only
  // requires plan: → validates clean → SILENT.
  //
  // The test asserts stdout === '' (clean pass). TODAY this FAILS because plan.yaml
  // wins the first-match race and emits a missing-required-fields violation. This is
  // the correct RED — the failure is the current hook's glob-only limitation, not a
  // test bug.
  // -------------------------------------------------------------------------
  test('[AC5 kind-admitted-new-file] — Write with kind: review-sidecar at non-review-suffix path validates against review-sidecar schema (no plan-field violation)', async () => {
    // Path matches plan.yaml glob "docs/plans/*.md" BUT lacks the ".review.md" suffix
    // so it does NOT match review-sidecar.yaml's "docs/plans/*.review.md" glob.
    // Content has kind: review-sidecar + only plan: (valid for review-sidecar, invalid for plan.yaml).
    // C3-impl landed: kind-first routing selects review-sidecar.yaml → clean pass (GREEN).
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', '2026-06-23-kind-routing-test.md');
    const content = [
      '---',
      'kind: review-sidecar',
      'plan: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md',
      '---',
      '# Kind-routing test',
      '',
      'This file has kind: review-sidecar and only plan: — no plan-schema fields.',
      'After C3-impl, kind routing selects review-sidecar.yaml and this passes clean.',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates kind-first routing to review-sidecar.yaml (C3-impl).
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
      assert.equal(exitCode, 0, 'should exit 0 (hook never exits non-zero)');
      assert.equal(stdout, '', `kind: review-sidecar at non-review-suffix path must validate against review-sidecar.yaml (no plan-field violation); got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

  // -------------------------------------------------------------------------
  // C3-test-4 [RED NOW — fight-the-hook-fixed]: kind-sidecar-no-plan-fields
  //
  // EXPECTED TO FAIL against the CURRENT hook (glob-only routing forces plan.yaml).
  //
  // A Write for docs/plans/foo.the Director of Engineering-review.md with kind: review-sidecar + only
  // {plan: "docs/plans/foo.md"} (no title/author/status). This path DOES match
  // review-sidecar.yaml's "docs/plans/*-review.md" glob, but plan.yaml's broader
  // "docs/plans/*.md" glob appears FIRST in _byGlob (plan.yaml loads before
  // review-sidecar.yaml alphabetically). So today the hook routes to plan.yaml
  // and emits a plan-schema violation (missing title/author/status).
  //
  // This is the documented fight-the-hook bug: the Director of Engineering writing a review sidecar under
  // docs/plans/ was forced to add fake plan fields (title, author, status) to pass.
  //
  // After C3-impl: matchSchema() parses kind: review-sidecar FIRST → routes to
  // review-sidecar.yaml → only plan: required → validates clean → SILENT.
  //
  // The test asserts stdout === '' (no plan-schema violation). TODAY this FAILS
  // because plan.yaml is matched first-match and emits a violation for missing
  // required fields. After C3-impl this goes green.
  // -------------------------------------------------------------------------
  test('[AC5 fight-the-hook-fixed] — Write for docs/plans/foo.the Director of Engineering-review.md with kind: review-sidecar emits NO plan-schema violation', async () => {
    // Path matches BOTH plan.yaml "docs/plans/*.md" AND review-sidecar.yaml "docs/plans/*.review.md".
    // C3-impl landed: kind: review-sidecar wins (kind-first routing) → review-sidecar schema → clean.
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'foo.the Director of Engineering-review.md');
    const content = [
      '---',
      'kind: review-sidecar',
      'plan: docs/plans/foo.md',
      '---',
      '# the Director of Engineering review sidecar',
      '',
      'This sidecar has kind: review-sidecar and only plan: — no plan-schema fields.',
      'Kind routing selects review-sidecar.yaml and this passes clean.',
    ].join('\n');
    // Pre-create so fs.existsSync() is true → C0a scaffold offer doesn't fire.
    // This test validates kind-first routing fixes the fight-the-hook bug (C3-impl).
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
    try {
      const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
      assert.equal(exitCode, 0, 'should exit 0 (hook never exits non-zero)');
      // Primary assertion: no stdout when kind routing is correct.
      assert.equal(stdout, '', `docs/plans/foo.the Director of Engineering-review.md with kind: review-sidecar must NOT produce a plan-schema violation; got: ${stdout}`);
    } finally {
      try { fs.unlinkSync(filePath); } catch { /* ignore */ }
    }
  });

});
