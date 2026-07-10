---
title: Addon Chunker Categories
created: 2026-05-15
status: active
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-15-addon-chunker-categories-field.md §Chunk 2 -->

# Addon Chunker Categories

Vocabulary reference for the `categories: list[str]` field on
`AddonChunkerSpec` (declared in `core/addon_protocol.py`). This field is an
orthogonal axis to `scope` — `scope` routes project-vs-engine; `categories`
discriminates within a scope band for filtered ingest.

## Overview

The `categories` field lets consumers select a meaningful subset of chunkers
at ingest time via `--include-categories` / `--exclude-categories` on
`cli.py engine-index`, without enumerating producer IDs (which rots at addon
version boundaries). The controlled vocabulary here makes the consumer-side
filter predicate semantic rather than arbitrary.

Cross-reference: `AddonChunkerSpec.categories` is threaded through to
`ChunkerEntry.categories` by `indexer/chunker_registry.py:_adapt_addon_chunker_spec`.
The filter helper `filter_by_categories()` in the same module applies the
predicate at the registry-walk site.

Protocol note: this field is additive-defaulted. No `ADDON_PROTOCOL_VERSION`
bump was required on introduction — see [addon-protocol.md](addon-protocol.md)
for the defaulted-additive rule.

## Initial vocabulary

Four categories ship with v1 of this field. The list is controlled, not
free-tag — adding a new category requires a PR with usage rationale (see
§ How to propose a new category below).

| Category | Intent |
|---|---|
| `substrate` | Raw extraction outputs that feed other producers or are too large / low-density for direct embedding. Examples: C++ header chunks, UDN source, structural index output. Typically consumed by reference-index builders, not directly embedded into a user-facing Chroma collection. |
| `curated` | Human-authored or editorially selected content intended for direct embedding in a user-facing knowledge base. Examples: engine guides, decision records, architecture docs. This is the primary category for the W-2a filtered ingest use case. Concrete chunkers using this category: `engine_bp_to_cpp_chunks` (existing precedent), `engine_cvar_chunks` (incoming, post-Chunk 4 on project-rag-ue-addon side). |
| `reference` | First-class API reference entities (classes, functions, CVars, config keys) that are authoritative, factual, and dense. Valuable to embed but distinct from `curated` prose — they are generated/extracted, not hand-authored. Examples: UDN API reference, CVar registry, Python API stubs. |
| `qa` | Evaluation Q&A pairs. Useful for retrieval benchmarking and fine-tuning but generally excluded from production embedding runs. |

### Decision rule: curated vs reference

When tagging a new chunker, the primary split is:

- **`curated`** — first-class extracted knowledge with descriptive prose. The content carries enough
  natural-language context that embedding it produces semantically useful neighbors. CVars with
  non-empty descriptions, BP-to-C++ correspondence chunks, and engine guide prose all qualify.
- **`reference`** — generated/extracted API stubs without prose. Raw class or function signatures,
  type hierarchies, or config-key enumerations where the value is in the symbol name, not
  surrounding text. Dense and authoritative, but embedding alone yields noisier retrieval than
  `curated` content.
- **Mixed nature** → dual-membership `["curated", "reference"]` per the multi-tag composition
  rule below. **Note: dual-membership is not yet load-tested under D-4 curated-only-by-default
  chroma build** — the first chunker to ship that combination should validate retrieval behavior
  empirically before declaring it production-safe.

### D-4 implication

Under the D-4 curated-only-by-default chroma build:

- A chunker tagged `["curated"]` **WILL** embed in the user-facing chroma and surface through
  `_engine_search`. This is the intentional behavior: `engine_cvar_chunks` carries
  `categories=["curated"]` so CVar knowledge embeds by default.
- A chunker tagged `["reference"]` **WILL NOT** embed by default (default excluded from the D-4
  curated-only pass). Embedding reference content requires an explicit `--include-categories=reference`
  flag at `cli.py engine-index` time.
- The uncategorized chunker case (`categories=[]`) is unaffected — see § Empty list —
  uncategorized below for the include/exclude/no-flag semantics.

