---
title: Cross-Plugin MCP Whoami Contract
created: 2026-05-19
status: active
authoring_plan: [docs/plans/2026-05-19-cross-plugin-whoami-contract.md, docs/plans/2026-05-19-whoami-substrate-migration.md]  # Review: Reviewer C C-F6 — list form; wiki covers both phase-1 contract and phase-2 migration
---

<!-- Spec backlink: docs/plans/2026-05-19-cross-plugin-whoami-contract.md §5 Task 1 -->

# Cross-Plugin MCP Whoami Contract

This wiki defines the shared introspection envelope that every MCP-bearing plugin in the `~/.claude` ecosystem must implement. Coordinator-claude owns the envelope schema; each plugin implements a conformant MCP tool in its own repo and test suite.

The contract answers the question every coordinator-level tool or scanner has when it queries a plugin: *"What is this plugin bound to, and is it healthy?"* Previously that question was answered only by project-rag's `project_whoami` tool, whose response shape was project-rag-internal doctrine. As holodeck-control joined the ecosystem as a second MCP-bearing plugin, the need for a shared cross-plugin contract became concrete — the wrong-shape arrangement (holodeck-control piggybacking on project-rag's tool for cross-plugin introspection) was itself the evidence the abstraction was overdue. PM authorized hoisting the contract to coordinator-claude on 2026-05-19 (DoE memo `tasks/memos/2026-05-19-machine-local-doe-reply.md` § 5b).

Each plugin exposes its own named MCP tool (e.g. `project_whoami` for project-rag, `holodeck_whoami` for holodeck-control). The coordinator validates the envelope shape; plugin-specific extension fields live in the per-plugin `extras` slot, validated by the plugin itself.

---

## Envelope schema

The following fields constitute the shared cross-plugin whoami envelope. Every conformant plugin response must include all required fields. The machine-readable schema is at `coordinator_whoami/schemas/whoami-envelope.v1.json`.

### Required common fields

| Field | Type | Description |
|---|---|---|
| `contract_version` | `int` | Cross-plugin contract version. v1 for all initial implementations. This field versions the shared contract, not any plugin's internal envelope — see **Namespace disambiguation** below. |
| `plugin_name` | `str` | Canonical plugin identifier. Use kebab-case: `"project-rag"`, `"holodeck-control"`. Must be stable across daemon restarts. |
| `plugin_version` | `str \| null` | Plugin's own version string (semver or equivalent). `null` is permitted for plugins without a versioning discipline yet — treat `null` as "not declared", not as "broken". |
| `binding` | object | Binding-state shape. See **`binding` object** below. |
| `status` | object | Health-state shape. See **`status` object** below. |
| `extras` | object | Per-plugin extension slot. See **`extras` slot** below. |

### `binding` object

```
binding: {
  kind:   "bound" | "unbound" | "degraded",
  target: str | null
}
```

| Field | Description |
|---|---|
| `kind` | `"bound"` — plugin has successfully resolved its primary resource (project root, `.ueproject` path, etc.) and is ready to serve queries. `"unbound"` — no resource resolved (setup not run, or resource not found). `"degraded"` — resource partially resolved or some dependency missing; tool calls may succeed with reduced capability. |
| `target` | Plugin-specific identifier for what the plugin is bound to. For project-rag: the resolved project root path. For holodeck-control: the `.ueproject` file path. `null` when `kind` is `"unbound"` — see **Error semantics** below. |

### `status` object

```
status: {
  state:  "healthy" | "degraded" | "error",
  since:  str | null,
  reason: str | null
}
```

| Field | Description |
|---|---|
| `state` | `"healthy"` — all probes pass, tool calls expected to succeed. `"degraded"` — some probes failing; partial availability. `"error"` — a critical dependency is absent or a probe raised an unrecoverable exception. |
| `since` | ISO 8601 timestamp for when the current state was entered, if known. `null` when not tracked. Format: `"2026-05-19T17:30:00Z"`. |
| `reason` | Human-readable explanation when `state` is `"degraded"` or `"error"`. `null` when `state` is `"healthy"`. Actionable where possible: "embed sidecar not started", ".ueproject file not found at X:/path". |

### `extras` slot

```
extras: {
  "<plugin_id>": { ... },   # plugin's own extension fields
  ...
}
```

`extras` is a dict keyed by plugin identifier (snake_case: `"project_rag"`, `"holodeck_control"`). Each plugin writes into its own key. Coordinator validates:

1. `extras` is a dict (not a list or scalar)
2. All keys match `^[a-z_][a-z0-9_]*$` — lowercase snake_case identifiers only; non-conformant keys are rejected at parse time

