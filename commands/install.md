---
name: install
description: "Installs the coordinator plugin: prereqs, project config."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "AskUserQuestion"]
argument-hint: "[--check-only] [--non-interactive] [--accept-no-git-auth]"
---

# Coordinator Install

Guided install: agent runs mechanism, operator decides shape. Re-run anytime.

## The install: orientation, declared choices, one block

The install is a script with declared choices: `python3 "${CLAUDE_PLUGIN_ROOT}/lib/install/coordinator_install.py" ...`, run bare. The phases below are the reference for what each step wraps.

1. **Track.** `--plan` reports `environment.track`: `fresh`, `update` or `repair`; never pick one by hand. All three continue through steps 2-7: `fresh` runs `plugin_install`; `update` runs `plugin_update`, `engine_setup`, `engine_check` (`track_reason: already current` drops `plugin_update`); `repair` runs `engine_setup`, `engine_check`. On `repair`, surface `track_reason`. Never route `update` to `/coordinator:coordinator-update` or a hand-run `claude plugin update`. A model may run this command when the PM's turn states install intent; `plugin_update` stays gated: a model-invoked run answers it SKIPPED and tells the operator to type `/coordinator:install`.
2. **Orientation first.** Order: machine wiring, the tour inline in this session, then opt-in repo onboarding (Phase 8). Read the plan's `orientation` text to the operator before asking anything.
3. **Plan.** `python3 ".../coordinator_install.py" --plan --permission-mode <mode>` mutates nothing and prints one JSON document: every decision with `id`, `question`, `why`, `options`, `default`, `level`. Pass the session's `permission_mode` (auto, bypass and plan presume the recommended extras and list them as added; default and acceptEdits ask per change). Outside auto and bypass, mention shift-tab to auto mode once.
4. **Ask once.** Human path: `--express` takes every recommended default; `--custom` walks the decisions on stdin; both print the same RAN/SKIPPED/INHERITED/FAILED block. Ask the `question` text verbatim (never paraphrase the posture options) in ONE block. `--i-am-agent` (no answers) returns the full plan for an agent to answer for the operator.
5. **Execute.** `... --answers answers.json` (or inline JSON; `--non-interactive` for declared defaults). The answers document is one flat JSON object keyed by the decision `id`s from `--plan` (never question or option text); each value is one of that decision's `options` (for `posture`, the option id before the colon), or free text where the options are `<free text>`. Omitted ids take their `default`; an unknown id or out-of-set value is reported and nothing runs. One block reports every step `RAN`, `SKIPPED` (by answer), `INHERITED` (already true) or `FAILED`. `--check-drift` fails when the install manifest and the steps disagree.
6. **Report and tour.** Show the block as the status table, list `added_extras`, then run the tour in this session: the block's `tour` array holds Movements 2-4 (make it yours, take it for a spin, point it at a project); Movement 1 is the `orientation` text already read. Speak each movement in plain language, with the array's wording. An empty `tour` means deferred. Record `orientation_completed` at the end. `restart_needed` only defers settings env values and MCP registrations; it never blocks the tour. Run `bin/needs-restart.py` (prints `none`, `/reload-plugins` or `restart`) and act on that verdict.
7. **Show the files.** The `open_claude_home` step opens `~/.claude` in the file manager.

Canonical posture text comes from the script, never from memory. `docs/coordinator-currency.yaml` (the `coordinator_currency` decision, default skip) records the coordinator version a repo was set up against; write it in a project repo, not the plugin clone. The seeded `~/.claude/CLAUDE.md` is rendered from the answers (`PM_NAME`, `PERMISSION_MODE`, `POSTURE`, `DISPATCH_AND_COMMIT_PREFERENCE`); no `{{...}}` survives.

Reverses via `coordinator/commands/uninstall.md`, in lockstep; a write surface added here gets its disposition there in the same change.

Resolve `<engine-root>` once with `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_engine_root.py"` and substitute the printed path literally; exit 2 naming a missing registry key means the engine clone is unregistered (`INSTALL.md` § Step 1e): stop and report, never guess a path. Forwarders live under `$COORDINATOR_SETTINGS_HOME/bin` (default `~/.coordinator-claude-settings/bin`; `.exe`/`.cmd` on Windows).