Cross-link: see [`cross-repo-acceptance-coupling.md`](../../../../project-rag/docs/wiki/cross-repo-acceptance-coupling.md)
§ The pattern for the AC7 example, which is the canonical example-game-repo-side acceptance criterion
gated on D-4 curated chroma landing.

## Semantics

### Empty list — uncategorized

A chunker with `categories=[]` is **uncategorized**. The filter predicate
treats it as follows:

- `--include-categories X` — the chunker does **not** match (empty set has no
  intersection with `{X}`). An uncategorized chunker is invisible to any
  include predicate.
- `--exclude-categories X` — the chunker trivially passes (empty set has no
  intersection with `{X}`). An uncategorized chunker is never excluded.
- No filter flags — the chunker runs unconditionally (same behaviour as
  before the field existed).

This matches the `domain=[]` convention used elsewhere in this codebase
("empty means match all" for the `domain` gate, but the categories gate
inverts for include-predicates to avoid silently pulling in uncategorized
content when the caller asks for a specific subset).

### Multi-tag composition

A chunker may carry multiple categories. Example:

```python
AddonChunkerSpec(
    id="engine_epic_docs",
    runner=...,
    categories=["curated", "reference"],
)
```

This chunker matches `--include-categories curated`, `--include-categories
reference`, and `--include-categories curated,reference`. It is excluded by
`--exclude-categories curated` (the exclude predicate fires on any-of-excluded
intersection, so even one matching tag excludes the chunker).

### Filter precedence

The `filter_by_categories` helper applies **include-then-exclude**:

1. If `include` is specified, retain only entries where
   `set(entry.categories) & set(include)` is non-empty.
2. If `exclude` is specified, drop entries where
   `set(entry.categories) & set(exclude)` is non-empty.
3. If the same category appears in both `include` and `exclude`, a
   `ValueError` is raised immediately — this is a usage error, not silent
   inclusion or exclusion.

### No-flags behaviour

When neither `--include-categories` nor `--exclude-categories` is passed,
`filter_by_categories` is a no-op and all registered chunkers run. Existing
workflows that call `cli.py engine-index` without category flags are
unchanged.

## How to propose a new category

1. Open a PR that adds a row to the vocabulary table above.
2. Include at least one concrete chunker that would carry the new category
   (name the chunker `id` and the repo it lives in).
3. Explain why none of the existing four categories fit.
4. No runtime enforcement change required — the protocol does not validate
   category values at registration time.

Categories are advisory metadata. The enforcement mechanism is code review
and documentation, not a runtime allowlist.

## Per-Content-Family Chunk Sizing

*Source: project-rag-ue-addon, 2026-05-29. [universal]*

When corpus families have very different size distributions (e.g. short CVar entries vs. multi-page UDN guides vs. dense C++ header blocks), a single global worst-case chunk cap wastes embedding budget on families where smaller chunks would produce sharper retrieval, and over-splits families where larger chunks carry coherent semantics.

**Rule.** Size chunks per content family, not globally. Each chunker registered under a category (`substrate`, `curated`, `reference`, `qa`) should declare its own `chunk_size` / `overlap` tuned to the typical token density of its corpus family. The global cap remains as a hard ceiling; per-family sizing is the floor that operates below it.

This is especially important when adding a new category: establish the per-family sizing baseline before wiring the chunker into the curated-only chroma build, or the global cap silently governs and retrieval quality degrades on dense families.

## Cross-repo parity and the silent-degrade contract

Addons MAY ship with categories that the host has not heard of. The filter
predicate uses set-intersection, so an unknown category simply does not match
any host filter — it degrades silently to no-match rather than raising an
error.

Example: an addon ships `categories=["proprietary_internal"]` before that
category is added to this wiki. The host's `--include-categories curated`
will not include it (correct — unknown ≠ curated). The host's
`--exclude-categories substrate` will not exclude it (correct — unknown ≠
substrate). The addon author gets the expected neutral behaviour without
needing a coordinated host update.

This contract means:

- **Addon authors** can tag freely in development; host filters ignore tags
  they don't know about.
- **Host consumers** can add a new category to this wiki and start filtering
  on it once addons start declaring it — no protocol bump needed.
- **Drift** between addon-declared categories and this vocabulary is surfaced
  by code review on the addon side, not by runtime enforcement.
