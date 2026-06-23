'use strict';
/**
 * schema.js — frontmatter schema loader and validator for coordinator tracked records.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1
 *
 * Exports:
 *   loadSchemas(schemasDir)        → { [name]: schema, _byGlob: [{glob, schemaName}] }
 *   matchSchemaForPath(repoRel, schemas) → {schemaName, schema} | null
 *   parseFrontmatter(content)      → {frontmatter, body}  (body starts after closing ---; leading comment excluded)
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
    } else {
      // Pre-strip a trailing `# comment` so inline-list detection works on
      // `key: [a, b]  # note`. parseScalar would otherwise also strip; passing
      // the pre-stripped value avoids a double-strip and centralizes the rule.
      const stripped = stripInlineComment(rest);
      if (stripped.startsWith('[') && stripped.endsWith(']')) {
        result[key] = parseInlineList(stripped);
      } else {
        result[key] = parseScalar(stripped);
      }
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
  // Review: code-reviewer — align trimming with parseList: both now use raw.trimEnd().trimStart()
  // so indented comments and list items are handled identically in both functions.
  let i = start;
  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trimEnd().trimStart();
    if (trimmed === '' || trimmed.startsWith('#')) { i++; continue; }
    const indent = raw.length - raw.trimStart().length;
    if (indent < baseIndent) break;
    if (trimmed.startsWith('- ') || trimmed === '-') {
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

/**
 * Strip a YAML-style trailing inline comment from a scalar text.
 *
 * YAML semantics: a `#` begins a comment when it is at the start of the
 * scalar OR preceded by whitespace. A `#` inside a single- or double-quoted
 * span is a literal `#`, not a comment opener.
 *
 * Returns the scalar text with the comment (and the whitespace preceding it)
 * removed. No-op when no comment is present.
 *
 * Limitation: YAML single-quoted scalars escape a literal single-quote as `''`
 * (two consecutive single-quotes). This helper does not unfold that escape —
 * `''` flips `inSingle` twice (open then immediately close), so a `#` appearing
 * later in the same logical single-quoted value may be treated as a comment.
 * Use double-quoted scalars for values containing `'` in frontmatter.
 *
 * Cross-repo memo BS-2026-05-19-FRONTMATTER-HOOK-COMMENT-FALSE-POSITIVES
 * (2026-05-28 holodeck-em → central-em): unstripped inline comments
 * produced dirty scalars like "draft  # alpha" that silently failed enum
 * validation, surfacing as warnings on well-formed frontmatter.
 */
function stripInlineComment(text) {
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"' && !inSingle) inDouble = !inDouble;
    else if (c === "'" && !inDouble) {
      // YAML single-quoted escape: `''` is a literal single-quote. Skip both
      // characters without toggling state so a `#` later in the same span is
      // still seen as quoted.
      if (inSingle && text[i + 1] === "'") { i++; continue; }
      inSingle = !inSingle;
    }
    else if (c === '#' && !inSingle && !inDouble) {
      if (i === 0 || /\s/.test(text[i - 1])) {
        return text.slice(0, i).trimEnd();
      }
    }
  }
  return text;
}

