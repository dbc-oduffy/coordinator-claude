'use strict';
/**
 * validate-ac-grammar.js — PreToolUse hook that surfaces AC Test-cell grammar
 * violations to the agent before a Write/Edit/MultiEdit lands on a plan file.
 *
 * Spec backlink: docs/plans/2026-06-09-plan-coverage-rework-burden-reduction.md § C1
 *
 * Default mode is WARN: emits the violation as additionalContext so the agent sees
 * the grammar gripe but the write still proceeds. Strict mode (COORDINATOR_AC_GRAMMAR_STRICT=1)
 * restores the deny behavior — the write is blocked.
 *
 * Reads Claude PreToolUse JSON from stdin. Exits 0 in all cases (hook contract).
 *
 * Negative-spec: this hook NEVER exits non-zero. Infra failures (file read, apply
 * mismatch) are silently allowed — never block on infra. Mirror validate-frontmatter-schema.js
 * lines 17-21.
 *
 * Grammar source-of-truth: plan-coverage-checker.md Phase 5 lines 172-208 (S1-S4 classifier
 * + per-prefix arg-shape rules). Runtime reference: check-acceptance-oracle.sh parse_pipe_row().
 * The JS classifier MUST match runtime gate acceptance semantics.
 *
 * Design-as-offers: AC grammar failure is a misdirection (authors write prose because prose
 * is the natural shape) — additionalContext offer-shape is correct per eager-agent-calibration.md.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ---------------------------------------------------------------------------
// Helpers — shared with validate-frontmatter-schema.js (inlined for offline-safety)
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
 * Mirrors applyEdit() in validate-frontmatter-schema.js.
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
 * Matches docs/plans/<anything>.md (at any depth).
 */
function isPlanPath(repoRel) {
  return /(?:^|\/)docs\/plans\/.*\.md$/.test(repoRel.replace(/\\/g, '/'));
}

// ---------------------------------------------------------------------------
// AC table extraction
// ---------------------------------------------------------------------------

/**
 * Returns true if the content contains an ## Acceptance Criteria heading
 * (case-insensitive) followed by a markdown table with a Binding-Class column.
 *
 * Looks for the heading, then scans following lines for a table header row
 * that contains "Binding" (case-insensitive) — consistent with check-acceptance-oracle.sh
 * line 343 which uses grep -qi "Binding".
 */
