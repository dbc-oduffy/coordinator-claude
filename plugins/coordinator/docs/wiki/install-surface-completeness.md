---
title: Install-Surface Completeness
created: 2026-05-21
author: claude-central-em
status: current
kind: wiki
related:
  - plugins/coordinator/docs/wiki/cross-repo-communication.md
  - plugins/coordinator/docs/wiki/live-install-drift-audit.md
  - plugins/coordinator/docs/wiki/coordinator-installer-shape.md
  - plugins/coordinator/docs/wiki/machine-local-registry.md
  - plugins/coordinator/docs/wiki/cross-repo-handshake-doctrine.md
keywords:
  - install surface
  - clean install
  - installer story
  - machine-local
  - doctor surface
  - cross-repo install
  - install completeness
---

# Install-Surface Completeness

## Rule

**If work writes state outside the repo's source code, the clean-install path on a fresh machine must reproduce that state.** Local tests passing on your disk is not evidence that a new user can install the work. Work that depends on locally-mutated state without paired installer/template/doctor updates is *incomplete*, regardless of how green your tests are.

This rule sits above the `Build For Someone Else's Machine` doctrine (which governs *runtime* path resolution): this rule governs *install-time* state reproduction. Both apply.

## Failure mode

The empirical pattern this rule exists to prevent — observed in concentrated form across 2026-05-20 and 2026-05-21:

1. EM or executor is debugging an issue in repo X.
2. They write a manual tweak to `machine-local/`, an install script, a sentinel file, or some adjacent state.
3. Local tests pass. Their local machine works. The fix lands in a commit.
4. Another operator clones the repo and runs the documented install path on a fresh machine.
5. The install fails — or worse, succeeds but produces broken runtime — because the state the manual tweak left on the author's disk is not reproduced by the installer.
6. Root-cause is **invisible** because:
   - The author's local disk has the state; their tests pass.
   - The CI machine (if any) may also have the state, cached from prior runs.
   - The failure shows up days later on a colleague's machine or a fresh CI worker, with no obvious link to the original work.

The 2026-05-20/21 cleanup wave consumed roughly two days of EM time tracing exactly this pattern across the project-rag / project-rag-ue-addon / claude-unreal-holodeck trio.

## What counts as "install surface"

Explicit catalogue. Any write to these surfaces triggers the completeness rule:

- **`machine-local/` registry entries** — keys read via `bin/machine-local get <key>` or its Python/PowerShell siblings.
- **Install and setup scripts** — `bin/install.sh`, `setup/install.sh`, `setup/publish.sh`, per-plugin `install-*.sh`, and their templates.
- **Sentinel files** — anything matching the `addon-health-sentinel.md` family, `install-status*.json`, `*-sentinel.json`, drift markers.
- **Hook configurations** — `settings.json`, `settings.local.json`, anything that wires a hook into the session lifecycle.
- **Environment variables and shell-startup additions** — `~/.bashrc`, `~/.zshrc`, PowerShell `$PROFILE`, any per-machine env baseline.
- **Sibling-repo path registrations** — `plugin.mirrors.<plugin>` blocks, `REPO_<NAME>` exports, anything that tells other tools where to find another checkout.
- **Editable-install venv state** — `pyproject.toml` is source code, but the live `.venv/`'s editable-install MAPPING is install state. Changes to `pyproject.toml` that aren't paired with a refresh primitive (e.g. `bin/refresh-plugin-live-install.sh <plugin>`) leave drift. See `live-install-drift-audit.md`.
- **Doctor surface** — `:doctor` skills are read paths into install state; if your work depends on new install state, the doctor for that surface should detect its absence.
- **INSTALL.md and onboarding docs** — if a new operator's documented path doesn't lead them to the state your work requires, the documentation is part of the install surface that needs updating.

If you wrote to a file or registry that a fresh `~/.claude/` clone wouldn't have, you're on install surface. Default to "yes, this is install surface" when uncertain.

**Bootstrap gap — machine-local/ is NOT created by any current installer.** Neither `setup/install.sh` (OSS entry point, 1271 lines) nor `setup/publish.sh` (Central meta-repo sync) creates or seeds `~/.claude/machine-local/`. The deprecated `publish-targets.sh` fallback silently activates when the registry directory is absent. This is a Medium-severity gap (currently mitigated by deprecated fallback; becomes blocking when fallback is retired). Any work that depends on `machine-local/` keys must document a manual bootstrap step until an installer creates the directory.

