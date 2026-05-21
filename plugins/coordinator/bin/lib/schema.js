'use strict';
/**
 * schema.js — frontmatter schema loader and validator for coordinator tracked records.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1
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

  // Optional fields: only validate type/enum/list shape; presence not required.
  // (Required-field shape was checked above.)
  if (schema.optional) {
    for (const [field, spec] of Object.entries(schema.optional)) {
      if (!(field in frontmatter)) continue;
      const value = frontmatter[field];
      if (value === null || value === undefined) continue;
      if (typeof spec === 'string') {
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
        } else if (type === 'list-of-string') {
          if (!Array.isArray(value)) {
            errors.push({ field, error: 'expected a list', hint: `Use YAML list syntax, e.g. ["name"]` });
          }
        } else if (type === 'string-or-null') {
          if (value !== null && typeof value !== 'string') {
            errors.push({ field, error: `expected string or null, got ${typeof value}`, hint: `Set to a string or null` });
          }
        } else if (type === 'number') {
          if (typeof value !== 'number') {
            errors.push({ field, error: `expected number, got ${typeof value}`, hint: 'Provide a numeric value' });
          }
        } else {
          const typeErr = checkType(field, value, type);
          if (typeErr) errors.push(typeErr);
        }
      }
    }
  }

  // Cross-field rules — schema-specific. Schema YAML parser does not support inline
  // mapping list items (only scalars + nested blocks), so cross-field rules live in
  // JS keyed by schema name. Add new schemas here as needed.
  // See docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md § Phase 1a.
  const crossFieldErrors = applyCrossFieldRules(frontmatter, schema);
  errors.push(...crossFieldErrors);

  return errors.length === 0 ? { ok: true } : { ok: false, errors };
}

/**
 * Cross-field rule registry. Each entry: { schema: <name>, rules: [{ check, message }] }.
 * `check(fm)` returns null if ok, or { field, error, hint } if violated.
 */
