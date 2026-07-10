---
title: Coordinator installer — design shape and audience contracts
created: 2026-05-19
kind: wiki
spec_backlink_arch: "2026-05-19-coordinator-installer-redesign.md (lives in meta-repo docs/plans/; not bundled with the plugin)"
spec_backlink_impl: "2026-05-19-coordinator-installer-redesign-implementation.md § C7 (lives in meta-repo docs/plans/; not bundled with the plugin)"
---

# Coordinator installer — design shape and audience contracts

Purpose: document the three audiences `/coordinator:install` serves, the operator-identity
primitive it introduces, the render-template primitive it depends on, and the
`--non-interactive` contract that lets downstream callers invoke it without interactive
prompts. This is the canonical reference for the installer redesign shipped 2026-05-19.

---

## 1. Three audiences

`/coordinator:install` is load-bearing for three distinct audiences. Understanding which
audience you are shapes which flags and flows are operative.

### OSS adopters

**Who:** First-time user, fresh `~/.claude`, no prior coordinator install.

**Operative constraints:**
- Interactive by default — no `--non-interactive` flag needed.
- Full phase sequence runs: environment checks, operator-identity capture, meta-repo
  doctrine install, project-local scaffolding direction, optional features, status report.
- Trust-baseline-setting interaction: the installer's first-impressions quality (error
  tolerance, friendly prompts, completeness) sets expectations for the entire coordinator
  system downstream.
- Idempotency is not a concern on first run, but every phase is safe to re-run in case of
  interruption.

### Internal users (example-game-repo team and other downstream consumers)

**Who:** Teams where coordinator is a semi-hard prerequisite — chain step 5 per
`docs/plans/2026-05-08-install-chain-readiness-coord-and-dr.md`. These callers may invoke
`/coordinator:install` programmatically from a setup wrapper (e.g. `scripts/example_game_repo_setup.sh`).

**Operative constraints:**
- Speed, idempotency, low-prompt. Hanging on an `AskUserQuestion` in a CI-like flow is a
  hard failure.
- Pass `--non-interactive` to suppress all prompts. Each prompt site has a documented
  fallback (see § 4. `--non-interactive` contract).
- The canonical example-game-repo pre-flight invocation is `--check-only --non-interactive` — reports
  substrate state without any mutation, without any prompt.
- Parse the status-report table to determine pass/fail. Column names and value enums are
  a stable contract — see `docs/wiki/coordinator-installer-status-schema.md`.

### Meta-repo operator dogfooding

**Who:** The meta-repo operator (Dónal O'Duffy, or any future operator running
`~/.claude` as their personal coordinator tree) re-running `/coordinator:install` after
a percolation cycle that updates plugin content.

**Operative constraints:**
- Operator identity is already captured (`~/.claude/coordinator-identity.yaml` exists).
  Setup skips the identity-capture prompt silently — idempotency contract applies.
- `--check-only` is the typical mode for a "did percolation break anything?" sweep.
- `--reconfigure` re-prompts the identity-file step even when the file is already present,
  for the rare case where the operator name should change.
- This is the highest-frequency consumer of the installer; every phase must be fast and
  must never re-ask things that were already answered.

---

## 2. Operator identity primitive

### File location

```
~/.claude/coordinator-identity.yaml
```

This file is **operator-local**. It is written by `/coordinator:install` at runtime and
read by downstream skills that need the operator's display name. It is **never** a
publish-target — do not add it to `setup/publish-targets.sh`. (The publishable artifact
is `plugins/coordinator/templates/CLAUDE.local.md.tmpl`; the rendered
`~/.claude/CLAUDE.local.md` is the local output.)

### Schema

```yaml
# ~/.claude/coordinator-identity.yaml — operator-local, NEVER a publish target
version: 1
operator_name: <string>  # the form the EM should use when referring to the operator
# future fields are additive-only; bump `version:` if a field becomes mandatory
```

### Reader contract

Any consumer reads `version:` first and refuses to consume a higher major version than it
knows. If the file contains `version: 2` and the consumer only understands version 1, it
must fail-loud with a remediation message rather than silently consuming unknown fields.

### Writer contract

`/coordinator:install` writes `version: 1` today. Migration is documented when `version: 2`
ships; no migration is owed for version 1 since there are no version-0 consumers.

