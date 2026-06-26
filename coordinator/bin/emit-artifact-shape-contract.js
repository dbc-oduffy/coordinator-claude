'use strict';
/**
 * emit-artifact-shape-contract.js — emit a versioned JSON Schema contract from the
 * coordinator schema registry (schemas/*.yaml).
 *
 * PURPOSE
 * Emits `artifact-shape-contract/artifact-shape-contract.schema.json` — a stable,
 * versioned JSON Schema contract (draft-2020-12) carrying:
 *   (a) One JSON Schema per registered schema type (under `$defs`).
 *   (b) The cross-type liveness mapping as first-class contract data (tc-0 D2 forward
 *       seam) — so tc-5 (project-rag store) can derive LIVE/BLOCKED/DONE without
 *       re-reading or re-implementing bin/query-records.js in another language.
 *
 * DESIGN DECISIONS (tc-4 § Ratified design decisions)
 *   D1 — JSON Schema format (cockpit-contract parity); target: draft-2020-12.
 *   D2 — ONE registry-wide `version` ("1.0.0"); NOT per-type versions.
 *   D3 — Artifact named by CAPABILITY: `artifact-shape-contract`. Consumers
 *        (project-rag, opticon) are NOT part of the producer surface.
 *
 * PATTERN REUSE (not coupling)
 * Reuses cockpit-contract emit patterns (cockpit-contract/scripts/emit-schema.ts:
 * versioned bundle + per-entity schema files). Source here is YAML registry, not
 * Zod TypeScript. Separate artifact, separate version line, no shared module.
 *
 * Spec backlink: archive/specs/2026-06/2026-06-25-qffs-tc-4-fleet-machinery-contract-emit.md § Chunk B1
 */

const fs   = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONTRACT_VERSION = '1.0.0';

const HERE          = __dirname;
const COORDINATOR   = path.join(HERE, '..');
const SCHEMAS_DIR   = path.join(COORDINATOR, 'schemas');

// Honour an override env var so the test can redirect output to a tmp dir.
const OUT_DIR = process.env.ARTIFACT_CONTRACT_OUT_DIR
  ? path.resolve(process.env.ARTIFACT_CONTRACT_OUT_DIR)
  : path.join(COORDINATOR, 'artifact-shape-contract');

// ---------------------------------------------------------------------------
// Minimal YAML-schema → JSON Schema converter
// ---------------------------------------------------------------------------

/**
 * Convert a field descriptor from the coordinator YAML schema subset into a
 * JSON Schema fragment.
 *
 * Supported field types (the full set used in schemas/*.yaml):
 *   string        → { type: 'string' }
 *   iso-date      → { type: 'string', format: 'date' }
 *   boolean       → { type: 'boolean' }
 *   number        → { type: 'number' }
 *   list-of-string → { type: 'array', items: { type: 'string' } }
 *   string-or-null → { type: ['string', 'null'] }
 *   { type: enum, values: [...] } → { enum: [...] }
 *
 * Unrecognised descriptors are emitted as `{}` (permissive) with a note in the
 * returned fragment's description — never silently dropped.
 *
 * @param {string} fieldName
 * @param {*} descriptor  — the value under the field name in required:/optional:
 * @returns {object}      JSON Schema fragment
 */
function fieldToJsonSchema(fieldName, descriptor) {
  if (typeof descriptor === 'string') {
    switch (descriptor) {
      case 'string':         return { type: 'string' };
      case 'iso-date':       return { type: 'string', format: 'date' };
      case 'boolean':        return { type: 'boolean' };
      case 'number':         return { type: 'number' };
      case 'list-of-string': return { type: 'array', items: { type: 'string' } };
      case 'string-or-null': return { type: ['string', 'null'] };
      default:
        // Unknown scalar type — emit permissive with a description note.
        return { description: `[emit-note] unrecognised field type "${descriptor}" for field "${fieldName}"` };
    }
  }
  if (descriptor && typeof descriptor === 'object') {
    if (descriptor.type === 'enum' && Array.isArray(descriptor.values)) {
      return { enum: descriptor.values };
    }
    if (descriptor.type === 'string') return { type: 'string' };
    if (descriptor.type === 'list-of-string') return { type: 'array', items: { type: 'string' } };
    // Nested object descriptor we don't recognise — permissive with a note.
    return { description: `[emit-note] unrecognised descriptor for field "${fieldName}": ${JSON.stringify(descriptor)}` };
  }
  // null / undefined
  return { description: `[emit-note] null/missing descriptor for field "${fieldName}"` };
}

