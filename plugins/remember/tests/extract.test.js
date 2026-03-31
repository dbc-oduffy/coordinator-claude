// tests/extract.test.js — Unit tests for lib/extract.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { writeFileSync, unlinkSync, existsSync } from 'fs';
import { tmpdir } from 'os';

import { extractMessages, countLines } from '../lib/extract.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(__dirname, 'fixtures', 'sample-session.jsonl');

// ---------------------------------------------------------------------------
// countLines()
// ---------------------------------------------------------------------------

test('countLines — returns correct count for fixture file', async () => {
  const count = await countLines(FIXTURE);
  // Fixture has 17 lines, each terminated with \n → 17 newlines
  assert.equal(count, 17);
});

test('countLines — returns 0 for empty file', async () => {
  const emptyPath = join(tmpdir(), `empty-test-${Date.now()}.jsonl`);
  writeFileSync(emptyPath, '');
  try {
    const count = await countLines(emptyPath);
    assert.equal(count, 0);
  } finally {
    if (existsSync(emptyPath)) unlinkSync(emptyPath);
  }
});

// ---------------------------------------------------------------------------
// extractMessages() — filtering
// ---------------------------------------------------------------------------

test('extractMessages — filters file-history-snapshot lines', async () => {
  const messages = await extractMessages(FIXTURE);
  // No message should contain "file-history-snapshot"
  for (const { text } of messages) {
    assert.ok(!text.includes('file-history-snapshot'), `unexpected file-history-snapshot in message: ${text}`);
  }
});

test('extractMessages — filters isMeta messages', async () => {
  // isMeta messages are tool_result lines — they should not appear as HUMAN or AGENT messages
  const messages = await extractMessages(FIXTURE);
  // All tool_result lines in the fixture have isMeta:true and array content (no plain text)
  // They should produce no HUMAN entries with tool_result content
  for (const { text } of messages) {
    assert.ok(!text.includes('tool_result'), `isMeta tool_result leaked into messages: ${text}`);
  }
});

test('extractMessages — filters system-reminder content', async () => {
  // Line 11 of the fixture is a user message whose string content contains <system-reminder>
  // It should be filtered out entirely (no HUMAN entry for it)
  const messages = await extractMessages(FIXTURE);
  for (const { text } of messages) {
    assert.ok(!text.includes('<system-reminder>'), `system-reminder leaked into messages: ${text}`);
    assert.ok(!text.includes('system-reminder'), `system-reminder text leaked: ${text}`);
  }
});

test('extractMessages — extracts user messages as HUMAN role', async () => {
  const messages = await extractMessages(FIXTURE);
  const humans = messages.filter(m => m.role === 'HUMAN');
  assert.ok(humans.length >= 1, 'should have at least one HUMAN message');
  // Check the first user message is present
  const firstHuman = humans[0];
  assert.ok(
    firstHuman.text.includes('Can you help me read a config file?'),
    `expected first HUMAN message about config file, got: ${firstHuman.text}`
  );
});

test('extractMessages — extracts assistant messages as AGENT role', async () => {
  const messages = await extractMessages(FIXTURE);
  const agents = messages.filter(m => m.role === 'AGENT');
  assert.ok(agents.length >= 1, 'should have at least one AGENT message');
});

test('extractMessages — formats Read tool_use blocks correctly', async () => {
  const messages = await extractMessages(FIXTURE);
  const withReadTool = messages.find(m => m.text.includes('[TOOL: Read'));
  assert.ok(withReadTool, 'should have an AGENT message with a Read tool call');
  assert.ok(
    withReadTool.text.includes('[TOOL: Read config.json]'),
    `expected [TOOL: Read config.json], got: ${withReadTool.text}`
  );
});

test('extractMessages — formats Bash tool_use blocks correctly', async () => {
  const messages = await extractMessages(FIXTURE);
  const withBashTool = messages.find(m => m.text.includes('[TOOL: Bash'));
  assert.ok(withBashTool, 'should have an AGENT message with a Bash tool call');
  assert.ok(
    withBashTool.text.includes('[TOOL: Bash `ls -la /home/user/project`]'),
    `expected Bash tool summary, got: ${withBashTool.text}`
  );
});

