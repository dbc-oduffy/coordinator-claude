---
title: Authoring an addon
created: 2026-05-17
status: active
spec_backlink: docs/plans/2026-05-17-engine-rag-addon-contract.md
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-17-engine-rag-addon-contract.md §Component design -->

# Authoring an addon

Definitive contract reference for anyone authoring a project-rag addon of any kind —
engine corpus, content corpus, knowledge base, chunker extension, or anything else the
hookspec surface exposes. Three worked examples cover the UE engine corpus (real), a
Unity engine addon (paper, forward-looking), and the coordinator meta-knowledge corpus
(non-engine, universal).

## 1. Plug-points the substrate exposes

Every addon binding passes through one of the hookspecs below. The table is a
single-page index; §3 adds per-hookspec detail.

| Hookspec | Returns | MUST / SHOULD | Notes |
|---|---|---|---|
| [`project_rag_register_corpus_provider`](../../core/addon_hookspecs.py) | `list[CorpusBand]` | MUST (for corpus addons) | Parallel-call. Returns band instances for every corpus this addon declares. |
| [`project_rag_register_doctor_probe`](../../core/addon_hookspecs.py) | `list[FailureCatalogRow]` | MUST (for corpus addons) | v8 NEW. Parallel-call. Addon-contributed failure catalog rows merged at boot. |
| [`project_rag_register_chunker`](../../core/addon_hookspecs.py) | `list[AddonChunkerSpec]` | MUST (for chunker addons) | Parallel-call. |
| [`project_rag_register_chunk_metadata_extras`](../../core/addon_hookspecs.py) | `list[AddonChunkMetadataExtrasSpec]` | SHOULD (if custom chunk fields) | v7. Parallel-call. |
| [`project_rag_register_producer`](../../core/addon_hookspecs.py) | `list[AddonProducerSpec]` | SHOULD (if reindex pipeline) | Parallel-call. |
| [`project_rag_register_extractor`](../../core/addon_hookspecs.py) | `list[AddonExtractorSpec]` | SHOULD (if schema tables) | Parallel-call. |
| [`project_rag_register_health_field`](../../core/addon_hookspecs.py) | `list[AddonHealthFieldSpec]` | SHOULD (if addon-specific health) | v5. Parallel-call. |
| [`project_rag_register_cli_subcommand`](../../core/addon_hookspecs.py) | `list[AddonCliSubcommandSpec]` | OPTIONAL | v6. |
| [`project_rag_register_watch_pattern`](../../core/addon_hookspecs.py) | `list[AddonWatchPatternSpec]` | OPTIONAL | v6. |
| [`project_rag_register_extra_macros`](../../core/addon_hookspecs.py) | `list[AddonMacroSkipListSpec]` | OPTIONAL | v6. C++ macro skip-lists. |
| [`project_rag_register_long_lived_subprocess`](../../core/addon_hookspecs.py) | `list[AddonLongLivedSubprocessSpec]` | OPTIONAL | v2. GPU/CPU sidecar processes. |
| [`project_rag_register_eval_bank`](../../core/addon_hookspecs.py) | `list[AddonBankSpec]` | OPTIONAL | v5. |
| [`project_rag_register_eval_probe`](../../core/addon_hookspecs.py) | `list[AddonProbeSpec]` | OPTIONAL | v5. |

Hookspec definitions: `core/addon_hookspecs.py`. Discovery key: `project_rag.addons` entry-point group.

## 2. pyproject.toml entry-point format

```toml
[project.entry-points."project_rag.addons"]
my-addon-name = "my_addon_package:ProjectRagAddonPlugin"
```

The class named (e.g. `ProjectRagAddonPlugin`) must be a pluggy plugin class — a class
whose methods are `@hookimpl`-decorated. The entry-point group `project_rag.addons` is
the discovery key; the host calls
`pluggy.PluginManager.load_setuptools_entrypoints("project_rag.addons")` at boot.

The entry-point name (left of `=`) is used in log lines and as the `contributor` field
in doctor probe rows. Use a stable, globally-unique name matching the PyPI package name
(e.g. `project-rag-ue-addon`, `project-rag-unity-addon`).

