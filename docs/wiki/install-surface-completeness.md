---
title: Install-Surface Completeness
created: 2026-05-21
author: claude-central-em
status: active
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

The empirical pattern this rule exists to prevent — observed in concentrated form:

1. EM or executor is debugging an issue in repo X.
2. They write a manual tweak to `machine-local/`, an install script, a sentinel file, or some adjacent state.
3. Local tests pass. Their local machine works. The fix lands in a commit.
4. Another operator clones the repo and runs the documented install path on a fresh machine.
5. The install fails — or worse, succeeds but produces broken runtime — because the state the manual tweak left on the author's disk is not reproduced by the installer.
6. Root-cause is **invisible** because:
   - The author's local disk has the state; their tests pass.
   - The CI machine (if any) may also have the state, cached from prior runs.
   - The failure shows up days later on a colleague's machine or a fresh CI worker, with no obvious link to the original work.

The cleanup wave consumed roughly two days of EM time tracing exactly this pattern across the project-rag / project-rag-ue-addon / example-game-workbench-repo trio.

## What counts as "install surface"

Explicit catalogue. Any write to these surfaces triggers the completeness rule:

- **`machine-local/` registry entries** — keys read via `machine-local get <key>` or its Python/PowerShell siblings.
- **Install and setup scripts** — `bin/install.sh`, `setup/install.sh`, `setup/publish.sh`, per-plugin `install-*.sh`, and their templates.
- **Sentinel files** — anything matching the `addon-health-sentinel.md` family, `install-status*.json`, `*-sentinel.json`, drift markers.
- **Hook configurations** — `settings.json`, `settings.local.json`, anything that wires a hook into the session lifecycle.
- **Environment variables and shell-startup additions** — `~/.bashrc`, `~/.zshrc`, PowerShell `$PROFILE`, any per-machine env baseline.
- **Sibling-repo path registrations** — `plugin.mirrors.<plugin>` blocks, `REPO_<NAME>` exports, anything that tells other tools where to find another checkout.
- **Editable-install venv state** — `pyproject.toml` is source code, but the live `.venv/`'s editable-install MAPPING is install state. Changes to `pyproject.toml` that aren't paired with a refresh primitive (e.g. `refresh-plugin-live-install.py <plugin>` (claude-klabauter `coordinator/bin/refresh-plugin-live-install.py`)) leave drift. See `live-install-drift-audit.md`.
- **Doctor surface** — `:doctor` skills are read paths into install state; if your work depends on new install state, the doctor for that surface should detect its absence.
- **INSTALL.md and onboarding docs** — if a new operator's documented path doesn't lead them to the state your work requires, the documentation is part of the install surface that needs updating.

If you wrote to a file or registry that a fresh `~/.claude/` clone wouldn't have, you're on install surface. Default to "yes, this is install surface" when uncertain.

**Bootstrap gap — machine-local/ creation and seeding.** claude-klabauter `coordinator/lib/install-substrate.py:81` (`mkdir -p "$_ml_dst"`) DOES create `~/.claude/machine-local/` on the `coordinator:install` Phase 3 path. The OSS path (`plugins/coordinator/dist/publish-repo-setup/install.sh`, ~59.9 KB) uses a "minimal mirror" that calls `install-substrate.py --setup-only` (C7a/C7b), so both populations — `coordinator:install` users AND OSS `setup/install.sh` users — receive the full machine-local layer (dir creation, tracked baselines including `hardware.toml`, registry seed, bin/ resolver shims, hardware audit). The deprecated `publish-targets.sh` fallback silently activates when the registry directory is absent; it remains in place as a bootstrap backstop until all installations have been migrated to the new seeding path. Any work that depends on `machine-local/` keys must verify which install population the operator used and direct them to the appropriate re-run path (see `coordinator-doctor.md` hardware-probe remediation text for the two-population wording).

## The completeness test — three concrete checks

Before declaring work done, your install-surface writes pass all three:

### (a) Clean-install dry-run

Could you reproduce the state your work depends on by running the documented install path on a fresh `~/.claude/` (or fresh sibling-repo checkout)? If "no" or "I haven't checked," your installer is incomplete. The most direct version of this check is to actually run the installer in a scratch directory; the cheap version is to trace the install script line-by-line against the state your work needs.

### (b) Doctor surface

Does the relevant `:doctor` skill detect the absence of the state your work needs? If a new operator runs `:doctor` on a fresh install, do they get a diagnostic that names what's missing and remediates (or directs them to the installer)? Silent missing-state is the failure mode this check prevents.

**First-party coverage is an obligation, not a nicety — and it has three named reconciliation axes.** A drift condition first surfaced by a *downstream consumer's* chain-triage (or a user's boot-time hard error) rather than by the source repo's own doctor is a doctor *coverage bug*. The doctor must reconcile **declared source-of-truth vs actually-provisioned state** across three axes: (1) installed-artifact version vs local source version (§ setuptools editable MAPPING below — break-class, local); (2) completed-vs-currently-required install phases (break-class, local — conditional on phased installs); (3) installed version vs latest upstream release tag (advisory, consumer-only, network-gated). The full obligation, severity discipline, and source-machine gating live in `doctor-probe-design.md` § First-Party Install-Drift Coverage Is a Doctor Obligation.

### (c) New-user mental model

