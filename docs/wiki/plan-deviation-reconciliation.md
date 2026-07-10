# Plan-Deviation Reconciliation

<!-- spec backlink: archive/specs/2026-05-26-session-end-deviation-reconciliation-gate.md -->

A plan document is a **forecast**. `/distill` crystallizes ALLOWLIST sections of that forecast
into evergreen wiki entries. Without reconciliation, a deprecated forecast shape — a function
signature that changed, a decision that was reversed, an API contract that shipped differently —
becomes the canonical record when distill runs. `/workstream-complete` Step 2.4 closes this gap by
reconciling forecast→reality **at the source**, upstream of distill, so the shipped shape
crystallizes and the deprecated forecast does not.

---

## Two Contact Points

| Step | Role |
|------|------|
| `/workstream-complete` Step 2.4 | **Writer** — corrects the plan doc in place via `(was: <plan-forecast>)` ALLOWLIST annotations. The `## Deviations` audit table is **NO LONGER AUTO-APPENDED** (retired 2026-06-15); historical archived plans may carry one. |
| `/distill` Phase 5a | **Consumer** — extracts `[SUPERSEDED]` nuggets from corrected ALLOWLIST sections. Drops any legacy `## Deviations` table as `[EPHEMERAL]` (backwards-compat for archived plans). |

These are the only two contact points. `/handoff` does not reconcile (mid-flight: the deviation
set is not final). `/merge-to-main` and `/workday-complete` do not reconcile (downstream of the
seam that already reconciled at workstream-complete).

**Status-stamp note:** Step 2.4 now also stamps `status:` → `implemented` on the governing plan via `cs_stamp_plan_implemented <plan_path>` (`coordinator/lib/coordinator-archive-stamp.sh`) — guarded (only non-terminal source statuses flip; no-op otherwise). This is a header-agreement stamp, not a distinct reconciliation mechanism — see `docs/wiki/coordinator-tripwires.md § STAMP-PLAN-STATUS-ON-SHIP`.

---

## In-Place ALLOWLIST Correction

When the implementation deviated from what the plan's ALLOWLIST sections (Decisions Made, API
Contracts / Function Signatures, Sequencing) forecast, the EM corrects the affected item in place
using the `SHIPPED:` annotation:

```
SHIPPED: <what actually shipped> (was: <plan forecast>)
```

**Examples:**

- `SHIPPED: POST /api/v2/runs (was: POST /api/v1/runs)`
- `SHIPPED: reconcile_plan_doc(plan_path, session_ctx) (was: reconcile_plan_doc(plan_path))`
- `SHIPPED: Step 2.4 fires after Step 2 as a micro-chain (was: Step 2.4 is a sequential-gates peer)`

The `(was: Y)` half is inline supersession provenance — it records what was displaced, not a
live decision. What crystallizes into the wiki is the shipped `X` half: Phase 1 extracts the
corrected line as a `[DECISION]` nugget whose decision *is* `X`, so `Y` cannot crystallize as a
competing decision. (Distill's standalone `[SUPERSEDED]` nugget class is for a *later artifact
reversing an earlier one* — it is not auto-derived from the inline `(was:)` syntax; the loop does
not depend on that tagging.) Verbose deviation reasons live in git (`last_verbose_sha`) and the archived spec's
verbatim-trimmed ALLOWLIST section.

**No-deviation case:** if nothing deviated, the ALLOWLIST sections need no annotation. Step 2.4
is a no-op in that case — do not manufacture corrections.

---

## Acceptance Criteria Table Deviations — Handled Differently

AC tables in plans are optional prose artifacts for review context. Their Criterion and Status
columns should be treated as **read-only after the plan is authored** — free-text mutation
of those cells corrupts the structured record that reviewers and the post-ship narrative rely on.

When an AC shipped differently from what was forecast:

1. **Status column** — change to `shipped-differently` and add a one-line note naming what shipped
2. **Substantive delta** — record in the Decisions Made section's `(was: <plan-forecast>)` ALLOWLIST annotation

The Criterion cell remains as authored. The Decisions Made `(was: ...)` annotation is
the narrative record; the AC table carries only the status signal.

