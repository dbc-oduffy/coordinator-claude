/**
 * PlanSummary — summary view over docs/plans/*.md lifecycle and status.
 *
 * Spec backlink: state/roadmap/cockpit-contract-ext-2026-06-22/COORDINATOR-RESOLUTIONS.md
 * § R3 + C-ext-4 + the Data Science Reviewer C-F6.
 *
 * Composite primary key: (repo, coordinator_root_path, path). `author` is emitted
 * verbatim from plan frontmatter — no git-blame inference (C-F6).
 *
 * `repo` and `coordinator_root_path` are connector-injected (D4).
 * Nullable fields follow D9 (present-as-null, not optional).
 */
import { z } from "zod";
import { IsoDate } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

export const PlanStatus = z.enum([
  "draft",
  "reviewed",
  "approved",
  "executing",
  "implemented",
  "deferred",
  "abandoned",
  "superseded",
]);
export type PlanStatus = z.infer<typeof PlanStatus>;

export const PlanSummary = z.object({
  /** Connector-injected registry shortname. */
  repo: z.string(),
  /** Connector-injected — matches other summary entities. */
  coordinator_root_path: z.string(),
  /**
   * Relative path within the repo (e.g. "docs/plans/2026-06-22-foo.md").
   * Composite key with repo + coordinator_root_path (C-F6).
   */
  path: z.string(),
  /** First H1 of the plan document. */
  title: z.string(),
  /**
   * ISO calendar date (YYYY-MM-DD) from plan frontmatter.
   * IsoDateTime values (e.g. "2026-06-22T08:00:00Z") fail validation — emitter
   * MUST truncate full datetime strings to date-only before emitting.
   */
  created: IsoDate,
  /** Author verbatim from frontmatter — no git-blame (C-F6). */
  author: z.string(),
  /** Plan lifecycle state from frontmatter. */
  status: PlanStatus,
  provenance: ProvenanceEnvelope,

  // Nullable fields (D9 present-as-null).

  /** "atomic" | "fan-out" | etc. — null if not declared in frontmatter. */
  scope_mode: z.string().nullable(),
  /** Reviewer name from frontmatter; null if unreviewed. */
  reviewer: z.string().nullable(),
  /** Git branch this plan was authored/executing on; null if not set. */
  branch: z.string().nullable(),
  /** Path to the superseding plan; null if not superseded. */
  superseded_by: z.string().nullable(),
  /** Free-text source tag (roadmap slug, spinoff id, etc.); null if absent. */
  source: z.string().nullable(),
});
export type PlanSummary = z.infer<typeof PlanSummary>;
