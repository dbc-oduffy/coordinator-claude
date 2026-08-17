# Installing coordinator-claude

Written for the agent installing this repo (see `AGENTS.md`, this file's sibling at the repo
root, for the entry point) — a human reads it too, but there is no separate human instruction
set. This is a **two-leg install, and both legs are yours**: coordinator-claude is the doctrine;
the coordinator engine is a **hard co-requisite** most state-mutating flows fail without. An
install that stops after leg 1 is incomplete — do not report it as done.

## What you are installing, and why it needs two repos

coordinator-claude is a Claude Code plugin: skills, commands, agent definitions, and hooks that
give a session an engineering operating model. It is doctrine — it decides *what should happen*.
The operations that actually *make it happen* (writing work-state artifacts to disk, managing
sessions, running the gates) live in a separate Python engine. That split is what lets an engine
change ship without a doctrine change; the cost is that installing one means resolving the other.

coordinator-claude is a standard **Claude Code marketplace** — the single `coordinator` plugin
(deep-research folded inside it, not a separate plugin) is installed with the native `claude
plugin` CLI. There is no bespoke installer script for the plugin half; the CLI does the wiring,
and a post-restart `/coordinator:install` finishes the environment.

## Requirements

Only two things are needed to *begin* — `git` and the Claude Code CLI. The rest are resolved as
the install walks:

| Requirement | Why |
|---|---|
| `git` | Required. |
| Claude Code CLI | Required. The canonical runtime, preferred over the desktop app. |
| `bash` | **No version floor.** Earlier releases required 4.3+ because the scripts themselves used bash-4-only syntax; those were ported to Python and the requirement is gone — macOS's stock 3.2 is fine. The installer may still remark on it; that is a remark, not a blocker. |
| **Python 3.11+** | Required — a **real** `python3`, not a stub (see the Windows note below). Hooks and config helpers use Python, and `tomllib` (3.11+, stdlib) gates several of them. |
| `jq` | Optional. No hook invokes it at runtime; the installer warns if it's absent but proceeds. Install it anyway if you want `scc`'s JSON-output path instead of its text fallback (`brew install jq` / `sudo apt install jq` / `winget install jqlang.jq`). |
| `gh` (GitHub CLI) | Optional. Only needed for the merge/release ceremonies (`gh pr create`, `gh pr merge`); the setup probe treats it as advisory, not a blocker. |
| `node` 18+ | Only for the NotebookLM add-on and the ceremony-gate JS test suite. Nothing in the daily loop needs it. |
| **The coordinator engine — one hard dependency, not part of this clone.** | It handles all durable work-state mutation. Not a step to run now — § Step 4 below walks the full install, and it must run **after** the restart and `/coordinator:setup`, not before. |

**Windows gotchas, before installing anything:**

