/**
 * validate-cockpit-record.mjs — validates a single record against a named
 * entity's Zod schema from the frozen cockpit contract.
 *
 * Spec backlink: docs/plans/2026-06-22-example-cockpit-repo-cockpit-contract.md § C3
 *
 * HARD PRECONDITION: cockpit-contract/dist/index.js must exist before this
 * module is imported. If absent, the module fails loud with remediation advice.
 * dist/ is gitignored and may be missing on a fresh checkout.
 */

import { existsSync, statSync, readdirSync } from "node:fs";
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

// Freshness gate: if any cockpit-contract/src/*.ts is newer than the built
// dist entry, dist/ is stale and would produce wrong validation results.
// Guard is skipped gracefully when src/ is absent (e.g. stripped installs).
const CONTRACT_SRC = path.resolve(__dirname, "../../cockpit-contract/src");
if (existsSync(CONTRACT_SRC)) {
  const distMtime = statSync(CONTRACT_DIST).mtimeMs;

  // Small recursive walk — compatible with Node < 20 (no {recursive:true}).
  function newestTsMtime(dir) {
    let newest = 0;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        newest = Math.max(newest, newestTsMtime(full));
      } else if (entry.isFile() && entry.name.endsWith(".ts")) {
        newest = Math.max(newest, statSync(full).mtimeMs);
      }
    }
    return newest;
  }

  if (newestTsMtime(CONTRACT_SRC) > distMtime) {
    const coordinatorRoot = path.resolve(__dirname, "../..");
    process.stderr.write(
      `ERROR: cockpit-contract/dist/ is STALE — src/ has changed since the last build.\n` +
      `Run: cd ${coordinatorRoot}/cockpit-contract && pnpm run build\n` +
      `(dist/ is gitignored; a stale dist/ causes wrong schema validation)\n`
    );
    process.exit(1);
  }
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
// Single-record mode (original):
//   node validate-cockpit-record.mjs <entity> <json-file>
//   <json-file> holds a single JSON object. Exits 0 if valid, 1 otherwise.
//
// Array mode (batch — ONE node spawn per entity-type array):
//   node validate-cockpit-record.mjs --array <entity> <json-file>
//   <json-file> holds a JSON ARRAY. Validates every element, collects ALL
//   failures (not just the first), reports failing index + Zod issues to
//   stdout, exits 1 if any failed. Prints "ok: N records" + exits 0 if all
//   valid. Using this mode eliminates the per-record node-spawn cost that was
//   the emitter's #1 perf bottleneck (~130ms startup × 653 records ≈ 85s).

const isMain =
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isMain) {
  const arrayMode = process.argv[2] === "--array";
  const [entityName, jsonFile] = arrayMode
    ? [process.argv[3], process.argv[4]]
    : [process.argv[2], process.argv[3]];

  if (!entityName || !jsonFile) {
    process.stderr.write(
      `Usage: node validate-cockpit-record.mjs [--array] <entity> <json-file>\n` +
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

  if (arrayMode) {
    // Array mode: validate every element; collect ALL failures before exiting.
    if (!Array.isArray(obj)) {
      process.stderr.write(`ERROR: --array mode requires a JSON array in "${jsonFile}"\n`);
      process.exit(1);
    }

    const failures = [];
    for (let idx = 0; idx < obj.length; idx++) {
      const { ok, errors } = validateRecord(entityName, obj[idx]);
      if (!ok) {
        failures.push({ idx, errors });
      }
    }

    if (failures.length > 0) {
      // Review: code-reviewer — F4: diagnostic output on stderr; keeps stdout clean for "ok: N records" success signal
      for (const { idx, errors } of failures) {
        process.stderr.write(`failing index ${idx}:\n`);
        process.stderr.write(JSON.stringify(errors, null, 2) + "\n");
      }
      process.exit(1);
    } else {
      process.stdout.write(`ok: ${obj.length} records\n`);
      process.exit(0);
    }
  } else {
    // Original single-record mode — kept for any genuine single-record use.
    const { ok, errors } = validateRecord(entityName, obj);
    if (ok) {
      process.stdout.write(`ok: true — "${entityName}" is valid\n`);
      process.exit(0);
    } else {
      // Review: code-reviewer — F4: aligned with array-mode; diagnostic on stderr, success on stdout
      process.stderr.write(`ok: false — "${entityName}" validation failed\n`);
      process.stderr.write(JSON.stringify(errors, null, 2) + "\n");
      process.exit(1);
    }
  }
}
