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
  - state/lessons/
  - docs/plans/2026-05-18-plan-coverage-checker.md
  - docs/plans/2026-07-09-plan-full-coverage-and-deferred-harvest.md
---

# plan-coverage-checker Pre-Review Doctrine

<!-- distilled: run 2026-07-19-synth; sources: 2026-05-24-acceptance-oracle-with-teeth.md, 2026-05-27-cqcs-cluster2-review-pipeline-calibration.md -->

## What is plan-coverage-checker?

plan-coverage-checker is belt-and-suspenders against the EM's own pull toward small, unambitious scoping — a Sonnet-tier agent that verifies a plan artifact's internal consistency before the artifact reaches an Opus reviewer. It answers questions none of the other pre-flights answer: **does the plan's own fix slate cover the plan's own audit list, with no appetite-based hedges and no substrate citations that drift from disk — and, on the `## Tasks` task-spine, has the PM actually ratified every scope cut, or is an EM preference wearing a `deferred:` flag?**

The agent runs four mechanical lenses — coverage (slate-vs-oracle cross-reference), hedge detection (appetite-based deferral patterns), task-spine deferral-ratification and malformed-row detection, and substrate drift (in-repo path/symbol/constant verification) — and writes a sidecar at the plan-derivable `state/plan-sidecars/<plan-stem>.plan-coverage-check.md` home (D0) with six finding buckets: Missed, Ambiguous, Weak-OOS, Hedges, Unratified-Deferrals-and-Malformed-Rows, and Substrate-drift.

The output is REPORT-ONLY. The agent makes no decisions, applies no fixes, and auto-blocks nothing; it surfaces un-considered work and un-ratified scope cuts for the EM (and, where PM ratification is the open question, the PM) to disposition before the named Opus reviewer is dispatched. This is the agent's un-skippable secret sauce: it exists precisely for the plans an EM feels most confident about, because that confidence is exactly the state in which coverage gaps and quiet re-scoping go unnoticed.

## Empirical motivation — the 36/9/4 case

A different EM session produced a "comprehensive fix slate" plan against an audited list of issues. Post-hoc sanity-check by a Sonnet cross-referencer found:

- **36 items** present in the audit but absent from the fix slate (coverage gap)
- **9 items** asserted against substrate that had drifted on disk (paths/symbols/constants failed to match)
- **4 items** hedged with "follow-up" / "future work" framing where doctrine requires OOS to be architectural

The critical observation: the EM was confident the plan was comprehensive. The 36 misses were not the result of a distracted EM — they were the result of a structural gap in the pipeline. No agent upstream of the Opus reviewer checked whether the slate covered the oracle. The Opus reviewer can catch coverage gaps, but at >10× the token cost of a Sonnet cross-ref, and reviewers tend to assess the slate as-given rather than derive what is missing from a separate audit table.

The 36/9/4 split is the standing empirical motivation for this agent and for the design decision to make its trigger skill-internal (see § Trigger heuristic below).

## The four lenses

The agent runs four checks in sequence. Each produces findings in a distinct bucket. The final verdict is the worst case across all four.

### Lens 1 — Coverage (oracle-vs-slate cross-reference)

Parses the plan for an **oracle table** (audit/findings/issues list) and a **slate table** (fix/chunks/tasks list), then cross-references every oracle item against the slate using signal-confirmed matching (shared file path, shared symbol, shared distinctive noun phrase — in that priority order).

Three classification buckets: **MATCHED** (signal confirmed), **AMBIGUOUS** (signal-partial — stopword-only overlap or uncited consolidation), **MISSED** (no signal, no OOS justification). AMBIGUOUS items are informational only and do NOT gate the INCOMPLETE verdict.

M:N semantics apply: a slate chunk that consolidates multiple oracle items must enumerate them explicitly. Oracle members not explicitly cited in a consolidating chunk → AMBIGUOUS (not MISSED).

**Highest-priority oracle — the ratified problem-set (external).** Before the in-plan heuristics, the agent checks the plan frontmatter for a `problem_set:` key. A `problem_set: <path>` pointing at a `status: ratified` file (or `problem_set: inline (§ ...)` validated by a `> Ratified by PM <name> <date>` blockquote) becomes the **primary** oracle, with any in-plan audit table demoted to secondary. This is the only oracle source for feature/PRD-shaped plans, which otherwise carry no audit table. Because the problem-set is authored *before* and *outside* the plan (via `coordinator:shape`), it is a genuine external check — the plan cannot grade its own homework. See `docs/wiki/writing-plans.md § Problem-set as external oracle`.

