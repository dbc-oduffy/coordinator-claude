---
description: "PM-GATED: ask first; never from subagent. Deep research — web/repo/structured. Triggers: deep research, research the repo, structured research campaign."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "--mode={web,repo,structured} <args> [--deepest]"
---

# Deep Research — Unified Entry Point

This is the single entry point for all deep-research pipelines. Route by `--mode`.

## Arguments

`$ARGUMENTS`:
- `--mode=web <topic>` — Pipeline A (internet research, Agent Teams)
- `--mode=repo <path> [--compare <path>] [--survey] [--deeper] [--deepest]` — Pipeline B (repo research, Agent Teams)
- `--mode=structured <spec-path> [subject-key]` — Pipeline C (structured research, Agent Teams); use `create` sub-mode to build a new spec (see below)

**Auto-detect (legacy):** if `--mode` is absent, the first argument is used:
- path that exists on disk → `--mode=repo`
- otherwise → `--mode=web`

## Step 1: Parse Arguments

Parse `--mode` from `$ARGUMENTS`. If absent, apply auto-detect. Extract remaining arguments to pass through to the driver.

For `--mode=structured`, check whether remaining arguments start with `create` — if so, run Create Mode (see driver file Step 0) before the normal dispatch.

## Step 2: Route to Driver

Read the appropriate driver file and follow its steps, passing through all remaining arguments:

- **`--mode=web`:** Read `${CLAUDE_PLUGIN_ROOT}/pipelines/web-driver.md` and follow all steps exactly
- **`--mode=repo`:** Read `${CLAUDE_PLUGIN_ROOT}/pipelines/repo-driver.md` and follow all steps exactly
- **`--mode=structured`:** Read `${CLAUDE_PLUGIN_ROOT}/pipelines/structured-driver.md` and follow all steps exactly

The driver handles everything from here — team creation, spawn, completion, archival.

## Migration note

The former `/web`, `/repo`, and `/structured` slash-commands have been removed. Use `--mode=web`, `--mode=repo`, `--mode=structured` respectively. The former coordinator-side create-spec invocation is now `/research --mode=structured create <output-dir>`.
