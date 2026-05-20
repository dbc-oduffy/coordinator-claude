---
name: reviewer-pipeline
spec_backlink: docs/plans/2026-05-09-skill-consolidation-pass.md
status: canonical
---

<!-- Purpose: Canonical home for the shared reviewer pipeline phases used by both /review (plan-shaped) and /review-code (code-shaped). Carries Phases 2.5, 2.7, 2.7b, 2.7c, 2.8, 3.5, 3.7, 4, and 5 verbatim from the former review-dispatch skill. Does NOT carry the routing table (lives in each skill's Branch A.2) or the sequential-dispatch HARD RULE (lives in each skill's Branch A.3). -->

# Reviewer Pipeline — Shared Phases Reference

This wiki is the single authoritative source for the phases that run identically for plan reviews (`/review`) and code reviews (`/review-code`). Both skills reference these phases inline — they are not optional. Walk them in order as directed by the invoking skill.

**Scope boundary:** This wiki carries numbered phases with their inline framing prose (rationale paragraphs, EM Decision Step tables, On-failure clauses, write-ahead status). It does NOT carry:
- The reviewer routing table — lives in each skill's Branch A.2.
- The sequential-dispatch HARD RULE — lives in each skill's Branch A.3.

---

## Phase 2.4: Comprehensiveness Auditor (Sonnet, DRAFT — not yet wired)

> **Status: DRAFT.** PM has approved the concept; the implementation has not landed yet. The design below is the spec for a follow-up session to pick up and wire — standard `/plan` + reviewer chain applies. Not staff-session-gated; this is a normal new-skill scaffold, not an architectural decision.

**Problem this targets.** docs-checker and prior-art-checker both work on what IS in the plan. Patrik reasons from the plan's claims forward. None of them is structurally well-positioned to ask *what's missing* — the plan didn't write about X, so no reviewer's grep over the plan body surfaces X. The empirical failure shape: plans pass docs-check + prior-art + Patrik review with no findings, then the executor returns BLOCKED on a substrate gap that any senior engineer would have flagged at draft time ("you didn't say anything about the rollback path", "this plan doesn't address the consumer migration"). The gap is a missing-coverage problem, not a wrong-claim problem.

**Why a Sonnet mechanical auditor, not an Opus reviewer:** The work is enumerative — walk a checklist of canonical coverage areas (rollback, migration, observability, security boundary, error paths, test surface, concurrency, performance, accessibility, docs/changelog impact), grep the plan body for evidence of each area being addressed, emit a sidecar listing which areas are silent. This is mechanical pattern-matching, not architectural judgment; Sonnet at low temperature is the right altitude. Opus reviewers can then use the gap-list as input rather than re-deriving it.

**Sequencing — between plan-draft and prior-art-check:**

```
plan.write → comprehensiveness-auditor (Sonnet) → docs-checker (Sonnet) → prior-art-checker (Sonnet) → Opus reviewer → integrator
```

The auditor runs BEFORE docs-checker and prior-art-checker because gap findings often reshape the plan body (the EM adds a Rollback section, a Migration section), which means docs-checker and prior-art-checker should run on the AMENDED body, not the original. Running comprehensiveness-auditor last (post-Opus) is the wrong shape — it would force a second Opus pass after gap-fill.

**Coverage checklist (initial draft — to be tuned empirically):**

| Area | Trigger | What "addressed" looks like |
|------|---------|----------------------------|
| Rollback | Plan changes shipped behavior, contract, or schema | Section names a revert/disable path, names what state survives the rollback |
| Migration | Plan changes a producer-consumer contract or persisted format | Section addresses existing data / existing consumers / version-aware logic |
| Observability | Plan ships a new code path, hook, or background process | Section names log/metric/trace surface OR explicitly notes "no observability needed and why" |
| Security boundary | Plan reads/writes external input, executes shell, or crosses a privilege boundary | Section names the validation surface OR explicitly notes "trusted internal path" with grep evidence |
| Error paths | Plan adds error-prone surface (I/O, network, parse, exec) | Section names each failure mode + handling shape |
| Test surface | Any code change | Section names test files OR documents "no test, because <reason>" |
| Concurrency | Plan touches shared state, files appended by multiple actors, async dispatch | Section addresses lock/order/idempotency strategy |
| Docs impact | Plan changes user-visible behavior or operator-visible interface | Section names doc files to update OR notes none-needed |

**Output sidecar:** `tasks/review-findings/{timestamp}-comprehensiveness.md` with a Silent / Addressed / N/A verdict per area + evidence quote (file:line within plan). Empty Silent column = green light. Non-empty Silent column blocks dispatch of downstream reviewers until EM either fills the gaps or annotates each as N/A with rationale.

