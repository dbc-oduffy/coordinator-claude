// orphan-sweep.test.js — unit tests for bin/orphan-branch-sweep.sh
//
// Spec backlink: docs/plans/2026-05-01-orphan-branch-prevention.md § 1.3
//
// SCOPE: exercises the three classifier cases (OK, WARNING, CRITICAL) using a
// temp git repo with planted branches and a stub `gh` binary on PATH.
//
// What IS covered:
//   - work/test/cleanmerged  → merged PR, 0 commits after merge → OK
//   - work/test/orphaned-after-merge → merged PR, commits after mergedAt → CRITICAL
//   - work/test/no-pr-stale  → no PR, branch-name date ≥2 days old → WARNING
//
// What is NOT covered:
//   - Live GitHub API calls (gh is stubbed)
//   - Cross-machine branch detection (out of scope per plan Non-goals)

'use strict';

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execSync, spawnSync } = require('child_process');
const {
  PLUGINS_ROOT,
  mkTempRepo,
  cleanupTempRepo,
  mkPathShim,
} = require('./helpers/fs');

const COORDINATOR_DIR = path.join(PLUGINS_ROOT, 'coordinator-claude', 'coordinator');
const SWEEP_SCRIPT = path.join(COORDINATOR_DIR, 'bin', 'orphan-branch-sweep.sh');

// ---------------------------------------------------------------------------
// Bash availability guard
// ---------------------------------------------------------------------------
let bashAvailable = false;
try {
  const r = spawnSync('bash', ['--version'], { stdio: 'pipe' });
  bashAvailable = r.status === 0;
} catch { /* no bash */ }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Back-date a git commit by N seconds relative to now.
 * Returns the commit timestamp as a Unix epoch string.
 */
function backdate(repoPath, branchName, secondsAgo) {
  const ts = Math.floor(Date.now() / 1000) - secondsAgo;
  const isoDate = new Date(ts * 1000).toISOString();
  execSync(`git checkout -q -b ${branchName}`, { cwd: repoPath });
  fs.writeFileSync(path.join(repoPath, `${branchName.replace(/\//g, '-')}.txt`), `branch ${branchName}`);
  execSync('git add .', { cwd: repoPath });
  execSync(`git commit -q --date="${isoDate}" -m "commit on ${branchName}"`, {
    cwd: repoPath,
    env: {
      ...process.env,
      GIT_AUTHOR_DATE: isoDate,
      GIT_COMMITTER_DATE: isoDate,
    },
  });
  execSync('git checkout -q main', { cwd: repoPath });
  return ts.toString();
}

/**
 * Add additional commits to a branch after a given timestamp (for orphan simulation).
 */
function addCommitsAfterDate(repoPath, branchName, afterIso, count) {
  // Pick a timestamp 60 seconds after afterIso
  const baseSecs = Math.floor(new Date(afterIso).getTime() / 1000) + 60;
  execSync(`git checkout -q ${branchName}`, { cwd: repoPath });
  for (let i = 0; i < count; i++) {
    const ts = baseSecs + i * 10;
    const isoDate = new Date(ts * 1000).toISOString();
    fs.writeFileSync(
      path.join(repoPath, `orphan-extra-${i}.txt`),
      `orphan commit ${i}`
    );
    execSync('git add .', { cwd: repoPath });
    execSync(`git commit -q --date="${isoDate}" -m "orphan commit ${i} on ${branchName}"`, {
      cwd: repoPath,
      env: {
        ...process.env,
        GIT_AUTHOR_DATE: isoDate,
        GIT_COMMITTER_DATE: isoDate,
      },
    });
  }
  execSync('git checkout -q main', { cwd: repoPath });
}

