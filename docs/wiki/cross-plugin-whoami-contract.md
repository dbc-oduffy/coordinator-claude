---
title: Cross-Plugin MCP Whoami Contract
created: 2026-05-19
status: active
authoring_plan: [docs/plans/2026-05-19-cross-plugin-whoami-contract.md, docs/plans/2026-05-19-whoami-substrate-migration.md]  # Review: Reviewer C C-F6 — list form; wiki covers both phase-1 contract and phase-2 migration
---

<!-- Spec backlink: docs/plans/2026-05-19-cross-plugin-whoami-contract.md §5 Task 1 -->

# Cross-Plugin MCP Whoami Contract

> This wiki is the **plugin-author-facing half** of a doctrine-vs-operator-guide pair. It defines the contract — schema, validation, reference impl, namespace disambiguation — that MCP-bearing plugin authors implement. For **operator-facing health verification** using the contract surface (probes, citation contracts, cold-start bootstrap), see the companion wiki: [`coordinator-doctor.md`](coordinator-doctor.md).

This wiki defines the shared introspection envelope that every **adopter** in the `~/.claude` ecosystem must implement. Two adopter classes exist:

- **MCP-plugin adopters** — plugins that expose a live MCP tool (e.g. `project_whoami` for project-rag, `holodeck_whoami` for holodeck-control). Each plugin implements a conformant MCP tool in its own repo and test suite.
- **Coordinator-session adopter** (`plugin_name: "coordinator-session"`, `extras_key: "coordinator_session"`) — a non-MCP adopter computed live from git and filesystem at query time. It is the canonical orientation-health surface for the coordinator session itself. It is always `source_kind: "live"` (computed at query time, never cached or persisted). It ships inside the `coordinator_whoami` package as a sibling subpackage (`coordinator_whoami.session`).

**Orientation's canonical health surface is the session adopter.** MCP-plugin whoamis are optional ribs — they answer "is this plugin's binding healthy?" — but they do not constitute the spine of session orientation. `/workstream-start` routes through `coordinator_whoami.session`, not through any plugin adopter.

Coordinator-claude owns the envelope schema; each adopter (MCP-plugin or session) implements a conformant surface.

The contract answers the question every coordinator-level tool or scanner has when it queries a plugin: *"What is this plugin bound to, and is it healthy?"* Previously that question was answered only by project-rag's `project_whoami` tool, whose response shape was project-rag-internal doctrine. As holodeck-control joined the ecosystem as a second MCP-bearing plugin, the need for a shared cross-plugin contract became concrete — the wrong-shape arrangement (holodeck-control piggybacking on project-rag's tool for cross-plugin introspection) was itself the evidence the abstraction was overdue. PM authorized hoisting the contract to coordinator-claude on 2026-05-19 (DoE memo `~/.claude/cross-repo/archive/2026-05-19-machine-local-doe-reply.md` § 5b — grandfathered pre-cutoff memo).

Each plugin exposes its own named MCP tool (e.g. `project_whoami` for project-rag, `holodeck_whoami` for holodeck-control). The coordinator validates the envelope shape; plugin-specific extension fields live in the per-plugin `extras` slot, validated by the plugin itself.

---

## Envelope schema

The following fields constitute the shared cross-plugin whoami envelope. Every conformant plugin response must include all required fields. The machine-readable schema is at `coordinator_whoami/schemas/whoami-envelope.v1.json`.

### Required common fields

| Field | Type | Description |
|---|---|---|
| `contract_version` | `int` | Cross-plugin contract version. v1 for all initial implementations. This field versions the shared contract, not any plugin's internal envelope — see **Namespace disambiguation** below. |
| `plugin_name` | `str` | Canonical adopter identifier. Use kebab-case: `"project-rag"`, `"holodeck-control"`, `"coordinator-session"`. Free string — the schema does not enumerate valid values; adopter identity is established by convention. Must be stable across daemon restarts (or, for non-MCP adopters, across package upgrades). |
| `plugin_version` | `str \| null` | Plugin's own version string (semver or equivalent). `null` is permitted for plugins without a versioning discipline yet — treat `null` as "not declared", not as "broken". |
| `source_kind` | `"live" \| "offline"` (optional, default `"live"`) | Discriminator for whether this envelope was synthesized from live runtime state (`"live"`) or reconstructed from on-disk diagnostic artifacts (`"offline"`). See **§ Offline diagnostic surface** below. Absent value MUST be treated as `"live"`. Consumers classifying binding health MUST reject `"offline"` envelopes for that purpose. |
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

