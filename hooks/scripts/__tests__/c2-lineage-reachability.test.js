'use strict';
/**
 * __tests__/c2-lineage-reachability.test.js — C2 write-time lineage-reachability
 * hard-reject regression net for the PreToolUse frontmatter validator hook.
 *
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2
 *
 * Covers AC2/AC via the shared negative-fixture corpus at
 * coordinator/bin/tests/fixtures/validator-negative/c2-*.md, indexed by
 * c2-expected-reachability.json (distinct oracle from expected-rejections.json,
 * which is schema.js's filesystem/git-free shape/cross-field oracle — see that
 * file's C2 note for why these fixtures are NOT folded into it).
 *
 * Enforcement posture (deny-always, PM-ratified 2026-07-08): the reachability
 * reject fires as permissionDecision:'deny' even WITHOUT COORDINATOR_SCHEMA_STRICT.
 * This test asserts the deny fires in both strict and non-strict mode for the
 * negative fixtures, and stays silent/accept in both modes for the positive
 * carve-out + archive-relocation fixtures.
 *
 * Convention: same node:test / spawn pattern as the sibling hook test file.
 */

const { describe, test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const HOOK_SCRIPT = path.join(__dirname, '..', 'validate-frontmatter-schema.js');
const REPO_ROOT = path.resolve(__dirname, '../../../..');
// hooks/scripts/__tests__ is 4 levels below the DoE-claude repo root:
//   <repo>/coordinator/hooks/scripts/__tests__

const FIXTURES_DIR = path.join(REPO_ROOT, 'coordinator', 'bin', 'tests', 'fixtures', 'validator-negative');
const ORACLE_PATH = path.join(FIXTURES_DIR, 'c2-expected-reachability.json');

/**
 * Spawn the hook with the given payload (object → JSON piped to stdin).
 * Returns { stdout, stderr, exitCode }.
 */
function runHook(payload, opts = {}) {
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    if (opts.strict) env.COORDINATOR_SCHEMA_STRICT = '1';
    else delete env.COORDINATOR_SCHEMA_STRICT;
    const child = spawn(process.execPath, [HOOK_SCRIPT], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
      cwd: REPO_ROOT,
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
 * Build a minimal Write payload landing at a real state/handoffs/ path.
 *
 * The target is pre-created on disk with placeholder content (mirroring the
 * sibling C0a test file's pre-create convention) so the C0a new-file scaffold
 * offer (Write + !existsSync) does not fire and interfere with this test's
 * reachability assertions — the scaffold offer is an orthogonal concern.
 * The pre-created file is removed after the assertion (see afterEach-style
 * cleanup at each call site).
 */
function writePayload(repoRelTarget, content) {
  const absTarget = path.join(REPO_ROOT, repoRelTarget);
  fs.mkdirSync(path.dirname(absTarget), { recursive: true });
  fs.writeFileSync(absTarget, 'placeholder\n', 'utf8');
  return {
    tool_name: 'Write',
    tool_input: { file_path: absTarget, content },
    session_id: 'c2-reachability-test',
    cwd: REPO_ROOT,
  };
}

/** Remove a pre-created fixture target path (best-effort). */
function cleanupTarget(repoRelTarget) {
  try { fs.unlinkSync(path.join(REPO_ROOT, repoRelTarget)); } catch { /* already gone */ }
}

function isDeny(result) {
  if (result.exitCode !== 0) return false;
  let parsed;
  try { parsed = JSON.parse(result.stdout); } catch { return false; }
  return parsed &&
    parsed.hookSpecificOutput &&
    parsed.hookSpecificOutput.permissionDecision === 'deny';
}

const oracle = JSON.parse(fs.readFileSync(ORACLE_PATH, 'utf8'));

describe('C2 lineage reachability — write-time hard-reject (deny-always posture)', () => {
  for (const entry of oracle.fixtures) {
    const fixturePath = path.join(FIXTURES_DIR, entry.fixture);
    const content = fs.readFileSync(fixturePath, 'utf8');

    test(`${entry.fixture} (${entry.field}) — ${entry.expect_reject ? 'DENY' : 'PASS'} — non-strict (deny-always)`, async () => {
      const target = 'state/handoffs/2026-07-08_120000_c2-reachability-fixture.md';
      const payload = writePayload(target, content);
      try {
        const result = await runHook(payload, { strict: false });
        const denied = isDeny(result);
        assert.equal(
          denied,
          entry.expect_reject,
          `${entry.fixture}: expected deny=${entry.expect_reject}, got deny=${denied}. ` +
          `stdout=${result.stdout} stderr=${result.stderr}`
        );
      } finally {
        cleanupTarget(target);
      }
    });

    test(`${entry.fixture} (${entry.field}) — ${entry.expect_reject ? 'DENY' : 'PASS'} — strict mode`, async () => {
      const target = 'state/handoffs/2026-07-08_120000_c2-reachability-fixture.md';
      const payload = writePayload(target, content);
      try {
        const result = await runHook(payload, { strict: true });
        const denied = isDeny(result);
        assert.equal(
          denied,
          entry.expect_reject,
          `${entry.fixture} (strict): expected deny=${entry.expect_reject}, got deny=${denied}. ` +
          `stdout=${result.stdout} stderr=${result.stderr}`
        );
      } finally {
        cleanupTarget(target);
      }
    });
  }
});

describe('C2 lineage reachability — git-history tier (disk-absent, git-reachable target must NOT reject)', () => {
  test('predecessor resolving only via git history (relocated/deleted-on-disk) passes', async () => {
    // Use a real git-tracked handoff path in this repo's history that is
    // disk-absent NOW but git-reachable — pick the oldest commit that touched
    // any archive/handoffs/ file and re-derive a path guaranteed absent from
    // both the live worktree and the on-disk archive tree, but present in
    // git history via `git log --all -- <path>`.
    //
    // We synthesize this deterministically: create a throwaway file under
    // archive/handoffs/, commit it in a detached scratch, remove it from the
    // worktree, and confirm the hook's git-history tier resolves it. To keep
    // this test hermetic (no writes to the real repo state), we instead prove
    // the tier via the resolver's own git-history primitive directly: any
    // target path removed from disk but present via `git log --all -- <path>`
    // must resolve. We use a known git-removed historical handoff path if one
    // exists; otherwise this test is a structural no-op documenting the
    // requirement (git history in a shallow/fresh clone can vary).
    const { execFileSync } = require('node:child_process');
    let candidate = null;
    try {
      const out = execFileSync('git', [
        'log', '--all', '--diff-filter=D', '--name-only', '--pretty=format:',
        '--', 'archive/handoffs/', 'state/handoffs/',
      ], { cwd: REPO_ROOT, encoding: 'utf8' });
      const lines = out.split('\n').map(l => l.trim()).filter(Boolean);
      // Prefer a path not currently present on disk in either live or archive form.
      for (const l of lines) {
        const abs = path.join(REPO_ROOT, l);
        if (!fs.existsSync(abs)) { candidate = l; break; }
      }
    } catch {
      candidate = null;
    }

    if (!candidate) {
      // No deleted-and-gone handoff path found in THIS repo's history at test
      // time — the git-history tier is guaranteed hermetic coverage at the
      // unit level instead (walk-handoff-dag.test.js's "_resolveTarget
      // git-history tier — hermetic scratch git repo" describe block: a
      // throwaway scratch git repo, not this repo, so it never depends on
      // DoE-claude's actual history or clone depth). Skip here rather than
      // fail on an environment-dependent absence.
      // Review: code-reviewer F6 — this comment previously claimed
      // walk-handoff-dag.test.js already covered _resolveTarget's
      // git-history branch; that was false when written. It is now true.
      return;
    }

    const content = [
      '---',
      'title: C2 reachability — git-history-only predecessor',
      'created: 2026-07-08',
      'branch: test-branch',
      'status: active',
      'kind: session-handoff',
      'category: infra',
      'summary: C2 fixture — predecessor resolves only via git history (disk-absent).',
      `predecessor: ${candidate}`,
      '---',
      'Body text',
      '',
    ].join('\n');

    const target = 'state/handoffs/2026-07-08_120001_c2-git-history-fixture.md';
    const payload = writePayload(target, content);
    try {
      const result = await runHook(payload, { strict: true });
      assert.equal(
        isDeny(result),
        false,
        `git-history-resolvable predecessor (${candidate}) must NOT deny. stdout=${result.stdout} stderr=${result.stderr}`
      );
    } finally {
      cleanupTarget(target);
    }
  });
});
