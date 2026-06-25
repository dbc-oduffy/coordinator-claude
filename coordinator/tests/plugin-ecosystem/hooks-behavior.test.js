// hooks-behavior.test.js — Hook script behavior tests
//
// Spec backlink: plans/2026-04-29-claude-setup-borrows.md § Borrow #1 — Hook test suite
//
// SCOPE: Integration tests asserting load-bearing hook script behaviors under
// representative inputs. These complement hooks.test.js (which covers manifest
// config) — do not merge the two.
//
// What IS covered:
//   - coordinator-safe-commit: blanket bypass, COORDINATOR_OVERRIDE_SCOPE, scope-from
//   - verify-preamble-sync.sh: --check clean/dirty, --fix propagation, CRLF tolerance
//   - coordinator-auto-push: delegated to test-coordinator-auto-push.sh (PATH-shim fake-git)
//   - session-init.sh: smoke — exits 0, produces non-empty output, completes in < 10s
//   - Calibration sync assertion (informational; may fail before Borrow #5 lands)
//
// What is NOT covered:
//   - Live Claude session hook firing (requires running Claude Code instance)
//   - git push reaching a real remote (fake-git PATH shim intercepts all push calls)

'use strict';

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execSync, spawnSync } = require('child_process');
const {
  PLUGINS_ROOT,
  fileExists,
  mkTempRepo,
  cleanupTempRepo,
  mkPathShim,
} = require('./helpers/fs');

const COORDINATOR_DIR = path.join(PLUGINS_ROOT, 'coordinator-claude', 'coordinator');
const SAFE_COMMIT     = path.join(COORDINATOR_DIR, 'bin', 'coordinator-safe-commit');
const AUTO_PUSH       = path.join(COORDINATOR_DIR, 'bin', 'coordinator-auto-push');
const PREAMBLE_SYNC   = path.join(COORDINATOR_DIR, 'bin', 'verify-preamble-sync.sh');
const SESSION_INIT    = path.join(COORDINATOR_DIR, 'hooks', 'scripts', 'session-init.sh');
const SNIPPETS_DIR    = path.join(COORDINATOR_DIR, 'snippets');
const PREAMBLE_SNIP   = path.join(SNIPPETS_DIR, 'project-rag-preamble.md');
const CAL_SNIP        = path.join(SNIPPETS_DIR, 'reviewer-calibration.md');
const AUTO_PUSH_TEST  = path.join(
  COORDINATOR_DIR,
  'bin', 'tests', 'test-coordinator-auto-push.sh'
);

// Detect bash availability once
let bashAvailable = false;
try {
  execSync('bash --version', { stdio: 'pipe', timeout: 5000 });
  bashAvailable = true;
} catch { /* bash not available */ }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Run a script under bash in a given cwd and return { status, stdout, stderr }.
 * Never throws — status is null on spawn failure.
 */
function runBash(script, args, opts = {}) {
  const result = spawnSync('bash', [script, ...args], {
    encoding: 'utf-8',
    timeout: opts.timeout || 15000,
    env: { ...process.env, ...(opts.env || {}) },
    cwd: opts.cwd || process.cwd(),
  });
  return {
    status: result.status,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
  };
}

/**
 * Create a minimal coordinator session directory so coordinator-safe-commit
 * can resolve a session.
 */
function makeSession(repoPath, sessionId, touchedFiles = []) {
  const sessionDir = path.join(repoPath, '.git', 'coordinator-sessions', sessionId);
  fs.mkdirSync(sessionDir, { recursive: true });
  fs.writeFileSync(path.join(sessionDir, 'started_at'), new Date().toISOString());
  fs.writeFileSync(path.join(sessionDir, 'head_at_start'),
    execSync('git rev-parse HEAD', { cwd: repoPath }).toString().trim()
  );
  fs.writeFileSync(path.join(sessionDir, 'touched.txt'), touchedFiles.join('\n') + (touchedFiles.length ? '\n' : ''));
  fs.writeFileSync(path.join(sessionDir, 'meta.json'), JSON.stringify({
    session_id: sessionId,
    branch: 'main',
    pid: String(process.pid),
    last_activity: new Date().toISOString(),
    goal: 'test',
  }));
}

// ---------------------------------------------------------------------------
// coordinator-safe-commit behavior
// ---------------------------------------------------------------------------