---

## Requirements

- bash: no version floor — macOS's stock 3.2 is fine.
- git, Python 3, jq.
- uv (Pipeline D), scc (optional), Windows Terminal (default-on, not a blocker).
- Windows: PowerShell 7 is a prerequisite (see the pwsh 7 check below).
- Engine repo cloned (hard, not auto-discovered).
- **Sequence, exactly:** (1) install the coordinator plugin; (2) clone the engine repo — a clone, **not** an install; (3) load the plugin into a session (`needs-restart.py` says `/reload-plugins` or restart); (4) run this coordinator install; (5) only then run the engine repo's own installer, from a shell started after (4) so the `machine-local` resolver is on PATH. Matches `INSTALL.md` § Step 1e / Step 2 / Step 3 / Step 4; on disagreement `INSTALL.md` is the source of truth.

## Structural fork

```bash
python3 "<engine-root>/coordinator/lib/detect-existing-claude-home.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\detect-existing-claude-home.py"`

Emits `state=<pristine|used-vanilla|configured>`: a disclosure only; `state=` (and its `track=` alias) never selects the install track, `environment.track` does. `configured`: surface "existing setup — merge is yours"; else proceed with no/light note. Never clobbers `CLAUDE.md`/`settings.json`/registry (wiki).

## Flags

| Flag | Effect |
|---|---|
| `--check-only` | Read-only report — no mutations. |
| `--non-interactive` | Suppresses `AskUserQuestion`; per-site fallback is skip-with-note / default-with-warning / fail-loud (unannotated = fail-loud). |
| `--accept-no-git-auth` | Skips `clone_auth`. |

The flags combine freely. Environment-only here; `/coordinator:repo-setup` does per-project scaffolding.

## Phase 1 — Environment

**Bash version.** No floor — any bash, including macOS's stock 3.2. If `probe_shell_login_env` (`coordinator_core.install.prereq_probe`) reports an orphaned bash login shell (`~/.bash_profile` missing `~/.local/bin`), offer `normalize-env --yes` — detail: wiki.

If the operator git-tracks `~/.claude`:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/install-meta-repo-precommit-hook" "$HOME/.claude"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\install-meta-repo-precommit-hook.exe" "$HOME\.claude"`

No-ops if not a git repo. Under `--check-only`, report gate-marker presence instead.

Git-LFS: opt-in per repo (root `.gitattributes` `filter=lfs` pattern plus `# lfs-justification: <reason>`); the installer never enables it.

**Settings env values.** `python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/bin/check-settings-env.py" --apply` asserts `settings.json`'s `env` block against `templates/settings-manifest.md` § Environment Variables — **values, not key presence**. `--apply` writes only the all-machines rows and removes retired keys; machine-specific ones are reported, never auto-written. `--check-only`: drop `--apply`. Lands next session.

**Cross-session inbound.** Seeds `crossSessionInbound` to `"accept"` if absent:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/bin/seed-cross-session-inbound.py" --apply "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
```

PowerShell host: set `$cfg = if (-not $env:CLAUDE_CONFIG_DIR) { "$HOME\.claude" } else { $env:CLAUDE_CONFIG_DIR }`, then run `python3 "$env:CLAUDE_PLUGIN_ROOT\bin\seed-cross-session-inbound.py" --apply "$cfg\settings.json"`. Under `--check-only`, use `--check`. Lands next session; rationale: `inbound-peer-attention-control.md`.

**Python3.** Runs `--version`: ready. Not on PATH: fail-loud. Errors on `--version` (Windows App-Execution-Alias stub): warn; Phase 3 places a real interpreter.

**scc** (optional), **jq** (`command -v jq`; required for JSON output, else text fallback), **Windows Terminal** (offer install if absent, interactive only; commands: wiki) — presence check only. **pwsh 7 (Windows prerequisite):** check for `%ProgramFiles%\PowerShell\7\pwsh.exe`; when missing, print `winget install --id Microsoft.PowerShell --source winget --scope machine --installer-type wix`.

**NotebookLM (Pipeline D).** Check whether `gemini-notebook-mcp` is registered in `~/.claude/settings.json` / `~/.claude.json` / `.mcp.json`. Registered: ready. Absent: print one line, `NotebookLM (optional, deep-research Pipeline D): install and sign in per https://github.com/jacob-bd/gemini-notebook-mcp-cli (its README covers `nlm login` and registration; install per NLM-PREFLIGHT: user site of the OS's system or package-manager python3, no venv, never a pyenv or project interpreter)`, and move on. Install target (any later install into a shared interpreter can break its deps): macOS `python3 -m pip install --user --break-system-packages notebooklm-mcp-cli` with Homebrew python3; Linux `python3 -m pip install --user notebooklm-mcp-cli` with the distro python3 (add `--break-system-packages` on a PEP-668 distro); Windows `py -3 -m pip install --user notebooklm-mcp-cli` with the python.org install. Register the `notebooklm-mcp` script that lands in that user site's scripts directory (`bin` on POSIX, `Scripts` on Windows), with `env: {"NLM_AUTH_STORAGE": "file"}`; sign in with `nlm login --storage file` (browser login, never the Keychain-backed `protected` mode). Verify with `nlm-preflight.py`. This install runs no NotebookLM command, makes no offer and no restart call.

