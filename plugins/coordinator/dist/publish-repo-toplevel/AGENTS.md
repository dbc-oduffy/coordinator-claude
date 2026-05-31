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
- The recommended path (run `setup/install.sh`) and what it does
- How to validate the result
- What to tell the user before they restart Claude Code
- The one command to resume after the restart — `/pickup tasks/handoffs/continue-onboarding-and-installation.md` in a fresh session

## Why this file exists

`AGENTS.md` is a cross-tool convention filename that agents look for unprompted when they land in a repo. It means you can find the right entry point even when the human never pasted a one-liner — just navigate here, then to `docs/agent-install.md`.

## What you must NOT do

- Do not improvise the install steps from memory or inference — the playbook handles platform-specific traps (path translation, JSON-merge edge cases, bash version checks) that you will get wrong without it.
- Do not skip the validation pass after install — an install that looks done but isn't validated will fail silently at session-start hooks.
- Do not skip the restart — plugin/marketplace registration and the Agent Teams env var need a fresh session. The playbook stages a continue-onboarding handoff; the post-restart step is `/pickup tasks/handoffs/continue-onboarding-and-installation.md`.

Follow the playbook. Then report back to the human.
