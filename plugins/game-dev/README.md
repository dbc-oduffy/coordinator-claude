# game-dev

Game development domain plugin for the Donal + Claude agent hierarchy. Enable for Unreal Engine and game development projects.

## Components

**Agents:**
- staff-game-dev (Opus) — UE5 specialist, game systems architect, code reviewer
- ue-blueprint-inspector (Opus) — Blueprint documentation coordinator, dispatches Sonnet workers for large projects
- ue-blueprint-worker (Sonnet) — mechanical per-BP inspection via MCP, dispatched by the inspector coordinator

**MCP Servers:** holodeck-docs (UE documentation RAG), holodeck-control (UE Editor integration) — managed by the holodeck repo, configured globally in `~/.claude/settings.json`

**Routing:** Registers Sid for game dev signals with Patrik (coordinator) as backstop. Architecture and review route to Sid (Opus).

## Source of Truth

This plugin lives in [coordinator-claude](https://github.com/oduffy-delphi/coordinator-claude) at `plugins/game-dev/`.

## Authors

Donal O'Duffy & Claude
