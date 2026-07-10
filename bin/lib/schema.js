'use strict';
/**
 * schema.js — frontmatter schema loader and validator for coordinator tracked records.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1
 *
 * Exports:
 *   loadSchemas(schemasDir)        → { [name]: schema, _byGlob: [{glob, schemaName}], _byKind: {kindValue: schemaName} }
 *   matchSchema(repoRel, frontmatter, schemas) → {schemaName, schema} | null  (kind-first, glob-fallback)
 *   matchSchemaForPath(repoRel, schemas) → {schemaName, schema} | null  (delegates to matchSchema with null frontmatter)
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
      // Value is null or a nested block on following lines.
      // Advance past blank and comment-only lines to find the first real line.
      // A blank line between a key and its indented nested block must NOT sever the block —
      // YAML does not end a nested mapping on a blank line.
      // Mirrors schema_loader.py A-F6 fix (2026-06-26 code-reviewer slice-A):
      //   was a single-line peek; now a loop that skips blank/comment lines.
      let nextLine = i + 1;
      while (nextLine < lines.length) {
        const peekRaw = lines[nextLine];
        const peekStripped = peekRaw.trim();
        if (peekStripped && !peekStripped.startsWith('#')) break;
        nextLine++;
      }
      if (nextLine < lines.length) {
        const nextRaw = lines[nextLine];
        const nextIndent = nextRaw.length - nextRaw.trimStart().length;
        if (nextIndent > indent) {
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

// Mapping-item discriminator: the slice after '- ' is a mapping key when it
// matches 'key:' or 'key: value'. A bare ':' in a URL (e.g. 'http://x') must
// NOT trigger the mapping path — guard with the key-shape regex, not bare includes(':').
const LIST_ITEM_MAPPING_RE = /^[A-Za-z0-9_-]+:(\s|$)/;

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
      const itemContent = trimmed.slice(2).trim();
      if (LIST_ITEM_MAPPING_RE.test(itemContent)) {
        // Mapping list item: parse the inline key and any continuation lines
        // that are indented deeper than the '- ' marker.
        // The continuation block starts at the column of the key (dashIndent + 2).
        const dashIndent = indent;
        const continuationIndent = dashIndent + 2;
        // Seed the object with the inline key from the '- key: value' line.
        // Reuse parseYamlLines by fabricating a one-line block for the inline pair.
        const inlineObj = parseYamlLines([itemContent], 0, 0).value;
        // Collect continuation lines indented deeper than the dash.
        // Review: code-reviewer F1 — removed dead `j` variable (was `i+1` used only to init `k`)
        const contLines = [];
        let k = i + 1;
        while (k < lines.length) {
          const contRaw = lines[k];
          const contTrimmed = contRaw.trimEnd();
          if (contTrimmed === '' || contTrimmed.trimStart().startsWith('#')) { k++; continue; }
          const contIndent = contRaw.length - contRaw.trimStart().length;
          if (contIndent >= continuationIndent) {
            contLines.push(contRaw);
            k++;
          } else {
            break;
          }
        }
        let obj = inlineObj;
        if (contLines.length > 0) {
          // Parse the continuation block. Normalise indentation so the first
          // continuation key aligns at column 0 for parseYamlLines.
          const strippedContLines = contLines.map(l => l.slice(continuationIndent));
          const contObj = parseYamlLines(strippedContLines, 0, 0).value;
          obj = Object.assign({}, inlineObj, contObj);
        }
        list.push(obj);
        i = k;
      } else {
        list.push(parseScalar(itemContent));
        i++;
      }
    } else if (trimmed === '-') {
      list.push(null);
      i++;
    } else {
      break;
    }
  }
  return list;
}

function skipPast(lines, start, baseIndent) {
  // Review: code-reviewer — align trimming with parseList: both now use raw.trimEnd().trimStart()
  // so indented comments and list items are handled identically in both functions.
  // Also advances past mapping-item continuation lines (lines indented deeper
  // than the '- ' marker) so the outer parser resumes at the correct position
  // after a list-of-maps block.
  let i = start;
  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trimEnd().trimStart();
    if (trimmed === '' || trimmed.startsWith('#')) { i++; continue; }
    const indent = raw.length - raw.trimStart().length;
    if (indent < baseIndent) break;
    if (trimmed.startsWith('- ') || trimmed === '-') {
      // Consume the dash line itself, then also consume any continuation lines
      // that are indented deeper than this dash (mapping-item sub-keys).
      const dashIndent = indent;
      i++;
      while (i < lines.length) {
        const contRaw = lines[i];
        const contTrimmed = contRaw.trimEnd();
        if (contTrimmed === '' || contTrimmed.trimStart().startsWith('#')) { i++; continue; }
        const contIndent = contRaw.length - contRaw.trimStart().length;
        if (contIndent > dashIndent) {
          i++;
        } else {
          break;
        }
      }
    } else {
      break;
    }
  }
  return i;
}

function parseInlineList(text) {
  // "[a, b, c]" → ['a', 'b', 'c']
  const inner = text.slice(1, -1);
  // Empty-list guard: `[]` must parse to [] without throwing.
  // blocks:/blocked_by:[] are pervasive in roadmap handoffs — do NOT remove this guard.
  // Mirrors schema_loader.py _parse_inline_list `if not inner.strip(): return []`.
  if (!inner.trim()) return [];
  const items = inner.split(',').map(s => parseScalar(s.trim()));
  // Fail loud on genuinely malformed items (trailing comma, gap between commas).
  // A real empty/null element indicates a parse error in the source YAML, not a valid empty list.
  // Mirrors schema_loader.py A-F4 fix (2026-06-26 code-reviewer slice-A).
  const bad = items.reduce((acc, v, idx) => (v === null || v === '') ? [...acc, idx] : acc, []);
  if (bad.length > 0) {
    throw new Error(
      `schema.js: malformed inline list — item(s) at position(s) [${bad.join(', ')}] ` +
      `parsed to null/empty in ${text}. ` +
      'Remediation: check the inline list for trailing commas or empty items.'
    );
  }
  return items;
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
 * (2026-05-28 example-game-repo-em → central-em): unstripped inline comments
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
      // A `#` is a YAML comment opener only when preceded by whitespace AND either
      // at end-of-string or followed by a space character. This preserves `#N` tokens
      // (issue numbers, hashtags) while still stripping genuine trailing comments of
      // the form `value  # comment text`.
      //
      // the Data Science Reviewer C-F6 / the Staff Engineer F5: before this fix, `title: Borrow #4 widgets` was
      // truncated to `"Borrow"` because the space before `#` fired the old rule.
      // Fix: also require the character after `#` to be a space (or end of string).
      if (i === 0 || /\s/.test(text[i - 1])) {
        // Review: F2 — accept tab as well as space after '#'; text[i+1] === ' ' missed '\t'.
        if (i + 1 >= text.length || /\s/.test(text[i + 1])) {
          return text.slice(0, i).trimEnd();
        }
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
  if (!isNaN(n) && isFinite(n) && text !== '' && String(n) === text) return n;
  // Strip surrounding quotes
  if (text.startsWith('"') && text.endsWith('"')) {
    return text.slice(1, -1);
  }
  if (text.startsWith("'") && text.endsWith("'")) {
    // YAML single-quoted escape: '' (two consecutive single-quotes) → a literal '.
    // Mirrors schema_loader.py _parse_scalar `inner.replace("''", "'")` (code-reviewer F4).
    return text.slice(1, -1).replace(/''/g, "'");
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
 * Dotfile-exclusion invariant: wildcards (*, **, ?) at a path-segment start do NOT match
 * a leading dot. This mirrors Unix shell globbing and pathlib.Path.glob semantics — dot-
 * prefixed files in a record directory are control/config artifacts, never corpus records.
 * A leading dot is matched only by an explicit literal '.' or a bracket class in the pattern.
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
  // segStart tracks whether the current scan position is at a path-segment boundary
  // (i.e. immediately after a '/' or at the start of the pattern). Wildcards at a
  // segment boundary must not match a leading dot — Unix shell / pathlib.Path.glob semantics.
  let segStart = true;
  while (i < p.length) {
    const c = p[i];
    if (c === '*' && p[i + 1] === '*') {
      re += segStart ? '(?!\\.).*' : '.*';
      i += 2;
      if (p[i] === '/') i++; // consume trailing slash after **
      segStart = true; // next token is at segment start
    } else if (c === '*') {
      re += segStart ? '(?!\\.)[^/]*' : '[^/]*';
      i++;
      segStart = false;
    } else if (c === '?') {
      re += segStart ? '[^/.]' : '[^/]';
      i++;
      segStart = false;
    } else if (c === '[') {
      // Pass bracket character-class through verbatim until the closing ']'.
      // This allows [0-9], [a-z], [abc] etc. to work as regex character-classes.
      // An unmatched '[' (no closing ']') falls through to literal-escape below.
      const closeIdx = p.indexOf(']', i + 1);
      if (closeIdx !== -1) {
        re += p.slice(i, closeIdx + 1);
        i = closeIdx + 1;
        segStart = false;
      } else {
        // No closing bracket — escape the '[' as a literal character.
        re += '\\[';
        i++;
        segStart = false;
      }
    } else if ('.+^${}()|\\'.includes(c)) {
      re += '\\' + c;
      i++;
      segStart = false;
    } else {
      re += c;
      i++;
      // A '/' resets to segment-start for the next character
      segStart = (c === '/');
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
 * Default match_mode for a schema that doesn't declare one explicitly.
 *
 * A schema whose applies_to glob targets .yaml/.json files is, by construction,
 * NOT a markdown-with-frontmatter record — there is no --- fence to find. Left
 * undefaulted, the validator's match_mode dispatch (validate-frontmatter-schema.js)
 * falls into its "missing frontmatter" branch and reports every required field as
 * absent — a false positive on every valid bare-YAML/JSON record. Defaulting such
 * schemas to whole-document-yaml treats the entire file as the record, matching
 * how these schemas are actually authored (e.g. improvement-queue.yaml, which sets
 * this explicitly). An explicit match_mode on the schema always wins — this only
 * fills the gap when the field is absent, and only for non-.md applies_to globs
 * (a markdown-frontmatter schema never targets .yaml/.json, so this cannot change
 * behavior for any schema whose records actually carry frontmatter).
 *
 * Spec backlink: commit 6c6fd3bd (default .yaml/.json schemas to whole-document-yaml)
 * (false-positive class: non-.md schema + no match_mode → all-fields-missing warning).
 * Review: code-reviewer — repointed off the ephemeral lesson-capture file (swept by
 * learn-lessons) onto the stable bugfix commit SHA.
 *
 * @param {object} parsed - the parsed schema object (mutated in place)
 */
function applyDefaultMatchMode(parsed) {
  if (parsed.match_mode) return;
  if (typeof parsed.applies_to !== 'string') return;
  if (/\.(yaml|json)$/i.test(parsed.applies_to)) {
    parsed.match_mode = 'whole-document-yaml';
  }
}

/**
 * Load all *.yaml schema files from schemasDir.
 * Returns { [schemaName]: parsedSchema, _byGlob: [{glob, schemaName}], _byKind: {kindValue: schemaName} }
 *
 * Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 1
 * Negative-spec: throws on duplicate kind ownership — detect-then-fail-loud, not detect-then-silently-pick.
 */