### Why operator-local, not a publish-target

The identity file captures a specific human operator's name. Publishing it would
propagate personal configuration into the coordinator plugin's shared template set,
which is designed for any operator. The publish-side artifact is the template
(`CLAUDE.local.md.tmpl`); the rendered output is the local product. These two surfaces
must stay separate — publishing the rendered product or the identity file would silently
overwrite other operators' configuration on their machines.

### Idempotency contract (from D2)

| Condition | Behavior |
|-----------|----------|
| File exists + `version: 1` + `operator_name` present | Skip the identity-capture prompt silently. |
| File exists + `version:` higher than known | Fail-loud; log warning; do not consume unknown schema. |
| File exists + outdated/missing fields under known version | Migrate silently (no-op today — no v0 consumers exist). |
| File does not exist (or `--reconfigure` passed, interactive) | Prompt via `AskUserQuestion`; write file on completion. |
| File does not exist, `--non-interactive` | `fail-loud` — operator name is not derivable; exit non-zero with remediation. |

---

## 3. Render-template primitive

`/coordinator:install` and `/repo-setup` both render templates. The shared helper
is `render-template.sh` (top-level coordinator `bin/`, not nested under a skill, since
multiple skills consume it).

A test suite lives at `bin/tests/test-render-template.sh`. Run as:

```sh
bash bin/tests/test-render-template.sh
```

from the coordinator plugin root. Emits PASS/FAIL per case; exits non-zero on any failure.

### Narrow contract

The helper's contract is deliberately narrow:

- **Substitution:** literal `{{KEY}}` → the supplied value string. Exact match only.
- **Whitespace inside braces is NOT tolerated.** `{{ FOO }}` does not match `FOO=bar`
  and is treated as an unsubstituted key. This is intentional — it forces consistent
  template style and prevents silent partial-match failures.
- **Fail-loud on unsubstituted keys.** If any `{{KEY}}` pattern remains in the rendered
  output after all substitutions, the helper exits non-zero and writes to stderr:
  `render-template: unsubstituted keys: KEY1, KEY2 in <template-path>`.
- **No conditionals, no loops, no includes, no escaping, no default values.** The narrow
  contract is load-bearing — adding any of these features silently changes what templates
  work correctly under the helper.
- **Output:** rendered content to stdout, or to a file when `-o <path>` is supplied.
  The `-o` path write is atomic: render to a temp file, then `mv` to target.
- **Exit 0** on successful render with all keys substituted.

### Why the narrow contract matters

`repo-setup/templates/CLAUDE.md.template` originally used `{{IF_GLOBAL}}...{{/IF_GLOBAL}}`
conditional blocks. Preserving the narrow contract required flattening those conditionals
into `repo-setup/SKILL.md` driver code (C5 in the implementation plan). This
was the *cost* of keeping the helper scope-minimal — driver code constructs the appropriate
value strings before calling the helper, rather than the helper growing a conditional engine.
The narrow contract prevents that growth path and keeps the helper a dumb substituter.

---

## 4. `--non-interactive` contract (D4)

### The 2×2 interaction matrix

| | interactive | `--non-interactive` |
|---|---|---|
| **mutating** | default: prompt at each `AskUserQuestion` | per-callsite annotation governs fallback |
| **`--check-only`** | reports without mutating; skips prompts with a note | strict superset: no mutation regardless of interactivity; `--non-interactive` controls only the `AskUserQuestion` fallback |

`--check-only` is a strict superset of `--non-interactive`. Combining both is explicitly
supported and is the canonical example-game-repo chain-step-5 pre-flight invocation shape.

### Per-callsite annotation vocabulary

Each `AskUserQuestion` callsite in `/coordinator:install` carries one of three annotations:

| Annotation | Behavior under `--non-interactive` |
|---|---|
| `skip-with-note` | Do nothing at this callsite; surface a status-table row noting the skip. |
| `default-with-warning` | Apply the documented default value; surface a status-table row. |
| `fail-loud` | Exit non-zero with a remediation message; do not proceed. |

**Default for any unannotated callsite: `fail-loud`.** The installer is loud about gaps
rather than silently picking. Callsites with safe, well-documented defaults carry explicit
`default-with-warning` annotations; callsites where a wrong default would silently corrupt
downstream state carry `fail-loud`.