**Failure modes to watch for** (when this phase ships, calibrate against these):

1. **False-positive Silent on N/A areas.** A trivial single-file fix doesn't need a Rollback section. The auditor must NOT block trivial work; tune the area-trigger column to fire only when the plan's scope mode (prototype / production-patch / feature / architecture / spike — see writing-plans.md) justifies the check.
2. **Coverage checklist becomes ceremony.** If every plan ships with an empty Observability section just to clear the gate, the section is decorative. Calibrate the trigger so the area only surfaces on genuine scope; null-result audit at 4-week cadence to retire areas that never fire on real plans.
3. **Auditor competes with Patrik.** If the auditor surfaces gaps that Patrik would have surfaced anyway, it's pure overhead. Calibrate by tracking which gaps Patrik flags that the auditor DIDN'T pre-surface — those are the ones the auditor needs to learn; ones Patrik never flags are the ones the auditor over-surfaces.

**Open design questions (PM input pending):**

- Should this run on plan-mode `coordinator:plan` exit, or only when the plan is `architecture` / `feature` scope? Default proposal: only on `feature` and `architecture` (skip for `prototype`, `production-patch`, `spike`).
- Should Silent areas auto-amend the plan body with `## TODO: <area> coverage` stubs, or just emit the sidecar and let the EM author? Default proposal: sidecar-only, EM authors — auto-amend invites ceremony.
- Cumulative-effect: this adds a 4th pre-flight to the plan→review pipeline. Combined with docs-check + prior-art + external-pattern, the pre-review chain is now ~2-3 minutes of Sonnet dispatch. Acceptable cost vs. expected Opus-reviewer savings? Empirical calibration after first 10 dispatches.

Lesson source: `project-rag/tasks/lessons.md` (2026-05-18, comprehensiveness-auditor between plan-draft and prior-art-check).

---

## Phase 2.5: Write-Ahead Status Update

Before dispatching reviewers, mark the artifact's review status. If the artifact has a status header (plan doc, stub doc), update it:

```
**Status:** Under review by [Reviewer Name] (review started YYYY-MM-DD HH:MM)
```

If the artifact is code (no status header), note the review in the tracker or plan doc that references this work. The point is: if a crash happens mid-review, there's a breadcrumb showing what was being reviewed and by whom.

---

## Phase 2.7: API Verification (docs-checker pre-flight)

Before dispatching expensive Opus reviewers, decide whether to run the **docs-checker** agent (Sonnet) as a suggested pre-flight. docs-checker verifies external API references and applies AUTO-FIX-class corrections inline — reviewers receive a pre-verified artifact and can skip mechanical lookups entirely.

**EM Decision Step — consult the table below before dispatching:**

_Last calibrated: 2026-05-03 against Claude Opus 4.7 (1M context) training distribution. Re-evaluate when the underlying model changes._

| Language / Domain | Default | EM discretion |
|---|---|---|
| **C++ (Unreal Engine, native libraries)** | **Always run.** UE's API surface drifts every release; signatures and module/`.Build.cs` boundaries are easy to hallucinate. | None — run it. |
| **C++ (non-UE)** | Run unless trivially small. | Skip only when the artifact cites ≤3 stdlib calls and nothing else. |
| **C# (Unity, .NET)** | EM discretion, bias toward running for Unity package version drift and recent .NET preview features. | Skip for trivial scripts touching only well-known BCL APIs. |
| **Python** | EM discretion. | Run when the artifact pins library versions or uses uncommon SDKs (Stripe, Anthropic SDK new features, ML libraries). Skip for stdlib-only scripts. |
| **TypeScript / JavaScript** | EM discretion. | Run when SDK signatures matter (Anthropic, Stripe, AWS SDK v3 vs v2). Skip for routine React/Node code in the training distribution. |
| **Go, Rust, Swift** | EM discretion. | Bias toward running — fewer training tokens than Python/TS. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — nothing to mechanically verify. |
| **Plans citing in-repo symbols only** | Skip docs-checker (use project-RAG instead). | None — docs-checker is for external APIs. |

**Heuristic, not law.** The EM applies judgment: scale (1-page stub vs 30-page spec), complexity (3 API calls vs 50), distance from training (UE 5.6 features vs `Array.prototype.map`). When in doubt, run it — it's cheap. **Skip is silent — no flag needed, no justification required.**

**In practice:**
- **C++/UE artifacts:** run docs-checker.
- **Other languages:** EM judgment — bias toward running for unfamiliar SDKs and pinned versions; skip for routine in-distribution code.
- **Pure prose artifacts:** skip — nothing to verify.