- `python3` resolves by default to a Microsoft Store **App Execution Alias** — a 0-byte stub that
  errors on run and is invisible to Git Bash. Fix it first: `winget install Python.Python.3.13`,
  ensure the real `Python313\` dir precedes `…\WindowsApps` on PATH, and — since Windows ships
  `python.exe`, not `python3.exe` — provide a `python3` (copy/hardlink, or let
  `/coordinator:install` lay it down for you).
- `winget install …` prints *"Path environment variable modified; restart your shell."* — the
  change lands in the registry but not the current process. Start a fresh shell before continuing
  with anything that depends on the newly-installed tool.
- `bash` is not invokable by name after a fresh Git-for-Windows install — Git deliberately keeps
  `bash.exe` off `PATH`. Launch the "Git Bash" terminal, or invoke it by full path
  (`Program Files\Git\bin\bash.exe`).

**Windows is at least two environments, not one — pick the right shell for the command you're
running.**

| Shell | Sets `HOME`? | Sets `USERPROFILE`? | Good for |
|---|---|---|---|
| Git-Bash / MSYS (POSIX-emulating) | Yes | Yes | Any doc example written as `bash` |
| PowerShell / cmd.exe (native) | No | Yes | Day-to-day session launches; anything documented with a Windows-native form |

Coordinator's own home-resolution chain honours `USERPROFILE` via `Path.home()`, so native shells
resolve correctly there.

## Step 0 — Detect: Track A or Track B?

Before any other action, determine which track applies. Determine the state by hand, from the
human's `~/.claude`:

- **`state=pristine`** — `~/.claude` does not exist, or exists but is empty. **Track A** — proceed
  to Step 1 from zero.
- **`state=used-vanilla`** — `~/.claude` exists and Claude Code has run there, but nothing
  opinionated was set up: not a git repo, `installed_plugins.json` is absent or `{}`, no
  coordinator infra. **Track A** — the human's sessions and any `CLAUDE.md` edits are preserved,
  not overwritten. Surface a *light, non-alarming* note; do NOT show the Track-B warning below.
- **`state=configured`** — an opinionated, deliberately-customized home: `~/.claude` is a git
  repo, `installed_plugins.json` lists real plugins, or coordinator infrastructure is already
  present. **Track B** — surface the merge caveat below before proceeding.

**Track B — existing structure detected.** Surface this to the human:

> "Your `~/.claude` already has structure (I found: [name what you found]). The coordinator
> installs cleanly from zero. Merging into an existing setup is **your call and your EM's job** —
> we do not provide a cherry-pick or merge engine for pre-existing config.
>
> 1. **Proceed anyway.** The install runs from whatever the current state is; config files are
>    merged, not overwritten. You and your EM review the result together in the fresh session.
> 2. **Stop here** and do this manually with your existing EM.
>
> Which would you like to do?"

Wait for an explicit answer before continuing. If they choose to proceed, follow Track A from
Step 1 onward.

## Step 1 — Install via the `claude plugin` CLI

Get the whole system wired before the restart, so the fresh session comes up already
coordinator-shaped and the human and their new EM can get straight to customizing it together.

### 1a. Clone or locate the repo

The clone provides pre-install helper scripts and is the source for the offline/dev install
variant. The **primary install in 1d does not install *from* this clone** — it registers the
public GitHub repo as the marketplace, so the clone is a build-time input you can discard once
install completes.

```bash
# If the user hasn't cloned yet:
git clone https://github.com/dbc-oduffy/coordinator-claude.git ~/coordinator-claude
```

If it's already on disk, confirm the path with the human.

### 1b. The install-everything-vs-DIY decision gate

Before touching plugin selection, settle one thing: **install the whole system, or hand-pick
pieces?** Installing coordinator is installing a *collaboration contract, not software* — the
whole system goes in. Steer hard to **install-everything-then-customize**.

1. **Install-everything-then-customize (recommended).** Install the full system, get a fresh
   session that is *itself* coordinator-shaped, customize from there together.
2. **DIY-minimal.** Native cherry-pick of coordinator is **unsupported, period** — downstream
   repos plug into coordinator infra, and we cannot validate or certify a custom subset works. Be
   straight about this before anyone commits to it; do not proceed down this path on your own.

> **Chain-stability rule.** If the human intends *any* downstream chain — a private product, a
> sibling repo, anything that lists coordinator as a prerequisite — install the **FULL**
> coordinator system. A cherry-pick could silently remove infra a downstream repo depends on.

### 1c. Plugin selection — what to enable

| Tier | Plugins | Default |
|---|---|---|
| **core** | `coordinator` (deep-research folded in) | Always on. Full multi-agent pipelines require `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (Step 2 sets this). |
| **specialized** | UE/example-game-repo plugins, game-dev plugin, project-rag | Only relevant for Unreal Engine / example-game-repo workflows. Do NOT offer to a generic user. |

**Offer granularity is the add-on level, never the component level.** deep-research is not an
install-time choice — install coordinator and you have it. There is no install-time per-skill
picker. If the human wants a piece of an installed plugin turned off, that is a **post-install**
move (per-project plugin gating), set after the fact.

### 1d. Run the install (native `claude plugin` CLI)

Register the **public GitHub repo** as a marketplace, then install the plugins:

```bash
# 1. Register the PUBLIC GitHub repo as the marketplace (NOT your local clone — see note below):
claude plugin marketplace add dbc-oduffy/coordinator-claude

# 2. Install coordinator (always) — deep-research pipelines ship folded into it:
claude plugin install coordinator@coordinator-claude
```

Claude Code caches the marketplace under `~/.claude/plugins/marketplaces/coordinator-claude/` and
each plugin under `~/.claude/plugins/cache/coordinator-claude/<plugin>/<version>/` — both inside
`~/.claude`. The plugin install is fully self-contained: once it completes, the clone is a
build-time input you can move or delete, and the plugin's skills, hooks, and commands keep
working. That self-containment is scoped to the plugin, not to every capability it offers — the
engine (§ Step 4) is a separate install this step does not provide. Read the CLI output; if it
reports an error, surface it verbatim — do not paper over it.