`--non-interactive` controls only the `AskUserQuestion` fallback. It does not affect
mutation behavior, file writes, or status-report output beyond the prompt-fallback rows.

### Current prompt sites and their annotations

Five prompt sites exist in `/coordinator:install` (per substrate-correction B in the
implementation plan):

| Phase | Prompt | Annotation | Rationale |
|-------|--------|------------|-----------|
| Phase 2 — Operator identity | Operator name (`AskUserQuestion`) | `fail-loud` | No safe default — operator name is not derivable; a wrong name silently misidentifies the operator in all downstream renders. |
| Phase 3 — Meta-repo doctrine | Git-init Initialize/Skip (`AskUserQuestion`) | `default-with-warning` | Default: `Skip`. `git init` is reversible; defaulting to skip is safer than defaulting to init. |
| Phase 4 — Project-local | `project_type` prose-prompt | `fail-loud` | Note: the prompt fires only when `coordinator.local.md` is absent. When it fires under `--non-interactive`, no safe default exists — `general` might be correct but it might silently miss domain-specific scaffolding. |
| Phase 4 — Project-local | `project_subtypes` prose-prompt | `default-with-warning` | Default: empty subtypes list. Subtypes are advisory; empty is the documented neutral default. |
| Phase 5 — Optional | Persona customization Keep/Customize prose-prompt | `default-with-warning` | Default: `Keep defaults`. Customization is opt-in cosmetic; the canonical names are the default. |

For the producer-side row contract that example-game-repo-callable wrappers should pin against
(column names + value enums), see `docs/wiki/coordinator-installer-status-schema.md`.

---

## 5. Step Zero — preflight gate and env-normalization

<!-- spec-backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md -->

Step Zero runs BEFORE Phase 1 of `/coordinator:install`. It gates the install on functional prerequisite verification and offers idempotent fixes for advisory failures.

### Position in the install flow

```
Step Zero  →  Phase 1 (environment probes)  →  Phase 2 (operator identity)  →  …
```

Step Zero is the only phase that calls `scripts/setup.sh --preflight` and `scripts/normalize-env.sh`. All subsequent phases assume Step Zero completed without hard failures (Python probe passed). Advisory WARNs from Step Zero are surfaced in the Phase 7 status table but do not block the install chain.

### Probe-lib / fixer / gate contract

Three components, three roles — never conflated:

| Component | Role | Mutation |
|---|---|---|
| `scripts/lib/prereq_probe.sh` | SSOT functional probe lib — executes minimal runtime checks for 6 prereqs; `_co_prereq_probe_all` emits NDJSON; `inconclusive` is first-class | **Never mutates** |
| `scripts/normalize-env.sh` | Sole writer for fixable env conditions; consent/backup/restore shape; blast-radius-last ordering | **Sole mutation surface** |
| `scripts/setup.sh --preflight` | Gate — reads probe lib, tables results, exits non-zero on hard failures only (Python) | **Never mutates** |

Separating probe from fixer from gate is load-bearing: a probe that mutates state is a vacuous-pass hazard (it fixes the condition it was testing, then reports clean). See `install-surface-completeness.md § Step Zero Preflight and Env-Normalization Shape § FB-2 rule`.

### normalize-env.sh as a bootstrap-trap surface

`normalize-env.sh` is a bootstrap-trap surface: it may be invoked before brew bash is installed on macOS, so it must parse cleanly under bash 3.2 (stock macOS `/bin/bash`). No bash-4+ syntax (`declare -A`, `mapfile`, `${var^^}`) appears in the script body. This constraint applies to any future mutations added to the script — run `bash --version` check at the top, but write the entire script body to be 3.2-parseable. Cross-ref: `cross-platform-shell-portability.md` § support matrix.

### Windows platform — bash-only env-probe layer (DR-148)

The env-prerequisite probe layer (`prereq_probe.sh`, `step_zero_emit.sh`, `normalize-env.sh`) is
**bash-only by design**. This applies on ALL platforms, including Windows.

**How it works on Windows:** The coordinator requires bash ≥ 4 on every platform (DR-148 — see
`cross-platform-shell-portability.md`). On Windows this means git-bash (or WSL bash). The bash
`--preflight` path (`scripts/setup.sh --preflight`) is the canonical Step Zero entry point on
Windows too; it sources `prereq_probe.sh` and fires the semi-hard `clone_auth` gate through the
same code path that macOS and Linux use.

