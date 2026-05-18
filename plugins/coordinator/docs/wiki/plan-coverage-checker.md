---
title: plan-coverage-checker pre-review doctrine
created: 2026-05-18
type: doctrine
related:
  - plugins/coordinator/agents/plan-coverage-checker.md
  - plugins/coordinator/snippets/plan-coverage-check-consumption.md
  - plugins/coordinator/docs/wiki/reviewer-pipeline.md
  - plugins/coordinator/docs/wiki/docs-checker-pre-review.md
  - plugins/coordinator/docs/wiki/prior-art-checker.md
  - plugins/coordinator/docs/wiki/external-pattern-checker.md
  - plugins/coordinator/docs/wiki/ceremony-calibration.md
  - tasks/lessons.md
  - docs/plans/2026-05-18-plan-coverage-checker.md
---

<!-- spec-backlink: docs/plans/2026-05-18-plan-coverage-checker.md § Three Lenses, § Trigger Heuristic, § Sidecar Contract -->

# plan-coverage-checker Pre-Review Doctrine

## What is plan-coverage-checker?

plan-coverage-checker is a Sonnet-tier agent that verifies a plan artifact's internal consistency before the artifact reaches an Opus reviewer. It answers a question none of the other pre-flights answer: **does the plan's own fix slate cover the plan's own audit list, with no appetite-based hedges and no substrate citations that drift from disk?**

The agent runs three mechanical lenses — coverage (slate-vs-oracle cross-reference), hedge detection (appetite-based deferral patterns), and substrate drift (in-repo path/symbol/constant verification) — and writes a sidecar at `<plan-path>.plan-coverage-check.md` with five finding buckets: Missed, Ambiguous, Weak-OOS, Hedges, and Substrate-drift.

The output is REPORT-ONLY. The agent makes no decisions and applies no fixes; it surfaces findings for the EM to disposition before the named Opus reviewer is dispatched.

## Empirical motivation — the 36/9/4 case (2026-05-18)

On 2026-05-18, a different EM session produced a "comprehensive fix slate" plan against an audited list of issues. Post-hoc sanity-check by a Sonnet cross-referencer found:

- **36 items** present in the audit but absent from the fix slate (coverage gap)
- **9 items** asserted against substrate that had drifted on disk (paths/symbols/constants no longer matched)
- **4 items** hedged with "follow-up" / "future work" framing where doctrine requires OOS to be architectural

The critical observation: the EM was confident the plan was comprehensive. The 36 misses were not the result of a distracted EM — they were the result of a structural gap in the pipeline. No agent upstream of the Opus reviewer checked whether the slate covered the oracle. The Opus reviewer can catch coverage gaps, but at >10× the token cost of a Sonnet cross-ref, and reviewers tend to assess the slate as-given rather than derive what is missing from a separate audit table.

The 36/9/4 split is the standing empirical motivation for this agent and for the design decision to make its trigger skill-internal (see § Trigger heuristic below).

## The three lenses

The agent runs three checks in sequence. Each produces findings in a distinct bucket. The final verdict is the worst case across all three.

### Lens 1 — Coverage (oracle-vs-slate cross-reference)

Parses the plan for an **oracle table** (audit/findings/issues list) and a **slate table** (fix/chunks/tasks list), then cross-references every oracle item against the slate using signal-confirmed matching (shared file path, shared symbol, shared distinctive noun phrase — in that priority order).

Three classification buckets: **MATCHED** (signal confirmed), **AMBIGUOUS** (signal-partial — stopword-only overlap or uncited consolidation), **MISSED** (no signal, no OOS justification). AMBIGUOUS items are informational only and do NOT gate the INCOMPLETE verdict.

M:N semantics apply: a slate chunk that consolidates multiple oracle items must enumerate them explicitly. Oracle members not explicitly cited in a consolidating chunk → AMBIGUOUS (not MISSED).

When no oracle table is found, the agent emits `SCOPE-MISMATCH` and stops — this is the correct silent skip for greenfield design plans.

For full matching rubric, bucket definitions, and OOS sub-classification (OOS-ARCHITECTURAL vs. OOS-WEAK), see the agent body: `agents/plan-coverage-checker.md § Phase 2`.

### Lens 2 — Hedge / defer detection

Greps the plan body for appetite-based deferral language (follow-up, future work, TBD, if time permits, defer to, etc.) and classifies each hit using a two-stage classifier.

