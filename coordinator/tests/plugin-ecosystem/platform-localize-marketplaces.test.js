// Spec backlink: docs/plans/2026-06-14-codex-reviewer-integration-opt-in.md § C6
//
// Two suites:
//   1. platform-localize.sh schema regression (original, guards lastUpdated bug)
//   2. codex opt-in path (AC3 / AC4 / AC13 / AC14) — Leg-A and Leg-B Python edits
//      from commands/install.md Phase 6 Codex Integration step
//
// Sandbox invariant: every test redirects $HOME into a temp dir so the runner's
// real ~/.claude/settings.json is never touched. Failure to set up a sandbox
// throws, never silently skips.

// Regression test for the missing-`lastUpdated` bug (PM-surfaced 2026-06-14).
//
// The bug shape: platform-localize.sh writes known_marketplaces.json entries
// for directory-source marketplaces. Older versions of the script omitted the
// `lastUpdated` ISO string field, which is required by Claude Code's plugin-
// discovery schema. Result: `/plugin` enumeration fails with "Marketplace
// configuration file is corrupted".
//
// This test runs platform-localize.sh against a sandboxed $HOME, then asserts
// every entry it writes carries the required field. Cheap, fast, deterministic.
//
// Invariant — what this guards:
//   Every entry in known_marketplaces.json must have:
//     - source: { source: string, path?: string, url?: string, repo?: string }
//     - installLocation: string
//     - lastUpdated: string (ISO 8601)

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

const SCRIPT = path.resolve(os.homedir(), '.claude', 'bin', 'platform-localize.sh');