## 3. Hookspec inventory — MUST / SHOULD guidance per hookspec

### `project_rag_register_corpus_provider`

**What the host does with the return value:** host aggregates all `CorpusBand` instances
across all registered addons at boot, populates `SourceRegistry`, and serves bands via
`project_whoami`. The `SourceRegistry` is the runtime routing table for `project_semantic_search`
and the blended-query backend.

**What the addon must guarantee:**
- `band_name` is unique across the addon's own bands (host enforces global uniqueness at boot; collision raises immediately).
- `applicable_kinds=None` for universal bands (queryable from any project kind).
- Non-empty `applicable_kinds` for engine-specific or language-specific bands.
- `authority_pairs` entries use only authority values declared in `corpus-class-taxonomy.md`.
- `hookimpl` never raises — wrap any I/O in `try/except`; return empty list on failure.

### `project_rag_register_doctor_probe`

**What the host does with the return value:** host merges all `FailureCatalogRow` dicts
across all registered addons at boot into a unified failure catalog. The `/project-rag:doctor`
command iterates the catalog, runs each probe step, and surfaces findings with
`hint_template`-derived remediation text.

**What the addon must guarantee:**
- Each row's `id` field is globally unique across the merged catalog (use an addon-namespace prefix, e.g. `A-F-N` for the UE addon, `U-F-N` for Unity).
- The canonical seven fields are present (see §8 for the authoritative field list).
- `contributor` matches the addon's entry-point name.
- `hookimpl` never raises — return `[]` on failure.

### `project_rag_register_chunker`

**What the host does:** registers chunker specs into `indexer/chunker_registry.py`. The
spec's `runner` callable is invoked at reindex time for each file matching `domain`.

**What the addon must guarantee:** `id` is globally unique; `scope` is `"project"` (engine
scope is reserved); `runner` is a callable accepting `ChunkerContext`.

### Other hookspecs

For `project_rag_register_chunk_metadata_extras`, `project_rag_register_producer`,
`project_rag_register_extractor`, `project_rag_register_health_field`, and v6+ hookspecs,
see [`docs/wiki/addon-protocol.md`](addon-protocol.md) for full field documentation
and semantics. The table in §1 above is the index; that wiki is the field reference.

## 4. CorpusBand v13 field semantics

<!-- v13 (2026-05-19) reintroduced `default_weight` under a different ownership model —
     see `addon-protocol.md §v13` and `docs/plans/2026-05-19-fusion-pipeline-n-lane.md`. -->

`CorpusBand` is the façade type returned by `project_rag_register_corpus_provider`.
All fields are declared in `core/addon_protocol.py`.

| Field | Type | Default | Dispatch-gating? | Semantics |
|---|---|---|---|---|
| `band_name` | `str` | required | yes | Stable opaque name. Naming convention per §6. |
| `default_weight` | `float \| None` | `None` | yes (v13) | Optional suggested blend weight 0.0–1.0. Host may override via env or caller kwarg (see `fusion-policy.md §N-lane weight semantics`). `None` = no suggestion; band participates in fusion without multiplicative distortion. |
| `applicable_kinds` | `list[str] \| None` | `None` | yes | `None` = universal. `[]` = likely bug (warn+filter). Strings match `core/project_type.py` kind vocabulary. |
| `chunk_filter` | `dict[str, Any] \| None` | `None` | yes (v8) | Chroma `where` clause. `None` = whole-corpus query. E.g. `{"provenance_module": "runtime"}`. |
| `engine_version` | `str \| None` | `None` | yes (v8) | Engine version string. `None` treated as universal-version (auto-include in default blend regardless of caller engine_version). Non-None: only included in default blend when caller's `ProjectContext.engine_version` matches exactly. |
| `required_env` | `dict[str, str] \| None` | `None` | yes (v8) | Env-var name → expected-present-value. If declared, `project-rag-cli wire` aggregates and persists to `~/.project-rag/wiring.env`. Absent → `addon_unreachable` verdict. |
| `corpus_sha256` | `str \| None` | `None` | no (inert) | SHA256 of the corpus artifact for provenance. Populated at corpus download time by addon setup scripts. |
| `corpus_root` | `str \| None` | `None` | yes (v8) | Addon declares the Chroma parent directory. Host opens Chroma at `<corpus_root>/engine-vector-store/<engine_version>/` for engine-kinded bands. Non-engine bands use the data-dir convention (§5). `None` means no corpus mounted (empty / not-yet-downloaded). |