const CROSS_FIELD_RULES = {
  handoff: [
    {
      check: (fm) => {
        if (fm.deployment_state === 'awaiting_gate' && (!fm.gate_dependency || String(fm.gate_dependency).trim() === '')) {
          return {
            field: 'gate_dependency',
            error: 'required when deployment_state=awaiting_gate',
            hint: 'Add a one-line gate_dependency naming the subsystem or condition that gates this handoff'
          };
        }
        return null;
      },
    },
    {
      check: (fm) => {
        if (fm.deployment_state === 'ready_to_fire' && fm.gate_dependency && String(fm.gate_dependency).trim() !== '') {
          return {
            field: 'gate_dependency',
            error: 'must be empty or omitted when deployment_state=ready_to_fire',
            hint: 'A handoff cannot be ready_to_fire while it has a gate_dependency. Either clear gate_dependency or set deployment_state=awaiting_gate.'
          };
        }
        return null;
      },
    },
    {
      check: (fm) => {
        const graphFields = ['blocks', 'blocked_by', 'roadmap_id'];
        const present = graphFields.filter(f => fm[f] !== undefined && fm[f] !== null);
        if (present.length > 0 && fm.kind !== 'spinoff-roadmap') {
          return {
            field: present.join(', '),
            error: `permitted only when kind=spinoff-roadmap (current kind: ${fm.kind || 'unset'})`,
            hint: 'Graph primitives (blocks/blocked_by/roadmap_id) are roadmap-only. Remove them, or set kind: spinoff-roadmap if this is a roadmap stub.'
          };
        }
        return null;
      },
    },
    // Roadmap-stub-only validator rules (Phase 5g, 2026-05-08).
    // kind: spinoff-roadmap requires the full graph + identifier set.
    {
      check: (fm) => {
        if (fm.kind !== 'spinoff-roadmap') return null;
        const required = ['roadmap_id', 'tc_id', 'wave', 'blocks', 'blocked_by'];
        const missing = required.filter(f => fm[f] === undefined || fm[f] === null);
        if (missing.length > 0) {
          return {
            field: missing.join(', '),
            error: `required for kind=spinoff-roadmap`,
            hint: 'Roadmap stubs must declare their identifier (roadmap_id, tc_id), serialization order (wave), and graph edges (blocks, blocked_by — empty list ok). See skills/roadmap-planning/SKILL.md § Phase 2.1.'
          };
        }
        return null;
      },
    },
    // roadmap_id implies kind: spinoff-roadmap (the inverse of the spinoff-roadmap → roadmap_id rule).
    {
      check: (fm) => {
        if (fm.roadmap_id && fm.kind !== 'spinoff-roadmap') {
          return {
            field: 'roadmap_id',
            error: `present but kind is "${fm.kind || 'unset'}" — roadmap_id requires kind: spinoff-roadmap`,
            hint: 'Either set kind: spinoff-roadmap (if this is a roadmap stub), or remove roadmap_id (if not).'
          };
        }
        return null;
      },
    },
    // cost enum (Patrik P2-4, 2026-05-08): when present, must be one of T0/T1/T2/T3.
    {
      check: (fm) => {
        if (fm.cost === undefined || fm.cost === null) return null;
        const allowed = ['T0', 'T1', 'T2', 'T3'];
        if (!allowed.includes(String(fm.cost))) {
          return {
            field: 'cost',
            error: `invalid cost value "${fm.cost}"`,
            hint: `Allowed values: ${allowed.join(', ')}. T0 = trivial (minutes); T1 = small (<1h); T2 = medium (1-4h); T3 = large (multi-day).`
          };
        }
        return null;
      },
    },
  ],

  // ---------------------------------------------------------------------------
  // cross-repo-memo cross-field rules
  // Spec backlink: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Validator rules
  //
  // CRITICAL: Memo lifecycle timestamps are ISO-8601 convenience metadata only.
  // The authoritative audit trail lives in the receiver repo's git log of the
  // lifecycle-transition commit. Do NOT impose SHA-requirement logic here —
  // that is handoff's shipped_in: pattern, which does not apply to memos.
  //
  // Grandfather cutoff: memos with created < 2026-05-22 are skipped entirely.
  // ---------------------------------------------------------------------------
  'cross-repo-memo': [
    // Grandfather mechanism: skip validation for pre-lifecycle memos.
    // All subsequent rules return early when this fires.
    {
      check: (fm) => {
        if (!fm.created) return null;
        // created is YYYY-MM-DD; compare lexicographically (safe for ISO dates).
        if (String(fm.created) < '2026-05-22') {
          // Signal to applyCrossFieldRules via a special sentinel object.
          // We use the special field '__skip__' which applyCrossFieldRules detects.
          return { __skip__: true };
        }
        return null;
      },
    },
    // status: action_taken requires action_taken_at AND decision.
    {
      check: (fm) => {
        if (fm.status !== 'action_taken') return null;
        const missing = [];
        if (!fm.action_taken_at || String(fm.action_taken_at).trim() === '') missing.push('action_taken_at');
        if (!fm.decision || String(fm.decision).trim() === '') missing.push('decision');
        if (missing.length > 0) {
          return {
            field: missing.join(', '),
            error: `required when status=action_taken`,
            hint: `Set ${missing.join(' and ')} when marking a memo action_taken. decision must be one of: accepted, declined, partial, superseded.`
          };
        }
        return null;
      },
    },
    // status: closed requires closed_at AND action_taken_at AND decision.
    {
      check: (fm) => {
        if (fm.status !== 'closed') return null;
        const missing = [];
        if (!fm.closed_at || String(fm.closed_at).trim() === '') missing.push('closed_at');
        if (!fm.action_taken_at || String(fm.action_taken_at).trim() === '') missing.push('action_taken_at');
        if (!fm.decision || String(fm.decision).trim() === '') missing.push('decision');
        if (missing.length > 0) {
          return {
            field: missing.join(', '),
            error: `required when status=closed`,
            hint: `Set ${missing.join(', ')} when closing a memo. A closed memo must have a complete action record.`
          };
        }
        return null;
      },
    },
    // status: superseded requires superseded_by.
    {
      check: (fm) => {
        if (fm.status !== 'superseded') return null;
        if (!fm.superseded_by || String(fm.superseded_by).trim() === '') {
          return {
            field: 'superseded_by',
            error: 'required when status=superseded',
            hint: 'Set superseded_by to the path of the memo that supersedes this one (inverse of supersedes:).'
          };
        }
        return null;
      },
    },
    // delivery_mode: central-only requires to: (must address someone even without a receiver repo).
    {
      check: (fm) => {
        if (fm.delivery_mode !== 'central-only') return null;
        if (!fm.to || String(fm.to).trim() === '') {
          return {
            field: 'to',
            error: 'required when delivery_mode=central-only',
            hint: 'Specify the receiver EM identifier in "to:" even for central-only delivery. Used for workday-start surfacing and audit trail.'
          };
        }
        return null;
      },
    },
  ],
};

