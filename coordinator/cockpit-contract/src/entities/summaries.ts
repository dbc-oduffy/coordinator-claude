/**
 * Read-from-disk consumed shapes — the coordinator-artifact summaries the
 * connector (tc-4) / emitter (tc-3) extract from each repo's `state/` tree and
 * the store (tc-5) ingests for the cross-repo census.
 *
 * These are part of the frozen C5-consumable field set (tc-2 stub § Specification):
 * a field gap here forces a re-run of tc-3 AND tc-4, so the full set is pinned now.
 * `repo` + `coordinator_root_path` are injected by the connector/emitter (the
 * on-disk frontmatter does not carry which repo it was read from). Provenance is
 * mandatory, as on every cockpit fact.
 */
import { z } from "zod";
import { IsoDate, IsoDateTime } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

// ── Handoff summary (from state/handoffs/*.md frontmatter) ───────────────────

export const HandoffStatus = z.enum(["active", "consumed", "superseded"]);
export type HandoffStatus = z.infer<typeof HandoffStatus>;

/**
 * Handoff kind. NORMALISATION CONTRACT (tc-3/tc-4): on-disk frontmatter omits the
 * `kind:` key for plain continuation handoffs — the connector/emitter MUST inject
 * `"session-handoff"` when `kind:` is absent before emitting a HandoffSummary, or
 * the (required, non-optional) `kind` field below will fail Zod validation.
 */
export const HandoffKind = z.enum([
  "session-handoff", // plain continuation (frontmatter `kind:` absent → inject this)
  "spinoff",
  "spinoff-roadmap",
  "recovery",
]);
export type HandoffKind = z.infer<typeof HandoffKind>;

export const DeploymentState = z.enum([
  "awaiting_gate",
  "ready_to_fire",
  "in_flight",
  "shipped",
  "abandoned",
]);
export type DeploymentState = z.infer<typeof DeploymentState>;

export const HandoffSummary = z.object({
  /** Injected by connector/emitter from which repo it was read. */
  repo: z.string(),
  coordinator_root_path: z.string(),
  title: z.string(),
  created: IsoDate,
  status: HandoffStatus,
  kind: HandoffKind,
  deployment_state: DeploymentState,
  workstream: z.string(),
  /** Handoff path or "none". */
  predecessor: z.string(),
  /** Affected file paths (frontmatter `scope:` list) — stored as JSON array in tc-5. */
  scope: z.array(z.string()),
  provenance: ProvenanceEnvelope,
});
export type HandoffSummary = z.infer<typeof HandoffSummary>;

// ── Backlog item summary (debt / bug / improvement YAML) ─────────────────────

export const BacklogType = z.enum(["debt", "bug", "improvement"]);
export type BacklogType = z.infer<typeof BacklogType>;

/** Bug severity ladder (P3 observed on-disk alongside the corpus-noted P0–P2). */
export const BugSeverity = z.enum(["P0", "P1", "P2", "P3"]);
export type BugSeverity = z.infer<typeof BugSeverity>;

/** Backlog queue scope — discriminates the central universal queue from per-project backlogs (C-F4). */
export const BacklogQueueScope = z.enum(["central", "project"]);
export type BacklogQueueScope = z.infer<typeof BacklogQueueScope>;

export const BacklogItemSummary = z.object({
  /** debt | bug | improvement — the type tag discriminating which queue this came from. */
  type: BacklogType,
  id: z.string(),
  created: IsoDate,
  status: z.string(),
  title: z.string(),
  /**
   * Connector-injected registry shortname of the repo this item was read from (D4).
   * Census keying dimension — matches `repo` on HandoffSummary and other summary entities.
   * DISTINCT from `from_repo`: `repo` = which repo the YAML file lives in (connector-injected);
   * `from_repo` = YAML-authored authoring-EM identity (the `from_repo:` field in the YAML itself).
   */
  repo: z.string(),
  /** Source repo (YAML `from_repo` authoring-EM identity — NOT the same as `repo`). */
  from_repo: z.string(),
  coordinator_root_path: z.string(),
  /**
   * Whether this item came from the central universal queue (`coordinator-improvement-queue.md`)
   * or a per-project backlog (`state/{debt,bug,improvement}-backlog/`). Non-nullable (C-F4).
   */
  queue_scope: BacklogQueueScope,
  /** Present only for bug items; null otherwise. */
  severity: BugSeverity.nullable(),
  /**
   * Present only for debt items; null otherwise. Free-text on disk (the
   * debt-backlog `risk:` field is a prose sentence, not an enum — verified
   * against state/debt-backlog/*.yaml), so tc-5 stores this as a TEXT column.
   */
  risk: z.string().nullable(),
  provenance: ProvenanceEnvelope,
});
export type BacklogItemSummary = z.infer<typeof BacklogItemSummary>;

// ── Review-trail record (from state/review-trail/*.json) ──────────────────────

export const ReviewVerdict = z.enum(["ok", "warn", "blocked", "waived"]);
export type ReviewVerdict = z.infer<typeof ReviewVerdict>;

export const ReviewTrail = z.object({
  /** Injected by connector/emitter. */
  repo: z.string(),
  coordinator_root_path: z.string(),
  sha_range: z.string(),
  reviewer: z.string(),
  verdict: ReviewVerdict,
  /** Lines of diff reviewed. */
  diff_loc: z.number().int(),
  /**
   * ISO-8601 UTC — the review's own date. The review-trail JSON body carries no
   * canonical date field (verified across state/review-trail/*.json); the date is
   * encoded in the filename (`YYYY-MM-DD-...json`), so the connector/emitter
   * injects it here. tc-5 needs this for `WHERE reviewed_at BETWEEN ...` queries —
   * provenance.observed_at is the OBSERVATION time, not the review date.
   */
  reviewed_at: IsoDateTime,
  provenance: ProvenanceEnvelope,
});
export type ReviewTrail = z.infer<typeof ReviewTrail>;