**Note on `applicable_kinds` string values:** these are matched against the return value of
`core.project_type.detect_kind(project_root)`. Current values in tree: `"unreal"`, `"python"`,
`"ts"`, `"rust"`, `"generic"` (catch-all for unrecognised project types). Unity addon registers
`"unity"`. Godot addon registers `"godot"`. An addon can register `applicable_kinds=["unreal", "unity"]`
to serve both without requiring a separate band per engine. Universal bands use `applicable_kinds=None`.

Note: `"cpp"` is NOT a kind value — C++ projects that don't match another sentinel fall through
to `"generic"`. `"typescript"` is also not a valid kind — use `"ts"`.

**Dispatch-gating vs inert:** fields marked `yes (v8)` in the Dispatch-gating column gate
host behavior (routing, Chroma open, blend filter, verdict). Fields marked `no (inert)` are
carry-along data that does not alter host dispatch. Per OQ-2 refined bump rule: dispatch-gating
fields DO trigger `ADDON_PROTOCOL_VERSION` bumps; inert fields ship in the same bump for
atomicity but do not individually mandate it.

## 5. Data-dir convention

```
<addon-root>/data/<content-form>-{vector-store,structural}/<version>/
```

Registered `<content-form>` values (open-ended; these are examples, not a closed enum):

| `<content-form>` | Usage |
|---|---|
| `engine-` | Engine source code corpora (UE runtime, Unity assemblies, Godot modules) |
| `knowledge-` | Meta-knowledge corpora (coordinator wikis, decisions, lessons) |
| `corpus-` | Generic catch-all for non-engine, non-knowledge corpora |

The `<content-form>` slot exists to prevent path collisions between addons and to give the
directory tree a human-readable structure. Executors populating `corpus_root` in `CorpusBand`
should point at `<addon-root>/data` (the Chroma parent); the host resolves sub-paths per the
seam contracts in the parent mega-plan.

## 6. Band-name convention

Two naming patterns, no others:

**1. Engine bindings:** `[engine-name]_[engine-version]_[band]`

- Examples: `unreal_5.7_runtime`, `unreal_5.7_editor`, `unity_2023_runtime`, `unity_2023_hdrp`
- `[engine-name]`: lowercase, hyphen-free, matches `applicable_kinds` string (e.g. `unreal`, `unity`, `godot`)
- `[engine-version]`: dotted semver — use `5.7` not `5_7` or `57`
- `[band]`: purpose slice — `runtime`, `editor`, `plugin`, `lyra`, `hdrp`, `urp`, etc.

**2. Non-engine bindings (universal or content-specific):**

- Bare content-form: `coordinator_knowledge`, `project_lessons`, `api_docs`
- OR content-form_topic: `coordinator_knowledge_wikis`, `coordinator_knowledge_decisions`
- No engine-name prefix. No engine-version segment.
- `applicable_kinds=None` for truly universal bands (queryable from any project).
- `applicable_kinds=["python"]` (etc.) for content bands scoped to a project kind.

**Anti-patterns (explicit):**

- `engine_runtime` — wrong; generic prefix without engine-name hides multi-engine intent. Use `unreal_5.7_runtime`.
- `ue_runtime` — wrong; `ue` abbreviation is non-standard in the naming scheme. Use `unreal_5.7_runtime`.
- `engine_knowledge` — wrong for a knowledge corpus; use `coordinator_knowledge` (bare content-form, not engine-prefixed).
- Band names containing `holodeck`, `blueprint`, `uproject` — these are UE-specific terms; never use them in band names visible in the host substrate.

**Namespace reservation** (see also `cross-corpus-class-addon-contract.md §7`):

