<!-- GENERATED FILE: do not edit. -->

# Installing coordinator-claude with Claude Code

## Two legs, both yours

coordinator-claude is the doctrine; the coordinator engine (`claude-klabauter`) is a
**hard co-requisite** most state-mutating flows fail without. An install that stops after
leg 1 is incomplete — do not report it as done.

## What you are installing

coordinator-claude is a plugin (skills, commands, agents, hooks) that decides *what should
happen*; the Python engine does the durable work (work-state artifacts, sessions, gates).

### How Claude Code installs it

It is a standard **Claude Code marketplace** with one `coordinator` plugin (deep-research
folded in), installed with the native `claude plugin` CLI. A post-restart
`/coordinator:install` finishes the environment.

### The settings home

The install lands in the **settings home**, `~/.coordinator-claude-settings` (or
`$COORDINATOR_SETTINGS_HOME`): `bin/` (resolver and CLI forwarders), `machine-local/` (registry),
`coordinator-claude/` (plugin copy), `state/`. Confirm a write with
`ls -lt "$(dirname "$(machine-local dir)")/bin" | head` — fresh mtimes mean this install wrote it
(`install-receipt.json` is not rewritten on re-runs).

## Requirements

| Requirement | Why |
|---|---|
| `git` | Required to begin. |
| `bash` | No version floor (macOS 3.2 is fine). |
| **Python 3.11+: Homebrew `python3` on macOS** | `brew install python`; the engine puts its dependencies in `<settings-home>/engine-site`, so PEP-668 is no obstacle. No venv. Linux: the distro `python3`; Windows: python.org. Bare `python3` must resolve to it (§ Python, below). Floor 3.11 (`tomllib`). |
| `gh` | Required — clone auth and merge/release ceremonies. `gh auth login` first. No brew: § `gh` without Homebrew. |
| `jq` / `node` 18+ | Optional / ceremony-gate JS suite only. |
| **Windows only:** Smart App Control, App Execution Alias | Disable the Python App Execution Alias stubs (§ Python). Know Smart App Control's state before choosing the forwarder route: it blocks the unsigned `.exe` forwarders (§ Windows: Smart App Control). |
| NotebookLM MCP | Optional (deep-research Pipeline D); registers as `gemini-notebook-mcp`. Supported layouts and the exact registration command: § NotebookLM. The walk-through does not install or register it. |
| **The engine** | One hard dependency, not part of this clone. Installed at § Step 4, **after** the environment wiring (Step 3). |

### Your host

The Claude Code CLI (`claude`) is required to begin.

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
stubs disabled (Settings, Apps, Advanced app settings, App execution aliases), and Smart App Control
checked (§ Windows: Smart App Control).

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

**PowerShell profiles.** Never build a path under Documents by hand: folder redirection moves it.
Ask the shell: `[Environment]::GetFolderPath('MyDocuments')` or `$PROFILE.CurrentUserAllHosts`.
Windows PowerShell 5.1 and PowerShell 7 are separate shells with separate profiles and separate
execution policies; check each one a profile is written into
(`powershell -NoProfile -Command Get-ExecutionPolicy -List`, then the same with `pwsh`). A
`Restricted` policy (or `AllSigned` for an unsigned profile) means that profile never loads.

### Windows: Smart App Control

Smart App Control (SAC, Windows 11) blocks unsigned executables that have no reputation, and the
engine's .exe CLI forwarders are exactly that: no signed forwarder
exists. Check the state first (0 = off, 1 = enforcing, 2 = evaluation; unreadable is treated as on):

```powershell
reg query HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy /v VerifiedAndReputablePolicyState
```

Windows installs carry one extra install question, **`forwarder_route`** (`py` | `exe`):
"Use the fast prebuilt .exe forwarders (the .py route is slower but works with Smart App Control
on)?". The answer is stored as the machine-local key `coordinator.forwarder_route`.

| Route | Speed | Smart App Control |
|---|---|---|
| `exe` | fast | needs it **off**; every forwarder launch is blocked while it is on |
| `py` | slower | works with it **on** |

