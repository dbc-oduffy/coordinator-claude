/**
 * ProvenanceEnvelope — the mandatory source-grounding record on every cockpit fact.
 *
 * Provenance is a real schema, not a label (the Data Science Reviewer P1-D2): "source-grounded" is
 * unfalsifiable without enumerated fields. `observed_at` and `derivation` are
 * load-bearing — without them a dashboard number has no trustworthiness or
 * staleness signal, so both are required and non-nullable.
 *
 * `ref` is a structured object (the Data Science Reviewer P2), NOT a flat "work/...@sha" string:
 * the relational store (tc-5) splits it into `ref_branch` + `ref_sha` columns so
 * `WHERE ref_sha = ...` provenance queries are possible; a lossy flat string
 * defeats that.
 */
import { z } from "zod";

/** Where a datum physically came from. */
export const SourceKind = z.enum([
  "github_graphql",
  "github_rest",
  "local_fs",
  "coordinator_artifact", // query-records.js output, orientation_cache, etc.
]);
export type SourceKind = z.infer<typeof SourceKind>;

/** How far a datum is from its raw source. */
export const Derivation = z.enum(["raw", "parsed", "rolled_up"]);
export type Derivation = z.infer<typeof Derivation>;

/** The git ref a fact was observed at — branch + tip SHA, stored split in tc-5. */
export const Ref = z.object({
  branch: z.string(),
  sha: z.string(),
});
export type Ref = z.infer<typeof Ref>;

export const ProvenanceEnvelope = z.object({
  source_kind: SourceKind,
  repo: z.string(),
  ref: Ref,
  /** File path or API endpoint; "" for computed / rolled-up entities. */
  path: z.string(),
  /** ISO-8601 UTC wall-clock when the underlying source was read. Required. */
  observed_at: z.iso.datetime({ offset: true }),
  derivation: Derivation,
});
export type ProvenanceEnvelope = z.infer<typeof ProvenanceEnvelope>;