When no oracle is found — no ratified problem-set AND no in-plan audit table — the agent emits `SCOPE-MISMATCH` and stops. This is the correct silent skip for greenfield design plans. **For `feature` / `architecture` / `spike` plans lacking a ratified problem-set, the agent first writes an advisory nudge line** (*"no PM-ratified problem-set found; EM, confirm problem understanding with the PM before dispatch."*) into the SCOPE-MISMATCH sidecar — an advisory line, not a verdict change, and silent for `production-patch`/audit plans.

**Known false-positive: `## Acceptance Criteria` misdetected as an oracle table.** Phase 1's oracle-detection heuristic #3 (an "ID column" signal — a leading column of short row-identifiers) collides with the shape of a well-formed `## Acceptance Criteria` table (AC-1, AC-2, … rows), which is a *slate-verification* artifact, not an *audit-oracle* artifact. Phase 1 excludes `## Acceptance Criteria` from oracle-table detection by construction — the heuristic never fires on that heading. This is why the trigger table above lists "has `## Acceptance Criteria` but no oracle" as its own `SCOPE-MISMATCH` row rather than a MATCHED/MISSED cross-reference against itself.
<!-- src: plan11-018 -->

For full matching rubric, bucket definitions, and OOS sub-classification (OOS-ARCHITECTURAL vs. OOS-WEAK), see the agent body: `agents/plan-coverage-checker.md § Phase 2`.

### Lens 2 — Hedge / defer detection

Greps the plan body for appetite-based deferral language (follow-up, future work, TBD, if time permits, defer to, etc.) and classifies each hit using a two-stage classifier.

**Stage 1 — section-context (runs first, always):** If the token sits under a `Considered Alternatives / Rejected / Risks / Out of Scope` heading, or inside a markdown blockquote, classify as FALSE-POSITIVE immediately — Stage 2 does NOT run.

**Stage 2 — prose-context (only if Stage 1 did NOT fire):** Reads ±5 lines of context and classifies as HEDGE, OOS-JUSTIFIED, or FALSE-POSITIVE.

Only HEDGE findings produce sidecar entries. Doctrine basis: `coordinator/docs/wiki/implementation-standards-by-domain.md` — "OOS framing must be architectural, not appetite-based."

For the complete token list, stage-1 heading regex, and stage-2 classification rules, see the agent body: `agents/plan-coverage-checker.md § Phase 3`.

### Lens 2b — Task-spine closure-approval and malformed-row detection

Parses the plan's `## Tasks` task-spine — the pinned, parser-locate `yaml plan-tasks` fenced block that all downstream tooling (this checker, the harvest tool, `coordinator-doc-new`) binds to. See `agents/plan-coverage-checker.md § Phase 3.5` and the schema SSOT at `docs/plans/2026-07-09-plan-full-coverage-and-deferred-harvest.md § The task-spine schema (Item A — pinned interface)`.

**Report-only, not the enforcement surface for closure authorization** — that lives in the claude-klabauter frontmatter-schema layer and its write guards. This lens buys earlier visibility: the harvest tool WARN-AND-SKIPs a malformed row, so this checker is the first place a malformed row or a fabricated approval surfaces before it ships silently. It makes a bad approval *falsifiable*, not *impossible*.

A plan is GOVERNED iff its frontmatter carries a `grouping_approvals` key — bare presence is the whole discriminator, checked before anything else in this lens. Each spine row's grouping (do / defer / ruled_out) is derived from its `disposition` (open+coded / spun_off+backlogged / wont_do respectively) and is never stored on the row itself; `do` rows are live or shipped work and are never gated by this lens.

- **On a GOVERNED plan:** for any row whose grouping is closed (defer or ruled_out), check whether that grouping's `grouping_approvals` block reads `status: approved`, carries a non-empty `digest`, and an on-topic non-empty `pm_utterance`. **This lens cannot verify digest correctness** — only the field's presence and shape; recomputing against current row membership is the claude-klabauter write-time guard's job, not this checker's. A malformed or absent block on a grouping with closed rows is its own finding — never a fallback to the legacy per-row bool below.
- **On a LEGACY plan** (no `grouping_approvals` key at all): the pre-existing bare-bool lens applies unchanged — see checks 1 and 2 below.

