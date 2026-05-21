---
title: "source= addressing scheme — umbrella tokens, specific bands, multi-source"
status: shipped
shipped_in_wave: cross-repo-host-state-engine-collection-wiring
spec: docs/wiki/source-kwarg-routing.md (consumer-facing companion)
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-19-host-side-engine-corpus-unreachable-fix.md §S-4 -->

# `source=` addressing scheme — umbrella tokens, specific bands, multi-source

> **Audience:** anyone writing a consumer that calls a project-rag MCP tool with `source=`,
> anyone authoring an addon that contributes a corpus band, anyone reviewing a probe that
> asserts contract on `source=` validation. If you just want the "which value do I pass"
> table, see [`source-kwarg-routing.md`](source-kwarg-routing.md). This wiki is the
> *conceptual model* behind those values.

## TL;DR

The `source=` value space is **one-level flat**. There are three resolvable shapes and one
sentinel:

| Shape | Example | Resolution |
|---|---|---|
| **Specific band name** | `source="unreal_5.7_runtime"` | Exact match against `CorpusBand.band_name` |
| **Umbrella token** | `source="unreal"` | Fan-out to all bands whose `applicable_kinds` contains the token |
| **Multi-source list** | `source=["unreal", "dronesim"]` | Per-source resolution then merge (internal backend only) |
| **None / omitted** | `source=None` | AD-5 default-blend across registered bands |

There is **no two-level addressing**. There is no `engine`, `editor`, `runtime` *meta-umbrella*
above the kind tokens. There is no hardcoded enum at the host layer.

## The applicable_kinds-as-umbrella convention

Umbrella tokens are **derived from band declarations**, not declared at the host. Specifically:

```python
# Authoritative at project_rag_mcp/tools/audit.py:_known_source_names()
umbrella_tokens = {
    kind
    for band in source_registry.all_bands()
    for kind in (band.applicable_kinds or ())
}
```

If a band declares `applicable_kinds=["unreal"]`, then `"unreal"` becomes a valid umbrella
the moment that band registers. If no band declares a given kind, that kind is **not** a
valid source value — `_known_source_names()` rejects it with `verdict=input_invalid`.

This is content-agnostic by construction. There is no host-level vocabulary for
"engine", "editor", "runtime" — those are conventions addons may follow in their band
naming (`unreal_5.7_runtime`, `unreal_5.7_editor`), but they are not categories the host
addresses.

### Why this shape

Asymmetric corpus classes:

| Class | Has kind? | Addressing |
|---|---|---|
| Engine corpora (e.g. `unreal_5.7_runtime`) | Yes (`applicable_kinds=["unreal"]`) | Kind acts as umbrella; band name is specific |
| Example corpora (e.g. `dronesim`) | No (`applicable_kinds=None`) | Band name only — no umbrella |
| Project corpora (`project_runtime`, `project_plugin`) | No (`applicable_kinds=None`) | Band name only — no umbrella |
| Universal corpora (e.g. `template_example_band`) | No (`applicable_kinds=None`) | Band name only — no umbrella |

Engine-class bands are the only class with a kind, *because* the kind is meaningful
(searching "Unreal" vs "Unity" is a real consumer need). Project, example, and universal
classes don't have a meaningful super-category — the band name IS the address.

A two-level scheme (`engine.unreal`, `engine.unity`, vs `example.dronesim`, vs
`project.runtime`) would force every consumer to learn two-level naming for one class
and one-level for everything else. Net: more cognitive load, no expressive gain.

## Common consumer scenarios

### "Search Unreal 5.7 runtime corpus specifically"
```python
project_semantic_search(query="...", source="unreal_5.7_runtime")
```

### "Search anything Unreal-shaped, any version, any role (runtime/editor)"
```python
project_semantic_search(query="...", source="unreal")
```
Umbrella fans out to all registered bands with `"unreal" in applicable_kinds` — that
includes `unreal_5.7_runtime`, `unreal_5.7_editor`, `unreal_5.7_plugin`, `unreal_5.7_lyra`,
and any future `unreal_<v>_*` bands the addon adds.

