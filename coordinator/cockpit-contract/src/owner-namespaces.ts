/**
 * Owner-namespace seam for the cockpit work-state contract.
 *
 * The set of GitHub owner namespaces is operator / deployment configuration, NOT a
 * fixed GitHub-wide enum. A PRIVATE generation carries the operator's real orgs; an
 * OSS / example generation carries synthetic orgs. In BOTH cases the set stays a
 * CLOSED enum — the boundary guarantee (`branchSchema.parse()` / `coordinatorRootSchema.parse()`
 * rejecting an owner not in the configured set) is preserved regardless of which set
 * is configured. This is the seam that replaces the previously hard-baked literal
 * enum so the contract can be emitted OSS-portable without leaking real org identity.
 *
 * Negative spec: this seam is NOT a downgrade to `z.string()` (the rejected fallback) —
 * it is a swappable CLOSED enum. It reads config only in `resolveOwnerNamespaces()`;
 * entities import the built `OwnerNamespace` from `common.ts`.
 */
import { z } from "zod";

/**
 * Real, private owner set — the default when no override is supplied. Keeps the
 * existing fixtures (`owner: "dbc-oduffy"`) and the runtime snapshot emitter green.
 */
export const DEFAULT_OWNER_NAMESPACES = [
  "dbc-oduffy",
  "Example-Interactive",
  "workstation",
] as const;

/** Synthetic owner set for OSS / example schema emission (via the env override). */
export const EXAMPLE_OWNER_NAMESPACES = ["example-org", "example-team"] as const;

/**
 * Resolve the configured owner namespaces. Precedence: env
 * `COCKPIT_OWNER_NAMESPACES` (comma-separated, trimmed, blanks dropped) →
 * `DEFAULT_OWNER_NAMESPACES`. Fail loud on a present-but-all-blank override —
 * detect-then-fail, never silently fall back to the default behind a malformed
 * override (the default would mask an operator's emit-config error).
 */
export function resolveOwnerNamespaces(): readonly string[] {
  const raw = process.env.COCKPIT_OWNER_NAMESPACES;
  if (raw === undefined) return DEFAULT_OWNER_NAMESPACES;
  const members = raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  if (members.length === 0) {
    throw new Error(
      "COCKPIT_OWNER_NAMESPACES is set but resolves to zero members after trimming — " +
        "refusing to silently fall back to the default owner set. Unset it, or provide a non-empty comma-separated list.",
    );
  }
  return members;
}

/**
 * Build a CLOSED Zod enum from a runtime member list. Runtime `.parse()` rejects any
 * value not in `members` — the boundary guarantee this seam preserves. The TS-inferred
 * type widens to `string` for a non-`const` runtime list; that is an accepted tradeoff
 * (runtime closedness, not the literal union, is what the cross-repo contract boundary
 * needs). Fails loud on an empty member list.
 */
export function ownerEnum(members: readonly string[]) {
  if (members.length === 0) {
    throw new Error("ownerEnum: refusing to build an enum from zero members.");
  }
  return z.enum(members as [string, ...string[]]);
}
