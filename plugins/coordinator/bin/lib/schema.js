'use strict';
/**
 * schema.js — frontmatter schema loader and validator for coordinator tracked records.
 *
 * Spec backlink: docs/plans/2026-05-01-portable-ideas-from-obsidian-research.md §W1
 *
 * Exports:
 *   loadSchemas(schemasDir)        → { [name]: schema, _byGlob: [{glob, schemaName}] }
 *   matchSchemaForPath(repoRel, schemas) → {schemaName, schema} | null
 *   parseFrontmatter(content)      → {frontmatter, body}
 *   validateFrontmatter(fm, schema) → {ok, errors}
 *   validateLessonsFile(content, lessonSchema) → {ok, errors}
 *
 * No external dependencies — uses only Node built-ins. YAML parsing is limited to the
 * frontmatter subset our schemas produce: scalar strings, inline lists, and one level of
 * nested mapping (for type/values blocks). Complex YAML constructs are not supported.
 */

const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Minimal YAML parser for schema files and frontmatter blocks
// Handles: scalar key: value, list items (- val), one level of nested mapping.
// Does NOT handle: anchors, multi-line strings, flow mappings beyond inline lists.
// ---------------------------------------------------------------------------

/**
 * Parse a YAML string into a plain JS object.
 * Restricted to the subset used in coordinator schemas and frontmatter.
 */
function parseYaml(text) {
  const lines = text.split('\n');
  return parseYamlLines(lines, 0, 0).value;
}

/**
 * Parse lines starting at `start` with expected indent `baseIndent`.
 * Returns { value: object|array|scalar, nextLine: number }.
 */
function parseYamlLines(lines, start, baseIndent) {
  const result = {};
  let i = start;

  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trimEnd();

    // Skip blank lines and comments
    if (trimmed === '' || trimmed.trimStart().startsWith('#')) {
      i++;
      continue;
    }

    const indent = raw.length - raw.trimStart().length;

    // If we've dedented below base, stop
    if (indent < baseIndent) {
      break;
    }

    // List item at this level?
    if (trimmed.trimStart().startsWith('- ') || trimmed.trimStart() === '-') {
      // Caller expecting a list — signal via special return
      return { value: parseList(lines, i, baseIndent), nextLine: skipPast(lines, i, baseIndent) };
    }

    // key: value mapping
    const colonIdx = trimmed.indexOf(':');
    if (colonIdx === -1) {
      i++;
      continue;
    }

    const key = trimmed.slice(0, colonIdx).trim();
    const rest = trimmed.slice(colonIdx + 1).trim();

    if (rest === '' || rest.startsWith('#')) {
      // Value is either null or a nested block on following lines
      const nextLine = i + 1;
      if (nextLine < lines.length) {
        const nextTrimmed = lines[nextLine].trimEnd();
        const nextIndent = nextTrimmed === '' ? baseIndent : lines[nextLine].length - lines[nextLine].trimStart().length;

        if (nextIndent > indent && nextTrimmed !== '') {
          // Nested block
          const nested = parseYamlLines(lines, nextLine, nextIndent);
          result[key] = nested.value;
          i = nested.nextLine;
          continue;
        }
      }
      result[key] = null;
    } else if (rest.startsWith('[') && rest.endsWith(']')) {
      // Inline list: [a, b, c]
      result[key] = parseInlineList(rest);
    } else {
      result[key] = parseScalar(rest);
    }
    i++;
  }

  return { value: result, nextLine: i };
}

function parseList(lines, start, baseIndent) {
  const list = [];
  let i = start;
  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trimEnd().trimStart();
    if (trimmed === '' || trimmed.startsWith('#')) { i++; continue; }
    const indent = raw.length - raw.trimStart().length;
    if (indent < baseIndent) break;
    if (trimmed.startsWith('- ')) {
      list.push(parseScalar(trimmed.slice(2).trim()));
    } else if (trimmed === '-') {
      list.push(null);
    } else {
      break;
    }
    i++;
  }
  return list;
}

function skipPast(lines, start, baseIndent) {
  let i = start;
  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trimEnd();
    if (trimmed === '' || trimmed.startsWith('#')) { i++; continue; }
    const indent = raw.length - raw.trimStart().length;
    if (indent < baseIndent) break;
    if (trimmed.trimStart().startsWith('- ') || trimmed.trimStart() === '-') {
      i++;
    } else {
      break;
    }
  }
  return i;
}

function parseInlineList(text) {
  // "[a, b, c]" → ['a', 'b', 'c']
  const inner = text.slice(1, -1);
  return inner.split(',').map(s => parseScalar(s.trim())).filter(s => s !== null && s !== '');
}

function parseScalar(text) {
  if (text === 'null' || text === '~') return null;
  if (text === 'true') return true;
  if (text === 'false') return false;
  const n = Number(text);
  if (!isNaN(n) && text !== '') return n;
  // Strip surrounding quotes
  if ((text.startsWith('"') && text.endsWith('"')) ||
      (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1);
  }
  return text;
}

