// discover-working-repos.test.js — unit tests for lib/discover-working-repos.sh
//
// Spec backlink: tasks/handoffs/2026-06-01_105805_discover-working-repos-tier-a-lossy-decode.md
//
// SCOPE: exercises Tier A's lossy-encoding decode. Claude Code encodes a
// working-dir path into a projects-dir name by mapping `:` `\` `/` `.` → `-`.
// That encoding is LOSSY — a literal hyphen in a segment and a structural
// separator both become `-` — so a blanket `-`→separator reverse drops any
// repo whose path segments contain real hyphens (nearly every sibling repo:
// fifa-stats, project-rag-ue-addon, ...). The fix keeps the naive decode as a
// fast path and falls back to a greedy filesystem-walk disambiguation.
//
// Hermetic-test mechanics:
//   - Source the script (a main-guard skips the live tier dispatch when sourced)
//     and call _tier_a / _tier_a_greedy_decode in isolation — keeps Tier A.5
//     (the real machine-local registry on PATH) out of the assertions.
//   - HOME points at a fixture `.claude/projects/` tree of ENCODED names.
//   - COORDINATOR_TIER_A_FS_ROOT points at the real (fixture) tree the greedy
//     walk resolves against, replacing the real drive root (/x).
//
// What IS covered:
//   - single-hyphen repo (fifa-stats) resolves and emits native Windows form
//   - multi-hyphen repo (project-rag-ue-addon, geneva-mvp) resolves
//   - hyphens AND deeper nesting (some-thing/sub-dir) resolves
//   - non-existent encoded path emits nothing (fail-safe preserved)
//   - no-hyphen path still resolves unchanged (fast path)
//   - bash -n is clean
//
// What is NOT covered:
//   - Tier A.5 / B / C (out of scope — they already work and are non-lossy)
//   - the real machine's registry (isolated out by sourcing _tier_a directly)

'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawnSync } = require('child_process');
const { PLUGINS_ROOT } = require('./helpers/fs');

const SCRIPT = path.join(
  PLUGINS_ROOT, 'coordinator-claude', 'coordinator', 'lib', 'discover-working-repos.sh'
);

let bashAvailable = false;
try {
  bashAvailable = spawnSync('bash', ['--version'], { stdio: 'pipe' }).status === 0;
} catch { /* no bash */ }

// Build a fixture: encoded projects-dir names under HOME + a real tree under
// fsroot. `encodedToReal` maps each encoded projects-dir basename to its real
// relative tree path (POSIX, under fsroot) — or null to plant the activity
// record WITHOUT a matching tree (the fail-safe / drop case).
function mkFixture(encodedToReal) {
  const T = fs.mkdtempSync(path.join(os.tmpdir(), 'discover-repos-'));
  const projectsDir = path.join(T, 'home', '.claude', 'projects');
  fs.mkdirSync(projectsDir, { recursive: true });
  const fsroot = path.join(T, 'fsroot');
  fs.mkdirSync(fsroot, { recursive: true });
  for (const [encoded, realRel] of Object.entries(encodedToReal)) {
    fs.mkdirSync(path.join(projectsDir, encoded), { recursive: true });
    if (realRel) fs.mkdirSync(path.join(fsroot, realRel), { recursive: true });
  }
  return { T, home: path.join(T, 'home'), fsroot };
}

// Source the script and run `_tier_a` in isolation (no Tier A.5/B). Returns the
// emitted repo lines.
function runTierA(fixture) {
  // Pass a distinct $0 ('sourced') so the script's `BASH_SOURCE[0] == $0`
  // main-guard correctly detects sourcing and skips the live tier dispatch
  // (otherwise `bash -c 'source "$0"' SCRIPT` would set $0 == SCRIPT and the
  // guard would run Tier A.5/B, leaking the real machine registry).
  // `|| true` mirrors the production caller contract (`_a_out=$(_tier_a || true)`):
  // under `pipefail`, the trailing `grep -vE` legitimately exits 1 when it
  // filters everything out (empty Tier A), which is not a failure.
  const r = spawnSync('bash', ['-c', 'source "$1"; _tier_a || true', 'sourced', SCRIPT], {
    encoding: 'utf8',
    env: {
      ...process.env,
      HOME: fixture.home,
      COORDINATOR_TIER_A_FS_ROOT: fixture.fsroot,
    },
  });
  assert.equal(r.status, 0, `_tier_a exited ${r.status}: ${r.stderr}`);
  return r.stdout.split('\n').map((l) => l.trim()).filter(Boolean);
}

