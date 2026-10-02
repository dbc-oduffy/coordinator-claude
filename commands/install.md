---
name: install
description: "Installs the coordinator plugin: prereqs, project config."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive] [--accept-no-git-auth]"
disable-model-invocation: true
---

# Coordinator Install

Guided install — agent runs mechanism, operator decides shape. Re-run anytime; skips what's configured.

## The install: orientation, declared choices, one block

The install is a script with declared choices, `${CLAUDE_PLUGIN_ROOT}/lib/install/coordinator_install.py`. Run it bare (`python3 "${CLAUDE_PLUGIN_ROOT}/lib/install/coordinator_install.py" ...`); the phases further down are the reference for what each step wraps.

1. **Track.** `--plan` reports `environment.track`: `fresh`, `update` or `repair`. The installer decides it; never pick a track by hand. All three continue through steps 2-7, because the installer runs the track's own steps ahead of the configure steps: `fresh` runs `plugin_install`; `update` runs `plugin_update`, `engine_setup`, `engine_check` (with `track_reason: already current`, `plugin_update` drops and the engine steps still run); `repair` runs `engine_setup`, `engine_check`. On `repair`, surface `track_reason` to the operator. Never route `update` to `/coordinator:coordinator-update` or a hand-run `claude plugin update`; the installer performs the update.
2. **Orientation first.** Order: machine wiring, then the tour in a throwaway session, then opt-in repo onboarding (Phase 8). Read the plan's `orientation` text to the operator before asking anything. The posture question below only means something after it.
3. **Plan.** `python3 ".../coordinator_install.py" --plan --permission-mode <mode>` mutates nothing and prints one JSON document: every decision with `id`, `question`, `why`, `options`, `default`, `level`. Pass the session's `permission_mode` from hook input; it adapts defaults (auto, bypass and plan presume the recommended extras and list them at the end as added; default and acceptEdits ask per change and pre-install nothing). Outside auto and bypass, mention shift-tab to auto mode once.
4. **Ask once.** Human path: `--express` takes every recommended default; `--custom` walks the decisions one at a time on stdin, in plain language, and both print the same RAN/SKIPPED/INHERITED/FAILED block. Ask the `question` text verbatim (never paraphrase the posture options) in ONE block, not one prompt per item. `--i-am-agent` (no answers) returns the full plan for an agent to answer on the operator's behalf.
5. **Execute.** `... --answers answers.json` (or inline JSON; `--non-interactive` for declared defaults). One structured block reports every step `RAN`, `SKIPPED` (by answer), `INHERITED` (already true) or `FAILED`; nothing is passed over silently. `--check-drift` fails when the install manifest and the steps disagree.
6. **Report and tour.** Show the block as the status table, list `added_extras`, then run the tour in this session: the block's `tour` array (the plan carries the same text) holds Movements 2-4 (make it yours, take it for a spin, point it at a project). Movement 1 is the `orientation` text already read before the posture question. Speak each movement in plain language, condensed, and work through it with the operator; take the wording from the array and do not paraphrase what it prescribes. An empty `tour` means the operator deferred it. Record `orientation_completed` at the end. `restart_needed` only defers settings env values and MCP registrations to the next session; it never blocks the tour. Run `bin/needs-restart.py`: it prints `none`, `/reload-plugins` or `restart`; act on that verdict, never on a standing mandate.
7. **Show the files.** The `open_claude_home` step opens `~/.claude` in the file manager (`open`, `explorer`, `xdg-open`); a session started from any directory can reach it.

Canonical posture text comes from the script, never from memory. `docs/coordinator-currency.yaml` (the `coordinator_currency` decision, default skip) records which coordinator version a repo was set up against; write it inside a project repo, not the plugin clone. The seeded `~/.claude/CLAUDE.md` is rendered from the answers (`PM_NAME`, `PERMISSION_MODE`, `POSTURE`, `DISPATCH_AND_COMMIT_PREFERENCE`); no `{{...}}` survives a completed install.

Reverses via `coordinator/commands/uninstall.md`, which stays in lockstep: a write surface added here gets its disposition there in the same change.