Coordinator does NOT validate the contents of any `extras[<plugin>]` sub-object — those are per-plugin concerns, validated by the plugin against its own schema. The canonical snake_case identifier format means any consumer language (Python, C++, JS, Rust) can map keys to native field names without escaping.

### Namespace disambiguation

Three version surfaces exist in this ecosystem. They are orthogonal and must never be collapsed:

1. **`contract_version`** (this field) — versions the shared cross-plugin whoami contract. Starts at 1. Increments when the common envelope shape changes (field add/remove/retype on the required common fields).

2. **Per-plugin envelope versions** (e.g. project-rag's `ENVELOPE_VERSION`, currently at 6) — version each plugin's internal tool-response envelope. These are per-plugin concerns; they surface inside the plugin's `extras` slot if surfaced at all (e.g. `extras["project_rag"]["envelope_version"]`). They do NOT appear at the top level of the whoami response.

3. **`ADDON_PROTOCOL_VERSION`** — versions the hookspec contract between project-rag host and its addons. A third orthogonal counter. See [addon-protocol.md](addon-protocol.md).

Three version surfaces with distinct names are correct. Collapsing any two is a tripwire — the failure mode is silent version-check confusion across plugin boundaries.

---

## Error semantics

### `binding.kind` values

**`"bound"`** — Plugin has resolved its primary resource. `binding.target` is non-null and identifies exactly what the plugin is bound to. Tool calls are expected to succeed.

**`"unbound"`** — Plugin has no resolved resource. `binding.target` is `null`. This is a by-design state, not a failure: it means setup has not been run, or the resource was not found at the configured location. A coordinator-level scanner reading a `null` target must treat it as "consumer not yet bound", not as a mismatch. Mismatch comparisons across plugins are only valid when both `binding.target` values are non-null.

> **Null-source rule** (inherited from [plugin-identity-and-health-sentinels.md](plugin-identity-and-health-sentinels.md) § "Scanner-design wrinkle: `source: null` is unbound, not mismatch"): `binding.target: null` inherits the same semantic as `source: null` in project-rag's `project_whoami`. Null means unbound — the plugin hasn't been configured for a specific resource — not that the configuration is wrong.

**`"degraded"`** — Plugin resolved its resource but with reduced capability. `binding.target` is populated (the resource was found). `status.state` will typically also be `"degraded"` and `status.reason` will explain the degradation.

### `status.state` values and partial-availability signalling

**`"healthy"`** — All health probes pass. `status.reason` is `null`. Full tool availability.

**`"degraded"`** — Some but not all probes pass. Plugin is available but operating below capacity. `status.reason` describes what's missing. Common causes: optional sidecar not running, index partially built, one of multiple registered addons unreachable. Tool calls may partially succeed — consumers should read `status.reason` to understand which capabilities are affected.

**`"error"`** — Critical failure. Plugin cannot serve meaningful results. `status.reason` is required and must be actionable. `status.since` is set if the failure onset time is known.

### Live-not-receipt invariant

The whoami response is **always live** — synthesized from authoritative runtime state at query time. It is never cached to disk, never read from a file, never returned from a stale snapshot. A plugin that returns a cached or persisted whoami response is non-conformant.

This is the core decay-discipline rule from [plugin-identity-and-health-sentinels.md](plugin-identity-and-health-sentinels.md): identity has a live source; persisting it turns "stale = signal" into "stale = active lie". The contract enforces live response at the spec level — implementations must not add any caching layer to the whoami tool.

---

## Validation discipline

The coordinator validates the following when consuming a whoami response. Validation failures are surfaced as parse errors, not silently ignored.

1. **`contract_version` present** — field must exist and be an integer. Absent field = non-conformant response. Mismatch on value = version negotiation required (out of scope for v1; surface to EM).

2. **`plugin_name` present** — field must exist and be a non-empty string.

3. **`binding` object conforms** — `binding.kind` must be one of `{"bound", "unbound", "degraded"}`. Any other value is rejected. `binding.target` must be a string or null.

4. **`status` object conforms** — `status.state` must be one of `{"healthy", "degraded", "error"}`. Any other value is rejected. `status.since` and `status.reason` must each be a string or null.

5. **`extras` is a dict** — not a list, not a string, not null. An absent `extras` key is also non-conformant; plugins must include it (at minimum as `{}`).

6. **`extras` keys match `^[a-z_][a-z0-9_]*$`** — keys failing this regex are rejected at parse time, before any per-plugin extension processing. This constraint is baked into v1 specifically to avoid a v2 breaking change after consumers exist.

The coordinator does NOT validate the contents of `extras[<plugin_id>]` sub-objects. Per-plugin contents are the plugin's own concern, validated by the plugin against its own schema (e.g. via `jsonschema` in the plugin's own test suite).

