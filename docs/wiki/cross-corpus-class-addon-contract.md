---
title: Cross-corpus-class addon contract
created: 2026-05-17
status: active
spec_backlink: docs/plans/2026-05-17-engine-rag-addon-contract.md
---

<!-- Imported from X:/project-rag at SHA d376cb01. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — sibling-repo layout doctrine now lives in this repo's own wiki (the meta-repo local-doctrine file this once pointed at is retired). --> <!-- foreign-path-ok: import provenance, not a current-location claim -->

<!-- Spec backlink: docs/plans/2026-05-17-engine-rag-addon-contract.md §cross-corpus-class-addon-contract -->

# Cross-corpus-class addon contract

> Renamed from any prior "cross-engine" framing. This document covers any
> binding — engine, content corpus, knowledge base, or anything else.
> "Cross-corpus-class" = across engine + example + knowledge classes.

## 1. Substrate-discipline thesis

`project-rag` is an open-ended substrate for chunkers and knowledge bases. The substrate
has no knowledge of any specific engine, content form, or producer. It exposes three open
contracts (chunker, corpus, access) through which any binding — today's UE engine corpus,
tomorrow's Unity engine corpus, the coordinator meta-knowledge corpus, anything a
contributor authors — binds without contract surgery.

The substrate does NOT privilege any binding. There is no `if engine_kind == "unreal":`
branch in host dispatch. There is no UE-only catalog row in the host failure catalog. The
host produces the same envelope verdict, the same provenance schema, the same `whoami`
shape regardless of which addons are installed.

This property is not aspirational. It is structurally enforced:

- `tests/addons/test_v5_hookspec_naming.py` CI tripwire: no UE-specific terms in hookspec names/signatures.
- Host failure catalog ships only generic rows (F-1 through F-11); UE-specific rows live in the addon.
- `CorpusBand.applicable_kinds` is `list[str] | None`, not a UE enum.
- `core/project_type.py` detects kinds by filesystem sentinel, not by a closed enum.

## 2. HC-8 symmetry properties

Every addon binding — engine, knowledge, or otherwise — shares exactly these seven
properties:

1. **Same hookspec:** `project_rag_register_corpus_provider() -> list[CorpusBand]`
2. **Same dataclass:** `CorpusBand` v8 with the same 9 fields (see `authoring-an-addon.md §4`)
3. **Same data-dir convention:** `<addon-root>/data/<content-form>-{vector-store,structural}/<version>/`
4. **Same envelope:** `ToolResponse` with uniform verdicts and provenance schema
5. **Same provenance:** `source_name`, `indices`, `bands_queried`, `engine_version`, `corpus_sha256`, `index_age_seconds`, `phase`
6. **Same doctor-probe hookspec:** `project_rag_register_doctor_probe() -> list[FailureCatalogRow]`
7. **Same setup-script convention:** Phase 4 = register-with-project-rag; Phase 5 = optional corpus download

## 3. applicable_kinds taxonomy (including None for universal)

Three semantic cases, exactly:

| `applicable_kinds` value | Semantics | Use when |
|---|---|---|
| `None` | Universal: queryable from any caller kind, any project | Knowledge corpora, generic content, coordinator meta-knowledge |
| `["unreal"]` | Engine-scoped: only included in default-blend for UE projects | UE engine source bands |
| `["unity"]`, `["godot"]`, … | Engine-scoped for the named engine | Future engine addons |
| `["python"]`, `["ts"]`, … | Language-scoped | Content corpora scoped to a project kind. Use `"ts"` not `"typescript"`. |
| `["unreal", "unity"]` | Multi-engine: included in default-blend for either | Bands relevant to multiple engine kinds |
| `[]` | Bug shape: never use. Host warns and filters. | — |

The string values in `applicable_kinds` are matched against `core.project_type.detect_kind(project_root)`
(i.e. `core.project_type.detect()`) output at query time. The vocabulary is extensible:
any string that `detect()` returns is a valid `applicable_kinds` value. Current vocabulary:
`"unreal"`, `"ts"`, `"rust"`, `"python"`, `"generic"`. Note: `"cpp"` is not a valid kind
(falls through to `"generic"`); `"typescript"` is not valid (use `"ts"`).

## 4. How a new caller kind is added

Three mechanical steps — no protocol bump, no host catalog change, no new hookspec:

1. **Detect the kind in `core/project_type.py`:** add a filesystem-sentinel detection branch
   returning a new kind string (e.g. `"godot"`). Update `PROJECT_TYPES` tuple. Add a test
   in `tests/test_project_type_detection.py`.

