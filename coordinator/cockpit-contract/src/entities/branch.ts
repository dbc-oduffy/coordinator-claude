/**
 * Branch — a single ref observation, keyed on `(repo, branch_name, tip_sha)`.
 *
 * Branch-fact data-quality defenses (Camelia P1-D5, github-connector corpus):
 *  - `tip_sha` is the observation key: a tip-SHA change is a NEW observation, not
 *    name-continuity. Daily-branch renames appear as delete+create to a naive
 *    differ; SHA-keying makes that detectable.
 *  - `merge_base_sha` is stored alongside `ahead_by` — a rebase moves the merge
 *    base and silently changes `ahead_by` with no new work. Without it the cockpit
 *    shows a velocity spike that is a history-rewrite artifact.
 *  - `ahead_by` / `behind_by` come from the REST compare endpoint and may be
 *    uncomputed at census time, hence nullable. `merge_base_sha` is null when
 *    `ahead_by` was not computed.
 *  - machine/date hints are parsed from `work/{machine}/{date}`; null when the
 *    branch name does not match the pattern (e.g. `main`, `feature/*`).
 *
 * NULLABILITY CONTRACT (tc-3/tc-4): every nullable field below is `.nullable()`,
 * NOT `.optional()` — the key MUST be present in the emitted payload, carrying
 * `null` when uncomputed (e.g. `ahead_by: null` before the REST compare runs).
 * Omitting the key entirely fails validation. Present-as-null is deliberate: it
 * gives tc-5 a value to insert in every column. See DECISIONS.md § D9.
 */
import { z } from "zod";
import { IsoDateTime, OwnerNamespace } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

export const Branch = z.object({
  repo: z.string(),
  owner: OwnerNamespace,
  coordinator_root_path: z.string(),
  name: z.string(),
  /** Observation key — tip SHA change = new observation. */
  tip_sha: z.string(),
  /** Required when ahead_by present; null if not computed. */
  merge_base_sha: z.string().nullable(),
  /** vs. default branch; null if not yet computed (REST compare not run). */
  ahead_by: z.number().int().nullable(),
  behind_by: z.number().int().nullable(),
  /** ISO-8601 UTC; committedDate on the tip commit. */
  last_commit_at: IsoDateTime,
  last_commit_message: z.string(),
  /** Parsed from work/{machine}/{date}; null if unparseable. */
  machine_hint: z.string().nullable(),
  /** Parsed date segment; null if unparseable. */
  date_hint: z.string().nullable(),
  provenance: ProvenanceEnvelope,
});
export type Branch = z.infer<typeof Branch>;