function loadSchemas(schemasDir) {
  const schemas = { _byGlob: [], _byKind: {} };
  const files = fs.readdirSync(schemasDir).filter(f => f.endsWith('.yaml'));
  for (const file of files) {
    const raw = fs.readFileSync(path.join(schemasDir, file), 'utf8');
    const parsed = parseYaml(raw);
    const name = parsed.schema || path.basename(file, '.yaml');
    // Review: code-reviewer (A-F11) — throw on duplicate schema NAME registration.
    // Previously only different-name+same-kind threw; a name collision silently overwrote.
    if (Object.prototype.hasOwnProperty.call(schemas, name) && name !== '_byGlob' && name !== '_byKind') {
      throw new Error(`duplicate schema name "${name}" — a schema with this name is already registered`);
    }
    schemas[name] = parsed;
    applyDefaultMatchMode(parsed);
    if (parsed.applies_to) {
      // Fix: applies_to must be a string glob pattern. An array value (from multi-home
      // proposals) throws `pattern.replace is not a function` deep in globToRegex.
      // Fail loud at load time so the author sees a clear error, not a runtime crash.
      // Source: improvement-queue 2026-06-27-coordinator-schema-js-loadschemas-does-n
      if (typeof parsed.applies_to !== 'string') {
        throw new Error(
          `schema "${name}": applies_to must be a string glob pattern, ` +
          `got ${Array.isArray(parsed.applies_to) ? 'array' : typeof parsed.applies_to}. ` +
          `To cover multiple locations, use a brace-expansion glob or register separate schema files.`
        );
      }
      schemas._byGlob.push({ glob: parsed.applies_to, schemaName: name });
    }
    // Build _byKind index from kinds: (array) or kind: (string) field.
    // Fail loud on duplicate kind ownership — a copy-paste duplicate would otherwise
    // be a silent first-win, mis-routing a whole artifact family.
    const kindValues = [];
    if (Array.isArray(parsed.kinds)) {
      for (const v of parsed.kinds) {
        // Review: code-reviewer (S1-F11) — String(v) would coerce null/number/bool silently;
        // filter to non-empty strings only and warn on skipped elements.
        if (typeof v === 'string' && v.length > 0) {
          kindValues.push(v);
        } else {
          process.stderr.write(`schema "${name}": skipping non-string kinds element: ${JSON.stringify(v)}\n`);
        }
      }
    } else if (typeof parsed.kind === 'string') {
      kindValues.push(parsed.kind);
    }
    // Review: code-reviewer (S1-F2) — within-schema duplicate kind check.
    // A schema that lists the same kind twice in its own kinds: array is a copy-paste error.
    if (new Set(kindValues).size !== kindValues.length) {
      throw new Error(`schema "${name}" declares a duplicate kind in its own kinds: list`);
    }
    // Review: code-reviewer (S1-F9) — warn when a schema declares kinds/kind but no applies_to.
    // It will be kind-validated but invisible to query-records enumeration.
    if (kindValues.length > 0 && !parsed.applies_to) {
      process.stderr.write(`schema "${name}": declares kinds/kind but has no applies_to — will be kind-validated but not enumerated by query-records\n`);
    }
    for (const kindValue of kindValues) {
      if (schemas._byKind[kindValue] !== undefined && schemas._byKind[kindValue] !== name) {
        throw new Error(
          `duplicate kind "${kindValue}" declared by both ${schemas._byKind[kindValue]} and ${name}`
        );
      }
      schemas._byKind[kindValue] = name;
    }
  }
  // Dual-format loader: also read .schema.json (JSON Schema draft-2020-12 subset).
  // During the ccos-1 migration waves, .yaml and .schema.json schemas coexist in schemasDir;
  // a record type is validated by whichever schema file exists for it.
  // .schema.json files are also entered into _jsonSchemaCache for the validateRecord string-name path.
  //
  // W2.5 ccos-1: .schema.json files now fully participate in the path-based lint flow:
  //   - applies_to is registered in _byGlob (mirrors the .yaml branch at lines ~391-403)
  //   - a non-enumerable _isJsonSchema marker is stamped on the parsed object so
  //     validateFrontmatterDispatch can route to the JSON path without inspecting
  //     the schema's internal field shapes.
  //
  // Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2.5
  const jsonSchemaFiles = fs.readdirSync(schemasDir).filter(f => f.endsWith('.schema.json'));
  for (const jsFile of jsonSchemaFiles) {
    let parsed;
    try {
      parsed = JSON.parse(fs.readFileSync(path.join(schemasDir, jsFile), 'utf8'));
    } catch (e) {
      throw new Error(`schema file "${jsFile}" is not valid JSON: ${e.message}`);
    }
    const name = (typeof parsed['x-schema-name'] === 'string' && parsed['x-schema-name'])
      ? parsed['x-schema-name']
      : path.basename(jsFile, '.schema.json');

    // Stamp the non-enumerable _isJsonSchema marker BEFORE registering in schemas[],
    // so any reader of schemas[name] sees it without special-casing the file extension.
    Object.defineProperty(parsed, '_isJsonSchema', {
      value: true,
      enumerable: false,
      writable: false,
      configurable: true,
    });

    // Review: code-reviewer (A-F11) — throw on duplicate schema NAME registration.
    // Mirrors the .yaml branch check above; a name collision silently overwrote.
    if (Object.prototype.hasOwnProperty.call(schemas, name) && name !== '_byGlob' && name !== '_byKind') {
      throw new Error(`duplicate schema name "${name}" — a schema with this name is already registered`);
    }
    schemas[name] = parsed;
    _jsonSchemaCache[name] = parsed;
    applyDefaultMatchMode(parsed);

    // Register applies_to in _byGlob so matchSchemaForPath and collectFilesForGlob
    // can map file paths to this JSON-Schema-backed schema (mirrors the .yaml branch).
    if (typeof parsed.applies_to === 'string' && parsed.applies_to) {
      schemas._byGlob.push({ glob: parsed.applies_to, schemaName: name });
    }

    // Build _byKind index from x-kinds: (array) / x-kind: (string) / kinds: (array) / kind: (string).
    // .schema.json files may use either the x- prefix (JSON Schema extension convention)
    // or the bare keys matching .yaml dialect. Both forms are supported.
    // Mirrors the .yaml branch kind-registration logic (lines ~409-439).
    // Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W4 fix
    const jsonKindValues = [];
    const rawKindsArr = Array.isArray(parsed['x-kinds']) ? parsed['x-kinds']
      : Array.isArray(parsed['kinds']) ? parsed['kinds']
      : null;
    const rawKindStr = typeof parsed['x-kind'] === 'string' ? parsed['x-kind']
      : typeof parsed['kind'] === 'string' ? parsed['kind']
      : null;
    if (rawKindsArr !== null) {
      for (const v of rawKindsArr) {
        if (typeof v === 'string' && v.length > 0) {
          jsonKindValues.push(v);
        } else {
          process.stderr.write(`schema "${name}": skipping non-string x-kinds/kinds element: ${JSON.stringify(v)}\n`);
        }
      }
    } else if (rawKindStr !== null) {
      jsonKindValues.push(rawKindStr);
    }
    // Within-schema duplicate check (same as .yaml branch).
    if (new Set(jsonKindValues).size !== jsonKindValues.length) {
      throw new Error(`schema "${name}" declares a duplicate kind in its own x-kinds/kinds list`);
    }
    if (jsonKindValues.length > 0 && !parsed.applies_to) {
      process.stderr.write(`schema "${name}": declares x-kinds/kinds but has no applies_to — will be kind-validated but not enumerated by query-records\n`);
    }
    for (const kindValue of jsonKindValues) {
      if (schemas._byKind[kindValue] !== undefined && schemas._byKind[kindValue] !== name) {
        throw new Error(
          `duplicate kind "${kindValue}" declared by both ${schemas._byKind[kindValue]} and ${name}`
        );
      }
      schemas._byKind[kindValue] = name;
    }
  }

  // Sort _byGlob so more-specific globs are tried first by matchSchema.
  // Without a sort, registration order determines priority — .yaml schemas load before
  // .schema.json schemas, so a broad .yaml glob (docs/plans/*.md) beats a narrow
  // .schema.json glob (docs/plans/*.docs-check.md) even though the latter is more specific.
  //
  // Specificity rule: fewer wildcards wins; on tie, longer pattern wins (more literal chars).
  // This correctly resolves docs/plans/*.docs-check.md over docs/plans/*.md.
  //
  // W2.5 ccos-1 latent-bug fix: first-match on unsorted _byGlob caused the plan schema to
  // shadow docs-check-sidecar for *.docs-check.md paths; sort stabilises specificity.
  schemas._byGlob.sort((a, b) => {
    const wcA = (a.glob.match(/\*/g) || []).length;
    const wcB = (b.glob.match(/\*/g) || []).length;
    if (wcA !== wcB) return wcA - wcB;
    return b.glob.length - a.glob.length;
  });

  return schemas;
}

/**
 * Resolve schema for a file using kind-first, glob-fallback strategy.
 *
 * Resolution order:
 *   (a) If frontmatter is non-null and frontmatter.kind maps to a schema via _byKind → return it.
 *   (b) Otherwise fall back to the existing glob logic (_byGlob first-match).
 *
 * A file is matched if EITHER its kind maps to a schema OR a glob matches its path.
 * Returns {schemaName, schema} or null.
 *
 * Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 1
 */
function matchSchema(repoRelPath, frontmatter, schemas) {
  // (a) Kind-first: if frontmatter carries a kind: field and _byKind has it, return immediately.
  // null kind: is not a valid discriminator — falls through to glob-fallback.
  if (frontmatter !== null && frontmatter !== undefined && frontmatter.kind !== undefined && frontmatter.kind !== null) {
    const kindValue = String(frontmatter.kind);
    const schemaName = schemas._byKind[kindValue];
    if (schemaName !== undefined) {
      return { schemaName, schema: schemas[schemaName] };
    }
  }
  // (b) Glob-fallback: existing matchSchemaForPath logic.
  const normalised = repoRelPath.replace(/\\/g, '/');
  for (const { glob, schemaName } of schemas._byGlob) {
    if (matchGlob(glob, normalised)) {
      return { schemaName, schema: schemas[schemaName] };
    }
  }
  return null;
}

/**
 * Find the schema that matches repoRelPath (path-only, no frontmatter).
 * repoRelPath should use forward slashes (e.g. "state/handoffs/foo.md").
 * Returns {schemaName, schema} or null.
 *
 * Delegates to matchSchema with null frontmatter — all existing callers continue to work.
 */
