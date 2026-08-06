---
name: setup
description: "Install-chain walker (step 5/5) — verifies claude-klabauter, finishes install."
allowed-tools: ["Read", "Bash"]
argument-hint: "[--skip-dep-check --accept-missing-deps-risk]"
---

# /coordinator:setup

Chain-walker skill for coordinator-claude (chain position 5 of 5 — root of the OSS plugin-adoption chain). This skill is the agentic entry-point for the install-chain contract for the coordinator plugin. It reads the install manifest, walks the `direct_deps` list (ONE hard entry — `claude-klabauter`, the engine), and emits the chain-complete terminal banner once satisfied — or fails loud with remediation if claude-klabauter is unresolvable. It does NOT replace `coordinator:install` (the OSS plugin bootstrap for the coordinator package) or `coordinator:repo-setup` (the consumer-project first-time integration setup) — those concerns belong to their respective skills.

**Disambiguation — three coexisting `/coordinator:*` verbs:**

- `/coordinator:setup` — **this skill.** The install-chain walker, required by the agent-install-contract. Reports chain-walk status and verifies the manifest is structurally sound. Invoked by the install-chain DAG walker when a consumer resolves coordinator-claude as a dep.
- `coordinator:install` — installs the coordinator plugin package into a consumer's `~/.claude/` environment. OSS-user-facing bootstrap. Unrelated to the install-chain DAG contract.
- `coordinator:repo-setup` — first-time setup of the coordinator integration into a consumer project repo (generates coordinator scaffolding, sets up hooks, creates initial state files). Consumer-project-facing. Unrelated to the install-chain DAG contract.

These three verbs coexist without collision. The `:setup` verb is the established cross-plugin convention across DR, project-rag, ue-addon, and now coordinator-claude.

**IMPORTANT — `setup_skill` is informational metadata, not the dispatch primitive.** The manifest field `setup_skill: /coordinator:setup` tells humans what to type. Dispatched subagents cannot expand slash commands; this skill uses direct Bash calls instead of subagent dispatch (the single claude-klabauter dep self-confirms via the `claude_klabauter_seam_resolvable` probe kind — no recursive chain-walk, no subagent is needed).

**Naming note — internal registry key vs OSS-published name.** The `repos.claude_klabauter`/
`REPO_CLAUDE_KLABAUTER` lookups throughout this skill are the correct sibling-registry resolution
path for a dev-tree session that has that registry entry, and stay as written. An OSS installer has
no such registry entry and will not resolve the engine that way; for that audience the same engine
is the dependency described in `docs/install/AGENT.md` (published under its own OSS-facing name,
private and access-on-request until its publish goes live). Both paths resolve the identical
engine — the registry key is internal plumbing, not a second dependency.

---

## Out-of-scope actions for all dispatched agents in this skill

**Destructive-action prohibition (verbatim from the coordinator tripwires doctrine):**

DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find yourself reaching for a merge, STOP and surface the question to the EM in your final reply.

**Additional out-of-scope items specific to this skill:**

