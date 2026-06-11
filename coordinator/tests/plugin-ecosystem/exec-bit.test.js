// Exec-bit assertion — git index mode check for shebanged scripts.
//
// Purpose: Detect files committed at mode 100644 (no exec bit) when they
// carry a `#!` shebang line — regardless of file extension or directory.
// A shebanged script at 100644 silently never runs on fresh Mac/Linux clones
// (`[[ -x ]]` fails); Windows masks this because it ignores the git exec bit.
//
// Authoritative source: git index mode, NOT filesystem mode (Windows fs
// mode is unreliable). We run `git ls-files --stage` and check the mode
// field: 100755 = exec OK, 100644 = missing exec bit (test FAIL).
//
// Source-only scripts (sourced via `.` / `source`, never executed directly)
// are listed in SOURCE_ONLY_ALLOWLIST with a rationale. Default posture:
// all tracked files with a `#!` shebang are directly executable.
//
// Extension scope: ANY file whose first 2 bytes are `#!` — .sh, .py, .js,
// .bats, no-extension, etc. The previous .sh-only guard missed 24 .py +
// 15 no-extension + 8 .js + 1 .bats shebanged files (2026-06-11 audit).
//
// Directory scope: ALL tracked files under the plugin root — not just
// bin/ and hooks/scripts/. The previous two-dir guard missed lib/, tests/,
// setup/, .github/scripts/, dist/, and more.
//
// Spec backlink: docs/plans/2026-06-11-exec-bit-install-surface-completion.md
// § Chunk 3 (Patrik F0/F1 integrated).

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execSync } = require('child_process');
const { dirExists, getDirectoryMarketplaces, readJson } = require('./helpers/fs');

// ---------------------------------------------------------------------------
// Source-only allowlist
//
// Files listed here are deliberately committed without the exec bit because
// they are sourced via `. <script>` or `source <script>` rather than
// invoked as standalone executables. Each entry is a path relative to the
// plugin directory (e.g. "bin/common-lib.sh").
//
// Default: empty — all shebanged files in the plugin are asserted executable
// unless explicitly listed here.
// ---------------------------------------------------------------------------
const SOURCE_ONLY_ALLOWLIST = new Set([
  // Example (uncomment and add rationale when needed):
  // 'bin/common-lib.sh',  // sourced by other scripts, not a standalone entry point
]);

// ---------------------------------------------------------------------------
// Foreign-owned allowlist (repo-relative paths)
//
// These files are tracked in this meta-repo's git index but belong to
// copy_install / editable-sibling plugin mirrors whose SOURCE lives in another
// repo. The exec bit is owned and enforced by that source repo; fixing it here
// would be a reverse-drift edit (live ahead of source). When the source repo
// sets the exec bit, the live mirror refresh propagates it and the entry can be
// removed. Cross-repo memos sent 2026-06-01.
// ---------------------------------------------------------------------------
// Review: chunk-1 Finding 4 (FALSE POSITIVE — EM disposition: add comment, not fix).
// The prefix difference between the two entries below is INTENTIONAL, not a typo:
//   - 'plugins/claude-unreal-holodeck/...' (plural) — this file resolves within the
//     meta-repo (~/.claude) where the plugin mirror lives under 'plugins/'.
//   - 'plugin/project-rag-ue-addon/...' (singular) — this file resolves to the
//     project-rag-ue-addon source checkout (X:\project-rag-ue-addon) where the path
//     root is 'plugin/' (singular). Different git repo root → different path prefix.
// Both entries are correct. The test currently PASSES with these keys.
const FOREIGN_OWNED_ALLOWLIST = new Set([
  'plugins/claude-unreal-holodeck/holodeck-control/hooks/scripts/holodeck-awareness.sh', // holodeck-owned; memo -> holodeck-em
  'plugin/project-rag-ue-addon/hooks/scripts/check-addon-update-currency.sh',            // project-rag-ue-addon-owned (resolves to its source checkout); memo -> project-rag-ue-addon-em
]);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Find the git repository root containing `startDir`.
 * Returns null if `startDir` is not inside a git repo.
 */
function findGitRoot(startDir) {
  try {
    const result = execSync(`git -C "${startDir}" rev-parse --show-toplevel`, {
      stdio: 'pipe',
      timeout: 10000,
    });
    // Normalize to forward-slash (git outputs forward slashes on Windows too)
    return result.toString().trim().replace(/\\/g, '/');
  } catch {
    return null;
  }
}

/**
 * Return a Map from repo-relative path (forward-slash) to mode string
 * for all tracked files under `relDir` within `repoRoot`.
 *
 * We query the git index — not the filesystem — because Windows filesystem
 * mode bits are unreliable and do not reflect the exec bit stored in git.
 *
 * `relDir` may be empty string to query the entire repo root (git rejects
 * an empty pathspec — we substitute '.' in that case).
 */
