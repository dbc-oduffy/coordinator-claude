# Configuring a cloud environment for coordinator

**`setup.sh` is one of four fields, not the whole configuration.** A cloud environment is created at
[claude.ai/code](https://claude.ai/code) → environment selector → **Add cloud environment** (or the
settings icon on an existing one). The dialog is the operator's surface: it lives in no repo, and
nothing in any repo can read it, set it, or check it. That is why this file exists — the parts that
are not `setup.sh` have nowhere else to be written down.

An environment applies wherever a cloud session starts: Claude Code on the web, `claude --cloud`,
Claude Tag, routines, the mobile and desktop apps. **It is not scoped to a repo**, so one
correctly-configured environment serves sessions on every repo in the fleet — including siblings
that ship no installer and carry no coordinator files of their own.

## The four fields

### 1. Name

Anything. It is how you pick the environment later from the selector.

### 2. Network access — **Trusted** is correct; do not use None

| Level | Use for coordinator |
|---|---|
| **Trusted** (default) | **Correct.** Allowlisted domains: package registries, GitHub, cloud SDKs. |
| None | **Breaks the setup script.** No outbound access; the clones and the dependency install both fail. |
| Full | Works, and grants more than this needs. |
| Custom | Works if you tick *Also include default list of common package managers*; without it, list PyPI yourself. |

Two things reach a session regardless of level, because they do not traverse the session's
allowlist: **GitHub** (through its own proxy, which also keeps your real credentials off the VM)
and **MCP connector traffic** (through Anthropic's servers). So the clones would survive a
tightened allowlist; the `pip` install is what would not.

### 3. Environment variables

Paste both. They are `.env` format, one per line:

```
COORDINATOR_SETTINGS_HOME=/root/.coordinator-claude-settings
COORDINATOR_ENGINE_ROOT=/opt/coordinator/claude-klabauter
```

**These reach the SESSION, not the setup script.** The script cannot read this box, which is why it
hardcodes the same values internally — the two must agree. If the script's report says `HOME` is
not `/root`, or that `/opt` was not writable, it prints the `ROOT=` path it actually used; change
both lines to match it.

**This box is visible to anyone who can use the environment.** The dialog says so. No tokens, no
credentials. On Pro and Max plans, a key the agent proxy can attach belongs in **API credentials**
on an existing environment's dialog instead.

### 4. Setup script

Paste `setup.sh` from this directory. It runs on a fresh Ubuntu 24.04 VM with the repo already
cloned, **before Claude Code launches** — which is the ordering the whole design rests on, since it
means the script can write the VM's own `$HOME/.claude` and have Claude Code read it at launch.

Budget is roughly **five minutes**. It always exits 0: a non-zero exit fails the session, so every
problem is a `FAIL` line in the report rather than an abort.

## After the first boot — two things that are not optional

1. **Read the log.** The platform persists nothing of the script's stdout where a session can reach
   it. The script tees itself to `$HOME/.coordinator-cloud-setup.log`; that file is the only record
   of which path each phase took.
2. **Run the probes in `verify-in-session.md`.** Whether plugin-declared hooks fire in a cloud
   session is **still unverified**. Until a row in that file's results table is filled, treat cloud
   hook coverage as unknown-not-present — that is guards, not conveniences, and cloud sessions are
   the unattended ones.

## When the script re-runs

After the first run the filesystem is snapshotted and later sessions start from the snapshot,
skipping the script. It runs again only when **you change the setup script or the allowed network
hosts**, and at roughly **seven-day** cache expiry. Resuming an existing session never re-runs it.

The snapshot keeps what was written to disk and loses anything merely running: clones, installed
packages and files survive; a started database or `docker compose` stack does not.

**So editing `setup.sh` in this repo changes nothing about a live environment.** The paste is a
copy, not a link. Re-paste it into the dialog to pick up any change here.

## Known gap — doctrine does not yet reach non-authoring repos

`setup.sh` phase 3b installs fleet doctrine into the VM's `$HOME/.claude/` from the first of three
candidates it finds: the working repo's own `global-doctrine/`, a sibling checkout's, or the
published copy inside the plugin clone. **The third does not exist yet.** `git ls-tree
HEAD:templates` on `dbc-oduffy/coordinator-claude` has no `global-doctrine` entry — verified
2026-09-06 against a fresh clone of the mirror. The copy is committed on DoE `main` (`4f8a396db`)
and is waiting on a percolate publish.

Until that publish lands, a cloud session on a repo that does not itself carry `global-doctrine/`
takes the `FAIL` branch and **runs without fleet doctrine**. The session still gets the plugin and
the engine; what it lacks is the always-loaded conduct rules. Nothing in the environment
configuration fixes this — it is a publish, not a setting.

## Resource ceilings

4 vCPUs, 16 GB RAM, 30 GB disk, approximate and subject to change. Large builds and
memory-hungry test runs can be stopped by the VM.
