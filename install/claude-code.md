<!-- INSTALL-DOE-ONLY:BEGIN -->
<!-- GENERATED FILE: do not edit. Source: install/steps.yaml; regenerate with `python setup/gen_install_docs.py`. -->
<!-- INSTALL-DOE-ONLY:END -->

# Installing coordinator-claude with Claude Code

## Two legs, both yours

coordinator-claude is the doctrine; the coordinator engine (`claude-klabauter`) is a
**hard co-requisite** most state-mutating flows fail without. An install that stops after
leg 1 is incomplete — do not report it as done.
<!-- INSTALL-DOE-ONLY:BEGIN -->

**In this repo (coordinator-content-repo), you are installing the doctrine source itself, not a downstream
consumer of it.** Its `coordinator/` tree resolves live as the plugin, no publish step required.
Its engine dependency is the same one every other install has: the published `claude-klabauter`
mirror. Where the text says "register the public GitHub repo as the marketplace," read "register
this clone" — see the DoE-only notes in each step.

**`claude-klabauter` is where engine changes are authored; it is never the resolved engine root.**
Its working tree moves constantly. The one carve-out is the explicit live-tree env override, the
PM's manual test-and-execute path.
<!-- INSTALL-DOE-ONLY:END -->

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
| NotebookLM MCP | Optional (deep-research Pipeline D). Install per the [upstream README](https://github.com/jacob-bd/gemini-notebook-mcp-cli); it registers as `gemini-notebook-mcp`. No venv needed; the walk-through does not install or register it. |
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

<!-- INSTALL-DOE-ONLY:BEGIN -->

**The engine is a hard dependency, including OSS-mirror installs.** The engine root resolves via
a ladder (env var, then the `repos.claude_klabauter` registry key, then a sibling-dir default) to
the published `claude-klabauter` mirror — see `coordinator/docs/install/AGENT.md` § Fail-loud
Claude-klabauter resolution. `claude-klabauter` is private (a 404 clone means access is not granted); the
install does not need it.
<!-- INSTALL-DOE-ONLY:END -->

## Step 0 — Detect: which track?

The installer decides the track; never pick one by hand or infer it from probes of `~/.claude`.
Clone `claude-klabauter` (Step 1e; Step 4 keeps that clone), then run:

```bash
python3 <klabauter-clone>/lib/install/coordinator_install.py --plan
```

Read `environment.track` (with `track_reason`) from the JSON.

<!-- INSTALL-DOE-ONLY:BEGIN -->

**On a DoE box, prefix the command with `CLAUDE_PLUGIN_ROOT=<DoE clone>/coordinator`.** The
script defaults the plugin root to the engine clone when the variable is unset (a harness sets it
only inside a command), reads the engine's own manifest, and reports `manifest/step drift`:
that error is this missing variable, not real drift. The DoE box registers no plugin, so `--plan`
reports `fresh` there and lists a `plugin_install` step; ignore the track and follow § Launching
a session (Claude Code). That `plugin_install` step is the Claude plugin registration this box
skips by design, for every agent type.

The predicates behind each value are in
`coordinator/docs/wiki/install-playbook-rationale/install-command-residue.md`.
<!-- INSTALL-DOE-ONLY:END -->

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

## Step 1 — Install via the `claude plugin` CLI

Wire the whole system before the restart, so the fresh session comes up coordinator-shaped.

### 1a. Clone or locate the repo

The clone provides helper scripts and the offline/dev variant. **Keep it**: the engine's
`<klabauter-clone>/scripts/setup.py` resolves coordinator-claude as a sibling at Step 4.

```bash
git clone https://github.com/dbc-oduffy/coordinator-claude.git ~/coordinator-claude
```
<!-- INSTALL-DOE-ONLY:BEGIN -->

**coordinator-content-repo's own install has no clone step and no plugin install.** This repo *is* the clone;
the engine installer registers its `coordinator/` subdirectory as the live plugin. Skip 1a and
the plugin-install commands of Step 1.
<!-- INSTALL-DOE-ONLY:END -->

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
<!-- INSTALL-DOE-ONLY:BEGIN -->

**On a DoE box, do not run the two commands above, and register no coordinator plugin at all.**
Plain `claude` stays vanilla Claude Code. The only entry is the `coordinator` shell function: it
runs `claude-author` (`--plugin-dir` at this clone's `coordinator/`) with
`--dangerously-skip-permissions`, so it always serves the live clone. No
`coordinator@coordinator-claude` record in `installed_plugins.json` or `enabledPlugins`, and no
`coordinator-claude` key in `extraKnownMarketplaces`, is correct
(`docs/decisions/DR-plain-claude-is-vanilla-on-a-doe-box.md`). A `coordinator` session with no
coordinator skills is a launcher problem; check with a real launch (§ Launching a session).

**One-shot alternative — `coordinator-install`.** A single non-interactive trampoline performs the
engine-side steps (registry substrate and the rest of the chain); the `claude-author` shim and
`.content-root` pointer steps are the DoE copies (`coordinator/bin/gen-claude-author-shim.py`,
`setup/doe-tools/gen-content-root-pointer.py`), run as in `coordinator/commands/install.md`:

```bash
"$(dirname "$(machine-local dir)")/bin/coordinator-install"   # --check-only to probe first
```

The trampoline sits under `<settings-home>/bin/`. **Do NOT invoke
`coordinator_core/install/maximalist.py` directly** — it refuses without the env the trampoline
exports. **Not a cold bootstrap:** it needs a resolvable engine root; confirm with
`python3 coordinator/hooks/scripts/_engine_root.py` (exit 2, empty stdout: do § Step 1e first).
`--check-only` does not verify the install. **Windows:** run `scripts\setup.cmd` under the
resolved engine root. Caveats: `coordinator/docs/wiki/install-playbook-rationale.md` § One-shot
alternative.
<!-- INSTALL-DOE-ONLY:END -->

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
<!-- INSTALL-DOE-ONLY:BEGIN -->

**On a DoE box the channel is `candidate`, not `main`** (the value the engine installer writes on a
makers' box): set `engine.target candidate` and `git -C <klabauter-clone> switch candidate`.
Without `engine.target`, the sibling `claude-klabauter` working tree answers as the engine root.
<!-- INSTALL-DOE-ONLY:END -->

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
<!-- INSTALL-DOE-ONLY:BEGIN -->

**On a DoE box plain `claude` is vanilla by design, and the `coordinator` function does not exist
until the launcher is wired.** The first coordinator-loaded session is
`claude --plugin-dir <DoE clone>/coordinator` (paste `/coordinator:install` there); or the agent
runs the installer scripts directly through Bash, as `coordinator/commands/install.md` lays them
out. From the second session on, use `coordinator` (§ Launching a session).
<!-- INSTALL-DOE-ONLY:END -->

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
reports `backend X missing` and exits 1 when `ty` or `tsgo` is absent). The pins are bumped as
the tools release; `machine-local set lsp.front_backend pooled` is the per-box rollback to
pyright and typescript-language-server.
<!-- INSTALL-DOE-ONLY:BEGIN -->

In this repo the plugin root is `coordinator/`.
<!-- INSTALL-DOE-ONLY:END -->

<!-- INSTALL-DOE-ONLY:BEGIN -->

### DoE-only: launching a session — `coordinator`, never plain `claude`

`coordinator` runs `claude-author` (`--plugin-dir` at this clone) with
`--dangerously-skip-permissions`; edits here take effect next session with no reinstall. Plain
`claude` loads no coordinator and is never shadowed. The launcher chain is this clone's:
`coordinator/bin/gen-claude-author-shim.py` (the function; it supplies the default `--template`)
and `setup/doe-tools/gen-content-root-pointer.py` (the pointer), run by `coordinator-install` or as in
`coordinator/commands/install.md`. The engine's `scripts/setup.py` neither installs nor accepts
the launcher chain. A bad pointer or missing `claude-author` fails loud. **Verify with a real
launch** (`coordinator -p "reply ok"`); `--version` short-circuits and proves nothing
(`coordinator/docs/wiki/coordinator-tripwires/a-launcher-check-that-never-launches-is-born-passing.md`).
The launch's SessionStart orientation can switch this clone from `main` to the day's
`work/<box>/<date>` branch, carrying uncommitted edits: run the check on a clean tree, or expect
the switch. `<klabauter-clone>/scripts/unstick_claude.py` removes the shim.

**Pointer names.** `repos.content_root` is the canonical registry key; `repos.doe_claude` is its
legacy spelling and `ensure-doe-clone.py` still reads it, so set both to the clone path. The
installer writes the pointer file `<settings-home>/machine-local/.coordinator-content-root`
(with a `.content-root` twin beside it); `.content-root` in older text means that pointer.
The engine's help for the shim names `gen-claude-author-shim.sh` and says "for claude() to take
effect": it is the `coordinator()` function that takes effect, in a new shell.
<!-- INSTALL-DOE-ONLY:END -->

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
2. **Windows:** disable the Python App Execution Alias stubs first (§ Requirements). Python 3.11+.
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

<!-- INSTALL-DOE-ONLY:BEGIN -->

**In this repo the steps above apply verbatim — clone and install `claude-klabauter`**, never
`claude-klabauter` (its warm tree moves too fast to be a stable root). Author engine changes in
Claude-klabauter, percolate to klabauter, install klabauter.

**Pass `--coordinator-root <DoE clone>` to the Step 4 command**:
`python3 <klabauter-clone>/scripts/setup.py --i-am-agent --coordinator-root <DoE clone>`.
Without it the root ladder takes the sibling `coordinator-claude` directory (the OSS publish
mirror) as content root, registers it as `repos.content_root`, and downgrades `engine.target` to
`main`, all with exit 0. Recovery: re-run with the flag, then fix `repos.content_root` and
`engine.target candidate` by hand with `machine-local set` (a re-run does not rewrite them).
Confirm what answered:

```bash
python3 -c "import sys; sys.path.insert(0,'coordinator/hooks/scripts'); \
import _engine_root as e; print(e.resolve_claude_klabauter_root_with_provenance())"
```

Healthy prints the klabauter path with class `resolved-engine`, provenance `published-target`. A
`live-working-tree` class pointing at `claude-klabauter` is the misconfiguration to prevent.
`scripts/setup.ps1` does **not** exist in either engine repo; do not cite one.
<!-- INSTALL-DOE-ONLY:END -->

## Step 5 — Unimatrix cross-box messaging

Unimatrix carries cross-box idle notices between boxes.

<!-- INSTALL-DOE-ONLY:BEGIN -->

### Optional: Unimatrix cross-box messaging

Boxes on the same Claude account reach each other over native `/rc` (`ListAgents` plus
`SendMessage` by name); skip this step for them. Unimatrix serves cross-account boxes and carries
cross-box idle notices (bridge pipes are named `cc-msg-<32 hex>`). Check mode
is the default and refuses outside the verified Claude Code range (`--force` downgrades the
refusal to a warning):

```bash
python3 coordinator/bin/unimatrix-install.py            # macOS / Linux; Windows: python
python3 coordinator/bin/unimatrix-install.py --install  # only after "in verified range"
```

**Transport: LAN first, tunnel off-network only.** Boxes on the same network reach each other
directly over the LAN with the tunnel off; Unimatrix tooling tries the LAN address first and never
requires the tunnel. A roaming box (a laptop away from home) reaches the home boxes over a
self-hosted WireGuard tunnel that terminates on the home router; no third-party service (no
Tailscale). The roaming box joins the home LAN over the tunnel, then SSH to the relay works as on
the LAN. Set up the router's WireGuard server and each roaming box's peer by the router vendor's
own instructions; the peer private key is vault-resident per box. No router model, endpoint,
address or key body belongs in a tracked file. **On Windows, keep the tunnel inactive while on
the home LAN:** a split-tunnel peer whose AllowedIPs include the home subnet routes it ahead of the
NIC, so local traffic hairpins through the router. macOS keeps the LAN on its own interface.

**Windows sshd and admin accounts.** For an account in Administrators, OpenSSH reads
`%ProgramData%\ssh\administrators_authorized_keys`, never `~/.ssh/authorized_keys`, and ignores
that file unless its ACL grants only Administrators and SYSTEM. Key changes need no restart; on
Windows 11 `Restart-Service sshd` fails because `SshdBroker` depends on it.

**Key naming.** Each key is named `<role>: <from> → <to>`. Roles: `Unimatrix-01` is full shell,
break-glass; `Unimatrix-Zero` is the comms relay only; `Unimatrix-02` is the project-rag tunnel
only. One key per box pair, so a leak's blast radius is that pair; Zero is needed one way per pair
because the initiating box holds the inbox connection. Unimatrix-01 is a full mesh: "we should be
able to pick any one box as the controller or controlled, so long as the keys authenticate etc
etc". The one network-wide G-EM reaches other boxes over these keys; any box may hold it (last
writer wins). 1Password's CLI cannot edit SSH Key items, and a CLI import of an existing OpenSSH
key lands unparsed: import and rename in the app (`op --ssh-generate-key` is fine).

Route order and key custody: `coordinator/skills/group-em/references/multibox.md`,
`coordinator/docs/wiki/multibox-key-custody.md`.
<!-- INSTALL-DOE-ONLY:END -->

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

<!-- INSTALL-DOE-ONLY:BEGIN -->

### In this repo

**Tests resolve.** `python -m pytest coordinator/tests` should collect and run (see § Build &
Test in this repo's `CLAUDE.md`); the OSS mirror ships no such tree.
<!-- INSTALL-DOE-ONLY:END -->

<!-- INSTALL-DOE-ONLY:BEGIN -->

## Machinery locations

The executable install-chain surface (orchestrator, `scripts/setup.py`, substrate writer,
`normalize_env`) lives in `claude-klabauter` and resolves via the engine-root ladder; the DoE-clone
scripts are in `setup/doe-tools/` and `coordinator/bin/`. Path table and phase order:
`coordinator/docs/wiki/install-playbook-rationale.md` § Machinery locations.
<!-- INSTALL-DOE-ONLY:END -->

<!-- INSTALL-DOE-ONLY:BEGIN -->

## Percolation surface

`/percolate` needs a hand-provisioned `.percolate-identity` (copy
`coordinator/templates/setup/.percolate-identity.example` to `setup/.percolate-identity` and fill
`PERSONAL_REVIEW_PATTERNS`). Provisioning and the `publish.py --dry-run` check:
`coordinator/docs/wiki/install-playbook-rationale.md` § Percolation surface.
<!-- INSTALL-DOE-ONLY:END -->

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
<!-- INSTALL-DOE-ONLY:BEGIN -->

**This repo is the exception to its own rule:** it *is* the source, so editing `coordinator/` here
is the intended workflow.
<!-- INSTALL-DOE-ONLY:END -->

## Failure modes

- **`claude plugin install` reports nothing.** Add the marketplace first; the key is
  `<name>@coordinator-claude`.
- **`/reload-plugins` reports `0 plugins`.** Usually a clone-bound marketplace whose directory
  moved: re-register from GitHub, then `/reload-plugins`.
- **Commands missing after install.** Hooks and commands load at startup; restart (Step 2).

### Reporting rough edges

Per-project config is `coordinator.local.md` (`/coordinator:repo-setup` writes it). If you worked
around a rough edge, offer to send it upstream (PR or issue on `dbc-oduffy/coordinator-claude`;
see `CONTRIBUTING.md`).
<!-- INSTALL-DOE-ONLY:BEGIN -->

**In this repo you *are* upstream.** Fix it here; do not draft a PR against yourself.
<!-- INSTALL-DOE-ONLY:END -->

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
<!-- INSTALL-DOE-ONLY:BEGIN -->
- `coordinator/docs/wiki/DIRECTORY_GUIDE.md` — the wiki index (coordinator-content-repo authoring surface only).
- Percolation topology and the `PERCOLATE_ROOT` chain:
  `coordinator/docs/wiki/install-playbook-rationale/percolate-setup.md`.
<!-- INSTALL-DOE-ONLY:END -->
