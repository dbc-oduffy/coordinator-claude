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
sessions, running the gates) live in a separate Python engine — installing one means resolving
the other.

coordinator-claude is a standard **Claude Code marketplace** — the single `coordinator` plugin
(deep-research folded inside it) installs with the native `claude plugin` CLI. There is no bespoke
installer script for the plugin half; a post-restart `/coordinator:install` finishes the
environment.

## Requirements

Only two things are needed to *begin* — `git` and the Claude Code CLI. The rest are resolved as
the install walks:

| Requirement | Why |
|---|---|
| `git` | Required. |
| Claude Code CLI | Required — the canonical runtime, preferred over the desktop app. |
| `bash` | No version floor — macOS's stock 3.2 is fine. |
| **Python 3.11+** | Required — a **real** `python3`, not a stub (see Windows note below); gates `tomllib`. |
| `jq` | Optional; installer warns if absent but proceeds. |
| `gh` (GitHub CLI) | Required — backs clone auth and merge/release ceremonies. Authenticate before installing (`gh auth login`). |
| `node` 18+ | Only for the ceremony-gate JS suite and the NotebookLM add-on. |
| **The coordinator engine — one hard dependency, not part of this clone.** | Handles all durable work-state mutation. Runs at § Step 4, **after** the restart and `/coordinator:setup`, not before. |

This table states *why*, not pass/fail severity — run `/coordinator:setup` (its own prereq probe)
and read the severity it prints beside each row.

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

Before any other action, determine which track applies. **Run these three commands** — do not
infer the state from a property, because the obvious test for each one lies:

```bash
test -d ~/.claude/.git && echo "own-git-repo"          # NOT `git -C ~/.claude rev-parse …`
jq -e '. != {} and . != null' ~/.claude/plugins/installed_plugins.json 2>/dev/null && echo "has-plugins"
test -e ~/.claude/.doe-root -o -d ~/.coordinator-claude-settings && echo "has-coordinator-infra"
```

Use the literal commands, not `git rev-parse` — a home directory under dotfile tracking makes
`rev-parse` misread a clean home as configured.


- **`state=pristine`** — `~/.claude` does not exist, or exists but is empty. **Track A** — proceed
  to Step 1 from zero.
- **`state=used-vanilla`** — `~/.claude` exists and Claude Code has run there, but all three
  commands above printed nothing. **Track A** — the human's sessions and any `CLAUDE.md` edits are
  preserved, not overwritten. Surface a *light, non-alarming* note; do NOT show the Track-B
  warning below.
- **`state=configured`** — any of the three printed. **Track B.**

**Track B — proceed and report; do not stop.** The install merges config files rather than
overwriting them, so an existing home is not by itself a reason to hold. Proceed, and tell the
human afterwards what you found and what the install did with it:

> "Your `~/.claude` already had structure — I found: [name exactly what the commands printed].
> The install merges config rather than overwriting, so I proceeded. Here is what changed: […].
> Merging deeper into an existing setup is your call and your EM's job — we do not provide a
> cherry-pick or merge engine for pre-existing config, so if any of the above is not what you
> wanted, we unpick it together in the fresh session."

**Stop and ask only on a genuine conflict** — a file the install would have to *overwrite* rather
than merge, or pre-existing coordinator infra from a different install whose provenance you cannot
establish. "Structure exists" is not a conflict. Name the specific file and the specific clash;
never ask the generic question.

## Step 1 — Install via the `claude plugin` CLI

Get the whole system wired before the restart, so the fresh session comes up already
coordinator-shaped and the human and their new EM can get straight to customizing it together.

### 1a. Clone or locate the repo

The clone provides pre-install helper scripts and is the source for the offline/dev install
variant. The **primary install in 1d does not install *from* this clone** — it registers the
public GitHub repo as the marketplace. **Keep the clone**: the engine's `<klabauter-clone>/scripts/setup.py`
resolves coordinator-claude as a sibling at Step 4, install time, not just build time.

```bash
# If the user hasn't cloned yet:
git clone https://github.com/dbc-oduffy/coordinator-claude.git ~/coordinator-claude
```

**If it's already on disk, resolve it yourself — do not ask.** A clone is identifiable from the
machine:

```bash
git -C <candidate> remote -v          # expect a dbc-oduffy/coordinator-claude remote
git -C <candidate> status --porcelain # expect clean, or note what is dirty
git -C <candidate> rev-parse HEAD
```

A candidate with the right remote is the clone; use it and say which one you used. Ask the human
only if **two or more** candidates carry that remote and their HEADs differ — that is a real
ambiguity with a wrong answer. One clone, or several that agree, is not.

### 1b. Install the whole system — this is a statement, not a gate

