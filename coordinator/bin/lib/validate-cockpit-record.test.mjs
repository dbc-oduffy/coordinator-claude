/**
 * validate-cockpit-record.test.mjs — plain Node test for validateRecord().
 *
 * Runs with: node validate-cockpit-record.test.mjs
 * Exits 0 on all-pass, non-zero with diagnostic on first failure.
 *
 * Spec backlink: docs/plans/2026-06-22-project-opticon-cockpit-contract.md § C3
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Import the module under test — the precondition check inside it will abort
// loudly if cockpit-contract/dist/ is missing (which is the correct behaviour).
import { validateRecord } from "./validate-cockpit-record.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(__dirname, "../../cockpit-contract/fixtures");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;

function ok(label) {
  process.stdout.write(`  PASS  ${label}\n`);
  passed++;
}

function fail(label, err) {
  process.stderr.write(`  FAIL  ${label}: ${err.message ?? err}\n`);
  failed++;
}

async function test(label, fn) {
  try {
    await fn();
    ok(label);
  } catch (err) {
    fail(label, err);
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

process.stdout.write("validate-cockpit-record tests\n");

// 1. Known-good fixture: goal
await test("goal fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "goal.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("goal", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 2. Mangled goal — delete a required key → ok===false, errors non-empty
await test("mangled goal (missing text) returns ok===false", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "goal.json"), "utf8");
  const obj = JSON.parse(raw);
  delete obj.text; // 'text' is a required field on Goal
  const { ok: isOk, errors } = validateRecord("goal", obj);
  assert.equal(isOk, false, "Expected ok=false for invalid record");
  assert.ok(Array.isArray(errors) && errors.length > 0, "Expected non-empty errors array");
});

// 3. Mangled goal — wrong type on a field → ok===false, errors non-empty
await test("mangled goal (status=123 wrong type) returns ok===false", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "goal.json"), "utf8");
  const obj = JSON.parse(raw);
  obj.status = 123; // should be a string/enum, not a number
  const { ok: isOk, errors } = validateRecord("goal", obj);
  assert.equal(isOk, false, "Expected ok=false for wrong-typed field");
  assert.ok(Array.isArray(errors) && errors.length > 0, "Expected non-empty errors array");
});

// 4. Known-good fixture: routine-signal
await test("routine-signal fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "routine-signal.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("routine-signal", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 5. Unknown entity name → ok===false with explanatory string error
await test("unknown entity returns ok===false with string error", () => {
  const { ok: isOk, errors } = validateRecord("nonexistent-entity", {});
  assert.equal(isOk, false, "Expected ok=false for unknown entity");
  assert.ok(Array.isArray(errors) && errors.length > 0, "Expected non-empty errors array");
  assert.ok(
    typeof errors[0] === "string" && errors[0].includes("unknown entity"),
    `Expected 'unknown entity' message, got: ${JSON.stringify(errors[0])}`
  );
});

// ---------------------------------------------------------------------------
// Review: B-F6 — fixture validates ok===true for each remaining entity.
// Mirrors the goal-fixture pattern. Fixtures confirmed present in
// cockpit-contract/fixtures/ at time of writing (2026-06-22).
// ---------------------------------------------------------------------------

// 6. handoff-summary fixture
await test("handoff-summary fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "handoff-summary.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("handoff-summary", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 7. branch fixture
await test("branch fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "branch.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("branch", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 8. week-rollup fixture
await test("week-rollup fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "week-rollup.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("week-rollup", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 9. day-rollup fixture
await test("day-rollup fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "day-rollup.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("day-rollup", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 10. backlog-item-summary fixture
await test("backlog-item-summary fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "backlog-item-summary.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("backlog-item-summary", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 11. coordinator-root fixture
await test("coordinator-root fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "coordinator-root.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("coordinator-root", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 12. review-trail fixture
await test("review-trail fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "review-trail.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("review-trail", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// 13. provenance-envelope fixture
await test("provenance-envelope fixture validates ok===true", async () => {
  const raw = await readFile(path.join(FIXTURES_DIR, "provenance-envelope.json"), "utf8");
  const obj = JSON.parse(raw);
  const { ok: isOk, errors } = validateRecord("provenance-envelope", obj);
  assert.equal(isOk, true, `Expected ok=true; errors=${JSON.stringify(errors)}`);
  assert.equal(errors, null, "Expected errors=null on success");
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

process.stdout.write(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);

if (failed > 0) {
  process.exit(1);
}
