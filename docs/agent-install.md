# Agent Install Playbook

> **Audience: you, Claude (or another coding agent).** The human pasted a one-liner into their
> session and it brought you here. Your job is to guide a **guided install** of the coordinator
> system — not to run a script and declare done. This is a *collaboration system*; you follow this
> playbook **in partnership with the human**, and they participate in the shape decisions while you
> move fast on mechanism.
>
> There is no "install.sh exit = complete" reading of this playbook. The script wires the
> environment; the collaboration model is what the human is actually installing.

---

## Step 0 — Detect: Track A or Track B?

> **Before any block:** confirm Prerequisites (end of this doc) — Claude Code CLI, Python 3, jq, bash 4+.
> **Running the bash blocks:** pre-install blocks (Step 0 and Step 1a–1d) assume your cwd is the
> coordinator clone root — the directory you cloned and read this playbook from; `cd` there first.
> Post-install blocks (Step 1e onward) use absolute `~/.claude` paths and run from anywhere.

Before any other action, run the Track A/B classifier from the clone root:

```bash
bash plugins/coordinator/lib/detect-existing-claude-home.sh
```

The script emits one line: `track=A reason: …` or `track=B reason: …`.

**Track A — install from zero.** Nothing is in `~/.claude` beyond Claude's defaults. Proceed to
Step 1 (Layer 0).

**Track B — existing structure detected.** The classifier found a git-tracked `~/.claude`, an
installed plugin, or a substantially-edited `CLAUDE.md`. Surface this to the human:

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

Wait for an explicit answer before continuing. If they choose to proceed, follow the Track A path
from Step 1 onward, noting in the continue-onboarding handoff that Track B was detected.

---

## Step 1 — Layer 0: everything a vanilla session can do before the restart

Layer 0 is frontloaded. Do all of this before asking the human to restart Claude Code.

### 1a. Clone or locate the repo

```bash
# If the user hasn't cloned yet:
git clone https://github.com/dbc-oduffy/coordinator-claude.git ~/coordinator-claude
```

If it's already on disk, confirm the path with the human.

<!-- EDITOR NOTE: coordinator-claude has NO bin/register-claude-plugin script (confirmed phantom by
     the 2026-05-30 dogfood). The plugin-extraction wiki prescribes that script name *generically*;
     coordinator registers via setup/install.sh. Do not re-introduce a register-claude-plugin call here. -->
### 1b. How registration works (no separate register script)

coordinator-claude has **no standalone registration script** — `setup/install.sh` (Step 1d below) is
the bootstrap. It copies the plugins into `~/.claude` AND registers them in Claude Code's JSON config
(marketplace + enabled-plugin entries) from wherever the user cloned the repo. You run it in Step 1d;
there is nothing separate to run here.

After the installer has run, activate the coordinator's slash commands in the **current** session
without a cold restart:

```bash
# In the current Claude Code session, run:
# /reload-plugins
```

This makes the slash commands available immediately. The fresh session (Step 2) is still needed for
the Agent Teams env var — `/reload-plugins` alone is not a substitute.

### 1c. Plugin selection — what to enable

The ecosystem has three tiers. Offer the first two; do NOT offer the third to a generic user.

