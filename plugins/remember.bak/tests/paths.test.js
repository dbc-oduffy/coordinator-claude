// tests/paths.test.js — Unit tests for lib/paths.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolve } from 'path';
import { existsSync, readFileSync, unlinkSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

import { projectSlug, safeWriteFile, nowSec } from '../lib/paths.js';

// ---------------------------------------------------------------------------
// projectSlug()
// ---------------------------------------------------------------------------

test('projectSlug — Windows absolute path', () => {
  // On Windows, resolve('C:\\Users\\oduffy\\.claude') stays the same.
  // Drive letter C, colons and backslashes → dashes.
  // Expected: 'C--Users-oduffy--claude'
  const input = 'C:\\Users\\oduffy\\.claude';
  const slug = projectSlug(input);
  // All non-alphanumeric, non-dash chars must be replaced by '-'
  assert.match(slug, /^[a-zA-Z0-9-]+$/);
  // The resolved path should contain 'Users' somewhere in the slug
  assert.ok(slug.includes('Users'), `slug should contain 'Users': got ${slug}`);
  assert.ok(slug.includes('oduffy'), `slug should contain 'oduffy': got ${slug}`);
  assert.ok(slug.includes('claude'), `slug should contain 'claude': got ${slug}`);
});

test('projectSlug — path with special chars: dots and spaces become dashes', () => {
  // Dots and spaces are replaced with dashes
  // We test the replacement rule independently of resolve() platform behavior.
  // Pass an already-resolved absolute path on the current platform.
  const onWindows = process.platform === 'win32';
  const input = onWindows ? 'C:\\path\\with spaces\\and.dots' : '/path/with spaces/and.dots';
  const slug = projectSlug(input);
  assert.match(slug, /^[a-zA-Z0-9-]+$/, `slug should only contain alphanumeric and dashes: got ${slug}`);
  assert.ok(!slug.includes(' '), 'spaces should be replaced');
  assert.ok(!slug.includes('.'), 'dots should be replaced');
});

test('projectSlug — output contains only alphanumeric and dashes', () => {
  // Any path fed through projectSlug must produce a clean slug
  const paths = [
    'C:\\Users\\oduffy\\.claude',
    '/home/user/project',
    '/path/with spaces/and.dots',
    'C:\\My Projects\\hello world'
  ];
  for (const p of paths) {
    const slug = projectSlug(p);
    assert.match(slug, /^[a-zA-Z0-9-]+$/, `projectSlug('${p}') produced invalid chars: ${slug}`);
  }
});

test('projectSlug — deterministic: same input gives same output', () => {
  const input = 'C:\\Users\\oduffy\\.claude';
  assert.equal(projectSlug(input), projectSlug(input));
});

// ---------------------------------------------------------------------------
// safeWriteFile()
// ---------------------------------------------------------------------------

test('safeWriteFile — first write (file does not exist) succeeds', () => {
  const filePath = join(tmpdir(), `safe-write-test-${Date.now()}-new.txt`);
  // Ensure file does not exist
  if (existsSync(filePath)) unlinkSync(filePath);

  try {
    safeWriteFile(filePath, 'hello world');
    assert.ok(existsSync(filePath), 'file should exist after write');
    assert.equal(readFileSync(filePath, 'utf8'), 'hello world');
  } finally {
    if (existsSync(filePath)) unlinkSync(filePath);
    const tmp = filePath + '.tmp';
    if (existsSync(tmp)) unlinkSync(tmp);
  }
});

test('safeWriteFile — second write (file exists) overwrites without error', () => {
  const filePath = join(tmpdir(), `safe-write-test-${Date.now()}-overwrite.txt`);

  try {
    // First write
    safeWriteFile(filePath, 'original content');
    assert.equal(readFileSync(filePath, 'utf8'), 'original content');

    // Second write — this is the Windows EPERM test (can't rename onto existing)
    safeWriteFile(filePath, 'updated content');
    assert.equal(readFileSync(filePath, 'utf8'), 'updated content');
  } finally {
    if (existsSync(filePath)) unlinkSync(filePath);
    const tmp = filePath + '.tmp';
    if (existsSync(tmp)) unlinkSync(tmp);
  }
});

test('safeWriteFile — creates parent directories if they do not exist', () => {
  const dir = join(tmpdir(), `safe-write-test-${Date.now()}`, 'nested', 'dir');
  const filePath = join(dir, 'file.txt');

  try {
    safeWriteFile(filePath, 'nested content');
    assert.ok(existsSync(filePath), 'file should exist in nested directory');
    assert.equal(readFileSync(filePath, 'utf8'), 'nested content');
  } finally {
    if (existsSync(filePath)) unlinkSync(filePath);
  }
});

// ---------------------------------------------------------------------------
// nowSec()
// ---------------------------------------------------------------------------

test('nowSec — returns a number', () => {
  const result = nowSec();
  assert.equal(typeof result, 'number');
});

test('nowSec — value is within 1 second of Math.floor(Date.now() / 1000)', () => {
  const expected = Math.floor(Date.now() / 1000);
  const result = nowSec();
  assert.ok(
    Math.abs(result - expected) <= 1,
    `nowSec() returned ${result}, expected ~${expected}`
  );
});

test('nowSec — returns an integer (floor, not truncated float)', () => {
  const result = nowSec();
  assert.equal(result, Math.floor(result), 'nowSec() should return an integer value');
});