function getGitModesForDir(repoRoot, relDir) {
  const modeMap = new Map();
  let output;
  try {
    // Query the full staged file list under this directory prefix.
    // Empty relDir means the plugin IS the repo root — use '.' to avoid the
    // "empty string is not a valid pathspec" fatal error from git.
    const cleaned = relDir ? relDir.replace(/\/$/, '') : '';
    const pathspec = cleaned ? cleaned + '/' : '.';
    output = execSync(`git -C "${repoRoot}" ls-files --stage -- "${pathspec}"`, {
      stdio: 'pipe',
      timeout: 15000,
    }).toString();
  } catch {
    // git not available or path not tracked — return empty map
    return modeMap;
  }

  for (const line of output.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    // Format: <mode> <sha> <stage>\t<path>
    const match = trimmed.match(/^(\d{6})\s+\S+\s+\d+\t(.+)$/);
    if (match) {
      const mode = match[1];
      const filePath = match[2].replace(/\\/g, '/');
      modeMap.set(filePath, mode);
    }
  }
  return modeMap;
}

/**
 * Return true if the on-disk file at `absPath` begins with `#!`.
 * Returns false for any read error (untracked-only, missing on disk, etc.).
 *
 * This mirrors the enumeration approach used by Chunk 1+2's bash scripts:
 *   head -c 2 "$p" | grep -q '^#!'
 */