**Dispatch:**
1. Dispatch `docs-checker` agent with the artifact path
2. docs-checker applies AUTO-FIX-class corrections inline and writes all edits as a single git-revertible commit
3. docs-checker emits `tasks/review-findings/{timestamp}-docs-checker-edits.md` (changelog sidecar) and `tasks/review-findings/{timestamp}-docs-checker.md` (verification report)
4. EM reads the edits sidecar (if any) and includes the following verbatim in the Opus reviewer's dispatch prompt:

   > A docs-checker pre-flight ran on this artifact. AUTO-FIX corrections were applied inline — see [edits sidecar path] for the changelog. UNVERIFIED claims are listed in [report path] for your verification. VERIFIED claims do not need re-checking; focus your review on architecture, approach, and design.

**EM spot-check obligation (mandatory):** After the Opus reviewer completes, the EM diffs the docs-checker commit against the pre-edit artifact for any auto-fix the Opus reviewer did not explicitly endorse. This spot-check is mandatory and time-bounded — read the changelog AND run the diff before marking the review stage done. Rollback is `git revert <docs-checker-commit-sha>` — one command.

**On docs-checker failure:** Proceed to Phase 2.8 and Phase 3 without the report. Reviewers fall back to their own verification. This phase is additive, not blocking.

**Phase 2.8 integrator note:** The review-integrator does NOT review docs-checker auto-fixes — those are pre-applied before the Opus reviewer sees the artifact. The integrator continues to handle Opus reviewer findings as today. The docs-checker changelog is part of the review record archived alongside the review findings.

---

## Phase 2.7b: Prior-Art Verification (prior-art-checker pre-flight)

**The prior-art-checker is a recall pre-flight, not a reviewer. It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed by all downstream reviewers.**

Before dispatching expensive Opus reviewers, decide whether to run the **prior-art-checker** agent (Sonnet) as a suggested pre-flight. While docs-checker verifies factual claims about external APIs, prior-art-checker cross-references the plan's claims against **what we've already learned** — project wikis, global wikis, `tasks/lessons.md`, and the central improvement queue. Reviewers receive a sidecar showing where the plan conflicts with prior art, where it should cite established patterns, and where it touches unprecedented ground.

**EM Decision Step — when to run:**

| Artifact type | Default | EM discretion |
|---|---|---|
| **Plan documents** (`docs/plans/*.md`, `~/.claude/plans/*.md`) | **Run by default.** Plans are the artifact this agent was designed for. | Skip only when the plan is a single-file mechanical bug-fix with no architectural decision. |
| **Enriched stubs with architectural decisions** | Run if any chunk introduces a new pattern, new agent, new convention, or modifies cross-cutting doctrine. | Skip for stubs that are purely mechanical execution of a previously-checked plan. |
| **Code review (no plan artifact)** | Skip. | Run when a PR/diff lacks a plan but introduces a new pattern or convention worth checking against doctrine. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — no claim surface to cross-reference. |
| **Trivial single-file edits** | Skip. | None — overhead exceeds the benefit. |

**Heuristic, not law.** When the plan reverses a prior decision, ALWAYS run — that is exactly the case where prior art most matters (per `coordinator/CLAUDE.md` "Premise-pass before regenerating torn-down structure"). When in doubt, run it; the agent is cheap and the alternative is silent doctrine decay.

**Skip is silent.** No flag needed, no justification required. EM judgment.

**Dispatch:**
1. Dispatch `prior-art-checker` agent with the plan path.
2. prior-art-checker reads project wikis, global wikis, lessons, and the improvement queue; cross-references the plan; writes a sidecar at `<plan-path>.prior-art-check.md`.
3. Sidecar verdict is `COMPATIBLE`, `WARN`, or `BLOCKED-SURFACE-TO-PM`.
4. **EM reads the sidecar before dispatching the Opus reviewer.** This step is mandatory — the verdict determines whether to proceed or escalate to PM. It does NOT require EM pre-disposition of Conflicts; the Opus reviewer's judgment is the primary input on direction-of-correction (per `snippets/prior-art-check-consumption.md` and `docs/wiki/prior-art-checker.md § Bidirectional resolution`).
   - **COMPATIBLE:** include the sidecar path in the Opus reviewer's dispatch prompt and proceed.
   - **WARN:** include the sidecar in the Opus reviewer's dispatch prompt and proceed. The reviewer recommends a direction-of-correction per Conflict (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`). EM pre-disposition in the dispatch brief is OPTIONAL — use it when the right direction is mechanically obvious (e.g., a Conflict against load-bearing doctrine that's already settled), and leave it for the reviewer when the call is architectural. A reviewer recommendation contrary to an EM pre-disposition escalates as ASK in the integrator pass (see `agents/review-integrator.md § Prior-Art Conflict Resolution`).
   - **BLOCKED-SURFACE-TO-PM:** STOP. Surface to PM with the sidecar quote(s). Do NOT dispatch the Opus reviewer until PM has decided fold-in or authorized override.