**Stage 1 — section-context (runs first, always):** If the token sits under a `Considered Alternatives / Rejected / Risks / Out of Scope` heading, or inside a markdown blockquote, classify as FALSE-POSITIVE immediately — Stage 2 does NOT run.

**Stage 2 — prose-context (only if Stage 1 did NOT fire):** Reads ±5 lines of context and classifies as HEDGE, OOS-JUSTIFIED, or FALSE-POSITIVE.

Only HEDGE findings produce sidecar entries. Doctrine basis: `coordinator/CLAUDE.md` § Implementation Standards — "OOS framing must be architectural, not appetite-based."

For the complete token list, stage-1 heading regex, and stage-2 classification rules, see the agent body: `agents/plan-coverage-checker.md § Phase 3`.

### Lens 3 — In-repo substrate drift

Extracts all in-repo path citations and `file:line` / `file:symbol` references from the plan body, then verifies each against the current disk state using `ls`, `Read`, and `Grep`.

**Line-drift tolerance is mandatory:** same file, same symbol, line number shifted = FALSE-POSITIVE. The agent only emits a finding when the symbol/identifier is absent from the file, or the file itself is missing. This tolerates the legitimate line drift produced by concurrent-EM workstream branches.

Scope boundary: Lens 3 checks in-repo paths and symbols only. External API signatures are docs-checker's job.

For extraction heuristics, verification procedure, and scope boundary, see the agent body: `agents/plan-coverage-checker.md § Phase 4`.

## Trigger heuristic — skill-internal, not EM-judged

**The EM does not decide whether the agent runs.** The skill (`skills/review/SKILL.md` Phase 2.7d) runs the agent unconditionally on any plan with an oracle table. There is no EM opt-out in v1.

| Plan shape | plan-coverage-checker? |
|---|---|
| Plan contains an audit/findings/issues table (any size) | **Run.** |
| Plan is greenfield design with no found-facts oracle | Skip silently — agent emits `SCOPE-MISMATCH`. |
| Plan is single-file mechanical fix (no design content) | Skip silently. |
| Plan is doc redesign / wiki rewrite | Skip silently. |

**Why no EM opt-out?** The 2026-05-18 incident established that EM confidence is exactly the failure mode this agent exists to prevent. An EM who believes their plan is comprehensive is in the highest-risk state for a coverage gap — not the lowest. Making the trigger EM-judged would re-instantiate the failure mode every time the EM felt confident.

**Revisit criterion (pre-committed, not discretionary):** After 10 plan dispatches through this agent, the EM tallies findings. If the ratio of AMBIGUOUS-or-false-MISSED to true-MISSED is ≥2:1 (mostly noise, not signal), the next iteration adds a `skip_plan_coverage: <architectural-reason>` frontmatter skip-class. This pre-commitment prevents "when to add the opt-out" from becoming the same EM-confidence call the agent exists to prevent.

## Sidecar format

Sidecar path: `<plan-path>.plan-coverage-check.md`

Five finding sections:
- **Missed audit items** — oracle items with no slate entry and no architectural OOS, with the three valid resolution options stated per item (add-to-slate / architectural-OOS / oracle-was-wrong)
- **Ambiguous audit items** — signal-partial matches, informational only, do not gate INCOMPLETE
- **Weak OOS / hedges** — appetite-based deferrals with doctrine citation
- **Substrate drift** — in-repo path/symbol/constant mismatches

Five verdicts:
- **COMPLETE** — zero MISSED, zero weak-OOS, zero substrate-drift. AMBIGUOUS does not gate.
- **INCOMPLETE** — one or more gating findings. EM folds before reviewer dispatch.
- **BLOCKED-SURFACE-TO-PM** — ≥20% of oracle items MISSED (MISSED count alone, not MISSED+AMBIGUOUS) OR ≥3 substrate-drift findings.
- **SCOPE-MISMATCH** — no oracle found. No signal; review proceeds normally.
- **DEGRADED** — agent ran with incomplete coverage. No signal; review proceeds as if lens did not run.

Prior sidecars are never deleted. On re-run, the agent renames the existing sidecar to `<plan-path>.plan-coverage-check.<UTC-mtime>.md` before writing the new one. This preserves the re-run history for feedback-loop analysis.

## When NOT to run