describe('coordinator-safe-commit', () => {
  let repo;
  const SID = `test-sid-${process.pid}`;

  before(() => {
    if (!bashAvailable || !fileExists(SAFE_COMMIT)) return;
    repo = mkTempRepo();
    makeSession(repo, SID);
  });

  after(() => {
    cleanupTempRepo(repo);
    repo = null;
  });

  it('prerequisite: bash available and script exists', () => {
    assert.ok(bashAvailable, 'bash must be available to run hook-behavior tests');
    assert.ok(fileExists(SAFE_COMMIT), `coordinator-safe-commit not found: ${SAFE_COMMIT}`);
  });

  it('accepts explicit-path staging (exits 0)', () => {
    if (!bashAvailable || !repo) return;
    const scopedSid = `test-explicit-${process.pid}`;
    const subRepo = mkTempRepo();
    try {
      const filePath = path.join(subRepo, 'myfile.md');
      fs.writeFileSync(filePath, 'explicit path content');
      makeSession(subRepo, scopedSid, ['myfile.md']);

      const r = runBash(SAFE_COMMIT, ['test: explicit path'], {
        cwd: subRepo,
        // Set both env tiers to the scoped id: ...process.env spreads the runner's
        // real CLAUDE_CODE_SESSION_ID (resolver Priority 2), which must not leak in.
        env: { ...process.env, CLAUDE_SESSION_ID: scopedSid, CLAUDE_CODE_SESSION_ID: scopedSid, HOME: os.homedir() },
      });
      assert.equal(r.status, 0, `Expected exit 0, got ${r.status}. stderr: ${r.stderr}`);
      const log = execSync('git log -1 --name-only --pretty=format: -- myfile.md', {
        cwd: subRepo,
      }).toString().trim();
      assert.ok(log.includes('myfile.md'), 'expected myfile.md in last commit');
    } finally {
      cleanupTempRepo(subRepo);
    }
  });

  it('CLAUDE_INVOKING_COMMAND=workstream-start + --blanket stages everything (exit 0)', () => {
    // workstream-start is the ceremony token (session-start was removed — closed transition window)
    if (!bashAvailable) return;
    const subRepo = mkTempRepo();
    const bSid = `test-blanket-ws-${process.pid}`;
    try {
      const filePath = path.join(subRepo, 'ws-blanketfile.md');
      fs.writeFileSync(filePath, 'workstream-start blanket content');
      execSync('git add ws-blanketfile.md', { cwd: subRepo, stdio: 'pipe' });
      makeSession(subRepo, bSid);

      const r = runBash(SAFE_COMMIT, ['--blanket', 'test: workstream-start blanket'], {
        cwd: subRepo,
        env: {
          ...process.env,
          CLAUDE_SESSION_ID: bSid,
          CLAUDE_CODE_SESSION_ID: bSid,
          CLAUDE_INVOKING_COMMAND: 'workstream-start',
          HOME: os.homedir(),
        },
      });
      assert.equal(r.status, 0, `Expected exit 0 for blanket+workstream-start. stderr: ${r.stderr}`);
    } finally {
      cleanupTempRepo(subRepo);
    }
  });

  it('--blanket without CLAUDE_INVOKING_COMMAND is rejected (non-zero exit)', () => {
    if (!bashAvailable) return;
    const subRepo = mkTempRepo();
    const bSid = `test-blanket-reject-${process.pid}`;
    try {
      fs.writeFileSync(path.join(subRepo, 'file.md'), 'content');
      makeSession(subRepo, bSid);

      const r = runBash(SAFE_COMMIT, ['--blanket', 'test: rejected blanket'], {
        cwd: subRepo,
        env: { ...process.env, CLAUDE_SESSION_ID: bSid, CLAUDE_CODE_SESSION_ID: bSid, HOME: os.homedir() },
      });
      assert.notEqual(r.status, 0, 'Expected non-zero exit when blanket used without CLAUDE_INVOKING_COMMAND');
      assert.ok(
        r.stderr.includes('workstream-start') &&
          (r.stderr.includes('update-docs') || r.stderr.includes('distillation')),
        `Expected rejection message mentioning workstream-start and a still-valid peer token (update-docs/distillation). /workday-complete was intentionally removed from the allow-list 2026-06-22 (migrated to the path-classifier). stderr: ${r.stderr}`
      );
    } finally {
      cleanupTempRepo(subRepo);
    }
  });

  it('COORDINATOR_OVERRIDE_SCOPE=1 bypasses with stderr warning (exit 0)', () => {
    if (!bashAvailable) return;
    const subRepo = mkTempRepo();
    const oSid = `test-override-${process.pid}`;
    try {
      const f1 = path.join(subRepo, 'mine.md');
      const f2 = path.join(subRepo, 'extra.md');
      fs.writeFileSync(f1, 'mine');
      fs.writeFileSync(f2, 'extra');
      makeSession(subRepo, oSid, ['mine.md']);

      const r = runBash(SAFE_COMMIT, ['test: override'], {
        cwd: subRepo,
        env: {
          ...process.env,
          CLAUDE_SESSION_ID: oSid,
          CLAUDE_CODE_SESSION_ID: oSid,
          COORDINATOR_OVERRIDE_SCOPE: '1',
          HOME: os.homedir(),
        },
      });
      assert.equal(r.status, 0, `Expected exit 0 with COORDINATOR_OVERRIDE_SCOPE=1. stderr: ${r.stderr}`);
      assert.ok(
        r.stderr.includes('audit-trail-degraded') || r.stderr.includes('override') || r.stdout.includes('override'),
        `Expected override warning in output. stderr: ${r.stderr} stdout: ${r.stdout}`
      );
    } finally {
      cleanupTempRepo(subRepo);
    }
  });

  it('--scope-from reads handoff scope: frontmatter and stages matching path', () => {
    if (!bashAvailable) return;
    const subRepo = mkTempRepo();
    const sfSid = `test-scope-from-${process.pid}`;
    try {
      const scopedFile = path.join(subRepo, 'scoped-file.txt');
      const outOfScopeFile = path.join(subRepo, 'out-of-scope.txt');
      fs.writeFileSync(scopedFile, 'scoped content');
      fs.writeFileSync(outOfScopeFile, 'out of scope');

      const handoffDir = path.join(subRepo, 'state', 'handoffs');
      fs.mkdirSync(handoffDir, { recursive: true });
      const handoffPath = path.join(handoffDir, 'handoff.md');
      fs.writeFileSync(handoffPath, [
        '---',
        'workstream: test-scope',
        'scope:',
        '  - scoped-file.txt',
        '---',
        '# Handoff',
      ].join('\n'));

      makeSession(subRepo, sfSid);

      // Note: out-of-scope.txt and the handoff itself are dirty outside the declared
      // scope; the helper now fails-closed on those by default. Pass
      // --allow-out-of-scope-dirty to proceed (doctrine: "flagged loud, not silently dropped").
      const r = runBash(SAFE_COMMIT, [
        '--scope-from', 'state/handoffs/handoff.md',
        '--allow-out-of-scope-dirty',
        'test: scope-from',
      ], {
        cwd: subRepo,
        env: { ...process.env, CLAUDE_SESSION_ID: sfSid, CLAUDE_CODE_SESSION_ID: sfSid, HOME: os.homedir() },
      });
      assert.equal(r.status, 0, `Expected exit 0 for --scope-from. stderr: ${r.stderr}`);

      // Verify commit contains scoped file but not out-of-scope
      const committed = execSync('git show --name-only HEAD --format=""', { cwd: subRepo })
        .toString().replace(/^\n/, '');
      assert.ok(
        committed.includes('scoped-file.txt'),
        `Expected scoped-file.txt in commit. got: ${committed}`
      );
      assert.ok(
        !committed.includes('out-of-scope.txt'),
        `Expected out-of-scope.txt NOT in commit. got: ${committed}`
      );
    } finally {
      cleanupTempRepo(subRepo);
    }
  });
});