Installing coordinator is installing a *collaboration contract, not software*: install
everything, get a fresh session that is *itself* coordinator-shaped, and customize from there
together. **Do not offer a choice here.**

Native cherry-pick of coordinator is **unsupported, period** — downstream repos plug into
coordinator infra and a custom subset cannot be validated. If the human asks for a minimal subset
unprompted, say so before proceeding; do not do it unilaterally.

> **Chain-stability rule.** If the human intends *any* downstream chain — a private product, a
> sibling repo, anything that lists coordinator as a prerequisite — install the **FULL**
> coordinator system. A cherry-pick could silently remove infra a downstream repo depends on.

### 1c. Plugin selection — what to enable

| Tier | Plugins | Default |
|---|---|---|
| **core** | `coordinator` (deep-research folded in) | Always on. Full multi-agent pipelines require `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (Step 2 sets this). |
| **specialized** | UE/example-game-repo plugins, game-dev plugin, project-rag | Only relevant for Unreal Engine / example-game-repo workflows. Do NOT offer to a generic user. |

**Offer granularity is the add-on level, never the component level** — no install-time per-skill
picker. Turning a piece of an installed plugin off is a post-install move (per-project plugin
gating).

### 1d. Run the install (native `claude plugin` CLI)

Register the **public GitHub repo** as a marketplace, then install the plugins:

```bash
# 1. Register the PUBLIC GitHub repo as the marketplace (NOT your local clone — see note below):
claude plugin marketplace add dbc-oduffy/coordinator-claude