**Global CLAUDE.md.** No manual wiring — doctrine reaches the EM via SessionStart hook. Flag a stale `@…/coordinator/CLAUDE.md` import for removal.

## Phase 2 — Operator identity

Read `~/.claude/coordinator-identity.yaml`. `operator_name` present: use it. Absent (or `--reconfigure`): ask via `AskUserQuestion`. `--non-interactive` with none stored: fail-loud.

`--claude-home` takes the resolved `${CLAUDE_HOME:-$HOME}`, never `$HOME/.claude` — the op appends `.claude` itself.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}" --operator-name "${OPERATOR_NAME}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\write-identity-file.exe" --claude-home "$HOME" --operator-name "$OPERATOR_NAME"`

**Dev-repo box:** the authoring repo root carries `.coordinator-dev-repo` → skip the backup and the seed below on both the POSIX and PowerShell forms and report them `SKIPPED`: `~/.claude/CLAUDE.md` is re-derived from the authoring repo's global doctrine, so a write there is lost. Owner text is authored in that source. See claude-md-surfaces § Direction of truth.

Skip under `--check-only`. Then back up any global CLAUDE.md lacking the seed sentinel, no-clobber (first copy kept):
```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/backup-global-claude-md" --claude-home "${CLAUDE_HOME:-$HOME}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\backup-global-claude-md.exe" --claude-home "$HOME"`

Then seed the global CLAUDE.md:
```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/render-template" "${CLAUDE_PLUGIN_ROOT}/templates/CLAUDE.md.tmpl" -o "${CLAUDE_HOME:-$HOME}/.claude/CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" PM_NAME="${OPERATOR_NAME}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\render-template.exe" "$env:CLAUDE_PLUGIN_ROOT\templates\CLAUDE.md.tmpl" -o "$HOME\.claude\CLAUDE.md" --guard-sentinel "coordinator:claude-md-seed:v1" "PM_NAME=$OPERATOR_NAME"`

Never-clobber is `--guard-sentinel`'s contract (exit 3 = hand-authored file preserved, skip). No `--check-only` flag: skip the call.

**Engagement posture (mandatory gate, both modes).** Asked by the install script (`posture` decision); `--non-interactive` uses its default. `engagement_posture` present in the identity file: use it. It persists machine-wide there, with an optional `posture_text` the overlay render composes in; the per-repo overlay is Phase 8.

Persist the posture to the identity file:
```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/write-identity-file" --claude-home "${CLAUDE_HOME:-$HOME}" --operator-name "${OPERATOR_NAME}" --engagement-posture "${ENGAGEMENT_POSTURE}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\write-identity-file.exe" --claude-home "$HOME" --operator-name "$OPERATOR_NAME" --engagement-posture "$ENGAGEMENT_POSTURE"`

```bash
python3 "<engine-root>/coordinator/lib/discover-working-repos.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\discover-working-repos.py"`

→ `WORKING_REPOS` (Tier A/B; Tier C asks if empty and interactive). Prints only; writes no `~/.claude/working-repos.yaml`. `--check-only`: no Tier C.

