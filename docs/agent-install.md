# Agent Install Playbook

> **Audience: you, Claude (or another coding agent).** The human pasted a one-liner into their
> session and it brought you here. Your job is to guide a **guided install** of the coordinator
> system — not to run one command and declare done. This is a *collaboration system*; you follow
> this playbook **in partnership with the human**, and they participate in the shape decisions while
> you move fast on mechanism.
>
> coordinator-claude is a standard **Claude Code marketplace** — the plugins live at the repo root
> (`coordinator/`, `deep-research/`, `web-dev/`, `data-science/`) and are installed with the native
> `claude plugin` CLI. There is no bespoke installer script; the CLI does the wiring, and a
> post-restart `/coordinator:install` finishes the environment. The collaboration model is what the
> human is actually installing.

---

## Step 0 — Detect: Track A or Track B?

> **Before any block:** confirm Prerequisites (end of this doc) — Claude Code CLI, bash 4.3+
> (macOS: Homebrew + `brew install bash`), git, Python 3 (real `python3` — see the Windows note),
> jq.
> **Running the bash blocks:** Step 0 and Step 1's pre-restart blocks assume your cwd is the
> coordinator clone root — the directory you cloned and read this playbook from; `cd` there first.
> Post-install (`/coordinator:install` onward) runs from a fresh session and needs no clone path.

Before any other action, run the Track A/B classifier from the clone root:

```bash
bash coordinator/lib/detect-existing-claude-home.sh
```

The script emits one line: `state=<pristine|used-vanilla|configured> track=<A|B> reason: …`.
**Branch on the `state=` field** (the `track=` field is a backward-compat binary alias — `configured`
→ `B`, else `A` — kept for older callers; do not key new logic on it):

- **`state=pristine`** — Claude Code has never run here. **Track A** — proceed to Step 1 from zero.
- **`state=used-vanilla`** — Claude Code has run but nothing opinionated was set up (no git, no
  installed plugins, no coordinator infra). **Track A** — proceed to Step 1; the human's sessions and
  any `CLAUDE.md` edits are preserved, not overwritten. Surface a *light, non-alarming* note that an
  existing-but-uncustomized Claude Code home was detected; do NOT show the Track-B collision warning.
- **`state=configured`** — an opinionated, deliberately-customized home (git-tracked, installed
  plugins, or coordinator infrastructure). **Track B** — surface the merge caveat below before
  proceeding.

**Track B — existing structure detected (`state=configured`).** The classifier found a git-tracked
`~/.claude`, an installed plugin, or a substantially-edited `CLAUDE.md`. Surface this to the human:

> "Your `~/.claude` already has structure (the classifier detected: [paste reason line]).
> The coordinator installs cleanly from zero. Merging into an existing setup is **your call and
> your EM's job** — we do not provide a cherry-pick or merge engine for pre-existing config.
> Two options:
>
> 1. **Proceed anyway.** The install will run from whatever the current state is; config files
>    are merged, not overwritten. You and your EM review the result together in the fresh session.
> 2. **Stop here** and do this manually with your existing EM — who knows your setup better than
>    this cold agent does.
>
> Which would you like to do?"

Wait for an explicit answer before continuing. If they choose to proceed, follow Track A from
Step 1 onward.

---

## Step 1 — Install via the `claude plugin` CLI

Get the whole system wired before the restart, so the fresh session comes up already
Coordinator-shaped and the human and their new EM can get straight to customizing it together. Move
fast on the mechanism here — the collaboration shape gets decided after the restart, not during the
wiring.

### 1a. Clone or locate the repo

The clone provides the pre-install helper scripts (the Step 0 classifier, prerequisite checks) and
is the source for the offline/dev install variant. The **primary install in 1d does not install
*from* this clone** — it registers the public GitHub repo as the marketplace, so the clone is a
build-time input you can discard once install completes.

```bash
# If the user hasn't cloned yet:
git clone https://github.com/dbc-oduffy/coordinator-claude.git ~/coordinator-claude
```

If it's already on disk, confirm the path with the human.

### 1b. The install-everything-vs-DIY decision gate

Before you touch the plugin selection table, settle one thing with the human: **install the whole
system, or hand-pick pieces?** Installing Coordinator is installing a *collaboration contract, not
software* — the whole system goes in. This is **not like installing Linux** — it is not that deep,
not that much surface area, not a thing you assemble component-by-component to taste. Steer hard to
**install-everything-then-customize**, and do it without being tentative.

