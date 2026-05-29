---
title: Holodeck legacy migration notes
audience: operators (and their agents)
authored: 2026-05-16
related_plan: docs/plans/2026-05-16-w2b-install-holodeck-state-routing.md
pm_ruling: 2026-05-16 (Q2)
---

# Holodeck legacy migration notes

This wiki entry exists for one purpose: tell an operator (or their agent) what to do if they have a pre-PR-15 `mcpServers["holodeck-docs"]` entry in `~/.claude.json`.

## Background

Before the multi-rag-coexistence cutover (shipped 2026-05-08, three-repo split finalized 2026-05-14), holodeck registered a dedicated `holodeck-docs` MCP server. That server was **deregistered** as part of PR-15 — UE documentation lookups now flow through `mcp__project-rag__project_semantic_search` against the engine corpus served by the project-rag stack (with the `project-rag-ue-addon` producer responsible for engine-corpus build + release).

The legacy registration is **dead** — no code on the holodeck side reads it, no doctor probe asserts on it, no installer rewrites it. It sits in `~/.claude.json` doing nothing.

## What `/holodeck:setup` does about it

**Nothing automatic.** Per PM Q1/Q2 ruling 2026-05-16 (recorded in [`archive/specs/2026-05-16-w2b-install-holodeck-state-routing.md §3`](../../archive/specs/2026-05-16-w2b-install-holodeck-state-routing.md)):

> "Cleanup from legacy doesn't need to be permanently in the doctor routine — tell users about it."

The runtime verdict system (`scripts/_setup_routing.py`) does NOT detect-and-migrate. It has three verdicts: `install`, `update`, `install_reregister`. The Phase -1 probe table in `plugin/holodeck/commands/setup.md` carries a 5th row that surfaces an **informational** one-line operator note pointing here when the legacy key is present, but the probe **does not change the verdict**.

This is deliberate. Automated migration of a key the operator hand-edited (or that survived a partial cleanup) risks clobbering operator state the holodeck team can't reason about. The operator (or their agent) is the right authority for this cleanup.

## What an operator should do

1. **Confirm the entry is present.** Open `~/.claude.json` (or `%USERPROFILE%\.claude.json` on Windows) and look for a `mcpServers.holodeck-docs` key.

2. **Delete the entry.** Remove the entire `holodeck-docs` block from the `mcpServers` object. The surrounding JSON structure stays intact.

   ```jsonc
   {
     "mcpServers": {
       "holodeck-control": { ... },
       "holodeck-docs": { ... },   // ← delete this entry
       "project-rag": { ... }
     }
   }
   ```

3. **Restart Claude Code** so the MCP server list re-reads.

4. **Run `/holodeck:setup`** to verify the new state. The Phase -1 probe will no longer surface the legacy-migration note.

## What an agent should do

If the agent is operating on the operator's behalf and the Phase -1 probe surfaced the legacy-migration note:

1. Read this wiki entry.
2. Walk the operator through the four-step manual procedure above. Do NOT mutate `~/.claude.json` autonomously — that file is operator-authority territory per holodeck-doctrine §5.
3. After the operator confirms deletion, re-run `/holodeck:setup` and verify the verdict path matches expectations.

## Why not automate it?

Three reasons (recorded for future EMs considering reversing this ruling):

1. **`~/.claude.json` is operator state.** Even a "safe" rewrite that only removes one key can collide with concurrent edits from other Claude Code sessions or non-Anthropic tooling that uses the same config file.

2. **The cleanup is one-shot per machine.** A doctor probe that runs on every `/holodeck:setup` invocation is overhead for a problem the operator hits at most once. Operator docs are the right shape.

3. **The deregistration was upstream.** PR-15 removed `holodeck-docs` because UE doc lookups moved to the project-rag engine corpus. The migration story belongs in the multi-rag-coexistence narrative, not in holodeck's runtime.

## Related

- Multi-rag-coexistence migration: [`docs/wiki/migration-holodeck-docs-deregistration.md`](migration-holodeck-docs-deregistration.md)
- Holodeck doctrine §5 (read-`~/.claude.json` prohibitions and exemptions): [`docs/wiki/holodeck-doctrine.md`](holodeck-doctrine.md)
- W2b plan: [`archive/specs/2026-05-16-w2b-install-holodeck-state-routing.md`](../../archive/specs/2026-05-16-w2b-install-holodeck-state-routing.md)
