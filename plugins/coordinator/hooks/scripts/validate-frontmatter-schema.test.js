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

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'should emit no JSON on pass');
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

  // =========================================================================
  // Chunk 5 — design-as-offers hand-rolling catch
  // Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 5
  // =========================================================================

  // -------------------------------------------------------------------------
  // Offer (path-based): Write to state/memos/ → CLI offer emitted
  // -------------------------------------------------------------------------
  test('Offer — Write to state/memos/ emits cross-repo-memo CLI offer', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'memos', '2026-05-23-holodeck-to-addon.md');
    const content = [
      '# Memo: holodeck to addon',
      '',
      'To: project-rag-ue-addon-em',
      'From: holodeck-em',
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
      'From: holodeck-em',
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

    // Normal inbound: from=holodeck-em, to=<this-repo-em>. The own-inbox guard stays
    // silent (from != thisEmId). The routing check doesn't fire (canonical inbox path).
    const filePath = path.join(tmp, 'cross-repo', 'inbox', '2026-05-23-holodeck-request.md');
    const content = [
      '---',
      'title: Update indexer schema',
      'from: holodeck-em',
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
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
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
  // Genuine tag typos are still caught (the validator's actual value).
  // -------------------------------------------------------------------------
  test('Lessons — genuine tag typo [univeral] is still caught', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'tasks', 'lessons.md');
    const content = [
      '# Lessons',
      '',
      '- **Typo entry [univeral]** — misspelled tag should be flagged.',
      '  Detail line.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should still flag a misspelled tag');
    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    assert.ok(
      parsed.hookSpecificOutput.permissionDecisionReason.includes('univeral'),
      'reason should mention the typo tag'
    );
  });

  // =========================================================================
  // Lessons delta-scoping: a per-write hook validates only the text being
  // written now, never the whole reconstructed file. An Edit that appends a
  // clean entry must NOT surface pre-existing entries' tag drift. Whole-file
  // drift is swept separately by query-records --validate-all in /update-docs.
  // =========================================================================

  // -------------------------------------------------------------------------
  // Edit appending a clean entry to a file with pre-existing junk → silent.
  // -------------------------------------------------------------------------
  test('Lessons — Edit appending clean entry does not re-flag pre-existing drift', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'tasks'), { recursive: true });
    const filePath = path.join(tmp, 'tasks', 'lessons.md');
    // Pre-existing file already carries a genuinely-bad-tag entry.
    const existing = [
      '# Lessons',
      '',
      '- **Old broken entry [bogus]** — this pre-existing tag is invalid.',
      '  But it is not what the current write is touching.',
      '',
    ].join('\n');
    fs.writeFileSync(filePath, existing, 'utf8');

    const oldString = '  But it is not what the current write is touching.\n';
    const newString = [
      '  But it is not what the current write is touching.',
      '',
      '- **Fresh clean entry [universal]** — this is the entry I am adding now.',
      '  It is correctly tagged.',
      '',
    ].join('\n');

    const { stdout, exitCode } = await runHook(editPayload(filePath, oldString, newString, tmp), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `clean appended entry must not re-flag pre-existing drift, got: ${stdout}`);

    // Prove the suppression is the delta-scoping, not a shape mismatch on the
    // pre-existing entry (code-review F7): a whole-file Write of the SAME final
    // content DOES catch the pre-existing [bogus] tag. So the drift is real
    // drift the Edit deliberately scoped past, not invisible-to-the-validator.
    const wholeFile = existing.replace(oldString, newString);
    const whole = await runHook(writePayload(filePath, wholeFile, tmp), { strict: true });
    assert.ok(whole.stdout.length > 0, 'whole-file Write should catch the pre-existing [bogus] tag');
    assert.ok(
      JSON.parse(whole.stdout).hookSpecificOutput.permissionDecisionReason.includes('bogus'),
      'whole-file deny should name the pre-existing bad tag'
    );
  });

  // -------------------------------------------------------------------------
  // Edit appending a BAD-tag entry → caught (delta-scoping doesn't go blind).
  // -------------------------------------------------------------------------
  test('Lessons — Edit appending a bad-tag entry is still caught', async () => {
    const tmp = makeTempDir();
    fs.mkdirSync(path.join(tmp, 'tasks'), { recursive: true });
    const filePath = path.join(tmp, 'tasks', 'lessons.md');
    const existing = [
      '# Lessons',
      '',
      '- **Existing fine entry [universal]** — all good here.',
      '  Detail.',
      '',
    ].join('\n');
    fs.writeFileSync(filePath, existing, 'utf8');

    const oldString = '  Detail.\n';
    const newString = [
      '  Detail.',
      '',
      '- **New entry [whatever]** — bad tag in the text being written now.',
      '  Detail.',
      '',
    ].join('\n');

    const { stdout, exitCode } = await runHook(editPayload(filePath, oldString, newString, tmp), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should flag the bad tag in the delta');
    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    assert.ok(
      parsed.hookSpecificOutput.permissionDecisionReason.includes('whatever'),
      'reason should mention the bad tag in the appended entry'
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
    const senderEmId = 'holodeck-em';

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
  // DENY: holodeck alias case — basename=claude-unreal-holodeck → holodeck-em.
  // Verifies the REPO_BASENAME_TO_EM_SHORTNAME alias map is exercised.
  // -------------------------------------------------------------------------
  test('Own-inbox guard — DENY: holodeck alias (claude-unreal-holodeck → holodeck-em)', async () => {
    // Create a temp dir named "claude-unreal-holodeck" to simulate the holodeck repo.
    // resolveRepoRoot will fall back to cwd (no .git present) → basename = "claude-unreal-holodeck".
    const holodeckDir = path.join(os.tmpdir(), 'claude-unreal-holodeck');
    fs.mkdirSync(path.join(holodeckDir, 'cross-repo', 'inbox'), { recursive: true });

    const thisEmId = 'holodeck-em'; // alias resolution: claude-unreal-holodeck → holodeck-em
    const otherEmId = 'project-rag-em';

    const filePath = path.join(holodeckDir, 'cross-repo', 'inbox', '2026-05-23-holodeck-outbound.md');
    const content = inboxMemoContent({ from: thisEmId, to: otherEmId });

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, holodeckDir));

    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'should emit deny JSON for holodeck alias case');
    const parsed = JSON.parse(stdout);
    assert.equal(
      parsed.hookSpecificOutput.permissionDecision,
      'deny',
      'holodeck alias must resolve correctly and trigger deny'
    );
    const reason = parsed.hookSpecificOutput.permissionDecisionReason;
    assert.ok(
      reason.includes('holodeck-em'),
      `reason must name the resolved em-id (holodeck-em), got: ${reason}`
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
  // Offer (routing mismatch): memo `to: holodeck-em` landing in central (~/.claude) → offer.
  // Signal (a): YAML frontmatter `to:` field present. Landing repo: .claude → claude-central-em.
  // to: holodeck-em ≠ claude-central-em → routing mismatch → offer.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — memo to: holodeck-em landing in central → offer', async () => {
    // Write a YAML-frontmatter memo addressed to holodeck-em into ~/.claude (central).
    // This simulates the live failure: addon-EM hand-writes a memo into central instead
    // of using the CLI to deliver to holodeck's inbox.
    const filePath = path.join(CLAUDE_ROOT, 'cross-repo', '2026-05-23-addon-to-holodeck.md');
    const content = [
      '---',
      'title: "Addon update"',
      'from: claude-central-em',
      'to: holodeck-em',
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
      ctx.includes('holodeck-em'),
      `offer must name the resolved recipient (holodeck-em), got: ${ctx}`
    );
  });

  // -------------------------------------------------------------------------
  // Offer (hand-rolled path): state/memos/ with capitalized To:/From: headers → offer.
  // Signal (b): hasFreeFormMemoHeader() + memo-shaped path. Existing /memos/ path trigger
  // already confirmed by earlier test; this confirms it still fires in G's branch.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — state/memos/ with hand-rolled To:/From: headers → offer', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'state', 'memos', '2026-05-23-holodeck-reply.md');
    const content = [
      'To: claude-central-em',
      'From: holodeck-em',
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
  // Silent (central as recipient): to: claude-central-em landing in ~/.claude → SILENT.
  // Central is a valid explicit receiver (B2 fix). The routing check must recognize
  // ~/.claude (.claude basename) as central and stay silent when to: == central.
  // -------------------------------------------------------------------------
  test('Routing-mismatch (Chunk G) — to: claude-central-em landing in central → SILENT', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'cross-repo', '2026-05-23-holodeck-to-central.md');
    const content = [
      '---',
      'title: "Request for central"',
      'from: holodeck-em',
      'to: claude-central-em',
      'created: 2026-05-23',
      'status: open',
      'delivery_mode: receiver-repo',
      '---',
      '',
      'Please seed the new doctrine.',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT));
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', 'to: claude-central-em landing in central must be SILENT (routing match)');
  });

  // -------------------------------------------------------------------------
  // Silent (correct inbound edit): holodeck EM edits a memo addressed to holodeck
  // in holodeck's own inbox (status: open → actioned) → SILENT.
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
      'from: holodeck-em',
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
      'To: holodeck-em',
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
      'to: holodeck-em',
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

  // Note: CLI self-write exemption is not tested here because bin/cross-repo-memo
  // writes via Python open(path,"w") at bin/cross-repo-memo:444 (_write_file),
  // NOT the Claude Write tool. PreToolUse hooks fire on Claude Code tool invocations,
  // not on subprocess fs writes — the exemption is structural, not runtime-checkable.

  // -------------------------------------------------------------------------
  // AC-9 negative cases: non-memo Writes with a `to:` YAML field → SILENT.
  //
  // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk G
  // Review: F4 — isThisAMemo gate fires on any YAML `to:`, so we prove SILENCE on
  // non-memo-shaped paths even when `to:` is present in frontmatter.
  // -------------------------------------------------------------------------

  // AC-9(a): Write to docs/plans/test.md with YAML `to: holodeck-em` → SILENT.
  //
  // F4 fix applied (code-reviewer 2026-05-23): isThisAMemo gate now requires
  // isMemoShapedPath for BOTH signals (yamlToValue AND hasFreeForm). A docs/plans/
  // path with YAML `to:` is NOT memo-shaped, so the routing check does not fire.
  // This catches the false-positive class on non-memo files that happen to use the
  // `to:` key in their own frontmatter.
  test('AC-9(a) (Chunk G/F4) — docs/plans/ Write with YAML to: holodeck-em → SILENT routing-wise (path not memo-shaped)', async () => {
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
      'to: holodeck-em',
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
  // Cross-repo memo from holodeck-em (2026-05-28): plan frontmatter containing
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
      'author: holodeck-em',
      'status: draft  # canonical starting state',
      'target_surfaces:',
      '  - /foo/path  # surface A',
      '  - /bar/path  # surface B',
      '---',
      '# Plan body',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `well-formed plan with # comments must pass silently; got: ${stdout}`);
  });

  test('Regression — quoted "#" inside scalar is preserved (not treated as comment)', async () => {
    const filePath = path.join(CLAUDE_ROOT, 'docs', 'plans', 'test-quoted-hash.md');
    const content = [
      '---',
      'title: "this # is part of the title"',
      'created: 2026-05-28',
      'author: holodeck-em',
      'status: draft',
      '---',
      '# body',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `quoted # must not be stripped as a comment; got: ${stdout}`);
  });

  // Direct unit assertions for stripInlineComment edge cases.
  test('Unit — stripInlineComment edge cases', () => {
    const { _stripInlineComment: strip } = require('../../bin/lib/schema.js');
    assert.equal(strip(''), '', 'empty input');
    assert.equal(strip('#bare'), '', 'bare # at column 0 → empty');
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
      'author: holodeck-em',
      'status: "draft # intended"',
      '---',
      '# body',
    ].join('\n');

    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.ok(stdout.length > 0, 'quoted # in enum value must fail enum, not silently pass');
    const parsed = JSON.parse(stdout);
    assert.equal(parsed.hookSpecificOutput.permissionDecision, 'deny');
    assert.ok(
      /invalid enum value/.test(parsed.hookSpecificOutput.permissionDecisionReason),
      `should report enum failure; got: ${parsed.hookSpecificOutput.permissionDecisionReason}`
    );
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

    // Handoff schema has workstream as optional. The point of the test is that
    // pre-strip lets parseInlineList run (vs. parseScalar returning a string),
    // so the validator does not fire a "expected a list" violation.
    const { stdout, exitCode } = await runHook(writePayload(filePath, content, CLAUDE_ROOT), { strict: true });
    assert.equal(exitCode, 0, 'should exit 0');
    assert.equal(stdout, '', `inline list with trailing # must parse as a list; got: ${stdout}`);
  });

});