**PowerShell handles manifest deps only.** `scripts/setup.ps1` and `scripts/lib/dep_check.ps1`
handle the manifest-dependency severity walk (the install-chain DAG) and nothing else. Neither file
contains `clone_auth`, `step_zero`, `prereq_probe`, `--preflight`, or any env-prereq probe
logic — verified by grep (zero matches). The env-probe layer is bash-only, and that asymmetry is
intentional: adding an env-probe to PowerShell would create a second SSOT for probe logic, breaking
the `prereq_probe.sh` SSOT contract and the probe-fixer separation described in § Probe-lib / fixer
/ gate contract above.

**No Windows-native bypass.** There is no documented Windows-native install path that skips the
bash preflight. Any such path would be an unintentional gap (follow-up required), not a supported
variant. The `setup.ps1` header already documents 1:1 parity with `setup.sh` as the mirror
constraint — that constraint does not extend to env probes because env probes are bash-only.

_Follow-up note:_ if a future Windows install wrapper invokes `setup.ps1` without first running
the bash preflight, `clone_auth` and the other env prereqs will be silently unverified on that
path. Flag any such wrapper to the coordinator maintainer for a bash-preflight-invocation step.

### Severity model summary

Python is the only `hard` probe. `clone_auth` is `semi-hard` — blocks the preflight exit but is escapable via `--accept-no-git-auth`. All remaining prereqs (`uv`, `longpaths`, `pwsh`, `ue`) are `advisory` WARN — surfaced in the Phase 7 status table but do not stop the gate. Adding a new hard-fail to `--preflight` after consumers already exist requires PM sign-off and advisory-WARN migration window (see `install-surface-completeness.md § Post-Consumer Gates Must Be Advisory WARN`).
<!-- Review: code-reviewer — updated to reflect shipped semi-hard change for clone_auth; was "advisory WARN" which contradicted the actual severity model -->

---

## 5a. Provenance

This wiki documents the installer redesign ratified and shipped 2026-05-19. Full decision
trail:

- **Architecture parent:** `2026-05-19-coordinator-installer-redesign.md` (lives in meta-repo
  `docs/plans/`; not bundled with the plugin) — four decisions (D1 installer shape, D2 operator
  identity, D3 render-template primitive, D4 non-interactive contract); PM ratifications; the Director of Engineering
  review (APPROVED_WITH_NOTES).
- **Implementation plan:** `2026-05-19-coordinator-installer-redesign-implementation.md` (lives
  in meta-repo `docs/plans/`; not bundled with the plugin) — seven chunks (C1–C7), file-overlap
  analysis, sequential gate order. The Staff Engineer review integrated prior to execution.

<!-- Review: code-reviewer — spec_backlink paths were path-shaped but the plans live in meta-repo docs/plans/, not the plugin tree; converted to prose-shaped strings -->
- **Wiki amendments shipped 2026-05-19 (commit `9527128d`):**
  - `docs/wiki/plugin-identity-and-health-sentinels.md` — narrowed scope to
    runtime-queryable state, making the operator-configuration/runtime-identity distinction
    explicit (operator name is stable configuration, not runtime state).
  - `docs/wiki/ceremony-calibration.md` — added second valid override shape for
    instance-#1 promotion with named-instances-#2/#3 blocked on the same surface (the
    D3 case: three named templates on the same installer surface with structural dependence
    on the same renderer).

---

## 6. Phase architecture

```
Phase 1 — Environment probes (bash version, git repo, python3 real-vs-AppX-stub, agent-teams env var, scc, jq, pwsh, Windows Terminal, deep-research, global CLAUDE.md import)
Phase 2 — Operator identity (coordinator-identity.yaml existence check; capture or skip; working-repos discovery; CLAUDE.local.md render)
Phase 3 — Machine-local registry substrate (install-substrate.sh, install-health-run.sh, plugin.mirrors, coordinator_whoami venv, canonical structure, fan-out threshold, platform-localize)
Phase 4 — Meta-repo doctrine (~/.claude git-tracking offer)
Phase 5 — Project-local (coordinator.local.md install and project_type capture; currency stamp)
Phase 6 — Optional (persona customization, codex integration, percolation setup)
Phase 7 — Status report (setup-state receipt, guided-onboarding offer, repo-bootstrap offer)
```