function hasAcTable(content) {
  // Review: code-reviewer — hasAcTable must track fence state identically to
  // extractGateBoundRows (lines 151-155) so both functions agree on what is live
  // vs. illustrative AC content.
  const lines = content.split('\n');
  let inAcSection = false;
  let inFence = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // Mirror extractGateBoundRows fence tracking so both functions agree.
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    if (/^##\s+[Aa]cceptance\s+[Cc]riteria/.test(line)) {
      inAcSection = true;
      continue;
    }
    if (inAcSection) {
      // Stop at the next heading
      if (/^##/.test(line)) break;
      // Look for a pipe-delimited header row containing "Binding"
      if (line.includes('|') && /binding/i.test(line)) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Extract all gate-bound AC rows from the content.
 * Returns an array of { id: string, testCell: string } objects.
 *
 * Algorithm mirrors check-acceptance-oracle.sh:
 * 1. Find ## Acceptance Criteria heading.
 * 2. Parse header row to find column indices for ID, Test, Binding-Class.
 * 3. For each subsequent data row, split on |, trim, check Binding-Class for
 *    substring "gate" (case-insensitive), extract Test cell.
 * 4. Skip sentinel `pending realization` (case-insensitive).
 */
function extractGateBoundRows(content) {
  const lines = content.split('\n');
  let inAcSection = false;
  let inFence = false;
  let headerFound = false;
  let idCol = -1;
  let testCol = -1;
  let classCol = -1;
  const rows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Track markdown code-fence state. Inside a fence, no parsing fires —
    // a ```markdown block demonstrating AC grammar is illustrative, not live.
    // Without this guard, every plan with an AC-example fence would have its
    // example rows parsed as if real (2026-06-09 dogfood: this hook's own
    // plan tripped on it).
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

    // Stop at the next heading
    if (/^##/.test(line)) break;

    if (!line.includes('|')) continue;

    if (!headerFound) {
      // Identify header row: must contain "Binding" (case-insensitive)
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

    // Skip separator rows (---) and blank rows
    if (/^\s*\|[\s\-|]+\|\s*$/.test(line)) continue;

    const cells = splitPipeRow(line);
    if (classCol < 0 || classCol >= cells.length) continue;

    const bindingClass = cells[classCol];
    if (!/gate/i.test(bindingClass)) continue;

    const testCell = testCol >= 0 && testCol < cells.length ? cells[testCol] : '';
    const id = idCol >= 0 && idCol < cells.length ? cells[idCol] : '';

    // Skip sentinel
    if (/^pending\s+realization$/i.test(testCell.trim())) continue;

    rows.push({ id: id.trim(), testCell: testCell.trim() });
  }

  return rows;
}

/**
 * Split a pipe-delimited markdown table row into trimmed cells (not including
 * the leading/trailing empty cells from surrounding pipes).
 */
function splitPipeRow(line) {
  // Strip leading/trailing pipes
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map(c => c.trim());
}

// ---------------------------------------------------------------------------
// S1-S4 shape classifier + per-prefix arg-shape classifier
//
// Mirrors plan-coverage-checker.md Phase 5 lines 172-208 and
// check-acceptance-oracle.sh parse_pipe_row() tokenizer (lines 258-338).
//
// Accepted shapes:
//   S1 bare            prefix:value           (no backticks)
//   S2 prefix-wrapped  `prefix:` value        (backtick only around prefix+colon)
//   S3 whole-cell      `prefix:value`         (single backtick pair, no prose)
//   S4 prefix+sel      `prefix:` `selector`   (two backtick groups, optional trailing prose)
//
// Rejected shapes (produce findings):
//   U1 whole-cell + inline `in` connector:  `prefix:sel` in `path`
//   U2 whole-cell + trailing prose:         `prefix:sel` exists
//   No recognized prefix
//   Compound selectors (and / ; for single-token prefixes)
// ---------------------------------------------------------------------------

const KNOWN_PREFIXES = new Set(['pytest', 'node', 'cargo', 'grep', 'cited', 'sh', 'bash', 'bats']);

// Single-token-selector prefixes: strip trailing prose after first whitespace in S2.
// sh/bash/bats/node/cargo keep internal whitespace (argv semantics).
const SINGLE_TOKEN_PREFIXES = new Set(['grep', 'cited', 'pytest']);

/**
 * Tokenize a Test cell (after outer-whitespace trim) into { shape, prefix, selector }
 * mirroring parse_pipe_row's tokenizer exactly.
 *
 * Returns:
 *   { ok: true, prefix: string, selector: string, shape: 'S1'|'S2'|'S3'|'S4' }
 *   { ok: false, issue: string, prefix: string|null, rawSelector: string|null }
 */
function tokenizeCell(cell) {
  // S4: `prefix:` `selector` [trailing prose]
  const s4 = cell.match(/^`([a-z0-9_]+):`\s*`([^`]+)`(\s.*)?$/);
  if (s4) {
    return { ok: true, prefix: s4[1], selector: s4[2], shape: 'S4' };
  }

  // S2: `prefix:` rest
  const s2 = cell.match(/^`([a-z0-9_]+):`(.*)$/);
  if (s2) {
    const pfx = s2[1];
    let rest = s2[2];
    // Strip ONE leading space (parse_pipe_row _s2_rest="${BASH_REMATCH[2]# }")
    if (rest.startsWith(' ')) rest = rest.slice(1);
    // For single-token-selector prefixes, strip trailing prose
    if (SINGLE_TOKEN_PREFIXES.has(pfx)) {
      const ws = rest.indexOf(' ');
      if (ws !== -1) rest = rest.slice(0, ws);
    }
    if (!rest) {
      return { ok: false, issue: 'empty selector after prefix', prefix: pfx, rawSelector: null };
    }
    return { ok: true, prefix: pfx, selector: rest, shape: 'S2' };
  }

  // Whole-cell wrap variants — S3 (clean) or U1/U2 (with trailing prose)
  const wholeProse = cell.match(/^`([a-z0-9_]+):([^`]*)`(\s.+)?$/);
  if (wholeProse) {
    const trailing = wholeProse[3];
    if (trailing && trailing.trim()) {
      // U1/U2: whole-cell wrap with trailing prose
      const pfx = wholeProse[1];
      const sel = wholeProse[2];
      // Detect inline `in` connector pattern specifically.
      // The canonical fix is `prefix:pattern@path` — extract the path from the
      // trailing backtick-wrapped fragment (e.g. ``  in `bar.md` ``) so the
      // suggested rewrite carries it, not just the bare pattern.
      const inMatch = trailing.match(/^\s+in\s+`([^`]+)`/);
      if (inMatch) {
        return {
          ok: false,
          issue: 'whole-cell wrap with inline `in` connector — join pattern and path with `@` instead',
          prefix: pfx,
          rawSelector: `${sel}@${inMatch[1]}`,
        };
      }
      return {
        ok: false,
        issue: `whole-cell wrap with trailing prose ("${trailing.trim()}") — remove trailing text or use S4 shape`,
        prefix: pfx,
        rawSelector: sel,
      };
    }
    // S3: clean whole-cell wrap
    if (!wholeProse[2]) {
      return { ok: false, issue: 'empty selector in whole-cell wrap', prefix: wholeProse[1], rawSelector: null };
    }
    return { ok: true, prefix: wholeProse[1], selector: wholeProse[2], shape: 'S3' };
  }

  // S1: bare prefix:value (no backticks at all)
  const s1 = cell.match(/^([a-z0-9_]+):(.+)$/);
  if (s1) {
    if (s1[2].trim() === '') {
      return { ok: false, issue: 'empty selector after prefix', prefix: s1[1], rawSelector: null };
    }
    return { ok: true, prefix: s1[1], selector: s1[2], shape: 'S1' };
  }

  // No recognized prefix
  return { ok: false, issue: 'no recognized typed prefix (expected prefix:selector form)', prefix: null, rawSelector: null };
}

/**
 * Validate per-prefix arg-shape after S1-S4 is confirmed.
 * Returns null on pass, or a string describing the issue on fail.
 *
 * Mirrors plan-coverage-checker.md Phase 5 lines 200-208.
 */
function validateArgShape(prefix, selector) {
  switch (prefix) {
    case 'pytest':
      // arg must be <path> OR contain :: (selector)
      // Emit finding if arg contains whitespace inside what looks like a single selector
      if (/\s/.test(selector) && !selector.includes('::')) {
        return 'pytest: selector contains whitespace — use `path::TestName` form or a plain path';
      }
      return null;

    case 'node':
      // arg must be <path> OR <path> -t "<name>"
      // Emit finding if contains :: without -t (cargo-shape in node context)
      if (selector.includes('::') && !/ -t /.test(selector)) {
        return 'node: selector uses `::` (cargo-shape) — use `path -t "test name"` for node:test filtering';
      }
      return null;

    case 'cargo':
      // arg must contain :: OR be a single identifier
      // Emit finding if arg contains / (path-shape, not module-shape)
      if (selector.includes('/')) {
        return 'cargo: selector contains `/` (path-shape) — use `module::test_name` module-path form';
      }
      return null;

    case 'grep':
      // arg must contain @ separating pattern and path
      if (!selector.includes('@')) {
        return 'grep: missing `@` separator — expected `pattern@path` form';
      }
      // Emit finding if post-@ side contains another @
      {
        const atIdx = selector.indexOf('@');
        const pathSide = selector.slice(atIdx + 1);
        if (pathSide.includes('@')) {
          return 'grep: path side contains `@` — likely `@user/file` typo; use a single `@` separator';
        }
      }
      return null;

    case 'cited':
      // arg must be a 40-char hex SHA, a file path, or a comma-separated list of refs
      // Emit finding if path side contains spaces (smells of prose blob)
      if (/\s/.test(selector)) {
        return 'cited: selector contains spaces — expected a file path, 40-char SHA, or comma-separated paths (no spaces)';
      }
      return null;

    case 'sh':
    case 'bash':
    case 'bats':
      // arg must be a repo-relative script path (no leading /, no ..)
      {
        // The selector may include args after the first space; extract just the path
        const scriptPath = selector.split(/\s/)[0];
        if (scriptPath.startsWith('/')) {
          return `${prefix}: script path is absolute — use a repo-relative path`;
        }
        if (scriptPath.includes('..')) {
          return `${prefix}: script path contains \`..\` traversal — use a repo-relative path without ..`;
        }
      }
      return null;

    default:
      // Unknown prefix — already caught by shape classifier's known-prefix check below
      return null;
  }
}

// ---------------------------------------------------------------------------
// Finding builder
// ---------------------------------------------------------------------------

const SHAPES_RECAP = 'bare `prefix:value` (S1), prefix-wrap `` `prefix:` value `` (S2), whole-cell wrap `` `prefix:value` `` (S3), prefix+selector wrap `` `prefix:` `selector` `` optional trailing prose (S4)';

/**
 * Produce a corrected S1 rewrite for a cell, given the best-guess prefix + selector.
 * Always offers S1 (the form that renders in markdown table cells) per plan C1.
 */
function suggestS1Rewrite(prefix, selector) {
  if (!prefix) return '(unable to suggest — no recognized prefix)';
  const sel = selector ? selector.trim() : '<selector>';
  return `${prefix}:${sel}`;
}

/**
 * Build the per-finding message for one AC row.
 * Format per plan C1 § Offer-shape output:
 *   AC Test cell `<verbatim>` does not match S1-S4 grammar.
 *   Issue: <named shape failure>
 *   Supported shapes: <recap>
 *   Suggested rewrite: <concrete S1 rewrite>
 */
function buildFindingMessage(id, verbatimCell, issue, prefix, rawSelector) {
  const rowLabel = id ? `AC-${id}` : 'AC row';
  const rewrite = suggestS1Rewrite(prefix, rawSelector);
  return (
    `${rowLabel} Test cell \`${verbatimCell}\` does not match S1-S4 grammar.\n` +
    `Issue: ${issue}\n` +
    `Supported shapes: ${SHAPES_RECAP}\n` +
    `Suggested rewrite: ${rewrite}`
  );
}

/**
 * Validate one gate-bound row. Returns a finding message string or null.
 */
function validateRow(id, testCell) {
  const tok = tokenizeCell(testCell);

  if (!tok.ok) {
    return buildFindingMessage(id, testCell, tok.issue, tok.prefix, tok.rawSelector);
  }

  // Shape is valid (S1-S4). Check unknown prefix.
  if (!KNOWN_PREFIXES.has(tok.prefix)) {
    const issue = `unknown typed prefix \`${tok.prefix}:\` — supported prefixes: ${[...KNOWN_PREFIXES].join(', ')}`;
    return buildFindingMessage(id, testCell, issue, null, null);
  }

  // Run per-prefix arg-shape classifier
  const argIssue = validateArgShape(tok.prefix, tok.selector);
  if (argIssue) {
    // Arg-shape finding: still offer S1 rewrite with best-guess corrected selector
    return buildFindingMessage(id, testCell, argIssue, tok.prefix, tok.selector);
  }

  return null;
}

// ---------------------------------------------------------------------------
// Output builders
// ---------------------------------------------------------------------------

/**
 * Build hook output payload for AC grammar findings.
 * Default mode: additionalContext (warn). Strict mode: deny.
 */
function buildFindingsPayload(findings) {
  const message = findings.join('\n\n');
  const strict = process.env.COORDINATOR_AC_GRAMMAR_STRICT === '1';

  if (strict) {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: message,
      },
    });
  }

  // Review: code-reviewer — mirror validate-frontmatter-schema.js lines 264-269:
  // additionalContext branch does NOT carry hookEventName (only the deny branch does).
  return JSON.stringify({
    hookSpecificOutput: {
      additionalContext: `[ac-grammar warning] ${message}\n\nThe write will proceed. Fix the AC Test cells before workstream-complete, or set COORDINATOR_AC_GRAMMAR_STRICT=1 to block on violations.`,
    },
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  // Read all stdin
  let raw = '';
  try {
    for await (const chunk of process.stdin) {
      raw += chunk;
    }
  } catch {
    process.exit(0);
  }

  // Parse PreToolUse payload
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

    // Review: code-reviewer — mirror the Edit branch: exit 0 on read failure rather
    // than silently falling through with current = '' and applying edits to an empty
    // base (which would produce a false prospectiveContent and potentially mis-fire).
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

  // Gate 2: must have ## Acceptance Criteria section with a Binding-Class column
  if (!hasAcTable(prospectiveContent)) process.exit(0);

  // Extract and validate gate-bound rows
  const rows = extractGateBoundRows(prospectiveContent);
  if (rows.length === 0) process.exit(0);

  const findings = [];
  for (const { id, testCell } of rows) {
    const finding = validateRow(id, testCell);
    if (finding) findings.push(finding);
  }

  if (findings.length === 0) process.exit(0);

  process.stdout.write(buildFindingsPayload(findings));
  process.exit(0);
}

main().catch(err => {
  process.stderr.write(`validate-ac-grammar: unexpected error: ${err.message}\n`);
  process.exit(0);
});
