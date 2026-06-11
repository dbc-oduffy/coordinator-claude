<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

# project-rag Tool Response Envelope

<!-- Spec backlink: archive/specs/2026-04-30-project-rag-shakedown-response.md §W2 -->

## Overview

Before W2, the 13 project-rag tools returned heterogeneous shapes: some returned raw lists, some returned flat `{"error": "..."}` dicts, and several returned silent zeros that callers could not distinguish from "no data," "wrong input," or "extraction phase never ran." The blueprint graph's `not_primed_for_this_bp` vs `error` pattern (structural gap G1 from the shakedown plan) was the right shape — W2 makes it universal.

The envelope contract answers three questions every caller has about every tool response:

1. **Did the call succeed?** — `verdict`
2. **What data came back?** — `data`
3. **Why did this happen, and what should I do next?** — `hint` and `provenance`

The canonical home is `core/envelope.py` (`ENVELOPE_VERSION = 6`). Re-housed from `project_rag_mcp/tools/envelope.py` in 2026-05-14 tc-5-followups; `project_rag_mcp/tools/envelope.py` remains as a deprecated re-export shim for ~100 in-tree consumers. New code imports `core.envelope` directly. All 28 tools construct responses through its constructors — no tool builds the dict inline.

## Schema

```python
ToolResponse = {
    "verdict": Literal["ok", "not_found", "missing_index",
                        "extraction_skipped", "input_invalid",
                        "timeout", "warming", "not_supported",
                        "no_source_resolved", "addon_unreachable",
                        "corpus_missing", "schema_mismatch",
                        "registered_but_not_setup", "doctor_failed",
                        "extraction_failed", "degraded_runtime"],
                        # 8 verdicts at v4; 6 new routing-failure verdicts added ENVELOPE_VERSION 5;
                        # 2 new producer/runtime error verdicts added ENVELOPE_VERSION 6
    "data": dict,                  # tool-specific payload; always {} on non-OK verdicts (never null, never partial)
    "hint": str | None,            # actionable next step for the consumer
    "provenance": {                # which sources/indices answered this call
        "indices": list[str],      # e.g., ["graph.db", "engine_structural_index"]
        "phase": str | None,       # e.g., "3B" — which extraction phase populates this
        # Runtime-only fields (injected by @logged_retrieval — absent on bare constructor calls):
        "timing_ms": float,        # wall-clock ms; non-negative (TC-18)
        "response_bytes": int,     # serialized byte length including timing fields (TC-18)
        # Tool-optional freshness fields (TC-15 — present on project_semantic_search, absent on others):
        "freshness": str | None,   # "fresh" | "edited_uncommitted" | "stale_index" | None
        "stale_files": list[str],  # up to top-5 file paths with stale or uncommitted status
    }
}
```

## Canonical provenance schema (E-PROVENANCE)

<!-- Spec backlink: docs/plans/2026-05-17-engine-rag-provenance.md §AD-PR-1 -->

Every retrieval tool's `ToolResponse.provenance` block carries the same seven canonical fields regardless of tool, source, corpus, or verdict. Tool bodies supply them explicitly; the `@logged_retrieval` decorator backfills `source_name` and `engine_version` when the tool body left them absent.

The seven canonical fields are populated via `core.envelope.make_provenance(...)` — a single factory that is the only site where the `provenance` dict is constructed. All 14 verdict constructors call this factory.

### Seven canonical provenance fields

| Field | Type | Always present | Description |
|---|---|---|---|
| `indices` | `list[str]` | Yes | Index sources that answered this call (e.g. `["graph.db"]`, `["chroma_unreal_5.7"]`). Never `None` — always a list, may be `[]` on non-OK verdicts. |
| `phase` | `str \| None` | Yes | Extraction phase whose output populates the index (e.g. `"Phase 3B"`), or `None`. |
| `source_name` | `str \| None` | Yes | Registered source name that was resolved (e.g. `"unreal_5.7_runtime"`, `"myproject"`). `None` for registry/metadata tools (`project_list_sources`, `project_health`). Backfilled by `@logged_retrieval` decorator when tool body leaves the key absent. |
| `bands_queried` | `list[str]` | Yes | Band names actually queried (Class A tools). Always `[]` for Class B/C tools. Never `None` on any verdict. |
| `engine_version` | `str \| None` | Yes | Engine version from the resolved source or band (e.g. `"5.7"`). `None` for project-only and metadata tools. Backfilled by decorator. |
| `corpus_sha256` | `dict[str, str] \| None` | Yes | Dict keyed by collection name with sha256 value per band (e.g. `{"chroma_unreal_5.7": "abc..."}`) — `None` when no band declares a sha256. Never `{}`. |
| `index_age_seconds` | `dict[str, int] \| None` | Yes | Per-index file age in seconds since mtime, keyed by index name. Populated for SQL/filesystem indices (`graph.db`, `project_structural_index`). `None` for chroma (multi-file layout), filesystem, and metadata sources; also `None` on non-OK verdicts. Never `{}`. |