Phase numbering shifted twice: the 2026-05-19 redesign moved CLAUDE.local.md/git-tracking out of Phase 1; the machine-local registry substrate was later promoted to its own standalone Phase 3, pushing meta-repo doctrine → 4, project-local → 5, optional → 6, status → 7. All Phase 1 probe steps are independent — they can fan in parallel before Phase 2 consumes their results.

### Flag contract

| Flag | Effect |
|---|---|
| `--non-interactive` | Suppresses `AskUserQuestion` calls; each callsite has a documented fallback (fail-loud, default-with-warning, or skip-with-note). |
| `--check-only` | Strict superset of `--non-interactive` — no mutations regardless of interactivity mode. Status report shows "would write" rows instead of writes. |
| `--reconfigure` | Re-runs Phase 2 even when `coordinator-identity.yaml` already exists with matching schema. |

The canonical invocation from the example-game-repo install chain (chain step 5) is `--check-only --non-interactive`.

---

## 7. Status-report schema

Phase 6 emits a structured status report. The schema is stable (append-only across coordinator versions; renaming or removing a check identifier is a breaking change requiring a version bump). Consumer (`example-game-repo` wrapper) matches via `<Check> .* <Status>` regex.

**Check identifiers:**
`git_repo`, `agent_teams_env`, `scc`, `deep_research`, `notebooklm`, `global_claude_md_import`, `meta_repo_doctrine`, `claude_git_tracking`, `coordinator_local_md`, `percolation`, `project_scaffolding`, `operator_identity`, `non_interactive_contract`, `render_template_helper`

**Status vocabulary:**
`ready`, `missing`, `not_configured`, `not_a_repo`, `skipped (non-interactive default)`, `failed`, `not_applicable`

Full schema wiki: `docs/wiki/coordinator-installer-status-schema.md`.

---

## 8. Central vs publish-target separation

<!-- Review: code-reviewer — "Central meta-repo" throughout this section refers to the DoE-claude clone (as of the 2026-07 cutover); the table column and header retain the legacy label for brevity. -->
The Central meta-repo (the DoE-claude clone as of the 2026-07 cutover) and the OSS publish-target are deliberately asymmetric. Expected diffs:

> **Updated 2026-06-22 (flat-layout / CLI-primary migration).** The OSS publish-target migrated to a
> flat Claude Code marketplace (top-level `coordinator/ deep-research/ web-dev/ data-science/` +
> `.claude-plugin/marketplace.json`); install is via the native `claude plugin` CLI + post-restart
> `/coordinator:install`, not a `setup/install.sh` script. The `setup/install.sh` row below is
> retained for historical reference — it is **no longer the OSS entry point** and is not shipped to
> OSS `main`. See `docs/plans/2026-06-22-oss-install-flat-layout-cli-primary-migration.md`.

| Artifact | Central | Publish-target |
|---|---|---|
| `setup/install.sh` | Absent | **Not shipped** (legacy/sandboxed manual fallback only — superseded by the `claude plugin` CLI + `/coordinator:install`) |
| `setup/publish.sh` | Present | Absent (Central meta-repo sync tool) |
| `setup/publish-targets.sh` | Present (machine-local, gitignored) | Absent |
| `machine-local`, `bin/_machine_local.py` | Present | Absent |
| `whoami/tests/` (18 test files) | Present | Absent (expected for OSS) |
| `commands/doctor.md` | **Absent in both** | **Absent in both** (deliberate gap — no dedicated coordinator doctor entry point) |

Structural divergence beyond path substitutions (`coordinator-claude/coordinator/` → `coordinator/`) and persona depersonalization is a drift signal worth investigating.

**Publish-repo content (setup scripts, top-level docs) is authored in the DoE-claude source clone only.** Direct edits to `X:/coordinator-claude/setup/install.sh` or similar bypass the planning/review/doctrine pipeline and drift silently. The canonical source is `coordinator/dist/publish-repo-{setup,toplevel}/` in the DoE-claude clone; `setup/publish.sh` (via `publish_sync.py`) propagates outward to the `~/.claude/plugins/coordinator-claude` published mirror.

---

## 9. Gotchas

