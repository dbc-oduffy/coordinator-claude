---
title: Host vs. addons — content-agnostic core and domain-specific extensions
created: 2026-05-15
status: active
spec_backlink: docs/plans/2026-05-15-ws1-multi-language-core-spine.md §Step 12
relates_to:
  - docs/wiki/addon-protocol.md
  - docs/wiki/standalone-vs-ue-augmented.md
  - docs/wiki/addon-receiver-scaffold.md
  - docs/wiki/thin-wrapper-graceful-fail.md
  - ../../../project-rag-ue-addon/docs/wiki/triad-roles-doctrine.md
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-15-ws1-multi-language-core-spine.md §Step 12 (doc reframe — AC-WS1-9) -->

# Host vs. Addons

The canonical separation between project-rag's content-agnostic host and domain-specific addons.

> **Companion — triad role doctrine (PM framing).** The *why* behind the host/addon/holodeck split — mechanics-vs-knowledge as the load-bearing repo-carving axis, engine-wide-vs-project-specific as a distribution-mode axis inside the addon's output pipeline, and the two-clause seam-legitimacy test — lives in the addon repo at [`../../../project-rag-ue-addon/docs/wiki/triad-roles-doctrine.md`](../../../project-rag-ue-addon/docs/wiki/triad-roles-doctrine.md). Ratified by the project-rag EM 2026-05-18. This wiki captures the host-side mechanics; the triad doctrine captures the cross-repo conceptual model.

## Polarity

**project-rag (the host)** is a content-agnostic code RAG system. It serves TypeScript, C++, Python,
Markdown, and more as first-class consumers. Zero UE-specific privilege lives in the host. Any
code path that treats UE as a special case — rather than as one domain-gated domain among many —
is a port-out target.

**Addons** (e.g. `project-rag-ue-addon`) supply domain-specific extractors, producers, MCP tools,
preflight checks, and eval banks for a particular language ecosystem or runtime. They register
against host hookspecs; the host iterates their contributions at boot and at each call boundary.
No addon name, path, or capability is hard-coded in host source.

**Negative spec:** the host does NOT:
- Import from any addon package at startup
- Register UE-specific extractors or producers except through the addon hookspec path (PROVISIONAL
  gates during Wave 2a will be removed in Wave 2b physical extraction)
- Know which addons are installed; discovery is purely entry-point-based
- Hold a reference to `project-rag-ue-addon` in its manifest, schema, or configuration

## What lives in the host

| Concern | Location | Notes |
|---|---|---|
| Three-layer retrieval stack (L1 live / L2 graph SQL / L3 semantic) | `project_rag_mcp/tools/` | Serves any corpus |
| Schema (graph.db v12+) | `project_rag_mcp/graph/schema.py` | Content-agnostic; UE `bp_*` tables addon-owned post-Phase-6 (2026-05-18, v12); hookspec extension contract landed Phase 1 (v11), paired host+addon migration shipped Phase 6 (v12) |
| Addon protocol + hookspecs | `core/addon_protocol.py`, `core/addon_hookspecs.py` | Stable versioned contract; see [addon-protocol.md](addon-protocol.md) |
| Embed sidecar (CodeRankEmbed) | `embed_sidecar/` | Language-agnostic embedding |
| Chunker registry | `indexer/chunker_registry.py` | Any chunker registers here |
| Extractor registry | `priming/extractor_registry.py` | Any extractor registers here |
| Provenance classifier chain | `core/provenance.py` | Addons extend via hookspec |
| Python structural index (AST-lite) | `priming/producers/structural_index_lite_python.py` | Common-language; stays in-tree |
| C++ structural index (clang) | `priming/producers/structural_index_clang.py` | Common-language; UE source-root enumeration is addon-supplied; tree-sitter is the lite fallback (see `structural_index_treesitter.py`); `structural_index_lite.py` deleted in P2.5 |
| tree-sitter lite producer | `priming/producers/structural_index_treesitter.py` | Common-language; stays in-tree |
| scip-python wrapper | `priming/producers/scip_python_wrapper.py` | Common-language; stays in-tree |
| TS chunker | `indexer/ts_chunker.py` | Common-language; stays in-tree per host-multilang-first-class chain Phase 3 |
| Health envelope | `project_rag_mcp/tools/health.py` | Addons contribute subfields via `project_rag_register_health_field` |
| Tool envelope | `core/envelope.py` | `ENVELOPE_VERSION = 6` (W4-verdicts series) |