Fences below name the engine root as `<engine-root>` and the settings-home forwarders by path. Resolve the engine root once with `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_engine_root.py"` and substitute the printed path literally; an empty line means the engine clone is missing (`INSTALL.md` § Step 1e). Forwarders live under `$COORDINATOR_SETTINGS_HOME/bin` (default `~/.coordinator-claude-settings/bin`; `.exe`/`.cmd` on Windows). No fence needs an interpreter variable or command substitution.



---

## Requirements

- bash: no version floor — macOS's stock 3.2 is fine.
- git, Python 3, jq.
- uv (Pipeline D), scc (optional), PowerShell 7+ / Windows Terminal (default-on, not hard blockers).
- Engine repo cloned (hard, not auto-discovered).
- **Sequence, exactly:** (1) install the coordinator plugin; (2) clone the engine repo — a clone, **not** an install; (3) load the plugin into a session (`needs-restart.py` says whether `/reload-plugins` or a restart is needed) — what makes this command exist; (4) run this coordinator install; (5) only then run the engine repo's own installer, from a shell started after (4) so the `machine-local` resolver this command deposits is on PATH. Steps 2 and 5 read as circular only if "clone" and "install" are conflated — they are not the same step, and the engine's installer legitimately depends on coordinator already being installed. Matches `INSTALL.md` § Step 1e / Step 2 / Step 3 / Step 4 exactly; if the two ever disagree, `INSTALL.md` is the source of truth.

## Structural fork

```bash
python3 "<engine-root>/coordinator/lib/detect-existing-claude-home.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\detect-existing-claude-home.py"`

Emits `state=<pristine|used-vanilla|configured>`. This is a disclosure about the operator's existing home only: `state=` (and its `track=` alias) never selects the install track; `environment.track` from `--plan` does. `configured`: surface "existing setup — merge is yours"; else proceed with no/light note. Never clobbers `CLAUDE.md`/`settings.json`/registry regardless of state (wiki).

## Flags

| Flag | Effect |
|---|---|
| `--check-only` | Read-only report — no mutations. |
| `--non-interactive` | Suppresses `AskUserQuestion`; per-site fallback is skip-with-note / default-with-warning / fail-loud (unannotated = fail-loud). |
| `--accept-no-git-auth` | Skips `clone_auth`. |

Both `--check-only`/`--non-interactive` combine freely. Environment-only here — `/coordinator:repo-setup` handles per-project scaffolding after this.

## Phase 1 — Environment

**Bash version.** No floor — any bash, including macOS's stock 3.2, is ready. If `probe_shell_login_env` (`coordinator_core.install.prereq_probe`) reports an orphaned bash login shell (bash login shell, `~/.bash_profile` missing `~/.local/bin`), offer `normalize-env --yes` to reconstruct it — detail: wiki.

If the operator git-tracks `~/.claude`:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/install-meta-repo-precommit-hook" "$HOME/.claude"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\install-meta-repo-precommit-hook.exe" "$HOME\.claude"`

No-ops if not a git repo. Under `--check-only`, don't run it — report gate-marker presence instead.

Git-LFS: report presence only — never `git lfs install` (no flags) against a coordinator-hooked repo: it refuses to overwrite coordinator's own committed hooks and only offers `--force`, which would clobber them, so a per-repo hook install is permanently a no-op here and must not be attempted. Binary present: offer `git lfs install --skip-repo` (global filter config only, never touches repo hooks). Binary absent: advisory per-platform remediation (wiki). Always report which branch ran — never silent.

**Settings env values.** `python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/bin/check-settings-env.py" --apply` asserts `settings.json`'s `env` block against `templates/settings-manifest.md` § Environment Variables — **values, not key presence**: a key at the wrong value gates a tool out of every session on the box while reading as configured. `--apply` writes only the all-machines rows; machine-specific ones are reported, never auto-written. Under `--check-only`, drop `--apply`. Env is read at process start — a repair lands on the next session, not this one.

**Python3.** Resolves and runs `--version`: ready. Not on PATH: fail-loud. Resolves but errors on `--version` (Windows App-Execution-Alias stub): warn — Phase 3 places a real interpreter.