// ---------------------------------------------------------------------------
// verify-preamble-sync.sh behavior
// ---------------------------------------------------------------------------

describe('verify-preamble-sync.sh', () => {
  let bashTestSkip = false;
  const BEGIN_SENTINEL = '<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->';
  const END_SENTINEL   = '<!-- END project-rag-preamble -->';

  before(() => {
    if (!bashAvailable || !fileExists(PREAMBLE_SYNC) || !fileExists(PREAMBLE_SNIP)) {
      bashTestSkip = true;
    }
  });

  it('prerequisite: bash available, script and snippet both exist', () => {
    assert.ok(bashAvailable, 'bash must be available');
    assert.ok(fileExists(PREAMBLE_SYNC), `Script not found: ${PREAMBLE_SYNC}`);
    assert.ok(fileExists(PREAMBLE_SNIP), `Snippet not found: ${PREAMBLE_SNIP}`);
  });

  it('--check exits 0 on a synthetic clean tree (consumer preamble matches source)', () => {
    if (bashTestSkip) return;

    // Build a synthetic plugin tree with a clean consumer
    const tmpPlugin = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-preamble-test-'));
    try {
      // Replicate the expected directory structure under the fake plugin root
      const snipDir = path.join(tmpPlugin, 'snippets');
      const agentDir = path.join(tmpPlugin, 'coordinator', 'agents');
      fs.mkdirSync(snipDir, { recursive: true });
      fs.mkdirSync(agentDir, { recursive: true });

      // Copy the real snippet
      const snippetContent = fs.readFileSync(PREAMBLE_SNIP, 'utf-8');
      fs.writeFileSync(path.join(snipDir, 'project-rag-preamble.md'), snippetContent);

      // Build the snippet body (lines 3+, matching script's NR>2 logic)
      const snippetLines = snippetContent.split('\n');
      const snippetBody = snippetLines.slice(2).join('\n');

      // Create a consumer file with correct sentinel-bracketed content
      const consumerContent = [
        '# Agent Prompt',
        '',
        BEGIN_SENTINEL,
        snippetBody.replace(/\n$/, ''),
        END_SENTINEL,
        '',
        '## Domain section',
      ].join('\n');
      fs.writeFileSync(path.join(agentDir, 'test-consumer.md'), consumerContent);

      const r = spawnSync(
        'bash',
        [PREAMBLE_SYNC, '--check'],
        {
          encoding: 'utf-8',
          timeout: 10000,
          env: { ...process.env, CLAUDE_PLUGIN_ROOT: tmpPlugin },
        }
      );
      assert.equal(r.status, 0, `Expected exit 0 on clean tree. stdout: ${r.stdout} stderr: ${r.stderr}`);
      assert.ok(r.stdout.includes('OK'), `Expected "OK" in output. got: ${r.stdout}`);
    } finally {
      fs.rmSync(tmpPlugin, { recursive: true, force: true });
    }
  });

  it('--check exits non-zero when any consumer preamble differs', () => {
    if (bashTestSkip) return;

    const tmpPlugin = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-preamble-mismatch-'));
    try {
      const snipDir = path.join(tmpPlugin, 'snippets');
      const agentDir = path.join(tmpPlugin, 'coordinator', 'agents');
      fs.mkdirSync(snipDir, { recursive: true });
      fs.mkdirSync(agentDir, { recursive: true });

      const snippetContent = fs.readFileSync(PREAMBLE_SNIP, 'utf-8');
      fs.writeFileSync(path.join(snipDir, 'project-rag-preamble.md'), snippetContent);

      // Consumer has WRONG content between sentinels
      const consumerContent = [
        '# Agent Prompt',
        '',
        BEGIN_SENTINEL,
        'This content is intentionally different from the source snippet.',
        END_SENTINEL,
        '',
      ].join('\n');
      fs.writeFileSync(path.join(agentDir, 'test-consumer.md'), consumerContent);

      const r = spawnSync(
        'bash',
        [PREAMBLE_SYNC, '--check'],
        {
          encoding: 'utf-8',
          timeout: 10000,
          env: { ...process.env, CLAUDE_PLUGIN_ROOT: tmpPlugin },
        }
      );
      assert.notEqual(r.status, 0, `Expected non-zero exit on mismatch. stdout: ${r.stdout}`);
      assert.ok(
        r.stdout.includes('MISMATCH'),
        `Expected "MISMATCH" in output. got: ${r.stdout}`
      );
    } finally {
      fs.rmSync(tmpPlugin, { recursive: true, force: true });
    }
  });

  it('--fix propagates changed source to consumer; subsequent --check exits 0', () => {
    if (bashTestSkip) return;

    const tmpPlugin = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-preamble-fix-'));
    try {
      const snipDir = path.join(tmpPlugin, 'snippets');
      const agentDir = path.join(tmpPlugin, 'coordinator', 'agents');
      fs.mkdirSync(snipDir, { recursive: true });
      fs.mkdirSync(agentDir, { recursive: true });

      // Write a modified snippet (different from what the consumer has)
      const originalSnippet = fs.readFileSync(PREAMBLE_SNIP, 'utf-8');
      const modifiedSnippet = originalSnippet + '\n<!-- test-marker-unique -->\n';
      fs.writeFileSync(path.join(snipDir, 'project-rag-preamble.md'), modifiedSnippet);

      // Consumer has the original (stale) content
      const snippetLines = originalSnippet.split('\n');
      const originalBody = snippetLines.slice(2).join('\n');
      const consumerContent = [
        '# Agent Prompt',
        '',
        BEGIN_SENTINEL,
        originalBody.replace(/\n$/, ''),
        END_SENTINEL,
        '',
      ].join('\n');
      fs.writeFileSync(path.join(agentDir, 'test-consumer.md'), consumerContent);

      // --fix should propagate modified snippet
      const fixResult = spawnSync(
        'bash',
        [PREAMBLE_SYNC, '--fix'],
        {
          encoding: 'utf-8',
          timeout: 10000,
          env: { ...process.env, CLAUDE_PLUGIN_ROOT: tmpPlugin },
        }
      );
      assert.equal(fixResult.status, 0, `Expected --fix to exit 0. stdout: ${fixResult.stdout} stderr: ${fixResult.stderr}`);
      assert.ok(fixResult.stdout.includes('FIXED'), `Expected "FIXED" in output. got: ${fixResult.stdout}`);

      // --check should now exit 0
      const checkResult = spawnSync(
        'bash',
        [PREAMBLE_SYNC, '--check'],
        {
          encoding: 'utf-8',
          timeout: 10000,
          env: { ...process.env, CLAUDE_PLUGIN_ROOT: tmpPlugin },
        }
      );
      assert.equal(checkResult.status, 0, `Expected --check to pass after --fix. stdout: ${checkResult.stdout}`);
    } finally {
      fs.rmSync(tmpPlugin, { recursive: true, force: true });
    }
  });

  it('--check regex tolerates Windows CRLF line endings in consumer file', () => {
    // regression test for 2e6fb17 — Windows CRLF regex
    if (bashTestSkip) return;

    const tmpPlugin = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-preamble-crlf-'));
    try {
      const snipDir = path.join(tmpPlugin, 'snippets');
      const agentDir = path.join(tmpPlugin, 'coordinator', 'agents');
      fs.mkdirSync(snipDir, { recursive: true });
      fs.mkdirSync(agentDir, { recursive: true });

      const snippetContent = fs.readFileSync(PREAMBLE_SNIP, 'utf-8');
      fs.writeFileSync(path.join(snipDir, 'project-rag-preamble.md'), snippetContent);

      const snippetLines = snippetContent.split('\n');
      const snippetBody = snippetLines.slice(2).join('\n');

      // Write the consumer with CRLF line endings (Windows style)
      const consumerLines = [
        '# Agent Prompt',
        '',
        BEGIN_SENTINEL,
        ...snippetBody.replace(/\n$/, '').split('\n'),
        END_SENTINEL,
        '',
      ];
      // Join with CRLF
      const consumerCrlf = consumerLines.join('\r\n');
      const consumerPath = path.join(agentDir, 'test-consumer-crlf.md');
      fs.writeFileSync(consumerPath, consumerCrlf, 'utf-8');

      // Verify the file actually has CRLF bytes
      const raw = fs.readFileSync(consumerPath);
      const crCount = [...raw].filter((b, i) => b === 0x0d && raw[i + 1] === 0x0a).length;
      assert.ok(crCount >= 3, `Fixture should have CRLF endings; got ${crCount} CR bytes`);

      const r = spawnSync(
        'bash',
        [PREAMBLE_SYNC, '--check'],
        {
          encoding: 'utf-8',
          timeout: 10000,
          env: { ...process.env, CLAUDE_PLUGIN_ROOT: tmpPlugin },
        }
      );
      assert.equal(
        r.status, 0,
        `Expected --check to exit 0 for CRLF consumer. stdout: ${r.stdout} stderr: ${r.stderr}`
      );
    } finally {
      fs.rmSync(tmpPlugin, { recursive: true, force: true });
    }
  });
});