### machine-local/ install home — RELOCATED to settings home (2026-07-06)

> **Resolved by the 2026-05-19 installer redesign** — `/coordinator:install` Phase 3 Step 1 lays down the machine-local substrate via `install-substrate.sh` (idempotent; never clobbers live registry files).
>
> **Updated 2026-07-06 (durable-substrate-to-settings-home plan)** — the install destination is now `~/.coordinator-claude-settings/machine-local/`, NOT `~/.claude/machine-local/`. `install-substrate.sh` runs the one-time idempotent migration (`migrate-substrate-to-settings-home.sh`) BEFORE any `mkdir`/seed so that an upgrading operator's `registry.local.toml` (carrying `repos.*` sibling paths and `plugin.mirrors.*`) is migrated intact. After migration, `~/.claude/machine-local` is a realpath-symlink to the settings home — retained for consumers that read the old path through the compat window.

The `.doe-root` bootstrap pointer remains the ONLY coordinator artifact in `~/.claude` (PM-ratified 2026-07-06). Everything else coordinator previously parked in `~/.claude` now lives at `~/.coordinator-claude-settings/`. See §10 for the full install-home shape and compat contract.

~~Neither `install.sh` nor `publish.sh` creates or seeds `~/.claude/machine-local/`. The deprecated `publish-targets.sh` fallback activates silently when the directory is absent.~~ OSS newcomers now get the substrate laid automatically at install time under the settings home; no manual bootstrap step is required.

---

## 10. Durable Substrate Install Home — `~/.coordinator-claude-settings`

<!-- spec-backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § Design + § Chunks C1–C8 -->

As of 2026-07-06, `/coordinator:install` Phase 3 installs the durable coordinator substrate to a **settings home** that is a deliberate sibling to `~/.claude` — NOT inside `~/.claude`. The settings home is clone-mutation-independent: a user editing the coordinator-claude plugin clone cannot break example-game-repo's or project-rag's identity/config resolution.

### Settings home location

```
COORDINATOR_SETTINGS_HOME              (explicit home root override — XDG, CI, sandbox)
  else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
```

**Linux/XDG users:** set `COORDINATOR_SETTINGS_HOME=~/.config/coordinator-claude` if you prefer XDG placement — it is not auto-detected because the home is a deliberate sibling to `~/.claude` and follows the `CLAUDE_HOME` redirect (auto-XDG would break sandbox isolation). `COORDINATOR_SETTINGS_HOME` must be set before running `/coordinator:install`.

### What installs to the settings home

| Settings-home sub-path | Contents |
|---|---|
| `machine-local/` | TOML registry (`registry.toml`, `registry.local.toml`, concern files) |
| `bin/` | Resolver family: `machine-local`, `_machine_local.py`, `claude-home`, `_claude_home.py`, `coordinator-settings-home`, `_settings_home.py`, `resolve-coordinator-clone`, `platform-localize.sh`, `.cmd` shims |
| `coordinator-whoami/` | The `coordinator_whoami` Python package source (session-identity layer) — relocated from `~/.claude/coordinator-whoami/` by `install-substrate.sh` (C10a); `coordinator.whoami_src` registry key set to this path in the same run. |
| `.coordinator-venv/` | The coordinator Python venv — REBUILT (never copied) by `install-substrate.sh` (C10a) via `bin/ensure-coordinator-venv.sh`; `coordinator.python` registry key pinned to `<settings-home>/.coordinator-venv/bin/python`; legacy `~/.claude/.coordinator-venv` removed only after rebuild + health probe confirm healthy. |
| `setup/` | Percolation mechanism |
| `settings-manifest.md` | Durable reference manifest |

### The one intentional `~/.claude` residual

**`.doe-root`** — a single-line read-only bootstrap pointer, written by `install-substrate.sh` and read by `resolve-coordinator-clone.sh` rung-1 on cold-start. It is the ONLY coordinator artifact that deliberately stays in `~/.claude`. PM-ratified 2026-07-06.

All other coordinator-owned `~/.claude` content (harness-owned `settings.json`, `.mcp.json`, `plugins/`, `projects/`, `.claude.json`) is Anthropic's — coordinator populates those files per the harness API but does not own their location.

### Transitional compat window (phase-2 gated tail)

