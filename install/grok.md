<!-- GENERATED FILE: do not edit. -->

# Installing coordinator-claude with Grok

## Two legs, both yours

coordinator-claude is the doctrine; the coordinator engine (`claude-klabauter`) is a
**hard co-requisite** most state-mutating flows fail without. An install that stops after
leg 1 is incomplete — do not report it as done.

## What you are installing

coordinator-claude is a plugin (skills, commands, agents, hooks) that decides *what should
happen*; the Python engine does the durable work (work-state artifacts, sessions, gates).

### How this host installs it

The plugin is authored as a Claude Code plugin. This host reaches it through its own route
(Steps 1 and 5 below); Claude commands and agent definitions do not automatically become
native host commands or profiles, and the slash commands (`/coordinator:install`,
`/coordinator:setup`) belong to Claude Code. This document gives the shell steps that run
here; finish a leg that needs a slash command from a Claude Code session.

### The settings home

The install lands in the **settings home**, `~/.coordinator-claude-settings` (or
`$COORDINATOR_SETTINGS_HOME`): `bin/` (resolver and CLI forwarders), `machine-local/` (registry),
`coordinator-claude/` (plugin copy), `state/`. Confirm a write with
`ls -lt "$(dirname "$(machine-local dir)")/bin" | head` — fresh mtimes mean this install wrote it
Every run rebuilds `install-receipt.json` from that run's resolution journal, so its writer
list names this run's writers. If the rebuild fails, the install prints an `[ADVISORY]` line
and the receipt on disk may be from an earlier run.

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
| **The engine** | One hard dependency, not part of this clone. Installed at § Step 3, **after** the environment wiring (Step 2). |

### Linux preflight and optional tools

Start here on a fresh Linux box, before Step 1. Use the distro Python 3.11+ and install pip
explicitly: stock Debian/Ubuntu may ship neither pip nor ensurepip. Have the human approve
package changes and sudo authentication. Choose the command for the distro:

```bash
sudo apt install git python3 python3-pip
```

```bash
sudo dnf install git python3 python3-pip
```

Verify `git --version`, `python3 --version`, `command -v python3` and
`python3 -m pip --version`. Keep that resolved ambient interpreter throughout the install.
PEP-668 protects distro site-packages; engine dependencies belong in the installer's
`<settings-home>/engine-site`. Do not bypass it with global pip or introduce a runtime venv.
If provisioning is refused, preserve the failure for the engine owner.

| Tool / tier | Debian/Ubuntu | Fedora / alternative |
|---|---|---|
| `gh`, clone authentication | `sudo apt install gh` | `sudo dnf install gh`; if unavailable, use https://cli.github.com/manual/installation |
| `bash`, advisory | `sudo apt install bash` | `sudo dnf install bash` |
| `node` 18+ and `npm`, optional LSP/JS tooling | `sudo apt install nodejs npm` | `sudo dnf install nodejs npm`; check the installed Node version |
| `git-lfs`, optional | `sudo apt install git-lfs` | `sudo dnf install git-lfs` |
| `jq`, optional | `sudo apt install jq` | `sudo dnf install jq` |
| `uv`, optional LSP installer | `sudo apt install pipx`, then `pipx install uv` | `sudo dnf install pipx`, then `pipx install uv`, or https://docs.astral.sh/uv/getting-started/installation/ |
| `pwsh`, advisory | Follow https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-linux | Same; do not assume a distro package named `pwsh` |
| `scc`, 1Password CLI, optional | Use the vendors' Linux packages only when selected | Same |
| `ty`, `tsgo`, optional pinned backends | Let `python <plugin-root>/scripts/lsp_stock_plugins.py --install` consume the plugin's pins using `uv` and `npm` | Same; do not substitute latest global versions |

