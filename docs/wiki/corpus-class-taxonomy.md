<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

# Corpus-class taxonomy

> How `(source, authority)` pairs classify into corpus classes, and what a new binding (engine, knowledge, or other) must do to fit cleanly.

## Corpus classes: principled taxonomy

Three classes, principled rules, open-ended extension:

| Class | Authority value(s) | Corpus content | Examples |
|---|---|---|---|
| `engine` | `"api"`, `"editor"` | First-party engine source code | UE runtime, UE editor, Unity core assemblies |
| `example` | `"reference"` | Sample/reference projects layered on an engine | Lyra, CitySample, community demo projects |
| `knowledge` | `"knowledge"` | Documentation, decisions, lessons, system meta-knowledge | Coordinator wikis, project ADRs, lessons files |

Extension rule: if a new corpus type does not fit any of the three classes above,
extend the `Literal` return type of `corpus_class_for` (in `core/structural_schema.py`)
and add a row here. Do NOT overload an existing class for a semantically distinct
corpus type — that is the root cause of the "engine vs example" confusion that
motivated the original split (the Data Science Reviewer memo 2026-05-16). Vendored-parity rule
applies: extend all three vendored sites (`gate_structural_index.py:KNOWN_GOOD_PAIRS`,
addon read mirror, `core/structural_schema.py:_CORPUS_KNOWN_GOOD_PAIRS`) in one
commit and run `tests/test_schema_constant_parity.py`.

## What it is

A read-side classifier (`core/structural_schema.py:corpus_class_for`) maps a structural-index row's `(source, authority)` pair into a corpus class:

- **`engine`** — engine source: UE runtime / plugin / editor C++. `authority in {"api", "editor"}`.
- **`example`** — sample/reference projects layered on an engine: Lyra, CitySample, community samples. `authority == "reference"`.
- **`knowledge`** — meta-knowledge corpora: project/system documentation, decisions,
  lessons, plan history, coordinator wikis. `authority == "knowledge"`.
- **`None`** — project rows, or any unrecognised pair. Caller decides.

`host_state.get_corpus_class_sources(cls)` derives the **set of source names** in each class from the vendored pair set `_CORPUS_KNOWN_GOOD_PAIRS`. Engine-backed tool handlers (addon-side `engine_symbols`, `engine_hierarchy`, `engine_symbol_graph`) use this to scope SQL by class rather than enumerating sources literally.

## Why two classes, not one

Engine source and sample projects are physically similar (both are "not your project's code") but query semantics differ:

- An "engine API lookup" should not return Lyra's `ULyraCharacter` even though Lyra's source is in the same structural index.
- A "find a reference implementation" query should *prefer* sample-project rows over engine internals.
- Future sample corpora beyond Lyra (CitySample, community demos) need to fit without code edits — they share the `reference` authority and join the existing class automatically.

The Data Science Reviewer's rationale memo: `X:/project-rag-ue-addon/tasks/the Data Science Reviewer-engine-examples-split-2026-05-16.md`.

## Three-site vendored parity

The pair set is **vendored, not imported** — three independent copies must stay in lockstep:

| Site | Path | Role |
|---|---|---|
| Addon gate (authority) | `X:/project-rag-ue-addon/scripts/gate_structural_index.py:KNOWN_GOOD_PAIRS` | Write-side: rejects unknown pairs at ingestion |
| Addon read mirror | `X:/project-rag-ue-addon/<…>` (parity-tested) | Addon-side handlers |
| Host read mirror | `core/structural_schema.py:_CORPUS_KNOWN_GOOD_PAIRS` | This repo's `host_state` |

Parity is enforced by `tests/test_schema_constant_parity.py` (set-equality on all three). Vendoring (not importing) is deliberate: the host runs without the addon installed, and the addon must not become a runtime import dependency of the host's read path.

## No caching on the getter

`get_corpus_class_sources(cls)` recomputes from the pair set on every call. No `functools.cache`. Reasons (the Staff Engineer P2-2, 2026-05-16):

- Hot-reload safety during development (pair-set edits take effect immediately).
- Test isolation — no per-process cache to invalidate between cases.
- Overhead is dwarfed by the SQL the result feeds into; caching would be a measurement-free micro-optimisation.

## Adding a new binding (engine, knowledge, or other)

The "engine" section below originally covered only engine corpora. Adding any new
corpus type follows the same three-step pattern.

### Adding a new engine (Unity, Godot, …)

When the next engine addon ships, the engine-vs-example split must still hold. Three things have to land together:

1. **Pick an `authority` value per the existing rules** — engine code uses `api` (or `editor` for editor-only symbols); reference/sample projects use `reference`. Do **not** invent a new authority for "Unity engine" — `api` already classifies as `engine` and that is correct. Inventing a parallel authority forks the taxonomy.
2. **Pick `source` names that namespace the engine** — e.g. `unity_runtime`, `unity_editor`, `unity_samples`. Source names are free-form; authority is the classification rule.
3. **Add the new pairs to all three vendored sites in one commit** and run `tests/test_schema_constant_parity.py`. The addon gate copy is authoritative; host and addon-read mirrors follow.

The classifier itself does not change. The pair set grows; the `(api|editor) → engine`, `reference → example` mapping stays put. If a new engine has a structurally different category (e.g. an asset-only corpus with no symbols), that is a new class — extend the `Literal` return type and update consumers, do not overload `engine`/`example`.

**Anti-pattern:** UE-special-casing the classifier (e.g. `if source.startswith("engine_")`). The current implementation deliberately reads only `authority`, which is engine-agnostic. Keep it that way.

### Adding a non-engine corpus type

If the corpus type does not use `api`/`editor`/`reference`/`knowledge` authority:

1. **Decide the authority value** — pick a new authority string that honestly
   describes the corpus's role. Keep it short and lowercase (e.g. `"training"`,
   `"benchmark"`).
2. **Extend the corpus-class taxonomy** — add a row to the table in §"Corpus classes: principled taxonomy" above and a
   rule to `corpus_class_for` (new elif branch on the new authority).
3. **Extend the `Literal` return type** in `core/structural_schema.py:corpus_class_for`.
4. **Update all three vendored sites** and run `tests/test_schema_constant_parity.py`.

Anti-pattern: Inventing a new corpus class when the existing three cover it.
`coordinator_knowledge` uses authority `"knowledge"` and class `"knowledge"` —
it does not need a new class.

## See also

- Plan: `docs/plans/2026-05-16-wave-2b-engine-si-handler-schema-drift.md` (Chunk 0 — origin)
- Authority column convention: `core/structural_schema.py` § "authority column convention (PR-3 multi-rag-coexistence)"
- Host/addon split: [host-vs-addons.md](host-vs-addons.md)
- Cross-repo memo: `X:/project-rag-ue-addon/tasks/cross-repo-memo-2026-05-16-to-project-rag-em.md`

The addon-side wiki `mcp-port-mental-model.md`
describes a complementary but distinct framing. That wiki operates at
**port-multiplexing altitude**: one MCP server port serves multiple corpus classes
simultaneously, and the mental model concerns how a consumer distinguishes engine
corpus results from project corpus results at the transport level. This wiki operates
at **within-row classifier altitude**: given a structural-index row, how does
`(source, authority)` map to `engine | example | knowledge`? The two framings are
orthogonal — the classifier here runs inside the server; the port model describes how
a consumer addresses it from outside.
