<!-- INSTALL-DOE-ONLY:BEGIN -->
<!-- GENERATED FILE: do not edit. Source: install/steps.yaml; regenerate with `python setup/gen_install_docs.py`. -->
<!-- INSTALL-DOE-ONLY:END -->

# Installing coordinator-claude with Codex

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

The Codex CLI is required to begin. The slash commands (`/coordinator:install`,
`/coordinator:setup`) do not exist in Codex: run the shell steps here, or finish those legs
from a Claude Code session.

### Codex EMs and workers

With a Codex-capable published engine, `--plan` includes `codex_runtime`. Choose
`configure` and supply its normal step consent when authorized to change the native
Codex profile. `skip` leaves existing configuration in place. The selected step runs
after the engine and substrate; a failed or unconsented configuration is incomplete.
Keep using the installer-selected fresh, update or repair track.

First verify that the resolved published engine exposes this decision and the shared
runtime installer; a source commit alone does not make them available in an installed
release. On a shared fleet machine, obtain the required shared-resource approval before
applying profile changes. Source validation does not lift a live-install hold.

Merge this fragment into the plan's complete `--answers` document when configuration
and its native profile writes are authorized:

```json
{"codex_runtime":"configure","consent":{"codex_runtime":true}}
```

This is a fragment, not a replacement for the plan's other answers or consents.
Selecting `configure` without that consent fails the step and withholds the concluded
setup receipt. Choosing `skip` does not configure or repair Codex.
<!-- INSTALL-DOE-ONLY:BEGIN -->

For an existing base installation, `coordinator-install --host codex` first runs the
full base installer and, only after it succeeds, runs a second host-only leg using the
same runtime installer.
<!-- INSTALL-DOE-ONLY:END -->
That leg installs the owned lifecycle hooks, native hook trust, role
context, skills and status footer alongside the managed MCP entry. It preserves
foreign configuration. Enrolled profiles are refreshed through that same installer,
including renewed trust when installed hook bodies change.
An existing foreign MCP entry that differs from the requested route stays intact and is
reported as drift; it prevents overall host readiness even if native hooks are current.

When the published engine includes endpoint-aware enrollment, the host leg derives
the MCP URL from this machine's registered `repos.project_rag` checkout and its
`project_rag_mcp/http_config.py`, with explicit environment overrides. A missing or
stale declared source is reported for repair; the installer does not substitute a
guessed endpoint. Enrolled updates check MCP configuration before renewing native
trust. The corresponding doctor layer checks configuration only: it does not prove
native `tools/list`, engine-symbol retrieval, corpus version, or working LSP/hover.
These source capabilities require publication and the applicable live-install GO.

An older engine whose host report says **MCP entry only** has not installed this
runtime support. Update through the published `claude-klabauter` path; do not point
runtime hooks at an editable engine-source checkout or hand-write trust entries.
A successful file copy or read-only check is not proof of native execution. Verify
actual hook discovery, the exact registered messaging address and recipient reply,
worker/EM context separation, and the visible status footer. Unknown usage remains
marked as an incomplete estimate rather than a complete session cost.

### Status line parity

Every host shows the same three status-line fields the Claude Code status line shows: the
session's Unimatrix SendMessage name, context remaining before compact, and estimated session
spend. The name is per session and collision-free, like `myrepo-50`; it is never
`codex-<repo>`, which collides as soon as a second session starts in the folder. A field the
host cannot observe shows `unknown`, never zero and never a full gauge.

**Configured in:** `[tui].status_line` (footer) and `[tui].terminal_title`, each an array of item
ids, in `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`). The runtime step above
installs the footer.

| Field | Shows at default launch | Must show |
|---|---|---|
| Unimatrix name | nothing | the per-session registered name, through the thread title / `thread-name` footer item |
| Context before compact | nothing | context remaining before compact; `context-remaining` is a context-window figure, so the before-compact part stays `unknown` until the compaction threshold is observed |
| Session spend | nothing | the estimated session spend, with `+` marking incomplete coverage; the native `estimated-thread-cost` item has an undocumented pricing basis |

