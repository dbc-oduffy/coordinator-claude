/**
 * CoordinatorRoot — the unit of work-state.
 *
 * Keyed on `(repo, coordinator_root_path)`, NOT `repo` alone (Camelia P2-D7): a
 * monorepo (fifa-stats) or sibling-pair (project-rag + project-rag-ue-addon)
 * must not silently collapse to one key. `last_activity_at` is sourced from the
 * branch-tip `committedDate`, never `pushedAt` — `pushedAt` lies on dormant repos
 * touched by coordinator sweeps (github-connector corpus § staleness signals).
 *
 * NULLABILITY CONTRACT (tc-3/tc-4): nullable fields are `.nullable()`, NOT `.optional()`
 * — present-as-null, never absent (DECISIONS.md § D9). `open_pr_count` is GitHub-only
 * (tc-4 connector populates it); non-GitHub producers (e.g. tc-3 local emission) emit null.
 */
import { z } from "zod";
import { IsoDateTime, OwnerNamespace, Visibility } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

export const CoordinatorRoot = z.object({
  repo: z.string(),
  owner: OwnerNamespace,
  /** Relative to repo root; "." for single-root repos. */
  coordinator_root_path: z.string(),
  visibility: Visibility,
  archived: z.boolean(),
  /** From GitHub census `isFork`; closes the field-gap vs tc-4 census / tc-5 repos table. */
  is_fork: z.boolean(),
  default_branch: z.string(),
  /** ISO-8601 UTC — branch-tip committedDate, NOT pushedAt. */
  last_activity_at: IsoDateTime,
  /** Open PR count from GitHub census; null for non-GitHub producers (present-as-null, D9). */
  open_pr_count: z.number().int().nullable(),
  provenance: ProvenanceEnvelope,
});
export type CoordinatorRoot = z.infer<typeof CoordinatorRoot>;