`extras` is a dict keyed by adopter identifier (snake_case: `"project_rag"`, `"holodeck_control"`, `"coordinator_session"`). Each adopter writes into its own key. Coordinator validates:

1. `extras` is a dict (not a list or scalar)
2. All keys match `^[a-z_][a-z0-9_]*$` — lowercase snake_case identifiers only; non-conformant keys are rejected at parse time

Coordinator does NOT validate the contents of any `extras[<plugin>]` sub-object — those are per-plugin concerns, validated by the plugin against its own schema. The canonical snake_case identifier format means any consumer language (Python, C++, JS, Rust) can map keys to native field names without escaping.

### Addon collision semantics

Two collision cases are handled at the `addons.py` envelope-build layer:

- **Addon namespace collides with plugin canonical key** (e.g. an addon tries to write `extras["project_rag"]`): log warning + skip. Silent overwrite is not permitted — the plugin's canonical key is reserved and cannot be shadowed by an addon.
- **Addon-vs-addon collision** (two addons claim the same namespace): log warning + first-wins. The ordering is deterministic (hookspec collection order); the warning surfaces the conflict.

Both are logged but non-fatal. The contract does not hard-fail on collision — degraded output with a logged warning is preferable to a broken whoami response.

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

### Offline diagnostic surface (`source_kind: "offline"`)

There are situations where an operator or downstream doctor wants whoami-shaped information about a plugin, but the plugin's daemon cannot serve a live `*_whoami` MCP call — daemon is down, port is bound, install is mid-repair, etc. For these cases plugins MAY author an **offline diagnostic surface**: a per-plugin CLI or file-read path that reconstructs a contract-conformant envelope from on-disk artifacts (e.g., `~/.claude/<plugin>/install-profile.json`, sentinel files, recorded config). Examples:

- `python -m project_rag.diagnostic_whoami --offline` — reads `~/.claude/project-rag/install-profile.json`, reformats into an envelope.
- `holodeck-control --offline-whoami` — assembles binding/status from on-disk install state.

Plugins authoring such a surface MUST set `source_kind: "offline"` on the resulting envelope. Plugins serving the canonical live MCP path MUST set `source_kind: "live"` (or omit — default is `"live"`).

**The discriminator is normative.** Consumers branch on it:

- **Binding-health classification.** Consumers (especially doctors) classifying "is this plugin's binding healthy right now?" MUST reject envelopes with `source_kind: "offline"` — offline envelopes are by definition stale-by-design, not live evidence. Refer to the doctor's P-6-equivalent invocation that calls live MCP; if it fails, the binding is genuinely down — do not fall back to offline.
- **Config-audit consumption.** Consumers performing config audits ("which addons declared themselves at last install?", "what was the binding target as of the last successful daemon run?") MAY accept either `"live"` or `"offline"` envelopes. The offline envelope is the right primitive here; config-audit doesn't need live evidence.
- **Operator-facing prose.** Tools surfacing whoami results to operators SHOULD label offline-source envelopes (e.g., "(from cached install-profile, daemon offline)") so the operator knows the data is reconstructed.

**The offline tier exists to be honest about staleness, not to substitute for live.** The discriminator turns "stale = active lie" into "stale = explicitly labeled stale." A plugin that serves a stale envelope as `source_kind: "live"` is non-conformant — that's the failure mode this tier exists to close.

### Live-not-receipt invariant

**Producer side.** The whoami response from a plugin's canonical MCP tool (`source_kind: "live"`) is always live — synthesized from authoritative runtime state at query time. It is never cached to disk, never read from a file, never returned from a stale snapshot. A plugin that returns a cached or persisted response under `source_kind: "live"` is non-conformant. (Plugins that author an offline diagnostic surface label those envelopes `source_kind: "offline"` per §Offline diagnostic surface above; that is a separate, honest surface — not a violation of this invariant.)