<!-- INSTALL-DOE-ONLY:BEGIN -->
Pending engine work in claude-klabauter: the per-session Codex name source
(ask-20261109T110331-3c2dcf) and the renderers. The matrix is
`coordinator/docs/wiki/non-claude-workers/tui-status-parity.md`; the rule is the tripwire
`A-PEER-HOST-STATUS-LINE-SHOWS-THE-CLAUDE-PARITY-FIELDS`.
<!-- INSTALL-DOE-ONLY:END -->

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

## Step 1 — Get the sources

Host configuration adds no review gate or marketplace step. Step 1 gets the sources the later
steps run from; the host itself is configured in Step 5, after the engine.

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

### 1d. No host install here

There is no plugin-install command to run in this step. The host is configured in Step 5, which
needs the engine from Step 4.

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

## Step 2 — No Claude restart gate

The restart gate and the pasted `/coordinator:install` are Claude Code's; this host has neither.
Go on to Step 3 and run the environment wiring as a script. After the host is configured
(Step 5 for Codex and agy; Step 1d for Grok), start a new session of this host and verify native
discovery from it (§ Verifying your install).

## Step 3 — Finish the environment from the shell

`/coordinator:install` is a Claude Code slash command; it does not exist here. Its environment
wiring is a script with declared choices, `<klabauter-clone>/lib/install/coordinator_install.py`
(orientation, then `--plan`, then `--answers`; safe to re-run; reports every step RAN, SKIPPED,
INHERITED or FAILED). It checks prerequisites, lays down the machine-local registry, scaffolds
the canonical document structure and records the `setup_concluded` receipt. **Phase 3 deposits
the `machine-local` resolver** that Step 4 depends on. Run it through the shell, or finish this
leg from a Claude Code session.

## Step 4 — Install the engine (`claude-klabauter`)

coordinator-claude and its engine are **one joint installation**. Without the engine, planning,
review and personas work; claiming handoffs, memo resolution, coverage and terminal stamping do
not. **The sequence, literally:**

### The sequence

1. Get the sources (§ Step 1; Grok also runs § 1d). 2. Clone the engine and register
`repos.claude_klabauter` (§ 1e). 3. Run the environment wiring script (§ Step 3; deposits the
resolver). 4. **Only then** run the engine's installer, below, from a shell started after (3).
`/coordinator:setup` is the install-chain **verifier**, never a depositor; it runs *after* this
step, in a Claude Code session.

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

**`/coordinator:setup`** walks `direct_deps`, verifies the engine is satisfied and emits the
chain-complete banner. It installs nothing; run earlier it fails loud with "engine not
satisfied." It is a Claude Code slash command: run it from a Claude Code session after the
engine install. Until then, the engine installer's `PASS`/`FAIL` output is the only engine verdict.

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

## Step 5 — Configure the host

`unimatrix-install.py` exposes explicit host installation. Host configuration adds no
review gate or marketplace step. Verify published capability and obtain any required shared
resource approval before running a profile-changing command. Prerequisite:
`claude-klabauter` (Step 4), which ships `coordinator_core.host_hooks.shim`, the guard each host
calls. Name the host explicitly; with no `claude` on PATH the Claude range gate is skipped, with
a printed notice, only when `--hosts` names no `claude`. Bare `--install` still refuses outside
the verified Claude range.

### Install and remove

Codex sets no plugin-root variable, so name the plugin root as an explicit path: `<plugin-root>`
is the checkout or installed plugin directory that holds `bin/unimatrix-install.py`.
<!-- INSTALL-DOE-ONLY:BEGIN -->

On a DoE box `<plugin-root>` is `<DoE clone>/coordinator`.
<!-- INSTALL-DOE-ONLY:END -->