5. Include the following verbatim in the Opus reviewer's dispatch prompt:

   > A prior-art-check pre-flight ran on this plan. Sidecar: [path]. Verdict: [verdict]. The sidecar is unintegrated — your judgment is the primary input on direction-of-correction per Conflict. Recommend `update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed` per Conflict with one-sentence reasoning. Use the Compatible-but-relevant section to identify wikis the plan should cite; flag missing citations as findings if they would aid maintainability. (Any EM pre-disposition appears in this dispatch brief; if your judgment differs, say so — the integrator will escalate as ASK.)

**On prior-art-checker failure:** Proceed to Phase 2.8 and Phase 3 without the sidecar. Reviewers fall back to their own doctrine recall (which is the pre-2026-05-06 baseline). This phase is additive, not blocking.

**The prior-art-checker is a feedback loop on wiki quality.** Repeated false-positive conflicts on a wiki entry are signal — surface to PM as a candidate for wiki revision (the wiki may be outdated, vague, or wrong). This is the recall side of the capture-recall loop; without it, captured wikis decay silently.

**Phase 2.7b integrator note:** The review-integrator processes prior-art-side edits AFTER the Opus reviewer pass, per the direction-of-correction the reviewer (and optionally the EM) named. No integrator pass runs *between* the prior-art-checker and the first named reviewer — pre-flight sidecars are not a sequential reviewer. See `agents/review-integrator.md § Prior-Art Conflict Resolution` for the integrator's authority on wiki/registry/lessons edits. The prior-art-check sidecar is archived alongside the review findings. Note: this contract applies to prior-art-checker WARN (Conflicts with five valid directions, passing through the reviewer unintegrated); plan-coverage-checker INCOMPLETE has a different contract — see Phase 2.7d.

---

## Phase 2.7d: Plan Coverage Verification (plan-coverage-checker pre-flight)

**The plan-coverage-checker is a completeness pre-flight, not a reviewer. It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed by all downstream reviewers.**

**Trigger (skill-internal — no EM opt-out):**

| Plan shape | Run? | Why |
|---|---|---|
| Plan contains an audit/findings/issues table with ≥5 items | **Run.** | The oracle exists; coverage is checkable; the empirical 36/9/4 case lives here. |
| Plan contains an audit table with 1–4 items | Run. | Cheap. False-skip cost is higher than false-run cost. |
| Plan contains no audit/findings table (pure greenfield design) | Skip silently. | Agent would emit `SCOPE-MISMATCH`; no point spending the dispatch. |
| Plan is single-file mechanical fix (no design content) | Skip silently. | Same as prior-art-checker triviality skip. |
| Plan is a doc redesign / wiki rewrite | Skip silently. | No fix-slate shape. |

**Dispatch:**
1. Dispatch `plan-coverage-checker` agent with the plan path.
2. Agent parses oracle + slate, runs three lenses, writes sidecar at `<plan-path>.plan-coverage-check.md`.
3. EM reads sidecar before dispatching the Opus reviewer.
   - **COMPLETE:** include sidecar path in Opus reviewer dispatch and proceed.
   - **INCOMPLETE:** fold findings into the plan BEFORE Opus reviewer dispatch. Missed items added to slate or OOS with architectural reason. Weak-OOS rewritten or promoted to slate. Substrate-drift amended.
   - **BLOCKED-SURFACE-TO-PM:** STOP. Surface to PM with verbatim findings.
   - **SCOPE-MISMATCH / DEGRADED:** proceed; no fold needed.
4. Include verbatim in Opus reviewer dispatch prompt:

   > A plan-coverage-check pre-flight ran on this plan. Sidecar: [path]. Verdict: [verdict]. If INCOMPLETE, the EM has folded findings into the plan body — review the amended version. The sidecar is included as audit trail; coverage gaps are not yours to re-litigate, but if you spot a NEW gap the lens missed, flag it.

**On plan-coverage-checker failure:** Proceed without the sidecar. Phase is additive, not blocking.

