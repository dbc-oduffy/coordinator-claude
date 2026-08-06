---
name: enrich-and-review
description: "Runs the enrichment pipeline over plan chunk directories."
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[stub-ids|directory-path|'all']"
---

# Enrich and Review — Enrichment Pipeline for Plan Stubs

Run the enrichment-review pipeline on a chunk directory, dispatching Sonnet enricher agents and Opus reviewers sequentially.

<!-- Negative-spec: this block is single-sourced at snippets/project-rag-preamble.md and kept in
     sync across every consumer (this file, the plan-writing doctrine wiki, enricher/executor/
     review-integrator dispatch prompts, scout templates) by an automated gate —
     `bin/verify-snippet-sync project-rag-preamble --check/--fix`, wired into /workday-start
     Step 1.7. Do not fold or hand-edit this block independently — edit the source and let the
     gate sync. -->
<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
**Project-rag is project-scoped.** It indexes ONE specific codebase, configured at install time. Before reaching for `mcp__*project-rag*` tools, confirm they index the codebase you're investigating — not a different project on the same machine. If your target codebase doesn't have a project-rag index (no `Saved/ProjectRag/` marker at its root, no `--project-root` argument pointing at it in the MCP config), skip this preamble entirely and use grep/Explore.

**If MCP tools matching `mcp__*project-rag*` are available AND they index the codebase you're investigating, prefer them over grep/Explore for any code-shaped lookup.** Symbol-shaped questions ("where is X defined", "find the function that does Y") → `project_cpp_symbol` / `project_semantic_search`. Subsystem-shaped questions ("how does X work") → `project_subsystem_profile`. Impact questions ("what breaks if I change X") → `project_referencers` with depth=2. Stale RAG still beats grep on structure. Fall through to grep/Explore only if RAG returns nothing AND staleness is plausible.
<!-- END project-rag-preamble -->

## Instructions

When invoked, run the full enrichment pipeline on a chunk directory containing plan stubs.

If `$ARGUMENTS` is provided, use it to scope the work:
- A directory path → use as the chunk directory
- Specific stub IDs (e.g., "2A 2B 2C") → enrich only those stubs
- "all" → enrich everything with status "Pending enrichment"
- `--reviewers "name1,name2"` → explicit reviewer override (e.g., `--reviewers "sid,the Staff Engineer"`). When provided, this replaces routing table auto-detection in Phase 5. Reviewers are dispatched in the order listed — first is domain pass, second is architectural/generalist pass. This is the mechanism for PM-directed dual-review setups.

### Phase 0: Plan Review Gate

Before enriching anything, verify the source plan has been reviewed:

1. Check the plan document header for a `**Review:**` line
2. If it matches any of these patterns → proceed:
   - "Reviewed by [name] on [date]"
   - "Skipped per PM direction"
   <!-- Marker-string pin, consumer side: the third pattern is produced by
   `/staff-session --mode plan`'s Step 8. The single authoritative copy of the byte-exact string
   lives at `coordinator/skills/staff-session/SKILL.md` Step 8, item 2 — read it from there when
   checking the plan header. Do not hand-type a second copy of the string in this file. -->
   - The byte-exact marker string pinned at `coordinator/skills/staff-session/SKILL.md` Step 8,
     item 2 (produced by `/staff-session --mode plan`'s Step 8 — the F4 producer copy)
3. If no review marker exists → **HALT** and report:
   - "This plan has not been through review. Route it through `/review` first, or confirm PM override to skip."
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

Invoke the advance-tracker-status op — claude-klabauter's `tracker.advance_status`
(`coordinator_core/ops/tracker/advance_status.py`, `register_op "tracker.advance_status"`) — with
`tracker_path=<tracker README>`, `stub_ids=<about-to-be-enriched stubs>`,
`to_status="Enrichment in progress"`. It flips each named stub's status line atomically and does
NOT self-commit — the op's own module docstring is explicit that a handler-issued git commit would
be a second, independent boundary crossing on top of an already-uncarved-out write target, and that
every existing carve-out except the fleet-archival family forbids it. **Commit the tracker README
change immediately after the op returns, before any enricher launches** (scoped commit)
— this EM-issued commit is what makes the WAL record durable, not the op call itself.
<!-- Negative-spec: this op's write target (a caller-supplied tracker README path) carries no
ratified DR carve-out — check the op's own "Provisional classification" docstring note before
treating its authority here as settled. -->

This ensures that if the session crashes mid-enrichment, the tracker shows "in progress" rather than misleading "pending." The enricher agents will also mark their individual stub documents (per the enricher's write-ahead protocol), creating two layers of breadcrumbs.

### Phase 3: Dispatch Enrichers

**Optional: Task-scoped repo map.** Before dispatching enrichers, consider whether the stub's file scope is clear enough to benefit from a focused map. If so, gate and generate via the ported `misc-session-and-guards.py rag-freshness-gate` subcommand (checks freshness, generates the map only when stale, no-ops when `generate-repomap.py` is unresolvable) — `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/misc-session-and-guards" rag-freshness-gate --project-root <project> --task "<stub summary>" --focus-files "<key files from stub>"`.

Pass the task-scoped map path to the enricher in its dispatch prompt. This is awareness-based — use judgment, not every dispatch needs it.

**Enricher pre-pass discovery.** Scan all enabled plugins for root-level `enricher-pre-pass.md` files. These are instructions that run in the **EM's context** (with full tool access — MCP, Agent dispatch, etc.) to gather information the enricher cannot access with its own tools. For example, a UE plugin might inspect live Blueprint property surfaces via MCP, since the enricher can only read source files.

If pre-pass fragments are found:
- Read each fragment
- Follow its instructions for each relevant stub (the fragment defines relevance criteria)
- The fragment will produce companion artifacts (inventories, screenshots, etc.) written to disk alongside the stubs
- Include companion artifact paths in the enricher dispatch prompts so enrichers get concrete data, not vague "use MCP" instructions

If no pre-pass fragments are found, skip this step — it's an optional extension point.

**Enricher-survey fragment discovery.** Before dispatching, scan all enabled plugins for root-level `enricher-survey.md` files (analogous to routing fragment discovery in `/review` and `/review-code`). If a matching fragment exists for the project's `project_type`:
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

Invoke the advance-tracker-status op (see Phase 2.5) with `stub_ids=<enriched stubs>`,
`to_status="Under review"` — flips the tracker atomically. Commit the tracker README change
immediately afterward (see Phase 2.5) — the op does not self-commit.

### Phase 5: Dispatch Reviewers

Determine which reviewers to summon and dispatch them sequentially.

**Reviewer selection** — two modes:

- **Explicit override** (`--reviewers` provided): Use the specified reviewers in order. First name is Reviewer 1 (domain), second is Reviewer 2 (generalist/architectural). Look up each reviewer's agent type and model from the composite routing table.
- **Auto-detect** (no override): Analyze the enriched stubs to determine work type (game dev, front-end, ML, architecture, etc.). Apply the routing table using dynamic discovery: read the base routing table from this plugin's `routing.md`, scan all enabled plugins for root-level `routing.md` fragments, merge, and match.

**Persist reviewer findings — provisioned subagent-share path, no EM pre-scaffold.** Each reviewer's dispatch brief carries its provisioned `state/subagent-share/<session>/<provision_key>.md` sidecar path, injected at spawn by `provision_report`, plus the doc-handoff contract: write ReviewOutput there and return the pointer line, not a dump — `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. EM reads the returned path and passes it to the integrator. There is no EM pre-scaffold (`coordinator-doc-new --type review` is not called), no injected `docs/plans/<stem>.review.md` path, no `cs_write_review_claim`, no sentinel-append, and no EM-persists-inline fallback.

**Sequential dispatch with fix-application gate:**

1. Dispatch Reviewer 1 via Task tool — include ALL enriched stubs in scope; its brief carries the provisioned subagent-share sidecar path. The reviewer writes findings there and returns `DONE: <sidecar-path>`.
2. **CRITICAL: Reviewers must validate BOTH the implementation plan AND the enrichment assumptions** — if an enricher misread the codebase, catch it now
3. **STOP. Dispatch review-integrator pointing at the on-disk sidecar path** (the path Reviewer 1 returned). The review-integrator applies every finding with annotations. Verify integrator output (check escalations, spot-check diff). The stubs must be clean and corrected before the next reviewer sees them. Do not dispatch Reviewer 2 on artifacts with known issues.
4. **Multi-reviewer chain — Reviewer 2:** Dispatch Reviewer 2 on the **corrected** stubs; its brief carries its own provisioned subagent-share sidecar path — no path injection from Reviewer 1 is needed. They should see fresh, clean work, not work with known bugs stapled on.
5. **STOP. Dispatch review-integrator pointing at the on-disk sidecar path** (the path Reviewer 2 returned) — apply with the same apply-everything protocol.

**Single-reviewer case:** If only one reviewer is selected (by routing or by `--reviewers "name"`), skip steps 4-5. The fix-application rule (step 3) still applies — all feedback is incorporated before marking review complete.

Decision protocol for conflicting feedback:
- Apply all feedback unless it conflicts with stated requirements or PM direction
- Document any overrides with rationale in the stub
- If genuinely uncertain: escalate to PM

### Phase 6: Update Tracker

1. Invoke the advance-tracker-status op (see Phase 2.5) with `stub_ids=<reviewed stubs>`,
   `to_status="Enriched and reviewed"`, then commit the tracker README change immediately
   afterward (see Phase 2.5) — the op does not self-commit
2. Note any stubs that were flagged as manual
3. Note any stubs where reviewer feedback requires PM decision
4. Report summary: "Enrichment complete. N stubs ready for execution. M require PM decision. K are manual."

### Completion

Report the final state:
- How many stubs were enriched
- How many were reviewed and by whom
- Any outstanding flags or PM decisions needed
- Which stubs are now ready for executor dispatch
