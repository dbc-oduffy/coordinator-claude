/**
 * Owner-namespace seam tests — resolveOwnerNamespaces() + ownerEnum().
 *
 * Covers: env isolation, default path, override parsing, blank-override
 * fail-loud, closed-enum acceptance, and closed-enum rejection for both
 * the default and synthetic member sets.
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import {
  DEFAULT_OWNER_NAMESPACES,
  EXAMPLE_OWNER_NAMESPACES,
  resolveOwnerNamespaces,
  ownerEnum,
} from "../src/owner-namespaces.js";

describe("resolveOwnerNamespaces", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("resolveOwnerNamespaces: unset override returns DEFAULT_OWNER_NAMESPACES", () => {
    // Review: code-reviewer — passing undefined deletes the key per Vitest v3, so the
    // default-path test runs with COCKPIT_OWNER_NAMESPACES provably absent from process.env.
    vi.stubEnv("COCKPIT_OWNER_NAMESPACES", undefined);
    expect(resolveOwnerNamespaces()).toEqual([...DEFAULT_OWNER_NAMESPACES]);
  });

  it("resolveOwnerNamespaces: override 'acme-one, acme-two' returns trimmed members", () => {
    vi.stubEnv("COCKPIT_OWNER_NAMESPACES", "acme-one, acme-two");
    expect(resolveOwnerNamespaces()).toEqual(["acme-one", "acme-two"]);
  });

  it("resolveOwnerNamespaces: override ' , , ' (all blank) THROWS fail-loud", () => {
    vi.stubEnv("COCKPIT_OWNER_NAMESPACES", " , , ");
    // Review: code-reviewer — assert specific error substring for stability; confirmed in src/owner-namespaces.ts:47
    expect(() => resolveOwnerNamespaces()).toThrow("resolves to zero members");
  });
});

describe("default closed enum", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("default closed enum: accepts all DEFAULT members and rejects non-member", () => {
    vi.stubEnv("COCKPIT_OWNER_NAMESPACES", undefined);
    const e = ownerEnum(resolveOwnerNamespaces());
    expect(() => e.parse("dbc-oduffy")).not.toThrow();
    expect(() => e.parse("Example-Interactive")).not.toThrow();
    expect(() => e.parse("workstation")).not.toThrow();
    expect(() => e.parse("not-an-owner")).toThrow();
  });
});

describe("synthetic closed enum", () => {
  it("synthetic closed enum: accepts EXAMPLE members and rejects DEFAULT member", () => {
    const e = ownerEnum(EXAMPLE_OWNER_NAMESPACES);
    expect(() => e.parse("example-org")).not.toThrow();
    // Review: code-reviewer — AC3: assert SECOND example member is also accepted (was missing)
    expect(() => e.parse("example-team")).not.toThrow();
    expect(() => e.parse("dbc-oduffy")).toThrow();
  });
});

describe("ownerEnum guard", () => {
  it("ownerEnum: empty member list THROWS fail-loud", () => {
    // Review: code-reviewer — zero-member guard in src/owner-namespaces.ts:62-64 was untested
    expect(() => ownerEnum([])).toThrow("zero members");
  });
});
