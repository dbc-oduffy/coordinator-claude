// Exec-bit assertion — git index mode check for hook and bin scripts.
//
// Purpose: Detect .sh scripts committed at mode 100644 (no exec bit) in
// hooks/scripts/ and bin/ directories. A script at 100644 silently never
// runs on fresh Mac/Linux clones (`[[ -x ]]` fails); Windows masks this
// because it ignores the git exec bit entirely.
//
// Authoritative source: git index mode, NOT filesystem mode (Windows fs
// mode is unreliable). We run `git ls-files --stage` and check the mode
// field: 100755 = exec OK, 100644 = missing exec bit (test FAIL).
//
// Source-only scripts (sourced via `.` / `source`, never executed directly)
// are listed in SOURCE_ONLY_ALLOWLIST with a rationale. Default posture:
// all .sh files in hooks/scripts/ and bin/ are directly executable.
// Non-.sh files (.py, .ps1, etc.) are skipped — they have their own
// execution model.
//
// Spec backlink: exec-bit-assertion task (2026-06-01).

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
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
// Default: empty — all .sh files in hooks/scripts/ and bin/ are asserted
// executable unless explicitly listed here.
// ---------------------------------------------------------------------------
const SOURCE_ONLY_ALLOWLIST = new Set([
  // Example (uncomment and add rationale when needed):
  // 'bin/common-lib.sh',  // sourced by other scripts, not a standalone entry point
]);

// ---------------------------------------------------------------------------
// Foreign-owned allowlist (repo-relative paths)
//
// These .sh files are tracked in this meta-repo's git index but belong to
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
 * Walk `dir` recursively and collect all .sh file paths.
 * Returns paths relative to `baseDir` (for git ls-files queries).
 */
function collectShFiles(dir) {
  const fs = require('fs');
  const results = [];

  function walk(current) {
    let entries;
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile() && entry.name.endsWith('.sh')) {
        results.push(fullPath);
      }
    }
  }

  walk(dir);
  return results;
}

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
 * Fetch git index modes for files matching `relGlob` from `repoRoot`.
 * Returns a Map from normalized file path (forward-slash, relative to repoRoot)
 * to mode string (e.g. "100644" or "100755").
 *
 * We query the git index — not the filesystem — because Windows filesystem
 * mode bits are unreliable and do not reflect the exec bit stored in git.
 */
function getGitModes(repoRoot, relGlob) {
  const modeMap = new Map();
  let output;
  try {
    output = execSync(`git -C "${repoRoot}" ls-files --stage -- "${relGlob}"`, {
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

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

const marketplaces = getDirectoryMarketplaces();

describe('exec-bit: hook and bin scripts must be committed at mode 100755', () => {
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

      // Candidate directories: hooks/scripts/ and bin/
      const candidateDirs = [
        { relToPlugin: path.join('hooks', 'scripts'), label: 'hooks/scripts' },
        { relToPlugin: 'bin', label: 'bin' },
      ];

      for (const { relToPlugin, label } of candidateDirs) {
        const targetDir = path.join(pluginDir, relToPlugin);
        if (!dirExists(targetDir)) continue;

        // Collect .sh files on disk (for enumeration)
        const shFiles = collectShFiles(targetDir);
        if (shFiles.length === 0) continue;

        // Find the git repo root for this plugin dir
        const repoRoot = findGitRoot(pluginDir);
        if (!repoRoot) {
          it(`[${pluginLabel}] ${label}/ — skip (not a git repo)`, () => {
            // Not a tracked git repo; skip silently.
          });
          continue;
        }

        // Build the glob relative to the git repo root that covers this dir
        // We need the plugin dir relative to the repo root
        const pluginDirNorm = pluginDir.replace(/\\/g, '/');
        const repoRootNorm = repoRoot.replace(/\\/g, '/');
        // Compute relative path from repo root to the target directory
        const relTargetDir = pluginDirNorm.startsWith(repoRootNorm)
          ? pluginDirNorm.slice(repoRootNorm.length).replace(/^\//, '') + '/' + relToPlugin.replace(/\\/g, '/')
          : null;

        if (!relTargetDir) {
          // Plugin dir is not inside the repo root — unusual, skip
          continue;
        }

        // Fetch git index modes for all tracked files under this dir
        const modeMap = getGitModes(repoRoot, relTargetDir + '/');

        describe(`[${pluginLabel}] ${label}/: all .sh scripts must be 100755`, () => {
          for (const absFilePath of shFiles) {
            const normalizedAbs = absFilePath.replace(/\\/g, '/');

            // Compute path relative to repo root for mode map lookup
            const relFromRepo = normalizedAbs.startsWith(repoRootNorm)
              ? normalizedAbs.slice(repoRootNorm.length).replace(/^\//, '')
              : null;

            // Compute path relative to plugin dir for allowlist check
            const relFromPlugin = normalizedAbs.startsWith(pluginDirNorm)
              ? normalizedAbs.slice(pluginDirNorm.length).replace(/^\//, '').replace(/\\/g, '/')
              : path.relative(pluginDir, absFilePath).replace(/\\/g, '/');

            const fileName = path.basename(absFilePath);

            it(`${fileName} (${relFromPlugin}) is committed at 100755`, () => {
              // Source-only allowlist: skip assertion for explicitly sourced scripts
              if (SOURCE_ONLY_ALLOWLIST.has(relFromPlugin)) return;

              // Foreign-owned allowlist: skip mirror files whose exec bit is
              // owned by another source repo (fixing here = reverse drift).
              if (relFromRepo && FOREIGN_OWNED_ALLOWLIST.has(relFromRepo)) return;

              if (!relFromRepo) {
                // Cannot compute relative path — file outside repo root, skip
                return;
              }

              const mode = modeMap.get(relFromRepo);

              if (mode === undefined) {
                // File exists on disk but is NOT tracked in git — skip assertion.
                // (Untracked files have no index mode to check; a separate test
                // could enforce tracking, but that is out of scope here.)
                return;
              }

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
  }
});
