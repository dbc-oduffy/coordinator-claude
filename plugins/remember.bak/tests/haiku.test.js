// tests/haiku.test.js — Unit tests for lib/haiku.js (parseResponse only)
// callHaiku() requires the claude CLI — covered by manual smoke test.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { parseResponse } from '../lib/haiku.js';

// ---------------------------------------------------------------------------
// parseResponse() — basic parsing
// ---------------------------------------------------------------------------

test('parseResponse — parses valid JSON with result field', () => {
  const raw = JSON.stringify({
    result: 'Here is a summary of the session.',
    usage: { input_tokens: 1000, output_tokens: 200, cache_read_input_tokens: 0 },
    total_cost_usd: 0.001
  });
  const result = parseResponse(raw);
  assert.equal(result.text, 'Here is a summary of the session.');
  assert.equal(result.isSkip, false);
});

test('parseResponse — trims whitespace from result', () => {
  const raw = JSON.stringify({
    result: '  \n  Summary text here.  \n  ',
    usage: { input_tokens: 100, output_tokens: 50 },
    total_cost_usd: 0.0001
  });
  const result = parseResponse(raw);
  assert.equal(result.text, 'Summary text here.');
});

// ---------------------------------------------------------------------------
// parseResponse() — SKIP detection
// ---------------------------------------------------------------------------

test('parseResponse — detects SKIP prefix (uppercase)', () => {
  const raw = JSON.stringify({
    result: 'SKIP - not enough content to summarize',
    usage: { input_tokens: 500, output_tokens: 10 },
    total_cost_usd: 0.0005
  });
  const result = parseResponse(raw);
  assert.equal(result.isSkip, true);
});

test('parseResponse — detects SKIP prefix (mixed case)', () => {
  const raw = JSON.stringify({
    result: 'Skip: session too short',
    usage: { input_tokens: 500, output_tokens: 10 },
    total_cost_usd: 0.0005
  });
  const result = parseResponse(raw);
  assert.equal(result.isSkip, true, 'SKIP detection should be case-insensitive on first word');
});

test('parseResponse — non-SKIP text returns isSkip false', () => {
  const raw = JSON.stringify({
    result: 'This session covered reading a config file and running bash commands.',
    usage: { input_tokens: 800, output_tokens: 150 },
    total_cost_usd: 0.001
  });
  const result = parseResponse(raw);
  assert.equal(result.isSkip, false);
});

test('parseResponse — text containing SKIP not at start returns isSkip false', () => {
  const raw = JSON.stringify({
    result: 'The user asked to skip the validation step.',
    usage: { input_tokens: 800, output_tokens: 100 },
    total_cost_usd: 0.001
  });
  const result = parseResponse(raw);
  assert.equal(result.isSkip, false, 'SKIP in middle of text should not trigger isSkip');
});

// ---------------------------------------------------------------------------
// parseResponse() — token extraction
// ---------------------------------------------------------------------------

test('parseResponse — extracts input and output tokens from usage field', () => {
  const raw = JSON.stringify({
    result: 'Summary',
    usage: { input_tokens: 1500, output_tokens: 300 },
    total_cost_usd: 0.002
  });
  const result = parseResponse(raw);
  assert.equal(result.tokens.input, 1500);
  assert.equal(result.tokens.output, 300);
});

test('parseResponse — extracts cache_read_input_tokens', () => {
  const raw = JSON.stringify({
    result: 'Summary',
    usage: { input_tokens: 2000, output_tokens: 100, cache_read_input_tokens: 800 },
    total_cost_usd: 0.001
  });
  const result = parseResponse(raw);
  assert.equal(result.tokens.cache, 800);
});

test('parseResponse — falls back to cache_creation_input_tokens when cache_read absent', () => {
  const raw = JSON.stringify({
    result: 'Summary',
    usage: { input_tokens: 2000, output_tokens: 100, cache_creation_input_tokens: 500 },
    total_cost_usd: 0.001
  });
  const result = parseResponse(raw);
  assert.equal(result.tokens.cache, 500);
});

// ---------------------------------------------------------------------------
// parseResponse() — cost calculation
// ---------------------------------------------------------------------------

