<!-- GENERATED FILE: do not edit. -->

# Installing coordinator-claude

Written for the agent installing this repo (see `AGENTS.md`, this file's sibling at the repo
root, for the entry point) — a human reads it too. Follow the document for the agent type doing
the install; each is a **two-leg install, and both legs are yours**: coordinator-claude is the
doctrine; the coordinator engine (`claude-klabauter`) is a **hard co-requisite** most
state-mutating flows fail without. An install that stops after leg 1 is incomplete — do not
report it as done.

**First-time install:** read Requirements in your host playbook, then Step 1 to acquire the
sources. Run the environment and engine scripts before activation; restart only after both
succeed, then run the default setup verifier. Existing installs start with Step 0's `--plan`.

## Pick your agent

- [Installing coordinator-claude with Claude Code](install/claude-code.md)
- [Installing coordinator-claude with Codex](install/codex.md)
- [Installing coordinator-claude with agy (Gemini / Antigravity)](install/agy.md)
- [Installing coordinator-claude with Grok](install/grok.md)
