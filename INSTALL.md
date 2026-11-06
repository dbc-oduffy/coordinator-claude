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
| **Python 3.11+: Homebrew `python3` on macOS** | `brew install python`; the engine puts its dependencies in `<settings-home>/engine-site`, so PEP-668 is no obstacle. No venv. Linux: the distro `python3`; Windows: python.org. Bare `python3` must resolve to it (§ Python, below). Floor 3.11 (`tomllib`). |
| `gh` | Required — clone auth and merge/release ceremonies. `gh auth login` first. No brew: § `gh` without Homebrew. |
| `jq` / `node` 18+ | Optional / ceremony-gate JS suite only. |
| NotebookLM MCP | Optional (deep-research Pipeline D). Install per the [upstream README](https://github.com/jacob-bd/gemini-notebook-mcp-cli); it registers as `gemini-notebook-mcp`. No venv needed; the walk-through does not install or register it. |
| **The engine** | One hard dependency, not part of this clone. Installed at § Step 4, **after** the restart. |

### Python — decide before installing anything

**macOS: Homebrew `python3`.** `brew install python`, and make bare `python3` (the name every hook
and forwarder spawns) resolve to `/opt/homebrew/bin/python3`. The engine installs its dependencies
into `<settings-home>/engine-site`, not the interpreter's site-packages, so Homebrew's PEP-668
marker does not block it. No venv. Apple's `/usr/bin/python3` is a Command Line Tools stub, too old:
it must never win on PATH. Check: `command -v python3` prints `/opt/homebrew/bin/python3`.

**Anything sshd or launchd spawns does not read your shell profile.** Name the interpreter by
absolute path there (`/opt/homebrew/bin/python3`), or it gets the `/usr/bin` stub.

**macOS preflight, first.** `git --version` and `python3 -c 1` must both exit 0. If they print
"You have not agreed to the Xcode license", a human runs `sudo xcodebuild -license accept` (agents
cannot: it needs sudo); on a box with no developer tools, `xcode-select --install`.

**macOS PATH.** In `~/.zprofile` (login shells) and `~/.zshenv` (non-login shells, GUI and
launchd-spawned tools, an agent's Bash tool), put Homebrew first:

```bash
export PATH="/opt/homebrew/bin:$PATH"
```

A pyenv shim or version directory earlier on PATH shadows it; remove that line.

**Linux:** the distro `python3` (3.11+). **Windows:** python.org 3.11+, with the App Execution Alias
stubs disabled.

### `gh` without Homebrew

On a box with no brew, download the macOS `.zip`/`.pkg` for the box's arch from
`https://github.com/cli/cli/releases/latest`, put `gh` on a PATH directory (for example
`~/.local/bin`, added to `~/.zprofile`), then `gh auth login` and `gh --version`.

### Windows

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
  Steps 1 and 2; go to Step 3. A box installed before 8e7aef49ad that has NotebookLM registered
  as `notebooklm-mcp` runs `nlm setup add claude-code` once; it renames the entry in place to
  `gemini-notebook-mcp`.
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
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" \
    set engine.target main
```

**Both keys, always.** Without `engine.target` the ladder does not trust the registered engine and
falls through to any sibling engine checkout it can find.

> **If `machine-local` does not exist yet** (expected on a cold box; Phase 3 deposits it, so that
> remedy is circular), hand-write the one durable route — a registry entry in
> `<settings-home>/machine-local/registry.local.toml` (`<settings-home>` is
> `${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}`; create the dir if absent):
>
> ```toml
> [repos]
> claude_klabauter = "<absolute path of the claude-klabauter clone>"
>
> [engine]
> target = "main"   # "candidate" on a makers' box
> ```
>
> The session-only alternative is `export COORDINATOR_ENGINE_ROOT="<that path>"`; it dies with the
> shell. Verify with `python3 <plugin-root>/hooks/scripts/_engine_root.py`: it prints the
> **claude-klabauter** path and exits 0. Any other path (a sibling engine working tree) means
> `engine.target` is missing. **An exit of 2 (empty stdout, stderr names `repos.claude_klabauter`) means this
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
   prerequisites, lays down the machine-local registry, scaffolds the
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

### Consumer box: Unimatrix from the released plugin

A consumer box (released `coordinator-claude` plus `claude-klabauter` only) runs Unimatrix from the
installed plugin root, `$CLAUDE_PLUGIN_ROOT`, once a release that ships the `unimatrix-*` scripts
is installed. Check mode first; `--install` only after it prints `in verified range`:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/unimatrix-install.py"            # Windows: python
python3 "$CLAUDE_PLUGIN_ROOT/bin/unimatrix-install.py" --install
```

The relay, the mirroring supervisor and the install step all ship in that release. Bridge pipes
are named `cc-msg-<32 hex>`; idle notices cross boxes over Unimatrix only. The released scripts
try the far box's LAN address first and use the tunnel address only when the LAN address is
unreachable; the tunnel is never required on the home network. Box addresses and tunnel addresses
stay out of tracked files.

### Codex and agy hosts

A box with Codex, agy or both inherits the DoE doctrine under Klabauter governance through
`unimatrix-install.py`. This is a host install; it is not the Codex reviewer integration that
Phase 6 no longer carries, and it adds no review gate and no marketplace step. Prerequisite:
`claude-klabauter` (Step 4), which ships `coordinator_core.host_hooks.shim`, the guard each host
calls. Name the hosts explicitly; with no `claude` on PATH the Claude range gate is skipped, with
a printed notice, only when `--hosts` names no `claude`:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/bin/unimatrix-install.py" --install --hosts codex,agy   # Windows: python
python3 "$CLAUDE_PLUGIN_ROOT/bin/unimatrix-install.py" --uninstall                   # removes every managed entry
```

Bare `--install` still
refuses outside the verified Claude range.

`agy plugin import claude` is not an install route: agy's importer skips Claude agents (model
tiers), `hooks.json` (top-level `description`) and `commands/`, and truncates files over 24000 B.
Use this script.

| Lands | Codex | agy |
|---|---|---|
| Doctrine block (`coordinator-doctrine`, `global-doctrine/CLAUDE.md` then `rules/rules.md`, beside the peer block) | `$CODEX_HOME/AGENTS.md` (cap 32768 B) | `~/.gemini/GEMINI.md` (cap 24000 B) |
| Skills | one entry per skill in `~/.agents/skills/` (symlink, copy where refused; not moved by `CODEX_HOME`) | `{"entries":[{"path":"<plugin root>/skills"}]}` in `~/.gemini/config/skills.json` |
| Guard hook | `PreToolUse` in `$CODEX_HOME/hooks.json`, synchronous, shell tools only | the one `PreToolUse` group in `~/.gemini/config/hooks.json`, merged with the peer-bootstrap hook |
| Peer registration | `SessionStart` in `$CODEX_HOME/hooks.json` | flat `SessionStart` handler list |

The block is managed: edits inside it are overwritten on the next install and removed on
uninstall; text outside it is never touched. The installer resolves the engine root once and bakes
it into each hook command as `--engine-root`.

**Trust step.** Codex runs only trusted hooks. The installer trusts both owned handlers
(SessionStart and the PreToolUse guard) and verifies discovery, enabled state and
`currentHash == trustedHash` for each. A missing, disabled or untrusted guard prints
`governance verification FAILED` and exits non-zero even when doctrine seeding succeeded. An
unresolved engine root prints `governance DEGRADED: engine root unresolved`: the hooks are seeded
without `--engine-root` and answer only the neutral fallback.

**Fallbacks.** The guard never fails the host. With no engine verdict (engine absent, slow, error,
timeout) it answers `{"decision": "ask"}` on agy, which fails closed, and `{}` on Codex, which
fails open and leaves the normal approval flow untouched. Neither host ever gets `allow` as a
fallback; agy never gets `force_ask`. A degraded answer is never counted as verified governance.

**Limits.** Read these as the boundary of what is governed.

- Governance is shell-command governance only. On Codex it does not cover `apply_patch`, MCP and
  other local function calls, `write_stdin` input to a running shell, or hosted tools. `{}` is
  fail-open, so a degraded guard under `danger-full-access` with approval `never` has no approval
  backstop. The execpolicy rule the installer seeds is an allow prefix for peer-send only and has
  no deny coverage.
- `--dangerously-skip-permissions`, `--mode auto` (agy) and `danger-full-access` (Codex) are never
  set by default. The live enforcement matrix exercises shell commands only, so a passing matrix is
  evidence for shell-only governance, not complete Klabauter enforcement; it never clears these
  options alone. Beyond the assigned-task ceiling below, they stay unoffered until the excluded
  execution paths above are also covered.
- Operating ceiling for assigned peer tasks: Codex runs at `--sandbox workspace-write` with approval
  `on-request` (its auto equivalent). The sandbox bounds the paths no hook sees (`apply_patch`, MCP
  calls, writes to a running shell) to the workspace, and the guard governs shell commands. Peers
  take specific assigned tasks; they are not integrated into the workflow fleet, so the
  approval prompts this ceiling raises are accepted.
- agy runs assigned tasks at `--mode auto` in an interactive session. `auto` is not a sandbox: it
  lowers agy's own approval thresholds, and its file edits are not bounded to the workspace. Shell
  commands stay governed because the guard turns every non-deny answer into `ask`. Headless
  `agy -p` runs only when the same launch first runs the PreToolUse guard health check and it
  passes; a failed or absent check means no headless run. No such check ships yet, so headless
  `agy -p` is not run.
- Live matrix result (C6, 2026-11-04): shell-command deny holds under both Codex modes and under
  `--dangerously-bypass-approvals-and-sandbox`, which still runs hooks and rules. Not covered: a
  `forbidden` execpolicy rule does not match a command wrapped in `bash -c '...'` or `env ...`, so
  rules never govern wrapped forms. A degraded guard (import failure, timeout, malformed reply)
  enforces nothing on Codex. The p4-submit deny is armed only where the box sets
  `policy.p4_no_submit`; without it the command is allowed. Warm-engine deny (server-correlated) and
  the Codex on-request runtime (interactive TUI: approve runs, reject does not, hook deny blocks
  before the prompt) are proven. agy (run in the real home): warm deny, backstop deny and neutral
  `ask` are proven, and our hook denies `bash -c`/`env`-wrapped commands on both hosts, so the
  wrapper gap is Codex's rule matcher only. agy headless (`agy -p`) runs an `ask` command with no
  human, so a degraded guard (import failure, timeout, malformed reply) enforces nothing there,
  the same as Codex `{}`. The guard never passes an engine `allow` through to agy; any non-deny
  answer becomes `ask`. Matrix:
  `docs/plans/2026-11/2026-11-04-hnd-codex-agy-doctrine-install-and-773493.c6-matrix.md`.
- Budget versus cleanup: the guard's time budget bounds only the wait on the engine child
  (`communicate`), not process start-up. After a timeout the child is killed and reaped with up to
  2 s of additional cleanup grace, so the wall time of a degraded call can exceed the budget.
- `hooks/hooks.json` (under the plugin root) holds 52 Claude handlers across 13 events. agy hosts 6 events and
  has no event for 13 of those handlers (SessionEnd, SubagentStart/Stop, UserPromptExpansion,
  UserPromptSubmit, PreCompact, PostToolUseFailure, CwdChanged, ConfigChange). Codex has no event
  for 5 (UserPromptExpansion, PostToolUseFailure, CwdChanged, ConfigChange). Claude handlers are
  not ported one by one on either host; the guard runs through the engine adapter only.
- Commands and agent definitions are not ported; skills are.
- agy: `SessionStart` carries only `ANTIGRAVITY_CONVERSATION_ID`, no language-server address or
  CSRF token, so a peer leg starts on the first `run_command` through the `PreToolUse` rewrite,
  not at session start.

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
   to `permissions.allow` (background subagents need them). Set top-level `crossSessionInbound`
   to `"accept"` if absent (never overwrite an existing value).

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
