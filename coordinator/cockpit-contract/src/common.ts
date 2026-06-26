/**
 * Shared scalar primitives for the cockpit work-state contract.
 *
 * Every entity speaks ISO-8601 UTC for timestamps and ISO calendar dates for
 * day-grained periods. Centralising these here keeps the emitted JSON Schema
 * `format` hints consistent across every entity and gives one place to tighten
 * validation later (e.g. enforcing a trailing `Z`).
 */
import { z } from "zod";
import { ownerEnum, resolveOwnerNamespaces } from "./owner-namespaces.js";

/**
 * ISO-8601 UTC datetime, e.g. "2026-06-22T03:06:15Z". Emits `format: date-time`.
 * `offset: true` accepts BOTH the bare `Z` suffix and a numeric `+00:00` offset
 * (both forms are exercised in the fixtures / round-trip test). GitHub timestamps
 * arrive as `Z`; coordinator-emitted timestamps may use either.
 */
export const IsoDateTime = z.iso.datetime({ offset: true });

/** ISO calendar date, e.g. "2026-06-22". Emits `format: date`. */
export const IsoDate = z.iso.date();

/**
 * The GitHub owner namespaces where work lives (R5). Not an exhaustive GitHub-wide
 * enum, and NOT hard-baked — the members are seam-generated from configuration
 * (`resolveOwnerNamespaces()`: env `COCKPIT_OWNER_NAMESPACES` → private default) so a
 * private generation carries real orgs and an OSS/example generation carries synthetic
 * ones, while the enum stays CLOSED (validation rejects an unconfigured owner). See
 * `owner-namespaces.ts` for the seam.
 */
export const OwnerNamespace = ownerEnum(resolveOwnerNamespaces());
export type OwnerNamespace = z.infer<typeof OwnerNamespace>;

/** GitHub repository visibility as reported by the census (tc-4). */
export const Visibility = z.enum(["PRIVATE", "PUBLIC", "INTERNAL"]);
export type Visibility = z.infer<typeof Visibility>;

/**
 * Hostname slug identifying a machine in the fleet — the `@machine` component
 * of `owner/repo@machine` fleet identity. D11 (string-not-enum): the machine-slug
 * set is unstable; an enum would reproduce the exact bug D11 documents.
 */
// Review: code-reviewer — empty string passes parse → degenerate owner/repo@ fleet identity; D11 forbids enum but not min(1).
export const MachineSlug = z.string().min(1);
export type MachineSlug = z.infer<typeof MachineSlug>;