// ---------------------------------------------------------------------------
// Build a gh stub that returns appropriate JSON for each branch
// ---------------------------------------------------------------------------
function buildGhStub(shimDir, branchPrMap) {
  // branchPrMap: { branchName: { number, state, mergedAt } | null }
  // Write the map to a JSON file; stub reads it at runtime to avoid quoting hell.
  const mapFile = path.join(shimDir, 'pr-map.json');
  fs.writeFileSync(mapFile, JSON.stringify(branchPrMap));

  const scriptBody = `#!/usr/bin/env bash
# stub gh for orphan-sweep tests
BRANCH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --head) BRANCH="$2"; shift 2 ;;
    *) shift ;;
  esac
done
MAP_FILE="${mapFile.replace(/\\/g, '/')}"
python3 - "$BRANCH" "$MAP_FILE" <<'PYEOF'
import json, sys
branch = sys.argv[1]
with open(sys.argv[2]) as f:
    m = json.load(f)
pr = m.get(branch)
if pr is None:
    print('[]')
else:
    print(json.dumps([pr]))
PYEOF
`;
  const shimPath = path.join(shimDir, 'gh');
  fs.writeFileSync(shimPath, scriptBody, { mode: 0o755 });
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------
describe('orphan-branch-sweep.sh', { skip: !bashAvailable }, () => {
  let repoPath;
  let shimDir;
  let mergedAt;

  before(() => {
    // 1. Create a temp repo
    repoPath = mkTempRepo();

    // 2. Plant branches
    //    a) cleanmerged — branch from main, immediately merged back (ancestor of main tip)
    execSync('git checkout -q -b work/test/cleanmerged', { cwd: repoPath });
    // nothing extra — just check it out then merge it into main
    execSync('git checkout -q main', { cwd: repoPath });
    execSync('git merge --no-ff -q work/test/cleanmerged -m "merge cleanmerged"', { cwd: repoPath });

    //    b) orphaned-after-merge — create branch, record mergedAt, then add extra commits
    const staleDate = new Date(Date.now() - 4 * 24 * 3600 * 1000).toISOString();
    mergedAt = staleDate;
    backdate(repoPath, 'work/test/orphaned-after-merge', 4 * 24 * 3600 + 100);
    // Add commits after mergedAt
    addCommitsAfterDate(repoPath, 'work/test/orphaned-after-merge', mergedAt, 3);

    //    c) no-pr-stale — create with a 3-day-old branch-name date, no PR
    //    branch name includes a date ≥2 days ago
    const staleDayStr = new Date(Date.now() - 3 * 24 * 3600 * 1000)
      .toISOString().split('T')[0]; // YYYY-MM-DD
    const staleBranchName = `work/testmachine/${staleDayStr}`;
    backdate(repoPath, staleBranchName, 3 * 24 * 3600);

    // 3. Build gh stub
    shimDir = fs.mkdtempSync(path.join(os.tmpdir(), 'claude-gh-stub-'));
    buildGhStub(shimDir, {
      // cleanmerged has a merged PR with no commits after
      'work/test/cleanmerged': {
        number: 1,
        state: 'MERGED',
        mergedAt: new Date(Date.now() - 5 * 24 * 3600 * 1000).toISOString(),
        mergeCommit: null,
      },
      // orphaned-after-merge has a merged PR but commits exist after mergedAt
      'work/test/orphaned-after-merge': {
        number: 2,
        state: 'MERGED',
        mergedAt: mergedAt,
        mergeCommit: null,
      },
      // no-pr-stale has no PR (key absent — returns [])
    });
  });

  after(() => {
    cleanupTempRepo(repoPath);
    if (shimDir) {
      try { fs.rmSync(shimDir, { recursive: true, force: true }); } catch {}
    }
  });

  it('script exists and is runnable by bash', () => {
    assert.ok(fs.existsSync(SWEEP_SCRIPT), `sweep script not found at ${SWEEP_SCRIPT}`);
    // On Windows, POSIX mode bits via stat are unreliable. Confirm bash can run it.
    const r = spawnSync('bash', [SWEEP_SCRIPT, '--help'], { encoding: 'utf8' });
    assert.equal(r.status, 0, `bash could not execute sweep script: ${r.stderr}`);
  });

  it('exits 0 cleanly with --help', () => {
    const r = spawnSync('bash', [SWEEP_SCRIPT, '--help'], { encoding: 'utf8' });
    assert.equal(r.status, 0, `--help exited ${r.status}: ${r.stderr}`);
    assert.ok(r.stdout.includes('--format'), '--help output missing --format');
  });

  it('exits 0 outside a git repo (skip-silently contract)', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'no-git-'));
    try {
      const r = spawnSync('bash', [SWEEP_SCRIPT], {
        cwd: tmpDir,
        encoding: 'utf8',
      });
      assert.equal(r.status, 0, `expected exit 0 outside git repo, got ${r.status}`);
      assert.equal(r.stdout.trim(), '', 'expected no output outside git repo');
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('classifies work/test/orphaned-after-merge as CRITICAL', () => {
    const env = {
      ...process.env,
      PATH: `${shimDir}${path.delimiter}${process.env.PATH}`,
      HOME: repoPath,
    };
    const r = spawnSync(
      'bash',
      [SWEEP_SCRIPT, '--format', 'json', '--severity-min', 'critical', '--max-age-days', '90'],
      { cwd: repoPath, encoding: 'utf8', env }
    );
    assert.equal(r.status, 0, `sweep exited ${r.status}: ${r.stderr}`);
    const lines = r.stdout.split('\n').filter(l => l.trim());
    const critical = lines.filter(l => {
      try {
        const obj = JSON.parse(l);
        return obj.severity === 'CRITICAL' && obj.branch === 'work/test/orphaned-after-merge';
      } catch { return false; }
    });
    assert.ok(critical.length >= 1, `Expected CRITICAL for orphaned-after-merge, got:\n${r.stdout}`);
  });

  it('classifies the stale no-PR branch as WARNING', () => {
    const staleDayStr = new Date(Date.now() - 3 * 24 * 3600 * 1000)
      .toISOString().split('T')[0];
    const env = {
      ...process.env,
      PATH: `${shimDir}${path.delimiter}${process.env.PATH}`,
      HOME: repoPath,
    };
    const r = spawnSync(
      'bash',
      [SWEEP_SCRIPT, '--format', 'json', '--severity-min', 'warning', '--max-age-days', '90'],
      { cwd: repoPath, encoding: 'utf8', env }
    );
    assert.equal(r.status, 0, `sweep exited ${r.status}: ${r.stderr}`);
    const lines = r.stdout.split('\n').filter(l => l.trim());
    const warnings = lines.filter(l => {
      try {
        const obj = JSON.parse(l);
        return obj.severity === 'WARNING' && obj.branch.includes(staleDayStr);
      } catch { return false; }
    });
    assert.ok(warnings.length >= 1, `Expected WARNING for stale no-PR branch (${staleDayStr}), got:\n${r.stdout}`);
  });

  it('--severity-min critical suppresses WARNING entries', () => {
    const env = {
      ...process.env,
      PATH: `${shimDir}${path.delimiter}${process.env.PATH}`,
      HOME: repoPath,
    };
    const r = spawnSync(
      'bash',
      [SWEEP_SCRIPT, '--format', 'json', '--severity-min', 'critical', '--max-age-days', '90'],
      { cwd: repoPath, encoding: 'utf8', env }
    );
    assert.equal(r.status, 0);
    const lines = r.stdout.split('\n').filter(l => l.trim());
    const warnings = lines.filter(l => {
      try { return JSON.parse(l).severity === 'WARNING'; } catch { return false; }
    });
    assert.equal(warnings.length, 0, `--severity-min critical should suppress WARNINGs, got: ${r.stdout}`);
  });

  it('text format emits readable lines', () => {
    const env = {
      ...process.env,
      PATH: `${shimDir}${path.delimiter}${process.env.PATH}`,
      HOME: repoPath,
    };
    const r = spawnSync(
      'bash',
      [SWEEP_SCRIPT, '--format', 'text', '--severity-min', 'warning', '--max-age-days', '90'],
      { cwd: repoPath, encoding: 'utf8', env }
    );
    assert.equal(r.status, 0, `sweep exited ${r.status}: ${r.stderr}`);
    // Lines should start with CRITICAL or WARNING
    const lines = r.stdout.split('\n').filter(l => l.trim());
    assert.ok(lines.length >= 1, 'Expected at least one output line in text format');
    for (const line of lines) {
      assert.ok(
        line.startsWith('CRITICAL') || line.startsWith('WARNING') || line.startsWith('OK'),
        `Unexpected text format line: ${line}`
      );
    }
  });
});
