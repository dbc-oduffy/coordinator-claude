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
 *        (project-rag, cockpit) are NOT part of the producer surface.
 *
 * PATTERN REUSE (not coupling)
 * Reuses cockpit-contract emit patterns (cockpit-contract/scripts/emit-schema.ts:
 * versioned bundle + per-entity schema files). Source here is YAML registry, not
 * Zod TypeScript. Separate artifact, separate version line, no shared module.
 *
 * Spec backlink: archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk B1
 */

const fs   = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONTRACT_VERSION = '1.14.0';
// Review: code-reviewer — F2 (EM disposition): KEEP 1.9.0 (not 2.0.0). This contract has no
// vendored consumer — cockpit is stub-stage, project-rag never consumed session-events-summary,
// and assertSchemaVersion is not called against this contract (unlike cockpit-contract). For an
// in-flight contract with zero vendored consumers, removing a $defs entry is a non-breaking
// change; minor (1.9.0) is correct. Bump to 2.0.0 only when a consumer pins a version assertion.
// 1.10.0 (2026-07-03): additive minor — injected the ProvenanceEnvelope sub-shape; still additive-only, still no version-asserting consumer, so minor is correct.
// 1.11.0 (2026-07-03): same-day correction of unconsumed 1.10.0 — ProvenanceEnvelope ref key-absent → present-as-null + bidirectional conditional (D9).
// 1.12.0 (2026-07-05): additive — extended ProvenanceEnvelope.source_kind with 'git_commit' (git-backed commit-trailer stream, example-orchestration-hub commit.anchors op); joins the ref-non-null conditional. Additive-only, no consumer re-vendor forced. Discharges example-orchestration-hub freeze-gate item 2 (cross-repo/inbox/2026-07-05-example-orchestration-hub-commit-trailer-frozen-source-kind-enum.md).
// 1.12.0 (2026-07-09): correction — added 'computed' to derivation enum in emitter SOURCE to match the already-shipped OUTPUT (d8d5bb46 hand-patched the committed artifact's enum without updating the emitter; this closes that source/output drift). No version bump — the value was already live in the committed contract.
// 1.13.0 (2026-07-09): additive — schemas/plan-tasks.schema.json registered (48th schema; plan-full-coverage-and-deferred-harvest chunk C1). New $def for the ## Tasks task-spine per-row shape, $ref'd from plan.schema.json's new `tasks` property. Additive-only (schema_count delta 47→48 per the CONTRACT_VERSION bump rule), no consumer re-vendor forced.
// 1.14.0 (2026-07-10): additive — extended ProvenanceEnvelope.source_kind with 'transcript_summary' (consumer-emitted agentically-derived transcript summary; NOT git-backed, carries ref:null). Joins the ref-NULL D9 conditional branch alongside local_fs/coordinator_artifact. Additive-only, no consumer re-vendor forced. Serves project-rag DR-PRAG-042 (cross-repo/inbox/2026-07-10-project-rag-em-transcript-summary-source-kind-widen.md).

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
 *   string               → { type: 'string' }
 *   iso-date             → { type: 'string', format: 'date' }
 *   iso-datetime         → { type: 'string', format: 'date-time' }
 *   timestamp            → { type: 'string', format: 'date-time' }  (alias for iso-datetime)
 *   iso-date-or-datetime → { anyOf: [ date, date-time ] }  (permissive — reader-tolerate legacy/mixed corpora)
 *   boolean              → { type: 'boolean' }
 *   number               → { type: 'number' }
 *   list-of-string       → { type: 'array', items: { type: 'string' } }
 *   string-or-null       → { type: ['string', 'null'] }
 *   any                  → { description: '…' } (permissive, no type — for unstructured hand-authored values)
 *   { type: enum, values: [...] } → { enum: [...] }
 *
 * Unrecognised descriptors are emitted as `{}` (permissive) with a note in the
 * returned fragment's description — never silently dropped.
 *
 * @param {string} fieldName
 * @param {*} descriptor  — the value under the field name in required:/optional:
 * @returns {object}      JSON Schema fragment
 */
