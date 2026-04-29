---
description: Run enrichment pipeline on chunk directories
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[stub-ids|directory-path|'all']"
---

# Enrich and Review — Enrichment Pipeline for Plan Stubs

Run the enrichment-review pipeline on a chunk directory, dispatching Sonnet enricher agents and Opus reviewers sequentially.

## Instructions

When invoked, run the full enrichment pipeline on a chunk directory containing plan stubs.

If `$ARGUMENTS` is provided, use it to scope the work:
- A directory path → use as the chunk directory
- Specific stub IDs (e.g., "2A 2B 2C") → enrich only those stubs
- "all" → enrich everything with status "Pending enrichment"
- `--reviewers "name1,name2"` → explicit reviewer override (e.g., `--reviewers "sid,patrik"`). When provided, this replaces routing table auto-detection in Phase 5. Reviewers are dispatched in the order listed — first is domain pass, second is architectural/generalist pass. This is the mechanism for PM-directed dual-review setups.

### Phase 0: Plan Review Gate

Before enriching anything, verify the source plan has been reviewed:

1. Check the plan document header for a `**Review:**` line
2. If it matches any of these patterns → proceed:
   - "Reviewed by [name] on [date]"
   - "Skipped per PM direction"
   - "Staff session ([participants]) — debated and synthesized" (from `/staff-session --mode plan`)
3. If no review marker exists → **HALT** and report:
   - "This plan has not been through review. Route it through `/review-dispatch` first, or confirm PM override to skip."
4. Do NOT proceed to Phase 1 until the gate is satisfied

This prevents wasting enrichment cycles on a plan with structural problems.

### Phase 1: Discover Stubs

1. Read the tracker README (or chunk index) in the target directory
2. Identify stubs with status "Pending enrichment" or equivalent
3. Classify each stub:
   - **Survey-type**: Involves external assets, marketplace packs, unfamiliar codebases → needs survey sub-phase
   - **Plan-type**: Involves known codebase, needs file paths and implementation steps → needs plan sub-phase
   - **Manual**: Requires manual editor work, screenshots, or physical interaction → flag as non-delegatable
4. Report the discovery: "Found N stubs pending enrichment: X survey-type, Y plan-type, Z manual"

### Phase 2: Independence Verification

Before parallel dispatch, check whether stubs share files:

1. Read each stub's "Files Affected" and "Scope" sections
2. Build a map: file path → list of stubs that reference it
3. If any file appears in multiple stubs: those stubs MUST be enriched sequentially
4. Report: "N stubs can be enriched in parallel. M stubs have overlapping files and will be sequenced."

### Phase 2.5: Write-Ahead Status Update

**Before dispatching any enrichers**, mark every stub that is about to be enriched:

1. Update the tracker README: change each stub's status from "Pending enrichment" → **"Enrichment in progress"**
2. Commit this tracker update immediately (this is the WAL record — it must persist before agents launch)