```bash
python3 "<engine-root>/coordinator/lib/register-discovered-repos.py" ${ARGUMENTS}
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\register-discovered-repos.py" $ARGUMENTS`

Persists `WORKING_REPOS`: only-if-absent, tier-gated, into the `repos.*` registry.

## Phase 3 — Machine-local registry substrate

Idempotent; no mutations under `--check-only`; never overwrite an existing `registry.toml`/`registry.local.toml`. `install-substrate.py`, `register-coordinator-mirror.py`, and `check-install-singularity.py` derive their plugin root from their own location, wrong from the engine repo; set `CLAUDE_PLUGIN_ROOT` explicitly (the harness-provided value from the `render-template` fence) before calling any of the three.

```bash
python3 "<engine-root>/coordinator/lib/install-substrate.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\install-substrate.py"`

Writes the settings-home forwarders and ensures `claude` CLI's dir is on shell PATH. Re-run to repair a broken forwarder.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/install-health-run" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\install-health-run.exe" $ARGUMENTS`

Runs `bin/install-health/*.sh`, each self-gating; aggregates failures.


Optional interactive seed prompt (declinable, skipped if a registry file exists): seeds the standard `repos.*` keys and machine/contributor slugs via `machine-local set`.


```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/gen-settings-hooks" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\gen-settings-hooks.exe" $ARGUMENTS`


```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/seed-marketplace-enabledplugins" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\seed-marketplace-enabledplugins.exe" $ARGUMENTS`

Merges against `settings.json` ∪ `settings.local.json`; only `true` is ever written.

`~/.claude/plugins/` stays thin (pointer/config only) with no separate mutation, verified by the singularity gate below.


```bash
python3 "<engine-root>/coordinator/lib/register-coordinator-mirror.py" ${ARGUMENTS}
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\register-coordinator-mirror.py" $ARGUMENTS`

**No canonical-structure scaffold runs here** — `~/.claude` is not a project repo (`guard-repo-setup-claude-home-refusal` refuses it); scaffolding is `/coordinator:repo-setup`'s. Report this step as guard-blocked/no-op.

```bash
python3 "<engine-root>/coordinator/lib/check-install-singularity.py"
```

PowerShell host (rung 0): `& python3 "<engine-root>\coordinator\lib\check-install-singularity.py"`

Verifies exactly one canonical coordinator tree; non-zero exit is an accidental split — print remediation. Exempt: an exported `COORDINATOR_CLONE`/`COORDINATOR_ROOT` dev override.

Writes the fan-out soft-threshold (`--check-only` alone for a dry report):

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/capture-fan-out-threshold"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\capture-fan-out-threshold.exe"`

Closes the `/plugin` marketplace-corruption window before the first new session:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/run-platform-localize" ${ARGUMENTS}
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\run-platform-localize.exe" $ARGUMENTS`

## Phase 4 — Meta-repo doctrine

`git -C ~/.claude rev-parse --show-toplevel`. Not a repo, interactive, not `--check-only`: offer to `git init ~/.claude` + starter `.gitignore` (derived from `templates/dotgitignore.tmpl` at that moment) + initial commit — never creates a remote or pushes. Is a repo: run `<plugin-root>/bin/check-gitignore-template-drift.py` --apply — it derives the live-`.gitignore`-vs-`templates/dotgitignore.tmpl` diff and applies it, on this run and on its ceremony-gate cadence. **This call is the ONLY delivery path an existing install has** for a template rule added after `git init` laid the starter file down. **Derive the list from the template; never hardcode one here** — a fixed enumeration is a rule discharged by memory, and the template's own box was measured nine rules behind it. Then `git rm --cached` anything already tracked despite a newly-added rule. Two entries are not plain appends. Probe the auto-memory re-inclusion (`projects/**` plus its three `!` lines): a `.gitignore` carrying a bare `projects/` silently discards the auto-memory store the workstream-complete drain gate empties at every close. **This one entry is REPLACE, not append — appending is inert.** Delete the bare `projects/` line and write the four-line chain in its place: git does not descend into an excluded directory, so a chain appended BELOW a surviving `projects/` stages nothing. Then `git add` the store (an ignore fix does not retroactively track it) and warn the operator it becomes committed content wanting a read-through before any remote is added. Policy: `coordinator/docs/wiki/claude-md-surfaces/claude-home-tracking-policy.md`. Anchor the last two (`/machine-local`, `/.claude/`): a tracked `machine-local` is re-materialised as a real directory on every checkout and blocks Phase 3's settings-home migration. Write `/machine-local` with NO trailing slash: `dir/` matches only a real directory, so the slashed form misses the symlink the path becomes.