The default is `exe` only when the registry reads SAC off; enforcing, evaluation or unreadable
default to `py`. A blocked launch surfaces as `WinError 4551` ("An Application Control policy has
blocked this file"), or from Git Bash as a bare `Permission denied` that is not a chmod problem.
The engine's `scripts/setup.py --check` launches one forwarder and reports a blocked launch as
`FAIL [forwarder-launch]` naming SAC; an install step that hits the block reports BLOCKED:
"re-run the install and choose forwarder_route=py (works with Smart App Control on), or turn
Smart App Control off for the .exe route, then retry". `--check` fails only on the execution
policy of the PowerShell the engine uses (`pwsh` first); the other PowerShell shell warns.

**Switching routes later:** answer `forwarder_route` again in the Step 3 `--answers` document
(`{"forwarder_route":"py"}`), then re-run the engine installer and its check from a new terminal,
with the clone path from `machine-local get repos.claude_klabauter`:

```bash
python <klabauter-clone>/scripts/setup.py --i-am-agent
python <klabauter-clone>/scripts/setup.py --check
```

Turning SAC off is the human's call and is permanent for that Windows install (Windows does not
turn it back on without a reset).

### Windows: elevated runs and finishing `schtasks` later

Some optional extras need an elevated process: the Git Bash fast profile (it edits
`Git\etc\profile` under Program Files) and the `schtasks /Create` jobs (host sampler, pruner,
BoxCacheTrim). Run unelevated they report `Access is denied`, which is an advisory, not a failed
install. An agent cannot click the UAC prompt, so the human approves it:

```powershell
Start-Process -Verb RunAs -Wait -FilePath (Get-Command python).Source -ArgumentList '<absolute script path>','--install'
```

The elevated window's output is not returned: confirm from the normal shell afterwards (the
script's own `--check`, or `schtasks /Query /TN <task name>`). To finish a `schtasks` job later,
re-run the exact command the advisory printed, the same way, from an elevated terminal. Never run
the install-git-bash-fast-profile script twice blind: if its `--check` still says `ABSENT` right
after it reported `installed block`, its BEGIN/END markers are missing and a re-run would add a
second copy; report that instead.

### NotebookLM (optional)

Deep-research Pipeline D; install per the
[upstream README](https://github.com/jacob-bd/gemini-notebook-mcp-cli). The supported layouts:

- **User site of the system Python (default, no venv):** macOS Homebrew
  `python3 -m pip install --user --break-system-packages notebooklm-mcp-cli`; Linux distro
  `python3 -m pip install --user notebooklm-mcp-cli` (add `--break-system-packages` on a PEP-668
  distro); Windows python.org `py -3 -m pip install --user notebooklm-mcp-cli`. The scripts land in
  the user site's `bin` (POSIX) or `Scripts` (Windows) directory.
- **Isolated tool environment:** `uv tool install notebooklm-mcp-cli` (or `pipx`). To keep the
  packages in a directory of your choice, set `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` persistently
  first and put the bin directory on the user PATH; there is no other "packages directory" option.
  This is a venv by design, kept apart from every project.

Never install into a pyenv shim or a project interpreter. Register the `notebooklm-mcp` entry
script by its absolute path (`.exe` on Windows); in Claude Code the **name comes first** because
`-e` is variadic and swallows a name placed after it:

```bash
claude mcp add gemini-notebook-mcp -s user -e NLM_AUTH_STORAGE=file -- <absolute path to notebooklm-mcp>
```

The browser sign-in is the human's: `nlm login --storage file` (never the Keychain-backed
`protected` mode), run by absolute path or from a new terminal (§ Commands you hand the human).
Verify with `<plugin-root>/pipelines/deep-research/notebooklm/nlm-preflight.py`.

### Commands you hand the human

A running session's PATH is fixed at its launch, so a PATH edit made during the install is
invisible to it and to any `!` command the human runs inside it. Give the human a command by
absolute path (resolve it at run time: `command -v`, `Get-Command`, `machine-local get <key>`), or
say "open a new terminal first". A tool installed off PATH (a `pip install --user` Scripts
directory, the npm global directory) needs that directory added to the user PATH, then a new
terminal.

### Consumer box: SessionStart banners and filing friction

Some SessionStart text is written for the authoring fleet. On a consumer box:

- **"Guardless session(s), no --plugin-dir ... relaunch"** names the authoring box's launcher,
  which a consumer box does not have. Start a fresh `claude` instead: the marketplace-installed
  plugin loads (Step 2).
- **A foreign-platform `statusLine.command` box.** `~/.claude` can be git-synced across boxes, so
  a POSIX `statusLine.command` can land on Windows (or the reverse). It is the human's call:
  re-run the Step 3 environment wiring to regenerate it, or correct `statusLine.command` in
  `~/.claude/settings.json` by hand.