1. **Malformed rows** (applies on both governed and legacy plans). Any row that fails to parse (bad YAML) or is missing a required field (`id`, `title`, `change_kind`, `surface`; on a LEGACY plan only, `pm_approved` as a *key* — presence only, any boolean value — when `deferred: true`) is flagged — quoted verbatim, with the specific missing field named. The *value* being literal `true` is checked separately, below. Enum membership (`change_kind`, `disposition`, `queue_scope`) is NOT this lens's job: it is enforced at write time by the frontmatter-schema write guard, which validates each spine row against `coordinator/schemas/plan-tasks.schema.json`.
2. **Unratified deferrals — legacy plans only.** On a plan with no `grouping_approvals` block, any row with `deferred: true` but `pm_approved` absent, `false`, or non-`true` gets: **"deferral pending PM ratification — scope is a PM decision, EM preference is not a scope decision."** Fires regardless of how reasonable the deferral looks — the check is for the ratification signal, not the deferral's merit. On a GOVERNED plan this bool carries no authorization weight; the grouping-approval check above gates closure there.

3. **Missing or vacuous `case_against` on a candidate scope cut** (GOVERNED plans). A scope cut must reach the PM as an argument, not a conclusion — the row carries the case FOR in `disposition_detail` and the case AGAINST in `case_against` (`docs/wiki/writing-plans.md` § Both-Sides Deferral Argument). Any **candidate scope-cut row** (defined below) whose `case_against` is absent, empty, or vacuous gets a finding, quoting the field.

   **`case_against` is authored at SLATE time, not at closure time.** It is written when the row is first drafted `open` carrying its both-sides argument, and merely *survives* the later flip to `backlogged`/`wont_do`. A checker that expected it to appear at closure would be asking for it after the decision it exists to inform.

   **Specificity sub-check.** Phrase as a question to the EM, never an assertion: does `case_against` name a concrete consequence tied to this row's own surface, or is it a restated negation of `disposition_detail`? Anti-strawman is not fully mechanizable — this narrows the gap, it does not close it (honest-limit clause, `writing-plans.md`).

4. **The LEGACY equivalent.** On a plan with no `grouping_approvals` key, the same lens reaches legacy `deferred: true` rows through the **existing D8 legacy-equivalence rule** (`deferred: true` reads as `disposition: backlogged`) — check 3 applies to them unchanged. This is read-tolerance for the pre-existing corpus only. **Do not treat it as a new authoring surface**: the legacy shape gets no `case_against` authoring path of its own, because the fleet is retiring that vocabulary, not extending it.

**The candidate scope-cut row — the trigger definition both new checks share.** A row is a *candidate* scope cut if ANY of:

- its `disposition` is `backlogged` or `wont_do` (an already-closed cut); **or**
- its `disposition` is `open` **and** it carries a non-empty `case_against` (a cut drafted and argued, awaiting the PM's ruling); **or**
- it is named in the plan's own deferral-slate section.

The `open`-plus-`case_against` limb is the load-bearing one. Scoping these lenses to *closed* rows alone would mean they never fire before ratification — every candidate cut is still `open` at the review Exit gate, because the write-time guard refuses to close a row until the PM has ruled. The lens would then run only *after* the decision it exists to inform, which is no lens at all. `spun_off` is never a candidate *for this lens*: a spun-off row's work continues in a named successor, so there is no cut to argue against. It is not ungoverned — on a governed plan its assent is recorded in the `spun_off` grouping of the plan's `grouping_approvals` block, checked by `check_plan_tasks_grouping_approval`. Assent and argument are scoped differently on purpose: approving a move and arguing against a drop are different asks.

**Plan-level lens — deferral count.** A plan carrying **more than 4** candidate scope-cut rows gets **one** finding, phrased as a **prompt, not a verdict**: *"these N cuts span M distinct surfaces — do they form one shape?"* **Not punitive** — a long deferral slate is a scope-misalignment signal, not a failure; one finding per plan, never one per row. Threshold of 4 is provisional (`writing-plans.md`).

**FAIL-LOUD, not skip-quiet, when the spine itself is broken.** A `## Tasks` heading with zero or more than one `yaml plan-tasks` block is the parser-locate rule's defined error case — the checker cannot enforce without exactly one spine. Emits `DEGRADED`, stops this lens only (others still run). Differs from "no `## Tasks` heading at all," which is legitimate no-signal.

`## Anti-scope` items are never spine rows and are out of scope for this lens by construction.

### Lens 3 — In-repo substrate drift

Extracts all in-repo path citations and `file:line` / `file:symbol` references from the plan body, then verifies each against the current disk state using `ls`, `Read`, and `Grep`.

**Line-drift tolerance is mandatory:** same file, same symbol, line number shifted = FALSE-POSITIVE. The agent only emits a finding when the symbol/identifier is absent from the file, or the file itself is missing. This tolerates the legitimate line drift produced by concurrent-EM workstream branches. The tolerance window is **±50 lines** (widened from ±10 in the initial implementation) — neighbor sections inserted between plan-write and check-time can push a cited symbol further than ±10 lines without invalidating the citation, so the narrow window produced false substrate-drift findings on sound plans. **Anchor-heading citations are drift-immune:** when a plan cites by `§ Heading` or a distinctive heading line rather than a bare line number, the agent matches on the heading's presence on disk and ignores the line number entirely — prefer anchor-heading citations in plans for this reason.

Scope boundary: Lens 3 checks in-repo paths and symbols only. External API signatures are docs-checker's job.

For extraction heuristics, verification procedure, and scope boundary, see the agent body: `agents/plan-coverage-checker.md § Phase 4`.

### Lens 4 — Anti-scope vehicle-naming

Reads `## Anti-scope` as prose (its items are never spine rows — Lens 2b, above) — the one lens
here inspecting prose, not a table. An item naming an execution mechanism ("no fan-out",
"EM-sequenced") rather than a what-changes boundary is a finding citing tripwire
`A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`, carrying its own correction (depends_on edge, or a
named carve-out per `workflow-orchestration.md` § What qualifies as a carve-out) — never applied.

### Lens 5 — Hook registration liveness

Checks each cited `hooks/scripts/*.py` path against `hooks.json`'s registered set (there is no
literal `registered` key — it's `x-effective-delivery.carriers.*.guards[].script`, plus the
top-level `hooks.*[].hooks[].args` for directly-registered scripts), not disk presence alone.
Both storage shapes drop the plan-citation's leading `hooks/` segment, so the checker normalizes
before comparing. Absent → finding, citing `hook-registration-roster.json`'s `deregistered`
reason where one exists. Motivated by a real incident: two pre-flights confirmed hook files
existed without checking `hooks.json`, on a corpus that had just deregistered nine of them.

## Trigger heuristic — skill-internal, not EM-judged

**The EM does not decide whether the agent runs.** The skill (`skills/review/SKILL.md` Phase 2.7d) runs the agent unconditionally on any plan with an oracle table OR a `## Acceptance Criteria` section. There is no EM opt-out in v1.

| Plan shape | plan-coverage-checker? |
|---|---|
| Plan has a `problem_set:` frontmatter key → ratified external file (or inline ratified block) | **Run** — the problem-set is the primary oracle (highest priority). |
| Plan contains an audit/findings/issues table (any size) | **Run.** |
| Plan contains a `## Acceptance Criteria` section but NO oracle | `SCOPE-MISMATCH` — no oracle to check. |
| Plan is greenfield design with no found-facts oracle | Skip silently — agent emits `SCOPE-MISMATCH` (+ advisory nudge for feature/architecture/spike). |
| Plan is single-file mechanical fix (no design content) | Skip silently. |
| Plan is doc redesign / wiki rewrite | Skip silently. |
| Plan has a `## Tasks` heading with exactly one `yaml plan-tasks` block | **Run Lens 2b** (task-spine ratification/malformed-row check) alongside any other applicable lenses. |
| Plan has a `## Tasks` heading with zero or >1 `yaml plan-tasks` blocks | FAIL-LOUD for Lens 2b — verdict `DEGRADED`, "no spine to enforce." |
| Plan has no `## Tasks` heading at all | Lens 2b does not run — legitimate no-signal, not an error. |

**Why no EM opt-out?** The 36/9/4 incident established that EM confidence is exactly the failure mode this agent exists to prevent. An EM who believes their plan is comprehensive is in the highest-risk state for a coverage gap — not the lowest. Making the trigger EM-judged would re-instantiate the failure mode every time the EM felt confident.