Run `gh auth login`, then `gh auth status`; authentication is separate from package presence.
For distro npm, `npm config set prefix "$HOME/.local"` keeps selected global tools user-owned.
Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.profile` for login shells and `~/.bashrc`
for interactive Bash, then open a new terminal and verify selected tools resolve. Services
and non-interactive shells may not read these files; use the resolved interpreter and tool
paths there. Linux uses systemd user units or cron where the installer supports them, rather
than launchd or schtasks; report what the plan actually offers, never create an unrequested job.

Work from any directory, including a neutral folder outside a repository. Resolve both
clone roots to absolute paths and invoke scripts through those roots. The source clone,
installed plugin, settings home and current project are distinct; project onboarding is
a later per-project action, never a reason to scaffold the install session's current folder.

### Your host

The Grok CLI is required to begin. `grok` lives under the home at `.grok/bin`, which an
older session's PATH may lack; call it by full path or restart the shell. The slash
commands (`/coordinator:install`, `/coordinator:setup`) and the Claude restart do not exist
in Grok, so the install cannot close inside a Grok session: finish it from a Claude Code
session or the shell steps. From PowerShell, call `machine-local.cmd`; the extensionless
`machine-local` printed nothing and still reported exit 0.

### Status line parity

Every host shows the same three status-line fields the Claude Code status line shows: the
session's Unimatrix SendMessage name, context remaining before compact, and estimated session
spend. The name is per session and collision-free, like `myrepo-50`; it is never
`codex-<repo>`, which collides as soon as a second session starts in the folder. A field the
host cannot observe shows `unknown`, never zero and never a full gauge.

**Required default, unverified.** The installer-owned default is automatic: bare `grok` shows
the fields after normal installation, with no per-session `/statusline`, no opt-in flag and no
hand-built payload. A host without native multiline status gets an automatic companion started
by the installed integration (a hand-launched companion does not count). Windows, macOS and
Linux are each unverified until observed, and zero appears only when observed.

**Configured in:** `[ui.status_line]` in `$GROK_HOME/config.toml` (default `~/.grok/config.toml`),
with `type = builtin | command | disabled` (default disabled), `items`, `command`, `padding` and
`refresh_interval`. It is read at startup and settable only from the user's own config.

| Field | Shows at default launch | Must show |
|---|---|---|
| Unimatrix name | nothing | the per-session registered name, mapped by a `type = "command"` script from `session_id` / `session_name` |
| Context before compact | nothing | context remaining before compact, from `context_window.remaining_percentage` and `auto_compact_threshold_percent` (the builtin `context` item) |
| Session spend | nothing | the estimated session spend from the builtin `cost` item; absent until priced, so `unknown` rather than zero |

**Required default, not yet shipped:** after normal installation the installer seeds
`[ui.status_line]` itself, so bare `grok` shows the status line with no opt-in flag, no
per-session setting and no hand-built payload. That is a requirement, not a claim that it is
published, installed or rendered: this page records no observed behavior, and Windows, macOS and
Linux are each unverified until observed there. The optional model, effort and engine-run fields
are staged and shown by no renderer yet. An unobserved value is `unknown`; zero appears only when
observed; spend with a missing rate or child is partial, marked `+`; the name is the exact
registered alias and is absent before registration. Without native multiline status, an
automatic companion started by the installed integration is required; a companion launched by
hand does not satisfy the default. Configuration changes keep the user's own keys, and rollback
removes only the installer's entries and regenerates from the restored install source.


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

**Linux:** the distro `python3` (3.11+), with `git`, `pip` and `gh` from the distro. Debian and
Ubuntu, then Fedora and RHEL:

```bash
sudo apt install -y git python3 python3-pip gh
sudo dnf install -y git python3 python3-pip gh
python3 -m pip --version
gh auth status
```

`gh` missing from the distro's repositories: install it from `https://cli.github.com`, then
`gh auth login`. `gh auth status` must succeed before the clone steps.

**Windows:** python.org 3.11+, with the App Execution Alias
stubs disabled (Settings, Apps, Advanced app settings, App execution aliases), and Smart App Control
checked (§ Windows: Smart App Control).

### `gh` without Homebrew

Linux: use the distro `gh` package or the official GitHub CLI installation instructions
linked in Linux preflight, then authenticate. On macOS without brew, download the `.zip`/`.pkg` for the box's arch from
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
The engine's `python3 scripts/setup.py --check` launches one forwarder and reports a blocked launch as
`FAIL [forwarder-launch]` naming SAC; an install step that hits the block reports BLOCKED:
"re-run the install and choose forwarder_route=py (works with Smart App Control on), or turn
Smart App Control off for the .exe route, then retry". `--check` fails only on the execution
policy of the PowerShell the engine uses (`pwsh` first); the other PowerShell shell warns.

