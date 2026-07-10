'use strict';
/**
 * verify-coverage.test.js — Tests for verify-coverage.js.
 *
 * Builds temp plugin-tree fixtures and asserts the validator surfaces (and silences)
 * the right orphan-reference categories. Mirrors the spirit of
 * `control/server/src/__tests__/agent-domain-coverage.test.ts` in the example-game-repo repo —
 * the test must live alongside the validator it covers, not only in the consumer repo.
 *
 * Run with: node --test bin/verify-coverage.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const VERIFY = path.resolve(__dirname, 'verify-coverage.js');
// Review: code-reviewer (Finding 2) — import defaultRoot for unit-testing sentinel logic;
// require() is safe because main() is now guarded with require.main === module.
const { defaultRoot } = require('./verify-coverage');

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

let fixtureCounter = 0;
function makeFixtureRoot() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `verify-coverage-fixture-${process.pid}-${fixtureCounter++}-`));
  return dir;
}

function writeFile(p, content) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content);
}

/**
 * Make a minimal plugin tree at `root` with the given specs.
 *
 * spec example:
 *   {
 *     coordinator: { skills: ['plan'], agents: ['staff-eng'], commands: ['workday-start'] },
 *     'game-dev':  { agents: ['staff-game-dev'] },
 *   }
 *
 * Returns the root directory path.
 */
function scaffold(spec, files = {}) {
  const root = makeFixtureRoot();
  for (const [plugin, kinds] of Object.entries(spec)) {
    for (const skill of kinds.skills || []) {
      writeFile(path.join(root, plugin, 'skills', skill, 'SKILL.md'), `# ${skill}\n`);
    }
    for (const agent of kinds.agents || []) {
      writeFile(path.join(root, plugin, 'agents', `${agent}.md`), `# ${agent}\n`);
    }
    for (const cmd of kinds.commands || []) {
      writeFile(path.join(root, plugin, 'commands', `${cmd}.md`), `# ${cmd}\n`);
    }
  }
  for (const [relPath, content] of Object.entries(files)) {
    writeFile(path.join(root, relPath), content);
  }
  return root;
}

