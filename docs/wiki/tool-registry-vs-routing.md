<!-- Imported from X:/project-rag at SHA d376cb01. Inherited substrate; canonical lineage now in Claude Central. Source: project-rag/docs/... — sibling-repo layout doctrine now lives in this repo's own wiki (the meta-repo local-doctrine file this once pointed at is retired). --> <!-- foreign-path-ok: dated import provenance, not a current-location claim -->

# Tool registry vs. routing — reconciled catalog

> Reconciliation surface for what's actually registered in the MCP server vs.
> what's documented in `CLAUDE.md` Appendix F. Refreshed by the dogfood
> loop; last verified against `tasks/dogfood-runs/2026-05-14-181057-cd81/tool_catalog.json`.

## Why this file exists

The Appendix F routing table is curated for the EM's mental model — "what
query type goes to which tool." It is **not** the source of truth for "what
is registered today." Bucket C of the 2026-05-14 dogfood surfaced a 14-tool
gap in both directions:

- **4 tools documented in the routing table but NOT registered.** Planned UE
  extraction surfaces (`project_cvar`, `project_test_coverage`,
  `project_actor_composition`, `project_overrides`) that the table treats
  as live. Agents dispatched to them get `tool_not_registered`.
- **10 tools registered but NOT in the routing table.** Engine-corpus
  surface, diagnostics, composed briefs. Agents don't discover them when
  consulting Appendix F; they hit them only when explicitly named.

Until the four planned tools land (UE-C / UE-D extraction waves), the
routing table flags them with a "⚠ planned, not registered" annotation
and this file carries the full reconciled list.

## Registered today (25)

Sourced from `tasks/dogfood-runs/2026-05-14-181057-cd81/tool_catalog.json`; `project_symbol` added (alias plan Chunk 1).

| # | Tool | Layer | In Appendix F? |
|---|---|---|---|
| 1 | `project_asset_registry` | meta + L2 | yes (meta) |
| 2 | `project_referencers` | L2 asset graph | yes |
| 3 | `project_dependencies` | L2 asset graph | yes |
| 4 | `project_file` | L1 | yes |
| 5 | `project_blueprint_graph` | L2 | yes |
| 6 | `project_cpp_symbol` | L1 / engine | yes — alias; see `project_symbol` |
| 7 | `project_trace` | L2 cross-layer | yes |
| 8 | `project_tag_graph` | L2 tag-centric | yes |
| 9 | `project_semantic_search` | L3 | yes |
| 10 | `project_rag_blended_query` | L3 cross-source | yes |
| 11 | `project_staleness_check` | meta | yes (meta) |
| 12 | `project_subsystem_profile` | meta | yes (meta) |
| 13 | `project_health` | meta diagnostic | **no** |
| 14 | `engine_domain_status` | meta diagnostic | **no** |
| 15 | `project_rag_instructions` | meta | **no** |
| 16 | `project_symbol_source` | L1 (LSP byte offset) | **no** |
| 17 | `project_engine_examples` | engine RAG | implied (UE) |
| 18 | `project_engine_pattern_check` | engine RAG | implied (UE) |
| 19 | `project_engine_session_primer` | engine RAG | **no** |
| 20 | `project_engine_document_symbols` | engine RAG | **no** |
| 21 | `project_engine_type_hierarchy` | engine RAG | **no** |
| 22 | `project_engine_symbol_graph` | engine RAG | **no** |
| 23 | `project_engine_list_modules` | engine RAG | **no** |
| 24 | `project_symbol_brief` | composed | **no** |
| 25 | `project_symbol` | L1 / engine | yes — canonical multi-language form; shares handler with `project_cpp_symbol` (back-compat alias); registered in Chunk 1 of the 2026-05-17 alias plan |

## Planned, NOT registered (4)

These are documented in CLAUDE.md Appendix F today with a "⚠ planned, not
registered" annotation. Each maps to a future UE extraction wave:

| Tool | Routing-table row | Blocking wave |
|---|---|---|
| `project_cvar` | CVar declarations + reads/writes | UE-C extraction |
| `project_test_coverage` | Test coverage (forward + inverse) | UE-D extraction |
| `project_actor_composition` | Actor/class composition (native CDO + BP SCS) | UE-D extraction |
| `project_overrides` | Virtual method override chain | UE-D FR-I extraction (clang-only) |

When any of these land, flip the ⚠ annotation off in the Appendix F row and
move the row in the table above from "planned" to "registered."

## How to refresh this file

After any tool register/unregister or doc edit, regenerate the registered
catalog from a live MCP server:

```bash
# Drives the server via stdio JSON-RPC, captures tools/list, writes the catalog
python scripts/dogfood_mcp/runner.py --catalog-only \
  --out tasks/dogfood-runs/<run-id>/tool_catalog.json
```

Then diff the new catalog against Appendix F. The dogfood `runner.py` will
eventually grow a `--reconcile-routing` mode that emits this file
automatically; until then, the EM does it by hand and the doctor probe
`Step Z` (planned) will flag stale reconciliations.

## Agent-side analog — adopting an upstream MCP tool is permission AND use, not array-presence

The registered-vs-routed gap above has a mirror one layer down, at the *agent* boundary. When an external MCP server exposes more tools than an agent consumes, **adopting a NEW tool requires BOTH (a) presence in the agent's `tools:` frontmatter array AND (b) being named in the agent's graduated ToolSearch `select:` bootstrap string plus referenced in ≥1 operating-instruction step.** Array-only presence is latent bloat, not adoption — the same shape as "registered but absent from the routing table": present in one list, undiscoverable in practice.

The bloat-control seam is symmetric: the unwired set must be absent from BOTH the frontmatter array and every bootstrap string. Leave *conflicting-orchestration* tools — an upstream's own pipeline/batch engine that fights Agent-Teams — unwired **deliberately**, and note why, so a later reader doesn't "complete" the adoption by wiring them in.

## Related

- `CLAUDE.md` Appendix F — the EM-facing routing table
- `project-rag-ue-addon/eval/bank_ue.yaml` — every UE-flavored tool exercised at least once per run (ported from `scripts/dogfood_mcp/bank_legacy_ue.yaml` in Wave 2b phase-1I)
- `state/improvement-queue/` — `project_cvar` etc. land items
