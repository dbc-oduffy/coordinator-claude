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

- **`machine-local/` registry entries** — keys read via `machine-local get <key>` or its Python/PowerShell siblings.
- **Install and setup scripts** — `bin/install.sh`, `setup/install.sh`, `setup/publish.sh`, per-plugin `install-*.sh`, and their templates.
- **Sentinel files** — anything matching the `addon-health-sentinel.md` family, `install-status*.json`, `*-sentinel.json`, drift markers.
- **Hook configurations** — `settings.json`, `settings.local.json`, anything that wires a hook into the session lifecycle.
- **Environment variables and shell-startup additions** — `~/.bashrc`, `~/.zshrc`, PowerShell `$PROFILE`, any per-machine env baseline.
- **Sibling-repo path registrations** — `plugin.mirrors.<plugin>` blocks, `REPO_<NAME>` exports, anything that tells other tools where to find another checkout.
- **Editable-install venv state** — `pyproject.toml` is source code, but the live `.venv/`'s editable-install MAPPING is install state. Changes to `pyproject.toml` that aren't paired with a refresh primitive (e.g. `refresh-plugin-live-install.sh <plugin>`) leave drift. See `live-install-drift-audit.md`.
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

## The three recurring failure shapes — "works only by accident of machine state"

*Source: project-rag-ue-addon EM, 2026-05-29 (clean-install worked example: `project-rag-ue-addon/docs/plans/2026-05-29-clean-install-just-works.md`). [universal]*

The § Failure-mode narrative above describes the *pattern*; in practice it recurs in three concrete shapes. Each shares one root: **a step that succeeds only because of incidental author-machine state, and fails silently or late on a clean machine.** When your work touches install surface, audit it against all three explicitly — they are the recurring instances the abstract rule exists to catch.

1. **Live-process file-lock during install.** An installer replaces files a long-lived process holds open — a daemon, an editor, a sidecar, an indexer. Breaks *loudly* on Windows (`WinError 5` / "file in use"); may differ *silently* on POSIX (the rename succeeds, the held process keeps the old inode, and the new file is invisible until restart). **Mitigation:** sibling-create + atomic pointer-flip + handle-tolerant cleanup, or a graceful release signal to the holding process — never rename a directory or file a live process holds open.

2. **Editable-install label drift on repo-update.** An `-e` (editable) install whose `.dist-info` / `.pth` / import-finder isn't re-pinned when the repo advances, so the runtime misreports its own version. The MAPPING is baked at install time (see § Setuptools Editable MAPPING below); a `git pull` or a same-version rename never re-bakes it. **Mitigation:** pair every `pyproject.toml` package/version change with a `pip install -e .` (or `uv pip install -e .` / `refresh-plugin-live-install.sh <plugin>`) step in post-change verification. **Known coordinator-side gap:** `refresh-plugin-live-install.sh` returns `NOT_REGISTERED` for the "addon editable-installed into a *sibling's* venv" case — `plugin.mirrors` carries no `propagation_mode` for it. If this pattern recurs across repos, that gap warrants a coordinator-side fix (tracked in the improvement queue, not addon-local).

3. **Dependency-by-venv-leakage.** An importer relies on a dependency declared *elsewhere*, working only because a sibling package leaked it into a shared venv. The import succeeds on the author's machine and `ImportError`s on a clean install where the sibling isn't present. **Mitigation:** every importer declares its own dependencies in its own `pyproject.toml`, plus a pre-flight that verifies hard deps are importable *before* expensive work begins (fail-loud-early, not fail-deep-late).

**Audit checklist.** Before declaring install-surface work done, answer each:

- [ ] Does any install step rewrite a file a long-lived process might hold open? (shape 1)
- [ ] Does any `pyproject.toml` package/name/version change ship without a paired re-install / refresh step? (shape 2)
- [ ] Does any importer rely on a dep it does not declare itself? (shape 3)

A "yes" to any of these without the named mitigation is incomplete work, not a follow-up.

## The doctor is the consumer's self-service substitute for an on-machine EM

*Source: project-rag-ue-addon EM, 2026-05-29. [universal]*

A downloading consumer has no on-machine EM to hand-patch the three failure shapes above. **The `:doctor` skill IS their EM-substitute** — every install-surface defect must be catchable by a doctor probe, *and the probe must be offer-shaped* (design-as-offers: lead with the remediation — "run X to fix" — not just the violation). A defect that only an on-machine EM could diagnose leaves the consumer exactly where the EM was, minus the diagnostics.

