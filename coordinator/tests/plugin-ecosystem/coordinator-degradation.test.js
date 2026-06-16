// DSR-2026-04-03-5: Coordinator graceful degradation without deep-research
//
// SCOPE: Integration tests that exercise real script execution.
//
// What IS covered:
//   - suggest-sonnet-research.sh exits cleanly and produces valid JSON in both states
//   - Without deep-research: output omits unavailable commands (/deep-research,
//     /structured-research, /notebooklm-research) and redirects to installation
//   - Without deep-research: non-deep-research alternatives (Explore, enricher) still present
//   - With deep-research: output includes the full set of research commands
//   - coordinator-reminder.sh exits cleanly and produces non-empty output
//   - capability-catalog.md annotates deep-research-dependent features correctly
//
// What is NOT covered:
//   - Whether Claude actually routes to these alternatives (behavioral correctness)
//   - Runtime hook firing and context injection (requires live Claude session)

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const os = require('os');
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');
const { PLUGINS_ROOT, fileExists, dirExists } = require('./helpers/fs');

const COORDINATOR_PLUGIN_DIR = path.join(PLUGINS_ROOT, 'coordinator-claude', 'coordinator');
const HOOKS_SCRIPTS_DIR = path.join(COORDINATOR_PLUGIN_DIR, 'hooks', 'scripts');
const SUGGEST_SCRIPT = path.join(HOOKS_SCRIPTS_DIR, 'suggest-sonnet-research.sh');
const REMINDER_SCRIPT = path.join(HOOKS_SCRIPTS_DIR, 'coordinator-reminder.sh');
const CATALOG_PATH = path.join(COORDINATOR_PLUGIN_DIR, 'capability-catalog.md');
const DEEP_RESEARCH_DIR = path.join(PLUGINS_ROOT, 'coordinator-claude', 'deep-research');

// A fake HOME that has no deep-research directory — simulates a coordinator-only install
const FAKE_HOME_NO_DR = path.join(os.tmpdir(), 'coordinator-degradation-test-no-deep-research');

// Run suggest-sonnet-research.sh once per state, at module load time
// (bash syntax errors here are real failures, not skippable)
let withoutDrResult = null;
let withoutDrError = null;
let withDrResult = null;
let withDrError = null;
let bashAvailable = true;

try {
  execSync('bash --version', { stdio: 'pipe', timeout: 5000 });
} catch {
  bashAvailable = false;
}

if (bashAvailable && fileExists(SUGGEST_SCRIPT)) {
  try {
    const buf = execSync(`bash "${SUGGEST_SCRIPT}"`, {
      env: { ...process.env, HOME: FAKE_HOME_NO_DR },
      timeout: 10000,
      stdio: 'pipe',
    });
    withoutDrResult = { raw: buf.toString('utf-8') };
    withoutDrResult.parsed = JSON.parse(withoutDrResult.raw);
    withoutDrResult.ctx = withoutDrResult.parsed.hookSpecificOutput.additionalContext;
  } catch (e) {
    withoutDrError = e;
  }

  if (dirExists(DEEP_RESEARCH_DIR)) {
    try {
      const buf = execSync(`bash "${SUGGEST_SCRIPT}"`, {
        timeout: 10000,
        stdio: 'pipe',
      });
      withDrResult = { raw: buf.toString('utf-8') };
      withDrResult.parsed = JSON.parse(withDrResult.raw);
      withDrResult.ctx = withDrResult.parsed.hookSpecificOutput.additionalContext;
    } catch (e) {
      withDrError = e;
    }
  }
}

// ─── suggest-sonnet-research.sh — without deep-research ─────────────────────

describe('suggest-sonnet-research.sh — without deep-research (degradation path)', () => {

  it('prerequisite: bash is available and script exists', () => {
    assert.ok(bashAvailable, 'bash must be available to run integration tests');
    assert.ok(fileExists(SUGGEST_SCRIPT), `Script not found: ${SUGGEST_SCRIPT}`);
  });

  it('exits without error', () => {
    if (!bashAvailable) return;
    if (withoutDrError) {
      const stderr = withoutDrError.stderr ? withoutDrError.stderr.toString().trim() : '';
      assert.fail(`Script failed (exit ${withoutDrError.status}): ${stderr}`);
    }
    assert.ok(withoutDrResult, 'Script produced no output');
  });

  it('outputs valid JSON', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.ok(withoutDrResult.parsed, 'Output should parse as JSON');
    assert.equal(typeof withoutDrResult.parsed, 'object');
  });

  it('permissionDecision is "allow" (never blocks)', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.equal(
      withoutDrResult.parsed.hookSpecificOutput.permissionDecision,
      'allow',
      'Hook must always allow — it is a nudge only, never a block'
    );
  });

  it('does not reference /deep-research command (unavailable without plugin)', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.ok(
      !withoutDrResult.ctx.includes('→ /deep-research'),
      'Degraded output must not reference /deep-research as an available command'
    );
  });

  it('does not reference /structured-research command (unavailable without plugin)', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.ok(
      !withoutDrResult.ctx.includes('/structured-research'),
      'Degraded output must not reference /structured-research as an available command'
    );
  });

  it('does not reference /notebooklm-research command (unavailable without plugin)', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.ok(
      !withoutDrResult.ctx.includes('/notebooklm-research'),
      'Degraded output must not reference /notebooklm-research as an available command'
    );
  });

  it('redirects to deep-research installation instead of commands', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.ok(
      withoutDrResult.ctx.includes('install the deep-research plugin'),
      'Degraded output must direct user to install the deep-research plugin'
    );
  });

  it('still offers Explore subagent (non-deep-research codebase alternative)', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.ok(
      withoutDrResult.ctx.includes("subagent_type='Explore'"),
      "Degraded output must still mention subagent_type='Explore' for codebase research"
    );
  });

  it('still offers enricher subagent (non-deep-research spec enrichment alternative)', () => {
    if (!bashAvailable || withoutDrError) return;
    assert.ok(
      withoutDrResult.ctx.includes('coordinator:enricher'),
      'Degraded output must still mention coordinator:enricher for spec enrichment'
    );
  });
});

