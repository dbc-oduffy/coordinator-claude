'use strict';
/**
 * validate-frontmatter-schema.js — PreToolUse hook that surfaces frontmatter-schema
 * violations to the agent before a Write/Edit/MultiEdit lands on a tracked-record file.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W1/Validator
 *
 * Default mode is WARN: emits the violation as additionalContext so the agent sees
 * the schema gripe but the write still proceeds. Strict mode (COORDINATOR_SCHEMA_STRICT=1)
 * restores the original deny behavior — the write is blocked. Periodic drift sweeps
 * via bin/query-records --validate-all (in /update-docs) catch accumulated warn-mode drift.
 *
 * Reads Claude PreToolUse JSON from stdin. Exits 0 in all cases (hook contract).
 *
 * Negative-spec: this hook NEVER exits non-zero. Infra failures (schema load, repo
 * root resolution, file read) are logged to stderr and silently allowed — never block
 * on infra. The hook double-fails intentionally on Edit mismatches by falling through
 * silent (let Edit fail on its own merits per Patrik R1 finding 0).
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { loadSchemas, matchSchemaForPath, parseFrontmatter, validateFrontmatter, validateLessonsFile } = require('../../bin/lib/schema.js');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SCHEMAS_DIR = path.join(__dirname, '../../schemas');

// ---------------------------------------------------------------------------
// Helpers
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
 * Apply a single old_string→new_string replacement to content.
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

/**
 * Build a hook output payload for a validation failure.
 * errors is an array of {field, error, hint} (or {line, field, error, hint} for lessons).
 *
 * Default mode (warn): emits additionalContext — the agent sees the message, write proceeds.
 * Strict mode (COORDINATOR_SCHEMA_STRICT=1): emits a deny — the write is blocked.
 */
function buildViolationPayload(schemaName, errors) {
  const parts = errors.map(e => {
    const field = e.field || '(unknown)';
    const hint = e.hint ? `; required shape: ${e.hint}` : '';
    return `${field}: ${e.error}${hint}`;
  });
  const message = `${schemaName}: ${parts.join('; ')}`;
  const strict = process.env.COORDINATOR_SCHEMA_STRICT === '1';

  if (strict) {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: message,
      },
    });
  }

  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: `[frontmatter-schema warning] ${message}\n\nThe write will proceed. Fix the frontmatter on the next edit, or set COORDINATOR_SCHEMA_STRICT=1 to block on violations. Periodic drift is swept by /update-docs.`,
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

  // Load schemas (telemetry-style: log to stderr on error, never block)
  let schemas;
  try {
    schemas = loadSchemas(SCHEMAS_DIR);
  } catch (err) {
    process.stderr.write(`validate-frontmatter-schema: schema load error: ${err.message}\n`);
    process.exit(0);
  }

  // Match schema for this path
  const match = matchSchemaForPath(repoRel, schemas);
  if (!match) process.exit(0); // not a tracked-record path

  const { schemaName, schema } = match;

  // Build prospective content based on tool type
  let prospectiveContent;

  if (toolName === 'Write') {
    // Write: use content directly
    prospectiveContent = toolInput.content || '';

  } else if (toolName === 'Edit') {
    const oldString = toolInput.old_string;
    const newString = toolInput.new_string;

    // Read current file if it exists
    let current;
    try {
      current = fs.readFileSync(absFilePath, 'utf8');
    } catch {
      // File doesn't exist — old_string can't match; fall through silent.
      // (Edit will fail on its own merits when Claude applies it.)
      process.exit(0);
    }

    // Apply the edit
    const { result, matched } = applyEdit(current, oldString || '', newString || '');
    if (!matched) {
      // old_string doesn't appear — fall through silent (let Edit fail on its own)
      process.exit(0);
    }
    prospectiveContent = result;

  } else if (toolName === 'MultiEdit') {
    const edits = toolInput.edits || [];

    // Read current file if it exists
    let current = '';
    try {
      current = fs.readFileSync(absFilePath, 'utf8');
    } catch {
      // File doesn't exist — start with empty
      current = '';
    }

    // Apply each edit sequentially
    let content = current;
    for (const edit of edits) {
      const { result, matched } = applyEdit(content, edit.old_string || '', edit.new_string || '');
      if (!matched) {
        // Any mismatch — fall through silent
        process.exit(0);
      }
      content = result;
    }
    prospectiveContent = content;

  } else {
    process.exit(0);
  }

  // Validate the prospective content against the schema
  let validationResult;

  if (schema.match_mode === 'inline-tag-per-entry') {
    // Lessons file — validate inline tags
    validationResult = validateLessonsFile(prospectiveContent, schema);
  } else {
    // Standard frontmatter validation
    const { frontmatter } = parseFrontmatter(prospectiveContent);

    // Missing frontmatter on a schema'd file → surface as warn (or deny under strict mode)
    if (frontmatter === null) {
      const requiredFields = schema.required ? Object.keys(schema.required) : [];
      const hint = requiredFields.length > 0
        ? `expected fields: ${requiredFields.join(', ')}`
        : 'add --- delimited YAML frontmatter';
      process.stdout.write(buildViolationPayload(schemaName, [{
        field: '(missing frontmatter)',
        error: 'no YAML frontmatter found',
        hint,
      }]));
      process.exit(0);
    }

    validationResult = validateFrontmatter(frontmatter, schema);
  }

  if (validationResult.ok) {
    // Pass — exit silent
    process.exit(0);
  }

  // Fail — emit warn (or deny under COORDINATOR_SCHEMA_STRICT=1) to stdout
  process.stdout.write(buildViolationPayload(schemaName, validationResult.errors));
  process.exit(0);
}

main().catch(err => {
  process.stderr.write(`validate-frontmatter-schema: unexpected error: ${err.message}\n`);
  process.exit(0);
});