/**
 * Convert a parsed coordinator YAML schema object to a JSON Schema object.
 *
 * @param {string} schemaName   e.g. 'handoff'
 * @param {object} schema       parsed schema from loadSchemas
 * @param {string} srcFile      source YAML filename for the title annotation
 * @returns {object}            JSON Schema (draft-2020-12)
 */
function schemaToJsonSchema(schemaName, schema, srcFile) {
  const properties = {};
  const required   = [];

  // Process required fields
  if (schema.required && typeof schema.required === 'object' && !Array.isArray(schema.required)) {
    for (const [field, descriptor] of Object.entries(schema.required)) {
      properties[field] = fieldToJsonSchema(field, descriptor);
      required.push(field);
    }
  }

  // Process optional fields
  if (schema.optional && typeof schema.optional === 'object' && !Array.isArray(schema.optional)) {
    for (const [field, descriptor] of Object.entries(schema.optional)) {
      properties[field] = fieldToJsonSchema(field, descriptor);
      // optional fields are NOT added to required[]
    }
  }

  const jsonSchema = {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    title: schemaName,
    description: `Coordinator artifact schema: ${schemaName}. Source: schemas/${srcFile}.`,
    type: 'object',
    properties,
  };

  if (required.length > 0) {
    jsonSchema.required = required;
  }

  // Carry applies_to as x- extension — not JSON Schema, but useful for consumers.
  if (schema.applies_to) {
    jsonSchema['x-coordinator-applies_to'] = schema.applies_to;
  }

  return jsonSchema;
}

// ---------------------------------------------------------------------------
// Cross-type liveness mapping (first-class contract data)
// ---------------------------------------------------------------------------
// Transcribed from bin/query-records.js liveness() + canonical-artifact-shapes.md
// § The Cross-Type Liveness Predicate. This is the forward seam for tc-5: project-rag
// derives its LIVE/BLOCKED/DONE derivation FROM this published mapping — it does NOT
// re-read query-records.js.
//
// Format: array of rule objects. Rules are evaluated in order; first match wins.
//   { type, key, value, liveness }            — exact single-field match
//   { type, key, value, liveness, guard }      — match only when guard field present
//   { type, axes, combination_rule, ... }      — two-axis combination (handoff only)
//   { type, liveness, note }                   — fallback/default for a type
// ---------------------------------------------------------------------------

const LIVENESS_MAPPING = {
  version: CONTRACT_VERSION,
  spec_backlink: 'docs/wiki/canonical-artifact-shapes.md § The Cross-Type Liveness Predicate',
  implementation_ref: 'bin/query-records.js liveness(fm, type)',
  note: 'Rules evaluated in order; first match wins. Unknown values resolve LIVE (open posture).',
  types: {
    handoff: {
      combination_rule: 'two-axis',
      note: 'status and deployment_state combine; see axes.',
      axes: {
        status: {
          consumed:   'DONE',
          superseded: 'DONE',
          // active: depends on deployment_state (handled by combination rule)
        },
        deployment_state: {
          awaiting_gate: 'BLOCKED',
          ready_to_fire: 'LIVE',
          in_flight:     'LIVE',
          shipped:       'DONE',
          abandoned:     'DONE',
        },
      },
      combination_logic: [
        { condition: 'status ∈ {consumed,superseded} OR deployment_state ∈ {shipped,abandoned}', result: 'DONE' },
        { condition: 'deployment_state == awaiting_gate', result: 'BLOCKED' },
        { condition: 'otherwise', result: 'LIVE' },
      ],
    },
    'handoff-archived': {
      note: 'Same schema and combination rule as handoff.',
      combination_rule: 'two-axis',
      ref: 'handoff',
    },
    'cross-repo-memo': {
      combination_rule: 'single-axis',
      axis: 'status',
      mapping: {
        open:         'LIVE',
        in_progress:  'LIVE',
        actioned:     'DONE',
        reviewed:     'DONE',    // back-compat alias
        action_taken: 'DONE',   // back-compat alias
        closed:       'DONE',   // back-compat alias
        superseded:   'DONE',   // back-compat alias
      },
      default: 'LIVE',
    },
    plan: {
      combination_rule: 'single-axis',
      axis: 'status',
      note: 'deployment_state is IGNORED for plan (plans have no deployment_state).',
      mapping: {
        draft:       'LIVE',
        reviewed:    'LIVE',
        approved:    'LIVE',
        executing:   'LIVE',
        implemented: 'DONE',
        deferred:    'BLOCKED',
        abandoned:   'DONE',
        superseded:  'DONE',
      },
      default: 'LIVE',
    },
    decision: {
      combination_rule: 'single-axis',
      axis: 'status',
      note: 'An accepted decision record is terminal — no further lifecycle transitions expected.',
      mapping: {
        proposed:   'LIVE',
        accepted:   'DONE',
        deprecated: 'DONE',
        superseded: 'DONE',
      },
      default: 'LIVE',
    },
    'improvement-queue': {
      combination_rule: 'single-axis',
      axis: 'status',
      query_type: 'improvement',
      mapping: {
        open:     'LIVE',
        closed:   'DONE',
        deferred: 'BLOCKED',
      },
      default: 'LIVE',
    },
    'bug-backlog': {
      combination_rule: 'single-axis',
      axis: 'status',
      query_type: 'bug',
      mapping: {
        open:     'LIVE',
        closed:   'DONE',
        wontfix:  'DONE',
        deferred: 'BLOCKED',
      },
      default: 'LIVE',
      notes: {
        wontfix: 'Terminal — conscious rejection, not deferred work.',
      },
    },
    'debt-backlog': {
      combination_rule: 'single-axis',
      axis: 'status',
      query_type: 'debt',
      mapping: {
        open:     'LIVE',
        closed:   'DONE',
        deferred: 'BLOCKED',
      },
      default: 'LIVE',
    },
    lesson: {
      combination_rule: 'single-axis',
      axis: 'status',
      note: 'Status is derived at query time by parseLessonsFile from prose conventions; not a stored frontmatter field.',
      mapping: {
        resolved: 'DONE',
        open:     'LIVE',
      },
      default: 'LIVE',
    },
  },
};

