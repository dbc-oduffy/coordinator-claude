---
description: Route artifacts to the right reviewer
allowed-tools: ["Read", "Grep", "Glob", "Agent"]
argument-hint: "[file-path|'plan'|'code'|'stubs'] [--reviewers 'name1,name2'] [--problems-only]"
---

# Review Dispatch — Smart Reviewer Routing

Determine which reviewers to summon for a given artifact, at what effort level, and dispatch them sequentially. Usable standalone for hotfixes/PR reviews or as part of the enrichment pipeline.

## Instructions

When invoked, analyze the artifact to be reviewed and dispatch the appropriate reviewers.

If `$ARGUMENTS` is provided:
- A file/directory path → review that artifact
- "plan" → optimize routing for plan document review
- "code" → optimize routing for code review
- "stubs" → optimize routing for enriched stub review
- `--reviewers "name1,name2"` → explicit reviewer override, bypassing routing table auto-detection. Reviewers are dispatched in order listed. Use this for PM-directed dual-review setups (e.g., `--reviewers "sid,patrik"` for domain + architectural pass).
- `--problems-only` → suppress praise and suggestions; return only actionable findings. See **Problems-Only Mode** below for the full contract.

### Problems-Only Mode

When `--problems-only` is specified, append to the reviewer prompt:

> Return only findings that identify problems, bugs, security issues, or correctness concerns. Do not include praise, compliments, or suggestions for optional improvements. Nitpick-severity findings should still be included in your JSON output but will be filtered from the rendered summary.

Three explicit behaviors:
1. Nitpicks are written to the JSON file for audit trail
2. Nitpicks are omitted from the rendered Markdown table
3. Nitpicks are NOT auto-applied to the artifact

The filter criterion is `severity != "nitpick"` — not prose-based filtering.

### Phase 1: Analyze the Artifact

1. Read the artifact (file, directory of stubs, or diff)
2. Determine the nature of the work by looking for signals:
   - Game dev / Unreal / DroneSim references → Game Dev Reviewer route
   - Architectural changes, new subsystems, new abstractions → Staff Engineer route
   - Front-end, CSS, UI components, tokens, design system → Front-End Reviewer route
   - ML/AI pipeline, model serving, RAG, data science → Data Science Reviewer route
   - UX flow, user-facing feature, trust/clarity → UX Reviewer route
   - Cross-cutting changes (many files, new patterns) → Staff Engineer route
   - Multiple signals → use the strongest signal for Reviewer 1, secondary for Reviewer 2
3. Report the routing decision before dispatching

### Phase 2: Apply Routing Table

**If `--reviewers` was provided:** Skip auto-detection. Use the explicit list — first name is Reviewer 1, second (if any) is Reviewer 2. Look up each reviewer's agent type and model from the composite routing table. Report: "PM-directed review: [name1] then [name2]."

**Otherwise, auto-detect** using dynamic discovery:
1. Read the base routing table from this plugin's `routing.md` (at plugin root)
2. Scan all enabled plugins for root-level `routing.md` routing fragments
3. Merge into composite routing table
4. Match the artifact's signals against the composite table

Reference composite table (assembled at dispatch time from discovery):

| Signal | Reviewer 1 (Domain) | Reviewer 2 (Generalist) | Effort |
|--------|---------------------|------------------------|--------|
| Game dev / Unreal / DroneSim | the Game Dev Reviewer (`game-dev:staff-game-dev`) | the Staff Engineer (`coordinator:staff-eng`) | Medium → Medium |
| Architectural change, new subsystem | the Staff Engineer | (backstop: the Ambition Advocate (`coordinator:ambition-advocate`)) | High |
| Front-end, CSS, UI components | the Front-End Reviewer (`web-dev:senior-front-end`) | (backstop: the UX Reviewer (`web-dev:staff-ux`)) | Medium |
| Front-end + architecture | the Front-End Reviewer | the Staff Engineer | Medium → High |
| ML/AI pipeline, model serving, RAG | the Data Science Reviewer (`data-science:staff-data-sci`) | the Staff Engineer | High → High |
| UX flow, user-facing feature | the UX Reviewer | (backstop: the Staff Engineer) | Low → Medium |
| Cross-cutting (many files, new pattern) | the Staff Engineer | (backstop: the Ambition Advocate) | High |
| Major DroneSim feature / new game mode | the Game Dev Reviewer | the Staff Engineer | High → High |
| Other / unmatched | the Staff Engineer | (none) | Medium |