This raises the bar on § completeness-check (b): it is not enough that the doctor *detects* missing state — the doctor must name the fix in the consumer's own vocabulary and, where safe, offer to apply it. A doctor that prints "schema mismatch: version 3 expected, 2 found" and stops is a violation report; one that prints "schema mismatch — run `:doctor --fix` to migrate" is an EM-substitute. The first strands the consumer; the second unblocks them. Compose this framing with § Doctor surface gaps and the vacuous-pass anti-pattern below — a doctor that passes silently on fresh state is the *absence* of the EM-substitute, not a degraded one.

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

**Path declarations that resolve relative to a peer repo must be grepped against the installed-tree shape, not just the upstream source layout.** Installed trees (post-`pip install`, post-wheel-build, post-clone-to-different-path) can differ from upstream source — symlinks, package re-layout, missing dev directories. Grep your path declarations against the actual installed-tree shape on a clean machine. Distinct from citation-drift-over-time (the existing cross-repo path lesson); this is about installed-tree shape diverging from upstream layout structurally. (Source: project-rag-ue-addon L41)

Each of these codifies a specific install surface or specific failure shape. This wiki is the universal rule; they are the worked examples:

- **`live-install-drift-audit.md`** — source-tree → live-checkout propagation. Specific to plugins where the live install is a separate git checkout (e.g. `project-rag`). Probe: `check-plugin-drift.sh`. Refresh: `refresh-plugin-live-install.sh <plugin>`.
- **`coordinator-installer-shape.md`** — the coordinator's own installer (`/coordinator:install`) and its three audiences (OSS adopters, internal users, meta-repo operators).
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

This wiki is intentionally keyword-dense so prior-art-checker surfaces it on plans touching install surface. Keywords carried: `install surface`, `clean install`, `installer story`, `cross-repo install`, `machine-local`, `doctor surface`, `install completeness`, `live-process file-lock`, `editable-install drift`, `dependency-by-venv-leakage`, `doctor as EM-substitute`. Plans that grep for any of these will match this wiki in the prior-art sidecar.

## Doctor surface gaps and the vacuous-pass anti-pattern

**Existence checks on metadata files are weak substrate guards — check structural filesystem signatures unique to the desired substrate AND negative signatures for wrong variants.** A pre-flight that validates "is this a UE install?" via single-file existence (e.g. `Build.version`) catches deletion but not category mismatch — Epic launcher and from-source GitHub clones both ship that file, yet the launcher install is thinner. A pre-flight that passes against the launcher silently produces reduced extraction coverage downstream. Mitigation: check positive structural signatures unique to the desired substrate (`.git/` directory for clones, `Engine/Source/Runtime/Engine/Private/Engine.cpp` for full source) AND negative signatures for the wrong substrate (path prefix `Program Files/Epic Games/`). Generalizable to any third-party install with "lite" and "full" variants. (Source: project-rag-ue-addon L36)

A `:doctor` skill that passes silently when no sentinel files exist is not a health check — it is a vacuous pass. The canonical example is `scan-addon-health.sh --red-only` (used by `/workstream-start`): when no `doctor-last-run.json` sentinels exist on a fresh install, the script exits 0 and emits nothing. A fresh-install operator sees no signal that their install has never been doctor'd.

The three-check completeness test (§ above) includes doctor coverage precisely because of this pattern. When authoring or extending a `:doctor` skill, verify that the skill emits a non-trivial finding on a completely fresh install (no sentinels, no prior doctor runs). Sentinel-absent state must produce an AMBER or RED verdict, not a silent pass.

Complementary: `/workday-start` uses `--red-and-stale` (which catches AMBER verdict inversions) while `/workstream-start` uses `--red-only`. This asymmetry is intentional — daily triage posture vs. workstream-start signal-not-noise — but it means verdict inversions (doctor wrote AMBER at 10:03Z, re-probe at 10:30Z returns RED) surface only at the next workday-start, not at interim workstream starts. This is a known limitation, not a bug to fix urgently.

## Two-Layer Install Surfaces — Script-Layer vs. Agent-Layer Altitude

*Source: claude-unreal-holodeck, 2026-05-29. [universal]*

When an install pipeline has two layers — a script layer and an agent/orchestrator layer — both consuming the same upstream structured output (e.g. a doctor report, a health JSON), they consume it at **different altitudes**:

- **Script layer** stays binary: exit-code only. Green/red. It cannot branch on per-bucket detail.
- **Agent layer** goes per-bucket: reads the structured output and branches on individual verdict fields (`CUDA_WARN`, `VRAM_LOW`, `SCHEMA_MISMATCH`, …).

