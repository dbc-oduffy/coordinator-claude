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
4. **EM reads the sidecar before dispatching the Opus reviewer.** This step is mandatory — the verdict determines whether to proceed, fold prior art into the plan, or escalate to PM.
   - **COMPATIBLE:** include the sidecar path in the Opus reviewer's dispatch prompt and proceed.
   - **WARN:** EM dispositions each conflict (fold-in, override-and-document, or PM consult). For overrides, append a one-line entry to the plan's "Considered alternatives" section. Include the sidecar in the Opus reviewer dispatch.
   - **BLOCKED-SURFACE-TO-PM:** STOP. Surface to PM with the sidecar quote(s). Do NOT dispatch the Opus reviewer until PM has decided fold-in or authorized override.
5. Include the following verbatim in the Opus reviewer's dispatch prompt:

   > A prior-art-check pre-flight ran on this plan. Sidecar: [path]. Verdict: [verdict]. Conflicts (if any) have been dispositioned by the EM — see the plan for any overrides — the EM may have added a Considered Alternatives section or annotated the relevant phase inline. Use the sidecar's Compatible-but-relevant section to identify wikis the plan should cite; flag missing citations as findings if they would aid maintainability.

**On prior-art-checker failure:** Proceed to Phase 2.8 and Phase 3 without the sidecar. Reviewers fall back to their own doctrine recall (which is the pre-2026-05-06 baseline). This phase is additive, not blocking.

**The prior-art-checker is a feedback loop on wiki quality.** Repeated false-positive conflicts on a wiki entry are signal — surface to PM as a candidate for wiki revision (the wiki may be outdated, vague, or wrong). This is the recall side of the capture-recall loop; without it, captured wikis decay silently.

**Phase 2.7b integrator note:** The review-integrator does NOT process prior-art-check findings directly — those are EM-dispositioned before the Opus reviewer sees the plan. The integrator continues to handle Opus reviewer findings as today. The prior-art-check sidecar is part of the review record archived alongside the review findings.

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

This phase applies when the primary reviewer (the Staff Engineer or a domain reviewer) has run and the chain calls for a backstop pass. It does NOT apply when the Director of Engineering was the standalone primary reviewer — in that case, his findings flow through the normal integrator path (Phase 3.7) and Phase 4 is a no-op.

When effort level is High AND a primary reviewer (not standalone the Director of Engineering) ran:
1. Verify that the reviewer invoked their backstop partner (the Director of Engineering for the Staff Engineer; the Staff Engineer for domain reviewers; the UX Reviewer for the Front-End Reviewer; the Staff Engineer for the UX Reviewer)
2. If the backstop was not invoked, prompt the reviewer to do so OR dispatch the backstop directly with `mode: "backstop"`
3. If the backstop disagreed: both perspectives are surfaced to Coordinator/PM per the routing.md reconciliation protocol

When effort level is Medium:
- Backstop invocation is at the reviewer's (or EM's) discretion
- No verification needed

**When the Director of Engineering ran as standalone primary, skip Phase 4 entirely.** the Director of Engineering standalone is a peer-to-the Staff Engineer review with cross-team authority — there is no further backstop above the DoE chair. The terminal backstop in the system is the Director of Engineering himself; nothing wraps him.

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
3. **prior-art-checker pre-flight** (Phase 2.7b). Doctrine-recall against wikis + lessons + queue.
4. **the Staff Engineer Pass 0 premise review** (W3). Plan-level premise validity; `clean | needs-justification | refuted`.
5. **Domain reviewer (the Game Dev Reviewer for game-dev / the Data Science Reviewer for data / etc.) + enricher callsite read** (Phase 3). Existing-codebase pattern check + on-disk callsite reality.

Use the full five-layer recipe when the plan introduces a new cross-cutting abstraction, new doctrine surface, or the spec author flagged substrate-blind framing. Skip layers only with explicit rationale recorded in the dispatch trail. Specialist-worker lenses (test-evidence-parser, security-audit-worker, dep-cve-auditor, doc-link-checker) ride alongside layer 5 as routine, not opt-in — they catch what generalist Opus reviewer lenses miss.

### Architectural review chain — the Staff Engineer, the Game Dev Reviewer, enricher catch different bugs

Within the layer-5 envelope, the three roles divide the work:

- **the Staff Engineer catches structural problems.** Plan coherence, missing seams, architectural inversions, premise refutation.
- **the Game Dev Reviewer (or domain-equivalent) catches existing-codebase-pattern violations.** "We don't do it that way here" — patterns the plan invented when the codebase already had a convention.
- **The enricher catches callsite reality.** What the code actually does at the consumer end — function envelopes, reachability, guard conditions the plan paraphrased.

All three are needed on architecturally-loaded stubs. Dropping any one of them produces a known failure class.

### Sequential two-reviewer on architecturally-loaded stubs

For plan stubs that are architecturally-loaded but not full-spec scope, the minimum viable shape is **sequential two-reviewer (generalist the Staff Engineer + domain reviewer)** plus the layer-2/2.7b pre-flights. Single-pass review on this surface has a documented miss rate — the second lens routinely surfaces issues the first missed at lower cost than fixing the bug in execution. Sequential, not parallel: integrate Reviewer 1's findings before dispatching Reviewer 2 (the merge-gate parallel carve-out in CLAUDE.md does not apply to plan/stub review).

### Two-pipeline review on shared artifacts: per-stub + per-cohort + docs-check

When a cohort of stubs is enriched in parallel from a shared spec, **two pipelines on the same artifacts** beats picking one lens:

- **Per-stub depth:** the Staff Engineer (or domain reviewer) on each stub independently. Catches local correctness, premise validity, structural soundness.
- **Per-cohort coherence:** one reviewer across the whole cohort. Catches contradictions between stubs, shared-API gaps, sibling-surface drift, cross-stub seam violations.
- **docs-check pre-flight:** every external-API claim verified across the cohort, once.

Composition beats picking one. The per-cohort lens routinely re-edits stubs that the per-stub lens already marked "complete" — that is the value, not a defect. Stub completion is conditional on cohort settle, never on per-stub verdict alone. Integrator sweeps cohort-wide findings back across already-applied stubs before declaring the wave done.

### Reviewers false-positive on import-fallback seams

A common false positive: reviewers flag `try: import X / except ImportError: ...` patterns as bugs or anti-patterns without reading both arms. The except-arm is usually a deliberate graceful-degradation seam — a fallback to a vendored module, a stub for optional dependency, or a runtime-detected capability. Flagging the seam as a bug inverts the intent.

**EM disposition discipline:** when a reviewer flags an `ImportError` fallback, **read both arms** before applying. If the except-arm is a structural seam (not error-swallowing), dismiss the finding with a one-line reasoning ("intentional fallback for optional X"). Same shape for try/except `ModuleNotFoundError`, `AttributeError` on capability probes, and platform-conditional imports.

The integrator does not auto-apply import-fallback findings — they always land in the EM disposition table.

---

## Problems-Only Mode

When `--problems-only` is specified at invocation, append to the reviewer prompt:

> Return only findings that identify problems, bugs, security issues, or correctness concerns. Do not include praise, compliments, or suggestions for optional improvements. Nitpick-severity findings should still be included in your JSON output but will be filtered from the rendered summary.

Three explicit behaviors:
1. Nitpicks are written to the JSON file for audit trail
2. Nitpicks are omitted from the rendered Markdown table
3. Nitpicks are NOT auto-applied to the artifact

The filter criterion is `severity != "nitpick"` — not prose-based filtering. Applied in Phase 3.5 step 5.
