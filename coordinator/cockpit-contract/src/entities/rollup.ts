/**
 * DayRollup and WeekRollup — deterministic aggregation is the SSOT; narrative is
 * a regenerable VIEW over the deterministic numbers (the Data Science Reviewer P1-D4).
 *
 * Rule: deterministic aggregation (GROUP-BY over the completion-log `chain` key)
 * is reproducible and authoritative. The narrative is regenerable and MUST cite
 * its input watermark; it is never a substitute for the deterministic counts —
 * hence `deterministic_facts` is non-nullable and `narrative` is nullable.
 *
 * Dedupe grain is the completion-log `chain` key: the three overlapping sources
 * (completion log, week-changelog daily blocks, daily-summaries — the last
 * already synthesised from the completion log) dedupe to this grain to avoid
 * double-counting in week rollups. tc-3 emission owns the dedupe; this contract
 * pins the shape.
 */
import { z } from "zod";
import { IsoDateTime } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

export const Freshness = z.enum(["current", "stale"]);
export type Freshness = z.infer<typeof Freshness>;

/** Watermark of the inputs a narrative was generated from — makes "stale as of when" falsifiable. */
export const RollupWatermark = z.object({
  /** ISO-8601 UTC — latest observed_at across all input facts. */
  max_observed_at: IsoDateTime,
  /** Latest commit SHA in the period. */
  max_commit_sha: z.string(),
  /** Number of distinct source records consumed. */
  source_count: z.number().int(),
});
export type RollupWatermark = z.infer<typeof RollupWatermark>;

/** Regenerable narrative over the deterministic rollup; cites its input watermark. */
export const RollupNarrative = z.object({
  text: z.string(),
  /** Model/agent slug. */
  generated_by: z.string(),
  generated_at: IsoDateTime,
  input_watermark: RollupWatermark,
});
export type RollupNarrative = z.infer<typeof RollupNarrative>;

export const DayRollup = z.object({
  grain: z.enum(["chain", "day"]),
  /** ISO date YYYY-MM-DD. */
  period: z.string(),
  /** "" for cross-repo aggregate. */
  repo: z.string(),
  coordinator_root_path: z.string(),
  deterministic_facts: z.object({
    chains_completed: z.number().int(),
    /** {"XS": N, "S": N, …}. */
    tshirt_counts: z.record(z.string(), z.number().int()),
    opus_dispatches: z.number().int(),
    commits: z.number().int(),
  }),
  /** null if not yet generated; never a substitute for deterministic_facts. */
  narrative: RollupNarrative.nullable(),
  input_watermark: RollupWatermark,
  freshness: Freshness,
  provenance: ProvenanceEnvelope,
});
export type DayRollup = z.infer<typeof DayRollup>;

export const WeekRollup = z.object({
  grain: z.literal("week"),
  /** ISO week YYYY-Www. */
  period: z.string(),
  repo: z.string(),
  coordinator_root_path: z.string(),
  deterministic_facts: z.object({
    chains_completed: z.number().int(),
    tshirt_counts: z.record(z.string(), z.number().int()),
    opus_dispatches: z.number().int(),
    commits: z.number().int(),
    reviews_conducted: z.number().int(),
    /** {"ok": N, "warn": N, "blocked": N}. */
    verdicts: z.record(z.string(), z.number().int()),
  }),
  narrative: RollupNarrative.nullable(),
  input_watermark: RollupWatermark,
  freshness: Freshness,
  provenance: ProvenanceEnvelope,
});
export type WeekRollup = z.infer<typeof WeekRollup>;