Two paths:

1. **Install-everything-then-customize (recommended — this is the path).** Install the full
   coordinator system, get a fresh session that is *itself* Coordinator-shaped, and customize from
   there together. Customization is real and expected — it just happens *after* the install, with a
   Claude that now understands the system, not as an install-time pick-'n'-mix. This is what the rest
   of this playbook walks.
2. **DIY-minimal (discuss-with-EM-first).** The human wants to hand-pick a reduced subset. **Do not
   proceed down this path on your own.** Surface it as a decision for the human and their EM, and be
   straight with them about what it means (next paragraph) before anyone commits to it.

**On the DIY-minimal path: native cherry-pick of coordinator is unsupported, period.** This is not a
degraded-but-tolerated path with a shrug and a "you're on your own now" — it is genuinely
unsupportable. Downstream repos plug **into** coordinator infra, and we cannot validate a custom
subset, so we cannot certify the chain works at all. We will not pretend otherwise, and we will not
claim a hand-picked subset works.

Be honest about the obvious: a Claude *will* offer to DIY-cherry-pick if the human pushes — agents are
eager, and yours will too. Don't pretend that won't happen. But say plainly what it costs: the operator
owns the **entire** outcome, does their **own** research and planning, and gets **no claim from us that
it works**. That is the deal on the DIY path; there is no supported-subset middle ground.

> **Chain-stability rule (the coordinator-completeness axis).** If the human intends *any* downstream
> chain — a private product, a sibling repo, anything that lists coordinator as a prerequisite —
> install the **FULL** coordinator system. Do not DIY-trim coordinator: downstream repos depend on
> coordinator infra that a cherry-pick could silently remove, and you would not find out until the
> chain breaks later. This is the **coordinator-completeness** axis: *how much of coordinator goes in*.
>
> It is **orthogonal** to whether a given downstream dependency is itself mandatory or optional — that
> is a separate question, governed by the mandatory-vs-optional discriminator in
> `post-install-onboarding-pattern.md`. Both rules hold at once.

### 1c. Plugin selection — what to enable

The ecosystem has three tiers. Offer the first two; do NOT offer the third to a generic user.

