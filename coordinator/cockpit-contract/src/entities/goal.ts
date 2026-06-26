/**
 * Goal — the one net-new WRITABLE entity in the cockpit, modelled as an
 * append-only event record (the Data Science Reviewer P1-D6, R3).
 *
 * Goals are mutable, low-frequency, single-author-per-edit but MULTI-MACHINE
 * (Machine-C + Machine-A) — the worst shape for "just put it in a file and
 * git-merge it." Append-only per-machine event records sidestep the
 * last-write-wins / merge-conflict hazard entirely and give goal history for
 * free. A goal is never mutated in place; it is superseded by a newer record.
 * Current goals are derived as the latest non-superseded record per
 * `(repo, coordinator_root_path, period, period_value)`.
 *
 * R3: goals are DECLARED (not inferred), captured via enhanced existing
 * ceremonies (workweek-start, workday-start, HEADER.md per-repo) — tc-3 owns the
 * write; this contract owns the shape.
 */
import { z } from "zod";
import { IsoDateTime } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

export const GoalPeriod = z.enum(["day", "week", "repo"]);
export type GoalPeriod = z.infer<typeof GoalPeriod>;

export const GoalStatus = z.enum(["active", "done", "superseded", "dropped"]);
export type GoalStatus = z.infer<typeof GoalStatus>;

export const Goal = z.object({
  /** UUID or deterministic slug. */
  goal_id: z.string(),
  /** "" for cross-repo / global goals. */
  repo: z.string(),
  /** Default "."; joins with the (repo, coordinator_root_path) keying used everywhere else. */
  coordinator_root_path: z.string(),
  period: GoalPeriod,
  /** ISO date (YYYY-MM-DD) for day; ISO week (YYYY-Www) for week; "ongoing" for repo. */
  period_value: z.string(),
  /** Which machine declared it — the append-only event's author. */
  declared_by_machine: z.string(),
  declared_at: IsoDateTime,
  text: z.string(),
  status: GoalStatus,
  provenance: ProvenanceEnvelope,
});
export type Goal = z.infer<typeof Goal>;
