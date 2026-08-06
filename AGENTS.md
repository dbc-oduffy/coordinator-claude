# coordinator-claude — Agent Entry Point

> **You are an AI agent reading this file.** A human pointed you at this repo. Your job is to install the coordinator-claude plugin into their Claude Code environment — not just run a script, but follow the full playbook so the install is verified and the post-restart continuation is staged correctly.

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

## Why this file exists

`AGENTS.md` is a cross-tool convention filename that agents look for unprompted when they land in a repo. It means you can find the right entry point even when the human never pasted a one-liner — just navigate here, then to `docs/agent-install.md`.

## What you must NOT do

- Do not improvise the install steps from memory or inference — the playbook handles platform-specific traps (path translation, JSON-merge edge cases, bash version checks) that you will get wrong without it.
- Do not skip the validation pass after install — an install that looks done but isn't validated will fail silently at SessionStart hooks.
- Do not skip the restart — plugin/marketplace registration and the Agent Teams env var need a fresh session. The post-restart step is `/coordinator:install` (it finishes the environment wiring and records its own completion receipt — there is no `/pickup` baton in the CLI-install flow).
- Do not skip mentioning the coordinator engine dependency, and do not tell the human to clone it. coordinator-claude has one hard dependency — the coordinator engine, published as `claude-klabauter` — that this install does not provide. **That publish is not yet live**; until it is, the engine is available on request from the maintainer. This plugin install still gives you every pure-prompt flow (planning, review, personas, shaping); only the state machine (claiming handoffs, memo resolution, coverage computation, terminal stamping) needs the engine. Say so plainly; do not present the install as complete without naming this gap.

Follow the playbook. Then report back to the human.