## What lives in addons (UE example: `project-rag-ue-addon`)

| Concern | Hookspec used | Notes |
|---|---|---|
| UE asset-registry, BP inventory, DataTable producers | `project_rag_register_producer` | Mode B headless + Mode A live editor |
| UE MCP tools (engine examples, type hierarchy, etc.) | `project_rag_register_mcp_tool` | 8 engine-domain tools |
| UE source-root enumeration | `project_rag_register_cpp_source_roots` | `Source/**`, `Plugins/Source/**` layout |
| UE preflight (WrongProject / sentinel checks) | `project_rag_register_editor_preflight` | Bridge-mediated; v5 hookspec |
| UE extractor funcs (assets, BPs, tag edges, etc.) | `project_rag_register_extractor` | 6 UE-domain extract_* funcs |
| `ue_plugin_enabled` health subfield | `project_rag_register_health_field` | lands in `addon_fields` envelope block |
| Eval bank (DroneSim smoke bank) | `project_rag_register_eval_bank` | Formerly `bank_legacy_ue.yaml` in host |
| UE provenance classifier rules | `project_rag_register_provenance_classifier_rules` | `.uproject`-keyed classifier |

## Graceful-fail contract

The host boots and serves queries with zero addons installed. Addon-gated tools return
`extraction_skipped`; health probes emit `DEGRADED` with an actionable install hint.
Full doctrine: [thin-wrapper-graceful-fail.md](thin-wrapper-graceful-fail.md) §Three implementation rules.

## Protocol version

The formal contract between host and addons is versioned via `ADDON_PROTOCOL_VERSION`
(currently `12`). Bump triggers: field add/remove/retype on a public `Addon*` dataclass,
hookspec signature change, `PreflightVerdict` enum extension, `ENVELOPE_VERSION` bump.
Full specification: [addon-protocol.md](addon-protocol.md).

**v12 — per-tool project graph.db capability** (2026-05-18). Addon tools that need
project-graph-db access set `requires_project_graph_db=True` on their
`AddonToolRegistration`. The host wraps the handler at registration to inject
`project_db_conn` as a kwarg per call. Addon handlers must not cache the conn across
calls — the host contract is fresh-per-call. Source/authority separation at the
corpus-class layer (see `corpus-class-taxonomy.md` if present) is unaffected; the
flag is a *capability declaration*, not a corpus-class assertion. Reference:
`tasks/2026-05-18-v12-vs-option-c-tiebreaker/zoli-verdict.md`.

## Wave-2 transition status (2026-05-15)

Wave 2a (scaffold) landed the hookspecs and façade types. Wave 2b (physical extraction)
moved UE code out of the host into `project-rag-ue-addon`. Phases 1A–1I and Phase 2
(P2.1–P2.4) shipped via `/mise-en-place`; P2.5 (delete `structural_index_lite.py`) is
tracked in spinoff handoff `tasks/handoffs/2026-05-15_203216_wave-2b-p2.5-spinoff.md`.
Wave 2c (terminal carve-out) proceeds once the Phase 1 hookspec
contract is solid (parse-test + round-trip fixture-addon test
green). A second installed addon is not a precondition. Authority:
plan §(b) "B-3 disposition"
(docs/plans/2026-05-16-phase-1-addon-extensible-schema.md).

*(Updated 2026-05-16) "second addon validates migration contract"
precondition retired per PM 2026-05-16 disposition; hookspec-
contract-solid gate replaces it.*

PROVISIONAL gate comments in the host source (`# PROVISIONAL — Wave-2a project-type gate;
replace with addon hookimpl in Wave 2b physical extraction`) mark remaining in-tree UE
conditionals that Wave 2b executors grep to find all gate sites.