function matchSchemaForPath(repoRelPath, schemas) {
  return matchSchema(repoRelPath, null, schemas);
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

// ---------------------------------------------------------------------------
// Write-side frontmatter primitives — canonical home, consumed by
// handoff-transition.js, memo-transition.js, normalize-consumed-frontmatter.js,
// stamp-shipped-in.js. Reconciled 2026-07-09 from 4 divergent copies (the Staff Engineer
// review) into one implementation each; see docs/plans backlink on the
// consuming CLIs for the extraction plan. Unlike parseFrontmatter (which
// parses the YAML into an object for read access), these operate on the raw
// frontmatter TEXT so a targeted field edit can be applied without disturbing
// key order, comments, or quoting style of every other line.
// ---------------------------------------------------------------------------

/**
 * splitFrontmatter — split raw file content into { preamble, fmText, bodyWithLeadingNewline }.
 * Tolerates an optional leading preamble (blank lines + complete HTML comment
 * blocks) before the opening `---`; installer-seeded batons carry a provenance
 * comment ahead of the frontmatter. The preamble is captured verbatim and must
 * be reassembled by the caller on write so provenance survives the edit.
 * Returns null when no valid `---`-delimited frontmatter block is found.
 */
function splitFrontmatter(content) {
  let preamble = '';
  if (!content.startsWith('---')) {
    const pre = /^(?:[ \t]*\r?\n|[ \t]*<!--[\s\S]*?-->[ \t]*\r?\n?)+/.exec(content);
    if (!pre) return null;
    const after = content.slice(pre[0].length);
    if (!after.startsWith('---')) return null;
    preamble = pre[0];
    content = after;
  }
  const afterFirst = content.slice(3);
  const firstNewline = afterFirst.indexOf('\n');
  if (firstNewline === -1) return null;
  const rest = afterFirst.slice(firstNewline + 1);
  // [ \t]* (not \s*) — \s eats newlines and would consume the body's leading blank line.
  const closeRe = /^---[ \t]*$/m;
  const closeMatch = closeRe.exec(rest);
  if (!closeMatch) return null;
  const fmText = rest.slice(0, closeMatch.index);
  const bodyStart = closeMatch.index + closeMatch[0].length;
  // Preserve everything after the closing --- including the trailing newline,
  // so the reassembled file is byte-identical except for the frontmatter edits.
  const bodyWithLeadingNewline = rest.slice(bodyStart);
  return { preamble, fmText, bodyWithLeadingNewline };
}

/**
 * escapeRegExp — escape regex metacharacters in a string so it can be safely
 * interpolated into a `new RegExp(...)` source as a literal match.
 * Review: code-reviewer A-F2 — key/afterKey were spliced into RegExp sources
 * unescaped; every current caller passes a hardcoded literal key so this was
 * not exploitable today, but this is now the canonical shared primitive other
 * CLIs repoint at, and a future schema-driven key name would silently
 * construct a malformed/wrong regex without this guard.
 */
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * unquoteScalar — strip a single matched pair of leading/trailing YAML quote
 * characters from a raw (unparsed) scalar text, mirroring parseScalar's
 * unquoting (including the `''` single-quote escape unfold). No-op when the
 * text is not a matched quoted pair.
 */
function unquoteScalar(text) {
  if (text.length >= 2 && text.startsWith('"') && text.endsWith('"')) {
    return text.slice(1, -1);
  }
  if (text.length >= 2 && text.startsWith("'") && text.endsWith("'")) {
    return text.slice(1, -1).replace(/''/g, "'");
  }
  return text;
}

/**
 * readFmField — read a single-line YAML frontmatter field value by key from
 * raw frontmatter text. Returns the trimmed value string, or null when the
 * key is absent. Boundary lookahead `(?=[ \t]|$)` after the key name prevents
 * a key matching a longer key's prefix (e.g. `status` must not match
 * `status_message:`). Quote-aware: a matched pair of surrounding `"..."` or
 * `'...'` quotes is stripped (mirroring parseScalar's unquoting) so a
 * `status: "draft"` line round-trips identically to `status: draft` for
 * callers comparing against an unquoted enum.
 * Review: code-reviewer A-F3 — without this, a quoted scalar value made
 * plan-status-transition.js's TERMINAL_STATUSES/FLIPPABLE_STATUSES set lookup
 * silently fail on an otherwise well-formed plan.
 */
function readFmField(fmText, key) {
  const re = new RegExp('^' + escapeRegExp(key) + ':(?=[ \\t]|$)\\s*(.*?)\\s*$', 'm');
  const m = re.exec(fmText);
  return m ? unquoteScalar(m[1].trim()) : null;
}

/**
 * serializeYamlScalar — single-quote a YAML scalar value when it contains
 * characters/shapes that YAML would misinterpret as structure or a different
 * type: structural characters (conservative — quotes on ANY `#`, not just
 * whitespace-preceded, so SHA IDs aren't misread as inline comments), a
 * leading `-`/`?`/space, an all-numeric string (would parse as an integer —
 * e.g. a SHA-shaped value like "274671833"), or YAML 1.1 scientific-notation
 * float shape (e.g. "1958e194"). Internal single quotes are escaped by
 * doubling (`'` → `''`).
 */
function serializeYamlScalar(value) {
  const needsQuoting = /[#:{}\[\],&*!|>"'%@`]/.test(value) ||
                       value.startsWith('-') ||
                       value.startsWith('?') ||
                       value.startsWith(' ') ||
                       /^[0-9]+$/.test(value) ||
                       /^[0-9]+[eE][0-9]+$/.test(value);
  if (!needsQuoting) return value;
  return `'${value.replace(/'/g, "''")}'`;
}

/**
 * replaceFmField — replace the value of an existing `key:` line in raw
 * frontmatter text, preserving every other line (order, comments, unrelated
 * quoting) untouched. Throws when the current value is a YAML block scalar
 * (`>` or `|`) rather than silently truncating a folded/literal multi-line
 * value into a single line — fix the frontmatter manually in that case.
 * Boundary lookahead on `key:` guards against prefix-collision the same way
 * readFmField does.
 */
function replaceFmField(fmText, key, value) {
  const currentValue = readFmField(fmText, key);
  if (currentValue !== null && (currentValue.startsWith('>') || currentValue.startsWith('|'))) {
    throw new Error(
      `replaceFmField: field "${key}" uses a block-scalar YAML value ` +
      `("${currentValue.length > 40 ? currentValue.slice(0, 40) + '...' : currentValue}") — cannot safely replace single-line. ` +
      `Fix the frontmatter manually.`
    );
  }
  const re = new RegExp('^(' + escapeRegExp(key) + ':(?=[ \\t]|$)\\s*).*$', 'm');
  // Review: code-reviewer A-F1 — replacer FUNCTION, not a replacement-pattern string.
  // `$1${x}` treats `$1`/`$&`/`$$` inside x as replace()'s special tokens, silently
  // corrupting any value containing a literal dollar sign. A function return value
  // is never re-interpreted for `$`-patterns.
  return fmText.replace(re, (_, g1) => g1 + serializeYamlScalar(value));
}

/**
 * removeFmField — remove the `key: ...` line (and its trailing newline)
 * entirely from raw frontmatter text. Boundary lookahead `(?=[ \t]|$)` on the
 * key guards against the same prefix-collision hazard readFmField/
 * replaceFmField/insertFmField guard against (e.g. `gate_dependency` must not
 * match a hypothetical longer sibling key). The trailing `(?:\r?\n)?` is safe
 * when the key is the last line of frontmatter (no trailing newline).
 * Review: code-reviewer B-F1 — consolidated from 3 divergent local copies
 * (handoff-transition.js, memo-transition.js, normalize-consumed-frontmatter.js),
 * one of which (normalize-consumed-frontmatter.js) lacked the boundary
 * lookahead this reconciliation was meant to eliminate everywhere.
 */
function removeFmField(fmText, key) {
  const re = new RegExp('^' + escapeRegExp(key) + ':(?=[ \\t]|$).*(?:\\r?\\n)?', 'm');
  return fmText.replace(re, '');
}

/**
 * insertFmField — insert `key: value` immediately after the line matching
 * `afterKey:` in raw frontmatter text. Appends to the end of the frontmatter
 * block when `afterKey` is not present. Boundary lookahead on `afterKey:`
 * guards against prefix-collision the same way readFmField does.
 */
function insertFmField(fmText, key, value, afterKey) {
  const afterRe = new RegExp('^' + escapeRegExp(afterKey) + ':(?=[ \\t]|$).*$', 'm');
  const m = afterRe.exec(fmText);
  if (m) {
    const insertAt = m.index + m[0].length;
    return fmText.slice(0, insertAt) + `\n${key}: ${serializeYamlScalar(value)}` + fmText.slice(insertAt);
  }
  const trimmed = fmText.replace(/\s+$/, '');
  return `${trimmed}\n${key}: ${serializeYamlScalar(value)}\n`;
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
 *   - string (legacy):            "string" | "iso-date" | "number" | "boolean" | "object"
 *   // Review: code-reviewer (A-F13) — "bool" corrected to "boolean" to match checkType() runtime check.
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
  // JSON-Schema-backed schemas (stamped with _isJsonSchema by loadSchemas) route to
  // validateRecord, which runs the JSON Schema subset validator then cross-field rules.
  // This handles ccos-1 W4 migrated schemas transparently for existing call sites that
  // pass a SCHEMAS['name'] object directly (e.g. schema.test.js validateFrontmatter — plan/
  // decision/review suites). The YAML-dialect path below is unchanged.
  // Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W4 fix (RC2)
  if (isJsonSchemaBacked(schema)) {
    const record = (frontmatter !== null && frontmatter !== undefined) ? frontmatter : {};
    const result = validateRecord(record, schema);
    return result.ok ? { ok: true } : { ok: false, errors: result.errors };
  }

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
    // Accepts BOTH the object form `{type: 'string-or-null'}` AND the bare-string form
    // `'string-or-null'` (as review-trail.yaml writes `workstream: string-or-null`).
    // Mirrors the Python validate() behavior: a key present with null value is NOT missing.
    // Spec: drift-5 fix (2026-06-27, C1 dual-yaml-parser option-d).
    const isStringOrNull = (spec && typeof spec === 'object' && spec.type === 'string-or-null') ||
                           spec === 'string-or-null';
    const isNumberOrNull = (spec && typeof spec === 'object' && spec.type === 'number-or-null') ||
                           spec === 'number-or-null';
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
    // Follow-up (not yet implemented): a cross-field rule requiring recovers_session to be
    // non-null when kind=recovery would close the loop on crash-recovery batons always naming
    // the session they reconstruct. Deferred — see schemas/handoff.schema.json recovers_session description.
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
      // Graph-primitive gate: blocks/blocked_by/roadmap_id are permitted ONLY on kind=spinoff-roadmap.
      // Negative-spec: kind=spinoff-roadmap-creator !== kind=spinoff-roadmap, so this gate correctly
      // rejects graph primitives on spinoff-roadmap-creator. A roadmap-creator baton is the session that
      // produces the roadmap stubs (kind=spinoff-roadmap); it is not itself a stub and does not carry
      // the graph-primitive fields. Do NOT loosen this gate to include spinoff-roadmap-creator.
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
        const required = ['roadmap_id', 'stub_id', 'wave', 'blocks', 'blocked_by'];
        const missing = required.filter(f => fm[f] === undefined || fm[f] === null);
        if (missing.length > 0) {
          return {
            field: missing.join(', '),
            error: `required for kind=spinoff-roadmap`,
            hint: 'Roadmap stubs must declare their identifier (roadmap_id, stub_id), serialization order (wave), and graph edges (blocks, blocked_by — empty list ok). See skills/roadmap-planning/SKILL.md § Phase 2.1.'
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
    // cost enum (the Staff Engineer P2-4, 2026-05-08): when present, must be one of T0/T1/T2/T3.
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
        // Review: code-reviewer F11 — comparison is string-lexicographic; safe for ISO dates
        // (YYYY-MM-DD and YYYY-MM-DDTHH:MM:SSZ). Non-ISO created values absent in post-2026-04 corpus.
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
        // Review: code-reviewer F11 — lexicographic comparison safe for ISO YYYY-MM-DD / datetime.
        if (fm.created && String(fm.created) < '2026-05-29') return null;
        if (!fm.summary || String(fm.summary).trim() === '') {
          return {
            field: 'summary',
            error: 'required for handoffs created on or after 2026-05-29',
            hint: 'Add a one-line summary (≤140 chars) describing the session work'
          };
        }
        return null;
      },
    },
    // (c) summary length ≤140 chars when present (post-cutoff self-guard).
    {
      check: (fm) => {
        // Self-guard: skip for pre-cutoff handoffs.
        // Review: code-reviewer F11 — lexicographic comparison safe for ISO YYYY-MM-DD / datetime.
        if (fm.created && String(fm.created) < '2026-05-29') return null;
        if (fm.summary && String(fm.summary).length > 140) {
          return {
            field: 'summary',
            error: `summary exceeds 140 characters (got ${String(fm.summary).length})`,
            hint: 'Keep summary to one concise line of 140 characters or fewer'
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
    // ---------------------------------------------------------------------------
    // example-initiative tc-4 A3a — three additive cross-field rules (Ask-2 fold).
    // ADDITIVE-ONLY: no new required: fields; rules are cross-field guards on
    // existing optional fields with per-rule guards so legacy and manual-consume
    // corpus variants are never false-redded.
    //
    // Spec backlink: docs/plans/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk A3a
    // Design decisions: D5 (reuse schema.js, no parallel logic); additive-only per
    //   docs/wiki/canonical-artifact-shapes.md § C2.
    // ---------------------------------------------------------------------------

    // Rule A3a-1: status:consumed ⇒ consumed_by non-empty.
    // PRESENCE-GUARDED on consumed_at: fires ONLY when consumed_at is present.
    // consumed_by is a TRANSITION-TIME invariant enforced by cs_consume_handoff;
    // it is NOT a corpus invariant — legitimate handoffs that were consumed
    // manually (before the tool existed) have status:consumed with neither
    // consumed_at nor consumed_by. A date-cutoff guard is provably insufficient:
    // the 2026-06-22 roadmap-stub handoffs are post-cutoff and consumed without
    // either field. The consumed_at presence guard correctly skips all of them.
    // Negative-spec: do NOT add consumed_by to required: — that tightens the
    // schema against existing corpus artifacts (canonical-artifact-shapes.md C2).
    {
      check: (fm) => {
        if (fm.status !== 'consumed') return null;
        // Guard: only enforce when consumed_at is present (evidencing tool-driven consume).
        if (!fm.consumed_at) return null;
        if (!fm.consumed_by || String(fm.consumed_by).trim() === '') {
          return {
            field: 'consumed_by',
            error: 'required when status=consumed and consumed_at is present',
            hint: 'consumed_by identifies the consuming session (from --session-id). It is written by cs_consume_handoff; absent here indicates a partial or hand-edited consume. Set consumed_by to the session id.'
          };
        }
        return null;
      },
    },

    // Rule A3a-2: deployment_state:shipped ⇒ shipped_in non-empty.
    // DATE-GUARDED: fires only when created >= 2026-05-29. Pre-cutoff corpus
    // contains legitimate shipped handoffs that predate the shipped_in convention.
    // Guard fires on the field `created` (required on handoffs); if created is
    // absent (legacy) the guard is undefined → falsy → skipped (safe default).
    {
      check: (fm) => {
        if (fm.deployment_state !== 'shipped') return null;
        // Date guard: skip for pre-cutoff handoffs (legacy, pre-shipped_in convention).
        // Review: code-reviewer F11 — lexicographic comparison is safe for ISO dates
        // (YYYY-MM-DD and YYYY-MM-DDTHH:MM:SSZ). Non-ISO created absent in post-2026-04 corpus.
        if (!fm.created || String(fm.created) < '2026-05-29') return null;
        if (!fm.shipped_in || String(fm.shipped_in).trim() === '') {
          return {
            field: 'shipped_in',
            error: 'required when deployment_state=shipped (for handoffs created on or after 2026-05-29)',
            hint: 'Set shipped_in to the commit SHA or plan path where this work landed. Written by /workstream-complete or /handoff on transition to shipped.'
          };
        }
        return null;
      },
    },

    // Rule A3a-2b (C4b): shipped_in SHAPE guard — mirrors realized_by's
    // /^[0-9a-fA-F]{7,64}$/ regex (schema.js's cross-repo-memo block above).
    // DATE-GUARDED identically to Rule A3a-2 (fires only when created >= 2026-05-29)
    // so the pre-cutoff corpus (which predates the shipped_in convention entirely,
    // including the one known malformed legacy outlier) is not retroactively broken.
    //
    // Accepts EITHER a bare hex SHA (7-64 chars) OR the sanctioned stealth-skip
    // token `substantively-shipped-no-commit:<YYYY-MM-DD>`. This mechanizes pickup
    // Step 3f (stealth-skip / rationale-prose defer detection), previously pure
    // EM-judgment prose with no code behind it.
    //
    // Negative-spec: the token pattern validates the WHOLE value including the
    // date suffix (^...$-anchored) — it does NOT accept-anything-after-the-colon.
    // An unvalidated free-text suffix would reopen the exact prose-injection hole
    // this rule closes, one field-position to the right (the Staff Engineer F6).
    // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C4b
    {
      check: (fm) => {
        if (fm.deployment_state !== 'shipped') return null;
        if (!fm.created || String(fm.created) < '2026-05-29') return null;
        const v = fm.shipped_in == null ? '' : String(fm.shipped_in).trim();
        if (v === '') return null; // absence already caught by Rule A3a-2 above
        const wellFormed = /^[0-9a-fA-F]{7,64}$/.test(v) ||
          /^substantively-shipped-no-commit:\d{4}-\d{2}-\d{2}$/.test(v);
        if (!wellFormed) {
          return {
            field: 'shipped_in',
            error: `malformed shipped_in "${v}" — must be a bare commit SHA or the substantively-shipped-no-commit:<YYYY-MM-DD> token`,
            hint: `shipped_in must be one of: a hex commit SHA (7-64 hex chars, no annotation/brackets/prose), or the exact token substantively-shipped-no-commit:<YYYY-MM-DD> with a valid ISO date and nothing else. Prose rationale and annotated SHAs (e.g. "[~/.claude] f4f150a1d") are rejected.`
          };
        }
        return null;
      },
    },

    // Rule A3a-3: kind:spinoff|spinoff-goal|spinoff-roadmap-creator ⇒ predecessor === 'none' (or null).
    // These three kinds are all forks authored mid-session by the current EM; they have no
    // predecessor handoff to continue. predecessor: null is also accepted (same
    // semantic — no predecessor). Non-none string predecessors indicate a
    // mis-authored spinoff that should be a session-handoff continuation instead.
    // No date guard needed: the spinoff kind itself is the sufficient condition.
    // Negative-spec: predecessor: undefined (missing) is caught by the required-
    // field check in validateFrontmatter; this rule skips undefined to avoid a
    // redundant error alongside the required-field error.
    // spinoff-goal and spinoff-roadmap-creator are added 2026-07-07 as sister fork kinds;
    // they share the predecessor:none-by-design contract of kind:spinoff (DR-013/014).
    {
      check: (fm) => {
        const spinoffKinds = ['spinoff', 'spinoff-goal', 'spinoff-roadmap-creator'];
        if (!spinoffKinds.includes(fm.kind)) return null;
        const pred = fm.predecessor;
        // undefined (missing field): required-field validator catches it; skip here.
        // null: explicitly "no predecessor" — valid for spinoffs.
        // 'none': canonical sentinel for spinoffs.
        if (pred === undefined || pred === null || pred === 'none') return null;
        return {
          field: 'predecessor',
          error: `must be "none" or null for kind=${fm.kind} (got "${pred}")`,
          hint: 'Spinoff kinds (spinoff, spinoff-goal, spinoff-roadmap-creator) fork from the current session and have no predecessor baton to continue. Set predecessor: none (or null). If this is a continuation, use kind: session-handoff instead.'
        };
      },
    },

    // ---------------------------------------------------------------------------
    // DAG fan-in / fan-out fields (2026-06-29).
    //
    // Two additive optional fields extend the handoff lineage DAG with explicit
    // secondary edges beyond the single-spine `predecessor`:
    //
    //   additional_predecessors: [string]  — fan-in merge edges (LoE-aggregated when
    //     used with walkForward edgeKinds={predecessor,additional_predecessors}).
    //
    //   forked_from: string  — spinoff branch-point ancestry (lineage/render-only;
    //     NOT followed by the LoE primitive per DR-014 effort-isolation).
    //
    // Two cross-field rules govern them:
    //   (a) forked_from kind-gate: spinoff-only. A non-spinoff handoff with forked_from
    //       misrepresents its DAG position. A3a-3 (above) is UNCHANGED — it governs only
    //       the primary `predecessor` field; forked_from is governed here exclusively.
    //   (b) additional_predecessors integrity: array-of-string shape (covered by JSON
    //       Schema `type: array, items: string`); plus cross-field semantic guards:
    //       no duplicate entries within the array (self-reference); no entry duplicating
    //       the primary predecessor field.
    //
    // Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C1
    // ---------------------------------------------------------------------------

    // (a) forked_from kind-gate: permitted only on kind=spinoff.
    // Rationale for spinoff-only: forked_from records the branch-point ancestry of a
    // spinoff baton in the handoff DAG — it is the EM-authored record of "I forked from
    // session X's baton". Only spinoff handoffs represent forks; session-handoff,
    // spinoff-roadmap, and recovery kinds do not have a fork-branch-point concept.
    // Governed by this dedicated kind-gate, NOT by Rule A3a-3 (which checks only
    // the primary predecessor field and must remain unchanged per plan constraint).
    //
    // Negative-spec (spinoff-goal, spinoff-roadmap-creator): these two kinds are also
    // fork kinds (predecessor:none-by-design, Rule A3a-3), but they are intentionally
    // excluded from the forked_from allowlist. Goal-scoped and roadmap-creator sessions
    // are born from a PM directive, not from a running session's baton, so there is no
    // branch-point ancestry to record. They carry no lineage DAG edge beyond the session
    // boundary; forked_from is a spinoff-only DAG primitive.
    // Review: code-reviewer — F3 negative-spec documentation added (2026-07-07)
    {
      check: (fm) => {
        if (fm.forked_from === undefined || fm.forked_from === null || String(fm.forked_from).trim() === '') {
          return null;
        }
        if (fm.kind !== 'spinoff') {
          return {
            field: 'forked_from',
            error: `permitted only when kind=spinoff (current kind: ${fm.kind || 'unset'})`,
            hint: 'forked_from records the branch-point ancestry for spinoff lineage/rendering. Set kind: spinoff or remove forked_from. spinoff-goal and spinoff-roadmap-creator do not carry fork ancestry (PM-directive origin, no baton branch-point).'
          };
        }
        return null;
      },
    },

    // ---------------------------------------------------------------------------
    // Deliverable-spine identity field guards (2026-07-03).
    //
    // deliverable_id format: when present and non-null, must begin with 'dlv-'.
    // This is the carry-not-remint guard — a correctly inherited or minted id
    // always has the 'dlv-' prefix. A value without the prefix indicates a
    // hand-authored value that was not produced by mint-deliverable-id.sh.
    //
    // initiative FK non-empty: when present and non-null, must be a non-empty
    // string (a valid initiative id like 'delphi-pro-launch'). The null case
    // is the correct signal for "no initiative" — an empty string is never valid.
    //
    // Spec backlink: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § D1, D2
    // ---------------------------------------------------------------------------

    // deliverable_id format guard: present and non-null → must start with 'dlv-'.
    {
      check: (fm) => {
        if (fm.deliverable_id === undefined || fm.deliverable_id === null) return null;
        if (!String(fm.deliverable_id).startsWith('dlv-')) {
          return {
            field: 'deliverable_id',
            error: `deliverable_id "${fm.deliverable_id}" does not begin with "dlv-"`,
            hint: 'deliverable_id is minted by bin/mint-deliverable-id.sh and always begins with "dlv-". Inherit the id from the parent artifact (plan or roadmap stub); do not hand-author a value without the prefix.'
          };
        }
        return null;
      },
    },

    // initiative FK non-empty: present and non-null → must be a non-empty string.
    {
      check: (fm) => {
        if (fm.initiative === undefined || fm.initiative === null) return null;
        if (String(fm.initiative).trim() === '') {
          return {
            field: 'initiative',
            error: 'initiative FK must be a non-empty string when present and non-null',
            hint: 'Set initiative to a valid initiative id (e.g. "delphi-pro-launch") from state/initiatives/<id>.yaml, or null if this work does not belong to a named initiative.'
          };
        }
        return null;
      },
    },

    // (b) additional_predecessors integrity guards.
    // Shape (array-of-string) is enforced by the JSON Schema property definition.
    // These cross-field rules add semantic guards on top:
    //   — no duplicate entries within the array (self-reference guard): having the same
    //     predecessor path listed twice is an authoring error with no useful semantics.
    //   — no entry duplicating the primary predecessor field: the primary predecessor is
    //     already tracked via predecessor:; duplicating it in additional_predecessors
    //     would cause the LoE aggregator to double-count the path on fan-in traversal.
    {
      check: (fm) => {
        if (fm.additional_predecessors === undefined || fm.additional_predecessors === null) return null;
        const ap = fm.additional_predecessors;
        // Belt-and-suspenders array check (JSON Schema covers this; guard here for
        // cross-field rule callers that may bypass JSON Schema shape validation).
        if (!Array.isArray(ap)) {
          return {
            field: 'additional_predecessors',
            error: 'must be an array of strings',
            hint: 'Use YAML list syntax for additional_predecessors, e.g. ["state/handoffs/foo.md"]'
          };
        }
        // No self-reference: no duplicate entries within the array.
        const seen = new Set();
        for (const entry of ap) {
          if (seen.has(entry)) {
            return {
              field: 'additional_predecessors',
              error: `duplicate entry "${entry}" — each predecessor path must appear at most once`,
              hint: 'Remove the duplicate entry from additional_predecessors.'
            };
          }
          seen.add(entry);
        }
        // No entry duplicating the primary predecessor field.
        // Skip when predecessor is absent/null/'none' (spinoff or missing-field case).
        const primaryPred = fm.predecessor;
        if (primaryPred !== undefined && primaryPred !== null && primaryPred !== 'none') {
          for (const entry of ap) {
            if (entry === primaryPred) {
              return {
                field: 'additional_predecessors',
                error: `entry "${entry}" duplicates the primary predecessor field`,
                hint: 'The primary predecessor is already declared in predecessor:. Remove it from additional_predecessors to avoid double-counting on LoE traversal.'
              };
            }
          }
        }
        return null;
      },
    },

    // ---------------------------------------------------------------------------
    // Origin-axis cross-field rules (2026-07-07) — spinoff-provenance-ancestry plan.
    //
    // Four origin_* fields carry structured originating-session provenance for
    // spinoff/fork artifacts (kind: spinoff, spinoff-goal, spinoff-roadmap-creator).
    // They are a DISTINCT axis from predecessor (continuation spine), forked_from
    // (branch-point ancestry), and deliverable_id (dlv- grouping key).
    //
    // All four are nullable/optional (backfill=null for pre-existing forks; no migration).
    //
    // DR-014/DR-015 backlink: origin_* isolation is load-bearing for LoE effort-isolation
    // (DR-014) and rag's namespace-disjoint recursive-CTE (DR-015) — an id in the wrong
    // namespace silently returns zero rows in rag's origin_edges walk.
    //
    // Spec backlink: docs/plans/2026-07-07-spinoff-provenance-ancestry.md § C2, § AC3
    // ---------------------------------------------------------------------------

    // Rule C2-1: Kind-prefixed id well-formedness.
    // Each origin_* field (when non-null) must carry an id in the correct namespace.
    //
    // Namespace-disjointness is rag's hard requirement: its single recursive-CTE walks
    // mixed-kind edges over the origin_edges projection without a per-hop kind-join, so
    // ids must self-namespace to avoid cross-kind collisions.
    //
    // Negative-spec: prefix 'gol-' and 'g-' are NOT the goal-id scheme; the live scheme
    // (goal.schema.json id field) uses 'goal-' kebab-case. Do not accept 'gol-'/'g-' variants.
    //
    // Review: code-reviewer (F3) — split from one bundled check into four independent rule
    // entries so a record with multiple malformed origin fields surfaces all violations in one
    // pass, not just the first failing field.

    // Rule C2-1a: origin_plan_id prefix ('pln-').
    {
      check: (fm) => {
        if (fm.origin_plan_id === undefined || fm.origin_plan_id === null) return null;
        if (!String(fm.origin_plan_id).startsWith('pln-')) {
          return {
            field: 'origin_plan_id',
            error: `origin_plan_id "${fm.origin_plan_id}" does not begin with "pln-" (Rule C2-1: kind-prefixed id well-formedness)`,
            hint: 'origin_plan_id must carry a pln-prefixed plan id (e.g. pln-structured-originating-session-8b505c). Namespace-disjointness is required for rag\'s origin_edges recursive-CTE.'
          };
        }
        return null;
      },
    },

    // Rule C2-1b: origin_handoff path prefix ('state/handoffs/').
    {
      check: (fm) => {
        if (fm.origin_handoff === undefined || fm.origin_handoff === null) return null;
        if (!String(fm.origin_handoff).startsWith('state/handoffs/')) {
          return {
            field: 'origin_handoff',
            error: `origin_handoff "${fm.origin_handoff}" does not begin with "state/handoffs/" (Rule C2-1: kind-prefixed id well-formedness)`,
            hint: 'origin_handoff must be a handoff path (e.g. state/handoffs/2026-07-07-my-baton.md). Namespace-disjointness is required for rag\'s origin_edges recursive-CTE.'
          };
        }
        return null;
      },
    },

    // Rule C2-1c: origin_session non-empty (UUID-shaped).
    {
      check: (fm) => {
        if (fm.origin_session === undefined || fm.origin_session === null) return null;
        if (String(fm.origin_session).trim() === '') {
          return {
            field: 'origin_session',
            error: 'origin_session must be a non-empty string (UUID) when present and non-null (Rule C2-1: kind-prefixed id well-formedness)',
            hint: 'origin_session carries a session UUID (globally unique; no prefix needed). An empty string is not a valid UUID.'
          };
        }
        return null;
      },
    },

    // Rule C2-1d: origin_goal_id[] per-entry prefix ('goal-').
    // Array cardinality is enforced by Rule C2-2; here we check entry prefixes only
    // (skip prefix validation if the field is not an array — C2-2 will fire for that).
    {
      check: (fm) => {
        if (fm.origin_goal_id === undefined || fm.origin_goal_id === null || !Array.isArray(fm.origin_goal_id)) return null;
        for (let i = 0; i < fm.origin_goal_id.length; i++) {
          const entry = fm.origin_goal_id[i];
          if (!String(entry).startsWith('goal-')) {
            return {
              field: 'origin_goal_id',
              error: `origin_goal_id[${i}] "${entry}" does not begin with "goal-" (Rule C2-1: kind-prefixed id well-formedness)`,
              hint: 'Each origin_goal_id entry must carry a goal-prefixed id (e.g. goal-example-game-repo-shipping-velocity), matching the goal.schema.json id field scheme. Prefixes "gol-" and "g-" are not valid.'
            };
          }
        }
        return null;
      },
    },

    // Rule C2-2: Explicit per-kind cardinality.
    //
    // LOAD-BEARING (DR-014/DR-015): rag ingests origin_* via typed scalar columns (fast
    // equality path) and fans origin_goal_id array entries into N edge rows in the
    // origin_edges CQRS projection. An unexpected inline array crammed into a scalar
    // field lands as a JSON string in the scalar filter and SILENTLY RETURNS ZERO ROWS —
    // this is the exact failure class the origin-axis isolation rationale (DR-014) is
    // designed to prevent. The cardinality contract must be explicit here, not implied.
    //
    // Cardinality contract (matches § Field shape, ratified by rag + cockpit):
    //   origin_session   — scalar only (string | null); reject arrays.
    //   origin_handoff   — scalar only (string | null); reject arrays.
    //   origin_plan_id   — scalar only (string | null); reject arrays.
    //   origin_goal_id   — array only (string[] | null); reject bare scalars.
    //
    // Widen-trigger: a scalar field stays scalar until a fork demonstrably has two same-kind
    // parents → widen to string[], renegotiate with rag + cockpit before flipping the writer.
    // origin_goal_id ships as array now because multi-goal forks are already demonstrated.
    //
    // Review: code-reviewer (F4) — split from one bundled check into two independent rule
    // entries so a scalar-field-array violation and an origin_goal_id bare-scalar violation
    // both surface in one pass. Keeps the load-bearing DR-014/DR-015 comment above.

    // Rule C2-2a: Scalar fields (origin_session, origin_handoff, origin_plan_id) — reject arrays.
    {
      check: (fm) => {
        for (const field of ['origin_session', 'origin_handoff', 'origin_plan_id']) {
          const val = fm[field];
          if (val === undefined || val === null) continue;
          if (Array.isArray(val)) {
            return {
              field,
              error: `${field} must be a scalar string (not an array) — per-kind cardinality contract (Rule C2-2). An unexpected array in a scalar origin field lands as a JSON string in rag's scalar column filter and silently returns zero rows.`,
              hint: `${field} carries at most one value (0..1 cardinality). Use a plain string, not a YAML list. DR-014/DR-015 require explicit scalar-vs-array cardinality per field.`
            };
          }
        }
        return null;
      },
    },

    // Rule C2-2b: origin_goal_id array field — reject bare scalar.
    {
      check: (fm) => {
        const goalId = fm.origin_goal_id;
        if (goalId === undefined || goalId === null || Array.isArray(goalId)) return null;
        return {
          field: 'origin_goal_id',
          error: `origin_goal_id must be an array (string[] | null), not a bare scalar "${goalId}" — per-kind cardinality contract (Rule C2-2). rag fans array entries into N edge rows in origin_edges; a bare scalar bypasses the fan-out.`,
          hint: 'Use YAML list syntax for origin_goal_id, e.g. ["goal-example-game-repo-shipping-velocity"]. DR-014/DR-015 require origin_goal_id to be an array; a scalar bypasses rag\'s fan-out into origin_edges rows.'
        };
      },
    },

    // Rule C2-3: Direct self-reference rejection.
    //
    // origin_handoff must not equal the record's own path (partial emit-time acyclicity).
    // Full cycle detection across the fleet is the walker's job (walk-handoff-dag.js
    // visited-set, C3) + cockpit depth-cap; this rule catches the degenerate self-loop
    // at validation time.
    //
    // Implementation note: the cross-field rule interface passes only the frontmatter
    // object (no file path context). Self-reference detection is therefore best-effort:
    // the rule fires when the caller injects the record's own path via the optional
    // fm._filePath sentinel. Corpus validators (validate-handoff.js / query-records.js)
    // may inject _filePath to enable full acyclicity checking; callers without path
    // context silently skip this guard. "_filePath" is a validator-internal convention,
    // never written into the YAML frontmatter of a record.
    {
      check: (fm) => {
        if (fm.origin_handoff === undefined || fm.origin_handoff === null) return null;
        // Best-effort: only fires when the caller has injected the record's own path.
        // _filePath is a validator-internal sentinel — not a YAML frontmatter field.
        const ownPath = fm._filePath;
        if (ownPath === undefined || ownPath === null) return null;
        // Normalise both to forward-slash for cross-platform comparison.
        const normOrigin = String(fm.origin_handoff).replace(/\\/g, '/');
        const normOwn = String(ownPath).replace(/\\/g, '/');
        if (normOrigin === normOwn) {
          return {
            field: 'origin_handoff',
            error: `origin_handoff "${fm.origin_handoff}" equals the record's own path — self-reference creates a trivial cycle (Rule C2-3: direct self-reference rejection)`,
            hint: 'origin_handoff must point to a DIFFERENT handoff baton — the one that was active when this fork was spawned, not this record itself. Remove the self-reference.'
          };
        }
        return null;
      },
    },

    // Rule C2-4: predecessor:none invariant preserved for spinoff kinds.
    //
    // Presence of origin_* fields must not be read as, or coexist with, a continuity
    // predecessor on spinoff kinds (spinoff, spinoff-goal, spinoff-roadmap-creator).
    //
    // This rule reinforces Rule A3a-3 (predecessor:none for spinoff kinds, ~line 1100 above)
    // from the origin-axis perspective. origin_* fields are a DISTINCT provenance axis
    // from the continuation spine — setting origin_* does NOT change the expectation that
    // predecessor: none (or null) for all spinoff kinds.
    //
    // Design: this rule reports an error if origin_* fields are present on a spinoff kind
    // AND predecessor is a non-none/non-null string, complementing A3a-3's predecessor
    // check with an origin-axis-aware error message.
    //
    // Note: A3a-3 already rejects the predecessor value directly; this rule supplements
    // with a hint contextual to the origin_* axis. Both fire on the same condition, giving
    // the author two clear signals. No duplication of A3a-3's logic — the predecessor
    // check itself remains in A3a-3.
    //
    // Spec backlink: docs/plans/2026-07-07-spinoff-provenance-ancestry.md § C2 rule-4
    // Cross-plan: coordinate with goal-setting-okr C1b Rule A3a-3 (~line 1100).
    {
      check: (fm) => {
        const spinoffKinds = ['spinoff', 'spinoff-goal', 'spinoff-roadmap-creator'];
        if (!spinoffKinds.includes(fm.kind)) return null;
        // Only fire when at least one origin_* field is present (non-null/non-undefined).
        const hasOriginField = (
          (fm.origin_session !== undefined && fm.origin_session !== null) ||
          (fm.origin_handoff !== undefined && fm.origin_handoff !== null) ||
          (fm.origin_plan_id !== undefined && fm.origin_plan_id !== null) ||
          (fm.origin_goal_id !== undefined && fm.origin_goal_id !== null)
        );
        if (!hasOriginField) return null;
        // Predecessor must be 'none' or null for spinoff kinds (Rule A3a-3).
        const pred = fm.predecessor;
        if (pred === undefined || pred === null || pred === 'none') return null;
        return {
          field: 'predecessor',
          error: `origin_* provenance fields are present on a spinoff kind (${fm.kind}) but predecessor is "${pred}" — spinoff kinds must have predecessor: none (or null) regardless of origin_* presence (Rule C2-4: predecessor:none invariant)`,
          hint: 'The origin_* axis is DISTINCT from the continuation spine. origin_* records where this fork was spawned FROM; predecessor: none records that it does NOT continue a prior baton. Both are simultaneously correct for spinoffs. Set predecessor: none (or null). DR-014/DR-015.'
        };
      },
    },

    // Rule C2-5: forked_from / origin_handoff never-silently-disagree invariant.
    //
    // forked_from (branch-point ancestry, spinoff-only, PM-directed, archival-guard
    // member) and origin_handoff (originating-session provenance, all fork kinds,
    // auto-captured, LoE- and archival-excluded) are ORTHOGONAL axes, not aliases —
    // see walk-handoff-dag.js EDGE_KIND_META for the full distinction. They usually
    // name the same spawning baton, but nothing enforced that until now. This rule
    // is EQUALITY-WHEN-BOTH-SET, with NO precedence and NO presence-coupling:
    // requiring forked_from whenever origin_handoff is set would break the
    // spinoff-goal/spinoff-roadmap-creator case, where forked_from is validation-illegal
    // (see the forked_from kind-gate above) but origin_handoff is legal (C2-4).
    // Equality is enforced ONLY over the both-present intersection.
    //
    // Spec backlink: docs/plans/2026-07-07-spinoff-provenance-ancestry.md;
    // state/review-trail/findings/2026-07-08-the Director of Engineering-origin-handoff-forked-from-reconciliation.md
    //
    // Review: code-reviewer (F2) — normalisation below is backslash-to-forward-slash
    // ONLY (reused from C2-3): case, trailing slashes, and `./`-relative prefixes are
    // NOT normalized, so two case-differing paths naming the same file on a
    // case-insensitive filesystem would be flagged as divergent. Low real-world risk
    // (handoff paths are lowercase-kebab by convention) and symmetric with C2-3's
    // pre-existing behavior — flagged explicitly here rather than left to be silently
    // inherited via "reuses C2-3's normalisation."
    {
      check: (fm) => {
        const forkedFrom = fm.forked_from;
        const originHandoff = fm.origin_handoff;
        const isSet = (v) => v !== undefined && v !== null && String(v).trim() !== '' && v !== 'none';
        if (!isSet(forkedFrom) || !isSet(originHandoff)) return null;
        // Same forward-slash normalisation Rule C2-3 uses above.
        const normForkedFrom = String(forkedFrom).replace(/\\/g, '/');
        const normOriginHandoff = String(originHandoff).replace(/\\/g, '/');
        if (normForkedFrom !== normOriginHandoff) {
          // Review: code-reviewer (F4) — filed under origin_handoff as a deliberate
          // triage convention (origin_handoff is the auto-captured side and the
          // more-likely-drifted value), NOT a precedence claim: the record fails
          // identically regardless of which field is "wrong."
          return {
            field: 'origin_handoff',
            error: `origin_handoff "${originHandoff}" does not match forked_from "${forkedFrom}" — lineage-integrity divergence (Rule C2-5: never-silently-disagree invariant)`,
            hint: 'forked_from (branch-point ancestry) and origin_handoff (originating-session provenance) both name the spawning baton; when both are set they must be identical. They may legitimately differ only in that forked_from may be ABSENT where origin_handoff is set — origin_handoff covers spinoff-goal/spinoff-roadmap-creator where forked_from is illegal. If they genuinely reference different handoffs, one is wrong.'
          };
        }
        return null;
      },
    },

    // Rule C3: origin_* universal conflation rule (non-spinoff kinds).
    //
    // Rule C2-4 (above) rejects origin_* + real predecessor co-occurrence but is
    // SCOPED TO SPINOFF KINDS ONLY (predecessor:none invariant is a spinoff-fork
    // axiom). The underlying doctrine — "origin_* is a DISTINCT axis from the
    // continuation spine and must not be conflated with it" — is universal, not
    // spinoff-specific. This rule closes that scoping hole for non-spinoff kinds
    // (session-handoff, recovery): a mis-encoded continuity predecessor that
    // silently duplicates origin_handoff is caught the same way C2-5 catches
    // forked_from/origin_handoff divergence.
    //
    // Predicate: on non-spinoff kinds, reject iff normalise(origin_handoff) ===
    // normalise(predecessor) — reusing the same backslash-to-forward-slash
    // normalisation C2-5 uses. origin_session/origin_plan_id/origin_goal_id stay
    // OUT of this rule: they are cross-entity refs (not state/handoffs/ paths per
    // walk-handoff-dag.js EDGE_KIND_META), so they cannot conflate with a
    // handoff-path predecessor. A legitimate non-spinoff whose origin_handoff
    // points at a DIFFERENT baton than predecessor passes cleanly — this rule
    // does not couple the two fields' presence, only their equality when the
    // values happen to collide.
    //
    // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C3
    {
      check: (fm) => {
        const spinoffKinds = ['spinoff', 'spinoff-goal', 'spinoff-roadmap-creator'];
        if (spinoffKinds.includes(fm.kind)) return null;
        const originHandoff = fm.origin_handoff;
        const predecessor = fm.predecessor;
        const isSet = (v) => v !== undefined && v !== null && String(v).trim() !== '' && v !== 'none';
        if (!isSet(originHandoff) || !isSet(predecessor)) return null;
        // Same forward-slash normalisation Rule C2-5 uses above.
        const normOriginHandoff = String(originHandoff).replace(/\\/g, '/');
        const normPredecessor = String(predecessor).replace(/\\/g, '/');
        if (normOriginHandoff === normPredecessor) {
          return {
            field: 'origin_handoff',
            error: `origin_handoff "${originHandoff}" equals predecessor "${predecessor}" on a non-spinoff kind (${fm.kind}) — the origin_* axis must not be conflated with the continuation spine (Rule C3: universal conflation rule)`,
            hint: 'origin_handoff (originating-session provenance) and predecessor (continuation spine) are DISTINCT axes even on non-spinoff kinds. If this handoff genuinely continues from the same baton it forked from, that is a coincidence worth double-checking, not a mechanical requirement — set origin_handoff to the actual originating session, or remove it if there is none.'
          };
        }
        return null;
      },
    },
  ],

  // ---------------------------------------------------------------------------
  // plan cross-field rules
  //
  // Plan schemas have no date-cutoff guards (plans are always post-convention);
  // all cross-field rules apply to every plan record.
  //
  // Spec backlink: docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § D1, D2, D3
  // ---------------------------------------------------------------------------
  plan: [
    // deliverable_id format guard: present and non-null → must start with 'dlv-'.
    {
      check: (fm) => {
        if (fm.deliverable_id === undefined || fm.deliverable_id === null) return null;
        if (!String(fm.deliverable_id).startsWith('dlv-')) {
          return {
            field: 'deliverable_id',
            error: `deliverable_id "${fm.deliverable_id}" does not begin with "dlv-"`,
            hint: 'deliverable_id is minted by bin/mint-deliverable-id.sh and always begins with "dlv-". Inherit from the parent roadmap stub or mint a new one; do not hand-author a value without the prefix.'
          };
        }
        return null;
      },
    },

    // initiative FK non-empty: present and non-null → must be a non-empty string.
    {
      check: (fm) => {
        if (fm.initiative === undefined || fm.initiative === null) return null;
        if (String(fm.initiative).trim() === '') {
          return {
            field: 'initiative',
            error: 'initiative FK must be a non-empty string when present and non-null',
            hint: 'Set initiative to a valid initiative id (e.g. "delphi-pro-launch") from state/initiatives/<id>.yaml, or null if this plan does not belong to a named initiative.'
          };
        }
        return null;
      },
    },

    // plan_id format guard: present and non-null → must start with 'pln-'.
    {
      check: (fm) => {
        if (fm.plan_id === undefined || fm.plan_id === null) return null;
        if (!String(fm.plan_id).startsWith('pln-')) {
          return {
            field: 'plan_id',
            error: `plan_id "${fm.plan_id}" does not begin with "pln-"`,
            hint: 'plan_id is minted by coordinator-doc-new and always begins with "pln-". Do not hand-author a value without the prefix.'
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
    // status: actioned with decision accepted|partial requires a well-formed realized_by.
    // The realization-layer claim-of-record (2026-06-23 example-game-repo B3 incident): the 2026-06-21
    // claim-lock predecessor stamped picked_up_by only on in_progress, so once a memo went
    // actioned the claim was released and the archived memo recorded WHO handled it / WHERE the
    // work landed nowhere — letting a second session realize the same accepted memo concurrently.
    // realized_by makes the archived memo a claim-of-record. Both 'accepted' and 'partial' realize
    // work and are gated; decline/consult/fyi realize nothing and are exempt. The value SHAPE is
    // validated (not merely non-empty) so a typo'd pointer fails loud rather than reading as
    // authoritative — detect-then-fail-loud per CLAUDE.md Implementation Standards: 'inline'
    // sentinel, a path (contains '/'), or a hex SHA (7-40 chars). picked_up_by is preserved on the
    // terminal flip (skills/pickup M3/M4) but deliberately NOT mandated here — a same-session direct
    // accept that legitimately never claimed must still validate; the picked_up_by mandate stays on
    // in_progress only. Grandfathered memos (created < 2026-05-22) short-circuit via the __skip__ rule.
    // Spec backlink: docs/plans/2026-06-23-memo-pickup-realization-claim-visibility.md § C1
    {
      check: (fm) => {
        if (fm.status !== 'actioned') return null;
        if (fm.decision !== 'accepted' && fm.decision !== 'partial') return null;
        const v = fm.realized_by == null ? '' : String(fm.realized_by).trim();
        if (v === '') {
          return {
            field: 'realized_by',
            error: `required when status=actioned and decision=${fm.decision}`,
            hint: `Set realized_by to where the work landed: a plan path (docs/plans/*.md or tasks/<feature>/todo.md), a commit SHA, or the sentinel "inline". An accepted/partial memo realizes work and must carry a claim-of-record so a peer session does not re-realize it.`
          };
        }
        // Review: code-reviewer (F1) — accept uppercase hex + SHA-256 64-char object names;
        // regex widened from /^[0-9a-f]{7,40}$/ to /^[0-9a-fA-F]{7,64}$/ (7–64 hex chars).
        // The '/' check for path shape is kept deliberately permissive — see inline comment below.
        // The '/' check catches the common path case; a slash-containing prose value is a
        // pathological input not worth over-fitting against given the field is advisory
        // (realized_by is attribution for grep/re-pickup, not a machine-dereferenced pointer;
        // requiring a '.' segment would false-reject extensionless paths like tasks/foo/bar).
        const wellFormed = v === 'inline' || v.includes('/') || /^[0-9a-fA-F]{7,64}$/.test(v);
        if (!wellFormed) {
          return {
            field: 'realized_by',
            error: `malformed realized_by "${v}" when status=actioned and decision=${fm.decision}`,
            hint: `realized_by must be one of: the sentinel "inline", a path containing "/" (e.g. docs/plans/2026-06-23-foo.md, tasks/<feature>/todo.md), or a hex commit SHA (7–64 hex chars). A bare word reads as authoritative but points nowhere.`
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
    // When present, must be one of the pinned enum members: ask | consult | fyi | proposal.
    // 'proposal' is action-requiring (urgent band) — sender presents a concrete change +
    // recommendation; receiver decides adoption. Added per contract Deliverable D.
    // 'ack' is NOT a valid kind — acknowledgement is receipt-state, not sender-declared kind.
    // Spec backlink: docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md § Pinned interface
    {
      check: (fm) => {
        if (fm.kind === undefined || fm.kind === null) return null;
        const validKinds = ['ask', 'consult', 'fyi', 'proposal'];
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

/**
 * applyCrossFieldRulesFor — public wrapper for applyCrossFieldRules, addressed by schema name.
 * Consumed by memo-transition.js to validate cross-repo-memo cross-field rules without
 * exposing the internal schema-object shape.
 * Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C2
 */
function applyCrossFieldRulesFor(schemaName, fm) {
  return applyCrossFieldRules(fm, { schema: schemaName });
}

/**
 * checkReferentialIntegrity — resolver-seam existence + never-silently-disagree
 * validation for local handoff-DAG ID refs (predecessor_id, origin_handoff_id).
 *
 * Deliberately a SEPARATE exported function, not a CROSS_FIELD_RULES addition —
 * CROSS_FIELD_RULES closures run unconditionally inside validateFrontmatter /
 * validateRecord on every validate call and have no place to receive a resolver
 * (both existing public entry points, applyCrossFieldRules ~1897 and
 * applyCrossFieldRulesFor ~1917, call `rule.check(frontmatter)` single-arg —
 * threading a second ctx arg through both, plus their callers (validateRecord
 * ~855 and memo-transition.js:181), is materially more invasive than adding one
 * new opt-in export that cadence gates call explicitly). CROSS_FIELD_RULES and
 * both existing entry points are UNTOUCHED by this addition (0 existing call
 * sites changed) — see the seam-analysis enumeration in
 * docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C3.
 *
 * Scope (first cut, deliberately narrow): only LOCAL handoff-DAG ID refs —
 * predecessor_id, origin_handoff_id. deliverable_id and initiative are NOT
 * existence-checked here — they resolve against the CENTRAL/example-orchestration-hub state plane
 * (`coordinator_state_root --central`), not a local directory scan. DoE-claude
 * has no local state/initiatives/ directory; a naive local scan would soft-warn
 * every initiative ref forever, a false-positive class distinct from the normal
 * in-flight "target not authored yet" case soft-warn tolerates. Do not widen
 * this function to initiative/deliverable_id until the central-plane resolver
 * seam is wired — see § C3 initiative / central-state-plane constraint.
 *
 * @param {object} record - parsed frontmatter object (e.g. from parseFrontmatter).
 * @param {function|null} resolver - `(id: string) => ({ path?: string } | falsy)`.
 *   Given an artifact id, returns a truthy object (at minimum `{ path }`) if the id
 *   resolves to a real artifact. Any falsy return (`null`, `undefined`, `false`, `0`,
 *   `''`) is honored as dangling — not just `null`/`undefined`, though those are what
 *   real resolvers will realistically return. Callers own
 *   how the resolver is built (index lookup, disk walk, cache) — this function never
 *   does its own filesystem I/O. When resolver is omitted/null, this function is a
 *   shape-only no-op (returns no existence errors) — the same soft posture as an
 *   absent index anywhere else in this validator.
 * @param {object} [options] - `{ strict?: boolean }`. strict:true (set ONLY by a named
 *   cadence gate, e.g. /workweek-complete) flips a dangling ref from a soft warning to
 *   a hard error. No new gate is invented here — the caller decides when strict applies.
 * @returns {{ errors: Array<{field,error,hint}>, warnings: Array<{field,error,hint}> }}
 *   Dangling refs land in `errors` when strict, `warnings` otherwise (never both
 *   for the same ID ref — but the two pairs are classified independently, so the
 *   whole return CAN have both non-empty `errors` and non-empty `warnings` when
 *   one pair is dangling under non-strict and the other pair diverges).
 *   Never-silently-disagree divergences (ID resolves to a DIFFERENT path than the
 *   companion path field names) always land in `errors` regardless of strict — a
 *   resolvable-but-wrong ref is a correctness bug, not an in-flight-authoring gap.
 *
 * Negative-spec: does NOT hard-enforce outside the caller-set strict:true; does NOT
 * store the resolution result on the record; does NOT existence-check deliverable_id
 * or initiative (deferred, see scope note above).
 *
 * Spec backlink: docs/plans/2026-07-08-lifecycle-vocab-c2-durable-links-rollup.md § C3
 */
function checkReferentialIntegrity(record, resolver, options) {
  const errors = [];
  const warnings = [];
  if (!record || typeof record !== 'object') return { errors, warnings };
  const strict = !!(options && options.strict);

  // Path/ID companion pairs this cluster introduced (C2). Each pair: the human-legible
  // path field and its machine-walked ID companion.
  const pairs = [
    { pathField: 'predecessor', idField: 'predecessor_id' },
    { pathField: 'origin_handoff', idField: 'origin_handoff_id' },
  ];

  const isSet = (v) => v !== undefined && v !== null && String(v).trim() !== '' && v !== 'none';
  // Same forward-slash normalisation the existing forked_from/origin_handoff
  // never-silently-disagree rule (Rule C2-5, ~line 1543) uses, for consistency.
  const normPath = (v) => String(v).replace(/\\/g, '/');

  for (const { pathField, idField } of pairs) {
    const idValue = record[idField];
    if (!isSet(idValue)) continue; // no ID ref to check

    // No resolver supplied: shape-only no-op for this ID ref — existence cannot be
    // determined without one, and an absent resolver must never be conflated with
    // a resolver-that-found-nothing (dangling). See "no resolver → shape-only" contract.
    if (typeof resolver !== 'function') continue;

    const resolved = resolver(idValue);

    if (!resolved) {
      // Dangling ID ref: soft-warn by default; hard error only when the caller
      // (a named cadence gate) opts into strict.
      const violation = {
        field: idField,
        error: `${idField} "${idValue}" does not resolve to a known artifact`,
        hint: `No artifact was found for id "${idValue}" via the supplied resolver. This is the normal state for in-flight work whose target has not been authored yet. Outside a cadence gate this is a warning only; /workweek-complete's strict pass will error on it.`
      };
      if (strict) errors.push(violation);
      else warnings.push(violation);
      continue; // resolved artifact unknown — nothing to compare the path field against
    }

    // Never-silently-disagree: when both the path field and its ID companion are
    // non-null, the ID must resolve to the artifact the path field names.
    const pathValue = record[pathField];
    if (!isSet(pathValue)) continue; // ID present, path absent — nothing to compare
    const resolvedPath = resolved.path;
    if (resolvedPath === undefined || resolvedPath === null) continue; // resolver didn't supply a path — can't compare
    if (normPath(resolvedPath) !== normPath(pathValue)) {
      errors.push({
        field: idField,
        error: `${idField} "${idValue}" resolves to "${resolvedPath}", which does not match ${pathField} "${pathValue}" — never-silently-disagree invariant`,
        hint: `${pathField} and ${idField} are two representations of the same edge and must name the same artifact when both are set. Either ${pathField} was hand-edited without updating ${idField}, or ${idField} is stale. Mirrors the existing forked_from/origin_handoff invariant (Rule C2-5).`
      });
    }
  }

  return { errors, warnings };
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
 * Validate a lessons.md file against the lesson-entry schema (LEGACY FORMAT).
 *
 * This function validates the INLINE-MARKDOWN format used by the old state/lessons.md
 * append-only file. Each **bold-title** entry may carry a [universal] or [project] tag;
 * unknown tags (not in tag_enum.values) are rejected; untagged entries are allowed.
 *
 * After the 2026-06-30 migration (docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md),
 * lessons are stored as per-entry YAML files under state/lessons/<date>-<slug>.yaml.
 * Per-entry YAML lessons are validated by validateFrontmatter() against the lesson-entry
 * schema's required:/optional: field declarations (the stored-grammar path).
 *
 * lesson-entry schema registration: the lesson-entry schema is declared in
 * schemas/lesson-entry.yaml (applies_to: state/lessons/*.yaml) and loaded automatically
 * by loadSchemas(). It follows the same required:/optional: registration pattern as the
 * improvement-queue, bug-backlog, and debt-backlog schemas. No CROSS_FIELD_RULES entry
 * is needed -- lesson-entry uses the base-schema validation path (validateFrontmatter).
 *
 * This function remains for:
 *   (a) Migration tooling that validates the legacy lessons.md before converting it.
 *   (b) schema.test.js regression tests that use SCHEMAS['lesson-entry'] directly.
 *
 * When the lesson-entry schema no longer carries match_mode: inline-tag-per-entry (i.e.
 * after full fleet migration), this function short-circuits and returns {ok: true} for
 * every input -- a safe no-op.
 *
 * Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md (C1)
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

// ---------------------------------------------------------------------------
// JSON Schema draft-2020-12 subset validator
// Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 1
//
// Supported keywords: type, enum, required (JSON Schema array form), properties,
//   additionalProperties, $ref/#/$defs (in-file only — cross-file is a fail-loud error),
//   format: date|date-time, pattern (string values only), anyOf (primary use: nullable
//   [T, null] patterns).
//
// NO external dependencies — Node built-ins only.
// Negative-spec: cross-file $ref (any ref not starting with '#/$defs/') throws fail-loud.
//   The dependency-free context (hooks, bash) cannot fetch external files.
// ---------------------------------------------------------------------------

/**
 * Module-level JSON Schema cache. Populated by loadSchemas when .schema.json files
 * are present in schemasDir. Used by validateRecord's string-name lookup path.
 *
 * Negative-spec: .yaml-dialect schemas are NOT entered here; they use validateFrontmatter.
 */
const _jsonSchemaCache = Object.create(null);

// ---------------------------------------------------------------------------
// Schema-version gate helpers (W2 ccos-1)
// Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2
// Semantics:
//   warn-on-newer-read:   record.schema_version major > schema.x-schema-version major,
//                         mode='read' (default) → non-fatal warning in result.warnings
//   refuse-on-newer-write: same condition, mode='write' → FAIL loud in result.errors
//
// Opt-in: records or schemas without these fields pass through unchanged.
// Comparison is major-version only — patch/minor bumps do not gate.
// NO external semver package — hand-rolled parse (AC4 dep-free constraint).
// ---------------------------------------------------------------------------

/**
 * Parse a semver string "MAJOR.MINOR.PATCH" (or "MAJOR.MINOR" or "MAJOR") into
 * { major, minor, patch }.  Returns null when the string is not parseable.
 *
 * Hand-rolled — no external semver package permitted (AC4 dep-free constraint).
 * Only the major component is used for the version gate, but we parse all three
 * parts for correctness and future extensibility.
 *
 * Negative-spec: a non-string or a string with no leading integer returns null
 * (no throw) so the gate treats unparseable versions as absent (no-op).
 */
function parseSemver(v) {
  if (typeof v !== 'string') return null;
  // Review: code-reviewer (A-F5) — anchored with $ to reject trailing junk (e.g. "1.2.3-rc1 garbage").
  const m = /^(\d+)(?:\.(\d+))?(?:\.(\d+))?$/.exec(v.trim());
  if (!m) return null;
  return {
    major: parseInt(m[1], 10),
    minor: m[2] !== undefined ? parseInt(m[2], 10) : 0,
    patch: m[3] !== undefined ? parseInt(m[3], 10) : 0,
  };
}

/**
 * Resolve an in-file JSON Schema $ref.
 * Only '#/$defs/Name' references are supported.
 * Throws fail-loud on any cross-file or non-$defs ref.
 *
 * Negative-spec: cross-file $ref is a hard error — no network/filesystem fetch is
 * permitted in dependency-free validator contexts.
 */
function resolveJsonRef(ref, rootSchema) {
  if (typeof ref !== 'string' || !ref.startsWith('#/$defs/')) {
    throw new Error(
      `JSON Schema $ref "${ref}" is not supported — only in-file #/$defs/... references are allowed. ` +
      `Cross-file $ref would require a fetch, which is banned in dependency-free hook/bash contexts ` +
      `(docs/plans/2026-06-27-ccos-1-dual-context-validator.md § Architecture, $ref policy).`
    );
  }
  const defName = ref.slice('#/$defs/'.length);
  if (!rootSchema.$defs || !rootSchema.$defs[defName]) {
    throw new Error(
      `JSON Schema $ref "${ref}" not found — no $defs.${defName} in schema. ` +
      `Declare the definition under "$defs" in the same schema file.`
    );
  }
  return rootSchema.$defs[defName];
}

/**
 * Check whether a value satisfies a JSON Schema type specifier.
 * typeSpec may be a string or an array of strings (draft-2020-12 array form).
 * Returns null on match, or an error record {field, error, hint} on mismatch.
 */
function checkJsonType(value, typeSpec, field) {
  const types = Array.isArray(typeSpec) ? typeSpec : [typeSpec];
  for (const t of types) {
    if (t === 'null' && value === null) return null;
    if (t === 'string' && typeof value === 'string') return null;
    if (t === 'number' && typeof value === 'number') return null;
    if (t === 'integer' && typeof value === 'number' && Number.isInteger(value)) return null;
    if (t === 'boolean' && typeof value === 'boolean') return null;
    if (t === 'object' && value !== null && typeof value === 'object' && !Array.isArray(value)) return null;
    if (t === 'array' && Array.isArray(value)) return null;
  }
  const actual = value === null ? 'null' : (Array.isArray(value) ? 'array' : typeof value);
  const expected = Array.isArray(typeSpec) ? typeSpec.join(' or ') : typeSpec;
  return {
    field,
    error: `expected ${expected}, got ${actual}`,
    hint: `Provide a value of type: ${expected}`
  };
}

/**
 * Recursively validate a value against a JSON Schema node (draft-2020-12 subset).
 *
 * value      — the JS value to validate
 * schema     — the current schema node (may have been resolved from a $ref)
 * rootSchema — the top-level schema document (for in-file $ref resolution)
 * path       — dotted path string for error reporting ('' at root)
 *
 * Returns an array of error objects {field, error, hint}.
 *
 * Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 1
 */
function validateJsonSchemaNode(value, schema, rootSchema, path) {
  if (schema === null || schema === undefined || typeof schema !== 'object') return [];
  path = path === undefined ? '' : path;
  const field = path || '(root)';
  const errors = [];

  // $ref — resolve before any other keyword.
  if (schema.$ref !== undefined) {
    const resolved = resolveJsonRef(schema.$ref, rootSchema);
    return validateJsonSchemaNode(value, resolved, rootSchema, path);
  }

  // anyOf — value must match at least one sub-schema.
  // Primary use case: nullable types, e.g. anyOf: [{type: 'string'}, {type: 'null'}].
  // Review: code-reviewer (A-F1) — do NOT hard-return on match; fall through to sibling keywords
  // (required, properties, format, additionalProperties) that may appear on the same node.
  // Only early-return on FAILURE so callers never silently skip sibling constraint checks.
  if (schema.anyOf !== undefined) {
    const matchesAny = Array.isArray(schema.anyOf) && schema.anyOf.some(
      sub => validateJsonSchemaNode(value, sub, rootSchema, path).length === 0
    );
    if (!matchesAny) {
      const typeHints = Array.isArray(schema.anyOf)
        ? schema.anyOf.map(s => s.type || (Array.isArray(s.enum) ? s.enum.join('/') : JSON.stringify(s))).join(' or ')
        : '(unknown)';
      errors.push({
        field,
        error: `value does not match any allowed schema; expected ${typeHints} (got ${value === null ? 'null' : typeof value})`,
        hint: `Expected one of: ${typeHints}`
      });
      return errors;
    }
    // anyOf matched — fall through to check sibling keywords on this node.
  }

  // type — short-circuit on mismatch (object/array keyword checks require correct runtime type).
  if (schema.type !== undefined) {
    const typeErr = checkJsonType(value, schema.type, field);
    if (typeErr) {
      errors.push(typeErr);
      return errors;
    }
  }

  // enum — value must be one of the listed values (strict equality).
  // Review: code-reviewer (A-F3) — do NOT hard-return on match; fall through to sibling keywords
  // (format, object checks) that may appear on the same node alongside enum.
  // Only early-return on FAILURE so sibling constraint checks are never silently skipped.
  if (Array.isArray(schema.enum)) {
    const enumOk = schema.enum.some(e => e === value);
    if (!enumOk) {
      errors.push({
        field,
        error: `invalid enum value "${value}"`,
        hint: `Allowed values: ${schema.enum.map(String).join(', ')}`
      });
      return errors;
    }
    // enum matched — fall through to check sibling keywords (format, object checks).
  }

  // format — applied to string values only.
  if (schema.format !== undefined && typeof value === 'string') {
    if (schema.format === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      errors.push({ field, error: `invalid date format "${value}"`, hint: 'Use format YYYY-MM-DD' });
    } else if (schema.format === 'date-time' && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) {
      errors.push({ field, error: `invalid date-time format "${value}"`, hint: 'Use ISO 8601 date-time format (YYYY-MM-DDTHH:MM:SSZ)' });
    }
  }

  // pattern — applied to string values only (JSON Schema draft-2020-12 §6.3.3).
  // Review: code-reviewer (C4a, P1) — was declared on handoff.schema.json's shipped_in field
  // but silently inert (no branch handled it). Cross-field Rule A3a-2b already enforces the
  // identical shape on shipped_in (deployment_state:shipped⇒shipped_in coupling); this branch
  // makes the declared JSON Schema contract itself live, so a third-party JSON Schema validator
  // or a future refactor that trusts the declared schema sees the same enforcement this
  // hand-rolled engine has always applied via the cross-field rule. Complementary, not redundant:
  // pattern enforces value shape here; the cross-field rule enforces the field-presence coupling.
  if (typeof schema.pattern === 'string' && typeof value === 'string' && !new RegExp(schema.pattern).test(value)) {
    errors.push({
      field,
      error: `value "${value}" does not match required pattern`,
      hint: `Value must match the pattern: ${schema.pattern}`
    });
  }

  // Object-level keywords — only applied to non-null, non-array objects.
  const isObj = value !== null && typeof value === 'object' && !Array.isArray(value);
  if (isObj) {
    // required (JSON Schema array form) — key must be present; null value is allowed.
    if (Array.isArray(schema.required)) {
      for (const req of schema.required) {
        if (!(req in value)) {
          errors.push({
            field: path ? `${path}.${req}` : req,
            error: 'required field missing',
            hint: `Add "${req}:" to the record`
          });
        }
      }
    }

    // properties — validate each declared property that is present (including null).
    if (schema.properties !== null && schema.properties !== undefined && typeof schema.properties === 'object') {
      for (const [prop, propSchema] of Object.entries(schema.properties)) {
        if (prop in value && value[prop] !== undefined) {
          const propPath = path ? `${path}.${prop}` : prop;
          errors.push(...validateJsonSchemaNode(value[prop], propSchema, rootSchema, propPath));
        }
      }
    }

    // additionalProperties: false — reject keys not listed in properties.
    if (schema.additionalProperties === false) {
      const declaredProps = new Set(Object.keys(schema.properties || {}));
      for (const key of Object.keys(value)) {
        if (!declaredProps.has(key)) {
          errors.push({
            field: path ? `${path}.${key}` : key,
            error: `additional property "${key}" not allowed`,
            hint: 'Remove this property or add it to the schema properties'
          });
        }
      }
    }
  }

  // Array-level keywords — applied to arrays.
  if (Array.isArray(value) && schema.items !== undefined) {
    for (let i = 0; i < value.length; i++) {
      const itemPath = path ? `${path}[${i}]` : `[${i}]`;
      errors.push(...validateJsonSchemaNode(value[i], schema.items, rootSchema, itemPath));
    }
  }

  return errors;
}

/**
 * Return true when schema was loaded from a .schema.json file (JSON Schema draft-2020-12 subset).
 * Detection uses the non-enumerable _isJsonSchema marker stamped by loadSchemas.
 *
 * Negative-spec: .yaml-dialect schemas do NOT carry this marker.
 * Purpose: routing in validateFrontmatterDispatch — not for schema identification by external callers.
 *
 * Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2.5
 */
function isJsonSchemaBacked(schema) {
  return schema !== null && schema !== undefined && schema._isJsonSchema === true;
}

/**
 * Validation dispatch — route frontmatter validation to the correct validator based on schema type.
 *
 * When the schema is JSON-Schema-backed (stamped by loadSchemas with _isJsonSchema: true):
 *   → delegates to validateRecord(frontmatter, schema), which runs the dep-free JSON Schema
 *     subset validator (shape) then CROSS_FIELD_RULES (cross-field). Returns {ok, errors?}.
 *
 * When the schema is .yaml-dialect (no _isJsonSchema marker):
 *   → delegates to validateFrontmatter(frontmatter, schema) unchanged (existing behaviour).
 *
 * This is the single entry-point for per-file validation in lint-frontmatter.js so that
 * migrated .schema.json schemas are validated by the JSON path, not the YAML-dialect path.
 *
 * Negative-spec: validateFrontmatter(frontmatter, schema) is intentionally NOT modified —
 *   it remains the authoritative .yaml-dialect validator. This dispatch is the routing layer;
 *   the two validators are independent and must not be merged (ccos-1 W2.5 constraint).
 *
 * Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2.5 Deliverable 2
 */
function validateFrontmatterDispatch(frontmatter, schema) {
  if (isJsonSchemaBacked(schema)) {
    // JSON-Schema-backed path: null/missing frontmatter is treated as an empty object
    // so required-field checks produce "required field missing" errors rather than
    // short-circuiting. validateRecord handles the null guard internally, but to be
    // explicit and consistent with the YAML path's error semantics, pass {} for null.
    const record = (frontmatter !== null && frontmatter !== undefined) ? frontmatter : {};
    const result = validateRecord(record, schema);
    // Review: code-reviewer (A-F14) — return warnings in both branches so warn-on-newer-read
    // surfaces non-fatally through the lint path; previously warnings were silently dropped.
    if (result.ok) {
      return { ok: true, warnings: result.warnings };
    }
    return { ok: false, errors: result.errors, warnings: result.warnings };
  }
  return validateFrontmatter(frontmatter, schema);
}

/**
 * Validate a parsed record object against a JSON Schema (draft-2020-12 subset),
 * then apply CROSS_FIELD_RULES keyed by schema name (hybrid validation).
 *
 * schemaOrName — either:
 *   - a JSON Schema object. Schema name for cross-field rules is read from
 *     schemaOrName['x-schema-name'] (string) when present.
 *   - a string schema name. Looked up in the module-level _jsonSchemaCache,
 *     which is populated by loadSchemas when .schema.json files are present.
 *
 * options (optional):
 *   { mode: 'read' | 'write' }
 *   Controls the schema-version gate behaviour (W2 ccos-1):
 *     'read'  (default) — warn-on-newer-read: non-fatal warning in result.warnings
 *     'write'           — refuse-on-newer-write: FAIL loud in result.errors
 *   When mode is omitted the gate uses 'read' semantics (backward-compatible default).
 *   Schemas and records without x-schema-version / schema_version skip the gate entirely.
 *
 * Returns {ok: boolean, errors?: [{field, error, hint}], warnings: [{field, error, hint}]}.
 *   warnings is always present (empty array when no version-gate warnings fired).
 *
 * Spec backlinks:
 *   W1: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 2
 *   W2: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2
 * Negative-spec: this validates a pre-parsed record object, NOT a frontmatter string.
 *   If you have raw markdown, call parseFrontmatter first, then pass the result here.
 */
function validateRecord(record, schemaOrName, options) {
  const mode = (options && typeof options === 'object' && options.mode === 'write') ? 'write' : 'read';
  let jsonSchema, schemaName;

  if (typeof schemaOrName === 'string') {
    schemaName = schemaOrName;
    jsonSchema = _jsonSchemaCache[schemaName];
    if (!jsonSchema) {
      return {
        ok: false,
        errors: [{
          field: '(schema)',
          error: `JSON Schema "${schemaName}" not found in cache — call loadSchemas(schemasDir) first`,
          hint: `Ensure schemas/${schemaName}.schema.json exists and loadSchemas has been called`
        }],
        warnings: []
      };
    }
  } else if (schemaOrName !== null && typeof schemaOrName === 'object') {
    jsonSchema = schemaOrName;
    schemaName = typeof jsonSchema['x-schema-name'] === 'string' ? jsonSchema['x-schema-name'] : null;
  } else {
    return {
      ok: false,
      errors: [{
        field: '(schema)',
        error: 'schemaOrName must be a JSON Schema object or a schema name string',
        hint: 'Pass a JSON Schema object directly or a string name for a schema loaded via loadSchemas'
      }],
      warnings: []
    };
  }

  // Phase 0 (W2 ccos-1): schema-version gate.
  //
  // Compares the record's declared schema_version against the schema file's x-schema-version.
  // Only gates on MAJOR version differences — minor/patch bumps are backward-compatible by
  // semver convention and do not trigger the gate.
  //
  // warn-on-newer-read (default, mode='read'):
  //   record.schema_version major > schema.x-schema-version major → non-fatal warning.
  //   The consumer is behind; validation continues but the caller is notified.
  //   Expected when the producer has bumped a major and the consumer has not yet been widened.
  //
  // refuse-on-newer-write (mode='write'):
  //   Same condition → FAIL loud. A producer must not emit records against a stale schema.
  //   Upgrade the vendored schema (widen-reader-first per cross-repo ordering) before writing.
  //
  // Opt-in: records without schema_version or schemas without x-schema-version are no-ops.
  // Spec backlink: docs/wiki/schema-version-gate.md
  const warnings = [];
  const recordVersionRaw = record !== null && typeof record === 'object' ? record['schema_version'] : undefined;
  const schemaVersionRaw = jsonSchema['x-schema-version'];
  if (recordVersionRaw != null && schemaVersionRaw != null) {
    const rv = parseSemver(String(recordVersionRaw));
    const sv = parseSemver(String(schemaVersionRaw));
    if (rv !== null && sv !== null && rv.major > sv.major) {
      const versionMsg = {
        field: 'schema_version',
        error: `record schema_version "${recordVersionRaw}" major (${rv.major}) exceeds vendored schema x-schema-version "${schemaVersionRaw}" major (${sv.major})`,
        hint: mode === 'write'
          ? 'refuse-on-newer-write: upgrade the vendored schema before writing records at this version — see docs/wiki/schema-version-gate.md'
          : 'warn-on-newer-read: consumer is behind; widen the consumer schema before the next major producer bump (reader-first ordering) — see docs/wiki/schema-version-gate.md'
      };
      if (mode === 'write') {
        // refuse-on-newer-write: fail loud before shape/cross-field validation.
        return { ok: false, errors: [versionMsg], warnings };
      }
      // mode === 'read': warn-on-newer-read (non-fatal; shape + cross-field validation proceeds).
      warnings.push(versionMsg);
    }
  }

  // Phase 1: shape validation via the dep-free JSON Schema subset validator.
  const shapeErrors = validateJsonSchemaNode(record, jsonSchema, jsonSchema, '');

  // Phase 2: cross-field rules — same registry as validateFrontmatter, keyed by schema name.
  // DO NOT rewrite or simplify CROSS_FIELD_RULES — it stays as imperative JS (conditional-required
  // couplings, grandfather DATE cutoffs, length caps, optional-field enums, realized_by shape checks).
  const crossErrors = schemaName ? applyCrossFieldRules(record, { schema: schemaName }) : [];

  const allErrors = [...shapeErrors, ...crossErrors];
  return allErrors.length === 0
    ? { ok: true, warnings }
    : { ok: false, errors: allErrors, warnings };
}

/**
 * Run the negative-corpus regression sweep (AC5b oracle).
 *
 * Reads expected-rejections.json from fixturesDir, loads each .md fixture,
 * validates it via validateFrontmatter against its declared schema, and
 * asserts each is rejected as expected.
 *
 * Returns { passed, failed, total, results }.
 * When failed > 0, the W1 rewrite has broken the .yaml-dialect validation path.
 *
 * Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W1 Deliverable 6
 */
function testNegativeCorpus(fixturesDir, schemasDir) {
  const indexPath = path.join(fixturesDir, 'expected-rejections.json');
  const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
  const schemas = loadSchemas(schemasDir);

  const results = [];
  let passed = 0;
  let failed = 0;

  for (const entry of index.fixtures) {
    const fixturePath = path.join(fixturesDir, entry.fixture);
    const content = fs.readFileSync(fixturePath, 'utf8');
    const { frontmatter } = parseFrontmatter(content);
    const schema = schemas[entry.schema];
    const result = validateFrontmatter(frontmatter, schema);

    // entry.expect_ok is false for all negative corpus fixtures; a correctly-behaving
    // validator returns ok:false for each. A pass here means the validator rejected
    // the fixture as expected.
    const pass = result.ok === entry.expect_ok;
    results.push({
      fixture: entry.fixture,
      schema: entry.schema,
      result_ok: result.ok,
      expected_ok: entry.expect_ok,
      pass,
      errors: result.errors || [],
    });

    if (pass) passed++;
    else failed++;
  }

  return { passed, failed, total: results.length, results };
}

module.exports = {
  loadSchemas,
  matchSchema,
  matchSchemaForPath,
  parseFrontmatter,
  // Write-side frontmatter primitives (raw-text field edits) — canonical home
  // for the handoff-transition.js / memo-transition.js /
  // normalize-consumed-frontmatter.js / stamp-shipped-in.js CLIs.
  splitFrontmatter,
  readFmField,
  serializeYamlScalar,
  replaceFmField,
  insertFmField,
  removeFmField,
  validateFrontmatter,
  validateFrontmatterDispatch,
  validateLessonsFile,
  validateRecord,
  testNegativeCorpus,
  // Public YAML-block parser: parses a frontmatter body (no --- delimiters) into an object.
  // Consumed by handoff-transition.js validateHandoffFrontmatter; the `_parseYaml` alias below
  // is the same function retained for existing test imports.
  // Exported as `parseYaml` for whole-document-yaml mode consumers (validate-frontmatter-schema.js).
  parseYaml,
  parseYamlBlock: parseYaml,
  // Cross-field rule runner addressed by schema name — consumed by memo-transition.js.
  applyCrossFieldRulesFor,
  // Resolver-seam existence + never-silently-disagree check for local handoff-DAG
  // ID refs (predecessor_id, origin_handoff_id). Opt-in — cadence gates call this
  // explicitly; CROSS_FIELD_RULES/validateFrontmatter/validateRecord never call it.
  checkReferentialIntegrity,
  // Exported for testing
  _parseScalar: parseScalar,
  _parseYaml: parseYaml,
  _matchGlob: matchGlob,
  _stripCodeSpansAndLinks: stripCodeSpansAndLinks,
  _stripInlineComment: stripInlineComment,
  _isJsonSchemaBacked: isJsonSchemaBacked,
};

// ---------------------------------------------------------------------------
// CLI: --test-negative-corpus
// Run the negative-corpus regression sweep from the command line:
//   node bin/lib/schema.js --test-negative-corpus [fixturesDir [schemasDir]]
//
// Defaults:
//   fixturesDir = bin/tests/fixtures/validator-negative
//   schemasDir  = schemas/
// ---------------------------------------------------------------------------
if (require.main === module && process.argv.includes('--test-negative-corpus')) {
  const scriptDir = __dirname;
  const defaultFixturesDir = path.resolve(scriptDir, '../tests/fixtures/validator-negative');
  const defaultSchemasDir = path.resolve(scriptDir, '../../schemas');
  const flagIdx = process.argv.indexOf('--test-negative-corpus');
  const fixturesDir = process.argv[flagIdx + 1] || defaultFixturesDir;
  const schemasDir = process.argv[flagIdx + 2] || defaultSchemasDir;

  const { passed, failed, total, results } = testNegativeCorpus(fixturesDir, schemasDir);

  for (const r of results) {
    if (r.pass) {
      process.stdout.write(`PASS ${r.fixture} (correctly rejected)\n`);
    } else {
      process.stdout.write(`FAIL ${r.fixture} — expected ok:${r.expected_ok}, got ok:${r.result_ok}\n`);
      if (r.errors && r.errors.length > 0) {
        process.stdout.write(`  errors: ${JSON.stringify(r.errors)}\n`);
      }
    }
  }

  process.stdout.write(`\n${passed}/${total} fixtures correctly rejected (${failed} unexpected passes)\n`);
  process.exit(failed > 0 ? 1 : 0);
}
