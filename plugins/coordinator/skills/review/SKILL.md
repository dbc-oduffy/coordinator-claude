---
name: review
description: Use when a plan / design doc / RFC is ready for review or plan-review findings have landed.
version: 1.0.0
spec_backlink: docs/plans/2026-05-06-review-super-skill.md
---

# coordinator:review

<!-- Purpose: Decision-tree router for plan-review workflows. Covers outgoing (pre-flight + dispatch) and incoming (triage + integrate) directions. Does NOT cover code / diff / PR review — that is coordinator:review-code (TBD). -->

**Trigger:** EM has a plan / design doc / RFC ready for review (outgoing), OR a plan-review's findings have landed and need processing (incoming).

**When NOT to use:** Code / diff / PR review → `coordinator:review-code` (TBD). Frozen weekly diff at `/workweek-complete` Step 7 → `coordinator:parallel-code-review`. Mid-drafting (plan not finished) → keep writing. Stuck pattern → see `docs/wiki/stuck-detection.md`. Pure mechanical citation check with no Opus → run `docs-checker` directly.

---

## Branch A — Outgoing

_Condition: a plan / design doc exists; no reviewer has been invoked yet on this iteration._

### A.1 — Pre-flight workers (run BEFORE the Opus reviewer)

Both checks fire independently. A plan can be non-trivial AND cite C++/UE APIs — in that case both workers run.

**Check 1 — Triviality (prior-art-checker)**

- _Plan covers non-trivial work?_ (design docs, RFCs, architectural plans; anything beyond a single-file fix)
  → Dispatch `prior-art-checker` with the plan path. Read sidecar at `<plan-path>.prior-art-check.md`. Act on buckets: **Conflicts** → surface to PM with wiki quote before continuing; **Compatible-but-relevant** → fold reference into plan's "Considered alternatives"; **Silent** → no action.
  _See CLAUDE.md § Adding a Convention to the Coordinator System (Prior-art-checker tripwire)._
- _Plan is genuinely trivial?_ (one-line doc fix, typo, link repoint, no design content)
  → Skip `prior-art-checker`.

**Check 2 — Cited external APIs (docs-checker)** _(runs independently of Check 1)_

| API surface cited in plan | docs-checker? |
|---|---|
| C++ or Unreal Engine APIs | **Mandatory** — run `docs-checker` regardless of EM judgment. |
| Other external library APIs | EM judgment — run if cost is justified; skip silently if not. |
| Pure prose / in-repo-only references / no cited external APIs | Skip `docs-checker`. |

_See `docs/wiki/docs-checker-pre-review.md` for full rows and sidecar consumption pattern._

**Check 2b — Acceptance-criteria shape (offer, not block)** _(runs independently; offer-shaped)_

<!-- spec-backlink: docs/plans/2026-05-24-acceptance-oracle-with-teeth.md §2.5 — review-skill offer -->

When the reviewed plan's `## Acceptance Criteria` section is in **old prose-checkbox form** (lines like `- [ ] prose description`) rather than the bindable-table form (`ID | Criterion | Test | Binding-Class | Status`), NOTICE this and offer the template — do NOT block.

Offer: _"This plan's acceptance criteria are in prose-checkbox form. If this plan warrants review, it warrants verifiable exit criteria — the bindable-table form makes acceptance tests mechanically enforceable at merge time. Template and two-altitude flow: `docs/wiki/writing-plans.md` § Acceptance Oracle. Pre-review `Test` cells stay `pending realization`; they're realized as named failing tests after review. No action needed now — this is just a heads-up before the reviewer reads the criteria as a design lens."_

The reviewer's **substantive design-lens job is unchanged** — evaluating whether the criteria are testable-shaped, complete, and correctly scoped is always the reviewer's primary role here. This is a mechanical shape nudge, not a blocker. If the plan already uses the bindable-table form, skip this check silently.

**Check 3 — Plan internal completeness (plan-coverage-checker)** _(runs independently of Checks 1 and 2)_

| Plan shape | plan-coverage-checker? |
|---|---|
| Plan contains an audit/findings/issues table (any size) | **Run.** |
| Plan is greenfield design with no found-facts oracle | Skip — agent emits `SCOPE-MISMATCH`. |
| Plan is single-file mechanical fix | Skip. |
| Plan is doc redesign / wiki rewrite | Skip. |

_See `docs/wiki/plan-coverage-checker.md` for trigger rationale and lens details. Skip is silent — no flag, no justification._

### A.2 — Reviewer selection and dispatch

**Routing table assembly:** Read the base routing table from `coordinator/routing.md`, scan all enabled plugins for root-level `routing.md` fragments, merge into a composite routing table. Match the artifact's signals against the composite table to identify Reviewer 1 (domain specialist) and Reviewer 2 (generalist, if needed).

**Composite routing table (reference — assembled at dispatch time from fragment discovery):**