// ---------------------------------------------------------------------------
// coordinator-auto-push — delegated to bash test suite
// ---------------------------------------------------------------------------

describe('coordinator-auto-push (delegated to bash test suite)', () => {

  it('prerequisite: bash test suite exists and is runnable by bash', () => {
    assert.ok(bashAvailable, 'bash must be available');
    assert.ok(fileExists(AUTO_PUSH_TEST), `Bash test not found: ${AUTO_PUSH_TEST}`);
    // On Windows, fs.stat exec bits are always 0 — verify bash can at least parse the file
    const syntaxCheck = spawnSync('bash', ['-n', AUTO_PUSH_TEST], {
      encoding: 'utf-8',
      timeout: 5000,
    });
    assert.equal(
      syntaxCheck.status, 0,
      `Bash syntax check failed for ${AUTO_PUSH_TEST}: ${syntaxCheck.stderr}`
    );
  });

  it('bash test suite passes (T1–T5: branch routing, failure log, exit-0 guarantee)', () => {
    if (!bashAvailable || !fileExists(AUTO_PUSH_TEST)) return;

    const result = spawnSync('bash', [AUTO_PUSH_TEST], {
      encoding: 'utf-8',
      timeout: 30000,
      env: { ...process.env },
    });

    if (result.status !== 0) {
      // Surface meaningful output on failure
      const out = (result.stdout || '') + '\n' + (result.stderr || '');
      assert.fail(
        `coordinator-auto-push bash test suite failed (exit ${result.status}):\n${out.slice(0, 2000)}`
      );
    }
    assert.equal(result.status, 0, 'All auto-push bash tests must pass');
  });
});