**Switching routes later:** answer `forwarder_route` again in the Step 2 `--answers` document
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
  `python3 -m pip install --user --break-system-packages notebooklm-mcp-cli`; Linux
  distro Python (PEP-668): do not use `--user` here, use the isolated tool option below;
  Windows python.org `py -3 -m pip install --user notebooklm-mcp-cli`. The scripts land in
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
  plugin loads (Step 4).
- **A foreign-platform `statusLine.command` box.** `~/.claude` can be git-synced across boxes, so
  a POSIX `statusLine.command` can land on Windows (or the reverse). It is the human's call:
  re-run the Step 2 environment wiring to regenerate it, or correct `statusLine.command` in
  `~/.claude/settings.json` by hand.
- **"Friction: memo ..."** names inboxes that exist only on the authoring fleet. File friction as
  an issue or PR on `dbc-oduffy/coordinator-claude` (`CONTRIBUTING.md`); with no network route,
  write a dated friction-log markdown file in the working directory and hand its absolute path to
  the human.


## Step 0 — Detect: which track?

The installer decides the track; never pick one by hand or infer it from probes of `~/.claude`.
**Cold box: complete prerequisites and Step 1 first.**
Set `CLAUDE_PLUGIN_ROOT` to the absolute plugin root (the public clone root).
POSIX: `export CLAUDE_PLUGIN_ROOT="<resolved-plugin-root>"`;
PowerShell: `$env:CLAUDE_PLUGIN_ROOT='<resolved-plugin-root>'`. This locates source files
without activating plugin hooks. Once both source roots exist, run:

```bash
python3 "<klabauter-clone>/lib/install/coordinator_install.py" --plan
```

Read `environment.track` (with `track_reason`) from the JSON.

**That engine copy is the one authoritative `coordinator_install.py`.** Run it from the
`claude-klabauter` clone for `--plan` and `--answers` alike; do not run a copy of it found under
the plugin root, even if a command text names one.


### Tracks

- **`fresh`** — no coordinator plugin installed. Acquire sources in Step 1, then provision.
- **`update`** — installed; the installer performs the update itself (`plugin_update`,
  `engine_setup`, `engine_check`). `track_reason: already current` drops `plugin_update`. Skip
  source acquisition when the roots are already resolved; go to environment wiring. A box
  installed before 8e7aef49ad that has NotebookLM registered as `notebooklm-mcp` runs
  `nlm setup add claude-code` once; it renames the entry in place to `gemini-notebook-mcp`.
- **`repair`** — installed, not newer, engine check fails or the engine is unlocatable. Report
  `track_reason`. Keep existing resolved sources and go to environment wiring.

**First install may report `repair`** after plugin registration because engine provisioning
is incomplete. Follow the returned track and report its findings; never force `fresh` or
describe this alone as a broken prior install. No plugin/source root means start at Step 1,
not an attempt to run a nonexistent script. The installer chooses the track once available.

### Grok ignores the skip rule

The track reflects Claude's plugin registry only. On `update` and `repair`, source reuse
still leaves § 1d: run `grok plugin install` unless `grok plugin list` already names `coordinator`.

### Who runs what

When the PM's stated intent in this session is to install or set up, the agent runs `--plan`
and `python3 <klabauter-clone>/scripts/setup.py --i-am-agent` (the `engine_setup` and
`engine_check` leg) through the shell. `plugin_update` is Claude Code's plugin leg: an agent
never hand-runs `claude plugin update` — on `update`, hand the human that command.

### Existing home — disclosure, not routing