**Consumer side (synthesis-time consumers).** Consumers — especially downstream doctor agents that synthesize verdicts from whoami output — MUST call the live MCP `*_whoami` tool when classifying binding health. They MUST NOT read persisted whoami snapshots from disk (e.g., `~/.claude/<plugin>/install-profile.json`'s `whoami_profile` key) as binding-health evidence. A consumer that consults a persisted snapshot for binding-health purposes turns "stale = active lie" back on; the live-call requirement closes that hole on the consumer side. Snapshots persisted by `persist()` are operator-facing receipts and config-audit substrate, NOT live evidence.

The two halves of the invariant compose: producers serve live envelopes (or honestly-labeled offline envelopes), and consumers requiring liveness call live MCP rather than reading any persisted artifact.

This is the core decay-discipline rule from [plugin-identity-and-health-sentinels.md](plugin-identity-and-health-sentinels.md): identity has a live source; persisting it turns "stale = signal" into "stale = active lie". The contract enforces this at the spec level for both producers and consumers — implementations must not add any caching layer to the whoami tool, and consumers reading persisted snapshots for binding-health are out-of-contract. Cross-reference: the same rule is restated in operator-facing form in [`coordinator-doctor.md`](coordinator-doctor.md) §5 (binding-health probes MUST cite P-6 live, not P-7 config-presence).

### Non-sensitivity guarantee

**The envelope is contract-bound to carry no sensitive material.** Consumers (CI logs, doctor recordings, terminal echoes, install-script diagnostic prints) MAY record the full envelope verbatim without per-field redaction. The guarantee rests on three structural facts and one closed editorial rule:

1. **Closed top-level namespace.** The schema sets `additionalProperties: false` on the root object. Only `contract_version`, `plugin_name`, `plugin_version`, `source_kind`, `binding`, `status`, and `extras` may appear. Adding a new top-level field requires a schema bump and a contract-version increment — there is no silent surface for a sensitive field to land.
2. **Closed enums on `binding.kind` / `status.state`.** Both are restricted to small enumerated string sets. They cannot carry tokens, fingerprints, or operator-identifying material by construction.
3. **`binding.target` and `status.reason` are operator-facing diagnostic strings.** `binding.target` is a path-like resource identifier (project root, `.uproject` path) — the same identifier already echoed by `pwd`, IDE title bars, and `/workstream-start`. `status.reason` is required to be actionable human-readable prose; it MUST NOT carry secrets, auth tokens, machine identifiers, or environment-variable values. Plugin authors writing free-form reason strings are bound by this rule.
4. **Identity material lives in a separate, deliberately non-conformant surface.** Host identity (hostname, machine_id), GPU inventory, disk capacity, and similar machine-state fields are surfaced by `coordinator_whoami.machine` — see [`machine.py`](../../whoami/coordinator_whoami/machine.py) module docstring, which explicitly disclaims envelope conformance. The 2026-05-27 host-capacity work made this split structural, not stylistic: machine identity is reachable as a *separate* JSON probe (`python -m coordinator_whoami.machine`), never via the envelope. Plugins MUST NOT smuggle identity-class fields into `extras[<plugin>]` to work around this — extras vocabularies are reviewed for the same guarantee.

**Implication for downstream consumers.** A `WHOAMI_JSON=<raw envelope>` print (or equivalent recording surface) in CI, installer, or doctor output is contract-conformant and forward-safe. Security audits flagging the envelope for hypothetical future sensitivity should close as not-applicable: a future schema change adding sensitive material would itself violate this guarantee and would not land. Adopters relying on this in tests (e.g. `project-rag`'s `TestWhoamiPreflightStateA::test_cmd_preflight_whoami_envelope_recorded`) are correctly relying on a contractual non-sensitivity invariant.

**Implication for envelope evolution.** Any proposed schema change that would add a field carrying auth tokens, machine fingerprints, environment variable values, or secrets MUST be rejected at contract-review. If a downstream need for identity-class material arises, the resolution is to extend `coordinator_whoami.machine` (the diagnostic surface) or author a sibling probe — never to broaden the envelope. This guarantee is load-bearing and not overridable without an explicit PM-authorized contract-version-bumping decision.

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

### JSON Schema `examples:` keyword is annotation-only

The `examples:` keyword in JSON Schema draft 2020-12 is **annotation-only** — `jsonschema` >=4.18 does NOT auto-validate examples against the surrounding schema. Plugin test suites that want to verify their example envelopes are conformant MUST add an explicit step: load each example and run `Draft202012Validator.validate()` against the schema body, recording pass/fail per example. Do not rely on `examples:` appearing in the schema file as evidence that the examples were validated.

---

## Tripwires and failure recovery

**DIY-on-whoami is the failure mode this contract exists to prevent.** When an EM (or workstream-start) encounters `ModuleNotFoundError: No module named 'coordinator_whoami'` or an unbound envelope, the answer is:

- **Missing install:** run `/coordinator:setup` (installs the `coordinator_whoami` package via pip in Phase 3 Step 6).
- **Unbound envelope:** run `/repo-setup` or `/project-rag:setup` to bind the project.

Do NOT reach for grep, `git status`, or hand-rolled binding checks as a substitute. Those produce inconsistent output that diverges from the contract surface over time; the contract surface exists precisely to give one authoritative introspection path.

Registered in `docs/wiki/coordinator-tripwires.md`. Override env var: none (wiring is unconditional).

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

## How operators read this

Operators — as distinct from plugin authors implementing the contract — consume this surface through three entry points:

1. **CLI introspection — two probes, two questions.**
   - `python -m coordinator_whoami.session` is the canonical one-liner for inspecting orientation health (git state, cache freshness, workstream state). This is probe **P-6s** in [`coordinator-doctor.md`](coordinator-doctor.md) — the *orientation*-health probe.
   - `python -m coordinator_whoami.project_rag` is the canonical one-liner for inspecting project-rag's live plugin binding. This is probe **P-6** in [`coordinator-doctor.md`](coordinator-doctor.md) — the *plugin*-binding-health probe.
   - These two probes answer different questions and must not be collapsed. P-6s answers "is this session oriented?"; P-6 answers "is project-rag bound and healthy?".

2. **Downstream plugin doctors.** Plugin doctors (holodeck-control's agentic doctor, project-rag's doctor, project-rag-ue-addon's verification script) probe coordinator substrate by calling the plugin CLI entry point (P-6). When a downstream doctor surfaces a binding-health result, it is sourcing from this contract via P-6 — not from any persisted snapshot.

3. **Probe catalog in `coordinator-doctor.md`.** Probes P-5 (package import — `python -c "import coordinator_whoami"`), P-6s (orientation health — `python -m coordinator_whoami.session`), P-6 (plugin binding health — `python -m coordinator_whoami.project_rag`), and P-7 (config-presence check — whether `~/.claude.json` mcpServers entries exist and are well-formed) are the operator-facing health surface. P-7 is a **configuration-presence probe**, not a binding-health probe — it verifies the config entry is present and parseable; P-6 is the **live plugin-binding-health probe**; P-6s is the **live orientation-health probe**. The distinction matters: a passing P-7 with a failing P-6 means "wired but not bound."

4. **Live-call rule.** Operators and consumers wanting current binding health MUST call live `*_whoami` MCP, NOT read persisted snapshots. This is the Live-not-receipt invariant from **§ Error semantics** above, and it is also the binding-health rule named in [`coordinator-doctor.md`](coordinator-doctor.md) §5. Any file on disk labelled "whoami snapshot" is by definition stale — it was conformant at write time, not now.

### Workstream-start three-branch surfacing spec

The workstream-start Context Load emits exactly one line per session, branching on import state. Session orientation routes through `coordinator_whoami.session` (probe **P-6s**), not through any plugin adopter. The session adopter has binary binding (`bound` / `unbound` only — no `degraded` binding kind); the freshness/reconcile gradient is carried on `status.state` instead.

1. **Import fails:** `whoami: not installed (run /coordinator:setup to install the introspection package)`
2. **Import succeeds, `binding.kind == "unbound"`:** `whoami: unbound (run /repo-setup to onboard this repo as a coordinator workspace)`
3. **Import succeeds, `binding.kind == "bound"`:** `whoami: bound → <binding.target> (<status.state>)` — `status.state` carries the orientation-health gradient (`healthy` / `degraded` / `error`); `status.reason` names what's stale when degraded.

Plugin whoamis (project-rag, holodeck-control, etc.) may appear as optional sub-lines after the session line, but they are not the spine. A session that emits `whoami: bound → (healthy)` is oriented regardless of whether any MCP plugin is currently reachable.

Note: workstream-start does NOT surface bound-but-target-mismatched as a separate state — that is `/repo-setup`'s responsibility. Surfacing mismatch at workstream-start generates false positives for operators in a folder that is not the bound project root.

Auto-repair on import failure is explicitly out of scope. The loud nudge (branch 1) is the correct primitive — surfacing with remediation path, not mutating on the operator's behalf.

### Operator wiring — where the contract enters the pipelines

The cross-plugin whoami contract is wired into operator-facing pipelines at three points. Future doctrine maintainers extending the contract surface (e.g., adding a new adopter subpackage) must extend at least these three or document why not:

1. **`/coordinator:setup` Phase 3 Step 6** — pip installs the `coordinator_whoami` package on every coordinator setup run. Idempotent. → `commands/setup.md`. Default CLI output is compact single-line JSON (no flag needed); --human pretty-prints for human reading. Status vocabulary for this step: `ready` (importable — whether freshly installed or re-used), `would write` (--check-only mode against an absent package), `failed` (non-zero pip exit — reason logged to stderr; chain continues without hard-stopping). These are the three states the coordinator-installer status schema records for the `coordinator_whoami` identifier row.
   **Why-not for the session adopter:** no new install step is needed. The `coordinator_whoami.session` subpackage ships inside the same `coordinator_whoami` package the existing step installs. Adding a separate install step would be redundant.
2. **`/repo-setup` Next-Steps step 4** — branches on the live envelope's `binding.kind` to surface confirmation, mismatch, or remediation per project. → `skills/repo-setup/SKILL.md`.
   **Why-not for the session adopter:** `/repo-setup`'s concern is "is this project registered as a project-rag source" (project-registration). That question is answered by project-rag's binding semantics. The session adopter answers a different question ("am I in a coordinator-onboarded repo / oriented") and does not replace the repo-setup branch. Step 4 stays on project-rag's binding.
3. **`/workstream-start` Context Load** — emits a one-line whoami state per session, loud-when-actionable (no silent skip on missing install). → `skills/workstream-start/SKILL.md`. **Rewired to the session adopter** (`python -m coordinator_whoami.session`, probe P-6s in [`coordinator-doctor.md`](coordinator-doctor.md)). This is the contact point that moves when a new session adopter is added.

The canonical why-not detail for each contact point also lives in [`coordinator-doctor.md`](coordinator-doctor.md) §Probe Catalog (P-6s entry). Cross-reference rather than duplicate if the two surfaces diverge.

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

### Coordination constraint: `core/marker_dir.py` retention at project-rag

The project-rag host MUST retain `core/marker_dir.py` whole-file even after `resolve_user_marker_dir` was extracted into `coordinator_whoami._paths`. The addon imports BOTH `resolve_project_marker_dir` AND `resolve_user_marker_dir` from that module (`seed_project_sentinels.py:73`, `preflight.py:94,372`); the former is NOT migrated. Deleting `core/marker_dir.py` from the project-rag tree breaks both files loudly (hard import, no try/except).

This is a cross-repo coordination obligation, not a coordinator-claude implementation concern — it lives here as a reminder because the migration that necessitated it originated in Claude Central.

---

## Provenance

The contract emerged from a DoE-altitude consult on 2026-05-19:

1. **DoE memo** `~/.claude/cross-repo/archive/2026-05-19-machine-local-doe-reply.md` § 5b (grandfathered pre-cutoff memo) — PM authorized hoisting the whoami contract from project-rag-internal doctrine to coordinator-claude ownership, citing holodeck-control as a second MCP-bearing plugin that needed a shared introspection surface.

2. **Spinoff** `archive/handoffs/2026-05-19_175021_coordinator-whoami-contract.md` — workstream handoff carrying the implementation mandate (archived post-pickup).

3. **Plan** `docs/plans/2026-05-19-cross-plugin-whoami-contract.md` — full architecture plan including the spec-first delivery decision (markdown + JSON Schema, no Python module in coordinator-claude), the namespace disambiguation rationale, and the Director of Engineering review integration that landed `contract_version` naming and the `^[a-z_][a-z0-9_]*$` extras-key constraint.

**Authorship.** The contract shape was produced by the 2026-05-19 authoring session (coordinator EM + PM the PM O'Duffy). The Director of Engineering (cross-team/cross-repo reviewer, Opus-altitude) ratified the spec-first delivery shape, the namespace disentanglement, and the extras-key regex in the same session.

---

## Decision shape (for the next reader)

**Coordinator owns the envelope shape; each adopter owns its conformant implementation and its own extension slot.**

The boundary is crisp:

- Coordinator-claude defines the required common fields, the closed enum sets for `binding.kind` and `status.state`, the extras-key format constraint, and the JSON Schema. This is the shared contract that all adopters — MCP-plugin and non-MCP alike — must satisfy.

- MCP-plugin adopters (project-rag, holodeck-control, any future MCP plugin) each implement a conformant MCP tool in their own repo. The plugin's test suite validates its tool's output against `coordinator_whoami/schemas/whoami-envelope.v1.json`. Each plugin owns whatever it puts inside `extras[<its_plugin_id>]`.

- The coordinator-session adopter (`coordinator_whoami.session`) ships inside this package (coordinator-claude) and is coordinator-owned end-to-end. It is the one adopter where coordinator-claude owns both the spec and the implementation.

- Coordinator does not host a runtime validator, a test runner for cross-repo plugin code, or a Python reference implementation for MCP plugins. It owns the spec; conformance is each plugin's responsibility.

Don't re-litigate coordinator-vs-host ownership without PM authorization (PM made this call on 2026-05-19). Surface any disagreement as a re-decision request, not a silent revert.

---

## Reference implementation

<!-- Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § Task 9 (R1 subpackage layout) -->

The reference implementation lives at `plugins/coordinator/whoami/coordinator_whoami/` in the meta-repo (this Claude Central tree); the OSS distribution at the publish target (`X:/coordinator-claude`) carries the same package at the equivalent plugin path.

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

The package now has two adopter subpackages:

- `coordinator_whoami.project_rag/` — MCP-plugin adopter; live binding health for the project-rag daemon.
- `coordinator_whoami.session/` — coordinator-session adopter; orientation health computed live from git + filesystem; no MCP dependency; always `source_kind: "live"`.

When holodeck-control or another MCP plugin adopts the contract, the new subpackage lives at `coordinator_whoami.<plugin_name>/` — a sibling of `coordinator_whoami.project_rag/`. The subpackage layout is already in place; no package-root refactor is needed. The new plugin's subpackage authors its own `cli.py`, `envelope.py`, and `addons.py`, reusing `coordinator_whoami.contract` and `coordinator_whoami.envelope_base` from the parent package.

Non-MCP adopters follow the session adopter's pattern: `source_kind: "live"` always, no MCP tool, no daemon dependency, `extras_key` in `coordinator_session`-style snake_case.

### R2 single canonical CLI shape

The CLI emits envelope-shaped JSON unconditionally — no dual shape, no `--contract` flag. Persistence (`~/.claude/project-rag/install-profile.json` under the `whoami_profile` key) stores the full envelope. Downstream consumers (`/project-rag:doctor`, install scripts) access fields via the new envelope paths.

**Migration plan:** `docs/plans/2026-05-19-whoami-substrate-migration.md`
