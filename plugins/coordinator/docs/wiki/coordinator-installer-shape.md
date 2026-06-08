---
title: Coordinator installer — design shape and audience contracts
created: 2026-05-19
kind: wiki
spec_backlink_arch: "2026-05-19-coordinator-installer-redesign.md (lives in meta-repo docs/plans/; not bundled with the plugin)"
spec_backlink_impl: "2026-05-19-coordinator-installer-redesign-implementation.md § C7 (lives in meta-repo docs/plans/; not bundled with the plugin)"
---

# Coordinator installer — design shape and audience contracts

Purpose: document the three audiences `/coordinator:setup` serves, the operator-identity
primitive it introduces, the render-template primitive it depends on, and the
`--non-interactive` contract that lets downstream callers invoke it without interactive
prompts. This is the canonical reference for the installer redesign shipped 2026-05-19.

---

## 1. Three audiences

`/coordinator:setup` is load-bearing for three distinct audiences. Understanding which
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

### Internal users (holodeck team and other downstream consumers)

**Who:** Teams where coordinator is a semi-hard prerequisite — chain step 5 per
`docs/plans/2026-05-08-install-chain-readiness-coord-and-dr.md`. These callers may invoke
`/coordinator:setup` programmatically from a setup wrapper (e.g. `scripts/holodeck_setup.sh`).

**Operative constraints:**
- Speed, idempotency, low-prompt. Hanging on an `AskUserQuestion` in a CI-like flow is a
  hard failure.
- Pass `--non-interactive` to suppress all prompts. Each prompt site has a documented
  fallback (see § 4. `--non-interactive` contract).
- The canonical holodeck pre-flight invocation is `--check-only --non-interactive` — reports
  substrate state without any mutation, without any prompt.
- Parse the status-report table to determine pass/fail. Column names and value enums are
  a stable contract — see `docs/wiki/coordinator-installer-status-schema.md`.

### Meta-repo operator dogfooding

**Who:** The meta-repo operator (the PM O'Duffy, or any future operator running
`~/.claude` as their personal coordinator tree) re-running `/coordinator:setup` after
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

This file is **operator-local**. It is written by `/coordinator:setup` at runtime and
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

`/coordinator:setup` writes `version: 1` today. Migration is documented when `version: 2`
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

`/coordinator:setup` and `/repo-setup` both render templates. The shared helper
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
supported and is the canonical holodeck chain-step-5 pre-flight invocation shape.

### Per-callsite annotation vocabulary

Each `AskUserQuestion` callsite in `/coordinator:setup` carries one of three annotations:

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

Five prompt sites exist in `/coordinator:setup` (per substrate-correction B in the
implementation plan):

| Phase | Prompt | Annotation | Rationale |
|-------|--------|------------|-----------|
| Phase 2 — Operator identity | Operator name (`AskUserQuestion`) | `fail-loud` | No safe default — operator name is not derivable; a wrong name silently misidentifies the operator in all downstream renders. |
| Phase 3 — Meta-repo doctrine | Git-init Initialize/Skip (`AskUserQuestion`) | `default-with-warning` | Default: `Skip`. `git init` is reversible; defaulting to skip is safer than defaulting to init. |
| Phase 4 — Project-local | `project_type` prose-prompt | `fail-loud` | Note: the prompt fires only when `coordinator.local.md` is absent. When it fires under `--non-interactive`, no safe default exists — `general` might be correct but it might silently miss domain-specific scaffolding. |
| Phase 4 — Project-local | `project_subtypes` prose-prompt | `default-with-warning` | Default: empty subtypes list. Subtypes are advisory; empty is the documented neutral default. |
| Phase 5 — Optional | Persona customization Keep/Customize prose-prompt | `default-with-warning` | Default: `Keep defaults`. Customization is opt-in cosmetic; the canonical names are the default. |

For the producer-side row contract that holodeck-callable wrappers should pin against
(column names + value enums), see `docs/wiki/coordinator-installer-status-schema.md`.

---