// ---------------------------------------------------------------------------
// SessionStart hook chain — smoke
// ---------------------------------------------------------------------------

describe('session-init.sh — SessionStart smoke', () => {
  let repo;

  before(() => {
    if (!bashAvailable || !fileExists(SESSION_INIT)) return;
    repo = mkTempRepo();
  });

  after(() => {
    cleanupTempRepo(repo);
    repo = null;
  });

  it('prerequisite: bash available and session-init.sh exists', () => {
    assert.ok(bashAvailable, 'bash must be available');
    assert.ok(fileExists(SESSION_INIT), `session-init.sh not found: ${SESSION_INIT}`);
  });

  it('exits 0 when fed valid SessionStart JSON', () => {
    if (!bashAvailable || !repo) return;
    const input = JSON.stringify({ session_id: `smoke-${process.pid}`, source: 'startup' });
    const start = Date.now();

    const r = spawnSync('bash', [SESSION_INIT], {
      input,
      encoding: 'utf-8',
      timeout: 10000,
      cwd: repo,
    });

    const elapsed = Date.now() - start;
    assert.equal(r.status, 0, `Expected exit 0. stderr: ${r.stderr}`);
    assert.ok(elapsed < 10000, `Expected to complete in under 10s, took ${elapsed}ms`);
  });

  it('produces non-empty stdout or non-trivial side effect (session dir written)', () => {
    // AC4(b): stdout non-empty OR session dir created — session-init.sh writes files
    // to .git/coordinator-sessions/ and is allowed to have empty stdout
    if (!bashAvailable || !repo) return;
    const sessionId = `smoke-side-effect-${process.pid}`;
    const input = JSON.stringify({ session_id: sessionId, source: 'startup' });

    const r = spawnSync('bash', [SESSION_INIT], {
      input,
      encoding: 'utf-8',
      timeout: 10000,
      cwd: repo,
    });
    assert.equal(r.status, 0, r.stderr?.toString() || 'session-init.sh failed');

    // Side effect: .current-session-id sentinel should be written
    const sentinelPath = path.join(repo, '.git', 'coordinator-sessions', '.current-session-id');
    assert.ok(
      fileExists(sentinelPath),
      `Expected .current-session-id sentinel to be written at ${sentinelPath}`
    );
    const writtenId = fs.readFileSync(sentinelPath, 'utf-8').trim();
    assert.equal(writtenId, sessionId, 'Sentinel must contain the correct session ID');
  });

  it('stderr is empty or matches allowed-warnings pattern', () => {
    if (!bashAvailable || !repo) return;
    const input = JSON.stringify({ session_id: `smoke-stderr-${process.pid}`, source: 'startup' });

    const r = spawnSync('bash', [SESSION_INIT], {
      input,
      encoding: 'utf-8',
      timeout: 10000,
      cwd: repo,
    });

    // Allowed warnings: empty, or harmless shell warnings about missing optional tools
    const allowedWarnings = /^$|warning|deprecated|not found/i;
    const stderrTrimmed = (r.stderr || '').trim();
    assert.ok(
      allowedWarnings.test(stderrTrimmed),
      `Unexpected stderr output: ${stderrTrimmed}`
    );
  });

  it('completes in under 10 seconds', () => {
    if (!bashAvailable || !repo) return;
    const input = JSON.stringify({ session_id: `smoke-timing-${process.pid}`, source: 'startup' });

    const start = Date.now();
    const r = spawnSync('bash', [SESSION_INIT], {
      input,
      encoding: 'utf-8',
      timeout: 10500,
      cwd: repo,
    });
    const elapsed = Date.now() - start;

    assert.equal(r.status, 0, `Hook must exit 0. stderr: ${r.stderr}`);
    assert.ok(elapsed < 10000, `session-init.sh must complete in < 10s; took ${elapsed}ms`);
  });
});