**Doctrine note — divergence from Phase 2.7b sidecar contract.** The Phase 2.7b note that "the Opus reviewer's judgment is what we want shaping direction-of-correction" applies to **prior-art Conflicts**, which have five valid directions (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`). It does NOT apply to plan-coverage-check Missed findings, which have three valid EM-mechanical resolutions: (1) add-to-slate, (2) architectural-OOS, (3) oracle-was-wrong (amend the audit table with explanatory note). None of these three require reviewer judgment. The mechanical nature of a missed audit item makes pre-fold the correct posture; reviewer judgment adds no value on a question the EM can resolve mechanically. Same shape for substrate-drift (amend or explain). This is the architectural distinction between recall (prior art) and coverage (this lens). Note: this contract applies to prior-art-checker WARN, not to all pre-flight findings.

**Phase 2.7b and 2.7d run in parallel** when the plan triggers both. They are independent — neither reads the other's sidecar. **Phase 2.7c still gates on 2.7b completion (unchanged from existing doctrine)** — external-pattern-checker reads the prior-art sidecar as input. So the runtime shape is: (2.7b ∥ 2.7d) → 2.7c → 2.8 → named reviewer. The EM consumes all available sidecars before dispatching the named Opus reviewer.

---

## Phase 2.7c: External Pattern Verification (external-pattern-checker, opt-in)

**The external-pattern-checker is a triage pre-flight, not a reviewer. It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed as ad-hoc context in the Opus reviewer's dispatch prompt.**

Before dispatching expensive Opus reviewers, decide whether to run the **external-pattern-checker** agent (Sonnet) as an opt-in pre-flight. Where docs-checker verifies facts and prior-art-checker recalls internal doctrine, external-pattern-checker asks a different question: *"Is there enough external signal on this topic that we should dispatch deeper research before the Opus reviewer sees this plan?"*

**This phase is opt-in only and is skipped silently for ~95% of plans.** There is no default-on behavior.

**EM Decision Step — the two-condition trigger gate:**

| Condition | Requirement |
|---|---|
| **A** | prior-art-checker returned `Silent` on ≥ 1 **architecturally-loaded** claim — meaning the claim involves a new abstraction, protocol, or doctrine surface (not a constant bump, test fix, or rename) |
| **B** | The plan is `scope_mode: architecture` or `scope_mode: feature` AND the topic is one the project has struggled with, evidenced by ≥ 2 entries in `tasks/lessons.md` or `coordinator-improvement-queue.md` sharing a noun-phrase from the plan's central abstractions, OR ≥ 1 archived handoff in `archive/handoffs/` whose body matches the same noun-phrase AND contains "reverted" / "abandoned" / "rolled back" |

**Both A and B must hold.** If either condition is absent, skip this phase silently — no flag, no justification. PM can also authorize a direct invocation ("run external-pattern-check on this plan") which bypasses the gate.

**This phase always runs AFTER Phase 2.7b (prior-art-checker).** It reads the prior-art sidecar as input; dispatching it before prior-art-checker runs produces an automatic SCOPE-MISMATCH abstain.

**Dispatch (when both conditions hold):**
1. Dispatch `external-pattern-checker` agent with the plan path and the prior-art sidecar path.
2. The agent reads the prior-art sidecar, identifies architecturally-loaded Silent claims, runs ≤ 2 WebSearch + ≤ 5 WebFetch, and writes a sidecar at `<plan-path>.external-pattern.md`.
3. Sidecar verdict is `RESEARCH-RECOMMENDED`, `LIGHT-CONTEXT-AVAILABLE`, `NO-EXTERNAL-SIGNAL`, `DEGRADED`, or `SCOPE-MISMATCH`.
4. **EM reads the sidecar before dispatching the Opus reviewer.** The verdict determines next steps:
   - **RESEARCH-RECOMMENDED:** EM dispatches the recommended `general-purpose` web scout or `/deep-research` as a separate decision before the Opus review. Include the sidecar path in the Opus reviewer prompt.
   - **LIGHT-CONTEXT-AVAILABLE or CAUTIONARY-NOTE:** Fold the relevant `Light Context Surfaced` / `Cautionary Note` sections as a one-paragraph briefing into the Opus reviewer dispatch prompt.
   - **NO-EXTERNAL-SIGNAL:** Proceed to Phase 2.8. No fold-in needed.
   - **DEGRADED:** Treat as no signal — proceed as if the phase did not run.
   - **SCOPE-MISMATCH:** The trigger conditions were not met (the agent determined this itself). Note the reason and proceed.

**Mandatory fold-confirmation (auditable consumption — per plan disposition D1):**

In the same dispatch turn where you proceed to Phase 2.8 / Phase 3, you MUST include verbatim either:

> (a) A one-paragraph briefing copied from the sidecar's `Light Context Surfaced` / `Cautionary Note` buckets (included in the Opus reviewer's dispatch prompt), OR
> (b) "external-pattern-check ran; no fold needed (verdict: NO-EXTERNAL-SIGNAL)."

This makes consumption auditable. Silent omission of the sidecar with no confirmation is not permitted.

**On external-pattern-checker failure:** Proceed to Phase 2.8 and Phase 3 without the sidecar. This phase is additive, not blocking.

**Note on vocabulary:** external-pattern-checker uses its own bucket vocabulary (`Signal Worth Deeper Research`, `Light Context Surfaced`, `Cautionary Note`, `No External Signal`). These are distinct from prior-art-checker's vocabulary (`Conflicts`, `Compatible-but-relevant`, `Silent`). Do not conflate them in reviewer prompts or EM notes. Full doctrine: `docs/wiki/external-pattern-checker.md`.

---

## Phase 2.8: Pre-Review Artifact Verification (Haiku, optional)

Before dispatching an expensive Opus reviewer, dispatch a **Haiku agent** to verify the artifact is well-formed and worth reviewing. This catches broken artifacts before they waste the most expensive tokens in the system.

**When to run:** When the artifact is code or enriched stubs (not plans or docs — those are cheap to review regardless).

**Haiku checks:**
1. **Compilable/parseable** — does the code compile, typecheck, or lint clean? Run the project's validation command.
2. **Enrichment complete** — are all placeholder/TODO markers in enriched stubs filled? (`grep -r 'TODO\|PLACEHOLDER\|TBD\|\[UNKNOWN\]'`)
3. **Non-trivial** — is the artifact non-empty and substantive? (not a stub with only headers)

**On failure:** Report to coordinator with the specific issue. Do NOT dispatch the Opus reviewer. Fix the artifact first (or re-dispatch enrichment), then retry.

**On pass:** Proceed to Phase 3.

**Why Haiku:** Running `tsc --noEmit`, `grep`, and checking file sizes is mechanical work. A failed pre-flight saves 1 full Opus reviewer dispatch — the highest per-agent cost in the system.

---

## Phase 3.5: Parse and Render Structured Output

After each reviewer completes:

1. **Parse the JSON block** from the reviewer's output. Look for a fenced ` ```json ` block containing a `ReviewOutput` object with `reviewer`, `verdict`, `summary`, and `findings` fields.

2. **If valid JSON found:**
   - Render findings as a Markdown table for human reading:
     ```
     | # | File | Lines | Severity | Category | Finding |
     |---|------|-------|----------|----------|---------|
     | 0 | path/to/file.ts | 42-48 | critical | correctness | Description |
     ```
   - Write raw JSON to disk at: `tasks/review-findings/{timestamp}-{reviewer}.json`
     Create `tasks/review-findings/` directory if it doesn't exist.
   - Report: "Structured output parsed: N findings (X critical, Y major, Z minor, W nitpick)"

3. **If valid JSON but with field drift, normalize before rendering:**
   - Severity: map `"high"` → `"major"`, `"moderate"/"medium"` → `"minor"`, `"low"` → `"nitpick"`
   - Verdict: normalize to ALL_CAPS_UNDERSCORES (e.g., `"request_changes"` → `"REQUIRES_CHANGES"`)
   - Field names: map `"description"/"detail"` → `"finding"`, `"recommendation"` → `"suggested_fix"`, `"line"` → `"line_start"`
   - Category: strip underscores/verbose suffixes (e.g., `"trust_and_transparency"` → `"trust"`, `"cognitive_flow"` → `"cognitive-load"`)
   - Log: "Normalized N fields in reviewer output" (for tracking compliance improvement over time)

4. **If no valid JSON found (reviewer output is prose):**
   - Log a warning: "Reviewer returned prose output, not structured JSON. Proceeding with prose."
   - Continue with the prose findings as before.
   - Note in the Phase 5 report that this reviewer needs structured output enforcement on re-review.

5. **Apply `--problems-only` filter** (if flag was set):
   - Filter the rendered findings table to `severity != "nitpick"`. Findings missing a `severity` field are treated as `minor` and included.
   - Nitpicks are still present in the JSON file written to disk (audit trail)
   - Nitpicks are NOT auto-applied to the artifact
   - Only findings with severity ∈ {critical, major, minor} are included in the "apply all" list

---

## Phase 3.7: Review Integration (replaces manual feedback application)

After each reviewer completes (and Phase 3.5 runs):

1. Dispatch the review-integrator agent with:
   - The **filtered** finding list (post-Phase 3.5 `--problems-only` filtering if active)
   - The artifact path(s)
   - The reviewer name (for annotation attribution)
2. Review-integrator applies all findings, annotates changes, returns completion report
3. EM reviews:
   - Escalation list (usually 0 items) — resolve any disagreements
   - Spot-check the diff (verify integrator applied findings correctly)
   - If escalations exist: EM resolves directly or escalates to PM

**Reviewer 2 (Generalist) — if routing calls for one:**

4. Dispatch Reviewer 2 with the EVOLVED artifact (post-review-integrator changes)
5. Reviewer 2 catches novel issues AND regressions from the integration pass
6. Dispatch review-integrator again for Reviewer 2's findings (same Phase 3.7 protocol)

---

## Phase 4: Backstop Handling

This phase applies when the primary reviewer (Patrik or a domain reviewer) has run and the chain calls for a backstop pass. It does NOT apply when Zolí was the standalone primary reviewer — in that case, his findings flow through the normal integrator path (Phase 3.7) and Phase 4 is a no-op.

When effort level is High AND a primary reviewer (not standalone Zolí) ran:
1. Verify that the reviewer invoked their backstop partner (Zolí for Patrik; Patrik for domain reviewers; Fru for Palí; Patrik for Fru)
2. If the backstop was not invoked, prompt the reviewer to do so OR dispatch the backstop directly with `mode: "backstop"`
3. If the backstop disagreed: both perspectives are surfaced to Coordinator/PM per the routing.md reconciliation protocol

When effort level is Medium:
- Backstop invocation is at the reviewer's (or EM's) discretion
- No verification needed

