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

## Post-Synthesis: Coverage Auditor (all pipelines)

After the synthesis is complete and before archive/TeamDelete, the EM dispatches the **coverage auditor** (`agents/coverage-auditor.md`) as a **non-teammate Agent**. This is always-on across all four pipelines — no size floor, no opt-out.

The coverage auditor answers: *"Did the synthesis carry the research?"* It emits a `-coverage-audit.md` sidecar. It never writes the synthesis output path. Canonical pattern: `coordinator/docs/wiki/independent-coverage-auditor-pattern.md`.

**Depth→relay mapping by pipeline** (governs whether a fidelity relay also runs, in addition to the auditor):

| Pipeline | Coverage Auditor | Fidelity Relay | Relay trigger |
|---|---|---|---|
| A (web) | Always-on | Yes — Team-1 internal sweep phase, before Step 6 TeamDelete | Gap-report / deepening-threshold signal |
| B (repo) | Always-on | Yes — Team-1 internal sweep phase | `--deepest` flag only |
| C (structured) | Reduced (drop-annotation check against `synthesis-annotations.md`) | OOS — no prose synthesis to distort; CONTESTED pre-empts | N/A |
| D (notebooklm) | Always-on (**documented divergence:** D auditor additionally carries notebooklm MCP tools + cleanup-deferred ordering; degrades to claims-only if MCP unavailable) | OOS — no depth tier; structurally cannot gate | N/A — revisit if D gains depth concept |

**Pipeline D boundaries** (documented divergence from the unified auditor):
- D auditor carries notebooklm MCP tools (`notebook_query` at minimum) with graduated bootstrap (exact names → keyword fallback → graceful-skip); degrades to `{letter}-claims.json`-only with explicit sidecar note if MCP unavailable.
- D notebook cleanup (`--cleanup`) is deferred until AFTER the D auditor completes — notebook deletion must not run before the sidecar is written. Wire at `notebooklm/commands/notebooklm-research.md` Step 6: run auditor first, then delete notebooks.
- Relay is OOS for D until D gains a depth concept (architectural boundary, not an appetite call).

See `agents/coverage-auditor.md` for the full auditor spec (input universe, sidecar format, MCP bootstrap, D-specific divergences). See `coordinator/docs/wiki/independent-coverage-auditor-pattern.md` for the canonical pattern with both named instantiations (deep-research + coordinator comprehensiveness-auditor-DRAFT).