// ---------------------------------------------------------------------------
// Calibration sync assertion — informational; expected to fail before Borrow #5 lands
// ---------------------------------------------------------------------------

describe('reviewer-calibration sentinel sync (informational — may fail before Borrow #5)', () => {
  const CAL_BEGIN = '<!-- BEGIN reviewer-calibration (synced from snippets/reviewer-calibration.md) -->';
  const CAL_END   = '<!-- END reviewer-calibration -->';

  // The 6 live consumer files per the plan inventory
  const LIVE_CONSUMERS = [
    path.join(PLUGINS_ROOT, 'coordinator-claude', 'coordinator', 'agents', 'staff-eng.md'),
    path.join(PLUGINS_ROOT, 'claude-unreal-holodeck', 'coordinator', 'agents', 'staff-eng.md'),
    path.join(PLUGINS_ROOT, 'coordinator-claude', 'game-dev', 'agents', 'staff-game-dev.md'),
    path.join(PLUGINS_ROOT, 'claude-unreal-holodeck', 'game-dev', 'agents', 'staff-game-dev.md'),
    path.join(PLUGINS_ROOT, 'coordinator-claude', 'web-dev', 'agents', 'senior-front-end.md'),
    path.join(PLUGINS_ROOT, 'coordinator-claude', 'data-science', 'agents', 'staff-data-sci.md'),
  ];

  /**
   * Extract the content between the reviewer-calibration sentinel comments.
   * Returns null if sentinels are absent (Borrow #5 not yet landed).
   */
  function extractCalibrationBlock(filePath) {
    if (!fileExists(filePath)) return null;
    const content = fs.readFileSync(filePath, 'utf-8');
    const beginIdx = content.indexOf(CAL_BEGIN);
    const endIdx = content.indexOf(CAL_END);
    if (beginIdx === -1 || endIdx === -1) return null;
    return content.slice(beginIdx + CAL_BEGIN.length, endIdx);
  }

  /**
   * Compute a simple SHA-256-equivalent hash using Node's built-in crypto.
   */
  function sha256(str) {
    const { createHash } = require('crypto');
    return createHash('sha256').update(str, 'utf-8').digest('hex');
  }

  it('all extant consumer files have identical reviewer-calibration sentinel blocks', () => {
    // Match verify-calibration-sync.sh semantics: a consumer path that does not
    // exist on disk is skipped (the holodeck staff-eng.md overlay is optional —
    // the UE block currently lives directly in the coordinator copy). A file
    // that exists but lacks the sentinel block is a real failure.
    const fs = require('fs');
    const extant = LIVE_CONSUMERS.filter(f => fs.existsSync(f));
    const blocks = extant.map(f => extractCalibrationBlock(f));
    const missing = extant.filter((_, i) => blocks[i] === null);

    if (extant.length === 0) {
      console.warn('[INFO] no consumer files exist on disk yet.');
      return;
    }

    if (blocks.every(b => b === null)) {
      console.warn(
        '[INFO] reviewer-calibration sentinels not yet present in any consumer file. ' +
        'This is expected before Borrow #5 lands.'
      );
      return;
    }

    assert.equal(
      missing.length,
      0,
      `Extant consumer files missing the reviewer-calibration sentinel:\n  ` +
      missing.join('\n  ')
    );

    const hashes = blocks.map(block => sha256(block));
    const unique = [...new Set(hashes)];
    assert.equal(
      unique.length,
      1,
      `Expected all reviewer-calibration blocks to have identical content. ` +
      `Got ${unique.length} distinct hashes across ${extant.length} extant consumers:\n` +
      extant.map((f, i) => `  ${hashes[i].slice(0, 8)}  ${f}`).join('\n')
    );
  });
});

