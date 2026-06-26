/**
 * CrossRepoMemoSummary — outstanding cross-repo memos as a queryable snapshot
 * entity for the cockpit.
 *
 * METADATA-ONLY: no memo bodies ship to the all-staff web tier. The cockpit
 * stores only the structural envelope (from/to, status, kind, created date,
 * related paths) so the dashboard can surface actionable queue depth without
 * exposing private deliberation content.
 *
 * BOARD-PUBLIC FIELD — `title`: memo titles ARE visible to all staff on the
 * cockpit dashboard (PM-ratified 2026-06-24). Authors are warned of this via
 * the cross-repo-memo authoring norm documented in
 * `docs/wiki/cross-repo-communication.md`. No redaction is applied here.
 *
 * Spec backlink: docs/plans/2026-06-24-opticon-cockpit-contract-reshape.md
 * Ask 7 of the cockpit-contract reshape (chunk C6-entity).
 */
import { z } from "zod";
import { IsoDate } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

export const CrossRepoMemoSummary = z.object({
  /**
   * Connector-injected: which coordinator root's memo tree this fact was
   * observed in. This is the OBSERVATION LOCUS — the repo whose
   * `state/memos/` directory the connector scanned. It is DISTINCT from
   * `from` and `to`, which are the memo's authored cross-repo endpoints
   * (the originating EM and the destination repo, as written in the memo
   * frontmatter). A memo authored by `.claude-prime` to `example-repo` read
   * from the `.claude-prime` tree has `repo: ".claude-prime"`,
   * `from: ".claude-prime"`, `to: "example-repo"`.
   */
  repo: z.string(),
  /**
   * Connector-injected absolute filesystem path to the coordinator root
   * where this memo was observed (the observation locus; same locus as
   * `repo`, expressed as a path for local-FS tooling).
   */
  coordinator_root_path: z.string(),
  /**
   * The memo title as authored in its frontmatter.
   *
   * BOARD-PUBLIC free prose — this field is visible to all staff on the
   * cockpit dashboard (PM-ratified 2026-06-24: titles are staff-visible;
   * authors are warned via the cross-repo-memo authoring norm). No length
   * cap, no redaction applied.
   */
  title: z.string(),
  /**
   * The memo's authored source endpoint — the coordinator root identity
   * of the EM that created the memo (frontmatter `from:` field).
   */
  from: z.string(),
  /**
   * The memo's authored destination endpoint — the coordinator root identity
   * of the receiving repo (frontmatter `to:` field).
   */
  to: z.string(),
  /**
   * Primary memo lifecycle state. Only the three live values are modeled
   * here. The grandfathered back-compat values (reviewed, action_taken,
   * closed, superseded) are NOT modeled — connectors MUST normalise them
   * to one of these three before emitting a CrossRepoMemoSummary.
   */
  status: z.enum(["open", "in_progress", "actioned"]),
  /** ISO calendar date when the memo was created. */
  created: IsoDate,
  /** The memo kind discriminator (frontmatter `kind:` field). */
  kind: z.enum(["ask", "consult", "fyi"]),
  /**
   * Related artifact paths cited in the memo (frontmatter `related:` list).
   * Required, never null — connectors inject `[]` when absent on disk.
   */
  related: z.array(z.string()),
  provenance: ProvenanceEnvelope,
});
export type CrossRepoMemoSummary = z.infer<typeof CrossRepoMemoSummary>;
