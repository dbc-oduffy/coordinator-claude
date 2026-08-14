---
name: setup
description: "Install-chain walker (step 5/5) — verifies claude-klabauter, finishes install."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--skip-dep-check --accept-missing-deps-risk]"
---

# /coordinator:setup

Chain-walker skill for coordinator-claude (chain position 5 of 5 — root of the OSS
plugin-adoption chain). Reads the install manifest, walks `direct_deps` (ONE hard entry — the
control-plane engine), and emits the chain-complete terminal banner once satisfied, or fails loud
with remediation if the engine is unresolvable. Does NOT replace `coordinator:install` (OSS plugin
bootstrap into `~/.claude/`) or `coordinator:repo-setup` (consumer-project first-time
scaffolding) — three distinct verbs; disambiguation rationale: wiki.

**`setup_skill` in the manifest is informational, not the dispatch primitive** — it tells humans
what to type. This skill uses direct Bash calls, not subagent dispatch (the single engine
dependency self-confirms via the `claude_klabauter_seam_resolvable` probe kind — no recursive chain-walk).

**Registry-key resolution:** a dev-tree session resolves the engine via `repos.claude_klabauter` /
`REPO_CLAUDE_KLABAUTER`; an OSS install has no such registry entry and resolves the same engine
(published as `claude-klabauter`) via `docs/install/AGENT.md` instead. Both paths resolve the
identical dependency.

---

## Out-of-scope for all dispatched agents in this skill

DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh`
command mutating GitHub state beyond pushing the current branch. DO NOT commit to `main` directly.
Surface a needed merge to the EM instead of doing it.

- Writing outside `plugins/coordinator/`.
- Modifying `docs/install/agent-install-manifest.json` at runtime (static artifact, read-only here).
- Touching the DR, example-game-repo, ue-addon, or project-rag trees.
- Any `git commit` or `git push`.

---

## Step 1 — Detect layout

`PLUGIN_ROOT` is two levels up from this skill file (`coordinator/skills/setup/SKILL.md` →
`coordinator/`); resolve it relative to wherever this file lives on disk.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" layout --plugin-root "<PLUGIN_ROOT>"`.
Prints `Layout: <flat|nested>` and `Manifest path: <path>`; exits 1 with a "Manifest not found"
remediation if `docs/install/agent-install-manifest.json` is absent under the resolved repo root.
Surface an exit-1 error verbatim.

---

## Step 2 — Read the install manifest

Verify `${MANIFEST}` exists (error and exit if missing), then parse it. Extract:
`agent_install_contract_version` (must be 1, 2, or 3 — reject otherwise), `repo_id` (should be
`"coordinator-claude"`), `direct_deps` (the walk list — one hard entry), `override_flags` (the
consent-gate flag-pair names). On a JSON parse failure, surface the error and exit — do not
continue with a corrupt manifest.

---

## Step 3 — Initialise the visited-set

Disk-resident, for diamond-DAG and cycle detection across recursive subagent dispatches:
`<settings-home>/coordinator-claude/chain-walk-<session-id>.json`, where `<settings-home>` =
`${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}`.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" visited-init`
— generates a session id, prunes `chain-walk-*.json` files older than 60 minutes, writes the new
file with an empty `visited` array, prints `Session ID:` and `Visited-set:`.

---

## Step 4 — Walk direct_deps and resolve system prerequisites

Python is pre-verified (hard exit if absent — the sole hard gate on this path). Run
`python3 $CLAUDE_KLABAUTER_ROOT/coordinator/scripts/chain-walk.py` (resolve `CLAUDE_KLABAUTER_ROOT` via
`machine-local get repos.claude_klabauter`, or the `REPO_CLAUDE_KLABAUTER`/`CLAUDE_KLABAUTER_ROOT` env override
— the trampoline re-resolves `CLAUDE_KLABAUTER_ROOT` itself; from a shell already rooted in the engine repo,
`python3 -m coordinator_core.ops.setup_chain_walker` is the same walker without the trampoline).
**Never the deprecated `setup.py` forwarder.**

This calls `_co_run_prereq_gate post-consumer`, which emits one dep row (the engine, hard) and the
prereq probe rows (git, python, uv, gh, node, pwsh, ue, clone_auth, longpaths, git_lfs):

