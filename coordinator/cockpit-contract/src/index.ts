/**
 * @coordinator/cockpit-contract — the work-state data contract (tc-2).
 *
 * The single artifact both the producer half (`~/.claude` emission, tc-3) and the
 * ingestion/query/display stack (tc-4 connector, tc-5 store, tc-6 dashboard,
 * tc-8 MCP) import. Zod schemas are the authoring source of truth; TypeScript
 * types are inferred from them (never hand-maintained in parallel); the canonical
 * cross-repo wire format is the JSON Schema emitted under `schema/` (R7 — the
 * opticon repo generates its TS/Zod from that JSON Schema, it does not host it).
 *
 * `ENTITY_SCHEMAS` is the registry that drives schema emission and the round-trip
 * test — add an entity here and both pick it up automatically.
 */
import type { ZodType } from "zod";

import { ProvenanceEnvelope } from "./provenance.js";
import { CoordinatorRoot } from "./entities/coordinator-root.js";
import { Branch } from "./entities/branch.js";
import { Goal } from "./entities/goal.js";
import { RoutineSignal } from "./entities/routine-signal.js";
import { DayRollup, WeekRollup } from "./entities/rollup.js";
import {
  HandoffSummary,
  BacklogItemSummary,
  ReviewTrail,
} from "./entities/summaries.js";
import { LessonSummary } from "./entities/lesson-summary.js";
import { PlanSummary } from "./entities/plan-summary.js";
import { CrossRepoMemoSummary } from "./entities/cross-repo-memo-summary.js";
import { SnapshotEnvelope } from "./entities/snapshot-envelope.js";

export * from "./common.js";
export * from "./provenance.js";
export * from "./entities/coordinator-root.js";
export * from "./entities/branch.js";
export * from "./entities/goal.js";
export * from "./entities/routine-signal.js";
export * from "./entities/rollup.js";
export * from "./entities/summaries.js";
export * from "./entities/lesson-summary.js";
export * from "./entities/plan-summary.js";
export * from "./entities/cross-repo-memo-summary.js";
export * from "./entities/snapshot-envelope.js";

/** Contract version — bump on any breaking field change to the emitted schema. */
export const CONTRACT_VERSION = "2.0.0";

/**
 * Every emittable entity, keyed by stable kebab-case name (used as the JSON
 * Schema filename and the round-trip test label). ProvenanceEnvelope is included
 * as a shared type so the emitted schema set is self-contained.
 */
export const ENTITY_SCHEMAS: Record<string, ZodType> = {
  "provenance-envelope": ProvenanceEnvelope,
  "coordinator-root": CoordinatorRoot,
  branch: Branch,
  goal: Goal,
  "routine-signal": RoutineSignal,
  "day-rollup": DayRollup,
  "week-rollup": WeekRollup,
  "handoff-summary": HandoffSummary,
  "backlog-item-summary": BacklogItemSummary,
  "review-trail": ReviewTrail,
  "lesson-summary": LessonSummary,
  "plan-summary": PlanSummary,
  "cross-repo-memo-summary": CrossRepoMemoSummary,
  "snapshot-envelope": SnapshotEnvelope,
};