- `unreal_*` — reserved for `project-rag-ue-addon`.
- `unity_*` — reserved for the anticipated `project-rag-unity-addon`.
- `godot_*` — reserved for a future Godot addon.
- `coordinator_*` — reserved for coordinator-plugin-bundled addons.
- `template_*` — reserved for the template-addon and testing purposes.

## 7. Setup-script convention (Phase 4)

Every corpus addon should ship:

- `scripts/setup.{ps1,sh}` with a Phase 4 step that calls the host's registration
  helpers via the addon's own CLI subcommand:
  ```
  python -m <addon_cli_module> register-with-project-rag --target-project-root <consumer_root>
  ```
- An optional Phase 5 step that downloads the corpus artifact if absent locally
  (only relevant for addons distributing a pre-built corpus).
- `data/` directory at `<addon-root>/data/` as the `corpus_root` base.

Non-corpus addons (chunker-only, eval-bank-only) may ship minimal or no setup scripts.
The host does NOT require setup scripts — they are a convention, not a contract.

## 8. Doctor-probe registration

**Canonical failure-catalog row schema (authoritative location: `authoring-an-addon.md §8`):**

| Field | Required | Description |
|---|---|---|
| `id` | yes | Unique probe id across merged catalog (e.g. `A-F-3`, `TMPL-F-1`) |
| `failure_mode` | yes | Human-readable description of the failure mode |
| `doctor_probe` | yes | Name of the probe step function the doctor runs |
| `setup_remediation_template` | yes | Command template to surface in remediation hint |
| `runtime_verdict` | yes | Envelope verdict emitted at runtime when this failure is active |
| `hint_template` | yes | Template string for the user-facing hint |
| `contributor` | yes | Addon entry-point name that contributed this row |

Every corpus addon MUST implement `project_rag_register_doctor_probe` returning
`list[dict]`. Each row must conform to the canonical schema above (this section is
the single source of truth; §10/§11/§12 worked examples and test `required_fields`
assertions all derive from this table):

```python
@hookimpl
def project_rag_register_doctor_probe(self) -> list[dict]:
    return [
        {
            "id": "A-F-3",
            "failure_mode": "Addon entry-point not reachable in server venv",
            "doctor_probe": "step_addon_entrypoint_reachable",
            "setup_remediation_template": "/project-rag:setup --reinstall-addons",
            "runtime_verdict": "addon_unreachable",
            "hint_template": "❌ Addon {addon_name} not importable from server venv. Run: /project-rag:setup --reinstall-addons",
            "contributor": "project-rag-ue-addon"
        },
        # ... additional rows
    ]
```

Row `id` must be unique across the merged catalog. Use an addon-namespace prefix
(`A-F-N` for the UE addon, `U-F-N` for a Unity addon, `TMPL-F-N` for the template addon).
The host enforces id uniqueness at boot; collision raises immediately.

Non-corpus addons (e.g. chunker-only addons) SHOULD contribute at least one probe row
covering their own installation health (e.g. "chunker entry-point importable").

Field names are the canonical seven listed in the table above — any extension must be
proposed against this section as the source of truth.

## 9. Adding a new caller kind (extending core/project_type.py)

To add a new engine or content type as a first-class caller kind:

```python
# core/project_type.py (illustrative — check actual implementation before editing)
def detect(project_root: Path) -> str:
    """Returns one of: "unreal", "python", "ts", "rust", "generic", or any
    new kind added here. Current PROJECT_TYPES = ("unreal", "ts", "rust", "python", "generic").
    """
    # Unreal: look for *.uproject
    if any(project_root.glob("*.uproject")):
        return "unreal"
    # Unity: look for Assets/ directory + ProjectSettings/
    if (project_root / "Assets").is_dir() and (project_root / "ProjectSettings").is_dir():
        return "unity"
    # ... etc.
    return "generic"
```

The caller kind string (e.g. `"unity"`) then matches `CorpusBand.applicable_kinds`
registrations. An addon registering `applicable_kinds=["unity"]` will be auto-included
in default-blend for any project where `detect()` returns `"unity"`.

**No protocol bump is required** to add a new kind string — `applicable_kinds` is a
`list[str]` and the host matches strings, not an enum. The addon ships the
`applicable_kinds=["unity"]` declaration; the host auto-includes it when `detect()`
returns `"unity"`.

