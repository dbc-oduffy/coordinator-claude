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

/**
 * Handoff lifecycle stage — the two-value enumeration governing the current
 * actionability of a handoff: `active` (in play, awaiting pickup) or `consumed`
 * (picked up and acted on).
 *
 * **`superseded` was retired as a handoff status on 2026-06-26 (handoff-only).**
 * Supersession of a handoff is now expressed via `deployment_state: abandoned`
 * combined with the existing `predecessor`/`supersedes:` lineage fields — not a
 * distinct status value. The retirement sequence: doctrine writers (CLAUDE.md,
 * spinoff-handoffs.md, skills/handoff/SKILL.md, schemas/handoff.yaml) and live
 * data were migrated first; the contract was narrowed after (contract follows
 * doctrine, not vice-versa).
 *
 * **Legacy/external tolerance — coerce-at-ingest:** readers tolerate a legacy or
 * external handoff carrying `status: superseded`. The cockpit emitter
 * (`bin/emit-cockpit-snapshot.sh`) coerces `superseded` → `consumed` at ingest,
 * before the strict Zod validator sees the record. `schemas/handoff-archived.yaml`
 * also stays tolerant of `superseded` upstream so `query-records --type handoff-archived`
 * (which runs before the jq coerce) does not reject historical archived records.
 * Any other string-but-unrecognized handoff status that passes the per-record jq
 * `select` (which excludes only missing/null fields) but is NOT coerced triggers a
 * **whole-emit abort** at `validate_main_record` — not a per-record exclusion. Only
 * the one retired `superseded` token is coerced; any other unexpected status string
 * still hard-aborts the emit.
 *
 * **Stage vs. `deployment_state` — orthogonal axes, not redundant:**
 * `status` answers "is this handoff still in play?" — a two-stage gate.
 * `deployment_state` answers "where is the associated workstream in its delivery
 * lifecycle?" — a richer progression (`awaiting_gate | ready_to_fire | in_flight |
 * shipped | abandoned`). These are INDEPENDENT dimensions: a `consumed` handoff can
 * carry `deployment_state: in_flight` (picked up but not yet shipped); an `active`
 * handoff can carry `deployment_state: ready_to_fire` (staged, awaiting pickup).
 * Consumers keying on one axis must not substitute the other.
 *
 * Spec backlink: `docs/plans/2026-06-26-retire-superseded-handoff-status.md` § C4.
 */
export const HandoffStatus = z.enum(["active", "consumed"]);
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

/**
 * Delivery lifecycle progression for the workstream associated with a handoff.
 * Orthogonal to `HandoffStatus` — see the `HandoffStatus` docstring for the
 * stage↔`deployment_state` partition explanation.
 */
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
  /**
   * Session id that consumed this handoff (frontmatter `consumed_by:` field).
   * D9: nullable, never optional — key MUST be present, null when unset.
   */
  consumed_by: z.string().nullable(),
  /**
   * ISO-8601 UTC timestamp when the handoff was picked up.
   * D9: nullable, never optional — key MUST be present, null when unset.
   */
  consumed_at: IsoDateTime.nullable(),
  /**
   * Resolved commit sha + date when the workstream shipped.
   * Opticon wants the date for timeline rendering.
   * D9: nullable, never optional — key MUST be present, null when unset.
   */
  shipped_in: z.object({ sha: z.string(), date: IsoDate }).nullable(),
  /**
   * Session id that picked up the handoff.
   * D9: nullable, never optional — key MUST be present, null when unset.
   */
  picked_up_by: z.string().nullable(),
  /**
   * Metadata-only progress ratio: done/total acceptance-criterion count.
   * NO raw criterion text — privacy hard constraint for the all-staff web tier;
   * the full typed per-item array is the structured-handoff spinoff's deliverable.
   * D9: nullable, never optional — key MUST be present, null when unset.
   */
  acceptance_criteria: z.object({ done: z.number().int(), total: z.number().int() }).nullable(),
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
//
// NOTE — intentionally dropped on-disk fields: the on-disk review-trail JSON also
// carries `scope` (chain|session), `scope_kind` (diff|plan|integration), and
// `session_id` (the authoring session). These fields are consumed by
// workweek-trail-scope.sh for scope accounting but are NOT emitted to this cockpit
// entity. Do not add them to the Zod schema without a tc-3/tc-4/tc-5 migration plan.

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
  /**
   * Join key back to the handoff's `workstream` slug.
   * D9: nullable, never optional — archived review-trail records predate this field;
   * tolerant-reader rule: present-as-null for records that lack it.
   */
  workstream: z.string().nullable(),
  provenance: ProvenanceEnvelope,
});
export type ReviewTrail = z.infer<typeof ReviewTrail>;
