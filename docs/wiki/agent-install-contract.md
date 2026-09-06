# Agent Install Contract

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-06/2026-06-22-coordinator-env-normalization-step-zero.md, cross-repo/archive/2026-07-13-example-cockpit-repo-em-publish-validate-install-contract-to-oss-sibling.md, archive/specs/2026-06/2026-06-23-coordinator-install-surface-dogfood-hardening-d2-13-disposition.md, 2026-06-15-coordinator-install-chain-application-phase-b.md, 2026-06-15-deep-research-install-chain-application-phase-b.md, archive/specs/2026-06/2026-06-17-chain-preinstall-phase-vocabulary.md, archive/specs/2026-06/2026-06-17-coordinator-install-seed-phase-and-manifest-alignment.md, docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md, docs/plans/2026-07-11-packageability-contract-fleet-doctrine.md -->
<!-- Single-Entry-Point Doctrine canonical home: docs/wiki/doctor-probe-design.md § Single-Entry-Point Consolidation Must Stay Addressable (+ docs/wiki/implementation-standards-by-domain.md § Cross-cutting standards, formerly coordinator/CLAUDE.md § Implementation Standards). Originated in archive/specs/2026-05-04-example-game-repo-umbrella-plugin.md §Single Entry-Point Doctrine (example-game-repo-side; not present in this repo) — canonicalized here 2026-05-27. -->
<!-- spec-backlink: archive/specs/2026-05-08-example-game-repo-install-chain-deps.md §3.1 -->
<!-- migration: this doc's canonical home is coordinator-claude, moved here from example-game-workbench-repo as the ecosystem-wide canonical home. Example-game-repo's copy is a one-line pointer redirect; project-rag-ue-addon and other consumers cite this file rather than mirroring it. -->

> This document is the single normative reference for the ecosystem-wide agentic install
> contract. Every repo in the dependency chain conforms to this contract. The contract was
> first implemented in `example-game-workbench-repo` (chain leaf), authored bilaterally between
> example-game-repo and `project-rag-ue-addon`, and migrated to `coordinator-claude` (chain root) on
> 2026-05-23 as the canonical home. Per-repo schema files (`agent-install-manifest.schema.json`)
> remain in each repo; this doc is the single source of truth for the contract semantics they
> implement.

## Versioning

The contract is version-stamped via `agent_install_contract_version` in each repo's manifest.

| Version | Status | Summary |
|---|---|---|
| 1 | superseded by 2 | Initial contract: top-level `override_flags` upstream-authored, no consumer-authored per-dep arguments. |
| 2 | superseded by 3 | Adds optional `consumer_install_args` per-`DirectDep` (consumer-authored mode + version flags); formalises walker composition rules; tightens 92/93 exit-code semantics as walker-invocation bugs (not upstream failures). |
| 3 | **current** | Adds optional `system_prerequisites` top-level array; flipped to literal `3` in the 2026-06-23 fleet-wide simultaneous-merge cutover. |

**Step 0's orient-leg discovery + interleave does not bump the contract version.** Step 0 carries
an additive orient-leg discovery sweep (§ Orient-leg discovery), longest-prefix install↔orient
pairing, leaf-safe interleave (a `ready_to_fire` orient leg fires right after its paired install only
when that install is the leaf; paired to a non-leaf install it defers to the absolute tail unless an
explicit `orient_after:` anchors it mid-chain), supersedes-after-orient-discovery ordering, and the
optional `orient_after:` baton field — none of which bumps the contract version (stays `3`, not `4`).
The version literal is *reader-gated* — consumers reject `agent-install-manifest.json` whose version
they do not recognise, and the entire load-bearing purpose of a bump is the reader-widen-first
lockstep across repos to avoid breaking peer *manifest* readers. Every version (1/2/3) is exclusively
about manifest-JSON-schema fields (`override_flags`, `consumer_install_args`, `system_prerequisites`).
The orient-leg mechanics above are **spinoff-baton frontmatter** (`orient_after:` in
`state/handoffs/*.md`) **and spine-walk prose** — read by **no** manifest reader, tripping **no**
version-range rejection, requiring **no** reader-widen cutover. Bumping the version for them would
mint a manifest-schema literal that is meaningless — no manifest reader checks or acts on it — and
drag every repo through a pointless lockstep.

**The six-point packageability contract likewise does not bump the contract version.** The
`agent-install-manifest.schema.json` optional-additive fields backing § Packageability contract
(portable-core repos) below — per-requirement functional-probe/remediation shape, the
**separate optional top-level `programmatic_entry_point` field** (the point-2 cold-install entry;
see § Two entries, two roles below — this is NOT a sub-object on `standalone_setup_script`), the
`installer_floor` boundary annotation, `tested_platforms`/`present_platforms`, and
`configurable_locations[]` — follow the same no-bump precedent as the orient-leg amendment (above)
and the `provider_capabilities` field (§ below, `:230-244`). `agent_install_contract_version`
stays enum `[1,2,3]`, literal `3`. These fields are read by exactly two
consumers: **DoE's own `validate-install-contract.py`** (a repo-local, opt-in-scoped compliance gate —
never a fleet-wide hook) and **the example-os-repo external driver** (not a manifest reader in the chain-walk
sense at all — a packaging tool that reads the JSON sidecar to drive its own GUI install flow). No peer
chain-walk manifest reader enforces any of these fields, so a bump is not needed to protect the
reader-widen-first lockstep.

**Reader-widen-first sequencing.** Consumers reject manifests with a version they do not recognise. A safe v1→v2 rollout therefore widens each repo's manifest reader to accept the version *range* `{1,2}` in one commit per repo, confirms both green, then flips each repo's manifest literal `1 → 2` in lockstep. Whichever repo bumps its manifest first without the peer's reader-widen breaks the peer's walk — this is an install-surface-completeness trap. The same pattern applies to the v2→v3 bump — see §v2→v3 migration playbook.

## Overview

Each repo in the install chain is **self-describing**: it declares its own direct upstream
dependencies, its canonical install entry-points, and the functional probes used to verify
each dependency. Discovery is dynamic — when a setup skill walks the chain, it reads each
upstream repo's manifest at walk-time rather than consulting any cached or centrally-maintained
registry.

The machine-readable structure lives in a JSON sidecar at a contracted path:

```
docs/install/agent-install-manifest.json
```

The human-facing companion (`docs/install/AGENT.md`) carries a one-line YAML frontmatter
pointer to the JSON sidecar and a human-readable prose body. The frontmatter is a pointer
only; all structured data lives in the JSON file. AGENT.md is **recommended, not required**
for validator-compliance (see the compliance-vs-conformance note below): a repo can be
`validate-install-contract.py`-green on its manifest alone.

The JSON Schema (draft 2020-12) governing `agent-install-manifest.json` is repo-local — a
conforming repo **may** ship its own `docs/install/agent-install-manifest.schema.json` whose
`$id` field is the canonical schema identifier for that repo's manifest. The schemas are
mirrors (structurally identical modulo repo-specific defaults); this doc is the single source
of truth for what the schemas must encode. The per-repo schema mirror is likewise
**recommended, not required** — consistent with the deferral note at § v3 migration (schemas
"stay in each repo … deferred until a third consumer makes the duplication pressure obvious";
current state: only example-game-repo + addon carry one).

> **Compliance vs. conformance — the validator and this doc use two bars, on purpose.**
> `validate-install-contract.py` asserts **packageability-compliance**: the repo's
> `agent-install-manifest.json` satisfies the active manifest points (1/2/3/4/6). It does
> **not** check for the presence of `AGENT.md` or the repo-local schema mirror — a repo with
> neither is still validator-green. The fuller **conformance** ideal additionally ships the
> human-facing `AGENT.md` and (once duplication pressure warrants) the schema mirror; both are
> strongly encouraged for adopters but recommended-not-required, so validator-green and the
> conformance ideal are deliberately not the same bar.

---

## Authority boundary

Two distinct authorities meet inside the contract; the field-level split keeps them honest.

| Authority | Owned fields | Who declares the literal value |
|---|---|---|
| **Upstream-authored** | `override_flags.*`, `repo_id`, `setup_skill`, `doctor_skill` (optional), `standalone_setup_script.*`, `programmatic_entry_point.*` (optional), `required_env_vars` | The upstream repo, in its own manifest. The chain-walker reads these from the upstream's manifest at dispatch time. |
| **Consumer-authored** | Each `DirectDep` entry's `consumer_install_args` (v2+) | The consumer repo, in its own manifest, scoped to the specific upstream it's calling. |

**Why the split matters.** Two repos can declare the same schema key with different values — e.g. `override_flags.accept_hallucination_risk` is `--accept-hallucination-risk` in example-game-repo and `--accept-corpus-poisoning-risk` in `project-rag-ue-addon`. If a consumer hard-coded the upstream's gate spelling into its own manifest, that literal would drift the moment the upstream renamed its flag. The walker therefore reads override_flags from the **upstream's** manifest at dispatch time, never from the consumer's. `consumer_install_args` (mode + version selection) is the only consumer-authored part of the invocation.

---

## No subagent-hostile bash wrappers

<!-- spec-backlink: cross-repo/archive/2026-07-21-project-rag-em-debash-must-be-fleet-propagated.md -->

**Conformance expectation (PM-ratified):** a packageable consumer repo **declares no
subagent-hostile bash wrappers.** A `.sh` surface a subagent invokes is denied by the claude-klabauter
subagent-indirection guard (`_evaluate_wrapper_indirection`) and taxes every subagent in the
repo; the packageable shape is a python-native / claude-klabauter-compliant surface. This is the
downstream, consumer-facing half of de-bash — the coordinator's own surfaces already moved to
the claude-klabauter Python track. Full directive + rationale: `no-new-bash-surfaces.md`.

**Bar today: doctrine, not a wired validator field.** This is a stated conformance expectation
that adopters carry in their own CLAUDE.md and enforce via `code-reviewer` (a new `.sh` wrapper
is a review finding, same posture as the GNU-ism lens), NOT yet a
`validate-install-contract.py`-checked manifest point. Promoting it to a validated packageability
point (a `packageability_compliance`-keyed check with a manifest field) is deferred to a future
plan — consistent with the six-point contract's own additive-field precedent (§ Contract-amendment
note). Stated here so the contract is the greppable home; the teeth land when the plan does.

---

## Schema reference

### Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_install_contract_version` | `integer` | yes | Contract version. Readers MUST accept any version in the known range (currently `{1,2,3}`) and reject anything outside. Enables coordinated schema bumps across repos via reader-widen-first sequencing. |
| `repo_id` | `string` | yes | Canonical repo identifier — matches the GitHub repository name. Used as the visited-set entry key during chain-walk. |
| `setup_skill` | `string` | no (optional when `standalone_setup_script` is present) | The slash-command a human types to invoke the agentic setup flow (informational — not the agent dispatch primitive; see §Skill chain-walker). **Optional** for a script-only install node: a repo that ships working `standalone_setup_script.{posix,windows}` and no agentic setup skill (e.g. Claude-klabauter, which has retired its plugin surface) omits this field rather than naming a non-existent or unrelated skill. The chain-walker never reads `setup_skill` (the real dispatch target is `standalone_setup_script` — see §512), so its absence changes no behavior. This mirrors `doctor_skill`'s optionality directly below. |
| `doctor_skill` | `string` | no (optional) | The slash-command a human types to invoke a doctor/health-check flow (informational; unread by the chain-walker). **Omitted entirely** by repos with no health-check flow — not every conforming repo warrants one (e.g. deep-research, a research-pipeline plugin, declares none). Requiring it previously forced a do-nothing stub skill whose bare name collided with Claude Code's native `/doctor`; the field is now optional. When a repo DOES declare one, avoid the bare name `doctor`/`/doctor` (native-command collision) — name it distinctly (e.g. `/coordinator:code-health`). |
| `standalone_setup_script.posix` | `string` | yes | Relative path to the POSIX (bash) standalone setup script, resolved against the declaring repo's own root in the general case. A repo whose actual entrypoint files live in a dependency's tree instead of its own is an exception to that general case, not a different field meaning — coordinator-claude is the reference instance (files migrated to claude-klabauter, `b644d5a9b`): its value resolves against whichever engine root `_engine_root.py` returns (the live `repos.claude_klabauter` checkout or the declared `claude-klabauter` dependency), never against this repo's own tree; see `coordinator/docs/install/agent-install-manifest.json`. This is the actual agent dispatch target. |
| `standalone_setup_script.windows` | `string` | yes | Relative path to the Windows standalone setup entrypoint — a `.cmd`/`.bat` launcher or a `.ps1` script, per the declaring repo; not assumed to be PowerShell. Resolved the same way as `standalone_setup_script.posix` above, including that row's dependency-tree exception. For coordinator-claude this is `scripts/setup.cmd`, a launcher that forwards argv to `setup.py` — not a `.ps1`. |
| `programmatic_entry_point.*` | `object` | **no** (optional) | The Point-2 COLD-INSTALL entry per § Packageability contract point 2 — a single non-interactive, flag-driven, deterministic-exit-code install/register/assemble command, DISTINCT from `standalone_setup_script` (the chain-walk dispatch target; see § Two entries, two roles). For coordinator-claude this is `coordinator_core/install/maximalist.py` (engine-root-relative, same resolution as `standalone_setup_script.posix` above — resolves against either the live `repos.claude_klabauter` checkout or the declared `claude-klabauter` dependency, per `coordinator/docs/install/agent-install-manifest.json`), with `entry_point_contract` flags `--non-interactive` / `--check-only` and `deterministic_exit: true`. When both `programmatic_entry_point.entry_point_contract` and `standalone_setup_script.entry_point_contract` are present, `programmatic_entry_point` is the authoritative Point-2 witness; `standalone_setup_script.entry_point_contract` describes only the chain-walk invocation and is the Point-2 fallback only when `programmatic_entry_point` is absent. Because the engine is a separate install, coordinator-claude's `bin/` entrypoints resolve it at runtime through `cc_invoke`'s env/registry rungs rather than from anything inside the resolved engine root; a conforming check MUST NOT strip those rungs and assert a standalone-runnable contract this distribution does not make. |
| `direct_deps` | `array<DirectDep>` | yes | Ordered list of direct upstream dependencies. The chain-walker processes these in declaration order. Does not include transitive deps — each upstream declares its own. |
| `required_env_vars` | `array<string>` | yes | Environment variables that must be set for install to succeed. The standalone script prompts for any that are missing in interactive mode and fails fast in non-interactive mode. |
| `override_flags.skip_dep_check` | `string` | yes | The first flag of the override flag pair (e.g., `--skip-dep-check`). Both flags must be passed together; one alone produces exit code 93. **Upstream-authored** — see Authority boundary. |
| `override_flags.accept_hallucination_risk` | `string` | yes | The second flag of the override flag pair. Each upstream declares its own value (e.g., example-game-repo uses `--accept-hallucination-risk`, project-rag-ue-addon uses `--accept-corpus-poisoning-risk`). Signals the caller explicitly accepts the risk of running without hard deps. **Upstream-authored**. |
| `system_prerequisites` | `array<SystemPrereq>` | **no** (v3+) | OPTIONAL. Machine-level system prerequisites probed at Step Zero before any install proceeds. Each entry (DR-INSTALL-002 §3): `{id, tier, probe{kind REQUIRED, cmd REQUIRED, shell?, ref?}, install{mode REQUIRED, posix?, windows?, remediation?}, applies_to?, reference REQUIRED}`. **Cross-repo canonical schema owned centrally by coordinator; each consuming repo (example-game-repo, project-rag, project-rag-ue-addon, deep-research) populates its OWN `system_prerequisites` array against this shape.** `probe.cmd` is the universal probe every consumer resolves independently; `probe.ref` names a `_co_probe_<id>` function in `prereq_probe.sh` and is a vendor-only fast-path valid ONLY for verbatim-vendors of that lib. `tier` uses the ENV-PREREQ-PROBE taxonomy (`hard\|semi-hard\|advisory` — the pre-DR `optional` value was retired) from `step-zero-emitter-contract.md § severity Enum` — this is **orthogonal** to the `DirectDep.severity` manifest-dep taxonomy (`hard\|soft\|optional`); see §Severity semantics for the boundary. See §SystemPrereq fields for the full entry shape. |