| Tier | Plugins | Default |
|---|---|---|
| **core** | `coordinator` | Always on. This is the system. |
| **recommended** | `deep-research` | On by default — opt out if not wanted. Available standalone at [dbc-oduffy/deep-research-claude](https://github.com/dbc-oduffy/deep-research-claude). Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` for full multi-agent pipelines (the fresh session in Step 2 sets this). |
| **specialized — not part of this install** | UE/holodeck plugins, game-dev plugin, project-rag | Only relevant for Unreal Engine and holodeck workflows. Do NOT offer to a generic OSS user. |

If the human gave you a signal about their project type (web, ML, data science), confirm which
recommended plugins fit. Otherwise ask once, briefly.

### 1d. Run setup (installer + plugin wiring)

```bash
# Interactive (recommended — lets the human pick reviewers and confirm plugin selection):
bash setup/install.sh

# Non-interactive defaults (coordinator + deep-research):
bash setup/install.sh --non-interactive

# Explicit plugin list:
bash setup/install.sh --plugins coordinator,deep-research
```

Read the installer summary. If it reports validation errors, surface them to the human verbatim —
do not paper over.

### 1e. Write the sentinel file

```bash
touch ~/.claude/.coordinator-fresh-install
```

This sentinel marks the install session so downstream scripts and the continue-onboarding handoff
can identify it.

### 1f. Stage the continue-onboarding handoff

Copy the handoff template and substitute its tokens:

```bash
HANDOFF_DEST="${HOME}/.claude/tasks/handoffs/continue-onboarding-and-installation.md"
# install.sh (Step 1d) has already copied the plugin into ~/.claude — resolve the
# template from the installed location, NOT $0/cwd (this playbook is run as ad-hoc
# snippets by an agent, so $0 is the shell, not the clone path).
TEMPLATE="${HOME}/.claude/plugins/coordinator/templates/handoffs/continue-onboarding-and-installation.md"
mkdir -p "$(dirname "$HANDOFF_DEST")"
cp "$TEMPLATE" "$HANDOFF_DEST"

# Substitute {{DATE}} and {{BRANCH}} tokens:
TODAY="$(date +%Y-%m-%d)"
BRANCH="$(git -C "${HOME}/.claude" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'main')"
sed -i "s/{{DATE}}/${TODAY}/g; s/{{BRANCH}}/${BRANCH}/g" "$HANDOFF_DEST"
```

Confirm the file exists and the tokens are substituted before moving to Step 2.

### 1g. Pre-write the install state record

```bash
bash "${HOME}/.claude/plugins/coordinator/bin/coordinator-setup-state.sh" record setup_concluded
```

This records which install phases succeeded so the continue-onboarding session can check for
deferred legs without re-interrogating the user.

---

## Step 2 — The restart (load-bearing gate)

Layer 0 is complete. Now the human needs a fresh Claude Code session.

Tell the human exactly this — verbatim matters:

> **Start a fresh Claude Code session and paste:**
>
> `/pickup tasks/handoffs/continue-onboarding-and-installation.md`
>
> Why a fresh session? The Agent Teams capability (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) that
> the deep-research pipeline depends on is an environment variable that Claude Code reads at
> startup. `/reload-plugins` activated the coordinator's slash commands without a restart; the
> env var needs the fresh session to take effect.

Do NOT describe the fresh session as "restarting Claude Code" alone — the human needs to know
they are handing off to a new session that resumes from a specific point. The `/pickup` command
is the resumption mechanism; make sure they write it down or can copy it.

---

## Step 3 — Layer 2: what the fresh session does

The fresh session resumes via `/pickup tasks/handoffs/continue-onboarding-and-installation.md`.
That handoff carries everything the new session needs. You (this cold agent) do not need to
describe the fresh session's work in detail here — that work is specified in the handoff body.

The broad shape is:

1. **Co-write `CLAUDE.md` and `CLAUDE.local.md`.** The highest-leverage first step. The
   coordinator ships an opinionated default; the operator and EM write the version that fits *how
   they want to work* together.
2. **Finish any deferred install legs.** The sentinel file and state record from Layer 0 let the
   fresh session audit what completed and what didn't.
3. **First real working spin.** The guided tour in `docs/wiki/getting-started.md` is the vehicle;
   the EM facilitates it as a conversation, not a lecture.

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

Before running the registration step or installer, verify:

- **Claude Code CLI** on PATH: `claude --version`. If missing, link the human to
  https://docs.anthropic.com/en/docs/claude-code and stop.
- **Python 3** on PATH. The installer uses Python for JSON manipulation. If missing, link to
  https://python.org and stop.
- **jq** on PATH (`jq --version`). Hooks use it. If missing, the installer will warn and offer to
  continue — recommend installing it (`brew install jq` / `sudo apt install jq` /
  `winget install jqlang.jq`) but accept the human's call.
- **Node 18+** — only if the human wants the NotebookLM add-on. Otherwise irrelevant.

---

## Manual install (fallback only)

Use only if `setup/install.sh` cannot run (no bash, sandboxed environment). The mechanical steps:

1. `mkdir -p ~/.claude/plugins/coordinator-claude`
2. `cp -r plugins/* ~/.claude/plugins/coordinator-claude/`
3. Copy `.claude-plugin/marketplace.json` into `~/.claude/plugins/.claude-plugin/marketplace.json`,
   rewriting each plugin's `source` field from `./plugins/<name>` to `./<name>` (flat layout).
4. Merge an entry into `~/.claude/plugins/known_marketplaces.json` for `coordinator-claude`
   pointing at the install dir.
5. Merge entries into `~/.claude/plugins/installed_plugins.json` (one per plugin, key
   `<name>@coordinator-claude`, with `installPath` and `version` from each plugin's `plugin.json`).
6. Merge `~/.claude/settings.json`: enable plugins under `enabledPlugins`, register the
   marketplace under `extraKnownMarketplaces`, and add `Edit` and `Write` to `permissions.allow`
   (background subagents need these — `defaultMode: dontAsk` does not propagate to them).

Schema reference: read `setup/install.sh` directly — it is the spec. On Windows (Git Bash / WSL),
config files store **native** Windows paths (`C:\Users\...`), not POSIX (`/c/...`) —
`install.sh::native_path` does this translation.

---

## Optional follow-ups to mention

- **Name your reviewers (optional):** `bash setup/name-personas.sh "the Staff Engineer" "Alex"`.
  Display-only — agent behaviour is unchanged.
- **Per-project config:** `.claude/coordinator.local.md` with `project_type: web|data-science|game|pure-docs`
  controls which domain reviewers activate. Without it, only the universal reviewers run.
- **Plugin cache out of sync** after editing plugin source: `bash setup/dev-sync.sh`. Relevant if
  the human is contributing to the plugins themselves.

---

## Failure modes to watch for

- **`claude plugin install` from a directory marketplace** silently fails on some Claude Code
  versions. The JSON-merge approach in `install.sh` is the reliable path.
- **`enabledPlugins` keys must be `<name>@coordinator-claude`**, not bare `<name>`. Common typo.
- **`extraKnownMarketplaces` is an object, not an array.** Each key is the marketplace name.
- **Path translation on Windows.** Forget native paths in JSON and Claude Code will fail to
  resolve plugins. The installer handles this; if you go manual, replicate it.

---

## If you had to patch something to install — send it back

This install path leans on you (an agent) precisely because a script-only installer was
whack-a-mole: it worked on the author's machine and broke in small, machine-specific ways
elsewhere. If you hit one of those rough edges and worked around it — patched `install.sh`,
hand-merged a JSON file the script choked on, fixed a path-translation bug, anything — **you are
exactly the contributor we want to hear from.**

Before you wrap up, offer to send the fix upstream. You are well-placed to write it up: you have
the error in context and you made the change. Draft one of these for the human (preference order):

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

After install, `/coordinator-update` is the PM-invoked way to update later: it checks online for
the latest published version, computes a delta against the human's install, and **advises** a path
(overwrite / cherry-pick / plan-to-ingest) while **preserving the human's own customizations by
default** (renamed personas, structural divergence). It never blindly overwrites — re-running
`setup/install.sh` clobbers in-tree edits; `/coordinator-update` does not.

---

## Where the deeper docs live

- [docs/getting-started.md](getting-started.md) — first-run usage, per-project config,
  troubleshooting (audience: human, post-install).
- [docs/architecture.md](architecture.md) — how the system works.
- [docs/customization.md](customization.md) — adding skills, persona templates, CI checks.
- [setup/install.sh](../setup/install.sh) — canonical spec for what "installed" means.
