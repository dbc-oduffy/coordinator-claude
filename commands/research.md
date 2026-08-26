---
description: "PM-GATED, never from a subagent. Deep research — web, repo, or structured."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "--mode={web,repo,structured} <args> [--deepest]"
---

# Deep Research — Unified Entry Point

Single entry point for all deep-research pipelines. Route by `--mode`.

## Arguments

`$ARGUMENTS`:
- `--mode=web <topic>` — Pipeline A (internet research, Agent Teams)
- `--mode=repo <path> [--compare <path>] [--survey] [--deeper] [--deepest]` — Pipeline B (repo research, Agent Teams)
- `--mode=structured <spec-path> [subject-key]` — Pipeline C (structured research, Agent Teams); `create` sub-mode builds a new spec (see driver file Step 0)

<!-- engine-gap: field=research.resolved_mode producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
**Auto-detect (legacy, no `--mode`):** path that exists on disk → `--mode=repo`. Otherwise, a
repo-target candidate (GitHub URL, bare `<owner>/<repo>`, or a name resolvable via
`machine-local`) routes to `--mode=repo` only if it resolves via, in order: (1) `machine-local get
repos.<name>`, (2) `~/Documents/Code_Reference/<name>`, (3) opt-in shallow clone (never automatic).
Non-resolution falls back to `--mode=web`. Otherwise → `--mode=web`. `--mode=web` always overrides
auto-detection.

> The web pipeline caps at 5 topics — the ≤5 concurrent web-tool caller ceiling; exceeding it
> self-throttles indistinguishably from a platform gate. For more, `/spinoff` the question set
> into chunks across sessions rather than authoring an over-cap harness.

## Agent Teams Note

Teams form implicitly when the first teammate spawns (requires
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). No `TeamCreate` tool, no restart gate.

## Step 1: Parse Arguments

Parse `--mode`; if absent, apply auto-detect. Extract remaining arguments for the driver. For
`--mode=structured`, check for a leading `create` and run Create Mode (driver Step 0) first.

## Step 0: Run Identity

Runs after Step 1 despite the number — a universal pre-flight before mode-specific routing.

1. Generate run ID `YYYY-MM-DD-HHhMM` and a topic slug from the parsed topic/subject (repo mode:
   basename of `<repo-path>`; structured mode: `<subject-key>`).
2. Create the shared run workdir `docs/research/{run-id}-{topic-slug}-workdir`; bind it as
   `{scratch-dir}` and forward it to the driver (its Step 1 accept-if-passed clause uses it).

## Step 0.5: Prior-Art Pre-Flight

Always-on, all modes. Advisory/report-only — never blocking. Dispatch `prior-art-checker` as a
non-teammate `Agent` in research mode (`mode: research`, `research_question`, `scratch_dir`,
optional `peer_repos`) before fan-out. Read the sidecar it writes at
`{scratch-dir}/prior-art-check.md` (path per `coordinator/agents/prior-art-checker.md` § Sidecar
path (research mode)). If the "Existing corpus" bucket is non-empty, surface it to the operator
before spawning the team — options: read it and refine, proceed fresh, or abort. Sidecar absent,
or `prior-art-checker` unresolvable: log a one-liner and proceed to Step 2 — never abort.

## Step 2: Route to Driver

Read and follow the driver file for the parsed mode, passing through remaining arguments:

- `--mode=web` → `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/web-driver.md`
- `--mode=repo` → `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-driver.md`
- `--mode=structured` → `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/structured-driver.md`

The driver handles team creation, spawn, completion, archival.

## Post-Synthesis: Coverage Auditor

Always-on, all four pipelines, no opt-out. After synthesis, before the run concludes, dispatch
the coverage auditor (`agents/coverage-auditor.md`) as a non-teammate `Agent` — it answers "did
the synthesis carry the research?", writes a `-coverage-audit.md` sidecar, never the synthesis
path itself. Full depth→relay mapping (which pipelines also run a fidelity relay, Pipeline D's
MCP-extended/cleanup-deferred divergence): wiki (`deep-research-pipelines`).
