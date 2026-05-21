---
title: Addon Protocol
created: 2026-05-08
status: active
last_distilled: 2026-05-14
distilled_from:
  - docs/plans/2026-05-08-ue-carveout-wave-2.md
  - docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-08-ue-carveout-wave-2.md §A-2 §B-1 §B-5 §B-6 §C-1 §C-4 -->
<!-- Spec backlink: tasks/ue-carveout-wave-2/PR-9-receiver-harness.md (sole author / wiki serializer) -->
<!-- Spec backlink: docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md (v1→v2 bump, 7th register hookspec) -->

# Addon Protocol
<!-- Review: Sonnet burst-2 P2-2 — dropped "v1" version qualifier from title; protocol version lives in body (ADDON_PROTOCOL_VERSION constant) -->

The stable, versioned contract between the project-rag host and domain addons.
Wave 2a (scaffold) lands the seam, hookspecs, façade types, and discovery
machinery. UE-specific code stays in-tree behind these seams; physical
extraction to `claude-unreal-holodeck` is Wave 2b.

## Overview

- **Purpose:** stable versioned contract between project-rag host and domain
  addons. Internal types may churn freely; façade-shape changes require an
  `ADDON_PROTOCOL_VERSION` bump.
- **Version constant:** `ADDON_PROTOCOL_VERSION = 14` — defined in
  `core/addon_protocol.py` (single source of truth). Bump-notes chain:
    * `1 → 2` (tc-2, 2026-05-13): `AddonLongLivedSubprocessSpec` façade added for
      long-lived subprocess hosting. New façade dataclass = surface-shape change.
    * `2 additive` (W1, 2026-05-14): `project_rag_register_producer` hookspec
      added with pre-existing `AddonProducerSpec` façade. **No bump** — tc-6
      precedent (additive hookspec, no new façade).
    * `2 → 3` (tc-4, 2026-05-14): `AddonDiagnostic` + `AddonReconciledDiagnostic`
      façades added for the F-L4 three-layer (UHT + Redpoint Clang + tree-sitter)
      reconciliation host. New façades = surface-shape change. Reconciler module
      + policy wiki: `project_rag_mcp/tools/reconciler.py`, `docs/wiki/f-l4-reconciliation-policy.md`.
    * `4 → 5` (WS-1 Step 3, 2026-05-15): Five new hookspecs for multi-language
      core-spine, each with a new façade dataclass in `core/addon_dataclasses.py`:
      `project_rag_register_cpp_source_roots` → `AddonCppSourceRootsResult`;
      `project_rag_register_provenance_classifier_rules` → `AddonClassifierRuleSpec`;
      `project_rag_register_eval_bank` → `AddonBankSpec`;
      `project_rag_register_eval_probe` → `AddonProbeSpec`;
      `project_rag_register_health_field` → `AddonHealthFieldSpec` + `HealthContext`.
      Also absorbs coordinated `ENVELOPE_VERSION 2 → 3` bump (per-hit
      `authority` + `feature_level` propagation on `data.hits[*]`).
      Health-field subfields land in the `addon_fields` envelope sub-block —
      NOT inside `_collect_project_block` (which is .uproject-gated).
    * `5 → 6` (2026-05-16): bundles three new façade dataclasses +
      four register_* hookspecs for the cross-workstream v6 landing:
      (a) AddonCliSubcommandSpec + project_rag_register_cli_subcommand —
          host-side CLI subcommand registration; enables UE-shaped
          subcommands (e.g. `engine-index`) to migrate from host `cli.py`
          to addon hookimpls without host knowing the subcommand name.
      (b) AddonWatchPatternSpec + project_rag_register_watch_pattern —
          filesystem watch-pattern registration; de-leaks watcher's
          `_ASSET_EXTS` / `_CPP_EXTS` / `_CONFIG_EXTS` UE-specific
          constants. Companion hookspec `project_rag_register_watch_ignore_segments`
          (no façade — additive, no bump trigger of its own) replaces
          hardcoded `_DEFAULT_IGNORE_SEGMENTS`.
      (c) AddonMacroSkipListSpec + project_rag_register_extra_macros —
          C++ structural-index macro-skiplist registration; union semantics
          so multiple addons (UE, future Unity, future Rust) can each
          contribute their own runtime macro lists.
      Three new façade dataclasses = three surface-shape changes; bump-once
      economics bundle them into v6 rather than v6→v7→v8. Per v5 precedent
      (5 façades bundled).
    * `6 → 7` (γ-prime, 2026-05-16): new façade dataclass
      `AddonChunkMetadataExtrasSpec` — frozen dataclass with three fields
      (`source_type: str`, `extras: frozenset[str]`, `contributor: str`) that
      addons return via the new `project_rag_register_chunk_metadata_extras`
      hookspec (parallel-call, returns `list[AddonChunkMetadataExtrasSpec]`).
      The bump is triggered by the **new façade dataclass**, NOT the hookspec
      addition alone — per the established rule (the Staff Engineer anti-pattern D: additive
      hookspec without new façade does not bump). This seam relocates the Layer-1
      chunk metadata validation algorithm to host (`core/chunk_schema.py`) and
      moves the per-source-type extras vocabulary from the addon's closed
      allow-list (`SOURCE_TYPE_EXTRAS` dict) to declarative hookimpl returns —
      the same architectural shape as the v6 `register_schema_tables` /
      `register_schema_edge_types` precedent. Zero UE source_type names in host
      code (polarity rule). Full contract:
      [`docs/wiki/chunk-metadata-schema-seam.md`](chunk-metadata-schema-seam.md).
      Spec backlink:
      `docs/plans/2026-05-16-host-pluggy-chunk-metadata-schema-seam.md`.

      **Joint v6 surface — concurrent W8c T1 contribution (commit `6e4dee00`)
      lands eight additional façades + eight hookspecs under the same v6
      stamp** (no separate bump; bump-once economics across workstreams):
      (d) host-addon-capability-dispatch (W8a AC-3): AddonCapabilityResult,
          AddonContentErrorClassification, AddonRuntimeLogSummary,
          AddonRuntimeBinaryResolution, AddonRuntimeDispatchResult,
          AddonQueryRoutingSpec (6 façades) + provide_capability,
          summarize_runtime_log, classify_content_error,
          resolve_external_runtime_binary, dispatch_external_runtime
          (firstresult=True) + register_query_routing (parallel-call).
      (e) Phase-1 addon-extensible-schema: AddonTableSpec, AddonEdgeTypeSpec
          (2 façades) + register_schema_tables, register_schema_edge_types
          (parallel-call).
      Joint v6 totals: 11 new façades + 12 new register_*/dispatch hookspecs
      across three contributing workstreams. ADDON_PROTOCOL_VERSION=6 stamp
      shipped in commit `38ab63bf` (port-out Stage B); W8c T1 declared
      signatures additively without a second bump.
    * `7 → 8` (2026-05-17, engine-RAG mega-plan E-NAMED-BANDS): Extends `CorpusBand`
      with five additive defaulted fields (`engine_version`, `chunk_filter`,
      `required_env`, `corpus_sha256`, `corpus_root`). Adds new façade dataclass
      `FailureCatalogRow` and new hookspec `project_rag_register_doctor_probe` for
      addon-side failure-catalog contribution. Also adds three new exception subclasses
      (`AddonCatalogIdCollision`, `AddonCatalogModeCollision`,
      `AddonCatalogInvalidVerdict`) all subclassing `AddonProtocolViolation`.
    * `8 → 9` (E-RUNTIME H1, 2026-05-17): Bump recorded here; wiki lag corrected
      by prior-art-checker Conflict 2 (2026-05-18). Verified at `core/addon_protocol.py:65`.
      Full changelog entry to be authored by the wave that introduced it — this entry
      closes the wiki-vs-substrate tracking gap. Plan reference:
      `docs/plans/2026-05-18-comprehensive-audit-remediation.md` §Prior-art Conflict 2
      disposition.
    * Phase 6 closure (2026-05-18, host+addon paired migration): no
      `ADDON_PROTOCOL_VERSION` bump — the schema-extension hookspec contract
      (`project_rag_register_schema_tables`, `project_rag_register_schema_edge_types`)
      shipped in v6 was already the migration contract. Phase 6 moved 8 `bp_*`
      tables + 10 indexes + 4 UE-shaped edge types from core into the UE addon's
      hookimpl. Core schema bumped to v12 (no `bp_*` DDL in `SCHEMA_DDL`).
      B-3 transition-window CLOSED (see §"Wave-2 scope notes" below). The
      `extractor_table_conflict` failure-mode row now reflects post-Phase-6
      semantics: addon-vs-core name collisions raise `AddonRegistrationError`
      at boot via the runtime guard at `project_rag_mcp/graph/db.py:887-920` — no
      transition-window carve-out.
    * `9 → 10` (comprehensive-audit-remediation 2026-05-18): Extends `CorpusBand`
      with two additive defaulted fields: `contributor: str = "unknown"` and
      `collection_name: str | None = None`. `collection_name` is dispatch-gating
      (routes `_open_chroma_for_band` collection lookup — Z-AMEND-1 OQ-2 bump rule
      applies); `contributor` is observability-only (inert, carried along atomically).
      **Generic-substrate contract:** an addon-owned chroma collection name is opaque
      to the host — the host looks it up via `band.collection_name`, never derives it
      from a naming convention. Addon authors (UE, Unity, future) must populate
      `collection_name` with the actual on-disk chroma collection name at band
      registration time. Derivation is the addon's responsibility; derivation logic
      must NOT leak into host code.

      **Z-AMEND-1 OQ-2 refined bump rule**: defaulted-additive fields that gate host
      dispatch behavior DO bump; inert carry-along (`corpus_sha256`) ships in the
      same bump for atomicity. New hookspecs (additive but dispatch-gating boot-time
      catalog assembly) DO bump. This resolves OQ-2 (the question of whether defaulted
      additions require a bump): when any new field or hookspec changes host behavior
      (routing, Chroma open, blend filter, verdict gate), it is dispatch-gating and
      bumps. Purely carry-along fields (INERT) ship in the same bump for atomicity but
      do not individually mandate the bump.

      **v8 backward compatibility:**
      - v7 addons with `applicable_kinds=None` (universal bands): continue to load
        and auto-include in any caller's default-blend. No migration required.
      - v7 addons with `applicable_kinds` set to a non-None value (engine-kinded):
        **must migrate to v8 and declare `engine_version`**. Without `engine_version`,
        boot fails-loud. This is intentional — letting an engine-kinded v7 band load
        as "universal-version" would reintroduce the confidently-wrong-answer class
        Z-5 was added to prevent.
      - Other absent fields: `chunk_filter` → whole-corpus query; `required_env` →
        no env-gating; `corpus_sha256` → `provenance.corpus_sha256 = None`;
        `corpus_root` → queries return `corpus_missing` (engine-kinded) or
        `not_found` (universal).
      - v6 and older are NOT supported in v8; minimum supported addon protocol is v7.
    * `10 → 11` (2026-05-18, chunker-author-discoverability-and-residuals):
      Type-widens `AddonChunkerSpec.target_substrate` and host
      `ChunkerEntry.target_substrate` to accept the `ALWAYS_PUBLISH` sentinel
      (`Literal['__always_publish__']`) in addition to `tuple[str, ...]`.
      Exports module-level `ALWAYS_PUBLISH` constant from
      `core.addon_protocol`. `Registry.substrate_matches()` short-circuits to
      `True` when the entry carries the sentinel. Adds host-side inventory
      tripwire at `tests/test_chunker_registry_substrate_inventory.py`
      asserting `entry.target_substrate not in ((),)` for every registered
      entry (host + addon-supplied).

      **Calibration note:** this bump's justification is "land coherent
      doctrine before the first known consumer (CTO, imminent, gated on
      functionality parity + publish) inherits it" — not "protect
      anonymous-community addons." There is no ecosystem at this bump.
      The doctrine below is written for the consumer scale we expect to
      operate at within the next year, not for hypothetical addon-author
      audiences.

      **Z-AMEND-1 refinement (canonical reading from this bump forward):**
      Z-AMEND-1's "defaulted-additive fields that gate host dispatch
      behavior DO bump" rule applies under three conditions, refined here:

      1. **Existing-field re-evaluation (the original Z-AMEND-1 case).**
         A change to how the host evaluates an existing dispatch field for
         existing addons (substrate matching semantics, scope filtering,
         routing key derivation) DOES bump. Pre-bump addons' observed
         behavior changes under the new host without their participation.

      2. **New opt-in dispatch path (the single_file_runner carve-out).**
         A new defaulted field that introduces an opt-in dispatch path
         unreachable without the new field DOES NOT bump on the dispatch
         axis alone. Pre-bump addons cannot set the field; the host falls
         through to the prior dispatch surface; observed behavior is
         identical. `single_file_runner` (shipped `1ec27543` without bump)
         is the canonical example. *New façade dataclasses and new
         hookspecs still bump on their own surface-shape rules,
         independently of this carve-out.*

         **Refinement (v12, 2026-05-18):** The carve-out applies only to
         *truly inert* defaulted additive fields — fields whose presence
         changes nothing about how existing hookimpls are invoked. When a
         new defaulted field gates NEW host wrap-behavior on opt-in (i.e.,
         the host checks the field and changes handler dispatch for
         flag-True registrations), the carve-out does NOT apply even
         though the field is defaulted and existing callers omit it. In
         that case, bump for coordination safety: the manifest-version gate
         then prevents pre-bump addons from loading against a post-bump
         host that would inject unexpected kwargs into their handlers.
         Contrast: `single_file_runner` (Z-AMEND-1 original) is truly
         inert — the field's presence never changes host invocation
         behavior regardless of value. `requires_project_graph_db` (v12)
         triggers host-side kwarg injection when `True`, qualifying for the
         bump despite the default-`False` value.

         **Canonical carve-out 2 instance — `CorpusBand.structural_index_resolver`
         (S-1a, 2026-05-19):** This field is the clearest application of the
         carve-out. `structural_index_resolver: Callable[[], Path] | None = None`
         introduces an opt-in dispatch path (H-2's structural-index resolution
         chain in `paths.py`) that is entirely unreachable unless an addon
         populates the callable. Three qualifying reasons why no bump is required:
         (i) Pre-bump addons leaving the field `None` observe identical host
         behavior — the resolution chain falls through to the next step in
         `paths.py` exactly as before, with no behavioral change for any existing
         addon or caller. (ii) The new dispatch branch is unreachable without
         addon participation — a pre-bump addon cannot accidentally trigger the
         new chain step because the field defaults to `None` and the branch gates
         on the field being callable. (iii) `resolution_trace` observability
         added in H-2 is provenance, not behavior — it records what the chain
         did and does not change what tools return to MCP callers. This field is
         therefore a callable-resolver pattern instance, not an opt-in-wrap
         instance (the `requires_project_graph_db` case); it qualifies under the
         original `single_file_runner` carve-out shape, refined by the inert-vs-
         wrap discrimination above. Forward-compat guard for addon hookimpls:
         `if "structural_index_resolver" in CorpusBand.__dataclass_fields__: ...`.
         Full field contract and opaque-resource semantics: `docs/wiki/corpus-band-protocol.md`.

      3. **CI-time / load-time registry-content invariants are
         dispatch-gating (clause added with the v10 → v11 bump).** A new
         test invariant that rejects registry contents (e.g., the
         `target_substrate` inventory tripwire shipped with this bump), or
         a load-time manifest gate that rejects out-of-range addons before
         any of their code executes (the `requires_protocol_version`
         closed-range gate in `addon-manifest.json`), IS dispatch-gating
         against pre-bump addons — the addon is rejected before the
         runtime dispatch path is reached, which is functionally identical
         to a runtime rejection. Such invariants DO bump.

      **Unifying principle: bump triggers are contract changes, not
      enforcement-mechanism choices.** Inventory tripwires (CI-time),
      manifest range gates (load-time), and runtime dispatch evaluators
      are three enforcement surfaces for the same contract; any one of
      them changing the set of conformant addons IS dispatch-gating and
      DOES bump.

      **Two complementary gates on this bump:**
      - **Load-time:** addons must declare `requires_protocol_version`
        containing 11. Closed range `[11, 11]` is the recommended posture
        — open ranges defeat the load-time gate. A pre-bump addon with
        `[10, 10]` hard-fails at host boot before its hookimpls register.
      - **CI-time:** the inventory tripwire fires on any entry whose
        `target_substrate` is the bare `()` default, demanding either a
        glob tuple or the `ALWAYS_PUBLISH` sentinel. An addon that
        declares compatible protocol range but ships bare-default specs
        is caught here.

      **Backward compatibility within the v10 → v11 transition:**
      Pre-v11 addons whose specs default `target_substrate=()` continue
      to import (type widening is additive). They will fail one or both
      gates above unless updated. There is no transition window — host
      and addon coordinate at the same release boundary as a normal
      paired migration (PM is the relay; cross-repo "ratification gate"
      ceremony is not used at this consumer scale).

    * `12 → 13` (2026-05-19, fusion-pipeline-n-lane): Reintroduces
      `default_weight: float | None = None` field on `CorpusBand` under a
      **different ownership model** than its v10 removal.

      **v10→v13 ownership-model shift:** At v10 (comprehensive-audit-remediation
      D3, 2026-05-18), `default_weight` and `authority_pairs` were removed with
      rationale "no live consumer was driving reranker behavior from them" — the
      three-lane hardcoded pipeline could not consume per-band values even if
      declared.  v13 reintroduces `default_weight` as a **suggestion-not-policy**
      field with the N-lane fusion pipeline as the first live consumer.  The
      framing is "v10 removed dead fields; v13 adds live fields that share an
      ancestor's name" — not "we changed our minds."

      **Ownership model:** addon declares a suggested weight; host may override via
      env (`PROJECT_RAG_BAND_WEIGHT_<band_name>`) or caller kwarg (`band_weights`).
      Addon-declared `default_weight` is third in the resolution chain (caller >
      env > addon-declared > absent).  The host treats `default_weight=None` as
      "no suggestion" — band participates in fusion without multiplicative
      distortion (absent-as-sentinel principle per `fusion-policy.md §N-lane weight
      semantics`).

      **Gate:** v13 publish was gated on N-lane fusion landing AND
      `tests/integration/test_blended_query_n_lane.py::test_default_weight_load_bearing`
      failing when the host ignores the field (the Director of Engineering F#2 consumer-proof requirement).

      **`authority_rank` / `authority_pairs`:** NOT reintroduced.  Deferred to v14,
      gated on a separate failing-test consumer proof (per the Director of Engineering F#2 convergence).
      v14 stub at `tasks/2026-05-19-fusion-pipeline-n-lane/v14-authority-rank-stub.md`.

      Plan reference: `docs/plans/2026-05-19-fusion-pipeline-n-lane.md`.
      Waves A–D (code changes) committed in `124eb3dd` (A), `2d21415c` (B),
      `3c5262d9` (C), `a273fefc` (D).

    * `11 → 12` (2026-05-18, addon-protocol-v12-and-ue-tool-migration):
      Adds `requires_project_graph_db: bool = False` to
      `AddonToolRegistration`. When an addon sets this flag `True`, the
      host wraps the handler at registration to inject `project_db_conn`
      as a kwarg per call; addon handlers must not cache the connection
      (host contract: fresh-per-call). Engine-corpus addon tools omit the
      flag; their behavior is unchanged.

      **Bump rationale — elective coordination-safety, not field-shape
      mandate.** This is a defaulted additive field and the Z-AMEND-1
      carve-out 2 would normally apply. However, the field gates new host
      wrap-behavior on opt-in (the Z-AMEND-1 refinement above: a field
      that triggers host-side kwarg injection when True does NOT qualify
      for the inert-field carve-out). The bump's payoff: a pre-v12 UE
      addon manifest declaring `requires_protocol_version: [11, 11]` is
      rejected at host boot before any hookimpl registers, rather than
      failing late with an `AttributeError` at registration. Early-fail
      signal buys cross-repo coordination safety; it is not a dataclass-
      shape dispatch change.

      **Bundle stays v11-shaped.** No fields added to `AddonMcpDepBundle`.
      Source/authority separation at the bundle layer survives intact.

      **Held-docstring replaced.** `AddonMcpDepBundle` docstring at
      `core/addon_protocol.py:706-707` replaced with the Director of Engineering-authored text
      separating two previously conflated concerns: (a) per-tool capability
      declaration — why project graph.db access is intentionally NOT
      bundle-level; (b) source/authority separation — governs corpus-class
      classifier, unaffected by this decision. Reference:
      `tasks/2026-05-18-v12-vs-option-c-tiebreaker/zoli-verdict.md`.

  Bump rule: **adding a defaulted additive field to a façade does NOT mandate
  a bump** (existing addons remain importable; the default propagates via the
  dataclass default_factory). **Required-field additions DO mandate a bump.**
  Also bumps on: field removal, field retype, hookspec signature change,
  `PreflightVerdict` enum extension, `ENVELOPE_VERSION` bump. See the
  one-line canonical statement at the end of §"Façade types" (and the
  §"Version-bump triggers" table below for bridge-protocol cases).
- **Entry-points group:** `project_rag.addons` — addons advertise their
  package via `[project.entry-points."project_rag.addons"]` in `pyproject.toml`.
- **Discovery:** `core/addon_discovery.py:discover_addons()` scans the entry
  points, validates `addon-manifest.json`, calls `addon.setup()` for the
  capability dict, and builds a `pluggy.PluginManager`.
- **Façade discipline:** addon authors see ONLY `Addon*`-prefixed types —
  never raw internal types. Enforced statically by
  `tests/addons/test_facade_discipline.py` (AST-walk tripwire, four attack
  shapes covered: `import-from`, `importlib.import_module`, `module-as-import`,
  `__all__` re-export).

## Manifest validation modes

<!-- Spec backlink: docs/plans/2026-05-17-addon-manifest-boot-gate-decoupling.md -->

As of 2026-05-17, `core/addon_manifest.py:validate_manifest()` is mode-aware.
Boot uses **lenient mode** (`mode='boot'`); `/project-rag:doctor` probe
`addon_manifest_drift` uses **strict mode** (`mode='strict'`).

### Five irreducible boot gates (fail-LOUD in both modes)

These gates fail-LOUD regardless of mode — without them the host cannot
identify or load the addon:

1. **File readable** — `OSError` on manifest read aborts discovery for that addon.
2. **JSON-parseable object** — malformed JSON or a non-dict top-level value
   is fatal.
3. **`name` present** — required for log lines and error attribution.
4. **`protocol_version` present** — required for the compatibility check below.
5. **Protocol-version compatible** — `protocol_version` must equal
   `ADDON_PROTOCOL_VERSION` (exact match, or within a declared accepts range).

### Drift — boot logs WARNING and proceeds; `/doctor` surfaces all drift

Everything else is **drift**: unknown fields, missing `version`, missing
`requires_schema_version`, optional-field type errors. In `mode='boot'` the
validator accumulates all drift into a `ManifestDriftReport` (a frozen
dataclass returned alongside the parsed dict), logs each at `WARNING` on the
`project_rag.addon_manifest` logger, and proceeds with boot. The
`manifest_version_mismatch` failure mode in § "Failure modes" is updated
to reflect this split.

In `mode='strict'` (used by the `/doctor` `addon_manifest_drift` probe), any
drift raises `AddonManifestError` as before. The probe runs strict validation
across all installed addons, cross-references declared `registered_producers` /
`registered_chunkers` / `registered_mcp_tools` against actual hookimpl returns,
and surfaces the full drift picture in one place — without blocking boot.
See [`docs/wiki/doctor-as-remediation-surface.md`](../../../../project-rag/docs/wiki/doctor-as-remediation-surface.md)
for the doctrine placing strict validation in `/doctor`, not the boot path.

### Rationale — type-confusion problem and motivating incident

The strict unknown-field gate was originally a deliberate "detect-then-fail-loud"
choice (ratified in the Staff Engineer's Wave 2a review). The 2026-05-17 motivating incident
exposed a type-confusion: a `_comment` field added to
`project-rag-ue-addon/project_rag_ue_addon/addon-manifest.json` (commit
`d690d0c1e`) for author bookkeeping — explicitly marked `"INFORMATIONAL — not
authoritative, not loaded at runtime"` by its own text — caused the host's strict
validator to raise `AddonProtocolMismatchError` and brick cold-boot, taking down
all L3 retrieval queries. The manifest's own `_comment` says the file is advisory;
the source comments at `core/addon_manifest.py:41-44` agree ("Advisory-only:
operational truth is pm.hook.project_rag_register_producer() results at boot").
Failing loud on self-declared advisory data is the type confusion. The five
irreducible gates are the genuinely ambiguous cases — they remain fail-LOUD
because the host cannot proceed without them. Everything above them (unknown
fields, optional-field drift) is validly informational. Authoritative spec:
`docs/plans/2026-05-17-addon-manifest-boot-gate-decoupling.md`.

### Note for addon authors

If you want strict validation in your addon's CI, import
`core.addon_manifest.validate_manifest` with `mode='strict'`. Boot-side
validation is intentionally lenient — your CI is the right gate for catching
typos and stale fields before publish.

### Return-type asymmetry (the Staff Engineer Finding 0)

`mode='strict'` returns `dict[str, Any]` (unchanged from the pre-2026-05-17
public API). `mode='boot'` returns `tuple[dict[str, Any], ManifestDriftReport]`.

The asymmetry is intentional: strict mode raises on any drift, so the caller
never receives a drift report on the success path (an empty report carries zero
information and would be misleading). Boot mode needs the report so the boot
path can log it; the caller always unpacks a 2-tuple. Writing
`manifest = validate_manifest(path, v, mode='boot')` silently binds the tuple
to `manifest` — use `manifest, drift = validate_manifest(path, v, mode='boot')`
in boot callers. Addon CI callers use `mode='strict'` and can write
`manifest = validate_manifest(path, v, mode='strict')` safely.

## Hookspecs (v7 surface — seventeen core + v7 addition)

Defined in `core/addon_hookspecs.py`. Each hookspec is a pluggy `@hookspec`
returning a list of façade instances. The host iterates the lists collected
across all registered addons.

| Hookspec | Returns | Semantics |
|---|---|---|
| `project_rag_register_mcp_tool` | `list[AddonToolRegistration]` | MCP tools the addon contributes; host iterates at boot (B-1, PR-6) |
| `project_rag_register_extractor` | `list[AddonExtractorSpec]` | Extractor specs registered into `priming/extractor_registry.py` (B-2, PR-2) |
| `project_rag_register_chunker` | `list[AddonChunkerSpec]` | Chunker specs registered into `indexer/chunker_registry.py` (B-5, PR-4) |
| `project_rag_register_provenance_classifier` | `list[AddonProvenanceClassifier]` | Classifiers added at the declared priority (B-6, PR-3) |
| `project_rag_register_editor_preflight` | `list[AddonPreflightCallback]` | Preflight callbacks fired before producers requiring a live editor (C-1, PR-7) |
| `project_rag_register_project_validity_check` | `list[AddonProjectValidityCallback]` | Project-validity callbacks (sentinel-style) (C-2, PR-7) |
| `project_rag_register_long_lived_subprocess` | `list[AddonLongLivedSubprocessSpec]` | Long-lived CPU/GPU subprocesses the addon contributes; host harness owns spawn/PID-lock/watchdog/tenant-registry (tc-2) |
| `project_rag_register_producer` | `list[AddonProducerSpec]` | Producer specs contributed by the addon; host adapter synthesizes sentinel runner string and appends to topo-sorted `Manifest.producers` before boot (W1, additive at v2 — wires pre-existing `AddonProducerSpec` façade) |
| `project_rag_refine_scope_ranges` | `list[ScopeRange] \| None` | Transformation hook: refine scope ranges for a file after per-language detection; return `None` to abstain (tc-6) |
| `project_rag_register_cpp_source_roots` | `AddonCppSourceRootsResult \| None` | C++ source root enumeration; host uses first non-None result; falls back to compile_commands.json walk when all addons abstain (v5, WS-1 Step 3) |
| `project_rag_register_provenance_classifier_rules` | `list[AddonClassifierRuleSpec]` | Provenance classifier rule-sets; inserted into core/provenance.py chain at declared priority (v5, WS-1 Step 3) |
| `project_rag_register_eval_bank` | `list[AddonBankSpec]` | Evaluation bank YAML files for dogfood discovery (v5, WS-1 Step 3) |
| `project_rag_register_eval_probe` | `list[AddonProbeSpec]` | Evaluation probe callables for programmatic bank generation (v5, WS-1 Step 3) |
| `project_rag_register_health_field` | `list[AddonHealthFieldSpec]` | Addon-contributed health subfields; land in ``addon_fields`` envelope sub-block (v5, WS-1 Step 3) |
| `project_rag_register_schema_tables` | `list[AddonTableSpec]` | Addon-contributed table DDL; host executes each spec's `ddl` + `indexes` after core DDL on every `init_graph_db` open. `schema_extension_version` in the capability dict is load-bearing: host upserts it into `addon_schema_versions` for observability. DDL must use `CREATE TABLE IF NOT EXISTS`; indexes must use `CREATE INDEX IF NOT EXISTS`. Parse-tested against `:memory:` at registration; malformed DDL raises `AddonRegistrationError` at boot (v6, Phase-1 addon-extensible-schema, 2026-05-16) |
| `project_rag_register_schema_edge_types` | `list[AddonEdgeTypeSpec]` | Addon-contributed edge type names; host builds `EdgeTypeRegistry` from `CORE_EDGE_TYPES` + all hookimpl returns at `init_graph_db` time. Registry is constructed fresh per `init_graph_db` invocation — no module-global state. Extractor INSERT sites validate against the registry; unknown edge types raise `UnknownEdgeTypeError` (v6, Phase-1 addon-extensible-schema, 2026-05-16) |
| `project_rag_register_chunk_metadata_extras` | `list[AddonChunkMetadataExtrasSpec]` | Per-source-type Layer-1 chunk field extras the addon contributes. Host unions all registered specs per `source_type` at validation time; canonical-eight and `_UNIVERSAL_EXTRAS` are host-owned and not extensible through this hookspec. Parallel-call (no `firstresult`). Graceful-fail: return `[]` when no extras applicable. Collision with canonical-eight or `_UNIVERSAL_EXTRAS` raises `AddonRegistrationError` at registration time. See [`chunk-metadata-schema-seam.md`](chunk-metadata-schema-seam.md) (v7, γ-prime, 2026-05-16) |

Hookspec naming uses a single `project_rag_` namespace. There is no per-hook
versioning — `ADDON_PROTOCOL_VERSION` is the single version constant.

### `project_rag_register_long_lived_subprocess`

The 7th register hookspec, added in tc-2 (protocol bump v1 → v2). Authority:
`docs/plans/2026-05-13-tc-2-long-lived-subprocess-hookspec.md §WS-1` and the tc-1
audit memo at `docs/strategy/2026-05-13-c-core-host-runtime-audit.md §5 R-1`.

An addon returns one or more `AddonLongLivedSubprocessSpec` instances describing a
daemon-style subprocess (a GPU sidecar, an LSP server, a background extractor) that
the project-rag host harness should own for the full server lifetime. The **host**
(`core.long_lived_runtime._boot_subprocess`) handles:

- `bounded_popen` wrapping of the spawn with memory-ceiling enforcement
- Single-instance PID lock under `<data_dir>/<spec.id>.pid` (`O_EXCL`)
- asyncio idle-offload and process-exit watchdog (thresholds from the spec)
- Doctor probe registration via `spec.doctor_probe_step_id`
- Tenant-registry write under `~/.claude/process-tenants/` (or
  `~/.claude/gpu-tenants/` per `spec.tenant_kind`)

The **addon** supplies: an `argv_builder` callable, `env_extras`, per-batch and
per-request memory ceilings, idle/exit timeout thresholds, a health URL, and the
doctor probe step id. Field-level documentation lives in `core/addon_protocol.py`.

The embed sidecar dogfoods this seam: `BUILTIN_EMBED_SIDECAR_SPEC` in
`embed_sidecar/builtin_spec.py` is registered by the host directly (no addon
required for built-in subprocesses). See `docs/wiki/embed-sidecar.md §Built-in spec`.

### `project_rag_register_producer`

The 9th hookspec, added in W1 (2026-05-14). Additive at `ADDON_PROTOCOL_VERSION=2`
(no bump — pre-existing `AddonProducerSpec` façade was declared at v1). The
constant has since been bumped to v3 by tc-4 for unrelated façade additions
(`AddonDiagnostic` + `AddonReconciledDiagnostic`), and to v4 by tc-5
(2026-05-15) for the `AddonDiagnostic.anchor_line` AC-8 dedup key — `canonical_id`
derivation in `project_rag_mcp/tools/reconciler.py` now keys on `anchor_line` when set, falls
back to `line_range` when None. See [`f-l4-reconciliation-policy.md`](../../../../project-rag/docs/wiki/f-l4-reconciliation-policy.md) §2.
— no version bump because `AddonProducerSpec` (the façade it wires) was already
declared at v1 (PR-1). Authority: tc-6 precedent (`refine_scope_ranges`, additive
hookspec with pre-existing façade, no bump).

An addon returns one or more `AddonProducerSpec` instances. The **host**
(`project_rag_mcp/project_rag_server.py` boot — mirroring the tc-2 long-lived-subprocess
block) handles:

- Fail-soft iteration (BLE001 shape): hookimpl exception skips that producer; boot continues.
- Per-spec call to `priming.manifest._adapt_addon_producer_spec()`, which:
  - Stashes the bound `Callable` in `_ADDON_PRODUCER_CALLABLES[spec.id]`
  - Returns a `ProducerEntry` with `runner="addon_callable:<id>"` (sentinel)
  - Raises `ProducerIDConflictError` on duplicate id (loud-and-early per the Staff Engineer P1-7)
- Appends the returned `ProducerEntry` to `_PENDING_ADDON_PRODUCERS`.
- `load_manifest()` merges `_PENDING_ADDON_PRODUCERS` into `Manifest.producers` before
  topo-sort; YAML-declared producers win on id conflict.

`priming/producer_runner.py:_run_one` routes `runner.startswith("addon_callable:")` to
the stashed callable. **D3 constraint (PM 2026-05-14):** addon-callable producers with
`requires_editor=True` raise `NotImplementedError` at `_run_one` — Mode-B subprocess
callable survival is deferred to Wave-2b-proper.

Cross-link: `AddonProducerSpec` façade row in the table above. `output_dir` is the
4th `ProducerEntry` output-axis (D1, W1): a producer that writes into a directory
rather than a fixed file declares `output_dir: str | None` in its spec. At most one
of (`output`, `output_glob`, `output_path_from`, `output_dir`) may be set per entry;
multi-axis collision raises `ManifestValidationError`.

### `project_rag_register_cpp_source_roots` (v5, WS-1 Step 3)

Returns `AddonCppSourceRootsResult | None`. The host calls this hookspec before the
C++ structural producer begins its source-root walk. Return `None` to abstain (graceful
fallback to `compile_commands.json`-driven walk). The host uses the **first non-None
result** across all registered addons.

```python
@hookspec(firstresult=True)
def project_rag_register_cpp_source_roots(
    project_root: Path,
) -> "AddonCppSourceRootsResult | None": ...
```

`AddonCppSourceRootsResult` fields (defined in `core/addon_dataclasses.py`):
- `roots: list[Path]` — explicit source root directories to walk
- `extra_compile_commands_json: Path | None` — optional supplementary `compile_commands.json`

This hookspec satisfies `thin-wrapper-graceful-fail.md` Rule 1 (probe lazily at first call, not
at boot) and Rule 3 (return `None` gracefully when no addon registered). The UE addon uses it
to supply `Source/**` and `Plugins/Source/**` root layout; non-UE C++ projects fall back to
`compile_commands.json` directly.

### `project_rag_register_provenance_classifier_rules` (v5, WS-1 Step 3)

Returns `list[AddonClassifierRuleSpec]`. Each spec inserts a rule-set into the
`core/provenance.py` classifier chain at its declared priority (UE addon band: 100–199).

```python
@hookspec
def project_rag_register_provenance_classifier_rules(
    project_root: Path,
) -> "list[AddonClassifierRuleSpec]": ...
```

`AddonClassifierRuleSpec` fields (defined in `core/addon_dataclasses.py`):
- `priority: int` — insertion priority (see §"Reserved provenance priority bands")
- `classifier: Callable[[Path, Path, Path | None], AddonProvenance | None]` — returns `None`
  to abstain; returns an `AddonProvenance` to claim the path

### `project_rag_register_eval_bank` (v5, WS-1 Step 3)

Returns `list[AddonBankSpec]`. Each spec declares a YAML evaluation bank file the dogfood
runner should discover.

```python
@hookspec
def project_rag_register_eval_bank() -> "list[AddonBankSpec]": ...
```

`AddonBankSpec` fields (defined in `core/addon_dataclasses.py`):
- `bank_path: Path` — absolute path to the bank YAML file
- `bank_type: str` — `"smoke"` or `"graded_relevance"` (mirrors bank-v2-schema.md)

The UE addon uses this to register `eval/bank_ue.yaml` (formerly `bank_legacy_ue.yaml` in
the host repo, moved in D6).

### `project_rag_register_eval_probe` (v5, WS-1 Step 3)

Returns `list[AddonProbeSpec]`. Each spec declares a callable that programmatically generates
bank entries against the current corpus index.

```python
@hookspec
def project_rag_register_eval_probe() -> "list[AddonProbeSpec]": ...
```

`AddonProbeSpec` fields (defined in `core/addon_dataclasses.py`):
- `probe_id: str` — unique identifier for this probe
- `probe_fn: Callable[[], list[dict]]` — called by the dogfood runner; returns a list of
  bank entry dicts in bank-v2-schema format
- `corpus_under_test: str` — symbolic name matching the `corpus_under_test` field in the bank schema

### `project_rag_register_health_field` (v5, WS-1 Step 3)

Returns `list[AddonHealthFieldSpec]`. Each spec contributes a named subfield to the `addon_fields`
block of the health envelope. **Landing site:** `addon_fields` sub-block, NOT inside
`_collect_project_block` (which is `.uproject`-gated and would break host-only lossless contract).

```python
@hookspec
def project_rag_register_health_field() -> "list[AddonHealthFieldSpec]": ...
```

`AddonHealthFieldSpec` fields (defined in `core/addon_dataclasses.py`):
- `field_name: str` — key under `addon_fields` in the health envelope
- `value_provider: Callable[[HealthContext], Any]` — called lazily at health probe time

`HealthContext` is a lightweight dataclass (defined in `core/addon_dataclasses.py`):
- `project_root: Path` — project root resolved at first health call

The UE addon uses this to contribute `ue_plugin_enabled`, replacing the deprecated
`holodeck_plugin_enabled` core field (which emits `DeprecationWarning` on read since D4).

## v6 hookspecs — host-addon-capability-dispatch + Phase-1 schema extension

<!-- Spec backlink: docs/plans/2026-05-16-w8c-v6-ratification-content-error-migration.md §T10 (AC-10, AC-11) -->
<!-- Spec backlink: docs/plans/2026-05-16-w8c-v6-ratification-content-error-migration.md §T1 -->

All eight v6 hookspecs land under `ADDON_PROTOCOL_VERSION=6` (commit `38ab63bf` for the
bump; W8c T1 declared signatures in commit `6e4dee00` without a second bump — bump-once
economics across concurrent workstreams). Full hookspec signatures are in
`core/addon_hookspecs.py`. Full capability-dispatch doctrine is in
[capability-dispatch.md](capability-dispatch.md).

### `AddonProducerSpec` polarity flip (v6, W8c)

`requires_editor: bool` and `domain: list[str]` are **retired** in v6. Producers now
declare named capability strings via `requires_capabilities: tuple[str, ...]`. The host
gate at `priming/producer_runner.py` resolves each capability through
`project_rag_provide_capability` (pluggy `firstresult=True`) at preflight time.

No transition alias — PM 2026-05-16 OQ-2 disposition: **stop, not warn**. Old manifests
declaring `requires_editor:` or `domain:` raise `ManifestSchemaError` with the migration
path documented in [capability-dispatch.md](capability-dispatch.md) §Migration.

### Six capability-dispatch hookspecs (W8c)

| Hookspec | Pluggy semantics | Returns | Notes |
|---|---|---|---|
| `project_rag_provide_capability` | `firstresult=True` | `AddonCapabilityResult \| None` | Capability satisfaction query. Abstain (return `None`) for unrecognised capability strings. `satisfied=False` when recognised but not currently satisfiable. See abstain-vs-unsatisfied contract in [capability-dispatch.md](capability-dispatch.md). |
| `project_rag_classify_content_error` | `firstresult=True` | `AddonContentErrorClassification \| None` | Replaces `priming.bp_corruption.is_bp_content_error`. Return `None` when error is not recognised by this addon at all. Return non-None only when claiming the error AS a content/non-content classification. |
| `project_rag_summarize_runtime_log` | `firstresult=True` | `AddonRuntimeLogSummary \| None` | Replaces `ue_log_parser.parse_ue_log` + `compose_remediation`. Invoked after `dispatch_external_runtime`. Return `None` to abstain. |
| `project_rag_resolve_external_runtime_binary` | `firstresult=True` | `Path \| None` | Returns absolute path to the binary for `capability` (e.g. `UnrealEditor-Cmd.exe` for `'ue_editor'`). Return `None` to abstain. Sister hookimpl: W8d. |
| `project_rag_dispatch_external_runtime` | `firstresult=True` | `AddonRuntimeDispatchResult \| None` | Invokes the resolved binary with addon-specified argv/env/timeout. The host owns subprocess lifecycle via `core.long_lived_subprocess`. Return `None` to abstain. Sister hookimpl: W8d. |
| `project_rag_register_query_routing` | parallel-call | `list[AddonQueryRoutingSpec]` | Registers domain-specific query patterns + optional decomposer references. Replaces W6/Wave-2b P3.6 port-out. Sister hookimpl: W8f. |

**Sister hookimpl status:**
- `provide_capability`, `classify_content_error`, `summarize_runtime_log` — sister hookimpls
  land in W8c (see `project-rag-ue-addon` T12).
- `resolve_external_runtime_binary`, `dispatch_external_runtime` — sister hookimpls deferred
  to W8d.
- `register_query_routing` — sister hookimpl deferred to W8f.

### Two schema-extension hookspecs (Phase-1 addon-extensible-schema)

| Hookspec | Pluggy semantics | Returns | Notes |
|---|---|---|---|
| `project_rag_register_schema_tables` | parallel-call | `list[AddonTableSpec]` | Addon-contributed table DDL. Host executes after core DDL on every `init_graph_db` open. DDL parse-tested against `:memory:` at registration; malformed DDL raises `AddonRegistrationError`. |
| `project_rag_register_schema_edge_types` | parallel-call | `list[AddonEdgeTypeSpec]` | Addon-contributed edge type names. Host builds `EdgeTypeRegistry` at `init_graph_db` time. Unknown edge types in extractor INSERTs raise `UnknownEdgeTypeError`. |

The `schema_extension_version` capability-dict field is load-bearing at v6: the host upserts
it into `addon_schema_versions` for observability when either schema hookspec is implemented.

### Doctor probe: `capability-satisfaction`

The v6 capability-dispatch surface is observable via the `capability-satisfaction` probe
phase in `/project-rag:doctor`. The probe enumerates the union of `requires_capabilities`
across all registered producers, calls `project_rag_provide_capability` for each, and
surfaces a structured table: `capability | claimed_by | satisfied | reason`. See
[capability-dispatch.md](capability-dispatch.md) §Doctor probe.

## Façade types

All public façades carry the `Addon` prefix and are declared in
`core/addon_protocol.py`. Stability contract: any field add/remove/retype
requires an `ADDON_PROTOCOL_VERSION` bump.

| Façade type | Wraps | Key fields |
|---|---|---|
| `AddonChunkerSpec` | `indexer.chunker_registry.ChunkerEntry` | `id: str`, `runner: Callable`, `domain: list[str]`, `scope: str`, `requires: list[str]`, `categories: list[str]` (defaulted-additive, see [addon-chunker-categories.md](addon-chunker-categories.md)) |
| `AddonProducerSpec` | `priming.manifest.ProducerEntry` | `id: str`, `runner: Callable`, `requires_capabilities: tuple[str, ...]`, `depends_on: list[str]`, `timeout_seconds: int`, `required_python_classes: list[dict]`, `output_dir: str | None` (v6: `requires_editor: bool` and `domain: list[str]` retired — see [capability-dispatch.md](capability-dispatch.md)) |
| `AddonExtractorSpec` | `priming.extractor_registry.ExtractorEntry` | `id: str`, `runner: Callable`, `domain: list[str]`, `requires: list[str]`, `writes_tables: list[str]` (string list — the host translates to `TableTarget` at registration) |
| `AddonProvenanceClassifier` | `core.provenance._ClassifierFn` | `priority: int`, `classify: Callable[[Path, Path, Path \| None], AddonProvenance \| None]` |
| `AddonToolRegistration` | MCP tool registration | `name: str`, `description: str`, `handler: Callable` |
| `AddonPreflightCallback` | `Callable[[PreflightContext], PreflightResult]` | (callable type alias) |
| `AddonProjectValidityCallback` | `Callable[[PreflightContext], PreflightResult]` | (callable type alias) |
| `AddonProvenance` | re-export of `core.provenance.Provenance` | Stable re-export under `Addon`-prefixed alias |
| `AddonLongLivedSubprocessSpec` | `core.long_lived_subprocess.SubprocessSpec` | Lifecycle spec for an addon-managed CPU/GPU subprocess. Key fields: `id: str`, `argv_builder: Callable`, `env_extras: dict`, `health_url: str`, `idle_timeout_s: int`, `exit_timeout_s: int`, `tenant_kind: str`, `doctor_probe_step_id: str`. Added in tc-2 (v2 bump). Full field docs: `core/addon_protocol.py`. |
| `AddonCapabilityResult` | (v6, W8c) | `satisfied: bool`, `reason: str | None`. Returned by `project_rag_provide_capability` hookimpls when the capability string is recognised. Return `None` (abstain) to pass through to the next addon. See [capability-dispatch.md](capability-dispatch.md). |
| `AddonContentErrorClassification` | (v6, W8c) | `is_content_error: bool`, `error_class: str`, `file_path: Path | None`, `hint: str | None`. Returned by `project_rag_classify_content_error` hookimpls. Replaces direct `is_bp_content_error` calls. |
| `AddonRuntimeLogSummary` | (v6, W8c) | `verdict: str`, `summary: str`, `remediation_hint: str | None`, `structured_findings: tuple[dict, ...]`. Returned by `project_rag_summarize_runtime_log` hookimpls. Replaces `parse_ue_log` + `compose_remediation` calls. |
| `AddonRuntimeBinaryResolution` | (v6, W8c) | `binary_path: Path`, `found: bool`, `reason: str | None`. Structured failure context for `project_rag_resolve_external_runtime_binary` callers needing more than `Path | None`. Consumer: W8d. |
| `AddonRuntimeDispatchResult` | (v6, W8c) | `returncode: int`, `stdout_excerpt: str`, `stderr_excerpt: str`, `log_summary: AddonRuntimeLogSummary | None`. Returned by `project_rag_dispatch_external_runtime` hookimpls. Consumer: W8d. |
| `AddonQueryRoutingSpec` | (v6, W8c) | `domain_patterns: tuple[str, ...]`, `decomposer_callable_name: str | None`. Returned by `project_rag_register_query_routing` hookimpls. Replaces W6/Wave-2b P3.6 ue_patterns + query_decomposition port-out. Consumer: W8f. |
| `AddonTableSpec` | (v6, Phase-1 addon-extensible-schema) | `name: str`, `ddl: str`, `indexes: list[str]`. Returned by `project_rag_register_schema_tables`. DDL parse-tested against `:memory:` at registration. |
| `AddonEdgeTypeSpec` | (v6, Phase-1 addon-extensible-schema) | `edge_types: frozenset[str]`. Returned by `project_rag_register_schema_edge_types`. Host builds `EdgeTypeRegistry` from `CORE_EDGE_TYPES` + all hookimpl returns. |
| `AddonChunkMetadataExtrasSpec` | (v7, γ-prime, 2026-05-16) | `source_type: str`, `extras: frozenset[str]`, `contributor: str`. Returned by `project_rag_register_chunk_metadata_extras`. Host unions extras per `source_type` across all registered specs; validation algorithm stays in `core/chunk_schema.py`. Bump trigger for v6→v7 per the new-façade rule (the Staff Engineer anti-pattern D). |

The `envelope` module is also re-exported (`from core.addon_protocol import envelope`)
so addon tool handlers can return envelope-shaped dicts via `envelope.ok(...)`,
`envelope.not_found(...)`, etc. An `ENVELOPE_VERSION` bump triggers an
`ADDON_PROTOCOL_VERSION` bump (the re-export pin is part of the public surface).

## PreflightResult and PreflightVerdict

`PreflightVerdict` is `class PreflightVerdict(str, Enum)` with exactly 5 members
(NOT `typing.Literal` — the harness uses `.ok` member access which requires
a proper Enum class):

- `PreflightVerdict.ok` — editor available and project confirmed.
- `PreflightVerdict.editor_contention` — editor open but holodeck-control
  not registered.
- `PreflightVerdict.editor_required_unavailable` — Mode A required but no
  live editor / holodeck-control found.
- `PreflightVerdict.transient_failure` — recoverable; retry after
  `retry_after_seconds`.
- `PreflightVerdict.permanent_failure` — non-recoverable; `hint` carries
  remediation. `wrong_project` and `sentinel_fail` both collapse here with
  diagnostic text in `hint`.

**Closed-set invariant:** adding a verdict requires an `ADDON_PROTOCOL_VERSION`
bump.

`PreflightResult` is a frozen dataclass with three fields:

- `verdict: PreflightVerdict` — the closed-enum branch axis.
- `hint: str | None` — remediation text or disambiguator.
- `retry_after_seconds: int | None` — INFORMATIONAL ONLY. Receivers MAY apply
  backoff via `time.sleep(result.retry_after_seconds or 0)` but MUST NOT
  branch logic on the numeric magnitude (e.g. `if rs > 60: ...`). The closed
  enum `verdict` is the only branch axis. `tests/structural/test_retry_after_seconds_no_branch.py`
  enforces this — Compare/BoolOp use of `retry_after_seconds` (excluding
  `is None` / `is not None`) fails the build (PR-7 AC-9a).

`PreflightContext` is a frozen dataclass with four v1 fields:

- `project_root: Path` — façade-authoritative name (PR-1 declaration). Internal
  UE assertion code may locally name the parameter `expected_root`; the façade
  field wins.
- `sentinel_asset_paths: list[str]` — `/Game/...` paths to verify via the
  bridge.
- `python_runner: Callable[[str], dict] | None` — bridge closure.
- `mode_a_required: bool` — when True, "live editor + no Mode A + Mode B
  not wired" resolves to `editor_required_unavailable`; when False, the same
  path resolves to `ok` (graceful degradation for non-`requires_editor`
  producers).

Adding a field with a default IS NOT a version bump (additive, backward-compatible);
removing or retyping a field IS a bump.

## Reserved provenance priority bands

Source: plan §B-6, PR-3. Classifiers registered via `@_register(priority=N)`
are sorted ascending. Lower values fire first (higher priority).

| Band | Range | Owner | Examples |
|---|---|---|---|
| Core | 0–99 | project-rag internals | `_uplugin_classifier=10`, `_engine_classifier=20`, `_project_fallback_classifier=80`, `_generic_classifier=90` |
| UE addon | 100–199 | `claude-unreal-holodeck` UE addon | Any UE-specific classifier that should fire after core but before generic |
| Future addons | 200–299 | Reserved for addon #2+ | — |
| Reserved | 300+ | Reserved | — |

**Collision policy:** within-band priority collisions emit `logger.warning`
at startup (chain-build time). Hard enforcement deferred to v2. Within a band,
insertion order is the stable secondary key — classifiers with the same
priority run in the order they were registered.

**Default priority:** omitting `priority` emits `DeprecationWarning` and
defaults to `100` (UE addon band start). Migrate to explicit values before v2.

## bridge_protocol_version

Named protocol: **`holodeck_python_bridge_v1`**. Field: `bridge.protocol_version = 1`
set at closure-creation site in `project_rag_mcp/preflight.py:make_holodeck_python_runner()`
(PR-8). Doctor probe `Step 16: Bridge protocol check` asserts version match.

### Closure shape

```python
Callable[[str], dict]
```

- Input: `code: str` — a Python expression to execute in the UE editor.
- Output: `dict` with keys `output: str` (stdout from the editor) and
  `success: bool`.

### Obtaining a tagged closure

Use `mcp.preflight.make_holodeck_python_runner()`. The returned closure carries:
- `bridge_protocol_version: int = 1`
- `bridge_name: str = "holodeck_python_bridge_v1"`

### Version semantics

`protocol_version` bumps to 2 only on **protocol shape changes**:

- Closure signature change (`str → dict` is v1; any other signature is v2+).
- Return contract change (key names, types, or error semantics change).
- Error-contract change (`RuntimeError` wrapping vs bare raise).

Adding metadata fields to the closure is **NOT** a bump. Changing the bridge
name within v1 is **NOT** a bump.

### Version-bump triggers

| Change | Bump? |
|---|---|
| Signature: input is no longer `str` | YES → v2 |
| Signature: return is no longer `dict` | YES → v2 |
| `output` key renamed | YES → v2 |
| `success` key removed or renamed | YES → v2 |
| Error contract changes (e.g. raises different exception class) | YES → v2 |
| New metadata attribute added to closure | NO |
| `bridge_name` value changes | NO |

### v1 is synchronous-only (the Game Dev Reviewer SX-1)

The closure executes Python in the Editor's main-thread Python VM and blocks
until the expression returns. The closure does **not** support: callback-based
completion, multi-tick yielding, awaiting Editor subsystems that complete on
later ticks (e.g. `AssetRegistry` background scan completion). Addon callers
that need to observe an async-completing UE subsystem must implement their
own poll-loop on the addon side, returning `PreflightVerdict.transient_failure`
with a `retry_after_seconds` hint when the subsystem is not yet ready.

v2 of the bridge protocol is reserved for introducing async semantics; until
then, addon authors should treat the closure as a single-tick blocking probe.
See PR-7's `transient_failure` verdict as the v1 escape hatch for
async-not-ready conditions.

### Liveness vs version-match (the Game Dev Reviewer S8-1)

**`bridge_state.json` records the bridge state at MCP server boot. It does
not track per-call liveness.** A doctor `PASS` on the bridge-protocol probe
means "the registered bridge declares v1 protocol"; it does **not** mean
"the bridge is currently responsive."

Common confusion case: if the UE Editor crashes while the MCP server stays
up (the Editor OOMs more frequently than the MCP server shuts down),
`bridge_state.json` will remain fresh (`captured_at` updated at boot, not
per call) while the bridge itself is dead. The doctor probe will report
`PASS` (version match, not stale) even though every bridge call will fail.
Use Mode-A preflight to test current bridge responsiveness; the
`bridge_protocol_check` probe verifies **version contract only**, not live
reachability.

### Doctor verdict matrix

| Condition | Verdict |
|---|---|
| Registered runner with `bridge_protocol_version == 1` AND `captured_at < 600s` | PASS |
| Registered runner with `bridge_protocol_version == 1` AND `captured_at > 600s` | INFO (staleness hint) |
| Registered runner with `bridge_protocol_version != 1` | FAIL (`bridge_version_mismatch`) |
| No registered runner | INFO (no bridge active) |

The `INFO` verdict is new in PR-8 — it extends the project-rag doctor verdict
palette from `{PASS, WARN, FAIL, BROKEN, DEGRADED}` to add `INFO`. The
holodeck doctor renderer must add the `INFO` case correspondingly (cross-repo
coordination per P8-2; SHAKEDOWN.md verifies).

## Manifest schema

Filename: `addon-manifest.json` in the addon package root. Validated by
`core/addon_manifest.py` (PR-5).

**Required keys:**

- `addon_name: str`
- `addon_version: str`
- `protocol_version: int` — must equal `ADDON_PROTOCOL_VERSION`
- `domain_tags: list[str]` — file markers (e.g. `["*.uproject"]`)
- `declared_producers: list[str]`
- `declared_mcp_tools: list[str]`
- `declared_schema_tables: list[str]`

**Optional keys:**

- `requires_schema_version: int`
- `schema_extension_version: int`
- `concurrency_safe: bool` (default `false`)
- `bridge_protocol_version: int`

Pattern 4 (Sphinx-style): `addon.setup()` returns a capability dict with the
runtime-introspectable subset of these fields; the receiver calls `setup()`
during discovery and validates the capability dict against the manifest.

### Cross-repo parity guard lives addon-side

The drift guard between host `ADDON_PROTOCOL_VERSION` and an addon's manifest
is enforced **in the addon's test suite**, not here. `project-rag-ue-addon`
ships an AC-6 parity test that asserts the host's live
`core/addon_protocol.py:ADDON_PROTOCOL_VERSION` is satisfied by the addon
manifest's accepted-protocol list. (The original AC-6 implementation was
tautological — double-imported the constant from the same module — and was
fixed addon-side on 2026-05-15 to read host + manifest from independent
sources.)

**Implication for host-side bumps:** bumping `ADDON_PROTOCOL_VERSION` in
`core/addon_protocol.py` requires a coordinated PR against each installed
addon to extend its manifest's accepted-protocol list. There is intentionally
no symmetric host-side test — the host does not know which addons exist; the
addons know which host they require. Don't add one.

**Implication for prior-art checks:** any plan that proposes a host-side
parity test, version-skew shim, or "host enumerates known addons" surface is
inverting the polarity codified here. Cite this section before re-deriving.

## Capability dict shape

Returned by `addon.setup()` (Pattern 4). **Canonical schema is defined in
PR-5 at `core/addon_discovery.py:_build_host_capability` — this section
cross-references, not redefines.**

```python
{
    # Runtime-introspectable invariants (canonical site: core/addon_discovery.py):
    "name": str,                          # human-readable addon name
    "version": str,                       # semver string
    "schema_extension_version": int,      # 0 if no schema extension; LOAD-BEARING at v6:
                                          # host upserts this into addon_schema_versions table
                                          # for observability when project_rag_register_schema_tables
                                          # or project_rag_register_schema_edge_types are implemented.
    "requires_schema_version": int,       # minimum graph.db SCHEMA_VERSION
    "concurrency_safe": bool,
    "bridge_protocol_version": int | None,  # int (e.g. 1) for holodeck_python_bridge_v1, None if no bridge
    # NOTE: registered_producers, registered_mcp_tools, domain_tags belong in addon-manifest.json
    # — they are declarative manifest fields, not runtime invariants. NOT in the capability dict.
}
```

### Addon `setup()` contract — pure capability declaration only (the Game Dev Reviewer S5-1)

`addon.setup()` is called during MCP server boot on the hot-path in
`core/addon_discovery.py:discover_addons()`, interleaved with all other boot
work. Addon authors must ensure `setup()` completes without:

- Invoking the `python_runner` bridge or any `mcp__holodeck-control__*` call.
- Executing any UE-Editor Python code.
- Performing filesystem mutation (writes, deletes, renames outside the addon
  package itself).

Bridge invocations are deferred to the registered preflight callbacks, fired
lazily by the receiver when a producer with `requires_editor: True` fires
(PR-7 hook path). Discovery is hot-path during MCP boot; bridge calls during
discovery contend with whatever the Editor is currently doing (BP compile,
asset cook, another MCP client), causing non-deterministic failures that
are difficult to diagnose.

**Permitted in `setup()`:** reading the addon's own metadata (version,
declared tables, etc.); importing addon-internal modules; returning the
capability dict. Everything else must be deferred to a hookimpl.

## Failure modes

| Failure | Cause | Receiver behavior |
|---|---|---|
| `manifest_version_mismatch` | `protocol_version` in manifest ≠ `ADDON_PROTOCOL_VERSION` | **Five irreducible gates** (file-readable, JSON-object, `name`, `protocol_version`, protocol-version-compatible) — refuse to load. **All other manifest issues** (unknown fields, missing `version`, missing `requires_schema_version`, optional-field type errors) — log `WARNING` and proceed; surfaced via `/doctor` `addon_manifest_drift` probe. See §"Manifest validation modes". |
| `addon_setup_exception` | `addon.setup()` raised | Skip addon; startup warning; probe surfaces |
| `bridge_version_mismatch` | `bridge.protocol_version` ≠ expected | Doctor probe verdict; remediation hint |
| `extractor_table_conflict` | `writes_tables` (or `AddonTableSpec.name`) lists a table already registered by another addon, OR shadows a core-owned table — runtime guard at `project_rag_mcp/graph/db.py:887-920` raises `AddonRegistrationError` at boot. Post-Phase-6 (2026-05-18) the transition-window carve-out for core-table collisions is closed; addon-vs-core and addon-vs-addon collisions both fail-loud. |
| `priority_band_collision` | Two classifiers share same priority in a band | Startup `logger.warning`; deterministic tie-break by registration order |

*(Updated 2026-05-16) addon-vs-core collision handling split from
addon-vs-addon; transition-window carve-out documented per §(d)
of plan `2026-05-16-phase-1-addon-extensible-schema.md`.*

## Graceful-fail contract

project-rag must boot and serve queries with zero addons installed. When addon discovery finds no
registered entry-points, or when an addon's `setup()` raises, the host degrades gracefully: boot
completes, UE-shaped tools return `extraction_skipped` (never a stack trace), and a `DEGRADED`
doctor probe verdict is registered with an actionable install hint. Full doctrine — including the
three implementation rules (probe at the seam, loud warnings, degrade not fail) and the canonical
probe-site table — lives in [`docs/wiki/thin-wrapper-graceful-fail.md`](../../../../project-rag/docs/wiki/thin-wrapper-graceful-fail.md).

## Facade discipline — tripwire allowlist exceptions

The AST tripwire at `tests/addons/test_facade_discipline.py` greps addon source for non-`Addon`-prefixed type imports. Two resolution exceptions exist and are documented in the tripwire allowlist:

| Exception | Resolution | Rationale |
|---|---|---|
| `core.provenance.Provenance as AddonProvenance` | Resolution 3 — allowlisted alias import | `AddonProvenance` IS the `Provenance` re-export; the alias pattern is the canonical façade shape; the tripwire must recognise the `as` form as stable |
| `mcp.tools.envelope as envelope` | Resolution 4 — allowlisted module import | Addon tool handlers that return envelope-shaped dicts need the module; `ENVELOPE_VERSION` bumps trigger `ADDON_PROTOCOL_VERSION` bump (re-export pin is part of the public surface) |

Any new allowlist additions require an explicit rationale entry in the tripwire and a review comment in the PR.

> Distilled from: `tasks/2026-05-08-rag-extractor-sdk/README.md` (batch-5 nugget), `tasks/mise-done/PR-1.md`

## Wave-2 scope notes

- **B-3 schema ownership — Phase 6 CLOSED (2026-05-18).**
  The transition-window B-3 reserved is now closed. Phase 6 paired
  host+addon migration moved 8 `bp_*` tables (`bp_inventory`,
  `bp_graphs`, `bp_functions`, `bp_events`, `bp_variables`,
  `bp_components`, `bp_implemented_interfaces`, `bp_nodes`,
  `bp_node_pins`, `bp_connections`) and 4 UE-shaped edge types out
  of core schema and into `project-rag-ue-addon` via the v6
  hookspecs (`project_rag_register_schema_tables`,
  `project_rag_register_schema_edge_types`). Core SCHEMA_VERSION
  bumped to v12 (no `bp_*` DDL in core `SCHEMA_DDL`). Opening a
  v12 graph with `--no-addons` produces no `bp_*` tables; the UE
  addon's hookimpl recreates them. Addon-vs-core name collisions
  raise `AddonRegistrationError` at the runtime guard
  (`project_rag_mcp/graph/db.py:887-920`) — no transition carve-out remains.
  Authority: `docs/plans/2026-05-18-phase-6-ue-cleanup-host-and-addon-paired.md`.

  *(Superseded 2026-05-16 → 2026-05-18) Earlier text described
  Phase 1 hookspec contract as the migration contract pending
  Phase 6 paired migration. Phase 6 has now shipped; the
  hookspec contract is the operational reality, not a pending
  bump.*

  *(Superseded 2026-05-16) Old text: "Pre-empting this without
  a second addon to validate the migration contract is a doctrine
  violation." PM disposition: Liberal B-3 — Phase 1 IS the
  coordinated bump; second-addon precondition retired.*
- **B-4 taxonomy SUPERSEDED (2026-05-15)** — `_VALID_SOURCES` is retired;
  `_VALID_DOMAINS = {"project","engine","official_docs","external"}` + per-domain
  `_VALID_SUBTYPES` replaces it per spec §6.1 (Amendment 1). The collection axis
  (collection axis, previously `sources=` list-form, has been replaced by the
  `source=` singular routing kwarg per C4; see plan
  `docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.md`). See
  `docs/decisions/DR-WAVE2-valid-sources-frozen.md` (status: superseded).
- **Wave 2b execution status (2026-05-16):** Physical extraction of UE code shipped
  in Phases 1A–1I and Phase 2 (P2.1–P2.4) via `/mise-en-place`. P2.5 (`structural_index_lite.py` deleted, FR-D/E/H macro helpers ported to addon `treesitter_postprocessor.py`) shipped 2026-05-16. Schema-extension
  migration seam (hookspec contract) shipped in Phase 1 of the multi-language chain
  (2026-05-16, v11 schema, `project_rag_register_schema_tables` +
  `project_rag_register_schema_edge_types`); see B-3 disposition above.
  Wave 2c terminal carve-out proceeds once the hookspec contract is solid
  (parse-test + round-trip fixture-addon test green); second-addon precondition retired.

  *(v6 changelog, AC-13, 2026-05-16) Hookspec table extended with
  `project_rag_register_schema_tables` + `project_rag_register_schema_edge_types`
  (Phase-1 addon-extensible-schema). `schema_extension_version` capability-dict
  field is now load-bearing: host upserts it into `addon_schema_versions` at
  addon load for observability. Both hookspecs use `@hookspec` parallel-call
  semantics; host iterates results and executes DDL + indexes after core DDL.*
- `provide_schema_migrations` hookspec is **reserved but NOT defined in v1**.
  The receiver harness ships an `assert_schema_migration_callable_present()`
  stub documenting the seam.
- **WrongProjectError and SentinelLoadError deprecation (PR-7 P7-1):** both
  classes in `project_rag_mcp/preflight.py` emit `DeprecationWarning` on import (added
  in PR-7) and are scheduled for removal in Wave 2c after addon physical
  extraction. Test authors should migrate from
  `pytest.raises(WrongProjectError)` to
  `result.verdict == PreflightVerdict.permanent_failure`. The Wave-2c
  removal is the doctrine-bound terminal step that eliminates these two
  symbols from the public surface.

**Engine-agnostic by design.** All hookspec names, signatures, and façade types are
engine-agnostic. No `blueprint`, `bp_`, `unreal`, `holodeck`, `uproject`, `umap`, or
`uasset` appears in any hookspec identifier. Unity or other engine addons can implement
any hookspec without a protocol revision. The CI tripwire
`tests/addons/test_v5_hookspec_naming.py` enforces this for all v5 additions; v6
additions are covered by the `_V6_HOOKSPEC_NAMES` list in the same file. The v7
hookspec `project_rag_register_chunk_metadata_extras` is engine-agnostic-compliant and
must be explicitly added to a `_V7_HOOKSPEC_NAMES` list in that test (Stub 2 of this
plan — the test reads the live hookspec module so auto-coverage of new names requires
explicit registration in the static list).

See [`addon-receiver-scaffold.md`](addon-receiver-scaffold.md) for Wave-2a
doctrine and the project-type gate philosophy.

---

## `project_rag.addon_commands` — v1 Addon-Contract Entry-Point Group

Introduced 2026-05-17 by §5 of the engine-RAG addon integration plan (A3).
This is a **new v1 addon-contract entry-point group** alongside the existing
`project_rag.addons` group (which carries the hookimpl class). The two groups
are orthogonal:

| Entry-point group | Purpose | Loaded by |
|---|---|---|
| `project_rag.addons` | pluggy hookimpl class (`_V8UEAddon` or equivalent) | Host PluginManager at boot |
| `project_rag.addon_commands` | `run_command(argv: list[str] \| None = None) -> int` callable per addon command | Umbrella aggregator (`/holodeck:doctor`, future peers) via `importlib.metadata` scan |

**Callable signature contract (uniform across all future addon `:doctor` implementations):**

```python
def run_command(argv: list[str] | None = None) -> int:
    ...
```

When invoked with `argv=["--json"]`, emits the `umbrella_envelope` JSON on stdout and
returns `0` (GREEN) or `1` (RED). The `umbrella_envelope` schema_version 1 is the
contract surface for `/holodeck:doctor` merge (see §5.6 of the sub-plan).

**Naming convention:** `doctor = "<package>.doctor:run_command"`. Future addons
(Unity, Godot, etc.) declare their `:doctor` entry-point under this group.

**Discovery:** umbrella aggregators scan via
`importlib.metadata.entry_points(group="project_rag.addon_commands")` — standard
Python entry-point machinery, no pluggy process-boundary introspection required.

**pyproject.toml declaration pattern:**

```toml
[project.entry-points."project_rag.addon_commands"]
doctor = "project_rag_ue_addon.doctor:run_command"
```

Spec backlink: docs/plans/2026-05-17-engine-rag-addon-section5-doctor.md §5.6.x

---

## collection_name opacity (v10 contract)

**Added 2026-05-18 (comprehensive-audit-remediation Wave 1, D8).**

The chroma collection name for an addon-owned corpus band is **opaque to the host**.
The host reads `band.collection_name` if set, and falls back to `_derive_collection_name(band)`
only when `collection_name is None`. The host never parses, derives, or validates the
collection name structure — the addon is the single authoritative source.

**Addon contract:**
- `_make_ue_band()` (or equivalent band constructor) MUST populate
  `collection_name` with the actual on-disk chroma collection name (e.g. `"ue_docs"`).
- The name must match exactly what was created by the corpus packaging script
  (`scripts/package_engine_archive.py`). No host-side derivation will correct a mismatch.
- Anticipated next-addon case (Unity): Unity addon must follow the same contract — populate
  `collection_name` with its own collection name. The host will use it verbatim.

**Host side:**
```python
collection_name = band.collection_name if band.collection_name else _derive_collection_name(band)
collection = client.get_collection(collection_name)
```

The `_derive_collection_name` fallback exists for bands that pre-date v10 and do not yet
populate the field. New addon hookimpls MUST populate `collection_name`.

**Why opacity:** future Unity, Godot, and other addons will have collection-naming
conventions the host does not and should not know. Encoding derivation logic in the host
creates a tight-coupling footgun every time a new addon engine has a different naming
scheme. The addon owns the corpus; the addon owns the name.

Spec backlink: docs/plans/2026-05-18-comprehensive-audit-remediation.md § W1-keystone

---

## v14 (2026-05-19) — whoami contributor seam

**Added 2026-05-19 (cross-repo unblock for project-rag-ue-addon W6 hookimpl; PM authorization verbatim: "authorized as document + chat message. NO DEFERRAL").**

### New façade: `AddonWhoamiContributorSpec`

Frozen dataclass exported from `core.addon_protocol`. Three fields:

```python
@dataclass(frozen=True)
class AddonWhoamiContributorSpec:
    namespace: str                       # ^[a-z][a-z0-9_]+$
    probe: Callable[[], dict[str, Any]]  # returns the sub-block; must not raise
    contributor: str = "unknown"         # addon identity; empty string rejected
```

`__post_init__` rejects empty `contributor` to keep the collision-diagnostic message readable (per the Staff Engineer F4 review). Namespace regex is also exported as `ADDON_WHOAMI_NAMESPACE_RE: Final[str]` for SSOT consumption (per the Staff Engineer F0).

### New hookspec: `project_rag_register_whoami_contributor`

Parallel-call (no `firstresult`); each addon returns `list[AddonWhoamiContributorSpec]`. Matches the `register_corpus_provider` / `register_schema_tables` pattern.

```python
@hookspec
def project_rag_register_whoami_contributor() -> "list[AddonWhoamiContributorSpec]":
    ...
```

Empty list is the graceful-fail signal (addon contributes no whoami sub-block).

### Aggregation helper: `core.addon_discovery.aggregate_whoami_contributors(pm)`

The canonical aggregation site. Validates each spec (type, namespace regex, callable probe) and enforces namespace uniqueness across **all** contributors (host + every addon). Raises `AddonWhoamiNamespaceCollision` (subclasses `AddonProtocolViolation`) with both contributor identity strings AND the conflicting namespace in the message.

**Lifecycle divergence (the Staff Engineer F6):** NOT called from `discover_addons()` at boot. Whoami is a command-time introspection surface — collisions surface at first `python -m core.whoami` invocation, not at server start. A bad whoami contributor must not prevent the MCP server from starting; the consumer (`core/whoami.py`, lands in W3 of `docs/plans/2026-05-19-first-class-install-redesign.md`) calls the aggregator at invocation time.

### Host JSON shape

Contributors compose under a top-level `addons:` key, nested per namespace:

```json
{
  "schema_version": 1,
  "os": {...}, "arch": {...}, "gpu": {...},
  "addons": {
    "ue": {"schema_version": 1, "corpus": {"present": true, ...}}
  }
}
```

The namespaced shape (vs. the addon EM's original top-level-merge proposal) is the deliberate re-shape negotiated in `archive/cross-repo/2026-05-19-host-whoami-hookspec-reply.md` — operator tooling can iterate contributors without knowing the addon set in advance, and host-owned top-level keys never collide with addon-contributed keys (anticipated Unity addon).

### Contracts the addon must honor

- `probe()` MUST return a `dict` (host validates `isinstance`).
- `probe()` MUST NOT raise. Absent state goes in fields: `corpus: {"present": false}`.
- `probe()` MUST complete in <500 ms wall-clock on a warm machine (heavy probes belong in `/project-rag-<addon>:doctor`).
- Each contributor sub-block carries its own `schema_version: int` (contributor-owned; host does not parse).

Enforcement of the must-not-raise and time-budget contracts is consumer-side (`core/whoami.py:compose()`, W3); the v14 surface ships ahead of the consumer.

### Cross-repo origin

- Ask doc: `../project-rag-ue-addon/archive/cross-repo/2026-05-19-host-whoami-hookspec-request.md`
- Reply doc: `archive/cross-repo/2026-05-19-host-whoami-hookspec-reply.md`
- the Staff Engineer review: APPROVED_WITH_NOTES on the in-tree diff; all 7 findings folded inline.

---

## v13 (2026-05-19) — CorpusBand.default_weight restored under N-lane ownership

**Added 2026-05-19 (fusion-pipeline-n-lane Wave C).**

Restores `CorpusBand.default_weight: float | None = None` as a SUGGESTED multiplicative weight for the N-lane fusion pipeline. Weight resolution chain (highest precedence first): caller-supplied `band_weights` kwarg on `project_rag_blended_query`, then `PROJECT_RAG_BAND_WEIGHT_<band_name>` env override, then this field, then "absent" (multiplicative no-op).

The v10 removal was correct given the three-lane hardcoded fusion pipeline that had no consumer for per-band values; v13's N-lane fusion is the first real consumer. `authority_pairs` remains REMOVED (v14 may revisit gated on a separate failing-test consumer proof per the Director of Engineering finding F#2).

Plan: `docs/plans/2026-05-19-fusion-pipeline-n-lane.md` § Wave C.

---

## v12 (2026-05-18) — per-tool project graph.db capability

**Added 2026-05-18 (addon-protocol-v12-and-ue-tool-migration, Phase 1).**

### New field: `AddonToolRegistration.requires_project_graph_db`

`AddonToolRegistration` gains a new defaulted field:

```python
requires_project_graph_db: bool = False
```

When an addon tool sets this field `True`, the host wraps its handler at
registration time to inject `project_db_conn` as a keyword argument per call.

### Host-side wrap mechanism

At the addon-tool registration loop in `project_rag_mcp/project_rag_server.py`, the host
inspects each `_reg.requires_project_graph_db`; when `True`, it wraps the
handler via a module-level factory:

```python
def _wrap_addon_handler_for_project_db(handler, get_db_conn):
    """Host-injected per-call project graph.db conn factory.

    Addon handler receives project_db_conn as a fresh SQLite connection per
    call. Handler must not cache the connection — helper is fresh-per-call by
    host contract (see docs/wiki/addon-protocol.md § v12).
    """
    if inspect.iscoroutinefunction(handler):
        async def _wrapped(*args, **kwargs):
            return await handler(*args, project_db_conn=get_db_conn(), **kwargs)
    else:
        def _wrapped(*args, **kwargs):
            return handler(*args, project_db_conn=get_db_conn(), **kwargs)
    return _wrapped
```

**Handler async/sync.** Handlers may be either sync or async — `_wrap_addon_handler_for_project_db` branches on `inspect.iscoroutinefunction()` and returns a wrapper of the same kind. Sync handlers are called directly; async handlers are awaited. Tool authors choose based on whether the handler's body genuinely benefits from async I/O.
<!-- Review: code-reviewer F10 — document async/sync handler contract; snippet updated to match F1 fix -->

**Addon handler contract:**
- Handlers with `requires_project_graph_db=True` receive `project_db_conn`
  as a fresh SQLite connection per call.
- Handlers MUST NOT cache the connection across calls — the host contract is
  fresh-per-call.
- Engine-corpus addon tools omit the flag; their behavior and handler
  signatures are unchanged.

### Source/authority separation is unaffected

Source/authority separation at the corpus-class layer (see
`docs/wiki/corpus-class-taxonomy.md` if present) is unaffected by this
decision. That layer governs what corpus a structural-index row belongs to,
not what data sources a handler may read. The `requires_project_graph_db`
flag is a *capability declaration* at the registration surface, not a
corpus-class assertion.

Reference: `tasks/2026-05-18-v12-vs-option-c-tiebreaker/zoli-verdict.md`
§Conditions-to-flip for the architectural framing and conditions under which
bundle-level promotion could revisit this decision.

---

## Tool description prefix conventions

Addon-contributed MCP tools use a bracketed prefix as the first token of
their `description=` field. The prefix signals domain scope to consumers
(context-builder agents, routing tables, operator docs) without relying on
tool name alone. Single space after `]`. Example:

```python
AddonToolRegistration(
    name="project_engine_examples",
    description="[Engine corpus] Find usage examples ...",
    handler=...,
)
```

### Defined prefixes

| Prefix | Scope | Applies to |
|--------|-------|------------|
| `[Engine corpus]` | Engine-wide reference corpus (UE docs, engine source) | Addon tools that answer questions about engine APIs, built-ins, or engine-side docs — never about the specific project under analysis |
| `[Project (UE)]` | UE-project graph — project-specific data in UE-shaped vocabulary | Addon tools that answer project-graph questions but require UE-specific schema knowledge (e.g., Blueprint graph, CVar, actor composition, tag graph, test coverage, virtual override chains). These tools require `requires_project_graph_db=True`. |

**Why `[Project (UE)]` and not `[Engine corpus]` for project-graph tools:**
`[Engine corpus]` is materially misleading for tools that read from the
project's own `graph.db` — they are querying project-specific extracted data,
not the engine's reference corpus. The `(UE)` qualifier signals that the tool
speaks UE-shaped vocabulary (Blueprint names, Gameplay Tags, UE component
hierarchy), which is why it lives in the UE addon rather than in-host.

**Tools carrying `[Project (UE)]` prefix (v12 Phase 2 migration targets):**
`project_blueprint_graph`, `project_cvar`, `project_actor_composition`,
`project_overrides`, `project_tag_graph`, `project_test_coverage`.

Spec backlink: docs/plans/2026-05-18-addon-protocol-v12-and-ue-tool-migration.md §Chunk-1.3 edit 4 (the Staff Engineer Finding 2)
