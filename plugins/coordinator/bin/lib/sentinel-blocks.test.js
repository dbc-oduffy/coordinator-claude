'use strict';
/**
 * sentinel-blocks.test.js — node:test suite for sentinel-blocks.js
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W2
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { extractBlock, replaceBlock, insertOrReplaceBlock } = require('./sentinel-blocks.js');

const BEGIN = '<!-- BEGIN alpha -->';
const END = '<!-- END alpha -->';
const BEGIN2 = '<!-- BEGIN beta -->';
const END2 = '<!-- END beta -->';

// ---------------------------------------------------------------------------
// extractBlock
// ---------------------------------------------------------------------------

test('extractBlock: returns null when begin marker is absent', () => {
  const content = 'no markers here\n';
  assert.strictEqual(extractBlock(content, BEGIN, END), null);
});

test('extractBlock: returns null when end marker is absent', () => {
  const content = `before\n${BEGIN}\nsome content\n`;
  assert.strictEqual(extractBlock(content, BEGIN, END), null);
});

test('extractBlock: extracts block between markers', () => {
  const content = `before\n${BEGIN}\nfoo bar\nbaz\n${END}\nafter\n`;
  const result = extractBlock(content, BEGIN, END);
  assert.ok(result, 'should not be null');
  assert.strictEqual(result.block, 'foo bar\nbaz\n');
  assert.ok(result.before.includes('before'));
  assert.ok(result.before.includes(BEGIN));
  assert.ok(result.after.includes(END));
  assert.ok(result.after.includes('after'));
});

test('extractBlock: empty block', () => {
  const content = `${BEGIN}\n${END}\n`;
  const result = extractBlock(content, BEGIN, END);
  assert.ok(result);
  assert.strictEqual(result.block, '');
});

// ---------------------------------------------------------------------------
// replaceBlock
// ---------------------------------------------------------------------------

test('replaceBlock: returns null when markers are missing', () => {
  assert.strictEqual(replaceBlock('no markers', BEGIN, END, 'new content'), null);
});

test('replaceBlock: replaces block content, preserves markers', () => {
  const content = `header\n${BEGIN}\nold content\n${END}\nfooter\n`;
  const updated = replaceBlock(content, BEGIN, END, 'new content\n');
  assert.ok(updated.includes(BEGIN));
  assert.ok(updated.includes(END));
  assert.ok(updated.includes('new content'));
  assert.ok(!updated.includes('old content'));
  assert.ok(updated.includes('header'));
  assert.ok(updated.includes('footer'));
});

test('replaceBlock: preserves before and after content unchanged', () => {
  const before = 'line1\nline2\n';
  const after = 'line3\nline4\n';
  const content = before + BEGIN + '\nold\n' + END + '\n' + after;
  const updated = replaceBlock(content, BEGIN, END, 'replaced\n');
  assert.ok(updated.startsWith(before));
  assert.ok(updated.includes(after));
});

test('replaceBlock: adds trailing newline to newBlockContent if missing', () => {
  const content = `${BEGIN}\nold\n${END}\n`;
  const updated = replaceBlock(content, BEGIN, END, 'no-newline');
  // end marker should be on its own line
  const lines = updated.split('\n');
  const endIdx = lines.findIndex(l => l.includes(END));
  assert.ok(endIdx > 0);
  // The line before end marker should be the new content
  assert.strictEqual(lines[endIdx - 1], 'no-newline');
});

// ---------------------------------------------------------------------------
// Round-trip
// ---------------------------------------------------------------------------

test('round-trip: insert, extract, replace, extract again — content equal', () => {
  const base = 'preamble\n';
  // Insert block
  const withBlock = insertOrReplaceBlock(base, BEGIN, END, 'v1 content\n');
  assert.ok(withBlock.includes(BEGIN));
  assert.ok(withBlock.includes(END));

  // Extract
  const ex1 = extractBlock(withBlock, BEGIN, END);
  assert.strictEqual(ex1.block, 'v1 content\n');

  // Replace
  const replaced = replaceBlock(withBlock, BEGIN, END, 'v2 content\n');
  assert.ok(replaced.includes('v2 content'));
  assert.ok(!replaced.includes('v1 content'));

  // Extract again
  const ex2 = extractBlock(replaced, BEGIN, END);
  assert.strictEqual(ex2.block, 'v2 content\n');
});

// ---------------------------------------------------------------------------
// insertOrReplaceBlock
// ---------------------------------------------------------------------------

test('insertOrReplaceBlock: inserts at end when markers missing', () => {
  const content = 'existing content\n';
  const result = insertOrReplaceBlock(content, BEGIN, END, 'new block\n');
  assert.ok(result.startsWith('existing content\n'));
  assert.ok(result.includes(BEGIN));
  assert.ok(result.includes('new block'));
  assert.ok(result.includes(END));
});

test('insertOrReplaceBlock: inserts at start when insertAt=start', () => {
  const content = 'existing content\n';
  const result = insertOrReplaceBlock(content, BEGIN, END, 'new block\n', 'start');
  assert.ok(result.startsWith(BEGIN));
  assert.ok(result.includes('existing content'));
});

test('insertOrReplaceBlock: replaces when markers already exist', () => {
  const content = `before\n${BEGIN}\nold\n${END}\nafter\n`;
  const result = insertOrReplaceBlock(content, BEGIN, END, 'new\n');
  assert.ok(result.includes('new'));
  assert.ok(!result.includes('old'));
  assert.ok(result.includes('before'));
  assert.ok(result.includes('after'));
});

// ---------------------------------------------------------------------------
// Multiple independent blocks in one file
// ---------------------------------------------------------------------------

test('multiple blocks: alpha and beta are independently addressable', () => {
  const content =
    `header\n` +
    `${BEGIN}\nalpha content\n${END}\n` +
    `middle\n` +
    `${BEGIN2}\nbeta content\n${END2}\n` +
    `footer\n`;

  const alpha = extractBlock(content, BEGIN, END);
  const beta = extractBlock(content, BEGIN2, END2);

  assert.strictEqual(alpha.block, 'alpha content\n');
  assert.strictEqual(beta.block, 'beta content\n');
});

test('multiple blocks: replacing alpha does not touch beta', () => {
  const content =
    `${BEGIN}\nalpha\n${END}\n` +
    `${BEGIN2}\nbeta\n${END2}\n`;

  const updated = replaceBlock(content, BEGIN, END, 'new alpha\n');
  const beta = extractBlock(updated, BEGIN2, END2);
  assert.strictEqual(beta.block, 'beta\n');
  assert.ok(!updated.includes('\nalpha\n'));
  assert.ok(updated.includes('new alpha'));
});

// ---------------------------------------------------------------------------
// Idempotency
// ---------------------------------------------------------------------------

test('replaceBlock is idempotent when new content equals existing content', () => {
  const content = `${BEGIN}\nsame content\n${END}\n`;
  const once = replaceBlock(content, BEGIN, END, 'same content\n');
  const twice = replaceBlock(once, BEGIN, END, 'same content\n');
  assert.strictEqual(once, twice);
});
