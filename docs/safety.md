# Safety — What the Install Changes and How to Undo It

This document tells you exactly what installing coordinator-claude changes on your machine, what
it does *not* do, how to verify an installation, and how to reverse it completely. Every claim
here cites a specific file or command in this repo.

**The published install path is the native Claude Code plugin CLI**, not a bundled shell
installer — there is no `setup/install.sh` in this distribution. The two commands you actually
run are:

```bash
claude plugin marketplace add dbc-oduffy/coordinator-claude
claude plugin install coordinator@coordinator-claude
```

followed, in a fresh session, by `/coordinator:install` (environment wiring) and
`/coordinator:repo-setup` (per-project scaffolding). Source: `INSTALL.md` §§ 1d, 3.

---

## 1. What the install changes

### The `claude plugin` CLI step

Registering the marketplace and installing the plugin is handled entirely by Claude Code's own
plugin manager — this repo ships no code for that step. Claude Code caches the marketplace under
`~/.claude/plugins/marketplaces/coordinator-claude/` and the plugin under
`~/.claude/plugins/cache/coordinator-claude/coordinator/<version>/`, both inside `~/.claude`.
There is a single plugin, `coordinator`, at the repo root — deep-research is folded inside it,
not a separate plugin, and there is no longer a multi-plugin layout
(`web-dev`/`data-science`/`deep-research`/`game-dev` subdirectories, from an earlier version of
this system, do not exist in this distribution).

Source: `INSTALL.md` § 1d.

### `/coordinator:install` — environment wiring

Run once, post-restart, in a fresh session. It is safe to re-run (idempotent — skips anything
already configured) and never overwrites `CLAUDE.md` or `settings.json` wholesale. Per
`coordinator/commands/uninstall.md` § "What gets reversed" (the authoritative, symmetric surface
list this repo maintains against its own uninstall command), the surfaces it can write are:

| # | Surface | What it is |
|---|---------|-----------|
| 1 | Plugin wiring / mirror registry keys | Records which plugin tree is active |
| 2 | A generated hook block in `~/.claude/settings.json` | Registers coordinator's hooks with Claude Code, preserving any hooks you already had |
| 3 | Machine-local registry (`~/.coordinator-claude-settings/machine-local/`) | Coordinator's own config keys (e.g. sibling-repo paths), never your other settings |
| 4 | A shell launch shim + an `rc`-file source line | Only present in the maximalist/dev install mode; the flat marketplace-plugin install (the path this doc covers) does not need it |
| 5 | A small helper venv (`whoami` tool) | Local Python virtualenv under the settings-home tree |
| 6 | `.doe-root` pointer | Only relevant to the dev-clone install mode, not the marketplace path |
| 7 | `~/.claude/bin/` forwarder scripts | Coordinator-owned command names only — never a blanket write to that directory |
| 8 | `~/.coordinator-claude-settings/` tree | Coordinator-authored files only (`machine-local/`, `bin/`, `coordinator-whoami/`, `.coordinator-venv/`, `state/handoffs`) |
| 9 | `~/.claude/coordinator-identity.yaml`, `working-repos.yaml` | Your operator name and posture preferences |
| 10 | `${HOME}/.local/bin/claude-doe` wrapper | Only present in the maximalist/dev install mode |

It also, on request, adds `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"` to the `env` block of
`~/.claude/settings.json` (required for staff sessions and research pipelines; takes effect on
next restart) and seeds `~/.claude/CLAUDE.md` from a template — but only when that file is absent
or already carries the seed's own sentinel; a hand-authored `CLAUDE.md` is never overwritten.

Sources: `coordinator/commands/uninstall.md` §§ "What gets reversed", "Backing script";
`coordinator/commands/install.md` Phase 1b, Phase 2 "Personal-layer doctrine seed".

