---
name: enrich-and-review
description: "Runs the enrichment pipeline over plan chunk directories."
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[stub-ids|directory-path|'all']"
---

# Enrich and Review — Enrichment Pipeline for Plan Stubs

Run the enrichment-review pipeline on a chunk directory: dispatch Sonnet enricher agents, then
Opus reviewers (review § A.3). Every phase below is a manual EM procedure; worked detail: wiki.

Never a stage of an engineering ask's one submission or its relay fallback: it serves backlog runs
and hands-on re-plans.

<!-- Single-sourced at snippets/project-rag-preamble.md; synced by `bin/verify-snippet-sync
     project-rag-preamble --check/--fix`. Edit the source, never this block. -->
<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->

**Code lookup: project-rag first.** Whenever project-rag's CLI, MCP tools or registry entry is present it is the primary path: engine facts and symbol questions (definitions, callers, members) go to its tools before Grep/Glob; Grep is for literal text. Grep/Read stays available (never a prohibition); a project-rag shortfall is reported to project-rag as a gap, not silently routed around.

First action, when `mcp__project-rag__*` tools are present (they arrive deferred): `ToolSearch("select:mcp__project-rag__project_staleness_check,mcp__project-rag__project_symbol_brief,mcp__project-rag__project_lsp_definition,mcp__project-rag__project_lsp_hover,mcp__project-rag__project_code_outline,mcp__project-rag__project_symbol,mcp__project-rag__project_rag_instructions")`
Then `project_staleness_check(repo=<repos.* key>)`.
Pass `repo=<repos.* key>` on every project-rag call; its key is a `repos.` row of `machine-local keys`. An answer from the wrong repo is a miss.
Shape -> tool: symbol `project_symbol_brief(symbol_name=X, lsp=true)` first; type/location `project_lsp_definition`/`project_lsp_hover(file=, line=, name=)`; a file's symbols `project_code_outline(file=)`; exact-name identity `project_symbol(symbol_name=X)`; else `project_rag_instructions`.
Bodies and members: load `project_symbol_source` by name; a `project_symbol` stub is not "corpus can't answer".
**Enumeration is not a lookup.** "What exists?" (target list, file set, coverage count, "is X covered?") is answered by walking the filesystem, never by an index; use project-rag to understand what the walk found.
If a project-rag call errors, retry it once; retry a substring timeout by exact name.
A miss after the retry never ends your task: the failed call counts as an attempt; use Grep/Read scoped to named paths, carry on, and report the call, its output and the fallback to project-rag as a gap. The engine alone aborts a run. No project-rag CLI, MCP or registry entry at all: Grep/Read.
Executors only: an executor working from a plan's cited facts needs no fresh lookup; a new fact it needs and cannot get stops that row only.
**Every grep is scoped**: `git grep` or the Grep tool on named paths in your own repo; never search recursively from a repo root, `..`, a sibling checkout or a drive (`A-RECURSIVE-GREP-FROM-A-REPO-ROOT-STALLS-THE-BOX`). A search constraint in your brief or `em_context` binds you, even when project-rag is down.
Friction: memo `project-rag-em` / `gh issue create -R dbc-oduffy/project-rag`.
<!-- END project-rag-preamble -->

## Arguments

`$ARGUMENTS`: a directory path → chunk directory; specific stub IDs ("2A 2B 2C") → enrich only
those; "all" → everything at "Pending enrichment"; `--reviewers "name1,name2"` → explicit
reviewer override, dispatched in listed order (first = domain pass, second =
architectural/generalist), replacing Phase 5 auto-detection (PM-directed dual review).

## Phase 0: Plan Review Gate

HALT before enriching anything unless the source plan's header carries a `**Review:**` line
matching "Reviewed by [name] on [date]", "Skipped per PM direction", or the byte-exact marker
string pinned at `coordinator/skills/staff-session/SKILL.md` Step 8, item 2 (read it from there,
never hand-type a second copy). No match → "This plan has not been through review. Route it
through `/review` first, or confirm PM override to skip."
<!-- engine-gap: field=plan.review_marker_present producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

## Phase 1: Discover Stubs