```bash
python3 <plugin-root>/bin/unimatrix-install.py --install --hosts codex --plugin-root <plugin-root>   # Windows: python
python3 <plugin-root>/bin/unimatrix-install.py --uninstall   # removes every managed entry
```

### What lands

| Lands | Codex |
|---|---|
| Doctrine block (`coordinator-doctrine`, `global-doctrine/CLAUDE.md` then `rules/rules.md`, beside the peer block) | `$CODEX_HOME/AGENTS.md` (cap 32768 B) |
| Skills | one entry per skill in `~/.agents/skills/` (symlink, copy where refused; not moved by `CODEX_HOME`) |
| Guard hook | One catch-all `PreToolUse` registration in `$CODEX_HOME/hooks.json`; native tool arguments select the shared policy body |
| Lifecycle and role context | Owned native lifecycle handlers in `$CODEX_HOME/hooks.json`, including actual session registration and worker/EM context separation |

### The managed block

The block is managed: edits inside it are overwritten on the next install and removed on
uninstall; text outside it is never touched. The installer resolves the engine root once and bakes
it into each hook command as `--engine-root`.

### Trust step

The installer verifies discovery and enabled state for each expected owned
handler, with separate native trust keys. It checks `currentHash == trustedHash` when the
native response exposes `trustedHash`; otherwise it requires native `trustStatus: trusted`.
Missing, disabled, duplicated or untrusted handlers prevent a successful runtime outcome.
The shared runtime entry reports unresolved engine/content prerequisites as unavailable or
partial; it does not certify readiness because some files were seeded. A legacy install's
degraded/neutral-hook report is not a successful runtime installation.

### Fallbacks

If the engine is absent, slow or errors, the cold irreversible-external
backstop can still return a real denial. With neither an engine verdict nor a backstop denial,
the guard answers `{}` on Codex, which fails open and leaves the normal approval flow untouched.
Neither host ever gets `allow` as a fallback. A degraded answer is never counted as verified
governance.

### Limits

Read these as the boundary of what is governed.

- `--dangerously-skip-permissions`, `--mode auto` (agy) and `danger-full-access` (Codex) are never
  set by default. The historical enforcement matrix exercises shell commands only, so a passing matrix is
  evidence for those tested shell paths, not complete Klabauter enforcement; it never clears these
  options alone. Beyond the assigned-task ceiling below, they stay unoffered until the excluded
  execution paths above are also covered.
- Engine timeouts and fallback diagnostics must remain visible; they do not establish that a
  policy ran successfully. Verify actual native execution separately from read-only file checks.
- Native event registration does not establish semantic parity for every Claude handler. Shared
  bodies and host adapters cover supported native payloads; Claude-only events and specialized
  paths remain gaps. Do not infer coverage from a historical handler count.
- Claude commands and agent definitions do not automatically become native host commands or
  profiles. Dedicated worker/reviewer routes may reuse approved definitions through their own
  contracts; installing skills does not prove every such route works.

### Limits specific to Codex

- On a compatible engine, Codex shell calls use shared shell guards; `apply_patch` targets use
  bounded projections into shared write guards; named MCP operations use argument-aware policies;
  and `spawn_agent` briefs use the portable brief policy. This is not complete policy coverage for
  every local function or indirect MCP operation. Ambiguous patch bodies retain an explicit
  inspection gap. Hosted tools, specialized native paths that omit hooks, and `write_stdin` input
  that does not rerun PreToolUse remain limits. A degraded Codex guard answers `{}`; that proves no
  enforcement. The seeded peer-send execpolicy allow prefix is not a general deny policy.
- The portable Codex worker route requests `--sandbox workspace-write` and approval
  `on-request`, alongside its actual assignment and admission checks. Other workflow runners
  have their own launch arguments; verify the selected route. This is not evidence that
  remote MCP side effects are confined to the workspace. A configured host is not by itself proof
  that a worker, reviewer or workflow route has passed its own runtime acceptance.