## Engine-only mode

Engine-only mode lets the daemon serve engine-RAG tools (`project_engine_examples`,
`engine_domain_status`, `project_rag_blended_query`) against a non-UE project root
— for example, when `--project-root` points at `X:/project-rag` itself (a Python
codebase with no `.uproject`).

**Activation:** pass `--require-uproject=false` (or let `--require-uproject=auto`
detect the absence of a `*.uproject` file). The `--require-uproject` flag is
independent of `--no-addons`: addons load whenever the daemon is running and a
`project_root` path resolves, regardless of `.uproject` presence.

**Behaviour in engine-only mode:**

| Layer | Behaviour |
|---|---|
| Engine tools (`engine_domain_status`, `project_engine_examples`, `project_rag_blended_query`) | Fully operational when engine corpus is mounted |
| Project-* tools (`project_subsystem_profile`, `project_semantic_search`, etc.) | Return `no_source_resolved` with enriched hint: "pass `--require-uproject=true` or point `--project-root` at a UE project root" |
| Addon discovery | Runs normally; addon count logged via WARNING line |
| Boot log | Emits a WARNING: "Engine-only mode active … project-* tools will return no_source_resolved" |

**`--require-uproject` arg values:**

```
auto   (default) — scans <--project-root>/*.uproject; resolves to true when found,
                   false otherwise. Falls back to true (legacy) when --project-root unset.
true             — legacy: error on missing .uproject (same as old --no-addons=false behaviour)
false            — engine-only mode unconditionally
```

**Hint routing:** the `no_source_resolved` verdict carries a context-keyed hint from
`docs/wiki/failure-catalog.json` (row F-16, `context_key: engine_only_mode`) when in
engine-only mode. The hint text distinguishes "engine-only-mode-with-no-project" from
legacy "caller cwd not registered" (F-2, F-7) so operators know the exact fix path.

**Negative spec:** `--require-uproject` does NOT gate addon loading. Addons load whenever
`project_root` resolves, regardless of `.uproject` presence. This is intentional — an
addon that mounts an engine corpus (e.g. `project-rag-ue-addon`) should register its bands
even when pointed at a non-UE project root so engine-RAG tools work.

Spec backlink: docs/plans/2026-05-18-host-side-install-surface-from-addon-relay.md §C-1

## Related docs

- [corpus-band-protocol.md](corpus-band-protocol.md) — field-by-field `CorpusBand` contract; `structural_index_resolver` callable semantics, opaque-resource rules, and back-compat discipline (Z-AMEND-1). Canonical mechanics reference for addon authors registering a corpus band.
- [host-addon-separation-of-concerns.md](host-addon-separation-of-concerns.md) — umbrella design principle for protocol-surface shape decisions; five tactics (opaque-resource resolvers, closed surfaces, additive evolution, addon-declared failure modes); decision rule for new seams; prior-art-checker guidance.
- [addon-protocol.md](addon-protocol.md) — formal versioned contract, hookspec table, façade types
- [addon-receiver-scaffold.md](addon-receiver-scaffold.md) — Wave-2a doctrine and project-type gate philosophy
- [standalone-vs-ue-augmented.md](standalone-vs-ue-augmented.md) — legacy capability matrix; status `deprecated` (was `transitional` through 2026-05-18). Runtime self-declaration via `FastMCP(instructions=...)` + `project_rag_instructions()` + per-tool `ToolAnnotations` is now the authoritative routing surface; this wiki and `corpus-class-taxonomy.md` are the doctrine anchors. The capability-matrix wiki remains for historical reference only and is not consulted by the runtime.
- [thin-wrapper-graceful-fail.md](thin-wrapper-graceful-fail.md) — three implementation rules for addon seam probe sites
- [project-type-domains.md](project-type-domains.md) — domain-gate split by detected language
- [h3-4x2-baseline-freeze-matrix.md](h3-4x2-baseline-freeze-matrix.md) — canonical (corpus × query-shape) baseline-freeze matrix; addon authors registering a new corpus should extend the matrix's per-row cell-history with their corpus's NDCG/MRR/Recall cells per ship
