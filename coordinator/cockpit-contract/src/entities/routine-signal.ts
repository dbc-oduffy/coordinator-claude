/**
 * RoutineSignal — staleness as a typed derived-signal, NOT a scalar (the Data Science Reviewer P1-D3).
 *
 * Staleness is at least six distinct derived quantities, each with different
 * inputs, thresholds, and units; they must not collapse to one boolean or string.
 * Light bitemporal: `observed_at` (when the underlying fact was read) vs
 * `computed_as_of` (the wall-clock the threshold was computed against) so the
 * dashboard can render "stale (as of 14m ago)" honestly and falsifiably. This is
 * NOT full effective-dated revision — only the observed/computed pair on derived
 * signals.
 */
import { z } from "zod";
import { IsoDateTime } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

/**
 * The six named staleness kinds (cockpit-emission corpus § 10). Each has distinct
 * inputs/thresholds/units — enumerated, never an open string.
 */
export const RoutineSignalKind = z.enum([
  "weekly", // week-changelog cadence; threshold: >=5 days AND >=15 commits
  "bug-sweep", // bug-backlog cadence; threshold: >50 commits AND >7 days, OR >14 days AND >20 commits
  "docs", // update-docs cadence; threshold: any commits since last update-docs run
  "arch-audit", // architecture audit cadence; threshold: 10 days
  "dormant-repo", // repo inactivity; threshold: default-branch tip >30 days old
  "distill-backlog", // undigested archive entries; threshold: >N entries pending (N TBD at tc-3)
]);
export type RoutineSignalKind = z.infer<typeof RoutineSignalKind>;

export const ComputedState = z.enum(["fresh", "mild", "stale", "unknown"]);
export type ComputedState = z.infer<typeof ComputedState>;

export const RoutineSignal = z.object({
  kind: RoutineSignalKind,
  repo: z.string(),
  coordinator_root_path: z.string(),
  /** Kind-specific: {commits_since, days_since, last_sweep_sha, …}. Stored as JSON column in tc-5. */
  inputs: z.record(z.string(), z.union([z.string(), z.number()])),
  /** Human-readable threshold definition. Stored as text in tc-5. */
  threshold: z.string(),
  computed_state: ComputedState,
  overdue: z.boolean(),
  /** ISO-8601 UTC — when the underlying fact was read. */
  observed_at: IsoDateTime,
  /** ISO-8601 UTC — wall-clock at threshold computation; enables "stale as of Xm ago". */
  computed_as_of: IsoDateTime,
  provenance: ProvenanceEnvelope,
});
export type RoutineSignal = z.infer<typeof RoutineSignal>;