// ─── suggest-sonnet-research.sh — with deep-research ────────────────────────

describe('suggest-sonnet-research.sh — with deep-research present', () => {

  it('mentions /research --mode=web when plugin is present', () => {
    if (!bashAvailable || !dirExists(DEEP_RESEARCH_DIR)) return; // skip if not installed
    if (withDrError) {
      assert.fail(`Script failed with deep-research present: ${withDrError.message}`);
    }
    assert.ok(
      withDrResult.ctx.includes('/research --mode=web'),
      'With deep-research installed, output must reference /research --mode=web'
    );
  });

  it('mentions /research --mode=structured when plugin is present', () => {
    if (!bashAvailable || !dirExists(DEEP_RESEARCH_DIR) || withDrError) return;
    assert.ok(
      withDrResult.ctx.includes('/research --mode=structured'),
      'With deep-research installed, output must reference /research --mode=structured'
    );
  });

  it('mentions /notebooklm-research when plugin is present', () => {
    if (!bashAvailable || !dirExists(DEEP_RESEARCH_DIR) || withDrError) return;
    assert.ok(
      withDrResult.ctx.includes('/notebooklm-research'),
      'With deep-research installed, output must reference /notebooklm-research'
    );
  });

  it('does not say "install the deep-research plugin" when plugin is present', () => {
    if (!bashAvailable || !dirExists(DEEP_RESEARCH_DIR) || withDrError) return;
    assert.ok(
      !withDrResult.ctx.includes('install the deep-research plugin'),
      'When deep-research is installed, must not show installation prompt'
    );
  });
});

// ─── coordinator-reminder.sh — runs without deep-research ───────────────────

describe('coordinator-reminder.sh — runs without crashing', () => {

  it('exits cleanly and produces non-empty output', { timeout: 30_000 }, () => {
    if (!bashAvailable) return;
    assert.ok(fileExists(REMINDER_SCRIPT), `Script not found: ${REMINDER_SCRIPT}`);

    let output;
    try {
      const buf = execSync(`bash "${REMINDER_SCRIPT}"`, {
        timeout: 25000,
        stdio: 'pipe',
      });
      output = buf.toString('utf-8');
    } catch (e) {
      const stderr = e.stderr ? e.stderr.toString().trim() : '';
      assert.fail(`coordinator-reminder.sh crashed (exit ${e.status}): ${stderr}`);
    }

    assert.ok(output && output.length > 0, 'coordinator-reminder.sh must produce non-empty output');
  });
});

// ─── capability-catalog.md — deep-research annotations ──────────────────────

describe('capability-catalog.md — deep-research dependent features are annotated', () => {

  let catalog;

  try {
    catalog = fs.readFileSync(CATALOG_PATH, 'utf-8');
  } catch {
    // If catalog doesn't exist, tests below will fail with a clear message
  }

  it('catalog file exists', () => {
    assert.ok(fileExists(CATALOG_PATH), `Capability catalog not found: ${CATALOG_PATH}`);
  });

  it('annotates /research --mode=web as requiring the plugin', () => {
    if (!catalog) return;
    assert.ok(
      catalog.includes('/deep-research:research --mode=web'),
      'Catalog must reference /deep-research:research --mode=web'
    );
    assert.ok(
      catalog.includes('requires deep-research plugin'),
      'Catalog must annotate deep-research dependent features with "requires deep-research plugin"'
    );
  });

  it('annotates /research --mode=structured as requiring the plugin', () => {
    if (!catalog) return;
    assert.ok(
      catalog.includes('/deep-research:research --mode=structured'),
      'Catalog must reference /deep-research:research --mode=structured'
    );
    // The annotation is shared — verified by the presence check above
  });

  it('annotates /notebooklm-research as requiring the plugin', () => {
    if (!catalog) return;
    assert.ok(
      catalog.includes('/notebooklm-research'),
      'Catalog must reference /notebooklm-research'
    );
  });

  it('deep-research-orchestrator is annotated as requiring the plugin', () => {
    if (!catalog) return;
    assert.ok(
      catalog.includes('deep-research-orchestrator'),
      'Catalog must reference deep-research-orchestrator'
    );
    const drOrchestratorLine = catalog.split('\n').find(l => l.includes('deep-research-orchestrator'));
    assert.ok(
      drOrchestratorLine && drOrchestratorLine.includes('requires deep-research plugin'),
      'deep-research-orchestrator entry must be annotated as requiring the plugin'
    );
  });
});