## 5. Provenance

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
Phase 1 — Environment probes (git repo, agent-teams env var, scc, deep-research, global CLAUDE.md import)
Phase 2 — Operator identity (coordinator-identity.yaml existence check; capture or skip)
Phase 3 — Meta-repo doctrine (CLAUDE.local.md install consuming Phase 2 identity; ~/.claude git-tracking offer)
Phase 4 — Project-local (coordinator.local.md install and project_type capture)
Phase 5 — Optional (persona customization, percolation setup)
Phase 6 — Status report
```

Phase numbering shifted during redesign (2026-05-19): the original Phase 1g (CLAUDE.local.md) and Phase 1h (git-tracking offer) became Phase 3. All probe steps (1a/1b/1c/1d/1f) are independent — they can fan in parallel before Phase 2 consumes their results.

### Flag contract

| Flag | Effect |
|---|---|
| `--non-interactive` | Suppresses `AskUserQuestion` calls; each callsite has a documented fallback (fail-loud, default-with-warning, or skip-with-note). |
| `--check-only` | Strict superset of `--non-interactive` — no mutations regardless of interactivity mode. Status report shows "would write" rows instead of writes. |
| `--reconfigure` | Re-runs Phase 2 even when `coordinator-identity.yaml` already exists with matching schema. |

The canonical invocation from the holodeck install chain (chain step 5) is `--check-only --non-interactive`.

---

## 7. Status-report schema

Phase 6 emits a structured status report. The schema is stable (append-only across coordinator versions; renaming or removing a check identifier is a breaking change requiring a version bump). Consumer (`holodeck` wrapper) matches via `<Check> .* <Status>` regex.

**Check identifiers:**
`git_repo`, `agent_teams_env`, `scc`, `deep_research`, `notebooklm`, `global_claude_md_import`, `meta_repo_doctrine`, `claude_git_tracking`, `coordinator_local_md`, `percolation`, `project_scaffolding`, `operator_identity`, `non_interactive_contract`, `render_template_helper`

**Status vocabulary:**
`ready`, `missing`, `not_configured`, `not_a_repo`, `skipped (non-interactive default)`, `failed`, `not_applicable`

Full schema wiki: `docs/wiki/coordinator-installer-status-schema.md`.

---

## 8. Central vs publish-target separation

The Central meta-repo and the OSS publish-target are deliberately asymmetric. Expected diffs:

| Artifact | Central | Publish-target |
|---|---|---|
| `setup/install.sh` | Absent | Present (1271 lines; OSS entry point) |
| `setup/publish.sh` | Present | Absent (Central meta-repo sync tool) |
| `setup/publish-targets.sh` | Present (machine-local, gitignored) | Absent |
| `machine-local`, `bin/_machine_local.py` | Present | Absent |
| `whoami/tests/` (18 test files) | Present | Absent (expected for OSS) |
| `commands/doctor.md` | **Absent in both** | **Absent in both** (deliberate gap — no dedicated coordinator doctor entry point) |

Structural divergence beyond path substitutions (`coordinator-claude/coordinator/` → `coordinator/`) and persona depersonalization is a drift signal worth investigating.

**Publish-repo content (setup scripts, top-level docs) is authored in Claude Central only.** Direct edits to `X:/coordinator-claude/setup/install.sh` or similar bypass the planning/review/doctrine pipeline and drift silently. The canonical source is `coordinator/dist/publish-repo-{setup,toplevel}/` under Claude Central; `publish_sync.py` propagates outward.

---

## 9. Gotchas

### machine-local/ is never created by the installer

Neither `install.sh` nor `publish.sh` creates or seeds `~/.claude/machine-local/`. The deprecated `publish-targets.sh` fallback activates silently when the directory is absent (no warning). OSS newcomers cannot leverage `machine-local` for coordinator config without a manual bootstrap step. This gap is Medium-severity today; blocking when the deprecated fallback is retired.

Mitigation for now: document the manual step. Long-term fix tracked in `state/coordinator-improvement-queue.md`.

### coordinator_whoami package is not installed by any installer path (pre-2026-05-21)

`coordinator_whoami` (Python package under `whoami/`) was completely absent from all operator-facing health-check prose and installer status schema as of the 2026-05-20 audit. Three independent wiring failures: (1) setup didn't install, (2) onboarding was passive, (3) workstream-start silently skipped on import failure. The gap is closed by `/coordinator:setup Phase 3 Step 6` installing it — but verify this step exists in your version before assuming it runs.

`/workstream-start` must emit a loud one-line nudge (not silent skip) when `coordinator_whoami` is not importable.

### Holodeck repo discovery uses wrong env var as primary

CRITICAL audit finding (2026-05-20): `/holodeck:doctor` repo-discovery routing uses `HOLODECK_REPO` (deprecated env var) as its primary lookup instead of `machine-local get repos.holodeck`. Operators who populate `registry.local.toml` with `repos.holodeck` but don't also set `HOLODECK_REPO` hit the cwd-marker check or hard error silently. Fix: replace with `$(machine-local get repos.holodeck --default "")`.

### project-rag:doctor hardcodes a machine-specific drive letter

HIGH finding: `project-rag:doctor` Step 1 hardcodes `"X:/project-rag"`. Violates "build for someone else's machine." Fix: `$(machine-local get repos.project_rag --default "")`.

### workstream-start --red-only is vacuous-pass eligible on fresh installs

`scan-addon-health.sh --red-only` (workstream-start) is silent when no sentinel files exist. Fresh-install machine sees the health check pass with no signal that their install has never been doctor'd. `/workday-start` uses `--red-and-stale` (correct for daily triage); the asymmetry is intentional but means fresh-install gaps only surface at daily cadence.

### Cross-plugin coupling via ~/.claude.json parsing

`/workday-start` Step 3.6 originally parsed project-rag's `~/.claude.json` entry to extract the project-root path. This is cross-plugin coupling at the wrong layer — when project-rag migrated from stdio to HTTP transport, the args[]-walk pattern raised `KeyError`. The coordinator's contract with plugin CLIs is: **invoke + read exit code + read stdout**. Coordinator must not parse peer-plugin MCP entries.

Fix shipped: Step 3.6 now invokes project-rag's `cli.py cmd_staleness_survey` directly (with `PROJECT_RAG_PROJECT_ROOT` env), removing the coordinator-side JSON parsing.