What `~/.claude` already holds (the installer's INHERITED rows) is disclosed, never routed on. The
install merges config rather than overwriting, so **proceed and report; do not stop**, and tell
the human afterwards what you found and did. **Stop and ask only on a genuine conflict** — a file
the install would have to *overwrite*, or coordinator infra of unestablishable provenance. Name
the file and the clash.

Setup clones or adopts the user's `group-em` and `.claude` GitHub repos without overwriting a
file, and links both homes into the repos folder (`machine-local get coordinator.repo_home`);
report each home's action line to the human.

## Step 1 — Install the plugin tree into Grok

Grok installs a copy of the plugin tree, not a link. Read 1d before running it.

### 1a. Clone or locate the repo

The clone provides helper scripts and the offline/dev variant. **Keep it**: the engine's
`<klabauter-clone>/scripts/setup.py` resolves coordinator-claude as a sibling at Step 3.

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

### 1d. Install the plugin tree (`grok plugin install`)

Run it on every track, including `update` / `already current`: `--plan` reads only Claude's plugin
registry, and no other command puts the plugin into Grok. Install from a **clean source**, never a
working clone root: that copies `.git`, `scratch/`, `state/` and `.coordinator-local/`. Either
install from GitHub, which fetches the committed tree:

```bash
grok plugin install dbc-oduffy/coordinator-claude --trust
```

or export the clone's tracked files into a fresh empty directory (bash; Git Bash on Windows) and
install from that:

```bash
mkdir <plugin-src>
git -C <coordinator-clone> archive HEAD | tar -x -C <plugin-src>
grok plugin install <plugin-src> --trust
```

The plugin root is the directory that holds `.claude-plugin/` and `bin/`: the clone root for the
public repo.

- **It copies.** The command copies the source tree into `~/.grok/installed-plugins/`; it does not
  link, so edits in the checkout never reach the installed copy. The `local:` path in
  `grok plugin list` is provenance, not a link. Treat the installed copy as a snapshot.
- **It flattens the component count.** `grok plugin validate` is green but reports one skill
  dir, one command dir and one agent dir for the whole plugin. Whether Grok executes
  `hooks/hooks.json` (Claude event names) is unverified. Do not count a Grok install as governed.
- **Windows: set `GROK_SHELL=bash`.** On Windows Grok runs hook commands under pwsh and ignores
  a hook's `"shell"` field, so the plugin's bash hooks fail (`VAR=value` prefixes are not
  recognized; ParserErrors). Set it once per user, then open a new shell:
  `[Environment]::SetEnvironmentVariable('GROK_SHELL','bash','User')`.
- **Restart before hooks can fire.** A running Grok session does not pick up the installed
  plugin's hooks; start a new session.
- **Inspect by name.** `grok plugin details` takes the plugin name (`coordinator`), not the
  marketplace id that `grok plugin list` prints first; the id returns `Plugin not found`.
- **It is not the engine install.** The Grok install path never reads the settings home
  (`COORDINATOR_SETTINGS_HOME`) or runs the engine installer, and there is no
  `/coordinator:install` in Grok. Handoffs, memos, coverage and guards still need the engine
  (Step 3) and Claude hooks.

### 1e. Clone the engine and register it — a clone, **not** an install

The engine is installed in Step 3, but its **clone must exist now, before Step 2**:
the environment wiring's Phase 3 bootstraps the substrate from a script inside the engine repo,
and Step 2 fails on its first command with an unset root otherwise. The order is
**sources, environment wiring, engine installation, activation, verification** (why:
`docs/wiki/install-playbook-rationale.md` § Step 3).

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
once it runs; this hand-set is the cold-box bootstrap (Step 3 needs the key first):

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

## Step 2 — Finish the environment from the shell

`/coordinator:install` is a Claude Code slash command; it does not exist here. Its environment
wiring is a script with declared choices, `<klabauter-clone>/lib/install/coordinator_install.py`
(orientation, then `--plan`, then `--answers`; safe to re-run; reports every step RAN, SKIPPED,
INHERITED or FAILED). It checks prerequisites, lays down the machine-local registry, scaffolds
the canonical document structure and records the `setup_concluded` receipt. **Phase 3 deposits
the `machine-local` resolver** that Step 3 depends on. Run it through the shell, or finish this
leg from a Claude Code session.

### Read the plan and report effects

Set `CLAUDE_PLUGIN_ROOT` to the resolved plugin root for both calls (the public clone root),
without loading the plugin. POSIX uses
`export CLAUDE_PLUGIN_ROOT="<resolved-plugin-root>"`; PowerShell uses
`$env:CLAUDE_PLUGIN_ROOT='<resolved-plugin-root>'`.
Then invoke from any directory with absolute roots.
POSIX: `python3 "<klabauter-clone>/lib/install/coordinator_install.py" --plan`;
PowerShell: `& "<resolved-python>" "<klabauter-clone>/lib/install/coordinator_install.py" --plan`.
Show the returned orientation before asking posture and optional choices. Apply the complete
answers using the same script with `--answers <answers-file>`; never invent decision IDs.
The installer persists posture into `~/.claude/coordinator-identity.yaml`, custom text as
`posture_text`; never hand-write em-context.md.

Before consent, describe resolved files, shortcuts, clones, scaffolds and timers from the
actual plan. Relay progress and report RAN, SKIPPED, INHERITED and FAILED effects.
Missing paths/effects, silent long work or unactionable errors are engine defects to capture.
End with every unfinished step and remedy. Session banners and a first-install repair track
do not replace script results; defer normal project work until the install is ready.

### Ask the human once: posture and every optional extra

Show the plan's orientation before posture. Before `--answers`, put **one** numbered questionnaire to the human in a single message and take
the answer as one string; never answer an optional extra for them, and never drop one because a
non-interactive default would skip it. Say what each "no" leaves out:

1. **Posture** (offer it, never declare it; show the current value as the default and ask on
   every guided install, never inherit it silently): `precision` (close to the work), `default`
   (the PM/EM middle ground, the engineering manager acts and pushes back), or `substrate-free`
   (maximum altitude: "build me X"). Free text the human adds travels as `posture_text`, composed
   into every repo's overlay render.
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

## Step 3 — Install the engine (`claude-klabauter`)

coordinator-claude and its engine are **one joint installation**. Without the engine, planning,
review and personas work; claiming handoffs, memo resolution, coverage and terminal stamping do
not. **The sequence, literally:**

### The sequence

Acquire sources and register the engine root (Step 1), provision the environment (Step 2),
then install the engine here. Only after both scripts succeed, activate in the following
stage and run the verifier. /coordinator:setup verifies; it never deposits the substrate.
If a cold script requires a loaded plugin, stop with its exact command, output and missing
prerequisite. Never silently activate hooks against an incomplete substrate. A clean Linux
cold run remains required before claiming this sequence runtime-verified.

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
4. **Run the agent install path**, non-interactive, through the resolved absolute clone path:
   ```bash
   python3 "<klabauter-clone>/scripts/setup.py" --i-am-agent
   ```
   (Windows: `python "<klabauter-clone>/scripts/setup.py" --i-am-agent`.) It checks dependencies
   (including the Step 2 resolver), installs, and registers the engine. Relative to the
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


## Step 4 — Activate in a fresh session

After environment wiring and engine provisioning succeed, Codex and agy must complete
Step 5 before opening a fresh session. Then use this host's documented launch route;
Grok uses Step 1d. Claude Code loads the provisioned plugin in its fresh session; run
the verifier below. Do not paste /coordinator:install merely to activate it.
Honor the installer's restart classification: none, /reload-plugins or restart; request
another restart only on restart.

### Run the setup verifier after activation

**`/coordinator:setup`** walks `direct_deps`, verifies the engine is satisfied and emits the
chain-complete banner. It installs nothing; run earlier it fails loud with "engine not
satisfied." It is a Claude Code slash command: run it from a Claude Code session after the
engine install. Until then, the engine installer's `PASS`/`FAIL` output is the only engine verdict.

## Step 5 — Unimatrix for Grok

Grok is its own host, not an alias of agy, and needs no hooks to join Unimatrix: the box router
discovers live Grok sessions from `$GROK_HOME/active_sessions.json` (via `_unimatrix/adapters/grok.py`
and spawn-free `libproc` process inspection on macOS) and delivers each message as a
cwd-pinned headless resume (`--permission-mode dontAsk`). Grok is opt-in: bare `--install` seeds the relay and no host, so name
it, `unimatrix-install.py --install --hosts grok`. That vendors `_unimatrix/` beside the CLI scripts and seeds three files under `$GROK_HOME`
(default `$HOME/.grok`, `%USERPROFILE%\.grok`):

- the status line, as `[ui.status_line]` in `config.toml`; it never overwrites a status line you set;
- the peer-doctrine rules file `rules/unimatrix-peer-doctrine.md` (Grok loads every `*.md` there);
- a `PreToolUse` host-guard hook, `hooks/coordinator.json` (`--host grok`), over the shell and edit tools.

`--uninstall` removes all three. No skill seeder exists for Grok. Run the installer from a tree that
ships `templates/unimatrix/peer-doctrine.md`; without it the install exits 1. Peer mechanics:
`docs/wiki/unimatrix-mechanism.md` § Peer registration.

The Grok CLI has no winget or npm package; install it by its vendor's instructions first, then
open a new terminal.

### Pre-installing before the host CLI lands

**A Grok absent from `PATH` is skipped, not pre-seeded.** `unimatrix-install.py --install --hosts
grok` prints `grok hook skipped: grok not on PATH and a leftover home does not count` and writes
no status line, peer-doctrine rules file or hook; a leftover `$GROK_HOME` alone is not presence.
The CLI creates `$GROK_HOME` itself on first run; do not create it by hand.

- **Completing run:** once `grok` is on `PATH`, run `unimatrix-install.py --install --hosts grok`
  to seed the status line, the peer-doctrine rules file and the `PreToolUse` host-guard hook.
  It is idempotent, so a box where Grok already ran may already carry them.
- **The one CLI-free file:** the per-checkout `.grok/config.toml` project-rag entry (see
  "Step 6 — project-rag access"); it lives in the checkout and needs no Grok install.

## Step 6 — project-rag access (PROVISIONAL)

> **Provisional.** Tested on Grok only; Codex and agy are untested. Owned by project-rag, whose
> maintainers may revise it. No SCIP or LSP parity is claimed for Grok, agy or Codex: that is
> unassessed.

1. **Register the checkout as a project root.** It must be a registered project root in the
   project-rag `projects.json` (under `<settings-home>/project-rag/`). A checkout that is not a
   registered root stays ambiguous: the daemon cannot select it.
2. **Add a per-project MCP entry** for `http://127.0.0.1:8767/mcp` with the header
   `x-project-rag-roots: <checkout path, forward slashes>`. For Grok that is
   `.grok/config.toml` in the checkout, a `[mcp_servers.project-rag]` table; it takes effect in
   a new session. For Codex and agy use the host's own per-project MCP configuration for the
   same URL and header (untested). A plugin-shipped `.mcp.json` cannot carry this: the header
   is per checkout.
3. **Verify with a real call:** `project_file` with no `repo`. `no_source_resolved` and
   `peer_scan_ambiguous` are failures. Never verify through `grok inspect`: it attributes the
   entry to the wrong file and shows no header.
4. **Fallback:** pass `repo=<key>` on tools that advertise it.

**With the host CLI absent:** only Grok's `.grok/config.toml` is a file in the checkout, so it
can be written before `grok` lands. The Codex and agy per-project locations are untested, so no
entry is pre-seeded for them, and the live `project_file` check in item 3 needs the CLI. Owner
gate (project-rag): pre-seed per-host entries for registered checkouts where the host CLI is
absent, with the Codex and agy locations confirmed.

## Verifying your install

Don't infer coordinator is live from the absence of errors:

### This host

1. **Launched from a fresh session of this host** after the install, so the installed
   configuration is loaded.
2. **Native execution is what counts.** A successful file copy or read-only check is not proof of
   native execution. Verify actual hook discovery from inside the host session.
3. **Do not count a configured host as governed** until its own hooks are shown to fire.
   For Grok, whether `hooks/hooks.json` executes at all is unverified.




## Failure modes

- **`grok` is command not found.** It lives under the home at `.grok/bin`; call it by full
  path or restart the shell.
- **`grok plugin details` says `Plugin not found`.** Pass the plugin name (`coordinator`), not
  the marketplace id that `grok plugin list` prints first.
- **Edits in the checkout do not show up in Grok.** The install copied the tree; it is not a
  link (Step 1d).
- **Hooks do not fire.** Start a new Grok session; whether Grok executes `hooks/hooks.json` at
  all is unverified.

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

## More detail

- Guided runbook, one phase at a time: `commands/install.md`. Reversing an install:
  `commands/uninstall.md`. Install-chain walker: `docs/install/AGENT.md`.