### DirectDep fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | yes | Canonical dep identifier — matches the upstream's `repo_id`. Used as the visited-set key during chain-walk. |
| `severity` | `enum` | yes | `hard`, `soft`, or `optional` — see §Severity semantics. |
| `sibling_dir_name` | `string` | yes | Expected directory name of the sibling clone, relative to the consumer repo's parent directory. The chain-walker checks for presence at `<parent>/<sibling_dir_name>` before running the functional probe. |
| `upstream_url` | `string` | yes | Canonical GitHub HTTPS URL for cloning this dep. |
| `functional_probe` | `FunctionalProbe` | yes | Verifies the dep is not only present but functional. See §Functional probe kinds. |
| `consumer_install_args` | `array<string>` | **no** (v2+) | Optional. Args the consumer wants passed to this upstream's standalone setup script — mode selection (e.g. `--consumer-only`) and version selection (e.g. `--ue-version 5.7`). Composed by the chain-walker with `--i-am-agent` and the **upstream's** `override_flags`; does NOT include the upstream's override flags (those are read from the upstream manifest at dispatch time). Omit version-tag literals (e.g. `--corpus-tag`) where the upstream supports a newest-for-line resolution convention — let the upstream resolve to avoid pin-to-deleted-tag skew. |

`DirectDep` retains `additionalProperties: false`. `consumer_install_args` is an additive optional property, so a v1 consumer manifest validates clean under the v2 schema (forward-compatible).

### SystemPrereq fields

<!-- manifest-prereq schema (DR-INSTALL-002 §3): id | tier | probe{kind,cmd,shell?,ref?} | install{mode,posix?,windows?,remediation?} | applies_to? | reference -->
<!-- tier uses ENV-PREREQ-PROBE taxonomy (hard|semi-hard|advisory — NO optional) — ORTHOGONAL to manifest-dep taxonomy (hard|soft|optional) -->

Canonical shape ruled by **DR-INSTALL-002** (`docs/decisions/DR-INSTALL-002-system-prerequisites-schema-owner.md`): central owns the shape, consumers mirror it.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | yes | Canonical probe identifier (e.g. `git`, `python`, `gh`). Matches the `_co_probe_<id>` function suffix in `prereq_probe.sh` where a `ref` function exists. |
| `tier` | `enum` | yes | ENV-PREREQ-PROBE severity tier: `hard` (block install), `semi-hard` (warn loudly, offer remediation, continue only with confirmation), `advisory` (warn, never block). Mirrors `step-zero-emitter-contract.md § severity Enum`. The pre-DR `optional` value was **retired** (DR-INSTALL-002 §2a — no distinct semantic vs `advisory`). **Orthogonal** to `DirectDep.severity` — do not conflate. |
| `probe.kind` | `enum` | **yes** | Probe kind, reusing the FunctionalProbe vocabulary (`command_succeeds` in practice for presence probes). DR-INSTALL-002 §2c load-bearing add. |
| `probe.cmd` | `string` | **yes** | Universal shell command to check for the prerequisite. Must be portable (sh-compatible). E.g. `command -v git`. Every consumer resolves `probe.cmd` independently — it is the universal probe. |
| `probe.shell` | `boolean` | no | When true, the probe `cmd` runs through a shell (for pipe/`\|\|`/glob compound probes). Optional, default false. Ratified from ue-addon (DR-INSTALL-002 §2c). |
| `probe.ref` | `string` | no (vendor-only) | Names a `_co_probe_<id>` function in the vendored `prereq_probe.sh` lib. A vendor-only fast-path — **MUST NOT be relied on by non-vendors** of `prereq_probe.sh`. |
| `install.mode` | `enum` | yes | `auto-with-confirmation` (first-class automated install with printed confirmation + opt-out; `posix`/`windows` supply the commands) or `manual` (operator installs; `remediation` carries the instruction). DR-INSTALL-002 §2b/§2d. |
| `install.posix` | `string` | no | POSIX (sh/bash) install command string, run on confirmation under `auto-with-confirmation`. |
| `install.windows` | `string` | no | Windows (PowerShell) install command string, run on confirmation under `auto-with-confirmation`. |
| `install.remediation` | `string` | no (manual) | One-line human-readable install instruction for `mode: manual`. May reference per-OS package managers. |
| `applies_to` | `array<string>` | no | Which install class(es) the prerequisite applies to. Defaults to `["consumer"]` when omitted. Ratified from ue-addon (DR-INSTALL-002 §2e). |
| `reference` | `string` | **yes** | Doc pointer — path or URL to further documentation about this prerequisite. Required item key (DR-INSTALL-002 §3). |

`system_prerequisites` is an optional top-level array; omitting it entirely is valid (manifests without it validate clean under the v3 schema). The schema enforces `additionalProperties: false` on each `SystemPrereq` entry.

### `provider_capabilities` — upstream-provider early-hoist (reader-first contract seeding)

<!-- spec-backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § Upstream-provider early-hoist (PM directive B) C8c -->
<!-- additive-no-bump: this field follows the same precedent as the orient-leg amendment (lines above); see § Versioning note at :25–40 -->

**Reader-first up front.** This is contract *seeding*: coordinator **declares**
`provider_capabilities` now; **no consumer install script reads it yet.** The consumer read
protocol below is the specification for future adoption, documented here so each consuming EM can
adopt it on their own clock — not a behavior any consumer implements today.

**Purpose.** `system_prerequisites` (v3) covers *system tools* (python, git, gh, …). A separate
axis — **provider capabilities** — lets an upstream repo *declare* its Claude Code provider role so
a downstream consumer can **hoist those requirements by reference at its own Step Zero**, alongside
`system_prerequisites`, minimizing handoffs/restarts by surfacing coordinator's plugin
self-registration and `refresh-plugin` requirements as early as possible.

**Which repos declare this field.** Only **upstream providers** in the install DAG declare
`provider_capabilities`. In the current ecosystem, that means exactly:

- **`coordinator-claude`** — the DAG root, and the sole declarer. Declares plugin self-registration,
  hook wiring, and the `refresh-plugin` primitive that every downstream leg depends on to receive
  coordinator plugin updates. deep-research is folded into the coordinator plugin bundle (not a
  separate repo — see § the deep-research callout below) and carries no manifest of its own to
  declare the field from.

Consumer repos (example-game-repo, project-rag, project-rag-ue-addon, …) do **not** declare this field —
they read and hoist it from the upstream they depend on.

**Field shape.** `provider_capabilities` is an **optional top-level object** in the manifest JSON
with the following declared sub-fields:

```json
"provider_capabilities": {
  "role": "<string — enum: \"upstream-provider\" | \"consumer\". \"upstream-provider\" = DAG root other repos depend on; \"consumer\" = depends on an upstream provider>",
  "plugin_self_registration": "<boolean — true when this repo self-registers its plugin during install (self-contained plugin activation)>",
  "refresh_primitive": "<string — relative path (from repo root) to the script that refreshes the plugin's live-install checkout. Empty string when relying on an upstream refresh primitive rather than owning one>",
  "hoistable_at_step_zero": "<boolean — true if the chain-walker may surface this provider's requirements at the consumer's Step Zero alongside system_prerequisites>"
}
```

All four sub-fields are required when the parent `provider_capabilities` object is present. The
parent object itself is optional — manifests that omit it entirely validate clean under the schema
(forward-compatible with all existing manifests). Consumers MUST treat an absent `provider_capabilities`
as "no provider role declared for this upstream" and proceed without hoisting.

**Consumer read protocol.** When a consumer's chain-walker encounters a `provider_capabilities`
object on an upstream manifest, it MAY (opt-in, not mandatory today):

1. **At Step Zero** — before any install step runs — surface the upstream's
   `plugin_self_registration` and `refresh_primitive` requirements to the operator, alongside the
   existing `system_prerequisites` probe output. This is the "hoist by reference" mechanic: the
   consumer reads the upstream's declaration rather than re-declaring it inline.
2. If `hoistable_at_step_zero` is `true`, the chain-walker is authorised to emit the upstream's
   provider requirements in the Step-Zero block without waiting for that upstream's install leg
   to run.
3. Consumers that do not yet read `provider_capabilities` are **not broken** — the field is
   invisible to them (additive, `additionalProperties: false` schema still validates after the
   schema `properties` block is widened to include it).

**Declaration only, adopted on each sibling's own clock.** No consumer install script is edited as
part of declaring this field — consumer-side hoisting is adopted by each sibling repo via the
existing cross-repo memo channel. AC12 of the originating plan tests *declaration + schema-validity*,
NOT live consumption: a vacuous-pass on an inert field is explicitly rejected as the validation shape
(see `docs/wiki/install-surface-completeness.md § vacuous-pass anti-pattern`).

**No contract version bump — additive + reader-first.** `additionalProperties: false` stays strict;
only coordinator — the sole declarer — widens its own schema's `properties` to admit the field. A
peer that never carries the field never validates against it, so the version literal `3` is
unchanged. This is **bilateral-bump-safe**: a schema not widened for `provider_capabilities` simply
never produces it; a reader that doesn't know the key silently skips it. Neither direction requires
a `3 → 4` bump or a reader-widen lockstep.

---

### Chain-walk prereq-gate posture (Decision-3)

<!-- chain-walk-prereq-gate-posture: post-consumer chain-walk advisory WARN; --preflight strict -->
<!-- spec-backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md Decision-3 -->
<!-- boundary: docs/wiki/install-surface-completeness.md § Post-Consumer Gates Must Be Advisory WARN -->

The DAG-root chain-walk (`setup.py` default body, the POST-CONSUMER path) now resolves coordinator's `system_prerequisites` at Step Zero before any install proceeds. On this post-consumer path the probe outcomes are gated as follows:

- **`python`** — the **sole hard gate** on the chain-walk path. `python`/`python3` is the runtime that drives the manifest read, dep-chain walk, and Step Zero probe itself; without it, the walk cannot proceed at all. Blocks with exit non-zero on failure.
- **`gh`, `node`, `git`, `clone_auth`** — emit advisory-WARN (printed to stderr; no exit-code block). These tools are required for a complete install but are either available via system paths or recoverable interactively. Absent any of these, the walk continues and surfaces a remediation line per tool. Rationale: post-consumer gates MUST be advisory WARN per `install-surface-completeness.md § Post-Consumer Gates Must Be Advisory WARN`.

The interactive `--preflight` path stays **STRICT**: `gh`, `node`, `git` are hard gates; `clone_auth` is semi-hard (warn loudly, offer remediation, continue only with confirmation). `--preflight` is the explicit pre-install verification path where the operator has consented to a blocking check.

### Canonical Step-Zero functional probe set

<!-- src: plan20-025, plan20-026, plan20-027, plan20-028, plan20-029 -->

`--preflight` is a superset of `--check` — it extends the probe set and reuses `--check`'s
tabling + NDJSON emitter (one output surface, two intents) rather than inventing a second
reporting shape. The concrete probe set backing both `--check` and `--preflight` is six
functional checks, each independently testable and each exiting 0 on success:

| Probe | What it does | Gate posture |
|---|---|---|
| `_co_probe_python` | Delegates to `_co_find_python` — one floor-version constant, defined in one place, not duplicated per probe. | Hard (sole hard gate on the post-consumer chain-walk path; see § Chain-walk prereq-gate posture above). |
| `_co_probe_uv` | Runs `uv --version`. | Advisory WARN (new gate — promote to hard only after fleet-wide verification). |
| `_co_probe_pwsh` | pwsh 7+ passes; 5.1 does not — it is not a supported host. | Advisory WARN today; promotion to semi-hard on Windows is memo'd to claude-klabauter. |
| `_co_probe_ue` | Unreal Editor presence, honoring `EXAMPLE_GAME_REPO_UE_ROOT` when set. | WARN-only — coordinator itself does not require UE. |
| `_co_probe_clone_auth` | Checks `gh`, SSH, or Git Credential Manager auth against a private clone URL. | Semi-hard under `--preflight` (warn loudly, offer remediation, continue only with confirmation); advisory-WARN on the post-consumer chain-walk path. |
| `_co_probe_longpaths` | Windows-only: verifies `git config core.longpaths == true`. | Advisory WARN (new gate). |

**Gate-severity posture on new probes is advisory-first, promote-after-verification.** Only
`python` is a pre-existing hard gate (it drives the manifest read and the Step-Zero probe
machinery itself, so without it the walk cannot proceed at all). `gh`/`node`/`git`/`clone_auth`
are pre-existing advisory-WARN on the post-consumer chain-walk path (§ Chain-walk prereq-gate
posture). `uv`/`pwsh`/`ue`/`longpaths` are **newly-added** probes and ship advisory-WARN by
default; a probe is promoted to a harder gate only once verified safe across the fleet, never
pre-emptively hard-gated on introduction.

**Env-normalization mutation mechanics — auto-normalize with an in-script confirm gate, not a
blanket "proceed?" prompt.** Where a Step-Zero probe fails and the fix is auto-mutable (e.g.
PATH entries, shell aliases), the normalization script is idempotent and `--dry-run`-capable, and
enumerates each planned mutation individually (which alias gets disabled, which PATH segment
gets prepended) rather than asking one blanket "proceed? [y/N]" for the whole batch. Sequencing
is backup-first: snapshot the prior PATH to a timestamped backup file before any mutation, print
a `--restore` affordance, apply blast-radius-last ordering (lowest-risk mutations first), then
re-probe post-mutation to confirm the fix actually took. `--yes` bypasses the confirm gate for CI.
Windows is first-class for auto-mutation; macOS/Linux default to offer-and-print remediation
(e.g. `brew install` pointers) rather than aggressive auto-mutation.

**Idempotency claim is narrowed, not blanket.** `git config` and `uv`-installed-tool checks are
byte-stable no-ops on re-run. PATH/shim/alias mutations are **not** byte-stable — they "converge
toward the target state, re-runnable without harm," which is a weaker and more honest claim:
Windows platform updates silently re-create aliases the probe must re-disable, and PATH
correctness requires semantic matching (is the right entry present anywhere) rather than
string-equality against a previous run's exact output.

### FunctionalProbe fields

| Field | Type | Conditional | Description |
|---|---|---|---|
| `kind` | `enum` | always | One of `sibling_dir_exists`, `file_exists`, `python_import`, `command_succeeds`. |
| `path` | `string` | required when `kind` is `file_exists` | Path relative to the sibling repo root. |
| `expr` | `string` | required when `kind` is `python_import` | Python import expression evaluated via the resolved Python interpreter. |
| `cmd` | `string` | required when `kind` is `command_succeeds` | Shell command that must exit zero for the dep to be considered functional. |

---

## Severity semantics

<!-- manifest-dep taxonomy: hard | soft | optional (this section, ENV-PREREQ-PROBE-distinct) -->
<!-- DISTINCT from ENV-PREREQ-PROBE taxonomy: hard | semi-hard | advisory (step-zero-emitter-contract.md §severity-enum) -->
<!-- The two taxonomies are orthogonal contracts for different surfaces — do not conflate. -->
<!-- Greppable boundary: search "manifest-dep taxonomy" or "ENV-PREREQ-PROBE taxonomy" to find both anchors. -->

The severity values below apply to **manifest `DirectDep` entries** (chain-walker behavior). This is the **manifest-dep taxonomy** (`hard | soft | optional`). It is a **separate and orthogonal contract** from the ENV-PREREQ-PROBE taxonomy (`hard | semi-hard | advisory`) used in Step Zero probe NDJSON lines — see `docs/wiki/step-zero-emitter-contract.md § severity Enum`. Do not conflate: a dep declared `hard` here does not make its probe emit `hard` severity; those are different fields on different contracts.

| Severity | Chain-walker behavior |
|---|---|
| `hard` | Block install unless the override flag pair is passed and (in TTY mode) double-confirmation is satisfied. Hard-missing deps trigger the consent gate (§Consent gate). |
| `soft` | Warn loudly. Offer to walk the dep chain and install. If the user declines, proceed without the dep. |
| `optional` | Offer once. No warning if the user declines. Proceed silently. |

> **Coordinator-owner ruling — `coordinator-claude` is canonically `soft`.** Severity is consumer-authored (each consumer declares how hard *it* couples to the dep), but where consumers diverge on `coordinator-claude` specifically — example-game-repo declared `soft`, project-rag-ue-addon declared `hard` — the authoritative classification is **`soft`**. `coordinator-claude` is the DAG-root doctrine/pipeline layer (its own `direct_deps` is `[]`): a non-blocking *enhancer*, not a runtime prerequisite. A consumer can install and operate — degraded, without the pipeline/reviewers — when it is absent, which is exactly the `soft` contract (warn loudly, offer to walk-and-install, proceed if declined). `deep-research-claude` declares it `soft`; consumers should align to `soft`.

