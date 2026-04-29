---
description: Route artifacts to the right reviewer
allowed-tools: ["Read", "Grep", "Glob", "Agent"]
argument-hint: "[file-path|'plan'|'code'|'stubs'] [--reviewers 'name1,name2'] [--problems-only] [--depth thorough|standard|quick]"
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
- `--depth "thorough|standard|quick"` → controls review intensity:
  - `thorough` — multi-reviewer sequential pipeline (Reviewer 1 → integrator → Reviewer 2 → integrator). Default for High effort artifacts.
  - `standard` — single reviewer with integration. Current default behavior for Medium effort.
  - `quick` — single reviewer, `--problems-only` auto-applied, skip Phase 2.7/2.8 pre-checks. Default for Low effort artifacts.

  When `--depth` is not specified, infer from the routing table's Effort column: High→thorough, Medium→standard, Low→quick. This is a UX refinement making existing implicit behavior explicit and user-overridable. `--depth quick` implies `--problems-only`.

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
   - Game dev / Unreal / DroneSim references → Sid route
   - Architectural changes, new subsystems, new abstractions → Patrik route
   - Front-end, CSS, UI components, tokens, design system → Palí route
   - ML/AI pipeline, model serving, RAG, data science → Camelia route
   - UX flow, user-facing feature, trust/clarity → Fru route
   - Cross-cutting changes (many files, new patterns) → Patrik route
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
| Game dev / Unreal / DroneSim | Sid | Patrik | Medium → Medium |
| Architectural change, new subsystem | Patrik | (backstop: Zolí) | High |
| Front-end, CSS, UI components | Palí | (backstop: Fru) | Medium |
| Front-end + architecture | Palí | Patrik | Medium → High |
| ML/AI pipeline, model serving, RAG | Camelia | Patrik | High → High |
| UX flow, user-facing feature | Fru | (backstop: Patrik) | Low → Medium |
| Cross-cutting (many files, new pattern) | Patrik | (backstop: Zolí) | High |
| Major DroneSim feature / new game mode | Sid | Patrik | High → High |
| Other / unmatched | Patrik | (none) | Medium |

**Depth resolution** (before dispatching):
1. If `--depth` was provided, use that
2. Else map from effort: High→thorough, Medium→standard, Low→quick

**Depth application:**
- `quick`: Force single reviewer, auto-apply `--problems-only`, skip Phase 2.7 and 2.8
- `standard`: Single reviewer (Reviewer 1 from routing), run Phase 2.7 if applicable
- `thorough`: Full dual-reviewer pipeline

### Phase 2.5: Write-Ahead Status Update

Before dispatching reviewers, mark the artifact's review status. If the artifact has a status header (plan doc, stub doc), update it:

```
**Status:** Under review by [Reviewer Name] (review started YYYY-MM-DD HH:MM)
```

If the artifact is code (no status header), note the review in the tracker or plan doc that references this work. The point is: if a crash happens mid-review, there's a breadcrumb showing what was being reviewed and by whom.

### Phase 2.7: API Verification (docs-checker, optional)

Before dispatching expensive Opus reviewers, optionally dispatch the **docs-checker** agent (Sonnet) to verify external API references in the artifact. This separates mechanical verification from architectural review — reviewers receive a pre-verified artifact and can skip their own API lookups.

**When to run:**
- Artifact contains UE API references (C++ headers, Blueprint nodes, engine classes)
- Artifact contains heavy external library usage (SDKs, frameworks)
- Effort level is Medium or High (skip at Low — not worth the extra dispatch)

**When to skip:**
- Doc-only or test-only changes
- Pure architectural changes with no API references
- Low effort reviews
- `--reviewers` override was specified (PM is directing the pipeline)

**Dispatch:**
1. Dispatch `docs-checker` agent with the artifact path
2. Save the verification report to `tasks/review-findings/{timestamp}-docs-checker.md`
3. If report contains INCORRECT claims: flag to coordinator before proceeding — the artifact may need fixes before review
4. Pass the report path to Opus reviewers in their dispatch prompt: "A docs-checker verification report is available at [path]. Trust VERIFIED claims — focus your review on architecture and design."

**On docs-checker failure:** Proceed to Phase 2.8 and Phase 3 without the report. Reviewers fall back to their own verification. This phase is additive, not blocking.

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
- **`/delegate-execution`** follows after review-dispatch approves artifacts for execution
