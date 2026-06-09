---
kind: wiki
title: project-rag MCP Self-Declaration and Content-Class Routing
status: active
created: 2026-05-24
sources:
  - docs/plans/2026-05-18-project-rag-mcp-self-declaration-and-content-class-routing.md
  - docs/plans/2026-05-21-doe-side-mcp-registration-visibility-and-drift-audit.md
  - cross-repo/archive/2026-05-23-project-rag-host-configure-not-edit-framing.md
  - archive/specs/2026-04-29-project-rag-readiness.md
tags: [project-rag, mcp, content-class-routing, self-declaration]
---

# project-rag MCP Self-Declaration and Content-Class Routing

> See also: project-rag-tool-envelope.md

## Why runtime self-declaration exists

Before 2026-05-18, project-rag did not declare its content-class topology or bug-ownership boundary on any runtime surface. The failure that motivated this work: a consumer connected to the project-rag MCP port, encountered a daemon-layer regression, and routed to the wrong doctor (`/project-rag-ue-addon:doctor` instead of `/project-rag:doctor`) because no in-band signal indicated that the failure was host-owned.

Four documentation-substrate roots (this wiki, `host-vs-addons.md`, `corpus-class-taxonomy.md`, `standalone-vs-ue-augmented.md`) are necessary but insufficient. The load-bearing intervention is runtime self-declaration: a consumer who has never read any wiki still receives content-class and bug-ownership signal at the moment they select a tool. Four declaration surfaces:

1. `FastMCP(instructions=...)` — ≤200 words, loaded at MCP connection time
2. `project_rag_instructions()` tool body — detailed routing table, enumerated at session start
3. Per-tool `ToolAnnotations` — machine-readable capability metadata
4. Description tag prefixes — content-class signal embedded in every tool description

## FastMCP(instructions=...) constraints

The `FastMCP(instructions=...)` block is ≤200 words and leads with content-class routing (primary) then query-shape routing (secondary) then bug-ownership statement.

**Content-agnostic invariant (the Director of Engineering Directive 1):** Host text must contain NO addon names or engine-specific vocabulary. Banned regex: `\b(blueprint|bp_|unreal|holodeck|uproject|umap|uasset)\b` — also "BPs"; no `UCharacterMovementComponent`-shape exemplars; no `r.DroneSim.EnableFlight`-shape CVar names. Generic content-class phrasing throughout.

**Vocabulary pin:** "addon-registered" (not "addon-contributed") for addon-supplied corpus classes.

**Tripwire:** `tests/addons/test_v5_hookspec_naming.py` scans `FastMCP(instructions=...)` text AND host-native tool description strings for banned vocab. Host-native error hints / log lines / docstring prose are out of scope (may legitimately quote corpus-class concepts to flag as unsupported).

## Routing table structure (project_rag_instructions())

Two-axis routing: content class first, query shape second.

**Content-class axis:**
- Consumer-project content (indexed project under `--project-root`): `project_file`, `project_semantic_search`, `project_referencers`, `project_subsystem_profile`, and addon-supplied composition/graph tools when an engine addon is installed.
- Engine-corpus content (addon-registered first-party APIs): tools registered by the active engine addon — call `project_rag_instructions()` to enumerate at runtime.
- Cross-class blend: `project_rag_blended_query`.

**Query-shape axis (within a content class):**
- Identity / enumeration / reachability → graph-SQL tools (`project_referencers`, `project_dependencies`, `project_trace`)
- Similarity / intent → embedding tools (`project_semantic_search`)
- Raw content retrieval → `project_file` or `project_symbol`

**`_CAPABILITY_MATRIX_PATH` in `instructions.py`** redirects to `docs/wiki/host-vs-addons.md` (primary) and `docs/wiki/corpus-class-taxonomy.md` (secondary). Data envelope keys: `host_addon_contract_path` + `corpus_class_taxonomy_path`.