Read the tracker README/chunk index; classify each stub at "Pending enrichment" as survey-type
(external assets, unfamiliar codebases), plan-type (known codebase, file paths + steps), or
manual (non-delegatable). Report the split.

## Phase 2: Independence Verification

Before parallel dispatch, build a file→stub map from each stub's Files-Affected/Scope; stubs
sharing a file enrich sequentially. Report the parallel/sequential split.
<!-- engine-gap: field=tracker.stub_file_overlap producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->

## Phase 2.5: Write-Ahead Status Update

Before dispatching any enrichers: `tracker.advance_status`
(`coordinator_core/ops/tracker/advance_status.py`) with `tracker_path=<tracker README>`,
`stub_ids=<about-to-be-enriched>`, `to_status="Enrichment in progress"` — flips status atomically,
does NOT self-commit. **Commit the tracker README change (scoped) immediately after, before any
enricher launches** — the commit makes the WAL record durable, not the op call.

**Negative-spec:** this op's write target (a caller-supplied tracker README path) carries no
ratified DR carve-out; check the op's "Provisional classification" docstring note first.

## Phase 3: Dispatch Enrichers

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

Optional repo map via `misc-session-and-guards.py rag-freshness-gate` (pass its path in the
prompt). Run enabled plugins' root-level `enricher-pre-pass.md` fragments in your own context and
name their artifacts in enricher prompts; fold `enricher-survey.md` fragments matching
`project_type` into the survey-type prompt (fall back to the enricher's generic protocol if none match).

Independent stubs → parallel Sonnet enrichers (`Task`, `subagent_type: "enricher"`,
`model: "sonnet"`, `run_in_background: true`, single message). Dependent stubs → sequential.
Manual stubs → report to PM/Coordinator.

## Phase 4: Resolve Coordinator Flags

Read each enriched stub for `NEEDS_COORDINATOR:` flags, decide from project context/design
docs/PM direction, write the resolution back replacing the flag. Escalate if uncertain.

## Phase 4.5: Pre-Review Status Update

Same op as Phase 2.5 with `stub_ids=<enriched stubs>`, `to_status="Under review"`; commit
immediately after.

## Phase 5: Dispatch Reviewers

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

Selection: explicit `--reviewers` override, or auto-detect (classify enriched-stub work type,
merge this plugin's `routing.md` with every enabled plugin's root-level `routing.md` fragment,
match). **Persist findings to the provisioned sidecar, no EM pre-scaffold** — each reviewer's
brief carries its `state/subagent-share/<session>/<provision_key>.md` path
(`provision_report`-injected); the reviewer writes ReviewOutput there and returns `DONE:
<sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>` (detail: wiki).

Both reviewers dispatch in parallel over all enriched stubs (single message, review § A.3),
then one fix pass runs over the union of their findings with one applied-and-verified gate:
every finding applied and checked (spot-checked diff) against the returned sidecar paths. A
single reviewer gets the same fix pass over its own findings. Conflicting feedback: apply unless
it conflicts with stated requirements or PM direction, document overrides in the stub, escalate
genuine uncertainty.

**The enriched-artifact duty is contract, not brief text.** The contract is injected at dispatch
for every `REVIEWER_ROSTER` member. A resolved reviewer whose `contract_blocks:` row in
`coordinator/subagent-sandbox-policy.yaml` does not list `enriched-artifact-review-contract`, or
that has no row, gets the **path** `coordinator/snippets/enriched-artifact-review-contract.md` in
its dispatch, never a paraphrase: no brief restates the duty's text
(`A-DUTY-ONLY-A-BRIEF-CARRIES-DISAPPEARS-WITH-THE-EM`).

## Phase 6: Update Tracker

Same op with `stub_ids=<reviewed stubs>`, `to_status="Enriched and reviewed"`, commit immediately
after. Note manual-flagged stubs and any needing PM decision.

## Completion

Report: stubs enriched, stubs reviewed (and by whom), outstanding flags/PM decisions, which stubs
are ready for executor dispatch, and — when this ran unattended — the accepted losses at
`state/audits/2026-09-07-em-carried-obligations-census/accepted-losses.md`, named, not summarised:
four duties on this path have no carrier once no EM is in the loop, and the report is where an
operator learns the run did not perform them.