**Revisit criterion (pre-committed, not discretionary):** After 10 plan dispatches through this agent, the EM tallies findings. If the ratio of AMBIGUOUS-or-false-MISSED to true-MISSED is ≥2:1 (mostly noise, not signal), the next iteration adds a `skip_plan_coverage: <architectural-reason>` frontmatter skip-class. This pre-commitment prevents "when to add the opt-out" from becoming the same EM-confidence call the agent exists to prevent.

## Sidecar format

Sidecar path: the plan-derivable `state/plan-sidecars/<plan-stem>.plan-coverage-check.md` home (D0).

Six finding sections:
- **Missed audit items** — oracle items with no slate entry and no architectural OOS, with the three valid resolution options stated per item (add-to-slate / architectural-OOS / oracle-was-wrong)
- **Ambiguous audit items** — signal-partial matches, informational only, do not gate INCOMPLETE
- **Weak OOS / hedges** — appetite-based deferrals with doctrine citation
- **Task-spine: unratified closures and malformed rows** — on a GOVERNED plan, closed (defer/ruled_out) rows whose grouping lacks an `approved` block with a current membership digest and an on-topic `pm_utterance`; on a LEGACY plan, `deferred:true` rows lacking `pm_approved:true`; plus, on either plan shape, rows that fail to parse or are missing a required field
- **Substrate drift** — in-repo path/symbol/constant mismatches
- **Deferral arguments** — candidate scope-cut rows whose `case_against` is absent, empty, or vacuous (one per row, quoting the field), plus at most one plan-level prompt when the plan carries more than 4 candidate cuts. See Lens 2b checks 3–4.

Five verdicts:
- **COMPLETE** — zero MISSED, zero weak-OOS, zero substrate-drift, zero unratified-deferrals, zero malformed-rows, zero deferral-argument findings. AMBIGUOUS does not gate.
- **INCOMPLETE** — one or more gating findings. EM folds before reviewer dispatch. When the verdict is INCOMPLETE, the sidecar's verdict line gains a per-lens sub-label: `INCOMPLETE — Mechanical: N, Judgment: M` where Mechanical = Substrate-drift + Malformed-rows bucket counts (Lens 3 + Lens 2b malformed half — typically auto-foldable) and Judgment = Missed + Weak-OOS + Hedges + Unratified-deferrals + Deferral-arguments bucket counts (Lens 1 + Lens 2 + Lens 2b ratification half + Lens 2b checks 3–4 — needs EM/PM decision; a missing `case_against` is Judgment, never Mechanical, because writing one is an argument the EM has to actually make). The sub-label is a cost estimate: Mechanical findings are usually a rewrite away; Judgment findings require an EM/PM decision (add-to-slate / architectural-OOS / oracle-was-wrong / promote-OOS-to-slate / PM ratifies / EM un-defers). Verdict enum values are unchanged — back-compat preserved.
- **BLOCKED-SURFACE-TO-PM** — ≥20% of oracle items MISSED (MISSED count alone, not MISSED+AMBIGUOUS), OR ≥3 substrate-drift findings.
- **SCOPE-MISMATCH** — no oracle table found. Agent writes a sidecar carrying the SCOPE-MISMATCH verdict; for feature/architecture/spike plans lacking a ratified problem-set, the sidecar also carries the advisory nudge. Review proceeds normally — no lens ran. Orthogonal to the task-spine lens, which has its own no-signal/DEGRADED handling.
- **DEGRADED** — agent ran with incomplete coverage, OR the `## Tasks` heading is present but the spine is missing/ambiguous (zero or >1 `yaml plan-tasks` blocks — FAIL-LOUD case). No signal; review proceeds as if lens did not run.

Prior sidecars are never deleted. On re-run, the agent renames the existing sidecar to `state/plan-sidecars/<plan-stem>.plan-coverage-check.<UTC-mtime>.md` before writing the new one. This preserves the re-run history for feedback-loop analysis — `state/plan-sidecars/` is an unreaped-by-design archive class (Z1) for exactly this reason.

## When NOT to run

The trigger heuristic is skill-internal, so "when not to run" is encoded in the skip logic rather than EM judgment. The agent silently skips plans without an oracle table. Concretely, this covers:

- **Greenfield design plans** — no audit table, no found-facts list, just a proposed design. The agent emits `SCOPE-MISMATCH` and writes a sidecar carrying that verdict (and, for `feature` / `architecture` / `spike` plans lacking a ratified problem-set, the advisory problem-set nudge). The verdict still signals "no coverage lens ran"; the sidecar exists so the advisory nudge has a surface to land on.
- **Single-file mechanical fixes** — a plan that says "edit line 47 of file X to fix Y" has no oracle/slate structure worth parsing. Skip.
- **Doc redesigns and wiki rewrites** — no fix-slate shape. Skip.

