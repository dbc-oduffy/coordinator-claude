/**
 * LessonSummary — one captured lesson from the full {lessons.md} ∪ {lessons-outbox/} ∪
 * {drained/} union surface.
 *
 * Spec backlink: state/roadmap/cockpit-contract-ext-2026-06-22/COORDINATOR-RESOLUTIONS.md § R4
 * + pinned field set (C-F1/C-F2/C-F3/C-F7).
 *
 * Coverage: ALL lessons, not only promoted ones. The EMITTER is the structuring boundary —
 * it performs a FULL OUTER JOIN of lessons.md ∪ outbox ∪ drained (C-F3: NOT a simple LEFT-JOIN;
 * outbox/drained-only entries with no lessons.md body are also emitted). parse_status is
 * non-nullable on every record; partial records still carry every field they CAN populate.
 *
 * C-F5: `created` is nullable — time-range queries are only valid over promoted lessons
 * (captured-only entries have null `created` and must be excluded from date-bounded queries).
 *
 * `repo` and `coordinator_root_path` are connector-injected (D4), never in on-disk prose.
 * Nullable fields follow D9 (present-as-null, not optional).
 */
import { z } from "zod";
import { IsoDateTime } from "../common.js";
import { ProvenanceEnvelope } from "../provenance.js";

export const LessonScope = z.enum(["universal", "project"]);
export type LessonScope = z.infer<typeof LessonScope>;

export const LessonPromotionState = z.enum(["captured", "pending", "drained"]);
export type LessonPromotionState = z.infer<typeof LessonPromotionState>;

/**
 * parse_status — result of the prose→fields decomposition.
 * - ok: all required fields fully parsed.
 * - partial: at least one decomposed field could not be extracted (DEGRADED-BUT-COUNTED;
 *   the entry is still emitted so "all lessons" coverage is honest).
 * Spec: COORDINATOR-RESOLUTIONS § R4 C-F2.
 */
export const LessonParseStatus = z.enum(["ok", "partial"]);
export type LessonParseStatus = z.infer<typeof LessonParseStatus>;

export const LessonSummary = z.object({
  /** Connector-injected registry shortname — census keying dimension. Non-nullable. */
  repo: z.string(),
  /** Connector-injected — matches other summary entities. */
  coordinator_root_path: z.string(),
  /**
   * Synthetic identity: 16-char lowercase hex hash of normalized title. PRIMARY KEY for tc-5.
   * Union-dedup key across {lessons.md} ∪ {outbox} ∪ {drained/} (C-F1).
   * Shape: first 16 nibbles of SHA-256(normalize(title)) — e.g. "a3f9c2e1b4d8f6a7".
   */
  // Review: code-reviewer — lesson_key is the stable PK; regex guards hash shape to prevent silent identity collisions.
  lesson_key: z.string().regex(/^[0-9a-f]{16}$/),
  /** Bold-title from the capture entry. */
  title: z.string(),
  /** Parsed from [universal] tag; 'project' when tag absent — emitter MUST supply, no schema default. */
  scope: LessonScope,
  /**
   * Full capture-entry body — raw prose for partial records; parsed body for ok records.
   * Stored as TEXT in tc-5 (C-F8: side-table deferred to v2 if corpus grows).
   */
  body: z.string(),
  /** promotion_state precedence: drained > pending > captured (C-F3). */
  promotion_state: LessonPromotionState,
  /** Non-nullable on every record — ok for clean decomposition, partial for degraded (C-F2). */
  parse_status: LessonParseStatus,
  provenance: ProvenanceEnvelope,

  // Nullable fields (D9 present-as-null) — absent until promotion via outbox/drained join.

  /** 8-value enum on the outbox/drained record; null for captured-only entries. */
  // change_kind stays z.string() pending C-ext-5 enum canonicalization (OVERVIEW § enum drift); do not tighten here.
  change_kind: z.string().nullable(),
  /** Target wiki path; null until promotion. */
  target_wiki: z.string().nullable(),
  /**
   * Authoring-EM identity (e.g. "claude-central-em"), from outbox/drained join.
   * Answers a different question than `repo` (C-F7) — NOT redundant.
   * Null for captured-only entries.
   */
  from_repo: z.string().nullable(),
  /** Free-text evidence from the outbox record; null if not present. */
  evidence: z.string().nullable(),
  /**
   * Minted by coordinator-lesson-promote CLI at promotion time.
   * Null for captured-only entries — time-range queries valid only over promoted lessons (C-F5).
   */
  created: IsoDateTime.nullable(),
});
export type LessonSummary = z.infer<typeof LessonSummary>;