### Phase 2.5: Write-Ahead Status Update

Before dispatching reviewers, mark the artifact's review status. If the artifact has a status header (plan doc, stub doc), update it:

```
**Status:** Under review by [Reviewer Name] (review started YYYY-MM-DD HH:MM)
```

If the artifact is code (no status header), note the review in the tracker or plan doc that references this work. The point is: if a crash happens mid-review, there's a breadcrumb showing what was being reviewed and by whom.

### Phase 2.7: API Verification (docs-checker pre-flight)

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

### Phase 2.7b: Prior-Art Verification (prior-art-checker pre-flight)

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

### Phase 2.8: Pre-Review Artifact Verification (Haiku, optional)

Before dispatching an expensive Opus reviewer, dispatch a **Haiku agent** to verify the artifact is well-formed and worth reviewing. This catches broken artifacts before they waste the most expensive tokens in the system.

**When to run:** When the artifact is code or enriched stubs (not plans or docs — those are cheap to review regardless).

**Haiku checks:**
1. **Compilable/parseable** — does the code compile, typecheck, or lint clean? Run the project's validation command.
2. **Enrichment complete** — are all placeholder/TODO markers in enriched stubs filled? (`grep -r 'TODO\|PLACEHOLDER\|TBD\|\[UNKNOWN\]'`)
3. **Non-trivial** — is the artifact non-empty and substantive? (not a stub with only headers)

**On failure:** Report to coordinator with the specific issue. Do NOT dispatch the Opus reviewer. Fix the artifact first (or re-dispatch enrichment), then retry.

**On pass:** Proceed to Phase 3.

**Why Haiku:** Running `tsc --noEmit`, `grep`, and checking file sizes is mechanical work. A failed pre-flight saves 1 full Opus reviewer dispatch — the highest per-agent cost in the system.

### Phase 3: Sequential Dispatch

> **HARD RULE: Reviews are ALWAYS sequential, never parallel.** Each reviewer must see the evolved artifact including all changes from prior reviewers. This compounding context is the entire point of multi-reviewer pipelines. Do not parallelize for speed.

**Reviewer 1 (Domain Specialist):**
1. Dispatch via Task tool with the appropriate agent type and model
2. Include the full artifact in the prompt — do not make the reviewer read files themselves if avoidable
3. Wait for Reviewer 1's findings

**Phase 3.7: Review Integration (replaces manual feedback application)**

4. Dispatch the review-integrator agent with:
   - The **filtered** finding list (post-Phase 3.5 `--problems-only` filtering if active)
   - The artifact path(s)
   - The reviewer name (for annotation attribution)
5. Review-integrator applies all findings, annotates changes, returns completion report
6. EM reviews:
   - Escalation list (usually 0 items) — resolve any disagreements
   - Spot-check the diff (verify integrator applied findings correctly)
   - If escalations exist: EM resolves directly or escalates to PM

**Reviewer 2 (Generalist) — if routing calls for one:**
7. Dispatch Reviewer 2 with the EVOLVED artifact (post-review-integrator changes)
8. Reviewer 2 catches novel issues AND regressions from the integration pass
9. Dispatch review-integrator again for Reviewer 2's findings (same Phase 3.7 protocol)

### Phase 3.5: Parse and Render Structured Output

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

### Phase 4: Backstop Handling

When effort level is High:
1. Verify that the reviewer invoked their backstop partner
2. If backstop was not invoked, prompt the reviewer to do so
3. If backstop disagreed: both perspectives are surfaced to Coordinator/PM

When effort level is Medium:
- Backstop invocation is at the reviewer's discretion
- No verification needed

### Phase 5: Report

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

### Relationship to Other Commands

- **`/enrich-and-review`** invokes this command's logic during Phase 5
- For lightweight code quality checks, dispatch a Sonnet-level subagent directly rather than the full review-dispatch pipeline
- Executor dispatch (`docs/wiki/delegate-execution.md`) follows after review-dispatch approves artifacts for execution