Collapsing these two into a single "check the output once" path forces either the script to parse structured output (fragile) or the agent to operate on a binary signal (loses remediation fidelity). Keep the altitude separation explicit in the install surface design and name which layer consumes which shape in the installer doc.

## One install-script portability bug ⇒ audit the whole install surface

*2026-05-30, self (claude-central).* A single portability defect found in an install script is never an isolated typo — it is evidence that the script was authored against the author's shell/OS and not tested across the supported matrix. **Finding one ⇒ audit all install scripts for the same class.** The recurring offenders:

- **bash-3.2 incompatibility** — `declare -A` (associative arrays), `${var^^}` / `${var,,}` (case conversion), and `&>>` appear only in bash 4+; macOS ships bash 3.2. These fail loud (`declare: -A: invalid option`) or, worse, silently mis-parse on the older shell.
- **BSD-vs-GNU flag drift** — `sed -i` (GNU) vs `sed -i ''` (BSD), `grep -P`, `sort -V`, `readlink -f`, `date -d` all diverge between macOS/BSD and Linux/GNU userlands.
- **`python3`-hardcoding** — absent on many Windows hosts (see platform-gotchas § `python3` may not be on PATH); use the PYTHON_BIN resolver.

The fix splits three ways, not one: **(a) fail-loud guard** at script top (assert bash version / required tool present, exit with remediation); **(b) 3.2-safe rewrite** of the offending construct (parallel arrays instead of `declare -A`, `tr` instead of `${var^^}`); **(c) portable-idiom** substitution (host-detect with `uname -s` and dispatch, or pin to the documented-portable subset). Pairs with platform-gotchas § Cross-platform script portability — that rule names the runtime symptom; this rule names the audit-the-whole-surface response when one instance surfaces.

## Install-surface verification is bidirectional — leak-exclusion AND publish-coverage

*2026-05-30, claude-prime.* Verifying an install/publish surface is two opposite checks, and passing one does not imply the other:

- **Leak-exclusion** (the negative): does the surface *exclude* what must NOT ship — tooling outputs, secrets, machine-local state, scratch? (See § Chronically Dirty Tree — `git ls-files` is the oracle.)
- **Publish-coverage** (the positive): does the surface *include* everything that MUST ship — every source file a fresh clone needs to run?

A single matcher (an `.gitignore` rule, a copy-list glob, a publish manifest pattern) can satisfy one direction and silently fail the other. **The silent-failure mode is a path-root mismatch**: a pattern anchored to the wrong root (`docs/**` vs `./docs/**`, repo-relative vs absolute, leading-slash vs not) compiles cleanly, matches *nothing* against the actual tree, and reports zero violations — the verifier appears green precisely because it is inert. Verify both directions explicitly, and verify the matcher's path-root against a known file that *should* match (assert at least one hit), not just against the absence of unwanted hits.

## When this rule does NOT apply

- **Pure runtime path resolution** — covered by `Build For Someone Else's Machine` in coordinator/CLAUDE.md, not this rule. That rule says "explicit flag → env var → marker auto-discovery → silent skip / hard error"; this rule says "and your installer must produce the marker."
- **Test fixtures and battle-story comments** — pinned paths in fixtures or one-off forensic comments are exempt from the cross-machine reproduction requirement.
- **Genuinely one-machine ephemera** — `~/.bash_history`, editor state, OS-level config a project has no business touching. If you find yourself writing to user-level state the project doesn't own, the question isn't installer-completeness — it's *should the project be writing there at all*.

## Versioned gates added after consumers exist must be advisory, not hard-fail

A cross-repo or cross-version gate added AFTER consumers already exist must start advisory (WARN), not hard-fail. A new hard-fail gate regresses every install that predates the gate — those installs satisfied the implied constraint before it was codified, but they now fail the gating check on next run. Keep the older, narrower checks as the hard floor; make the new gate a WARN with remediation instructions until all known consumers are updated. Promote to hard-fail only when the gate has been verified against the full install population. (Source: 2026-05-24 project-rag)

## setuptools editable installs bake a MAPPING at install time — adding a package doesn't refresh it

`setuptools`-style editable installs (`pip install -e <root>`) bake a top-level-package MAPPING file into the `.venv/` at install time. Adding a new sub-package to `pyproject.toml` does NOT update this MAPPING automatically — the new package is invisible to the editable-install finder until `pip install -e <root>` is re-run. The `bin/refresh-plugin-live-install.sh <plugin>` primitive handles this for coordinator plugins (venv-state leg). For any other Python package: if a `pyproject.toml` change adds or removes a top-level package, the clean-install path must explicitly re-run `pip install -e .` — adding the package to the source tree is not enough. The doctor surface for the affected plugin should detect MAPPING staleness (compare `pyproject.toml` packages against the on-disk MAPPING) and offer the refresh command. (Source: 2026-05-24 project-rag)