This ensures that if the session crashes mid-enrichment, the tracker shows "in progress" rather than misleading "pending." The enricher agents will also mark their individual stub documents (per the enricher's write-ahead protocol), creating two layers of breadcrumbs.

### Phase 3: Dispatch Enrichers

**Optional: Task-scoped repo map.** Before dispatching enrichers, consider whether the stub's file scope is clear enough to benefit from a focused map. If so, generate one:
```
Invoke `/generate-repomap` with task-scoped flags:
```bash
/generate-repomap --project-root <project> --task "<stub summary>" --focus-files "<key files from stub>"
```
Pass the task-scoped map path to the enricher in its dispatch prompt. This is awareness-based — use judgment, not every dispatch needs it.

**Enricher pre-pass discovery.** Scan all enabled plugins for root-level `enricher-pre-pass.md` files. These are instructions that run in the **EM's context** (with full tool access — MCP, Agent dispatch, etc.) to gather information the enricher cannot access with its own tools. For example, a UE plugin might inspect live Blueprint property surfaces via MCP, since the enricher can only read source files.

If pre-pass fragments are found:
- Read each fragment
- Follow its instructions for each relevant stub (the fragment defines relevance criteria)
- The fragment will produce companion artifacts (inventories, screenshots, etc.) written to disk alongside the stubs
- Include companion artifact paths in the enricher dispatch prompts so enrichers get concrete data, not vague "use MCP" instructions

If no pre-pass fragments are found, skip this step — it's an optional extension point.

**Enricher-survey fragment discovery.** Before dispatching, scan all enabled plugins for root-level `enricher-survey.md` files (analogous to routing fragment discovery in `/review-dispatch`). If a matching fragment exists for the project's `project_type`:
- Read the fragment file
- Include its content in the enricher dispatch prompt as domain-specific survey instructions
- If no fragment matches, the enricher uses its generic survey protocol

This is how domain-specific survey knowledge (e.g., UE project structure scanning) reaches the enricher without polluting the coordinator-core agent spec.

For independent stubs — dispatch Sonnet enricher agents in parallel:
- Use `Task` tool with `subagent_type: "enricher"`, `model: "sonnet"`, and `run_in_background: true`
- Each agent gets: the stub document path, the project root, and instruction to follow the enricher agent protocol
- If a task-scoped map was generated, include its path in the dispatch prompt
- Launch independent agents in a single message for parallel execution

For dependent stubs — dispatch sequentially, waiting for each to complete before starting the next.

For manual stubs — report them to the PM/Coordinator as requiring human action.

### Phase 4: Resolve Coordinator Flags

After all enrichers complete:

1. Read each enriched stub for `NEEDS_COORDINATOR:` flags
2. For each flag: make the architectural decision based on project context, design docs, and PM direction
3. Write the resolution back into the stub document, replacing the flag
4. If uncertain about a flag: escalate to PM before resolving

### Phase 4.5: Pre-Review Status Update

Before dispatching reviewers, update status to reflect the transition:

1. Update the tracker README: change each enriched stub's status to **"Under review"**
2. Commit this tracker update

### Phase 5: Dispatch Reviewers

Determine which reviewers to summon and dispatch them sequentially.

**Reviewer selection** — two modes:

- **Explicit override** (`--reviewers` provided): Use the specified reviewers in order. First name is Reviewer 1 (domain), second is Reviewer 2 (generalist/architectural). Look up each reviewer's agent type and model from the composite routing table.
- **Auto-detect** (no override): Analyze the enriched stubs to determine work type (game dev, front-end, ML, architecture, etc.). Apply the routing table using dynamic discovery: read the base routing table from this plugin's `routing.md`, scan all enabled plugins for root-level `routing.md` fragments, merge, and match.

**Sequential dispatch with fix-application gate:**

1. Dispatch Reviewer 1 via Task tool — include ALL enriched stubs in scope
2. **CRITICAL: Reviewers must validate BOTH the implementation plan AND the enrichment assumptions** — if an enricher misread the codebase, catch it now
3. **STOP. Dispatch review-integrator to apply Reviewer 1 feedback.** The review-integrator applies every finding with annotations. Verify integrator output (check escalations, spot-check diff). The stubs must be clean and corrected before the next reviewer sees them. Do not dispatch Reviewer 2 on artifacts with known issues.
4. Dispatch Reviewer 2 on the **corrected** stubs — they should see fresh, clean work, not work with known bugs stapled on
5. Incorporate Reviewer 2's feedback with the same apply-everything protocol

**Single-reviewer case:** If only one reviewer is selected (by routing or by `--reviewers "name"`), skip steps 4-5. The fix-application rule (step 3) still applies — all feedback is incorporated before marking review complete.

Decision protocol for conflicting feedback:
- Apply all feedback unless it conflicts with stated requirements or PM direction
- Document any overrides with rationale in the stub
- If genuinely uncertain: escalate to PM

### Phase 6: Update Tracker

1. Update each stub's status in the tracker README: "Pending enrichment" → "Enriched and reviewed"
2. Note any stubs that were flagged as manual
3. Note any stubs where reviewer feedback requires PM decision
4. Report summary: "Enrichment complete. N stubs ready for execution. M require PM decision. K are manual."

### Completion

Report the final state:
- How many stubs were enriched
- How many were reviewed and by whom
- Any outstanding flags or PM decisions needed
- Which stubs are now ready for `/delegate-execution`
