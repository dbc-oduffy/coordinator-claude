---
name: setup
description: "Install-chain step 5/5: verify the engine, finish install."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--skip-dep-check --accept-missing-deps-risk]"
---

# /coordinator:setup

Chain-walker for coordinator-claude (chain position 5 of 5). Reads the install manifest, walks
`direct_deps` (ONE hard entry — the control-plane engine), emits the chain-complete banner once
satisfied, or fails loud with remediation if the engine is unresolvable. Does NOT replace
`coordinator:install` or `coordinator:repo-setup`.

**Runnable on stated intent.** The PM's stated intent to install or set up coordinator authorizes
running this skill; it need not be human-typed. `plugin_update` stays gated.

This skill uses direct Bash calls, not subagent dispatch.

**Registry-key resolution:** a dev-tree session resolves the engine via `repos.claude_klabauter` /
`REPO_CLAUDE_KLABAUTER`; an OSS install (engine published as `claude-klabauter`) via
`docs/install/AGENT.md`.

## Out-of-scope for all dispatched agents in this skill

DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh`
command mutating GitHub state beyond pushing the current branch. DO NOT commit to `main` directly.
Surface a needed merge to the EM instead.

- Writing outside `plugins/coordinator-claude/coordinator/`.
- Modifying `docs/install/agent-install-manifest.json` at runtime (static, read-only here).
- Touching the DR, example-game-repo, ue-addon, or project-rag trees.
- Any `git commit` or `git push`.

## Step 1 — Detect layout

`PLUGIN_ROOT` is two levels up from this skill file (`coordinator/skills/setup/SKILL.md` →
`coordinator/`).

**`SV` below is the `setup-verify` launcher.** On a PowerShell host it is
`& "$env:COORDINATOR_SETTINGS_HOME\bin\setup-verify.exe"` (call operator, Shape W), never the
`${...}` POSIX form. Ladder and shapes: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

Run `SV layout --plugin-root "<PLUGIN_ROOT>"`. Prints `Layout: <flat|nested>` and
`Manifest path: <path>`; exits 1 with a "Manifest not found" remediation if
`docs/install/agent-install-manifest.json` is absent. Surface an exit-1 error verbatim.

## Step 2 — Read the install manifest

Verify `${MANIFEST}` exists (error and exit if missing), then parse it (surface a parse failure and
exit). Extract: `agent_install_contract_version` (must be 1, 2, or 3 — reject otherwise), `repo_id`
(should be `"coordinator-claude"`), `direct_deps` (the walk list), `override_flags` (the
consent-gate flag-pair names).

## Step 3 — Initialise the visited-set

Disk-resident, for diamond-DAG and cycle detection:
`<settings-home>/coordinator-claude/chain-walk-<session-id>.json`, `<settings-home>` resolved per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. Run `SV visited-init` — generates a
session id, prunes `chain-walk-*.json` older than 60 minutes, writes the new file with an empty
`visited` array, prints `Session ID:` and `Visited-set:`.

## Step 4 — Walk direct_deps and resolve system prerequisites

Python is pre-verified (hard exit if absent — the sole hard gate on this path). Run
`python3 -m coordinator_core.ops.setup_chain_walker --coordinator-root "${CLAUDE_PLUGIN_ROOT}"`
(the engine resolves itself; no root variable to set). **Never the deprecated `setup.py`
forwarder.**

It calls `_co_run_prereq_gate post-consumer`, emitting one dep row (the engine, hard) and the
prereq probe rows (git, python, uv, gh, node, pwsh, ue, clone_auth, longpaths, git_lfs).
Advisory failures print `[WARN]` to stderr and do not block exit 0. A missing/broken engine
dependency triggers the [FAIL] hard-fail path — exit 1 (`--preflight`/`--check`) or consent-gate
codes 90/91/92 (full install), remediation pointing at the engine-root resolver. Full contract
detail (severity taxonomy, consent-gate banner, exit codes): wiki.

**Read-only flags** (`--help`, `--version`, `--phase-list`, `--last-status`, `--check`) are
serviced before any dep-walking and skip the override check.

**Override flags** — pass BOTH together: `--skip-dep-check` and `--accept-missing-deps-risk`.
Validate via `SV check-override-flags -- $args` — exits 93 when exactly one is present, else 0.
One alone degrades most mutating operations; both together bypass the consent gate.

Then seed the Group EM's home: `"$_py" "${CLAUDE_PLUGIN_ROOT}/bin/group-em-home.py" ensure`
(idempotent; also moves an existing legacy general-work home into place when no session is live in it). Exit 3 (home inside a checkout): a `[WARN]` row; never move it.
The installer's general-work step converges the root into a full coordinator repo (manifest tree, `coordinator.local.md`, `archive/`, seed commit on `main`); re-check it with `"$_py" "${CLAUDE_PLUGIN_ROOT}/bin/general-work-root.py" ensure` (idempotent). Exit 3: a `[WARN]` row.

## Step 5 — Terminal report

Header `## /coordinator:setup — chain step 5 of 5`; manifest path, contract version, layout,
session id; a prerequisite table (python hard; the rest advisory); a dependency row (the engine,
hard, `claude_klabauter_seam_resolvable`); result line `coordinator install-chain walker — chain step 5 of
5: all deps satisfied.` then `coordinator-claude install chain complete.` Exit 0.