> **Why the GitHub repo, not your clone path?** `claude plugin marketplace add <a-directory>`
> registers a *directory* source that Claude Code resolves from that exact path on **every**
> load — it never copies a directory marketplace into `~/.claude`. Point it at your clone and the
> installed plugins gain a hard runtime dependency on the clone staying put; move or delete the
> clone and `/reload-plugins` reports `0 plugins`. A `git`/`github` source is cached into
> `~/.claude` instead, so it survives. The repo is public — no credentials needed.
>
> **Offline, or installing local modifications?** With no network access, or to reflect
> *uncommitted* clone edits, register the clone directly:
> `claude plugin marketplace add <clone-path>`. In that mode the clone **is** the runtime source —
> keep it in place, or re-add from GitHub later to cut over to the self-contained source.
> (A future coordinator session also auto-repairs a clone-bound entry once the clone goes missing,
> but don't rely on it; prefer the GitHub source up front.)

> **No sentinel, no onboarding baton, no `/pickup` staging here.** The native CLI flow has no
> pre-restart script, so there is nothing to seed: the post-restart `/coordinator:install`
> (Step 3) *is* the onboarding, and it records its own completion receipt. Do not hand-create a
> sentinel file or a handoff baton.

## Step 2 — The restart (load-bearing gate)

The plugins are installed. Now the human needs a fresh Claude Code session.

Tell the human exactly this:

> **Start a fresh Claude Code session from your coordinator root, then paste one command.**
>
> 1. Open a terminal.
> 2. `cd ~/.claude`
> 3. `claude`
>
> Then, in that session, paste:
>
> ```
> /coordinator:install
> ```
>
> **Switch to auto mode first.** Coordinator is an agentic system — the EM edits files, runs
> setup scripts, and dispatches subagents on your behalf. Press **Shift+Tab** to cycle the
> permission mode to **auto-accept ("auto") mode** so the install runs without a prompt on every
> action.
>
> (If `claude` isn't found, install the CLI first: `npm install -g @anthropic-ai/claude-code`. If
> you've been using the desktop app, switch to the CLI for coordinator work.)
>
> Why a fresh session, and why from `~/.claude`? Two things take effect only at startup: (1) the
> coordinator's hooks and slash-commands load when Claude Code reads the newly-installed plugin,
> and (2) the Agent Teams capability (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) is an environment
> variable Claude Code reads at startup (`/coordinator:install` writes it; it takes effect on the
> *next* restart after that).

Do NOT describe the fresh session as "just restarting" — the human is handing off to a new
session that runs `/coordinator:install` to finish the environment wiring.

## Step 3 — Post-restart: finish the environment, onboard a project

In the fresh session, the human runs:

1. **`/coordinator:install`** — environment wiring (safe to re-run; skips anything already
   configured). Checks prerequisites, sets the Agent Teams env var, lays down the machine-local
   registry, builds the helper venv, scaffolds the canonical document structure, records the
   `setup_concluded` receipt, and offers a guided tour + repo bootstrap. This *is* the
   post-restart onboarding — there is no separate baton to `/pickup`.
2. **`/coordinator:repo-setup`** — per-project scaffolding (project `CLAUDE.md`, tracker, project
   type) for whatever repo the human wants to onboard.
3. **`/workday-start`** — only if the human queued *other* downstream tools at the pre-restart
   step (1c): each downstream installer seeds its own leg into `~/.claude/state/handoffs/`, and
   `/workday-start` triages and sequences whatever is present. On a solo coordinator install,
   there is nothing queued — skip it and go straight to `/workstream-start`.

The highest-leverage first *customization* is co-writing `CLAUDE.md` together — the guided tour
that `/coordinator:install` offers is the vehicle.

## Step 4 — Install the engine (`claude-klabauter`)

coordinator-claude and its engine are **one joint installation, not two independent ones.**
Cloning coordinator-claude is not the same as installing it, and installing coordinator-claude is
not the same as installing the engine — treat this step as mandatory, not optional, before
declaring the install complete. Without it, planning/review/personas/shaping still work; claiming
handoffs, memo resolution, coverage computation, and terminal stamping do not.

**Do this only after Step 3 has completed** — `/coordinator:install` has run and the session has
been through its restart. The reason is mechanical, not procedural: coordinator-claude ships
`bin/machine-local` as a thin forwarder; the real resolver is deposited by `/coordinator:setup`
(Phase 3), which runs as part of Step 3. Run the engine installer before that, and its dependency
check calls the forwarder, finds no resolver, and **exits 127** reporting `resolver not
installed` — the fix it names is exactly "run `/coordinator:setup` (Phase 3)."

1. **Confirm the resolver is live** before proceeding: `machine-local keys` (or equivalent) should
   resolve, not 127. If it doesn't, finish Step 3 first.
2. **Windows only, before anything else:** disable the Python App Execution Alias stubs — see
   § Requirements.
3. **Prerequisite:** Python 3.11+.
4. **Clone the engine** (a separate repo from coordinator-claude):
   ```bash
   git clone https://github.com/dbc-oduffy/claude-klabauter
   cd claude-klabauter
   ```
5. **Run the agent install path** — non-interactive, the one you should use, from inside that
   clone:
   ```bash
   python3 <klabauter-clone>/scripts/setup.py --i-am-agent
   ```
   (Windows: `python <klabauter-clone>\scripts\setup.py --i-am-agent`.) This checks dependencies
   (including that the `machine-local` resolver from Step 3 is present), installs, and registers
   the engine.
6. **Verify with the check-only pass:**
   ```bash
   python3 <klabauter-clone>/scripts/setup.py --check
   ```
   No side effects — use it to confirm success without risk of re-running the install.

**What NOT to do:**
- **Do not run `pip install .` as the engine install.** It makes `coordinator_core` importable
  and provides one console script, but skips the dependency check and registration step above.
- **Do not pass `--skip-dep-check --accept-missing-deps-risk`** unless you have a specific,
  understood reason — it's a documented degraded path, not a normal step, and the two flags are a
  pair: passing only one is an error.
- **The engine has no plugin or skills surface** — it is a Python package, not a second Claude
  Code plugin. There is no `claude plugin install` step for it.

For the human path (interactive prompts instead of `--i-am-agent`), the same three commands apply
without that flag.

## Verifying your install

Don't infer coordinator is live from the absence of errors — confirm it directly:

1. **Launched via your install path's documented launch method, not a bare `claude` invocation
   with nothing resolving the plugin.** If you started the session yourself, confirm you used
   that method. If someone else's transcript is in question, look for the SessionStart
   `additionalContext` the EM-role hook injects — a coordinator-less session never gets it.
2. **Coordinator commands resolve.** Type `/` and confirm coordinator-namespaced commands (e.g.
   `/coordinator:validate`, `/coordinator:install`) appear in the list. Their absence means the
   plugin never took effect.
3. **Hooks are wired.** `cat ~/.claude/settings.json` and confirm the `hooks` block is populated
   (`SessionStart`, `PreToolUse`, etc. each list entries) rather than empty, and that hook command
   paths are fully substituted — no literal `${CLAUDE_PLUGIN_ROOT}` left in a command string.

A coordinator-less session and a session with genuinely missing/corrupted doctrine look identical
from the outside — step 1 above is what tells them apart, and it is the fastest check to run
first.

### Standing cost & cosmetics (set expectations)

Two things worth explaining up front, visible in `claude plugin details`:

- **Always-on token cost.** The `coordinator` plugin adds roughly **~8.2k tokens to every session
  baseline** before any skill is invoked — that is the standing cost of the doctrine and command
  surface being available. Skills and command bodies load on demand; this baseline is the
  always-present part.
- **Doubled skills count is cosmetic.** `claude plugin details` reports a skills count (e.g.
  "Skills (75)") with about half the names doubled (`plan, plan`, `bug-sweep, bug-sweep`, …) —
  coordinator ships most capabilities as both a skill and a same-named slash-command wrapper, and
  the CLI counts both. It inflates the *displayed* count; it is not a real duplication.

## Manual install (fallback only)

Use only if the `claude plugin` CLI cannot run (no CLI available, sandboxed environment). These
steps are self-contained. The CLI flow above is strongly preferred; reach for this only when it
is genuinely unavailable.

1. `mkdir -p ~/.claude/plugins/coordinator-claude`
2. `cp -r coordinator ~/.claude/plugins/coordinator-claude/` (the repo's single top-level plugin
   dir — deep-research ships folded inside it).
3. Copy `.claude-plugin/marketplace.json` into
   `~/.claude/plugins/.claude-plugin/marketplace.json`. Its one plugin entry's `source` field is
   already flat (`.`) — keep it as-is.
4. Merge an entry into `~/.claude/plugins/known_marketplaces.json` for `coordinator-claude`
   pointing at the install dir.
5. Merge entries into `~/.claude/plugins/installed_plugins.json` (one per plugin, key
   `<name>@coordinator-claude`, with `installPath` and `version` from each plugin's `plugin.json`).
6. Merge `~/.claude/settings.json`: enable plugins under `enabledPlugins` (keys are
   `<name>@coordinator-claude`, **not** bare `<name>`); register the marketplace under
   `extraKnownMarketplaces` (an object, each key a marketplace name); and add `Edit` and `Write`
   to `permissions.allow` (background subagents need these — `defaultMode: dontAsk` does not
   propagate to them).

On Windows (Git Bash / WSL), config files store **native** Windows paths (`~…`), not POSIX
(`/c/…`). Write native paths into the JSON or Claude Code will fail to resolve the plugins.

After a manual install, restart and run `/coordinator:install` exactly as in Step 3.

## Refinement target: edit your `~/.claude`, not this clone

After install, the human evolves their live, git-tracked `~/.claude` — their Claude Central.
**Do NOT edit the `coordinator-claude` source repo (the delivery truck) to customize behavior.**
Changes to a clone of the source repo don't touch running sessions; the next install would
overwrite them.

The rule: **edit your `~/.claude`, not this clone.** Methodology refinements, persona names, and
`CLAUDE.md` evolution land in `~/.claude`. `coordinator.local.md` project-type config is the one
exception — it is per-project, and lives at the consuming repo's own root, not in `~/.claude`.

## Optional follow-ups to mention

- **Name your reviewers (optional):** persona renaming is a post-install, cosmetic choice — handle
  it in `/coordinator:install` Phase 6 (Persona Customization) or by hand-editing the names across
  the agent files. Display-only; agent behaviour is unchanged.
- **Per-project config:** repo-root `coordinator.local.md` with
  `project_type: web-dev|data-science|game-dev|general` controls which domain reviewers activate.
  Without it, only the universal reviewers run. `/coordinator:repo-setup` writes this for you.
- **Contributing to the plugins themselves?** See `CONTRIBUTING.md` for the dev workflow.

## Failure modes to watch for

- **`claude plugin install` reports nothing / no plugin appears.** Confirm the marketplace was
  added first and that the key is `<name>@coordinator-claude`.
- **`/reload-plugins` reports `0 plugins` after a working install.** Almost always a clone-bound
  marketplace whose source directory was moved or deleted. Check
  `~/.claude/plugins/known_marketplaces.json`: if the `coordinator-claude` entry's `source.source`
  is `directory` with a `path` that no longer exists, re-register from GitHub, then
  `/reload-plugins`. Coordinator also self-heals this on the next session start (the
  `platform-localize` hook rewrites a missing clone-bound entry to the GitHub source), but the
  manual re-add is the immediate fix.
- **`enabledPlugins` keys must be `<name>@coordinator-claude`**, not bare `<name>`. Common typo on
  the manual path.
- **`extraKnownMarketplaces` is an object, not an array.** Each key is the marketplace name.
- **Path translation on Windows (manual path only).** Forget native paths in JSON and Claude Code
  will fail to resolve plugins.
- **Plugins installed but commands missing.** The hooks and slash-commands load at startup — the
  human must restart (Step 2) before `/coordinator:install` is available.

## If you had to patch something to install — send it back

If you hit a rough edge and worked around it — hand-merged a JSON file, fixed a path-translation
bug, patched around a platform-specific snag, anything — **you are exactly the contributor we
want to hear from.**

Before you wrap up, offer to send the fix upstream. Draft one of these for the human (preference
order): a PR against `dbc-oduffy/coordinator-claude`; an issue describing what broke, on what
platform, and what you changed; or a rough note — a paragraph in an issue is plenty. Don't polish
it, and don't gate on code quality. See `CONTRIBUTING.md`.

## Keeping the install current

After install, `/coordinator-update` is the PM-invoked way to update later: it checks online for
the latest published version, computes a delta against the human's install, and **advises** a
path (overwrite / cherry-pick / plan-to-ingest) while **preserving the human's own customizations
by default**. It never blindly overwrites. To pull a newer published version through the CLI,
`claude plugin install coordinator@coordinator-claude` again picks up the latest from the
marketplace; `/coordinator-update` is the safer, customization-aware path.

## More detail

- Full guided runbook, one phase at a time, with rationale and status-table rows:
  `coordinator/commands/install.md` (published flat as `commands/install.md`, no `coordinator/`
  prefix, in the OSS mirror). Has its own "You are here" preamble distinguishing cold-bootstrap
  from post-install re-run at the top.
- Reversing an install: `coordinator/commands/uninstall.md` (published flat as
  `commands/uninstall.md` in the OSS mirror).
- `coordinator/docs/install/AGENT.md` (published flat as `docs/install/AGENT.md` in the OSS
  mirror) — the install-chain walker guide (for multi-repo chains).
</content>