test('parseResponse — uses total_cost_usd when present (non-zero)', () => {
  const raw = JSON.stringify({
    result: 'Summary',
    usage: { input_tokens: 10000, output_tokens: 500 },
    total_cost_usd: 0.0123
  });
  const result = parseResponse(raw);
  assert.equal(result.tokens.costUsd, 0.0123);
});

test('parseResponse — uses total_cost_usd when value is 0 (does NOT fall back to calculation)', () => {
  // This is the critical regression test: 0 is a valid cost value.
  // The old || operator would have treated 0 as falsy and triggered the fallback.
  // The fixed != null check preserves the 0.
  const raw = JSON.stringify({
    result: 'SKIP',
    usage: { input_tokens: 100, output_tokens: 5 },
    total_cost_usd: 0
  });
  const result = parseResponse(raw);
  assert.equal(result.tokens.costUsd, 0, 'total_cost_usd: 0 should be used as-is, not trigger fallback');
});

test('parseResponse — calculates cost when total_cost_usd is absent', () => {
  // Haiku pricing: input $0.80/M, output $4.00/M, cache $0.08/M (as of 2026-03)
  const raw = JSON.stringify({
    result: 'Summary',
    usage: { input_tokens: 1000000, output_tokens: 1000000, cache_read_input_tokens: 0 }
    // no total_cost_usd field
  });
  const result = parseResponse(raw);
  // Expected: (1M - 0) * 0.80/M + 1M * 4.00/M + 0 * 0.08/M = 0.80 + 4.00 = 4.80
  assert.ok(result.tokens.costUsd > 0, 'calculated cost should be greater than 0');
  assert.ok(
    Math.abs(result.tokens.costUsd - 4.80) < 0.001,
    `expected calculated cost ~4.80, got ${result.tokens.costUsd}`
  );
});

test('parseResponse — calculates cost accounting for cache tokens (lower rate)', () => {
  // 500k cache tokens, 500k non-cache input, 100k output
  // Cost = (500k * 0.80/M) + (100k * 4.00/M) + (500k * 0.08/M)
  //      = 0.40 + 0.40 + 0.04 = 0.84
  const raw = JSON.stringify({
    result: 'Summary',
    usage: { input_tokens: 1000000, output_tokens: 100000, cache_read_input_tokens: 500000 }
  });
  const result = parseResponse(raw);
  const expected = (500000 * 0.80 / 1_000_000) + (100000 * 4.00 / 1_000_000) + (500000 * 0.08 / 1_000_000);
  assert.ok(
    Math.abs(result.tokens.costUsd - expected) < 0.0001,
    `expected ${expected}, got ${result.tokens.costUsd}`
  );
});

// ---------------------------------------------------------------------------
// parseResponse() — missing usage field
// ---------------------------------------------------------------------------

test('parseResponse — handles missing usage field gracefully (no crash)', () => {
  const raw = JSON.stringify({
    result: 'Summary without usage data',
    total_cost_usd: 0.001
  });
  // Should not throw
  let result;
  assert.doesNotThrow(() => {
    result = parseResponse(raw);
  });
  assert.equal(result.text, 'Summary without usage data');
  assert.equal(result.tokens.input, 0);
  assert.equal(result.tokens.output, 0);
  assert.equal(result.tokens.cache, 0);
});

test('parseResponse — handles completely empty usage object gracefully', () => {
  const raw = JSON.stringify({
    result: 'Summary',
    usage: {},
    total_cost_usd: 0.001
  });
  let result;
  assert.doesNotThrow(() => {
    result = parseResponse(raw);
  });
  assert.equal(result.tokens.input, 0);
  assert.equal(result.tokens.output, 0);
  assert.equal(result.tokens.cache, 0);
});

test('parseResponse — handles empty result field', () => {
  const raw = JSON.stringify({
    result: '',
    usage: { input_tokens: 10, output_tokens: 5 },
    total_cost_usd: 0
  });
  const result = parseResponse(raw);
  assert.equal(result.text, '');
  assert.equal(result.isSkip, false);
});
