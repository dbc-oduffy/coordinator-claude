<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

# Cross-RAG Sync Table

Tracks every UE-flavored surface shared between project-rag and example-game-repo (engine-RAG).
Update the `last_verified_in_sync` date whenever you confirm alignment.
On drift: add `drift_detected` date and file a stub plan in the example-game-repo repo.

Spec backlink: archive/specs/2026-04-30-shakedown-2-response.md §WS-A.6

## Drift check methodology (WS-A.6 scout)

Performed 2026-04-30 by comparing `indexer/cpp_chunker.py` against
`X:/example-game-workbench-repo/scripts/chunk_ue_source.py`:

1. **Forward-declaration handling**: project-rag has explicit `is_forward_declaration`
   boolean filter via `SymbolResolver.is_real_symbol()` at `cpp_chunker.py:216`.
   example-game-repo uses `type == "function"` / `type == "class"` enum — no explicit fwd-decl
   filter, but the same effect is achieved by not emitting stubs from class forward
   declarations (class bodies only entered when braces found).

2. **Token limit**: project-rag `_MAX_TOKENS = 450` (`cpp_chunker.py:42`).
   example-game-repo `MAX_CHUNK_TOKENS = 450` (`scripts/shared.py:60`). **In sync.**

3. **Shared regex patterns**: project-rag uses `_CLASS_RE` and `_FUNC_RE` regexes;
   example-game-repo uses a different parsing approach (finds class bodies via brace counting,
   then extracts member functions separately). Different implementation, same semantic
   intent. No shared regex — not a drift risk.

No material drift found. Token limits match. Fwd-decl handling uses different
mechanisms but produces equivalent results. No stub plan required.

## Sync rows

| surface | project-rag path | example-game-repo path | invariant | last_verified_in_sync | drift_detected | notes |
|---|---|---|---|---|---|---|
| CodeRankEmbed model pin | `core/embed.py`: `EMBED_MODEL_NAME`, `EMBED_MODEL_REVISION` | `scripts/shared.py`: lines 55–56 | Revision strings must match exactly. Mismatch = blended-query scores undefined. | 2026-04-30 | — | Both at `"3c4b608"` as of 2026-04-30; A.6b runtime assertion added to `_get_engine_collection()` |
| C++ chunker — forward-decl filter | `indexer/cpp_chunker.py`: `SymbolResolver.is_real_symbol()` line 216 | `scripts/chunk_ue_source.py`: no explicit filter; type enum achieves same effect | project-rag filters `is_forward_declaration`; example-game-repo uses `type` enum — different mechanism, same intent | 2026-04-30 | — | example-game-repo type field: `class`/`struct`/`function`/`property`; no `function_decl` equivalent |
| C++ chunker — granularity enum | `indexer/cpp_chunker.py`: `chunk_granularity` field | `scripts/chunk_ue_source.py`: `type` field | Different schemas — not directly comparable. See A.3 measurement notes. | 2026-04-30 | — | project-rag: `function_body`/`function_decl`/`class_full`/`class_summary`; example-game-repo: `function`/`class`/`struct`/`property` |
| C++ chunker — token limit | `indexer/cpp_chunker.py`: `_MAX_TOKENS = 450` (line 42) | `scripts/shared.py`: `MAX_CHUNK_TOKENS = 450` (line 60) | Both must use the same limit to produce comparable chunk sizes for cross-source reranking | 2026-04-30 | — | In sync at 450 tokens |
| BP chunker | `indexer/bp_json_chunker.py` | N/A (example-game-repo does not chunk BPs for RAG) | No sync required | 2026-04-30 | — | — |
| Reranker | `indexer/rerank.py`: `CrossSourceReranker` | N/A (reranker lives in project-rag only) | No example-game-repo counterpart | 2026-04-30 | — | — |
| F6 confidence thresholds | `tests/semantic/calibrated_thresholds.json` | N/A | project-rag internal | 2026-04-30 | — | example-sim-repo calibration corpus kept disjoint from F6 corpus |
| engine-rag function_body ratio | `indexer/embed.py`: `_CPP_FUNCTION_BODY_FLOOR_ENGINE` / `_CPP_FUNCTION_BODY_FLOOR_PROJECT` | `scripts/chunk_ue_source.py` JSONL output (cpp_chunks.jsonl) | Engine and project baselines are separate; `_check_cpp_floor` routes by `provenance_source`. Update engine baseline after engine reindex; update project baseline after example-sim-repo corpus refresh. | 2026-05-06 | — | Engine (2026-04-30): ratio=28346/136421=0.2078, floor=0.1078. Project (example-sim-repo 2026-05-06): ratio=7617/19773=0.3852, floor=0.2852. Per-bucket baselines shipped WS-L. |
| envelope schema (kind enum) | `core/structural.py`, `project_rag_mcp/graph/extractor.py` | `project-rag-ue-addon` (post-migration) — schema v2.3 declared in `archive/2026-05-15-envelope-v2.3-proposal.md` (example-game-repo `5f72f3af8`) | One-directional authority-shift notification (additive enum extension, not mutual-sync invariant): `ConsoleVariable` / `ConsoleCommand` added to `kind` upstream; host accepts as informational notice per `cross-repo-authority-shift-protocol.md`. Pre-condition (no closed validator host-side) verified by `tasks/d-4-readiness/closed-enum-audit.md`. | 2026-05-15 | — | Inbound from CVar coverage port (example-game-repo plan `2026-05-15-cvar-coverage-port.md`, post-review `c1ffbbf2`). 4,252 entities / 809 chunks emit as `engine_cvar_chunks` with `categories=["curated"]`. Will embed via D-4 build. |

## How to check for drift

1. **Engine baseline**: Run the measurement script against the latest `cpp_chunks.jsonl`
   from engine-RAG (`scripts/chunk_ue_source.py` output). Count `type=="function"` chunks
   over all cpp-type chunks; floor = ratio − 0.10. Update `_CPP_FUNCTION_BODY_FLOOR_ENGINE`
   and `_CPP_FUNCTION_BODY_MEAN_ENGINE` in `indexer/embed.py`.
2. **Project baseline**: Run `cpp_chunker.chunks_from_source_files("<project_root>")` and
   count `chunk_granularity=="function_body"` over total chunks; floor = ratio − 0.10.
   Update `_CPP_FUNCTION_BODY_FLOOR_PROJECT` and `_CPP_FUNCTION_BODY_MEAN_PROJECT` in
   `indexer/embed.py`. Last measured against example-sim-repo 2026-05-06 (7617/19773 = 0.3852).
3. Compare `MAX_CHUNK_TOKENS` in `scripts/shared.py` against `_MAX_TOKENS` in
   `indexer/cpp_chunker.py`.
4. Check `EMBED_MODEL_REVISION` in `core/embed.py` against `scripts/shared.py:56`.
5. Update `last_verified_in_sync` dates in this table.