- **"Friction: memo ..."** names inboxes that exist only on the authoring fleet. File friction as
  an issue or PR on `dbc-oduffy/coordinator-claude` (`CONTRIBUTING.md`); with no network route,
  write a dated friction-log markdown file in the working directory and hand its absolute path to
  the human.


## Step 0 — Detect: which track?

The installer decides the track; never pick one by hand or infer it from probes of `~/.claude`.
Clone `claude-klabauter` (Step 1e; Step 4 keeps that clone), then run:

```bash
python3 <klabauter-clone>/lib/install/coordinator_install.py --plan
```

Read `environment.track` (with `track_reason`) from the JSON.

**That engine copy is the one authoritative `coordinator_install.py`.** Run it from the
`claude-klabauter` clone for `--plan` and `--answers` alike; do not run a copy of it found under
the plugin root, even if a command text names one.


### Tracks

- **`fresh`** — no coordinator plugin installed. Go to Step 1, then Step 2.
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

### Who runs what

`/coordinator:install` is model-invocable. When the PM's stated
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

Setup clones or adopts the user's `group-em` and `.claude` GitHub repos without overwriting a
file, and links both homes into the repos folder (`machine-local get coordinator.repo_home`);
report each home's action line to the human.

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

The engine is installed in Step 4, but its **clone must exist now, before Step 3**:
the environment wiring's Phase 3 bootstraps the substrate from a script inside the engine repo,
and Step 3 fails on its first command with an unset root otherwise. This is the one place the
order is stated: **1e before Step 3, Step 4 after** (why: `docs/wiki/install-playbook-rationale.md` § Step 4).

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

### Pinned LSP backends (ty and tsgo)

The plugin's language servers route through the box's LSP front, on by default; it needs `ty`
and `tsgo` at the versions in `scripts/lsp_front_pins.json`. From the plugin root, run
`python scripts/lsp_stock_plugins.py --install` (installs the pins with `uv` and `npm`, then
re-verifies; exit 1 on a mismatch or a missing installer), then
`python scripts/lsp_stock_plugins.py --doctor` (one `backend <tool> ...` line per backend; it
reports `backend X missing` and exits 1 when `ty` or `tsgo` is absent; a binary present but off
PATH reports `installed at <path>, not on PATH`: add that directory to the user PATH, then open
a new terminal; `uv` via `pip install --user` and npm globals land off PATH on Windows). The pins are bumped as
the tools release; `machine-local set lsp.front_backend pooled` is the per-box rollback to
pyright and typescript-language-server.

### Ask the human once: posture and every optional extra

Before `--answers`, put **one** numbered questionnaire to the human in a single message and take
the answer as one string; never answer an optional extra for them, and never drop one because a
non-interactive default would skip it. Say what each "no" leaves out:

1. **Posture** (offer it, never declare it; show the current value as the default and ask on
   every guided install, never inherit it silently): `precision` (close to the work), `default`
   (the PM/EM middle ground, the engineering manager acts and pushes back), or `substrate-free`
   (maximum altitude: "build me X").
2. Cross-box messaging (Unimatrix) and the Codex / agy host hooks (host CLIs first, Step 5).
3. NotebookLM deep-research (§ NotebookLM).
4. Context7 docs (it still needs a sign-in through `/mcp` after the install).
5. Git Bash fast profile and the BoxCacheTrim task (each needs an elevated run, § Windows).
6. Cloning the user's general-work repo.
7. Persona renames.
8. Optional tools: `jq`, `scc`, the 1Password CLI.
9. Windows only: `forwarder_route` (§ Windows: Smart App Control).

`--answers` is one flat JSON object keyed by the plan's decision `id`s, plus a **`consent`
object** (`{"consent":{"<step id>":true}}`, shaped by `answers_shape` in the `--plan` output). A
step that needs consent and has none is SKIPPED with "consent required; re-run with
consent.<id>=true", whatever the permission mode: presumed extras are listed, not consented.


## Step 4 — Install the engine (`claude-klabauter`)

coordinator-claude and its engine are **one joint installation**. Without the engine, planning,
review and personas work; claiming handoffs, memo resolution, coverage and terminal stamping do
not. **The sequence, literally:**

### The sequence

1. Install the plugin (§ 1d). 2. Clone the engine and register `repos.claude_klabauter` (§ 1e,
before the restart). 3. Load the plugin into a session (§ Step 2). 4. Run `/coordinator:install`
(§ Step 3; deposits the resolver). 5. **Only then** run the engine's installer, below, from a
shell started after (4).

