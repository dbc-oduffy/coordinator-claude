---
title: Coordinator Doctor
created: 2026-05-20
author: claude-central-em
status: current
---

<!-- spec-backlink: archive/specs/2026-05/2026-05-20-coordinator-doctor-wiki.md § Chunk 1 -->

# Coordinator Doctor

**Purpose.** This wiki is the operator-facing health-verification surface for the two pieces of coordinator substrate that downstream plugins depend on: the `~/.claude/machine-local/` registry and the `coordinator_whoami` package. It enumerates twenty runnable probes (P-1 through P-19, plus P-6s; P-7a is EM-native and absent from the manifest), defines severity vocabulary for probe results, and establishes the citation contract that downstream plugin doctors (example-game-repo, project-rag, project-rag-ue-addon) MUST follow when probing coordinator-owned substrate.
<!-- Review: code-reviewer slice-B F2 — updated count from eleven/P-1..P-11 to twenty/P-1..P-19+P-6s; verified against doctor-probes.toml (20 entries) -->

**What this wiki is not.** It is not a slash skill — a `/coordinator:doctor` command would be bloat for a non-interactive verification surface. It is not a runtime validator or a programmatic API. It does not duplicate the substrate doctrines: for `machine-local/` resolution order, see [`machine-local-registry.md`](machine-local-registry.md); for the whoami envelope schema, see [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md). That "wiki, not a skill" call is this repo applying [`doctor-proportionality.md`](doctor-proportionality.md) to itself — the citable rule for *whether* a component earns a doctor skill vs a wiki vs just fail-loud scripts.

**Cadence path — sentinel-writer primitive.** The wiki's "no slash skill" decision stands. To close the gap where coordinator-claude's substrate health was invisible to the daily addon-health sweep, the non-skill primitive `coordinator-doctor-sentinel.sh` fires all probes in `doctor-probes.toml` on cadence (from `/workday-start` Step 1.10, ahead of `scan-addon-health.sh`) and writes `~/.claude/plugins/coordinator-claude/data/doctor-last-run.json` in the sentinel schema documented in [`addon-health-sentinel.md`](addon-health-sentinel.md).
<!-- Review: code-reviewer slice-B F3 — replaced "P-1..P-12" with resilient form; fires all 20 manifest probes --> Operators retain the inline-invocation path of §3 below; the script is the same probes, batched and serialized. See §7 for the script's contract.

**Adding a probe?** A new probe is a P-N entry in §3 of *this wiki* + a firing wire-up in `coordinator-doctor-sentinel.sh` — there is no `coordinator/commands/doctor.md` to edit (the "no slash skill" decision above). Dispatch briefs for probe-wiring or coordinator-substrate audits should name this wiki path explicitly: an agent told to "check `coordinator/commands/` for a doctor" finds nothing and mis-wires the probe into a downstream project-doctor instead. Project-doctors are runtime consumers that cite P-N back to this authority surface.

---

> **Found a broken probe, or a fix that isn't in here? Patch it and send it back.** This substrate leans on agents because a script-only install was whack-a-mole across machines — and your machine is where the remaining rough edges surface. Hotwire whatever you need to get healthy, then send the fix upstream: open a PR, file an issue, or paste a rough note. Don't polish it — the *what / how / why* of your fix is what we generalize from, and it beats a one-line bug report. The agent diagnosing this with you can draft the writeup. See [CONTRIBUTING.md](https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md).

---

## Audience Routing

Three readers land here for different reasons:

**(a) Operator with a config failure.** You hit a "machine-local key not found" or "coordinator_whoami import error" and want a one-line answer. Go directly to the probe catalog §3 — run P-1 through P-4 for registry failures, P-5 through P-7 for whoami failures. For orientation health specifically, P-6s is the probe. If probes surface a missing substrate, see §6 (Bootstrap from cold-start).

**(b) Agent invoked from a downstream doctor.** You are running a example-game-repo or project-rag doctor and need to verify coordinator substrate as a prerequisite. Read §5 (Citation contract) first — it defines whether you should delegate to this wiki's probe or augment with your own. Do not reinvent the probe; cite P-N and surface the verdict.

**(c) Author of a new downstream doctor.** You are writing a plugin doctor that touches machine-local keys or coordinator_whoami introspection. Read §5 in full before authoring. The citation contract is binding — two shapes are defined, a third path is explicitly closed.

---

## Probe Catalog

Each probe has a single-line invocation. All `machine-local` invocations use the `machine-local` CLI from the coordinator install. All `python -m coordinator_whoami.*` invocations assume `coordinator_whoami` is importable from the **coordinator venv** — NOT the bare system `python3`. After the venv-pin change (2026-06-20), `coordinator_whoami` lives in `~/.claude/.coordinator-venv/` and is reachable only via the interpreter pinned at `coordinator.python` in the machine-local registry (or via `COORDINATOR_PYTHON` env override). Downstream doctors probing `coordinator_whoami` MUST resolve the interpreter via `COORDINATOR_PYTHON` env → `machine-local get coordinator.python` — or by sourcing `lib/resolve-python.sh` — before invoking `python -m coordinator_whoami.*`. Bare `python3` will produce an ImportError on any machine where the system interpreter does not have `coordinator_whoami` installed (which is the expected state after the venv migration). P-5 verifies importability; P-5 itself must be invoked with the resolved interpreter, not bare `python3`.

Severity values are from the vocabulary defined in §4.