## Step 6 — Live Claude-Code-integration validation

Collect every **restart-gated** finding into one block emitted before the probe table, only if
non-empty: "The following items require a Claude Code restart to take effect. Restart Claude Code
NOW, then re-validate (re-run /coordinator:setup)." then one `[restart-gated] <item>` line each.

Discriminator:
- **restart-gated-expected** — fails, no restart since the config write → restart-batch, not a hard failure.
- **configured-but-broken** — fails after a restart (or its settle window) → fail loud.
- **pending-settle** — fails within the settle window → re-probe once, then reclassify.

Run each probe via Bash, resolving `PLUGIN_ROOT` per-probe if not in scope.

**Probe 0 — Plugin reachable.**
`SV check-plugin-registered --plugin coordinator --marketplace coordinator-claude --marketplace-source dbc-oduffy/coordinator-claude --plugin-dir "<PLUGIN_ROOT>"`.
Asserts reachability (marketplace registration OR live `--plugin-dir` resolution — `PASS
(live-resolved)`). **Never restart-gated.**

**Probe 1 — Plugin enabled in settings.json.**
`SV check-settings-membership --plugin-dir "<PLUGIN_ROOT>"` (optional `--settings <path>`, default
`~/.claude/settings.json`; omitting `--plugin-dir` FAILs a live-resolved install). `PASS`/exit 0,
`[WARN]`/exit 0 if settings.json missing/unparseable, `FAIL`/exit 1 otherwise. A FAIL with no
restart since a config write is restart-gated-expected; after a restart, configured-but-broken.
On Probe 0 `PASS (live-resolved)`, Probe 1 degrades to `[WARN]`/exit 0. Retired
`<name>@coordinator-claude` keys (not in the marketplace manifest) `[WARN]`; `--prune-retired` removes them.

**Probe 2 — Hooks registered and live on disk.**
`SV check-hooks --plugin-root "<PLUGIN_ROOT>"`. Verifies each coordinator-owned hook path in
`<PLUGIN_ROOT>/hooks/hooks.json` exists on disk. `PASS`/exit 0, `FAIL` (lists missing paths)/exit
1, `[WARN]` (hooks.json absent/unparseable, or no coordinator hooks)/exit 0. Absent from disk →
configured-but-broken; present but not yet loaded → restart-gated-expected.

**Probe 3 — Skill discovery preconditions.**
`SV check-skill-description --skill-file "<PLUGIN_ROOT>/skills/setup/SKILL.md"`. `PASS`/exit 0,
`FAIL` (missing file, no frontmatter, no/empty `description:`)/exit 1 — always
configured-but-broken. Probe 1's WARN propagates here.

**Probe 4 — Windows launch shape (dogfood shape only).**
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-launch-shape"` (PowerShell: `& "$env:COORDINATOR_SETTINGS_HOME\bin\check-launch-shape.exe"`).
Asserts the interactive `claude.exe` is a DIRECT child of the invoking shell. `PASS`/exit 0,
`FAIL` (names the offender)/exit 1, `SKIP`/exit 0 on non-Windows or with no rendered launcher pair
on PATH. FAIL is always configured-but-broken, **never restart-gated**.

### Validation summary table

Heading `### Step 6 — Live Claude-Code-integration validation (running-in-Claude-Code)`, then a
`| Probe | Surface | Result | Classification |` table, one row per probe (Probe 4 is the launch shape). Classification is
`live`, `restart-gated-expected` (Probes 1-2 only; Probe 1 reads `live-resolved` when Probe 0
passed), `configured-but-broken`, or `not-this-shape` (Probe 4 SKIP).

### Exit-code semantics

`configured-but-broken` → `[ERROR]` to stderr, exit non-zero (the exception to the advisory-WARN
model). `restart-gated-expected` → WARN row and restart-batch, exit code unchanged. All PASS → exit 0.

## Negative-spec

<!-- negative-spec: this skill does NOT dispatch subagents (no recursive chain-walk; the visited-set is for contract-conformance only), does NOT replace coordinator:install or coordinator:repo-setup (it only asserts reachability via Probe 0), and does NOT seed install-leg spinoffs into the install-baton rendezvous (/spinoff only). -->