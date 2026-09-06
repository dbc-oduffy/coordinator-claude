# Plan-Deviation Reconciliation

<!-- spec backlink: archive/specs/2026-05-26-session-end-deviation-reconciliation-gate.md -->

A plan document is a **forecast**. `/distill` crystallizes ALLOWLIST sections of that forecast
into evergreen wiki entries. Without reconciliation, a deprecated forecast shape — a function
signature that changed, a decision that was reversed, an API contract that shipped differently —
becomes the canonical record when distill runs. `/workstream-complete`'s `plan-vs-reality-reconcile` judgment point closes this gap by
reconciling forecast→reality **at the source**, upstream of distill, so the shipped shape
crystallizes and the deprecated forecast does not.

---

## Two Contact Points

| Step | Role |
|------|------|
| `/workstream-complete`'s `plan-vs-reality-reconcile` judgment point | **Writer** — corrects the plan doc in place via `(was: <plan-forecast>)` ALLOWLIST annotations. The `## Deviations` audit table is **NOT AUTO-APPENDED**; historical archived plans may carry one. |
| `/distill` Phase 5a | **Consumer** — extracts `[SUPERSEDED]` nuggets from corrected ALLOWLIST sections. Drops any legacy `## Deviations` table as `[EPHEMERAL]` (backwards-compat for archived plans). |

These are the only two contact points. `/handoff` does not reconcile (mid-flight: the deviation
set is not final). `/merging-to-main` and `/workday-complete` do not reconcile (downstream of the
seam that already reconciled at workstream-complete).

**Status-stamp note:** Step 2.4 now also stamps `status:` → `implemented` on the governing plan via `archive-stamp-cli stamp-plan-implemented <plan_path>` (claude-klabauter `coordinator_core/archive_stamp.py::cs_stamp_plan_implemented`) — guarded (only non-terminal source statuses flip; no-op otherwise). This is a header-agreement stamp, not a distinct reconciliation mechanism — see `docs/wiki/coordinator-tripwires.md § STAMP-PLAN-STATUS-ON-SHIP`.

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