2. **Register addon bands with the new kind:** addon returns
   `CorpusBand(applicable_kinds=["godot"], ...)`. No host change beyond step 1.

3. **Verify default-blend includes the new kind:** from a Godot project root,
   `project_semantic_search(source=None)` should include the Godot addon's bands.
   Add an integration test.

## 5. How a non-engine producer binds (coordinator meta-knowledge case study)

The coordinator meta-knowledge corpus has no engine version, no engine kind, and no
corpus root derived from an engine install path. It is the canonical non-engine universal
binding.

Shape:

```python
CorpusBand(
    band_name="coordinator_knowledge",
    authority_pairs=[("coordinator_docs", "knowledge")],
    default_weight=0.3,
    applicable_kinds=None,   # universal
    engine_version=None,     # not engine-tied
    chunk_filter=None,
    corpus_root=str(addon_data_root),
)
```

The host handles this identically to an engine band in every layer except default-blend
filtering: because `engine_version=None`, the engine-version filter does not apply, and
the band is auto-included from any consumer project.

Provenance for a query against `coordinator_knowledge`:

```json
{
  "source_name": "coordinator_knowledge",
  "indices": ["chroma_coordinator_knowledge"],
  "bands_queried": ["coordinator_knowledge"],
  "engine_version": null,
  "corpus_sha256": {"chroma_coordinator_knowledge": "..."},
  "index_age_seconds": {"chroma_coordinator_knowledge": 3600},
  "phase": null
}
```

Chroma collection name derivation: for universal bands (`applicable_kinds=None`), the
collection name is `chroma_<band_name>` → `chroma_coordinator_knowledge`.

## 6. The no-magic rule

The substrate does NOT auto-configure itself on first query. Every corpus band must be
explicitly registered through setup. Every requirement has a doctor probe. Every doctor
probe has a setup remediation.

Translated into addon-author terms:

- Do not write a hookimpl that "falls back to auto-discovery" when `corpus_root` is `None`.
  Return the band with `corpus_root=None`; the host returns `corpus_missing` verdict,
  doctor surfaces the remediation.
- Do not write setup scripts that silently skip registration steps. Every skipped step is
  a silent wrong answer.
- Do not write doctor probes that return GREEN on a best-effort check. Probes are binary:
  the requirement is met or it is not.

This is Invariant 1 + 2 from the engine-RAG mega-plan, translated into addon-author terms.

## 7. Band-name convention and namespace reservation

See `authoring-an-addon.md §6` for the full naming convention (two patterns: engine
bindings and non-engine bindings).

Namespace reservation policy:

- `unreal_*` — reserved for `project-rag-ue-addon`. No other addon registers bands starting with `unreal_`.
- `unity_*` — reserved for the anticipated `project-rag-unity-addon`. No other addon registers bands starting with `unity_`.
- `godot_*` — reserved for a future Godot addon.
- `coordinator_*` — the entire prefix is reserved for coordinator-plugin-bundled addons.
  `coordinator_knowledge` is the first reserved instance; future coordinator-bundled bands
  (`coordinator_lessons`, `coordinator_decisions`) follow the same prefix. No project addon
  registers bands starting with `coordinator_`.
- `template_*` — reserved for the template-addon and testing purposes.

Namespace reservation is a documentation convention. The host enforces `band_name` uniqueness
at boot (collision raises immediately), but does not enforce namespace reservation beyond
that — reservation is an authoring-time contract. If two addons use the same prefix, the
uniqueness check catches it.

Policy reference: `project-rag-ue-addon` repo's `docs/decisions/DR-CORPUS-NAMES-001-addon-contributed-corpus-band-naming-policy.md`
(naming policy + 3-tier stability model).

## 8. Cross-links

- `docs/wiki/authoring-an-addon.md` — full authoring reference (13 sections, 3 worked examples)
- `docs/wiki/corpus-class-taxonomy.md` — authority value vocabulary and principled taxonomy
- `docs/wiki/addon-protocol.md` — version bump history
- `docs/wiki/addon-hookspec-shape.md` — hookspec signatures
- `core/addon_protocol.py` — `CorpusBand` dataclass + `ADDON_PROTOCOL_VERSION`
- `core/addon_hookspecs.py` — hookspec definitions
- `project-rag-ue-addon` repo's `docs/wiki/multi-corpus-source-doctrine.md` — collision precedence rule
- `project-rag-ue-addon` repo's `docs/decisions/DR-CORPUS-NAMES-001-addon-contributed-corpus-band-naming-policy.md` — naming policy + 3-tier stability model