---

## `## Deviations` Section Format

**(Legacy / historical only — retired 2026-06-15; no longer auto-written at `/workstream-complete` Step 2.4.)** Historical archived plans may carry a `## Deviations` table from before retirement; `/distill` continues to drop them as `[EPHEMERAL]` for backwards-compat. Do not hand-author new ones — forecast-vs-shipped reconciliation now happens entirely via the `(was: <plan-forecast>)` ALLOWLIST annotations above.

**Heading:** exactly `## Deviations` (no variants).

**Format:**

```markdown
## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| <brief description of what shipped vs forecast> | <why> | <short SHA or "n/a"> |
```

One row per deviation. Keep descriptions brief — verbose context lives in the commit message
(cited via the commit column) and the archived spec. The section is **provenance-only audit
material** — it is intentionally non-crystallized and `/distill` drops it as `[EPHEMERAL]`
without re-homing its rows.

**`/distill` exemption:** `## Deviations` is the first and only exception to distill's
unconditional re-homing scan for DENYLIST sections. The exemption is bounded to headings that
exactly match `## Deviations`. All other DENYLIST sections retain the unconditional re-homing
scan. The crystallized equivalent of each deviation row already lives in the corrected ALLOWLIST
section (`SHIPPED: X (was: Y)`) — the `deviation/reason/commit` lines add audit depth, not new
facts, and are intentionally non-crystallized.

---

## Proportionality — When Step 2.4 Fires

Step 2.4 is **conditional**: it fires only when a governing plan or spec exists for this session's
work (reusing Step 2.9's existing predicate). Sessions with no governing plan skip Step 2.4
entirely. Do not invent a plan to reconcile against.

This keeps the gate proportional per `docs/wiki/ceremony-calibration.md`: plan-governed sessions
get a reconciliation write-back; organic fix/doc-touch sessions see no added ceremony.

---

## Distill Behavior Summary

| Section type | Distill fate |
|---|---|
| Corrected ALLOWLIST (contains `SHIPPED: X (was: Y)`) | Crystallizes the shipped shape `X` as the live `[DECISION]`; `(was: Y)` rides along as inline supersession provenance (NOT auto-tagged `[SUPERSEDED]` — that nugget class is for cross-artifact reversal). The forecast `Y` never crystallizes as a competing decision. |
| `## Deviations` table | Dropped as `[EPHEMERAL]`; no re-homing; does not trigger negative-AC halt |
| Uncorrected ALLOWLIST sections | Crystallize normally (no deviation, no annotation) |

---

## Distill-Forked Open DRs — Reconcile Against Shipped Reality

*Source: project-rag-ue-addon, 2026-05-29. [universal]*

`/distill` crystallizes plan ALLOWLIST sections into wiki entries. When a plan has an "open DR" or unresolved decision recorded in an ALLOWLIST section, distill may crystallize it as an *open question* in the wiki — even when the implementation already resolved it in code. The distilled wiki then carries a stale "open" marker for a decision that shipped months ago.

**Rule.** Before treating a distill-forked DR as genuinely open, reconcile it against shipped reality: grep the codebase for the decision's subject, check the git log for commits that settled the question, and read the relevant `(was: <plan-forecast>)` ALLOWLIST annotations in the source plan (or the legacy `## Deviations` table if the plan predates 2026-06-15). If the shipped code answers the question, update the wiki entry in-place (remove the "open" marker, write the actual decision) — do not defer as a "separate triage item." An unreconciled "open" DR in a wiki is doctrine rot that misleads future reviewers and prior-art checkers.

## Companion Doctrine

- `/workstream-complete` Step 2.4 — the writer; see `skills/workstream-complete/SKILL.md`
- `/distill` Phase 5a — the consumer; see `commands/distill.md`
- `docs/wiki/writing-plans.md` § Plan Document Lifecycle — plan authors: `## Deviations` is no longer auto-written (retired 2026-06-15); forecast-vs-shipped reconciliation uses `(was: <plan-forecast>)` ALLOWLIST annotations
- `docs/wiki/ceremony-calibration.md` — proportionality calibration