## Host-native tool inventory (24 tools, post-C1-deferral)

24 host-native tools as of 2026-05-18 (6 UE-native tools are deferred for migration to project-rag-ue-addon pending AddonMcpDepBundle v12 protocol bump):

| # | Tool | File | UE-native (deferred) |
|---|---|---|---|
| 1 | project_file | live.py:2506 | — |
| 2 | project_symbol | live.py:2687 | — |
| 3 | project_cpp_symbol | live.py:2712 | — |
| 4 | project_referencers | live.py:2411 | — |
| 5 | project_dependencies | live.py:2472 | — |
| 6 | project_blueprint_graph | live.py:2561 | deferred |
| 7 | project_trace | live.py:2743 | — |
| 8 | project_tag_graph | live.py:2909 | deferred |
| 9 | project_asset_registry | live.py:2374 | — |
| 10 | project_semantic_search | semantic.py:3036 | — |
| 11 | project_rag_blended_query | semantic.py:3779 | — |
| 12 | project_staleness_check | staleness.py:445 | — |
| 13 | project_subsystem_profile | subsystem.py:1224 | — |
| 14 | project_health | health.py:1453 | — |
| 15 | project_engine_domain_status | health.py:1719 | — |
| 16 | project_cvar | cvar.py:400 | deferred |
| 17 | project_test_coverage | test_coverage.py:264 | deferred |
| 18 | project_actor_composition | actor_composition.py:320 | deferred |
| 19 | project_overrides | cpp_overrides.py:424 | deferred |
| 20 | project_rag_instructions | instructions.py:164 | — |
| 21 | project_symbol_source | symbol_source.py:215 | — |
| 22 | project_symbol_brief | symbol_brief.py:126 | — |
| 23 | project_whoami | whoami.py:123 | — |
| 24 | project_list_sources | whoami.py:172 | — |

## ToolAnnotations wiring

**Correct import:** `from mcp.types import ToolAnnotations` — NOT `from mcp.server.fastmcp.tools import ToolAnnotations` (the latter raises ImportError at runtime; the "canonical wiring example" in `symbol_brief.py:40` was non-functional before this fix). All consumers import from the new `_annotations.py` shim in `project_rag_mcp/tools/`.

**Shared helper:** `project_rag_mcp/tools/_annotations.py` — centralized soft-import guard (~10 lines). All 24 tools use this shim, not direct imports.

**Values:**
| Annotation | Value | Notes |
|---|---|---|
| `destructive` | False | Universal |
| `readOnly` | True | Universal |
| `idempotent` | False | ONLY for `project_semantic_search` and `project_rag_blended_query` — genuine LLM/ANN non-determinism |
| `idempotent` | True | All other 22 tools. MCP spec: `idempotentHint` is environment-mutation guarantee, not same-result; redundant on `readOnlyHint=True` tools but correct |
| `openWorld` | True | Only: `project_file`, `project_symbol_source`, `project_staleness_check` |

**Description prefix convention:** All 24 host-native tools carry `[Consumer project]` as description prefix — capital C, lowercase p, single space after `]`. This is the content-class signal embedded in every description.

## Bug ownership boundary

The health envelope's `addon_fields` block identifies which addons are loaded. Bug ownership follows the host/addon split:
- **Host owns:** daemon, embed sidecar, schema, response envelope, consumer-project content paths.
- **Addons own:** their respective content classes (engine corpora, example corpora, knowledge corpora).

Practical routing for doctors:
- **`/project-rag:doctor`** — project-RAG-in-general health: MCP server liveness, index freshness, basic substrate. Cite when the MCP server is unreachable or degraded.
- **`/project-rag-ue-addon:doctor`** — UE-specific capability extension: engine corpus access, UE marketplace expansion. Cite when engine corpus is missing on a UE project with an otherwise-healthy project-RAG.