| Probe | Severity |
|---|---|
| python | hard (sole hard gate) |
| gh, node, git | advisory (demoted from hard) |
| clone_auth | advisory (demoted from semi-hard) |
| everything else | advisory |

Advisory failures print `[WARN]` to stderr and do not block exit 0. A missing/broken engine
dependency triggers the [FAIL] hard-fail path — exit 1 (`--preflight`/`--check`) or consent-gate
codes 90/91/92 (full install), remediation pointing at the `CLAUDE_KLABAUTER_ROOT` resolution ladder. Full
contract detail (severity taxonomy, consent-gate banner, exit codes): wiki.

**Read-only flags** (`--help`, `--version`, `--phase-list`, `--last-status`, `--check`) are
serviced before any dep-walking and do not trigger the override check.

**Override flags** — both must be passed TOGETHER: `--skip-dep-check` and
`--accept-missing-deps-risk`. Validate via
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-override-flags -- "$@"`
— exits 93 when exactly one is present, 0 otherwise (printing which path applies). Passing only
one degrades most mutating coordinator operations (no bash fallback under the big-bang cutover);
both together bypass the consent gate.

---

## Step 5 — Terminal report

```
## /coordinator:setup — chain step 5 of 5

Manifest: plugins/coordinator/docs/install/agent-install-manifest.json
Contract version: <agent_install_contract_version from manifest>
Layout: <flat | nested>
Session ID: <uuid>

### System prerequisite gate (post-consumer mode)

| Probe      | Severity | Result | Notes                                      |
|------------|----------|--------|--------------------------------------------|
| python     | hard     | PASS   | Python 3.11+ (the sole hard gate)          |
| gh         | advisory | PASS/WARN | demoted from hard; WARN does not block  |
| node       | advisory | PASS/WARN | demoted from hard; WARN does not block  |
| git        | advisory | PASS/WARN | demoted from hard; WARN does not block  |
| clone_auth | advisory | PASS/WARN | demoted from semi-hard; WARN does not block |
| uv/pwsh/ue/longpaths/git_lfs | advisory | PASS/WARN | advisory, no change |

### Dependency walk

| Dep | Severity | Probe | Action |
|-----|----------|-------|--------|
| claude-klabauter | hard | PASS/FAIL | claude_klabauter_seam_resolvable — self-confirming (this walker code only runs once claude-klabauter is already resolved) |

### Result

coordinator install-chain walker — chain step 5 of 5: all deps satisfied.

coordinator-claude install chain complete.
```

Exit 0 (advisory WARN rows do not affect exit code).

---

## Step 6 — Live Claude-Code-integration validation

Asserts the plugin is running-in-Claude-Code, not just present on disk, via three testable
surfaces (no MCP server for this plugin):

1. **Plugin enabled** — listed in `settings.json`/`enabledPlugins`, not disabled/overridden.
2. **Hooks registered and live** — this plugin's hooks exist on disk at their expected paths and
   are included in the Claude Code hooks configuration.
3. **Skill discovery preconditions** — a representative skill file exists, parses, and exposes a
   `description:` field with trigger phrases. Skills are model-invoked, not shell-invoked — the
   assertion is discovery-preconditions-met, not shell execution.

### Restart-batch (emit before the per-item probe table)

Collect every **restart-gated** finding into one block, emitted only if non-empty:

```
restart-batch (emit this block if any restart-gated items are found):
────────────────────────────────────────────────────────────────
The following items require a Claude Code restart to take effect.
Restart Claude Code NOW, then re-validate (re-run /coordinator:setup).

  [restart-gated] <item description>
  ...
────────────────────────────────────────────────────────────────
```

### Restart discriminator

- **restart-gated-expected** — fails, no restart since the config write → restart-batch; not a
  hard failure.
- **configured-but-broken** — fails after a restart (or its settle window) → fail loud.
- **pending-settle** — fails within the settle window → re-probe once, then reclassify.

### Probes

Run via Bash. Resolve `PLUGIN_ROOT` per-probe if not already in scope (each probe must be
self-contained). Rationale for probe ordering and design: wiki.

**Probe 0 — Plugin reachable.**
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-plugin-registered --plugin coordinator --marketplace coordinator-claude --marketplace-source dbc-oduffy/coordinator-claude --plugin-dir "<PLUGIN_ROOT>"`.
Asserts reachability (marketplace registration OR live `--plugin-dir` resolution — `PASS
(live-resolved)` when a manifest plus commands or hooks are present at that path), not mere
enablement membership. Runs before Probe 1 deliberately. **Never restart-gated** — always
configured-but-broken on FAIL.