- Writing files OUTSIDE `plugins/coordinator/` (this skill owns nothing in the DR, example-game-repo, ue-addon, or project-rag trees)
- Modifying `docs/install/agent-install-manifest.json` at runtime (manifest is a static artifact read by the walker, not mutated by it)
- Touching any example-game-repo tree, ue-addon tree, or project-rag tree (deep-research content is now bundled inside coordinator — its commands/agents/pipelines live under `plugins/coordinator/`, which is this skill's own tree; but this skill must not restructure or rename DR content without a dedicated plan)
- Any `git commit` or `git push` operation

<!-- Spinoff-schema awareness: N/A — this skill does not author handoffs or spinoffs. -->
<!-- Recheck-marker semantics: N/A — this skill is not cadenced; it is invoked on demand. -->

---

## Discovery-surface integration

This skill announces itself via its `description:` frontmatter field. The description contains the trigger phrases and is surfaced by Claude Code's skill discovery. Discovery-surface integration with `/workstream-start` (Step 1 plugin-bootstrap surfacing) is a follow-up item — do NOT edit `/workstream-start` in this chunk.

**Platform-vocabulary collision check:** `:setup` is the established verb across coordinator-claude, example-game-repo, and project-rag-ue-addon. No collision; consistent verb. (deep-research no longer has a separate plugin or `:setup` verb — its content is bundled into coordinator.) The coexistence with `coordinator:install` and `coordinator:repo-setup` is documented above. ✓

---

## Step 1 — Detect layout (flat publish-repo vs. nested working-repo)

Determine whether this skill is running inside the nested working-repo (under `~/.claude/plugins/coordinator/`) or the flat publish-repo (a standalone `coordinator-claude/` checkout).

`PLUGIN_ROOT` is the directory two levels up from this skill file (`coordinator/skills/setup/SKILL.md` → `coordinator/`) — resolve it relative to wherever this skill file itself lives on disk. AGENT.md lives at `docs/install/AGENT.md` relative to the plugin root when the layout is flat.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" layout --plugin-root "<PLUGIN_ROOT>"` (substituting the resolved path). It prints `Layout: <flat|nested>` and `Manifest path: <path>`, and exits 1 with a "Manifest not found" remediation message if `docs/install/agent-install-manifest.json` is absent under the resolved repo root.

Report the detected layout. On the exit-1 remediation case, surface the printed error verbatim:
`"Manifest not found at <manifest>. Re-run after the install surface has been committed (plugins/coordinator/docs/install/agent-install-manifest.json)."`

---

## Step 2 — Read the install manifest

Verify `${MANIFEST}` exists (error and exit if missing), then read its contents.

Parse the manifest to extract:
- `agent_install_contract_version` — must be 1, 2, or 3 (reject anything outside `{1, 2, 3}` with a remediation message)
- `repo_id` — should be `"coordinator-claude"`
- `direct_deps` — the list to walk (coordinator-claude declares ONE hard entry: the control-plane engine)
- `override_flags` — the flag pair names for consent-gate invocations

If the manifest fails JSON parsing, surface the parse error and exit. Do not continue with a corrupt manifest.

---

## Step 3 — Initialise the visited-set (contract § Visited-set protocol)

The visited-set is a disk-resident file used for diamond-DAG and cycle detection across recursive subagent dispatches. Coordinator's visited-set lives at:

```
<settings-home>/coordinator-claude/chain-walk-<session-id>.json
```

where `<settings-home>` = `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}` (relocated off `~/.claude/` so the visited-set survives independently of the harness config tree).

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" visited-init` — it generates a fresh session id, prunes `chain-walk-*.json` files older than 60 minutes from the visited-set directory, writes the new file with an empty `visited` array, and prints `Session ID: <uuid>` and `Visited-set: <path>`.

---

## Step 4 — Walk direct_deps AND resolve system prerequisites (DAG-root path)

For coordinator-claude, `direct_deps` declares ONE hard entry — `claude-klabauter`. "DAG root" means root of the OSS plugin-adoption chain, not zero dependencies. The chain-walk default body also runs the system-prerequisite gate (`_co_run_prereq_gate post-consumer`) so that the DAG-root node reports its own machine-level prerequisites alongside the dep-probe row.

The walk proceeds as follows:

Python is pre-verified (hard exit if absent — the existing hard gate); this is the SOLE hard gate on the chain-walk path (post-consumer mode). Run the install-chain DAG walker's default body — `python3 <claude-klabauter-root>/coordinator/scripts/setup.py` (resolve `<claude-klabauter-root>` via `machine-local get repos.claude_klabauter`, or the `REPO_CLAUDE_KLABAUTER`/`CLAUDE_KLABAUTER_ROOT` env override) — which calls `_co_run_prereq_gate post-consumer`. Severity demotion applied inside that gate: `python` stays hard (unchanged — pre-existing hard gate); `gh`, `node`, `git` are demoted from hard to advisory (no exit-code regression); `clone_auth` is demoted from semi-hard to advisory (no exit-code regression); all other probes were already advisory in `--preflight` (no change). Advisory failures emit `[WARN]` rows to stderr but do NOT block exit 0.

The dep-probe loop inside the gate emits one dep row (`claude-klabauter`, hard). A missing/broken claude-klabauter triggers the [FAIL] hard-fail path — exit 1 (`--preflight`/`--check`) or the consent-gate 90/91/92 codes (full install), with remediation pointing at the four-rung CLAUDE_KLABAUTER_ROOT resolution ladder. The prereq probe rows (git, python, uv, gh, node, pwsh, ue, clone_auth, longpaths, git_lfs) ARE also emitted; their advisory failures print WARN but do not change the exit code.

**Override flags** — both flags must be passed TOGETHER to skip dep checking. If claude-klabauter genuinely cannot be resolved and you understand the degraded posture (most mutating coordinator operations hard-fail without it — no legacy bash fallback under the big-bang cutover), both override flags bypass the consent gate. Validate the pairing by running `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-override-flags -- "$@"` — it exits 93 with the contract-exit-code-93 remediation message ("Both --skip-dep-check AND --accept-missing-deps-risk must be passed together. Passing only one is not valid.") when exactly one of `--skip-dep-check`/`--accept-missing-deps-risk` is present, and exits 0 (printing which of the two paths applies) otherwise.

---

## Step 5 — Terminal report

After walking direct_deps (the one claude-klabauter entry) and resolving system prerequisites, print a structured summary:

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

Exit 0 (advisory WARN rows from post-consumer gate do not affect exit code).

---

## Step 6 — Live Claude-Code-integration validation

This step asserts that the coordinator plugin is **running-in-Claude-Code** — not just present on disk, but active as a live integration, per the three testable surfaces below.

**What "running-in-Claude-Code" means for coordinator-claude** (no MCP server — three testable surfaces):

1. **Plugin enabled** — coordinator-claude is listed in `settings.json` (or the active enabledPlugins surface) and the entry is not disabled/overridden.
2. **Hooks registered and live** — the hooks this plugin registers (PreToolUse, PostToolUse, etc.) are present at their expected paths on disk and are included in the Claude Code hooks configuration.
3. **Skill discovery preconditions met** — a representative skill file exists, is parseable, and exposes a `description:` field with trigger phrases; the plugin being enabled is a necessary condition for the skill to be reachable by the model. **Note:** skills are model-invoked, not shell-invoked — the assertion here is discovery-preconditions-met, not shell execution. (the Staff Engineer F1: "a representative skill is invocable" was downgraded to discovery-preconditions.)

### Restart-batch up-front

Before running any live probes, collect all **restart-gated** items and emit them as a single consolidated block:

```
restart-batch (emit this block if any restart-gated items are found):
────────────────────────────────────────────────────────────────
The following items require a Claude Code restart to take effect.
Restart Claude Code NOW, then re-validate (re-run /coordinator:setup).
After restart, these items move from restart-gated-expected → live (or
configured-but-broken if they still fail).

  [restart-gated] <item description>
  ...
────────────────────────────────────────────────────────────────
```

Emit the restart-batch block **before** the per-item probe table. An empty restart-batch (no restart-gated items found) is omitted entirely — do not emit an empty block.

### Restart discriminator

Classify each failing probe using the settle-window + restart-occurred axis:

- **restart-gated-expected** — probe fails AND no load-bearing restart has occurred since the relevant config was written → emit in the restart-batch block above; NOT a hard failure.
- **configured-but-broken** — probe fails AND a restart has already occurred (or settle window has elapsed post-restart) → fail loud (see below).
- **pending-settle** — probe fails within the settle window (e.g. first seconds after a config write) → re-probe once; if still failing after settle, reclassify as restart-gated-expected or configured-but-broken.

### Probe sequence

Run the following probes via Bash:

**Probe 0 — Plugin reachable (not just enablement-membership)**

Re-derive `PLUGIN_ROOT` if it is not already in scope from Step 1 — the plugin root is two levels up from this skill file (`coordinator/skills/setup/SKILL.md` → `coordinator/`).

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-plugin-registered --plugin coordinator --marketplace coordinator-claude --marketplace-source dbc-oduffy/coordinator-claude --plugin-dir "<PLUGIN_ROOT>"`.

This probe runs BEFORE Probe 1 deliberately. `enabledPlugins` membership (Probe 1) can read `true` while the plugin was never registered at all — a repo can ship a plugin, register its MCP server, and never register the plugin itself, leaving a `~/.claude/plugins/<name>/` directory that holds only runtime data (session state, caches) with no manifest, no commands, and no hooks. Every weaker check — enablement membership, hook-file presence, skill-file presence — still reads as "installed" against that state, so the plugin's `SessionStart` hook never fires and nothing reports a problem. Checking enablement first yields a false pass on exactly this state.

What the probe asserts is **reachability**, not marketplace registration specifically, because there are two legitimate routes to it: a marketplace install (present in both `installed_plugins.json` and `known_marketplaces.json`), or live resolution from a source checkout via `--plugin-dir`. Passing `--plugin-dir` is what lets the second route pass — it reports `PASS (live-resolved)` when a plugin manifest plus commands or hooks are actually present at that path. Omit it and an unregistered plugin fails, which is correct for an install that was meant to go through a marketplace. Positive evidence is required either way: a bare directory never passes.

Unlike the probes below it, a FAIL here is **never restart-gated**. Registration writes the plugin registry immediately, so an unregistered plugin is unregistered now and will still be unregistered after a restart — classifying this FAIL as restart-gated-expected would wave through the exact state the probe exists to catch. Always **configured-but-broken**; fail loud.

**Probe 1 — Plugin enabled in settings.json**

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-settings-membership` (optionally `--settings <path>` to override the default `~/.claude/settings.json` — the canonical Claude Code user-settings path). It checks that `coordinator` appears in `enabledPlugins` (or the legacy `plugins` field), printing `PASS — coordinator plugin found in enabledPlugins` and exiting 0, `[WARN] settings.json not found ... — cannot verify plugin enablement` and exiting 0 if the file is missing/unparseable, or `FAIL — coordinator plugin NOT found in enabledPlugins` and exiting 1.

A FAIL here that follows a config-write without a subsequent restart is **restart-gated-expected** — add to the restart-batch block. A FAIL after a restart is **configured-but-broken** — fail loud.

**Probe 2 — Hooks registered and live on disk**

Re-derive `PLUGIN_ROOT` if it is not already in scope from Step 1 (code-reviewer F4: this probe must be self-contained when run independently) — the plugin root is two levels up from this skill file (`coordinator/skills/setup/SKILL.md` → `coordinator/`).

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-hooks --plugin-root "<PLUGIN_ROOT>"`. It parses `<PLUGIN_ROOT>/hooks/hooks.json`, extracts coordinator-owned hook script paths referenced via `${CLAUDE_PLUGIN_ROOT}/hooks/...` `command` fields, and verifies each exists on disk — checking specific hooks named in hooks.json by path, not a blanket `*.sh` count (code-reviewer F6: a blanket count passes vacuously when coordinator's hooks are absent but other `*.sh` files happen to exist). It prints `PASS — N coordinator-owned hook file(s) verified present on disk` and exits 0 when all named hooks are present, `FAIL — coordinator hook(s) named in hooks.json are missing from disk` (listing each missing path) and exits 1 on any gap, or `[WARN]` (hooks.json absent/unparseable, or no coordinator-owned hooks detected) and exits 0.

Coordinator-owned hook files absent from disk → **configured-but-broken** (fail loud). Hook files present but not yet loaded by a running Claude Code session → **restart-gated-expected** (emit in restart-batch; advisory WARN).

**Probe 3 — Skill discovery preconditions (representative skill)**

Re-derive `PLUGIN_ROOT` if it is not already in scope from Step 1 (code-reviewer F4: this probe must be self-contained when run independently). Use this skill itself as the representative: `<PLUGIN_ROOT>/skills/setup/SKILL.md`.

Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/setup-verify" check-skill-description --skill-file "<PLUGIN_ROOT>/skills/setup/SKILL.md"`. It confirms the file exists, parses its YAML frontmatter, and validates a non-empty `description:` field is present — printing `PASS — description field present with trigger phrases (N chars)` and exiting 0 on success, or a `FAIL —` message (missing file, no frontmatter, no `description:` field, or an empty one) and exiting 1 on any of those gaps.

A missing or unparseable skill file is always **configured-but-broken** (fail loud — a skill file cannot be restart-gated, it either exists on disk or it doesn't). The plugin being enabled (Probe 1) is a precondition for the model to reach this skill; an advisory WARN from Probe 1 propagates here.

### Validation summary table

After running all probes, emit a summary table:

```
### Step 6 — Live Claude-Code-integration validation (running-in-Claude-Code)

| Probe | Surface | Result | Classification |
|-------|---------|--------|----------------|
| Plugin reachable | marketplace registration OR `--plugin-dir` live resolution | PASS/FAIL | live / configured-but-broken (never restart-gated) |
| Plugin enabled | settings.json enabledPlugins | PASS/WARN/FAIL | live / restart-gated-expected / configured-but-broken |
| Hooks live on disk | ~/.claude/hooks/ | PASS/WARN/FAIL | live / restart-gated-expected / configured-but-broken |
| Skill discovery preconditions | skills/setup/SKILL.md | PASS/WARN | live / configured-but-broken |
```

**Exit-code semantics (extends, but is NOT identical to, the Step 4/5 advisory-WARN model — `configured-but-broken` is the exception):**

- `configured-but-broken` findings → emit `[ERROR]` to stderr and exit non-zero. The install is incomplete; the chain-walk result is NOT valid. **This is the exception to the advisory model — it exits non-zero.**
- `restart-gated-expected` findings → emit as WARN rows in the summary table and in the restart-batch block above; do NOT change the exit code (advisory, per § Post-Consumer Gates).
- All probes PASS → emit the summary table and exit 0 normally.

The advisory-WARN semantics are inherited from Steps 4/5 for `restart-gated-expected` items: WARN rows do not change the exit code. The distinction is: a `restart-gated-expected` item is not a failure — it is an expected transient state that resolves after a restart. A `configured-but-broken` item is a real failure that the operator must fix — and it exits non-zero, unlike the pure-advisory Steps 4/5 model.

---

## Override flags

Both flags from the manifest's `override_flags` section must be passed TOGETHER to skip dep checking:
- `--skip-dep-check` (contract-locked name per § Schema reference)
- `--accept-missing-deps-risk` (coord's repo-specific value for `accept_hallucination_risk`)

Passing only one produces an error and exits (mirrors contract exit-code 93 behavior). Read-only flags (`--help`, `--version`, `--phase-list`, `--last-status`, `--check`) are serviced before any dep-walking and do not trigger the override check.

---

## Negative-spec

<!-- negative-spec: this skill does NOT dispatch subagents. coordinator-claude's one direct_dep (claude-klabauter) self-confirms via the claude_klabauter_seam_resolvable probe kind — there is no recursive chain-walk into claude-klabauter's own manifest. The visited-set is initialised for contract-conformance only. -->
<!-- negative-spec: this skill does NOT replace coordinator:install (OSS plugin install of the coordinator package) or coordinator:repo-setup (consumer-project first-time setup). Three distinct verbs, three distinct concerns — see disambiguation prose above. This skill DOES assert, via Probe 0 above, that the plugin is actually reachable — by marketplace registration or by live --plugin-dir resolution — rather than merely enabled by membership; that assertion is in scope here even though performing the registration itself remains coordinator:install's job. -->
<!-- negative-spec: this skill does NOT seed install-leg spinoffs into the install-baton rendezvous (`$(coordinator-settings-home)/state/handoffs/`). Spinoffs are PM-authorized via /spinoff only. -->
<!-- negative-spec: the visited-set path is <settings-home>/coordinator-claude/chain-walk-*.json where <settings-home> = ${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings} — the settings-home prefix is canonical per agent-install-contract.md § Visited-set protocol. -->