test('extractMessages — formats Grep tool_use blocks correctly', async () => {
  const messages = await extractMessages(FIXTURE);
  const withGrepTool = messages.find(m => m.text.includes('[TOOL: Grep'));
  assert.ok(withGrepTool, 'should have an AGENT message with a Grep tool call');
  assert.ok(
    withGrepTool.text.includes("[TOOL: Grep 'import.*from']"),
    `expected Grep tool summary, got: ${withGrepTool.text}`
  );
});

test('extractMessages — combined text+tool_use message includes both parts', async () => {
  const messages = await extractMessages(FIXTURE);
  // First assistant message has both text and a Read tool_use block
  const combined = messages.find(m =>
    m.role === 'AGENT' &&
    m.text.includes("Sure, I'll read the config file") &&
    m.text.includes('[TOOL: Read')
  );
  assert.ok(combined, 'should find AGENT message with both text and tool call');
});

test('extractMessages — total message count is correct', async () => {
  const messages = await extractMessages(FIXTURE);
  // 3 HUMAN + 7 AGENT = 10 total
  // Filtered out: file-history-snapshot, 2x system/isMeta, 3x tool_result isMeta,
  //               1x user with system-reminder content, 1x summary isMeta
  assert.equal(messages.length, 10, `expected 10 messages, got ${messages.length}`);
});

// ---------------------------------------------------------------------------
// extractMessages() — skipLines parameter
// ---------------------------------------------------------------------------

test('extractMessages — skipLines skips first N lines', async () => {
  // With skipLines=0, we get all 11 messages
  const allMessages = await extractMessages(FIXTURE, 0);

  // With skipLines=3, we skip the first 3 lines:
  // line 0: file-history-snapshot (would be filtered anyway)
  // line 1: isMeta system (would be filtered anyway)
  // line 2: first user message "Can you help me read a config file?" — this gets skipped
  const skipped3 = await extractMessages(FIXTURE, 3);

  // The first user message should be absent when skipping 3 lines
  const hasFirstUser = skipped3.some(m => m.text.includes('Can you help me read a config file?'));
  assert.ok(!hasFirstUser, 'first user message should be skipped with skipLines=3');

  // Should have fewer messages than the full set
  assert.ok(skipped3.length < allMessages.length, 'skipLines=3 should yield fewer messages than skipLines=0');
});

test('extractMessages — skipLines=0 is same as no skipLines', async () => {
  const withZero = await extractMessages(FIXTURE, 0);
  const withDefault = await extractMessages(FIXTURE);
  assert.deepEqual(withZero, withDefault);
});

// ---------------------------------------------------------------------------
// extractMessages() — empty file
// ---------------------------------------------------------------------------

test('extractMessages — returns empty array for empty file', async () => {
  const emptyPath = join(tmpdir(), `empty-extract-test-${Date.now()}.jsonl`);
  writeFileSync(emptyPath, '');
  try {
    const messages = await extractMessages(emptyPath);
    assert.deepEqual(messages, []);
  } finally {
    if (existsSync(emptyPath)) unlinkSync(emptyPath);
  }
});

test('extractMessages — returns empty array for file with only metadata lines', async () => {
  const metaOnlyPath = join(tmpdir(), `meta-only-test-${Date.now()}.jsonl`);
  const metaContent = [
    JSON.stringify({ type: 'file-history-snapshot', files: {} }),
    JSON.stringify({ type: 'system', content: 'init', isMeta: true }),
    JSON.stringify({ type: 'summary', summary: 'text', isMeta: true })
  ].join('\n') + '\n';
  writeFileSync(metaOnlyPath, metaContent);
  try {
    const messages = await extractMessages(metaOnlyPath);
    assert.deepEqual(messages, []);
  } finally {
    if (existsSync(metaOnlyPath)) unlinkSync(metaOnlyPath);
  }
});