describe('discover-working-repos.sh — Tier A lossy decode', { skip: !bashAvailable }, () => {
  it('script exists and is bash -n clean', () => {
    assert.ok(fs.existsSync(SCRIPT), `script not found at ${SCRIPT}`);
    const r = spawnSync('bash', ['-n', SCRIPT], { encoding: 'utf8' });
    assert.equal(r.status, 0, `bash -n reported syntax errors: ${r.stderr}`);
  });

  it('resolves a single-hyphen repo to its native Windows path', () => {
    const fx = mkFixture({ 'X--dev-fifa-stats': 'dev/fifa-stats' });
    try {
      const out = runTierA(fx);
      assert.ok(out.includes('X:\\dev\\fifa-stats'), `expected X:\\dev\\fifa-stats, got:\n${out.join('\n')}`);
      // Regression guard: the pre-fix bug emitted the mis-split X:\dev\fifa\stats.
      assert.ok(!out.includes('X:\\dev\\fifa\\stats'), `mis-split path leaked: ${out.join('\n')}`);
    } finally {
      cleanup(fx);
    }
  });

  it('resolves multi-hyphen repo names', () => {
    const fx = mkFixture({
      'X--dev-project-rag-ue-addon': 'dev/project-rag-ue-addon',
      'X--dev-geneva-mvp': 'dev/geneva-mvp',
    });
    try {
      const out = runTierA(fx);
      assert.ok(out.includes('X:\\dev\\project-rag-ue-addon'), `missing project-rag-ue-addon in:\n${out.join('\n')}`);
      assert.ok(out.includes('X:\\dev\\geneva-mvp'), `missing geneva-mvp in:\n${out.join('\n')}`);
    } finally {
      cleanup(fx);
    }
  });

  it('resolves hyphens combined with deeper nesting', () => {
    const fx = mkFixture({ 'X--dev-some-thing-sub-dir': 'dev/some-thing/sub-dir' });
    try {
      const out = runTierA(fx);
      assert.ok(out.includes('X:\\dev\\some-thing\\sub-dir'), `expected nested path, got:\n${out.join('\n')}`);
    } finally {
      cleanup(fx);
    }
  });

  it('emits nothing for an encoded path with no matching tree (fail-safe)', () => {
    const fx = mkFixture({ 'X--dev-ghost-repo': null });
    try {
      const out = runTierA(fx);
      assert.equal(out.length, 0, `expected no output for a non-existent path, got:\n${out.join('\n')}`);
    } finally {
      cleanup(fx);
    }
  });

  it('emits nothing for a bare-drive-root encoded entry (double guard)', () => {
    // X-- decodes to the bare drive root; the greedy walk fails on the empty
    // remainder AND the `^[A-Za-z]:\\?$` filter drops it — neither should emit.
    const fx = mkFixture({ 'X--': null });
    try {
      const out = runTierA(fx);
      assert.equal(out.length, 0, `expected no output for bare drive root, got:\n${out.join('\n')}`);
    } finally {
      cleanup(fx);
    }
  });

  it('still resolves a no-hyphen path via the fast path', () => {
    const fx = mkFixture({ 'X--workspace': 'workspace' });
    try {
      const out = runTierA(fx);
      assert.ok(out.includes('X:\\workspace'), `expected X:\\workspace via fast path, got:\n${out.join('\n')}`);
    } finally {
      cleanup(fx);
    }
  });

  it('greedy decode helper resolves directly against an injected root', () => {
    const fx = mkFixture({ '_': 'dev/project-rag-ue-addon' });
    try {
      const r = spawnSync(
        'bash',
        ['-c', 'source "$1"; _tier_a_greedy_decode "dev-project-rag-ue-addon" "X" "$2"', 'sourced', SCRIPT, fx.fsroot],
        { encoding: 'utf8', env: { ...process.env } }
      );
      assert.equal(r.status, 0, `helper exited ${r.status}: ${r.stderr}`);
      assert.equal(r.stdout.trim(), 'X:\\dev\\project-rag-ue-addon');
    } finally {
      cleanup(fx);
    }
  });
});

function cleanup(fx) {
  try { fs.rmSync(fx.T, { recursive: true, force: true }); } catch { /* best effort */ }
}