> **Coordinator-owner ruling — override-flag-name divergence is by design.** The consent-gate override flag has different spellings per upstream — example-game-repo `--accept-hallucination-risk`, coordinator/project-rag `--accept-missing-deps-risk`, ue-addon `--accept-corpus-poisoning-risk`. This is **sanctioned, not a defect**: per § Why the split matters, the chain-walker reads `override_flags` from the *upstream's own* manifest at dispatch time, so each upstream names the risk it actually gates (AI hallucination, missing deps, corpus poisoning) with zero drift hazard. The coordinator-canonical/generic spelling is **`--accept-missing-deps-risk`**; repos keep their semantic flag and are not required to rename. A shared alias is optional polish, not a contract obligation.

> **Coordinator-owner ruling — canonical OSS install-probe path is `.claude-plugin/plugin.json`, not `coordinator/CLAUDE.md`.** No spelling of a `CLAUDE.md` path is diagnostic of a working `coordinator-claude` install: `coordinator/CLAUDE.md` (the EM operating-doctrine file) is not a member of `setup/publish-targets.portable`'s `coordinator-claude` mirror allowlist — that allowlist enumerates `bin,lib,hooks,skills,agents,commands`, a short named `docs/wiki/*.md` set, `.claude-plugin`, `cockpit-contract/schema`, two schemas, and several `templates/*` entries (including `templates/CLAUDE.md.tmpl`) — `CLAUDE.md` itself is absent from that list. A `CLAUDE.md` does exist at the OSS mirror's repo root, but it is the generic project-principles template rendered from `templates/CLAUDE.md.tmpl` — unrelated boilerplate, not doctrine content.
>
> The OSS mirror's installed sibling-repo tree is **flat single-plugin** at the repo root, with **no `coordinator/` segment anywhere** — `bin/`, `lib/`, `hooks/`, `skills/`, `agents/`, `commands/`, `docs/wiki/`, `.claude-plugin/` all sit directly under the sibling repo root. A consumer pins this path once and does not need to chase the layout again.
>
> **Canonical probe:** a `coordinator-claude` `functional_probe` of kind `file_exists` MUST declare `path: ".claude-plugin/plugin.json"`. It is in the publish allowlist and is Claude Code's own native plugin manifest — structurally required for the plugin to be installable at all, not an artifact of our own naming that could get reorganized out from under a probe.

---

## Functional probe kinds

The chain-walker runs two checks for each dep, in order:

1. **Implicit sibling presence check** (`sibling_dir_exists`): does the directory `<parent>/<sibling_dir_name>` exist? This check is always implicit — it runs regardless of the declared `functional_probe.kind`.
2. **Functional probe** (declared in `functional_probe.kind`): is the dep actually usable?

The initial set of probe kinds (extensible — new kinds require a contract version bump):

| Kind | Description | Required extra field |
|---|---|---|
| `sibling_dir_exists` | Implicit always-run check. No additional fields. Can be used as the declared probe when directory presence alone is sufficient. | none |
| `file_exists` | The file at `path` (relative to the sibling repo root) exists. | `path` |
| `python_import` | The Python import expression in `expr` succeeds via the resolved Python interpreter. | `expr` |
| `command_succeeds` | The shell command in `cmd` exits zero. Escape hatch for non-Python upstreams. | `cmd` |

A dep may be `present` (sibling dir exists, functional probe passes), `missing` (sibling dir absent), or `present-but-broken` (sibling dir exists, functional probe fails).

Probe-status returns must follow the closed remediation loop invariant: every status branch carries an explicit `remediation` field that names the next mutation step. See `example-game-repo-doctrine.md §7.4` and the doctor agent surface in `example-game-repo-install-prereq.md` for the broader doctor/probe contract that this manifest's probes plug into (example-game-repo-side references; consumers adapt the equivalent locally).

---

## Dual-mode script UX

Every conforming repo's standalone setup script operates in two modes: **human-interactive** (invoked by hand from a terminal) and **machine-parseable** (invoked by an agent). The (a)(b)(c)(d) sequence below defines both paths.

### Step (a) — Agent-or-human detection

On launch in a TTY context, the script prints a one-line preamble and waits for input:

```
Are you running this script as an autonomous agent rather than via /<setup-skill>? [y/N]
```

Responses:
- **y**: print the path to `docs/install/AGENT.md` and exit **92** (agent-direct-invocation-detected). The agent should dispatch the setup skill instead.
- **N** (or enter): continue as interactive human-mode.

Override mechanisms (suppress the prompt entirely):
- `--i-am-agent` flag: acts as y by itself (exit 92); paired with the upstream's `override_flags` pair, runs in agent mode (see §Walker composition).
- `--i-am-human` flag: acts as N (continue).
- Equivalent environment variable (e.g. `EXAMPLE_GAME_REPO_RUN_MODE=agent` / `=human` in the example-game-repo reference impl; consumer repos may declare an analogous repo-scoped env var).

**Non-interactive contexts** (`--non-interactive` flag or non-TTY): step (a) prompt is skipped entirely — both are treated as implicit `--i-am-human`. This avoids prompt text appearing in CI logs.

### Read-only flag carve-out

Certain flags indicate the caller wants information only, not installation. When any of these flags is present, step (a) and the consent gate (steps b–d) are skipped entirely — the script services the request and exits without running Phase 0:

| Flag | Description |
|---|---|
| `--help` | Print usage and exit 0. |
| `--version` | Print version and exit 0. |
| `--phase-list` | Enumerate the values accepted by `--phase <name>` and exit 0. See `--phase <name>` below. |
| `--phase <name>` | Dispatch a named install phase by value. `seed-install-spinoff` is always a read-only no-op (see § The two roles); phases that write install-status are NOT in this carve-out. The carve-out applies to phases that, by their contract, write no install-status or persistent state. Scripts MUST fail loud (non-zero) on unknown `--phase` values — silent-skip is prohibited. Carve-out membership is determined by the phase's contract-level statefulness declaration, NOT by per-leg body behavior. A phase declared stateful-by-contract (e.g. chain-preinstall) is never in the carve-out, even at legs whose bodies happen to write nothing (coordinator/DR no-ops). Otherwise the same phase would carry different guard behavior per-leg. |
| `--last-status` | Print the last recorded install status and exit 0. |
| `--i-am-agent` | (documented here for completeness) exits 92 before Phase 0 when passed alone. |
| `--check` | (coordinator-specific extension) Read-only dep probe; no state written. Not part of the baseline contract — conforming non-coordinator repos need not implement it. |

`--phase-list` and `--phase <name>` are a related pair: `--phase-list` enumerates the values `--phase <name>` accepts. Conforming scripts MUST keep the two in sync — every value advertised by `--phase-list` must be accepted by `--phase <name>`, and every accepted value must appear in `--phase-list` output.

This is the canonical read-only flag baseline. Repos that conform to this contract inherit this set and may extend it with repo-specific read-only flags. The set must be greppable from a single named function or allowlist comment block in the script.

### Read-only carve-out and install-status.json mutation

(see § Relocation boundary for the full two-artifact relocation scope this example path assumes)

Flags in the read-only carve-out table MUST prevent any write to the install-status ledger (e.g. `<settings-home>/example-game-repo/install-status.json` in example-game-repo; consumers adapt the path — see § Visited-set protocol for the `<settings-home>` definition). The carve-out is not just a UX convenience — it is a safety boundary: doctor probes invoke the standalone script with `--last-status` to read phase state without triggering a new install or modifying the ledger. This ledger path relocated to `<settings-home>/<repo-id>/install-status.json` per § Relocation boundary.

**Enforcement:** every conforming repo's standalone script must gate install-status writes behind the read-only-carveout check. Any write path that bypasses this gate will corrupt the ledger during doctor-mode reads.

If a probe needs to inspect the install ledger while the write gate is active, it reads the file directly — it does not invoke the standalone script without `--last-status`.

### Step (b) — Dependency probing

For each declared dep, the script runs the implicit sibling check then the functional probe:
- `hard` dep missing or broken: capture for the consent gate (step d).
- `soft` dep missing: warn loudly, offer to clone-and-walk via gh CLI, proceed if declined.
- `optional` dep missing: print a one-line offer, proceed silently if declined.

### Step (c) — Required env var collection

Interactively prompt for any `required_env_vars` that are not already set. Validate each before proceeding. In non-interactive mode, fail fast if any required var is missing.

### Step (d) — Install with consent gate

Run the install. If hard-missing deps were found in step (b), the consent gate fires (§Consent gate below). If all hard deps are present and functional, the gate is not shown.

---

## Consent gate

The consent gate is the last barrier before installing without all hard deps. Its text is stored in a single file (`scripts/lib/dep_consent_banner.txt` in the example-game-repo reference implementation) — both script halves and the setup skill read from that file so the warning text has one source of truth.

**Example consent gate banner (example-game-repo concrete example):**

```
================================================================
WARNING — UNSAFE INSTALL REQUESTED

You are installing <repo-id> WITHOUT one or more of
its dependency-chain prerequisites:

  <list of missing hard deps, one per line>

Without these, agents using example-game-repo-control to mutate your
Unreal Engine project will operate with confident hallucination
at ~25% (Opus 4.7 baseline; smaller models are worse). UE
projects corrupted by hallucinated API calls are not always
recoverable from the editor's transaction log.

Canonical install order (do this first instead):
  1. coordinator-claude   (open-source, public; bundles deep-research)
  2. project-rag
  3. project-rag-ue-addon
  4. Example-game-workbench-repo

To proceed anyway, you must confirm twice. The first prompt
asks whether you accept the missing-dep risk; the second asks
whether you specifically accept the ~25% hallucination risk.
================================================================
```

The verbatim warning text (including the ~25% figure) must not be paraphrased by the setup skill — the skill quotes it directly from the banner file.

### Consent gate behavior table

| Mode | Behavior |
|---|---|
| TTY, no flag pair | Banner → confirm 1 → confirm 2 → proceed. Either N → exit **91**. |
| Non-TTY, no flag pair | Banner to stderr → exit **90**. |
| TTY, both flags | Banner once → one-line acknowledgment → proceed. |
| Non-TTY, both flags | Banner once to stderr → proceed. |
| Either, only one of two flags | Exit **93** (override-flag-pair-incomplete). |

---

## Exit code table

| Code | Name | Semantics |
|---|---|---|
| 0 | `success` | Install completed; ledger updated. |
| 11 | `gh-unauth` | `gh` CLI is unauthenticated; chain-walker should surface remediation and halt the walk (**actionable-stop**). |
| 12 | `uv-missing` | `uv` is not installed/resolvable; chain-walker should surface remediation and halt the walk (**actionable-stop**). |
| 90 | `hard-dep-missing-non-tty` | A hard dep is missing in a non-interactive / non-TTY context and the override flag pair was not provided. |
| 91 | `double-confirm-declined-tty` | The user answered N to either of the two double-confirmation prompts under TTY. |
| 92 | `agent-direct-invocation-detected` | `--i-am-agent` was passed without the upstream's override-flag pair, OR agent-mode was detected via env. In a correctly-implemented v2 walker, **92 from an upstream dispatch is a walker-invocation bug, not an upstream install failure** — the walker built the command without composing override_flags. Surface as an internal walker error, not as a dep failure. |
| 93 | `override-flag-pair-incomplete` | Only one of the two override flags was provided. Both are required together. Same walker-bug interpretation as 92 when seen during an agent-mode walk. |
| 94 | `preflight-git-auth-unverified` | A semi-hard probe (clone_auth) emitted a warn/fail row without `--accept-no-git-auth` being supplied. Chain-walker should surface remediation and halt the walk (**actionable-stop**). |

**Not this table's codespace.** Exit `96` (`entry_point_contract.refusal_exit_code` in
Claude-klabauter's manifest) is their reserved designed-refusal code for a PEP-668-guarded
interpreter — not a coordinator-claude code. See `docs/install/AGENT.md` § Settings-home
provisioning.

---

## Skill chain-walker

The setup skill (e.g., `/example-game-repo:install`) is the agentic entry point. It walks the dependency chain dynamically, never consulting a cached or centrally-maintained registry.

**Important:** `setup_skill` in the manifest is informational metadata — it tells humans what to type. It is NOT the agent dispatch primitive. Dispatched subagents do not expand slash commands in their prompts. The canonical dispatch mechanism is: subagent + constructed prompt + standalone-script invocation.

### Walker composition (v2)

When the chain-walker iterates a consumer's `direct_deps` and dispatches a subagent to install an upstream, the constructed standalone-script invocation MUST be:

```
<upstream standalone_setup_script> \
  <consumer_install_args...> \      # from the consumer's DirectDep entry (may be empty)
  --i-am-agent \
  <upstream override_flags.skip_dep_check> \
  <upstream override_flags.accept_hallucination_risk>
```

Composition rules:

- **`consumer_install_args` come from the *consumer's* `DirectDep` entry for this upstream.** Mode + version selection only — never the upstream's gate-flag spelling.
- **`override_flags.*` are read from the *upstream's* manifest at dispatch time**, never literal-pinned in the consumer's manifest. Same schema key, different values across repos — the authority boundary depends on this.
- **`--i-am-agent` alone is exit 92.** In agent-mode chain-walk, bare `--i-am-agent` MUST always be accompanied by the upstream's override-flag pair. This makes the override flags an intrinsic property of agent-mode invocation, not a parallel mechanism.
- **Composition order is functionally irrelevant** — the standalone scripts parse all three in any order. The order above is for readability and consistency.

### Exit-code handling (Step 4 of the walker)

| Exit code | Walker classification | Action |
|---|---|---|
| 0 | `success` | Continue. |
| 11 / 12 | **actionable-stop** (upstream prerequisite missing on the host) | Surface remediation. Halt the walk. |
| 92 / 93 | **invocation bug** (walker built the command wrong) | Surface as an internal walker error, NOT an upstream install failure. With composition correctly implemented, these should be unreachable; if they fire, the composition logic regressed. |
| 94 | **actionable-stop** (git-host authentication unverified — semi-hard gate) | Surface remediation. Halt the walk. Operator may re-run with `--accept-no-git-auth` to suppress. |
| other non-zero | generic failure | Report last 20 lines of output; halt or continue per severity. |

### Constructed-prompt template

The chain-walker dispatches subagents using a rendered prompt template stored at a contracted path within each conforming repo:

```
scripts/lib/chain_walker_subagent_prompt.txt
```

(Path relative to the repo root. Each conforming repo stores its template at this contracted path so the dispatch mechanism is greppable.)

Template substitution variables:

| Variable | Value |
|---|---|
| `$UPSTREAM_ID` | The dep's `id` field from the manifest. |
| `$SIBLING_PATH` | The resolved absolute path of `../<sibling_dir_name>`. |
| `$SESSION_ID` | The UUID generated at top-level invocation start. |
| `$CONSUMER_INSTALL_ARGS` (v2+) | The space-joined `consumer_install_args` array from the consumer's `DirectDep` entry, or empty string if absent. |

The template instructs the subagent to: read the visited-set file (see below), check for the dep before cloning, append to visited-set before dispatching further subagents, compose the v2 invocation (`$CONSUMER_INSTALL_ARGS` + `--i-am-agent` + upstream override_flags), and recurse for the upstream's own `direct_deps`.

### Visited-set protocol

To handle diamond-DAG and cycle detection across recursive subagent dispatches (which share no EM context), the chain-walker uses a **disk-resident visited-set file** at:

```
<settings-home>/<repo-id>/chain-walk-<session-id>.json
```

**`<settings-home>` definition (cold-safe, computable without any bin dependency; POSIX-host
form — a PowerShell host resolves the same value via rung 0 / Shape W, see
`coordinator/snippets/resolve-coordinator-bin.md`):**
```
${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}
```
The canonical install-chain write prefix is `<settings-home>/`, relocated from `~/.claude/` (durable-substrate-to-settings-home plan). Consumers repoint their own chain-walk and install-status writers per this relocated protocol. During the migration window, a consumer MAY additionally read the legacy `~/.claude/<repo-id>/` path as a fallback.

**Example (example-game-repo concrete example):** `<settings-home>/example-game-repo/chain-walk-<session-id>.json`

### Relocation boundary — what moves to `<settings-home>/<repo-id>/` and what stays

The relocation above did not move the entire `~/.claude/<repo-id>/` directory — only two artifacts relocated. This subsection is the ruling consumers repeatedly ask about; treat it as authoritative.

