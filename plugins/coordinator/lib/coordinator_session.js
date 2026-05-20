'use strict';
/**
 * coordinator_session.js — Node.js shim for coordinator session self-claim.
 *
 * Purpose: Allow Node writers (e.g. refresh-queries.js) to register touched
 * paths with the active coordinator session's touched.txt without reimplementing
 * the atomic-dedup-append logic. Shells out to the Bash lib via child_process
 * so there is one implementation per language and one source of truth for the
 * Windows + POSIX portability gotchas.
 *
 * Spec backlink: ~/.claude/plans/safe-commit-fixes.md § Phase 3b
 *
 * Self-claim contract (best-effort, never throws):
 *   - No coordinator session → stderr warning → return.
 *   - Exactly one live session → claim the path.
 *   - 2+ live sessions → stderr warning (ambiguous) → skip.
 *   - Any subprocess error → stderr warning → return.
 *   - claimPath() NEVER throws or causes a non-zero exit.
 *
 * Session resolution: shells out to cs_live_session_ids (lib line ~517) which
 * returns one sid per line with no headers. Do NOT use cs_active_sessions.
 */

const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

// ---------------------------------------------------------------------------
// Lib path resolution
// ---------------------------------------------------------------------------

/** @returns {string|null} absolute path to coordinator-session.sh, or null */
function _libPath() {
  // Prefer sibling in the same lib/ directory.
  const adjacent = path.join(__dirname, 'coordinator-session.sh');
  if (fs.existsSync(adjacent)) return adjacent;

  // Fallback: known install location.
  const fallback = path.join(
    process.env.HOME || process.env.USERPROFILE || '',
    '.claude', 'plugins', 'coordinator-claude', 'coordinator', 'lib', 'coordinator-session.sh'
  );
  if (fs.existsSync(fallback)) return fallback;

  return null;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Run a Bash one-liner and return stdout (trimmed), or null on error.
 * Never throws.
 *
 * @param {string} script
 * @returns {string|null}
 */
function _bashOneliner(script) {
  try {
    const out = execFileSync('bash', ['-c', script], {
      encoding: 'utf8',
      timeout: 10000,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return out.trim();
  } catch (_e) {
    return null;
  }
}

/**
 * Convert a native path to a POSIX form safe for Bash double-quoted strings.
 * On Windows + Git Bash, uses cygpath -u when available.
 *
 * @param {string} p
 * @returns {string}
 */
function _toShellPath(p) {
  // Normalise Windows backslashes to forward slashes first.
  let normalized = p.replace(/\\/g, '/');
  // Try cygpath for Git Bash on Windows (best-effort; ignored if unavailable).
  try {
    const out = execFileSync('cygpath', ['-u', p], {
      encoding: 'utf8',
      timeout: 5000,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    if (out && out.trim()) normalized = out.trim();
  } catch (_e) {
    // cygpath not available — use normalized form.
  }
  // Escape double-quotes and dollar signs for safe interpolation inside
  // bash -c "..." double-quoted strings (backslash handling above already
  // converted Windows separators; do quotes/dollars last).
  normalized = normalized.replace(/"/g, '\\"').replace(/\$/g, '\\$');
  return normalized;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Resolve live coordinator session IDs.
 *
 * @returns {string[]} array of session IDs (may be empty)
 */
function resolveLiveSessionIds() {
  const lib = _libPath();
  if (!lib) return [];
  const out = _bashOneliner(`source "${lib}" && cs_live_session_ids`);
  if (out === null || out === '') return [];
  return out.split('\n').map(l => l.trim()).filter(Boolean);
}

/**
 * Append entry to touched_file using cs_atomic_dedup_append from the Bash lib.
 *
 * Best-effort: logs to stderr and returns on any failure. Never throws.
 *
 * @param {string} touchedFile  Absolute path to the session's touched.txt.
 * @param {string} entry        Repo-relative path to record.
 */
function claimPath(touchedFile, entry) {
  const lib = _libPath();
  if (!lib) {
    process.stderr.write(
      `coordinator-session: lib not found — skipping self-claim for ${entry}\n`
    );
    return;
  }

  const tfShell = _toShellPath(touchedFile);
  const entryShell = _toShellPath(entry);
  const out = _bashOneliner(
    `source "${lib}" && cs_atomic_dedup_append "${tfShell}" "${entryShell}"`
  );
  if (out === null) {
    process.stderr.write(
      `coordinator-session: cs_atomic_dedup_append failed — skipping self-claim for ${entry}\n`
    );
  }
}

/**
 * Convenience wrapper: resolve the active session and claim writtenPath.
 *
 * Resolves session via cs_live_session_ids, then appends writtenPath to
 * the session's touched.txt. Best-effort; never throws.
 *
 * @param {string} writtenPath  Absolute or repo-relative path just written.
 */
function selfClaim(writtenPath) {
  const lib = _libPath();
  if (!lib) {
    process.stderr.write(
      `coordinator-session: lib not found — skipping self-claim for ${writtenPath}\n`
    );
    return;
  }

  const sids = resolveLiveSessionIds();

  if (sids.length === 0) {
    process.stderr.write(
      `coordinator-session: no active session found — skipping self-claim for ${writtenPath}\n`
    );
    return;
  }

  if (sids.length > 1) {
    process.stderr.write(
      `coordinator-session: ${sids.length} live sessions (ambiguous) — skipping self-claim for ${writtenPath}\n`
    );
    return;
  }

  const sid = sids[0];
  const sdirRaw = _bashOneliner(`source "${lib}" && _cs_session_dir "${sid}"`);
  if (!sdirRaw) {
    process.stderr.write(
      `coordinator-session: could not resolve session dir for ${sid} — skipping self-claim for ${writtenPath}\n`
    );
    return;
  }

  const touchedFile = sdirRaw + '/touched.txt';
  claimPath(touchedFile, writtenPath);
}

module.exports = { resolveLiveSessionIds, claimPath, selfClaim };