**Probe 1 — Plugin enabled in settings.json.**
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-settings-membership` (optional `--settings <path>`, default `~/.claude/settings.json`).
`PASS`/exit 0, `[WARN]`/exit 0 if settings.json missing/unparseable, `FAIL`/exit 1 otherwise. A
FAIL after a config write with no subsequent restart is restart-gated-expected; after a restart,
configured-but-broken.

**Probe 2 — Hooks registered and live on disk.**
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-hooks --plugin-root "<PLUGIN_ROOT>"`.
Parses `<PLUGIN_ROOT>/hooks/hooks.json`, verifies each coordinator-owned hook path exists on disk
(named lookup, not a blanket file count). `PASS`/exit 0, `FAIL` (lists missing paths)/exit 1,
`[WARN]` (hooks.json absent/unparseable, or no coordinator-owned hooks)/exit 0. Hooks absent from
disk → configured-but-broken. Hooks present but not yet loaded by a running session →
restart-gated-expected.

**Probe 3 — Skill discovery preconditions.**
Use this skill itself as the representative: `<PLUGIN_ROOT>/skills/setup/SKILL.md`.
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-skill-description --skill-file "<PLUGIN_ROOT>/skills/setup/SKILL.md"`.
`PASS`/exit 0, `FAIL` (missing file, no frontmatter, no/empty `description:`)/exit 1. Missing or
unparseable skill file is always configured-but-broken — never restart-gated. Probe 1's WARN
propagates here since plugin-enabled is a precondition for the model reaching this skill.

### Validation summary table

```
### Step 6 — Live Claude-Code-integration validation (running-in-Claude-Code)

| Probe | Surface | Result | Classification |
|-------|---------|--------|----------------|
| Plugin reachable | marketplace registration OR `--plugin-dir` live resolution | PASS/FAIL | live / configured-but-broken (never restart-gated) |
| Plugin enabled | settings.json enabledPlugins | PASS/WARN/FAIL | live / restart-gated-expected / configured-but-broken |
| Hooks live on disk | ~/.claude/hooks/ | PASS/WARN/FAIL | live / restart-gated-expected / configured-but-broken |
| Skill discovery preconditions | skills/setup/SKILL.md | PASS/WARN | live / configured-but-broken |
```

### Exit-code semantics

`configured-but-broken` → `[ERROR]` to stderr, exit non-zero — the install is incomplete and the
chain-walk result is not valid; this is the exception to the Steps 4/5 advisory-WARN model.
`restart-gated-expected` → WARN row in the summary table and restart-batch; does not change the
exit code. All probes PASS → emit the summary table, exit 0.

---

## Negative-spec

<!-- negative-spec: this skill does NOT dispatch subagents. coordinator-claude's one direct_dep (the engine) self-confirms via the claude_klabauter_seam_resolvable probe kind — there is no recursive chain-walk into the engine's own manifest. The visited-set is initialised for contract-conformance only. -->
<!-- negative-spec: this skill does NOT replace coordinator:install (OSS plugin install) or coordinator:repo-setup (consumer-project first-time setup). This skill DOES assert, via Probe 0, that the plugin is actually reachable — by marketplace registration or live --plugin-dir resolution — rather than merely enabled by membership; that assertion is in scope here even though performing the registration itself remains coordinator:install's job. -->
<!-- negative-spec: this skill does NOT seed install-leg spinoffs into the install-baton rendezvous (`$(coordinator-settings-home)/state/handoffs/`). Spinoffs are PM-authorized via /spinoff only. -->
<!-- negative-spec: the visited-set path is <settings-home>/coordinator-claude/chain-walk-*.json where <settings-home> = ${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings} — canonical per agent-install-contract.md § Visited-set protocol. -->