## Phase 5 — Install-clone gate

Skip Phase 8 entirely when cwd is the plugin or engine clone (its toplevel equals `CLAUDE_PLUGIN_ROOT`, the resolved engine root, or `repos.claude_klabauter`) or not inside a git repo. The install clone is never a working repo: no `em-context.md` overlay, no `installed_repos` entry, no `coordinator.local.md`, no git perf config.

## Phase 6 — Optional

**Persona customization.** `--check-only`/`--non-interactive`: keep defaults. Interactive: offer **Customize** (runs `name-personas.sh`, reversible; exclude the engine repo's `publish-time-transform-py`).


**Git Bash fast profile.** Windows only; a POSIX host skips silently. The block reproduces the Bash tool's `bash -c -l` profile spawn-free (~800ms saved per call), gated on a non-interactive shell carrying `CLAUDECODE`.

    `& python3 "$env:CLAUDE_PLUGIN_ROOT\templates\bin\install-git-bash-fast-profile.py" --check`

Exits 0 installed, 1 absent, 2 if Git's `/etc/profile` is unlocatable. `--check-only`/`--non-interactive`: report only. On rc 1, interactive: hand over the command without `--check` to run **elevated** (never reported as done); re-offer every run.

**BoxCacheTrim (Windows, opt-in).** Default **not installed**. Registers a trigger-less, highest-run-level scheduled task `BoxCacheTrim` so a non-elevated session can run the elevated `trim-file-cache --apply` via `schtasks /Run /TN BoxCacheTrim`.

    `& python "$env:CLAUDE_PLUGIN_ROOT\templates\bin\install-box-cache-trim-task.py" --check`

Exits 0 installed, 1 absent or stale, 2 not Windows. `--check-only`/`--non-interactive`: report only. Interactive on rc 1: ask "Install BoxCacheTrim? [y/N]" (default N); on Y hand the operator the command with `--install` for `--check`, to run **elevated**; rc 3 means "re-run elevated", never "done".

**Codex and agy hosts.** Opt-in; `--check-only` reports only, `--non-interactive` skips. Not the Codex reviewer integration. Offer it when `codex` or `agy` is on PATH. Prerequisite: the engine (`claude-klabauter`), which ships the guard shim. Interactive on Y:

`"$_py" "$CLAUDE_PLUGIN_ROOT/bin/unimatrix-install.py" --install --hosts codex,agy`, where `$_py` is the interpreter resolved per `snippets/resolve-coordinator-bin.md`.

PowerShell host (rung 0): `& python3 "$env:CLAUDE_PLUGIN_ROOT\bin\unimatrix-install.py" --install --hosts codex,agy`

It seeds the `coordinator-doctrine` block into `$CODEX_HOME/AGENTS.md` and `~/.gemini/GEMINI.md`, seeds skills, and registers one guard `PreToolUse` hook per host plus peer registration. Report `governance verification FAILED` or `governance DEGRADED: engine root unresolved` verbatim; neither is a pass. Limits and the trust step: `INSTALL.md` § Codex and agy hosts.

**Percolation setup.** A `coordinator/bin/publish.py` AND a `setup/` dir in the repo under setup → percolation source; else skip. No targets registered: walk detect/scaffold → register target → author `.percolate-ignore` → scaffold hook dirs, interactively.

## Phase 7 — Status Report

The engine installer writes the `setup_concluded` receipt; this phase records nothing for it.

When `gemini-notebook-mcp` is registered, run `python3 coordinator/pipelines/deep-research/notebooklm/nlm-preflight.py` (NLM-PREFLIGHT) and show its `ok` and `remedy` with the table. Present the script block as the status table. Statuses: `RAN` | `SKIPPED` (mode-gated, e.g. `--check-only`) | `DISABLED` (a deliberate operator opt-out marker, e.g. `~/.claude/.coordinator-hooks-disabled`; not a failure) | `INHERITED` (the target already held the right value before this run; never collapse into a bare pass: presence is not provenance). Not `--check-only`: offer a guided walkthrough (four movements — Orient, make `~/.claude/CLAUDE.md` yours (on a dev-repo box, author the authoring repo's global doctrine instead), test-drive inline against `repos.general_work` or a repo the operator picks, then opt-in onboarding of a chosen repo via `/coordinator:repo-setup` or `/coordinator:new-project`; text: the block's `tour` array, narrated by `coordinator/docs/wiki/install-playbook-rationale/getting-started.md`):

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/coordinator-setup-state" record orientation_started
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-setup-state.exe" record orientation_started`

Record `orientation_completed` at the end. Sign-off note and the `/coordinator:repo-setup` bootstrap offer (gated on `repos.*` having ≥1 newly-registered entry from this run): wiki.

**Terminal message.** Report the script block, then continue into the `tour` Movements 2-4. Say "restart" only when `needs-restart.py` prints `restart`, as "settings env values apply next session", not as a gate.

## Phase 8 — Repo onboarding (opt-in, after the tour)

Runs when the operator picks a repo in tour Movement 4 and Phase 5 passes; `--check-only`/`--non-interactive` skip it.

**Git.** `git rev-parse --show-toplevel` — not a repo: warn, proceed.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/coordinator-configure-git"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-configure-git.exe"`

Sets `gc.auto 0`/`core.checkStat minimal`/`maintenance.strategy incremental`/
`maintenance.auto false`/`maintenance.prefetch.enabled false`; idempotent; skip under
`--check-only`. **Cwd repo only** (no repo argument; Phase 5 excluded the install clone).

```bash
git rev-parse --show-toplevel 2>/dev/null
```
→ `_EM_CONTEXT_REPO_ROOT`.

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-resolve-validation-cmd" --read-key "${_EM_CONTEXT_REPO_ROOT}" engagement_posture
```

PowerShell host: the same arguments to `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-resolve-validation-cmd.exe"`.

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-resolve-validation-cmd.exe" --read-key $PWD engagement_posture`

Differs from the identity file: fail-loud, no overlay. Empty: proceed.

Render the overlay:

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/render-posture-overlay" "${ENGAGEMENT_POSTURE}" "${_EM_CONTEXT_REPO_ROOT}/.claude/em-context.md"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\render-posture-overlay.exe" "$ENGAGEMENT_POSTURE" "$_EM_CONTEXT_REPO_ROOT\.claude\em-context.md"`

`--check-only`: append `--check-only` to the overlay call (writes nothing). Empty `_EM_CONTEXT_REPO_ROOT`: Phase 5 already skipped this phase.

```bash
git -C "${_EM_CONTEXT_REPO_ROOT}" check-ignore -q .claude/em-context.md
```

Exit 1: append (via Edit) to `.gitignore`:
```text
# Operator-local EM posture overlay — per-operator, never shared.
.claude/em-context.md
```
Exit >1: fail-loud, no append. Already tracked: tell the operator to `git rm --cached` it.

```bash
"${COORDINATOR_SETTINGS_HOME:?COORDINATOR_SETTINGS_HOME unset — run the POSIX preamble above first}/bin/machine-local" array-append coordinator.installed_repos "${_EM_CONTEXT_REPO_ROOT}"
```

PowerShell host (rung 0): `& "$env:COORDINATOR_SETTINGS_HOME\bin\machine-local.cmd" array-append coordinator.installed_repos "$_EM_CONTEXT_REPO_ROOT"`

`--check-only`: skip. `repo-setup` re-renders this overlay later from the persisted value (wiki).

`test -f coordinator.local.md`. Exists: report `project_type` (flag legacy values for manual migration). Missing, not `--check-only`: `--non-interactive` fails loud; interactive asks `project_type`/subtypes (`unreal-engine` for an Unreal Engine repo: the Game Dev Reviewer default reviewer, docs-checker on every plan and diff), writes:

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