---

## How addon-extension surfaces fit

Each plugin's own extension chain writes into its dedicated key inside `extras`. Project-rag's pluggy hookspec chain (`project_rag_register_whoami_extras`, planned for v9 work) writes into `extras["project_rag"]`. Holodeck-control's eventual extension surface (none today) would write into `extras["holodeck_control"]`.

The coordinator's role at the `extras` boundary:

- Validates that `extras` is a dict with conformant keys (see **Validation discipline** above)
- Does not inspect or validate the contents of any `extras[<plugin>]` sub-object
- Does not own or define what goes inside any plugin's extras slot

This mirrors the pattern from [chunk-metadata-schema-seam.md](chunk-metadata-schema-seam.md) (the γ-prime seam): the outer authority owns the validation algorithm and the closed-set namespace; inner contributors own vocabulary within their slot. Host unions the contributed vocabularies and runs the algorithm once; contributors supply declarative specs, not callable validators.

**Analogy caveat:** The analogy holds at the *pattern* layer — outer authority owns the algorithm and closed-set namespace; inner contributors own vocabulary within their slot — but NOT at the *runtime* layer. The chunk-metadata seam is enforced by host runtime code at chunk-emit time: the pluggy hookspec runs, host collects specs, host validates each chunk at write time. This whoami contract is enforced by each plugin's own conformance tests against the shared JSON Schema at `coordinator_whoami/schemas/whoami-envelope.v1.json`. Coordinator-claude ships no runtime validator; it owns the spec, not a process. The pattern is the same; the enforcement mechanism differs: host-runtime-at-emit vs. plugin-test-at-ship.

---

## Worked example — project-rag's conformant response (TEMPLATE)

The following illustrates what a conformant `project_whoami` response looks like after project-rag implements v9 envelope work conforming to this contract. Field names are exact; values are illustrative.

```json
{
  "contract_version": 1,
  "plugin_name": "project-rag",
  "plugin_version": "0.6.0",
  "binding": {
    "kind": "bound",
    "target": "X:/my-unreal-project"
  },
  "status": {
    "state": "healthy",
    "since": "2026-05-19T14:22:00Z",
    "reason": null
  },
  "extras": {
    "project_rag": {
      "envelope_version": 6,
      "source": "my-unreal-project",
      "project_kind": "unreal",
      "engine_version": "5.7",
      "registered_sources": [
        {"name": "my-unreal-project", "kind": "unreal", "last_indexed": "2026-05-19T13:00:00Z"}
      ],
      "addon_sources_available": [
        {"band_name": "unreal_5.7_runtime", "kind": "engine", "engine_version": "5.7", "contributor": "project-rag-ue-addon"}
      ]
    }
  }
}
```

