---
title: CorpusBand protocol — field-by-field contract
created: 2026-05-19
status: active
spec_backlink: docs/plans/2026-05-19-host-side-engine-corpus-unreachable-fix.md §S-1a §S-1b
relates_to:
  - docs/wiki/addon-protocol.md
  - docs/wiki/host-vs-addons.md
  - docs/wiki/host-addon-separation-of-concerns.md
  - docs/wiki/engine-rag-runtime-contract.md
---

<!-- Imported from X:/project-rag at SHA d376cb01. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — sibling-repo layout doctrine now lives in this repo's own wiki (the meta-repo local-doctrine file this once pointed at is retired). --> <!-- foreign-path-ok: dated import provenance, not a current-location claim -->

<!-- Spec backlink: docs/plans/2026-05-19-host-side-engine-corpus-unreachable-fix.md §S-1a (CorpusBand.structural_index_resolver addition) §S-1b (this wiki) -->

# CorpusBand Protocol

The complete, field-by-field contract for `CorpusBand` — the dataclass addons
use to register a queryable corpus with the project-rag host.

> **Umbrella principle.** This wiki documents the mechanics of one protocol
> dataclass. For the broader principle governing why host-addon protocol surfaces
> are shaped the way they are, see
> [host-addon-separation-of-concerns.md](host-addon-separation-of-concerns.md).

`CorpusBand` is defined in `core/addon_protocol.py`. It is registered by addons
via the `project_rag_register_corpus_band` hookspec (or, for engine addons, via
`project_rag_register_engine_corpus`). The host aggregates registered bands at
boot into `_BANDS_BY_NAME` (the in-memory band catalog).

---

## Protocol version

`ADDON_PROTOCOL_VERSION` is defined in `core/addon_protocol.py` and is the
single source of truth for the host-addon contract version. The current value is
documented in [addon-protocol.md](addon-protocol.md) § Version constant.

**When to bump:** `ADDON_PROTOCOL_VERSION` bumps on breaking changes — field
removal, field rename, semantic change to an existing field, hookspec signature
change, or `PreflightVerdict` enum extension. See Z-AMEND-1 below for the
additive-optional carve-out.

---

## Fields

### `band_name: str`

Unique opaque identifier for this corpus band, used as the `source=` kwarg
value in MCP query tools (`project_semantic_search`, `project_cpp_symbol`, etc.)
and as the key in `_BANDS_BY_NAME`.

**Host consumer semantics:** treated as an opaque string. The host does not
parse, split, or pattern-match the name. Equality comparison only.

**Addon authoring convention:** use `<engine>_<version>_<kind>` (e.g.,
`unreal_5.7_runtime`). Convention is addon-internal; the host does not enforce
it.

---

### `corpus_root: str | None`

Root directory of this band's corpus artifacts on disk, as a `str`. The host
uses this value to resolve the Chroma vector store for semantic search. `None`
when the band does not provide a local corpus root (e.g., for bands that resolve
everything via `structural_index_resolver` only).

**Path objects must be converted to `str` before assigning:** `corpus_root=str(my_path)`.
`validate_corpus_band` flags `Path` objects as a violation.

**Host resolution convention for Chroma:** the host walks a documented sub-path
under `corpus_root`:

- Engine-kinded bands: `<corpus_root>/engine-vector-store/<engine_version>/chroma/`
- Universal bands: `<corpus_root>/corpus-vector-store/<version>/chroma/`

**This sub-path convention IS the protocol surface.** The host walks the subtree
by specification, not by accident. This is the v10 `collection_name`-opacity
precedent: the addon's documented sub-path layout IS the contract. Addons that
relocate their Chroma store must update `corpus_root` accordingly.

**Chroma-symmetry note.** `corpus_root` is intentionally value-shaped (a raw
`str`) rather than a resolver callable. Future work MAY migrate Chroma
resolution to a parallel `corpus_root_resolver: Callable[[], Path] | None`
field, which would give Chroma the same opaque-resource semantics as
`structural_index_resolver`. That migration is out of scope here: the chroma
layout IS documented and works; unlike the structural-index path (which was
never a documented `corpus_root` sub-path convention), the sub-tree walk IS the
documented contract. See plan Followups in the spec backlink.

---

### `corpus_sha256: str | None`

SHA-256 of the corpus artifact bundle at index time. Used by the host for
provenance fingerprinting and corpus-change detection. `None` when the addon
does not track content hashes (acceptable for live-editor-backed corpora).

---