### "Search across multiple engine kinds at once"
Today, with only Unreal kinds registered, `source="unreal"` already covers everything.
When Unity bands ship (say `unity_2023_runtime` with `applicable_kinds=["unity"]`),
cross-engine queries take one of two forms:

- Multi-source list (internal backend): `sources=["unreal", "unity"]`
- Default blend with no `source=`: omit the kwarg entirely; the daemon blends across all
  registered bands via AD-5.

There is no `source="engine"` meta-umbrella. If you find yourself reaching for one,
write the multi-source list instead, or omit `source=` and rely on the default blend.

### "Search everything the daemon knows about"
```python
project_semantic_search(query="...")  # source=None
```
AD-5 default-blend triggers when `source=None` and addon bands are registered. Opt-out
with `default_blend=False`.

## Negative space — what the host explicitly does NOT do

| Anti-pattern | Why not |
|---|---|
| `source="engine"` as a meta-umbrella over all engine kinds | Re-introduces hardcoded enum the doctrine forbids; redundant with `source=[...]` and `source=None`+default-blend |
| `source="engine.unreal"` two-level notation | Asymmetric vs project/example/universal classes; no expressive gain |
| Hardcoded acceptance of `"engine"`, `"plugin"`, `"editor"`, `"runtime"` as tokens | Host has no vocabulary for these — they're addon-side conventions, not host categories |
| `kind=` as a separate filter kwarg alongside `source=band_name` | Demotes the kind from address-space to filter-space; net more complexity for the same expressiveness |

The host enforces this by deriving `_known_source_names()` from band declarations at boot
([`project_rag_mcp/audit.py:69-116`](../../../../../plugins/project-rag/project_rag_mcp/audit.py)). There is no
hardcoded enum to keep in sync; adding a new engine kind is purely an addon-side change.

## Authority — where the contract lives

| Surface | What it says | File:line |
|---|---|---|
| Resolver docstring | "Umbrella tokens are exactly the set of distinct `applicable_kinds` values across registered bands. No hardcoded enum." | `project_rag_mcp/tools/semantic.py:1861-1863` |
| Validator docstring | "S-4 extension: also includes umbrella tokens (distinct applicable_kinds values across registered bands)." | `project_rag_mcp/audit.py:77-79` |
| CorpusBand field doc | `applicable_kinds: list[str] \| None` — None means universal; non-None means engine-kinded with these umbrella tokens. | `core/addon_protocol.py:CorpusBand` |
| CLAUDE.md § Ambition | "project-rag is content-agnostic code RAG... UE is first-class only via project-rag-ue-addon." | `CLAUDE.md` |

## When to reconsider this shape

This wiki is not a permanent veto. The one-level scheme is correct *for today's
expressiveness needs*. The threshold for adding a meta-umbrella layer is:

1. A real consumer surfaces wanting "every engine kind at once" as a frequent operation, AND
2. Both `source=None`/default-blend AND multi-source list-form are demonstrably insufficient
   (specific empirical case, not anticipated need), AND
3. The asymmetry against project/example/universal classes can be resolved without bleeding
   the two-level scheme into those classes.

Until all three are present, "no meta-umbrella" stands. Surface a real example to PM if
you think you've found the threshold.

## Cross-references

- [`source-kwarg-routing.md`](source-kwarg-routing.md) — consumer-facing precedence chain
  and per-tool kwarg shapes
- [`multi-source-daemon.md`](multi-source-daemon.md) — internal resolver mechanics, boot
  aggregation, cwd-resolver middleware
- [`corpus-band-protocol.md`](corpus-band-protocol.md) — `CorpusBand` field-by-field
  reference, including `applicable_kinds`
- [`host-addon-separation-of-concerns.md`](host-addon-separation-of-concerns.md) — why
  the host has no engine vocabulary

## History

- **2026-05-19** — Wiki authored in response to cross-repo dialogue with
  project-rag-ue-addon EM on `source="engine"` umbrella naming question. The 419b8d16
  commit message's sloppy "source='engine' umbrella" phrasing prompted the question; this
  wiki is the authoritative contract surface, superseding that commit message's framing.
  applicable_kinds-as-umbrella convention itself dates to S-4 (engine-RAG named bands,
  2026-05-17).