Several of these surfaces (#4, #6, #10) belong to a "maximalist" development-install mode used
inside the doctrine repo itself, and are not written by a plain `claude plugin install` +
`/coordinator:install` run. This document lists them for completeness because the uninstall
command reverses them unconditionally where present; a marketplace-only install simply never
creates them.

### Hooks registered

The plugin ships `hooks/hooks.json`, read automatically by Claude Code once the plugin is
enabled — no separate registration step. All hook scripts are Python, invoked through a runpy
trampoline that fails open (no-ops) if a registered script is missing. As of a 2026-07-15
directive, boot-time guardrail/reminder/detector `SessionStart` hooks were removed to keep
session boot fast; only an orientation-cache loader and a small set of integrity self-checks
remain at `SessionStart`. The authoritative, current hook roster always lives in
`coordinator/hooks/hooks.json` in this repo — read it directly rather than trusting a table here
to stay current.

None of these hooks make network calls, collect credentials, or transmit data.

Source: `coordinator/hooks/hooks.json`.

### Optional add-ons

- **NotebookLM (Pipeline D)** — default-off. An external, third-party, OSS MCP server
  (`jacob-bd/gemini-notebook-mcp-cli`) that you install yourself via `uv tool install
  notebooklm-mcp-cli`, authenticate via `nlm login` (your own Google account), and register via
  `nlm setup add claude-code`. This repo does not install or launch it — it only offers to walk
  you through the steps. Source: `coordinator/commands/install.md` § 1d.

### The engine (`coordinator_core` / `claude-klabauter`)

coordinator-claude declares a **hard dependency** on a separate control-plane engine, published
as a companion repository, [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter).
That publish is live and public — the engine is installed separately, not something this
install fetches or runs for you.

This document does not attempt to describe what the engine writes to your machine, because it is
not part of this distribution and this repo cannot verify claims about code it does not ship.
Most of coordinator-claude's 36 skills call into the engine, directly or through a settings-home
forwarder, and will not function without it; the skills that don't (plan-review, brainstorming,
shape flows) are pure-prompt and work regardless.