Three consumer repos (example-game-repo, project-rag, project-rag-ue-addon) bind directly to the legacy surfaces. The compat layer keeps them working through the transition:

1. **`~/.claude/machine-local` symlink** — after migration, this is a realpath-symlink to `<settings-home>/machine-local/`. Consumer direct reads (e.g. `registry.local.toml`) resolve through the symlink unchanged.
2. **`~/.claude/bin/machine-local` retained-and-repointed forwarder** — legacy resolver names under `~/.claude/bin/` are RETAINED and repointed to exec the settings-home resolver. `project-rag-ue-addon`'s absolute-path probe of `~/.claude/bin/machine-local` continues to resolve.

**Removal:** the compat symlink and retained forwarders are removed only at the single phase-2 gated tail, triggered when all 5 consumers (example-game-repo, project-rag, project-rag-ue-addon, cockpit, example-orchestration-hub) confirm they have migrated off the legacy surfaces. This plan does NOT fire that tail.

### Uninstall / teardown symmetry

The uninstall path MUST clean the **settings home** (`~/.coordinator-claude-settings/`) substrate, not the old `~/.claude/bin` or `~/.claude/machine-local` legacy locations. A relocation that installs to the new home but uninstalls the old one leaves orphans at the settings home. The install and uninstall surfaces are:

- **Install:** `install-substrate.sh` → writes to `<settings-home>/machine-local/`, `<settings-home>/bin/`, `<settings-home>/coordinator-whoami/`, `<settings-home>/.coordinator-venv/`
- **Uninstall:** must remove `<settings-home>/` contents (not `~/.claude/machine-local/` or `~/.claude/bin/coordinator-*`) — see `external-plugin-live-resolution.md § 9. Install/Uninstall Symmetry — settings-home paths`

The compat forwarders under `~/.claude/bin/` are cleaned in the gated tail (phase-2), not in the normal uninstall path.

---

### coordinator_whoami package is not installed by any installer path (pre-2026-05-21)

`coordinator_whoami` (Python package under `whoami/`) was completely absent from all operator-facing health-check prose and installer status schema as of the 2026-05-20 audit. Three independent wiring failures: (1) setup didn't install, (2) onboarding was passive, (3) workstream-start silently skipped on import failure. The gap is closed by `/coordinator:install Phase 3 Step 6` installing it — but verify this step exists in your version before assuming it runs.

`/workstream-start` must emit a loud one-line nudge (not silent skip) when `coordinator_whoami` is not importable.

### example-game-repo repo discovery uses wrong env var as primary

CRITICAL audit finding (2026-05-20): `/example-game-repo:doctor` repo-discovery routing uses `EXAMPLE_GAME_REPO_REPO` (deprecated env var) as its primary lookup instead of `machine-local get repos.example-game-repo`. Operators who populate `registry.local.toml` with `repos.example-game-repo` but don't also set `EXAMPLE_GAME_REPO_REPO` hit the cwd-marker check or hard error silently. Fix: replace with `$(machine-local get repos.example-game-repo --default "")`.

### project-rag:doctor hardcodes a machine-specific drive letter

HIGH finding: `project-rag:doctor` Step 1 hardcodes `"X:/project-rag"`. Violates "build for someone else's machine." Fix: `$(machine-local get repos.project_rag --default "")`.

### workstream-start --red-only is vacuous-pass eligible on fresh installs

`scan-addon-health.sh --red-only` (workstream-start) is silent when no sentinel files exist. Fresh-install machine sees the health check pass with no signal that their install has never been doctor'd. `/workday-start` uses `--red-and-stale` (correct for daily triage); the asymmetry is intentional but means fresh-install gaps only surface at daily cadence.

### Cross-plugin coupling via ~/.claude.json parsing

`/workday-start` Step 3.6 originally parsed project-rag's `~/.claude.json` entry to extract the project-root path. This is cross-plugin coupling at the wrong layer — when project-rag migrated from stdio to HTTP transport, the args[]-walk pattern raised `KeyError`. The coordinator's contract with plugin CLIs is: **invoke + read exit code + read stdout**. Coordinator must not parse peer-plugin MCP entries.

Fix shipped: Step 3.6 now invokes project-rag's `cli.py cmd_staleness_survey` directly (with `PROJECT_RAG_PROJECT_ROOT` env), removing the coordinator-side JSON parsing.
