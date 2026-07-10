---
title: Capability dispatch — v6 host-addon-capability surface
created: 2026-05-16
status: active
spec_backlink: docs/plans/2026-05-16-w8c-v6-ratification-content-error-migration.md §T10
relates_to:
  - docs/wiki/addon-protocol.md
  - docs/wiki/addon-receiver-scaffold.md
  - docs/wiki/thin-wrapper-graceful-fail.md
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-16-w8c-v6-ratification-content-error-migration.md §T10 (AC-10, AC-11) -->
<!-- Spec backlink: docs/plans/2026-05-16-w8c-v6-ratification-content-error-migration.md §T1 -->

# Capability dispatch

The v6 host-addon-capability-dispatch surface: how the host asks addons whether
a named capability is currently satisfiable, and how producers declare their
runtime requirements without hard-coding engine names or flags.

## Capability-string vocabulary

Capability strings are **opaque snake_case ASCII identifiers** that producers
declare as runtime requirements and addons claim via `project_rag_provide_capability`.
The host has no registry of known strings — the string is opaque to the host; only
the claiming addon's hookimpl recognises it.

**Conventions:**
- Lowercase snake_case ASCII: `ue_editor`, `libclang`, `uecheckhost`.
- No product version embedded in the string (version-specific branching is the
  hookimpl's responsibility, not the capability string's).
- Domain prefix when ambiguous across addons: `ue_editor` not `editor`; `libclang`
  not `clang`.

**Known v6 capability strings (UE addon — `project-rag-ue-addon`):**

| String | Satisfied when |
|---|---|
| `ue_editor` | UE editor process is running and `example-game-repo-control` bridge is live |
| `libclang` | `libclang` is importable in the current interpreter |
| `uecheckhost` | `UeCheckHost.exe` is locatable on this host |
| `ue_plugin_installed` | A named UE plugin `.uplugin` file exists under the resolved engine root. Context carries `engine_root: Path` and `plugin_name: str` set by the host. Used by `_engine_plugin_installed_via_pm` in `priming/producer_runner.py` (W8d). |

Non-UE addons contribute their own strings. The host unions all claimed capabilities
across all registered addons.

## `AddonProducerSpec` — polarity flip (v6)

Before v6, producers declared `requires_editor: bool` and `domain: list[str]` to
gate execution. These fields are **retired in v6** with no transition alias (PM
2026-05-16 OQ-2 disposition: **stop, not warn**).

**v6 shape:**
```python
@dataclass(frozen=True)
class AddonProducerSpec:
    id: str
    runner: Callable[..., Any]
    requires_capabilities: tuple[str, ...] = ()   # replaces requires_editor + domain
    depends_on: list[str] = field(default_factory=list)
    timeout_seconds: int = 1200
    required_python_classes: list[dict[str, str]] = field(default_factory=list)
    output_dir: str | None = None
```

**Migration from v5:**

| v5 field | v6 replacement |
|---|---|
| `requires_editor=True` | `requires_capabilities=("ue_editor",)` |
| `requires_editor=False` | `requires_capabilities=()` (omit; default) |
| `domain=["unreal"]` | drop entirely; no replacement |
| `clang-layer2` producer | `requires_capabilities=("libclang",)` |
| `uht_layer1` producer | `requires_capabilities=("uecheckhost",)` |

Old manifests or hookimpls declaring `requires_editor:` or `domain:` raise
`ManifestSchemaError` at boot. The error message names this wiki page.

## Abstain-vs-unsatisfied contract

The following contract is **mandatory for all `project_rag_provide_capability` hookimpls**.
The text below is reproduced verbatim from the hookspec docstring in
`core/addon_hookspecs.py`:

> **ABSTAIN vs UNSATISFIED CONTRACT (mandatory for all hookimpls):**
> Hookimpls MUST return None when they do NOT recognise the capability string
> at all — returning None is the abstain signal, indicating no addon claims
> this capability (operator-config-error territory: wrong string, missing
> addon). Hookimpls that DO recognise the capability but cannot satisfy it
> (e.g. UE editor not running, libclang not found) MUST return
> `AddonCapabilityResult(satisfied=False, reason=<human-readable string>)`.
> The host distinguishes these two cases at the ledger layer:
> - all hookimpls returned None → `status="capability_unclaimed"` row
> - first non-None returned `satisfied=False` → `status="capability_unsatisfied"` row
>
> This contract is the semantic load-bearing seam; hookimpls that conflate
> "don't recognise" with "can't satisfy" will produce misleading ledger rows.

## Ledger statuses

The host records capability query results in the producer-run ledger. Two status
values specific to capability dispatch:

| Status | Meaning |
|---|---|
| `capability_unclaimed` | All hookimpls returned `None` for this capability string. No addon claims it. Likely an operator error: wrong string, missing addon install. |
| `capability_unsatisfied` | The first non-None hookimpl returned `satisfied=False`. An addon recognises the capability but cannot satisfy it right now (e.g. UE editor not running). The `reason` field carries the human-readable explanation. |

Producers whose `requires_capabilities` contains any `capability_unclaimed` or
`capability_unsatisfied` capability are skipped with the ledger status recorded.

See [`producer-ledger-status-vocabulary.md`](../../../../project-rag/docs/wiki/producer-ledger-status-vocabulary.md) for the canonical status carve-up across all 9 final statuses.

