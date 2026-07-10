'use strict';
/**
 * schema-cli.js — thin CLI over schema.js exposing schema introspection and
 * record validation to Python callers.
 *
 * Purpose: subprocess-friendly JSON bridge for Python callers that shell out
 * after the Python parser is retired. Honors COORDINATOR_SCHEMAS_DIR for
 * consumer-test schema isolation so tests can redirect to fixture schema dirs
 * without touching production schemas.
 *
 * Modes:
 *   --describe <schema-name>
 *       Load the named schema, emit JSON to stdout:
 *         { "required": [<field names in schema order>],
 *           "optional": [<field names in order>],
 *           "enums":    { <field>: [<values>], ... } }
 *       required/optional are ORDERED arrays of field names (schema YAML order).
 *       enums maps top-level fields that declare an enum type to their value lists.
 *       Exit 0 on success.
 *
 *   --validate <schema-name>
 *       Read a record as JSON from stdin, validate via validateFrontmatterDispatch,
 *       emit JSON to stdout: { "ok": <bool>, "errors": [<error strings>] }.
 *       Exit 0 if ok, exit 1 if not ok, exit 2 on malformed stdin JSON.
 *
 * Env:
 *   COORDINATOR_SCHEMAS_DIR — override the schemas directory (default: ../schemas
 *     relative to this file's location). When set and the directory contains no
 *     .yaml or .schema.json schema files, fails loud with non-zero exit so consumer
 *     tests that redirect to a fixture dir catch misconfiguration immediately.
 *
 * Spec backlink: (dual-yaml-parser option-d, C2)
 * Negative-spec: does NOT modify schema.js; uses only its stable exports.
 */

const fs = require('fs');
const path = require('path');
const { loadSchemas, validateFrontmatterDispatch, _isJsonSchemaBacked } = require('./lib/schema.js');

// ---------------------------------------------------------------------------
// Schema dir resolution — env var override takes precedence over default.
// ---------------------------------------------------------------------------
const DEFAULT_SCHEMAS_DIR = path.resolve(__dirname, '../schemas');
const schemasDir = process.env.COORDINATOR_SCHEMAS_DIR || DEFAULT_SCHEMAS_DIR;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Write an error to stderr and exit with a non-zero status.
 * No return — process.exit terminates execution.
 */
function failLoud(msg) {
  process.stderr.write(`schema-cli: error: ${msg}\n`);
  process.exit(1);
}

/**
 * Load schemas, with a fail-loud empty-dir guard when COORDINATOR_SCHEMAS_DIR is set.
 * Purpose: consumer tests that redirect to an empty or wrong fixture dir get an
 * immediate error rather than a silent "unknown schema" later.
 */
function loadSchemasOrDie() {
  if (process.env.COORDINATOR_SCHEMAS_DIR) {
    let entries = [];
    try {
      entries = fs.readdirSync(schemasDir);
    } catch (err) {
      failLoud(`COORDINATOR_SCHEMAS_DIR="${schemasDir}" cannot be read: ${err.message}`);
      return; // unreachable; satisfies static analysis
    }
    const schemaFiles = entries.filter(f => f.endsWith('.yaml') || f.endsWith('.schema.json'));
    if (schemaFiles.length === 0) {
      failLoud(
        `COORDINATOR_SCHEMAS_DIR="${schemasDir}" is set but contains no .yaml or .schema.json schema files`
      );
      return; // unreachable; satisfies static analysis
    }
  }

  try {
    return loadSchemas(schemasDir);
  } catch (err) {
    failLoud(`failed to load schemas from "${schemasDir}": ${err.message}`);
  }
}

/**
 * Extract the enum value list from a YAML-dialect field spec.
 * Returns the values array when the spec is { type: 'enum', values: [...] }, null otherwise.
 */
function extractEnumValues(spec) {
  if (spec && typeof spec === 'object' && spec.type === 'enum' && Array.isArray(spec.values)) {
    return spec.values;
  }
  return null;
}

/**
 * Describe a YAML-dialect schema.
 * Returns { required: string[], optional: string[], enums: Record<string, string[]> }.
 * Field name arrays preserve schema YAML key insertion order.
 */
function describeYamlSchema(schema) {
  const required = schema.required ? Object.keys(schema.required) : [];
  const optional = schema.optional ? Object.keys(schema.optional) : [];
  const enums = {};

  if (schema.required) {
    for (const [field, spec] of Object.entries(schema.required)) {
      const vals = extractEnumValues(spec);
      if (vals !== null) enums[field] = vals;
    }
  }
  if (schema.optional) {
    for (const [field, spec] of Object.entries(schema.optional)) {
      const vals = extractEnumValues(spec);
      if (vals !== null) enums[field] = vals;
    }
  }

  return { required, optional, enums };
}

/**
 * Describe a JSON-Schema-backed schema.
 * Returns { required: string[], optional: string[], enums: Record<string, string[]> }.
 * required preserves the order declared in the JSON Schema `properties` object
 * filtered to those listed in `required`; optional is the remainder.
 */
function describeJsonSchema(schema) {
  const properties = schema.properties || {};
  const requiredSet = new Set(Array.isArray(schema.required) ? schema.required : []);
  const allProps = Object.keys(properties);
  const required = allProps.filter(k => requiredSet.has(k));
  const optional = allProps.filter(k => !requiredSet.has(k));
  const enums = {};

  for (const [field, propSchema] of Object.entries(properties)) {
    if (propSchema && Array.isArray(propSchema.enum)) {
      enums[field] = propSchema.enum;
    }
  }

  return { required, optional, enums };
}

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const mode = args[0];
const schemaName = args[1];

if (!mode) {
  failLoud('missing mode. Usage: schema-cli.js --describe <schema-name> | --validate <schema-name>');
}

if (mode !== '--describe' && mode !== '--validate') {
  failLoud(`unknown mode "${mode}". Use --describe or --validate`);
}

if (!schemaName) {
  failLoud(`missing schema name. Usage: schema-cli.js ${mode} <schema-name>`);
}

// ---------------------------------------------------------------------------
// Load schemas
// ---------------------------------------------------------------------------

const schemas = loadSchemasOrDie();

const schema = schemas[schemaName];
if (!schema || schemaName === '_byGlob' || schemaName === '_byKind') {
  const available = Object.keys(schemas)
    .filter(k => k !== '_byGlob' && k !== '_byKind')
    .join(', ');
  failLoud(`unknown schema "${schemaName}". Available: ${available}`);
}

// ---------------------------------------------------------------------------
// --describe mode
// ---------------------------------------------------------------------------

if (mode === '--describe') {
  const result = _isJsonSchemaBacked(schema)
    ? describeJsonSchema(schema)
    : describeYamlSchema(schema);
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  process.exit(0);
}

// ---------------------------------------------------------------------------
// --validate mode
// ---------------------------------------------------------------------------

if (mode === '--validate') {
  let input = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => { input += chunk; });
  process.stdin.on('end', () => {
    let record;
    try {
      record = JSON.parse(input);
    } catch (err) {
      process.stderr.write(`schema-cli: error: malformed JSON on stdin: ${err.message}\n`);
      process.exit(2);
    }

    const result = validateFrontmatterDispatch(record, schema);
    const ok = result.ok === true;
    const errors = ok
      ? []
      : (result.errors || []).map(e => {
          if (typeof e === 'string') return e;
          const fieldPart = e.field ? `${e.field}: ` : '';
          return `${fieldPart}${e.error || ''}`;
        });

    process.stdout.write(JSON.stringify({ ok, errors }, null, 2) + '\n');
    process.exit(ok ? 0 : 1);
  });
}