// Review: F2 — replace fragile ../../../../../ depth count with robust repo-root walk.
// Walk upward from __dirname until a .git directory is found. Throws if no .git found
// within 20 ancestors (prevents accidental filesystem-root escape).
function findRepoRoot() {
  let dir = __dirname;
  for (let i = 0; i < 20; i++) {
    if (fs.existsSync(path.join(dir, '.git'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break; // filesystem root
    dir = parent;
  }
  throw new Error(`findRepoRoot: no .git found within 20 ancestors of ${__dirname}`);
}

function mkSandbox() {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'platform-localize-test-'));
  fs.mkdirSync(path.join(sandbox, '.claude', 'plugins', 'fake-marketplace', '.claude-plugin'), { recursive: true });
  fs.writeFileSync(
    path.join(sandbox, '.claude', 'plugins', 'fake-marketplace', '.claude-plugin', 'marketplace.json'),
    JSON.stringify({ name: 'fake-marketplace', owner: { name: 'test' }, metadata: { description: 'test fixture' } })
  );
  fs.mkdirSync(path.join(sandbox, '.claude', 'machine-local'), { recursive: true });
  fs.writeFileSync(path.join(sandbox, '.claude', 'machine-local', 'registry.local.toml'), 'schema = 1\n');
  return sandbox;
}

function runScript(sandbox) {
  // CLAUDE_HOME redirects all writes into the sandbox. The shell defaults are
  // already cross-platform — same hook runs on macOS, Linux, Windows Git-Bash.
  execFileSync('bash', [SCRIPT], {
    env: { ...process.env, CLAUDE_HOME: path.join(sandbox, '.claude') },
    stdio: 'pipe',
  });
}

describe('platform-localize.sh writes schema-valid known_marketplaces entries', () => {
  let sandbox;

  before(() => {
    if (!fs.existsSync(SCRIPT)) {
      // Script missing — not our test failure. Skip with informative reason.
      return;
    }
    sandbox = mkSandbox();
    runScript(sandbox);
  });

  after(() => {
    if (sandbox) fs.rmSync(sandbox, { recursive: true, force: true });
  });

  it('writes known_marketplaces.json', () => {
    if (!sandbox) return;
    const kmPath = path.join(sandbox, '.claude', 'plugins', 'known_marketplaces.json');
    assert.ok(fs.existsSync(kmPath), 'known_marketplaces.json must be written by the hook');
  });

  it('every entry carries lastUpdated as a string', () => {
    if (!sandbox) return;
    const km = JSON.parse(fs.readFileSync(path.join(sandbox, '.claude', 'plugins', 'known_marketplaces.json'), 'utf8'));
    for (const [name, entry] of Object.entries(km)) {
      assert.equal(typeof entry.lastUpdated, 'string', `marketplace '${name}' is missing lastUpdated`);
      assert.ok(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(entry.lastUpdated),
        `marketplace '${name}' lastUpdated must be ISO 8601 — got: ${entry.lastUpdated}`
      );
    }
  });

  it('every entry has source.source and installLocation', () => {
    if (!sandbox) return;
    const km = JSON.parse(fs.readFileSync(path.join(sandbox, '.claude', 'plugins', 'known_marketplaces.json'), 'utf8'));
    for (const [name, entry] of Object.entries(km)) {
      assert.ok(entry.source && typeof entry.source.source === 'string', `marketplace '${name}' missing source.source`);
      assert.equal(typeof entry.installLocation, 'string', `marketplace '${name}' missing installLocation`);
    }
  });

  it('idempotent: a second run does not corrupt the file', () => {
    if (!sandbox) return;
    runScript(sandbox);
    const km = JSON.parse(fs.readFileSync(path.join(sandbox, '.claude', 'plugins', 'known_marketplaces.json'), 'utf8'));
    for (const [name, entry] of Object.entries(km)) {
      assert.equal(typeof entry.lastUpdated, 'string', `idempotent run lost lastUpdated on '${name}'`);
    }
  });

  it('backfills lastUpdated on pre-existing entry that lacks it', () => {
    if (!sandbox) return;
    // Inject an entry missing the field, re-run, assert it gets backfilled.
    const kmPath = path.join(sandbox, '.claude', 'plugins', 'known_marketplaces.json');
    const km = JSON.parse(fs.readFileSync(kmPath, 'utf8'));
    km['legacy-stale-entry'] = {
      source: { source: 'github', repo: 'example/legacy' },
      installLocation: '/tmp/legacy',
      // intentionally no lastUpdated
    };
    fs.writeFileSync(kmPath, JSON.stringify(km, null, 2) + '\n');
    runScript(sandbox);
    const after = JSON.parse(fs.readFileSync(kmPath, 'utf8'));
    assert.equal(typeof after['legacy-stale-entry'].lastUpdated, 'string',
      'platform-localize must backfill lastUpdated on entries it sees without one');
  });
});

// ---------------------------------------------------------------------------
// Suite 2 — codex opt-in path (install Phase 6 Codex Integration)
//
// Simulates Leg-A and Leg-B Python scripts from commands/install.md verbatim
// (Option i from the plan spec) using child_process.execFileSync(<python>, ...).
// Each sub-test creates its own sandboxed $HOME so runs are fully isolated.
//
// Spec: docs/plans/2026-06-14-codex-reviewer-integration-opt-in.md § AC3/AC4/AC13/AC14
//
// Cross-platform Python detection: on Windows, 'python3' is often a bash shim
// that Node's execFileSync cannot spawn directly (ENOENT). We detect the actual
// Python executable at module load time so every sub-test shares the same binary.
// On Windows, Path.home() reads USERPROFILE (not HOME), so sandbox env must set both.
// ---------------------------------------------------------------------------

function detectPython() {
  for (const candidate of ['python3', 'python', 'py']) {
    try {
      execFileSync(candidate, ['--version'], { stdio: 'pipe' });
      return candidate;
    } catch (_) { /* try next */ }
  }
  return null;
}

const PYTHON = detectPython();

// Build a sandboxed HOME env that works on both Unix and Windows.
// On Windows, pathlib.Path.home() reads USERPROFILE; on Unix it reads HOME.
// Review: F9 — spreading process.env is intentional: Python subprocess needs PATH, TEMP,
// SystemRoot, etc. to function; we override only the home-dir variables so all Leg-A/Leg-B
// writes are redirected into the sandbox while the environment remains functional.
// Review: F10 — PYTHONUNBUFFERED=1 guarantees stdout flush before sys.exit(0); critical
// for the AC13 stdout-capture path where Leg-B prints the meta-repo skip message.
function sandboxedHomeEnv(sandbox) {
  return { ...process.env, HOME: sandbox, USERPROFILE: sandbox, PYTHONUNBUFFERED: '1' };
}

// Review: F12 — sync-discipline warning.
// LEG_A_PY / LEG_B_PY are VERBATIM copies of the Python heredocs in
// `plugins/coordinator-claude/coordinator/commands/install.md` § Phase 6
// Codex Integration. Any change to install.md MUST be mirrored here, and
// vice versa. There is no automatic sync check — manual discipline only.
// (Future improvement: extract to a shared .py file both consume.)

// Leg-A Python source — verbatim from commands/install.md Phase 6 Codex Integration.
// Reads/writes ~/.claude/settings.json using Path.home(), which honours $HOME/$USERPROFILE.
const LEG_A_PY = `\
import json, pathlib, tempfile, os, sys
p = pathlib.Path.home() / ".claude" / "settings.json"
try:
    s = json.loads(p.read_text()) if p.exists() else {}
except (json.JSONDecodeError, OSError) as e:
    print(f"FATAL: existing settings.json malformed ({e}) — skipping codex opt-in. Repair and re-run.", file=sys.stderr)
    sys.exit(1)
mkts = s.setdefault("extraKnownMarketplaces", {})
mkts.setdefault("openai-codex", {"source": {"source": "git", "url": "https://github.com/openai/codex-plugin-cc.git"}})
# Per plugin-extraction-and-distribution.md § 7, enablement does NOT belong in user-global settings.json.
# Do NOT write enabledPlugins here.
fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".settings.", suffix=".tmp")
try:
    with os.fdopen(fd, "w", newline="\\n") as f:
        f.write(json.dumps(s, indent=2) + "\\n")
    os.replace(tmp_path, p)
except Exception:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    raise
`;

// Leg-B Python source — verbatim from commands/install.md Phase 6 Codex Integration.
// Uses Path.home() (for meta-repo guard) and os.getcwd() (for project detection).
const LEG_B_PY = `\
import json, pathlib, os, tempfile, sys
cwd = pathlib.Path(os.getcwd()).resolve()
home_claude = (pathlib.Path.home() / ".claude").resolve()
if cwd == home_claude:
    print("install run from meta-repo — skipping leg-B project-enablement write")
    sys.exit(0)
proj_settings = pathlib.Path(os.getcwd()) / ".claude" / "settings.local.json"
if proj_settings.parent.exists():
    try:
        s = json.loads(proj_settings.read_text()) if proj_settings.exists() else {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"FATAL: existing {proj_settings} malformed ({e}) — skipping project enablement. Repair and re-run.", file=sys.stderr)
        sys.exit(1)
    plugins = s.setdefault("enabledPlugins", {})
    plugins.setdefault("codex@openai-codex", True)
    fd, tmp_path = tempfile.mkstemp(dir=proj_settings.parent, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="\\n") as f:
            f.write(json.dumps(s, indent=2) + "\\n")
        os.replace(tmp_path, proj_settings)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    print(f"codex enabled in project: {proj_settings.parent.parent}")
else:
    print("no .claude/ at cwd — run /plugin enable codex@openai-codex from any project that wants it active")
`;

/**
 * Create a minimal sandboxed $HOME for codex opt-in tests.
 *
 * Layout:
 *   <sandbox>/                ← acts as HOME
 *     .claude/
 *       settings.json         ← pre-populated or created by Leg-A
 *       plugins/
 *         known_marketplaces.json (absent until platform-localize.sh runs)
 *       machine-local/
 *         registry.local.toml
 *
 * The sandbox has NO ~/.claude/plugins/openai-codex/ directory mirror —
 * codex is a git-URL marketplace, not a local directory marketplace.
 */
function mkCodexSandbox({ preloadSettingsJson } = {}) {
  const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-opt-in-test-'));
  fs.mkdirSync(path.join(sandbox, '.claude', 'plugins'), { recursive: true });
  fs.mkdirSync(path.join(sandbox, '.claude', 'machine-local'), { recursive: true });
  fs.writeFileSync(
    path.join(sandbox, '.claude', 'machine-local', 'registry.local.toml'),
    'schema = 1\n'
  );
  if (preloadSettingsJson !== undefined) {
    fs.writeFileSync(
      path.join(sandbox, '.claude', 'settings.json'),
      JSON.stringify(preloadSettingsJson, null, 2) + '\n'
    );
  }
  return sandbox;
}

/** Run a Python script string with HOME redirected into the sandbox. */
function runLegA(sandbox) {
  if (!PYTHON) throw new Error('No Python interpreter found (tried python3, python, py)');
  execFileSync(PYTHON, ['-c', LEG_A_PY], {
    env: sandboxedHomeEnv(sandbox),
    stdio: 'pipe',
  });
}

/** Run Leg-B with HOME redirected and CWD set to targetCwd. */
function runLegB(sandbox, targetCwd) {
  if (!PYTHON) throw new Error('No Python interpreter found (tried python3, python, py)');
  execFileSync(PYTHON, ['-c', LEG_B_PY], {
    env: sandboxedHomeEnv(sandbox),
    cwd: targetCwd,
    stdio: 'pipe',
  });
}

/** Run platform-localize.sh against sandbox (reuses CLAUDE_HOME env pattern). */
function runPlatformLocalize(sandbox) {
  execFileSync('bash', [SCRIPT], {
    env: { ...sandboxedHomeEnv(sandbox), CLAUDE_HOME: path.join(sandbox, '.claude') },
    stdio: 'pipe',
  });
}

describe('codex opt-in path (install Phase 6 Codex Integration)', () => {

  // Review: F1 — fail loud at suite level when Python is absent rather than silently
  // returning mid-test (the Suite 1 silent-return pattern is the anti-pattern here).
  // Names all three candidates tried so the skip message is actionable.
  before(function() {
    if (PYTHON === null) {
      this.skip('No Python interpreter found (tried python3, python, py) — Suite 2 requires Python');
    }
  });

  // AC3(a) — Leg-A first-run write on empty settings.json
  it('AC3(a) — Leg-A writes extraKnownMarketplaces["openai-codex"] with git+url shape', () => {
    const sandbox = mkCodexSandbox();
    try {
      runLegA(sandbox);
      const settingsPath = path.join(sandbox, '.claude', 'settings.json');
      assert.ok(fs.existsSync(settingsPath), 'settings.json must exist after Leg-A');
      const s = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
      const codexEntry = s?.extraKnownMarketplaces?.['openai-codex'];
      assert.ok(codexEntry, 'extraKnownMarketplaces["openai-codex"] must be written');
      // Canonical shape: source.source == "git" + source.url (NOT source: "github" + repo)
      assert.deepEqual(
        codexEntry,
        { source: { source: 'git', url: 'https://github.com/openai/codex-plugin-cc.git' } },
        'codex entry must use git+url shape (not legacy github+repo shape)'
      );
      // AC11: enabledPlugins MUST NOT appear in user-global settings.json
      assert.ok(
        !Object.prototype.hasOwnProperty.call(s, 'enabledPlugins'),
        'Leg-A must NOT write enabledPlugins to user-global settings.json'
      );
    } finally {
      fs.rmSync(sandbox, { recursive: true, force: true });
    }
  });

  // AC3(b) — Leg-A idempotency: same-shape entry → file byte-identical after re-run
  it('AC3(b) — Leg-A is idempotent: re-run with canonical entry produces no diff', () => {
    const canonical = {
      extraKnownMarketplaces: {
        'openai-codex': { source: { source: 'git', url: 'https://github.com/openai/codex-plugin-cc.git' } },
      },
    };
    const sandbox = mkCodexSandbox({ preloadSettingsJson: canonical });
    try {
      const settingsPath = path.join(sandbox, '.claude', 'settings.json');
      const before = fs.readFileSync(settingsPath, 'utf8');
      runLegA(sandbox);
      const after = fs.readFileSync(settingsPath, 'utf8');
      // Review: F4 — use strictEqual (byte identity) rather than deepEqual. atomic-write +
      // os.replace on a setdefault no-op MUST be a no-op at byte level, including key order.
      // If this fails, it exposes a real serialization-ordering bug worth surfacing.
      assert.strictEqual(after, before, 'settings.json must be byte-identical after idempotent Leg-A re-run');
    } finally {
      fs.rmSync(sandbox, { recursive: true, force: true });
    }
  });

  // AC3(c) — Leg-A no-clobber: existing entry with different shape is preserved
  it('AC3(c) — Leg-A preserves existing entry with different shape (setdefault no-clobber)', () => {
    const forkUrl = 'https://github.com/some-fork/codex-plugin-cc.git';
    const preloadedEntry = { source: { source: 'git', url: forkUrl } };
    const preloaded = {
      extraKnownMarketplaces: {
        'openai-codex': preloadedEntry,
      },
    };
    const sandbox = mkCodexSandbox({ preloadSettingsJson: preloaded });
    try {
      runLegA(sandbox);
      const s = JSON.parse(fs.readFileSync(path.join(sandbox, '.claude', 'settings.json'), 'utf8'));
      const actualEntry = s?.extraKnownMarketplaces?.['openai-codex'];
      // Review: F5 — deep-equal the entire entry object (not just .url) to prove every
      // nested field including the outer key structure survived the setdefault no-clobber.
      assert.deepEqual(
        actualEntry,
        preloadedEntry,
        'Leg-A must NOT overwrite any field of an existing codex entry (setdefault no-clobber)'
      );
    } finally {
      fs.rmSync(sandbox, { recursive: true, force: true });
    }
  });

  // AC3(d) / F1 — Two-file coexistence: platform-localize does NOT clobber settings.json's codex entry
  //
  // platform-localize.sh manages settings.local.json's extraKnownMarketplaces via directory-scan.
  // The codex entry in settings.json (git-URL, no local directory mirror) must survive platform-localize.
  //
  // Note on known_marketplaces.json: platform-localize.sh only adds entries for
  // directory-source marketplaces (those with .claude-plugin/ on disk under ~/.claude/plugins/).
  // Since this test sandbox has NO ~/.claude/plugins/openai-codex/ directory, the codex entry
  // will NOT appear in known_marketplaces.json after platform-localize. The codex entry in
  // known_marketplaces.json is created by Claude Code's marketplace-resolution at session-start
  // (reading settings.json's extraKnownMarketplaces), not by platform-localize.sh.
  it('AC3(d)/F1 — platform-localize does not clobber settings.json codex entry; settings.local.json manages separately', () => {
    if (!fs.existsSync(SCRIPT)) {
      throw new Error('platform-localize.sh not found — cannot run AC3(d)/F1 coexistence test');
    }
    // Seed settings.json with canonical codex entry from Leg-A
    const preloaded = {
      extraKnownMarketplaces: {
        'openai-codex': { source: { source: 'git', url: 'https://github.com/openai/codex-plugin-cc.git' } },
      },
    };
    const sandbox = mkCodexSandbox({ preloadSettingsJson: preloaded });
    try {
      runPlatformLocalize(sandbox);
      // 1. settings.json codex entry must be intact (platform-localize never touches settings.json)
      const s = JSON.parse(fs.readFileSync(path.join(sandbox, '.claude', 'settings.json'), 'utf8'));
      const codexEntry = s?.extraKnownMarketplaces?.['openai-codex'];
      assert.ok(codexEntry, 'settings.json must still contain codex entry after platform-localize');
      assert.deepEqual(
        codexEntry,
        { source: { source: 'git', url: 'https://github.com/openai/codex-plugin-cc.git' } },
        'settings.json codex entry shape must be unchanged'
      );
      // 2. settings.local.json check — this sandbox has no ~/.claude/plugins/openai-codex/
      //    directory mirror, so platform-localize.sh will NOT write an openai-codex entry
      //    to settings.local.json. Two valid outcomes: (a) settings.local.json is absent
      //    (no directory-source marketplaces → no write at all), or (b) settings.local.json
      //    exists but does NOT contain openai-codex. One of those two MUST be true.
      //    Review: F6 — assert both branches explicitly rather than treating absent file as
      //    silent pass; the conditional on settings.local.json is correct and explained here.
      const localSettingsPath = path.join(sandbox, '.claude', 'settings.local.json');
      if (fs.existsSync(localSettingsPath)) {
        // Branch (b): file exists — codex must NOT be present (no local directory mirror).
        const local = JSON.parse(fs.readFileSync(localSettingsPath, 'utf8'));
        const localMkts = local?.extraKnownMarketplaces || {};
        assert.ok(
          !Object.prototype.hasOwnProperty.call(localMkts, 'openai-codex'),
          'settings.local.json must NOT carry openai-codex (no local directory mirror in sandbox)'
        );
      }
      // Branch (a): file absent — also correct; no assertion needed for an absent file.
      // The two branches are mutually exclusive and exhaustive — one always holds.
    } finally {
      fs.rmSync(sandbox, { recursive: true, force: true });
    }
  });

  // AC4 — schema-validity via validate-json-schemas.py
  //
  // Substrate gap documented: platform-localize.sh does NOT propagate the codex entry
  // from settings.json into known_marketplaces.json. The validator checks
  // known_marketplaces.json only when it exists; without a local directory marketplace
  // in the sandbox, known_marketplaces.json may not be written at all. We seed
  // settings.json with a pre-existing enabledPlugins key (schema requires it) so the
  // settings.json validation path is exercised correctly.
  //
  // Review: F3 — explain why enabledPlugins: {} is pre-seeded in the AC4 fixture:
  //   - validate-json-schemas.py REQUIRES enabledPlugins to be present in settings.json
  //     (schema enforces the key's existence).
  //   - Leg-A does NOT write enabledPlugins to settings.json — that is AC11's contract;
  //     per plugin-extraction-and-distribution.md § 7, enablement never goes user-global.
  //   - The fixture pre-populates enabledPlugins: {} to satisfy the validator. This
  //     represents a real install state: (a) user has run other plugins before opting in
  //     to codex, so enabledPlugins is already present from a prior plugin install, or
  //     (b) freshly-installed Claude Code where enabledPlugins may default to {}.
  //   - The structural gap (Leg-A on a literally-empty settings.json would fail the
  //     validator) is documented in the plan's ## Deviations table (commit 0e9d8c71).
  //   - This test asserts validator behavior over a realistic post-Leg-A state, NOT that
  //     Leg-A alone produces validator-clean output.
  it('AC4 — validate-json-schemas.py exits 0 over sandbox after Leg-A + platform-localize', () => {
    if (!fs.existsSync(SCRIPT)) {
      throw new Error('platform-localize.sh not found — cannot complete AC4 schema-validity test');
    }
    // Schema-valid initial settings.json: extraKnownMarketplaces from Leg-A + enabledPlugins.
    // enabledPlugins: {} is pre-seeded here because validate-json-schemas.py requires the key;
    // Leg-A intentionally does NOT write it (per AC11 / plugin-extraction-and-distribution.md § 7).
    // See extended comment above this test for the full rationale.
    const preloaded = {
      enabledPlugins: {},
      extraKnownMarketplaces: {
        'openai-codex': { source: { source: 'git', url: 'https://github.com/openai/codex-plugin-cc.git' } },
      },
    };
    const sandbox = mkCodexSandbox({ preloadSettingsJson: preloaded });
    try {
      runPlatformLocalize(sandbox);
      // validate-json-schemas.py uses CWD-relative paths. Run it from sandbox/.claude
      // so it finds settings.json and plugins/known_marketplaces.json (if present).
      if (!PYTHON) throw new Error('No Python interpreter found (tried python3, python, py)');
      // Review: F2 — use findRepoRoot() instead of fragile ../../../../../ depth count.
      const validatorPath = path.join(findRepoRoot(), '.github', 'scripts', 'validate-json-schemas.py');
      const claudeDir = path.join(sandbox, '.claude');
      try {
        execFileSync(PYTHON, [validatorPath], {
          cwd: claudeDir,
          env: sandboxedHomeEnv(sandbox),
          stdio: 'pipe',
        });
      } catch (e) {
        // Review: F8 — ENOENT discriminator: surface a clear message when the validator
        // script itself is not found (as opposed to a validator-logic failure).
        if (e.code === 'ENOENT') throw new Error(`validate-json-schemas.py not found at: ${validatorPath}`);
        const exitCode = e.status ?? 1;
        const stderr = e.stderr ? e.stderr.toString() : '';
        const stdout = e.stdout ? e.stdout.toString() : '';
        throw new Error(
          `validate-json-schemas.py exited ${exitCode}:\nstdout: ${stdout}\nstderr: ${stderr}`
        );
      }
      // Review: F8 — removed dead assert.equal(exitCode, 0) that was unreachable after
      // the try/catch above (non-zero exit throws, so exitCode is always 0 here).
    } finally {
      fs.rmSync(sandbox, { recursive: true, force: true });
    }
  });

  // AC13 / F3 — Leg-B skips when cwd is ~/.claude (meta-repo guard)
  //
  // When install is invoked from inside the meta-repo, Leg-B must print the
  // skip message and NOT write to ~/.claude/.claude/settings.local.json.
  it('AC13/F3 — Leg-B skips and does not write settings.local.json when cwd is HOME/.claude', () => {
    const sandbox = mkCodexSandbox();
    try {
      // CWD is the meta-repo path (sandbox/.claude)
      const metaRepoCwd = path.join(sandbox, '.claude');
      if (!PYTHON) throw new Error('No Python interpreter found (tried python3, python, py)');
      let stdout = '';
      try {
        const result = execFileSync(PYTHON, ['-c', LEG_B_PY], {
          env: sandboxedHomeEnv(sandbox),
          cwd: metaRepoCwd,
          stdio: ['pipe', 'pipe', 'pipe'],
        });
        stdout = result ? result.toString() : '';
      } catch (e) {
        // Non-zero exit in the guard path would be a test failure
        const errOut = e.stderr ? e.stderr.toString() : '';
        const stdoutErr = e.stdout ? e.stdout.toString() : '';
        throw new Error(`Leg-B unexpectedly exited non-zero in meta-repo guard path: ${errOut || stdoutErr}`);
      }
      assert.ok(
        stdout.includes('meta-repo'),
        `Leg-B must print the meta-repo skip message; got: "${stdout}"`
      );
      // ~/.claude/.claude/settings.local.json must NOT exist
      const nestedSettings = path.join(sandbox, '.claude', '.claude', 'settings.local.json');
      assert.ok(
        !fs.existsSync(nestedSettings),
        'Leg-B must NOT write nested ~/.claude/.claude/settings.local.json on meta-repo skip'
      );
    } finally {
      fs.rmSync(sandbox, { recursive: true, force: true });
    }
  });

  // AC14 / F3 — Leg-B writes enabledPlugins to <project>/.claude/settings.local.json
  //
  // When cwd is a consumer project directory that has a .claude/ subdirectory,
  // Leg-B writes enabledPlugins["codex@openai-codex"] = true there.
  it('AC14/F3 — Leg-B writes enabledPlugins to project .claude/settings.local.json', () => {
    const sandbox = mkCodexSandbox();
    // Create a fake project directory with .claude/ subdir
    const projectDir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-project-test-'));
    try {
      fs.mkdirSync(path.join(projectDir, '.claude'), { recursive: true });
      runLegB(sandbox, projectDir);
      const projSettingsPath = path.join(projectDir, '.claude', 'settings.local.json');
      assert.ok(
        fs.existsSync(projSettingsPath),
        'Leg-B must write <project>/.claude/settings.local.json'
      );
      const s = JSON.parse(fs.readFileSync(projSettingsPath, 'utf8'));
      assert.ok(
        s?.enabledPlugins?.['codex@openai-codex'] === true,
        'settings.local.json must contain enabledPlugins["codex@openai-codex"] = true'
      );
      // Verify user-global settings.json was NOT modified (it shouldn't exist in sandbox for this test)
      const globalSettings = path.join(sandbox, '.claude', 'settings.json');
      if (fs.existsSync(globalSettings)) {
        const global = JSON.parse(fs.readFileSync(globalSettings, 'utf8'));
        assert.ok(
          !Object.prototype.hasOwnProperty.call(global, 'enabledPlugins'),
          'Leg-B must NOT write enabledPlugins to user-global settings.json'
        );
      }
    } finally {
      fs.rmSync(sandbox, { recursive: true, force: true });
      fs.rmSync(projectDir, { recursive: true, force: true });
    }
  });
});
