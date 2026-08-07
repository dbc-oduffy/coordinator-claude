# coordinator-claude — Agent Entry Point

> **You are an AI agent reading this file.** A human pointed you at this repo. Your job is to install the coordinator-claude plugin into their Claude Code environment — not just run a script, but follow the full playbook so the install is verified and the post-restart continuation is staged correctly.
>
> **This is a two-leg install, and both legs are yours.** coordinator-claude is the doctrine; the coordinator engine (`claude-klabauter`) is a **hard co-requisite** that most state-mutating flows fail without. Leg 2 is described in [§ Leg 2: the engine](#leg-2-the-engine-a-hard-co-requisite) below. An install that stops after leg 1 is incomplete — do not report it as done.

## Start here: the install playbook

<!-- The link below is repo-published-layout-relative: in the published coordinator-claude repo
     AGENTS.md sits at the root and agent-install.md at docs/, so it resolves for the OSS user. In
     the source/dev tree these live under dist/publish-repo-toplevel/ and dist/publish-repo-docs/,
     so run doc-link-checker against the PUBLISHED layout, not the dev tree (where it false-positives). -->
Read and follow **[`docs/agent-install.md`](docs/agent-install.md)** — that is the authoritative, step-by-step playbook written for you.

It tells you:
- What you are installing and why the order of steps matters
- The recommended path — the native `claude plugin` CLI (`claude plugin marketplace add dbc-oduffy/coordinator-claude` + `claude plugin install coordinator@coordinator-claude`, registering the public GitHub repo so the install is self-contained under `~/.claude`) — and what it does
- How to validate the result
- What to tell the user before they restart Claude Code
- The one command to run after the restart — `/coordinator:install` in a fresh session (it finishes the environment wiring; no `/pickup` baton)
- Step 4 — installing the required engine, `claude-klabauter`, from its own public repo, **after** the restart and `/coordinator:setup`, never before

## Why this file exists

`AGENTS.md` is a cross-tool convention filename that agents look for unprompted when they land in a repo. It means you can find the right entry point even when the human never pasted a one-liner — just navigate here, then to `docs/agent-install.md`.

## What you must NOT do

- Do not improvise the install steps from memory or inference — the playbook handles platform-specific traps (path translation, JSON-merge edge cases, the Windows Python App Execution Alias stub) that you will get wrong without it.
- Do not skip the validation pass after install — an install that looks done but isn't validated will fail silently at SessionStart hooks.
- Do not skip the restart — plugin/marketplace registration and the Agent Teams env var need a fresh session. The post-restart step is `/coordinator:install` (it finishes the environment wiring and records its own completion receipt — there is no `/pickup` baton in the CLI-install flow).
- Do not skip leg 2, and do not present leg 1 alone as the whole job — see below.

## Leg 2: the engine (a hard co-requisite)

coordinator-claude has one hard dependency: the engine, published as `claude-klabauter` at
[`https://github.com/dbc-oduffy/claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter).
**You install this yourself, as the agent** — clone that repo and run
`python3 <klabauter-clone>/scripts/setup.py --i-am-agent` (the non-interactive agent path), then verify with
`python3 <klabauter-clone>/scripts/setup.py --check`. `pip install .` is NOT the engine install — do not use it.

Do this **only after** the restart and `/coordinator:setup` complete Step 3 of the playbook; run
it earlier and the engine's dependency check exits 127 (`resolver not installed`) because
coordinator-claude's `machine-local` forwarder has no resolver yet.

Windows: `python <klabauter-clone>\scripts\setup.py` with the same flags, and disable the Python App Execution Alias
stubs first (Settings › Apps › App execution aliases › turn off `python`/`python3`) — left on,
every diagnostic afterwards misleads. Python 3.11+ is required.

Two more things not to get wrong: the engine is **not a plugin** and ships no skills or commands
surface, so never attempt `claude plugin install` for it; and its installer **fails loud** when
coordinator-claude is absent, so do not reach for the documented degraded override pair
(`--skip-dep-check --accept-missing-deps-risk`, both together or neither) just to clear an error.
Read the engine repo's own `INSTALL.md` and `AGENTS.md` rather than improvising past them.

Until the engine is installed, every pure-prompt flow (planning, review, personas, shaping) still
works; the state machine (claiming handoffs, memo resolution, coverage computation, terminal
stamping) does not. **The safety guards also live there now** — a doctrine-only install has no
destructive-`rm` guard, no destructive-git guard and no `--no-verify` block, because those hooks
moved into the engine. Say all of this plainly; do not present the install as complete without both
legs done.

Follow the playbook. Then report back to the human.