const SCALAR_TYPES = {
  'string':               { type: 'string' },
  'iso-date':             { type: 'string', format: 'date' },
  'iso-datetime':         { type: 'string', format: 'date-time' },
  'timestamp':            { type: 'string', format: 'date-time' },
  'iso-date-or-datetime': { anyOf: [ { type: 'string', format: 'date' }, { type: 'string', format: 'date-time' } ] },
  'boolean':              { type: 'boolean' },
  'number':         { type: 'number' },
  'list-of-string': { type: 'array', items: { type: 'string' } },
  'string-or-null': { type: ['string', 'null'] },
  'number-or-null': { type: ['number', 'null'] },
  'string-or-list-of-string': { anyOf: [{ type: 'string' }, { type: 'array', items: { type: 'string' } }] },
  'any':            { description: 'heterogeneous hand-authored value — permissive by design (no type enforcement)' },
};

function fieldToJsonSchema(fieldName, descriptor) {
  if (typeof descriptor === 'string') {
    // Review: code-reviewer F3 — use structuredClone instead of shallow spread so the
    // iso-date-or-datetime token's nested anyOf array is not shared by reference across
    // all fields that use it (latent mutation hazard if any downstream consumer mutates
    // the returned fragment). Node 17+ required; this repo runs modern Node.
    if (SCALAR_TYPES[descriptor]) return structuredClone(SCALAR_TYPES[descriptor]);
    // Unknown scalar type — emit permissive with a description note.
    return { description: `[emit-note] unrecognised field type "${descriptor}" for field "${fieldName}"` };
  }
  if (descriptor && typeof descriptor === 'object') {
    if (descriptor.type === 'enum' && Array.isArray(descriptor.values)) {
      const frag = { enum: descriptor.values };
      if (descriptor.description) frag.description = descriptor.description;
      return frag;
    }
    if (descriptor.type === 'object' && descriptor.fields && typeof descriptor.fields === 'object') {
      const properties = {};
      for (const [subName, subDesc] of Object.entries(descriptor.fields)) {
        properties[subName] = fieldToJsonSchema(`${fieldName}.${subName}`, subDesc);
      }
      const frag = { type: 'object', properties };
      if (descriptor.description) frag.description = descriptor.description;
      return frag;
    }
    if (typeof descriptor.type === 'string' && SCALAR_TYPES[descriptor.type]) {
      const frag = { ...SCALAR_TYPES[descriptor.type] };
      if (descriptor.description) frag.description = descriptor.description;
      return frag;
    }
    // Bare-nested-object: a plain map of field→descriptor with no `type` wrapper.
    // Used by bug-backlog, debt-backlog, improvement-queue, lesson-entry for their
    // `system` field. Equivalent to {type:'object', fields:{...}} — detect by absence
    // of a `type` key on the outer object and recurse over its entries as properties.
    if (!('type' in descriptor)) {
      const properties = {};
      for (const [subName, subDesc] of Object.entries(descriptor)) {
        properties[subName] = fieldToJsonSchema(`${fieldName}.${subName}`, subDesc);
      }
      return { type: 'object', properties };
    }
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
  // JSON-Schema-backed schemas (stamped with non-enumerable _isJsonSchema by loadSchemas)
  // are already in full JSON Schema format — pass their properties through directly
  // instead of running the YAML-subset translation, which produces empty properties for
  // these schemas (their `required` is an array, not a field→descriptor map).
  // Spec backlink: emit-artifact-shape-contract.js fix 2026-06-30 — failures 1,3,4,5.
  const jsonSchemaMeta = Object.getOwnPropertyDescriptor(schema, '_isJsonSchema');
  if (jsonSchemaMeta && jsonSchemaMeta.value === true) {
    const emitted = {
      $schema: 'https://json-schema.org/draft/2020-12/schema',
      title: schemaName,
      description: schema.description ||
        `Coordinator artifact schema: ${schemaName}. Source: schemas/${srcFile}.`,
      type: schema.type || 'object',
    };
    if (schema.properties && typeof schema.properties === 'object') {
      emitted.properties = schema.properties;
    }
    // required is an array in JSON Schema format; only carry it when non-empty.
    if (Array.isArray(schema.required) && schema.required.length > 0) {
      emitted.required = schema.required;
    }
    if (schema.applies_to) {
      emitted['x-coordinator-applies_to'] = schema.applies_to;
    }
    return emitted;
  }

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
    roadmap: {
      combination_rule: 'single-axis',
      axis: 'status',
      note: 'Forward horizon/portfolio record. blocked resolves LIVE (in-flight), NOT the BLOCKED liveness bucket — that bucket is reserved for handoff awaiting_gate and plan deferred. Spec: example-initiative example-workstream example-repo Ask 1.',
      mapping: {
        planning: 'LIVE',
        active:   'LIVE',
        blocked:  'LIVE',
        shipped:  'DONE',
        archived: 'DONE',
      },
      default: 'LIVE',
    },
    tracker: {
      combination_rule: 'single-axis',
      axis: 'status',
      note: 'Current status board / action register; one per repo. Spec: example-initiative example-workstream example-repo Ask 5 promote.',
      mapping: {
        active:   'LIVE',
        archived: 'DONE',
      },
      default: 'LIVE',
    },
    'health-status': {
      combination_rule: 'single-axis',
      axis: 'status',
      note: 'Periodic health summary/ledger. Liveness keys on status (lifecycle axis), NOT on health (posture axis — HEALTHY/WATCH/ACTION/CRITICAL). Spec: example-initiative example-workstream example-repo Ask 5 promote.',
      mapping: {
        active:   'LIVE',
        archived: 'DONE',
      },
      default: 'LIVE',
    },
    'decision-guide': {
      combination_rule: 'single-axis',
      axis: 'status',
      note: 'Consolidated/distilled terminal shape of a DR corpus (container document; liveness keys on document currency, NOT per-decision lifecycle). Sibling of per-record `decision` — per-file decision remains the escape hatch for individually-tracked/contested decisions. Spec backlink: cross-repo/inbox/2026-06-27-example-stats-repo-decision-records-fleet-share.md § Q2.',
      mapping: {
        active:   'LIVE',
        archived: 'DONE',
      },
      default: 'LIVE',
    },
  },
};