| Tier | Plugins | Default |
|---|---|---|
| **core** | `coordinator` | Always on. This is the system. |
| **recommended** | `deep-research` | On by default — opt out if not wanted. Also available standalone at [dbc-oduffy/deep-research-claude](https://github.com/dbc-oduffy/deep-research-claude). Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` for full multi-agent pipelines (the fresh session in Step 2 sets this). |
| **specialized — not part of this install** | UE/holodeck plugins, game-dev plugin, project-rag | Only relevant for Unreal Engine and holodeck workflows. Do NOT offer to a generic OSS user. |

If the human gave you a signal about their project type (web, ML, data science), confirm which
recommended plugins fit. Otherwise ask once, briefly.

**Offer granularity is the add-on level, never the component level.** The picks above —
deep-research (on by default, opt out) and the NotebookLM add-on (opt in) — are genuine install-time
choices, and they are the *only* kind of install-time choice on offer. You never pick-'n'-mix the
**internals** of a plugin you've chosen: install coordinator and you get *all* of it — every skill and
reviewer (`/staff-session`, the review personas, the full pipeline). There is no install-time per-skill
picker, and you do not add one. If the human wants a piece of an installed plugin turned off, that is a
**post-install** move — installed-but-disabled is a supported state (per-project plugin gating), set
*after* the fact, not carved out during install.

**Pre-restart "what else do you want installed?" question.** Coordinator is the natural *first*
install when the human wants several related tools — it is the contract the rest plug into. Remember
this is an **add-on-level** question, not a component-level one: you are asking *which whole tools go
in alongside coordinator*, not which slices of coordinator to keep. So while you have them, ask once:

- **deep-research** — recommended; the bundled OSS add-on. Install it in the same CLI pass (1d).
- **Other downstream repos** — if the human came here to install something further down a chain
  (e.g. a private/proprietary product that lists coordinator as a prerequisite), that product has
  its own installer. Note what they name; the post-restart session sequences any queued install legs
  via `/workday-start` (see Step 3) — you do not need to know what those are here.
- **Dev tooling worth having present** — recommend (don't force) **Python 3** and **Node 18+ /
  TypeScript** if absent: Claude reaches for them when solving problems, and a missing runtime turns
  a quick fix into a yak-shave. (Bash 4.3+ is already a hard prerequisite — see Prerequisites; macOS
  ships 3.2, so `brew install bash`.)

### 1d. Run the install (native `claude plugin` CLI)

Register the **public GitHub repo** as a marketplace, then install the plugins. This is the primary,
supported path — it works on current Claude Code (verified 2.1.186) and lets Claude Code manage
versions, updates, and the on-disk layout for you:

```bash
# 1. Register the PUBLIC GitHub repo as the marketplace (NOT your local clone — see note below):
claude plugin marketplace add dbc-oduffy/coordinator-claude

# 2. Install coordinator (always) and deep-research (if opted in at 1c):
claude plugin install coordinator@coordinator-claude
claude plugin install deep-research@coordinator-claude
```

Claude Code caches the marketplace under `~/.claude/plugins/marketplaces/coordinator-claude/` and
each plugin under `~/.claude/plugins/cache/coordinator-claude/<plugin>/<version>/` — **both inside
`~/.claude`. The install is fully self-contained: once it completes, the clone is a build-time input
you can move or delete, and the plugins keep working.** Read the CLI output; if it reports an error,
surface it to the human verbatim — do not paper over.

> **Why the GitHub repo, not your clone path?** `claude plugin marketplace add <a-directory>`
> registers a *directory* source that Claude Code resolves from that exact path on **every** load —
> it never copies a directory marketplace into `~/.claude`. Point it at your clone and the installed
> plugins gain a hard runtime dependency on the clone staying put; move or delete the clone and
> `/reload-plugins` reports `0 plugins`. A `git`/`github` source is cached into `~/.claude` instead,
> so it survives. The repo is public — no credentials needed.
>
> **Offline, or installing local modifications?** If you have no network access, or you want the
> installed runtime to reflect *uncommitted* edits in your clone, register the clone directly:
> `claude plugin marketplace add <clone-path>`. In that mode the clone **is** the runtime source —
> keep it in place, or re-run `claude plugin marketplace add dbc-oduffy/coordinator-claude` later to
> cut over to the self-contained GitHub source. (A future coordinator session also auto-repairs a
> clone-bound entry once the clone goes missing — see the self-heal note in the troubleshooting
> section — but don't rely on it; prefer the GitHub source up front.)

> **No sentinel, no onboarding baton, no `/pickup` staging here.** Earlier versions of this playbook
> ran a bespoke installer script before the restart and seeded an onboarding handoff for a `/pickup`
> resume. The native CLI flow has no pre-restart script, so there is nothing to seed: the
> post-restart `/coordinator:install` (Step 3) *is* the onboarding, and it records its own
> completion receipt. Do not hand-create a sentinel file or a handoff baton.

---

## Step 2 — The restart (load-bearing gate)

The plugins are installed. Now the human needs a fresh Claude Code session.

Tell the human exactly this:

> **Start a fresh Claude Code session from your coordinator root, then paste one command.**
>
> Coordinator's canonical runtime is the **Claude Code CLI** (preferred over the desktop app). To
> start the fresh session:
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
> **Switch to auto mode first.** Coordinator is an agentic system — the EM edits files, runs setup
> scripts, and dispatches subagents on your behalf. Press **Shift+Tab** to cycle the permission mode
> to **auto-accept ("auto") mode** so the install (and your everyday coordinator work) runs without a
> prompt on every action. This is the recommended way to run coordinator; you stay in control via the
> branch-as-review-buffer and commit history rather than per-action approvals.
>
> (If `claude` isn't found, install the CLI first: `npm install -g @anthropic-ai/claude-code`. If
> you've been using the desktop app, switch to the CLI for coordinator work — open a *new* CLI
> session with `~/.claude` as the working directory rather than reopening the desktop window.)
>
> Why a fresh session, and why from `~/.claude`? Two things take effect only at startup: (1) the
> coordinator's hooks and slash-commands load when Claude Code reads the newly-installed plugin, and
> (2) the Agent Teams capability (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) that the deep-research
> pipeline depends on is an environment variable Claude Code reads at startup. (`/coordinator:install`
> writes that env var; it takes effect on the *next* restart after that — the command tells you when.)
> Launching from `~/.claude` makes that directory the working root, so coordinator's doctrine and
> state load correctly from the first message.

Do NOT describe the fresh session as "just restarting" — the human is handing off to a new session
that runs `/coordinator:install` to finish the environment wiring. Whenever any step says "restart
your session from `~/.claude`", the concrete action is exactly the three lines above: a terminal,
`cd ~/.claude`, `claude`. Make sure they write the command down or can copy it.

---

## Step 3 — Post-restart: finish the environment, onboard a project

In the fresh session, the human runs:

1. **`/coordinator:install`** — environment wiring (safe to re-run; skips anything already
   configured). It checks prerequisites, sets the Agent Teams env var, lays down the machine-local
   registry, builds the helper venv, renders `CLAUDE.local.md`, scaffolds the canonical document
   structure, records the `setup_concluded` receipt, and offers a guided tour + repo bootstrap. This
   is the post-restart onboarding — there is no separate baton to `/pickup`.
2. **`/coordinator:repo-setup`** — per-project scaffolding (project `CLAUDE.md`, tracker, project
   type) for whatever repo the human wants to onboard. `/coordinator:install` is environment-only;
   `/coordinator:repo-setup` is the project-level step.
3. **`/workday-start`** — only if the human queued *other* downstream tools at the pre-restart step
   (1c): each downstream installer seeds its own install leg into `~/.claude/state/handoffs/`, and
   `/workday-start` triages whatever is present and sequences it. On a solo coordinator install (with
   or without deep-research — neither seeds a downstream leg), there is nothing queued — skip
   `/workday-start` and go straight to `/workstream-start` when ready to work.

The fresh session is a Claude that now understands the system. The highest-leverage first
*customization* is co-writing `CLAUDE.md` / `CLAUDE.local.md` together — the coordinator ships an
opinionated default; the operator and EM write the version that fits *how they want to work*. The
guided tour in `docs/getting-started.md` is the vehicle.

---

## Refinement target: edit your `~/.claude`, not this clone

After install, the human evolves their live, git-tracked `~/.claude` — their Claude Central.
**Do NOT edit the `coordinator-claude` source repo (the delivery truck) to customize behavior.**
Changes to a clone of the source repo don't touch running sessions; the next install would
overwrite them.

The rule: **edit your `~/.claude`, not this clone.** Methodology refinements, persona names,
`CLAUDE.md` evolution, `coordinator.local.md` project type — all of it lands in `~/.claude`.

---

## Prerequisites to check before any of the above

Before installing, verify:

- **Claude Code CLI** — present **by definition** if an agent is reading this playbook inside a
  Claude Code session; you are the proof. Skip the `claude --version` PATH check in that case: it
  false-negatives on the common native install (`claude` lives in `~/.local/bin`, often not on
  `PATH`), and reporting "Claude Code missing" to a human while a Claude Code agent runs the check
  is incoherent. Only when a *human* is bootstrapping with no session yet: if `claude --version`
  fails, probe `~/.local/bin/claude` (and the platform native-install dirs) before concluding it's
  absent; if truly missing, link to https://docs.anthropic.com/en/docs/claude-code and stop.
  - **Desktop-app installers — `claude` missing in the terminal.** A very common snag: the operator
    installs the plugins inside the Claude Code **desktop app**, then opens a terminal to follow the
    CLI steps and hits *"`claude`: command not found"* — the native CLI lives at `~/.local/bin`,
    which their login shell never put on PATH. The post-restart `/coordinator:install` (Step 3e) fixes
    this automatically (idempotent: a sentinel-guarded rc block on macOS/Linux, the user PATH on
    Windows). To run `claude` in a terminal *before* that, prepend the dir yourself:
    `export PATH="$HOME/.local/bin:$PATH"` (macOS/Linux) or add `%USERPROFILE%\.local\bin` to your
    user PATH (Windows).
- **bash 4.3+** on PATH (`bash --version`). The coordinator's scripts use associative arrays
  (bash 4.0+) and `coordinator-safe-commit` — invoked on essentially every commit — uses `local -n`
  namerefs (bash **4.3+**). **macOS ships bash 3.2 as `/bin/bash`**: install [Homebrew](https://brew.sh),
  `brew install bash`, and put it first on PATH (`export PATH="$(brew --prefix)/bin:$PATH"` in
  `~/.zshrc`/`~/.bashrc`). Coordinator scripts use `#!/usr/bin/env bash`, so PATH order — not
  `/bin/bash` — decides. `/coordinator:install` fails fast with this guidance if it runs under < 4.3.
  Linux, WSL, and Git Bash for Windows ship bash 4.3+ already — **but on Windows, `bash` is not
  invokable by name after a fresh Git-for-Windows install.** Git deliberately keeps `bash.exe` off
  `PATH` (to avoid shadowing); it lives at `C:\Program Files\Git\bin\bash.exe`. Either launch the
  "Git Bash" terminal (which puts it on `PATH` for that shell) or invoke it by full path. The native
  `claude plugin` install flow above needs no bash at all — bash is a prerequisite for coordinator's
  *scripts and hooks at runtime*, not for installing the plugins.
- **git** on PATH (`git --version`). Branch management, commits, handoffs, and the auto-push safety
  net all require it. If missing, link to https://git-scm.com and stop.
- **Python 3** on PATH — a **real** `python3`, not a stub (see the Windows note). The hooks and
  config helpers use Python for JSON manipulation. If missing, link to https://python.org and stop.
  - **Windows gotcha — the `python3` App-Execution-Alias stub.** On Windows, `python3` resolves by
    default to a Microsoft Store **App Execution Alias** — a 0-byte stub that errors on run and is
    invisible to Git Bash. Any `python3 …` call breaks against it. Fix it *before* installing:
    `winget install Python.Python.3.13`, ensure the real `Python313\` dir precedes
    `…\WindowsApps` on PATH, and — since Windows ships `python.exe`, not `python3.exe` — provide a
    `python3` (copy `python.exe` → `python3.exe`, or use the shim `/coordinator:install` lays down).
    `/coordinator:install` Phase 3 also detects orphan AppX stubs and installs a `python3.cmd` shim,
    but the pre-restart steps in *this* playbook need a working `python3` first.
  - **Windows gotcha — `winget` PATH changes don't reach the running shell.** `winget install …`
    prints *"Path environment variable modified; restart your shell."* — the change lands in the
    registry but not in the current process. An agent that installs a prerequisite and then tries to
    use it in the **same** session will see it as still-missing. After any `winget install`, start a
    fresh shell (or refresh `PATH` from the Machine + User registry hives) before continuing.
- **jq** on PATH (`jq --version`). Hooks use it. If missing, install it
  (`brew install jq` / `sudo apt install jq` / `winget install jqlang.jq`).
- **Node 18+** — only if the human wants the NotebookLM add-on. Otherwise irrelevant.

---

## Standing cost & cosmetics (set expectations)

Two things the human will see in `claude plugin details` that are worth explaining up front:

- **Always-on token cost.** The `coordinator` plugin adds roughly **~8.2k tokens to every session
  baseline** (per `claude plugin details`) before any skill is invoked — that is the standing cost of
  the doctrine and command surface being available. It is real; mention it so the number isn't a
  surprise. (Skills and command bodies load on demand; this baseline is the always-present part.)
- **Doubled skills count is cosmetic.** `claude plugin details` reports a skills count (e.g.
  "Skills (75)") with about half the names doubled (`plan, plan`, `bug-sweep, bug-sweep`, …). This is
  because coordinator ships most capabilities as **both** a skill (`skills/<name>/`) and a same-named
  slash-command wrapper (`commands/<name>.md`) — the CLI counts both. It inflates the *displayed*
  count and token estimate; it is not a real duplication or a runtime multiplier. Cosmetic only.

---

## Manual install (fallback only)

Use only if the `claude plugin` CLI cannot run (no CLI available, sandboxed environment). These
steps are self-contained — you do not need any installer script. The CLI flow above is strongly
preferred; reach for this only when it is genuinely unavailable.

1. `mkdir -p ~/.claude/plugins/coordinator-claude`
2. `cp -r coordinator deep-research web-dev data-science ~/.claude/plugins/coordinator-claude/`
   (copy whichever plugins the human chose — the repo's top-level plugin dirs).
3. Copy `.claude-plugin/marketplace.json` into
   `~/.claude/plugins/.claude-plugin/marketplace.json`. The `source` fields are already flat
   (`./coordinator`, `./deep-research`, …) — keep them as-is.
4. Merge an entry into `~/.claude/plugins/known_marketplaces.json` for `coordinator-claude`
   pointing at the install dir.
5. Merge entries into `~/.claude/plugins/installed_plugins.json` (one per plugin, key
   `<name>@coordinator-claude`, with `installPath` and `version` from each plugin's `plugin.json`).
6. Merge `~/.claude/settings.json`: enable plugins under `enabledPlugins` (keys are
   `<name>@coordinator-claude`, **not** bare `<name>`); register the marketplace under
   `extraKnownMarketplaces` (an object, each key a marketplace name); and add `Edit` and `Write` to
   `permissions.allow` (background subagents need these — `defaultMode: dontAsk` does not propagate
   to them).

On Windows (Git Bash / WSL), config files store **native** Windows paths (`C:\Users\…`), not POSIX
(`/c/…`). Write native paths into the JSON or Claude Code will fail to resolve the plugins.

After a manual install, restart and run `/coordinator:install` exactly as in Step 3.

---

## Optional follow-ups to mention

- **Name your reviewers (optional):** persona renaming is a post-install, cosmetic choice — handle it
  in `/coordinator:install` Phase 6 (Persona Customization) or by hand-editing the names across the
  agent files. Display-only; agent behaviour is unchanged.
- **Per-project config:** `coordinator.local.md` with
  `project_type: web-dev|data-science|game-dev|general` controls which domain reviewers activate.
  Without it, only the universal reviewers run. `/coordinator:repo-setup` writes this for you.
- **Contributing to the plugins themselves?** See
  [CONTRIBUTING.md](https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md) for
  the dev workflow.

---

## Failure modes to watch for

- **`claude plugin install` reports nothing / no plugin appears.** Confirm the marketplace was added
  first (`claude plugin marketplace add dbc-oduffy/coordinator-claude`) and that the key is
  `<name>@coordinator-claude` (the marketplace name is `coordinator-claude`, from the repo's
  `.claude-plugin/marketplace.json` — identical whether the source is the GitHub repo or a clone).
- **`/reload-plugins` reports `0 plugins` after a working install.** Almost always a clone-bound
  marketplace whose source directory was moved or deleted. Check
  `~/.claude/plugins/known_marketplaces.json`: if the `coordinator-claude` entry's `source.source`
  is `directory` with a `path` outside `~/.claude` that no longer exists, re-register from GitHub —
  `claude plugin marketplace add dbc-oduffy/coordinator-claude` — then `/reload-plugins`. Coordinator
  also self-heals this on the next session start (the `platform-localize` hook rewrites a missing
  clone-bound entry to the GitHub source), but the manual re-add is the immediate fix.
- **`enabledPlugins` keys must be `<name>@coordinator-claude`**, not bare `<name>`. Common typo on the
  manual path.
- **`extraKnownMarketplaces` is an object, not an array.** Each key is the marketplace name.
- **Path translation on Windows (manual path only).** Forget native paths in JSON and Claude Code will
  fail to resolve plugins.
- **Plugins installed but commands missing.** The hooks and slash-commands load at startup — the human
  must restart (Step 2) before `/coordinator:install` is available.

---

## If you had to patch something to install — send it back

If you hit a rough edge and worked around it — hand-merged a JSON file, fixed a path-translation bug,
patched around a platform-specific snag, anything — **you are exactly the contributor we want to hear
from.**

Before you wrap up, offer to send the fix upstream. You are well-placed to write it up: you have the
error in context and you made the change. Draft one of these for the human (preference order):

1. **A PR** against [dbc-oduffy/coordinator-claude](https://github.com/dbc-oduffy/coordinator-claude)
   with your patch.
2. **An issue** describing what broke, on what platform, and what you changed.
3. **A rough note** — a paragraph in an issue is plenty.

Don't polish it, and don't gate on code quality. The valuable part is the *what / how / why*:
what failed, how you worked around it, and why it failed on this setup. We can generalize a proper
fix from a throwaway hack — far more than from a one-line bug report.
See [CONTRIBUTING.md](https://github.com/dbc-oduffy/coordinator-claude/blob/main/CONTRIBUTING.md).

---

## Keeping the install current

After install, `/coordinator-update` is the PM-invoked way to update later: it checks online for the
latest published version, computes a delta against the human's install, and **advises** a path
(overwrite / cherry-pick / plan-to-ingest) while **preserving the human's own customizations by
default** (renamed personas, structural divergence). It never blindly overwrites. To pull a newer
published version through the CLI, `claude plugin install coordinator@coordinator-claude` again picks
up the latest from the marketplace; `/coordinator-update` is the safer, customization-aware path.

---

## Where the deeper docs live

- [docs/getting-started.md](getting-started.md) — first-run usage, per-project config,
  troubleshooting (audience: human, post-install).
- [docs/architecture.md](architecture.md) — how the system works.
- [docs/customization.md](customization.md) — adding skills, persona templates, CI checks.
- [docs/install/AGENT.md](install/AGENT.md) — the install-chain walker guide (for multi-repo chains).
