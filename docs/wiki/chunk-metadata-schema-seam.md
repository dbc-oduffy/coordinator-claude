---
title: Chunk Metadata Schema Seam (γ-prime)
created: 2026-05-16
status: active
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-16-host-pluggy-chunk-metadata-schema-seam.md -->
<!-- Spec backlink: tasks/w2a-1i-revised/patrik-pluggy-seam-design-2026-05-16.md -->

# Chunk Metadata Schema Seam (γ-prime)

> Host owns the Layer-1 validation algorithm and the canonical-eight. Addons own
> per-source-type extras vocabulary. This page documents the pluggy seam at
> protocol v7.

## Why this seam exists

The addon-side `SOURCE_TYPE_EXTRAS` closed allow-list drifted behind chunker
evolution repeatedly — every new chunker field required a manual dict update in
a module the chunker author didn't own, and missed updates produced silent Layer-1
failures. PM flagged the recurrence pattern as structural, not per-incident. The
polarity rule (`CLAUDE.md § Ambition`) requires that UE-specific vocabulary lives
in the addon, not the host — but host must own the canonical-eight if it is to be
the single contract across all future languages (Python, TS, Rust, Markdown).
γ-prime resolves both constraints: host owns the algorithm, addons own the
vocabulary they contribute.

## Shape (γ-prime)

**Host owns:** `Layer1ChunkRecord` (the canonical-eight TypedDict/dataclass),
`CANONICAL_EIGHT` (the closed set of required field names), `_UNIVERSAL_EXTRAS`
(pipeline-state fields injected by host code post-chunker — `context_prefix`,
`sub_index`, `sub_total`, `parent_chunk_id`, `chunker_id`, etc.; `chunker_id` was
added 2026-05-19 via `indexer/chunk_utils.make_chunk()` — see
`docs/plans/2026-05-19-chunk-type-filter-on-semantic-search.md`), `_compute_drift` (the per-record
diff algorithm), `validate_chunk(chunk: dict, *, source_type: str) -> list[str]`
(returns error strings; empty = valid), and `_HOST_SOURCE_TYPE_EXTRAS: dict[str,
frozenset[str]] = {}` (empty at v7 — populated when in-tree Python/TS chunkers land
first-class; not fed through the hookspec, as in-tree contributors are host code).
Host also owns `AddonChunkMetadataExtrasSpec` (the façade dataclass) and the
`project_rag_register_chunk_metadata_extras` hookspec definition.

**Addons contribute:** declarative `AddonChunkMetadataExtrasSpec` instances returned
via `project_rag_register_chunk_metadata_extras` hookimpl(s). Each spec declares a
`source_type`, a `frozenset[str]` of optional field names permitted for that
source_type beyond the canonical-eight and `_UNIVERSAL_EXTRAS`, and a `contributor`
identifier for diagnostics.

**Host unions contributions per source_type at validation time:**

```
allowed = (
    _HOST_SOURCE_TYPE_EXTRAS.get(source_type, frozenset())
    | _addon_contributed_extras.get(source_type, frozenset())
    | _UNIVERSAL_EXTRAS
)
```

The validation algorithm runs once, in one place (host), against this unioned
vocabulary. No addon ships a callable validator; vocabulary is data, not code. This
eliminates the multi-validator debugging hazard of the γ-as-stated (callable) shape
and preserves a single traceable error-attribution path.

## Polarity rule

`CLAUDE.md § Ambition`: UE-specific code goes to the addon; common-language code
stays in host. The canonical-eight (`chunk_id`, `title`, `body`, `source_type`, etc.)
is universal across every language project-rag will ever index — it belongs in host.
UE source_type names (`cvar`, `community_tutorial`, `engine`, `blueprint_extraction`,
etc.) belong in the UE addon's hookimpl return, not in any host-side default dict.

`core/chunk_schema.py` must contain **zero UE source_type strings** at all times. The
cross-repo PR that introduces the seam must land host changes (seam + empty
`_HOST_SOURCE_TYPE_EXTRAS`) and addon changes (15 source_type specs via hookimpl)
atomically. There is no transitional state where host holds UE rows even temporarily.

## Anti-patterns (from Patrik consult, abridged)

These seven anti-patterns shaped the γ-prime design. The full analysis is in
`tasks/w2a-1i-revised/patrik-pluggy-seam-design-2026-05-16.md §5`.

**A. No UE rows in host — even as a "transitional default."** Framing like "Phase 1
keeps the UE dict in host, Phase 2 migrates it out" re-injects UE knowledge into host
for an indeterminate window and has been explicitly flagged as improvement-queue
laziness by PM. The cross-repo PR is atomic: host gains the seam with no UE rows in
the same commit-set as addon contributes them via hookimpl.

**B. "Addon owns algorithm" is wrong.** If you find yourself adding a callable
validator field to `AddonChunkMetadataExtrasSpec`, stop. The point of γ-prime over
γ-as-stated is that the algorithm stays host-side. Declarative specs (data) beat
callable specs (code) for the same problem — data can be unioned, inspected, and
diffed; callables cannot.

**C. `_UNIVERSAL_EXTRAS` is host-owned, not addon-extensible.** `context_prefix`,
`sub_index`, `sub_total`, `parent_chunk_id`, `chunker_id` are host pipeline state
injected by host code after the chunker runs (`chunker_id` stamped via
`indexer/chunk_utils.make_chunk()`). They are not source_type-keyed and are not
contributed through `project_rag_register_chunk_metadata_extras`. Collision detection
at registration time rejects any `extras` member that collides with `_UNIVERSAL_EXTRAS`
or the canonical-eight — so an addon attempting to register `chunker_id` in its
`extras` frozenset will raise `AddonRegistrationError`, which is correct behavior.