function applyCrossFieldRules(frontmatter, schema) {
  if (!frontmatter || !schema || !schema.schema) return [];
  const rules = CROSS_FIELD_RULES[schema.schema];
  if (!rules) return [];
  const errors = [];
  for (const rule of rules) {
    const violation = rule.check(frontmatter);
    if (!violation) continue;
    // __skip__ sentinel: pre-cutoff grandfather mechanism fires — skip all remaining rules.
    if (violation.__skip__) return [];
    errors.push(violation);
  }
  return errors;
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
 * Strip inline backtick code-spans and markdown link text from a single line so
 * downstream tag-detection regexes don't trip on bracket-tokens that live
 * inside code spans (e.g. `claude-opus-4-7[1m]`, `arr[0]`) or inside the
 * `[text]` portion of a `[text](url)` link.
 *
 * Code-span semantics follow CommonMark: a backtick run of length N opens a
 * span that closes on the next backtick run of identical length N. This makes
 * the strip robust against mixed nesting like ``weird`code``, which a
 * non-greedy single/double-backtick regex pair mis-handles.
 */
function stripCodeSpansAndLinks(line) {
  let out = '';
  let i = 0;
  const n = line.length;
  while (i < n) {
    const c = line[i];
    if (c === '`') {
      // Measure opening backtick run length
      let runLen = 0;
      while (i + runLen < n && line[i + runLen] === '`') runLen++;
      // Search for a closing run of identical length
      let j = i + runLen;
      let closeAt = -1;
      while (j < n) {
        if (line[j] === '`') {
          let k = 0;
          while (j + k < n && line[j + k] === '`') k++;
          if (k === runLen) {
            closeAt = j;
            break;
          }
          j += k; // skip past run of different length and keep searching
        } else {
          j++;
        }
      }
      if (closeAt === -1) {
        // No matching close — emit the unmatched backticks literally and continue
        out += ' '.repeat(runLen);
        i += runLen;
      } else {
        // Replace the entire span (including the delimiters) with whitespace
        out += ' '.repeat(closeAt + runLen - i);
        i = closeAt + runLen;
      }
      continue;
    }
    out += c;
    i++;
  }
  // Now strip markdown link text: [text](url) → keep (url) part out so the
  // bracketed text doesn't register as a tag.
  return out.replace(/\[[^\]]*\]\([^)]*\)/g, ' ');
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
  // Strip inline code spans and markdown link text before tag-matching so
  // model-ID literals like `claude-opus-4-7[1m]`, array-ish prose like
  // `arr[0]`, and link text like `[some link](url)` are not mistaken for
  // tags. The code-span scanner walks the line character-by-character and
  // matches CommonMark-style runs: an opening backtick run of length N closes
  // on the next backtick run of identical length N. This handles nested /
  // mixed runs (e.g. ``weird`code``) that simple non-greedy regexes mis-strip.
  const stripNoise = (s) => stripCodeSpansAndLinks(s);

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
  _stripCodeSpansAndLinks: stripCodeSpansAndLinks,
};