// ---------------------------------------------------------------------------
// Glob matcher — supports *, **, ? with no external deps
// ---------------------------------------------------------------------------

/**
 * Convert a glob pattern to a RegExp. Handles *, **, ?.
 * Uses posix-style / separators regardless of platform.
 */
function globToRegex(pattern) {
  // Normalise separators
  const p = pattern.replace(/\\/g, '/');
  let re = '';
  let i = 0;
  while (i < p.length) {
    const c = p[i];
    if (c === '*' && p[i + 1] === '*') {
      re += '.*';
      i += 2;
      if (p[i] === '/') i++; // consume trailing slash after **
    } else if (c === '*') {
      re += '[^/]*';
      i++;
    } else if (c === '?') {
      re += '[^/]';
      i++;
    } else if ('.+^${}()|[]\\'.includes(c)) {
      re += '\\' + c;
      i++;
    } else {
      re += c;
      i++;
    }
  }
  return new RegExp('^' + re + '$');
}

function matchGlob(pattern, filePath) {
  const normalised = filePath.replace(/\\/g, '/');
  return globToRegex(pattern).test(normalised);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Load all *.yaml schema files from schemasDir.
 * Returns { [schemaName]: parsedSchema, _byGlob: [{glob, schemaName}] }
 */
function loadSchemas(schemasDir) {
  const schemas = { _byGlob: [] };
  const files = fs.readdirSync(schemasDir).filter(f => f.endsWith('.yaml'));
  for (const file of files) {
    const raw = fs.readFileSync(path.join(schemasDir, file), 'utf8');
    const parsed = parseYaml(raw);
    const name = parsed.schema || path.basename(file, '.yaml');
    schemas[name] = parsed;
    if (parsed.applies_to) {
      schemas._byGlob.push({ glob: parsed.applies_to, schemaName: name });
    }
  }
  return schemas;
}

/**
 * Find the schema that matches repoRelPath.
 * repoRelPath should use forward slashes (e.g. "tasks/handoffs/foo.md").
 * Returns {schemaName, schema} or null.
 */
function matchSchemaForPath(repoRelPath, schemas) {
  const normalised = repoRelPath.replace(/\\/g, '/');
  for (const { glob, schemaName } of schemas._byGlob) {
    if (matchGlob(glob, normalised)) {
      return { schemaName, schema: schemas[schemaName] };
    }
  }
  return null;
}

/**
 * Extract YAML frontmatter from markdown content.
 * Expects optional "---\n...\n---\n" delimiters at the start.
 * Returns {frontmatter: object|null, body: string}.
 */
function parseFrontmatter(content) {
  if (!content.startsWith('---')) {
    return { frontmatter: null, body: content };
  }
  const afterFirst = content.slice(3);
  // Allow optional \r after ---
  const firstNewline = afterFirst.indexOf('\n');
  if (firstNewline === -1) {
    return { frontmatter: null, body: content };
  }
  // Find closing ---
  const rest = afterFirst.slice(firstNewline + 1);
  const closeIdx = rest.search(/^---\s*$/m);
  if (closeIdx === -1) {
    return { frontmatter: null, body: content };
  }
  const yamlBlock = rest.slice(0, closeIdx);
  const body = rest.slice(closeIdx).replace(/^---\s*\n?/, '');
  try {
    const fm = parseYaml(yamlBlock);
    return { frontmatter: fm, body };
  } catch {
    return { frontmatter: null, body: content };
  }
}

/**
 * Validate a frontmatter object against a schema.
 * Returns {ok: true} or {ok: false, errors: [{field, error, hint}]}.
 * Permissive on optional fields; only validates required.
 */
function validateFrontmatter(frontmatter, schema) {
  if (!schema || !schema.required) {
    return { ok: true };
  }
  if (!frontmatter) {
    return {
      ok: false,
      errors: [{ field: '(frontmatter)', error: 'missing frontmatter block', hint: 'Add --- delimited YAML frontmatter at the top of the file' }]
    };
  }

  const errors = [];
  for (const [field, spec] of Object.entries(schema.required)) {
    const value = frontmatter[field];

    // For string-or-null fields, explicit null is a valid value — don't treat as missing.
    const isStringOrNull = spec && typeof spec === 'object' && spec.type === 'string-or-null';
    const isMissing = value === undefined || (value === null && !isStringOrNull);

    if (isMissing) {
      errors.push({ field, error: 'required field missing', hint: `Add "${field}:" to frontmatter` });
      continue;
    }

    if (typeof spec === 'string') {
      // Simple type check
      const typeErr = checkType(field, value, spec);
      if (typeErr) errors.push(typeErr);
    } else if (spec && typeof spec === 'object') {
      const type = spec.type;
      if (type === 'enum') {
        const allowed = spec.values || [];
        if (!allowed.includes(String(value))) {
          errors.push({
            field,
            error: `invalid enum value "${value}"`,
            hint: `Allowed values: ${allowed.join(', ')}`
          });
        }
      } else if (type === 'string-or-null') {
        if (value !== null && typeof value !== 'string') {
          errors.push({ field, error: `expected string or null, got ${typeof value}`, hint: `Set to a string or null` });
        }
      } else if (type === 'list-of-string') {
        if (!Array.isArray(value)) {
          errors.push({ field, error: 'expected a list', hint: `Use YAML list syntax, e.g. ["name"]` });
        } else {
          const bad = value.filter(v => typeof v !== 'string');
          if (bad.length > 0) {
            errors.push({ field, error: 'list contains non-string items', hint: 'All list items must be strings' });
          }
        }
      } else if (type === 'number') {
        if (typeof value !== 'number') {
          errors.push({ field, error: `expected number, got ${typeof value}`, hint: 'Provide a numeric value' });
        }
      } else {
        // Treat as simple type string
        const typeErr = checkType(field, value, type);
        if (typeErr) errors.push(typeErr);
      }
    }
  }

  return errors.length === 0 ? { ok: true } : { ok: false, errors };
}

function checkType(field, value, type) {
  if (type === 'string') {
    if (typeof value !== 'string') {
      return { field, error: `expected string, got ${typeof value}`, hint: `Provide a string value for "${field}"` };
    }
  } else if (type === 'iso-date') {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(value)) {
      return { field, error: `expected ISO date (YYYY-MM-DD), got "${value}"`, hint: 'Use format YYYY-MM-DD' };
    }
  } else if (type === 'number') {
    if (typeof value !== 'number') {
      return { field, error: `expected number, got ${typeof value}`, hint: 'Provide a numeric value' };
    }
  }
  return null;
}