function parseScalar(text) {
  text = stripInlineComment(text);
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
 * Convert a glob pattern to a RegExp. Handles *, **, ?, and bracket character-classes.
 * Uses posix-style / separators regardless of platform.
 *
 * Bracket character-classes ([0-9], [a-z], [abc]) are passed through verbatim into
 * the RegExp — they are NOT escaped. This allows `cross-repo/[0-9]*.md` to match
 * dated memos (e.g. cross-repo/2026-05-23-topic.md) while excluding non-digit-prefixed
 * files like cross-repo/README.md.
 *
 * code-review F7: the bracket passthrough scans for the FIRST ']' after '['
 * (via p.indexOf(']', i+1)), so classes with an embedded literal ']' as the first
 * character (e.g. []] or []a]) will early-terminate incorrectly. This is intentional —
 * the supported subset is "simple character classes without embedded ']'" such as
 * [0-9], [a-z], [abc]. Patterns with embedded ']' inside a class are not supported.
 *
 * Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
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
    } else if (c === '[') {
      // Pass bracket character-class through verbatim until the closing ']'.
      // This allows [0-9], [a-z], [abc] etc. to work as regex character-classes.
      // An unmatched '[' (no closing ']') falls through to literal-escape below.
      const closeIdx = p.indexOf(']', i + 1);
      if (closeIdx !== -1) {
        re += p.slice(i, closeIdx + 1);
        i = closeIdx + 1;
      } else {
        // No closing bracket — escape the '[' as a literal character.
        re += '\\[';
        i++;
      }
    } else if ('.+^${}()|\\'.includes(c)) {
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
 * repoRelPath should use forward slashes (e.g. "state/handoffs/foo.md").
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
 * Expects optional "---\n...\n---\n" delimiters at the start, optionally preceded
 * by one or more HTML comment blocks (<!-- ... -->) and surrounding whitespace.
 *
 * Seed-handoff templates deliberately lead with a <!-- seed comment --> explaining
 * substitution-time instructions. The leading comment is annotation metadata, not
 * body content — it is skipped before frontmatter extraction, and the returned
 * `body` starts after the closing `---` delimiter (the comment is dropped).
 *
 * Returns {frontmatter: object|null, body: string}.
 * When frontmatter is present, body is the content AFTER the closing --- delimiter;
 * the leading HTML comment (if any) is excluded from body.
 *
 * Negative-spec: if a <!-- has no matching -->, the function treats the file as
 * having no frontmatter (returns {frontmatter:null, body:content}) — no hang risk.
 */
function parseFrontmatter(content) {
  // Skip optional leading HTML comment block(s) before looking for frontmatter.
  // Multi-line and multiple consecutive comments are handled; unclosed comments bail out.
  let cursor = 0;
  // Trim leading whitespace/newlines before each comment candidate.
  while (true) {
    // Advance past whitespace/newlines at current position.
    // JS \s already includes \n and \r — no need for explicit [\s\n\r]*.
    const wsMatch = content.slice(cursor).match(/^\s*/);
    const wsLen = wsMatch ? wsMatch[0].length : 0;
    const afterWs = cursor + wsLen;
    if (content.slice(afterWs, afterWs + 4) === '<!--') {
      const closeIdx = content.indexOf('-->', afterWs + 4);
      if (closeIdx === -1) {
        // Unclosed comment — treat as no frontmatter.
        return { frontmatter: null, body: content };
      }
      cursor = closeIdx + 3; // advance past '-->'
    } else {
      cursor = afterWs;
      break;
    }
  }
  // cursor now points at the content after any leading comments + surrounding whitespace.
  const remaining = content.slice(cursor);
  if (!remaining.startsWith('---')) {
    return { frontmatter: null, body: content };
  }
  const afterFirst = remaining.slice(3);
  // Allow optional \r after ---
  const firstNewline = afterFirst.indexOf('\n');
  if (firstNewline === -1) {
    return { frontmatter: null, body: content };
  }
  // Guard: a real YAML frontmatter delimiter is "---\n" with nothing but optional
  // whitespace between the dashes and the newline. An HR like "--- foo" or "------"
  // is not a frontmatter opener. If there is non-whitespace before the first newline,
  // treat the file as having no frontmatter.
  if (afterFirst.slice(0, firstNewline).trim() !== '') {
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
    // Guard: parseYaml is lenient and returns {} for non-YAML prose (e.g. markdown
    // body prose accidentally wrapped in --- delimiters). An empty object is not a
    // valid frontmatter block — treat it as no-frontmatter so callers don't index
    // a record with all fields missing.
    if (fm === null || fm === undefined || Object.keys(fm).length === 0) {
      return { frontmatter: null, body: content };
    }
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
/**
 * Validate a single field value against its spec. Returns an array of error
 * records (empty when the value is well-formed). Recurses into `type: object`
 * specs that declare a `fields:` sub-spec block.
 *
 * Spec shapes accepted:
 *   - string (legacy):            "string" | "iso-date" | "number" | "bool" | "object"
 *   - object spec:                { type: "enum", values: [...] }
 *                                 { type: "string-or-null" }
 *                                 { type: "number-or-null" }
 *                                 { type: "list-of-string" }
 *                                 { type: "object", fields: { sub: spec, ... } }
 *
 * Nested-object recursion: when spec.type === 'object' and spec.fields is set,
 * each declared sub-field is validated against its sub-spec. Sub-field nulls
 * and missing sub-fields are tolerated by default — sub-fields are
 * implicitly optional. The error `field` path is dotted (`loe.tshirt`) so
 * downstream consumers can map back to the source frontmatter.
 */
function validateField(field, value, spec) {
  const errors = [];

  if (typeof spec === 'string') {
    const typeErr = checkType(field, value, spec);
    if (typeErr) errors.push(typeErr);
    return errors;
  }

  if (!spec || typeof spec !== 'object') return errors;

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
  } else if (type === 'number-or-null') {
    if (value !== null && typeof value !== 'number') {
      errors.push({ field, error: `expected number or null, got ${typeof value}`, hint: `Set to a number or null` });
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
  } else if (type === 'object') {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      errors.push({
        field,
        error: `expected object, got ${Array.isArray(value) ? 'array' : (value === null ? 'null' : typeof value)}`,
        hint: 'Use YAML nested mapping syntax'
      });
    } else if (spec.fields) {
      for (const [subField, subSpec] of Object.entries(spec.fields)) {
        const subValue = value[subField];
        if (subValue === undefined || subValue === null) continue; // sub-fields tolerate null/missing
        errors.push(...validateField(`${field}.${subField}`, subValue, subSpec));
      }
    }
  } else {
    // Unknown type tag — fall through to checkType (which silently passes unknowns).
    const typeErr = checkType(field, value, type);
    if (typeErr) errors.push(typeErr);
  }

  return errors;
}

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
    const isNumberOrNull = spec && typeof spec === 'object' && spec.type === 'number-or-null';
    const isMissing = value === undefined || (value === null && !(isStringOrNull || isNumberOrNull));

    if (isMissing) {
      errors.push({ field, error: 'required field missing', hint: `Add "${field}:" to frontmatter` });
      continue;
    }

    errors.push(...validateField(field, value, spec));
  }

  // Optional fields: only validate type/enum/list shape; presence not required.
  // (Required-field shape was checked above.)
  if (schema.optional) {
    for (const [field, spec] of Object.entries(schema.optional)) {
      if (!(field in frontmatter)) continue;
      const value = frontmatter[field];
      if (value === null || value === undefined) continue;
      errors.push(...validateField(field, value, spec));
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
    // ---------------------------------------------------------------------------
    // Grandfather-cutoff presence rules for category and summary (2026-05-29).
    //
    // NOTE: Cross-field rules run AFTER the required-field validation loop in
    // validateFrontmatter (applyCrossFieldRules is called at the very end, after
    // the required-field loop and optional-field type checks complete). Because
    // `created` is a REQUIRED field on handoffs, any post-cutoff handoff with a
    // missing `created` already errors on the required-field check before these
    // rules are reached. The cutoff self-guards below are therefore defence-in-
    // depth for belt-and-suspenders correctness, not a substitute for that ordering.
    //
    // Spec backlink: docs/plans/2026-05-29-handoff-schema-category-summary.md § Chunk 1
    // ---------------------------------------------------------------------------

    // (a) category must be present and non-empty on post-cutoff handoffs.
    {
      check: (fm) => {
        // Self-guard: skip for pre-cutoff handoffs (legacy handoffs have no category).
        if (fm.created && String(fm.created) < '2026-05-29') return null;
        if (!fm.category || String(fm.category).trim() === '') {
          return {
            field: 'category',
            error: 'required for handoffs created on or after 2026-05-29',
            hint: 'Set category to one of: roadmap, infra, bug, docs, research, refactor'
          };
        }
        return null;
      },
    },
    // (b) summary must be present and non-empty on post-cutoff handoffs.
    {
      check: (fm) => {
        // Self-guard: skip for pre-cutoff handoffs.
        if (fm.created && String(fm.created) < '2026-05-29') return null;
        if (!fm.summary || String(fm.summary).trim() === '') {
          return {
            field: 'summary',
            error: 'required for handoffs created on or after 2026-05-29',
            hint: 'Add a one-line summary (≤120 chars) describing the session work'
          };
        }
        return null;
      },
    },
    // (c) summary length ≤120 chars when present (post-cutoff self-guard).
    {
      check: (fm) => {
        // Self-guard: skip for pre-cutoff handoffs.
        if (fm.created && String(fm.created) < '2026-05-29') return null;
        if (fm.summary && String(fm.summary).length > 120) {
          return {
            field: 'summary',
            error: `summary exceeds 120 characters (got ${String(fm.summary).length})`,
            hint: 'Keep summary to one concise line of 120 characters or fewer'
          };
        }
        return null;
      },
    },
    // supersedes: is the conditional-live orientation-supersession field on install/orientation
    // batons. It belongs only on kind: spinoff — not kind: spinoff-roadmap or any other kind.
    //
    // Structural disambiguation: this rule lives in the HANDOFF block (not the memo block).
    // The memo block carries the terminal status: superseded ⇒ superseded_by: coupling, which
    // is a different lifecycle concept. Baton supersession (conditional-live, install-chain) and
    // memo supersession (terminal, lifecycle) are separate mechanisms; do not conflate them.
    {
      check: (fm) => {
        if (fm.supersedes === undefined || fm.supersedes === null || String(fm.supersedes).trim() === '') {
          return null;
        }
        if (fm.kind !== 'spinoff') {
          return {
            field: 'supersedes',
            error: `permitted only when kind=spinoff (current kind: ${fm.kind || 'unset'})`,
            hint: 'supersedes: on a baton is the conditional-live orientation-supersession field; it belongs only on a kind: spinoff install/orientation baton, not spinoff-roadmap. Distinct from the terminal memo supersedes:/superseded_by: coupling.'
          };
        }
        return null;
      },
    },
  ],

  // ---------------------------------------------------------------------------
  // cross-repo-memo cross-field rules
  // Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3
  // Prior spec: docs/plans/2026-05-21-cross-repo-memo-discoverability.md § Validator rules
  // code-review F8: updated primary backlink to the 2026-05-23 spec; 2026-05-21 retained as prior art.
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
    // code-review F1: 'actioned' is the SIMPLE-MODEL terminal (decision optional).
    // The receiver flips status: open → actioned in place (via Edit + commit).
    // No action_taken_at or decision is required — those are grandfathered fields
    // from the pre-2026-05-23 'action_taken' lifecycle.
    // 'action_taken' is a GRANDFATHERED-ONLY value — kept for backward compat only.
    // New memos MUST use 'actioned'; 'action_taken' retains its stricter cross-field
    // requirements (action_taken_at AND decision both required) to prevent data loss
    // on old memos that relied on those fields being present.

    // status: in_progress requires picked_up_by (claim attribution).
    // The open → in_progress → actioned lifecycle (2026-06-21 memo-pickup claim-lock parity):
    // in_progress is the receiver's at-pickup claim state, mirroring handoff deployment_state:
    // in_flight. picked_up_by makes the "who holds it" attribution non-optional in the one state
    // where it matters — without it an in_progress memo is claimed-by-nobody, defeating the
    // visibility half of the design. Symmetric with the action_taken/closed required-companion
    // rules below. Back-compat: open/actioned/grandfathered statuses are unaffected.
    // Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C2
    {
      check: (fm) => {
        if (fm.status !== 'in_progress') return null;
        if (!fm.picked_up_by || String(fm.picked_up_by).trim() === '') {
          return {
            field: 'picked_up_by',
            error: `required when status=in_progress`,
            hint: `Set picked_up_by to the claiming session id when a memo is claimed at pickup-start (status: in_progress). Cleared on release back to open.`
          };
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
    // summary length ≤120 chars when present.
    // The __skip__ grandfather guard above already returns [] for memos with
    // created < 2026-05-22, so this rule only fires for non-skipped post-cutoff
    // memos — no additional per-rule cutoff self-guard is needed here.
    // Spec backlink: docs/plans/2026-05-29-handoff-schema-category-summary.md § Chunk 1
    {
      check: (fm) => {
        if (fm.summary === undefined || fm.summary === null) return null;
        if (String(fm.summary).length > 120) {
          return {
            field: 'summary',
            error: `summary exceeds 120 characters (got ${String(fm.summary).length})`,
            hint: 'Keep summary to one concise line of 120 characters or fewer'
          };
        }
        return null;
      },
    },
    // kind enum validation — optional field; absent/undefined/null is VALID (back-compat).
    // When present, must be one of the pinned enum members: ask | consult | fyi.
    // 'ack' is NOT a valid kind — acknowledgement is receipt-state, not sender-declared kind.
    // Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § Pinned interface
    {
      check: (fm) => {
        if (fm.kind === undefined || fm.kind === null) return null;
        const validKinds = ['ask', 'consult', 'fyi'];
        if (!validKinds.includes(String(fm.kind))) {
          return {
            field: 'kind',
            error: `invalid enum value "${fm.kind}" for kind`,
            hint: `kind must be one of: ${validKinds.join(', ')}. Absent is also valid (reader applies 'ask' default). Note: 'ack' is not a kind — acknowledgement is receipt-state.`
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
  } else if (type === 'boolean') {
    // Review: code-reviewer — boolean fields (e.g. pickup_ready) were silently accepted as any type; now validated
    if (typeof value !== 'boolean') {
      return { field, error: `expected boolean, got ${typeof value}`, hint: 'Use bare true or false (no quotes)' };
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
  // A bracket token is a *candidate tag* only if it is tag-shaped: a single
  // bracket pair wrapping a bareword of lowercase letters with optional
  // hyphen-joined segments — the shape every real tag has. The enum values
  // (universal, project) are pure lowercase alpha, and a *typo* of a real tag
  // is too (univeral, projct), so a valid candidate tag never contains a digit
  // or an uppercase letter. Anything else is bracket prose and is ignored:
  //   [[wikilink]]  → captured as "[wikilink" (leading bracket fails ^[a-z])
  //   [11§L4]       → digit-initial (and § is outside the class)
  //   [1]           → digit-initial footnote
  //   [Smith2020]   → uppercase-initial citation key
  //   [v2] [h264]   → contain digits → not a tag shape (version refs, codecs)
  // Only candidate tags get allowlist-checked, so genuine invalid tags
  // ([univeral], [deprecated]) are still caught. This is an allowlist-shaped
  // guard, not a denylist of known-bad bracket forms: the latter grows a new
  // false positive every time someone invents a bracket convention.
  // Accepted miss: an uppercase-cased typo of a real tag ([Universal]) slips,
  // because catching it requires allowing uppercase-initial tokens, which
  // re-introduces the citation-key false positive — the more common case.
  const tagShapeRe = /^[a-z]+(?:-[a-z]+)*$/;
  // Strip inline code spans and markdown link text before tag-matching so
  // model-ID literals like `claude-opus-4-7[1m]`, array-ish prose like
  // `arr[0]`, and link text like `[some link](url)` are not mistaken for
  // tags. The code-span scanner walks the line character-by-character and
  // matches CommonMark-style runs: an opening backtick run of length N closes
  // on the next backtick run of identical length N. This handles nested /
  // mixed runs (e.g. ``weird`code``) that simple non-greedy regexes mis-strip.
  // NOTE: this strip pass deliberately does NOT collapse [[wikilink]] into its
  // inner text — wikilink immunity comes from the leading-bracket capture
  // artefact above (tagShapeRe rejects "[wikilink"). If a future change makes
  // the strip pass rewrite wikilinks to bare [text], reconfirm tagShapeRe still
  // rejects them, or the immunity is lost.

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!entryRe.test(line)) continue;

    // Collect all bracket-enclosed tokens on this line, ignoring those inside
    // code spans or markdown link text. matchAll yields a fresh iterator each
    // call, so there is no shared regex lastIndex to reset per line.
    const scrubbed = stripCodeSpansAndLinks(line);
    const tags = [];
    for (const m of scrubbed.matchAll(/\[([^\]]+)\]/g)) {
      // Only tag-shaped tokens are candidate tags; bracket prose is ignored.
      if (tagShapeRe.test(m[1])) tags.push(m[1]);
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
  _stripInlineComment: stripInlineComment,
};