**Engine-agnostic hookspec discipline — explicit anti-patterns:**

The following patterns are forbidden in hookspec names and signatures:

| Anti-pattern | Reason | Correct form |
|---|---|---|
| `project_rag_register_ue_corpus` | UE-specific prefix in hookspec name | `project_rag_register_corpus_provider` |
| `project_rag_register_unreal_doctor_probe` | Engine-specific prefix | `project_rag_register_doctor_probe` |
| `applicable_kinds: UnrealKindEnum` | Typed to a UE-specific enum | `applicable_kinds: list[str] \| None` |
| `band_name: UnrealBandName` | Typed to UE-specific named values | `band_name: str` |
| Hookspec docstring mentioning `Blueprint`, `UFUNCTION`, `uproject` | Engine-specific vocabulary in host contract | Generic vocabulary; UE-specific content belongs in addon docstrings |

Unity future-compat shapes the design today in the following specific ways:

1. `CorpusBand.applicable_kinds` uses `list[str]` not `list[Literal["unreal"]]` — Unity addon registers `["unity"]` without a host change.
2. `project_rag_register_doctor_probe` row schema uses `"contributor": "<addon-entry-point-name>"` (string, not a UE-specific type) — Unity addon contributes rows with `"contributor": "project-rag-unity-addon"`.
3. `data/<content-form>-vector-store/<version>/` path convention uses `<content-form>` as a free-form segment — Unity addon uses `engine-vector-store/2023/` without a host change.
4. The `project_rag_register_corpus_provider` hookspec docstring explicitly mentions "any addon" and avoids UE vocabulary — this is the contract text that Unity authors read.

## 10. Worked example A — UE 5.7 engine addon (4 bands)

References the real `project-rag-ue-addon` repo as the canonical implementation.
See `X:/project-rag-ue-addon/project_rag_ue_addon/__init__.py` and the addon plan
§3.1 for the actual hookimpl code (path exists once E-NAMED-BANDS ships; see addon
plan `2026-05-17-engine-rag-addon-integration.md §3.1` for implementation).

**Four-band table:**

| Band name | `chunk_filter` | `applicable_kinds` | `engine_version` | `default_weight` |
|---|---|---|---|---|
| `unreal_5.7_runtime` | `{"provenance_module": "runtime"}` | `["unreal"]` | `"5.7"` | 0.5 |
| `unreal_5.7_editor` | `{"provenance_module": "editor"}` | `["unreal"]` | `"5.7"` | 0.3 |
| `unreal_5.7_plugin` | `{"provenance_module": "plugin"}` | `["unreal"]` | `"5.7"` | 0.3 |
| `unreal_5.7_lyra` | `{"provenance_module": "lyra"}` | `["unreal"]` | `"5.7"` | 0.2 |

**Doctor probe rows:** A-F-3 (entry-point reachable), A-F-4 (corpus present), A-F-6 (schema
valid), A-F-8 (dead structural-index path retired). Each row conforms to the canonical schema
at §8 (this section is the source of truth for all field names).

**`corpus_root`** points at `<addon-root>/data`. All four bands share one Chroma collection
(`chroma_unreal_5.7`); `chunk_filter` carves the view per band.

**Default-blend note:** a UE 5.7 consumer with `source=None` blends caller-project + all
bands with `applicable_kinds ⊇ {"unreal"}` AND `engine_version == "5.7"` + all universal
bands. The `unreal_5.5_*` bands (if installed in parallel) are excluded from default-blend
— cross-version query is via explicit `source="unreal_5.5_runtime"`.

## 11. Worked example B — Unity 2023 engine addon (paper-only)

This worked example is forward-looking; no `project-rag-unity-addon` repo exists. It
demonstrates that the contract is genuinely engine-agnostic.