| Signal | Reviewer 1 (Domain) | Reviewer 2 (Generalist) | Effort |
|--------|---------------------|------------------------|--------|
| Game dev / Unreal / DroneSim | the Game Dev Reviewer | the Staff Engineer | Medium → Medium |
| Architectural change, new subsystem | the Staff Engineer | (backstop: the Director of Engineering) | High |
| Cross-team / cross-repo seam (consumer ↔ producer, plugin ↔ host) | the Director of Engineering (standalone — DoE altitude) | (none) | High |
| Generic-substrate / consumer-leak risk on producer-side surface | the Director of Engineering (standalone — DoE altitude) | (none) | High |
| Front-end, CSS, UI components | the Front-End Reviewer | (backstop: the UX Reviewer) | Medium |
| Front-end + architecture | the Front-End Reviewer | the Staff Engineer | Medium → High |
| ML/AI pipeline, model serving, RAG | the Data Science Reviewer | the Staff Engineer | High → High |
| UX flow, user-facing feature | the UX Reviewer | (backstop: the Staff Engineer) | Low → Medium |
| Cross-cutting (many files, new pattern) | the Staff Engineer | (backstop: the Director of Engineering) | High |
| Major DroneSim feature / new game mode | the Game Dev Reviewer | the Staff Engineer | High → High |
| Other / unmatched | the Staff Engineer | (none) | Medium |

**the Director of Engineering standalone vs. The Director of Engineering backstop.** When the signal matches a cross-team or consumer-leak row above, dispatch the Director of Engineering **standalone** with `mode: "standalone"` in the prompt — do NOT run the Staff Engineer first. Standalone the Director of Engineering is a peer of the Staff Engineer in technical rigor with the additional cross-team authority the Staff Engineer's EM altitude would hedge on. The "(backstop: the Director of Engineering)" entries above are the chained-after-the Staff Engineer usage for High-effort architectural reviews; that mode is still in play but does not exhaust the Director of Engineering's role.

If `--reviewers "name1,name2"` was provided, skip auto-detection. Use the explicit list — first name is Reviewer 1, second (if any) is Reviewer 2. Report: "PM-directed review: [name1] then [name2]."

**Matching review tier to plan complexity:**

Match tier to complexity, not importance. Routing every "important" plan to a staff session burns budget without finding more bugs. The heuristic: would a second reviewer likely **contradict** the first, or just add diminishing-return notes? If contradiction is unlikely, one reviewer is enough.

| Situation | Correct tier |
|---|---|
| Single-domain plan (new feature, doc redesign, refactor) | One Opus-persona reviewer (auto-detects domain from routing table above) |
| Cross-domain plan (e.g., UE + data pipeline, front-end + arch) | Two sequential Opus-persona reviewers: `--reviewers "<domain>,patrik"` |
| Contested architectural choice with ≥2 valid approaches AND PM authorized | `/staff-session` review-mode |
| "This is important, I want it done right" | One Opus-persona reviewer (auto-detects domain) |
| "the Staff Engineer feels heavy for this; route to code-reviewer instead" | **Not a valid row.** `code-reviewer` is the Sonnet diff reviewer, not a plan reviewer. The fork is named Opus persona OR skip review (implement and let `code-reviewer` catch issues on the diff at `/session-end`). Sonnet-on-plan-body is not on the menu. _See `skills/plan/SKILL.md` § Exit ¶ Reviewer altitude is binary._ |

- _Plan is genuinely trivial?_ (one-line doc fix, typo, link repoint)
  → No review needed; commit and proceed.
- _PM has explicitly waived review on a non-trivial plan?_ ("ship it", "skip review", "straight to execution")
  → Exit; this skill does not run. Log the waiver in the plan frontmatter (`review: skipped per PM direction YYYY-MM-DD`).

_See CLAUDE.md § Challenging the PM — `/staff-session` is PM-gated; ask first._

**Pipeline phases (docs-checker, (prior-art-checker ∥ plan-coverage-checker), external-pattern-checker, integrator, backstop, report) live in `docs/wiki/reviewer-pipeline.md`. Walk those phases inline — they are not optional.** Walk Phase 2.5 → 2.7 → (2.7b ∥ 2.7d) → 2.7c → 2.8, then dispatch, then Phase 3.5 → 3.7 → 4 → 5.
<!-- Review: code-reviewer — listed phases as a flat sequence, obscuring that prior-art-checker and plan-coverage-checker run in parallel; updated to (prior-art-checker ∥ plan-coverage-checker) to match the runtime shape. -->

### A.3 — Sequencing (HARD RULE for plan reviews)

- Default → sequential. Integrate Reviewer 1's findings via `coordinator:review-integrator` BEFORE dispatching Reviewer 2.
- The merge-gate parallel-review carve-out does NOT apply to plan reviews — plans are never parallelized.
- _See CLAUDE.md § Review Sequencing._

---

## Branch B — Incoming

_Condition: a reviewer has returned output on a plan. EM is deciding what to do with each finding._