// ---------------------------------------------------------------------------
// block-subagent-archive-write.sh — daily-summary carve-out + scope discrimination
// ---------------------------------------------------------------------------

describe('block-subagent-archive-write.sh', () => {
  const ARCHIVE_HOOK = path.join(
    COORDINATOR_DIR, 'hooks', 'scripts', 'block-subagent-archive-write.sh'
  );
  // Valid agent_id per the hook's format guard: lowercase hex, 12+ chars.
  const AID = 'abf1293aa3405b695';

  /** Run the hook with a hook-input JSON on stdin. Returns { status, stdout }. */
  function runHook(inputObj, env = {}) {
    const r = spawnSync('bash', [ARCHIVE_HOOK], {
      input: JSON.stringify(inputObj),
      encoding: 'utf-8',
      timeout: 10000,
      env: { ...process.env, ...env },
    });
    return { status: r.status, stdout: r.stdout || '' };
  }
  const isDeny = (out) => out.includes('"permissionDecision":"deny"');

  it('ALLOWS a subagent writing the dated daily-summary file (the Step 4b/4c sanctioned path)', { skip: !bashAvailable, timeout: 30_000 }, () => {
    const r = runHook({ tool_name: 'Write', agent_id: AID,
      tool_input: { file_path: 'archive/daily-summaries/2026-05-27.md' } });
    assert.equal(r.status, 0);
    assert.ok(!isDeny(r.stdout), 'dated daily-summary write must NOT be denied');
  });

  it('ALLOWS the same path with backslash separators (Windows normalization)', { skip: !bashAvailable }, () => {
    const r = runHook({ tool_name: 'Edit', agent_id: AID,
      tool_input: { file_path: 'archive\\daily-summaries\\2026-05-27.md' } });
    assert.ok(!isDeny(r.stdout), 'backslash daily-summary path must normalize and allow');
  });

  it('ALLOWS an ABSOLUTE daily-summary path (proves (^|/) anchor is load-bearing, not ^)', { skip: !bashAvailable }, () => {
    // Hook file_path inputs are frequently absolute; ^archive/ would wrongly DENY these.
    const r = runHook({ tool_name: 'Write', agent_id: AID,
      tool_input: { file_path: 'C:\\Users\\dev\\.claude\\archive\\daily-summaries\\2026-05-27.md' } });
    assert.ok(!isDeny(r.stdout), 'absolute-path daily-summary write must be allowed');
  });

  it('ALLOWS a MultiEdit to the dated daily-summary file (MultiEdit carries tool_input.file_path)', { skip: !bashAvailable }, () => {
    const r = runHook({ tool_name: 'MultiEdit', agent_id: AID,
      tool_input: { file_path: 'archive/daily-summaries/2026-05-27.md' } });
    assert.ok(!isDeny(r.stdout), 'MultiEdit daily-summary write must be allowed by the carve-out');
  });

  it('DENIES a subagent writing a NON-dated file under daily-summaries/ (tight scope)', { skip: !bashAvailable }, () => {
    const r = runHook({ tool_name: 'Write', agent_id: AID,
      tool_input: { file_path: 'archive/daily-summaries/notes.md' } });
    assert.ok(isDeny(r.stdout), 'non-dated daily-summaries file must still be denied');
  });

  it('DENIES a subagent writing elsewhere under archive/', { skip: !bashAvailable }, () => {
    const r = runHook({ tool_name: 'Write', agent_id: AID,
      tool_input: { file_path: 'archive/handoffs/something.md' } });
    assert.ok(isDeny(r.stdout), 'unsanctioned archive/ write must be denied');
  });

  it('ALLOWS the existing per-entry completion fallback (regression)', { skip: !bashAvailable }, () => {
    const r = runHook({ tool_name: 'Write', agent_id: AID,
      tool_input: { file_path: 'archive/completed/2026-05/2026-05-27-foo-abc123.md' } });
    assert.ok(!isDeny(r.stdout), 'per-entry completion fallback must remain allowed');
  });

  it('ALLOWS a top-level EM write to the daily summary (no agent_id)', { skip: !bashAvailable }, () => {
    const r = runHook({ tool_name: 'Write',
      tool_input: { file_path: 'archive/daily-summaries/2026-05-27.md' } });
    assert.ok(!isDeny(r.stdout), 'top-level EM write (no agent_id) is always allowed');
  });
});