**RELOCATES to `<settings-home>/<repo-id>/`** — ONLY the two artifacts this agent-install contract names:

1. **`install-status.json`** — the install-status ledger (§ Read-only carve-out and install-status.json mutation, line ~338).
2. **`chain-walk-<session-id>.json`** — the chain-walk visited-set (§ Visited-set protocol).

**NOT swept by the coordinator relocation** — files this contract never named; the coordinator's own migration leaves them where they are. Their **owning repo** may relocate them under its own authority (see the amended discriminator and negative-spec below):

- `sentinels.json`
- `install-profile.json`
- `install-chain-state.json`

**Discriminator:** an artifact is swept **by the coordinator's own relocation** if and only if it is *named by this agent-install contract*. Contract-named (`install-status.json`, `chain-walk-<session-id>.json`) ⇒ the coordinator moves it to `<settings-home>/<repo-id>/`. Not named by this contract (`sentinels.json`, `install-profile.json`, `install-chain-state.json`) ⇒ the coordinator does NOT move it — and, because the contract does not govern it at all, its **owning repo** (project-rag / project-rag-ue-addon, not the coordinator) MAY relocate it under its own authority + directive. `setup-state.json` is governed by § Consumer durable-data plane below, not this addon-owned-runtime-state list.

**Negative-spec (scope-fence on the coordinator migration, NOT an eternal pin — per the `amend-516-marker-dir-vacate` ruling):** the coordinator's relocation does NOT sweep files this contract never named — that migration's scope is exactly the two contract-named files. A consumer MUST NOT repoint `sentinels.json`, `install-profile.json`, or `install-chain-state.json` **on the basis of *that coordinator relocation*** (it did not move them and makes no claim about them). This negative-spec fences the *coordinator migration's* scope; it does **not** pin these three to `~/.claude/<repo-id>/` in perpetuity. Because this contract does not name or govern them, their owning repo MAY relocate them to `<settings-home>/<repo-id>/` under its own authority — exactly as § Consumer durable-data plane (PM-accepted) sanctioned for a consumer's own durable data. project-rag is doing precisely this for all three (PM directive: zero durable `~/.claude` footprint): the host-written `install-profile.json` / `install-chain-state.json` relocate directly; `sentinels.json` additionally carries a host↔addon tier-2 **writer contract** (host `preflight.py` + `seed_project_sentinels.py`; `project-rag-ue-addon` seeds the tier-2 copy) that project-rag sequences with `project-rag-ue-addon-em` before moving — a coordination outside this contract's scope, not a §516 exception. Coexistence-by-vacating (neither repo writes the shared prefix) is strictly stronger than coexistence-by-boundary, which is why the move is sanctioned rather than blocked.

### Consumer durable-data plane

> Added by the consumer-durable-data-plane-uninstall-boundary plan (cluster 11) — DoE-altitude
> doctrine-seeding under PM direction (project-rag-em's inbound proposal, PM-accepted).
> Per [`cross-repo-communication.md`](./cross-repo-communication.md) § Doctrine seeding vs.
> code/install-surface change (lines 562-574), this is a legitimate direct wiki edit: it shapes *how*
> sibling repos understand a shared contract surface, authored from DoE altitude on PM direction, not
> a code/install-surface change to any sibling's own tree. The receiving repo's EM (project-rag-em) may
> amend on receipt.

The relocation boundary above (§500-518) governs **install-chain artifacts** — data tied to the
coordinator's own install/orient machinery (the two the coordinator relocates, plus the not-contract-named
files the coordinator leaves in place — which their owning repo may itself relocate per the 2026-07-21
amendment above). It is silent on a different category: **a consumer's own durable
application data**, which has no tie to the install chain and which the consumer owns end-to-end.

**Ruling:** `<settings-home>/<repo-id>/` MAY also serve as the sanctioned home for a consumer's own
durable application data — data the consumer reads/writes as part of its normal runtime operation,
independent of coordinator install/orient state.

**Worked example (project-rag):** `projects.json`, `sessions/`, `workstate-store/`,
`external-corpora/`, `structured-records/`, and `server.json` are all project-rag-owned durable data
with no install-chain role. project-rag MAY consolidate these under
`<settings-home>/project-rag/` rather than scattering them across ad hoc per-tool home-directory
locations.

**The discriminator (install-chain/marker vs. durable-data) — the crisp test a future reader applies:**

- **Install-chain / marker state** stays governed by §500-518 above: the two coordinator-relocated,
  contract-named files (`install-status.json`, `chain-walk-<session-id>.json`) and the three
  not-contract-named files the coordinator leaves in place (`sentinels.json`, `install-profile.json`,
  `install-chain-state.json`) — the latter three owning-repo-relocatable per the amendment
  to the § Relocation boundary above.
- **A consumer's own durable data** — data with no install-chain role, that the consumer owns
  end-to-end — MAY consolidate under `<settings-home>/<repo-id>/`.

**These are two planes sharing a prefix, NOT a contradiction of §516's negative-spec.** §516 forbids
repointing the *four* (now three) addon-owned-runtime-state files to `<settings-home>/<repo-id>/` "on
the basis of this relocation" — that negative-spec is scoped to those specific contract-named-adjacent
files, not to the prefix itself. A consumer consolidating its *own* durable data under the same prefix
is a distinct, sanctioned use of `<settings-home>/<repo-id>/` — not an end-run around §516. A reader
skimming both sections needs this spelled out, not inferred, because the same root path now hosts two
semantically distinct planes.

**Fourth enumerated use of the `<settings-home>` prefix.** Cross-reference
[`state-placement-law.md`](./state-placement-law.md) § Taxonomy (line ~38): that table enumerates the
uses of the `<settings-home>` prefix — (1) `install-status.json`/`chain-walk-<session-id>.json` under
`<settings-home>/<repo-id>/` (§ Visited-set protocol above); (2) the install-baton rendezvous
`state/handoffs/`, machine-shared and NOT scoped under `<repo-id>/`; and now (3) consumer durable data
under `<settings-home>/<repo-id>/` (this section) — one place enumerates all uses of the prefix so a
future reader doesn't have to reconstruct the taxonomy from separate wiki pages.

**Disambiguation — do not confuse project-rag's `setup-state.json` with coordinator's own setup-state
receipt.** Two near-identically-named files, different owners, different planes — pre-empt the grep
collision:

| File | Owner | Current/target location | Purpose |
|------|-------|--------------------------|---------|
| `setup-state.json` | project-rag | `~/.project-rag/setup-state.json` (current, hardcoded); `<settings-home>/project-rag/setup-state.json` (target — see § below) | project-rag's own per-machine setup-completion marker; a live cross-repo read contract. **example-game-repo is the one confirmed DIRECT file reader.** ue-addon consumes the receipt only via project-rag's path-agnostic `record_setup_state.py check-oriented` verb — NOT a direct file read — and was struck from the direct-reader set on 2026-07-09 (see § reader-enumeration Gate). |
| `coordinator-setup-state.yaml` | coordinator | `~/.claude/coordinator-setup-state.yaml` (unaffected by this section) | Coordinator's own per-machine setup-concluded + orientation milestone receipt — see [`coordinator-setup-state-receipt.md`](./coordinator-setup-state-receipt.md). Gitignored, gitignore-anchored, unrelated to the durable-data plane. |

These are unrelated files that happen to share the substring "setup-state" — a grep for `setup-state`
across this wiki will hit both; do not conflate them.

**`setup-state.json` folds into this durable-data plane** — it is not among the addon-owned-runtime-
state files that stay at `~/.claude/<repo-id>/`; `~/.claude/project-rag/setup-state.json` is absent
and `~/.project-rag/setup-state.json` is where project-rag's writer actually hardcodes it
(`Path.home()/".project-rag"/"setup-state.json"`), a location this contract never named or governed.
Target home:

```
<settings-home>/project-rag/setup-state.json
```

**This fold is gated behind a RECEIPT-BASED dual-read window — explicitly NOT a fixed-duration timer.**
`setup-state.json` is a live cross-repo read contract (example-game-repo's trio install-receipt gate reads
`:: completed_at` — the one confirmed DIRECT file reader; ue-addon consumes it only via project-rag's
own path-agnostic `record_setup_state.py check-oriented` verb, NOT a direct file read), so the writer
cannot move unilaterally without breaking a consumer mid-flight. The window closes — i.e. the legacy `~/.project-rag/setup-state.json` read may be
cut — only on the conjunction of **three receipts**, not on elapsed time:

1. **Writer moved** — project-rag's own writer has moved to the new plane path
   (`<settings-home>/project-rag/setup-state.json`).
