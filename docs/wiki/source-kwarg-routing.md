---
title: "source= kwarg — consumer routing contract"
status: shipped
shipped_in_wave: h7-followups-and-install-surface
spec: docs/plans/2026-05-17-h7-followups-and-install-surface.md (C-5)
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-17-h7-followups-and-install-surface.md §C-5 -->

# source= kwarg — consumer routing contract

> **Audience:** consumers of project-rag MCP tools. If you are looking for how the daemon
> resolves sources internally (CwdResolverMiddleware, SourceRegistry, boot-time aggregation),
> see [`docs/wiki/multi-source-daemon.md`](multi-source-daemon.md).

The `source=` kwarg is the mechanism by which an agent explicitly addresses a named corpus
band rather than relying on the daemon's automatic per-session resolution. Most tool calls
never need it — the daemon already knows which project the session belongs to. Use `source=`
only when you need to reach a corpus that is *not* the session's home project.

## 1. When to use source=

| Scenario | Do |
|---|---|
| Querying your current project | Omit `source=` — the daemon resolves it automatically |
| Cross-repo query (agent has sessions open across multiple projects) | Set `source="<registered-name>"` |
| Querying an addon-contributed engine corpus | Set `source="unreal_5.7_runtime"` (or equivalent band name) |
| Querying a universal addon band | Set `source="template_example_band"` (or whatever was registered) |

## 2. Precedence chain — how source= fits into resolution

Every retrieval tool body resolves its project context through a 4-step chain in
`@logged_retrieval` (`project_rag_mcp/audit.py`):

| Priority | Source | Mechanism |
|---|---|---|
| **1** | Explicit `source=` kwarg | `SourceRegistry().entry_for(source)` → `ProjectContext` v2 |
<!-- Review: Sonnet burst-2 P2-3 — corrected band_for→entry_for; project_rag_mcp/audit.py:152 calls registry.entry_for(source) -->
| **2** | Middleware-set ContextVar | `current_project_context()` — set by `CwdResolverMiddleware` from peer-PID cwd walk |
| **3** | Legacy `project_root` kwarg | Bare path (backward-compat; no source_name/engine_version/project_kind) |
| **4** | Nothing resolved | Returns `(None, False)` → tool emits `verdict="no_source_resolved"` |

`source=` always wins over middleware resolution (Priority 1 beats Priority 2). There is no
silent fallback — if the chain exhausts all four priorities without a match, the tool fails
loud with `no_source_resolved`.

**`PROJECT_RAG_DEFAULT_PROJECT_ROOT` is NOT in the chain.** This env var governs
daemon-launch defaulting in `project_rag_server.py` boot only. It is never consulted by the
tool-body resolver chain — setting it does not rescue an unresolved tool call. (Post-E-RUNTIME
role; `AD-RT-1` removed it from tool bodies 2026-05-17.)

## 3. Band naming convention

The string you pass to `source=` must exactly match a registered band name (case-sensitive).
Band names follow the convention established in `AD-9` (E-NAMED-BANDS, 2026-05-17):

**Engine-tied bands** — `[engine-name]_[engine-version]_[band]`:
```
"unreal_5.7_runtime"
"unreal_5.7_editor"
"unreal_5.5_plugin"
```

**Universal bands** — `[content-form]` or `[content-form]_[topic]`:
```
"coordinator_knowledge"
"template_example_band"
```

Call `project_whoami()` at any time to see the registered sources and addon bands available
to the current daemon instance.

> **`engine_runtime` is no longer valid.** The canonical name for the UE 5.7 engine corpus
> changed from `engine_runtime` to `unreal_5.7_runtime` in the E-NAMED-BANDS naming
> convention (2026-05-17). Passing `engine_runtime` returns `input_invalid`.

## 4. Concrete call examples

```python
# Default: daemon resolves source from session cwd
result = project_semantic_search(query="drone recovery logic")

# Explicit: query the UE 5.7 runtime corpus contributed by the addon
result = project_semantic_search(query="CharacterMovementComponent tick", source="unreal_5.7_runtime")

# Explicit: query a universal example band
result = project_semantic_search(query="event dispatcher pattern", source="template_example_band")

# Cross-repo: query a sibling indexed project by its registry name
result = project_cpp_symbol(symbol="DGFlightController", source="project-rag-ue-addon")
```

## 5. Routing-failure verdicts

When `source=` is set and the source cannot be served, the tool returns one of the six
routing-failure verdicts introduced in `ENVELOPE_VERSION 5` (E-RUNTIME, 2026-05-17). Each
has a distinct cause and remediation:

| Verdict | When it fires | What to do |
|---|---|---|
| `no_source_resolved` | `source=None` AND no middleware ContextVar AND no `project_root` kwarg | Run `/project-rag:setup` to register the current directory; check `hint.cwd` |
| `input_invalid` | The string passed to `source=` does not match any registered band name | Call `project_whoami()` to list valid names; correct the spelling |
| `addon_unreachable` | The band is registered but its addon's `required_env` probe failed at boot | Set the required environment variables (check `hint.addon_name`) and restart the daemon |
| `corpus_missing` | The band is registered but `CorpusBand.corpus_root` does not exist on disk | Run `/project-rag:index` (or the addon's corpus download step) to build the corpus; check `hint.corpus_root` for the expected path |
| `schema_mismatch` | The corpus on disk has a schema version below `MIN_SUPPORTED_SCHEMA` | Re-run `/project-rag:index` with the current daemon version to rebuild; check `hint.actual_version` vs `hint.expected_version` |
| `registered_but_not_setup` | The source name is in the source registry but no corpus exists on disk | Run `/project-rag:setup` then `/project-rag:index`; the source declaration exists but was never built |
| `doctor_failed` | A doctor probe returned a failure verdict for this source at daemon boot | Run `/project-rag:doctor` for full diagnosis; check `hint.probe_id` for which probe failed |

> There are 6 routing-failure verdicts, not 5 — the plan's headline count of "5" omitted
> `no_source_resolved`, which is present in `ENVELOPE_VERSION 5` and fires on unresolved tool
> calls regardless of whether `source=` was set.

Full verdict reference: [`docs/wiki/project-rag-tool-envelope.md`](project-rag-tool-envelope.md).

## 6. Post-H7 wiring guarantees (Gap 1 closure)

H7 Gap 1 closed the `source=` routing primitive layer end-to-end. The wiring path through
`project_rag_mcp/tools/semantic.py` is:

```
_handle_source_kwarg(source, ctx)
  └─ _resolve_blend_scope(ctx, source)
       └─ _resolve_band_for_source(name)   # SourceRegistry.band_for(name)
  └─ _open_chroma_for_band(band)           # corpus_root → Chroma collection
```

**What this means for consumers:**

- An unknown `source=` name returns `input_invalid` immediately (no silent fallback).
- A known band with a missing corpus returns `corpus_missing` (not an exception).
- A known band with a schema-version mismatch returns `schema_mismatch` (not an exception).
- A known band whose corpus opens cleanly is now queried via the AD-5 default-blend fan-out
  when `source=None` — both `project_semantic_search` and `project_rag_blended_query` route
  through `_resolve_blend_scope(ctx, None)` to include registered addon bands.

<!-- Review: code-reviewer (F6) — rephrased to distinguish the two sub-problems in Gap 2. -->
The `source=None` unrouted case is **resolved** as of 2026-05-18 by Shape 2-lite wiring
in `docs/plans/2026-05-18-project-semantic-search-unrouted-disposition.md`: when addon
bands are registered, both `project_semantic_search` and `project_rag_blended_query` fan
out across the project corpus plus all applicable bands, and the `not_supported` verdict
for `source=None` is retired.

The per-band backend (explicit `source=<band>` routing) remains deferred: calls with an
explicit `source=<band>` still return `not_supported` for any band whose query execution
has not been separately wired. That gap closes in the fusion-pipeline-n-lane spinoff
(`tasks/handoffs/2026-05-18_235457_fusion-pipeline-n-lane.md`).

## 7. `project_whoami` — self-discovery

Before passing `source=` to any tool, call `project_whoami()` to confirm the band name is
registered:

```python
result = project_whoami()
# result["data"]["addon_sources_available"] → list of registered band names
# result["data"]["registered_sources"]      → list of registered project sources
```

`project_whoami()` never returns a non-OK verdict and requires no `source=` argument.

## 8. No-list-form policy

The old `sources=["project", "engine"]` list-form parameter is deleted. There is one
`source=` (singular, optional string), not a filter list. PM directive 2026-05-16: "kill
backwards compat, let's make this clean."

## 9. See also

- [`docs/wiki/source-addressing-scheme.md`](source-addressing-scheme.md) — conceptual model behind the address space: applicable_kinds-as-umbrella convention, why there is no `engine` meta-umbrella, when to reconsider the one-level scheme
- [`docs/wiki/multi-source-daemon.md`](multi-source-daemon.md) — daemon internals: CwdResolverMiddleware, SourceRegistry, boot-race contract, SessionStart hook
- [`docs/wiki/project-rag-tool-envelope.md`](project-rag-tool-envelope.md) — full verdict enum and provenance schema
- `project_rag_mcp/tools/semantic.py` — `_handle_source_kwarg`, `_resolve_band_for_source`, `_open_chroma_for_band` implementation
- `core/source_registry.py` — `band_for()`, `aggregate_at_boot()`, `CorpusBand` shape