## Skill-script phase parity — audit both surfaces when one gains a phase

When a skill (agent-dispatched) and a standalone script cover the same pipeline, their phase lists can drift independently. A phase added to the skill but not the script (or vice versa) means one execution path silently skips a check the other requires. Resolve divergence via a wrapper that delegates to the canonical surface, not by gate-overloading (adding conditional logic to both surfaces independently). Parity audit procedure: grep both the skill body and the script for their phase-list definitions, diff them, and add a CI assertion that counts phases in both surfaces and fails on mismatch. (Source: 2026-05-24 project-rag-ue-addon)

## How this rule was authored and extended

Authored 2026-05-21 by central-EM under PM direction, after the 2026-05-20/21 cleanup wave revealed the pattern at scale across the project-rag trio.

Extended 2026-05-24 (distillation run) with: code-reviewer enforcement lens, machine-local bootstrap gap callout, doctor vacuous-pass anti-pattern guidance. These additions fold findings from the 2026-05-20 install-doctor audit and the 2026-05-19 coordinator-installer-redesign plan.

Extended 2026-05-30 (central-EM, discharging the cross-repo memo `2026-05-29-install-surface-completeness-instance.md` from the project-rag-ue-addon EM) with: the three recurring failure shapes as an explicit audit checklist (live-process file-lock; editable-install label drift; dependency-by-venv-leakage), and the "doctor is the consumer's self-service substitute for an on-machine EM, offer-shaped per defect" framing. These generalize the addon's 2026-05-29 clean-install worked example into universal doctrine.

Sibling EMs in all repos may amend this wiki on receipt — doctrine-seeding under the cross-repo altitude distinction (§ Cross-repo dimension above) is alignment-shaped, not fait-accompli.

## Post-Consumer Gates Must Be Advisory WARN, Not Hard-Fail

*2026-05-24, project-rag.* A cross-repo or cross-version compatibility gate added AFTER consumers already exist must default to advisory WARN rather than hard-fail. A hard-fail gate applied retroactively causes every consumer predating the gate to regress on upgrade — the gate produces a silent install-regression that surfaces only when a consumer next runs. Pattern: emit a clear `WARN: <reason>; this will become an error in <version>` message, give consumers a migration window, then promote to hard-fail in a named future version. Never introduce a hard-fail gate whose failure predates the gate's existence. (Source: 2026-05-24 project-rag)

## Setuptools Editable MAPPING Is Baked at Install Time

*2026-05-24, project-rag.* With `pip install -e .` (editable install), setuptools bakes a `__editable__.<pkg>.pth` or `MAPPING` file at install time from the current `pyproject.toml`. Adding a new package or sub-package to `pyproject.toml` after the editable install does NOT automatically register it — the new package is invisible to `import` until `pip install -e .` is re-run. This affects both the venv-state leg of the live-install propagation and local dev workflows. When a plan adds packages to `pyproject.toml`, include `pip install -e .` (or `uv pip install -e .`) as an explicit step in the post-change install verification. (Source: 2026-05-24 project-rag)

## Skill-Script Phase Parity Requires Explicit Comparison

*2026-05-24, project-rag-ue-addon.* When a workflow exists in both a skill (`.md` step list) and a standalone script (`.sh`/`.py`), the two phase lists drift independently — a phase added to the script is invisible to skill-users, and a phase added to the skill spec is unenforced in script runs. Defense: grep both the skill and the script for phase identifiers (numbered steps, `PHASE:` comments, function names) and assert parity in a test or doc-checker. When parity diverges, resolve with a wrapper (script calls the skill's canonical steps, or skill imports the script's phase list) rather than adding a gate-overloading flag. (Source: 2026-05-24 project-rag-ue-addon)

## Release-Channel Gates — Local Fixes and Rename Bumps

*Consolidated 2026-05-27 from L10/L231 (project-rag-ue-addon).* Two facets of the same install-surface failure: a fix that lands only on the author's disk, and a rename that strands installs by skipping the version gate.