**When Zolí ran as standalone primary, skip Phase 4 entirely.** Zolí standalone is a peer-to-Patrik review with cross-team authority — there is no further backstop above the DoE chair. The terminal backstop in the system is Zolí himself; nothing wraps him.

---

## Phase 5: Report

Summarize the review with a **triage table** — every finding must have an explicit disposition:

| # | Finding | Severity | Disposition | Reasoning |
|---|---------|----------|-------------|-----------|
| 0 | [summary] | critical | Applied | [what changed] |
| 1 | [summary] | minor | Dismissed | [why — PM input needed / disagree] |

Dispositions: **Applied** (fix implemented), **Captured** (deferred to backlog — state where), **Dismissed** (with reasoning).

Then summarize:
- Who reviewed, at what effort level
- Disposition counts: N applied, N captured, N dismissed
- What was escalated to PM (if anything)
- Verdict: Ready for execution / Needs PM decision / Needs rework

**Post-review synthesis:** If 2+ reviewers ran, produce a synthesis note per the routing rules. This cross-references coverage declarations and flags reinforcing findings, conflicts, and gaps. The synthesis is the coordinator's judgment — no additional agent dispatch.

---

## Composition Patterns for Major Surface Additions

The numbered phases above describe a single review pass. For substrate-blind spec→impl chains, parallel-enriched cohorts, and architecturally-loaded plan stubs, composition matters as much as any single reviewer's depth. The patterns below name the recipes that have caught real bugs the single-pass shapes missed.