- Windows: a sandboxed Codex shell dies with `CreateProcessAsUserW failed: 5` when `pwsh` resolves
  to the `…\WindowsApps\pwsh.exe` alias; put `C:\Program Files\PowerShell\7` ahead of it on PATH.
  The sandbox also denies writes under `.git` to its children.
- Historical matrix observations (C6, 2026-11-04; not current whole-system acceptance): shell-command
  deny held under both Codex modes and under `--dangerously-bypass-approvals-and-sandbox`, which
  still runs hooks and rules. Not covered: a `forbidden` execpolicy rule does not match a command
  wrapped in `bash -c '...'` or `env ...`, so rules never govern wrapped forms. A degraded guard
  (import failure, timeout, malformed reply) enforces nothing on Codex. That matrix's P4 result
  depended on its recorded box policy; inspect the current policy and registered
  external-workspace arming rules separately. Warm-engine deny (server-correlated) and the Codex
  on-request runtime (interactive TUI: approve runs, reject does not, hook deny blocks before the
  prompt) are proven, and our hook denies `bash -c`/`env`-wrapped commands, so the wrapper gap is
  Codex's rule matcher only. Matrix:
  `docs/plans/2026-11/2026-11-04-hnd-codex-agy-doctrine-install-and-773493.c6-matrix.md`.

### Pre-installing before the host CLI lands

Run the default `unimatrix-install.py --install --hosts codex` with `codex` absent from `PATH`.

- **Lands without the CLI:** `$CODEX_HOME/AGENTS.md` (peer block and `coordinator-doctrine`
  block), `$CODEX_HOME/hooks.json` (`SessionStart`, `PreToolUse`), `$CODEX_HOME/rules/unimatrix.rules`,
  and the skill entries in `~/.agents/skills/`. `CODEX_HOME` defaults to `$HOME/.codex`
  (`%USERPROFILE%\.codex` on Windows).
- **Deferred until the CLI lands:** hook trust. The installer reports `governance verification
  FAILED: codex not on PATH; hook stays untrusted until reviewed in /hooks` and exits 5; that
  is the deferral, not a failed pre-seed.
- **Completing re-run:** after `codex` is on `PATH`, re-run
  `unimatrix-install.py --install --hosts codex`; it replays trust. A pre-seeded home does not clash with
  the files the CLI creates itself (`config.toml`, stores).
- **Owner gates (engine maintainers):** report "trust deferred" with a zero or distinct exit code
  instead of exit 5 for an absent CLI; on Windows the trust-key write consumes the backslashes of the
  hooks path, so the replay cannot succeed there until the engine escapes the key.
- **Engine root:** if klabauter is not registered, the install reports `governance DEGRADED:
  engine root unresolved` and the guard answers the neutral fallback (`{}`); that is a recorded
  limit, not a pass. Baking a registered-but-absent klabauter path is an engine gate; the
  engine root, when it lands, is picked up by re-running the install.

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

## Failure modes

- **The host report says `MCP entry only`.** An older engine has not installed the runtime
  support: update through the published `claude-klabauter` path (Step 4); do not point runtime
  hooks at an editable engine-source checkout or hand-write trust entries.
- **A foreign MCP entry differs from the requested route.** It stays intact and is reported as
  drift; it prevents overall host readiness even if native hooks are current.
- **A handler is missing, disabled, duplicated or untrusted.** That prevents a successful
  runtime outcome (§ Trust step).

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

## More detail

- Guided runbook, one phase at a time: `commands/install.md`. Reversing an install:
  `commands/uninstall.md`. Install-chain walker: `docs/install/AGENT.md`.
<!-- INSTALL-DOE-ONLY:BEGIN -->
- `coordinator/docs/wiki/DIRECTORY_GUIDE.md` — the wiki index (coordinator-content-repo authoring surface only).
- Percolation topology and the `PERCOLATE_ROOT` chain:
  `coordinator/docs/wiki/install-playbook-rationale/percolate-setup.md`.
<!-- INSTALL-DOE-ONLY:END -->
