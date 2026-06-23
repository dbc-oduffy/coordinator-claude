/**
 * Round-trip contract test (AC: "JSON.parse(JSON.stringify(exampleInstance))
 * passes Zod parse on every entity").
 *
 * For every entity in ENTITY_SCHEMAS:
 *  - a fixture file exists under fixtures/<name>.json,
 *  - the fixture passes Zod parse,
 *  - serialising and re-parsing the validated value round-trips cleanly.
 *
 * Also asserts fixture/registry symmetry in both directions so a new entity
 * cannot be added without a fixture (and a stray fixture cannot rot unnoticed).
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it, expect } from "vitest";
import { ENTITY_SCHEMAS, Branch, IsoDateTime } from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = join(here, "..", "fixtures");

const fixtureNames = readdirSync(fixturesDir)
  .filter((f) => f.endsWith(".json"))
  .map((f) => f.replace(/\.json$/, ""));

const registryNames = Object.keys(ENTITY_SCHEMAS);

describe("fixture / registry symmetry", () => {
  it("every registry entity has a fixture", () => {
    const missing = registryNames.filter((n) => !fixtureNames.includes(n));
    expect(missing, `entities missing fixtures: ${missing.join(", ")}`).toEqual(
      [],
    );
  });

  it("every fixture maps to a registry entity", () => {
    const orphan = fixtureNames.filter((n) => !registryNames.includes(n));
    expect(orphan, `orphan fixtures: ${orphan.join(", ")}`).toEqual([]);
  });
});

describe("round-trip", () => {
  for (const [name, schema] of Object.entries(ENTITY_SCHEMAS)) {
    it(`${name}: fixture parses and round-trips`, () => {
      const raw = JSON.parse(
        readFileSync(join(fixturesDir, `${name}.json`), "utf8"),
      );
      const parsed = schema.parse(raw);
      const roundTripped = JSON.parse(JSON.stringify(parsed));
      expect(() => schema.parse(roundTripped)).not.toThrow();
      expect(roundTripped).toEqual(parsed);
    });
  }
});

describe("nullability contract (nullable means present-as-null, NOT optional)", () => {
  const branchFixture = () =>
    JSON.parse(readFileSync(join(fixturesDir, "branch.json"), "utf8"));

  it("nullable field present-as-null parses", () => {
    const v = branchFixture();
    v.ahead_by = null;
    v.behind_by = null;
    v.merge_base_sha = null;
    v.machine_hint = null;
    v.date_hint = null;
    expect(() => Branch.parse(v)).not.toThrow();
  });

  it("nullable field omitted entirely is REJECTED (proves .nullable() != .optional())", () => {
    const v = branchFixture();
    delete v.ahead_by;
    expect(Branch.safeParse(v).success).toBe(false);
  });

  it("non-null branch facts parse (exercises the non-null path, not just null)", () => {
    const v = branchFixture();
    v.ahead_by = 42;
    v.behind_by = 3;
    expect(Branch.parse(v).ahead_by).toBe(42);
  });
});

describe("IsoDateTime accepts both Z and numeric offset", () => {
  it("bare Z suffix", () => {
    expect(IsoDateTime.safeParse("2026-06-22T03:06:15Z").success).toBe(true);
  });
  it("+00:00 numeric offset", () => {
    expect(IsoDateTime.safeParse("2026-06-22T03:06:15+00:00").success).toBe(
      true,
    );
  });
  it("no offset is rejected", () => {
    expect(IsoDateTime.safeParse("2026-06-22T03:06:15").success).toBe(false);
  });
});
