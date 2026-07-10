---
title: Addon Receiver Scaffold (Wave 2a)
created: 2026-05-08
status: active
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-08-ue-carveout-wave-2.md §D-1 §"Wave 2a" -->
<!-- Spec backlink: tasks/ue-carveout-wave-2/PR-9-receiver-harness.md -->

# Addon Receiver Scaffold (Wave 2a)

The doctrine behind Wave-2a's "scaffold first, extract later" approach. Read
this before authoring Wave 2b/2c PRs or onboarding a second addon.

## Receiver-scaffold-first principle

Wave 2a lands seams, hookspecs, façade types, and discovery machinery. **No
UE code physically moves.** UE producers, extractors, MCP tools, and graph
extractors stay in their current `priming/`, `project_rag_mcp/`, and `project_rag_mcp/graph/`
locations through Wave 2a; the seams route through pluggy hookspecs but
the implementation bodies are unchanged.

**Rationale:** the scaffold pass separates seam-design risk from
physical-extraction risk. example-sim-repo can confirm non-functional change
against scaffold before extraction begins. If shakedown surfaces a
behavior change, the diff to investigate is bounded — it's the seam
plumbing, not 5,000 lines of relocated code.

**Contrast with "big bang":** physical extraction in one wave increases
rollback cost and example-sim-repo regression risk. The scaffold + extract split
makes both phases verifiable independently.

## Project-type gate philosophy

Wave 2a uses a **provisional project-type gate** — `_detected_project_type == "unreal"`
controls whether the UE extractor / chunker / MCP tool registrations
activate. The detection lives in `core/project_type.py` (`detect()`
returning `"unreal" | "ts" | "rust" | "python" | "generic"`).

- **v0 gate (Wave 2a, scaffold):** `if project_type == "unreal":` blocks
  in `priming/consumer_runner.py` and `project_rag_mcp/project_rag_server.py`. These
  blocks gate the in-tree UE registrations against project type.
- **v1 gate (Wave 2b, physical extraction):** pluggy hookimpl presence
  replaces the conditional. Physical extraction is what flips the gate
  from provisional (project-type-conditional in core) to structural
  (presence-of-addon).

**Provisional gate comment convention.** Every v0 gate block must include
the canonical phrase:

```
# PROVISIONAL — Wave-2a project-type gate; replace with addon hookimpl in Wave 2b physical extraction
```

The phrase is greppable across `priming/`, `project_rag_mcp/`, `core/` so the Wave-2b
executor can find every site in one query. Tripwire test
`tests/structural/test_provisional_gate_comment.py` (AC-16) enforces the
phrase at every detected gate site.

## In-tree-but-behind-seam pattern

UE code stays in:

- `priming/producers/` — UE producer modules
- `project_rag_mcp/tools/` — UE-flavored MCP tools (`project_blueprint_graph`,
  `project_tag_graph`, `project_asset_registry`, `project_cvar`,
  `project_test_coverage`, `project_actor_composition`, `project_overrides`)
- `project_rag_mcp/graph/extractor.py` — extractor functions for graph.db population

The **seams** are the hookspec call sites: boot, producer registration,
extractor registration, chunker registration, preflight. The host iterates
the registered hookimpls; in Wave 2a, the in-tree registrations look
identical to addon-supplied registrations from the host's perspective.
The physical move (Wave 2b) rewrites only the hookimpl call site; the UE
code body is unchanged.

**OSS-foreclosure advisory (E-1 risk).** If OSS publish lands before Wave 2b,
UE code ships in the OSS repo. Surface this to PM before any OSS publish
discussion — Wave 3 rename + Wave 2b physical extraction must precede OSS.

## Scaffold-vs-physical-extraction split

| Wave | Action | UE code location |
|---|---|---|
| **2a (scaffold)** | Seams, hookspecs, façade, harness, docs | In-tree (`priming/`, `project_rag_mcp/`) |
| **2b (extraction)** | Move UE producers/tools to example-game-repo addon | Addon (`example_game_workbench_repo.project_rag_addon`) |
| **2c (terminal)** | Schema carve-out (move UE DDL + UE edge types to addon hookimpl, narrow `CORE_EDGE_TYPES`), `WrongProjectError`/`SentinelLoadError` removal | Post Phase 1 hookspec contract green |

The Wave-2c terminal step is what unlocks the schema carve-out.
The trigger condition is hookspec contract solid: both
`project_rag_register_schema_tables` and
`project_rag_register_schema_edge_types` have a parse-test and
a round-trip fixture-addon test green (per Phase 1 ACs). A
second installed addon is not a precondition. Authority: plan
§(b) "B-3 disposition"
(`docs/plans/2026-05-16-phase-1-addon-extensible-schema.md`).

*(Updated 2026-05-16) "requires a second addon to validate the
migration contract" precondition retired per PM disposition;
hookspec-contract-solid gate replaces it.*

## Corpus §5 architectural calls cross-reference

Cross-references to `docs/research/2026-05-08-ue-carveout/` architectural
calls (verbatim corpus references for downstream debaters):

- **A-1 Option 2:** receiver identity → example-game-repo core
- **A-2:** pluggy + entry-points + manifest + capability dict (Pattern 4)
- **B-1 through B-6:** six seam resolutions
  - B-1: MCP tool registry → `MCPToolRegistry` (PR-6)
  - B-2: extractor registry → `priming/extractor_registry.py` (PR-2)
  - **B-3: schema ownership FROZEN** — see Wave-2 scope notes
  - **B-4: `_VALID_SOURCES` FROZEN** — see Wave-2 scope notes
  - B-5: chunker extender → `chunker_extender` kwarg + entry-points scan (PR-4)
  - B-6: provenance priority bands (PR-3)
- **C-1 through C-5:** subsystem relocation plan
  - C-1: editor preflight hook (PR-7)
  - C-2: project-validity check hook (PR-7)
  - C-3: doctor probe inventory accommodation (PR-9, this PR)
  - C-4: bridge protocol versioning (PR-8)
  - C-5: addon manifest schema (PR-5)
- **D-1:** wave structure (three-stage: 2a scaffold → 2b extract → 2c terminal)

## What changes for existing contributors

- **New chunker:** register via `indexer/chunker_registry.py` (unchanged
  from pre-Wave-2a; `chunker_extender` kwarg added in PR-4 lets addons
  contribute additional chunkers without editing the core registry).
- **New extractor:** register via `priming/extractor_registry.py` (NEW
  in PR-2 — replaces the old `_CONSUMER_DISPATCH` dict).
- **New MCP tool:** register via the `mcp_tool_registry` iteration in
  `_boot_server()` (NEW in PR-6 — replaces the ~150-line register-call
  cascade).
- **New provenance classifier:** use `@_register(priority=N)` in the UE
  band (100–199) for UE-related classifiers; pick a distinct value to
  avoid the within-band collision warning.
- **Tests:** use `ReceiverHarness` from `tests/addons/receiver_harness.py`
  for any contract test exercising the addon protocol surface. The harness
  registers a synthetic addon with recording-body hookimpls and exposes
  seven assertion helpers covering all six hookspecs plus the Wave-2c
  schema-migration stub.

See [`addon-protocol.md`](addon-protocol.md) for the formal contract
(façade types, hookspec signatures, `PreflightVerdict` enum semantics,
manifest schema, capability dict shape, failure modes).