**D. Version bump must cite the façade dataclass, not the hookspec alone.** The
v6→v7 bump is triggered by the new `AddonChunkMetadataExtrasSpec` façade dataclass.
An additive hookspec without a new façade does NOT bump per the established rule
(`core/addon_hookspecs.py:39-41`). Get this right in the bump-rationale comment or
future maintainers will misread which rule fired.

**E. The 5 Layer-1 FAILs are downstream of the seam.** The specific chunker bugs
(missing canonical fields like `cvar`'s `type` field) can be fixed under either the
old closed-allow-list or the new hookimpl return. PM's recurrence-pattern concern is
addressed structurally by this seam; the individual FAILs are addon-team followup,
not a host gate.

**F. No second copy of the addon's `chunk_schema.py`.** After migration, the addon's
`chunk_schema.py` is deleted (not shimmed). Addon imports `Layer1ChunkRecord` etc.
directly from `core.chunk_schema`. A live re-export shim left in place would
reintroduce the drift problem in a new location.

**G. Separate hookspec — do not fold into `AddonChunkerSpec`.** A chunker may emit
multiple `source_type` values; non-chunker entities (post-processors, synthesizers)
may also contribute source_types. Folding extras into `AddonChunkerSpec` would
exclude those contributors and force a per-chunker granularity that doesn't match
the per-source_type semantics. Separate hookspec is the correct granularity at v7.
Merging them is a v8+ conversation if ever needed.

## Hookspec contract

```python
@hookspec  # parallel-call (no firstresult) — registration hookspec
def project_rag_register_chunk_metadata_extras() -> "list[AddonChunkMetadataExtrasSpec]":
    ...
```

| Property | Value |
|---|---|
| Name | `project_rag_register_chunk_metadata_extras` |
| Pluggy semantics | parallel-call (no `firstresult`) — host collects all returns |
| Signature | `() -> list[AddonChunkMetadataExtrasSpec]` |
| Graceful-fail | return `[]` when no extras applicable for this addon |
| Collision guard | `extras ∩ (canonical-eight ∪ _UNIVERSAL_EXTRAS)` must be empty; collision raises `AddonRegistrationError` at registration time (not silently accepted or dropped) |

`AddonChunkMetadataExtrasSpec` fields (frozen dataclass, `core/addon_protocol.py`):

| Field | Type | Purpose |
|---|---|---|
| `source_type` | `str` | The `source_type` string this spec applies to (must match the value the chunker emits) |
| `extras` | `frozenset[str]` | Optional field names permitted for this `source_type` beyond the canonical-eight and `_UNIVERSAL_EXTRAS`. Empty frozenset is valid — explicit is better than implicit. |
| `contributor` | `str` | Free-form identifier for the registering addon/chunker. Conventionally matches the chunker `id`. Used in error messages and collision diagnostics. |

Collision semantics: when two specs register the same `source_type`, the host unions
the `extras` frozensets (additive — extras are a vocabulary, not an exclusion list).
Multiple contributors for the same `source_type` is legal. Conflicting *meanings* for
the same field name across contributors are a coordination problem; host has no
dispute-resolution mechanism.

## Freshness contract

The extras registry is collected fresh per validation-init, mirroring the v6
`register_schema_edge_types` precedent (`core/addon_hookspecs.py:543-577`), where
`EdgeTypeRegistry` is constructed fresh per `init_graph_db` invocation with no
module-global state. This is the safer contract for partial-boot and test scenarios
where addon discovery may not have run. Module-global caching is permitted only with
an explicit runtime assertion that discovery has completed before any validation call
(option b of Stub 3); see the plan's Stub 3 spec for the named exception path.

## Engine-agnostic compliance

`project_rag_register_chunk_metadata_extras` contains no UE vocabulary
(`blueprint`, `bp_`, `unreal`, `holodeck`, `uproject`, `umap`, `uasset`). It is
engine-agnostic-compliant. It must be explicitly registered in a `_V7_HOOKSPEC_NAMES`
list in `tests/addons/test_v5_hookspec_naming.py` — the test's static lists (`_V5_`,
`_V6_`) require explicit opt-in; new hookspecs are not auto-covered (Stub 2 of the
plan handles this).

## Supersession of addon's chunk-landing-policy

`X:/project-rag-ue-addon/docs/reference/chunk-landing-policy.md` previously served
as an informal description of chunk field conventions, including some field names that
overlap with the canonical-eight. After v7:

- **Canonical authority for canonical-eight requirements:** `core/chunk_schema.py`
  (host). The landing-policy document is no longer authoritative for which fields are
  required in every chunk.
- **Landing-policy retains authority for:** addon-internal pipeline conventions (how
  content enters the corpus, curation tiers, git-tracking policy, chunker script
  references). These are UE-addon internal concerns not covered by the host schema.

An addon-side doc update to the landing-policy is followup work for the addon team
and is not a host gate for this plan.

## References

- Plan: `docs/plans/2026-05-16-host-pluggy-chunk-metadata-schema-seam.md`
- Patrik consult: `tasks/w2a-1i-revised/patrik-pluggy-seam-design-2026-05-16.md`
- v6 precedent: `core/addon_hookspecs.py:543-577` (`register_schema_tables`, `register_schema_edge_types`)
- Addon protocol v7 bump notes: `docs/wiki/addon-protocol.md` (v7 section)
- Polarity rule: `CLAUDE.md § Ambition`
- Façade discipline: `tests/addons/test_facade_discipline.py`
- Engine-agnostic tripwire: `tests/addons/test_v5_hookspec_naming.py`