### `applicable_kinds: list[str] | None`

The corpus-class kinds this band applies to (e.g., `["engine"]` for
engine corpora, `["example"]` for example corpora). `None` means
universal — the band applies to all query shapes regardless of kind.

**Host consumer semantics:**
- `applicable_kinds=None` → universal band; always included in blend when band
  is registered, exempt from per-kind diversity guarantee regardless of weight.
- `applicable_kinds=["engine"]` → band participates in the engine
  lane of blended queries; subject to per-kind diversity guarantee when band
  weight ≥ `diversity_weight_floor`.

The host uses `applicable_kinds` to determine which resolution chain step should
invoke `structural_index_resolver` (H-2: iterate bands, check
`applicable_kinds` for engine-class membership before invoking).

---

### `engine_version: str | None`

Engine version string for engine-kinded bands (e.g., `"5.7"`). `None` for
universal bands. Used in the Chroma sub-path convention and in diagnostics.

---

### `default_weight: float`

Default multiplicative band weight in blended queries. Applied when no
caller-supplied `band_weights` entry overrides the band. Weight resolution chain
(highest priority first): caller kwarg → `PROJECT_RAG_BAND_WEIGHT_<band_name>`
env var → `CorpusBand.default_weight`.

---

### `required_env: list[str]`

Environment variable names that must be set for this band to be usable. The
host checks each name at boot; missing vars produce a `DEGRADED` health entry
with an actionable hint. Empty list means the band has no env prerequisites.

---

### `structural_index_resolver: Callable[[], Path] | None = None`  *(added S-1a)*

Callable that the host invokes to obtain the filesystem path of this band's
structural index (sqlite3 database). Introduced to decouple the host's path
resolution chain from any assumption about where the addon stores its structural
index on disk.

#### Semantics

| Field value | Meaning |
|---|---|
| `None` | Band declares no structural-index backing. The host's resolution chain falls through to the next step. This is also how addons signal "corpus not yet materialized." |
| `Callable[[], Path]` | Band has a structural-index backing. Host invokes the callable lazily (at resolution time, not at boot) to obtain the sqlite3 path. |

There is no "resolver returns `None`" state. The type signature commits to a
`Path` return. Addons that cannot produce a path for a given band must leave
the field `None` rather than registering a resolver that conditionally returns
`None`. The sentinel for "corpus absent" is `structural_index_resolver=None`.

#### Opaque-resource contract (type-enforced via callable shape)

Once the resolver returns a `Path`, the host opens it (sqlite3 connection) and
stops. **The host MUST NOT:**

- Derive sibling paths (e.g., a metadata sidecar next to the sqlite3 file)
- Walk parent directories to find adjacent artifacts
- Glob siblings or pattern-match the filename
- Assume anything about the directory layout around the returned path

The `Path` is an opaque handle. Anything adjacent the host needs is a separate
`CorpusBand` field (e.g., a future `structural_index_metadata_resolver` field),
not a path derivation. This contract is **type-enforced** by the callable shape:
the host never sees a directory, only a `Path`. The "host-MUST-NOT-derive-
siblings" rule being type-enforced (rather than doc-enforced) is deliberate —
doc-enforced contracts decay under refactor; type-enforced ones don't. See
[codebase-judgment/typed-surface-over-text-pattern.md](../../../../../plugins/project-rag/docs/wiki/codebase-judgment/typed-surface-over-text-pattern.md)
for the convergent judgment grounding this design choice.

#### Invocation discipline (host-side)

The host invokes the resolver **lazily** — at resolution time in `paths.py`,
not at boot in `aggregate_at_boot()`. This ensures addons that haven't
materialized a corpus yet don't cause boot failures.

The **protocol does NOT promise Path stability across invocations.** The addon
may relocate artifacts between invocations (rare but permitted by the protocol).
The host MUST NOT memoize the returned `Path` beyond the immediate resolution
chain entry. Connection sharing happens at the sqlite-opener layer, keyed by the
most-recently-resolved `Path` (a separate concern from resolver invocation).

The host catches `addon_errors.AddonResolutionError` from the resolver and
records it in `resolution_trace` without propagating as a host crash. The host
also catches bare `Exception` defensively (log warning, treat as resolution
failure — the resolver should have raised `AddonResolutionError`, but the
resolution chain must remain robust to malformed addons).

#### Multi-band-same-path behavior