function hasShebang(absPath) {
  try {
    const fd = fs.openSync(absPath, 'r');
    const buf = Buffer.alloc(2);
    const bytesRead = fs.readSync(fd, buf, 0, 2, 0);
    fs.closeSync(fd);
    return bytesRead === 2 && buf[0] === 0x23 && buf[1] === 0x21; // '#' + '!'
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

const marketplaces = getDirectoryMarketplaces();

describe('exec-bit: all shebanged scripts must be committed at mode 100755', () => {
  for (const marketplace of marketplaces) {
    const marketplaceDir = marketplace.source.path;
    const metadataPath = path.join(marketplaceDir, '.claude-plugin', 'marketplace.json');

    let plugins;
    try {
      const data = readJson(metadataPath);
      plugins = data.plugins || [];
    } catch {
      continue;
    }

    for (const plugin of plugins) {
      if (typeof plugin.source !== 'string') continue;
      const pluginDir = path.resolve(marketplaceDir, plugin.source);
      const pluginLabel = `${marketplace.name}/${plugin.name}`;

      // Find the git repo root for this plugin dir
      const repoRoot = findGitRoot(pluginDir);
      if (!repoRoot) {
        it(`[${pluginLabel}] — skip (not a git repo)`, () => {
          // Not a tracked git repo; skip silently.
        });
        continue;
      }

      const pluginDirNorm = pluginDir.replace(/\\/g, '/');
      const repoRootNorm = repoRoot.replace(/\\/g, '/');

      // Compute relative path from repo root to the plugin directory
      const relPluginDir = pluginDirNorm.startsWith(repoRootNorm)
        ? pluginDirNorm.slice(repoRootNorm.length).replace(/^\//, '')
        : null;

      if (!relPluginDir) {
        // Plugin dir is not inside the repo root — unusual, skip
        continue;
      }

      // Fetch git index modes for ALL tracked files under this plugin dir.
      // This is the widened scope: we query the entire plugin subtree, not
      // just bin/ and hooks/scripts/. Extension-agnostic: we then filter
      // by shebang presence rather than file extension.
      const modeMap = getGitModesForDir(repoRoot, relPluginDir);

      describe(`[${pluginLabel}]: all shebanged files must be 100755`, () => {
        for (const [relFromRepo, mode] of modeMap) {
          // Reconstruct the absolute path for shebang detection
          const absPath = path.join(repoRootNorm, relFromRepo.replace(/\//g, path.sep));

          // Only assert on files that have a #! shebang.
          // This is the extension-agnostic widening: .sh, .py, .js, .bats,
          // no-extension — all are candidates if the first 2 bytes are '#!'.
          if (!hasShebang(absPath)) continue;

          // Compute path relative to plugin dir for allowlist check
          const relFromPlugin = relFromRepo.startsWith(relPluginDir + '/')
            ? relFromRepo.slice(relPluginDir.length + 1)
            : relFromRepo;

          const fileName = path.basename(relFromRepo);

          it(`${fileName} (${relFromPlugin}) is committed at 100755`, () => {
            // Source-only allowlist: skip assertion for explicitly sourced scripts
            if (SOURCE_ONLY_ALLOWLIST.has(relFromPlugin)) return;

            // Foreign-owned allowlist: skip mirror files whose exec bit is
            // owned by another source repo (fixing here = reverse drift).
            if (FOREIGN_OWNED_ALLOWLIST.has(relFromRepo)) return;

            assert.strictEqual(
              mode,
              '100755',
              `${relFromRepo}: committed at mode ${mode} (want 100755). ` +
              `Fix with: git -C "${repoRoot}" update-index --chmod=+x "${relFromRepo}"`
            );
          });
        }
      });
    }
  }
});

// ---------------------------------------------------------------------------
// AC4 synthetic-fixture test
//
// Proves the widened test catches a `.py` shebanged file at mode 100644 under
// lib/, tests/, setup/, and .github/scripts/ — directories that were NOT
// covered by the original bin/ + hooks/scripts/ scope.
//
// Approach: build a minimal synthetic git repo that mimics the plugin
// marketplace structure, stage a shebanged .py at 100644 under each of the
// four directories, then run the detection logic directly and assert that
// the offending files are identified.
//
// This is a self-contained correctness proof for the widened scope, decoupled
// from the live plugin tree above.
// ---------------------------------------------------------------------------

describe('exec-bit AC4: synthetic fixture — widened scope catches .py shebang at 100644 in lib/, tests/, setup/, .github/scripts/', () => {
  let tmpDir = null;

  // Directories that were previously unguarded (not bin/ or hooks/scripts/)
  const UNGUARDED_DIRS = ['lib', 'tests', 'setup', '.github/scripts'];
  const SHEBANG_CONTENT = '#!/usr/bin/env python3\nprint("hello")\n';

  before(() => {
    // Create a fresh temp git repo that acts as the "plugin" source
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'exec-bit-ac4-'));
    execSync('git -c init.defaultBranch=main init -q', { cwd: tmpDir, stdio: 'pipe' });
    execSync('git config user.email "test@test.example"', { cwd: tmpDir, stdio: 'pipe' });
    execSync('git config user.name "Test"', { cwd: tmpDir, stdio: 'pipe' });

    // Create a shebanged .py file in each previously-unguarded directory
    for (const dir of UNGUARDED_DIRS) {
      const absDir = path.join(tmpDir, ...dir.split('/'));
      fs.mkdirSync(absDir, { recursive: true });
      const filePath = path.join(absDir, 'script.py');
      fs.writeFileSync(filePath, SHEBANG_CONTENT);
    }

    // Stage all files WITHOUT exec bit (mode 100644 — the drift scenario)
    execSync('git add .', { cwd: tmpDir, stdio: 'pipe' });
    // Explicitly ensure they are staged at 100644 (git add without -x leaves them at 100644)
    // Verify by checking no exec bit was auto-assigned
  });

  after(() => {
    if (tmpDir) {
      try {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      } catch {
        // best-effort cleanup
      }
    }
  });

  it('staged .py files at 100644 are detected by getGitModesForDir', () => {
    // Query the git index for the tmp repo — this exercises the same code path
    // the widened test uses for each plugin
    const modeMap = getGitModesForDir(tmpDir, '');
    const violations = [];

    for (const [relFromRepo, mode] of modeMap) {
      const absPath = path.join(tmpDir, relFromRepo.replace(/\//g, path.sep));
      if (!hasShebang(absPath)) continue;
      if (mode !== '100755') {
        violations.push({ relFromRepo, mode });
      }
    }

    // Should find exactly one violation per previously-unguarded directory
    assert.strictEqual(
      violations.length,
      UNGUARDED_DIRS.length,
      `Expected ${UNGUARDED_DIRS.length} shebanged 100644 violations (one per unguarded dir), ` +
      `got ${violations.length}: ${JSON.stringify(violations)}`
    );

    // Verify each expected directory's script.py is in the violation list
    for (const dir of UNGUARDED_DIRS) {
      const expectedPath = dir + '/script.py';
      const found = violations.some(v => v.relFromRepo === expectedPath);
      assert.ok(
        found,
        `Expected violation for '${expectedPath}' (a .py shebang at 100644 in a previously-unguarded dir) ` +
        `but it was not detected. Violations found: ${JSON.stringify(violations)}`
      );
    }
  });

  it('staged .py files at 100755 are NOT flagged as violations', () => {
    // Fix the exec bit on one file and confirm it drops out of violation list
    execSync('git update-index --chmod=+x -- lib/script.py', { cwd: tmpDir, stdio: 'pipe' });

    const modeMap = getGitModesForDir(tmpDir, '');
    const violations = [];

    for (const [relFromRepo, mode] of modeMap) {
      const absPath = path.join(tmpDir, relFromRepo.replace(/\//g, path.sep));
      if (!hasShebang(absPath)) continue;
      if (mode !== '100755') {
        violations.push({ relFromRepo, mode });
      }
    }

    // lib/script.py was fixed; the other 3 dirs still have violations
    const fixedInViolations = violations.some(v => v.relFromRepo === 'lib/script.py');
    assert.ok(
      !fixedInViolations,
      `lib/script.py was chmod +x in the index but still appears as a violation`
    );

    assert.strictEqual(
      violations.length,
      UNGUARDED_DIRS.length - 1,
      `After fixing lib/script.py, expected ${UNGUARDED_DIRS.length - 1} violations, ` +
      `got ${violations.length}: ${JSON.stringify(violations)}`
    );
  });
});