### Per-tool population matrix (AD-PR-2)

Three population classes:

- **Class A** — band-routed retrieval (chroma collections): `bands_queried` non-empty, `corpus_sha256` populated if band declares one.
- **Class B** — L1/L2 SQL/filesystem retrieval: `bands_queried=[]`, `corpus_sha256=None`, `index_age_seconds` populated for the indices consulted.
- **Class C** — metadata/registry surfaces: `bands_queried=[]`, `corpus_sha256=None`, `source_name=None`, `engine_version=None`.

| Tool | Class | `bands_queried` | `corpus_sha256` | `index_age_seconds` |
|---|---|---|---|---|
| `project_semantic_search` | A | project + default-blend bands when `default_blend=True` (default); `["project"]` when `default_blend=False` | per-band sha256 or None | None (chroma age deferred) |
| `project_rag_blended_query` | A | `_resolve_blend_scope`-driven band list for `source=None` (Shape 2-lite fan-out: project + AD-5 default-blend bands); explicit `source=` uses `_blended_query_backend` three-lane fusion | per-band shas or None | None |
| `project_file` | B | `[]` | None | `{}` (filesystem — no single mtime) |
| `project_cpp_symbol` | B | `[]` | None | `{index: age}` |
| `project_referencers` | B | `[]` | None | `{index: age}` |
| `project_dependencies` | B | `[]` | None | `{index: age}` |
| `project_blueprint_graph` | B | `[]` | None | `{index: age}` |
| `project_trace` | B | `[]` | None | `{"graph.db": age}` |
| `project_tag_graph` | B | `[]` | None | `{"graph.db": age}` |
| `project_asset_registry` | B | `[]` | None | `{index: age}` |
| `project_subsystem_profile` | B | `[]` | None | `{"project_structural_index": age}` |
| `project_staleness_check` | B | `[]` | None | `{"graph.db": age}` |
| `project_symbol_brief` | B | `[]` | None | `{idx: age}` |
| `project_overrides` | B | `[]` | None | `{index: age}` |
| `project_cvar` | B | `[]` | None | `{"graph.db": age}` |
| `project_test_coverage` | B | `[]` | None | `{"graph.db": age}` |
| `project_actor_composition` | B | `[]` | None | `{"graph.db": age}` |
| `project_whoami` | C | `[]` | None | None |
| `project_list_sources` | C | `[]` | None | None |
| `project_health` | C | `[]` | None | None |

### Decorator backfill discipline (AD-PR-3)

`@logged_retrieval` in `project_rag_mcp/audit.py` backfills `source_name` and `engine_version` from `current_project_context()` ONLY when the key is **absent** from `prov`. Keys explicitly set by the tool body (including `None`) are preserved. Class C tools call `make_provenance(source_name=None, ...)`, writing the key with `None`; the decorator sees the key present and does NOT overwrite.

### Non-OK verdict provenance (AD-PR-7)

Non-OK verdicts always carry the canonical seven fields with these defaults:
- `bands_queried = []` (never `None`)
- `indices = []` on most non-OK; some constructors accept explicit indices
- `corpus_sha256 = None`
- `index_age_seconds = None`
- `source_name` / `engine_version`: `None` for unresolved verdicts; populated from `source=` kwarg for routing-failure verdicts (`addon_unreachable`, `corpus_missing`, `schema_mismatch`, `registered_but_not_setup`, `doctor_failed`).

### Freshness and lineage rationale

`index_age_seconds[index_name] = int(time.time() - os.path.getmtime(<path>))` where `<path>` is the on-disk artifact. This is distinct from the existing `freshness` field (TC-15), which classifies results relative to git HEAD:
- `freshness` answers "are these results stale relative to committed code?"
- `index_age_seconds` answers "how old is the index file itself?"

Chroma collections have a multi-file layout — no single mtime represents the collection's freshness — so they are absent from `index_age_seconds`. Chroma age is deferred to a follow-on plan.

### Worked example — engine-band query

