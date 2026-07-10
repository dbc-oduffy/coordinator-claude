# Changelog

All notable changes to coordinator-claude are documented here.

## [Unreleased]

## [3.0.0] — 2026-06-27

> Theme: **re-architecture of the document-infrastructure / artifact-shape contracts for standardization and queryability** — the largest structural shift since the move to super-skills. The coordinator's entire artifact surface (handoffs, queues, lessons, completions, audit records, review trail, week-changelog) was given uniform, machine-addressable shapes via the example-initiative fleet-substrate (tc-0 → tc-4) and the artifact-shape-contract (v1.1 → v1.5), so the whole substrate is now uniformly queryable. The second theme is a large install-surface + macOS cross-platform-portability hardening cohort from clean-target dogfooding. The breaking contract changes below are why this is a major bump.

### Breaking changes

**Distribution consolidated from five plugins to a single `coordinator` plugin.** The v2 marketplace shipped `coordinator`, `web-dev`, `data-science`, `deep-research`, and `notebooklm` as separate plugins; v3 folds them into one `coordinator` plugin with a flat repository layout (`source: .` at the repo root). The front-end (`web-dev`), data-science, and research (`deep-research`/`notebooklm`) agents and skills now ship inside `coordinator`. Consumers upgrading from 2.9.0 install the single plugin — the separate marketplace entries are retired.

**`coordinator-schema-version` bumped v1 → v2.** The install contract and all central-owned record readers move to schema epoch 2. Consumers of coordinator record contracts must account for the v2 shapes.

**`superseded` retired as a handoff status value.** Supersession of a handoff is now expressed as `status: consumed` + `deployment_state: abandoned` (+ `predecessor`/`supersedes:` lineage) rather than a distinct `superseded` status. Doctrine, code, and existing data were migrated; the cockpit contract was narrowed to match.

**Artifact shapes restandardized across the record family.** example-initiative tc-0 → tc-4 gave plans, decisions, sidecars, queues, lessons, audit records, atlas files, and week-changelog dailies canonical machine-addressable shapes; the artifact-shape-contract emits versioned schemas (v1.1 → v1.5, including new record types and a deliverable-type-schema taxonomy with kind-aware `matchSchema`). Downstream consumers of these shapes (the cockpit / example-repo fleet) should re-vendor against the v1.5 contract.

### Highlights

- **example-initiative fleet-substrate (tc-0 → tc-4)** — canonical baton shape + cross-type liveness predicate + GENERATE-altitude scaffolder; records/queues/lessons consolidation; expressive-audit canonical shape; fleet machinery + versioned contract emission.
- **Artifact-shape-contract v1.1 → v1.5 + cockpit-contract v2.0** — example-repo example-workstream asks, datetime-coherence (contract v1.5.0), fleet-shaped `coordinator_roots[]`, owner-enum seam (closes a personal-data publish-tree leak), live `state/cockpit-emission.json` C2 producer.
- **Install-surface completeness + macOS / cross-platform portability** — install-chain Phase B, declarative `system_prerequisites`, fresh-machine `~/.claude` landing, deep-research install-parity, `/bin/sh` polyglot shebang, macOS phase-zero bash login-shell provisioning, persisted machine slug, OSS flat-layout / CLI-primary migration.

Full per-entry detail with source links: `state/week-changelog/` archive for the week of 2026-06-14 and `archive/release-notes/2026-06-27-v3.0.0.md`.

## [2.9.0] — 2026-06-24

> Theme: **native-CLI install migration + install-suite hardening, from a week of clean-target dogfooding.** This release cuts over to the native `claude plugin` CLI as the primary install path and is the harvest of stress-testing `coordinator:install`, `repo-setup`, the install-chain walker, and the publish/percolate path against fresh machines (macOS Apple-Silicon + new-clone). Most entries close a gap that only appears on a machine you've never seen.

### Breaking changes

**`/coordinator:setup` is now the install-chain walker only — repo scaffolding moves to `/coordinator:repo-setup` (2026-06-22).** The scaffolding command (`commands/setup.md`) was a redundant wrapper over `/coordinator:repo-setup` (which already does single-repo *and* `--batch` fleet via the same orchestrator) and collided with the ecosystem-wide `/<repo>:setup` install-chain-walker convention. It has been retired. Migration:

| Old verb | New verb |
|---|---|
| `/coordinator:setup` (scaffold a repo) | `/coordinator:repo-setup` |
| `/coordinator:setup --batch` (fleet) | `/coordinator:repo-setup --batch` |

`/coordinator:setup` now unambiguously runs the install-chain walker (the `setup_skill` named in `docs/install/agent-install-manifest.json`). See `docs/plans/2026-06-22-oss-install-flat-layout-cli-primary-migration.md`.

`/project-onboarding` and `/bootstrap-repos` consolidated into single `/repo-setup` command (2026-06-08). Migration:

| Old verb | New verb |
|---|---|
| `/project-onboarding` | `/repo-setup` |
| `/bootstrap-repos` | `/repo-setup --batch` |