### Five-layer review topology

For major surface additions where the spec author was substrate-blind (no on-disk grep, no per-file Read), a single Opus reviewer is not enough — orthogonal lenses catch different error classes. The full topology:

1. **Plan-author negative-search** (W1, `writing-plans` SKILL). Prohibitions and prior reversals surfaced before reviewer dispatch.
2. **docs-checker pre-flight** (Phase 2.7). External-API claim verification, AUTO-FIX inline.
3a. **prior-art-checker pre-flight** (Phase 2.7b). Doctrine-recall against wikis + lessons + queue.
3b. **plan-coverage-checker pre-flight** (Phase 2.7d). Oracle-vs-slate completeness, hedge detection, in-repo substrate drift. Skill-internal trigger — runs unconditionally on plans with oracle tables. Runs in parallel with layer 3a (prior-art-checker).
4. **Patrik Pass 0 premise review** (W3). Plan-level premise validity; `clean | needs-justification | refuted`.
5. **Domain reviewer (Sid for game-dev / Camelia for data / etc.) + enricher callsite read** (Phase 3). Existing-codebase pattern check + on-disk callsite reality.

<!-- Review: code-reviewer — plan-coverage-checker (Phase 2.7d) was absent from the five-layer topology list; added as 3b parallel to prior-art-checker, matching the (2.7b ∥ 2.7d) runtime shape documented in Phase 2.7d. -->

Use the full five-layer recipe when the plan introduces a new cross-cutting abstraction, new doctrine surface, or the spec author flagged substrate-blind framing. Skip layers only with explicit rationale recorded in the dispatch trail. Specialist-worker lenses (test-evidence-parser, security-audit-worker, dep-cve-auditor, doc-link-checker) ride alongside layer 5 as routine, not opt-in — they catch what generalist Opus reviewer lenses miss.

### Architectural review chain — Patrik, Sid, enricher catch different bugs