Today's UE addon resolves all four engine bands (`unreal_5.7_runtime`,
`unreal_5.7_editor`, `unreal_5.7_plugin`, `unreal_5.7_lyra`) to the **same**
merged sqlite3 path. Per-band row discrimination happens inside the sqlite via
`WHERE source = '<discriminator>'` on `symbols` / `calls` / `inherits`. The
host's sqlite-opener layer caches+shares connections keyed by **resolved Path**,
not band identity — two bands returning the same Path share one handle.

---

## Back-compat rules

### Additive-optional fields (no version bump required — Z-AMEND-1 carve-out 2)

A new field added with `= None` default that introduces an **opt-in dispatch
path unreachable without the new field** does NOT require an
`ADDON_PROTOCOL_VERSION` bump. The qualifying conditions are:

(i) Pre-bump addons leaving the field `None` observe **identical host behavior**
   (the resolution chain falls through to the next step).
(ii) The new dispatch branch is **unreachable** without an addon populating the
   field with a non-None value.
(iii) Any new observability (e.g., `resolution_trace` entries) is provenance, not
   behavior — it records what the chain did, does not change what it returns to
   callers.

`structural_index_resolver` qualifies under all three conditions. S-1a
deliberately did NOT bump `ADDON_PROTOCOL_VERSION`.

**Addon forward-compat guard:** post-S-1a addon hookimpls that want to supply a
resolver check `"structural_index_resolver" in CorpusBand.__dataclass_fields__`
before setting the field. Pre-S-1a hookimpls that do not set the field remain
valid.

### Breaking changes (version bump required)

Any of the following requires an `ADDON_PROTOCOL_VERSION` bump:
- Removing or renaming a field
- Changing the semantic meaning of an existing field
- Changing a field's type in a backward-incompatible way (e.g., `Path` →
  `list[Path]`)
- Making an optional field required
- Changing hookspec signatures

---

## Validation helper

`core/addon_protocol.py` exports a `validate_corpus_band(band) -> list[str]`
helper. Addons can call it against their own `_make_*_band()` outputs before
registration. Returns a list of violation strings (empty if conformant). Checks
include:

- `structural_index_resolver` is either `None` or callable — catches the
  migration footgun where an addon developer copies the old
  `structural_index_path: str` shape and assigns a string to the new field.
- `band_name` must be a non-empty string.- `default_weight` is a non-negative float.

---

## Closed-world verdict palette — migration note for addon authors

Addons that contribute `FailureCatalogRow` entries via
`project_rag_register_doctor_probe` declare a `runtime_verdict` field on each
row. The host enforces a **closed-world palette** for this field — the row's
verdict must be one of `_VALID_ENVELOPE_VERDICTS` in
`core/source_registry.py` (currently 22 entries at `ENVELOPE_VERSION=6`).
An addon that ships a row with a verdict outside the palette causes the host
to raise `AddonCatalogInvalidVerdict` at `aggregate_at_boot()` time —
**daemon boot fails loud, not silent**.

Addons may NOT extend the palette. If a genuinely new failure shape needs a
new verdict, that's a host-side `ENVELOPE_VERSION` bump (per
`docs/wiki/codebase-judgment/verdict-palette-reuse-before-add.md`) coordinated
with the host team. Until the bump ships, addons relabel to the closest
existing verdict (semantic match preferred over exact-string match).

**Empirically (addon-EM rev-4 sweep):** the addon's `A-F-22`
(`sentinels_absent`) and `A-F-23` (`umbrella_source_rejected`) rows failed boot
post-`419b8d16`. Mechanical relabel succeeded: `A-F-22` → `registered_but_not_setup`
(semantic match — project IS registered, a setup phase didn't run);
`A-F-23` → `input_invalid` (exact match of actual failure verdict).

The full palette is greppable in `core/source_registry.py:_VALID_ENVELOPE_VERDICTS`.

---

## See also

- [host-addon-separation-of-concerns.md](host-addon-separation-of-concerns.md)
  — umbrella principle governing why protocol fields are shaped as resolvers vs.
  raw values; the decision rule for new protocol-surface design.
- [addon-protocol.md](addon-protocol.md) — full `ADDON_PROTOCOL_VERSION` bump
  history; Z-AMEND-1 boundary analysis; hookspec table.
- [host-vs-addons.md](host-vs-addons.md) — host/addon polarity; what lives in
  the host vs. what lives in addons.
- [engine-rag-runtime-contract.md](../../../../../plugins/project-rag/docs/wiki/engine-rag-runtime-contract.md) — runtime
  contract for engine RAG; CorpusBand version lifecycle; AD-5 default-blend
  mechanics.