**Forbidden triage outcomes (never valid):** defer-to-later, capture-for-backlog, time-estimate-as-rationale. If any of these would be the disposition, surface to PM — the PM decides whether to defer, not the EM.
_See CLAUDE.md § Core Principles ('Implement and iterate over deliberate and defer')._

Walk each finding against the triage table below — it lands in exactly one row:

- _Tradeoff-free correctness fix?_ (factual error, broken citation, wrong API name in stub, missing cross-reference, internally inconsistent rule)
  → Dispatch `coordinator:review-integrator` with `mode: "acceptEdits"` and findings. EM spot-checks the diff.
  _See CLAUDE.md § Review Sequencing (after-review integrator rule) and § Reviewer findings — apply, don't ratify._

- _Plan-shape tradeoff?_ (architectural direction, scope question, sequencing call)
  → Surface to PM with finding + reasoning. Wait for direction.
  Plan reviews skew heavily toward this row — most plan findings are about *what to build*, not *how it's coded*.
  - _(i) YAGNI / scope-trim argument from reviewer?_ → **Always escalation, never auto-trim.** Even framed as tradeoff-free, YAGNI is a product decision. Surface to PM. _See CLAUDE.md § Challenging the PM._
  - _(ii) Refactor-over-patch signal?_ → Refactor is the default when AI is the implementer. Surface to PM with refactor proposal. _See CLAUDE.md § Core Principles ('Do the right thing, not the easy thing')._
  - _(iii) Build-vs-defer call?_ → Always PM. Never EM-unilateral. _See CLAUDE.md § Challenging the PM ¶ Ask the PM when._

- _Multiple findings collectively suggest the plan needs a structural refactor (not just patches)?_
  → Do NOT integrate piecemeal. Surface to PM with a refactor proposal — the aggregate signal is the finding.
  _See CLAUDE.md § Core Principles ('Refactor over patch') and § Convergence as Confidence._

- _Premise / hypothesis question?_ (reviewer challenges the plan's framing or motivating hypothesis)
  → Read the cited prior art (wiki, lessons, archived spec). Confirm or revise premise.
  _See `docs/wiki/reviewer-premise-challenge.md`._

- _Multiple reviewers converged on the same issue from different entry points?_
  → High-confidence; apply via integrator without per-finding verification.
  _See CLAUDE.md § Convergence as Confidence._

- _Worker Dispatch Recommendations block present in reviewer output?_
  → Dispatch each named worker. For plan reviews: `doc-link-checker` (most relevant); `dep-cve-auditor` (if plan introduces a dependency). Feed worker output back into EM context.
  `test-evidence-parser` and `security-audit-worker` do NOT fire for plan reviews — they require runtime artifacts. If a reviewer names them on a plan, treat as miscalibration and surface to PM.
  _See `docs/wiki/reviewer-routed-workers.md` and CLAUDE.md § Reviewer-Routed Workers._

- _Default / unmatched?_
  → Apply via integrator. Default is to integrate, not to ratify.
  _See `docs/wiki/receiving-code-review.md` (triage tables, push-back patterns, performative-agreement guard) and CLAUDE.md § Reviewer findings — apply, don't ratify._

---

## Prior-Art Mutability and Reviewer Elevation

**Prior-art mutability as first-class deliverable.** When the PM authorizes prior-art mutation as an explicit deliverable of the review (i.e., the plan is intended to *update* settled doctrine, not simply comply with it), the DoE-elevated reviewer (typically the Director of Engineering) MAY override the prior-art-checker sidecar's `update-plan` / `update-prior-art` recommendation with an explicit cross-reference to the PM authorization in their findings. Default mode is still "plan adapts to prior art"; prior-art mutation is opt-in and requires PM sign-off stated in the dispatch brief.

**Reviewer elevation must be stated verbatim in the dispatch brief.** Elevating a reviewer past their charter (e.g., the Director of Engineering from ambition-backstop to DoE-with-mutation-authority) without verbatim brief language reverts at integrator-apply — the reviewer's prompt-defined charter is the default boundary. If the PM authorizes elevation, the EM must include the exact authorization phrase (e.g., "PM-authorized to override prior-art-checker on this run") in the dispatch brief to the reviewer; otherwise the integrator will treat the override as out-of-charter and escalate as ASK.

---

## Cross-reference exit

After Branch B completes for a multi-reviewer review and Reviewer 1 is integrated, return to **A.2** to dispatch Reviewer 2. This skill is re-entrant — each pass walks one direction.

When all reviewer integration is complete and the plan is ready for execution, the EM owns the **dispatch-gate graph** before the first executor dispatch: enumerate touched files per task, mark file-overlap / output-consumption / contract-change gates (and only those — narrative causality is not a gate), size per-executor scope to ~15-25 min, and author parallel-wave prompts with explicit peer-scope prohibition. Procedure: `coordinator:execute-plan` Phase 1.5. Taxonomy: `docs/wiki/dispatching-parallel-agents.md` § Dispatch-Gate Taxonomy and § Peer-Scope Prohibition in Parallel-Wave Prompts.