## The completeness test — three concrete checks

Before declaring work done, your install-surface writes pass all three:

### (a) Clean-install dry-run

Could you reproduce the state your work depends on by running the documented install path on a fresh `~/.claude/` (or fresh sibling-repo checkout)? If "no" or "I haven't checked," your installer is incomplete. The most direct version of this check is to actually run the installer in a scratch directory; the cheap version is to trace the install script line-by-line against the state your work needs.

### (b) Doctor surface

Does the relevant `:doctor` skill detect the absence of the state your work needs? If a new operator runs `:doctor` on a fresh install, do they get a diagnostic that names what's missing and remediates (or directs them to the installer)? Silent missing-state is the failure mode this check prevents.

### (c) New-user mental model

If a new operator clones the repo and follows `INSTALL.md` (or `README.md`'s setup section), do they land in a working state where your work runs? If your work assumes prior knowledge ("you have to know to also run X"), `INSTALL.md` is part of the install surface that needs updating.

**Failing any of the three means the work is incomplete**, regardless of whether tests pass on your machine.

## Multi-site value parity — when one value is mirrored across N locations

A close cousin of install-surface completeness: when a single logical value (a file list, a closed-enum's members, a schema's fields) is **mirrored across multiple source locations**, expanding it in one place leaves the others stale — and the staleness fails *silently*, often in a different test family than the one you ran.

Three observed shapes (2026-05-21 / 2026-05-23):

- **A delivered file list lives in 3+ install surfaces.** A new file shipped via `install-substrate.sh` appears in (1) the delivery loop, (2) the drift-verifier `PAIRS` array, (3) the fresh-install function. Each executor updated its own slice; two files were templated nowhere; the drift verifier reported zero drift because it only knew its own 3 PAIRS. **Lift the list to a single canonical manifest that all call-sites consume, and add a parity test.** The manifest IS the contract.

- **A closed-enum value lives in the typed source + the JSON schema + the test closed-set mirror.** Expand the Literal / TS-union / Pydantic enum and the JSON-schema `enum` and the test `_VALID_*` constant reject the new value silently — and in *different* test families (`test_release_round_trip` vs `test_provenance_module_stamping`), so a partial sweep passes the first and misses the second. **Grep the VALUE SET (not the variable name — mirrors rename for context) for all locations before commit; add a single cross-mirror parity test if the enum is load-bearing.**

- **A schema field has N projections.** Adding a schema field is not the same as widening every projection of it (NDJSON emitters, walkers, dataclasses, doctors, manifest readers). Schema-additive ≠ projection-additive — audit every projection when you touch the schema.

**Bilateral bump sequencing (cross-repo schema/contract version).** When two repos read each other's manifest, bump the version *reader-first*: both readers must accept `{old, new}` before either side flips its manifest. Same-machine sibling-dir + on-branch + auto-push does NOT relax this — whichever flips first breaks the other's walk immediately (per the reject-unknown-version contract). Land the receive (schema enum + reader accept-range + test) in commit 1; hold the manifest flip until both readers accept.

*Cross-ref: the `game-dev:schema-migration-auditor` worker mechanically enumerates downstream schema readers for UE-flavored schema bumps — dispatch it when a diff bumps a manifest / structural-index version.*

## Cross-repo dimension — doctrine seeding vs. code/install-surface change

Per PM ruling 2026-05-21, not all cross-repo writes are the same. The install-surface rule combines with the cross-repo memo doctrine differently at the two altitudes:

- **DoE-altitude doctrine seeding** (CLAUDE.md additions, `docs/wiki/` entries, agent-prompt amendments authored from central-EM under PM direction) is a legitimate direct cross-repo write. The DoE has standing to seed "how we work" into sibling repos. Provenance is noted in the commit message; sibling EM may amend on receipt.
- **Code / install-surface changes in a sibling repo** (source edits, machine-local entries, install scripts, sentinel files, registry edits) route via `cross-repo-memo` CLI (writes ONE dirty file into `<receiver>/cross-repo/`) — **and the PM is handed the receiver path to relay to the affected EM**. The memo file is the persistent record; the PM is the active relay. A memo written without PM-relay is a document dropped in a hole — the affected EM has no signal to look at it. The sibling EM, once briefed by the PM, lands the change with their own implementation context. PM-authorized direct writes are the documented exception, not the default.
- **Why the altitudes differ.** Doctrine is alignment work the DoE owns; code is implementation work the sibling EM owns. Conflating them produces churn in both directions — DoE doctrine that never lands because it routed through a slow memo loop, OR sibling-repo code edits that lose the implementing EM's context.

The 2026-05-20/21 cleanup wave was largely the *code/install-surface* failure mode: EMs and executors making manual install-surface tweaks across the trio without the affected EM's coordination.

## Known sub-cases — cross-references to existing wikis

Each of these codifies a specific install surface or specific failure shape. This wiki is the universal rule; they are the worked examples:

- **`live-install-drift-audit.md`** — source-tree → live-checkout propagation. Specific to plugins where the live install is a separate git checkout (e.g. `project-rag`). Probe: `bin/check-plugin-drift.sh`. Refresh: `bin/refresh-plugin-live-install.sh <plugin>`.
- **`coordinator-installer-shape.md`** — the coordinator's own installer (`/coordinator:setup`) and its three audiences (OSS adopters, internal users, meta-repo operators).
- **`machine-local-registry.md`** — per-machine value writes (install roots, sibling-repo paths, vendor SDKs) under `~/.claude/machine-local/`. Authors the schema-vs-value distinction.
- **`cross-repo-handshake-doctrine.md`** — when a sentinel crosses a repo boundary, it must self-document its preconditions inline; producer-only documentation is invisible at consumption time.
- **`cross-repo-communication.md`** — the single `cross-repo/` surface and the doctrine-vs-code altitude distinction. Cross-repo memos (dirty files placed in the receiver's `cross-repo/` via the CLI) are signalling artifacts — they do not alter what runs in the receiver repo. The install-surface completeness rule (this wiki) applies to implementation-intent changes; memo delivery is governed by the lifecycle in `cross-repo-communication.md § Cross-repo memo lifecycle`.

## For trio repos (project-rag / project-rag-ue-addon / claude-unreal-holodeck)

The trio shares an unusually entangled install surface — host runtime, addon corpus, downstream consumer. Trio-specific discipline lives in `X:/project-rag/docs/wiki/trio-install-surface-coupling.md` (in the project-rag repo, since project-rag is the install-surface keystone). Trio CLAUDE.md files reference both this universal wiki and the trio-specific one.

## Code-reviewer enforcement (always-on lens)

The `agents/code-reviewer.md` agent carries an install-surface coverage lens that fires on every diff — it is not opt-in. When reviewing a diff, the reviewer scans for edits to:

- `machine-local/` registry files
- `install*.sh`, `setup*.sh`, and any file under `**/installers/**`
- Hook scripts under `.claude/`, `settings.json`, `settings.local.json`
- Sentinel files matching `*-sentinel.json`, `addon-health-*`, `install-status*`
- `pyproject.toml` paired with live `.venv/` editable-install MAPPING changes
- `INSTALL.md`, `setup/publish-targets.sh`, percolate registration

For each match the reviewer asks two questions:

1. **Installer coverage** — does the clean-install path reproduce the state this diff requires? Missing coverage is P1.
2. **Cross-repo coordination** — does this diff write to a sibling repo's install surface without PM authorization? Missing provenance is P1.

This lens runs as a structural check; the reviewer need not have domain context on the specific surface. Findings surface as `WARN` or `BLOCKED` verdict entries and feed the review-integrator pass.

## Greppability for prior-art-checker

This wiki is intentionally keyword-dense so prior-art-checker surfaces it on plans touching install surface. Keywords carried: `install surface`, `clean install`, `installer story`, `cross-repo install`, `machine-local`, `doctor surface`, `install completeness`. Plans that grep for any of these will match this wiki in the prior-art sidecar.

## Doctor surface gaps and the vacuous-pass anti-pattern

A `:doctor` skill that passes silently when no sentinel files exist is not a health check — it is a vacuous pass. The canonical example is `scan-addon-health.sh --red-only` (used by `/session-start`): when no `doctor-last-run.json` sentinels exist on a fresh install, the script exits 0 and emits nothing. A fresh-install operator sees no signal that their install has never been doctor'd.

The three-check completeness test (§ above) includes doctor coverage precisely because of this pattern. When authoring or extending a `:doctor` skill, verify that the skill emits a non-trivial finding on a completely fresh install (no sentinels, no prior doctor runs). Sentinel-absent state must produce an AMBER or RED verdict, not a silent pass.

Complementary: `/workday-start` uses `--red-and-stale` (which catches AMBER verdict inversions) while `/session-start` uses `--red-only`. This asymmetry is intentional — daily triage posture vs. session-start signal-not-noise — but it means verdict inversions (doctor wrote AMBER at 10:03Z, re-probe at 10:30Z returns RED) surface only at the next workday-start, not at interim session starts. This is a known limitation, not a bug to fix urgently.

## When this rule does NOT apply

- **Pure runtime path resolution** — covered by `Build For Someone Else's Machine` in coordinator/CLAUDE.md, not this rule. That rule says "explicit flag → env var → marker auto-discovery → silent skip / hard error"; this rule says "and your installer must produce the marker."
- **Test fixtures and battle-story comments** — pinned paths in fixtures or one-off forensic comments are exempt from the cross-machine reproduction requirement.
- **Genuinely one-machine ephemera** — `~/.bash_history`, editor state, OS-level config a project has no business touching. If you find yourself writing to user-level state the project doesn't own, the question isn't installer-completeness — it's *should the project be writing there at all*.

## How this rule was authored and extended

Authored 2026-05-21 by central-EM under PM direction, after the 2026-05-20/21 cleanup wave revealed the pattern at scale across the project-rag trio.

Extended 2026-05-24 (distillation run) with: code-reviewer enforcement lens, machine-local bootstrap gap callout, doctor vacuous-pass anti-pattern guidance. These additions fold findings from the 2026-05-20 install-doctor audit and the 2026-05-19 coordinator-installer-redesign plan.

Sibling EMs in all repos may amend this wiki on receipt — doctrine-seeding under the cross-repo altitude distinction (§ Cross-repo dimension above) is alignment-shaped, not fait-accompli.

## Post-Consumer Gates Must Be Advisory WARN, Not Hard-Fail

*2026-05-24, project-rag.* A cross-repo or cross-version compatibility gate added AFTER consumers already exist must default to advisory WARN rather than hard-fail. A hard-fail gate applied retroactively causes every consumer predating the gate to regress on upgrade — the gate produces a silent install-regression that surfaces only when a consumer next runs. Pattern: emit a clear `WARN: <reason>; this will become an error in <version>` message, give consumers a migration window, then promote to hard-fail in a named future version. Never introduce a hard-fail gate whose failure predates the gate's existence. (Source: 2026-05-24 project-rag)

## Setuptools Editable MAPPING Is Baked at Install Time

*2026-05-24, project-rag.* With `pip install -e .` (editable install), setuptools bakes a `__editable__.<pkg>.pth` or `MAPPING` file at install time from the current `pyproject.toml`. Adding a new package or sub-package to `pyproject.toml` after the editable install does NOT automatically register it — the new package is invisible to `import` until `pip install -e .` is re-run. This affects both the venv-state leg of the live-install propagation and local dev workflows. When a plan adds packages to `pyproject.toml`, include `pip install -e .` (or `uv pip install -e .`) as an explicit step in the post-change install verification. (Source: 2026-05-24 project-rag)

## Skill-Script Phase Parity Requires Explicit Comparison

*2026-05-24, project-rag-ue-addon.* When a workflow exists in both a skill (`.md` step list) and a standalone script (`.sh`/`.py`), the two phase lists drift independently — a phase added to the script is invisible to skill-users, and a phase added to the skill spec is unenforced in script runs. Defense: grep both the skill and the script for phase identifiers (numbered steps, `PHASE:` comments, function names) and assert parity in a test or doc-checker. When parity diverges, resolve with a wrapper (script calls the skill's canonical steps, or skill imports the script's phase list) rather than adding a gate-overloading flag. (Source: 2026-05-24 project-rag-ue-addon)