| Command | What it is | When |
|---|---|---|
| **`/coordinator:install`** | Environment wiring, Phases 1–7; Phase 3 deposits `machine-local`. | Step 3 |
| **`/coordinator:setup`** | Install-chain walker (5/5): a **verifier**, never a depositor. | *After* this step |

### Run the engine installer

1. **Confirm the resolver is live** by absolute path (a bare `command -v machine-local` miss is
   ambiguous):
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" get repos.claude_klabauter
   ```
   Expect the Step 1e path. **Do not use `machine-local keys` as the check** — it prints a fatal
   malformed-registry error yet exits 0. `get` exits 2 correctly.
2. **Windows:** disable the Python App Execution Alias stubs first and check Smart App Control
   (§ Requirements, § Windows: Smart App Control). Python 3.11+.
3. **The clone already exists** (Step 1e); do not clone again.
4. **Run the agent install path**, non-interactive, from that clone:
   ```bash
   python3 <klabauter-clone>/scripts/setup.py --i-am-agent
   ```
   (Windows: `python <klabauter-clone>\scripts\setup.py --i-am-agent`.) It checks dependencies
   (including the Step 3 resolver), installs, and registers the engine. Relative to the
   coordinator clone the entry point is `../claude-klabauter/scripts/setup.py` (Windows:
   `../claude-klabauter/scripts/setup.cmd`).
5. **Read that output — it is the only thing that tells you the engine installed.** Every line is
   `PASS`/`FAIL`; a non-zero exit or traceback means it did not complete.
   `python3 <klabauter-clone>/scripts/setup.py --check` covers only the CLI forwarders, door, guards,
   required `repos.*` pointers and statusline — not dependency provisioning or a
   `coordinator_core` import — so it is not the verdict.

**Do not** run `pip install .` as the engine install (it skips the dependency check and
registration), and do not pass `--skip-dep-check --accept-missing-deps-risk` (a degraded path;
the flags are a pair). The engine has no plugin surface. The human path omits `--i-am-agent`.

### Step 4 closes the chain — run the setup verifier last

In a Claude Code session, run **`/coordinator:setup`**: it walks `direct_deps`, verifies the
engine is satisfied and emits the chain-complete banner. It installs nothing; run earlier it fails
loud with "engine not satisfied." That is the whole install.


## Step 5 — Unimatrix cross-box messaging

Unimatrix carries cross-box idle notices between boxes.

### Host CLIs first

Install the Codex and agy CLIs **before** Unimatrix when the box will govern those hosts: with
one absent the installer reports `governance verification FAILED: codex not on PATH` and exits 5.
Codex: `npm i -g @openai/codex`. agy on Windows: `winget install Google.AntigravityCLI`. Open a
new terminal so PATH sees them, then re-run. The Grok CLI has no winget or npm package; install it
by its vendor's instructions.


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

## Verifying your install

Don't infer coordinator is live from the absence of errors:

### Claude Code

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

### Close with a not-done list

End your report with an explicit **not-done list**: every step that did not run, and every
human step you cannot do. The real-launch check is the human's: a fresh terminal the human
opens, running the real launch command (a launch that never starts the host, such as
`--version`, proves nothing). Verify from the user's real default shell with a clean env: on
Windows, `Remove-Item Env:PSExecutionPolicyPreference` first, in each PowerShell (5.1 and 7)
that carries a profile. A pass in the shell you ran the install from is not that verdict.

### Reporting rough edges

Per-project config is `coordinator.local.md` (`/coordinator:repo-setup` writes it). If you worked
around a rough edge, offer to send it upstream (PR or issue on `dbc-oduffy/coordinator-claude`;
see `CONTRIBUTING.md`).

## Keeping the install current

Re-run `--plan` (Step 0): `track: update` means the installer performs the update itself. The
agent/human split is Step 0's.

### Claude Code update advisory

`/coordinator:coordinator-update` is the customization-aware
advisory; it never performs the update. `version.txt` in the installed plugin directory is the
update baseline (a published-clone commit SHA written only by a completed
`/coordinator:coordinator-update` apply), not the plugin version (`.claude-plugin/plugin.json`).

## More detail

- Guided runbook, one phase at a time: `commands/install.md`. Reversing an install:
  `commands/uninstall.md`. Install-chain walker: `docs/install/AGENT.md`.