Rationale: new-project setup is infrequent enough that muscle-memory cost is low. Single consolidated surface eliminates the "which verb do I invoke when" decision the prior dual-surface architecture imposed on every setup site. See `docs/plans/2026-06-08-repo-setup-consolidation.md` (and the Decision-#0 reversal of 2026-05-30 in that plan) for the full architectural rationale.

### Added

- **`/coordinator:new-project` — one-command greenfield repo creation.** Creates the directory, `git init`s, scaffolds a vendored stack template (`next-app` = Next/React/TS/Tailwind/Vitest shell, or `empty`), delegates coordinator onboarding to `/coordinator:repo-setup`, and offers an opt-in remote (never defaults to public, never creates a remote without an explicit choice). Sibling of `repo-setup`: **create-new** (`new-project`, from any cwd) vs **onboard-existing** (`repo-setup`, inside the folder). Promptable inputs with defaults (`--name`, `--parent`, `--template`, `--remote`).
- **Three-state Claude-home install classifier.** `install.sh` now distinguishes a *pristine* `~/.claude` from a *used-vanilla* and an already-*configured* one, and adapts the install path to each instead of assuming a clean home.
- **PowerShell 7 + Windows Terminal as default-on install prerequisites.** Windows operators are now provisioned a modern shell baseline by default.
- **Distill cruft-sweep — two-layer filesystem hygiene.** Layer 1 `bin/cruft-sweep.sh` (mechanical) + Layer 2 `/cruft-sweep` (judgment + registry-diff), with an EM front-line self-clean at workstream-complete.
- **Runtime tripwire** — a model-aware nudge that actuates the 15-minute executor ceiling, with an orphan-tail max-age cap.
- **Partitioned code-review parallel-integrator fan-out** (`bin/fan-out-integrator.sh`) — integrator dispatches now run 1:1 with reviewer slices.
- **Atlas attestation clock split** — a `last_attested:` schema field separates "when the doc was written" from "when its claims were last verified."
- **Durable coordinator venv pin.** `ensure-coordinator-venv.sh` (idempotent create + seed + pin, build mutex, network-aware fail-loud) gives `coordinator_whoami` and the doctor a stable interpreter on a fresh machine.
- **Windows console-flash suppression.** PreToolUse Bash/Write offer-hooks plus portable `creationflags` for subprocess spawns stop the console-window flash on Windows installs.
- **Coordinator declares its full `system_prerequisites`.** The agent-install manifest now carries `bash` (hard, ≥4.3 — `coordinator-safe-commit` uses `local -n`), `claude_code` (semi-hard, canonical CLI runtime, auto-install), `node` (auto-with-confirmation), and `typescript` (semi-hard, auto-install) entries — 13 entries total, manifest contract v3. Restart guidance is now concrete (terminal → `cd ~/.claude` → `claude`) with auto-accept-mode encouragement across the guided playbook and `AGENT.md`.
- **Onboarding spine discovers and interleaves ORIENT batons agnostically.** Step 0 of the install-chain walker previously found install batons only via `grep -l 'install_chain_order:'` — the exact field separately-seeded *orient* batons omit, so orientation fell on the floor at walk time. The spine now runs a second agnostic discovery sweep (`kind: spinoff` + no `install_chain_order:` + orient-shaped filename/title), pairs install↔orient legs by longest-prefix stem (equal-tie → ambiguous, never auto-pick), and interleaves them (`ready_to_fire` after its install leg, `awaiting_gate` to the tail). New optional `orient_after: <repo-id | "leaf">` baton field expresses knowledge-before-control cross-capability dependencies.
- **Setup-time substrate completeness.** `repo-setup` now seeds the downstream artifacts a project needs to be coordinator-operable from minute one: test-command keys, a health-ledger, an explicit RAG-index decision, and `.node-version`/`.nvmrc` resolution via `fnm`. `install-substrate.sh` audits host cores/RAM into a `hardware.*` machine-local SSOT (registered concern + P-16 doctor probe) and installs the `fnm` binary. OSS installer is at parity via a new `install-substrate.sh --setup-only` flag (seeds the machine-local region, exits before machine-env ops; full-install path byte-unchanged), removing ~200 lines of duplicated seeding.
- **`bin/handoff-transition.js consume` + `cs_consume_handoff` wrapper.** An atomic single-write frontmatter transition (`status→consumed`, `deployment_state→in_flight`, `+consumed_at/consumed_by`) for the `/pickup` Step 5 lifecycle write. Because it writes via node-over-Bash it is structurally invisible to the Edit-only consumed-handoff freeze hook — the prior two-sequential-Edit approach tripped its own hook.
- **Chain-end review-coverage gate** (`bin/review-coverage-gate.sh` + shared `lib/review-coverage-core.sh`) — unconditional Step 2.9 in `/workstream-complete` and Step 1.65 in `/merge-to-main`, verifying every workstream in a session's range has a passing review trail before the chain-end ceremony.
- **Cockpit-contract 1.0 cutover** — `SnapshotEnvelope`/`LessonSummary`/`PlanSummary` entities; `schema_version` sourced from the contract bundle (killed the hardcoded literal); `query-records` `TYPE_TO_GLOB` derived from the schema registry (single SSOT).
- **Deliverable-type schema taxonomy** — frontmatter validation now discriminates by `kind:` field, not directory position (fixes the sidecar fight-the-hook problem); 7 content-shaped sidecar schemas shipped.
- **prereq-probe self-source collision guard** — fail-loud when a vendored lib resolves to the coordinator's own copy; isolated-subdir vendor directive.

### Changed

- **Native `claude plugin` CLI is now the primary documented install path.** The agent-install flow drops `setup/install.sh` and the sentinel/baton staging in favour of the native CLI; solo post-restart routes to `/coordinator:install` (+ `/workday-start` for queued chain legs). Windows gains a `python3` App-Execution-Alias prereq. See `docs/plans/2026-06-22-oss-install-flat-layout-cli-primary-migration.md`.
- **`/coordinator:repo-setup` produce-not-prescribe.** Repo-setup now emits minimum-viable downstream artifacts and installs `coordinator_whoami` self-sufficiently in Phase 1, rather than prescribing files the consumer must hand-author.
- **DR-148 bash baseline.** Every shipped `.sh`/hook now targets bash ≥ 4 + BSD coreutils; stock macOS bash 3.2 is unsupported as an execution target (fail-loud guard with brew remediation). `coordinator:install` provisions brew bash.
- **`tasks/` vs `state/` folder split.** Load-bearing session substrate lives under `state/` (never swept); ephemera under `tasks/` (swept aggressively by `/distill` and `/update-docs`). A tripwire blocks writing a load-bearing surface under `tasks/`.
- **Acceptance-oracle parser grammar-first rewrite**, with backtick-tolerance for typed prefixes; `plan-coverage-checker` Lens 4 retired.
- **Percolate-hardening** — content-aware copy gate, source-authoritative `plugin.json`, and a `publish.sh` version-regression gate.
- **Executor flight-recorder sidecars** — plan bodies are now mechanically immutable to executors; status writes go through a sidecar.
- **Background-by-default `Agent` dispatch is now enforced.** Foreground dispatch is hard-blocked by a PreToolUse hook (with `COORDINATOR_AGENT_FOREGROUND_OK=1` escape), reconciled with param-less Agent harnesses via a capability-probe gate.
- **Review-integrator emits a bulk-dispositions block** (with optional Rationale prose) instead of per-finding inline annotations.
- **Cross-machine portability for Claude-home settings** — a settings union + per-machine overrides driven by a `platform-localize` hook.
- **`#!/bin/bash` → `#!/usr/bin/env bash`** normalized across 82 scripts.
- **`/update-docs` doc-link check** renumbered from Phase 11e to Phase 12 (EM-led); DoE handoff-tracker refresh wired into `/workday-start`.
- **git-lfs is a step-zero materialization requirement.** New `/coordinator:install` step 1a.3 runs an idempotent `git lfs install` (act-not-gate) so operators reaching `install` directly — not just via `first-run.sh` — get LFS enablement; the prior enablement lived only in first-run, leaving direct-install operators with an advisory WARN. Doctrine seeded in `install-surface-completeness.md`: the silent-pointer/orphaned-object failure shape, the `git lfs pull` + `git lfs ls-files` materialization-assert, and the altitude split (coordinator proactive-install + advisory-verify; LFS-content repos own the hard pull+assert).
- **Exec-bit precommit gate is wired into `/coordinator:install`.** `install-meta-repo-precommit-hook.sh` gained an explicit repo-root arg and is now installed from `commands/install.md` § 1a.2 + `repo-setup` § 3f.5.5 against `"$HOME/.claude"` — so every operator (ours and any OSS coordinator-claude user) gets the gate on their own `~/.claude`. It was previously wired only into `/repo-setup`, which runs with cwd = a consumer project where the helper no-ops.
- **agent-install contract § step 5 blesses curated ordered-leg `/pickup`.** The contract previously prescribed `/workday-start` as the sole sanctioned post-restart instruction; it now blesses a curated, ordered direct `/pickup` of seeded *leg* batons as equally valid, recasting the sanctioned test as the safety goal (no dangling-spine hard-`/pickup`; legs idempotently re-seeded) rather than the specific verb — the right UX for a leaf-is-entry-point downstream.
- **`do-now` applies to cross-repo memo asks.** Landing a fix on `origin/main` is the work-gate (do-now); a synchronized go-live is the PM-owned *release*-gate and is never the EM's standing reason to hold a landable fix. Codified in `cross-repo-communication.md`, the `/pickup` M3 Accept gate, and a `/workstream-complete` Step 2.65 belt-and-suspenders check.
- **`/autonomous` encodes an away-from-keyboard posture.** When autonomous mode is active, a pause is the most expensive action (it stalls the run until the PM physically returns). The First Officer Doctrine becomes the sole gate; reaching the goal via tracked patches/shims is acceptable provided the debt is logged and named in the end-of-run summary.

### Fixed

- **Exec-bit install-surface completion (DR-151).** The exec-bit invariant gate was widened to every shebanged tracked file (the 2.8.1 fix covered the 168 hook/bin scripts); OSS publish parity restored.
- **Personal-data leak scrub** across the `coordinator-claude` publish surface, plus a cross-repo audit; `cross-repo-memo` and `publish.sh` made macOS-portable.
- **`known_marketplaces.json` schema invariant** (`lastUpdated` now required) — `platform-localize.sh` writes and backfills it, with a regression test.
- **Runtime-tripwire EM-side false positive** firing on already-completed agents.
- **`mktemp` concurrency collision on BSD/macOS** (predictable suffix when `X` is not template-terminal) in the snapshot emitter.
- **snippet-sync** now fails loud when a canonical body extracts empty, and restored missing sentinels in the docs-checker / prior-art-check canonicals.
- **`bin/machine-local` reader exit-code contract + version-aware interpreter resolution.** The wrapper resolved its interpreter via `command -v python3`, which under a stripped daemon PATH picked system Python 3.9, tripped the 3.11+ guard, and returned rc=1 — indistinguishable from a genuinely-absent key. The wrapper now prefers a ≥3.11 interpreter (self-healing for any caller), and the reader contract is explicit: `0`=found, `1`=clean-absence, `2`=operational error (chosen over the literal memo proposal to preserve every `get X || fallback` consumer and the `has` boolean idiom).
- **`COORDINATOR_ROOT` test-only override no longer mis-roots workday ceremonies.** `/workday-complete` Step 3.5 backfill and `/workday-start` Step 1.85 detector hard-coded `COORDINATOR_ROOT="$HOME/.claude"`, but `COORDINATOR_ROOT` is the repo-root override — so on any non-meta project repo the skipped-day scan and changelog writes mis-rooted into the meta-repo. Removed from all three call sites; both scripts now warn-guard when `COORDINATOR_ROOT` is set but differs from the cwd git toplevel (`COORDINATOR_ROOT_WARN_SUPPRESS=1` escape).
- **session-init orphan sweep no longer false-abandons live handoffs.** The sweep now uses the canonical 30-minute liveness window with a `consumed_at` floor and is background-session-aware, and runs its liveness check in a `$GIT_ROOT` subshell (fixes OS1 isolation + OS4 cwd regression).
- **`/workstream-complete` Step 3 commit is scoped to the session pathspec.** It committed via `git commit -F "$msg_file"` with no pathspec, so on a shared branch it swept in files a sibling session had staged. It now captures the session path set into `WSC_PATHS` and commits scoped, with a pre-commit scope-verify step.
- **`setup/publish.sh` scoped publish no longer aborts on an unrelated unset registry key.** `_load_targets` hard-aborted any scoped publish when an unrelated portable target had an unset machine-local key; a DRYed `_rc1_skip_or_abort` helper now skips-when-filtered and fails-loud otherwise across all three loader arms.
- **Acceptance-oracle exit-4 remap gated to opted-in runners.** The oracle's default runner is bare `pytest`, which reserves exit-4 for its own usage error — so a real misconfiguration was silently downgraded RED → ENV-UNPROVISIONED. The exit-4→ENV remap now fires only when a custom runner was explicitly configured (`COORDINATOR_PYTEST_CMD` / `pytest_cmd:`); the default runner keeps exit-4 RED.

### Removed

- **`/coordinator:setup` scaffolding behavior** — folded into `/coordinator:repo-setup` (see Breaking changes).
- **`plan-coverage-checker` Lens 4.**
- **`dep-cve-auditor` marker ceremony** — folded into the change-aware `/workweek-complete` cadence.

## [2.8.1] — 2026-06-01

Patch release — 2026-06-01 weekly-close ceremony residual: install-surface exec-bit fix, an acceptance-oracle shell-test prefix, review-trail `scope_kind`, weekly-gate test hardening, plus the nomenclature cleanups deferred from 2.8.0.

### Fixed

- **Exec bit restored on 168 coordinator hook/bin `.sh` scripts.** Scripts under `coordinator/hooks/scripts/` and `coordinator/bin/` were committed at mode `100644`; on fresh Mac/Linux clones (and OSS publish repos) scripts invoked as `./x`, gated by `[[ -x ]]`, or run as bare `hooks.json` commands silently never ran (Windows masked it). Now `100755`, with an `exec-bit.test.js` lint pinning the invariant. Two mirror files owned by sibling source repos are allowlisted and memo'd to their EMs.
- **Weekly code-review gate test hardening.** The `block-no-verify` CRLF-regression test is now portable (removed GNU-only `grep -P`; `#!/usr/bin/env bash`) and fails loud when CRLF injection produces no CR bytes (was silently passing with zero coverage).
- **Restored a dropped behavioral spec block** in `setup.md` (the install "Test surface" expectations) lost during a line-ceiling trim.

### Added

- **`sh:` / `bash:` typed-prefix in the acceptance-oracle checker.** Gate-bound shell-script ACs (this repo's `.sh` test convention) can now be expressed and run (exit 0 = pass), with a path-validation guard (rejects `..`, absolute, non-existent script paths) before dispatch. Closes the false-red at `/merge-to-main` Step 0a.
- **Typed `scope_kind` (`diff` | `plan` | `integration`) on review-trail records.** The weekly scope helper classifies via the typed field (plan/integration → skip; diff → process) instead of fragile `..`-presence inference, with a backward-compatible fallback for existing records.

### Changed

- **`reviewed_at_session_end` handoff frontmatter key renamed to `reviewed_at_workstream_complete`.** 2.8.0 deliberately kept the old key name for record back-compat (the command/data-field split). That constraint turned out to be empty — the field is write-only (no consumer reads it) and zero handoff records, live or archived, ever carried it — so the back-compat justification was moot. The key now matches the renamed ceremony. Schemas (`handoff.yaml`, `handoff-archived.yaml`), the `/handoff` frontmatter template, and the spinoff anti-scope note are updated; no record migration was needed.

### Removed

- **`/session-start` and `/session-end` deprecation aliases removed.** The transition stubs shipped in 2.8.0 (aliasing to `/workstream-start` / `/workstream-complete`) are gone. The aliases were live for a single release cycle; the rename had already landed and the stubs carried no behavior of their own. Use `/workstream-start` and `/workstream-complete`. (Temporal "session start/end" prose and the `SessionStart`/`SessionEnd` platform hooks are unaffected — only the slash-command aliases were removed.)

## [2.8.0] — 2026-06-01

Minor release — lifecycle skill renames and nomenclature correction, plus a cross-repo-memo discovery surface, the install-contract orientation layer, and a generalized git-tag cut seam.

### Added

- **`cross-repo-memo --list-receivers`.** A canonical enumerator of every valid `--to` target (Claude Central first, then registered siblings with their paths). The previously-documented discovery path (`machine-local keys | grep '^repos\.'`) structurally could not surface Claude Central — it is special-cased to `~/.claude`, not a `repos.*` key — so a sibling EM enumerating receivers that way concluded "central isn't registered" and hand-authored into the inbox, the exact anti-pattern the CLI exists to prevent. The new flag also filters out publish-target mirrors so a repo where no EM reads inbound memos can never appear as a discoverable receiver (closes a latent `--to deep-research-em` misdelivery into the OSS mirror).
- **Install-contract orientation-supersession layer.** A continuing onboarding/install chain driven by the coordinator trunk: a durable continuation-handoff layer, conditional-and-live `supersedes:` on `kind: spinoff` batons (validated in the handoff frontmatter schema), and narrative coherence across the install/orient surfaces with a `provision` sub-axis. Captured in `agent-install-contract.md` and the continue-onboarding template.

### Changed

- **`/session-start` → `/workstream-start` (skill rename).** The PM-invoked front-of-session orientation skill is now `/workstream-start`. The old name `/session-start` is a deprecation alias that resolves to the same skill; it will be removed in a future major release. Update any automation or documented workflows that reference `/session-start`.
- **`/session-end` → `/workstream-complete` (skill rename).** The PM-invoked end-of-session wrap-up skill is now `/workstream-complete`. The old name `/session-end` is a deprecation alias; same removal timeline. The mutual-exclusion doctrine (`/handoff` vs. `/workstream-complete`) is unchanged — just the command name.
- **"session boot" coinage reverted.** The term "session boot" (used briefly in doctrine to name the automatic open-session machinery) has been removed. The platform hook is `SessionStart` (PascalCase, no slash); temporal prose uses "session start"; neither role needed a separate coined term. Doctrine updated across `CONTEXT.md` and `coordinator/CLAUDE.md`.
- **`merging-to-main` Mode A git-tag cut seam generalized (DR-149).** The Step 1.5 Mode A cut (`tag_anchor: git-tag`) gains two optional, additive `coordinator.local.md` knobs — `tag_prefix:` (default empty → bare `vX.Y.Z`; e.g. `example-game-repo-` → `example-game-repo-vX.Y.Z`) and `version_source:` (default `manifest` reads `pyproject`/`package.json`/`Cargo`; `tag` treats the latest `${tag_prefix}v*` tag as the version SSOT). Defaults reproduce the current bare-`v*` behavior exactly — non-breaking — so one cut seam now serves single-package repos and prefixed multi-version-line repos alike instead of forcing a hand-rolled fork.
- **Receiver-side ceremony calibration for memo pickup.** `/pickup` now scales its ceremony to the inbound memo's `--kind` rather than applying full workstream rigor to every memo, with the calibration recorded in `ceremony-calibration.md`.

### Motivation

The `{session}-start` / `{session}-end` skill names shadowed the `SessionStart` / `SessionEnd` platform hook identifiers, creating a three-way collision (skill slash-command, platform hook key, temporal phrase). Renaming to `workstream-*` breaks the collision: platform hooks keep `SessionStart`/`SessionEnd` (PascalCase, no slash); temporal "session start/end" prose stays as free English; the PM-invoked skills are now `workstream-start`/`workstream-complete`.

### Migration

```diff
- /session-start
+ /workstream-start

- /session-end
+ /workstream-complete
```

Deprecation aliases are active during the transition window — existing invocations continue to work. The `reviewed_at_session_end` frontmatter key is **not** renamed (it is a data key, not a command reference).

## [2.7.1] — 2026-06-01

Patch release — the 2026-06-01 weekly-close ceremony fixes.

### Fixed

- **Weekly validation gate unblocked.** `validate-capability-catalog` now reads the union of `capability-catalog*.md` so example-game-repo-domain agents documented in the `.example-game-repo.md` split count as covered; `_plugin_discovery` skips nested-git/submodule plugin dirs so the meta-repo no longer gates its release on a submodule's internal files; `setup.md` trimmed under the 500-line ceiling.
- **`block-no-verify.sh` made CRLF-robust.** The `FLAT_COMMAND` pipeline is collapsed onto a single physical line so a transient working-tree CRLF can't make a backslash-continuation escape the CR and crash the hook (which had denied all Bash mid-session).
- **`workweek-trail-scope.sh` hardened.** Skips (warns) trail records whose `sha_range` isn't a diff range instead of aborting the weekly gate on a co-located plan-review record, and validates `sha_range` against git-argument injection before handing it to git.

## [2.7.0] — 2026-05-31

Minor release. A large batch of session-lifecycle, hook, and skill work, plus the previously-undocumented 2.6.0 safety hook folded in. Headlines: EM-environment and boundary-guard hooks, a generated-tracker system, the cross-repo memo `--kind` lifecycle, the fan-out demotion, and assorted reviewer/skill hardening.

### Added

- **EM-environment & boundary-guard hooks** — effort/model self-check baked into the three start ceremonies and the `/plan` entry point; a nudge that catches the probe-spray loop at the boundary; a `git -C`-over-`cd` redirect; `block-destructive-rm` to guard uncommitted-work loss; `guard-settings-integrity` to auto-recover a clobbered `settings.json`.
- **`block-destructive-git-orphan` safety hook** (originally 2.6.0) — blocks destructive git operations that would orphan commits; pairs with the tool-output-flakiness floors.
- **Generated-tracker system** — schema fields, `query-records` memo type + renderer, producer templates emitting category+summary, lifecycle wire-ins, and edit-resistance for generated trackers.
- **Cross-repo memo `--kind {ask,consult,fyi}`** — a validated kind enum, `/pickup` form-classification fork, and surfacing priority by kind.
- **New skills** — `coordinator:systematic-debugging` (single-issue root-cause discipline) and `/coordinator-update` (OSS self-update).
- **`editable_sibling_venv` propagation mode** — drift-check support for addons editable-installed into a sibling host venv.

### Changed

- **Fan-out demoted from a skill to a methodology** — it collided with native Claude Code vocabulary; `fan-out-dispatch.sh` plus the dispatching-parallel-agents wiki are now the surface. Concurrency uses an organic ramp instead of a hard 6–8 cap.
- **`block-unauthorized-handoff`** reworked from a hard block into a warn-not-block nudge.
- **`bug-blitz`** now runs the full test suite every run and treats failing tests as first-class fix items.
- **`/workweek-complete` version bump** deferred to the consumer's `versioning-convention.md`.

### Fixed

- Tool-output-flakiness stop-at-floors (re-run-solo discipline, destructive-git/rm floors); session-end reviewer routing (named reviewers for plans/arch, not code output); install-portability sweep (bash-4 / BSD-GNU / python3 gotchas across the install surface); drift-check path corrections; assorted hook and skill repairs.

## [2.5.1] — 2026-05-26

Patch release — cleanup. Retires the `game-dev` plugin from the OSS distribution: it is Unreal-Engine/example-game-repo-coupled by nature (references the example-game-repo-docs/example-game-repo-control MCP servers and the `example-game-workbench-repo` sibling repo) and its MCP health gate aborts on use in a naked consumer, so it has no working configuration for an OSS installer. The plugin is now solely owned by the example-game-repo distribution. Coordinator ships a coherent operating system for colleagues, not generic personae as an OSS contribution.

### Removed

- **`plugins/game-dev/`** — the Game Dev Reviewer plus its Blueprint inspector/worker agents, knowledge base, and routing. Removed from `marketplace.json` and the README plugin inventory. The "build your own domain reviewer" reference framing now points at the shipped web-dev and data-science plugins.

### Added

- **Publish-time guard** (`setup/percolate-hooks/coordinator-claude/pre-rsync/`) — aborts a coordinator-claude publish if a `game-dev/` plugin dir reappears in the mirror source; override via `COORDINATOR_OVERRIDE_GAMEDEV_GUARD=1`. Registered in the tripwires wiki.
- **Doctrine** — one-way ownership note for example-game-repo-owned plugins in `plugin-extraction-and-distribution.md` (no bidirectional back-prop); editorial principle in the meta-repo local instructions.

### Fixed

- **Spec line-count ceiling** — trimmed `commands/workday-start.md` back under the 500-line CI ceiling.

## [2.2.0] — 2026-05-20

Minor release. Headline change: centralize the `CLAUDE_HOME` / `~/.claude` path-resolution definition as a load-bearing module that ships with `/coordinator:setup`, so peer-repo install scripts (project-rag, example-game-repo, deep-research, future Python/TS/Rust consumers) consume one canonical resolver instead of inlining a precedence chain in each repo. Also trims four pre-existing skills/commands to fit the CI spec-line-count ceiling (>500 lines), and ships the ergonomic-substrate / eager-agent-calibration chunks (meta-ask preamble snippet + sync verifier + templates-mirror verifier + new wiki).

### Added

- **`coordinator/lib/claude-home/`** — new load-bearing module that resolves the `$HOME` analog (`CLAUDE_HOME → HOME → USERPROFILE → Path.home()`), `~/.claude.json`, `~/.claude/`, `~/.claude/machine-local/`, `~/.claude/plugins/`. Ships as `bin/claude-home` (CLI), `bin/_claude_home.py` (Python module + CLI; importable for path resolvers AND atomic JSON read/write of `~/.claude.json` with BOM-tolerant read + JSONDecodeError enrichment), and `bin/claude-home.cmd` (Windows shim). Co-located README and 17-test stdlib-`unittest` suite (no pytest dep). Installed to `~/.claude/bin/` by `/coordinator:setup` Phase 3 Step 3. The `lib/<module>/` location signals "cross-repo contract surface, do not customize." Peer repos retire their local copies (e.g., `project-rag/scripts/_claude_config.py`) by shelling out to `claude-home` or importing `_claude_home`.
- **`docs/wiki/machine-local-registry.md § 4a`** — new doctrine section: filesystem-layout invariant (`.claude.json` and `.claude/` are SIBLINGS under `$HOME`, never nested); resolution-order precedence with rationale for why `CLAUDE_HOME` ranks ABOVE `HOME` (unlike `MACHINE_LOCAL_<KEY>` env vars which rank BELOW the registry); generic `read_config` / `write_config` JSON I/O surface; alignment policy naming project-rag as the canonical consumer to retire its inline copy.
- **`coordinator/lib/install-substrate.sh`** — new helper encapsulating `/coordinator:setup` Phase 3 mechanical work (machine-local substrate, bin/ resolver install, Windows PATH integration, Windows Python-resolution health checks: orphan AppX stub detection with `[y/N]` consent, store-alias-on-PATH warning, no-Python-at-all warning). Replaces ~190 lines of inline bash in `setup.md`; setup.md now describes the contract while the script does the work. Fail-loud on missing template directories (hard precondition for downstream skills).
- **`coordinator/lib/discover-working-repos.sh`** — new helper encapsulating `/coordinator:setup` Phase 2 Step 4 working-repos discovery (Tier A: `~/.claude/projects/` activity record; Tier B: common dev-folder layouts). Tier C interactive prompt remains in `setup.md`.
- **`coordinator/lib/workweek-trail-scope.sh`** — new helper encapsulating the `/workweek-complete` Step 7 prelude logic (parses `state/week-changelog/HEADER.md`, globs `state/review-trail/*.json`, computes `patrik_scope = unreviewed_week_SHAs ∪ cross-segment-seam SHAs`, writes `state/review-trail/.weekly-reviewer-scopes.json`). Subprocess-only, fail-loud, spec-backlinked. Same shape as `install-substrate.sh`.
- **`coordinator/snippets/meta-ask-preamble.md` + `bin/verify-meta-ask-preamble-sync.sh`** — new shared preamble snippet plus a sync verifier in the tripwires registry; ergonomic substrate for the eager-agent-calibration doctrine.
- **`coordinator/docs/wiki/eager-agent-calibration.md`** — new wiki capturing the design-as-offers ethos: agent-facing tooling defaults to offer-shape (lead with the better alternative), not nag-shape. Referenced from `~/.claude/CLAUDE.md § Implementation Standards`.
- **`coordinator/bin/verify-templates-bin-sync.sh`** — new verifier ensuring `templates/bin/` resolver scripts stay in sync between source and install targets.

### Changed

- **`commands/setup.md`** trimmed from 718 → 500 lines. Phase 3 (substrate + resolvers + Windows PATH/AppX) now a contract description that invokes `install-substrate.sh`; Phase 2 Step 4 (working-repos discovery) invokes `discover-working-repos.sh`. Phase 7 status table grows new rows for machine-local directory / tracked files / bin resolvers / Windows PATH+shims / registry seed; the four substrate rows are explicitly marked hard-preconditions (`FATAL` halts the chain).
- **`templates/bin/machine-local.cmd`** uses `%~dp0machine-local` instead of `%USERPROFILE%/.claude/bin/machine-local` — same `CLAUDE_HOME` correctness fix applied to `claude-home.cmd`. The shim now tracks wherever `~/.claude/bin/` lives, including non-default install roots.
- **`commands/workday-start.md`** — 545 → 496 lines. Prose compaction only; no extraction. Doctrine preserved (every step number, precedence rule, exit code, behavioral trigger intact).
- **`commands/workweek-complete.md`** — 651 → 498 lines. Step 7 prelude extracted to `lib/workweek-trail-scope.sh`; Step 4c UBT-gate, Step 4f enabledPlugins-drift, and Step 9.2 editorial-worker prose-compacted. All MANDATORY steps and gate behaviors preserved.
- **`skills/learn-lessons/SKILL.md`** — 593 → 499 lines. Prose compaction (merged duplicate Anti-Patterns entries, condensed DoE-adjudication rationale, tightened Local-mode auto-apply bounds). All five modes-and-cadence rules, the four-check gate, the routing schema, and the Change-Kind taxonomy intact.
- **`skills/repo-setup/SKILL.md`** (formerly `skills/project-onboarding/SKILL.md`) — 528 → 498 lines. Prose compaction (collapsed lazy-dir bullet enumeration to a reference to the existing table; compacted inline `docs/README.md` template from 43 to 28 lines). No phase ordering or behavior change.

### Fixed

- **`coordinator:setup` Phase 3 Step 1** is now fail-loud on missing template directories. Previously emitted an error and "skipped remaining steps of this phase" — Phases 4–7 still ran, leaving the operator with a broken-and-undiagnosable install. Now exits non-zero and halts the chain. Machine-local substrate is a hard precondition for downstream skills (project-rag, example-game-repo, deep-research all shell out to `bin/machine-local`).
- **`install-substrate.sh` PATH check** uses `cygpath -w "${_bin_dst}"` instead of hardcoded `$env:USERPROFILE` — previously, operators with `CLAUDE_HOME` set to a non-default location would have bin/ resolvers installed at `$CLAUDE_HOME/.claude/bin/` but PATH pointing at `%USERPROFILE%\.claude\bin`. Same env-var-passthrough pattern applied to the AppX `Remove-Item` call (defends against shell-injection through the resolved stub path).

### Internal

- Sonnet code-review pre-merge (three passes total): claude-home module (6 findings, all applied — `.cmd` shim `%USERPROFILE%` hardcode, `setup.md` `_bin_dst` precedence, Python import bootstrap respecting `CLAUDE_HOME`, missing failure-path tmp-cleanup test, two doc nits); install-substrate refactor pass 1 (14 findings, P1/P2 applied — Remove-Item injection, PATH/CLAUDE_HOME mismatch, silent PowerShell failure, `COORDINATOR_NON_INTERACTIVE==1`); install-substrate + discover-working-repos pre-percolate pass (10 findings, all P1/P2 applied — variable name mismatch `WORKING_REPOS_LIST` vs `WORKING_REPOS`, stale "Step 5" reference, GNU sed `\L` non-portable, git-worktree `.git`-as-file handling, `_install_one` `set -e` function fall-through, Tier A pipefail SIGPIPE).
- claude-home test suite: 17 tests, stdlib `unittest` (no pytest), all passing. Run: `python plugins/coordinator/lib/claude-home/tests/test_claude_home.py`.
- Spec-line-count trims dispatched as four parallel Sonnet executors (one per file), with tight constraints (extract bash blocks ≥30 lines OR compact prose only when every distinct doctrine point survives; FORBIDDEN: splitting files, changing step ordering, removing sections). Each executor reported what they did NOT cut and why. EM spot-checked diffs before commit. Net markdown delta: 437 deletions / 111 insertions across the 4 files; new helper +124 lines. CI line-count check now passes (10/2 → 11/1; only the pre-existing reference-validation failure remains).

### Also in 2.2.0 — earlier `coordinator_whoami` + `~/.claude/machine-local/` substrate work

Closes incompleteness in the 2026-05-19 `coordinator_whoami` + `~/.claude/machine-local/` migration that the project-rag-ue-addon dogfood doctor invocation surfaced as cross-team friction.

#### Added

- **`docs/wiki/coordinator-doctor.md`** — wiki-shaped agentic-steps doctor (explicitly NOT a slash skill) with nine probes covering machine-local registry and `coordinator_whoami` substrate. Downstream plugin doctors (example-game-repo, project-rag, project-rag-ue-addon) cite this wiki as the canonical health-verification surface; reinvention is named as a doctrine violation. Cross-team directives at Chunk 1 §5 bind: (a) coordinator-substrate probes MUST use delegation or augmentation shape; (b) binding-health classification MUST cite P-6 (live whoami) not P-7 (config-presence file read). Reviewed standalone by the Director of Engineering 2026-05-20 (DoE altitude, cross-team seam).
- **`cross-plugin-whoami-contract.md` — offline diagnostic surface.** New optional `source_kind: "live" | "offline"` discriminator (additive at contract v1; absent value treated as `"live"`). Plugins authoring CLI / file-read fallback envelopes when the daemon is unavailable label them `"offline"`; consumers classifying binding health MUST reject offline envelopes. Schema (`coordinator_whoami/schemas/whoami-envelope.v1.json`) extended additively — 86/86 whoami tests still pass.
- **Live-not-receipt invariant — consumer side.** The invariant now binds consumers, not just producers: synthesis-time consumers (doctor agents) MUST call live MCP `*_whoami`, NEVER read persisted whoami snapshots from disk as binding-health evidence.
- **Doctrine-vs-operator-guide pairing.** Both `cross-plugin-whoami-contract.md` and `machine-local-registry.md` gain audience preambles explicitly naming themselves as the substrate-doctrine half of a pair, with `coordinator-doctor.md` as the operator-guide half.
- **`scan-addon-health.sh --check-sentinel-presence` mode** — closes the H-1 vacuous-pass shape in session-start (`--red-only` could silently pass on fresh installs with no sentinels). The new mode fires a one-line bootstrap notice exactly when at least one plugin is installed AND no doctor sentinels exist anywhere; silent otherwise. Wired into `/session-start`.

#### Changed (substrate)

- **`commands/setup.md` Phase 3 See: line** cites `coordinator-doctor.md` as the canonical post-install verification surface.
- **`docs/wiki/machine-local-registry.md`** prose aligned to template ground-truth: `repos.example-game-repo` → `repos.example_game_workbench_repo` across §4 (naming + shell examples) and §8(f) anti-pattern. Template (`registry.toml.example`) is operative; the wiki now matches.
- **`docs/wiki/percolate-setup.md` Step 2** default-registers via `machine-local set publish.targets.<name>`; the legacy `publish-targets.sh` path is reachable only via `--legacy` flag.
- **`setup/publish.sh`** uses a portable PY fallback chain (`python3 || py -3 || python` with fail-loud) instead of bare `python`, so the script works on Linux/macOS AND Windows Git Bash. Smoke `--dry-run` clean across 4 targets.
- **`/session-start` orientation health-check** now invokes `python3 -m coordinator_whoami.project_rag --human` (gated on `coordinator_whoami` importability) as a spot-check of the coordinator/project-rag binding. Cites `coordinator-doctor.md` P-6.
- **`/repo-setup` (formerly `/project-onboarding`) Phase 4 Next Steps** cites `coordinator_whoami` as the canonical introspection surface with a one-line bootstrap pointer to `coordinator-doctor.md` P-1 through P-4 for machine-local health verification.

#### Fixed (substrate)

- **`/example-game-repo:doctor` discovery order** — `machine-local get repos.example_game_workbench_repo` is now tier 1; `MACHINE_LOCAL_REPOS_EXAMPLE_GAME_WORKBENCH_REPO` tier 2; `EXAMPLE_GAME_REPO_REPO` env var demoted to named-successor tier 3; cwd marker tier 4; hard error remediation now points operators at `machine-local-registry.md`. example-game-repo doctor's remediation prose now names machine-local as Tier 0 (canonical fix) before the env-var and reinstall fallbacks.
- **`/project-rag:doctor` PLUGIN_ROOT discovery** — prepended a `machine-local get repos.project_rag` lookup; Striker-specific `X:/project-rag` hardcoded candidate removed from the fallback loop.
- **`coordinator_whoami/project_rag/cli.py:270` HTTP-transport classification** — `_probe_claude()` now accepts `entry.get("url")` alongside `command` and `args`. Post-multi-RAG MCP daemon entries (HTTP transport, no `command` field) no longer mis-classify as `"broken"`. Mirror of project-rag-ue-addon's F4 finding from the same dogfood run.
- **`docs/wiki/wiring-env-source-of-truth.md`** — `status: current` → `status: deprecated`, `superseded_by: machine-local-registry.md`, with a prominent deprecation banner naming the dogfood-friction trigger. Wiring.env retirement is the worked precedent for the broader `~/.<project>/` → `~/.claude/<project>/` migration pattern.
- **`docs/wiki/authoring-an-addon.md:118`** — `required_env` row now flags `~/.project-rag/wiring.env` as transitional/deprecated and names `~/.claude/machine-local/project_rag.toml [env]` as the canonical successor for future addon authors.
- **`bin/verify-ue-overrides.sh`** — Striker-specific hardcoded paths (`X:/...`) removed; resolves UE-context roots via `machine-local get repos.example_game_workbench_repo` and `repos.project_rag`. Now fail-loud on absent registry instead of silent-pass.
- **`/session-start` `<plugin-cli-path>` literal placeholder** — resolved with an inline `~/.claude.json`-parsing snippet sourced from `commands/workday-start.md` Step 3.6.
- **Global `CLAUDE.md` line 16 parenthetical** — described `publish-targets.sh` as "(machine-local)" which conflated the legacy file with the canonical `~/.claude/machine-local/` registry. Reworded to "(per-machine legacy file, superseded by `~/.claude/machine-local/`)".

#### Migration

No breaking changes. Operators with `~/.claude/machine-local/` already populated need no action. Operators on a fresh install: `/coordinator:setup` Phase 3 lays down the substrate; populate `registry.local.toml` with sibling-repo roots. Verification: run the nine probes in `coordinator-doctor.md` §3 (on Windows Git Bash, substitute `py -3` for `python3`).

#### Sanitization

- OSS-side stale self-reference fixed in `cross-plugin-whoami-contract.md` (line was describing the file's own location as a "ships outward via setup/publish.sh to X:/coordinator-claude" destination).

## [2.1.0] — 2026-05-09

Minor release. New publish-flow skills, sanitization hardening, plugin-wiki bundling, and session-end review doctrine.

### Added

- **`coordinator:percolate` skill** — wraps `setup/publish.sh` with a deterministic dry-run → PM-confirm → real-run → optional CI-smoke flow. Adds coverage-drift detection (`find -newer .percolate-ignore`), impact-radius gut-check (top dirs / file types / sensitive paths), and a three-tier content-leakage scan (HIGH credentials / MEDIUM identity+internal+peer-repo / LOW informational) on every invocation. HIGH hits abort; MEDIUM forces the confirmation gate even on small changesets.
- **`coordinator:setup-percolate` skill** — idempotent walkthrough for registering a publish target, scaffolding `.percolate-ignore`, and seeding `setup/percolate-hooks/<target>/{pre-rsync,post-rsync,pre-ci}/`.
- **`bin/sync-plugin-wiki.sh`** — sweeps wiki references inside plugin files and demotes / copies guides into `<plugin-root>/docs/wiki/` so plugin-bundled wikis stay self-contained. Wired into `/update-docs`.
- **Plugin-bundled wiki convention** — when a plugin file cites a wiki guide, the guide MUST live inside the plugin at `<plugin-root>/docs/wiki/<name>.md`. Project-level wikis (architecture atlas, codebase-specific) stay in the consumer's `~/.claude/docs/wiki/`.

### Changed

- **Mandatory end-of-run Sonnet code review in mise-en-place Phase 6.** `/mise-en-place` now requires a minimum-Sonnet review on the cumulative diff before declaring the run complete; fires in both standard and hibernate modes (doctrine commit `e592b2d1`).
- **Session-end review doctrine recalibrated.** Reverted the closed-set blacklist over-correction; encoded a four-point shape framing for when `/session-end` and `/handoff` warrant a Sonnet (default) or Sonnet+the Staff Engineer (chain-end escalation, EM-judged) code review on the diff. Records land in `state/review-trail/*.json` and feed `/workday-complete` Step 9 + `/workweek-complete` Step 7. Doctrine: `docs/wiki/session-end-review.md`.
- **Bare-slash skill invocations standardized for 24 coordinator skills/commands.** `name:` frontmatter doctrine captured in `docs/wiki/writing-skills.md`.
- **`depersonalize-for-publish.sh` hardened** — extended identity-vocab and JSON coverage; sanitization sweep over 10 wikis + the 3 deferred wikis; PM-D2 placeholders, PM-D3 ue-bootstrap exclusion, PM-D4 disclaimer integrated.

### Fixed

- **`bin/coordinator-safe-commit` overlap-gate** — atomic `mkdir`-lock closes the prior TOCTOU window (the Staff Engineer finding 7; `flock` unavailable on Git Bash, used `cs_claim_handoff` pattern).
- **`bin/coordinator-safe-commit` combined-mode dead path** — `do_scope_from` now delegates to `do_scoped`, eliminating duplicated combined-mode code (the Staff Engineer finding 0).
- **block-off-daily-branch hook regex** — tightened cheap-gate to stop at the `--` pathspec separator.
- **`/percolate` post-rsync hook stdin** — always-pipe `</dev/null` to prevent blocking; pre-ci hook discovery added (Sonnet review-2 F0+F5).

### Sanitization

- Generalized hardcoded `c:/users/<user>/.claude` path in `/update-docs` Phase 14 (Step 2c MEDIUM).
- Dropped hardcoded `/x/<peer-repo>` list from `staff-eng.md` routing note (Step 2c MEDIUM).
- Source-edit sanitization sweep per audit Section 4.3.

## [2.0.0] — 2026-05-07

**This is a major release.** Three skill renames, one branch-naming change, and a new validator gate make this incompatible with v1.x consumers. See **Breaking Changes** and **Migration** below.

Five themes:
- A — Super-skill pattern (`coordinator:plan` / `coordinator:review` / `coordinator:review-code` as decision-tree super-skills)
- B — Loop-closure (`/bug-blitz`, `coordinator:learn-lessons`, `/dogfood` fully integrated into discovery surfaces)
- C — Daily-branch span-aware refactor (silent midnight rename; `work/{m}/{date}to{dd}` format)
- D — Bug-sweep 2026-05-06 (19 targeted fixes in `bin/`, `hooks/`, `lib/`)
- E — Doctrine consolidation (CLAUDE.md tightening, snippet-system maturation, prior-art-checker pre-flight)

### Breaking Changes

- **`coordinator:writing-plans` → `coordinator:plan`.** Skill body refactored from prose to decision-tree super-skill (Branch A triage / B substrate / C compose / Exit). Long-form doctrine extracted to `docs/wiki/writing-plans.md`. Existing `Skill(coordinator:writing-plans)` invocations break.
- **`coordinator:requesting-code-review` → `coordinator:review-code`.** Same super-skill refactor. `/requesting-code-review` slash command no longer exists.
- **`coordinator:using-git-worktrees` removed.** Doctrine carried by `CLAUDE.md` § Concurrent-EM Git Operations bullet 1 ("Worktrees forbidden") — no separate wiki page.
- **Daily-branch naming: `work/{machine}/{date}` → `work/{machine}/{span}`.** Span format carries dates across days for multi-day workstreams; midnight rename is silent. Validated regex from `lib/coordinator-daily-branch.sh`: `^work/[^/]+/[0-9]{4}-[0-9]{2}-[0-9]{2}(to[0-9]{2})?$`. Span branches look like `work/MACHINE-A/2026-05-04to07` — suffix is the trailing day-of-month only, separator is a literal `to`. External tooling that parsed the date suffix must handle date-or-span shape.
- **`description-budget` validator hard CI gate.** Skills with descriptions exceeding 150 chars (175 PM-gated) need explicit `description-budget: <N>` frontmatter exemption. `/workday-complete` Step 0b blocks on failure.

### Migration

For consumers with custom commands or skills that invoke renamed coordinator skills:

```diff
- Skill(coordinator:writing-plans)
+ Skill(coordinator:plan)

- Skill(coordinator:requesting-code-review)
+ Skill(coordinator:review-code)
```

For automation that parsed daily-branch names:

```bash
# Old: only date-suffix branches
[[ "$branch" =~ ^work/[^/]+/(20[0-9]{2}-[0-9]{2}-[0-9]{2})$ ]]

# New: date OR span — span is YYYY-MM-DD with optional `to<DD>` suffix
[[ "$branch" =~ ^work/[^/]+/([0-9]{4}-[0-9]{2}-[0-9]{2}(to[0-9]{2})?)$ ]]
```

For out-of-tree skills failing the description-length validator:

```diff
+ description-budget: 400
```

### Theme A — Super-skill pattern

Decision-tree super-skills replace prose skills for plan / review / review-code. A skill is a router with named branches: A triage / B substrate / C compose-or-work / Exit handoff. The EM walks branches by condition, not by reading prose. Long-form doctrine lives in `docs/wiki/writing-plans.md` and `docs/wiki/receiving-code-review.md` where it belongs as reference, not procedure.

Includes a plan-trigger-binding doctrine fix: `CLAUDE.md` § Plan-First Workflow now binds the trigger word "plan" mechanically to `Skill(coordinator:plan)` — writing a plan body to disk via `Write` without first invoking the skill skips substrate verification, the four PM doctrinal lenses, and the prior-art-checker → the Staff Engineer (`coordinator:staff-eng`) → integrator chain at Exit.

### Theme B — Loop-closure (bug-blitz / learn-lessons / dogfood)

- **`/bug-blitz`** — autonomous bug-backlog grinder, EM-serial commits at wave gates, integrated into `/session-start`, `/workday-start`, `/workweek-complete` Step 4, and README.
- **`coordinator:learn-lessons`** — unified surface (renamed from `lessons-trim`) covering local-mode / central-mode / recheck-mode lesson triage. Closed Phase 6 + R-code integration.
- **`/dogfood`** — smoke-driven fix-through super-skill, three-tier gate. Binary outcome: converge or switch gears, no defer.

### Theme C — Daily-branch span-aware refactor

Span-aware branch-naming with silent midnight rename. New shared lib `lib/coordinator-daily-branch.sh`. Hook `block-off-daily-branch.sh` simplified (no more commit-time date enforcement). Skills with inline overrides (`/workday-start`, `/merge-to-main`, `/consolidate-git`) updated. Doctrine in `docs/wiki/daily-branch-discipline.md`.

### Theme D — Bug-sweep 2026-05-06 (19 fixes)

Targeted fixes in `bin/`, `hooks/`, `lib/` from the 2026-05-06 sweep. Highlights: hash-set lookup in `coordinator-safe-commit do_scoped` (BS-012); atomic mktemp+mv in learn-lessons-config-update (BS-014); cross-platform mtime helper (BS-022); GIT_ROOT in context-pressure-precompact (BS-027); validate-commit chained-invocation detection (BS-019); set -f TOKENS array guard (BS-023). Full set: BS-2026-05-06-{004,007,010-017,019-027}.

### Theme E — Doctrine consolidation

CLAUDE.md tightening (40.6k→33.9k chars; rule density preserved, redundant inline enumerations collapsed to one-liners + links to authoritative wikis). Snippet-system maturation: 6 verify-sync scripts (`prior-art`, `docs-checker`, `default-routing`, `text-only-recovery`, `reviewer-calibration`, `project-rag-preamble`). Prior-art-checker pre-flight agent integrated into `/review-dispatch` Phase 2.7b — Sonnet recall over project wikis + global wikis + lessons + improvement queue, sidecar at `<plan-path>.prior-art-check.md`. Description-length validator (`bin/check-description-length.sh`) added with `description-budget` exemption frontmatter. New wikis: `dogfooding-doctrine.md`, `tiered-context-loading.md`, `prior-art-checker.md`, `docs-checker-pre-review.md`, `oom-reproducer-strategy.md`, `parallel-enrichment-seam-review.md`, `reviewer-routed-workers.md`, `round-trip-contract-tests.md`, `scoped-safety-commits.md`, `cleanup-sweep-hazards.md`, `claude-code-platform-gotchas.md`, `plugin-extraction-and-distribution.md`, `per-project-plugin-gating.md`, `example-game-repo-for-your-ue-project.md`, `rag-bait-conventions.md`, `reviewer-premise-challenge.md`.

### Also Added
- ISSUE_TEMPLATEs (command_request, docs_improvement, install_problem, reviewer_request) and `evals/` stub (W6 author-feedback roadmap).
- Role-first reviewer presentation + contracts index (W4 author-feedback roadmap).
- 13 user-typed commands migrated `commands/<n>.md` → `skills/<n>/SKILL.md` for bare-form slash invocation (pickup, handoff, spinoff, execute-plan, daily-review, code-health, architecture-rotation, enrich-and-review, bug-sweep, generate-repomap, staff-session, review-dispatch, session-start, session-end). Auto-runners stayed in `commands/` by design.

### Fixed
- `setup/install.sh --profile full` no longer warns: `deep-research` added to `PLUGIN_REGISTRY`.
- Windows console-flash regression: `coordinator-auto-push` and `hooks.json` SessionStart pwsh now invoked with `-WindowStyle Hidden`. Tripwire `bin/verify-no-powershell-flash.sh` greps shell + hook JSON.
- `git branch --show-current` Windows case-fragility: `coordinator-auto-push` canonicalizes via `git for-each-ref` before push, eliminating mixed-case daily-branch push failures.

### Removed
- **`remember` plugin removed.** Agent-summarized session memory (rolling daily/weekly/archive files under `.remember/`) was duplicating the work the handoff/commit/plan pipeline already does, at worse fidelity, with its own staleness modes and Windows-path-quirks. Recording-without-routing was the wrong layer to invest in; v2.0.0 invested in *consumers* (prior-art-checker, `/learn-lessons`, `/bug-blitz`) instead. Rationale chapter: [`docs/evolution/08-loop-closure.md`](docs/evolution/08-loop-closure.md). Live references purged from README, `setup/install.sh`, `docs/architecture.md`, `docs/getting-started.md`, `docs/agent-install.md`, `docs/safety.md`. `setup/patch-remember-plugin.sh` deleted. Historical references in older changelog entries and `docs/plans/2026-04-01-registry-submission-readiness.md` left intact as historical record.

## [1.10.0] — 2026-05-06

Four themes in this release: workday/workweek cadence split, layered reviewer-premise-challenge defense, PM-native operating layer reframe, and Codex opt-in add-on. Coordinator plugin bumps 1.0.0 → 1.1.0; the rest of the plugin set is unchanged.

### Theme A — Workday/workweek cadence split

`/workday-complete` had grown to 306 lines doing double duty: lightweight daily housekeeping AND release-grade ceremony. Multi-day workstreams don't fit a daily wrap, so the heavy half either got skipped or fired at the wrong cadence. This release splits the cadence into daily and weekly bookends, with a structured `state/week-changelog/` ledger acting as a thin index over handoffs (which remain the unit of session continuity).

### Added
- **`/workweek-start`** (new) — PM-invoked strategic orient at the start of a week. Reads the prior week's changelog, surfaces stalled workstreams, runs an orphan sweep, prompts the PM for 1–3 priorities, and resets-or-updates `state/week-changelog/HEADER.md` based on whether a `/workweek-complete` has occurred since the last `/workweek-start`.
- **`/workweek-complete`** (new) — PM-invoked release-grade close. Reads the week-changelog as canonical record, runs full validation + `/update-docs` + ShellCheck + Codex review + improvement-queue triage + scc snapshot, drafts release notes from changelog + `archive/completed/`, surfaces a version bump, invokes `/merge-to-main`, archives the daily files, and resets the HEADER.
- **`state/week-changelog/`** convention — per-machine daily files (`YYYY-MM-DD-{hostname}.md`) + shared `HEADER.md`. Per-machine layout eliminates concurrent-write conflicts when multiple machines wrap the same calendar day.
- **`bin/check-weekly-staleness.sh`** — emits `STALE` / `MILD` / `FRESH` / `UNKNOWN` based on days-since-last-weekly + commits-since-last-weekly thresholds (≥5 days AND ≥15 commits = STALE). Consumed by daily nudge and both weekly commands.
- **`/pickup` "while you were away" surface** — when the named handoff is from a prior day (not a same-day baton pass), surfaces one-line summaries of changelog blocks since the handoff date, capped at ~10 lines. Strengthens the handoff/pickup backbone for multi-workstream weeks.
- **`docs/wiki/workday-workweek-cadence.md`** — tutorial guide for the new cadence.

### Changed
- **`/workday-complete`** rewritten (307 → 210 lines). Drops `/update-docs`, scc, ShellCheck, Codex review gate, and improvement-queue triage action — all moved to `/workweek-complete`. Adds: read-only improvement-queue depth nudge (≥5 entries surfaces a one-liner, no triage), changelog append (synthesises today's block from handoffs + `/daily-review` summary, does NOT re-author), staleness check (surfaces "weekly is stale" when thresholds cross). `Validation:` field on the daily block is auto-filled from gate exit codes, never LLM-authored.
- **`plugins/coordinator/CLAUDE.md`** — new "Workday/Workweek Cadence" doctrine section ("handoffs are the atom, the changelog is the index"); existing improvement-queue triage rule updated to reflect daily-nudge / weekly-action split.

### Migration
- Existing projects do not need to do anything. `state/week-changelog/HEADER.md` is shipped as a seed template; first `/workweek-start` populates it. Until then, `bin/check-weekly-staleness.sh` returns `UNKNOWN` (no nudge fires).
- Existing `/workday-complete` workflows continue to work — the command does less, but everything it still does was already there.
- `/pickup` enhancement is additive; same-day handoffs (the common case) are unaffected.

### Design source
`docs/plans/2026-05-04-workweek-cadence-split.md` (the Staff Engineer APPROVED_WITH_NOTES — all findings folded in).

### Theme B — Reviewer premise challenge (layered W1–W5 defense)

Closes the "shape-correct, premise-wrong" gap surfaced by the 2026-05-04 example-game-repo `.uplugin Modules` incident: a plan was empirically refuted post-review because it reintroduced something `state/lessons.md` and the wiki had explicitly forbidden 5 days earlier; no checkpoint surfaced the prior prohibition. The layered defense adds challenge points across the pipeline so the same failure mode is caught at multiple stages rather than relying on any single agent.

#### Added
- **W1 — `writing-plans` skill** gains a negative-search step and a reversal-verb hint that suggests a staff-session at PM discretion when a plan reverses a recently-shipped decision.
- **W2 — `repo-specialist` agent** gains a counter-evidence pass with a hard always-read rule for `state/lessons.md`.
- **W3 — `staff-eng` (the Staff Engineer)** gains "Pass 0 — Premise & Alternatives" with three new structured fields, a `REJECTED` verdict (refuted alone — no architectural-superiority clause), and five hard guardrails. Self-reviewed `REJECTED`-trigger inconsistency caught and integrated.
- **W4 — `staff-game-dev` (the Game Dev Reviewer (`game-dev:staff-game-dev`))** gets a mirror of W3 so game-dev plans receive the same premise scrutiny.
- **W5 — `review-integrator`** treats `REJECTED` as advisory; EM override requires a verbatim PM quote.

#### Changed
- Calibration block byte-identical across all reviewers (`verify-calibration-sync` clean).

#### Design source
`docs/plans/2026-05-04-reviewer-premise-challenge.md` (the Staff Engineer APPROVED_WITH_NOTES — all 7 findings integrated).

#### Note
The `dfdcf8f` commit also carried an early-write probe addition to `plugins/deep-research/agents/repo-specialist.md` — orthogonal to the W1–W5 work but mixed into the same source-side commit and percolated together via `publish.sh`.

### Theme C — PM-native operating layer

The repo has always implemented a PM-EM split, but the README and surrounding doctrine framed it as "a Claude Code productivity framework." This release sharpens the framing: a *PM-native operating layer for AI engineering work* — turning product intent into scoped plans, delegated implementation, evidence, and ship/no-ship decisions, while keeping the PM technical enough to spot when something looks wrong. The framing acknowledges higher-altitude (fully non-technical PM) operation as future work, not current default; the current sweet spot is a technical-evaluating PM.

#### Added
- **the VP-Product Reviewer** (`plugins/coordinator/agents/vp-product.md`) — new primary reviewer (`coordinator:vp-product`), VP of Product (they/them), with software-engineering instincts. Stress-tests engineering choices: shape (concurrency model, sync vs. async, polling vs. event-driven, abstraction altitude), refactor-vs-patch calibration when AI execution makes refactors cheap, the dumb questions experienced engineers skip ("why single-threaded when threading is 30 lines?"), YAGNI-vs-laziness distinction, and "have you considered a different shape?" alternatives. Distinct from the Staff Engineer (code quality) and the Ambition Advocate (`coordinator:ambition-advocate`) (Staff Engineer backstop). Synced calibration block; `bin/verify-calibration-sync.sh` consumer list updated.
- **Scope modes in `writing-plans` skill** — required header field with explicit rules per mode: prototype, production-patch, feature, architecture, spike. Routes review depth and the evidence bar.
- **Acceptance Criteria + Non-Goals as required plan-header sections** — ends "done means whatever the agent says it means."
- **Definition of Ready gate** in `writing-plans` (pre-drafting) and **Definition of Done gate** in `verification-before-completion` (pre-merge).
- **Ship verdict** in `merging-to-main` Step 1.57 — every merge stages a verdict (ship / ship-behind-flag / hold / split / spike-only) for PR body and PM confirmation.
- **Demo Path** in `merging-to-main` Step 1.56 — for user-visible work, append demonstrable steps to the release notes.
- **"VP-Product Reviewer Pre-Flight" in `writing-plans`** — anticipate the VP-Product Reviewer's questions during plan drafting. The spectre of that review keeps the planner honest, so most actual VP-Product reviews are belt-and-suspenders backstops rather than gatekeepers catching laziness that should have been caught earlier.
- **`docs/evolution/` doc set** — README + 6 chapters: origin, handoffs-over-compaction, personas-as-ergonomics (the honest negative-result story), investigation-funnel, failure-modes (12-mode taxonomy with detection signals + prevention rules + recovery moves), what-we-rejected (the taste chapter, including external-review proposals declined with reasoning). The publish-repo answer to "evidence ledger" — outside readers evaluating the system see that the model has been pressure-tested and learns from failure.

#### Changed
- **README rewritten around PM-native thesis.** New lede framing, "What This Is *Not*" section to head off miscategorization, commands reorganized around 5 flows (build a feature, fix a bug, resume work, autonomous sprint, architecture change). Inventory table demoted to collapsed appendix.
- **Coordinator CLAUDE.md gains "Challenging the PM" doctrine** — explicit pushback triggers (request doesn't serve stated objective; change is larger than PM realizes; request hides a product decision; cheaper experiment available; scope expanding; acceptance criteria missing or unverifiable; PM asking to ship despite insufficient evidence).
- **Coordinator CLAUDE.md gains "PM Escalation Triggers — Ask vs. Don't Ask"** — explicit list cutting the ambiguity between EM implementation discretion and PM product authority.
- **Reviewer-calibration tripwire** updated — consumer list now includes `agents/vp-product.md` (the VP-Product Reviewer).

### Theme D — Codex opt-in add-on

`codex-review-gate` is now an opt-in add-on. The skill ships inside the coordinator plugin but is stripped from the install unless the user passes `--enable-codex` (or answers `y` at the new interactive prompt). Default installs no longer reference Codex from `/workweek-complete`, `/workday-complete`, or `/bug-sweep` summaries. `/bug-sweep --codex-verify` and the workweek Codex step both gate on skill presence — when absent, they skip silently and omit the line from their reports rather than printing _"skipped"_. Rationale: Codex was hassle for our setup and the integration was creating noise in routine reports; consumers who run Codex still have the on-ramp via the install flag.

### Plugin versions

- `coordinator`: 1.0.0 → 1.1.0 (substantive doctrine and reviewer additions)
- All other plugins: unchanged.

---

## [1.9.0] — 2026-05-03

### Removed — `remember` plugin

The `remember` plugin (automatic session memory via Haiku-summarized transcripts) is removed. Its Haiku-summarization PostToolUse and SessionStart hooks fired constantly across every session, burning tokens for no measurable workflow benefit beyond what the existing process guardrails already provide:

- Handoffs (`/handoff`, `/pickup`) carry forward what matters between sessions.
- The orientation cache, lessons file, project tracker, and `tasks/` artifacts cover continuity at the project level.
- Built-in conversation compaction handles in-session context.

Net effect: `remember` was redundant infrastructure for a problem already solved by discipline. Keeping it costs Haiku spend on every tool call with no signal anyone was reading the resulting `memory/sessions/*.md` files.

### Migration

- The plugin entry in `marketplace.json` is gone. Existing installs should run plugin-uninstall (or just delete the plugin dir).
- Accumulated `~/.claude/projects/<slug>/memory/sessions/` data dirs can be deleted; nothing reads from them.
- Five coordinator commands had their `remember`-aware paragraphs removed: `setup`, `session-start`, `session-end`, `update-docs`, `workday-complete`. Each now skips straight to its next step.

### Added (publish tooling)

- `setup/publish.sh` now prunes orphan plugin directories from the target (matching the existing per-file `--delete` semantics). Hidden dirs like `.git` are preserved. Respects `--dry-run`.

## [1.8.0] — 2026-05-03

### Theme — docs-checker as suggested pre-flight + inline-edit authority

Promotes the `docs-checker` Sonnet agent from optional reporting-only to a suggested pre-flight before Opus reviewer dispatch, with authority to apply AUTO-FIX-class corrections inline. Reviewer awareness propagated to all five Opus reviewers via a new sentinel-snippet sync surface, parallel to the existing calibration and project-rag-preamble patterns.

### Added
- **`docs/wiki/docs-checker-pre-review.md`** — full doctrine page: EM Decision Rules table (always-run for C++/UE; EM judgment elsewhere; freshness-marked against the current model), AUTO-FIX allowlist + hard prohibitions, scope constraint (artifact-only, never referenced files), project-RAG staleness rule, sidecar YAML schema, edit-budget cap, integrator-bypass rollback story.
- **`plugins/coordinator/snippets/docs-checker-consumption.md`** — canonical consumer-side block (synced into all five Opus reviewer prompts).
- **`plugins/coordinator/bin/verify-docs-checker-sync.sh`** — sync verifier with `--fix` and `--list` modes; clone of `verify-calibration-sync.sh`.
- **`plugins/coordinator/CLAUDE.md`** new section "Pre-Review Mechanical Verification" (terse rule + pointer to wiki) + tripwire under "Adding a Convention to the Coordinator System".

### Changed
- **`plugins/coordinator/agents/docs-checker.md`** — gains `Edit` tool + seven `mcp__project-rag__*` tools, project-RAG bootstrap subsection, expanded scope (in-repo symbols verifiable when project-RAG present), 5-tier verification source hierarchy with explicit staleness handling, new "Inline Auto-Fix Authority" section (allowlist, scope constraint, edit-budget cap, sidecar YAML schema, hard prohibitions, oscillation stuck-detection), removal of "Apply fixes" from "What You Do NOT Do", verification-table `Action` column.
- **`plugins/coordinator/agents/staff-eng.md`** (the Staff Engineer), **`plugins/game-dev/agents/staff-game-dev.md`** (the Game Dev Reviewer), **`plugins/data-science/agents/staff-data-sci.md`** (the Data Science Reviewer (`data-science:staff-data-sci`)), **`plugins/web-dev/agents/senior-front-end.md`** (the Front-End Reviewer (`web-dev:senior-front-end`)) — sentinel-block docs-checker-consumption inserted (replaces inline block in staff-eng; new in the others).
- **`plugins/coordinator/commands/review-dispatch.md`** — Phase 2.7 promoted from optional to suggested pre-flight; embeds the EM Decision Rules table; integrator-bypass note + mandatory EM spot-check after Opus review.
- **`plugins/coordinator/skills/requesting-code-review/SKILL.md`**, **`plugins/coordinator/skills/requesting-staff-session/SKILL.md`** — pointer to docs-checker pre-flight in review-setup steps.

### Internal
- Source commit `3a00f18` on `dbc-oduffy/.claude` `main`. The Staff Engineer's R1 review (REQUIRES_CHANGES, 11 findings) → integrator (all 11 AUTO-FIX-applied) → the Staff Engineer's R2 review (APPROVED, 0 findings). Plan + reviews preserved at `state/reviews/2026-05-03-docs-checker-pre-flight-*.md` in the source repo.

## [1.7.1] — 2026-05-03

### Theme — Doc refresh

Patch release. README plugin enumeration was stale (still listing 4 plugins and pointing at the retired `deep-research-claude` companion repo); social preview stats were stale; one cross-platform fix and one universal-tier doctrine sync had landed without a release marker.

### Changed
- **README plugin enumeration** updated to reflect the 7 plugins shipped via `marketplace.json` — `deep-research` and `notebooklm` are bundled (not external companions), and `remember` is now surfaced. Directory tree refreshed with current counts (23 commands, 34 skills, 11 coordinator agents).
- **Social preview** (`assets/social-preview.{html,png}`) regenerated — 7 plugins, 36 skills, 26 agents, 4 research pipelines.
- **`plugins/coordinator/.claude-plugin/plugin.json`** bumped 1.6.0 → 1.7.1 (1.7.0 release shipped without a manifest bump).

### Fixed
- **`hooks/scripts/track-tier-usage.sh`** — normalize MSYS/Git-Bash cwd before slug derivation so the W3 telemetry counter writes to the correct per-repo log on Windows (mirror of `dbc-oduffy/.claude` PR #62).

### Internal
- Promoted 5 universal-tier lessons from `/workday-start` triage queue (mirror of `dbc-oduffy/.claude` PR #63).

## [1.7.0] — 2026-05-01

### Theme — Portable Ideas from Obsidian (W1+W2+W3)

Three workstreams percolated from `~/.claude` HEAD as a single bundle (R2 APPROVED_WITH_NOTES, all 7 findings integrated). Schemas + lint belt, live-query primitives, and tiered context-loading doctrine — each tackling a different decay mode in the coordinator pipeline.

### Added
- **W1 — Frontmatter schemas + lint belt + PreToolUse validator.** New `schemas/{handoff,plan,review,decision,worker-run,lesson-entry}.yaml`, shared `bin/lib/schema.{js,test.js}` validator (with code-span / link-text robustness), `bin/lint-frontmatter.{sh,js}` CLI, and `hooks/scripts/validate-frontmatter-schema.{js,test.js}` PreToolUse hook (default WARN mode; `COORDINATOR_SCHEMA_STRICT=1` to deny).
- **W2 — Live queries CLI + sentinel-block primitives.** `bin/query-records.{js,sh}` queries frontmatter-indexed records; `bin/refresh-queries.{js,sh}` regenerates `<!-- BEGIN query: ... -->` callouts in markdown (consumed by `/update-docs` Phase 11c); `bin/lib/sentinel-blocks.{js,test.js,cli.js}` factor out shared sentinel-block extraction (now delegated by `verify-preamble-sync.sh` and `verify-calibration-sync.sh`).
- **W3 — Tiered context loading doctrine + telemetry.** New `docs/wiki/tiered-context-loading.md` canonical guide; `coordinator/CLAUDE.md` "Codebase Investigation" section rewritten to enumerate tiers 0–4 plus the tier-4 rationale rule; `hooks/scripts/track-tier-usage.sh` PostToolUse telemetry counter classifies each tool call by tier and detects the rationale preamble; `/session-end` Step 0 emits a tier-usage report.

### Changed
- **Doctrine + preamble syncs** across `CLAUDE.md`, `agents/staff-eng`, and commands `{distill, handoff, mise-en-place, session-start, session-end, update-docs}` to thread the new tiered-context model and rationale rule through the agent surfaces that consume them.

### Internal
- Test coverage for `schema.js` (code-span / link-text edge cases), `query-records`, and `sentinel-blocks` modules.

## [1.6.0] — 2026-05-01

### Theme — Orphan-Branch Prevention

In response to a 2026-05-01 postmortem (15 commits stranded for 22 hours on a branch whose source-PR had already merged, with downstream sessions actively rewriting docs to claim "shipped"), the coordinator pipeline gains structural defenses against orphan branches and false "shipped" claims. Three shared helpers, six surfaces hardened, one paragraph of doctrine.

### Added
- **`bin/orphan-branch-sweep.sh`** — enumerates `work/*` and `feature/*` branches owned by the user, classifies CRITICAL (commits added after a PR merged from this branch) / WARNING (no PR, ahead, ≥2 days old or >36h) / OK. JSON or text output, `--severity-min` filtering eliminates `| jq` / `| grep` parsing at every call site.
- **`bin/sync-main.sh`** — fetch + ff-only invariant called before any branch creation. Uses `git fetch origin main:main` refspec form so local `main == origin/main` regardless of which branch the working tree is on. Every `git checkout -b` site in the coordinator pipeline now runs this first.
- **`bin/check-shipped-on-main.sh`** — thin wrapper around `git merge-base --is-ancestor` so "shipped" claims have a single authoritative answer.
- **`commands/workday-start.md` Step 0.5** — new orphan sweep surfaces CRITICAL/WARNING branches in the Morning Briefing before any new work begins.
- **`commands/workday-start.md` Step 0 Branch Reconciliation Decision** — when yesterday's branch can't be merged forward, the PM is forced to choose A (consolidate now) / B (defer with re-check date in `tasks/.deferred-branches.md`) / C (archive). TTY-aware: blocks interactively, auto-defers in non-interactive (overnight) sessions.
- **Tracking file `tasks/.deferred-branches.md`** — single-line entries managed by the Branch Reconciliation Decision flow; surfaced when re-check date arrives.

### Changed
- **`commands/handoff.md` Step 3** — pre-flight reachability check on completed-work commits. When commits aren't on `origin/main`, "shipped" wording is replaced with "complete on branch, not yet merged" and a `## Not Yet On Main` section is appended.
- **`commands/update-docs.md`, `commands/distill.md`, `commands/architecture-audit.md`** — explicit DO-NOT-MERGE prohibition inline in Sonnet dispatch prompts. Closes the 2026-05-01 rogue-merge trigger (a doc-maintenance Sonnet ran `gh pr merge` autonomously).
- **`skills/merging-to-main/SKILL.md`** — Step 4 5-min quiet gate (cross-platform `gh`+Python snippet, override via `--force-merge-active-branch`); Step 6 reports other unmerged branches owned by the user.
- **`skills/using-git-worktrees/SKILL.md`, `commands/workday-complete.md`, `commands/session-start.md`** — `sync-main.sh` injected at every branch-creation site.
- **`coordinator/CLAUDE.md`** — one paragraph added to "Verification Before Done" ("Shipped means on `origin/main`, not on a branch tip"), one bullet under "Git Commit Policy" pointing at `sync-main.sh` + the workday-start contract, and a tripwire entry naming the three skills that must carry the gh-merge prohibition. Aggressive compression — ~5 lines total addition, lean per-PM-direction.

### Internal
- **Test fixture** `tests/plugins/orphan-sweep.test.js` covering the three severity classes with stubbed `gh`.

### Why this matters
The git tree is the only authoritative answer to "is this shipped." Handoffs, docs, and orientation cache are downstream artifacts that inherit any lie planted upstream — in the postmortem, a single false "shipped" claim propagated through five layers of artifacts in 24 hours, and a follow-on session struck a real shipped tool from the docs as "never built." This release closes the surfaces where that lie can be authored.

## [1.5.0] — 2026-04-30

### Theme — Build For Someone Else's Machine

A run of small, related changes converging on one principle: the code we ship runs on machines we've never seen, in projects we don't own, in shells we didn't configure. Portability is the baseline, not a feature.

### Added
- **Agent-driven install as first-class path** — `README.md` Quick Start replaces the `git clone && bash install.sh` block with a paste-to-agent prompt pointing at `docs/agent-install.md`. The agent reads the playbook, runs the installer, validates the result, and queues `/repo-setup` (was `/project-onboarding` pre-2026-06-08) as the immediate post-restart step. New `docs/agent-install.md` is written second-person to the agent — prereq checks, plugin selection guidance, manual fallback section, failure modes. Manual install steps remain in `docs/getting-started.md` but are no longer surfaced from the front page.
- **Doctrine rule: "Build For Someone Else's Machine"** (in `coordinator/CLAUDE.md`) — generalizes the older "Shipped Code Has No Home Field" intuition into a concrete fallback chain: explicit flag → env var → marker auto-discovery → silent skip (opt-in) or hard error with remediation (explicitly invoked). Hardcoded local paths are last-resort only. Project-scoped tools need a cwd-scope guard. Test fixtures and battle-story comments are exempt.
- **Project-RAG project-scope guard** — single-source preamble (`snippets/project-rag-preamble.md`) gains a guard so agents skip project-RAG calls when the indexed repo doesn't match the current working directory. Propagated to all 8 sentinel-fenced consumers via `bin/verify-preamble-sync.sh --fix`. Prevents wrong-project pollution when an agent is dispatched in repo A while project-RAG is indexed against repo B.

### Changed
- **UE distrust hook runbook** (`docs/testing/`) genericized — dropped the machine-specific `Keep_Blank` path that was leaking out of one author's environment. Runbook is now reproducible on any UE project layout.

### Internal
- No surface API changes for end users beyond the README Quick Start. The installer (`setup/install.sh`) is untouched and remains the canonical mechanism — agents and humans both invoke it, the difference is who types the command.

## [1.4.0] — 2026-04-29

### Added
- **Project-RAG readiness (W1–W6)** — generic project-RAG detection hook (cross-platform), single-source preamble snippet with sentinel-fenced inline distribution to 8 consumers + `verify-preamble-sync.sh`, `docs/wiki/rag-bait-conventions.md` (4 patterns including function-level purpose lines), executor RAG-bait stanza, Staff Engineer generic project-RAG block alongside the UE block.
- **Reviewer-routed workers** — four Sonnet workers (`test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`) named in reviewer findings; EM dispatches. Generalizes the Staff Engineer → Front-End Reviewer escalation pattern.
- **Mandatory release notes on every merge** — `merging-to-main` Step 1.5 always runs. Detects `CHANGELOG.md`, groups by Added/Changed/Fixed/Deps/Internal, suggests version bump (advisory).
- **example-game-repo overlay Phase 1** — Staff Engineer UE-specific workers subsection (`project_type: unreal` gated) and `merging-to-main` Step 1.6 UE check items.

### Changed
- **`/distill` reframed** — trim+archive specs (not delete), allowlist/denylist rubric, mandatory re-homing, Decision Rationale extraction, schema-pinned distillation log, broader link-heal sweep, negative-AC set-diff token check.
- **`/update-docs`** — gates atlas-enumeration + repomap-regen on RAG presence; adds preamble-sync phase; per-run repomap audit log.
- **`/architecture-audit`** — reframed to narrative + judgment with flag-drift-from-RAG check.
- **`atlas-integrity-check`** — repurposed to narrative-drift detection.
- **Three-tier repomap gating** — PM-directed: absent→primary, stale→fallback, fresh→skipped (demote, don't retire).
- **Plan-First Workflow** — adds "investigate before planning" doctrine; bug reports and consumer docs are framing, not ground truth.

### Internal
- Coordinator hook test suite wired as blocking gate in `workday-complete` and `merging-to-main`; reviewer-calibration sentinel sync via `bin/verify-calibration-sync.sh`.

## [1.3.0] — 2026-04-02

### Independence from Superpowers — Conscious Uncoupling (D-032)

Coordinator-claude is now fully self-contained. The soft dependency on [superpowers](https://github.com/obra/superpowers) (obra/superpowers) has been removed.

Superpowers gave us our start — we installed it when plugins first shipped, before coordinator-claude existed as a formal system. Its core skills (TDD, systematic debugging, planning, verification) became the behavioral floor we built on. Over time, the philosophical gap widened: superpowers treats the agent as a system to be hardened against its own optimization tendencies; coordinator-claude treats the agent as a professional with defined authority (the PM/EM model). Both work, but for different reasons — and the layered approach was paying context budget for parallel instructions we were overriding.

**New:**
- **`coordinator:brainstorming` skill** — PM/EM-native design gate. Turns intent into a committed spec through collaborative dialogue. HARD-GATE prevents implementation once brainstorming starts, but the EM has judgment on when to invoke (not "always brainstorm"). Includes targeted rationalization resistance and scope-splitting. Output feeds directly into `coordinator:writing-plans`.
- **`docs/specs/` convention** — brainstorming specs land at `docs/specs/YYYY-MM-DD-<topic>-design.md`.

**Changed:**
- **`skill-discovery` flowchart** — brainstorming gate is now judgment-based ("spec exists or EM judges brainstorming unnecessary?"), not mandatory.
- **`using-git-worktrees`** — removed `~/.config/superpowers/worktrees/` path convention.
- **`README.md`** — coordinator positioned as self-contained; superpowers install recommendation removed.
- **`docs/customization.md`** — `superpowers:writing-skills` → `coordinator:writing-skills`.

**Decision doc:** `docs/decisions/D-032-superpowers-conscious-uncoupling.md`

## [1.2.1] — 2026-04-01

### Path Hygiene — Move Default Output Paths Out of `.claude/`

Anthropic now enforces mandatory user permission grants for any writes inside the `.claude/` directory (recursively). Several default output paths were inside `.claude/`, causing permission friction for autonomous pipelines and subagents.

**Changes:**
- **Research output fallback:** `~/.claude/docs/research/` → `~/docs/research/` in `notebooklm/commands/research.md`, `notebooklm/pipelines/team-protocol.md`, and both cache versions (1.0.0, 1.1.0).
- **`settings.json` permissions:** Added explicit `Edit(~/.claude/**)` and `Write(~/.claude/**)` allow entries to cover platform-owned paths (task storage, plan mode output, team metadata) that cannot be relocated.
- **Task storage documentation:** The `~/.claude/tasks/{team-name}/N.json` reference in `deep-research/pipelines/team-protocol.md` and `structured-team-protocol.md` (source + cache) now notes these are platform-internal and must not be directly read/written by agents.

### `/distill` — Handoffs as First-Class Wiki Sources

Archived handoffs contain valuable architectural knowledge that was being treated as ephemera. The distillation pipeline now explicitly treats them as first-class inputs.

**Changes to `coordinator/pipelines/artifact-distillation/PIPELINE.md` and `agent-prompts.md` (source + cache):**
- **Phase 0 inventory** now includes `docs/research/` and `~/docs/research/` as artifact directories.
- **Special classification rules** added to the Phase 0 reality-check: archived handoffs are always `NEW` (never ephemeral); research outputs are always `NEW`; Pipeline C structured outputs (files containing `manifest_version:`) are `PRESERVE` — copied verbatim, never deleted.
- **Phase 1 scanner prompt** now includes explicit handoff section parsing: `## What Was Accomplished` → `[KNOWLEDGE]`, `## Key Decisions Made` → `[DECISION]`, `## Blockers or Issues` → `[KNOWLEDGE:gotchas]`.
- **New `[PRESERVE]` nugget type** added to the Phase 1 scanner for structured artifacts that should be copied verbatim without synthesis.
- **Phase 3 deletion manifest** now includes a `PRESERVE` disposition: research outputs and Pipeline C artifacts are never deleted, only canonicalized.
- **Distillation log format** updated to include `PRESERVE` as a valid disposition value.

## [1.2.0] — 2026-04-01

### Codex Review Gate — Independent-Model Second Opinion
- **New `codex-review-gate` skill** wraps the Codex plugin's `/codex:review` command with graceful error handling and structured result reporting. Codex (GPT-5.4) provides a different model family's perspective on code changes, catching issues that intra-family reviewers may share blind spots on.
- **`/workday-complete` Step 3.8 — on by default.** The day's full diff against main is reviewed by Codex as a second opinion alongside the existing daily review. Falls back gracefully if Codex CLI is not installed, not authenticated, or credits are exhausted — the existing daily review from Step 3 stands alone when Codex is unavailable. Designed for users on limited ChatGPT plans: one bounded review per end-of-day, not continuous.
- **`/bug-sweep --codex-verify` — opt-in flag.** After Claude's sweep identifies and fixes bugs, Codex reviews the fix diff for regressions or issues that Claude's own reviewers might miss. Captures a pre-fix baseline ref in Phase 2 for precise diff scoping. Codex findings go to the backlog for PM triage, not auto-fix.
- **Why a different model family matters.** Our existing reviewer pipeline (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer) provides thorough domain-specific review, but all reviewers share Claude's model family. Blind spots may be correlated — if Claude misses a pattern, its reviewer personas are more likely to miss it too. Codex mitigates this by providing an independent sample from a different training lineage. The integration is additive (never blocking) and token-conscious (validation of diffs, not codebase discovery).
- **Requirements:** [openai-codex plugin](https://github.com/openai/codex-plugin-cc) installed, Codex CLI authenticated (`codex login`). No Codex API key needed — runs through the CLI.

## [1.1.1] — 2026-04-01

### Strategic Daily Review (new command)
- **`/daily-review` replaces `/code-health` as the default end-of-day check** in `/workday-complete`. The review-heavy build pipeline (plan → enrich → chunk → review) already catches code-level issues; end-of-day now focuses on whether the day's accumulated decisions create technical debt, lock into patterns, or miss opportunities for the product's longer-term direction.
- **Three-phase pipeline.** Haiku scout inventories the day's commits, file changes, plans, and handoffs. Sonnet analyst produces a narrative work summary identifying explicit and implicit architectural decisions. Sonnet reviewer provides a strategic assessment against the project's roadmap and vision.
- **Reusable daily summary artifact.** Output saved to `archive/daily-summaries/YYYY-MM-DD.md` — feeds `/update-docs`, `/distill`, completed work register, and next-morning orientation. Fills the gap between terse commit logs and verbose in-flight handoffs.
- `/code-health` remains available for on-demand detailed code-level review.

### Reviewer Strategic Awareness
- **All five domain reviewers now read project roadmap and vision documents** (when available) before reviewing. Reviewers flag when an implementation — even a correct one — creates accidental lock-in, forecloses a roadmap option, or misses a low-cost bridging opportunity toward planned future capabilities.
- Strategic findings use `minor`/`nitpick` severity with `architecture` category — they inform, they don't block.
- Each reviewer's strategic lens is adapted to their domain: the generalist reviewer focuses on architecture and extensibility; the game development reviewer on engine system choices and scalability; the front-end reviewer on design system evolution; the UX reviewer on user journey trajectories; the data science reviewer on model and pipeline architecture.
- Guardrails prevent false positives: no strategic findings when no roadmap exists, when concerns are purely speculative, or when work is explicitly temporary.

### Orientation Cache Enhancement
- `/workday-start` now includes a "Yesterday's Strategic Review" excerpt in the orientation cache, giving every subsequent session automatic strategic context without reading a separate file.

### Handoff Deletion Policy
- **Explicit policy: `/workday-complete` never deletes handoffs.** Handoffs are archived (moved to `archive/handoffs/`) by `/update-docs`, but only `/distill` may delete them — after careful knowledge extraction and PM approval.

## [1.1.0] — 2026-03-31

### Remember Plugin (new)
- **Temporal memory system.** New `remember` plugin adds session-scoped memory persistence. PostToolUse hooks capture key actions as they happen; SessionStart hooks inject the last N days of session history into context automatically.
- **Haiku-powered compression pipeline.** Raw session events are compressed by `claude-haiku` into structured NDC (Notable Decisions & Changes) summaries, then consolidated into daily memory files. Designed for minimal token overhead at session start.
- **Coordinator integration.** `session-end`, `update-docs`, and `workday-complete` commands now include a `/remember` step to persist session state before closing out.
- **Marketplace registration.** Plugin is registered in `marketplace.json` for one-command install.

### Deep Research — Pipeline A v2.2 (Internet Research)
- **Iterative deepening.** After Team 1 completes, the sweep agent produces a structured gap report (YAML severity scores + Gap Targets table). If significant gaps remain, the EM dispatches a smaller Team 2 (1-3 gap-specialists + merge-mode sweep) for targeted follow-up. Hard cap at 2 passes. `--shallow` flag skips the decision gate for single-pass behavior.
- **Structured gap reporting.** Sweep's gap report now includes machine-readable YAML front-matter (`deepening_recommended`, `coverage_score`, `high_severity_gaps`) and a Gap Targets table with severity, type, and suggested queries.
- **Gap-specialist prompt template.** New specialist variant for Team 2 with Prior Findings context, tighter timing (3 min floor / 8 min ceiling), D-prefixed claim IDs, and `resolves_gap` field linking claims to gap targets.
- **Merge-mode sweep.** Team 2's sweep produces a delta document (`deepening-delta.md`) instead of a full replacement. The EM merges the delta seamlessly into Team 1's synthesis.

### Deep Research — Pipeline A v2.1 (Internet Research)
- **Consolidator eliminated.** Specialists now report directly to the sweep agent, freeing one agent slot and reducing pipeline latency.
- **Adversarial specialist interaction.** Specialists are expected to challenge each other's claims via `SendMessage`. A resolution protocol is defined for contested findings.
- **Structured claims output.** Specialists produce dual output: `{letter}-claims.json` (machine-readable, typed claims with confidence scores) and `{letter}-summary.md` (human-readable).
- **Sweep phased discipline.** Sweep operates in three explicit phases: Assess (inventory specialist claims), Fill (targeted gap research), Frame (executive summary + conclusion).
- **EM scoping checklist.** Sub-question quality gates from published multi-agent research ensure scoping produces decomposable, answerable questions.

### Deep Research — Pipeline B v2.1 (Repo Research)
- **Structural orientation pass.** EM performs a codebase orientation (entry points, key directories, architecture pattern) before scoping, so focus questions are grounded in actual structure.
- **Execution-trace framing.** Specialists frame analysis around execution paths rather than file-by-file inventory, producing more actionable findings.
- **`file:line` citation enforcement.** Specialist prompts now require `file:line` citations for all claims, making findings directly navigable.
- **LLM context file discovery.** Scoping phase now surfaces `CONTEXT.md`, `CLAUDE.md`, `.cursorrules`, and similar files as high-priority reads for specialists.
- **Independent-analysis-first comparison mode.** When comparing two repos, specialists analyze each independently before cross-referencing to avoid anchoring bias.

### Deep Research — Pipeline B v2.2 (Repo Research)
- **`--deeper` mode.** EM generates a dependency-weighted repomap during scoping (Phase 1.5). Language-aware import extraction (Python, JS/TS, Go, Rust, C/C++, Java) with cross-reference counting and tiered output (Tier 1/2/3). Specialists read repomap before inventories for prioritization. Graceful fallback if import graph is thin.
- **`--deepest` mode.** Two-wave pipeline: Wave 1 is the standard 7-agent team (unchanged), Wave 2 dispatches a Sonnet atlas subagent after synthesis. Produces 4 architecture atlas artifacts: file index, system map, connectivity matrix, and architecture summary. `--deepest` implies `--deeper`. Atlas failure is non-blocking.

### NotebookLM — Pipeline D v2
- **Strategist elimination.** Removed the separate Opus strategist agent. EM now scopes directly with baked-in NLM best practices, saving one agent dispatch and ~2 minutes.
- **NLM-adapted claims schema.** Workers now output structured `{letter}-claims.json` with NLM-specific fields (`transcription_suspect`, `source_type`, `nlm_citation`) alongside `{letter}-summary.md`.
- **Synthesizer → sweep rename.** Final agent renamed from "synthesizer" to "sweep" to match Pipeline A naming and reflect its actual role (adversarial coverage check + gap-filling, not just synthesis).
- **Notebook preservation (default).** Notebooks are now kept after research runs by default — they represent significant ingestion work and are valuable for follow-up queries. New `--cleanup` flag opts in to deletion.

### Developer Ergonomics
- **Plugin command naming cleanup.** Removed redundant plugin-name prefixes from all commands: `deep-research-web.md` → `web.md`, `deep-research-repo.md` → `repo.md`, `notebooklm-research.md` → `research.md`, etc. 26 files updated, all cross-references synced.

## [1.0.0] — 2026-03-28

Initial public release. 8 plugins, 24 agents, 37 skills.