**Portability note (Windows / Git Bash).** `python3` is the canonical Linux/macOS interpreter name. On Windows + Git Bash, the Python Launcher is the canonical entry; substitute `py -3` for `python3` in every command below. Operators on Windows may want to alias once: `alias python3='py -3'`. The `python3` references in the table are otherwise portable.

**PATH and bare-invocation note (macOS / Linux).** `~/.claude/bin` is NOT on PATH on macOS/Linux — the Claude Code harness injects only `plugins/*/bin` (cross-platform), while `~/.claude/bin` is written to PATH only by `install-substrate.sh` Step 3b on Windows. This is exactly why probes such as P-4 (`machine-local`) and P-10 that invoke `~/.claude/bin` tools use absolute paths (e.g. `~/.claude/bin/machine-local`) rather than bare names. **Absolute-path resolution for `~/.claude/bin` tools is the correct robust pattern** — bare invocation of those tools from probe commands will fail on macOS/Linux with `command not found`. Tools under `plugins/*/bin` (e.g. `fan-out-dispatch.sh`, `coordinator-safe-commit`) DO resolve by bare name on all platforms.

| ID | What it checks | Command | Pass interpretation | Fail interpretation | Severity if fail | Remediation |
|---|---|---|---|---|---|---|
| **P-1** | `<settings-home>/machine-local/` directory exists (relocated from `~/.claude/machine-local/`; compat symlink retained there during the transition window) | `test -d "$(machine-local dir)" && echo healthy \|\| echo error` | `healthy` | Directory absent — substrate was never bootstrapped | `error` | Run `/coordinator:install` Phase 3 (§6); `<settings-home>` = `$(coordinator-settings-home)` |
| **P-2** | `registry.toml` parses and declares `schema = 1` | `python3 -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('~/.claude/machine-local/registry.toml').expanduser().read_text()); assert d.get('schema')==1"` | Exits 0 | File missing, unparseable TOML, or wrong schema version | `error` | Re-run Phase 3; check for manual edits that broke TOML structure |
| **P-3** | At least one key under `repos.*` is populated in `registry.local.toml` | `machine-local keys \| grep -q '^repos\.' && echo healthy \|\| echo degraded` | `healthy` — at least one repo path declared | `degraded` — fresh install or operator never seeded machine-specific paths | `degraded` | Run `machine-local set repos.<name> <path>` for each sibling repo (see [`machine-local-registry.md`](machine-local-registry.md) §9 for the `.local.toml` discipline) |
| **P-4** | `machine-local` CLI shell-out works (smoke test) | `machine-local keys >/dev/null && echo healthy \|\| echo error` | `healthy` — CLI runs and registry is parseable | CLI not on PATH, `bin/` not linked, or registry.toml unparseable — setup incomplete | `error` | <!-- review: code-reviewer slice2-F2 — old text "verify ~/.claude/bin/ is on PATH" contradicts macOS PATH note; bare-name reach on POSIX comes from the coordinator/bin forwarder, not a PATH entry for ~/.claude/bin/ --> Run Phase 3; verify the coordinator/bin forwarder for `machine-local` is present (`plugins/coordinator/bin/machine-local`) — bare-name reach on POSIX comes from the forwarder in `plugins/coordinator/bin/`, NOT a PATH entry for `~/.claude/bin/`; verify `~/.claude/machine-local/registry.toml` parses |
| **P-5** | `coordinator_whoami` package is importable | `$(machine-local get coordinator.python) -c "import coordinator_whoami; print('healthy')"` | `healthy` | ImportError — coordinator venv missing or pin stale | `error` | Run `bin/ensure-coordinator-venv.sh` (or `/coordinator:install` Phase 3 Step 6) — rebuilds the coordinator venv at `<settings-home>/.coordinator-venv/` idempotently and re-pins `coordinator.python`; `<settings-home>` = `$(coordinator-settings-home)` (relocated from `~/.claude/.coordinator-venv/` by durable-substrate-to-settings-home plan). The bare `python3` invocation is no longer correct; `coordinator_whoami` is importable only from the coordinator venv. |
| **P-6** | Live `coordinator_whoami.project_rag` returns a v1-conformant envelope (**plugin-binding-health probe** for project-rag — NOT orientation health; see P-6s) | `$(machine-local get coordinator.python) -m coordinator_whoami.project_rag --human \| head -5` | Output contains `contract_version: 1` | JSON parse error, missing required fields, or non-zero exit | `error` | Check P-5 first (coordinator venv); then inspect `~/.claude/machine-local/registry.toml` for missing keys the probe requires; see [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) §Validation. Re-run `bin/ensure-coordinator-venv.sh` or `/coordinator:install` Phase 3 Step 6 if venv is suspect. |
| **P-6s** | Live `coordinator_whoami.session` returns a v1-conformant envelope (**orientation-health probe** — answers "is this session oriented?"; no MCP dependency; always `source_kind: "live"`; `binding.kind` is `bound`/`unbound` only) | `$(machine-local get coordinator.python) -m coordinator_whoami.session --human \| head -5` | Output contains `contract_version: 1` and `plugin_name: coordinator-session` | JSON parse error, missing required fields, non-zero exit, or `plugin_name` is not `coordinator-session` | `error` | Check P-5 first (coordinator venv); then verify `coordinator_whoami.session` subpackage is present (ships with `coordinator_whoami` package); re-run `bin/ensure-coordinator-venv.sh` or `/coordinator:install` Phase 3 Step 6 to rebuild the venv if absent. |
| **P-7** | `~/.claude.json` mcpServers entries for installed plugins are present and well-formed (**configuration-presence probe — not binding health**) | `python3 -c "import json,pathlib; cfg=json.loads(pathlib.Path('~/.claude.json').read_text()); assert 'mcpServers' in cfg and len(cfg['mcpServers'])>0; print('healthy')"` | `healthy` — config entry exists and is parseable JSON | Config entry absent, malformed JSON, or `mcpServers` key missing | `degraded` | Re-run plugin install to write the mcpServers entry; verify `~/.claude.json` is writable. **For live binding state, see P-6** — P-7 confirms the config exists, not that the binding is active. |
| **P-7a** | `~/.claude.json` mcpServers entries are reachable (reachability-augmentation of P-7 — configuration presence is P-7's job; this probe adds transport-layer checks) | EM-native: read the deferred-tools registry at workstream-start (`/workday-start` Step 1.10.5) to detect tools that appear in `mcpServers` config but are absent from the live session tool surface. A standalone shell probe (`bin/probe-mcp-registration.sh`) is planned but not yet implemented — the EM-native Step 1.10.5 probe covers this gap. | All servers emit `registered presumed` or tools appear in session surface | Any server appears in config but absent from live tool surface | `degraded` (advisory; never gating) | Check the named server's transport: for stdio servers, verify command exists on PATH; for HTTP servers, verify the server process is running. Run `/workday-start` to trigger Step 1.10.5 visibility. |
| **P-8** | Sentinel presence: at least one `doctor-last-run.json` exists across installed plugins | `ls ~/.claude/plugins/*/data/doctor-last-run.json 2>/dev/null \| head -1 \| grep -q . && echo healthy \|\| echo degraded` | `healthy` — at least one doctor has been run | `degraded` — no plugin doctor has ever been run on this machine | `degraded` | Run each installed plugin's doctor once to bootstrap the sentinel; see [`addon-health-sentinel.md`](addon-health-sentinel.md) for the sentinel schema |
| **P-9** | UE override paths resolve against registry-declared roots | `bash "$(coordinator-settings-home)/bin/verify-ue-overrides.sh"` (compat: also at `~/.claude/bin/verify-ue-overrides.sh` during the transition window) | Exits 0 with no remediation output | Non-zero exit or remediation message emitted | `degraded` or `error` (per script output) | Follow the remediation hint from the script, which will point to the relevant machine-local key (typically `repos.example_game_workbench_repo`); re-run after setting the key |
| **P-10** | `claude-home` path resolver smoke (added 2026-05-21 for resolver-family symmetry with P-4) | `"$(coordinator-settings-home)/bin/claude-home" plugins` (compat: also at `~/.claude/bin/claude-home` during the transition window) | Prints an absolute path to an existing directory | Command missing, prints empty, or path doesn't resolve to a directory | `error` | Re-run `/coordinator:install` Phase 3; verify `<settings-home>/bin/` contains the `claude-home` script + `_claude_home.py` (reached via the coordinator/bin forwarder, not PATH directly); `<settings-home>` = `$(coordinator-settings-home)` |
| **P-11** | `coordinator/templates/setup/` matches live `~/.claude/setup/` (no drift) | `bash ~/.claude/plugins/coordinator/bin/verify-templates-setup-sync.sh >/dev/null && echo healthy \|\| echo degraded` | `healthy` — templates and live install are byte-identical | `degraded` — operator customized `~/.claude/setup/publish.sh` (or sibling) AND template ships a different version; bugfixes in the template will not reach this operator until manually re-synced | `degraded` | Inspect drift with `bash ~/.claude/plugins/coordinator/bin/verify-templates-setup-sync.sh` (no flags — inspect-only, there is no `--fix`). Recovery is manual and template-as-authoritative: `cp coordinator/templates/setup/<file> ~/.claude/setup/<file>` for each drifted file. |
| **P-12** | Canonical document structure present — eager dirs from `canonical-structure.yaml` exist at `~/.claude` and their `README.md` files are intact | `bash ~/.claude/plugins/coordinator/bin/scaffold-canonical-structure.sh --root ~/.claude --dry-run \| grep -q "skip (exists)" && echo healthy \|\| echo degraded` | `healthy` — all eager directories and their READMEs are present | `degraded` — one or more eager dirs (e.g. `cross-repo/`) or READMEs are missing; the scaffold has not been run or a directory was manually deleted | `degraded` | Run `bash ~/.claude/plugins/coordinator/bin/scaffold-canonical-structure.sh --root ~/.claude` to restore the canonical structure; or re-run `/coordinator:install` (Phase 3 Step 7). |
| **P-13** | Onboarding currency — per-repo `coordinator-currency.yaml` stamp matches current `COORDINATOR_SCHEMA_VERSION`; legacy repos (pre-stamp) surface as honest AMBER rather than silent pass | `bash ~/.claude/plugins/coordinator/bin/probe-onboarding-currency.sh` | `current` — stamp present and matches current schema version | One of: `drift(stale:…)` (stamp present but older than current), `unstamped(legacy)` (repo predates currency feature), `inconclusive(…)` (probe could not run — schema constant missing or stamp unparseable) | `degraded` | For `drift`: re-run `/repo-setup` to refresh the stamp. For `unstamped(legacy)`: run `/repo-setup` once to create the stamp. For `inconclusive`: verify `coordinator-schema-version` file is present in the coordinator plugin root (`~/.claude/plugins/coordinator/coordinator-schema-version`). `source_is_live` repos (the coordinator source itself) are expected-unstamped — not a warning. |
| **P-14** | Bare-name resolution of `~/.claude/bin` resolvers — `machine-local` and `claude-home` are reachable by bare name on PATH (regression net for macOS `~/.claude/bin`-not-on-PATH bug; P-4/P-10 mask this because they resolve absolute-path-first) | `command -v machine-local && command -v claude-home && echo healthy \|\| echo error` | `healthy` — both bare names resolve on PATH via coordinator/bin forwarders | Either bare name missing from PATH — coordinator/bin forwarder absent; C1 forwarders not installed or PATH misconfigured | `error` | Re-run `/coordinator:install` Phase 3 to install the coordinator/bin forwarders; on macOS `~/.claude/bin` is NOT on PATH — bare-name resolution requires the Phase 3 forwarder installed under `plugins/coordinator/bin/` |
| **P-15** | System-prerequisite gate — verifies hard-tier machine prerequisites (git, Python 3.11+, gh CLI, Node.js) are installed and functional. Reuses `scripts/lib/prereq_probe.sh` (`_co_prereq_probe_all`) as SSOT — the same check the install Step Zero gate runs. Advisory-tier absences (uv, pwsh, ue, git_lfs, longpaths) do NOT drive verdict per doctor-probe-design.md § "AMBER on Optional Absence Is Bad Form". | `bash scripts/lib/prereq_probe.sh` (runs all 10 NDJSON probes; sentinel selects hard-severity rows only) | All hard prerequisites pass; advisory-only warnings surface as install-improvement hints but do not change the verdict | One or more hard prerequisites absent or broken — `status: fail, severity: hard` in the NDJSON row | `error` | Install the missing hard prerequisite(s): git (`brew install git` / `apt-get install git` / `winget install Git.Git`), Python 3.11+ (https://python.org/downloads), GitHub CLI (`brew install gh` / `winget install GitHub.cli`), Node.js LTS (`brew install node` / `winget install OpenJS.NodeJS.LTS`) |
| **P-16** | Hardware capacity SSOT — verifies that `hardware.cores` and `hardware.ram_gb` have been seeded into `machine-local` by the install-substrate hardware-audit step. Absence means downstream capacity-budget tools (project-rag worker-cap, build batch-sizers) fall back to conservative or wrong values; the coordinator's own substrate is unaffected. Reads the keys via `machine-local get` (cheap: two key lookups, no subprocess spawn). Spec backlink: `docs/plans/2026-06-23-setup-time-substrate-completeness.md` AC9. | `machine-local get hardware.cores >/dev/null && machine-local get hardware.ram_gb >/dev/null && echo healthy \|\| echo degraded` | `healthy` — both keys are present and resolve | One or both keys absent — hardware-audit step did not run or the machine-local concern file is missing | `degraded` | `hardware.cores` / `hardware.ram_gb` absent from machine-local. Remediation depends on your install path: **(1) coordinator:install users** — re-run `coordinator:install` Phase 3 (the hardware-audit step seeds these values via `lib/detect-hardware.sh`); **(2) OSS setup/install.sh users** — re-run `setup/install.sh` (the `--setup-only` path seeds `hardware.*` via the same detector). After re-running, verify with: `machine-local get hardware.cores`. |
| **P-17** | macOS bash login-shell orphan check — verifies that the bash login shell has `~/.local/bin` in its PATH and that `claude` resolves. Reuses `_co_probe_shell_login_env` from `scripts/lib/prereq_probe.sh` (FB-2 functional probe: spawns the actual login shell, not just a file-presence check). Non-macOS machines and non-bash login shells return pass immediately. Not in triage pass: spawning a login shell sources arbitrary user rc files (nvm/pyenv/conda-init) with latency and side effects — surfaces under `--full` / `--cluster machine-local` / `--symptom shell-env`. | `bash -c 'source scripts/lib/prereq_probe.sh && _co_probe_shell_login_env'` | Non-macOS, non-bash login shell, or bash with `~/.local/bin` in login PATH and `claude` resolving | bash login shell has orphaned `~/.local/bin` (absent from login PATH) or `claude` does not resolve — Claude Code `claude` dispatch will fail | `error` | bash login shell orphaned `~/.local/bin` — run `coordinator:install` or `normalize-env.sh` to reconstruct `~/.bash_profile` |
| **P-18** | Install singularity — exactly one canonical coordinator tree reachable, consistent marketplace registration across `settings.json` / `settings.local.json` / `known_marketplaces.json`, and no doubled `.claude/.claude` venv pin. Two shapes are recognized: **pre-cutover** (`~/.claude` shape) — canonical tree = `~/.claude/plugins/coordinator-claude`; **maximalist post-W4.2 shape** — canonical tree = DoE clone resolved via `plugin.mirrors.coordinator-claude.live_path` in `registry.local.toml` (delivered live via `--plugin-dir`; `~/.claude/plugins/coordinator-claude` absent). In both cases exactly one tree is expected; a genuine second tree (stray clone, stale worktree) is always an accidental split that silently loads a stale coordinator copy (the 2026-06-26 three-tree failure). Exit-0 INFO names the resolved canonical tree path. Exempts a single explicitly-exported `COORDINATOR_CLONE` / `COORDINATOR_ROOT` dev-loop override (`.git`-backed); `CLAUDE_PLUGIN_ROOT` is NOT an exemption signal (harness-injected). | **Pre-cutover shape:** `bash ~/.claude/plugins/coordinator/lib/check-install-singularity.sh` — this path exists in the flat install. **Maximalist post-W4.2 shape** (`~/.claude/plugins/coordinator-claude` absent): `bash "$(machine-local get repos.doe_claude)/coordinator/lib/check-install-singularity.sh"` — resolves via the machine-local registry. Inside a live Claude Code session with `CLAUDE_PLUGIN_ROOT` set by the harness: `bash "${CLAUDE_PLUGIN_ROOT}/lib/check-install-singularity.sh"`. <!-- Review: code-reviewer F2 — added both invocation forms; pre-cutover path fails on maximalist machines where ~/.claude/plugins/coordinator-claude/ is absent. --> | Exits 0 — single canonical tree confirmed (INFO names the resolved path; post-W4.2: DoE clone; pre-cutover: `~/.claude/plugins/coordinator-claude`) | Non-zero — >1 reachable clone, divergent settings / `known_marketplaces.json` coordinator path, doubled `.claude/.claude` venv pin, or a `.claude`-suffixed `CLAUDE_HOME` | `error` | Remove stray clones/symlinks. **Post-W4.2 maximalist shape:** remove `~/.claude/plugins/coordinator-claude`; ensure `plugin.mirrors.coordinator-claude.live_path` in `registry.local.toml` points to the DoE clone; remove or override the coordinator-claude marketplace entry. **Pre-cutover shape:** align `settings.json` / `settings.local.json` / `known_marketplaces.json` to `~/.claude/plugins/coordinator-claude`. Fix a doubled venv pin via `bin/ensure-coordinator-venv.sh`. Re-run `/coordinator:install`. |

### Probe metadata (generated — manifest SSOT)

The table below is machine-generated from `bin/doctor-probes.toml`. It carries the structured fields the manifest is SSOT for (`cluster`, `weight`, `triage`, `severity_if_fail`). Regenerate with `python3 bin/doctor-catalog-gen.py --write`; validate with `--check`. Do not hand-edit between the markers.

<!-- BEGIN generated-probe-metadata (from bin/doctor-probes.toml — regenerate via bin/doctor-catalog-gen.py; do not hand-edit) -->

| id | cluster | weight | triage | severity_if_fail |
|---|---|---|---|---|
| **P-1** | machine-local | cheap | yes | error |
| **P-2** | machine-local | standard | no | error |
| **P-3** | machine-local | standard | no | degraded |
| **P-4** | machine-local | standard | yes | error |
| **P-5** | whoami | standard | yes | error |
| **P-6** | whoami | standard | no | error |
| **P-6s** | whoami | standard | no | error |
| **P-7** | whoami | standard | no | degraded |
| **P-10** | resolver | standard | yes | error |
| **P-14** | resolver | cheap | no | error |
| **P-8** | structure | cheap | no | degraded |
| **P-11** | structure | standard | no | degraded |
| **P-12** | structure | standard | no | degraded |
| **P-13** | currency | cheap | yes | degraded |
| **P-15** | system-prereq | standard | yes | error |
| **P-16** | machine-local | cheap | no | degraded |
| **P-17** | machine-local | standard | no | error |
| **P-9** | ue-overrides | standard | no | degraded |
| **P-18** | structure | standard | yes | error |
| **P-19** | currency | standard | no | degraded |

<!-- END generated-probe-metadata -->

**Note on P-6s vs P-6 vs P-7.** Three distinct probes, three distinct questions:

- **P-6s** (`coordinator_whoami.session`) — *orientation-health probe*: "is this session oriented?" Answers whether the coordinator session is bound to a repo, the git state is clean, and the orientation cache is fresh. No MCP dependency. This is the probe `/workstream-start` cites.
- **P-6** (`coordinator_whoami.project_rag`) — *plugin-binding-health probe*: "is project-rag's binding healthy?" Answers whether the project-rag daemon is running and its binding is live. Requires project-rag to be installed and running.
- **P-7** — *configuration-presence probe*: verifies the mcpServers entry exists and is well-formed JSON. Does NOT verify the MCP server process is running, the binding resolves, or that tool calls succeed.

Orientation health (P-6s) and plugin-binding health (P-6) answer different questions and must not be collapsed. A session can be oriented (P-6s healthy) while project-rag is down (P-6 failing). Treating P-7 as a binding-health probe is the consumer-leak shape this wiki exists to close.

### Operator-wiring contact points — session adopter coverage

The contract wiki (`cross-plugin-whoami-contract.md` § Operator wiring) requires that any new adopter extends the three operator-wiring contact points or documents why not. For the `coordinator_whoami.session` session adopter:

1. **`/coordinator:install` Phase 3 Step 6 (pip install):** no-op — why not. The `coordinator_whoami.session` subpackage ships inside the same `coordinator_whoami` package the existing step installs. No separate install step is needed; the existing Step 6 covers this adopter automatically.

2. **`/repo-setup` Next-Steps step 4 (branch on `binding.kind`):** stays on project-rag's binding — why not. `/repo-setup`'s concern is "is this project registered as a project-rag source" (project-registration). That is a project-rag binding question. The session adopter answers "am I in a coordinator-onboarded repo / oriented" — a different question that does not replace or overlap the repo-setup branch.

3. **`/workstream-start` Context Load:** **rewired to the session adopter.** Session orientation now invokes `python3 -m coordinator_whoami.session` (P-6s, above) rather than `python3 -m coordinator_whoami.project_rag`. This is the contact point that moved. MCP-plugin whoamis (project-rag, example-game-repo-control) may appear as optional sub-lines but are not the spine. → `skills/workstream-start/SKILL.md`.

**Note on P-7a.** P-7a is the **reachability-augmentation** of P-7, per the THIRD-PATH-CLOSED citation contract defined in §5. P-7 confirms the mcpServers configuration entry is present and well-formed. P-7a confirms the configured server is actually reachable: for stdio servers, that the configured command exists on PATH; for HTTP servers, that the endpoint responds (3s timeout). Neither P-7 nor P-7a proves tool registration is active in a running session — that is `/workday-start` Step 1.10.5's job. Step 1.10.5 is the current implementation of P-7a: it reads the deferred-tools registry from session context and compares it against the `mcpServers` config, writing a sentinel at `~/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json`. A standalone shell probe (`bin/probe-mcp-registration.sh`) is planned but not yet implemented; `probe-cwd-project-rag-relevance.sh` reads the Step 1.10.5 sentinel to determine MCP health for the current cwd.

### Machine info (informational — not a probe)

`python -m coordinator_whoami.machine [--human]` emits the host machine/toolchain inventory — `os`, `arch`, `gpu`, `python`, `uv` — sourced from the shared `coordinator_whoami.host_probes` module. This is the doctor's "what host am I on?" surface (GPU/Python/OS visibility).

It is **informational, not a probe**: machine-state is inventory, not a *binding*, so there is no pass/fail verdict and no RED/AMBER — there is no "wrong" GPU. It is deliberately a plain JSON dict, **not** a whoami-contract envelope (no `binding`/`status`); forcing machine-state into the envelope shape would be the category error the session/plugin-binding separation exists to avoid.

The sentinel writer embeds this inventory in `doctor-last-run.json` under a `machine` key (additive; gated on P-5 — empty object if `coordinator_whoami` is not importable), so the machine-readable doctor record carries it alongside the probe verdict. For a human one-liner, run the CLI with `--human`.

### P-11 — Templates/setup drift detection

<!-- spec-backlink: docs/plans/2026-05-21-generic-percolation-via-coordinator-install.md § Step 3 + Step 8 -->

P-11 covers the source-of-truth substrate the coordinator plugin ships for `/coordinator:install` and the generic percolator: `coordinator/templates/setup/publish.sh`, `publish_sync.py`, and `publish-targets.example.sh`. The live install at `~/.claude/setup/` is materialized from these templates by `install-substrate.sh`. **Drift** here means the bytes on disk in `~/.claude/setup/` no longer match the templates the plugin ships — typically because the operator hand-edited the live file, or because a plugin update bumped the template without re-running the installer. Either way, the next `/coordinator:install` or installer run would produce a result the templates declare but the operator does not have.

**Recovery is inspect-only and manual, template-as-authoritative.** `verify-templates-setup-sync.sh` reports drift; it has no `--fix` flag (removed — no automated caller ever invoked the prior live→template `--fix` path, and an inspect-only tool cannot silently overwrite the plugin's shipped source with an operator's local edits). To resolve drift, the operator runs `cp coordinator/templates/setup/<file> ~/.claude/setup/<file>` by hand, deliberately restoring the template's reviewed content over the local edit.

**Why `degraded` and not `error`.** Operator-customized `publish.sh` is intentional behavior the doctrine accepts — operators legitimately tune their publish targets, retry logic, or commit messages for their environment. Drift is informational ("bugfixes in the template will not reach this operator until manually re-synced"), not a failure mode that blocks coordinator function. `error` severity is reserved for substrate that, when broken, prevents downstream plugins from working at all (P-1, P-2, P-4, P-5, P-6, P-10). P-11 is in the same severity family as P-3 (machine-local repos populated) and P-7 (mcpServers config presence) — surface to operator, do not block.

---

## Severity Vocabulary

This wiki uses a four-state probe-result vocabulary: `{healthy, degraded, error, inconclusive}`.

**Relationship to `cross-plugin-whoami-contract.md`.** The whoami contract defines a *closed* `status.state` enum: `{"healthy", "degraded", "error"}`. That enum is enforced by the envelope validator — a response with `status.state = "inconclusive"` would be rejected as non-conformant. The doctor-wiki vocabulary is a *separate* surface used in operator-facing prose and probe tables, never inside a whoami envelope. The first three states intentionally match the contract's so that a probe verdict lines up with a `status.state` when you are reporting results in a table; `inconclusive` is added for the case where a probe cannot determine pass or fail (e.g., a dependency tool is absent and the probe cannot execute).

**Three-way "degraded" disambiguation.** The term `degraded` appears in three distinct vocabularies in this system, with different semantics:

- **Doctor-probe result** (this wiki): the probe ran and surfaced a non-fatal problem. The substrate is partially functional. Operator action recommended but not blocking.
- **`status.state` in the whoami envelope** ([`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) §`status` object): the plugin reported that its health is degraded — some dependency is missing or tool calls may succeed with reduced capability.
- **`binding.kind` in the whoami envelope** ([`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) §`binding` object): the plugin's primary resource is only partially resolved.

All three reuse the word deliberately (the probe-result vocabulary aligns with the contract's so probe tables read cleanly), but they are non-interchangeable. A doctor probe returning `degraded` does not imply the whoami envelope will carry `status.state = "degraded"` — the probe may have found a configuration gap that does not affect the live binding reported by the daemon.

**`inconclusive`** is doctor-wiki-only. It is the correct probe verdict when the probe cannot run at all (command not found, required dependency absent). It must never flow into a whoami envelope `status.state`.

---

## Citation Contract for Downstream Doctors

> **Consumers (not just doctors) calling `coordinator_whoami`:** any sibling/consumer process that wants `coordinator_whoami` output must resolve the coordinator interpreter (`COORDINATOR_PYTHON` env → `machine-local get coordinator.python`) and invoke it as a **subprocess** — bare in-process `import coordinator_whoami` from a consumer venv is fail-loud by design (2026-06-20). The copy-paste shell + Python recipe lives in `machine-local-registry.md § 5c` (Consumer recipe — D2-26). Do NOT install `coordinator_whoami` into a consumer venv or add a `sys.path` shim.

Plugin doctors (example-game-repo, project-rag, project-rag-ue-addon) that probe coordinator-owned substrate — the machine-local registry, the `coordinator_whoami` package, or mcpServers classification — MUST use one of two citation shapes:

**(a) Delegation.** The downstream doctor's probe says "for diagnostic procedure, see coordinator-doctor.md P-N" and surfaces this wiki's verdict verbatim. Use this when the downstream doctor has no additional context to add — it is asking the same question this wiki's probe answers.

Example citation string:
```
Probe C-N delegates to coordinator-doctor P-3. Run: machine-local list | grep -q '^repos\.' && echo healthy || echo degraded
See coordinator-doctor.md P-3 for full pass/fail interpretation and remediation.
```

**(b) Augmentation.** The downstream doctor runs its own check that depends on coordinator substrate, and cites P-N as the prerequisite. Use this when the downstream doctor's probe builds on a coordinator-substrate result (e.g., "given P-3 is healthy, verify that `repos.example_game_workbench_repo` resolves to a directory containing a `.uproject` file").

Example citation string:
```
Prerequisite: coordinator-doctor P-3 (machine-local repos populated). This probe extends P-3:
given P-3 healthy, verify repos.example_game_workbench_repo resolves to a valid .uproject root.
```

**THIRD-PATH-CLOSED.** There is no third path. Downstream doctors probing coordinator-owned substrate (machine-local registry, `coordinator_whoami`, mcpServers classification) MUST use citation shape (a) or (b). Reinventing a probe against coordinator substrate without one of these citation shapes is a doctrine violation, surfaceable to PM. Ad-hoc invention is out-of-contract; the citation shapes exist precisely to close that failure mode.

> *Cross-team directive (example-game-repo, project-rag, project-rag-ue-addon): any doctor.md surfacing probes against coordinator-owned substrate — machine-local registry, coordinator_whoami, mcpServers classification — MUST use citation shape (a) delegation or (b) augmentation. Reinventing a probe against our substrate is the failure mode this wiki exists to close; ad-hoc invention is out-of-contract.*

**Binding-health probes MUST cite P-6, not P-7. Orientation-health probes MUST cite P-6s, not P-6.** When a downstream doctor is classifying plugin-binding health ("is this plugin's binding working?"), it MUST cite P-6 (live plugin whoami call), not P-7 (config-presence file check) — even when P-7 is sufficient for a pure config-audit purpose. File presence does not equal runtime correctness. For session orientation health, the probe is P-6s (`coordinator_whoami.session`) — not P-6 (`coordinator_whoami.project_rag`). These are distinct questions; downstream doctors must use the appropriate probe for each. This applies whether the doctor delegates (a) or augments (b).

> *Cross-team directive (example-game-repo, project-rag, project-rag-ue-addon): when probing "is this plugin's binding healthy?" the answer comes from live whoami (P-6), not file-read mcpServers classification (P-7). Treating P-7 as a binding-health probe is consumer-leak shape — file presence ≠ runtime correctness. When probing "is the coordinator session oriented?", cite P-6s, not P-6 — orientation is not a plugin-binding question.*

**Live-call requirement for whoami-dependent probes.** Per [`plugin-identity-and-health-sentinels.md`](plugin-identity-and-health-sentinels.md) (live = MCP truth; persistent = receipt) and the live-not-receipt invariant in [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md), any downstream doctor reusing P-7 or any whoami-dependent probe MUST call the live MCP `*_whoami` tool — never read a persisted snapshot from `~/.claude/<plugin>/install-profile.json` or equivalent. Persisted whoami snapshots are operator-facing receipts, not diagnostic truth; consulting a stale snapshot turns "stale = signal" into "stale = active lie." This requirement applies to both delegation (a) and augmentation (b) citation shapes.

---

## Bootstrap from Cold-Start

If P-1, P-2, or P-4 fail because the substrate does not exist yet, the operator has not run Phase 3 of `/coordinator:install`. Phase 3 lays down:

- `~/.claude/machine-local/` directory
- `machine-local` CLI shim
- `registry.toml` (tracked baseline with `schema = 1`)
- `registry.local.toml` (gitignored machine-specific overrides)
- A README and `.gitignore` for the directory

Run `/coordinator:install` and follow the Phase 3 interactive prompts to seed the four baseline keys (`publish.mirrors.coordinator_claude.path`, `repos.project_rag`, `repos.example_game_workbench_repo`, and `publish.targets`). After Phase 3 completes, re-run P-1 through P-4 to confirm.

For P-5 failures (package not importable), the coordinator venv at `~/.claude/.coordinator-venv/` is missing, broken, or the `coordinator.python` pin is stale. Run `bin/ensure-coordinator-venv.sh` to rebuild the venv idempotently — this is what `/coordinator:install` Phase 3 Step 6 now does. The script creates `~/.claude/.coordinator-venv/`, seeds `coordinator_whoami` via editable install from `plugins/coordinator/whoami/`, and writes the venv interpreter path to `machine-local` as `coordinator.python`. <!-- Review: code-reviewer F2/F7 — corrected venv path from ~/.coordinator-venv/ to ~/.claude/.coordinator-venv/ (canonical form). --> A bare `pip install -e <path>` into the system interpreter is the **wrong remediation** after this change — it is PEP-668-blocked on Homebrew/Debian and goes invisible after a system Python bump.

---

## Sentinel-Writer Primitive

**Script.** `coordinator-doctor-sentinel.sh` (in the coordinator-claude plugin tree). Fires all probes in `doctor-probes.toml` in batch, classifies each result, and writes a sentinel at `~/.claude/plugins/coordinator-claude/data/doctor-last-run.json` for [`scan-addon-health.sh`](addon-health-sentinel.md) to consume.
<!-- Review: code-reviewer slice-B F3 — replaced "P-1..P-12" with resilient form; fires all 20 manifest probes -->

**Why a script and not a slash skill.** The §1 framing ("not a slash skill") remains the design. A slash skill would imply an interactive flow with EM choice points; the cadence path is the opposite — fire the probes, write the receipt, move on. The script is a thin glue layer over the same probes operators run inline.

**Verdict synthesis.**

- Any probe with severity `error` failing → `RED`
- No errors, but one or more `degraded` failing → `AMBER`
- All probes pass → `GREEN`
- Probes that cannot execute (missing dependency tool) → `AMBER` with explanatory note in `hint`

**Sentinel schema** (mirrors `addon-health-sentinel.md`, plus an `amber_probes` field for machine-readable AMBER triage — `scan-addon-health.sh` ignores unknown fields, so the extension is additive-safe):

```json
{
  "ran_at":       "<ISO-8601 UTC, Z-suffix>",
  "verdict":      "GREEN" | "AMBER" | "RED",
  "red_probes":   ["P-1", "P-5", ...],
  "amber_probes": ["P-3", "P-9", ...],
  "hint":         "<one-line per failing probe, joined with ' | '>",
  "machine":      { "os": {...}, "arch": {...}, "gpu": {...}, "python": {...}, "uv": {...} },
  "plugin":       "coordinator-claude"
}
```

The `machine` field is informational host inventory (see § Machine info above), not a probe verdict — gated on P-5, empty object `{}` when `coordinator_whoami` is not importable. `scan-addon-health.sh` ignores it (additive-safe).

**Severity rule for missing dependencies.** Probes for OPTIONAL tools whose dependency is absent (e.g. P-9 `verify-ue-overrides.sh` on a non-UE workstation) are silently skipped — not surfaced. Probes for REQUIRED INFRASTRUCTURE whose binary is missing (P-4 `machine-local` CLI, P-10 `claude-home` resolver) are RED — their absence means `/coordinator:install` Phase 3 regressed and downstream plugins will fail.

**Where it fires.**

- `/workday-start` Step 1.10 — runs the script ahead of `scan-addon-health.sh` so the freshly-written sentinel is picked up the same run.
- Direct operator invocation — `bash ~/.claude/plugins/coordinator/bin/coordinator-doctor-sentinel.sh` any time. Silent on GREEN; brief AMBER/RED stdout for direct visibility.

**Citation contract carryover.** Downstream plugin doctors that need to verify coordinator substrate MUST still follow §5 — delegate to P-N or augment P-N, never reinvent. The sentinel-writer is the *batch-execution* path for our own scheduled probing; it does not change the contract for cross-plugin citations.

**Environment honored.** `CLAUDE_HOME` (test sandboxes / CI), `COORDINATOR_PYTHON` (explicit interpreter override), `COORDINATOR_PLUGINS_ROOT` (alternate plugin root for testing).

---

## Cross-References

- [`machine-local-registry.md`](machine-local-registry.md) — substrate doctrine: what belongs in the registry, resolution order, anti-patterns, tracked-baseline + `.local` discipline. For health verification, see P-1 through P-4 above; do not consult this wiki for "is my registry healthy?" — that is what P-1 through P-4 answer.
- [`cross-plugin-whoami-contract.md`](cross-plugin-whoami-contract.md) — envelope schema, binding/status field semantics, validation, and reference implementation. For operator-facing health verification using `coordinator_whoami`, use P-5, P-6s (orientation health), P-6 (project-rag plugin-binding health), and P-7 above.
- [`addon-health-sentinel.md`](addon-health-sentinel.md) — decay-discipline convention: doctor writes receipts (stale = signal), scanner is the no-side-effects bridge. P-8 above surfaces sentinel absence as the operator-facing gap this convention addresses.
- [`plugin-identity-and-health-sentinels.md`](plugin-identity-and-health-sentinels.md) — companion doctrine defining the live/persistent split that underlies the P-6-not-P-7 rule in §5.
- [`coordinator-installer-shape.md`](coordinator-installer-shape.md) — three-audience installer contract; Phase 3 referenced in §6 above.
- [`coordinator-installer-status-schema.md`](coordinator-installer-status-schema.md) — status-report table schema for `/coordinator:install`; referenced when reading Phase 3 output.
- [`live-install-drift-audit.md`](live-install-drift-audit.md) — two-leg drift probe and refresh primitives; used when P-11 surfaces template/live-install drift as systematic.
- `bin/probe-mcp-registration.sh` — planned P-7a standalone shell probe (not yet implemented as of 2026-05-21; `/workday-start` Step 1.10.5 EM-native probe covers this gap); writes `~/.claude/plugins/coordinator-claude/data/mcp-probe-last-run.json` when implemented.
