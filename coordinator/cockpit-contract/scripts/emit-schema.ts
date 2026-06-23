/**
 * Emit the canonical JSON Schema for every contract entity (AC: "JSON Schema is
 * emitted from the Zod definitions").
 *
 * Writes one `schema/<name>.schema.json` per entity plus a bundled
 * `schema/cockpit-contract.schema.json` (all entities under `$defs`). The emitted
 * JSON Schema is the canonical cross-repo wire format (R7) — the opticon repo
 * generates its TS/Zod from these files; they are committed, not gitignored.
 *
 * Uses Zod v4's native `z.toJSONSchema()` (no `zod-to-json-schema` dependency).
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { ENTITY_SCHEMAS, CONTRACT_VERSION } from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const schemaDir = join(here, "..", "schema");
mkdirSync(schemaDir, { recursive: true });

const entries = Object.entries(ENTITY_SCHEMAS);
if (entries.length === 0) {
  console.error(
    "emit-schema: ENTITY_SCHEMAS is empty — bad import or registry regression. Refusing to emit an empty schema set.",
  );
  process.exit(1);
}

const bundleDefs: Record<string, unknown> = {};
let count = 0;

for (const [name, schema] of entries) {
  const json = z.toJSONSchema(schema, { target: "draft-2020-12" });
  writeFileSync(
    join(schemaDir, `${name}.schema.json`),
    JSON.stringify(json, null, 2) + "\n",
  );
  bundleDefs[name] = json;
  count++;
}

const bundle = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://coordinator.local/cockpit-contract.schema.json",
  title: "Cockpit work-state contract",
  description: `Canonical work-state contract (tc-2), version ${CONTRACT_VERSION}.`,
  version: CONTRACT_VERSION,
  $defs: bundleDefs,
};
writeFileSync(
  join(schemaDir, "cockpit-contract.schema.json"),
  JSON.stringify(bundle, null, 2) + "\n",
);

console.log(`emitted ${count} entity schemas + 1 bundle → ${schemaDir}`);
