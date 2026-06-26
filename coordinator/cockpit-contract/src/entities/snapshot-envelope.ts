/**
 * SnapshotEnvelope — the top-level shape of every emitted cockpit snapshot.
 *
 * Spec backlink: state/roadmap/cockpit-contract-ext-2026-06-22/COORDINATOR-RESOLUTIONS.md
 * § R5 (the Staff Engineer F0): formalize the ad-hoc jq-assembled top-level object
 * (bin/emit-cockpit-snapshot.sh:1084-1129) as a governed Zod schema so adding
 * new keys (`plans`, `lessons`) is a governed schema change, not silent shape drift.
 *
 * This is the breaking surface that justifies the 1.0 major bump (R1 amendment, F7).
 * The emitter assembles this object; tc-6 / MCP / opticon consume it as the
 * parse root.
 *
 * Arrays new in 1.0 (`plans`, `lessons`) are present-but-can-be-empty (D9) so the
 * emitter can land them as `[]` until tc-2/tc-3 wire them up.
 *
 * Nullability discipline: D9 — present-as-null for singular slots (narrative_views);
 * fleet arrays (`coordinator_roots`, `branches`) are required and default to `[]`,
 * never null. All other required arrays are similarly never null (default to []).
 */
import { z } from "zod";
import { IsoDateTime } from "../common.js";
import { CoordinatorRoot } from "./coordinator-root.js";
import { Branch } from "./branch.js";
import { DayRollup, WeekRollup } from "./rollup.js";
import { HandoffSummary, BacklogItemSummary, ReviewTrail } from "./summaries.js";
import { CrossRepoMemoSummary } from "./cross-repo-memo-summary.js";
import { RoutineSignal } from "./routine-signal.js";
import { Goal } from "./goal.js";
import { LessonSummary } from "./lesson-summary.js";
import { PlanSummary } from "./plan-summary.js";

/**
 * Malformed-record buckets — each bucket carries the raw JSON that failed Zod parse.
 * `plans` and `lessons` buckets added in 1.0; tc-3/tc-4 emit wiring requires quarantine
 * slots or failed-record draining silently discards new entity arrays.
 * `cross_repo_memos` bucket added in 1.0 for quarantine-slot consistency (C6-envelope).
 */
// Review: code-reviewer — plans/lessons/cross_repo_memos buckets needed so tc-3/tc-4 emit wiring has quarantine slots (F5).
export const MalformedRecords = z.object({
  handoffs: z.array(z.record(z.string(), z.unknown())),
  backlogs: z.array(z.record(z.string(), z.unknown())),
  review_trail: z.array(z.record(z.string(), z.unknown())),
  coordinator_roots: z.array(z.record(z.string(), z.unknown())),
  plans: z.array(z.record(z.string(), z.unknown())),
  lessons: z.array(z.record(z.string(), z.unknown())),
  cross_repo_memos: z.array(z.record(z.string(), z.unknown())),
});
export type MalformedRecords = z.infer<typeof MalformedRecords>;

/** The nested backlogs object, one array per queue type. */
export const BacklogsEnvelope = z.object({
  bug: z.array(BacklogItemSummary),
  debt: z.array(BacklogItemSummary),
  improvement: z.array(BacklogItemSummary),
});
export type BacklogsEnvelope = z.infer<typeof BacklogsEnvelope>;

/**
 * Period-keyed completion rollup arrays (C5 — the Staff Engineer F0 resolution).
 *
 * Replaces the old single-object form (`{ week: WeekRollup | null, day: DayRollup | null }`).
 * Keyed-object-of-arrays sidesteps the DayRollup/WeekRollup `z.union` discrimination
 * footgun (structurally identical discriminant-less shapes confuse Zod union parsing).
 * Each period bucket is an array so the snapshot can carry multiple rollup windows
 * (e.g. current + previous week) as queryable entries rather than a single latest-slot.
 *
 * tc-3 emitter MUST emit the nested plural shape — not the old singular `completion_rollup`.
 */
export const CompletionRollups = z.object({
  day: z.array(DayRollup),
  week: z.array(WeekRollup),
});
export type CompletionRollups = z.infer<typeof CompletionRollups>;

export const SnapshotEnvelope = z.object({
  /**
   * Sourced from CONTRACT_VERSION via the emitted bundle .version (the Staff Engineer F1).
   * Must be a semver string matching the exported CONTRACT_VERSION constant.
   */
  // Review: code-reviewer — semver regex prevents silent version drift; ties schema_version to CONTRACT_VERSION shape.
  schema_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  /** ISO-8601 UTC wall-clock when the snapshot was assembled. */
  emitted_at: IsoDateTime,
  /** Hostname of the machine that ran the emitter. */
  emitted_by_machine: z.string(),
  /**
   * Fleet of coordinator roots observed in this snapshot (one-fleet-snapshot shape).
   * Each row carries `repo` + `coordinator_root_path` + `owner` + `machine` for keying.
   * Required array; emitter MUST emit `[]` when there are no entries rather than omitting the key (D9). An absent key fails parse.
   */
  coordinator_roots: z.array(CoordinatorRoot),
  /**
   * Active git branches across the fleet. A single branch is incoherent in a
   * multi-root fleet snapshot — this replaces the singular `branch` field.
   * Required array; emitter MUST emit `[]` when there are no entries rather than omitting the key (D9). An absent key fails parse.
   */
  branches: z.array(Branch),
  handoffs: z.array(HandoffSummary),
  /** Period-keyed queryable arrays of completion rollups; replaces the former single latest-week/day object. */
  completion_rollups: CompletionRollups,
  backlogs: BacklogsEnvelope,
  review_trail: z.array(ReviewTrail),
  routine_signals: z.array(RoutineSignal),
  goals_current: z.array(Goal),
  /** Plans summary, present-but-empty until tc-3 wires the emit section (D9). */
  plans: z.array(PlanSummary),
  /** Lessons summary, present-but-empty until tc-3 wires the emit section (D9). */
  lessons: z.array(LessonSummary),
  /** Outstanding cross-repo memos, metadata-only (no memo bodies; C6-envelope). */
  cross_repo_memos: z.array(CrossRepoMemoSummary),
  /** Narrative / LLM-generated view layer; null when not yet generated. */
  narrative_views: z.unknown().nullable(),
  malformed_records: MalformedRecords,
});
export type SnapshotEnvelope = z.infer<typeof SnapshotEnvelope>;