## Six W8c hookspecs

### Hookspecs with W8c sister hookimpls

These three hookspecs have sister hookimpls shipping in W8c (`project-rag-ue-addon`
T12). They are immediately functional after the W8c cross-repo landing.

**`project_rag_provide_capability`** (`firstresult=True`)

```python
def project_rag_provide_capability(
    capability: str,
    ctx: AddonCapabilityContext,
) -> AddonCapabilityResult | None: ...
```

Capability satisfaction query. Pluggy `firstresult=True` — the host takes the first
non-None reply. Hookimpls MUST return `None` for capability strings they do not claim.
See abstain-vs-unsatisfied contract above.

**`project_rag_classify_content_error`** (`firstresult=True`)

```python
def project_rag_classify_content_error(
    error_text: str,
    file_path: Path | None,
) -> AddonContentErrorClassification | None: ...
```

Replaces direct `priming.bp_corruption.is_bp_content_error` calls. Return `None` when
the error is not recognised by this addon at all. Return non-None only when **claiming**
the error as a content/non-content classification. This respects the pluggy
`firstresult=True` "first-non-None" semantics — returning non-None short-circuits the
call chain.

**`project_rag_summarize_runtime_log`** (`firstresult=True`)

```python
def project_rag_summarize_runtime_log(
    capability: str,
    log_text: str,
) -> AddonRuntimeLogSummary | None: ...
```

Replaces `ue_log_parser.parse_ue_log` + `compose_remediation` calls. The host invokes
this after `dispatch_external_runtime` to produce structured post-mortem summaries
surfaced via doctor probes. Return `None` to abstain.

### Hookspecs deferring to W8d/W8f for sister hookimpls

These three hookspecs have signatures declared in v6 but sister hookimpl implementations
are deferred to later waves. They are available for host-side wiring now; addon
implementations follow.

**`project_rag_resolve_external_runtime_binary`** (`firstresult=True`) — sister hookimpl: W8d

```python
def project_rag_resolve_external_runtime_binary(
    capability: str,
) -> Path | None: ...
```

Locates the binary that satisfies `capability` on this host (e.g. `UnrealEditor-Cmd.exe`
for `capability='ue_editor'`). Returns absolute path or `None` to abstain. Used by Mode B
subprocess setup; host treats the returned path as opaque.

**`project_rag_dispatch_external_runtime`** (`firstresult=True`) — sister hookimpl: W8d

```python
def project_rag_dispatch_external_runtime(
    capability: str,
    spec: AddonRuntimeDispatchSpec,
) -> AddonRuntimeDispatchResult | None: ...
```

Invokes the resolved binary with addon-specified argv/env/timeout. The host owns
subprocess lifecycle (bounded_popen, PID files, watchdogs) via `core.long_lived_subprocess`;
the addon owns argv-builder, env-builder, sentinel substitution, and runtime-specific
log-marker conventions. Return `None` to abstain.

**`project_rag_register_query_routing`** (parallel-call) — sister hookimpl: W8f

```python
def project_rag_register_query_routing() -> list[AddonQueryRoutingSpec]: ...
```

Registers domain-specific query patterns and optional decomposer references. Replaces
the W6 / Wave-2b P3.6 `ue_patterns` + query_decomposition port-out. Pluggy parallel-call
semantics — host collects the full list across all registered addons.

## Doctor probe

**Phase name:** `capability-satisfaction`

**Insertion point:** after `Step 18: Addon discovery — UE producer registration`.

The probe enumerates the union of `producer.requires_capabilities` across all registered
producers, calls `pm.hook.project_rag_provide_capability(capability=..., ctx=...)` for
each, and surfaces a structured table:

| Column | Description |
|---|---|
| `capability` | The capability string declared by one or more producers |
| `claimed_by` | Addon package name whose hookimpl returned non-None, or `(none)` |
| `satisfied` | `True` / `False` / `—` (when unclaimed) |
| `reason` | `AddonCapabilityResult.reason` when `satisfied=False`; empty otherwise |

**Verdict matrix:**

| Condition | Verdict |
|---|---|
| No producers declare any `requires_capabilities` | `INFO` (host-only or zero-capability-producers install) |
| All declared capabilities are satisfied | `OK` |
| One or more capabilities are `capability_unsatisfied` | `DEGRADED` (lists affected capabilities + reasons) |
| One or more capabilities are `capability_unclaimed` | `FAIL` (likely missing addon; hint names the string) |

## Negative spec

- Does NOT cover `register_schema_tables` or `register_schema_edge_types` — those are
  documented in the Phase-1 addon-extensible-schema workstream wiki.
- Does NOT enumerate known capability strings globally — the host has no registry; only
  the claiming addon's hookimpl knows whether a string is valid.
- Does NOT cover `AddonRuntimeDispatchSpec` façade — that lands in W8d alongside
  consumer wiring.

## Related docs

- [addon-protocol.md](addon-protocol.md) — full v6 hookspec table + façade types
- [addon-receiver-scaffold.md](addon-receiver-scaffold.md) — Wave-2a doctrine, project-type gate
- [thin-wrapper-graceful-fail.md](../../../../project-rag/docs/wiki/thin-wrapper-graceful-fail.md) — graceful-fail contract for addon seam probe sites
