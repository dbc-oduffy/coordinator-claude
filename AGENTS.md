# coordinator-claude — Agent Entry Point

> **You are an AI agent reading this file.** A human pointed you at this repo. Your job is to install the coordinator-claude plugin into their agent environment — not just run a script, but follow the full playbook so the install is verified and the post-restart continuation is staged correctly.
>
> **This is a two-leg install, and both legs are yours.** coordinator-claude is the doctrine; the coordinator engine (`claude-klabauter`) is a **hard co-requisite** that most state-mutating flows fail without. Leg 2 is described in [§ Leg 2: the engine](#leg-2-the-engine-a-hard-co-requisite) below. An install that stops after leg 1 is incomplete — do not report it as done.

## Start here: the install playbook

Read **`INSTALL.md`** — the root sibling of this file — then follow the per-agent playbook it
links for the agent type you are. The route is by agent type; do not run another agent's commands.

| You are | Follow |
|---|---|
| Claude Code | [`install/claude-code.md`](install/claude-code.md) |
| Codex | [`install/codex.md`](install/codex.md) |
| agy (Gemini / Antigravity) | [`install/agy.md`](install/agy.md) |
| Grok | [`install/grok.md`](install/grok.md) |

The native `claude plugin` CLI path (`claude plugin marketplace add dbc-oduffy/coordinator-claude` +
`claude plugin install coordinator@coordinator-claude`) is the Claude Code route only; it lives in
`install/claude-code.md`, not here.

The playbook for your agent type tells you:
- What you are installing and why the order of steps matters
- How to validate the result
- What to tell the user before they restart
- The activation and restart steps, followed by setup verification, for your agent type
- The engine step — installing the required engine, `claude-klabauter`, from its own public repo, at the point your agent's playbook places it (step ordering is per host; follow `install/<agent>.md`, never another host's order)

## Why this file exists

`AGENTS.md` is a cross-tool convention filename that agents look for unprompted when they land in a repo. It means you can find the right entry point even when the human never pasted a one-liner — just navigate here, then to `INSTALL.md`.

## What you must NOT do

- Do not improvise the install steps from memory or inference — the playbook handles platform-specific traps (path translation, JSON-merge edge cases, the Windows Python App Execution Alias stub) that you will get wrong without it.
- Do not skip the validation pass after install — an install that looks done but isn't validated will fail silently at SessionStart hooks.
- Do not skip the activation or restart your agent's playbook names — registration needs a fresh session. Follow `install/<agent>.md` for the continuation.
- Do not skip leg 2, and do not present leg 1 alone as the whole job — see below.

## Leg 2: the engine (a hard co-requisite)

coordinator-claude has one hard dependency: the engine, published as `claude-klabauter` at
[`https://github.com/dbc-oduffy/claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter).
**You install this yourself, as the agent** — clone that repo and run
`python3 <klabauter-clone>/scripts/setup.py --i-am-agent` (the non-interactive agent path), then verify with
`python3 <klabauter-clone>/scripts/setup.py --check`. `pip install .` is NOT the engine install — do not use it.

Step ordering belongs to each host's generated playbook, `install/<agent>.md`; follow your host's
order and its prerequisite checks. `/coordinator:setup` verifies the installed environment and
engine; it is not a prerequisite for installing the engine. A `resolver not installed` failure
requires the playbook's substrate remedy, rather than setup verification of an absent engine.

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
