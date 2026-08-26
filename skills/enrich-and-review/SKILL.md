---
name: enrich-and-review
description: "Runs the enrichment pipeline over plan chunk directories."
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[stub-ids|directory-path|'all']"
---

# Enrich and Review — Enrichment Pipeline for Plan Stubs

Run the enrichment-review pipeline on a chunk directory: dispatch Sonnet enricher agents, then
Opus reviewers, sequentially. Nothing computes this pipeline for you yet — every phase below is a
manual EM procedure over theoretically claude-klabauter-izable facts (stub discovery, independence
verification, status transitions); worked detail and phase archaeology: wiki.

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

## Arguments

`$ARGUMENTS`: a directory path → chunk directory; specific stub IDs ("2A 2B 2C") → enrich only
those; "all" → enrich everything at "Pending enrichment"; `--reviewers "name1,name2"` → explicit
reviewer override, dispatched in listed order (first = domain pass, second =
architectural/generalist), replacing Phase 5 routing-table auto-detection — the mechanism for
PM-directed dual-review setups.

## Phase 0: Plan Review Gate

HALT before enriching anything unless the source plan's header carries a `**Review:**` line
matching "Reviewed by [name] on [date]", "Skipped per PM direction", or the byte-exact marker
string pinned at `coordinator/skills/staff-session/SKILL.md` Step 8, item 2 (produced by
`/staff-session --mode plan` Step 8 — read it from there, never hand-type a second copy). No match
→ "This plan has not been through review. Route it through `/review` first, or confirm PM override
to skip." Prevents wasting enrichment cycles on a structurally unreviewed plan.
<!-- engine-gap: field=plan.review_marker_present producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

## Phase 1: Discover Stubs

Read the tracker README/chunk index, identify stubs at "Pending enrichment" or equivalent,
classify each survey-type (external assets, unfamiliar codebases), plan-type (known codebase, file
paths + steps), or manual (non-delegatable). Report the split.
<!-- engine-gap: field=tracker.stub_classification producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

## Phase 2: Independence Verification

Before parallel dispatch, read each stub's Files-Affected/Scope, build a file→stub map, force
sequential enrichment for stubs sharing a file. Report the parallel/sequential split.
<!-- engine-gap: field=tracker.stub_file_overlap producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

## Phase 2.5: Write-Ahead Status Update

Before dispatching any enrichers: `tracker.advance_status`
(`coordinator_core/ops/tracker/advance_status.py`) with `tracker_path=<tracker README>`,
`stub_ids=<about-to-be-enriched>`, `to_status="Enrichment in progress"` — flips status atomically,
does NOT self-commit. **Commit the tracker README change immediately after, before any enricher
launches** (scoped commit) — the commit is what makes the WAL record durable, not the op call.

**Negative-spec:** this op's write target (a caller-supplied tracker README path) carries no
ratified DR carve-out — check the op's own "Provisional classification" docstring note before
treating its authority here as settled.

## Phase 3: Dispatch Enrichers

Optional task-scoped repo map via `misc-session-and-guards.py rag-freshness-gate` when the stub's
file scope benefits from one — pass its path in the dispatch prompt (judgment call, not every
dispatch needs it). Scan enabled plugins for root-level `enricher-pre-pass.md` fragments — these
run in the EM's own context (full tool access, MCP) to gather what the enricher's tools can't reach
(e.g. live Blueprint property surfaces); include their companion-artifact paths in enricher
prompts. Separately scan for `enricher-survey.md` fragments matching `project_type` and fold into
the survey-type dispatch prompt (fall back to the enricher's generic protocol if none match).

Independent stubs → parallel Sonnet enricher dispatch (`Task`, `subagent_type: "enricher"`,
`model: "sonnet"`, `run_in_background: true`, single message). Dependent stubs → sequential,
waiting for each to complete. Manual stubs → report to PM/Coordinator.

## Phase 4: Resolve Coordinator Flags

Read each enriched stub for `NEEDS_COORDINATOR:` flags, decide from project context/design
docs/PM direction, write the resolution back replacing the flag. Escalate if uncertain.

## Phase 4.5: Pre-Review Status Update

Same op as Phase 2.5 with `stub_ids=<enriched stubs>`, `to_status="Under review"`; commit
immediately after.

## Phase 5: Dispatch Reviewers

Selection: explicit `--reviewers` override, or auto-detect (classify enriched-stub work type,
merge this plugin's `routing.md` with every enabled plugin's root-level `routing.md` fragment,
match). **Persist findings to the provisioned sidecar, no EM pre-scaffold** — each reviewer's
dispatch brief carries its `state/subagent-share/<session>/<provision_key>.md` path
(`provision_report`-injected); reviewer writes ReviewOutput there and returns `DONE: <sidecar-path>
| verdict: <OK|WARN|BLOCKED> | findings: <N>` (detail: wiki).

Sequential dispatch with fix-application gate: dispatch Reviewer 1 (scope = all enriched stubs;
must validate both the implementation plan AND the enrichment assumptions) → STOP, dispatch
review-integrator against the returned sidecar path, apply every finding, spot-check the diff →
only then dispatch Reviewer 2 on the corrected stubs (fresh sidecar path, no injection needed) →
STOP, integrate again the same way. Single-reviewer case skips the second pass but keeps the
fix-application step. Conflicting feedback: apply unless it conflicts with stated requirements or
PM direction, document overrides with rationale in the stub, escalate genuine uncertainty.

## Phase 6: Update Tracker

Same op with `stub_ids=<reviewed stubs>`, `to_status="Enriched and reviewed"`, commit immediately
after. Note manual-flagged stubs and any needing PM decision.

## Completion

Report: stubs enriched, stubs reviewed (and by whom), outstanding flags/PM decisions, which stubs
are ready for executor dispatch.