Sources: `NOTICE.md` (this distribution's top level), `docs/wiki/manifesto.md` (status note),
`README.md` § "The engine underneath" (this distribution's top level).

---

## 2. What the install does NOT do

From `PRIVACY.md` (this distribution's top level, last updated 2026-04-02):

> This plugin does **not** collect, transmit, or store any user data. It has no analytics,
> telemetry, tracking, or external reporting of any kind.

Specifically:

- **Collect credentials** — no API keys, tokens, or authentication material are read, transmitted,
  or exfiltrated by this repo's own code. (`gh auth login` / `nlm login`, if you choose to run
  them, are your own interactions with GitHub/Google, not something coordinator-claude
  intercepts.) This does **not** cover the optional, consent-gated `setup-github-auth-1password.py`
  helper (§ "GitHub Auth via 1Password (optional opt-in)"; the `[y/N]` consent prompt and the
  "On YES" leg that runs `scripts/setup-github-auth-1password.py`): on explicit `[y/N]` consent it
  detects and optionally installs the `op` CLI, **rewrites `~/.ssh/config`** (backing it up first),
  configures **global SSH commit signing**, and offers to flip the current repo's `origin` remote
  to SSH. Nothing it touches is sent anywhere by this repo's code — it only edits local config and
  calls `git ls-remote` to verify — but it is credential-*adjacent* local-machine mutation,
  declined by default, and worth naming explicitly rather than folding under the `gh auth login`
  parenthetical. Separately, install persists `coordinator.contributor_slug` (§ "Step 3 — Optional
  seed prompt (declinable, interactive only)") — an identifier derived
  from your `git user.email` — to the local machine-local registry; it is never transmitted, but
  it is PII-derived and this document previously omitted it.
- **Start a background daemon** — no persistent process, service, or cron job is created. Install
  does, however, write sentinel-guarded blocks into your interactive shell rc file
  (`~/.bashrc`/`~/.zshrc`): the `claude()` shim (§ "3.5a.2 — Install `claude()` shim
  (idempotent)"), the interactive resource-cap guard seam (§ "3.5b.1 — Install interactive-shell
  resource-cap guard (idempotent, graceful-absent)"), and the `~/.local/bin` PATH block (§ "Step
  3e — `claude` CLI on PATH (cross-platform, idempotent)"). None of these are a daemon — nothing runs
  unless you open a new interactive shell — but coordinator-authored code does execute at every
  new shell start as a result, and a careful reader may reasonably count that against "nothing
  persists."
- **Send telemetry** — no usage data, session data, or diagnostic pings leave your machine from
  coordinator's own code.
- **Modify project files without being asked** — `/coordinator:install` itself writes into the
  invocation repo, not only into `~/.claude`/settings-home, at four points: it writes
  `<repo-root>/.claude/em-context.md` (the EM-posture overlay — `coordinator/commands/install.md`
  § "Step 3b-5 — Materialize the overlay pre-restart", and creates the file if absent), appends
  two lines to `<repo-root>/.gitignore` — creating that file if it's absent — to keep that overlay
  untracked (same step, "add these two lines to the end of that file"), writes
  `<repo-root>/coordinator.local.md` (§ "Phase 5 — Project-local" § "coordinator.local.md", "Write
  `coordinator.local.md`:"), and writes a currency stamp via `coordinator_currency.py write "$PWD"`
  (§ "Currency stamp (idempotent)"). It also mutates that repo's git config — `gc.autoDetach false`
  and `core.checkStat minimal` (§ "1a.1. Git-config hardening (concurrent-EM lock safety)",
  "Idempotent" but not consent-gated — `core.checkStat minimal` is also set globally and
  unconditionally: `git config --global core.checkStat minimal`). None of this is destructive and all of it is idempotent, but it is not confined
  to `~/.claude`/settings-home as an earlier version of this document claimed. Broader project
  scaffolding — beyond these four writes — is deferred to `/coordinator:repo-setup`, which you run
  explicitly and separately.

**This is not a network-call-free system, and this document will not claim it is.** The `claude
plugin` CLI itself fetches from GitHub to register the marketplace and install/update the plugin;
`/coordinator:install` can, with your consent at each step, invoke `git`, `brew`, `winget`, or `gh
auth login`/`glab auth login` to check or install prerequisites; and the optional NotebookLM
add-on talks to Google. Most of these are individually consent-gated (see
`coordinator/commands/install.md`, its "D4 Non-Interactive Contract" and per-step consent
language) — but not all: `git lfs install` (§ "1a.3. Git-LFS enablement (idempotent, harmless —
proactive coverage)") is documented as **"act-not-gate"** — a global git config mutation applied
without a prompt whenever the `git lfs` binary is present. And `ensure-doe-clone` (§ "3.5a — Clone
the DoE repo (idempotent)") performs an un-prompted `git clone` against a remote whenever the
registry path resolves but the target directory is absent — the `AskUserQuestion` prompt fires
only when the path is *unresolved*, and under `--non-interactive` the registry must be pre-seeded,
so this leg runs with no interactive gate at all in that mode. Separately, venv provisioning (§
"Step 6 — Coordinator venv / `coordinator_whoami` provisioning (native, folded into Step 1)") is
annotated in this
document's own source as "no prompt site" and normally fetches `pydantic`/`psutil` from a package
index; the code that does this now lives in the unpublished `claude-klabauter` engine
(`coordinator_core.install.ensure_venv`), so that leg is **unverifiable against this
distribution** — this document cannot audit code it doesn't ship. No step in this repo phones
home usage or session data as a side effect; the qualification above is about prerequisite/package
fetches, not telemetry.

Source: `PRIVACY.md`; `coordinator/commands/install.md`.

---

## 3. How to audit the installation

All commands below read existing files and make no changes.

### Verify plugin registration

```bash
claude plugin list
```

### Inspect the marketplace and plugin cache

```bash
cat ~/.claude/plugins/known_marketplaces.json | jq '.["coordinator-claude"]'
ls ~/.claude/plugins/cache/coordinator-claude/coordinator/
```

### Check installed_plugins.json

```bash
jq '.plugins | keys | map(select(endswith("@coordinator-claude")))' \
  ~/.claude/plugins/installed_plugins.json
```

### Check settings.json changes

```bash
# Enabled plugins
jq '.enabledPlugins | to_entries | map(select(.key | endswith("@coordinator-claude")))' \
  ~/.claude/settings.json

# Agent Teams env var (only if you accepted the Phase 1b offer)
jq '.env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS' ~/.claude/settings.json
```

### List installed hook scripts

```bash
ls ~/.claude/plugins/cache/coordinator-claude/coordinator/*/hooks/scripts/
```

### Check operator identity / settings-home writes

```bash
cat ~/.claude/coordinator-identity.yaml 2>/dev/null
ls ~/.coordinator-claude-settings/ 2>/dev/null
```

---

## 4. How to uninstall

There is a first-class, tested, symmetric command for this: `/coordinator:uninstall`
(`coordinator/commands/uninstall.md`). It reverses every surface #1–#10 listed in § 1 above,
whichever of them are actually present on your machine (the maximalist-only surfaces #4/#6/#10
simply have nothing to reverse on a plain marketplace install).

```
/coordinator:uninstall
```

- **Default (full-remove).** Every surface reversed; no coordinator tree resolvable afterward.
- **`--keep-marketplace`** — reverts to a bare flat marketplace plugin instead of removing it
  entirely.
- **`--purge-operator-config`** — also removes `coordinator-identity.yaml` and
  `working-repos.yaml` (not removed by default — a bare uninstall never touches your identity
  file).
- **`--dry-run`** — prints the plan; performs zero writes.

After running it, **restart Claude Code** — the uninstall rewrites `settings.json` and plugin
wiring, both of which Claude Code only re-reads at boot.

If you cannot run `/coordinator:uninstall` (e.g. you already removed the plugin so the command
isn't available), the manual equivalent for the plain marketplace install is the native CLI:

```bash
claude plugin uninstall coordinator@coordinator-claude
claude plugin marketplace remove coordinator-claude
```

then remove any settings-home files you want gone by hand, per the audit commands in § 3.

### What uninstall does NOT reverse

`/coordinator:uninstall` does not claim, and this document will not claim on its behalf, to put
your machine back to its exact pre-install state. The following survive an uninstall and need
manual cleanup if you want them gone; fixing the uninstall command to cover them is separate,
already-filed work, not something this document attempts to paper over:

- **Windows Defender process exclusions** (if you accepted the offer in
  `coordinator/commands/install.md` § "Step 1c — Windows Defender process-exclusion offer
  (Windows-only, admin-gated, declinable)") — that same section documents the
  rollback as manual: run `Remove-MpPreference -ExclusionProcess "<path>"`, elevated, per
  excluded interpreter path.
- **`~/.ssh/config` changes and global SSH commit signing** (if you accepted the 1Password offer,
  § "GitHub Auth via 1Password (optional opt-in)") — a backup of the pre-edit file is left alongside it, but restoring it is on you.
- **Global git config** written outside any single repo — `core.checkStat minimal` (also set
  globally per § "1a.1", not just per-repo) and the `git lfs install` filter wiring (§ "1a.3",
  un-prompted per the network-touch note in § 2 above).
- **The two extra shell-rc sentinel blocks** named above (resource-cap guard, PATH block) — the
  `claude()` shim block is reversed by uninstall per surface #4/#10 in § 1's table, but the other
  two are not currently in that reversal list.
- **The four project-repo files** listed in § 1 under "Modify project files without being asked"
  (`.claude/em-context.md`, the `.gitignore` append, `coordinator.local.md`, the currency stamp) —
  uninstall operates on `~/.claude`/settings-home surfaces, not on repos you ran install from.

None of these are hidden or destructive on their own — each is documented at its own citation
above — but "uninstall" undoing all of them is not currently true, and this document will not
repeat that claim.

Source: `coordinator/commands/uninstall.md`.

---

## 5. A note on this document's scope

Earlier versions of coordinator-claude shipped a bespoke `setup/install.sh` bash installer, and
an earlier version of this document was written against it. That installer is not part of this
distribution — the native `claude plugin` CLI plus `/coordinator:install` is the canonical,
supported path (see `INSTALL.md`), and the bash installer's publish target is
deliberately disabled in this repo's own build. If you find a reference to `setup/install.sh`
anywhere else in this distribution's docs, it is stale — please open an issue.

This document does not, and cannot, describe what the `claude-klabauter` engine changes on your
machine, because that repository is not published and not shipped here (see § 1, "The engine").
Treat any engine-dependent workflow as out of this document's audit scope until that repository
is public and this document can be updated against it.