2. **Consumer dual-read live** — each DIRECT reader (example-game-repo's trio gate) has confirmed its own
   dual-read (new path with legacy fallback) is live. ue-addon carries NO dual-read obligation: its
   consumption is verb-mediated (see the reclassification in the Gate below), so path resolution is
   delegated to project-rag's own `record_setup_state.py` and the writer move is transparent to it.
3. **Fleet-wide reader-enumeration clean** — see the precondition below: the enumeration returns
   exactly the known reader set, with no reader beyond it still legacy-only.

All three conditions must hold before ANY sibling repo cuts its legacy read. A EM reasoning from elapsed
time alone ("it's been N weeks, safe to cut") is reasoning outside this contract's discriminator and
MUST NOT cut the legacy read on that basis alone.

**Fleet-wide reader-enumeration PRECONDITION — a gate on the writer move, authored into contract text
so a future EM can gate the move by reading this contract, not the roadmap.** Before project-rag's
writer moves `setup-state.json` at all, enumerate every reader across the fleet by grepping each of the
following repos for literal `~/.project-rag/setup-state.json` / `.project-rag` / `setup-state.json`
read paths:

- project-rag (the owner's own tree — confirm no other internal reader was missed)
- project-rag-ue-addon (ue-addon) — **verb-mediated consumer, NOT a direct reader** (struck); a `setup-state.json` grep here returns only the path-agnostic `record_setup_state.py check-oriented ue_addon` CLI call, never a direct read path
- example-game-workbench-repo (example-game-repo)
- claude-klabauter (claude-klabauter)
- example-cockpit-repo (cockpit)
- the project-rag-hosted co-tenant cockpit addon (`addons/coordinator-cockpit-addon/_seam.py`)

**Gate:** the writer move is permitted only when this enumeration returns EXACTLY the known
**direct-reader** set — **example-game-repo** (the sole confirmed direct file reader). **ue-addon was struck from
the direct-reader set on 2026-07-09** (project-rag-ue-addon-em memo
`2026-07-09-project-rag-ue-addon-em-c11-setup-state-ueaddon-not-direct-reader`): its consumption is
verb-mediated — the only hit a `setup-state.json` grep returns in ue-addon's tree is the path-agnostic
`record_setup_state.py check-oriented ue_addon` CLI call, never a direct read path. Because path
resolution is delegated to project-rag's own script, the writer move is transparent to ue-addon and it
carries **no dual-read obligation**. **DETECT-THEN-FAIL-LOUD, not a silent scope extension:** if the
enumeration turns up any DIRECT reader beyond example-game-repo, that is a hard stop — the writer move does not
proceed until the newly-discovered reader is accounted for (added to the dual-read coordination, or
confirmed as a false-positive grep hit). A verb-mediated consumer (like ue-addon) is NOT a direct reader
and does not gate the move — but see the host-internal lockstep constraint immediately below. This
enumeration is a precondition on the writer move, not something this contract or this plan executes —
see the plan's Anti-scope for why the move itself is out of scope here.

**Host-internal constraint (project-rag's own, NOT a fleet gate) — reader-verbs move in lockstep with
the writer.** For verb-mediated consumers, project-rag MUST relocate its `check-oriented` /
`mark-oriented` reader-verbs to the new path in the SAME move as the writer. If writes go to
`<settings-home>/project-rag/setup-state.json` while `check-oriented` still reads
`~/.project-rag/setup-state.json`, every verb-mediated consumer's receipt check silently regresses
(reads the old path → no receipt → e.g. ue-addon's orientation-offer suppression fails open). This is
entirely within project-rag's own writer↔reader-verb consistency; verb-mediated consumers neither
observe nor gate the transition.

**Extension (install-baton-rendezvous-off-dotclaude plan):** the shared install-baton
rendezvous folder (`state/handoffs/` — install AND orient batons; see § The rendezvous below) is a
related but distinct relocation. It shares the same `<settings-home>` root prefix as the two artifacts
above but is NOT scoped under `<settings-home>/<repo-id>/` — it is machine-shared, not per-repo-id, and
lives at `$(coordinator-settings-home)/state/handoffs/`. Ledger/visited-set (this section) and the
rendezvous (§ The rendezvous) are both "per-machine install substrate," a plane distinct from
`$GIT_ROOT/state/` (per-repo work state) and from claude-klabauter's central meta-repo session state — see
`state-placement-law.md` § Taxonomy for the full breakdown and the row that ratifies this rendezvous.

### Uninstall boundary

> Added by the consumer-durable-data-plane-uninstall-boundary plan (cluster 11) — companion
> ruling to § Consumer durable-data plane above. Without this boundary, a durable-data plane is only
> half a contract: nothing would stop coordinator uninstall from silently destroying a consumer's
> durable subtree under the same `<settings-home>` root.

**Ruling: blanket-with-provenance is the DEFAULT.** Coordinator uninstall deletes only
coordinator-authored artifacts under `<settings-home>` — everything else under that root, including
consumer `<settings-home>/<repo-id>/` durable subtrees (§ Consumer durable-data plane), is
consumer-owned by default and **survives**. This is §516's discriminator inverted for deletion: the
coordinator deletes only what it wrote/named, exactly as it relocates only what it names.

**The coordinator-authored allowlist.** Uninstall removes ONLY the following five items,
derived by grepping every writer of `<settings-home>` (`$sh`) — this same enumeration is the one
implemented in `coordinator_core.install.uninstall_legs` (claude-klabauter)'s provenance-scoped teardown; the authored text here
and the implemented code there are SET-EQUAL by construction, not merely similar in shape. **The
five are gated in two tiers, not one:** four are full-remove-only; one is removed unconditionally
in BOTH end-states.

- `machine-local/` — the machine-local registry directory (full-remove only)
- `bin/` — the settings-home resolver family, distinct from the `~/.claude/bin` compat forwarders
  which are a separate teardown leg (full-remove only)
- `settings-manifest.md` — written directly by `install-substrate.py` and copied by the migration
  script (full-remove only)
- `state/handoffs/` — the install-baton rendezvous, see the Extension note above (full-remove only)
- `.coordinator-venv/` — **removed unconditionally in both `full-remove` AND
  `revert-to-marketplace`**

**`setup/` is explicitly EXCLUDED from this allowlist.** Two coordinator-authored sources disagree on
whether `setup/` is settings-home substrate (`machine-local-registry.md` §11's Namespace table lists it
as settings-home namespace; `state-placement-law.md`'s Relocated-surfaces table lists it as relocated to
`<settings-home>/setup/`), but the migration script's own execution-time behavior is the authoritative
signal, not the wiki tables: claude-klabauter `coordinator_core/install/substrate_migrate.py`'s header comment states `setup/` is
"intentionally NOT migrated: nothing reads setup/ from settings-home at runtime (coordinator continues
to read `~/.claude/setup/`)," and `install-substrate.py` writes `SETUP_DEST` to
`${_install_base}/.claude/setup/`, not to settings-home. Code that runs beats a stale wiki inventory —
`setup/` therefore lives at `~/.claude/setup/`, NOT under `<settings-home>`, and is NOT on this
allowlist.

**The discriminator is BINARY, not three-way: allowlist-delete / default-preserve.** The coordinator
deletes ONLY entries on its own authored allowlist above; every other top-level entry under
`<settings-home>` — including any consumer `<repo-id>/` durable subtree, registered or not — is
preserved by default. There is no "is this a plausible consumer subtree" heuristic to apply and none is
needed: absence from the allowlist IS the preservation signal. **Detect-then-fail-loud is reserved for
its real job** — a coordinator-authored allowlist artifact that fails to remove (surfaced via the
existing `overall_rc` error-accumulation + stderr-on-failure idiom) — not for classifying ambiguous
entries. There are no ambiguous entries under this discriminator.

**The optional per-repo-id keepset is a NARROWING, not the primary mechanism.** A consumer MAY
additionally register a keepset to protect coordinator-adjacent paths it wants preserved beyond the
blanket default. This is explicitly a narrowing on top of blanket-with-provenance, not a
registration-as-default model: the blanket default is chosen precisely because it does not depend on
every consumer registering anything — an **unregistered** consumer's durable data is still protected by
the blanket default, whereas a registration-as-default model would silently delete an unregistered
consumer's durable data on uninstall. That silent-deletion failure mode is exactly the half-a-contract
problem this boundary exists to prevent.

**Forward-guard.** Cluster 1's unified resolver exposes exactly three verbs (`--clone-root`,
`--content-root`, `--percolate-root`) and does NOT touch the coordinator-settings-home seam — there is
no live `11←1` edge today. This note is a forward-guard for a hypothetical future extension of that
resolver, not a statement of a current dependency.

**Why disk, not memory:** each dispatched subagent runs as an independent process with its own EM context. The parent EM's in-memory state is invisible to subagents. A visited-set held only in the parent's memory will not prevent a subagent from re-dispatching a dep the parent has already claimed — because the subagent has no parent-memory access. Disk is the only shared state that survives the process boundary.

#### Soft-dep resolution — resolve the settings-home prefix defensively

A **soft-dep** consumer (one that takes coordinator-claude as a soft, not hard, dependency) hits a real ordering gap: the chain-walker writes the visited-set *before* the soft-dep presence check completes. `coordinator-settings-home` is a **coordinator-claude bare-name CLI** — it rides in the mutable coordinator-claude clone, not in the consumer's own install. On the soft-dep-**absent** path, the consumer is asked to resolve the settings-home prefix via a CLI that lives in the very dependency it hasn't yet confirmed present. A naive `$(coordinator-settings-home)` then either empty-substitutes — `mkdir -p /<repo-id>`, writing at filesystem root — or hard-fails, regressing the soft-proceed path.

**Ruling:** a consumer MUST resolve the settings-home prefix **defensively** for the visited-set write. If `coordinator-settings-home` is unavailable, fall back to `~/.claude/<repo-id>` for the (then-unused) visited-set rather than allowing an empty substitution.

**Canonical shell idiom:**
```
_SETTINGS_HOME="$(coordinator-settings-home 2>/dev/null || true)"
VISITED_DIR="${_SETTINGS_HOME:-${HOME}/.claude}/<repo-id>"
```

**Why this is safe:** the absent-seam case is exactly when the visited-set goes unused (the chain terminates at the missing soft dep), so the fallback never bridges live content — it only keeps the soft-proceed path from crashing. (This assumes `coordinator-settings-home` either succeeds with a valid absolute path or fails cleanly — not hardened against a malformed-but-zero-exit stdout.)

**Applies to every soft-dep consumer** of the install-chain contract, not any single repo — this is a generic property of the resolution-before-confirmation ordering, not a one-off fix.

#### Visited-set file schema

```json
{
  "session_id": "<uuid>",
  "started_at": "<ISO8601 timestamp>",
  "visited": ["<dep-id-1>", "<dep-id-2>"]
}
```

| Field | Type | Description |
|---|---|---|
| `session_id` | `string` (UUID) | Generated once at top-level invocation. Propagated to all recursive subagents via the constructed-prompt template (`$SESSION_ID` substitution variable). |
| `started_at` | `string` (ISO8601) | Timestamp of visited-set creation. Used for stale-file detection. |
| `visited` | `array<string>` | Dep IDs already claimed for walking. A dep found here is skipped — "already walking <id>, skipping". |

#### Lifecycle

1. **Top-level invocation start:** delete any `chain-walk-*.json` files in `<settings-home>/<repo-id>/` older than 1 hour (stale-cleanup). Then create a new `chain-walk-<session-id>.json` with an empty `visited` array.
2. **Before each clone+walk:** read the visited-set file. If the dep ID is already in `visited`, log "already walking <dep-id>, skipping" and continue to the next dep.
3. **Before dispatching the subagent:** atomically append the dep ID to the `visited` array using a stdlib-only read-modify-write (Python `json` module — no `pyyaml` or other non-stdlib dep):
   ```
   python -c "import json, os, sys; p=sys.argv[1]; d=json.load(open(p)); d['visited'].append(sys.argv[2]); json.dump(d, open(p,'w'), indent=2)" <path-to-visited-set> <dep-id>
   ```
4. **Subagents** read the same file (path derived from `$SESSION_ID` passed in the constructed prompt) and follow steps 2–3 for their own deps.

#### Stale-cleanup

At top-level invocation start, delete `chain-walk-*.json` files older than 1 hour. This ensures a crashed or abandoned previous session does not block a new walk.

---

## Install-spinoff layer — durable multi-repo install under coordinator

> The §Skill chain-walker model dispatches recursive subagents within a single
> session. That holds for a short walk, but installing several repos in one vanilla session overruns
> its context — a session asked to install a whole chain can lose the thread and loop. The install-spinoff layer makes a multi-leg install **durable**
> by handing the work to a coordinator-ified session that has a flight recorder, the Tasks API, and
> saved-to-disk handoffs/spinoffs. The recursive walker and this layer are not alternatives — the
> walker is how a single repo locates and probes its direct deps; this layer is how *several legs*
> are sequenced across the load-bearing coordinator reboot without losing state.

**The shape is one spine, N spinoffs** — exactly what `coordinator:roadmap-planning` produces.
Coordinator onboarding (`continue-onboarding-and-installation.md`) is the **handoff**: the genuine
continuation across the reboot, same workstream. Each *other* repo the operator queued is a
**spinoff**: a fork of a different install topic, `predecessor: none`. Continuation vs. fork — each
in its proper folder, each with its native semantics (no lineage exception to explain).

**Coordinator is standalone-first and chain-agnostic.** It installs and runs on its own; it is the
root that other repos *can* build on, not part of any mandatory chain. Coordinator hardcodes no
downstream leg by name: every leg is whatever the operator queued. Nothing in the coordinator surface
hardcodes a particular chain, order, or leaf repo — that knowledge lives in each downstream repo and
arrives only as the spinoff that repo seeds.

> **deep-research is NOT a downstream install leg.** It is folded into the coordinator plugin for
> everyone (`deep-research-claude` is archived read-only on GitHub, not a live, separately-installable
> repo). If you have coordinator, you have deep-research. It carries
> **no opt-in** (no pre-restart "do you want deep-research?" question), **no separate install**, **no
> separate orient leg**, and **no `install_chain_order:` baton** — it is not seeded into or discovered
> from the rendezvous/handoffs folder. Treating deep-research as coordinator's "one downstream by
> name" with a seeded install-leg baton discovered via the Step-0 sweep is a **vestige of the
> deprecated separate-repo model** and is affirmatively false. For a genuine install-leg baton, the
> reference shape is `coordinator/templates/handoffs/install-claude-klabauter.md` (claude-klabauter is a real
> coordinator-seeded install leg).

### Authorization — the pre-restart question is the spinoff gate

Spinoffs are normally PM-authorized and keyword-gated (`/spinoff`); EM-initiated spinoffs are
forbidden (`docs/wiki/spinoff-handoffs.md`). Install-leg spinoffs are the **one sanctioned
non-`/spinoff` creation path**, and they do not erode that gate: the authorization is captured at the
install's **pre-restart question** ("what else do you want to install?"). The operator selecting a
leg there *is* the human authorizing that fork — the same authorization `/spinoff` captures, captured
at a different but equally explicit moment. A leg never appears as a spinoff unless the operator chose
it; the script merely materializes a choice the human already made. (Full carve-out: `spinoff-handoffs.md`.)

### The rendezvous: the standard handoff folder

```
$(coordinator-settings-home)/state/handoffs/
```

Install legs are ordinary `/pickup`-valid **spinoffs** (`kind: spinoff`, `predecessor: none`) dropped
into the **standard handoff folder**, re-rooted at the per-machine settings-home prefix — the *same*
place `/spinoff` and `coordinator:roadmap-planning` already write spinoffs, now resolved through
`coordinator-settings-home` instead of a hardcoded `~/.claude`. This is the load-bearing reason for the
spinoff frame: `query-records --type handoff` globs `state/handoffs/*.md` under the resolved
settings-home root, `/pickup` Step 1 (Classify, Load, and Reconcile Against Reality) classifies a `kind: spinoff` file there as a spinoff, and
`/workday-start` surfaces it under "spinoffs awaiting pickup" — all unchanged. There is **no new folder
and no new convention**: the folder is still `state/handoffs/` — only its root moved, from
`~/.claude/` (legacy) to `$(coordinator-settings-home)/` (current). A downstream repo's whole
obligation is "drop a `kind: spinoff` baton (carrying `install_chain_order:`) into the rendezvous
handoffs folder at `$(coordinator-settings-home)/state/handoffs/` (inline fallback:
`${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings/state/handoffs` — see `state-placement-law.md`)."
The `install_chain_order:` tag is what distinguishes an install leg from the coordinator onboarding
handoff in the same folder. They do not linger as stale batons because coordinator's Step 0 builds an
install-chain spine that drives every leg to conclusion before the install workstream is completed
(see `coordinator/templates/plans/install-chain-tracking.md`).

> Do **not** invent a `tasks/spinoffs/` (or `tasks/install-chain/`) directory: no coordinator
> machinery scans it, so a baton dropped there is invisible to `/pickup`, `query-records`, and
> `/workday-start`. The standard `state/handoffs/` folder is the only surface all three already read.

> **Compat read (transition window).** A consumer resolving the rendezvous MUST read-new-first: try
> `$(coordinator-settings-home)/state/handoffs/`, and only if a baton is not found there, fall back to
> the legacy `~/.claude/state/handoffs/` location for the duration of the migration window. This is a
> read-new-first, legacy-fallback compat read, not a permanent dual-write — new seeds target
> settings-home only.

### Spinoff frontmatter contract

Each conforming repo seeds ONE spinoff per install leg, with `/pickup`-valid spinoff frontmatter plus
the install-chain fields below. A repo MAY additionally seed a **separate orient leg** (a second
`kind: spinoff` baton carrying the post-install orientation) — see § Orient-leg discovery and the
`orient_after:` field.

| Field | Type | Required | Description |
|---|---|---|---|
| `repo` | `string` | yes | The leg's `repo_id` (matches the manifest). The spine key for the leg. |
| `install_chain_order` | `integer` | install legs only | Relative install position (lower = installed earlier; coordinator = 0). The coordinator EM sorts the spine by this; **absent → discovered order**. Also the tag the Step 0 sweep greps to distinguish install legs from both the onboarding handoff AND orient legs, so an install leg MUST include it and an orient leg MUST omit it. |
| `plan` | `string` | no | Relative path to a leg plan file, when the leg warrants one. Plans live in the seeding repo's `docs/plans/`; the spinoff names the path. |
| `orient_after` | `string` | orient legs only, optional | Cross-capability ordering hint for an orient leg that must run after an install leg *other than* its own paired one (the "knowledge-before-control" case). Value is **`<repo-id>`** (the `repo:` of the install leg this orient must follow) **or the sentinel `"leaf"`** (after the highest-order install leg present in the chain). **Absent → the orient leg interleaves after its own install leg ONLY if that install is the leaf; paired to a non-leaf install it defers to the absolute tail** (batch-equivalent, safe — see § Provision sub-axis). To interleave a non-leaf orient leg mid-chain, seed `orient_after:` explicitly (this field is the opt-in). The value is **NOT** an `install_chain_order:` integer: install-order integers are operator-queue-relative (assigned at Step 0 from whatever leg-set the operator picked), so a seeding sibling cannot predict the integer at seed-time — `<repo-id>` is the stable, sibling-predictable identifier. **Edge (a):** the named `<repo-id>` is absent from the operator's queued chain → the dependency is unsatisfiable this session; the orient leg falls back to unpaired-tail ordering AND the spine surfaces `"orient_after: <repo-id> unmet — named leg not in chain"` (visible, not dropped). **Edge (b):** the named `<repo-id>` is present but `deployment_state: awaiting_gate` → the orient leg inherits the deferral (orders at/after the gated leg's tail, consistent with § Provision sub-axis `awaiting_gate` deferral). `"leaf"` needs no edge handling — it resolves to whatever the highest install leg is at walk-time. |

Base spinoff fields are required per the canonical spinoff schema (`spinoff-handoffs.md` § Frontmatter
schema): `title`, `created`, `kind: spinoff`, `status: active`, `predecessor: none`,
`authoring_session:` (the audit trail back to origin that replaces the predecessor link — for an
install leg, name the install + the operator's opt-in), `workstream:`, plus `deployment_state:
ready_to_fire`, `pickup_ready: true`, `scope:`. See
`coordinator/templates/handoffs/install-claude-klabauter.md` for the reference shape (claude-klabauter is a
genuine coordinator-seeded install leg; deep-research is NOT — it is folded into the coordinator
bundle, see § the deep-research callout above).

#### Orient-leg discovery

An orient leg is a **separate** `kind: spinoff` baton carrying a repo's post-install orientation,
seeded alongside (not folded into) its install leg. Because orient legs deliberately omit
`install_chain_order:` (orientation is post-install onboarding, not an install-chain leg), the
install-leg sweep cannot see them. Step 0 therefore runs a **second, additive discovery sweep** —
reading the same rendezvous folder, `$(coordinator-settings-home)/state/handoffs/` (compat-read:
legacy `~/.claude/state/handoffs/` fallback during the transition window) — that identifies an orient
leg by the conjunction:

> `kind: spinoff` **AND** no `install_chain_order:` **AND** (filename matches `orient-*.md` **OR**
> the `summary:`/`title` frontmatter matches a **word-boundary** "orientation").

The discriminator operates on **baton shape only** — it names no repo. The `kind: spinoff` gate and
the **word-boundary** "orientation" match (not a bare substring) are load-bearing: they keep a
recovery handoff or a plan baton that merely *mentions* "orientation" (e.g. "lost orientation after
crash", "spine orientation rework") from being falsely swept into the operator's install walk. The
`orient-*.md` filename arm is exact; the `summary:`/`title` arm is the human-legibility convention
(§ Orientation-supersession) promoted here to *also* serve as a discovery signal. This is an
**additive sweep over existing baton shape**, not a new `kind:`, baton type, or folder.

### The two roles

- **Downstream repos SEED.** A conforming repo's installer drops its `kind: spinoff` baton into
  the rendezvous handoffs folder at `$(coordinator-settings-home)/state/handoffs/` (see
  `state-placement-law.md`). Seeding is a cheap `cp`/`sed`/`curl`, not a heavy install — it can run
  for every chosen leg *before* the coordinator reboot (per the pre-restart question, § Authorization
  above), so the durable session sees the whole chain at once. Idempotent
  (overwrite-on-reseed). Seed via `cp`/`sed`, **not the Write tool** — a Write into `state/handoffs/`
  without an active authoring skill trips the unauthorized-handoff nudge; `cp` does not.
  `claude-klabauter` seeds its own spinoff from a shipped template
  (`templates/handoffs/install-claude-klabauter.md`) via coordinator's onboarding flow — a coordinator-seed
  rather than a self-seed (a design choice, not a structural necessity — see § Which model a new
  node adopts below). (deep-research is NOT a leg — it is folded into the coordinator bundle for
  everyone and seeds no baton; see § the deep-research callout above.)
- **Coordinator STITCHES + DRIVES.** Post-reboot, `continue-onboarding-and-installation.md` Step 0
  greps `$(coordinator-settings-home)/state/handoffs/` (compat-read: legacy `~/.claude/state/handoffs/`
  fallback during the transition window) for `install_chain_order:` legs, writes a lightweight
  install-chain spine listing every leg found, and drives each to conclusion via `/pickup`. This is
  the durability a vanilla session lacked — and it is agnostic: it tracks whatever spinoffs are
  present, asserting no fixed set. Because coordinator is the DAG root (`direct_deps: []`), its
  `--phase seed-install-spinoff` is a deliberate no-op: it confirms it is the spine, prints a one-line
  explanation, and exits 0 without writing any install-status or baton state — the only
  coordinator-seeded baton is `claude-klabauter`'s (from `templates/handoffs/install-claude-klabauter.md`), seeded
  by coordinator's own onboarding flow, not by the leaf-walk phase.

**Which model a new node adopts — the discriminator.** A generic downstream leaf node **self-seeds**
(§ Guidance for conforming (downstream) repos, step 1): its own installer drops its `kind: spinoff`
baton into the rendezvous handoffs folder. Coordinator-seed is the alternative model — used today for
`claude-klabauter` by continuity convention, not because any repo is structurally barred from
self-seeding. **Seeding-ownership is ratified "both":** at a per-machine settings-home, no repo hosts
the rendezvous folder itself, so self-seed and coordinator-seed are uniformly valid for any repo —
either model reaches the identical drop target. Being a hard *upstream dependency* of other repos (e.g.
`project-rag`) does **NOT** make a repo coordinator-seeded — it still self-seeds. (A
coordinator-*bundled* capability such as deep-research is not seeded at all: it ships inside the
plugin for everyone and is never an install leg — see § the deep-research callout above.) If you are
adding a new leaf node: **self-seed** is the default; use coordinator-seed only if you have a specific
continuity reason, as claude-klabauter does.

### The spine is cold-start-only — downstream runbooks route post-restart to `/workday-start`

**The leg/spine seeding asymmetry is correct by design, not a gap to close.** Leg batons are
shell-seeded and **idempotent** (overwrite-on-reseed) because each per-leg install is genuinely
re-runnable. The spine (`continue-onboarding-and-installation.md`) carries coordinator's *one-shot*
onboarding — the first-time co-write of `CLAUDE.md` and the First Officer framing choice — so it is
**not idempotently re-seedable**: re-seeding it would resurrect that first-time conversation against
an operator who made those choices months ago. The spine seeds once, gets consumed, and stays gone.

> **CLI-install.** Coordinator installs via the native `claude plugin` CLI, and its cold-start
> install path has **no `install.sh` and no scripted `cp`** — nothing auto-seeds the
> spine. On the **solo** coordinator install (the common OSS case) there is no multi-leg chain to
> orchestrate; `/coordinator:install` drives the single leg to conclusion (it records the
> `setup_concluded` receipt) and handles onboarding directly, post-restart. The spine **template
> remains** in the repo as the orchestrator a multi-leg chain consumes if one is ever seeded; the
> contract does not rely on the CLI-install path to seed it.

**Three verbs, three jobs — don't conflate them when a remediation message needs to redirect a
bootstrap-seeking agent.** <!-- src: plan21-026, plan21-027, plan21-028 --> `/coordinator:install`
is the canonical machine-bootstrap remediation (Phase 3 of it — machine-local registry substrate,
env vars, venv, scaffolding — is fully agent-runnable via `--non-interactive`, no human keystroke
required: every `AskUserQuestion` site in it carries a non-interactive fallback). `/coordinator:setup`
is the install-chain DAG-walker described throughout this doc — it bootstraps nothing on its own.
`/coordinator:repo-setup` is per-project consumer scaffolding, a third and distinct verb again. A
remediation string that names only `/coordinator:setup` when the actual need is bootstrap sends an
agent to a no-op; name `/coordinator:install` for bootstrap remediation specifically.

**Negative-spec for downstream runbooks.** A downstream bootstrap runbook (e.g. a example-game-repo
`/example-game-repo:install` re-run that re-seeds the install-chain legs) MUST NOT print a hard
`/pickup state/handoffs/continue-onboarding-and-installation.md` as its post-restart instruction.
That path dangles on every re-run / already-onboarded machine, because nothing re-stages the spine
(and nothing should). There is **no hard-`/pickup`-of-spine site at all** — coordinator's own
cold-start playbook does not seed the spine (no §1f `cp`), so it joins the same pattern as every
downstream: route post-restart to `/coordinator:install` (solo
install, environment wiring) and `/workday-start` (when downstream legs were queued).

**The robust default post-restart entry is `/workday-start`.** It triages every `ready_to_fire` handoff in
`state/handoffs/` — the freshly-seeded install legs always, plus the spine when (and only when) a
cold-start staged one. It is the canonical reader of that folder named throughout this contract; the
spine's own Step 0 build runs whenever the spine is present, so nothing is lost. A downstream that
trusts the printed command gets correct behavior on both fresh and re-run machines.

**An equally-valid alternative — a curated, ordered direct `/pickup` of the seeded *leg* batons.** The
sanctioned test is the **safety goal, not the specific verb**: (a) no hard `/pickup` of the **spine**
path (it dangles on re-run — the negative-spec above), and (b) the batons it pickups are idempotently
re-seeded (§ Guidance step 1), so they are always present on both fresh and re-run machines. A
downstream whose operator-intent is a single capability install — **leaf-is-entry-point**, e.g. a
fresh operator who pasted a repo link and said "install this" — MAY instead print a curated ordered
leg-walk that hard-`/pickup`s each seeded **leg** baton in install order, each leg pointing to the
next. That carries none of the dangling-path failure mode (leg batons are never the spine; they are
always re-seeded) and is more operator-legible than `/workday-start`, whose name and day-orientation
purpose are a non-sequitur to an operator mid-install. Choose by operator-intent: `/workday-start`
for a general day-orientation entry; the curated ordered leg-walk for a leaf-is-entry-point
single-capability install.

> Precedent: example-game-repo's own leg-walk curates a direct ordered `/pickup` of its leg batons rather than
> `/workday-start` (documented there as "a day-orientation sweep, a non-sequitur mid-install"). This
> subsection ratifies the **safety goal** (no dangling-spine hard-pickup) as the contract — satisfiable
> by `/workday-start` **or** by a curated ordered-leg `/pickup` — so the dangling-path failure does not
> recur for other downstreams. See `cross-repo/archive/2026-06-17-spine-staging-asymmetry.md`.

### Guidance for conforming (downstream) repos

This is the "teach the other side in a wiki, don't code their ceremony" half of the contract (per
`cross-repo-communication.md` § When lifting a cross-repo primitive). To align:

1. Add a **seed step** to your standalone setup script that writes a `kind: spinoff` baton (with
   `repo`, `install_chain_order`, `authoring_session`) into the rendezvous handoffs folder at
   `$(coordinator-settings-home)/state/handoffs/` (inline fallback:
   `${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings/state/handoffs` — see `state-placement-law.md`)
   via `cp`/`sed` (not the Write tool). Idempotent. If coordinator is not yet installed, drop the
   spinoff first, then run the coordinator install — so it is waiting when the durable session starts.
2. If your leg needs a plan, write it to your `docs/plans/` and name it via the spinoff's `plan:`
   field.
3. Adopt the **coordinator-lite-before-reboot** pattern: verify a minimal coordinator surface (all
   pre-reboot dependencies present) before instructing the operator to restart, so the durable
   session can follow the coordinator-style pickup flow.
4. If your addon wants to supersede another repo's orientation, add `supersedes: <orientation-id>` to
   the spinoff baton you seed in step 1. Use the same `cp`/`sed` seeding discipline — **not the Write
   tool** — and seed before the coordinator reboot (same gate as step 1) so the baton is present when
   Step 0 builds the spine. Publish your own orientation as a normal spinoff leg. The superseded repo's
   orientation file is not modified; it remains the correct default when your baton is absent. Neither
   side codes the other's ceremony: your addon seeds the `supersedes:` assertion; coordinator's
   spine-builder resolves it at Step 0.
4a. **To seed a separate orient leg** (independent of step 4 — any repo seeding orientation as its own
   baton follows this step, supersession optional), drop a second `kind: spinoff` baton that the
   § Orient-leg discovery sweep will find: name the file `orient-<stem>.md` **and/or** set its
   `summary:`/`title:` to include a word-boundary "orientation", and **omit `install_chain_order:`**
   (its presence would misclassify the baton as an install leg). Pair it to your install leg by matching
   `<stem>` to your install leg's `repo:` id (longest-prefix wins, so `orient-<repo>-<addon>` binds to
   the addon leg, not the host; an equal-longest tie is surfaced as ambiguous, never auto-paired). Use
   the same `cp`/`sed` seeding discipline (**not the Write tool**) and seed it **before the coordinator
   reboot** — the same seed-before-reboot gate as install legs (§ Orient-leg discovery; same gate as
   § Guidance step 1): an orient baton that arrives after Step 0 is invisible to the spine for that
   session. If the orient leg depends on a *later* install leg (knowledge-before-control),
   add `orient_after: <repo-id>` or `orient_after: "leaf"` (§ Spinoff frontmatter contract).

5. For your **post-restart instruction**, print either `/workday-start` **or** a curated, ordered
   direct `/pickup` of your seeded **leg** batons (in install order, each leg pointing to the next) —
   **not** a hard `/pickup state/handoffs/continue-onboarding-and-installation.md`. The hard
   prohibition is narrowly on the **spine** path: it is cold-start-only and does not exist on
   re-run / already-onboarded machines. Both sanctioned options satisfy the same safety goal — no
   dangling-spine hard-pickup, and (for the leg-walk) the legs are idempotently re-seeded (step 1) so
   they are always present. Print `/workday-start` for a general day-orientation entry; print the
   curated ordered leg-walk when your operator-intent is a single capability install
   (leaf-is-entry-point) and handing the operator each next install step in order is the clearer UX.
   See § The spine is cold-start-only.

Coordinator owns only the agnostic stitch (sweep + spine + drive); each downstream repo owns its own
seeded spinoff and its own install steps. Neither side codes the other's ceremony.

### Orientation-supersession

An addon-seeded `kind: spinoff` baton MAY carry a `supersedes:` field to assert that its orientation
should be preferred over another repo's orientation **when that baton is present at spine-build time**.

```yaml
supersedes: <repo>-orientation   # e.g. project-rag-orientation
```

The value is an **orientation identifier** — an opaque id the superseded repo publishes. The
conventional form is `<repo>-orientation` (for example, `project-rag-orientation`), but that example
is illustrative; the coordinator treats the value as an opaque string and asserts no canonical form.
This keeps coordinator agnostic: no single consumer id reads as the reference shape.

**No new `kind`.** Orientation-supersession rides the existing `kind: spinoff` frame. The
`supersedes:` field is additive frontmatter on a normal spinoff. No new baton *type* and no new
folder. (This bars new baton *kinds/types* — it does **not** bar the additive orient-leg *discovery*
sweep over existing baton shape described in § Orient-leg discovery; that sweep introduces no new
`kind:` value, only a second read over the same `state/handoffs/` batons.)

**Conditional and live — this is the load-bearing semantic.** The superseded orientation is **never**
marked `status: superseded`, and there is **no** `superseded_by:` back-pointer written to it.
The superseded orientation remains the correct default when the declaring baton is absent. Supersession
is **resolved at spine-build time** (Step 0 of `coordinator/templates/handoffs/continue-onboarding-and-installation.md`)
by the presence or absence of the declaring baton in `state/handoffs/` — resolved via
`$(coordinator-settings-home)/state/handoffs/` (compat-read: legacy `~/.claude/state/handoffs/`
fallback during the transition window) — not by a status flip, not by
a pointer, not by a registry entry. **Supersedes resolution runs AFTER the orient-leg discovery sweep**
(§ Orient-leg discovery), not before: a supersedes assertion can only drop a default orientation the
spine has actually discovered, so the orient sweep must populate the orient-leg set first. Contrast
this with the existing memo/handoff `status: superseded`,
which is a terminal mutation: the superseded artifact is dead and stays dead. Orientation-supersession
is different: it is live and conditional on baton presence. Removing or not seeding the baton restores
the default orientation exactly as if the field had never existed.

**Seed-before-reboot discipline.** A conforming repo that wants its baton to be in effect MUST seed it
**before** the coordinator reboot — the same pre-reboot seeding discipline already required for install
legs (§ Guidance for conforming repos, step 1). The install-chain spine is built once at Step 0 of the
durable session; a baton that arrives after Step 0 is not visible to the spine for that session.

**Legibility + discovery convention — `summary:` field.** Orientation legs SHOULD include the word
"orientation" in their `summary:` (or `title:`) frontmatter field so the spine is human-readable at a
glance (e.g., `summary: "<repo-id> orientation"`). This keyword now serves **two** roles: legibility
(a human reads the spine at a glance) **and** one arm of the § Orient-leg discovery sweep (a
word-boundary "orientation" match is a discovery signal). It remains additive frontmatter on the
existing `kind: spinoff` frame — NOT a new `kind`. The companion discovery arm is the `orient-*.md`
filename, so a leg that carries either signal (and omits `install_chain_order:`) is discovered.

### Provision sub-axis

Install, provision, and orient are three distinct sub-steps, not one monolithic phase:

- **Install** — the synchronous chain: fetch, wire, validate. Completes in one session. Gate-bound:
  the spine will not advance past an install leg that hasn't reached `status: complete`.
- **Provision** — long-running background work triggered by install (example: project-rag's
  ~1-hour index build). A slow provision step runs in the **background** and does **not** block
  the synchronous install chain. The spine does not wait on it; install completes, the session
  continues, and provision catches up asynchronously.
- **Orient** — the coordinator's first durable session for a leg after install; it **opens with
  co-writing `CLAUDE.md` together** (the first customization of the contract), then walks the operator
  through what was installed. See `continue-onboarding-and-installation.md` for the install → reload
  → orient flow.

**Orient is a separate, interleaved baton — default-on, not a batch/return-later sub-axis.** A repo
MAY seed its orientation as a **separate `orient-<stem>` `kind: spinoff` baton** (§ Orient-leg
discovery), paired to its install leg by longest-prefix stem and interleaved **immediately after**
that install leg in the spine — not batched to the end of all installs and returned to later. The
install leg's `not-yet-oriented` state below is **cleared by picking up the paired orient baton**;
the two are one leg's lifecycle viewed from the install side (a sub-axis state) and the orient side
(a discoverable baton). A `ready_to_fire` orient leg with no `orient_after:` surfaces right after its
paired install leg **only when that install is the leaf** (highest `install_chain_order:` — then
"after its install" coincides with the absolute tail, safe by construction); **paired to a non-leaf
install it DEFERS to the absolute tail** (batch-equivalent, known-safe) and is surfaced as
`"ready_to_fire orient leg paired to non-leaf install <repo-id> — deferred to tail; seed orient_after:
to interleave mid-chain"`. A non-leaf orient leg may carry an unstated dependency on a *later* install
(the knowledge-before-control case: an addon's knowledge orientation reads a surface a later-installed
repo provides), so mid-chain firing without an explicit anchor is unsafe — **mid-chain interleave of a
non-leaf orient leg is opt-in via `orient_after:`, never the silent default** (detect-then-fail-loud).
An `awaiting_gate` orient leg defers to **after the last install leg (absolute tail)**.
An `orient_after: <repo-id>` leg is an **anchor** — it surfaces immediately after the *named* install
leg (mid-chain, not necessarily the tail); `orient_after: "leaf"` anchors after the highest install
leg. **Pairing is by longest-prefix stem; if two install legs tie as equal-longest prefix the orient
leg is treated as ambiguous/unpaired and surfaced as `"ambiguous pairing — N candidate install legs"`,
never auto-picked** (detect-then-fail-loud). **When one orient leg carries BOTH `orient_after:` AND its
own `awaiting_gate`,** resolve the `orient_after:` anchor position first, then apply the `awaiting_gate`
tail-deferral relative to that anchor (both push tail-ward, no conflict — pinned for determinism).
Orientation still happens by default, just ordered correctly.

**Per-leg state the spine tracks** reflects this three-step structure. A leg that has been installed
but whose background provision has not yet finished is in a distinct intermediate state:

| State | Meaning |
|---|---|
| `installed` | Synchronous chain complete; no background work pending |
| `installed / provisioning (ETA ~Xm)` | Synchronous chain complete; background provision in flight |
| `not-yet-oriented` | Install and provision complete; first-orient session not yet run |

The long-lived state a human-readable spine entry carries is one of these three — not the generic
"in progress" of the install phase. Conforming repos that trigger a slow provision step SHOULD
write their install-leg baton with an estimated ETA in the `provision_eta:` frontmatter field so
the spine can surface a human-readable estimate.

## chain-preinstall phase — sanctioned pre-restart full-install seam

<!-- Spec backlink: docs/plans/2026-06-17-chain-preinstall-phase-vocabulary.md -->

> Minted at the DAG root (coordinator-claude). This section
> is the canonical vocabulary every leg in the install chain honors; the section name is the
> cross-repo-converged phase name.

### Phase name and rationale

`chain-preinstall` is minted top-down at the DAG root, mirroring the same pattern as
`seed-install-spinoff` — a cross-repo-converged phase name every leg honors to avoid
bottom-up variant drift. The installer for each repo in the chain invokes its own setup
script with `--phase chain-preinstall` to perform synchronous script-level install work
**before** the single MCP/skill-registration restart that transitions to the durable
coordinator session.

### Valid-when consent predicate

`--phase chain-preinstall` is **valid-when** a non-empty chain-walk consent token
(`$COORDINATOR_CHAIN_PREINSTALL_CONSENT`, minted by the operator-run install skill at the pre-restart
question and propagated through the chain walk) is present in the environment — i.e. inside
a consented chain walk, not a bare agent-direct invocation.

**Three auth layers** govern agent-mode invocation of any setup script. Downstream
implementors must not conflate them:

1. **Repo-scoped run-mode env var** (`EXAMPLE_GAME_REPO_RUN_MODE=agent` / `COORDINATOR_RUN_MODE=agent`
   — see § Dual-mode script UX Step (a)) — detected at the top of the script to distinguish
   agent context from human-interactive context.
2. **Override-flag pair** (`override_flags.skip_dep_check` + `override_flags.accept_hallucination_risk`,
   per the upstream manifest, see § Walker composition) — the explicit acknowledgment that the
   agent accepts missing-dep risk.
3. **`$COORDINATOR_CHAIN_PREINSTALL_CONSENT` consent token** — introduced **alongside**, not instead of,
   layers (1) and (2). This token is the redirect guard specific to consented chain walks:
   its non-empty presence proves the operator-run install skill set it during this chain walk.
   It is a redirect guard at the **same trust altitude** as the override-flag pair, NOT a
   capability token and NOT validated against the live session — presence is the only check.

**Token source.** The token carries the chain-walk session id — the same UUID the visited-set
protocol already propagates as `$SESSION_ID` (→ § Visited-set protocol; template substitution
variable `$SESSION_ID` at the constructed-prompt template). Token value equals `$SESSION_ID`;
a distinct value buys nothing while presence is the only check.

**Token honesty and freshness.** The install skill MUST mint `$COORDINATOR_CHAIN_PREINSTALL_CONSENT`
fresh at top-level walk start and MUST NOT inherit a value already present in the environment
(overwrite or fail-loud, never trust an inherited value). This mirrors the visited-set
stale-cleanup lifecycle (→ § Visited-set protocol → Lifecycle / Stale-cleanup): a
leaked or stale consent token from a prior session is not a valid grant for a new walk.

**Orthogonality.** The consent token and the override-flag pair are orthogonal: the override
pair means "I accept missing deps"; the consent token means "the operator authorized this
chain walk." A consented chain walk passes both.

### Three invariants

**i. INSTALL ≠ INDEX.** `chain-preinstall` performs synchronous capability install only
(fetch, wire, validate — the "Install" sub-step in the install/provision/orient axis).
It MUST NOT trigger slow provisioning (e.g. project-rag's ~1-hour index build); provisioning
stays background post-restart. → § Provision sub-axis.

**ii. Consent satisfied once, up front.** The valid-when predicate above. The seam coexists
with exit 92 by being chain-context-gated (via `$COORDINATOR_CHAIN_PREINSTALL_CONSENT`), not a blanket
bypass. See § Phase-level gate / exit-92 interaction below.

**iii. Durable tracking preserved.** A heavy-install leg's `chain-preinstall` WRITES its
install-status receipt — it is a real install. Therefore `chain-preinstall` is
**stateful-by-contract** and is **NOT** in the read-only carve-out table (→ § Dual-mode
script UX → Read-only flag carve-out). Contrast `seed-install-spinoff`, which is read-only
by contract and is in the carve-out. A no-op leg (coordinator/DR) simply has nothing to
write and exits 0 harmlessly — it does not earn a per-leg carve-out exception; see
§ Carve-out resolution below.

### Phase-level gate / exit-92 interaction

**ANY leg honoring `--phase chain-preinstall`** — no-op or heavy — MUST route past the
read-only carve-out to the agent-direct/token gate:

- **In agent-mode WITHOUT `$COORDINATOR_CHAIN_PREINSTALL_CONSENT`** (and without the override pair) →
  the agent-direct guard fires (exit 92-equivalent), **NOT** silent-proceed. This gate is
  uniform across all legs (phase-level) — a no-op leg gates identically with an empty body
  after the gate.
- **Token present** (non-empty `$COORDINATOR_CHAIN_PREINSTALL_CONSENT`), **or override-flag pair present,
  or non-agent mode** → run the body → exit 0.

This is the sentence that prevents a downstream implementor from accidentally building a
blanket bypass. A no-op body (coordinator/DR) still routes through the gate; it simply
executes nothing after passing. (→ § Walker composition `:286-288` for agent-mode invocation
composition rules.)

The gate is **phase-level**, not body-level. The no-op legs exit 0 after the gate in the
same way a heavy body would — but both route through the gate first.

### Carve-out resolution

`chain-preinstall` is stateful-by-contract and is **NOT** in the read-only carve-out (→
§ Dual-mode script UX → Read-only flag carve-out `--phase <name>` row). The authority text
governing carve-out membership is stated there: carve-out membership is determined by the
phase's contract-level statefulness declaration, NOT by per-leg body behavior. A phase
declared stateful-by-contract (e.g. chain-preinstall) is never in the carve-out, even at
legs whose bodies happen to write nothing (coordinator/DR no-ops). Otherwise the same phase
would carry different guard behavior per-leg — a detect-then-silently-diverge footgun.

Scripts MUST NOT list `chain-preinstall` in the read-only flag allowlist comment block
alongside `seed-install-spinoff`. The allowlist comment must remain honest about what is
and is not read-only.

### Negative-spec

**chain-preinstall MUST NOT itself dispatch subagents or recurse the dep chain** — recursion
is the walker's job, already completed before any chain-preinstall fires. Each leg's
`chain-preinstall` is a flat synchronous shell operation.

On non-zero exit, a heavy-install `chain-preinstall` surfaces an **actionable-stop** exit
code and **halts the chain** — never an interactive pre-restart repair loop. The chain-walker
classifies the non-zero exit the same way it classifies exit 11/12 (→ § Exit-code handling):
surface remediation, halt the walk.

### Downstream-repo guidance

This subsection is the "teach the other side in a wiki" half of the `chain-preinstall`
contract (per `cross-repo-communication.md` § When lifting a cross-repo primitive). A
heavy-install leg implements `chain-preinstall` as follows:

1. **Gate on token** (per § Phase-level gate / exit-92 interaction): check
   `$COORDINATOR_CHAIN_PREINSTALL_CONSENT` (or the override pair) in agent mode before doing anything
   else; exit 92 if absent and in agent mode.
2. **Run script-install**: execute the synchronous install body (fetch, wire, validate).
3. **Write install-status receipt**: record the install outcome in the repo's install-status
   ledger (→ § JSON Schema for install-status.json).
4. **MUST NOT trigger provision**: slow work (indexes, corpus builds, long compiles) stays
   background post-restart (→ § Provision sub-axis).

**Three implementor obligations for a heavy-install `chain-preinstall` body:**

1. **Fully non-interactive.** Consume the consent token in lieu of any interactive prompt.
   Never block on stdin — the chain-walk context has no TTY at the preinstall stage. The
   consent token IS the operator's authorization; do not re-prompt.
2. **Bounded synchronous output.** Long compiler/index streams belong to background provision,
   not the synchronous pre-restart body. INSTALL ≠ INDEX applied to OUTPUT, not just timing —
   project-rag specifically: the ~1-hour index stream stays background; the preinstall body
   must complete with bounded output before the chain advances.
3. **Fail-fast with an actionable-stop exit code.** Never an interactive repair loop. On
   failure, emit a one-line remediation and exit non-zero so the chain-walker can halt and
   surface the stop (→ § Exit-code handling).

**coordinator is a no-op.** Coordinator is the DAG root with no Python/binary install phases
(deep-research is folded into the coordinator plugin bundle — not a separate leg — and carries no
`chain-preinstall` of its own; see § the deep-research callout above). Coordinator's leg implements
`chain-preinstall` as a gate + explanatory no-op body + exit 0.

### Contract-version note

The contract-version table (→ § Versioning) is untouched by this phase. Minting a `--phase`
value is additive script behavior with no schema surface — `chain-preinstall` appears in no
manifest JSON and in no schema `$defs`. No reader-widen-first sequencing is required and no
version bump is needed.

---

## Runtime vs. test-time validation

**Runtime** (Phase 0 manifest read in the standalone script): uses stdlib Python `json` module only. Validates structure shape minimally — presence of required top-level fields. No `jsonschema` import at runtime; `jsonschema` is NOT a runtime dependency.

**Test-time** (each conforming repo's `test_agent_install_contract.py` or equivalent): uses `jsonschema` to validate that repo's `agent-install-manifest.json` against its `agent-install-manifest.schema.json`. The `jsonschema` library is acceptable as a test-only dependency. The contract test also verifies that this doc's referenced semantics match the schema file's actual constraints (versions accepted, required fields, additive-only property changes between v1 and v2).

### JSON Schema for install-status.json

Each conforming repo's install-status ledger (e.g. `<settings-home>/example-game-repo/install-status.json` in example-game-repo; see § Visited-set protocol for the `<settings-home>` definition) is validated at read time by any consumer that imports it (doctor probes, recovery scripts). The validation uses JSON Schema Draft 2020-12.

**Strict unknown-property rejection.** Consumers MUST reject install-status.json objects with unknown top-level or phase-level properties loudly (raise / exit non-zero with a schema-violation message) rather than silently ignoring them. Silent-skip on unknown shapes masks schema drift across repo versions.

**Schema location:** Each repo stores its install-status schema at `docs/install/install-status.schema.json`. The repo's contract test verifies that the schema `$id` matches the file path; divergence fails CI.

**Draft 2020-12 gotcha — sibling_dir_exists then-block:** JSON Schema Draft 2020-12 has a known behavior difference from Draft 07 in `if`/`then`/`else` evaluation when `additionalProperties` is in the then-block. Verify schema behavior against the 2020-12 spec if extending the schema with conditional branches.

---

## v2 → v3 migration playbook

<!-- spec-backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md C6/C7 -->

For consumers and upstreams adopting v3, the per-repo mechanical steps are:

1. **Reader-widen** (per repo, one commit): change the manifest reader's version check from `version in {1, 2}` to `version in {1, 2, 3}` (both the `.sh` and `.ps1` readers — the PowerShell sibling is a separate edit site).
2. **Schema mirror** (per repo bumping its OWN manifest): widen the `agent_install_contract_version` enum in `agent-install-manifest.schema.json` from `[1, 2]` to `[1, 2, 3]`. Add the optional `system_prerequisites` array to `properties` (already defined in coordinator's schema). Preserve `additionalProperties: false`. (A repo that only *reads* coordinator's v3 but does not bump its own manifest widens only its reader, not its schema enum.)
3. **Manifest bump** (per repo bumping its OWN contract): flip the literal `agent_install_contract_version: 2` to `3`. Populate `system_prerequisites` with the ENV-PREREQ-PROBE entries for that repo's machine-level requirements.
4. **Walker/contract-test update** (per repo): update the contract test to assert a v3 manifest validates; assert `system_prerequisites` is optional + forward-compatible (a v2-shaped manifest with no `system_prerequisites` still passes under the v3 schema).

**Sequencing — two valid strategies for closing the deployment-skew window.** The hazard is a v3 manifest meeting a `{1,2}`-only reader (a consumer's chain-walk breaks). There are two doctrine-valid ways to avoid it:

- **Reader-widen-first (the default / OSS posture).** Widen every consumer's reader to `{1,2,3}` and confirm green, THEN flip the producer literal, in lockstep. This is the correct posture when the repos are independently controlled / released — no single operator can guarantee a synchronized cutover. See §Reader-widen-first sequencing. **This remains the documented default and applies to any future v3→v4 bump.**
- **Simultaneous-merge cutover.** When one operator controls every repo in the chain, widening all consumer readers AND flipping the producer literal in a single PM-coordinated merge wave closes the skew window structurally — no intermediate state ever ships where a vN manifest meets an `{1,2,...,N-1}`-only reader, because nothing is on `main` until everything is. **This strategy is only safe under single-operator control of the full chain; it is not a substitute for reader-widen-first in the OSS distribution, where consumers upgrade independently.**

---

## Historical migration note

This contract's ecosystem-wide canonical home is `coordinator-claude` (the chain root), migrated
from its original `example-game-workbench-repo` (chain leaf) home, bilaterally co-developed with
`project-rag-ue-addon`.
- This file in the DoE-claude clone (`coordinator/docs/wiki/agent-install-contract.md`) is the single canonical source; `~/.claude/plugins/coordinator/docs/wiki/agent-install-contract.md` is its published mirror (propagated outward via claude-klabauter `coordinator/bin/publish.py` to consumer projects).
- `example-game-workbench-repo/docs/wiki/agent-install-contract.md` becomes a one-line pointer redirect to this file.
- `project-rag-ue-addon` and other consumers (`project-rag`, `deep-research-claude`) cite this file rather than mirroring it.
- Per-repo `docs/install/agent-install-manifest.schema.json` files **stay in each repo** — the schema is the per-repo implementation of this contract; this doc is the contract spec. Moving schemas would change every `$id` URL and is deferred until a third consumer makes the duplication pressure obvious (current state: example-game-repo + addon are the only two repos with schemas).
- Doctrine for cross-repo doc moves of this shape: `coordinator/docs/wiki/cross-repo-communication.md` in the DoE-claude clone § Doctrine seeding vs. code/install-surface change.

---

## DirectDep fields (schema v2)

**`override_flags`** (upstream-authored, array of strings): CLI flags the upstream's install
script requires to run in agent mode. The chain-walker reads these from each upstream's
manifest and appends them verbatim after `--i-am-agent`. **Do NOT hard-code** — upstream
spellings differ (e.g., `--accept-corpus-poisoning-risk` ≠ `--accept-hallucination-risk`).
Exit codes 92/93 from an upstream script typically mean `override_flags` are missing or wrong
(invocation bugs), not install failures.

**`consumer_install_args`** (consumer-authored, array of strings, optional, v2+): Per-dep
args the consumer (example-game-repo) wants the upstream's setup invoked with. The walker composes
`<script> <consumer_install_args…> --i-am-agent <override_flags…>`. Added v2; optional and
forward-compatible; no `consumer_install_args` needed today for the addon wrapper invocation
(wrapper self-resolves UE version and corpus tag).

**Schema version:** `agent_install_contract_version` field. Reader accepts `{1, 2, 3}` range
(reader-widen before literal flip).

### CONTRACT-VERSION STATUS (self-serve — no ack needed)

> Cross-repo readers: this block is the source of truth for coordinator's contract-version
> posture. Grep `CONTRACT-VERSION STATUS` rather than pinging for an ack.

| What | Value | Since |
|---|---|---|
| Emitted manifest literal (`docs/install/agent-install-manifest.json`) | **3** | 2026-06-23 fleet-wide simultaneous-merge cutover (C7 of plan `2026-06-23-coordinator-root-system-prerequisites.md`) — flipped in lockstep with all consumer reader-widens |
| Reader-accepted range (`scripts/lib/manifest_reader.{sh,ps1}`) | **{1, 2, 3}** | reader-widen 2026-06-23 (`.sh` C6; `.ps1` C7 — C6 missed the PowerShell sibling) |
| Schema enum (`docs/install/agent-install-manifest.schema.json`) | **{1, 2, 3}** | schema-widen 2026-06-23 (C6) |
| Lockstep with addon | **v3** — coordinator literal 3; addon reader widened to {1,2,3} (vendor-bump + reader-widen dispatched via cross-repo memo, merged in the same wave) | 2026-06-23 |
| v3 cross-repo reader-widen status | **closed via simultaneous merge** — deep-research (central-owned) widened in-tree; example-game-repo / project-rag / project-rag-ue-addon reader-widens dispatched via memo + PM relay and merged in the same coordinated wave | 2026-06-23 |

**No-coordination doctrine.** The dep-chain is unidirectional: example-game-repo *consumes* the addon
manifest; the addon never reads ours. The v2→v3 flip landed via the simultaneous-merge cutover
(§v2→v3 migration playbook) — no intermediate state shipped a v3 manifest against a `{1,2}`-only
reader. Re-open contact only if a KeepBlank clean-consumer smoke run surfaces an
invocation-composition gap.

**Exit-code taxonomy for dep-chain walk:**
- `0` success, `1` generic failure, `2` repo-shape mismatch, `11` missing system dep,
  `12` uv missing → actionable install stops.
- `92` / `93` → invocation bugs (wrong flags); fix `override_flags` in upstream manifest.
- `94` git-auth unverified → actionable-stop (semi-hard gate).

---

## Packageability contract (portable-core repos)

<!-- spec-backlink: docs/plans/2026-07-11-packageability-contract-fleet-doctrine.md § Problem -->
<!-- source: example-os-repo-em inbound ask (source_memo 2026-07-11-unknown-sender-em-example-os-repo-packageability-contract.md), PM-ratified -->

Example-os-repo packages the assembled fleet into a native `.exe`/`.app` a "just-technical-enough" human
installs like ordinary software. That distribution target is only reachable if every portable-core
repo in the fleet exposes — and *keeps* — an install surface example-os-repo can drive headlessly, with no
agent in the loop. `example-os-repo-em` sent an inbound ask naming six such properties; the PM ratified
accepting it and homing it here as **standing fleet-wide DoE doctrine** — the bar every repo, present
and future, inherits by virtue of being in the fleet, not a per-repo goodwill target.

This section is the **doctrine layer**. The **schema layer** (optional-additive `agent-install-manifest.schema.json`
fields encoding points 1/2/3/4/6) and the **enforcement layer** (`validate-install-contract.py`, a
DoE-local opt-in-scoped compliance gate) are separate, cross-linked surfaces — see the
`packageability-compliance` marker note below and `docs/plans/2026-07-11-packageability-contract-fleet-doctrine.md`
for the full six-chunk delivery.

<!-- src: memo05-011 -->
**Enforcement-layer reachability.** `validate-install-contract.py` ships to the flat
OSS sibling `coordinator-claude/bin/` (not just the private DoE-claude clone) so a downstream
consumer repo can actually invoke it. It accepts `--manifest-path` to point at any
repo's `agent-install-manifest.json`. The plugin-mirror copy is satisfied-by-design under
`source_is_live` (coordinator's plugin source resolves live from the DoE-claude clone via
`--plugin-dir`) — vendoring a second copy into consumer repos was rejected.

**Cross-links.** Two existing wikis frame the two halves of "packageable": `install-surface-completeness.md`
covers the fresh-machine dimension (does the install surface work on a machine you've never seen) AND
the running-in-Claude-Code dimension (`install-surface-completeness.md § Running-in-Claude-Code` — a
leg only counts complete once its Claude Code surface is live-validated, not merely present in config);
`coordinator-installer-shape.md` covers the shape an installer itself should take. The six points below
are this contract's answer to "what does example-os-repo specifically need from that install surface to drive
it headlessly."

### The six points

1. **Declared machine-readable requirements.** Every system prereq *and* fleet dependency lives in
   `agent-install-manifest.json` with a *functional* probe (actually run the tool — `probe.kind`/`probe.cmd`
   per § SystemPrereq fields above — not merely `command -v`), a remediation that is either a
   machine-runnable command (`install.mode: auto-with-confirmation`, per-OS `posix`/`windows`) or a
   website URL for the genuinely un-scriptable class (Epic launcher, git-for-windows installers).
   `required_env_vars` is declared **even when empty (`[]`)** — omission, not an empty array, is the
   non-conforming state.
2. **One programmatic entry point.** A single non-interactive, flag-driven, deterministic-exit-code
   install/register/assemble command per repo. The agentic setup skill (`/x:setup`) stays as a human
   wrapper but must *delegate* to that command — no install logic living only inside the skill prose.
3. **Installer-floor split.** example-os-repo provisions the prerequisite chain up to and including git and
   the Claude Code CLI; each repo declares only the dependencies *above* that line and stays drivable
   against a example-os-repo-provided install root — no hardcoded `~/.claude` or sibling-directory assumption
   baked into the entry point itself.
4. **Real, declared, *tested* platform support.** A repo declares which OSes its entry point is
   actually executed-and-verified on, distinct from which OSes it merely ships a script for. A
   static-reviewed-only PowerShell twin is not "Windows parity" and the manifest must say so, not imply
   otherwise.
5. **Stay-in-shape invariant.** Any change that adds a dependency, a system prereq, or an env var
   updates the manifest in the **same commit**. A slice that adds an API key or a system dep without
   touching the manifest is a break, not a follow-up — see § Same-commit invariant below.
6. **Every configurable location is detect → suggest → default → override, exposed as data.** For each
   location a repo resolves (install root, projects root, UE root, package store, data root), the
   manifest declares (a) discovery yielding *ranked candidate* paths, not a found/not-found boolean,
   (b) a sane default so the flow can proceed silently, and (c) an override (env var or flag) so
   example-os-repo can inject the human's chosen path. See § Point 6 below — this is a generalization of an
   existing grammar, not a new philosophy.

### Two entries, two roles — `standalone_setup_script` vs `programmatic_entry_point`

The contract now recognises **two distinct roles** a manifest's install-entry fields can play, and a
repo may satisfy them with either one script or two:

- **`standalone_setup_script`** — the **chain-walk dispatch target** (§ Dual-mode script UX, § Skill
  chain-walker). This is the script the agentic setup skill and the recursive subagent walker invoke;
  its `entry_point_contract` (where declared) describes the `--i-am-agent`/`--check`-shaped invocation
  used *during a chain walk*.
- **`programmatic_entry_point`** — the **Point-2 cold-install entry** (§ Packageability contract point
  2): a single non-interactive, flag-driven, deterministic-exit-code install/register/assemble command
  a driver like example-os-repo can invoke headlessly, with no agent and no chain-walk context in the loop.

**The two-role rule.** Where the chain-walk target and the cold-install entry are literally the *same*
script, `standalone_setup_script.entry_point_contract` remains the Point-2 witness on its own — no
second field is needed and none should be added redundantly. Where they **differ** — as they do for
coordinator-claude, whose chain-walk target (`setup.py`) is a DAG-root no-op walker but whose actual
mechanical install/register/assemble sequence lives in a separate cold-install orchestrator — the repo
declares BOTH fields, and `programmatic_entry_point` is preferred as the Point-2 witness.

**In-band precedence rule.** When both `programmatic_entry_point.entry_point_contract` and
`standalone_setup_script.entry_point_contract` are present, `programmatic_entry_point` is the
authoritative Point-2 witness; `standalone_setup_script.entry_point_contract` describes only the
chain-walk invocation and is the Point-2 fallback only when `programmatic_entry_point` is absent.

**Coordinator-claude's own declaration.** The manifest's `standalone_setup_script` names
`scripts/setup.py` (engine-root-relative, per migration `b644d5a9b` — resolves against either the
live `repos.claude_klabauter` checkout or the declared `claude-klabauter` dependency, whichever
`_engine_root.py` returns) — the install-chain **walker**, with `entry_point_contract` flags
`--i-am-agent` (non-interactive) / `--check` (check-only). `setup.py` performs no mechanical
install work for this repo on its own; it is the chain-walk dispatch target, distinct from the
cold-install entry below.
Point 2 for coordinator-claude is met by the top-level `programmatic_entry_point` field, which
declares `coordinator_core/install/maximalist.py` (also engine-root-relative, same resolution as
above) — the cold maximalist install-phase orchestrator, with `entry_point_contract` flags
`--non-interactive` / `--check-only` and `deterministic_exit: true`. `standalone_setup_script.
entry_point_contract` (`setup.py`'s flags) remains correct as the chain-walk witness; it does not
double as the Point-2 witness once `programmatic_entry_point` is present.

### Confirmed sub-asks — satisfied, not re-opened

One of `example-os-repo-em`'s sub-asks was checked against disk during this doctrine-homing and is recorded
here as **closed**; do not re-litigate it in a future pass without new contrary evidence.

- **Posture selector as a stable UI contract.** `engagement_posture` (precision/default/substrate-free)
  ships with an explicit `--posture <precision|default|substrate-free>` flag honored under
  `--non-interactive` (`coordinator/commands/install.md:669`), a persisted per-machine value in
  `~/.claude/coordinator-identity.yaml`, a per-repo override in `coordinator.local.md`, and the
  idempotent managed-merge renderer claude-klabauter `coordinator/bin/render-posture-overlay.py`. Framing carries
  forward unchanged: posture changes **engagement**, never **strictness** — the floor (Verification
  Before Done, Plan-First, etc., now enumerated at `global-doctrine/CLAUDE.md` § Posture, with the
  plan-first mechanics at `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off)
  is invariant regardless of posture.

### Greenfield inheritance

A repo spun up via `coordinator:new-project` / `coordinator:repo-setup` inherits this contract **at
birth**, not as a retrofit — the starter `agent-install-manifest.json` seeded at spin-up is
packageability-compliant from its first commit. There is no "adopt the contract later" grace period for
new repos; the fleet-wide bar applies from day one, same as any other floor doctrine in this file.

### Same-commit invariant (point 5)

Point 5 is a **process** invariant, not a schema field — there is no JSON shape that encodes "this
dependency and its manifest entry landed in the same commit." It is enforced by doctrine plus the
always-on code-reviewer lens that already scans install-surface diffs
(`install-surface-completeness.md § Code-reviewer enforcement (always-on lens)`) — a manifest-drift
question belongs in that existing lens's question set, not a bespoke new check. A diff that adds a
dependency/prereq/env-var without a matching manifest update in the same commit is
`install-surface-completeness.md`'s "works only by accident of machine state" failure mode applied
to the manifest itself.

**Adopter trap — a tightened manifest probe must be mirrored into the entry script(s) in the
same commit.** The dual of the above: tightening a `system_prerequisites[]` probe from a
presence check to a functional check (e.g. python *present* → python `>=3.11`) makes the
**manifest** stricter than the `setup.sh`/`setup.ps1` gate it describes if the script still
only checks presence. A headless example-os-repo/validator run honors the manifest probe; a human
`setup.sh` run honors the looser script gate — so the same machine can **diverge** (python 3.10
blocks in one path, sails through the other). `validate-install-contract.py` is single-manifest
scope and **structurally cannot** catch this cross-file drift; only the always-on code-reviewer
lens can. Port the tightened gate into both the manifest probe and the entry script(s) in the
**same commit** — this is the same-commit invariant applied to probe *strictness*, not just
probe *existence*.

### Point 6 — a generalization, not a new philosophy

`configurable_locations[]` is **not** a fresh resolution philosophy bolted onto the contract — it
generalizes the existing resolution grammar this fleet already runs on
(`coordinator/docs/wiki/machine-local-registry.md` § 4 Resolution Order): the four-rung ladder
**explicit `REPO_<SLUG>`-style override → tracked `search-roots.toml` autodiscovery (+ marker
convention) → tracked `path-exceptions.toml` → `registry.local.toml` fallback**, with
`MACHINE_LOCAL_<KEY>` as the emergency env-var escape valve below the `.toml` layers.

Point 6 **adopts this ladder's rung vocabulary** — discovery/candidates, default, override — rather
than inventing a parallel taxonomy. The net-new piece is the **shape**: no existing manifest field
declares a repo's resolvable locations (install root, projects root, UE root, package store, data
root) as a structured, driver-consumable array with ranked candidates + default + override per
entry — what lets example-os-repo render a detect/suggest/confirm GUI step per location instead of an
agent reading prose and improvising. The schema shape for `configurable_locations[]` is pinned in
`agent-install-manifest.schema.json`; this section owns only the doctrine framing.

### Point 4 — a derived field, not a hand-assertable claim

`tested_platforms` is not an ordinary array a repo author types by hand. Hand-writing
`"tested_platforms": ["windows"]` on the strength of "I'm pretty sure this works on Windows" is the
"static-reviewed-only PowerShell twin" failure mode (§ The six points, point 4) moved up from the
entry-point script into the manifest field meant to be the honest record of it.

**Scope.** Point 4 covers platform support for a manifest-declared **entry point** —
`standalone_setup_script` or `programmatic_entry_point` (§ Two entries, two roles above) — not
every script or code path a repo happens to ship. `agent-install-manifest.schema.json`'s
`tested_platforms` description (schema `:167`) draws the same line: it distinguishes platforms
the entry point has been *executed-and-verified* on from platforms the repo merely *ships code
for* (`present_platforms`). A platform absent from `tested_platforms` MUST NOT be marketed as
supported parity even when it's present in `present_platforms`.

**PROMOTION rule.** A platform enters `tested_platforms` ONLY via the DoE-owned generator,
never by hand-edit. The generator computes membership from `state/platform-outcomes/` records —
one record per real ceremony run, capturing platform, surface, command, exit status, SHA,
machine, and UTC timestamp — filtered to records whose `surface` resolves to a manifest-declared
entry point. `tested_platforms` is therefore a **derived** field: there is no value in it that
wasn't computed from committed evidence on disk, and there is no hand-assertable value to write
over it. Writing the array by hand does not make a claim true; it makes the manifest diverge
from what the generator would have produced, which is exactly the drift the belt-and-braces
validator check (§ below) exists to catch.

**DEMOTION rule.** A platform's presence in `tested_platforms` is not a one-time achievement —
it is re-earned on every generator run. A **failing** outcome record, or a record that has gone
**stale** (see below), removes that platform's claim the next time the generator runs: there is
no "once tested, always tested" pass for a platform whose evidence has turned bad.

**Transitional grandfather — narrow, and never a promotion path.** There is exactly one case the
demotion rule does *not* fire on: a platform *already* present in `tested_platforms` for which
**zero** qualifying records exist yet (as opposed to failing or stale ones). Such a pre-existing
claim is *preserved* with a `grandfathered: <platform> has no backing records` advisory rather
than silently demoted to `[]`. This is a bootstrap provision, not a loophole, and its scope is
deliberately tight:
- It fires only on the **absence** of records, never in the presence of a failing or stale one — a
  bad record always demotes.
- It can only ever **preserve an existing** entry; it can **never introduce a new** platform. A
  platform not already in `tested_platforms` (e.g. `windows`) cannot be grandfathered in — it is
  promoted solely by real passing entry-point records. The hand-assertion this whole subsection
  exists to forbid remains impossible.
- It exists because record backfill for the already-declared platforms (`macos`/`linux`) is
  deferred work (a machine to produce those records may not be reachable in a given session — see
  the plan's D1 deferral); demoting a genuinely-tested platform merely because its record hasn't
  been *written yet* would be its own dishonesty. Once the backfill lands, the advisory clears.

**STALENESS rule.** An outcome record backs a `tested_platforms` claim only while it is fresh,
judged the same two-tier way `state/platform-outcomes/` freshness is judged elsewhere in this
plan's evidence chain: **`surface_sha` is the primary staleness signal** — if the entry point's
current content hash differs from the SHA recorded at outcome-capture time, the record does not
speak to what's actually on disk and cannot back a claim, regardless of how recently it
was captured. **A 30-day calendar window is the secondary signal** — even when `surface_sha`
still matches, a record older than 30 days is stale and drops out of the promotion set on the
next generator run. Either condition alone is sufficient to demote; a platform needs a record
that is both SHA-current and within the 30-day window to remain tested.

**Producers.** The ledger is not scoped to manifest-declared entry points alone — any surface that
runs a real ceremony/op and captures a pass/fail verdict may land a record here, keyed off its own
`surface` value (only records whose `surface` resolves to a manifest-declared entry point feed the
promotion/demotion rules above). Two producers fold their live-verification outcomes into this
ledger rather than a bespoke scratch note: `docs/plans/2026-07-19-review-folded-into-workflow-sidecars.md`'s
C1 confinement dogfood (confinement-dogfood outcome, one record per dogfood run) and
`docs/plans/2026-07-19-architecture-survey-workflow-claude-klabauter-rebuild.md`'s scheduled live-fire run
(architecture-survey live-fire outcome, one record per scheduled run). Neither `surface` is a
manifest-declared entry point, so neither backs a `tested_platforms` claim.

**Downstream consumer.** `tested_platforms` has exactly two readers (§ Contract-amendment note
above): DoE's own `validate-install-contract.py`, and **example-os-repo**, the external packaging
driver. Example-os-repo reads `tested_platforms` to decide what it may package and ship as
platform-supported — a platform this repo has not actually run its entry point on and verified
MUST NOT be presented to an end user as supported.

### Opt-in compliance marker

A v3 manifest declares fleet-wide compliance by carrying a top-level optional
`packageability_compliance: { "declared": true }` object. This is the **opt-in signal** — the
DoE-local `validate-install-contract.py` gate fires its per-point completeness checks only when
`packageability_compliance.declared === true`. A v3 manifest that omits the field entirely **skips
clean** — it is not failing, it has simply not opted in yet. This keeps the "active compliance gate"
directive at full strength for repos that have declared, without regressing any sibling that hasn't
adopted the six points on its own clock yet.
