/**
 * validate-cockpit-record.mjs — validates a single record against a named
 * entity's Zod schema from the frozen cockpit contract.
 *
 * Spec backlink: docs/plans/2026-06-22-project-opticon-cockpit-contract.md § C3
 *
 * HARD PRECONDITION: cockpit-contract/dist/index.js must exist before this
 * module is imported. If absent, the module fails loud with remediation advice.
 * dist/ is gitignored and may be missing on a fresh checkout.
 */

import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

// Resolve the contract dist entry relative to this file's own location.
// From bin/lib/, the contract is at ../../cockpit-contract/dist/index.js.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONTRACT_DIST = path.resolve(__dirname, "../../cockpit-contract/dist/index.js");

// Fail loud if the compiled contract is absent — do NOT import lazily and hide
// the error inside validateRecord() since that would surface as a confusing
// module-not-found at call time rather than at startup.
if (!existsSync(CONTRACT_DIST)) {
  const coordinatorRoot = path.resolve(__dirname, "../..");
  process.stderr.write(
    `ERROR: cockpit-contract/dist/ not found.\n` +
    `Run: cd ${coordinatorRoot}/cockpit-contract && pnpm install\n` +
    `(pnpm install rebuilds dist/ via the package's prepare script)\n`
  );
  process.exit(1);
}

// Use createRequire to import the CJS-compiled contract from an ESM module.
// The contract's own node_modules (with zod) resolves transitively from there.
const require = createRequire(import.meta.url);
const { ENTITY_SCHEMAS, CONTRACT_VERSION } = require(CONTRACT_DIST);

export { CONTRACT_VERSION };

/**
 * Validates `obj` against the named entity's Zod schema from the frozen
 * cockpit contract.
 *
 * @param {string} entityName  — kebab-case entity name (e.g. "goal", "branch")
 * @param {unknown} obj        — the value to validate
 * @returns {{ ok: boolean, errors: Array|null }}
 *   ok=true → valid; ok=false → errors is a non-empty array of issue objects
 *   (or a single string element for unknown-entity failures).
 */
export function validateRecord(entityName, obj) {
  const schema = ENTITY_SCHEMAS[entityName];
  if (!schema) {
    return { ok: false, errors: [`unknown entity: ${entityName}`] };
  }
  const result = schema.safeParse(obj);
  if (result.success) {
    return { ok: true, errors: null };
  }
  return { ok: false, errors: result.error.issues };
}

// --- CLI form ----------------------------------------------------------------
// When run directly: node validate-cockpit-record.mjs <entity> <json-file>
// Exits 0 if valid, 1 otherwise.

const isMain =
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isMain) {
  const [, , entityName, jsonFile] = process.argv;
  if (!entityName || !jsonFile) {
    process.stderr.write(
      `Usage: node validate-cockpit-record.mjs <entity> <json-file>\n` +
      `Known entities: ${Object.keys(ENTITY_SCHEMAS).join(", ")}\n`
    );
    process.exit(1);
  }

  let raw;
  try {
    raw = await readFile(jsonFile, "utf8");
  } catch (err) {
    process.stderr.write(`ERROR: cannot read file "${jsonFile}": ${err.message}\n`);
    process.exit(1);
  }

  let obj;
  try {
    obj = JSON.parse(raw);
  } catch (err) {
    process.stderr.write(`ERROR: invalid JSON in "${jsonFile}": ${err.message}\n`);
    process.exit(1);
  }

  const { ok, errors } = validateRecord(entityName, obj);
  if (ok) {
    process.stdout.write(`ok: true — "${entityName}" is valid\n`);
    process.exit(0);
  } else {
    process.stdout.write(`ok: false — "${entityName}" validation failed\n`);
    process.stdout.write(JSON.stringify(errors, null, 2) + "\n");
    process.exit(1);
  }
}
