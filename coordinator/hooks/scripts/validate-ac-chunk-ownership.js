'use strict';
/**
 * validate-ac-chunk-ownership.js — PreToolUse hook that surfaces AC Test-cell
 * path-ownership gaps to the agent before a Write/Edit/MultiEdit lands on a plan file.
 *
 * Spec backlink: docs/plans/2026-06-15-ac-chunk-owner-coverage-validator.md § C1
 *
 * For every gate-bound AC row whose typed-prefix Test cell contains a file path,
 * the hook checks that at least one chunk's `write-files` cell in the ## Dispatch
 * Ledger table owns that path. Ownership is defined per the plan § Design match function:
 *   1. Exact match with a write-files entry.
 *   2. The write-files entry is a directory pathspec (trailing `/` or no extension) that prefixes the path.
 *   3. The write-files entry is a glob pattern (contains `*`, `?`, or `[`) that matches under POSIX glob semantics.
 *
 * Default mode is WARN: emits the violation as additionalContext so the agent sees
 * the ownership gap but the write still proceeds. Strict mode
 * (COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT=1) restores the deny behavior.
 *
 * Reads Claude PreToolUse JSON from stdin. Exits 0 in all cases (hook contract).
 *
 * Negative-spec: this hook NEVER exits non-zero. Infra failures (file read, parse
 * failure, ledger absent, AC section absent) are silently allowed — never block on
 * infra. Mirrors validate-ac-grammar.js lines 14-17.
 *
 * Design-as-offers: chunk-ownership gap is a misdirection at plan-authoring time
 * (the author may not have filled in the ledger yet) — additionalContext offer-shape
 * is correct per eager-agent-calibration.md.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ---------------------------------------------------------------------------
// Helpers — inlined for offline-safety (mirrors validate-ac-grammar.js)
// ---------------------------------------------------------------------------

/**
 * Resolve the git repo root by running `git rev-parse --show-toplevel` in cwd.
 * Falls back to cwd if the command fails or we're not in a git repo.
 */
function resolveRepoRoot(cwd) {
  try {
    const result = execSync('git rev-parse --show-toplevel', {
      cwd,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 3000,
    });
    return result.trim();
  } catch {
    return cwd;
  }
}

/**
 * Convert an absolute file_path to a repo-relative path using forward slashes.
 * Returns null if the path is not under repoRoot.
 */