**scc** (optional), **jq** (`command -v jq` — required for JSON output, else text fallback), **pwsh 7+**/**Windows Terminal** (offer install per-platform if absent, interactive only; commands: wiki) — presence checks only, no branch beyond offer-or-skip.

**NotebookLM (Pipeline D).** Check whether `notebooklm-mcp` is registered in `~/.claude/settings.json` / `~/.claude.json` / `.mcp.json`. Not registered, interactive, `uv` present: offer to walk:

Install the CLI:

```bash
uv tool install notebooklm-mcp-cli
```

Authenticate:

```bash
nlm login
```

Register the MCP server:

```bash
nlm setup add claude-code
```

Then run `needs-restart.py` for the reload-or-restart verdict. `uv` absent: offer defaults to decline. `--non-interactive`/`--check-only`: skip.

**Global CLAUDE.md.** No manual wiring — doctrine reaches the EM via SessionStart hook. Flag a stale `@…/coordinator/CLAUDE.md` import for removal if present.

## Phase 2 — Operator identity

Read `~/.claude/coordinator-identity.yaml`. `operator_name` present: use it. Absent (or `--reconfigure`): ask via `AskUserQuestion`. `--non-interactive` with none stored: fail-loud.

`--claude-home` takes the resolved `${CLAUDE_HOME:-$HOME}`, never `$HOME/.claude` — the op appends `.claude` itself, so passing the deeper path writes to `~/.claude/.claude/` and the file the next run reads stays absent.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}" --operator-name "${OPERATOR_NAME}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\write-identity-file.exe" --claude-home "$HOME" --operator-name "$OPERATOR_NAME"`

Skip under `--check-only`. Then seed the global CLAUDE.md:
```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/render-template" "${CLAUDE_PLUGIN_ROOT}/templates/CLAUDE.md.tmpl" -o "${CLAUDE_HOME:-$HOME}/.claude/CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" PM_NAME="${OPERATOR_NAME}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\render-template.exe" "$env:CLAUDE_PLUGIN_ROOT\templates\CLAUDE.md.tmpl" -o "$HOME\.claude\CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" "PM_NAME=$OPERATOR_NAME"`

Never-clobber is the `--guard-sentinel` flag's own contract (exit 3 = hand-authored file preserved, skip). No `--check-only` flag on the primitive — skip the call there instead.

**Navi nudge role.** `render-template` never mkdirs and `~/.claude/agents/` will not exist on a fresh box — create it first, then render the role, same guard-sentinel contract as the CLAUDE.md seed above. Skip both calls under `--check-only`.

```bash
mkdir -p "${CLAUDE_HOME:-$HOME}/.claude/agents"
```

Then render the role into it:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/render-template" "${CLAUDE_PLUGIN_ROOT}/templates/agents/navi.md" -o "${CLAUDE_HOME:-$HOME}/.claude/agents/navi.md" --guard-sentinel "coordinator:navi-role:v1"
```

PowerShell host (rung 0): `New-Item -ItemType Directory -Force "$HOME\.claude\agents" | Out-Null`
    `& "$env:COORDINATOR_SETTINGS_HOME\bin\render-template.exe" "$env:CLAUDE_PLUGIN_ROOT\templates\agents\navi.md" -o "$HOME\.claude\agents\navi.md" --guard-sentinel "coordinator:navi-role:v1"`

**Engagement posture (mandatory gate, both modes).** Asked by the install script (`posture` decision, canonical text in the plan); `--non-interactive` uses its default. Reuse the identity read; `engagement_posture` present: use it. The choice persists machine-wide in the identity file, with an optional `posture_text` the overlay render composes in; the per-repo overlay is Phase 8.


Persist the posture to the identity file:
```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}" --operator-name "${OPERATOR_NAME}" --engagement-posture "${ENGAGEMENT_POSTURE}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\write-identity-file.exe" --claude-home "$HOME" --operator-name "$OPERATOR_NAME" --engagement-posture "$ENGAGEMENT_POSTURE"`

```bash
python3 "<engine-root>/coordinator/lib/discover-working-repos.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\discover-working-repos.py"`

→ `WORKING_REPOS` (Tier A/B; Tier C asks if empty and interactive). Prints only; nothing writes `~/.claude/working-repos.yaml`. `--check-only`: no Tier C.

```bash
python3 "<engine-root>/coordinator/lib/register-discovered-repos.py" ${ARGUMENTS}
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\register-discovered-repos.py" $ARGUMENTS`

The persistence for `WORKING_REPOS`: only-if-absent, tier-gated registration into the machine-local `repos.*` registry.

## Phase 3 — Machine-local registry substrate

Idempotent throughout; skip mutations under `--check-only`; never overwrite an existing `registry.toml`/`registry.local.toml`. `install-substrate.py`, `register-coordinator-mirror.py`, and `check-install-singularity.py` below derive their plugin root from their own on-disk location — since they live in the engine repo, that resolution is wrong; set `CLAUDE_PLUGIN_ROOT` explicitly (the harness-provided value from line 116's `render-template` fence) before calling any of the three.

```bash
python3 "<engine-root>/coordinator/lib/install-substrate.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\install-substrate.py"`

Writes the settings-home forwarders themselves (not one itself). Also builds the coordinator venv and ensures `claude` CLI's dir is on shell PATH. Re-run this exact call to repair a broken venv.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/install-health-run" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\install-health-run.exe" $ARGUMENTS`

Runs `bin/install-health/*.sh`, each self-gating; aggregates failures without aborting on first.


Optional interactive seed prompt (declinable, skipped if a registry file already exists): offers to seed the standard `repos.*` keys and machine/contributor slugs via `machine-local set`.


```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/gen-settings-hooks" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\gen-settings-hooks.exe" $ARGUMENTS`


```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/seed-marketplace-enabledplugins" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\seed-marketplace-enabledplugins.exe" $ARGUMENTS`

Merge-never-clobber against `settings.json` ∪ `settings.local.json`; only `true` is ever written.

`~/.claude/plugins/` stays thin under this shape (pointer/config only, no plugin-source byte-copy) automatically — no separate mutation, verified by the singularity gate below.


```bash
python3 "<engine-root>/coordinator/lib/register-coordinator-mirror.py" ${ARGUMENTS}
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\register-coordinator-mirror.py" $ARGUMENTS`

**No canonical-structure scaffold runs here** — `~/.claude` is not a project repo, and
`guard-repo-setup-claude-home-refusal` refuses it; per-project scaffolding is
`/coordinator:repo-setup`'s. Report this step as guard-blocked/no-op.

```bash
python3 "<engine-root>/coordinator/lib/check-install-singularity.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\check-install-singularity.py"`

Verifies exactly one canonical coordinator tree; non-zero exit is a genuine accidental split — print remediation. Exempt: an explicitly-exported `COORDINATOR_CLONE`/`COORDINATOR_ROOT` dev override.

Writes the fan-out soft-threshold (`--check-only` as sole arg for a dry report):

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/capture-fan-out-threshold"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\capture-fan-out-threshold.exe"`

Closes the `/plugin` marketplace-corruption window before the operator's first new session:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/run-platform-localize" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\run-platform-localize.exe" $ARGUMENTS`

## Phase 4 — Meta-repo doctrine

`git -C ~/.claude rev-parse --show-toplevel`. Not a repo, interactive, not `--check-only`: offer to `git init ~/.claude` + starter `.gitignore` (derived from `templates/dotgitignore.tmpl` at that moment) + initial commit — never creates a remote or pushes. Is a repo: run `<plugin-root>/bin/check-gitignore-template-drift.py` --apply — it owns deriving the live-`.gitignore`-vs-`templates/dotgitignore.tmpl` diff and applying it, on both this install run and its own recurring ceremony-gate cadence. **This call is the ONLY delivery path an existing install has** for a template rule added after `git init` laid the starter file down, since that starter file is never re-applied outside this gate. **Derive the list from the template; never hardcode one here** — a fixed enumeration has to be extended by whoever next edits the template, which is a rule discharged by memory, and memory is what failed: the box that AUTHORS the template was measured nine rules behind it, including the shape-matched credential rules (`*-token-key`, `*-token.json`, `*.pem`) that exist so a plugin installed later is covered the day it first writes a key — deriving from `templates/dotgitignore.tmpl` propagates every future rule with nothing to remember. Then `git rm --cached` anything already tracked despite a newly-added rule. Two entries the gate's diff surfaces are not plain appends and need naming here: Probe the auto-memory re-inclusion too (`projects/**` plus its three `!` lines): an operator whose `.gitignore` carries a bare `projects/` is silently discarding the auto-memory store the workstream-complete drain gate empties to zero at every close. **This one entry is REPLACE, not append — appending is inert.** Delete the existing bare `projects/` line and write the four-line chain in its place: git does not descend into an excluded directory, so a chain appended BELOW a surviving `projects/` is never reached and stages nothing, which is the exact silent failure the probe is here to repair. Every existing install is in that state by construction. Then `git add` the store — an ignore FIX does not retroactively track what was never committed. Warn the operator that the store becomes committed content: it is model-authored prose about their work, so it wants a read-through before any remote is added. Full policy and rationale: `coordinator/docs/wiki/claude-md-surfaces/claude-home-tracking-policy.md`. Anchor the last two (`/machine-local`, `/.claude/`) — a tracked `machine-local` is re-materialised as a real directory on every checkout, which permanently blocks Phase 3's settings-home migration from reaching its terminal symlink and ships one box's resolved pointers to every peer machine. Write `/machine-local` with NO trailing slash: `dir/` matches only a real directory, so the slashed form walks past the symlink the path becomes once that migration completes — the rule reads as present and matches nothing.

## Phase 5 — Install-clone gate

Repo onboarding (Phase 8) runs only when cwd is a repo the operator chose to onboard. Skip Phase 8 entirely, writing nothing, when cwd is the plugin or engine clone (its toplevel equals `CLAUDE_PLUGIN_ROOT`, the resolved engine root, or `repos.claude_klabauter`) or when cwd is not inside a git repo. The install clone is never a working repo: it gets no `em-context.md` overlay, no `installed_repos` entry, no `coordinator.local.md`, and no git perf config.

## Phase 6 — Optional

**Persona customization.** `--check-only`/`--non-interactive`: keep defaults. Interactive: offer **Customize** (runs `name-personas.sh`, reversible; exclude the engine repo's `publish-time-transform-py` from search-replace).


**Git Bash fast profile.** Windows only — a POSIX host has no Git-for-Windows `/etc/profile`
and skips silently. The Bash tool invokes `bash -c -l`, so the stock profile is sourced and
discarded once per Bash call — ~800ms measured, and the tool's own contract states shell state
does not persist between calls. The block reproduces that environment spawn-free, gated on a
non-interactive shell carrying `CLAUDECODE`, so an interactive Git Bash keeps its prompt.

    `& python3 "$env:CLAUDE_PLUGIN_ROOT\templates\bin\install-git-bash-fast-profile.py" --check`

Exits 0 installed, 1 absent, 2 if Git's `/etc/profile` is unlocatable. `--check-only`/
`--non-interactive`: report only. Interactive on rc 1: hand the operator the same command
without `--check` to run **elevated** — `/etc/profile` is inside the Git install root, so this
step cannot self-elevate and is never reported as done. Re-offer every run; a Git update
removes the block silently.

**Percolation setup.** A `coordinator/bin/publish.py` file in the repo under setup AND a `setup/` dir both present → percolation source; else skip. No targets registered: walk detect/scaffold → register target → author `.percolate-ignore` → scaffold hook dirs, interactively.

## Phase 7 — Status Report

The engine installer writes the `setup_concluded` receipt at the end of a completed run; this phase records nothing for it.

Present the script block as the status table, one row per step. Status vocabulary: `RAN` | `SKIPPED` (mode-gated, e.g. `--check-only`) | `DISABLED` (a deliberate operator opt-out marker, e.g. `~/.claude/.coordinator-hooks-disabled` — distinct from a failure) | `INHERITED` (the step's target already held the right value before this run, rather than being freshly written by it — never collapse this into a bare pass: presence is not provenance, and a crashed writer that left a correct pre-existing value must read differently from one that actually ran). Not `--check-only`: offer a guided walkthrough (four movements — Orient, make `~/.claude/CLAUDE.md` yours, test-drive in a throwaway directory, then opt-in onboarding of a chosen repo via `/coordinator:repo-setup` or `/coordinator:new-project`; text: the script block's `tour` array, narrated by `coordinator/docs/wiki/install-playbook-rationale/getting-started.md`):

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/coordinator-setup-state" record orientation_started
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-setup-state.exe" record orientation_started`

Record `orientation_completed` at the end. Standing sign-off note and the `/coordinator:repo-setup` bootstrap offer (gated on `repos.*` having ≥1 newly-registered entry from this run, not a `working-repos.yaml` file — none is written): wiki.

**Terminal message.** Report the script block, then continue into the block's `tour` Movements 2-4 in this session. Say "restart" only when `needs-restart.py` prints `restart`, and then as "settings env values apply next session", not as a gate.

## Phase 8 — Repo onboarding (opt-in, after the tour)

Runs when the operator picks a repo in tour Movement 4 and Phase 5's gate passes; `--check-only` and `--non-interactive` skip it.

**Git.** `git rev-parse --show-toplevel` — not a repo: warn, proceed.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/coordinator-configure-git"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-configure-git.exe"`

Sets `gc.auto 0`/`core.checkStat minimal`/`maintenance.strategy incremental`/
`maintenance.auto false`/`maintenance.prefetch.enabled false`; idempotent; skip under
`--check-only`.
**Cwd repo only** — it takes no repo argument, and Phase 5's gate has already excluded the install clone.

```bash
git rev-parse --show-toplevel 2>/dev/null
```
→ `_EM_CONTEXT_REPO_ROOT`.

```bash
python3 "<engine-root>/coordinator/bin/coordinator-resolve-validation-cmd.py" --read-key "${_EM_CONTEXT_REPO_ROOT}" engagement_posture
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\bin\coordinator-resolve-validation-cmd.py" --read-key $PWD engagement_posture`

Differs from the identity-file value: fail-loud, don't write the overlay. Empty output (repo has no posture set): not a difference — proceed, treat as absent.

Render the overlay:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/render-posture-overlay" "${ENGAGEMENT_POSTURE}" "${_EM_CONTEXT_REPO_ROOT}/.claude/em-context.md"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\render-posture-overlay.exe" "$ENGAGEMENT_POSTURE" "$_EM_CONTEXT_REPO_ROOT\.claude\em-context.md"`

`--check-only`: append `--check-only` to the overlay call, writes nothing. `_EM_CONTEXT_REPO_ROOT` is empty: Phase 5's gate already skipped this phase.

```bash
git -C "${_EM_CONTEXT_REPO_ROOT}" check-ignore -q .claude/em-context.md
```

Exit 1: append (via Edit, never a shell redirect) to `.gitignore`:
```text
# Operator-local EM posture overlay — per-operator, never shared.
.claude/em-context.md
```
Exit >1: fail-loud, don't append. Already tracked: tell the operator to `git rm --cached` it.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/machine-local" array-append coordinator.installed_repos "${_EM_CONTEXT_REPO_ROOT}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\machine-local.cmd" array-append coordinator.installed_repos "$_EM_CONTEXT_REPO_ROOT"`

Skip under `--check-only`. A repo onboarded later re-renders this overlay via `repo-setup` from the persisted value (wiki).

`test -f coordinator.local.md`. Exists: report `project_type` (flag legacy values for manual migration). Missing, not `--check-only`: `--non-interactive` fails loud (no safe default); interactive asks `project_type`/subtypes, writes:

```markdown
---
project_type: {type}
project_subtypes: [{subtype1}, {subtype2}]   # omit field when blank
fast_test_cmd: "<your-project-fast-test-command>"  # optional, single command only
terminal_test_cmd: "<your-project-terminal-test-command>"  # optional, single command only; run verbatim by the terminal commit gate
---
```

```bash
python3 "<engine-root>/coordinator/lib/coordinator_currency.py" write "$PWD" "${CLAUDE_PLUGIN_ROOT}"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\coordinator_currency.py" write "$PWD" "$env:CLAUDE_PLUGIN_ROOT"`