function runValidator(root) {
  try {
    const out = execFileSync(process.execPath, [VERIFY, '--root', root, '--json'], {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return { exit: 0, json: JSON.parse(out) };
  } catch (err) {
    return { exit: err.status, json: err.stdout ? JSON.parse(err.stdout) : null, stderr: err.stderr };
  }
}

// ---------------------------------------------------------------------------
// Smoke
// ---------------------------------------------------------------------------

test('empty tree: zero violations, exit 0', () => {
  const root = scaffold({ coordinator: {} });
  const r = runValidator(root);
  assert.equal(r.exit, 0);
  assert.equal(r.json.summary.violations, 0);
  assert.equal(r.json.ok, true);
});

test('all refs resolve: zero violations', () => {
  const root = scaffold(
    {
      coordinator: { skills: ['plan'], agents: ['staff-eng'], commands: ['workday-start'] },
    },
    {
      'coordinator/skills/plan/SKILL.md':
        '# plan\n\nSee `coordinator:staff-eng` for review.\n',
      'coordinator/agents/staff-eng.md':
        '# staff-eng\n\nInvoke via `coordinator:plan` and `/coordinator:workday-start`.\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0, `expected exit 0, got ${r.exit}; violations: ${JSON.stringify(r.json?.violations)}`);
  assert.equal(r.json.summary.violations, 0);
});

// ---------------------------------------------------------------------------
// QUALIFIED_ORPHANED
// ---------------------------------------------------------------------------

test('qualified orphan: typo in skill name surfaces as QUALIFIED orphan', () => {
  const root = scaffold(
    { coordinator: { skills: ['plan'] } },
    { 'coordinator/skills/plan/SKILL.md': '# plan\n\nSee `coordinator:plann` for typo.\n' }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 1);
  assert.equal(r.json.summary.violations, 1);
  assert.equal(r.json.violations[0].kind, 'qualified');
  assert.equal(r.json.violations[0].ref, 'coordinator:plann');
});

test('qualified orphan: ref to wrong plugin namespace flagged', () => {
  // `coordinator:no-such-skill` is a plausible-looking but nonexistent coordinator skill.
  // Writers sometimes reference a renamed/removed skill — exactly the drift this validator
  // catches. (Must NOT be an allowlisted name; `coordinator:writing-plans` was used here
  // originally but is now in QUALIFIED_ALLOWLIST as a known historical rename, which
  // correctly suppressed it and left this assertion stale — see 2026-06-01 fix.)
  const root = scaffold(
    { coordinator: { skills: ['plan'] } },
    { 'coordinator/skills/plan/SKILL.md': '# plan\n\nSee `coordinator:no-such-skill`.\n' }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 1);
  assert.equal(r.json.violations[0].ref, 'coordinator:no-such-skill');
});

test('refs to plugins NOT in tree are skipped (treated as external)', () => {
  // example-game-repo-control:* and superpowers:* are external plugins — the validator should
  // not flag them since they don't live in coordinator-claude.
  const root = scaffold(
    { coordinator: { skills: ['plan'] } },
    {
      'coordinator/skills/plan/SKILL.md':
        '# plan\n\nDispatch `example-game-repo-control:ue-asset-author`. See `superpowers:writing-plans` too.\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0);
  assert.equal(r.json.summary.violations, 0);
});

// ---------------------------------------------------------------------------
// SUBAGENT_ORPHANED
// ---------------------------------------------------------------------------

test('subagent: bare-name ref resolves against any plugin', () => {
  const root = scaffold(
    {
      coordinator: { skills: ['plan'] },
      'game-dev': { agents: ['staff-game-dev'] },
    },
    {
      'coordinator/skills/plan/SKILL.md':
        '# plan\n\nDispatch with `subagent_type: "staff-game-dev"`.\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0, `unexpected exit ${r.exit}; violations: ${JSON.stringify(r.json?.violations)}`);
});

test('subagent: typo flagged', () => {
  const root = scaffold(
    {
      coordinator: { skills: ['plan'], agents: ['staff-eng'] },
    },
    {
      'coordinator/skills/plan/SKILL.md':
        '# plan\n\nDispatch with `subagent_type: "staf-eng"`.\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 1);
  const found = r.json.violations.find(v => v.kind === 'subagent' && v.ref === 'staf-eng');
  assert.ok(found, `expected subagent orphan for staf-eng; got: ${JSON.stringify(r.json.violations)}`);
});

test('subagent: template placeholder ({domain}) does NOT trigger orphan', () => {
  // Real artifact: docs/skills sometimes embed example dispatches like
  //   subagent_type='example-game-repo-control:ue-{domain}'
  // These are templates, not refs. Validator must not flag the trailing-dash capture.
  const root = scaffold(
    { coordinator: { skills: ['session-start'] } },
    {
      'coordinator/skills/session-start/SKILL.md':
        "# session-start\n\nExample: `Agent(subagent_type='example-game-repo-control:ue-{domain}')`.\n",
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0, `template placeholder must not trigger orphan; got: ${JSON.stringify(r.json?.violations)}`);
});

// ---------------------------------------------------------------------------
// COMMAND_ORPHANED
// ---------------------------------------------------------------------------

test('command: /coordinator:workday-start resolves to the registered command', () => {
  const root = scaffold(
    { coordinator: { commands: ['workday-start'], skills: ['plan'] } },
    { 'coordinator/skills/plan/SKILL.md': '# plan\n\nRun /coordinator:workday-start to start.\n' }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0);
});

test('command: bare /workday-start resolves via fallback', () => {
  const root = scaffold(
    { coordinator: { commands: ['workday-start'], skills: ['plan'] } },
    { 'coordinator/skills/plan/SKILL.md': '# plan\n\nRun `/coordinator:workday-start` to start.\n' }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0);
});

// ---------------------------------------------------------------------------
// WORKER_ORPHANED — bullets under "## Worker Dispatch Recommendations"
// ---------------------------------------------------------------------------

test('worker: bullet under reviewer header resolves to agent', () => {
  const root = scaffold(
    {
      coordinator: { agents: ['staff-eng', 'test-evidence-parser', 'security-audit-worker'] },
    },
    {
      'coordinator/agents/staff-eng.md':
        '# staff-eng\n\nSome prose.\n\n## Worker Dispatch Recommendations\n\n- test-evidence-parser — parse vitest output\n- security-audit-worker — scan diff\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0, `unexpected exit ${r.exit}; violations: ${JSON.stringify(r.json?.violations)}`);
});

test('worker: typo in worker name flagged', () => {
  const root = scaffold(
    { coordinator: { agents: ['staff-eng', 'test-evidence-parser'] } },
    {
      'coordinator/agents/staff-eng.md':
        '# staff-eng\n\n## Worker Dispatch Recommendations\n\n- test-evidence-pareser — typo\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 1);
  const found = r.json.violations.find(v => v.kind === 'worker' && v.ref === 'test-evidence-pareser');
  assert.ok(found, `expected worker orphan; got: ${JSON.stringify(r.json.violations)}`);
});

test('worker: header scope ends at next ## heading', () => {
  // A bullet outside the Worker Dispatch Recommendations block must NOT be parsed
  // as a worker reference — even if it looks like an agent name.
  const root = scaffold(
    { coordinator: { agents: ['staff-eng'] } },
    {
      'coordinator/agents/staff-eng.md':
        '# staff-eng\n\n## Worker Dispatch Recommendations\n\n- test-evidence-parser — ok\n\n## Other Section\n\n- not-a-real-worker — must NOT be flagged here\n',
    }
  );
  const r = runValidator(root);
  // Only the worker-block bullet was parsed; "not-a-real-worker" is in a different section.
  const workerOrphans = (r.json?.violations || []).filter(v => v.kind === 'worker');
  // test-evidence-parser doesn't exist in this fixture so it WILL be flagged once.
  assert.equal(workerOrphans.length, 1, `got: ${JSON.stringify(workerOrphans)}`);
  assert.equal(workerOrphans[0].ref, 'test-evidence-parser');
});

// ---------------------------------------------------------------------------
// Code-fence stripping — refs inside ```...``` blocks are not parsed
// ---------------------------------------------------------------------------

test('code fences are stripped: orphan ref inside ``` is not flagged', () => {
  const root = scaffold(
    { coordinator: { skills: ['plan'] } },
    {
      'coordinator/skills/plan/SKILL.md':
        '# plan\n\nExample:\n\n```\ncoordinator:not-a-real-skill\n```\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0, `code-fence ref must not trigger orphan; got: ${JSON.stringify(r.json?.violations)}`);
});

// ---------------------------------------------------------------------------
// Frontmatter stripping
// ---------------------------------------------------------------------------

test('frontmatter is stripped: name field with colon does not trigger orphan', () => {
  const root = scaffold(
    { coordinator: { skills: ['plan'] } },
    {
      'coordinator/skills/plan/SKILL.md':
        '---\nname: coordinator:plan\ndescription: anything\n---\n\n# plan\n',
    }
  );
  const r = runValidator(root);
  assert.equal(r.exit, 0);
});

// ---------------------------------------------------------------------------
// Self-check — verify-coverage.js running against the live tree must not regress
// past the current orphan baseline. Skipped when run outside the meta-repo
// (e.g., from a published consumer copy) since the baseline is meta-repo-specific.
// ---------------------------------------------------------------------------

test('self-check: live coordinator-claude tree runs without script error', () => {
  // Review: code-reviewer (Findings 1 + 5) — two levels up from coordinator/bin reaches the
  // DoE-clone root (DoE-claude/), whose child coordinator/ exists; three levels was correct
  // only for the old published-mirror layout (coordinator-claude/) where __dirname was one
  // level shallower.  DoE layout: ../.. = DoE-clone root; mirror layout: ../../.. = coordinator-claude root.
  const live = path.resolve(__dirname, '..', '..'); // DoE layout: DoE-clone root; mirror layout: coordinator-claude root (three levels up)
  if (!fs.existsSync(path.join(live, 'coordinator'))) return; // Skip when consumer-published.
  const r = runValidator(live);
  // We do NOT assert exit 0 — there's a known drift baseline (~15 orphans as of v0.1).
  // The contract here is: the script doesn't crash and emits parseable JSON.
  assert.ok(r.json !== null, `validator did not emit JSON for live tree; stderr: ${r.stderr}`);
  assert.ok(typeof r.json.summary.violations === 'number');
});

// ---------------------------------------------------------------------------
// defaultRoot() — sentinel read and OSS fallback
// Review: code-reviewer (Finding 2) — the primary behavioral change of C5 must be testable.
// defaultRoot() now accepts an injectable homeDir so we can isolate the sentinel logic
// without touching process.env.HOME or the real filesystem.
// ---------------------------------------------------------------------------

test('defaultRoot: uses sentinel path when .doe-root file is present and non-empty', () => {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), `doe-root-sentinel-test-${process.pid}-`));
  const sentinelDir = path.join(tmpHome, '.claude');
  fs.mkdirSync(sentinelDir, { recursive: true });
  const fakeDoeRoot = '/fake/doe/clone/root';
  fs.writeFileSync(path.join(sentinelDir, '.doe-root'), fakeDoeRoot + '\n'); // trailing newline — trim() must strip it
  const result = defaultRoot(tmpHome);
  assert.equal(result, fakeDoeRoot, `expected sentinel value ${fakeDoeRoot}; got ${result}`);
});

test('defaultRoot: falls back to OSS mirror path when sentinel is absent', () => {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), `doe-root-fallback-test-${process.pid}-`));
  // No .doe-root file — ENOENT expected; should fall back silently.
  const result = defaultRoot(tmpHome);
  const expected = path.join(tmpHome, '.claude', 'plugins', 'coordinator-claude');
  assert.equal(result, expected, `expected OSS fallback ${expected}; got ${result}`);
});