If a new operator clones the repo and follows `INSTALL.md` (or `README.md`'s setup section), do they land in a working state where your work runs? If your work assumes prior knowledge ("you have to know to also run X"), `INSTALL.md` is part of the install surface that needs updating.

**Failing any of the three means the work is incomplete**, regardless of whether tests pass on your machine.

## The three recurring failure shapes — "works only by accident of machine state"

*Source: project-rag-ue-addon EM (clean-install worked example: `project-rag-ue-addon/docs/plans/2026-05-29-clean-install-just-works.md`). [universal]*

The § Failure-mode narrative above describes the *pattern*; in practice it recurs in three concrete shapes. Each shares one root: **a step that succeeds only because of incidental author-machine state, and fails silently or late on a clean machine.** When your work touches install surface, audit it against all three explicitly — they are the recurring instances the abstract rule exists to catch.

1. **Live-process file-lock during install.** An installer replaces files a long-lived process holds open — a daemon, an editor, a sidecar, an indexer. Breaks *loudly* on Windows (`WinError 5` / "file in use"); may differ *silently* on POSIX (the rename succeeds, the held process keeps the old inode, and the new file is invisible until restart). **Mitigation:** sibling-create + atomic pointer-flip + handle-tolerant cleanup, or a graceful release signal to the holding process — never rename a directory or file a live process holds open.

2. **Editable-install label drift on repo-update.** An `-e` (editable) install whose `.dist-info` / `.pth` / import-finder isn't re-pinned when the repo advances, so the runtime misreports its own version. The MAPPING is baked at install time (see § Setuptools Editable MAPPING below); a `git pull` or a same-version rename never re-bakes it. **Mitigation:** pair every `pyproject.toml` package/version change with a `pip install -e .` (or `uv pip install -e .` / `refresh-plugin-live-install.py <plugin>` (claude-klabauter `coordinator/bin/refresh-plugin-live-install.py`)) step in post-change verification. **Known coordinator-side gap:** `refresh-plugin-live-install.py` returns `NOT_REGISTERED` for the "addon editable-installed into a *sibling's* venv" case — `plugin.mirrors` carries no `propagation_mode` for it. If this pattern recurs across repos, that gap warrants a coordinator-side fix (tracked in the improvement queue, not addon-local).

3. **Dependency-by-venv-leakage.** An importer relies on a dependency declared *elsewhere*, working only because a sibling package leaked it into a shared venv. The import succeeds on the author's machine and `ImportError`s on a clean install where the sibling isn't present. **Mitigation:** every importer declares its own dependencies in its own `pyproject.toml`, plus a pre-flight that verifies hard deps are importable *before* expensive work begins (fail-loud-early, not fail-deep-late).

**Audit checklist.** Before declaring install-surface work done, answer each:

- [ ] Does any install step rewrite a file a long-lived process might hold open? (shape 1)
- [ ] Does any `pyproject.toml` package/name/version change ship without a paired re-install / refresh step? (shape 2)
- [ ] Does any importer rely on a dep it does not declare itself? (shape 3)

A "yes" to any of these without the named mitigation is incomplete work, not a follow-up.

## Maintainer-green is not clean-install-green — the install-surface face of DR-117

*Source: claude-klabauter EM (memo `2026-07-31-claude-klabauter-em-doe-only-signals-in-shipped-guards.md`; claude-klabauter `d6fa361d` → `d19dbe78`). [universal]*

**The rule itself is DR-117 — read it there.** `docs/decisions/DR-117-maintainer-signals-may-classify-never-diagnose.md`, registered as `MAINTAINER-SIGNAL-DIAGNOSIS`: a DoE-only signal (`.doe-root`, `COORDINATOR_CONTENT_ROOT`, a machine-local key) may **classify** an install — "dev or OSS?" — but its absence must never be **evidence that an install is unhealthy**. The discriminator is polarity, not vocabulary: `.coordinator-dev-repo` is exactly as DoE-only and is entirely legitimate, because absence there is a designed fact landing on a fully-supported path. This section carries only what that ruling implies *for install-surface work specifically*, and exists so prior-art-checker surfaces the class on install-touching plans.

**Maintainer-green is not clean-install-green.** This wiki's § Rule says local-green is not clean-install-green; the guard-time sibling is that verifying a fix on the maintainer's own box is the one observation that *cannot distinguish* the two outcomes. `DoE-claude` is one person's tree; `coordinator` ships to dozens, so the absent-signal branch is the **majority** branch and earns primary-path scrutiny.

**Walk the remedy, not just the detection.** The defect's damage was not the false positive but what it armed. The self-probe falsely armed the hook-generation kill-switch, and `generate()` checks the kill-switch marker *ahead* of its plugin-delivery-live check — so the banner's own stated remedy ("re-run the installer / `/coordinator:setup`") returned `"skipped (disabled by operator marker)"`. The user was told to do the one thing that could not work; recovery meant hand-deleting a marker nobody had named. **Before shipping a guard that arms persistent state, walk its own printed remedy from a clean install with that state already armed, and confirm the remedy is not gated behind the thing it undoes.** This composes with § The doctor is the consumer's self-service substitute below: a self-masking remedy is the doctor-substitute failing in the one state it exists for.

**State a guard's *reachable* true positive, not its aspirational one.** A probe registered plugin-side in `coordinator/hooks/hooks.json` cannot run at all on a machine whose only delivery is plugin-side and whose tree is destroyed — the seam wrapper prints "registered hook script unreachable" and exits. Its reachable positive is therefore narrower than a docstring saying "the tree is broken" implies. Write the reachable positive into the module: a carve-out is only assessable against a correctly-stated positive, and an overstated one makes safe carve-outs look risky.

**Audit checklist — apply alongside the § three-shapes checklist whenever the work touches a guard:**

- [ ] Does any guard/probe/banner treat the **absence** of a maintainer-only signal as ill-health rather than as a classification? (DR-117)
- [ ] If a health discriminator reads a registry or config **declaration** (`enabledPlugins`, `installed_plugins.json`, `known_marketplaces.json`), is it paired with a **stat** of the thing it declares? Declarations outlive the tree they name.
- [ ] If the guard arms persistent state, does its own printed remedy work from a clean install *with that state already armed*?
- [ ] Does the guard's docstring claim a true positive wider than the delivery surface it is registered on can reach?

## The doctor is the consumer's self-service substitute for an on-machine EM

*Source: project-rag-ue-addon EM. [universal]*

A downloading consumer has no on-machine EM to hand-patch the three failure shapes above. **The `:doctor` skill IS their EM-substitute** — every install-surface defect must be catchable by a doctor probe, *and the probe must be offer-shaped* (design-as-offers: lead with the remediation — "run X to fix" — not just the violation). A defect that only an on-machine EM could diagnose leaves the consumer exactly where the EM was, minus the diagnostics.

This raises the bar on § completeness-check (b): it is not enough that the doctor *detects* missing state — the doctor must name the fix in the consumer's own vocabulary and, where safe, offer to apply it. A doctor that prints "schema mismatch: version 3 expected, 2 found" and stops is a violation report; one that prints "schema mismatch — run `:doctor --fix` to migrate" is an EM-substitute. The first strands the consumer; the second unblocks them. Compose this framing with § Doctor surface gaps and the vacuous-pass anti-pattern below — a doctor that passes silently on fresh state is the *absence* of the EM-substitute, not a degraded one.

## Multi-site value parity — when one value is mirrored across N locations

A close cousin of install-surface completeness: when a single logical value (a file list, a closed-enum's members, a schema's fields) is **mirrored across multiple source locations**, expanding it in one place leaves the others stale — and the staleness fails *silently*, often in a different test family than the one you ran.

Three observed shapes:

- **A delivered file list lives in 3+ install surfaces.** A new file shipped via `install-substrate.py` appears in (1) the delivery loop, (2) the drift-verifier `PAIRS` array, (3) the fresh-install function. Each executor updated its own slice; two files were templated nowhere; the drift verifier reported zero drift because it only knew its own 3 PAIRS. **Lift the list to a single canonical manifest that all call-sites consume, and add a parity test.** The manifest IS the contract.

- **A closed-enum value lives in the typed source + the JSON schema + the test closed-set mirror.** Expand the Literal / TS-union / Pydantic enum and the JSON-schema `enum` and the test `_VALID_*` constant reject the new value silently — and in *different* test families (`test_release_round_trip` vs `test_provenance_module_stamping`), so a partial sweep passes the first and misses the second. **Grep the VALUE SET (not the variable name — mirrors rename for context) for all locations before commit; add a single cross-mirror parity test if the enum is load-bearing.**

- **A schema field has N projections.** Adding a schema field is not the same as widening every projection of it (NDJSON emitters, walkers, dataclasses, doctors, manifest readers). Schema-additive ≠ projection-additive — audit every projection when you touch the schema.

**Bilateral bump sequencing (cross-repo schema/contract version).** When two repos read each other's manifest, bump the version *reader-first*: both readers must accept `{old, new}` before either side flips its manifest. Same-machine sibling-dir + on-branch + auto-push does NOT relax this — whichever flips first breaks the other's walk immediately (per the reject-unknown-version contract). Land the receive (schema enum + reader accept-range + test) in commit 1; hold the manifest flip until both readers accept.

*Cross-ref: the `game-dev:schema-migration-auditor` worker mechanically enumerates downstream schema readers for UE-flavored schema bumps — dispatch it when a diff bumps a manifest / structural-index version.*

## Cross-repo dimension — doctrine seeding vs. code/install-surface change

Per PM ruling, not all cross-repo writes are the same. The install-surface rule combines with the cross-repo memo doctrine differently at the two altitudes:

- **DoE-altitude doctrine seeding** (CLAUDE.md additions, `docs/wiki/` entries, agent-prompt amendments authored from central-EM under PM direction) is a legitimate direct cross-repo write. The DoE has standing to seed "how we work" into sibling repos. Provenance is noted in the commit message; sibling EM may amend on receipt.
- **Code / install-surface changes in a sibling repo** (source edits, machine-local entries, install scripts, sentinel files, registry edits) route via `cross-repo-memo` CLI (writes ONE dirty file into `<receiver>/cross-repo/`) — **and the PM is handed the receiver path to relay to the affected EM**. The memo file is the persistent record; the PM is the active relay. A memo written without PM-relay is a document dropped in a hole — the affected EM has no signal to look at it. The sibling EM, once briefed by the PM, lands the change with their own implementation context. PM-authorized direct writes are the documented exception, not the default.
- **Why the altitudes differ.** Doctrine is alignment work the DoE owns; code is implementation work the sibling EM owns. Conflating them produces churn in both directions — DoE doctrine that never lands because it routed through a slow memo loop, OR sibling-repo code edits that lose the implementing EM's context.

The cleanup wave was largely the *code/install-surface* failure mode: EMs and executors making manual install-surface tweaks across the trio without the affected EM's coordination.

## Known sub-cases — cross-references to existing wikis

**Path declarations that resolve relative to a peer repo must be grepped against the installed-tree shape, not just the upstream source layout.** Installed trees (post-`pip install`, post-wheel-build, post-clone-to-different-path) can differ from upstream source — symlinks, package re-layout, missing dev directories. Grep your path declarations against the actual installed-tree shape on a clean machine. Distinct from citation-drift-over-time (the existing cross-repo path lesson); this is about installed-tree shape diverging from upstream layout structurally. (Source: project-rag-ue-addon L41)

Each of these codifies a specific install surface or specific failure shape. This wiki is the universal rule; they are the worked examples:

- **`live-install-drift-audit.md`** — source-tree → live-checkout propagation. Specific to plugins where the live install is a separate git checkout (e.g. `project-rag`). Probe: `check-plugin-drift.py`. Refresh: `refresh-plugin-live-install.py <plugin>` (claude-klabauter `coordinator/bin/refresh-plugin-live-install.py`).
- **`coordinator-installer-shape.md`** — the coordinator's own installer (`/coordinator:install`) and its three audiences (OSS adopters, internal users, meta-repo operators).
- **`machine-local-registry.md`** — per-machine value writes (install roots, sibling-repo paths, vendor SDKs) under `~/.claude/machine-local/`. Authors the schema-vs-value distinction.
- **`cross-repo-handshake-doctrine.md`** — when a sentinel crosses a repo boundary, it must self-document its preconditions inline; producer-only documentation is invisible at consumption time.
- **`cross-repo-communication.md`** — the single `cross-repo/` surface and the doctrine-vs-code altitude distinction. Cross-repo memos (dirty files placed in the receiver's `cross-repo/` via the CLI) are signalling artifacts — they do not alter what runs in the receiver repo. The install-surface completeness rule (this wiki) applies to implementation-intent changes; memo delivery is governed by the lifecycle in `cross-repo-communication.md § Cross-repo memo lifecycle`.

## For trio repos (project-rag / project-rag-ue-addon / example-game-workbench-repo)

The trio shares an unusually entangled install surface — host runtime, addon corpus, downstream consumer. Trio-specific discipline lives in the `project-rag` repo's `docs/wiki/trio-install-surface-coupling.md` (resolve the repo root via `repos.project_rag`; project-rag is the install-surface keystone). Trio CLAUDE.md files reference both this universal wiki and the trio-specific one.

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

This wiki is intentionally keyword-dense so prior-art-checker surfaces it on plans touching install surface. Keywords carried: `install surface`, `clean install`, `installer story`, `cross-repo install`, `machine-local`, `doctor surface`, `install completeness`, `live-process file-lock`, `editable-install drift`, `dependency-by-venv-leakage`, `doctor as EM-substitute`, `git-lfs`, `git lfs pull`, `LFS pointer materialization`, `LFS orphan object`, `silent pointer`. Plans that grep for any of these will match this wiki in the prior-art sidecar. Additional keywords from the running-in-Claude-Code section: `running-in-Claude-Code`, `restart-gated`, `configured-but-broken`, `restart-batch`, `validated as working`.

## Doctor surface gaps and the vacuous-pass anti-pattern

**Existence checks on metadata files are weak substrate guards — check structural filesystem signatures unique to the desired substrate AND negative signatures for wrong variants.** A pre-flight that validates "is this a UE install?" via single-file existence (e.g. `Build.version`) catches deletion but not category mismatch — Epic launcher and from-source GitHub clones both ship that file, yet the launcher install is thinner. A pre-flight that passes against the launcher silently produces reduced extraction coverage downstream. Mitigation: check positive structural signatures unique to the desired substrate (`.git/` directory for clones, `Engine/Source/Runtime/Engine/Private/Engine.cpp` for full source) AND negative signatures for the wrong substrate (path prefix `Program Files/Epic Games/`). Generalizable to any third-party install with "lite" and "full" variants. (Source: project-rag-ue-addon L36)

A `:doctor` skill that passes silently when no sentinel files exist is not a health check — it is a vacuous pass. The canonical example is `scan-addon-health.py --red-only` (used by `/workstream-start`): when no `doctor-last-run.json` sentinels exist on a fresh install, the script exits 0 and emits nothing. A fresh-install operator sees no signal that their install has never been doctor'd.

The three-check completeness test (§ above) includes doctor coverage precisely because of this pattern. When authoring or extending a `:doctor` skill, verify that the skill emits a non-trivial finding on a completely fresh install (no sentinels, no prior doctor runs). Sentinel-absent state must produce an AMBER or RED verdict, not a silent pass.

Complementary: `/workday-start` uses `--red-and-stale` (which catches AMBER verdict inversions) while `/workstream-start` uses `--red-only`. This asymmetry is intentional — daily triage posture vs. workstream-start signal-not-noise — but it means verdict inversions (doctor wrote AMBER at 10:03Z, re-probe at 10:30Z returns RED) surface only at the next workday-start, not at interim workstream starts. This is a known limitation, not a bug to fix urgently.

## Singularity gate false-positive on data-only directories — require the plugin manifest, not just runtime output

<!-- spec-backlink: install-dogfood-friction.md (nugget b8-005); distill run 2026-07-22-23h55 -->

**A "rogue coordinator tree" gate that counts a directory as a coordinator install must require a positive structural signature the tree could only have if it IS an install (the plugin manifest, `.claude-plugin/plugin.json`) — not merely the presence of runtime output the coordinator writes as a side effect.** The failure mode mirrors § Doctor surface gaps above (existence checks on the wrong artifact), but for a *tree-identity* gate rather than a health-check gate: a directory containing only `data/doctor-last-run.json` — a runtime artifact coordinator's own doctor writes as a byproduct of running, not a marker of being installed — was flagged by the singularity gate as a rogue coordinator tree. The doctor sentinel is *consumer output*, not *installer signature*; any directory the doctor happens to write into inherits the false-positive regardless of whether a real install lives there.

Fix shape: `_looks_like_coordinator_tree()` gates on the plugin manifest (`.claude-plugin/plugin.json`) existing before counting the path as a coordinator tree at all — the manifest is the one file a genuine install cannot lack and a data-only directory cannot spuriously produce. Generalizes: any gate whose job is "is this path an install of X" should key off X's installer-authored identity file, not off files X's *runtime* happens to write nearby — runtime output is reachable from directories that were never installed (e.g., a shared data/output dir, a doctor run pointed at the wrong cwd), so gating on it produces exactly the kind of accidental-tree false positive this pattern warns against.

## Running-in-Claude-Code — install-surface-completeness ≠ running-in-Claude-Code

<!-- spec-backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § C1 -->

**install-surface-completeness (files on disk + green script phases) is not the same as the integration actually running-in-Claude-Code.** A chain leg is only "complete" when its Claude Code surface is **validated live**:

- **MCP servers it configured connect** — `claude mcp list` shows the server with a live connection, not `✘ Failed to connect`. Status-logged `upserted` is not a live connection.
- **Any LSP it emits boots** — "no project → silent non-attach" is **EXPECTED, not broken**; absent a project-root that activates the LSP, the LSP simply does not attach and no error fires.
- **Plugins and skills it registers are validated as working** — discovery preconditions met (file parses, `description:` trigger phrases present, plugin enabled in `settings.json`) AND the surface is live, not merely present in `settings.json` or `enabledPlugins`. The validation target is **"validated as working,"** not "appears in the config file."

This is the vacuous-pass at the live-integration altitude — the same anti-pattern as § Doctor surface gaps and the vacuous-pass anti-pattern, applied one layer higher. The canonical example of that anti-pattern (a doctor that passes silently on fresh state) IS the named precedent: `claude mcp list` showing `example-game-repo-native-mcp ✘ Failed to connect` while its setup phase logged `status=ok detail="example-game-repo-native-mcp upserted"`. Config present; server never started; the check said green. That is a vacuous pass at the live-integration altitude.

**Enforcement is advisory/surfacing, not hard-fail.** Per § Post-Consumer Gates Must Be Advisory WARN, Not Hard-Fail — any baton completeness mechanism added after consumers exist starts advisory WARN, not hard-fail.

### Discriminator — pending-settle vs. restart-gated-expected vs. configured-but-broken

The discriminator keys on **whether a load-bearing restart has occurred since config-write**, plus a bounded **settle/retry window** before declaring ✘ — NOT a static property of the surface. Four classes:

<!-- Review: code-reviewer — taxonomy was missing a named success class; a reader implementing probe logic had no "done" outcome to key on -->
- **live / validated:** ✓ after settle (probe passes) → validated; emit "validated as working". This is the success outcome — the surface is live and confirmed.
- **pending-settle:** ✘ within the settle window (e.g., a slow-to-start MCP server) → re-probe after the window closes; not yet a verdict.
- **restart-gated-expected:** ✘ after settle, but no load-bearing restart has occurred since the config write → "restart required, then re-validate." This is **NOT a failure**; Claude Code cannot load newly-written MCP registrations or plugin enablements until it restarts. See § Install-chain heavy installs are deliberately agent-gated — the restart is load-bearing for two independent reasons (the gated heavy install AND the harness re-read of newly-written enablement/registry state). Treat as "restart then re-validate," not a broken install.
- **configured-but-broken:** ✘ after settle AND after the load-bearing restart → **fail loud.** This is real misconfiguration.

**Canonical-case resolution:** `example-game-repo-native-mcp ✘ Failed to connect` is restart-gated-expected *pre*-restart — the config was written but Claude Code has not yet restarted to load it. It becomes configured-but-broken ONLY when it shows ✘ *after* the load-bearing restart.

**Lazy-load caveat:** a plugin whose skills load on first reference is not configured-but-broken for skills absent before any reference has occurred — validate **discovery preconditions** (file parses, `description:` trigger phrases present, plugin enabled), not eager load.

### Restart-batch doctrine — order restart-needs first, emit once

A restart is the most expensive event in an install baton. A session boundary means a handoff + re-pickup; the cost is in the **count** of restarts, not their presence. The practical consequence:

1. **Order restart-needs first.** Restart-requiring work is hoisted to the front of the install sequence so one restart clears the maximum surface — surface all restart-gated items up front rather than discovering them interleaved with live checks mid-chain.
2. **Emit one consolidated restart-batch.** All restart-gated items are surfaced as ONE restart-batch (*"these N items require one restart — restart now, then re-validate"*), never per-item restarts that chain several session boundaries where one would do.

   **The load-bearing unit is the restart EVENT, not the literal announce line.** "One consolidated restart-batch" means the operator restarts *once* and re-validates everything — it does NOT mandate a single physical NDJSON line / print statement. What the rule forbids is *per-item* restarts that chain session boundaries; it does not forbid more than one announce line that all map to the same single restart event. When two announce lines both say "restart once, then re-validate," the restart-event count is still one and the doctrine is satisfied.

3. **Two-phase announce carve-out — pre-probe-hoist vs. probe-discovered.** Some restart-gated items are knowable up front (hoistable — read from a manifest / provider_capabilities before any probe runs) and some are discovered only *during* probing (e.g. a host-liveness probe that returns config-correct-but-not-yet-live). The hoist line is emitted at the front of the sequence by construction (item 1), so it structurally **cannot** carry a discovery that does not exist until probes run. In that case, a **second** announce line at the end of the probe sequence — clearly labeled, enumerating the probe-discovered restart-gated items — is the correct shape, NOT a doctrine violation: it is the same single restart event announced in two phases because the two item-classes are discovered at two different times. "Order restart-needs first" (item 1) still governs the hoistable class; it is simply infeasible for the probe-discovered class, which is a structural exception, not an override. A downstream consumer assembles the complete restart set by reading the full stream (hoist-at-front + probe-discovered-at-end). *(Source: example-game-workbench-repo host-mcp-live-restart-batch-fold — project-rag-host validate-live restart-gated discovery cannot be hoisted ahead of the probe that discovers it.)*

The restart-batch primitive is the prevention dimension on top of the detection dimension: the discriminator above tells you what class a ✘ is; the restart-batch doctrine tells you how to minimize the restart count before you ever reach a ✘.

## Two-Layer Install Surfaces — Script-Layer vs. Agent-Layer Altitude

*Source: example-game-workbench-repo. [universal]*

When an install pipeline has two layers — a script layer and an agent/orchestrator layer — both consuming the same upstream structured output (e.g. a doctor report, a health JSON), they consume it at **different altitudes**:

- **Script layer** stays binary: exit-code only. Green/red. It cannot branch on per-bucket detail.
- **Agent layer** goes per-bucket: reads the structured output and branches on individual verdict fields (`CUDA_WARN`, `VRAM_LOW`, `SCHEMA_MISMATCH`, …).

Collapsing these two into a single "check the output once" path forces either the script to parse structured output (fragile) or the agent to operate on a binary signal (loses remediation fidelity). Keep the altitude separation explicit in the install surface design and name which layer consumes which shape in the installer doc.

## One install-script portability bug ⇒ audit the whole install surface

*self (claude-central).* A single portability defect found in an install script is never an isolated typo — it is evidence that the script was authored against the author's shell/OS and not tested across the supported matrix. **Finding one ⇒ audit all install scripts for the same class.** The recurring offenders:

- **bash-3.2 incompatibility** — `declare -A` (associative arrays), `${var^^}` / `${var,,}` (case conversion), and `&>>` appear only in bash 4+; macOS ships bash 3.2. These fail loud (`declare: -A: invalid option`) or, worse, silently mis-parse on the older shell.
- **BSD-vs-GNU flag drift** — `sed -i` (GNU) vs `sed -i ''` (BSD), `grep -P`, `sort -V`, `readlink -f`, `date -d` all diverge between macOS/BSD and Linux/GNU userlands.
- **`python3`-hardcoding** — absent on many Windows hosts (see platform-gotchas § `python3` may not be on PATH); use the PYTHON_BIN resolver.

The fix splits three ways, not one: **(a) fail-loud guard** at script top (assert bash version / required tool present, exit with remediation); **(b) 3.2-safe rewrite** of the offending construct (parallel arrays instead of `declare -A`, `tr` instead of `${var^^}`); **(c) portable-idiom** substitution (host-detect with `uname -s` and dispatch, or pin to the documented-portable subset). Pairs with platform-gotchas § Cross-platform script portability — that rule names the runtime symptom; this rule names the audit-the-whole-surface response when one instance surfaces.

## Install-surface verification is bidirectional — leak-exclusion AND publish-coverage

*example-doctrine-mirror-repo.* Verifying an install/publish surface is two opposite checks, and passing one does not imply the other:

- **Leak-exclusion** (the negative): does the surface *exclude* what must NOT ship — tooling outputs, secrets, machine-local state, scratch? (See § Chronically Dirty Tree — `git ls-files` is the oracle.)
- **Publish-coverage** (the positive): does the surface *include* everything that MUST ship — every source file a fresh clone needs to run?

A single matcher (an `.gitignore` rule, a copy-list glob, a publish manifest pattern) can satisfy one direction and silently fail the other. **The silent-failure mode is a path-root mismatch**: a pattern anchored to the wrong root (`docs/**` vs `./docs/**`, repo-relative vs absolute, leading-slash vs not) compiles cleanly, matches *nothing* against the actual tree, and reports zero violations — the verifier appears green precisely because it is inert. Verify both directions explicitly, and verify the matcher's path-root against a known file that *should* match (assert at least one hit), not just against the absence of unwanted hits.

## Cross-boundary plugin→repo-doc links must be absolute URLs

Relative doc links resolve correctly only *within* a single distribution boundary. A link from plugin-shipped content to a repo doc that crosses the plugin↔repo boundary breaks under the mirror layout — the relative path that was valid in the source tree points at nothing once the plugin is installed to its own subtree. Cross-boundary links MUST be absolute URLs. `validate-references` catches the mirror-layout break. (Source: example-game-workbench-repo.)

## Retiring an installed subsystem has a long orphan-consumer tail

Removing an installed subsystem (a plugin, an MCP server, a helper family, a sentinel class) leaves orphan consumers scattered across surfaces — references in skills, hooks, settings, agent allowlists, docs, other installers. Do **not** chase the tail by working a chunk-list of known call sites; chase it with **grep-zero + collect-only**: grep the retired name across the whole tree, collect every hit, and drive the count to zero. The chunk-list misses the consumers nobody remembered to enumerate. (Source: example-game-workbench-repo.)

## Renaming a literal-filename-discovered artifact breaks consumers silently

A build artifact discovered by **literal filename** (a lockfile, manifest, sentinel, `version.txt`) has consumers that hardcode that name. Renaming it breaks every such consumer silently — no import error, no link failure, just a discovery that finds nothing and degrades quietly. Grep all consumers for the old name and repoint in lockstep within the same change. When a consumer is a sibling repo or plugin, route via `cross-repo-memo` + PM relay (the rename can't land atomically across the boundary). (Source: project-rag-ue-addon.) Composes with § Multi-site value parity and the `Build For Someone Else's Machine` literal-name-discovery class.

## Install-surface bugs must be fixed at the emitter, not the emitted copy

When an install-surface defect appears in emitted state (a generated sentinel, a copied config, a templated script on the consumer machine), fix it at the **emitter** (the installer / template / generator), not in the local emitted copy. A fix to the local copy is the §Failure-mode trap restated: it works on the author's disk and every fresh install re-emits the defect. The fix is real only when re-running the emitter on a clean machine produces correct state. (Source: project-rag-ue-addon.) This is the install-surface specialization of the "fix forward at root cause" principle — the emitter IS the root.

## Install-chain heavy installs are deliberately agent-gated — a leaf bootstrap can only seed batons

In a multi-stage install chain, heavy installs (MCP registration, large downloads, engine indexing) are intentionally agent-gated upstream (e.g. exit 92 = "agent must drive this step"). A pre-restart **leaf bootstrap** can therefore only *seed batons / handoffs* — it cannot perform the heavy install itself. The post-bootstrap restart is **not** "just MCP registration": it exists for two independent reasons (the gated heavy install AND the harness re-read of newly-written enablement/registry state). Do not collapse the restart as a redundant step. (Source: example-game-workbench-repo.)

## Committed publish-mirror of executable scripts — preserve exec-bit, shebang line 1, freshness-compare modulo banner

When an executable script is committed as a publish-mirror copy (a second tracked copy in a distribution tree), the mirror must:

1. **Preserve the exec-bit** (100755) — see § Exec-bit-shebang invariant.
2. **Keep the shebang on line 1** — any injected provenance/banner goes AFTER the shebang, never before it (a banner before `#!` makes the kernel fail to find the interpreter).
3. **Freshness-compare modulo the banner** — the drift check between source and mirror must strip the injected banner before diffing, or every mirror reads as drifted from its source on every check.

(Source: example-game-workbench-repo.) Composes with the SHA-sentinel `copy_install` drift class in `machine-local-registry.md § propagation_mode = "copy_install"` (which notes the installer's banner/BOM injection defeats naive content-diff).

## Mirroring a peer's pinned-CUDA dependency requires mirroring its non-CUDA-host escape hatch

When mirroring a peer repo's pinned-dependency story (e.g. a pinned-CUDA lockfile), you MUST also mirror its **escape hatch** for hosts that lack the pinned hardware/toolchain — copying only the pin strands every non-CUDA host. Two specific traps:

- **`--no-sources` is inert against `--no-deps -r <pinned-lock>`** — the lockfile pins exact versions/sources directly, so `--no-sources` does nothing; the escape hatch must be a *separate* non-pinned install path, not a flag on the pinned one.
- **`soft-dep || true` swallow + a deleted readiness probe = green-twice defect** — a soft dependency that swallows its own failure (`|| true`) AND a readiness probe that was removed produces a doubly-false green: the install "succeeds" and the (absent) probe "passes," so the broken state ships undetected.

(Source: example-game-workbench-repo.) Composes with § Versioned gates / Post-Consumer Gates (advisory-WARN) and the doctor-EM-substitute framing — a deleted readiness probe is the absence of the consumer's self-service diagnostic.

## A runtime sidecar provisions on the host's resolved interpreter, not a separate phase

*Source: example-game-workbench-repo (gpu_sidecar cu130 trap).*

A long-lived runtime's optional sidecar (a GPU worker, an out-of-process indexer, a model server) installs its dependencies onto the **same managed-Python interpreter the host runtime already resolved** — not via a separate install phase carrying its own pip wrapper or interpreter contract. Example-game-repo's gpu_sidecar phase hard-failed under the venv-fallback path because it relied on a pip wrapper that wasn't in scope there and never re-pointed at the venv interpreter the host had resolved; the deps landed nowhere (or in the wrong interpreter) and the sidecar couldn't import them at runtime. Separate-phase provisioning silently drifts from the host path and misses exactly the awkward hosts — managed-Python / PEP-668 / venv-fallback — where the host and phase interpreters diverge.

**Rule:** resolve the interpreter ONCE (the host's `resolve-python` / venv-pin path) and thread that resolved interpreter through every dependent install phase. A sidecar phase that re-resolves its own interpreter is a drift seam — pin it to the host's resolution, or fail loud when the two diverge. Composes with § Three recurring failure shapes (shape 3, dependency-by-venv-leakage — the consumption-side symptom of this provisioning-side cause), § Worked example: editable-install venv pin (single resolution path + interpreter isolation), and § Mirroring a peer's pinned-CUDA dependency (the CUDA pin is the most common dep that exposes the divergence).

## settings.json portability — tracked-union + local-override architecture

`settings.json` portability requires a **tracked-union + local-override** architecture: the tracked file carries the cross-machine union (plugin enables by name, env baselines, hook wiring) and a gitignored `settings.local.json` carries machine-specific overrides (PATHs, marketplace paths). A companion `settings-manifest.md` documents which keys live where so the split is auditable. (Source: claude-central.) This composes with § `settings.json` Is Harness-Managed — relocate machine-specific PATHs to the local layer, but do NOT relocate active `enabledPlugins` enable flags (the harness re-asserts them).

## Agent-facing vs. consumer-facing tooling activation — dev repo vs. consumer disk

*Source: project-rag-ue-addon EM. [universal]*

When a plugin ships agent-facing infrastructure (an LSP, an MCP server, a slash-command, a hook), *where it must activate* depends on **who the tool serves** — and the two answers pull in opposite directions, so name which one applies before setting the attach rule:

- **Tooling the agent uses to work on THIS repo must activate in the shipping repo's own checkout.** An LSP/MCP/hook that the dogfooding agent needs has to attach in the plugin's own tree, not only on a downstream consumer that happens to have a canonical project file at root. If it only attaches downstream, the dogfood loop is dead — the authoring agent can never exercise the tool it ships. **Default-on with no guard beats default-off-when-in-doubt here:** a false-attach is silent noise the agent ignores; a false-non-attach silently kills the dogfood loop.
- **Tooling that exists to serve DOWNSTREAM consumers must match the consumer's disk, not the dev repo.** The counterweight: when the tool's job is to serve a consumer's project (an LSP for consumer UE projects, an MCP for consumer agents), its attach rules should key on *what the consumer has on disk*. Making it false-attach to your own dev repo solves the wrong problem — it can make verification look successful (the tool "attached!") while the real consumer flow stays unverified.

The discriminator is **audience, not convenience**: is this surface something the authoring agent exercises (activate in-tree), or something a downstream user's project drives (activate against the consumer's markers)? A tool can need both — then it carries two attach paths, each keyed to its own audience, not one path that guesses. Conflating them produces either a dead dogfood loop or a green-but-vacuous consumer verification.

## Committed machine-specific absolute paths are a dark install on every other machine

An absolute interpreter path, install root, or OS-specific path that is *emitted on one machine and committed* (e.g. a Windows `python.exe` path baked into a tracked `marketplace.json`, a `/Users/<name>/` prefix in a config) silently breaks the artifact on every other machine and OS that clones it — the path resolves to nothing, and nothing errors until the artifact is used. **Per-machine artifacts must be gitignored and emitted at install time, never committed.** The tracked layer carries the cross-machine union; machine-specific values resolve from `machine-local get` or are re-emitted by the installer on the target box. This is the general form of § `settings.json` portability (relocate machine PATHs to the gitignored local layer) and § Worked example: editable-install venv pin (interpreter path lives in the registry, not the tree). (Source: project-rag-ue-addon.)

## git push "Device not configured" is a credential-routing gap, not a network failure

A `git push` that dies with "Device not configured" (or falls through to an interactive username prompt and hangs/fails) on an HTTPS remote is a **credential-routing** gap, not a broken network or a bad token. The classic shape: an HTTPS remote with the osxkeychain (or other) credential helper configured, but the GitHub token living in the `gh` CLI keyring rather than as a git HTTPS credential entry — so git finds no credential, falls back to a tty username prompt, and dies in a non-interactive context. Network and auth are both fine; only the wiring between them is missing.

**Fix:** `gh auth setup-git` installs a global non-interactive credential helper that routes git's HTTPS auth through the `gh` token. On dev machines prefer an SSH agent (e.g. 1Password SSH agent) as the primary path with `gh`-token as the headless fallback. Do not chase this as a token-scope or firewall problem — verify the credential-helper wiring first. (Source: example-game-workbench-repo.)

## When this rule does NOT apply

- **Pure runtime path resolution** — covered by `docs/wiki/machine-local-registry.md` § 4 Resolution Order (formerly `Build For Someone Else's Machine` in coordinator/CLAUDE.md), not this rule. That rule says "explicit flag → env var → marker auto-discovery → silent skip / hard error"; this rule says "and your installer must produce the marker."
- **Test fixtures and battle-story comments** — pinned paths in fixtures or one-off forensic comments are exempt from the cross-machine reproduction requirement.
- **Genuinely one-machine ephemera** — `~/.bash_history`, editor state, OS-level config a project has no business touching. If you find yourself writing to user-level state the project doesn't own, the question isn't installer-completeness — it's *should the project be writing there at all*.

## Skill-script phase parity — audit both surfaces when one gains a phase

When a skill (agent-dispatched) and a standalone script cover the same pipeline, their phase lists can drift independently. A phase added to the skill but not the script (or vice versa) means one execution path silently skips a check the other requires. Resolve divergence via a wrapper that delegates to the canonical surface, not by gate-overloading (adding conditional logic to both surfaces independently). Parity audit procedure: grep both the skill body and the script for their phase-list definitions, diff them, and add a CI assertion that counts phases in both surfaces and fails on mismatch. (Source: project-rag-ue-addon)

## Publish-Target Parity — Script+Manifest Pairs and Machine-Local Registry

### Re-publishing a script+manifest pair requires re-publishing BOTH targets

When an install pipeline chains a manifest (e.g. `docs/install/` flat-mirror target) to a script (e.g. `coordinator/scripts/` mirror target), re-publishing only the manifest leaves the published script stale. The chain-walker reads the manifest from one target and invokes the script from the other; a manifest-only re-publish produces a version skew that fails on the first dogfood run.

**Rule:** an install-surface change to a script+manifest pair must re-publish BOTH targets that produce them. Dogfood against the PUBLISHED layout, not the dev tree — the dev tree hides layout-relative drift the publish exists to fix.

Empirical basis (Machine-c coordinator-install-seed-phase dogfood): a manifest-only re-publish left the published script stale; the dogfood failed first-pass (`Unknown argument: --phase`).

### Contract-required publish targets in the portable publish-targets template silently drop on new devices — use machine-local registry

The active `setup/publish-targets.sh` is gitignored/per-machine. A fresh device that hand-copies only the `mirror` row from `setup/publish-targets.portable` loses the contract-required `toplevel-install` and `toplevel-wiki` targets with no error — those rows simply don't exist in the per-machine file.

**Fix:** write required targets into the machine-local registry via `machine-local array-append publish.targets` / `machine-local array-set publish.targets`, combined with a registry-aware pre-flight that derives and injects required toplevel rows at publish time. Documentation telling operators to hand-copy rows is install-surface-incomplete — the enforcement must be structural, not prose.

Empirical basis (Machine-c coordinator-install-seed-phase C0/C0b).

### Tracked topology + `repos.*` resolution is the evolved fix for this problem class

The portable `repo:` row format in `setup/publish-targets.portable` closes the silent-drop gap structurally. The shared topology (which targets exist) is committed and travels via git; per-machine DEST roots resolve at publish time from `machine-local get repos.<dest_key>`. An unset key fails loud with a remediation message instead of silently dropping targets. See `machine-local-registry.md § 5c.1` for the resolver contract and bootstrap precondition, and `plugin-extraction-and-distribution.md § Portable publish topology + provisioning a new machine` for the new-machine setup sequence.

### When source and publish layouts diverge, cross-file path resolution must be layout-aware in BOTH directions

Fixing a manifest→script resolution for the publish flat layout does NOT automatically fix the reverse (script→manifest). Each cross-file path reference carries its own layout assumption; making one direction layout-aware does not close the others.

**Rule:** when a publish layout differs from the source tree, enumerate every cross-file path assumption in the affected surface — manifest→script, script→manifest, and sibling resolutions — and make each layout-aware in the same change. The test is: does a cold-tree install from the published artifacts resolve every path without error? Probe both candidate roots and fail loud with a re-publish remediation message if neither resolves.

**Corollary — `set -u` latent crash:** a variable set only in one code path (e.g. `--check`) but referenced in another (e.g. full-install) is a latent `set -u` crash. Assign-or-guard at every reference site, not just at the primary code path.

Empirical basis (Machine-c coordinator-setup-manifest-path-mismatch memo): the install-seed-phase plan fixed manifest→script resolution in the publish flat layout but left `setup.sh`'s script→manifest resolution assuming `REPO_ROOT/docs/install/` when the flat-mirror publishes the manifest at the repo ROOT one level up. A cold-tree install crashed (`manifest parent directory not found`, then `_MANIFEST_PATH: unbound variable`).

## `settings.json` Is Harness-Managed — Relocate Paths, Not Enable Flags

### settings.json enabledPlugins is harness-re-asserted — relocate machine-specific paths, not active enable flags

`settings.json` is a live harness-managed file. The harness re-asserts `enabledPlugins` entries for active plugins back into `settings.json` regardless of any `settings.local.json` override — an enabled plugin's by-name flag propagates back within the session. Fighting this is the fight-the-hook anti-pattern.

**Rule for portability fixes on harness-managed config:** relocate machine-specific PATHS (e.g. marketplace path entries) out of tracked `settings.json` into gitignored `settings.local.json` — that change is durable (the harness leaves paths in local alone once moved). Do NOT attempt to relocate active `enabledPlugins` enable flags; the harness re-asserts them and the relocation silently reverts each session. An enable keyed by name (not a path) is not a portability defect — a fresh installer without the marketplace simply does not load the plugin.

**Corollary — acceptance-criteria test binding:** do NOT gate acceptance-criteria tests on the *contents* of a harness-managed live file (`settings.local.json` EKM/enabledPlugins churn per-session — the harness moves marketplace entries between EKM and enabledPlugins between reads). Gate only the durable *tracked-file* invariant (e.g. "no machine PATH in tracked `settings.json`"); mark the harness-managed assertion `cited:` shipped-differently in the oracle table.

Empirical basis (Machine-c portability-tracked-per-machine-config C5): moving a machine-specific marketplace PATH from tracked `settings.json` to `settings.local.json` was durable. But the harness re-asserted active `enabledPlugins` entries back into `settings.json` within the same session. A retired Step 3.8 oracle (acceptance oracle) that gated on `settings.local.json` contents flipped RED after a clean commit because the harness had reorganized those contents between the commit and the oracle check.

## Worked example: editable-install venv pin

An editable `pip install -e` of a coordinator-owned Python package into the bare system `python3` failed in two independent ways that were invisible at authoring time. First, Homebrew Python and Debian Python now refuse direct `pip install` into the system interpreter (PEP 668 — "externally managed environment"), so the install command errored on fresh macOS/Linux machines. Second, even where the install initially succeeded, a system Python bump (e.g. Homebrew upgrading from 3.12 to 3.13) silently invalidated the `.dist-info` entry — the package raised `ImportError` after the upgrade with no signal pointing at the coordinator install.

The fix: a coordinator-owned venv builder — originally `bin/ensure-coordinator-venv.sh`, since ported to the native `coordinator_core.install.ensure_venv` (claude-klabauter-resident, invoked via `/coordinator:install` Phase 3 Step 6 / `install-substrate`) — creates a coordinator-owned venv at `~/.coordinator-venv/`, seeds the dependency-bearing package via editable install into that venv, and writes the absolute interpreter path to the machine-local registry as `coordinator.python`. The `coordinator.python` resolution contract resolves `COORDINATOR_PYTHON` env → `machine-local get coordinator.python` → PATH fallback, with a loud error if the pin is stale (formerly implemented by `lib/resolve-python.sh`; that FLOOR shim is retired — see `machine-local-registry.md § coordinator.python resolution contract`). The coordinator doctor (P-5) uses the resolved interpreter, not bare `python3`, so it catches venv-absent and pin-stale states and self-heals via the venv builder (`/coordinator:install` Phase 3 Step 6).

This instance illustrates the **editable-install label drift** failure shape (§ Three recurring failure shapes, shape 2) combined with a **PEP-668 install block** that prevents recovery via the old remediation path. The venv is the canonical solution: interpreter isolation + drift-proof re-pinning via the registry + doctor-driven self-heal closes all three gaps.

## Plugin hook registered in plugin's hooks.json must NOT be re-registered in consumer settings.json

A plugin that self-registers a hook via its own bundled `hooks.json` must NOT also be hand-vendored into the consumer's `settings.json` — the duplicate drifts and breaks cross-platform.

Example-game-repo's `settings.json` carried a hand-wired `powershell.exe -File .claude/hooks/project-rag-staleness.ps1` SessionStart registration that was a byte-identical, redundant duplicate of what the project-rag plugin already registers via its own `hooks.json` (with `pwsh` + `${CLAUDE_PLUGIN_ROOT}`). The vendored copy added no value, diverged to the wrong interpreter (`powershell.exe`, Windows-only vs the plugin's cross-platform `pwsh`), and errored every SessionStart on macOS.

**How to apply:** when an enabled plugin owns a hook via its bundled `hooks.json`, the consumer registers nothing — deleting the consumer's duplicate is the fix, not patching it. A consumer-side hook registration is only correct for hooks the consumer itself owns (e.g. a project's `boot-project-services.sh`). Cross-platform hooks use `bash` or `pwsh`, never `powershell.exe`. The hook-install install surface is the plugin's `hooks/hooks.json`; the consumer's `settings.json` is not the install surface for plugin-owned hooks. Composes with § `settings.json` Is Harness-Managed and § Install-surface bugs must be fixed at the emitter.

### Worked example — this rule held 22 violations on the maintainer's own box, undetected {#duplicate-registration-worked-example}

*DoE-claude dev install on Windows. Full write-up: DoE-claude `state/2026-08-07-oduffy-pc-install-dogfood-friction-log.md` § F3.*

`~/.claude/settings.json` carried 27 hook commands (22 distinct scripts) that the coordinator plugin's own `hooks.json` already registered at the same event. Confirmed three independent ways: claude-klabauter's `detect_hook_delivery_duplication()` (`double_fire=True, duplicated=22, settings_only=6`); an independent basename+event enumeration; and **direct runtime observation** — `agent-completion-log.py` is one of the 22, and every agent dispatch wrote two identical rows to `.git/coordinator-sessions/logs/agent-audit.jsonl` (same timestamp, same `agentId`). Onset dating across 218 rows: zero doubled on every prior date, 3-of-3 on the day it was found.

The rule above was already written, already correct, and already precisely on point. **Three things still let 22 violations accumulate silently:**

1. **Nothing enforces it.** There is no gate, test, or commit-time check for consumer-side re-registration of a plugin-owned hook. The only detector is a SessionStart banner — advisory, easily read past, and in this case actively wrong (it rendered *"nothing is firing twice today"*; see the `plugin_resolvable` defect in claude-klabauter's `format_hook_delivery_banner`).
2. **The cost is invisible per-occurrence and severe in aggregate.** One duplicated hook is one extra process spawn. Twenty-two of them, on the platform whose standing P0 is `spawn-count × indirection`, is a doubled hook tax that presents as "the machine feels slow" rather than as a config defect.
3. **The two surfaces spell the same script differently** — `settings.json` bakes absolute paths, the plugin uses `${CLAUDE_PLUGIN_ROOT}` — so a naive comparison finds no overlap. Any check written for this rule must compare by **resolved script identity + event**, never by command text. A check that compares raw strings will report a confident, permanent green.

**The durable ask this example makes:** a rule stated in prose with no mechanism is a rule that will be violated by the very install that documents it. This section's own existence did not prevent the incident it now describes. Prefer a commit-time or ceremony-gate check over another paragraph.

## Enumerate a fix's class from the producer, not from the instance in front of you {#enumerate-from-the-producer}

*[universal] From three break-class install defects, in nine days, that shared one shape. Lesson: `state/lessons/2026-08-07-enumerate-a-fix-s-class-from-the-produce-*.yaml`.*

A fix scoped to the instance that surfaced it leaves every sibling instance live — **and the documentation of the fix makes the class look closed**, so the next operator reads the remedy, sees it applied, and stops looking. Three worked examples, all from one install repair:

| # | The fix, correctly reasoned and written down | The sibling it did not reach |
|---|---|---|
| 1 | Deleted hook scripts brick every write. Remedy: *"commit the deletion in the same commit as the `hooks.json` registration removal."* Applied to the plugin-side `hooks.json`. | `settings.json` is a **second registration surface**. Nobody named it; it reproduced the identical every-write-blocked incident nine days later, with three of the same four scripts. |
| 2 | `.doe-root` retired as machine-local state in a synced repo; **writer** migrated to `<settings-home>/machine-local/.doe-root`. | `is_inline_install` in claude-klabauter still **reads** the legacy rung. The canonical dev box now falls through both self-probe carve-outs and kill-switches its own hooks every boot. |
| 3 | `~/.claude/.gitignore` block forbidding tracked machine-local coordinator state; lists `.doe-root`, `.coordinator-hooks-disabled`. | `.coordinator-content-root-last-seen` — written by the **same probe, in the same call, every boot** — was not listed, so one machine's resolution result was tracked into every other checkout. |

In all three the reasoning was sound and recorded; only the **scope of application** was narrower than the scope of the problem. Nobody was careless — the *enumerations* were.

**How to apply.** Before closing a fix, derive its class from the producer rather than from the reporting instance:

- **A writer moved?** Grep every **reader**, across all repos. A cross-repo seam makes this failure silent by construction: the writer's repo tests pass, the reader's repo tests pass, and only a real install exercises the seam.
- **A hook/script/registration was retired?** Check **every delivery surface that can declare it** — the plugin `hooks.json`, the consumer `settings.json`, and any generated config. One is not the set.
- **The rule is expressed as a list of filenames?** Ask what **function produces those files**, and whether it produces others. An enumeration that is complete when written is incomplete the moment a new file joins the class, and nothing signals that.

Prefer a guard that asks the question — *"is any tracked file under `~/.claude` written per-boot by a coordinator hook?"* — over a list a future author must remember to append to. Composes with § Multi-site value parity and § Install-surface bugs must be fixed at the emitter, not the emitted copy.

## How this rule was authored and extended

This wiki is authored by central-EM under PM direction, generalizing the project-rag trio's cleanup-wave pattern, the three recurring failure shapes audit checklist, and the "doctor is the consumer's self-service substitute for an on-machine EM, offer-shaped per defect" framing into universal doctrine.

Sibling EMs in all repos may amend this wiki on receipt — doctrine-seeding under the cross-repo altitude distinction (§ Cross-repo dimension above) is alignment-shaped, not fait-accompli.

## Step Zero Preflight and Env-Normalization Shape

<!-- spec-backlink: docs/plans/2026-06-22-coordinator-env-normalization-step-zero.md -->

### FB-2 rule — functional-not-existence probes (required)

**Existence probes are insufficient install-surface guards for prerequisites.** A check that only asks "is the binary on PATH?" silently passes for:

- Windows App-Execution-Alias stubs (python3 resolves but does not execute)
- Wrong-version installs that satisfy PATH presence but fail runtime requirements
- Shims that delegate to absent interpreters

The `--preflight` gate (`scripts/setup.py --preflight`) uses **functional probes** from `coordinator_core.install.prereq_probe` (native Python port; claude-klabauter) — each probe executes a minimal runtime operation to confirm the tool actually works, not just exists. This is FB-2 (functional-not-existence probe) as a required rule for any install-surface prerequisite check added to the coordinator. Existence checks are acceptable only for optional informational rows in the status table (never for hard or advisory gates).

### Advisory-WARN gate severity for post-consumer gates

Cross-ref: § Post-Consumer Gates Must Be Advisory WARN, Not Hard-Fail (below).

The `--preflight` step implements this doctrine for all env-prereq probes except Python: `clone_auth`, `uv`, `longpaths` (Windows), `pwsh`, and `ue` probes emit advisory WARN and allow install to continue. Only the `python` probe is a hard-fail gate, because Python is the load-bearing interpreter for hooks and JSON manipulation — every other prereq has either a fallback or is optional. Adding a new hard-fail gate to `--preflight` after consumers already exist requires PM sign-off and a migration window (see Post-Consumer Gates rule).

### Env-fix consent/backup/restore safety shape

`scripts/normalize-env` (sh/python polyglot trampoline over claude-klabauter `coordinator_core.ops.normalize_env`, bash-clean-slate migration) is the sole writer for fixable env-prereq conditions. Its safety contract:

- **Consent-gated per mutation** — each proposed mutation is enumerated and requires explicit acceptance; `--yes` accepts all; `--dry-run` previews without writing.
- **Backup before every write** — every mutation creates a timestamped backup before applying; `--restore` reverts to the pre-run state. The backup/restore discipline covers Windows PATH edits and registry mutations AND the macOS `~/.bash_profile` reconstruction (the one consent-gated macOS mutation — see § macOS/Linux = offers only below).
- **Blast-radius-last ordering** — higher-impact mutations (e.g. global PATH changes) are offered after lower-impact ones (e.g. enabling a Windows feature flag).
- **macOS/Linux = offers only, with one named carve-out** — the script emits advisory text on non-Windows platforms and applies no mutations, EXCEPT: macOS performs ONE consent-gated mutation when an operator has a bash login shell (switched via `chsh`) and their `~/.bash_profile` is absent or minimal. In that case the script reconstructs `~/.bash_profile` from a snapshot of the prior shell's PATH (see § Worked example: brew bash on macOS). This carve-out exists because a bash login shell without a proper `~/.bash_profile` orphans PATH additions that lived in the prior shell's rc chain. Coordinator NEVER proactively suggests `chsh`; this mutation is remediation-only for operators already on a bash login shell.
- **Contract — `scripts/lib/prereq_probe.sh` stays bash-3.2-parseable; `normalize-env` itself does not.** `normalize-env` runs as Python and calls the native `coordinator_core.install.prereq_probe` port in-process — the bash-3.2 floor does not govern `normalize-env`'s own logic. `scripts/lib/prereq_probe.sh` itself is NOT deleted: per DR-079 it stays on disk as the byte-stable vendor SSOT that project-rag-ue-addon and deep-research vendor-and-source, so it must remain bash-3.2-parseable for those consumers. See `coordinator-installer-shape.md` § Step Zero and `cross-platform-shell-portability.md`.

The probe lib (`coordinator_core.install.prereq_probe`) and the fixer (`normalize-env`) are separated by design: **probe lib = read-only SSOT, fixer = sole writer, gate (`--preflight`) = reader**. This prevents the probe from mutating state mid-check (vacuous-pass anti-pattern) and keeps the fixer auditable as the only mutation surface.

### Deferred verification — Windows-specific items (open items in the OS/version test matrix)

**Windows PowerShell 5.1 execution — descoped, not deferred.** `scripts/setup.ps1` is not required to run under `powershell.exe`; pwsh 7+ is the only supported host. This is not an open matrix item awaiting a Windows run.

**AC9 — consent-invariant on real mutation.** Whether the `--yes` flag correctly gates consent for every mutation type (including registry edits, PATH changes, and feature flags) under a real Windows environment is macOS-unverifiable. Tested structurally via dry-run on macOS; real mutation behavior is Windows-deferred.

**AC10 — PATH/shim rollback round-trip.** Whether `--restore` correctly reverses PATH and shim mutations applied by `normalize-env` on Windows is macOS-unverifiable. The backup mechanism is structurally sound from code inspection, but the round-trip (apply → restore → verify unchanged state) requires a Windows box to confirm. Both AC9 and AC10 are tracked as Windows-deferred in the version/OS test matrix.

> **CI enforcement arm.** Closing the deferred items above (AC9–AC10 consent/rollback under a real Windows environment) requires a multi-OS CI matrix with an honest measurement gate. → `cross-platform-ci-discipline.md`

## Post-Consumer Gates Must Be Advisory WARN, Not Hard-Fail

*project-rag.* A cross-repo or cross-version compatibility gate added AFTER consumers already exist must default to advisory WARN rather than hard-fail. A hard-fail gate applied retroactively causes every consumer predating the gate to regress on upgrade — the gate produces a silent install-regression that surfaces only when a consumer next runs. Pattern: emit a clear `WARN: <reason>; this will become an error in <version>` message, give consumers a migration window, then promote to hard-fail in a named future version. Never introduce a hard-fail gate whose failure predates the gate's existence. (Source: project-rag)

## Setuptools Editable MAPPING Is Baked at Install Time

*project-rag.* With `pip install -e .` (editable install), setuptools bakes a `__editable__.<pkg>.pth` or `MAPPING` file at install time from the current `pyproject.toml`. Adding a new package or sub-package to `pyproject.toml` after the editable install does NOT automatically register it — the new package is invisible to `import` until `pip install -e .` is re-run. This affects both the venv-state leg of the live-install propagation and local dev workflows. When a plan adds packages to `pyproject.toml`, include `pip install -e .` (or `uv pip install -e .`) as an explicit step in the post-change install verification. (Source: project-rag)

## Release-Channel Gates — Local Fixes and Rename Bumps

*Consolidated from L10/L231 (project-rag-ue-addon).* Two facets of the same install-surface failure: a fix that lands only on the author's disk, and a rename that strands installs by skipping the version gate.

- **Local-only data fixes don't help fresh clones (L10).** A data correction applied directly to the author's local checkout (a fixed index row, a hand-patched config, a corrected corpus entry) does nothing for a `clone-and-go` user — the fresh clone reproduces the *old* data. The fix is only real when it ships through the **canonical distribution channel** (the installer, the seeded fixture, the release artifact, the migration). "It works on my disk" is the §Failure-mode trap restated for data, not just install scripts. Trace: does a fresh clone of the released artifact carry this fix? If no, it isn't shipped.
- **Package rename without a version bump strands every editable install (L231).** Renaming a package or sub-package without bumping the dist-info version leaves every `pip install -e .` consumer importing the *old* name with no signal to re-install — the editable MAPPING is baked at install time (see § Setuptools Editable MAPPING above) and a same-version rename never triggers a refresh. **Gate on dist-info version bump:** a diff that changes `packages = [...]` / `name = ...` in `pyproject.toml` without bumping `version` is a release-stranding smell. Pair the rename with a version bump AND a `pip install -e .` step in post-change verification, so the MAPPING re-bakes against the new name. This composes with § Post-Consumer Gates (a retroactive compat gate must be advisory WARN) — but a *rename* is a clean break, so the version bump must be a hard requirement, not advisory.

## State-Files Written Only by Install Ceremony Never Exist on `source_is_live` Machines

*self (claude-central).* A state-file whose sole writer is the install ceremony (sentinel, status JSON, registry seed) silently never exists on a `source_is_live` machine — where the live install IS the canonical source and no separate install step ever runs. The **writer-of-record ≠ the operator-of-record**: the ceremony that would write the file is structurally absent. A gate that hard-fails on the file's absence then mis-fires on exactly the machines that are correctly configured.

**Rule.** State-files gated by install ceremony need a **silent self-heal in the workstream-start Preflight** (create-if-absent with sane defaults), not a weaker gate-fallback that papers over the absence. The self-heal makes the file exist on first session regardless of install path; the gate then asserts a real invariant rather than an install-path artifact. Composes with `coordinator-installer-shape.md` (`source_is_live` propagation mode) and the § Doctor-surface vacuous-pass anti-pattern — a sentinel-absent state must self-heal or produce an honest AMBER, never a silent hard-fail on a correctly-configured machine.

## Hardware-Gated Validation — Validate at the Level the Local Box Supports, Name the OOS Gate

*example-game-workbench-repo.* When validation requires hardware the local box doesn't have (GPU for CUDA, specific UE version, a physical device), validate **at the level the local box supports** and architecturally OOS the rest **with the gate named explicitly**. The named gate is the difference between honest partial-validation and silent under-validation: "validated CPU path; GPU path OOS — requires CUDA host, gated on `<flag/host>`" tells the next operator exactly what was and wasn't proven. An unnamed skip reads as full validation and ships unverified behavior. Composes with the § three-check completeness test (b/doctor surface) — the gate name is what the doctor or next operator keys on to know the GPU path is unproven, not broken.

## OS-level autostart registration is unsolicited by default

Installers that register OS-level autostart (scheduled tasks, Windows `Startup` LNK files, systemd user units, login items) are unsolicited by default — the user did not ask for the process to run at every session. Gate autostart registration on consumer-session presence (e.g., verify the consuming tool is actually running), or replace with lazy-boot on `SessionStart` hook. Never register autostart silently as a convenience. Apply: any installer that writes to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, `~/.config/systemd/user/`, or `~/Library/LaunchAgents/` must carry a `--autostart` explicit opt-in flag.

## Unit-test the WRAPPER/integration path, not just the self-contained helper

Green helper tests mask integration-layer guards. At least one test must drive the real operator entry point (the wrapper script, the CLI surface, the skill phase-dispatch path) end-to-end, not just the inner function. Apply: for every install surface with a wrapper/CLI, add one test that calls the wrapper and verifies the guard fires — not a test of the helper the wrapper calls.

## Exec-bit-shebang invariant

> Spec backlink: `archive/specs/2026-06/2026-06-11-exec-bit-install-surface-completion.md`

### The invariant

Any tracked file whose first two bytes are `#!` MUST be committed at index mode `100755`. A shebanged file at `100644` is a silent install-surface failure: on any Unix clone, `[[ -x "$file" ]]` gates skip it, the interpreter never runs it, and the failure surfaces only at the downstream user's machine — not at the Windows authoring machine where `core.fileMode=false` suppresses all mode-bit visibility.

First confirmed instance: `session-init.sh`'s hygiene scripts (`lock-reaper`, `configure-git`, `renormalize-index`) committed at `100644` — dead on Mac/Linux until an install caught them via `[[ -x ]]` gating. Source lesson: `state/lessons/` content-anchor "A boot-hook script committed at mode 100644 silently never runs on fresh Mac/Linux clones [universal]".

### Three enforcement surfaces — each load-bearing

A single enforcement surface is not enough. Each protects a different stage:

1. **Precommit hook** — fires at commit time; surfaces new drift before it reaches the index. Meta-repo: `coordinator-precommit-exec-bit-check` → `exec-bit.test.js` (scope: any tracked file with `#!` shebang, any directory). OSS repo: parallel shim installed by `coordinator/dist/publish-repo-setup/install.sh`.

2. **CI validator** — fires on every PR; catches drift that bypasses the precommit hook (force-push, hook-skipped commit, Windows author without `core.fileMode` awareness). OSS repo: `check-exec-bit.py` wired into `.github/workflows/validate-plugins.yml`. NO allowlist — CI is the strict gate; any legitimate exception belongs in a DR, not the validator.

3. **Install-time chmod** — fires on a clean install; last-resort safety net against broken source-index state surviving into an end-user machine. `coordinator/dist/publish-repo-setup/install.sh` shebang-scans every installed file and `chmod +x` anything starting with `#!`.

Losing any one surface means silent failure at that stage. **Cross-surface obligation:** a fix that lives only in the meta-repo silently degrades OSS-user experience until re-clone. The obligation is to land all three surfaces (source-of-truth fix + percolation target fix + install-path awareness) in the same plan, never any single one alone.

### Windows-chmod commit mechanic

On Windows with `core.fileMode=false` (standard Machine-a config), the SC-DR-008 scoped-commit form `git commit -m "..." -- <paths>` silently resets exec bits: the path-restricted commit re-reads the working-tree pathspec and overwrites the `update-index` staged mode with the on-disk mode (always `100644` when `fileMode=false`).

**Correct mechanic for chmod-bearing commits** (named exception to SC-DR-008):

```bash
# Stage via update-index — NOT git add:
git update-index --chmod=+x -- <file1> <file2> ...

# Verify: git ls-files --stage <file> must show 100755

# Commit WITHOUT path restriction:
git commit -m "<subject>"
# No '-- <paths>' suffix. The path restriction re-reads working-tree mode under
# core.fileMode=false and resets the staged exec bit back to 100644.
```

The path restriction in SC-DR-008 is a re-staging guard to prevent blanket-staging of unrelated files. Once files are correctly staged via `update-index`, the path restriction is redundant and triggers the `fileMode=false` interaction. This carve-out also appears in `agents/executor.md § Commit Discipline` so dispatched executors see it at load time.

Source lesson: `state/lessons/` content-anchor "Windows `core.fileMode=false` + path-restricted `git commit` resets exec-bit in index [universal]".

### Scope-hole rot pattern

Narrow guards rot at the edges when the authoring machine doesn't reproduce the failure mode. The precommit hook initially covered `.sh` files under `bin/`+`hooks/scripts/` only. A later Mac install error surfaced that `.py`, `.js`, `.bats`, and extensionless shebanged files in `lib/`, `tests/`, `setup/`, `.github/scripts/`, and `dist/` were entirely unguarded — 141 files in meta-repo, 211 in OSS.

Rule when scoping a new guard: enumerate the negative space at design time (everything the guard does NOT cover, by extension and by directory) and either justify each exclusion architecturally or widen the scope. Default to the broadest enforceable scope; narrow only with a named cost. The cost of a wider scope is usually one regex change; the cost of a scope hole is a downstream-user-facing failure some days later.

## Hook-Install Probes — Self-Heal on Session Boot, Not Install-Time Only

*coordinator-claude.*

Crash-insurance hooks installed only at `/repo-setup` time silently rot: repos that pre-dated the doctrine, repos whose `.git/hooks/` got wiped (clean clone, worktree, machine migration), and any user who never ran `/repo-setup` lose the safety net with no warning. The day's commits stranded on local disk; the absence was discovered only when `/workstream-complete` tried to push.

**Rule:** any hook the doctrine relies on for crash insurance or safety-net behavior MUST self-heal on every session boot, not only at install time.

Mechanism: add a per-session `ensure-helper` (e.g., claude-klabauter `coordinator/bin/coordinator-ensure-hooks-fleet`) called unconditionally from a boot-time SessionStart hook. The helper is idempotent — a no-op when the hook is already present and correct. Companion: a `/workday-start` step that surfaces the "unpushed-commits-but-no-hook" signal catches the silent-failure mode even when the hook never wrote to `.git/push-failures.log`.

**Audit completeness — runtime-derived patterns must enumerate the multi-machine variation axis.** When designing an audit that derives its patterns from `$HOME`, `$SCRIPT_DIR`, or any other runtime-context value, the patterns will only match the running operator's flavor. Add shape-catchers for every OS-axis variation (Windows native paths, Git-Bash POSIX paths, macOS paths, Linux paths) plus embedded placeholder allowlists (`yourname|name|user|operator|foo|<...>`) so pedagogy isn't flagged but real identity literals are. Source: personal-data-cleanup spinoff.

## Chronically Dirty Tree = Git-Tracked Tooling Outputs — Untrack, Don't Flux-Commit

*coordinator-claude.* A working tree that is *always* dirty after routine tooling runs (doctor sentinels, last-run JSON, generated mirror metadata) is a signal that **tooling outputs are git-tracked when they shouldn't be**. The fix is to **untrack** them (`git rm --cached` + `.gitignore`), not to flux-commit the churn every session — flux-commits bury real diffs in noise and make `git status` useless as a change signal.

For `copy_install` mirror metadata specifically, the **source repo's `git ls-files` is the oracle** for what belongs in the mirror: the mirror should track exactly the set the source tracks, and tooling-generated outputs (which the source does not track) must not be committed into the mirror. When deciding "does this file belong in the install mirror," query `git ls-files` in the source repo — not the current dirty state of the mirror. Composes with § Multi-site value parity (the source `ls-files` set IS the canonical manifest the mirror's copy-list must match) and `gitignore-policy` (tooling outputs are gitignore targets, not tracked artifacts).

## Worked example: brew bash on macOS

**Failure mode.** `coordinator:install` Phase 1a.0 originally **detected** stock bash 3.2 on macOS and **printed** a remediation block (`brew install bash` + a PATH-prepend line). The user reading the printed text could ignore it, or follow it incorrectly (writing to `~/.zshrc` — interactive-only — instead of `~/.zprofile` — login-shell). Empirical: on Machine-c, brew bash 5.3 was installed via the printed hint but no rc edit followed; `/workday-complete`'s orphan-branch-sweep then hit `coordinator-safe-commit`'s `BASH_VERSINFO<4` fail-loud guard because login PATH still resolved `/bin/bash` (3.2).

**Fix shape.** Detect → **offer** (three nested `default-with-warning` prompts: brew presence, `brew install bash`, append shellenv block to `~/.zprofile`) → **act** (execute on accept) → **marker-guard for idempotency** (sentinel `# coordinator-install: brew shellenv (DR-148)` so re-runs are silent no-ops — the `DR-148` inside that sentinel is frozen historical numbering already written into users' rc files and must never be renumbered; the live record is `docs/decisions/DR-166-require-bash4-on-macos.md`) → **tell user to restart shell** (running Claude Code session inherits the stale PATH; new shell or `source <rc>` is mandatory).

**Generalizable rule.** Detect-and-print remediation is install-surface-incomplete when the print recipient is a user-already-running-the-installer: they came to be installed, not to read text. The pattern is detect → offer → act → idempotency-guard → restart-notice when the change requires shell reload.

See `docs/decisions/DR-166-require-bash4-on-macos.md` for the underlying policy.

**Extension — the login-shell-orphan dimension.** A related incident revealed a new failure mode: an operator `chsh`'d to brew bash believing `docs/decisions/DR-166-require-bash4-on-macos.md` required it. It does not — that decision's requirement is on the **PATH-resolved interpreter** (`bash <script>` resolution), not on login-shell identity. Switching the login shell to brew bash via `chsh` caused `~/.local/bin` to disappear from PATH in fresh terminals: macOS bash reads `~/.bash_profile` on login, not the zsh rc files (`~/.zshrc`, `~/.zprofile`) where the operator's PATH additions lived. An absent or minimal `~/.bash_profile` silently strands those entries.

**Coordinator's posture:** coordinator never requires or suggests `chsh`. When it detects a bash login shell with an absent or minimal `~/.bash_profile`, it offers to reconstruct `~/.bash_profile` — consent-gated, backed up before write, and reverted via `--restore` if needed (the same discipline all `normalize-env` mutations follow). The installer also SUPPORTS operators who are already on a bash login shell and whose environment is intact. What it never does is proactively offer to change login shell identity.

**Worked example: PATH-snapshot reconstruction (snapshot-not-enumerate).** The reconstruction must be portable across operators whose PATH additions vary — language managers, local bin directories, and project-specific entries differ per machine. The correct approach snapshots the prior shell's authoritative PATH rather than enumerating a fixed list of expected entries:

```bash
# Snapshot the prior shell's PATH by invoking it as a login shell:
PRIOR_PATH=$(zsh -l -c 'echo "$PATH"' 2>/dev/null)

# Reconstruct ~/.bash_profile — emit brew shellenv first, then add every
# entry from PRIOR_PATH that is not already present in the resulting PATH,
# then add a guarded source for interactive settings:
eval "$(brew shellenv)"
while IFS=: read -r entry; do
  case ":$PATH:" in
    *":$entry:"*) ;;   # already present; skip
    *) echo "export PATH=\"$entry:\$PATH\"" >> ~/.bash_profile ;;  # PREPEND: entry first
  esac
done <<< "$(tr ':' '\n' <<< "$PRIOR_PATH")"
# guarded source — absent or unreadable ~/.bashrc is silent; use . not source (POSIX)
echo '[ -f ~/.bashrc ] && [ -r ~/.bashrc ] && . ~/.bashrc' >> ~/.bash_profile
# Note: example is simplified. The shipped normalize_env.py implementation adds
# sentinel guards (_NE_START_SENTINEL/_NE_END_SENTINEL) and uses an atomic
# write (mktemp + mv) instead of appending directly to ~/.bash_profile.
```
<!-- Review: code-reviewer F7 — fixed three divergences from the real C2 impl:
     (1) export PATH was APPEND form ($PATH:$entry); changed to PREPEND ($entry:$PATH).
     (2) used 'source ~/.bashrc'; changed to '. ~/.bashrc' (POSIX; matches shipped code).
     (3) missing '[ -r ~/.bashrc ]' guard; added to match normalize_env.py's _ne_build_managed_block.
     Added simplification note so readers know the example omits sentinel/atomic-write. -->

**The snapshot-not-enumerate principle.** The anti-pattern is enumerating a fixed list of expected PATH directories. Enumerations diverge per machine, miss operator-specific entries, and may include paths absent on other operators' machines. Snapshotting the prior shell's own PATH resolution is the portable form: the prior shell's `$PATH` is the ground truth, not a guess. The same principle generalises to any PATH reconstruction task where the target state is operator-specific.

Cross-reference: `docs/decisions/DR-166-require-bash4-on-macos.md § Amendment 2026-06-25` for the policy ruling; `docs/wiki/cross-platform-shell-portability.md § PATH vs login shell` for the interpreter-identity summary.

## De-LFS at tip is incomplete — the same workstream must run history purge + force-push + backup tags

**A de-LFS commit at the branch tip is necessary but not sufficient: the LFS upload cost persists in repo history until `git filter-repo` removes the pointer blobs, `git lfs prune` clears the LFS cache, and the purged history is force-pushed with backup tags created first.**

Removing LFS tracking in a tip commit stops new uploads but leaves all historical LFS pointer objects (and the corresponding LFS server blobs) intact. Every clone that fetches a full history continues paying the LFS download cost; bandwidth bills continue accruing against the LFS storage. The same-workstream obligation:

1. Create a backup tag before any history rewrite (`git tag pre-lfs-purge-<YYYYMMDD>`).
2. Run `git filter-repo --strip-blobs-bigger-than 0 --path-glob '<pattern>'` (or equivalent) to excise the historical LFS pointer blobs from every ancestor commit.
3. Run `git lfs prune --verify-remote` to clear the LFS object cache.
4. Force-push the rewritten branch — requires PM authorization and `--force-with-lease` against the backup tag.

Defer any of these four steps to a follow-up and the LFS cost persists indefinitely. (Source: coordinator-improvement-queue L117.)

## Git-LFS materialization is a silent install-surface gap — verify+enable+pull+assert-no-pointers at step zero

<!-- anchor: git-lfs-materialization — cross-refs use "§ Git-LFS materialization" -->

*claude-central (DoE), discharging the cross-repo `ask` memo `cross-repo/inbox/2026-06-24-git-lfs-step-zero-requirement.md` from the project-rag-ue-addon EM.*

**A repo that LFS-tracks binary assets (`*.png`, `*.uasset`, `*.umap`, `*.fbx`, `*.psd`, …) clones into broken silent-pointer state when git-lfs was never verified/enabled at install — and the failure surfaces late, at first asset *open*, not at clone.** A plain `git clone` with git-lfs absent **succeeds and looks fine**, but every LFS-tracked file is a ~130-byte text pointer, not real content. Nothing errors until something tries to load one (an extension manifest referencing unmaterialized icons; a cooked `.uasset`; an embedded `.pdf`). This is the install-surface-completeness rule (§ Rule) applied to LFS content: the clone path silently fails to reproduce the binary state the work depends on.

**Orphaned-object subcase — permanent, unrecoverable loss.** If a pointer was committed on a machine *before* git-lfs was enabled there, the binary blob was **never uploaded to LFS remote storage** — the pointer exists in history but the object does not. `git lfs pull` cannot recover it; the asset is permanently lost. An orphan must therefore be **surfaced loud, never swallowed** — a green "pull succeeded" over a missing object is the worst outcome (it reads as materialized when the content is gone).

### Step-zero materialization shape (for repos that LFS-track content)

The earliest prerequisite block, before any phase that touches LFS-tracked content, must:

1. **Verify** `git lfs version`; if absent, **fail loud** with platform remediation (`brew install git-lfs` / `winget install GitHub.GitLFS` / `apt install git-lfs`). Do not silently continue.
2. **Enable** `git lfs install` — **plain, not `--force`**, so it coexists with existing pre-push/post-commit hooks (idempotent global config write).
3. **Materialize + assert** `git lfs pull`, then scan `git lfs ls-files` for any remaining `-` (pointer) row and **fail loud listing them** — a remaining pointer after pull is either a fetch failure or an orphaned object; both must surface, not swallow.
4. **Optional doctor probe** that goes RED on unmaterialized pointers (the consumer's EM-substitute per § doctor-as-EM-substitute).

### Altitude split — operator-setup probe (advisory) vs. content-repo materialization-assert (hard)

These are two *different* responsibilities at two *different* altitudes; do not collapse them. The governing principle: **the coordinator proactively covers the harmless, universal part (install + enable) so LFS-tracking peers are unblocked before they get there — git-lfs is cheap and harmless to install even for operators who never clone an LFS repo, so cover it upstream rather than letting a downstream peer discover broken assets.**

- **Coordinator-install altitude — proactively install + enable, advisory verify.** The coordinator install chain **installs git-lfs and runs `git lfs install` by default** at TWO surfaces. (1) `scripts/first-run` (naked-Python trampoline over `coordinator_core.install.first_run`, superseding the retired `scripts/first-run.sh` bash oracle on the bash-to-naked-Python engine migration) on the canonical fresh-clone bootstrap, as two distinct stages: the main brew-install block (`brew install git-lfs`, gated on git-lfs-absent) installs the *binary*, and `run_post_toolchain` Step 5 runs `git lfs install` (the *global config write*) — BOTH stages gated by the same explicit `--no-git-lfs` opt-out. (2) `/coordinator:install` Phase 1a.3 (idempotent `git lfs install`, act-not-gate) for operators who reach the install surface without traversing first-run (coordinator already present on an existing machine); this surface carries **no** `--no-git-lfs` opt-out — none is needed, the action is idempotent-and-harmless and degrades to an advisory line when the binary is absent. The two-surface coverage closes the first-run-only reachability gap. This is the "cover it before they get there" move — an operator who later clones an LFS-backed peer (project-rag-ue-addon, example-game-repo) finds git-lfs already present and enabled (`git lfs install` writes global config, so it covers all subsequent clones on the machine). The *verification probe* (`scripts/lib/prereq_probe.sh _co_probe_git_lfs`) checks the operator's git-lfs binary + `filter.lfs.clean` config and emits **advisory WARN**, never a hard exit-code gate — correct and deliberate (PM-decided, AC10): a hard gate would regress LFS-free installs (§ Post-Consumer Gates Must Be Advisory WARN). Proactive-install + advisory-gate compose cleanly: we set git-lfs up *for* the operator (harmless), and we don't hard-fail if it is somehow still absent. The meta-repo (`~/.claude`) itself LFS-tracks **nothing** (`git lfs ls-files` empty), so a *materialization*-assert here is vacuous by construction — only the install+enable is meaningful at this altitude.
- **Content-repo step-zero altitude — materialization-assert — HARD, repo-specific.** A repo that *does* LFS-track content (project-rag-ue-addon; example-game-repo with `*.uasset`/`*.umap`) owns the **hard, fail-loud** step-zero materialization-assert (steps 3 above: `git lfs pull` + `git lfs ls-files` pointer-scan) in its own install surface — silent broken assets are a clean break for that repo's consumers. This part is inherently repo-specific (it asserts against *that repo's* LFS content) and cannot be done generically upstream, so it stays with the LFS-content repo (§ emitter-not-emitted-copy). Coordinator covers verify+install+enable proactively; the content repo adds the pull+assert that only it can express.

**Not the engine corpus.** The project-rag-ue-addon engine corpus ships via GitHub Releases (`gh release download`), not LFS — this rule is specifically about git-tracked LFS assets, not release artifacts.

Composes with § De-LFS at tip is incomplete (the *removal* side of the same LFS surface — this is the *materialization* side), § Post-Consumer Gates Must Be Advisory WARN (why the operator-setup probe is advisory), and the FB-2 functional-not-existence probe rule (a `git lfs version` existence check is necessary but the `ls-files` pointer-scan is the functional materialization probe).

## Onboarding leg/restart prose must direct the durable session to ~/.claude (cwd-coupled)

**Onboarding install legs and restart-after-bootstrap instructions must explicitly direct the new Claude Code session to open with `~/.claude` as cwd — `/workday-start` and `/pickup` are cwd-scoped and silently resolve handoffs against the wrong folder when opened from a sibling repo.**

`/workday-start` and `/pickup` resolve handoff files relative to the current working directory's `state/handoffs/`. A bootstrap leg that seeds batons into the install-baton rendezvous (a machine-shared, per-machine folder at `$(coordinator-settings-home)/state/handoffs/` — distinct from claude-klabauter-central; see `state-placement-law.md`) and then instructs the operator to "open a new Claude Code session" without naming `~/.claude` as the starting directory causes the durable session to open wherever Claude Code defaults — typically the last-active project repo. The commands appear to work (no error) but operate against an empty or wrong `state/handoffs/` folder, silently skipping every seeded baton.

How to apply: any INSTALL.md, Phase-N restart-note, or handoff-prose that concludes a bootstrap leg must include the explicit instruction `Open Claude Code with ~/.claude as the working directory` (or equivalent `cd ~/.claude` CLI invocation). Pair with `spinoff-handoffs.md § Install-chain heavy installs` which documents the baton-seeding side. (Source: coordinator-improvement-queue L124.)

## Cold-terminal launch shim needs a registry-projected bootstrap pointer, not a bare machine-local call

*DoE-claude.*

**The coordinator plugin `bin/` dirs (`machine-local` etc.) are injected onto PATH by Claude Code at plugin-load — NOT by the shell profile.** A *cold* terminal (fresh Terminal.app opened outside a coordinator session) therefore has **zero** coordinator bins on PATH. A launch shim that calls bare `machine-local get repos.doe_claude` fails there, and any downstream bootstrap (e.g. Claude-klabauter `coordinator/bin/gen-settings-hooks.py`) dies with it.

The trap deepens post-cutover: `machine-local` **itself lives in the DoE clone**, so it cannot be the resolver that *finds* the DoE clone — a chicken-and-egg. The registry can't bootstrap the path to the registry.

**Correct design.** The installer **projects** the registry's `repos.doe_claude` into a stable, cold-readable settings-home artifact — a pointer file (`<settings-home>/machine-local/.doe-root`, with a read-only legacy `~/.claude/.doe-root` fallback rung) or a value baked into the shim — that the `claude()` shell function reads via `REPO_DOE_CLAUDE`. The registry stays the single source of truth; the projection is a **bootstrap cache** the cold terminal can read before any plugin loads. Setting `repos.doe_claude`, registering coordinator, and generating the shim from the registry is a **P0 install-surface-completeness requirement** for the maximalist install (its exact inverse is the coordinator-uninstall path). Hand-baking a literal path into one machine's `~/.bashrc` to unblock is a this-machine stopgap, not the install solution. Composes with § Publish-Target Parity (`repos.*` resolution + bootstrap precondition) and § Install-surface bugs must be fixed at the emitter (the projection is emitted by the installer, never hand-edited on one box).

## Installed-tree verification must use per-file content/blob-set membership, not a whole-tree digest

**A whole-tree digest comparison between the installed tree and the VCS source tree is unsound when the installer applies post-copy mutations (banner injection, variable substitution, exec-bit setting, line-ending normalization) — use per-file content comparison or blob-set membership instead.**

A single `sha256sum -r <tree>` or `find | sort | xargs sha256sum` over the installed directory will differ from the equivalent over the VCS checkout the moment any file was legitimately mutated post-copy — the digest mismatch tells you nothing about which files drifted vs. which files were correctly transformed. The comparison conflates install-correct mutations with genuine drift. Per-file approach: for each installed file, check whether its content (or its content minus the injected banner/BOM) matches the expected VCS blob-set member. Files that the installer is documented to mutate get a mutation-aware comparator; all other files get an exact match. A mismatch in the exact-match set is drift; a mismatch in the mutation-aware set against the wrong base is a bug.

How to apply: drift-audit scripts (e.g. `check-plugin-drift.py`) should compare files individually, stripping documented post-copy mutations before diffing, rather than hashing directory trees. Composes with § Committed publish-mirror of executable scripts (freshness-compare modulo banner). (Source: coordinator-improvement-queue L154.)

## A new process-supervisor requires auditing the OS boot-service for competing port ownership

**When a new process-supervisor lands, audit the OS boot-service (launchd plist / systemd unit / Windows service) to ensure it does not still spawn a competing owner of the same port — a surviving boot-service entry causes a crash-loop on every machine restart; the boot-service must exec the supervisor as single owner (lock-guarded) with crash-only restart so a failure surfaces rather than silently cycling.**

Installing a new supervisor (a daemon manager, a socket-owning proxy, a port-registering MCP server) is only complete when every OS-level autostart path for the SAME port is audited and either removed or subordinated. A stale `com.apple.launchd.*` plist, `~/.config/systemd/user/*.service`, or Windows `HKCU\...\Run` entry from a prior incarnation of the same service will race the new supervisor for the port on boot, causing the loser to crash-loop indefinitely — often with no user-visible error because both start, one wins the port, and the other loops silently in the background.

How to apply: after installing a new port-owning supervisor, `launchctl list | grep <port-token>` (macOS), `systemctl --user list-units | grep <name>` (Linux), or `Get-ScheduledTask | Where Name -like <name>` (Windows) and confirm only the new entry exists. The supervisor itself must self-register via a lock file (PID lock or socket lock) so a second instance detects the occupying owner and exits immediately rather than spinning. Crash-only restart (no exponential-backoff retry) ensures a startup failure surfaces in logs on the first attempt rather than being masked by a retry loop. Composes with § OS-level autostart registration is unsolicited by default (opt-in gate). (Source: coordinator-improvement-queue L155.)
