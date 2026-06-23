/**
 * Shared scalar primitives for the cockpit work-state contract.
 *
 * Every entity speaks ISO-8601 UTC for timestamps and ISO calendar dates for
 * day-grained periods. Centralising these here keeps the emitted JSON Schema
 * `format` hints consistent across every entity and gives one place to tighten
 * validation later (e.g. enforcing a trailing `Z`).
 */
import { z } from "zod";

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
 * The three GitHub owner namespaces where work lives (R5). Not an exhaustive
 * GitHub-wide enum — the connector (tc-4) is configured against exactly these.
 */
export const OwnerNamespace = z.enum([
  "dbc-oduffy",
  "Delphi-Interactive",
  "oduffy-work",
]);
export type OwnerNamespace = z.infer<typeof OwnerNamespace>;

/** GitHub repository visibility as reported by the census (tc-4). */
export const Visibility = z.enum(["PRIVATE", "PUBLIC", "INTERNAL"]);
export type Visibility = z.infer<typeof Visibility>;