```python
# project_rag_unity_addon/__init__.py (illustrative — not shipped)
import pluggy
from core.addon_protocol import CorpusBand

hookimpl = pluggy.HookimplMarker("project_rag")

class ProjectRagAddonPlugin:

    @hookimpl
    def project_rag_register_corpus_provider(self) -> list[CorpusBand]:
        return [
            CorpusBand(
                band_name="unity_2023_runtime",
                authority_pairs=[("unity_runtime", "api")],
                default_weight=0.5,
                applicable_kinds=["unity"],
                engine_version="2023",
                chunk_filter={"provenance_module": "runtime"},
                corpus_root=str(_addon_corpus_root()),
            ),
            CorpusBand(
                band_name="unity_2023_hdrp",
                authority_pairs=[("unity_hdrp", "api")],
                default_weight=0.3,
                applicable_kinds=["unity"],
                engine_version="2023",
                chunk_filter={"provenance_module": "hdrp"},
                corpus_root=str(_addon_corpus_root()),
            ),
        ]

    @hookimpl
    def project_rag_register_doctor_probe(self) -> list[dict]:
        return [
            {
                "id": "U-F-1",
                "failure_mode": "Unity addon entry-point not reachable in server venv",
                "doctor_probe": "step_unity_addon_entrypoint_reachable",
                "setup_remediation_template": "/project-rag:setup --reinstall-addons",
                "runtime_verdict": "addon_unreachable",
                "hint_template": "❌ Unity addon not importable. Run: /project-rag:setup --reinstall-addons",
                "contributor": "project-rag-unity-addon"
            },
        ]
```

No changes to host code. No new hookspecs. No protocol bump. The pattern is identical
to the UE addon; only the band names, `applicable_kinds` strings, and `contributor` id differ.

## 12. Worked example C — coordinator meta-knowledge corpus (non-engine, universal)

This is the Z-3 worked example. The producer is a follow-on plan (coordinator-plugin-bundled
addon at `~/.claude/plugins/coordinator/project_rag_addon/`); this example
documents the binding shape that the template-addon already demonstrates.

```python
# ~/.claude/plugins/coordinator/project_rag_addon/__init__.py
# (shape only — actual content is a follow-on plan)
import pluggy
from core.addon_protocol import CorpusBand

hookimpl = pluggy.HookimplMarker("project_rag")

class CoordinatorKnowledgeAddon:

    @hookimpl
    def project_rag_register_corpus_provider(self) -> list[CorpusBand]:
        return [
            CorpusBand(
                band_name="coordinator_knowledge",
                authority_pairs=[("coordinator_docs", "knowledge")],  # 'knowledge' authority — new in v8
                default_weight=0.3,
                applicable_kinds=None,   # universal — queryable from ANY project kind
                engine_version=None,     # not engine-tied; no version filter applies
                chunk_filter=None,       # whole corpus; no sub-band filter needed yet
                corpus_root=str(_addon_corpus_root()),
            ),
        ]
```

Key differences from the UE example:

- `applicable_kinds=None` (universal) — a Python project, a UE project, a TS project all
  auto-include `coordinator_knowledge` in default-blend.
- `engine_version=None` — not engine-tied; no engine_version filter applies.
- `chunk_filter=None` — single corpus band, no sub-band carving needed.
- `authority_pairs` uses `"knowledge"` authority — the corpus class added to
  `corpus-class-taxonomy.md` by this phase.
- `corpus_root` points at the coordinator plugin's data directory, not a project-relative path.

The namespace `coordinator_knowledge` is reserved per AD-11. No other addon should register
a band with this name.

## 13. Cross-references

- `docs/wiki/cross-corpus-class-addon-contract.md` — substrate symmetry spec (this phase)
- `docs/wiki/corpus-class-taxonomy.md` — authority value vocabulary
- `docs/wiki/addon-protocol.md` — version bump history
- `docs/wiki/addon-hookspec-shape.md` — hookspec signatures
- `core/addon_protocol.py` — `CorpusBand` dataclass + `ADDON_PROTOCOL_VERSION`
- `core/addon_hookspecs.py` — hookspec definitions
- `docs/wiki/failure-catalog.json` (shipped by E-NAMED-BANDS) + `docs/wiki/project-rag-failure-catalog.md` (shipped by E-NAMED-BANDS) — catalog row schema
- Template addon: `X:/project-rag-template-addon/` — working exemplar with one live universal band