```python
# project_semantic_search(source="unreal_5.7_runtime") result
{
    "verdict": "ok",
    "data": {"hits": [...], "max_score": 0.91},
    "hint": None,
    "provenance": {
        "indices": ["chroma_unreal_5.7"],
        "phase": None,
        "source_name": "unreal_5.7_runtime",
        "bands_queried": ["unreal_5.7_runtime"],
        "engine_version": "5.7",
        "corpus_sha256": {"chroma_unreal_5.7": "deadbeef..."},
        "index_age_seconds": None,           # chroma age deferred
        "timing_ms": 312.4,                  # injected by @logged_retrieval
        "response_bytes": 8192,              # injected by @logged_retrieval
        "embedding_source": "sidecar",       # injected by semantic tool
    }
}
```

### Per-hit provenance_module (E-PROVENANCE)

<!-- Spec backlink: docs/plans/2026-05-17-engine-rag-provenance.md §AD-PR-6, §AD-PR-9 -->

Class A tools (`project_semantic_search`, `project_rag_blended_query`) carry a `provenance_module` field on each hit in `data.hits[*]`. The field surfaces the addon-produced chunk metadata (Z-ASK-ADDON-2) so consumers can externally verify that band-scoped queries return chunks from the expected module.

**Closed value set:** `"runtime"` | `"editor"` | `"plugin"` | `"lyra"` | `None` (legacy chunks without the metadata field).

**Class B tools** (SQL/filesystem retrieval) do NOT carry `provenance_module` — the key is absent from Class B hits, not present-with-`None`.

**Attachment discipline:** `provenance_module` is attached to each candidate hit inside the per-band loop, before rerank. Do NOT zip `metadatas` against `hits` after rerank — order is lost after the reranker runs.

### `chunker_id=` filter kwarg (project_semantic_search / project_rag_blended_query)

<!-- Spec backlink: docs/plans/2026-05-19-chunk-type-filter-on-semantic-search.md -->

Both Class A tools accept a `chunker_id: str | None = None` kwarg that restricts results to chunks emitted by the named chunker.

| Kwarg | Type | Default | Behavior |
|---|---|---|---|
| `chunker_id` | `str \| None` | `None` | When set, pushes `where={"chunker_id": {"$eq": chunker_id}}` down to Chroma. Single string only — list form is rejected. |

**Validation:** An unknown chunker id returns `input_invalid` with a `hint` enumerating `Registry.iter_chunker_ids()` (the currently registered chunker ids). List-form input is rejected with `input_invalid` — pass a single string, matching the `source=` discipline (PM 2026-05-16).

**Combinability:** `chunker_id=` and `filter={"chunk_type": ...}` both push down independently to Chroma and intersect at the Chroma layer (AND semantics). Both kwargs may be supplied simultaneously.

**Blended-query propagation:** In `project_rag_blended_query`, the `filter_chunker_id` value is forwarded per-lane through the `_blended_query_backend`, replacing the formerly hard-coded `filter_chunk_type=None` at `semantic.py` lane-dispatch sites.

**Addon-supplied chunkers:** When `chunker_id` resolves to an addon-supplied chunker (`Registry.is_addon_supplied(chunker_id)` is `True`), the response `hint` notes that only chunks indexed after the addon was adopted will be filterable by this id — pre-adoption chunks were not stamped with `chunker_id` metadata.

### ENVELOPE_VERSION bump note

**ENVELOPE_VERSION did NOT bump for E-PROVENANCE additions** — additive provenance fields ride the no-bump carve-out documented at the bottom of `core/envelope.py`. The bump from `4` to `5` is owned by **E-RUNTIME** for the verdict palette expansion (6 new routing-failure verdicts). E-PROVENANCE's per-hit `provenance_module` addition co-rides the same bump as a `data.hits[*]` payload change.

Migration-history entry: v4 → v5 owned by **E-RUNTIME** (verdict palette) + **E-PROVENANCE** (per-hit `provenance_module`). v5 → v6 owned by **W4-verdicts** (`extraction_failed` + `degraded_runtime`).

### Per-hit fields (ENVELOPE_VERSION 3 — WS-1 Step 2, 2026-05-15)

Every tool that returns `data.hits[*]` now carries two additional keys on each hit:

| Key | Type | Meaning |
|---|---|---|
| `authority` | `str` | Producer authority band for this hit (e.g. `"project"`, `"project_lite"`, `"project_treesitter"`, `"engine"`). Empty string when the authority cannot be determined at query time (asset-graph hits, legacy collections). |
| `feature_level` | `str \| None` | Producer capability tier: `"full"` (clang full extraction), `"lite"` (AST-lite, tree-sitter), or `None` (unknown / not applicable). |

