# Installing coordinator-claude

Written for the agent installing this repo (see `AGENTS.md`, this file's sibling at the repo
root, for the entry point) — a human reads it too. This is a **two-leg install, and both legs are
yours**: coordinator-claude is the doctrine; the coordinator engine (`claude-klabauter`) is a
**hard co-requisite** most state-mutating flows fail without. An install that stops after leg 1 is
incomplete — do not report it as done.

## What you are installing

coordinator-claude is a Claude Code plugin (skills, commands, agents, hooks) that decides *what
should happen*; the Python engine does the durable work (work-state artifacts, sessions, gates).
It is a standard **Claude Code marketplace** with one `coordinator` plugin (deep-research folded
in), installed with the native `claude plugin` CLI. A post-restart `/coordinator:install`
finishes the environment.

The install lands in the **settings home**, `~/.coordinator-claude-settings` (or
`$COORDINATOR_SETTINGS_HOME`): `bin/` (resolver and CLI forwarders), `machine-local/` (registry),
`coordinator-claude/` (plugin copy), `state/`. Confirm a write with
`ls -lt "$(dirname "$(machine-local dir)")/bin" | head` — fresh mtimes mean this install wrote it
(`install-receipt.json` is not rewritten on re-runs).

## Requirements

| Requirement | Why |
|---|---|
| `git`, Claude Code CLI | Required to begin. |
| `bash` | No version floor (macOS 3.2 is fine). |
| **Python 3.11+** | A **real** `python3`, not a stub (Windows note below); gates `tomllib`. |
| `gh` | Required — clone auth and merge/release ceremonies. `gh auth login` first. |
| `jq` / `node` 18+ | Optional / ceremony-gate JS suite and NotebookLM add-on only. |
| **The engine** | One hard dependency, not part of this clone. Installed at § Step 4, **after** the restart. |

**Windows:** `python3` is by default a Microsoft Store alias stub, invisible to Git Bash. Install
a real Python (`winget install Python.Python.3.13`), put its dir before `…\WindowsApps` on PATH,
provide a `python3` (copy of `python.exe`), and start a fresh shell (`winget` edits only the
registry PATH). Git Bash keeps `bash.exe` off `PATH`; launch "Git Bash" or use the full path. Run
examples written as `bash` there; PowerShell/cmd set only `USERPROFILE`.

## Step 0 — Detect: which track?

The installer decides the track; never pick one by hand or infer it from probes of `~/.claude`.
Clone `claude-klabauter` (Step 1e; Step 4 keeps that clone), then run:

```bash
python3 <klabauter-clone>/lib/install/coordinator_install.py --plan
```

Read `environment.track` (with `track_reason`) from the JSON.

- **`fresh`** — no coordinator plugin installed. Go to Step 1, then the restart gate.
- **`update`** — installed; the installer performs the update itself (`plugin_update`,
  `engine_setup`, `engine_check`). `track_reason: already current` drops `plugin_update`. Skip
  Steps 1 and 2; go to Step 3.
- **`repair`** — installed, not newer, engine check fails or the engine is unlocatable. Report
  `track_reason`. Skip Steps 1 and 2; go to Step 3.

**Cold box** (no plugin root, nothing to run `--plan` from): by the installer's own predicate that
is `fresh`. The entry is `python3 <klabauter-clone>/scripts/setup.py --i-am-agent` (Step 4);
proceed to Step 1.

**Who runs what.** `/coordinator:install` is model-invocable. When the PM's stated
intent in this session is to install or set up (the PM need not type the command), the agent runs
`--plan` and `python3 <klabauter-clone>/scripts/setup.py --i-am-agent` (the `engine_setup` and
`engine_check` leg) through Bash. `plugin_update` stays gated: it runs only inside the
human-typed `/coordinator:install`, and an agent never hand-runs `claude plugin update` — on
`update`, hand the human that command.

### Reinstall (clean)

A deliberate clean reinstall is **uninstall, then the `fresh` track**; `--plan` reports
`update`/`repair`, never "reinstall."

1. **Back up first**: tar the settings home and the Claude config dir
   (`tar czf ~/coordinator-reinstall-backup-<date>.tgz ~/.coordinator-claude-settings ~/.claude`).
2. The human types `/coordinator:uninstall` (`disable-model-invocation`). If an agent runs the
   uninstall script instead, use **two round trips with literal paths**: first print the resolved
   engine root (`python3 <plugin-root>/hooks/scripts/_engine_root.py`), then invoke
   `python3 "<that literal path>/coordinator/bin/coordinator-uninstall.py"`. A `$VAR` or `$(...)`
   script path is blocked by the approval-sentinel guard.