**(Legacy / historical only — not auto-written at `/workstream-complete`'s `plan-vs-reality-reconcile` judgment point.)** Historical archived plans may carry a `## Deviations` table from before retirement; `/distill` drops them as `[EPHEMERAL]` for backwards-compat. Do not hand-author new ones — forecast-vs-shipped reconciliation happens entirely via the `(was: <plan-forecast>)` ALLOWLIST annotations above.

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

*Source: project-rag-ue-addon. [universal]*

`/distill` crystallizes plan ALLOWLIST sections into wiki entries. When a plan has an "open DR" or unresolved decision recorded in an ALLOWLIST section, distill may crystallize it as an *open question* in the wiki — even when the implementation already resolved it in code. The distilled wiki then carries a stale "open" marker for a decision that shipped months ago.

**Rule.** Before treating a distill-forked DR as genuinely open, reconcile it against shipped reality: grep the codebase for the decision's subject, check the git log for commits that settled the question, and read the relevant `(was: <plan-forecast>)` ALLOWLIST annotations in the source plan (or the legacy `## Deviations` table on an older plan). If the current code answers the question, update the wiki entry in-place (remove the "open" marker, write the actual decision) — do not defer as a "separate triage item." An unreconciled "open" DR in a wiki is doctrine rot that misleads future reviewers and prior-art checkers.

## Spinoff Fix-Slates Are Forecasts Too — Reconcile Against Recently-Shipped Sibling Plans at Pickup

The opening framing — *a plan document is a forecast* — applies with equal force to a **spinoff
handoff's proposed fix-slate**, and the reconciliation contact point is different: it fires at
**pickup**, not at distill. A spinoff authored today can be substantially obsoleted by a concurrent
sibling migration that lands between spinoff-authoring and pickup. A real instance: a handoff
prescribed "patch 4 shell scripts," but a sibling plan had already shipped the fleet-op wiring and
the keystone bug was engine-resident (fixed via memo) — reading the cited scripts plus the git log
for recently-landed plans collapsed the work from a rewrite to one selector hole plus cleanup.

**Rule.** At pickup, before executing a handoff's fix-slate, grep `docs/plans/` (and `git log`) for
recently-committed work touching the handoff's scope. Reconcile the slate against what already
shipped — do not execute the forecast as written when reality has moved underneath it. This is the
pickup-time cousin of § Distill-Forked Open DRs above: both refuse to action a stale forecast
without first checking shipped reality.

## Merge-Time Reference Stranding — Distinguish Fix-Locus Error from Real Staleness

<!-- provenance: run 2026-08-06-14h38, nugget c7-042 -->

*Source: 2026-07-25-adhoc-5e7a7d.md*

Merging several plans together can strand inbound references (dependency edges, cross-plan
pointers) that look broken at first pass but are not evidence of staleness. In one instance,
merging four plans stranded roughly 55 inbound references; triage found the largest class was
**fix-locus error** — dependency edges correctly named stubs that were still alive, just
relocated by the merge — not genuine forecast/reality drift. Only four stub pointer lines
actually needed moving to a new location.

**Rule.** When a merge strands a batch of references, do not treat the whole batch as deviation
to reconcile via `(was: <plan-forecast>)` annotations. First classify: is the referenced stub
still alive (fix-locus error — just update the pointer) or genuinely gone/changed (real
staleness — reconcile per the ALLOWLIST correction pattern above)? Conflating the two inflates
the reconciliation workload and risks manufacturing corrections for content that never actually
deviated (see § Proportionality above — do not manufacture corrections).

## Reconciliation Can Surface Live Decision Collisions — Narrow Scope, Don't Force Through

<!-- provenance: run 2026-08-06-14h38, nugget c7-054 -->

*Source: 2026-07-26-stale-bin-plan-repair-sweep-54dacd.md*

Repairing a stale reference or handoff axis during reconciliation can surface a genuine design
collision with a ratified decision record, not just a mechanical pointer fix. One instance: repair
of an `abandoned-to-closed` handoff axis surfaced that the axis, if repaired as originally
proposed, would drive claude-klabauter into re-divergence from DR-084. The resolution was not to force the
original repair through — the axis was narrowed to the plan/initiative/goal axes only, and the
narrowed scope was verified isolated from the DR-084 collision before landing.

**Rule.** When a reconciliation repair collides with a ratified decision, narrow the repair's
scope to what's provably isolated from the collision rather than overriding the decision inline.
A reconciliation task is not license to relitigate a DR — surface the collision, narrow, verify
isolation.

## Duplicate Plans Merge Rather Than Retire — Preserve Disagreements as Open Questions

<!-- provenance: run 2026-08-06-14h38, nugget c7-041 -->

*Source: 2026-07-25-adhoc-5e7a7d.md*

When plan reconciliation uncovers confirmed duplicate plans (same work forecast twice, e.g. an
mcollab/oaxis plan pair), the default disposition is **merge, not retire** — retiring one twin
loses whatever unique context it carried. One sweep merged four confirmed duplicate pairs this
way. Where the merged pair's authors had reached different design conclusions, those five
disagreements were preserved as **open reviewer questions** in the merged plan rather than
silently resolved in one direction — silent resolution would have destroyed the losing side's
reasoning with no record it ever existed. One pair merged against the prevailing direction: the
nominal survivor was externally gated (blocked on an outside dependency) while its twin was
immediately dispatchable, so the dispatchable twin's content became the merge target even though
it was not the "nominal" survivor.

**Rule.** Merge confirmed duplicate plans; do not retire one to save effort. Preserve genuine
design disagreements as open questions for reviewer resolution rather than picking a winner
silently. When one twin is externally blocked and the other dispatchable, prefer the dispatchable
twin as the merge target regardless of which was "nominal."

## Re-Running Pre-Flight Sidecars Can Flip a Verdict — Don't Trust a Stale "Passed"

<!-- provenance: run 2026-08-06-14h38, nugget c7-043 -->

*Source: 2026-07-25-adhoc-5e7a7d.md*

A plan marked COMPLETE can be carrying stale pre-flight sidecar verdicts that were treated as
"passed" but never re-run against current substrate. Re-running two such sidecars flipped the
plan's status from COMPLETE to BLOCKED: the re-run exposed ten substrate rows marked verified
against files that had already been deleted three days earlier. The plan's own "supposedly
complete" sweep had covered itself — it had not re-checked its own verification claims against a
moving substrate.

**Rule.** Do not treat a pre-flight sidecar's recorded verdict as durable truth — re-run it before
trusting a COMPLETE status, especially when substrate (files, rows, artifacts) could have moved
since the verdict was recorded. A plan claiming completeness is itself a forecast subject to the
same reconcile-against-shipped-reality discipline as any other ALLOWLIST section.

## Companion Doctrine

- `/workstream-complete`'s `plan-vs-reality-reconcile` judgment point — the writer; see `skills/workstream-complete/SKILL.md`
- `/distill` Phase 5a — the consumer; see `commands/distill.md`
- `docs/wiki/writing-plans.md` § Plan Document Lifecycle — plan authors: forecast-vs-shipped reconciliation uses `(was: <plan-forecast>)` ALLOWLIST annotations; `## Deviations` is not auto-written
- `docs/wiki/ceremony-calibration.md` — proportionality calibration