These are NOT interchangeable. Routing to the wrong doctor obscures the bug boundary and routes remediation effort to the wrong codebase.

## Why project-RAG is "triply important" for UE

Three compounding reasons (empirical anchor, 2026-05-21):
1. **Codebase scale:** UE engine source ~100K files — structural queries are the only viable lookup strategy.
2. **UE-exclusive tool surface:** `project_blueprint_graph`, `project_engine_examples`, `project_engine_pattern_check`, `project_cpp_symbol`, `project_subsystem_profile`, `project_referencers` — no grep substitute for blueprint graph traversal.
3. **High dead-end cost:** UE work has more "guess instead of look up → 30-minute dead end → discover the correct API existed all along" shape than other stacks. Working without project-RAG on UE is not slower work; it is wrong-work that has to be torn down.

## Content-agnostic preamble — single-source discipline

The project-RAG preamble for agent/skill dispatch lives at `coordinator/snippets/project-rag-preamble.md` (~80 words). Each consuming agent/skill file inlines it verbatim, fenced by:
```
<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->
<!-- END project-rag-preamble -->
```
Sync: `verify-preamble-sync.sh --check/--fix`. Wired into `/workday-start` Step 1.7. Inline targets: enricher dispatch prompts, executor dispatch prompts, review-integrator dispatch prompts, scout dispatch templates in brainstorming/writing-plans/systematic-debugging skills.

**Project detection:** the preamble uses generic any-project detection (not holodeck-specific). Holodeck deduplication uses positive context detection (`.holodeck/` dir or `Saved/HolodeckProjectRag/` path-up search), not hook-ordering sentinel — order-independent. False positives produce silent banners; false negatives are graceful (no banner, no behavior change).

## Configuration surfaces — configure via verbs, not hand-edits

project-rag's live checkout is refresh-managed (`refresh-plugin-live-install.sh` periodically runs `git checkout <track_ref>`). Hand-editing the source tree has no lasting effect AND gets silently reverted on next propagation. Configure through the provided verbs:

| Surface | Controls | Correct verb | Anti-pattern |
|---|---|---|---|
| `~/.claude.json projects.<root>.mcpServers.project-rag` | Per-project MCP wiring (`--project-root`, engine vector store) | Re-run `/project-rag:setup` or installer | Hand-editing `~/.claude.json` (races installer) |
| `~/.claude/machine-local/project_rag.toml [env]` | Env knobs addons require | `project-rag-cli wire` | Hand-editing TOML |
| `~/.claude/machine-local/registry.local.toml` | Repo paths, machine-local keys | `machine-local set <key> <val>` | Hand-editing |
| System env | Operator-chosen knobs (`EMBED_SIDECAR_REQUIRE_CUDA`, `PROJECT_RAG_USE_EMBED_SIDECAR`, etc.) | Shell profile | Editing source defaults |

**Exception:** `<ProjectRoot>/.project-rag/sentinels.json` and `coordinator.local.md` `project_type` are genuine per-project live files — editing them in place is the correct verb.

## Related guides

## instructions= string is live doctrine — review on every ambition change

A sister Claude session's first impression of your MCP server is the live `instructions=` string in the server registration — NOT your README or CLAUDE.md. The polarity of that string is doctrine, not prose: it shapes how every agent session routes queries to your server. Review the `instructions=` string whenever the server's ambitions change (new tool surface, new corpus class, updated routing rules). Apply: at every server-capability milestone, read the `instructions=` string out loud as if you were a new agent session seeing it for the first time and verify it still accurately describes routing priority and capability scope.

- `docs/wiki/project-rag-tool-envelope.md` — response envelope schema, verdict enum, provenance fields
- `docs/wiki/host-vs-addons.md` — host/addon separation of concerns (primary capability matrix)
- `docs/wiki/corpus-class-taxonomy.md` — corpus class definitions
- `docs/wiki/host-addon-separation-of-concerns.md` — architectural invariants