Note: `envelope_version` (project-rag's internal per-plugin counter) lives inside `extras["project_rag"]`, not at the top level. The top-level `contract_version: 1` is the cross-plugin contract version. These are orthogonal.

When project-rag is unbound (no project root resolved), the conformant response is:

```json
{
  "contract_version": 1,
  "plugin_name": "project-rag",
  "plugin_version": "0.6.0",
  "binding": {
    "kind": "unbound",
    "target": null
  },
  "status": {
    "state": "degraded",
    "since": null,
    "reason": "No project root registered. Run /project-rag:setup."
  },
  "extras": {
    "project_rag": {
      "envelope_version": 6,
      "source": null,
      "project_kind": "unknown",
      "engine_version": null,
      "registered_sources": [],
      "addon_sources_available": []
    }
  }
}
```

---

## Worked example — holodeck-control's planned conformant response (TEMPLATE)

The following illustrates what a conformant `holodeck_whoami` response looks like when holodeck-control implements its own coordinator-conformant whoami tool. No extension fields are defined for holodeck-control today; `extras["holodeck_control"]` is a placeholder.

```json
{
  "contract_version": 1,
  "plugin_name": "holodeck-control",
  "plugin_version": null,
  "binding": {
    "kind": "bound",
    "target": "X:/my-unreal-project/MyProject.uproject"
  },
  "status": {
    "state": "healthy",
    "since": "2026-05-19T14:25:00Z",
    "reason": null
  },
  "extras": {
    "holodeck_control": {}
  }
}
```

When holodeck-control cannot locate a `.ueproject` file:

```json
{
  "contract_version": 1,
  "plugin_name": "holodeck-control",
  "plugin_version": null,
  "binding": {
    "kind": "unbound",
    "target": null
  },
  "status": {
    "state": "degraded",
    "since": null,
    "reason": "No .uproject file found at configured project root."
  },
  "extras": {
    "holodeck_control": {}
  }
}
```

---

## Cross-references

- [plugin-identity-and-health-sentinels.md](plugin-identity-and-health-sentinels.md) — decay-discipline doctrine (receipt vs. live), the null-source rule (§ "Scanner-design wrinkle"), and the writer-boundary rule. The contract's `binding.target: null` semantic is directly inherited from that wiki's null-source rule.

- [doe-altitude-and-shared-infra.md](doe-altitude-and-shared-infra.md) — the DoE-altitude consult-chain methodology that produced the ownership decision (coordinator-claude owns the schema). The 2026-05-19 cross-plugin whoami consult is instance 2 of that methodology.

- [ceremony-calibration.md](ceremony-calibration.md) — the "wait for instance #3 before extracting a pattern into a skill" rule, including the worked example (Task 4 of the authoring plan) clarifying when the rule does NOT apply: two instances plus a misshapen arrangement provide equivalent information to three instances.

- [chunk-metadata-schema-seam.md](chunk-metadata-schema-seam.md) — the canonical γ-prime seam this contract's `extras` slot mirrors at the pattern layer: outer authority owns the algorithm and closed-set namespace; inner contributors own vocabulary within their slot. See **Analogy caveat** above for where the analogy breaks down at the runtime layer.

- [host-vs-addons.md](host-vs-addons.md) — ownership-boundary doctrine: project-rag (host) is content-agnostic; domain-specific extensions live in addons. The `extras` slot enforces the same boundary at the whoami layer.

- [host-addon-separation-of-concerns.md](host-addon-separation-of-concerns.md) — umbrella design principle for protocol-surface shape decisions; five tactics for additive evolution without coupling.

- [addon-protocol.md](addon-protocol.md) — the hookspec versioning surface (`ADDON_PROTOCOL_VERSION`, currently at 14) that governs the project-rag host-to-addon contract. This is the third orthogonal version counter distinct from `contract_version` and from per-plugin `envelope_version` — see **Namespace disambiguation** above.

- [project-rag-tool-envelope.md](project-rag-tool-envelope.md) — the existing project-rag tool response envelope (`ENVELOPE_VERSION = 6`) that this contract generalizes into a shared cross-plugin shape. Project-rag's per-plugin envelope fields map into `extras["project_rag"]`; the outer contract fields are new shared ground.

- `coordinator_whoami/schemas/whoami-envelope.v1.json` — JSON Schema draft 2020-12 encoding of this wiki's §Envelope schema. Each plugin's conformance tests validate against this schema in their own repo.

---

## Provenance

The contract emerged from a DoE-altitude consult on 2026-05-19:

1. **DoE memo** `tasks/memos/2026-05-19-machine-local-doe-reply.md` § 5b — PM authorized hoisting the whoami contract from project-rag-internal doctrine to coordinator-claude ownership, citing holodeck-control as a second MCP-bearing plugin that needed a shared introspection surface.

2. **Spinoff** `archive/handoffs/2026-05-19_175021_coordinator-whoami-contract.md` — workstream handoff carrying the implementation mandate (archived post-pickup).

3. **Plan** `docs/plans/2026-05-19-cross-plugin-whoami-contract.md` — full architecture plan including the spec-first delivery decision (markdown + JSON Schema, no Python module in coordinator-claude), the namespace disambiguation rationale, and the Zolí review integration that landed `contract_version` naming and the `^[a-z_][a-z0-9_]*$` extras-key constraint.

**Authorship.** The contract shape was produced by the 2026-05-19 authoring session (coordinator EM + PM Dónal O'Duffy). Zolí (cross-team/cross-repo reviewer, Opus-altitude) ratified the spec-first delivery shape, the namespace disentanglement, and the extras-key regex in the same session.

---

## Decision shape (for the next reader)

**Coordinator owns the envelope shape; each plugin owns its conformant implementation and its own addon-extension slot.**

The boundary is crisp:

- Coordinator-claude defines the required common fields, the closed enum sets for `binding.kind` and `status.state`, the extras-key format constraint, and the JSON Schema. This is the shared contract that all MCP-bearing plugins in the ecosystem must satisfy.

- Each plugin (project-rag, holodeck-control, any future MCP plugin) implements its own conformant MCP tool in its own repo. The plugin's test suite validates its tool's output against `coordinator_whoami/schemas/whoami-envelope.v1.json`. The plugin owns whatever it puts inside `extras[<its_plugin_id>]`.

- Coordinator does not host a runtime validator, a test runner for cross-repo plugin code, or a Python reference implementation. It owns the spec; conformance is each plugin's responsibility.

Don't re-litigate coordinator-vs-host ownership without PM authorization (PM made this call on 2026-05-19). Surface any disagreement as a re-decision request, not a silent revert.

---

## Reference implementation

<!-- Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § Task 9 (R1 subpackage layout) -->

The reference implementation lives at `plugins/coordinator/whoami/coordinator_whoami/` and ships outward via `setup/publish.sh` to `X:/coordinator-claude` (OSS publish target).

### Two-layer package structure (R1 subpackage layout)

The package is split into generic cross-plugin surfaces at the package root, and per-plugin implementations as subpackages.

**Generic, cross-plugin reusable surfaces (package root):**

- `coordinator_whoami.contract.validate_envelope(envelope: dict) -> None` — raises `jsonschema.ValidationError` on any non-conforming envelope. Loads the package-vendored schema via `importlib.resources`. This is the shared validation primitive; all plugin test suites call it.

- `coordinator_whoami.envelope_base.build_envelope(*, plugin_name, extras_key, plugin_version, binding, status, plugin_extras, addon_extras=None) -> dict` — plugin-agnostic envelope assembler. The caller supplies both `plugin_name` (kebab-case, e.g. `"project-rag"`) and `extras_key` (snake_case, e.g. `"project_rag"`) explicitly. The primitive embeds no naming-policy logic — that separation is intentional; naming conventions are the caller's responsibility.

**Per-plugin implementations (subpackages):**

- `coordinator_whoami.project_rag.envelope.compose_envelope() -> dict` — project-rag's own projection. Uses `build_envelope` with `plugin_name="project-rag"`, `extras_key="project_rag"`.

- `coordinator_whoami.project_rag.cli` — host introspection probe; provides `compose()` and `WHOAMI_SCHEMA_VERSION`. The CLI entry point is `coordinator_whoami.project_rag.__main__`; `python -m coordinator_whoami.project_rag` runs that module. <!-- Review: Reviewer C C-F4 — corrected misidentification; cli.py is the probe module, __main__.py is the entry point -->

- `coordinator_whoami.project_rag.addons` — addon contributor discovery and dispatch; collects addon-contributed `extras["project_rag"]` fields via the pluggy hookspec chain.

### Subpackage layout rationale

Holodeck-control's in-flight `agentic-doctor` plan (`X:/claude-unreal-holodeck/docs/plans/2026-05-19-holodeck-control-agentic-doctor.md`) is explicitly held pending this migration — the second adopter is named and blocked on R1 landing. The subpackage layout was established in this phase (R1, PM-authorized 2026-05-19) rather than deferred to a refactor. When holodeck-control adopts the contract, its implementation lives at `coordinator_whoami.holodeck_control/` (sibling subpackage to `coordinator_whoami.project_rag/`) and reuses the generic surfaces (`contract`, `envelope_base`) without any changes to the package root.

### Schema location (R1)

The contract envelope schema is vendored inside the package at `coordinator_whoami/schemas/whoami-envelope.v1.json` (package-data, NOT at the old `coordinator/schemas/whoami-envelope.v1.json` path — that location was retired in phase 2). The package loads the schema at runtime via:

```python
importlib.resources.files("coordinator_whoami.schemas").joinpath("whoami-envelope.v1.json")
```

Phase-1 references in this wiki were repointed in the Task 9 wiki amendment (2026-05-19).

### Adding a new adopter

When holodeck-control or another plugin adopts the contract, the new subpackage lives at `coordinator_whoami.<plugin_name>/` — a sibling of `coordinator_whoami.project_rag/`. The subpackage layout is already in place; no package-root refactor is needed. The new plugin's subpackage authors its own `cli.py`, `envelope.py`, and `addons.py`, reusing `coordinator_whoami.contract` and `coordinator_whoami.envelope_base` from the parent package.

### R2 single canonical CLI shape

The CLI emits envelope-shaped JSON unconditionally — no dual shape, no `--contract` flag. Persistence (`~/.claude/project-rag/install-profile.json` under the `whoami_profile` key) stores the full envelope. Downstream consumers (`/project-rag:doctor`, install scripts) access fields via the new envelope paths.

**Migration plan:** `docs/plans/2026-05-19-whoami-substrate-migration.md`