The trigger heuristic is skill-internal, so "when not to run" is encoded in the skip logic rather than EM judgment. The agent silently skips plans without an oracle table. Concretely, this covers:

- **Greenfield design plans** — no audit table, no found-facts list, just a proposed design. The agent emits `SCOPE-MISMATCH` immediately and writes no sidecar.
- **Single-file mechanical fixes** — a plan that says "edit line 47 of file X to fix Y" has no oracle/slate structure worth parsing. Skip.
- **Doc redesigns and wiki rewrites** — no fix-slate shape. Skip.

If you are unsure whether a plan has an oracle, dispatch the agent — a `SCOPE-MISMATCH` is cheap and does not block the pipeline.

## Distinction from sibling pre-flights

The four pre-flights answer orthogonal questions:

| Pre-flight | Question | Corpus | Authority |
|---|---|---|---|
| **plan-coverage-checker** (this) | Does the slate cover the oracle? Are deferrals architectural? Do in-repo citations match disk? | The plan itself + in-repo disk | REPORT-ONLY; fold before reviewer |
| **prior-art-checker** | Have we already established something relevant about this? | Project wikis, global wikis, lessons, improvement queue | REPORT-ONLY; Conflicts survive to reviewer (five direction options) |
| **docs-checker** | Are external API claims factually correct? | Context7, LSP, project-RAG, cppreference | AUTO-FIX allowlist for tradeoff-free corrections |
| **external-pattern-checker** | Are there public-domain patterns we should know about? | Web (public documentation, RFCs, community patterns) | REPORT-ONLY; informational |

**Key divergence from prior-art-checker fold posture.** prior-art-checker WARN sidecars survive to the named Opus reviewer — the reviewer's judgment shapes direction-of-correction on Conflicts (five valid directions, some requiring product input). plan-coverage-checker INCOMPLETE findings fold BEFORE the reviewer, because coverage gaps have only three valid EM-mechanical resolutions (add-to-slate / architectural-OOS / oracle-was-wrong) — none of these require reviewer judgment. The mechanical nature of a missed audit item is what makes pre-fold the correct posture; passing it through the reviewer wastes Opus tokens on a question the EM can resolve mechanically.

## Feedback loop on plan quality

When the same oracle shape produces repeated MISSED findings across multiple plans, that is a feedback signal pointing upstream — the **plan template**, not just the individual plan, has a gap.

If a recurring oracle type (e.g., "all plans that audit CLI flags consistently miss deprecation entries in the flag registry") produces MISSED findings in ≥3 plans, surface to the EM as a candidate for plan-template addition. The plan-coverage-checker thus becomes a quality loop on plan-authoring patterns, not just individual plan correctness.

<!-- Review: code-reviewer — claiming a specific step number (Step 4) was false precision; the activity isn't a named sub-step yet. -->
Operational hook: during `/workweek-complete`, as part of the weekly retrospective sweep (informal — not a numbered sub-step yet; promote to a named sub-step once the cadence proves itself), the EM scans recent `docs/plans/**/*.plan-coverage-check*.md` sidecars for recurring MISSED patterns across plans. Two plans with MISSED on the same oracle shape within a quarter means the plan template (or the authoring skill) has a structural gap worth addressing. This is judgment-based, not automated — but the responsibility lives in the weekly cadence so it does not drift.

## Distribution

The reviewer-side consumption block (`snippets/plan-coverage-check-consumption.md`) is synced via `bin/verify-plan-coverage-sync.sh --fix` to all Opus reviewer prompts that may receive plans with oracle tables:

- `agents/staff-eng.md` (the Staff Engineer)
- `plugins/game-dev/agents/staff-game-dev.md` (the Game Dev Reviewer)
- `plugins/data-science/agents/staff-data-sci.md` (the Data Science Reviewer)
- `plugins/web-dev/agents/senior-front-end.md` (the Front-End Reviewer)
- `agents/eng-director.md` (the Director of Engineering — reviews plans at DoE altitude)

**Excluded intentionally:** `agents/code-reviewer.md` (Sonnet code-shaped review, not plan-shaped) and `agents/staff-ux.md` (the UX Reviewer — UX flow review rarely has audit/slate structure). These exclusions are the same as for the sibling consumption snippets.

The sync verifier is auto-discovered by `/update-docs` Phase 11b. The tripwire entry lives in `docs/wiki/coordinator-tripwires.md`.
