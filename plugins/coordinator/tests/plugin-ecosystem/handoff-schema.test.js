// handoff-schema.test.js — unit tests for the reviewed_at_workstream_complete field
// added to schemas/handoff.yaml and schemas/handoff-archived.yaml.
//
// Spec backlink: docs/plans/2026-05-08-session-end-review-and-marker-trail.md § T1
//
// Coverage:
//   - Handoff WITH reviewed_at_workstream_complete validates clean (field accepted as optional string)
//   - Handoff WITHOUT reviewed_at_workstream_complete validates clean (field is optional — absence is ok)
//   - handoff-archived schema accepts the same field on archived handoffs
//
// What is NOT covered:
//   - Format enforcement of the "<sha-range> <reviewer> <YYYY-MM-DD>" shape — that is
//     owned by coordinator-write-review-trail.sh (T2), not the YAML schema validator.
//   - Cross-field rules unrelated to this field (covered by their own test surfaces).

'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const os = require('os');
const { PLUGINS_ROOT } = require('./helpers/fs');

const COORDINATOR_DIR = path.join(PLUGINS_ROOT, 'coordinator-claude', 'coordinator');
const SCHEMAS_DIR = path.join(COORDINATOR_DIR, 'schemas');
const SCHEMA_JS = path.join(COORDINATOR_DIR, 'bin', 'lib', 'schema.js');

const {
  loadSchemas,
  parseFrontmatter,
  validateFrontmatter,
} = require(SCHEMA_JS);

// ---------------------------------------------------------------------------
// Shared fixture builders
// ---------------------------------------------------------------------------

/**
 * Minimal valid handoff frontmatter fields that satisfy all required fields
 * and the cross-field rules (no awaiting_gate, no graph primitives).
 */
function baseHandoffFm(overrides = {}) {
  return {
    title: 'Test handoff',
    created: '2026-05-08',
    branch: 'work/striker/2026-05-08',
    status: 'active',
    predecessor: null,
    ...overrides,
  };
}

/**
 * Minimal valid handoff-archived frontmatter (same required fields as handoff).
 */
function baseArchivedFm(overrides = {}) {
  return {
    title: 'Test archived handoff',
    created: '2026-05-08',
    branch: 'work/striker/2026-05-08',
    status: 'consumed',
    predecessor: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Load schemas once at module level
// ---------------------------------------------------------------------------

const schemas = loadSchemas(SCHEMAS_DIR);

describe('handoff schema — reviewed_at_workstream_complete field', () => {
  const handoffSchema = schemas['handoff'];
  const archivedSchema = schemas['handoff-archived'];

  it('handoff schema loaded successfully', () => {
    assert.ok(handoffSchema, 'handoff schema not found in schemas dir');
    assert.equal(handoffSchema.schema, 'handoff', 'schema name mismatch');
  });

  it('handoff-archived schema loaded successfully', () => {
    assert.ok(archivedSchema, 'handoff-archived schema not found in schemas dir');
    assert.equal(archivedSchema.schema, 'handoff-archived', 'schema name mismatch');
  });

  it('handoff WITH reviewed_at_workstream_complete validates clean', () => {
    const fm = baseHandoffFm({
      reviewed_at_workstream_complete: 'abc123..def456 sonnet 2026-05-08',
    });
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(
      result.ok,
      `Expected validation to pass but got errors: ${JSON.stringify(result.errors)}`
    );
  });

  it('handoff WITHOUT reviewed_at_workstream_complete validates clean (field is optional)', () => {
    const fm = baseHandoffFm();
    // Ensure the field is truly absent, not just undefined
    assert.ok(!('reviewed_at_workstream_complete' in fm), 'fixture should not include the field');
    const result = validateFrontmatter(fm, handoffSchema);
    assert.ok(
      result.ok,
      `Expected validation to pass but got errors: ${JSON.stringify(result.errors)}`
    );
  });

  it('handoff-archived WITH reviewed_at_workstream_complete validates clean', () => {
    const fm = baseArchivedFm({
      reviewed_at_workstream_complete: 'def456..ghi789 patrik 2026-05-08',
    });
    const result = validateFrontmatter(fm, archivedSchema);
    assert.ok(
      result.ok,
      `Expected archived validation to pass but got errors: ${JSON.stringify(result.errors)}`
    );
  });

  it('handoff-archived WITHOUT reviewed_at_workstream_complete validates clean (field is optional)', () => {
    const fm = baseArchivedFm();
    assert.ok(!('reviewed_at_workstream_complete' in fm), 'fixture should not include the field');
    const result = validateFrontmatter(fm, archivedSchema);
    assert.ok(
      result.ok,
      `Expected archived validation to pass but got errors: ${JSON.stringify(result.errors)}`
    );
  });

  it('reviewed_at_workstream_complete is listed as optional (not required) in handoff schema', () => {
    assert.ok(
      handoffSchema.optional && 'reviewed_at_workstream_complete' in handoffSchema.optional,
      'reviewed_at_workstream_complete should be in the optional section of handoff schema'
    );
    assert.ok(
      !handoffSchema.required || !('reviewed_at_workstream_complete' in handoffSchema.required),
      'reviewed_at_workstream_complete must NOT be in the required section of handoff schema'
    );
  });

  it('reviewed_at_workstream_complete is listed as optional (not required) in handoff-archived schema', () => {
    assert.ok(
      archivedSchema.optional && 'reviewed_at_workstream_complete' in archivedSchema.optional,
      'reviewed_at_workstream_complete should be in the optional section of handoff-archived schema'
    );
    assert.ok(
      !archivedSchema.required || !('reviewed_at_workstream_complete' in archivedSchema.required),
      'reviewed_at_workstream_complete must NOT be in the required section of handoff-archived schema'
    );
  });

  it('reviewed_at_workstream_complete value is type-checked as string when present', () => {
    // The validator should reject a non-string value for this field
    const fm = baseHandoffFm({
      reviewed_at_workstream_complete: 12345, // wrong type — should be string
    });
    const result = validateFrontmatter(fm, handoffSchema);
    // Either the field is flagged or not — it depends on the type declared in the schema.
    // Schema declares it as "string", so a number should produce an error.
    assert.ok(
      !result.ok,
      'Expected type validation failure when reviewed_at_workstream_complete is a number'
    );
    const fieldError = result.errors.find(e => e.field === 'reviewed_at_workstream_complete');
    assert.ok(
      fieldError,
      `Expected an error for reviewed_at_workstream_complete field, got: ${JSON.stringify(result.errors)}`
    );
  });
});