# 2. Install coordinator (always) — deep-research pipelines ship folded into it:
claude plugin install coordinator@coordinator-claude
```

Claude Code caches the marketplace under `~/.claude/plugins/marketplaces/coordinator-claude/` and
each plugin under `~/.claude/plugins/cache/coordinator-claude/<plugin>/<version>/`. **Do not
delete the clone** — the engine (§ Step 4) resolves it as a sibling at install time. Read the CLI
output; if it errors, surface it verbatim.

> Register the public GitHub repo, not your clone path — a directory-source marketplace breaks if
> the clone moves. This step clones over SSH even though the repo is public; `gh auth login` does
> not satisfy that. `git@github.com: Permission denied (publickey)` means add an SSH key, or clone
> over HTTPS and register the local directory instead. Either way, a directory source is a
> **snapshot**, not live edits — check drift with
> `diff -r ~/.claude/plugins/cache/coordinator-claude/coordinator/*/ <clone>/coordinator/`.

> **No sentinel, no onboarding baton, no `/pickup` staging here.** The native CLI flow has no
> pre-restart script, so there is nothing to seed: the post-restart `/coordinator:install`
> (Step 3) *is* the onboarding, and it records its own completion receipt. Do not hand-create a
> sentinel file or a handoff baton.

### 1e. Clone the engine and register it — a clone, **not** an install

The engine (`claude-klabauter`) is installed last, in Step 4. Its **clone** has to exist now,
before the restart, because `/coordinator:install`'s Phase 3 bootstraps coordinator's substrate
from a script that lives inside the engine repo. Skip this and Step 3 fails on its first command
with an unset root. See § Step 4 for the full ordering and why it is shaped this way.

**Look before you clone.** A clone may already be on the box:

```bash
# 1. Is one already registered?
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" \
    get repos.claude_klabauter 2>/dev/null

# 2. Is one a sibling of the coordinator clone, or at ~/ ?
ls -d "$(dirname <coordinator-clone>)/claude-klabauter" ~/claude-klabauter 2>/dev/null
```

For each candidate found, confirm it is the right repo before using it — `git -C <path> remote -v`
should show `dbc-oduffy/claude-klabauter`. If exactly one candidate is real, use it. If several
are and their `git rev-parse HEAD` agree, use any and say which. Ask the human **only** when two
real candidates disagree on HEAD — that is a genuine ambiguity where a wrong pick strands the
install against the wrong tree.

**If none exists, clone it as a sibling of the coordinator clone** — not into `~`, and not into
whatever the current directory happens to be:

```bash
git clone https://github.com/dbc-oduffy/claude-klabauter \
    "$(dirname <coordinator-clone>)/claude-klabauter"
```

Sibling is the layout the engine's own resolver assumes (`sibling-dir default` rung).

**Then register it**, so nothing downstream has to guess. This hand-set is a **one-time cold-box
bootstrap**: the engine's own installer writes this same key once it runs, and takes over from
here. That is why the registry example calls the key installer-written and this step hand-sets it
anyway — the installer cannot run until Step 4, and Step 4 needs the key already registered:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" \
    set repos.claude_klabauter "$(dirname <coordinator-clone>)/claude-klabauter"
```

> **If `machine-local` does not exist yet** (expected on a cold box — Phase 3 hasn't run), export
> the engine root instead: `export COORDINATOR_ENGINE_ROOT="$(dirname <coordinator-clone>)/claude-klabauter"`.
> Durable equivalent: a pointer file at
> `~/.coordinator-claude-settings/machine-local/.claude-klabauter-live-root` containing the path.
> `CLAUDE_KLABAUTER_ROOT` is retired — see wiki § Step 1e for detail.

**Do not run the engine's installer here.** Cloning and registering is all this step does; the
install is Step 4, after the restart.

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
> A fresh session is required: hooks/commands and the Agent Teams env var both take effect only
> at startup.

Do NOT describe the fresh session as "just restarting" — the human is handing off to a new
session that runs `/coordinator:install` to finish the environment wiring.

## Step 3 — Post-restart: finish the environment, onboard a project

In the fresh session, the human runs:

1. **`/coordinator:install`** — environment wiring (safe to re-run; skips anything already
   configured). Checks prerequisites, sets the Agent Teams env var, lays down the machine-local
   registry, builds the helper venv, scaffolds the canonical document structure, records the
   `setup_concluded` receipt, and offers a guided tour + repo bootstrap. This *is* the
   post-restart onboarding — there is no separate baton to `/pickup`. **Phase 3 of this command
   is what deposits the `machine-local` resolver** that Step 4 depends on. Phase 3 also runs the
   git-perf-config sweep across every registered worktree, setting `gc.auto 0` plus scheduled
   maintenance (`maintenance.strategy incremental`, `maintenance.auto false`,
   `maintenance.prefetch.enabled false`) rather than `gc.autoDetach false` — the fleet default,
   idempotent, safe to re-run.
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

### The sequence, exactly — follow it literally (known braid defect, not a design choice)

1. **Install coordinator-claude** via the `claude plugin` CLI — § Step 1d.
2. **Clone** the engine repo and register `repos.claude_klabauter` — *a clone, not an install*
   (§ Step 1e, still before the restart).
3. **Restart Claude Code** — § Step 2. The one restart; it is what makes `/coordinator:install`
   exist.
4. **Run `/coordinator:install`** — § Step 3. This deposits the `machine-local` resolver.
5. **Only then run the engine repo's own installer** — this step, from a shell started after (4)
   so that resolver is on PATH.

The clone has to come first because `/coordinator:install`'s Phase 3 bootstraps coordinator's
substrate from a script that lives *in the engine repo*. Rationale, braid-defect detail:
`coordinator/docs/wiki/install-playbook-rationale.md` § Step 4.

**`/coordinator:install` and `/coordinator:setup` are not aliases:**

| Command | What it is | When |
|---|---|---|
| **`/coordinator:install`** | The environment wiring, Phases 1–7. **Phase 3 is what deposits the `machine-local` resolver.** | Step 3, right after the restart |
| **`/coordinator:setup`** | The install-chain walker (step 5/5). Verifies the engine is satisfied, emits the chain-complete banner. A **verifier**, never a depositor. | *After* this step — the final check, below |

1. **Confirm the resolver is live** before proceeding. coordinator-claude ships the forwarder at
   `templates/bin/machine-local` (plus `templates/bin/machine-local.cmd`); install-time deposits it to
   `$COORDINATOR_SETTINGS_HOME/bin/machine-local`, default
   `~/.coordinator-claude-settings/bin/machine-local`. There is no `bin/machine-local` in the
   plugin, so check the absolute path rather than a bare name — a `command -v machine-local` miss
   is ambiguous between "Step 3 didn't run" and "not on PATH yet":
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/machine-local" get repos.claude_klabauter
   ```
   Expect the engine path you registered in Step 1e. **Do not use `machine-local keys` as the
   check** — it prints a fatal malformed-registry error and still exits 0, so it passes on a
   completely dead registry. `get` exits 2 correctly.
2. **Windows only, before anything else:** disable the Python App Execution Alias stubs — see
   § Requirements.
3. **Prerequisite:** Python 3.11+.
4. **The engine clone already exists** — you made it in Step 1e. Do not clone again.
5. **Run the agent install path** — non-interactive, the one you should use, from inside that
   clone:
   ```bash
   python3 <klabauter-clone>/scripts/setup.py --i-am-agent
   ```
   (Windows: `python <klabauter-clone>\scripts\setup.py --i-am-agent`.) This checks dependencies
   (including that the `machine-local` resolver from Step 3 is present), installs, and registers
   the engine.
6. **Read step 5's output — it is the only thing that tells you the engine installed.** Every
   line is prefixed `PASS`/`FAIL`; a non-zero exit or a traceback means the install did not
   complete, however many `PASS` lines preceded it.

   `<klabauter-clone>/scripts/setup.py --check` is **not** an install verification. It smoke-tests that the script
   itself is present and executable and exits 0 — it returns green on a box whose engine install
   crashed. Do not report an install as verified on the strength of it.

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

### Step 4 closes the chain — run `/coordinator:setup` last

With the engine installed, run **`/coordinator:setup`** in a Claude Code session. This is the
install-chain walker (step 5/5): it reads the install manifest, walks `direct_deps`, verifies the
engine is satisfied, and emits the chain-complete banner. It is a **verifier, not a depositor** —
it installs nothing, and running it earlier in the hope that it will lay down the substrate gets a
fail-loud "engine not satisfied" with no explanation of what to do instead.

That is the whole install: `/coordinator:install` wires the environment, the engine installer
installs the engine, `/coordinator:setup` confirms the chain is closed.

## Verifying your install

Don't infer coordinator is live from the absence of errors — confirm it directly:

1. **Launched via your install path's documented launch method, not a bare `claude` invocation
   with nothing resolving the plugin.** If you started the session yourself, confirm you used
   that method. If someone else's transcript is in question, look for the SessionStart
   `additionalContext` the EM-role hook injects — a coordinator-less session never gets it.
2. **Coordinator commands resolve.** Type `/` and confirm coordinator-namespaced commands (e.g.
   `/coordinator:validate`, `/coordinator:install`) appear in the list. Their absence means the
   plugin never took effect.
3. **Hooks are wired.** Coordinator ships its hooks in the plugin's own `hooks/hooks.json`,
   which the harness reads directly — so on a plugin install `~/.claude/settings.json` has an
   **empty** `hooks` block and that is CORRECT, not a fault; do not "fix" it by hand. Confirm
   instead that the resolved plugin root has `hooks/hooks.json` listing the events:

   ```
   python3 -c "import json;h=json.load(open('<resolved-plugin-root>/hooks/hooks.json'))['hooks'];print({k:len(v) for k,v in h.items()})"
   ```

   **One exception, inverting the check:** `--plugin-dir` delivery GENERATES `settings.json` hooks
   from `hooks.json`, so there a populated block is correct and an empty one means auto-wire is
   broken.

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

1. `cp -r <clone> ~/.claude/plugins/coordinator-claude` — the published repo IS the plugin, so
   copy its root, not a subdirectory. `.claude-plugin/` (both `marketplace.json` and
   `plugin.json`) rides along; `source` is already `.` and stays as-is.
2. **The installed plugin root is `~/.claude/plugins/coordinator-claude`** — the marketplace-named
   dir itself, with no suffix. Verify with
   `test -f ~/.claude/plugins/coordinator-claude/.claude-plugin/marketplace.json`. Every
   `<plugin root>` below means exactly that path.
3. Merge an entry into `~/.claude/plugins/known_marketplaces.json` keyed `coordinator-claude`,
   with `source` `{"source": "directory", "path": "<plugin root>"}` and `installLocation` set to
   the same `<plugin root>`.
4. Merge an entry into `~/.claude/plugins/installed_plugins.json` keyed
   `coordinator@coordinator-claude`, with `installPath` set to `<plugin root>` and `version`
   from `<plugin root>/.claude-plugin/plugin.json`.
5. Merge `~/.claude/settings.json`: enable plugins under `enabledPlugins` (keys are
   `<name>@coordinator-claude`, **not** bare `<name>`); register the marketplace under
   `extraKnownMarketplaces` (an object, each key a marketplace name); and add `Edit` and `Write`
   to `permissions.allow` (background subagents need these — `defaultMode: dontAsk` does not
   propagate to them).

On Windows (Git Bash / WSL), config files store **native** Windows paths (`~…`), not POSIX
(`/c/…`). Write native paths into the JSON or Claude Code will fail to resolve the plugins.

After a manual install, restart and run `/coordinator:install` exactly as in Step 3.

## Refinement target: edit your `~/.claude`, not this clone

After install, the human evolves their live, git-tracked `~/.claude` — their Claude Central. Do
NOT edit the `coordinator-claude` source repo to customize behavior; it doesn't touch running
sessions, and the next install would overwrite it. `coordinator.local.md` project-type config is
the one exception — per-project, lives at the consuming repo's own root.

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

After install, `/coordinator-update` is the PM-invoked way to update later: it checks the latest
published version, computes a delta, and advises a path while preserving customizations by
default — never a blind overwrite. `claude plugin install coordinator@coordinator-claude` also
pulls the latest, but `/coordinator-update` is the safer, customization-aware path.

## More detail

- Full guided runbook, one phase at a time, with rationale and status-table rows:
  `commands/install.md`. Has its own "You are here" preamble distinguishing cold-bootstrap
  from post-install re-run at the top.
- Reversing an install: `commands/uninstall.md`.
- `docs/install/AGENT.md` — the install-chain walker guide (for multi-repo chains).
</content>
