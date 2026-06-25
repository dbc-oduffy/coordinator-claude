/**
 * SnapshotEnvelope — the top-level shape of every emitted cockpit snapshot.
 *
 * Spec backlink: state/roadmap/cockpit-contract-ext-2026-06-22/COORDINATOR-RESOLUTIONS.md
 * § R5 (Patrik F0): formalize the ad-hoc jq-assembled top-level object
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
 * Nullability discipline: D9 — present-as-null for singular slots (coordinator_root,
 * week/day rollup, narrative_views); required arrays are never null (default to []).
 */
import { z } from "zod";
import { IsoDateTime } from "../common.js";
import { CoordinatorRoot } from "./coordinator-root.js";
import { Branch } from "./branch.js";
import { DayRollup, WeekRollup } from "./rollup.js";
import { HandoffSummary, BacklogItemSummary, ReviewTrail } from "./summaries.js";
import { RoutineSignal } from "./routine-signal.js";
import { Goal } from "./goal.js";
import { LessonSummary } from "./lesson-summary.js";
import { PlanSummary } from "./plan-summary.js";

/**
 * Malformed-record buckets — each bucket carries the raw JSON that failed Zod parse.
 * `plans` and `lessons` buckets added in 1.0; tc-3/tc-4 emit wiring requires quarantine
 * slots or failed-record draining silently discards new entity arrays.
 */
// Review: code-reviewer — plans/lessons buckets needed so tc-3/tc-4 emit wiring has quarantine slots (F5).
export const MalformedRecords = z.object({
  handoffs: z.array(z.record(z.string(), z.unknown())),
  backlogs: z.array(z.record(z.string(), z.unknown())),
  review_trail: z.array(z.record(z.string(), z.unknown())),
  coordinator_root: z.array(z.record(z.string(), z.unknown())),
  plans: z.array(z.record(z.string(), z.unknown())),
  lessons: z.array(z.record(z.string(), z.unknown())),
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
 * Week/day rollup pair, mirroring emit-cockpit-snapshot.sh completion_rollup.
 * NOTE: the spec named flat `week_rollup`/`day_rollup` top-level keys but the contract ships
 * nested as `completion_rollup: { week, day }` to match the emitter's assembled shape.
 * tc-3 emitter MUST emit the nested shape — not the flat spec variant.
 */
export const CompletionRollup = z.object({
  week: WeekRollup.nullable(),
  day: DayRollup.nullable(),
});
export type CompletionRollup = z.infer<typeof CompletionRollup>;

export const SnapshotEnvelope = z.object({
  /**
   * Sourced from CONTRACT_VERSION via the emitted bundle .version (Patrik F1).
   * Must be a semver string matching the exported CONTRACT_VERSION constant.
   */
  // Review: code-reviewer — semver regex prevents silent version drift; ties schema_version to CONTRACT_VERSION shape.
  schema_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  /** ISO-8601 UTC wall-clock when the snapshot was assembled. */
  emitted_at: IsoDateTime,
  /** Hostname of the machine that ran the emitter. */
  emitted_by_machine: z.string(),
  /** CoordinatorRoot record; null when the emitter could not parse it. */
  coordinator_root: CoordinatorRoot.nullable(),
  /** Active git branch summary. */
  branch: Branch,
  handoffs: z.array(HandoffSummary),
  completion_rollup: CompletionRollup,
  backlogs: BacklogsEnvelope,
  review_trail: z.array(ReviewTrail),
  routine_signals: z.array(RoutineSignal),
  goals_current: z.array(Goal),
  /** Plans summary, present-but-empty until tc-3 wires the emit section (D9). */
  plans: z.array(PlanSummary),
  /** Lessons summary, present-but-empty until tc-3 wires the emit section (D9). */
  lessons: z.array(LessonSummary),
  /** Narrative / LLM-generated view layer; null when not yet generated. */
  narrative_views: z.unknown().nullable(),
  malformed_records: MalformedRecords,
});
export type SnapshotEnvelope = z.infer<typeof SnapshotEnvelope>;