3. Confirm `claude plugin list` no longer shows `coordinator@coordinator-claude`; if it does,
   remove it by hand before continuing.
4. Restart the shell, then run Step 0 again; expect `fresh`, and follow Step 1 onward.

### Existing home — disclosure, not routing

What `~/.claude` already holds (the installer's INHERITED rows) is disclosed, never routed on. The
install merges config rather than overwriting, so **proceed and report; do not stop**, and tell
the human afterwards what you found and did. **Stop and ask only on a genuine conflict** — a file
the install would have to *overwrite*, or coordinator infra of unestablishable provenance. Name
the file and the clash.

## Step 1 — Install via the `claude plugin` CLI

Wire the whole system before the restart, so the fresh session comes up coordinator-shaped.

### 1a. Clone or locate the repo

The clone provides helper scripts and the offline/dev variant. **Keep it**: the engine's
`<klabauter-clone>/scripts/setup.py` resolves coordinator-claude as a sibling at Step 4.

```bash
git clone https://github.com/dbc-oduffy/coordinator-claude.git ~/coordinator-claude
```

If a clone is already on disk, resolve it yourself — do not ask:

```bash
git -C <candidate> remote -v          # expect a dbc-oduffy/coordinator-claude remote
git -C <candidate> status --porcelain
git -C <candidate> rev-parse HEAD
```

Use the candidate with the right remote and say which. Ask only if two disagree on HEAD.

### 1b. Install the whole system — a statement, not a gate

Installing coordinator is installing a *collaboration contract, not software*: install
everything and **do not offer a choice.** Cherry-pick is unsupported (downstream repos depend on
the full infra); if the human asks for a subset unprompted, say so before proceeding.

### 1c. Plugin selection

`coordinator` is always on; `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` is retired and must not be
set. UE/example-game-repo, game-dev and project-rag plugins are specialized — never offer them to a generic
user. No per-skill picker; turning a piece off is post-install per-project gating.

### 1d. Run the install (native `claude plugin` CLI)

```bash
claude plugin marketplace add dbc-oduffy/coordinator-claude
claude plugin install coordinator@coordinator-claude
```

Register the **public GitHub repo**, not your clone path: a directory source breaks if the clone
moves and serves a **snapshot**, not live edits. The step clones over SSH;
`Permission denied (publickey)` means add an SSH key (`gh auth login` does not satisfy it) or
clone over HTTPS and register the directory. Surface CLI errors verbatim. Detail:
`docs/wiki/install-playbook-rationale.md` § Step 1d.

**No sentinel, no onboarding baton, no `/pickup` staging.** The post-restart
`/coordinator:install` (Step 3) *is* the onboarding and records its own completion receipt.

### 1e. Clone the engine and register it — a clone, **not** an install

The engine is installed in Step 4, but its **clone must exist now, before the restart**:
`/coordinator:install`'s Phase 3 bootstraps the substrate from a script inside the engine repo,
and Step 3 fails on its first command with an unset root otherwise. This is the one place the
order is stated: **1e before the restart, Step 4 after** (why: `docs/wiki/install-playbook-rationale.md` § Step 4).

**Look before you clone:**

```bash
# 1. Already registered?
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" \
    get repos.claude_klabauter 2>/dev/null
# 2. A sibling of the coordinator clone, or at ~/ ?
ls -d "$(dirname <coordinator-clone>)/claude-klabauter" ~/claude-klabauter 2>/dev/null
```

Confirm each candidate with `git -C <path> remote -v` (expect `dbc-oduffy/claude-klabauter`). One
real candidate, or several with equal `git rev-parse HEAD`: use it and say which. Ask the human
only when two real candidates disagree on HEAD.

**If none exists, clone it as a sibling of the coordinator clone** (not `~`, not the cwd):

```bash
git clone https://github.com/dbc-oduffy/claude-klabauter \
    "$(dirname <coordinator-clone>)/claude-klabauter"
```

**Then register it**, so nothing downstream guesses. The engine installer writes this same key
once it runs; this hand-set is the cold-box bootstrap (Step 4 needs the key first):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" \
    set repos.claude_klabauter "$(dirname <coordinator-clone>)/claude-klabauter"
```

> **If `machine-local` does not exist yet** (expected on a cold box; Phase 3 deposits it, so that
> remedy is circular), hand-write the one durable route — a registry entry in
> `<settings-home>/machine-local/registry.local.toml` (`<settings-home>` is
> `${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}`; create the dir if absent):
>
> ```toml
> [repos]
> claude_klabauter = "<absolute path of the claude-klabauter clone>"
> ```
>
> The session-only alternative is `export COORDINATOR_ENGINE_ROOT="<that path>"`; it dies with the
> shell. Verify with `python3 <plugin-root>/hooks/scripts/_engine_root.py`: it prints the path and
> exits 0, and **an exit of 2 (empty stdout, stderr names `repos.claude_klabauter`) means this
> step is missing.** `CLAUDE_KLABAUTER_ROOT` is retired and unhonoured. Detail:
> `docs/wiki/install-playbook-rationale.md` § Step 1e.

**Do not run the engine's installer here.** Cloning and registering is all this step does.

## Step 2 — The restart (load-bearing gate)

Tell the human exactly this:

> **Start a fresh Claude Code session from any directory, then paste one command.**
>
> 1. Open a terminal in any folder and run `claude`. (No `claude`? `npm install -g @anthropic-ai/claude-code`.)
> 2. In that session, paste:
>
> ```
> /coordinator:install
> ```
>
> The install opens `~/.claude` in your file manager; you never need to `cd` there. Everything
> after runs in that one session; `bin/needs-restart.py` prints `none`, `/reload-plugins` or
> `restart`, and the install asks for a further restart only on `restart`.

## Step 3 — Post-restart: finish the environment, onboard a project

1. **`/coordinator:install`** — runnable on the PM's stated intent (Step 0); `plugin_update`
   needs the human-typed command. Environment wiring as a script with declared choices
   (`<klabauter-clone>/lib/install/coordinator_install.py`: orientation, then `--plan`, then
   `--answers`; safe to re-run; reports every step RAN, SKIPPED, INHERITED or FAILED). It checks
   prerequisites, lays down the machine-local registry, builds the helper venv, scaffolds the
   canonical document structure, records the `setup_concluded` receipt, sweeps git-perf config
   over registered worktrees, and offers a guided tour and repo bootstrap. **Phase 3 deposits the
   `machine-local` resolver** that Step 4 depends on.
2. **`/coordinator:repo-setup`** — per-project scaffolding (project `CLAUDE.md`, tracker, type).
3. **`/workday-start`** — only if other downstream tools queued their legs in
   `~/.claude/state/handoffs/`; on a solo install skip to `/workstream-start`.

The highest-leverage first customization is co-writing `CLAUDE.md`; the tour is the vehicle.

## Step 4 — Install the engine (`claude-klabauter`)

coordinator-claude and its engine are **one joint installation**. Without the engine, planning,
review and personas work; claiming handoffs, memo resolution, coverage and terminal stamping do
not. **The sequence, literally:**

1. Install the plugin (§ 1d). 2. Clone the engine and register `repos.claude_klabauter` (§ 1e,
before the restart). 3. Load the plugin into a session (§ Step 2). 4. Run `/coordinator:install`
(§ Step 3; deposits the resolver). 5. **Only then** run the engine's installer, below, from a
shell started after (4).

| Command | What it is | When |
|---|---|---|
| **`/coordinator:install`** | Environment wiring, Phases 1–7; Phase 3 deposits `machine-local`. | Step 3 |
| **`/coordinator:setup`** | Install-chain walker (5/5): a **verifier**, never a depositor. | *After* this step |

1. **Confirm the resolver is live** by absolute path (a bare `command -v machine-local` miss is
   ambiguous):
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" get repos.claude_klabauter
   ```
   Expect the Step 1e path. **Do not use `machine-local keys` as the check** — it prints a fatal
   malformed-registry error yet exits 0. `get` exits 2 correctly.
2. **Windows:** disable the Python App Execution Alias stubs first (§ Requirements). Python 3.11+.
3. **The clone already exists** (Step 1e); do not clone again.
4. **Run the agent install path**, non-interactive, from that clone:
   ```bash
   python3 <klabauter-clone>/scripts/setup.py --i-am-agent
   ```
   (Windows: `python <klabauter-clone>\scripts\setup.py --i-am-agent`.) It checks dependencies
   (including the Step 3 resolver), installs, and registers the engine.
5. **Read that output — it is the only thing that tells you the engine installed.** Every line is
   `PASS`/`FAIL`; a non-zero exit or traceback means it did not complete.
   `<klabauter-clone>/scripts/setup.py --check` covers only the CLI forwarders, door, guards,
   required `repos.*` pointers and statusline — not dependency provisioning or a
   `coordinator_core` import — so it is not the verdict.

**Do not** run `pip install .` as the engine install (it skips the dependency check and
registration), and do not pass `--skip-dep-check --accept-missing-deps-risk` (a degraded path;
the flags are a pair). The engine has no plugin surface. The human path omits `--i-am-agent`.

### Step 4 closes the chain — run `/coordinator:setup` last

In a Claude Code session, run **`/coordinator:setup`**: it walks `direct_deps`, verifies the
engine is satisfied and emits the chain-complete banner. It installs nothing; run earlier it fails
loud with "engine not satisfied." That is the whole install.

## Verifying your install

Don't infer coordinator is live from the absence of errors:

1. **Launched via your install path's documented method**, not a bare `claude` with nothing
   resolving the plugin. In a transcript, look for the SessionStart `additionalContext` the
   EM-role hook injects — a coordinator-less session never gets it.
2. **Coordinator commands resolve.** `/` lists `/coordinator:validate`, `/coordinator:install`, …
3. **Hooks are wired** by the plugin's own `hooks/hooks.json`, which the harness reads directly
   (plugin install and `--plugin-dir` alike), so an **empty** `hooks` block in
   `~/.claude/settings.json` is CORRECT; coordinator hooks there would fire twice. Confirm:
   ```
   python3 -c "import json;h=json.load(open('<resolved-plugin-root>/hooks/hooks.json'))['hooks'];print({k:len(v) for k,v in h.items()})"
   ```

Cosmetic: the plugin adds ~8.2k tokens to every session baseline, and `claude plugin details`
shows doubled skill names (skill plus same-named command wrapper).

## Manual install (fallback only)

Only if the `claude plugin` CLI cannot run. The published repo IS the plugin; the installed root
is `~/.claude/plugins/coordinator-claude` (no suffix; verify
`test -f ~/.claude/plugins/coordinator-claude/.claude-plugin/marketplace.json`).

1. `cp -r <clone> ~/.claude/plugins/coordinator-claude` (the repo root).
2. Merge into `~/.claude/plugins/known_marketplaces.json` key `coordinator-claude`: `source`
   `{"source": "directory", "path": "<plugin root>"}`, `installLocation` the same path.
3. Merge into `~/.claude/plugins/installed_plugins.json` key `coordinator@coordinator-claude`:
   `installPath` `<plugin root>`, `version` from `.claude-plugin/plugin.json`.
4. Merge `~/.claude/settings.json`: `enabledPlugins` keys are `<name>@coordinator-claude` (not
   bare); `extraKnownMarketplaces` is an object keyed by marketplace name; add `Edit` and `Write`
   to `permissions.allow` (background subagents need them).

On Windows write **native** paths into the JSON, not `/c/…`. After a manual install, restart and
run `/coordinator:install` as in Step 3.

## Refinement target: edit your `~/.claude`, not this clone

After install the human evolves their live, git-tracked `~/.claude`. Do NOT edit the
`coordinator-claude` source repo to customize behaviour; the next install overwrites it.
`coordinator.local.md` at a consuming repo's root is the one exception.

## Failure modes

- **`claude plugin install` reports nothing.** Add the marketplace first; the key is
  `<name>@coordinator-claude`.
- **`/reload-plugins` reports `0 plugins`.** Usually a clone-bound marketplace whose directory
  moved: re-register from GitHub, then `/reload-plugins`.
- **Commands missing after install.** Hooks and commands load at startup; restart (Step 2).

Per-project config is `coordinator.local.md` (`/coordinator:repo-setup` writes it). If you worked
around a rough edge, offer to send it upstream (PR or issue on `dbc-oduffy/coordinator-claude`;
see `CONTRIBUTING.md`).

## Keeping the install current

Re-run `--plan` (Step 0): `track: update` means the installer performs the update itself. The
agent/human split is Step 0's. `/coordinator:coordinator-update` is the customization-aware
advisory; it never performs the update. `version.txt` in the installed plugin directory is the
update baseline (a published-clone commit SHA written only by a completed
`/coordinator:coordinator-update` apply), not the plugin version (`.claude-plugin/plugin.json`).

## More detail

- Guided runbook, one phase at a time: `commands/install.md`. Reversing an install:
  `commands/uninstall.md`. Install-chain walker: `docs/install/AGENT.md`.