These fields are present on all hit-array paths: `project_semantic_search`, `project_rag_blended_query`, `project_referencers`, `project_dependencies`, `project_trace`, `project_blueprint_graph`, `project_tag_graph`. Asset-graph tools (referencers, dependencies, trace, tag_graph, blueprint_graph) emit empty-string `authority` and `None` `feature_level` until a future per-row JOIN is implemented — the keys are present for contract stability; the values reflect current availability.

`data` is always a dict — never a raw list, never `None`. On non-OK verdicts it is `{}`. Tools that previously returned raw lists (asset_registry, referencers, dependencies, cpp_symbol) now wrap the list under a named key (e.g., `data["assets"]`, `data["referencers"]`, `data["dependencies"]`, `data["symbols"]`).

## Verdict enum (16 verdicts — ENVELOPE_VERSION 6)

The verdict enum grew from 5 to 7 in ENVELOPE_VERSION 2 (WS-D-11, 2026-05-07), adding `timeout` and `warming`. ENVELOPE_VERSION 3 (WS-1 Step 2, 2026-05-15) kept the same 7 verdicts but added per-hit `authority` and `feature_level` fields. ENVELOPE_VERSION 4 (wave-2b-engine-si-handler-schema-drift, 2026-05-16) adds `not_supported` as the 8th verdict. ENVELOPE_VERSION 5 (E-RUNTIME, 2026-05-17) adds 6 routing-failure verdicts for multi-source daemon operation, bringing the total to 14. ENVELOPE_VERSION 6 (W4-verdicts, 2026-05-18) adds `extraction_failed` and `degraded_runtime`, bringing the total to 16. Do not add a 17th without incrementing `ENVELOPE_VERSION` and updating this document.

`not_supported` (added ENVELOPE_VERSION 4, 2026-05-16, wave-2b-engine-si-handler-schema-drift):
capability-absent verdict for cases where the index is present but the requested
relationship/dimension is not extractable from the current schema dialect. Distinct from
`missing_index` (substrate absent), `not_found` (entity absent), and `extraction_skipped`
(data would exist if extraction were re-run; `not_supported` means the schema dialect cannot
express this relationship without a schema bump — re-running extraction would not help).
Example: the engine v4 structural index has no `references` table; `relationship='references'`
on `project_engine_symbol_graph` returns `not_supported`, not `missing_index`.

| Verdict | When it fires | What the consumer should do |
|---|---|---|
| `ok` | Data is populated and authoritative for the input | Read the tool-specific payload from `result["data"]` |
| `not_found` | The input does not match any known entity (typo, renamed, deleted asset) | Check spelling; use `project_asset_registry` to confirm asset paths |
| `missing_index` | A required index file or database table is absent — the phase that builds it has never run | Run `/project-rag:index`; call `project_health` to identify which index is missing |
| `extraction_skipped` | The index exists but the populating extraction phase did not run for this project or for this specific entity | Re-run `/project-rag:index`; check `provenance.phase` to target the specific phase |
| `input_invalid` | The input shape or value does not match the tool's contract | Fix the input; read `hint` for the correct format or a corrected value |
| `timeout` | The embed sidecar was saturated (inflight cap exhausted after all client retries), the query genuinely stalled after the sidecar was warm, OR the tool body exceeded its `@logged_retrieval` wall-budget (WS-8 — wall-budget breach) | Back off 30–60 s and retry. Read `provenance.timing_ms_at_abort` for elapsed time. Wall-budget breaches also carry `provenance.budget_ms` and `provenance.abort_reason="wall_budget"`. |
| `warming` | The embed sidecar's model is still loading; the call was aborted early | Wait `provenance.retry_after_warm_seconds` (from hint), then retry. Read `provenance.timing_ms_at_abort` for elapsed time. Do NOT retry immediately — repeated requests during model load are counterproductive. |
| `not_supported` | The index is present but the requested relationship or dimension cannot be answered by the current schema version — re-running extraction would NOT help, a schema bump is required | Read `hint` for what would re-enable the capability; file a schema-bump plan if the relationship is important |
| `no_source_resolved` | No project context could be resolved for the call (no source kwarg, no middleware ContextVar, no project_root kwarg) — added ENVELOPE_VERSION 5 (E-RUNTIME, 2026-05-17) | Run `/project-rag:setup` to register the current directory; check `hint.cwd` for the resolved working directory |
| `addon_unreachable` | A source is registered and band-registered but its addon's `required_env` probe failed at boot (missing environment variables) — added ENVELOPE_VERSION 5 | Set the required environment variables and restart the daemon; check `hint.addon_name` for which addon to configure |
| `corpus_missing` | A band is registered but `CorpusBand.corpus_root` does not exist on disk — added ENVELOPE_VERSION 5 | Run `/project-rag:index` to build the corpus; check `hint.corpus_root` for the expected path |
| `schema_mismatch` | The corpus schema version does not match the expected version — added ENVELOPE_VERSION 5 | Re-run `/project-rag:index` with the current daemon version to rebuild; check `hint.actual_version` vs `hint.expected_version` |
| `registered_but_not_setup` | The source name is in the registry but no corpus exists on disk — added ENVELOPE_VERSION 5 | Run `/project-rag:setup` then `/project-rag:index`; the source declaration exists but was never built |
| `doctor_failed` | A doctor probe returned a failure verdict for the source at boot — added ENVELOPE_VERSION 5 | Run `/project-rag:doctor` for full diagnosis; check `hint.probe_id` for which probe failed |
| `extraction_failed` | A producer or consumer raised a real exception during extraction — added ENVELOPE_VERSION 6 (W4-verdicts, 2026-05-18). Distinct from `extraction_skipped` (phase never ran) and `missing_index` (substrate absent) | Inspect logs for the root-cause exception; re-run `/project-rag:index` after resolving the underlying error |
| `degraded_runtime` | A tool dependency is unhealthy but the tool can return partial or empty results rather than failing outright (e.g. scanner-sidecar boot timeout, ue-ls merger absent, optional index unavailable) — added ENVELOPE_VERSION 6 | Run `/project-rag:doctor` for diagnosis; results in `data` are best-effort; `hint` describes the missing dependency |