// ---------------------------------------------------------------------------
// Injected sub-shapes (NOT schemas/*.yaml artifact types)
// ---------------------------------------------------------------------------
// Reusable cross-cutting shapes that emitted fleet records EMBED (via $ref), as
// opposed to the artifact TYPES generated from schemas/*.yaml. Coordinator owns
// the canonical shape (ratified tri-plane boundary: contract-lives-in-coordinator
// polarity) and publishes it here for the fleet to vendor; coordinator itself
// writes no files of this shape, so it is NOT a schemas/*.yaml entry and is NOT
// counted in schema_count. PascalCase key distinguishes sub-shapes from the
// kebab-case artifact types. Field-source-of-record: cockpit's provenance
// envelope (contract/schema/*.schema.json, ~30 identical embeddings) + project-rag
// D7 (docs/plans/2026-07-03-cockpit-store-inheritance-port.md).
// Spec backlink: cross-repo/inbox/2026-07-03-add-provenance-envelope-to-artifact-contract.md
const SUB_SHAPES = {
  ProvenanceEnvelope: {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    title: 'ProvenanceEnvelope',
    description: 'Cross-cutting provenance sub-shape embedded by emitted fleet work-state records (emission embeds provenance embeds artifact-shape-conformant record). Owned by coordinator-claude per the ratified tri-plane boundary; example-orchestration-hub emits conformant instances, project-rag/cockpit vendor it. NOT a coordinator-local artifact type (no applies_to; coordinator writes no files of this shape).',
    type: 'object',
    properties: {
      source_kind: {
        // Review: code-reviewer — F2: dropped redundant type:'string' — enum already constrains
        // the value space; aligns with emitter's own YAML-sourced enum convention ({enum:[...]}, no type).
        enum: ['github_graphql', 'github_rest', 'git_commit', 'local_fs', 'coordinator_artifact', 'transcript_summary'],
        description: 'How the fact was obtained. github_* and git_commit are git-backed and carry a non-null ref; local_fs, coordinator_artifact, and transcript_summary are filesystem/artifact/consumer-derived and carry no git ref.',
      },
      repo: {
        type: 'string',
        description: 'Repo slug the fact pertains to.',
      },
      ref: {
        anyOf: [
          {
            type: 'object',
            properties: {
              branch: { type: 'string' },
              sha: { type: 'string' },
            },
            required: ['branch', 'sha'],
            additionalProperties: false,
          },
          { type: 'null' },
        ],
        description: 'Git ref the fact was observed at. Present-as-null (D9): key always present; non-null for github_* sources, null for local_fs / coordinator_artifact / transcript_summary. Bidirectional conditional enforces the polarity.',
      },
      path: {
        type: 'string',
        description: 'Source path (repo-relative file path, or artifact locus) the fact was derived from.',
      },
      observed_at: {
        type: 'string',
        format: 'date-time',
        description: 'ISO-8601 timestamp when the fact was observed/emitted.',
      },
      derivation: {
        // Review: code-reviewer — F2: dropped redundant type:'string' — enum already constrains
        // the value space; aligns with emitter's own YAML-sourced enum convention ({enum:[...]}, no type).
        enum: ['raw', 'parsed', 'rolled_up', 'computed'],
        description: 'Processing stage of the fact: raw (as-fetched), parsed (structured), rolled_up (aggregated), computed (derived, D2).',
      },
    },
    required: ['source_kind', 'repo', 'ref', 'path', 'observed_at', 'derivation'],
    additionalProperties: false,
    allOf: [
      {
        // (i) github_* and git_commit sources must supply a non-null ref (D9 bidirectional conditional).
        if: {
          properties: { source_kind: { enum: ['github_graphql', 'github_rest', 'git_commit'] } },
          required: ['source_kind'],
        },
        then: {
          properties: { ref: { not: { type: 'null' } } },
        },
      },
      {
        // (ii) local_fs / coordinator_artifact / transcript_summary must carry ref:null (D9 bidirectional conditional).
        if: {
          properties: { source_kind: { enum: ['local_fs', 'coordinator_artifact', 'transcript_summary'] } },
          required: ['source_kind'],
        },
        then: {
          properties: { ref: { type: 'null' } },
        },
      },
    ],
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

  // Inject sub-shapes (see SUB_SHAPES) — these are NOT counted in schema_count,
  // which remains the count of schemas/*.yaml artifact types.
  // Review: code-reviewer — F3: fail-loud collision guard — Object.assign silently overwrites;
  // the PascalCase convention is the sole naming guard; make the assumption explicit + runtime-checked.
  for (const key of Object.keys(SUB_SHAPES)) {
    if (Object.prototype.hasOwnProperty.call(defs, key)) {
      process.stderr.write(`emit-artifact-shape-contract: SUB_SHAPES key "${key}" collides with a schemas/*.yaml schema — refusing to emit.\n`);
      process.exit(1);
    }
  }
  Object.assign(defs, SUB_SHAPES);

  // Build the bundle.
  // Review: code-reviewer ROBUSTNESS — `emitted_at` dropped: it created per-run diff churn
  //   and broke vendor byte-equality checks. `version` is the pinnable identity for consumers.
  const bundle = {
    $schema:     'https://json-schema.org/draft/2020-12/schema',
    $id:         'https://coordinator.local/artifact-shape-contract.schema.json',
    $comment:    'handoff-archived.status includes "superseded" (retired as a write status 2026-06-26) intentionally — retained for archived/legacy/sibling read-tolerance; the cockpit emitter validates archived records against handoff-archived.yaml before the coerce-at-ingest step; narrowing that enum breaks emit. See DECISIONS.md for full rationale and version history.',
    title:       'Coordinator artifact shape contract',
    description: `Versioned JSON Schema contract for all coordinator tracked artifact types (tc-4 B1). Single registry-wide version ${CONTRACT_VERSION}. Consumers vendor this file for a pinned shape; project-rag/cockpit are consumers, not part of the producer surface.`,
    version:     CONTRACT_VERSION,
    schema_count: count,
    // Review: code-reviewer F1 — document implicit glob-routing strategy so consumers know
    // "most-specific-glob-wins" is the intended dispatch rule (e.g. *-integration.json shadows *.json).
    routing_strategy: 'most-specific-glob-wins',
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