// ---------------------------------------------------------------------------
// Main emit
// ---------------------------------------------------------------------------

function main() {
  // Load schemas via the existing schema.js loader (reuse its YAML parser,
  // loadSchemas function, and schema normalisation — no parallel impl).
  const schemaJs = require(path.join(COORDINATOR, 'bin', 'lib', 'schema.js'));
  const schemas  = schemaJs.loadSchemas(SCHEMAS_DIR);

  // Collect schema names (exclude internal _byGlob / _byKind indexes).
  const schemaNames = Object.keys(schemas).filter(k => !k.startsWith('_'));

  if (schemaNames.length === 0) {
    process.stderr.write('emit-artifact-shape-contract: SCHEMAS is empty — refusing to emit an empty contract.\n');
    process.exit(1);
  }

  // Build per-type JSON Schema definitions.
  const defs    = {};
  let   count   = 0;
  const issues  = [];

  for (const name of schemaNames.sort()) {
    const schema   = schemas[name];
    const srcFile  = `${name}.yaml`;
    try {
      defs[name] = schemaToJsonSchema(name, schema, srcFile);
      count++;
    } catch (err) {
      issues.push(`schema "${name}": ${err.message}`);
    }
  }

  if (issues.length > 0) {
    process.stderr.write('emit-artifact-shape-contract: schema translation issues:\n');
    for (const issue of issues) {
      process.stderr.write(`  - ${issue}\n`);
    }
    // Do not fail — emit with issues noted (per spec: "note rather than silently drop").
  }

  // Build the bundle.
  // Review: code-reviewer ROBUSTNESS — `emitted_at` dropped: it created per-run diff churn
  //   and broke vendor byte-equality checks. `version` is the pinnable identity for consumers.
  const bundle = {
    $schema:     'https://json-schema.org/draft/2020-12/schema',
    $id:         'https://coordinator.local/artifact-shape-contract.schema.json',
    title:       'Coordinator artifact shape contract',
    description: `Versioned JSON Schema contract for all coordinator tracked artifact types (tc-4 B1). Single registry-wide version ${CONTRACT_VERSION}. Consumers vendor this file for a pinned shape; project-rag/opticon are consumers, not part of the producer surface.`,
    version:     CONTRACT_VERSION,
    schema_count: count,
    $defs:        defs,
    liveness_mapping: LIVENESS_MAPPING,
  };

  // Write output.
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const outFile = path.join(OUT_DIR, 'artifact-shape-contract.schema.json');
  fs.writeFileSync(outFile, JSON.stringify(bundle, null, 2) + '\n');

  console.log(`emitted ${count} schemas → ${outFile}`);
  console.log(`contract version: ${CONTRACT_VERSION}`);
  if (issues.length > 0) {
    console.log(`translation issues (noted in stderr): ${issues.length}`);
  }
}

main();