Within the layer-5 envelope, the three roles divide the work:

- **Patrik catches structural problems.** Plan coherence, missing seams, architectural inversions, premise refutation.
- **Sid (or domain-equivalent) catches existing-codebase-pattern violations.** "We don't do it that way here" — patterns the plan invented when the codebase already had a convention.
- **The enricher catches callsite reality.** What the code actually does at the consumer end — function envelopes, reachability, guard conditions the plan paraphrased.

All three are needed on architecturally-loaded stubs. Dropping any one of them produces a known failure class.

### Sequential two-reviewer on architecturally-loaded stubs

For plan stubs that are architecturally-loaded but not full-spec scope, the minimum viable shape is **sequential two-reviewer (generalist Patrik + domain reviewer)** plus the layer-2/2.7b pre-flights. Single-pass review on this surface has a documented miss rate — the second lens routinely surfaces issues the first missed at lower cost than fixing the bug in execution. Sequential, not parallel: integrate Reviewer 1's findings before dispatching Reviewer 2 (the merge-gate parallel carve-out in CLAUDE.md does not apply to plan/stub review).

### Two-pipeline review on shared artifacts: per-stub + per-cohort + docs-check

When a cohort of stubs is enriched in parallel from a shared spec, **two pipelines on the same artifacts** beats picking one lens:

- **Per-stub depth:** Patrik (or domain reviewer) on each stub independently. Catches local correctness, premise validity, structural soundness.
- **Per-cohort coherence:** one reviewer across the whole cohort. Catches contradictions between stubs, shared-API gaps, sibling-surface drift, cross-stub seam violations.
- **docs-check pre-flight:** every external-API claim verified across the cohort, once.

Composition beats picking one. The per-cohort lens routinely re-edits stubs that the per-stub lens already marked "complete" — that is the value, not a defect. Stub completion is conditional on cohort settle, never on per-stub verdict alone. Integrator sweeps cohort-wide findings back across already-applied stubs before declaring the wave done.

### Reviewers false-positive on import-fallback seams

A common false positive: reviewers flag `try: import X / except ImportError: ...` patterns as bugs or anti-patterns without reading both arms. The except-arm is usually a deliberate graceful-degradation seam — a fallback to a vendored module, a stub for optional dependency, or a runtime-detected capability. Flagging the seam as a bug inverts the intent.

**EM disposition discipline:** when a reviewer flags an `ImportError` fallback, **read both arms** before applying. If the except-arm is a structural seam (not error-swallowing), dismiss the finding with a one-line reasoning ("intentional fallback for optional X"). Same shape for try/except `ModuleNotFoundError`, `AttributeError` on capability probes, and platform-conditional imports.

The integrator does not auto-apply import-fallback findings — they always land in the EM disposition table.

---

## Reviewer Elevation Past Charter

*2026-05-17, project-rag.* The PM may elevate a reviewer past their default charter for a specific dispatch — e.g. invoking Zolí not as ambition-backstop (his default) but as standalone DoE for an architectural call; invoking Patrik with cross-repo authority he doesn't carry by default. Elevation must be **verbatim in the brief** — the reviewer's default charter is what they pattern-match against without explicit elevation, and pattern-match will silently win over implicit elevation.

**Required form:**

> *"You are dispatched in elevated mode: [DoE / cross-repo authority / prior-art-override / other]. This dispatch grants [specific authority]. Your default charter ([brief restatement]) does NOT apply for this artifact."*

Without the verbatim elevation, the reviewer falls back to default charter — even if the dispatching EM verbally framed the dispatch as elevated. The brief is the contract; chat context is not.

**Authorization gate.** Elevation past charter is **PM-only**. The EM may surface elevation candidates (*"this artifact would benefit from DoE-tier Zolí, not ambition-backstop"*) but must wait for PM authorization before dispatching the elevated brief. EM-initiated elevation creates a doctrine hole where any EM can promote any reviewer to any charter ad hoc.

**Companion:** `prior-art-checker.md § Prior-art mutability` — for one specific elevated authority (DoE-override of prior-art-checker findings).

## Problems-Only Mode

When `--problems-only` is specified at invocation, append to the reviewer prompt:

> Return only findings that identify problems, bugs, security issues, or correctness concerns. Do not include praise, compliments, or suggestions for optional improvements. Nitpick-severity findings should still be included in your JSON output but will be filtered from the rendered summary.

Three explicit behaviors:
1. Nitpicks are written to the JSON file for audit trail
2. Nitpicks are omitted from the rendered Markdown table
3. Nitpicks are NOT auto-applied to the artifact

The filter criterion is `severity != "nitpick"` — not prose-based filtering. Applied in Phase 3.5 step 5.