/**
 * Validate a lessons.md file against the lesson-entry schema.
 * Each **bold-title** entry may carry a [universal] or [project] tag.
 * Unknown tags (not in tag_enum.values) are rejected; untagged entries are allowed.
 *
 * Returns {ok: boolean, errors: [{line, field, error, hint}]}.
 */
function validateLessonsFile(content, lessonSchema) {
  if (!lessonSchema || lessonSchema.match_mode !== 'inline-tag-per-entry') {
    return { ok: true };
  }

  const allowedTags = (lessonSchema.tag_enum && lessonSchema.tag_enum.values) || [];
  const untaggedAllowed = lessonSchema.tag_enum && lessonSchema.tag_enum.untagged_allowed !== false;

  const errors = [];
  const lines = content.split('\n');

  // Match bold-title entry lines: **Some Title**
  const entryRe = /^\s*[-*]?\s*\*\*[^*]+\*\*/;
  // Match tags like [universal] or [project] within a line
  const tagRe = /\[([^\]]+)\]/g;
  // Strip inline code spans (`...`) and markdown link text (`[text](url)`) before
  // tag-matching so model-ID literals like `claude-opus-4-7[1m]` and link text
  // like `[some link](url)` aren't mistaken for tags. Code-span match is
  // non-greedy and tolerant of doubled backticks; link-text strip removes the
  // bracketed portion of `[…](…)` constructs.
  const stripNoise = (s) =>
    s.replace(/``[^`]*``/g, ' ').replace(/`[^`]*`/g, ' ').replace(/\[[^\]]*\]\([^)]*\)/g, ' ');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!entryRe.test(line)) continue;

    // Collect all bracket-enclosed tokens on this line, ignoring those inside
    // code spans or markdown link text.
    const scrubbed = stripNoise(line);
    const tags = [];
    let m;
    tagRe.lastIndex = 0;
    while ((m = tagRe.exec(scrubbed)) !== null) {
      tags.push(m[1]);
    }

    if (tags.length === 0) {
      // Untagged entry — ok if untagged_allowed
      if (!untaggedAllowed) {
        errors.push({
          line: i + 1,
          field: 'tag',
          error: 'entry has no tag',
          hint: `Add [${allowedTags.join('|')}] to the entry line`
        });
      }
    } else {
      // Validate each tag
      for (const tag of tags) {
        if (!allowedTags.includes(tag)) {
          errors.push({
            line: i + 1,
            field: 'tag',
            error: `unknown tag "[${tag}]"`,
            hint: `Allowed tags: ${allowedTags.map(t => '[' + t + ']').join(', ')}`
          });
        }
      }
    }
  }

  return errors.length === 0 ? { ok: true } : { ok: false, errors };
}

module.exports = {
  loadSchemas,
  matchSchemaForPath,
  parseFrontmatter,
  validateFrontmatter,
  validateLessonsFile,
  // Exported for testing
  _parseYaml: parseYaml,
  _matchGlob: matchGlob,
};