**`timeout` vs `warming` distinction:** `timeout` means the sidecar was alive and warm but either saturated (too many concurrent requests — `EmbedSidecarBusy` mapped to `timeout`) or genuinely stalled. `warming` means the sidecar was not yet warm — the model was still loading when the request arrived (`EmbedSidecarWarming`). Consumer remediation is different: `timeout` → back off briefly and retry; `warming` → wait for the estimated warmup time, then retry.

**Why `busy` doesn't appear as a verdict:** `EmbedSidecarBusy` (inflight cap exhausted) maps to `verdict: "timeout"` because both cases have identical consumer remediation (back off and retry). Introducing a separate `busy` verdict would add a verdict with no distinct consumer action.

**`timeout` provenance fields:**
- `timing_ms_at_abort` (float): wall-clock ms from request start to abort.
- `budget_ms` (float, wall-budget breaches only — WS-8): the resolved wall-budget that was exceeded. Set when `abort_reason="wall_budget"`.
- `abort_reason` (str, wall-budget breaches only — WS-8): `"wall_budget"`. Distinguishes the `@logged_retrieval` wall-budget abort from the embed-sidecar saturation/stall causes.

**`warming` provenance fields:**
- `retry_after_warm_seconds` (int): estimated seconds until the sidecar is warm (from the sidecar's `estimated_ready_ms` hint).
- `timing_ms_at_abort` (float): wall-clock ms from request start to abort.

**Why `missing_index` and `extraction_skipped` are distinct:** `missing_index` means the file or table does not exist at all — the phase that creates it has never been run at the project level. `extraction_skipped` means the index structure exists but the relevant phase did not populate data for this project or scope. Both have the same remediation (`/project-rag:index`) but different diagnostic meaning: `missing_index` signals a missing bootstrap step; `extraction_skipped` signals partial extraction (e.g., Phase 3B ran for some projects but not this one).

## Consumer routing table

| You see this verdict | Do this |
|---|---|
| `ok` | Read from `result["data"]` |
| `not_found` | Check input spelling; use `project_asset_registry` to confirm paths |
| `missing_index` | Run `/project-rag:index`; check `project_health` for details |
| `extraction_skipped` | Re-run `/project-rag:index`; check `provenance.phase` for which phase to target |
| `input_invalid` | Fix the input; read `hint` for correct format |
| `timeout` | Back off 30–60 s and retry; check `provenance.timing_ms_at_abort` for elapsed time |
| `warming` | Wait `provenance.retry_after_warm_seconds` seconds, then retry; sidecar model is still loading |
| `not_supported` | Read `hint` — the index is present but this capability requires a schema bump, not a re-index |
| `no_source_resolved` | Run `/project-rag:setup` to register the current directory |
| `addon_unreachable` | Set required environment variables and restart daemon; read `hint` for which addon |
| `corpus_missing` | Run `/project-rag:index` to build the corpus |
| `schema_mismatch` | Re-run `/project-rag:index` with current daemon version |
| `registered_but_not_setup` | Run `/project-rag:setup` then `/project-rag:index` |
| `doctor_failed` | Run `/project-rag:doctor` for full diagnosis |
| `extraction_failed` | Inspect logs for root-cause exception; re-run `/project-rag:index` after resolving the error |
| `degraded_runtime` | Run `/project-rag:doctor`; results are partial/best-effort; read `hint` for which dependency is unhealthy |

## Provenance block

`provenance.indices` lists the index sources that answered the call. `provenance.phase` names the extraction phase whose output populates the tool's data. `provenance.timing_ms` and `provenance.response_bytes` are injected at the `@logged_retrieval` decorator layer and are present on every live tool response (see below).

### Runtime-only provenance fields (TC-18)

These fields are injected by the `logged_retrieval` decorator in `project_rag_mcp/audit.py` after the tool body returns. They are **not** present on bare constructor calls (unit tests calling `envelope.ok()` directly). They are present on every response returned through the FastMCP dispatch path.

| Field | Type | Semantics |
|---|---|---|
| `timing_ms` | `float` | Wall-clock milliseconds from decorator entry to return. Rounded to 3 decimal places. Non-negative. Sub-millisecond calls read as e.g. `0.247` rather than `0.0`. |
| `response_bytes` | `int` | Byte length of `json.dumps(result, default=str)` measured after injection, so it includes `timing_ms` and `response_bytes` themselves in the count. Non-negative. |

**Ordering contract:** `_enqueue` (audit log write) runs before `_inject_timing` so the `bytes_returned` column in `retrieval_log` reflects the pre-injection payload size and does not double-count the timing fields.

### Tool-optional freshness fields (TC-15)

These fields are injected by `core/freshness_probe.py` into the `ok()` call via `**extra_provenance`. They are present only on tools wired to the freshness probe (currently `project_semantic_search`). Tools that do not wire the probe do not include these keys.

| Field | Type | Semantics |
|---|---|---|
| `freshness` | `str \| None` | Worst-case freshness across all hits: `"fresh"`, `"edited_uncommitted"`, or `"stale_index"`. `None` when no file paths were found in results or probe is not wired. |
| `stale_files` | `list[str]` | Up to 5 file paths classified as `stale_index` or `edited_uncommitted`. Empty list when all hits are fresh or probe is not wired. |

**Three-state classification:**
- `fresh` — file mtime ≤ index build time (within 1s hysteresis). No action required.
- `edited_uncommitted` — file mtime > git HEAD timestamp. A working-tree edit exists that has not been committed. Results may reflect stale data.
- `stale_index` — file mtime > index build time but ≤ git HEAD. A committed change has not been picked up by the last reindex. Run `/project-rag:index` to refresh.

**Hysteresis:** A 1-second window around the git HEAD timestamp avoids false `edited_uncommitted` classifications from filesystem timestamp rounding (FAT/NTFS mtime precision).

### Tool-optional confidence fields (TC-16)

These fields are injected by `core/confidence.py` into the `ok()` call via `**extra_provenance`. They are present only on `project_semantic_search`. Tools that do not compute confidence do not include these keys.

| Field | Type | Semantics |
|---|---|---|
| `confidence` | `float \| None` | Available-signals geometric mean confidence score in [0.0, 1.0]. `None` when no hits were returned or computation failed. |
| `confidence_signal_count` | `int \| None` | Count of signals (1–4: gap, strength, identity, freshness) that contributed to the score. `None` in the same cases as `confidence`. |

**Signal panel:** The formula considers up to four signals per result — `gap` (normalised score margin between rank-1 and rank-2), `strength` (saturating function of the top-1 score), `identity` (symbol name match in top-1 chunk), and `freshness` (from the TC-15 probe). Each signal is included only when available; absent signals are excluded from the geometric mean, not treated as zero.

**Consumer guidance:**
- A `confidence_signal_count < 3` means the confidence estimate is based on a partial signal panel and should be treated with **skepticism**. The most common case is `signal_count=2` (strength + gap only, when freshness probe is not wired and no identity check is performed).
- A high confidence value with `signal_count=2` is directional, not authoritative — consider the other signals before acting on it.
- `confidence` values are computed from top-1 result signals and summarise the provenance-level quality of the search response. Per-hit confidence labels (`"confident"`, `"tentative"`, `"unranked"`) live in `data.hits[i].confidence` and use a separate threshold-based calibration.

**Formula:** Available-signals weighted geometric mean — `(∏ signal_i^w_i)^(1/Σw_i)` computed over available signals only. Weights: gap=0.35, strength=0.35, identity=0.15, freshness=0.15 (adapted from jcodemunch-mcp retrieval/confidence.py Pattern 7). Calibration: see `tests/semantic/confidence_calibration_results.json`.

**Deferred fields (not shipped in TC-16):** `confidence_se: float | None` (CV-derived standard error) and `confidence_tier: low|medium|high` (quantile-cut tier) are explicitly out of scope for Sprint 1b and will be added in a follow-up stub to avoid API lock-in on a point-estimate-only shape.

**`ENVELOPE_VERSION`:** No bump for TC-15, TC-16, or TC-18. Bumped from 1 to 2 in WS-D-11 (2026-05-07) when `timeout` and `warming` were added to the verdict enum. Adding additive provenance fields does not change the verdict contract — downstream consumers that parse exact provenance keys should use `dict.get()` or subset checks rather than exact-equality on the key set.

### Index name catalog

| Index name | Used by |
|---|---|
| `graph.db` | `project_asset_registry`, `project_referencers`, `project_dependencies`, `project_blueprint_graph`, `project_trace`, `project_tag_graph` |
| `engine_structural_index` | `project_cpp_symbol` (engine DB) |
| `project_structural_index` | `project_cpp_symbol` (project DB), `project_subsystem_profile` |
| `chroma_project` | `project_semantic_search` |
| `chroma_engine` | `project_rag_blended_query` (engine collection) |
| `chroma_plugin` | `project_rag_blended_query` (plugin collection) |
| `priming_jsonl` | `project_asset_registry`, `project_referencers`, `project_dependencies`, `project_blueprint_graph` (JSONL fallback when graph.db absent) |
| `filesystem` | `project_file`, `project_staleness_check` |

For tools with a SQL fast-path and a JSONL fallback (asset_registry, referencers, dependencies, blueprint_graph), `provenance.indices` reflects which path actually answered the call — the wrapping is done inside each backend function, not at the handler level. Tools with a single source backend wrap at the handler level.

## Per-scope extraction_skipped

`provenance.phase` disambiguates which extraction scope was missing when `extraction_skipped` fires:

| Phase label | What it populates | Tools that report this phase |
|---|---|---|
| `Phase 1 (priming)` | Asset registry JSONL, BP batch files, tag references | `project_asset_registry`, `project_referencers`, `project_dependencies` |
| `Phase 2 (extract_bps)` | `classes` (kind=blueprint), `bp_functions`, `bp_components` in graph.db | `project_blueprint_graph` |
| `Phase 3A` | `bp_nodes`, `bp_node_pins`, `bp_connections` | `project_trace` (pin-level mode) |
| `Phase 3B` | `cross_layer_edges` | `project_trace` (cross-layer mode) |
| `Phase 3C` | `cross_layer_edges` (tag edges, input binding edges) | `project_tag_graph` |
| `Phase 4 (structural_index)` | C++ classes, structs, enums in structural_index sqlite | `project_cpp_symbol`, `project_subsystem_profile` |

**Why `not_primed_for_this_bp` became `extraction_skipped`:** The old key was a per-entity variant of the same structural condition — "priming index exists but this specific BP was not in it." That is exactly what `extraction_skipped` means. The Staff Engineer's W2 review consolidated all `not_primed*` variants into `extraction_skipped` so consumers see one verdict and one remediation path. The `provenance.phase` field carries the per-scope signal that the old key name was encoding.

## Truncation convention

Any tool that returns partial results because a documented bound was hit (depth cap, token cap, result-count cap) returns `verdict: ok` with two additional fields in `data`:

- `data.truncated: bool` — always present when a cap applies; `true` when results were cut short
- `data.truncation_reason: str` — human-readable explanation of which bound was hit

This convention is codebase-wide. New tools that hit a result cap must follow the same naming — do not invent `partial`, `limited`, `capped`, or any other synonym.

**Current users:**

- `project_trace` — existing `truncated` field at the trace return in `project_rag_mcp/tools/live.py`
- `project_dependencies` — `cycle_detected` depth-cap reclassified as `verdict: ok` with `data.truncated = true` and `data.truncation_reason = "recursive depth cap exceeded"` (the Staff Engineer Finding-4, W2)

**Rationale (the Staff Engineer Finding-4):** Depth-cap truncation is a successful execution that hit a documented operational bound, not an error condition. Returning `verdict: ok` with truncation metadata lets callers handle the partial result programmatically rather than treating it as a failure to retry.

## Backwards compatibility

**`data: {}` on non-OK:** Legacy callers that do `result.get("hits", [])` or `result.get("dependencies", [])` on non-OK verdicts receive empty results — same behavior as the old silent-zero paths, but now the caller knows why.

**List-returning tools (breaking change):** Four tools previously returned raw lists: `project_asset_registry`, `project_referencers`, `project_dependencies`, `project_cpp_symbol`. W2 wraps the list under a named key in `data`. Callers must update from `for item in result:` to `for item in result["data"]["assets"]:` (etc.). This is accepted breakage — the only known consumer is Claude Code via FastMCP/JSON serialization, which already wraps responses downstream. No deprecation banner (YAGNI; add one if an external consumer materializes).

**Key mapping for list-returning tools:**

| Tool | Old shape | New shape |
|---|---|---|
| `project_asset_registry` | `list[dict]` | `result["data"]["assets"]` |
| `project_referencers` | `list[dict]` | `result["data"]["referencers"]` |
| `project_dependencies` | `list[dict]` | `result["data"]["dependencies"]` |
| `project_cpp_symbol` | `list[dict]` | `result["data"]["symbols"]` |

**`project_health` inner verdict key:** The health tool's internal human-readable verdict string moved from `result["verdict"]` (which is now the envelope enum) to `result["data"]["health_verdict"]`. This preserves the full diagnostic string for callers that need it while avoiding the dual-`verdict` cognitive-load trap (the Staff Engineer Finding-7).

## Doctor allowed-tools scope (WS-A / WS-R)

The `/project-rag:doctor` command's `allowed-tools` scope was elevated from `["Bash", "Read"]` to `["Bash", "Read", "Edit"]` (WS-R PM approval). The `Edit` addition is required for Step 7 recovery workflows that must disable/re-enable the MCP entry in `~/.claude.json`.

This change is envelope-adjacent because the doctor command is the authoritative "non-OK verdict → remediation" surface: when a tool returns `missing_index` or `extraction_skipped`, the canonical remediation path flows through `/project-rag:doctor`, which may now write JSON edits as part of MCP-lifecycle coordination.

**Scope boundary (PM-approved 2026-05-06):** Doctor's Edit authority is scoped to `~/.claude.json` project-rag entries and `<data_dir>/` only. It may NOT edit user code, other MCP server configs, or any files outside the project-rag lifecycle.

Source: batch-A-phase1-haiku.md § WS-A KNOWLEDGE entry; batch-A § WS-R DECISION `doctor-elevation-exception`.

## Migration history

- **`2ce4de5`** — W2-prep: split `tests/test_live_tools.py` per-tool; created `project_rag_mcp/tools/envelope.py` with `ENVELOPE_VERSION = 1` and 5 constructor functions
- **`b44e7b2`** — W5 (E1c): `extract_all` ledger wiring + `project_health` `pipeline_ledger` surface
- **E5/E5a/E5-subsystem/E5-semantic** — per-tool envelope migration completed for all tools (now 19); `project_rag_mcp/tools/envelope.py` is the single constructor surface.
- **WS-Q (v0.5.2, 2026-05-08)** — `cuda_available` field marked DEPRECATED with pointer to replacement fields `torch_cuda_available`, `pynvml_importable`, `nvml_device0_resolved`.

## Deprecation notice — v0.5.2

The `cuda_available` field in the embed-sidecar startup event (surfaced in `project_health` output) is **deprecated** as of v0.5.2. It will be removed in v0.6.0.

Replacement fields (all boolean, all present in startup event):

| Old field | Replacement | What it measures |
|---|---|---|
| `cuda_available` (deprecated) | `torch_cuda_available` | `torch.cuda.is_available()` |
| — | `pynvml_importable` | NVML Python binding loadable |
| — | `nvml_device0_resolved` | First GPU device handle resolved via NVML |

The old field was a VRAM-probe-only indicator that collapsed three distinct GPU-readiness signals into one boolean. The three new fields provide granular GPU state visible in `project_health` responses and the embed-sidecar log.

**Consumer guidance:** If you read `project_health["data"]["embed_sidecar"]["cuda_available"]` in any automation, migrate to the three replacement fields before v0.6.0. The old field returns `DEPRECATED` (string) in v0.5.2 to surface unconsumed references.

Source: batch-A-phase1-haiku.md § WS-Q DECISION `deprecated-field` + DECISION `version-bump`.