- **Local-only data fixes don't help fresh clones (L10).** A data correction applied directly to the author's local checkout (a fixed index row, a hand-patched config, a corrected corpus entry) does nothing for a `clone-and-go` user — the fresh clone reproduces the *old* data. The fix is only real when it ships through the **canonical distribution channel** (the installer, the seeded fixture, the release artifact, the migration). "It works on my disk" is the §Failure-mode trap restated for data, not just install scripts. Trace: does a fresh clone of the released artifact carry this fix? If no, it isn't shipped.
- **Package rename without a version bump strands every editable install (L231).** Renaming a package or sub-package without bumping the dist-info version leaves every `pip install -e .` consumer importing the *old* name with no signal to re-install — the editable MAPPING is baked at install time (see § Setuptools Editable MAPPING above) and a same-version rename never triggers a refresh. **Gate on dist-info version bump:** a diff that changes `packages = [...]` / `name = ...` in `pyproject.toml` without bumping `version` is a release-stranding smell. Pair the rename with a version bump AND a `pip install -e .` step in post-change verification, so the MAPPING re-bakes against the new name. This composes with § Post-Consumer Gates (a retroactive compat gate must be advisory WARN) — but a *rename* is a clean break, so the version bump must be a hard requirement, not advisory.

## State-Files Written Only by Install Ceremony Never Exist on `source_is_live` Machines

*2026-05-23, self (claude-central).* A state-file whose sole writer is the install ceremony (sentinel, status JSON, registry seed) silently never exists on a `source_is_live` machine — where the live install IS the canonical source and no separate install step ever runs. The **writer-of-record ≠ the operator-of-record**: the ceremony that would write the file is structurally absent. A gate that hard-fails on the file's absence then mis-fires on exactly the machines that are correctly configured.

**Rule.** State-files gated by install ceremony need a **silent self-heal in the workstream-start Preflight** (create-if-absent with sane defaults), not a weaker gate-fallback that papers over the absence. The self-heal makes the file exist on first session regardless of install path; the gate then asserts a real invariant rather than an install-path artifact. Composes with `coordinator-installer-shape.md` (`source_is_live` propagation mode) and the § Doctor-surface vacuous-pass anti-pattern — a sentinel-absent state must self-heal or produce an honest AMBER, never a silent hard-fail on a correctly-configured machine.

## Hardware-Gated Validation — Validate at the Level the Local Box Supports, Name the OOS Gate

*2026-05-24, claude-unreal-holodeck.* When validation requires hardware the local box doesn't have (GPU for CUDA, specific UE version, a physical device), validate **at the level the local box supports** and architecturally OOS the rest **with the gate named explicitly**. The named gate is the difference between honest partial-validation and silent under-validation: "validated CPU path; GPU path OOS — requires CUDA host, gated on `<flag/host>`" tells the next operator exactly what was and wasn't proven. An unnamed skip reads as full validation and ships unverified behavior. Composes with the § three-check completeness test (b/doctor surface) — the gate name is what the doctor or next operator keys on to know the GPU path is unproven, not broken.

## OS-level autostart registration is unsolicited by default

Installers that register OS-level autostart (scheduled tasks, Windows `Startup` LNK files, systemd user units, login items) are unsolicited by default — the user did not ask for the process to run at every session. Gate autostart registration on consumer-session presence (e.g., verify the consuming tool is actually running), or replace with lazy-boot on `SessionStart` hook. Never register autostart silently as a convenience. Apply: any installer that writes to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, `~/.config/systemd/user/`, or `~/Library/LaunchAgents/` must carry a `--autostart` explicit opt-in flag.

## Unit-test the WRAPPER/integration path, not just the self-contained helper

Green helper tests mask integration-layer guards. At least one test must drive the real operator entry point (the wrapper script, the CLI surface, the skill phase-dispatch path) end-to-end, not just the inner function. Apply: for every install surface with a wrapper/CLI, add one test that calls the wrapper and verifies the guard fires — not a test of the helper the wrapper calls.

## Chronically Dirty Tree = Git-Tracked Tooling Outputs — Untrack, Don't Flux-Commit

*2026-05-27, coordinator-claude.* A working tree that is *always* dirty after routine tooling runs (doctor sentinels, last-run JSON, generated mirror metadata) is a signal that **tooling outputs are git-tracked when they shouldn't be**. The fix is to **untrack** them (`git rm --cached` + `.gitignore`), not to flux-commit the churn every session — flux-commits bury real diffs in noise and make `git status` useless as a change signal.

For `copy_install` mirror metadata specifically, the **source repo's `git ls-files` is the oracle** for what belongs in the mirror: the mirror should track exactly the set the source tracks, and tooling-generated outputs (which the source does not track) must not be committed into the mirror. When deciding "does this file belong in the install mirror," query `git ls-files` in the source repo — not the current dirty state of the mirror. Composes with § Multi-site value parity (the source `ls-files` set IS the canonical manifest the mirror's copy-list must match) and `gitignore-policy` (tooling outputs are gitignore targets, not tracked artifacts).