If you are unsure whether a plan has an oracle, dispatch the agent — a `SCOPE-MISMATCH` is cheap and does not block the pipeline.

## Distinction from sibling pre-flights

The four pre-flights answer orthogonal questions:

| Pre-flight | Question | Corpus | Authority |
|---|---|---|---|
| **plan-coverage-checker** (this) | Does the slate cover the oracle? Are deferrals architectural (and, on the task-spine, PM-ratified)? Is the task-spine well-formed? Do in-repo citations match disk? | The plan itself + in-repo disk | REPORT-ONLY; fold before reviewer |
| **prior-art-checker** | Have we already established something relevant about this? | Project wikis, global wikis, lessons, improvement queue | REPORT-ONLY; Conflicts survive to reviewer (five direction options) |
| **docs-checker** | Are external API claims factually correct? | Context7, LSP, project-RAG, cppreference | AUTO-FIX allowlist for tradeoff-free corrections |
| **external-pattern-checker** | Are there public-domain patterns we should know about? | Web (public documentation, RFCs, community patterns) | REPORT-ONLY; informational |

**Key divergence from prior-art-checker fold posture.** prior-art-checker WARN sidecars survive to the named Opus reviewer — the reviewer's judgment shapes direction-of-correction on Conflicts (five valid directions, some requiring product input). plan-coverage-checker INCOMPLETE findings fold BEFORE the reviewer, because coverage gaps have only three valid EM-mechanical resolutions (add-to-slate / architectural-OOS / oracle-was-wrong) — none of these require reviewer judgment. The mechanical nature of a missed audit item is what makes pre-fold the correct posture; passing it through the reviewer wastes Opus tokens on a question the EM can resolve mechanically.

## Feedback loop on plan quality

When the same oracle shape produces repeated MISSED findings across multiple plans, that is a feedback signal pointing upstream — the **plan template**, not just the individual plan, has a gap.

If a recurring oracle type (e.g., "all plans that audit CLI flags consistently miss deprecation entries in the flag registry") produces MISSED findings in ≥3 plans, surface to the EM as a candidate for plan-template addition. The plan-coverage-checker thus becomes a quality loop on plan-authoring patterns, not just individual plan correctness.

<!-- Review: code-reviewer — claiming a specific step number (Step 4) was false precision; the activity isn't a named sub-step yet. -->
Operational hook: during `/workweek-complete`, as part of the weekly retrospective sweep (informal — not a numbered sub-step yet; promote to a named sub-step once the cadence proves itself), the EM scans recent `state/plan-sidecars/*.plan-coverage-check*.md` sidecars for recurring MISSED patterns across plans. Two plans with MISSED on the same oracle shape within a quarter means the plan template (or the authoring skill) has a structural gap worth addressing. This is judgment-based, not automated — but the responsibility lives in the weekly cadence so it does not drift.

## Distribution

The reviewer-side consumption block (`snippets/plan-coverage-check-consumption.md`) is synced via `verify-snippet-sync plan-coverage-check-consumption --fix` to all Opus reviewer prompts that may receive plans with oracle tables:

- `agents/staff-eng.md` (the Staff Engineer)
- `agents/staff-data-sci.md` (the Data Science Reviewer)
- `agents/senior-front-end.md` (the Front-End Reviewer)
- `agents/eng-director.md` (the Director of Engineering — reviews plans at DoE altitude)
- example-game-repo sibling repo `game-dev/agents/staff-game-dev.md` (the Game Dev Reviewer — example-game-repo-resolved via machine-local registry key `repos.example_game_workbench_repo`; skipped when example-game-repo repo is absent locally; `game-dev` retired from OSS coordinator-claude distribution)

**Excluded intentionally:** `agents/code-reviewer.md` (Sonnet code-shaped review, not plan-shaped) and `agents/staff-ux.md` (the UX Reviewer — UX flow review rarely has audit/slate structure). These exclusions are the same as for the sibling consumption snippets.

The sync verifier is auto-discovered by `/update-docs` Phase 11b. The tripwire entry lives in `coordinator/docs/wiki/coordinator-tripwires/`.