function toRepoRelative(absPath, repoRoot) {
  const normalAbs = absPath.replace(/\\/g, '/');
  const normalRoot = repoRoot.replace(/\\/g, '/');
  if (!normalAbs.startsWith(normalRoot)) return null;
  return normalAbs.slice(normalRoot.length).replace(/^\//, '');
}

/**
 * Apply a single old_string->new_string replacement to content.
 * Returns { result: string, matched: boolean }.
 */
function applyEdit(content, oldString, newString) {
  const idx = content.indexOf(oldString);
  if (idx === -1) return { result: content, matched: false };
  return {
    result: content.slice(0, idx) + newString + content.slice(idx + oldString.length),
    matched: true,
  };
}

// ---------------------------------------------------------------------------
// Path gate — only plan files under docs/plans/**/*.md
// ---------------------------------------------------------------------------

/**
 * Returns true if a repo-relative path looks like a plan file.
 * Mirrors validate-ac-grammar.js:86 isPlanPath regex exactly.
 */
function isPlanPath(repoRel) {
  return /(?:^|\/)docs\/plans\/.*\.md$/.test(repoRel.replace(/\\/g, '/'));
}

// ---------------------------------------------------------------------------
// Markdown table parsing helpers
// ---------------------------------------------------------------------------

/**
 * Split a pipe-delimited markdown table row into trimmed cells (not including
 * the leading/trailing empty cells from surrounding pipes).
 * Mirrors validate-ac-grammar.js splitPipeRow.
 */
function splitPipeRow(line) {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map(c => c.trim());
}

// ---------------------------------------------------------------------------
// AC table extraction — typed-prefix path extraction
// ---------------------------------------------------------------------------

// 40-char lowercase hex SHA pattern for cited: skip rule.
const SHA40_RE = /^[0-9a-f]{40}$/;

/**
 * Extract the file path(s) from a typed-prefix Test cell selector.
 * Returns an array of path strings (empty array = no paths to check, skip silently).
 *
 * Extraction grammar per plan § Design typed-prefix table:
 *   pytest:   path or path::Class::method → substring before first ::
 *   node:     path::test-name → substring before first ::
 *   grep:     pattern@path1,path2 → comma-separated tail after @
 *   sh/bash:  shell command → first positional path-like token (skip flags)
 *   bats:     test-file → whole argument
 *   cargo:    NO PATH — skip (module::test form, not a file path)
 *   cited:    path | 40-char SHA | path,path,… → per ref: skip SHAs, treat rest as paths
 *
 * Mirrors validate-ac-grammar.js:380-390 cited: semantics and
 * writing-plans.md:392 parse semantics.
 */
function extractPathsFromSelector(prefix, selector) {
  switch (prefix) {
    case 'pytest':
    case 'node': {
      // path or path::selector — take substring before first ::
      const idx = selector.indexOf('::');
      return [idx === -1 ? selector.trim() : selector.slice(0, idx).trim()].filter(Boolean);
    }

    case 'grep': {
      // pattern@path1,path2 — take comma-separated tail after @
      const atIdx = selector.indexOf('@');
      if (atIdx === -1) return [];
      return selector.slice(atIdx + 1).split(',').map(p => p.trim()).filter(Boolean);
    }

    case 'sh':
    case 'bash': {
      // shell command — skip flags, return first positional path-like token.
      // A "path-like token" is not a flag (doesn't start with -) and contains / or .
      // Review: code-reviewer Slice A F5 — per plan § Design, ambiguous shell-token extraction
      // emits ADVISORY not WARN. Tokens starting with $ (env-var paths like $HOME/...) or ./
      // or ../ are ambiguous; bare command names without / or . are also ambiguous. Return null
      // (skip silently) for these cases so the hook doesn't WARN on unresolvable tokens.
      const tokens = selector.split(/\s+/).filter(t => t.length > 0);
      const pathToken = tokens.find(t => !t.startsWith('-') && (t.includes('/') || t.includes('.')));
      if (!pathToken) return [];
      // Ambiguous: env-var reference, relative script, or bare command name without path separator
      if (pathToken.startsWith('$') || pathToken.startsWith('./') || pathToken.startsWith('../')) {
        return [];  // advisory: cannot reliably resolve to a repo-relative path
      }
      if (!pathToken.includes('/') && !pathToken.includes('.')) {
        return [];  // advisory: bare command name, no path structure to resolve
      }
      return [pathToken];
    }

    case 'bats': {
      // whole argument is the test file path
      return [selector.trim()].filter(Boolean);
    }

    case 'cargo': {
      // module::test form — no file path, skip entirely
      return [];
    }

    case 'cited': {
      // comma-separated refs — skip 40-char SHAs, treat rest as paths
      return selector.split(',').map(r => r.trim()).filter(r => r.length > 0 && !SHA40_RE.test(r));
    }

    default:
      return [];
  }
}

// Known typed prefixes — mirrors validate-ac-grammar.js KNOWN_PREFIXES
const KNOWN_PREFIXES = new Set(['pytest', 'node', 'cargo', 'grep', 'cited', 'sh', 'bash', 'bats']);

/**
 * Parse a Test cell (raw from the table) into { prefix, selector } or null.
 * Handles S1-S4 shapes by stripping backticks and prefix: via regex.
 * Returns null when the cell has no recognized prefix (skip silently — grammar
 * check is validate-ac-grammar.js's job, not ours).
 */
function parseTestCell(cell) {
  const trimmed = cell.trim();
  if (!trimmed) return null;

  // Try to extract prefix:selector in any of the S1-S4 forms.
  // S3 / S4 whole-cell wrap: `prefix:selector` or `prefix:` `selector`
  // S2 prefix-wrap:          `prefix:` selector
  // S1 bare:                  prefix:selector

  // Remove surrounding backtick wraps to get at the content.
  // Match: optional leading backtick, prefix:selector, optional trailing backtick
  const m = trimmed.match(/^`?([a-z0-9_]+):([^`]*)`?/);
  if (!m) return null;

  const prefix = m[1];
  if (!KNOWN_PREFIXES.has(prefix)) return null;

  let selector = m[2];

  // S2 fires when primary regex captures `prefix:` with empty selector (S4 shape with
  // backtick-separated selector). Regex ordering is load-bearing: the primary regex m
  // runs first and captures S1/S3/S4 shapes; s2 overrides selector for the S2 variant.
  // For S2 shape (`prefix:` rest), the selector is the rest of the cell after
  // the closing backtick. Re-check for S2: backtick ends right after colon.
  // Pattern: `prefix:` <rest without backtick>
  // Review: code-reviewer Slice A F7 — regex interaction documented.
  const s2 = trimmed.match(/^`([a-z0-9_]+):`\s*`?([^`]*)`?/);
  if (s2) {
    // s2[1] === prefix by construction (same prefix capture in both regexes)
    // Review: code-reviewer Slice A F1 — dead expression deleted (result discarded, S2 regex re-captures prefix)
    selector = s2[2].trim();
  }

  return { prefix, selector: selector.trim() };
}

/**
 * Extract all gate-bound AC rows from content with their test paths.
 * Returns array of { id: string, paths: string[] }.
 * Rows where path extraction yields no paths are omitted (cargo:, SHA cited:, etc.).
 *
 * Mirrors validate-ac-grammar.js extractGateBoundRows structure.
 */
function extractAcPaths(content) {
  const lines = content.split('\n');
  let inAcSection = false;
  let inFence = false;
  let headerFound = false;
  let idCol = -1;
  let testCol = -1;
  let classCol = -1;
  const results = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    if (/^##\s+[Aa]cceptance\s+[Cc]riteria/.test(line)) {
      inAcSection = true;
      continue;
    }

    if (!inAcSection) continue;

    // Stop at the next heading (require space after ## to avoid matching ###)
    // Review: code-reviewer Slice A F9 — tightened from /^##/ to /^## / to avoid false-stops on ###.
    if (/^## /.test(line)) break;

    if (!line.includes('|')) continue;

    if (!headerFound) {
      // Header must contain "Binding" (case-insensitive) — mirrors validate-ac-grammar.js:181
      if (/binding/i.test(line)) {
        headerFound = true;
        const cells = splitPipeRow(line);
        for (let c = 0; c < cells.length; c++) {
          const cl = cells[c].toLowerCase();
          if (cl === 'id') idCol = c;
          else if (/^test/.test(cl)) testCol = c;
          else if (/binding/.test(cl)) classCol = c;
        }
      }
      continue;
    }

    // Skip separator rows
    if (/^\s*\|[\s\-|]+\|\s*$/.test(line)) continue;

    const cells = splitPipeRow(line);
    if (classCol < 0 || classCol >= cells.length) continue;

    const bindingClass = cells[classCol];
    if (!/gate/i.test(bindingClass)) continue;

    // Skip sentinel rows (pending realization)
    const testCell = testCol >= 0 && testCol < cells.length ? cells[testCol] : '';
    if (/^pending\s+realization$/i.test(testCell.trim())) continue;

    const id = idCol >= 0 && idCol < cells.length ? cells[idCol].trim() : '';

    const parsed = parseTestCell(testCell.trim());
    if (!parsed) continue;

    const paths = extractPathsFromSelector(parsed.prefix, parsed.selector);
    if (paths.length === 0) continue;

    results.push({ id, paths });
  }

  return results;
}

// ---------------------------------------------------------------------------
// Dispatch Ledger extraction — write-files per chunk
// ---------------------------------------------------------------------------

/**
 * Extract chunk write-files from the ## Dispatch Ledger section.
 * Returns a flat string array of all write-file entries across all chunk rows.
 * Ownership semantics are 'any chunk owns'; per-row attribution is intentionally collapsed.
 * Returns null if the section is absent (caller should skip silently).
 *
 * The ledger header must contain "write-files" (case-insensitive) to locate the column.
 * Returns null if the write-files column is not found in the header.
 *
 * Review: code-reviewer Slice A F4 — docstring corrected; old text said "array of arrays
 * (one per chunk row)" but function actually returns a flat array.
 */
function extractLedgerWriteFiles(content) {
  const lines = content.split('\n');
  let inLedgerSection = false;
  let inFence = false;
  let headerFound = false;
  let writeFilesCol = -1;
  const allWriteFiles = [];
  let ledgerSectionFound = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;

    if (/^##\s+[Dd]ispatch\s+[Ll]edger/.test(line)) {
      inLedgerSection = true;
      ledgerSectionFound = true;
      continue;
    }

    if (!inLedgerSection) continue;

    // Stop at the next ## heading (require space after ## to avoid matching ###)
    // Review: code-reviewer Slice A F9 — tightened from /^##/ to /^## /.
    if (/^## /.test(line)) break;

    if (!line.includes('|')) continue;

    if (!headerFound) {
      // Identify header: must contain "write-files" (case-insensitive)
      if (/write.files/i.test(line)) {
        headerFound = true;
        const cells = splitPipeRow(line);
        for (let c = 0; c < cells.length; c++) {
          if (/write.files/i.test(cells[c])) {
            writeFilesCol = c;
            break;
          }
        }
      }
      continue;
    }

    // Skip separator rows
    if (/^\s*\|[\s\-|]+\|\s*$/.test(line)) continue;

    const cells = splitPipeRow(line);
    if (writeFilesCol < 0 || writeFilesCol >= cells.length) continue;

    const rawCell = cells[writeFilesCol].trim();
    if (!rawCell) continue;

    // write-files cell is comma-separated list of paths
    const entries = rawCell.split(',').map(e => e.trim()).filter(Boolean);
    allWriteFiles.push(...entries);
  }

  if (!ledgerSectionFound) return null;
  if (!headerFound) return null;  // Ledger present but no write-files column → treat as malformed
  return allWriteFiles;
}

// ---------------------------------------------------------------------------
// Ownership match function
// ---------------------------------------------------------------------------

/**
 * Returns true if writeFilesEntry owns path P per the plan § Design match function:
 *   1. Exact match.
 *   2. Directory pathspec (trailing / or no extension) that prefixes P.
 *   3. Glob pattern (contains *, ?, or [) that matches P under POSIX glob semantics.
 */
function entryOwnsPath(entry, p) {
  // Normalize separators
  const e = entry.replace(/\\/g, '/');
  const target = p.replace(/\\/g, '/');

  // Clause 1: exact match
  if (e === target) return true;

  // Clause 3: glob pattern (check before directory-prefix to handle **/*.py correctly)
  if (e.includes('*') || e.includes('?') || e.includes('[')) {
    return globMatch(e, target);
  }

  // Clause 2: directory pathspec — trailing slash, or no extension (path with no dot after last /)
  // Spec approximation per plan § Design: no extension implies directory pathspec. False positives
  // possible on extensionless files (Makefile, Dockerfile, LICENSE) owning siblings with the same
  // prefix + extension. Accepted approximation.
  const isDir = e.endsWith('/') || !path.extname(e);
  if (isDir) {
    const prefix = e.endsWith('/') ? e : e + '/';
    return target.startsWith(prefix) || target === e;
  }

  return false;
}

/**
 * Minimal POSIX glob matcher supporting *, **, ?.
 * Converts the glob to a regexp and tests the target path.
 */
function globMatch(pattern, target) {
  // Review: code-reviewer Slice A F2 — [, ], *, ? are glob metacharacters and must NOT be
  // escaped by the general regex-escape pass. Escape only true regex-special chars that are
  // NOT glob metacharacters; then convert glob metacharacters to their regex equivalents.
  // Old code: /([.+^${}()|[\]\\])/ — included [ and ] which broke bracket-class glob support.
  const escaped = pattern.replace(/([.+^${}()|\\])/g, '\\$1');
  // Convert glob to regexp:
  //   [...]  → pass through as-is (POSIX bracket class — already valid regex syntax)
  //   **     → matches any path segment sequence (including /)
  //   *      → matches any chars except /
  //   ?      → matches any single char except /
  const reStr = escaped
    .replace(/\*\*/g, '@@DOUBLESTAR@@')  // protect ** temporarily
    .replace(/\*/g, '[^/]*')             // single * → no slash
    .replace(/\?/g, '[^/]')              // ? → no slash
    .replace(/@@DOUBLESTAR@@/g, '.*');   // ** → anything including /
  const re = new RegExp(`^${reStr}$`);
  return re.test(target);
}

/**
 * Returns true if any entry in writeFiles owns path P.
 */
function isOwned(writeFiles, p) {
  return writeFiles.some(entry => entryOwnsPath(entry, p));
}

// ---------------------------------------------------------------------------
// Output builders
// ---------------------------------------------------------------------------

/**
 * Build hook output payload for chunk-ownership violations.
 * Default mode: additionalContext (WARN). Strict mode: deny.
 *
 * Strict-mode env var: COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT
 * Mirrors validate-ac-grammar.js COORDINATOR_AC_GRAMMAR_STRICT precedent.
 */
function buildViolationsPayload(violations) {
  const lines = violations.map(({ id, p }) =>
    `AC ${id}: test path \`${p}\` has no chunk owner in the Dispatch Ledger write-files.`
  );
  const message = lines.join('\n');

  // never exits non-zero — env-var strict-mode guard mirrors validate-ac-grammar.js
  const strict = process.env.COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT === '1';

  if (strict) {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: message,
      },
    });
  }

  // additionalContext branch does NOT carry hookEventName (only the deny branch does).
  // Review: code-reviewer Slice A F8 — matches validate-ac-grammar.js:493 comment.
  return JSON.stringify({
    hookSpecificOutput: {
      additionalContext: `[ac-chunk-ownership warning] ${message}\n\nThe write will proceed. Ensure every AC test path is owned by a chunk's write-files, or set COORDINATOR_AC_CHUNK_OWNERSHIP_STRICT=1 to block on violations.`,
    },
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  let raw = '';
  try {
    for await (const chunk of process.stdin) {
      raw += chunk;
    }
  } catch {
    process.exit(0);
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    process.exit(0);
  }

  const toolName = payload.tool_name;
  const toolInput = payload.tool_input || {};
  const cwd = payload.cwd || process.cwd();

  const filePath = toolInput.file_path;
  if (!filePath) process.exit(0);

  // Resolve repo root and repo-relative path
  const repoRoot = resolveRepoRoot(cwd);
  const absFilePath = path.isAbsolute(filePath) ? filePath : path.join(cwd, filePath);
  const repoRel = toRepoRelative(absFilePath, repoRoot);
  if (!repoRel) process.exit(0);

  // Gate 1: only docs/plans/**/*.md
  if (!isPlanPath(repoRel)) process.exit(0);

  // Compute prospective content
  let prospectiveContent;

  if (toolName === 'Write') {
    prospectiveContent = toolInput.content || '';

  } else if (toolName === 'Edit') {
    const oldString = toolInput.old_string;
    const newString = toolInput.new_string;

    let current;
    try {
      current = fs.readFileSync(absFilePath, 'utf8');
    } catch {
      process.exit(0);
    }

    const { result, matched } = applyEdit(current, oldString || '', newString || '');
    if (!matched) process.exit(0);
    prospectiveContent = result;

  } else if (toolName === 'MultiEdit') {
    const edits = toolInput.edits || [];

    let current;
    try {
      current = fs.readFileSync(absFilePath, 'utf8');
    } catch {
      process.exit(0);
    }

    let content = current;
    for (const edit of edits) {
      const { result, matched } = applyEdit(content, edit.old_string || '', edit.new_string || '');
      if (!matched) process.exit(0);
      content = result;
    }
    prospectiveContent = content;

  } else {
    process.exit(0);
  }

  // Gate 2: extract AC paths — if none, skip silently
  // (also skips if no AC section with Binding-Class column exists)
  let acRows;
  try {
    acRows = extractAcPaths(prospectiveContent);
  } catch {
    process.exit(0);
  }

  if (acRows.length === 0) process.exit(0);

  // Gate 3: extract ledger write-files — if ledger absent, skip silently (AC6)
  let writeFiles;
  try {
    writeFiles = extractLedgerWriteFiles(prospectiveContent);
  } catch {
    process.exit(0);
  }

  if (writeFiles === null) process.exit(0);  // Ledger absent or malformed — AC6, AC14

  // Check ownership for each AC path
  const violations = [];
  for (const { id, paths } of acRows) {
    for (const p of paths) {
      if (!isOwned(writeFiles, p)) {
        violations.push({ id, p });
      }
    }
  }

  if (violations.length === 0) process.exit(0);

  process.stdout.write(buildViolationsPayload(violations));
  process.exit(0);
}

main().catch(err => {
  process.stderr.write(`validate-ac-chunk-ownership: unexpected error: ${err.message}\n`);
  process.exit(0);
});
