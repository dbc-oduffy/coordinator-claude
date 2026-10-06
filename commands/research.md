---
name: research
description: "PM-GATED, never from a subagent. Deep research — web, repo, or structured."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "Workflow"]
argument-hint: "--mode={web,repo,structured} <args> [--deepest]"
---

# Deep Research — Unified Entry Point

Single entry point for all deep-research pipelines. Route by `--mode`.

## Arguments

`$ARGUMENTS`:
- `--mode=web <topic>` — Pipeline A (internet research, chatty Workflow)
- `--mode=repo <path> [--compare <path>] [--survey] [--deeper] [--deepest]` — Pipeline B (repo research, chatty Workflow)
- `--mode=structured <spec-path> [subject-key]` — Pipeline C (structured research, chatty Workflow); `create` sub-mode builds a new spec (see driver file Step 0)

<!-- engine-gap: field=research.resolved_mode producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->
**Auto-detect (legacy, no `--mode`):** path that exists on disk → `--mode=repo`. Otherwise, a
repo-target candidate (GitHub URL, bare `<owner>/<repo>`, or a name resolvable via
`machine-local`) routes to `--mode=repo` only if it resolves via, in order: (1) `machine-local get
repos.<name>`, (2) `~/Documents/Code_Reference/<name>`, (3) opt-in shallow clone (never automatic).
Non-resolution falls back to `--mode=web`. Otherwise → `--mode=web`. `--mode=web` always overrides
auto-detection.

## Chatty Workflow

Every pipeline runs as ONE background `Workflow` the EM fires after scoping; the EM is then freed
and completion is the Workflow's task notification. The script runs the stages in `await` order
(`parallel()` for a fan-out). Workers never `SendMessage` each other or the EM: peer exchange goes
through mailbox files (`{workdir}/mail/<role>.jsonl`), challenge rounds are continuation
dispatches, and only the overseer's return value reaches the EM. Doctrine:
`coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md`. No feature flag gates it.

## Step 1: Parse Arguments

Parse `--mode`; if absent, apply auto-detect. Extract remaining arguments for the driver. For
`--mode=structured`, check for a leading `create` and run Create Mode (driver Step 0) first.

## Step 2: Run Identity

A universal pre-flight before mode-specific routing. Run ID format: `YYYY-MM-DD-HHhMM`. Topic
slug: repo mode uses the basename of `<repo-path>`; structured mode uses `<subject-key>`. Shared
run workdir: `docs/research/{run-id}-{topic-slug}-workdir`, bound as `{scratch-dir}` — the driver's
Step 1 accept-if-passed clause consumes that binding.

## Step 3: Prior-Art Pre-Flight

Always-on, all modes. Advisory/report-only — never blocking. Dispatch `prior-art-checker` as a
plain `Agent` in research mode (`mode: research`, `research_question`, `scratch_dir`,
optional `peer_repos`) before fan-out. Read the sidecar it writes at
`{scratch-dir}/prior-art-check.md` (path per `coordinator/agents/prior-art-checker.md` § Sidecar
path (research mode)). If the "Existing corpus" bucket is non-empty, surface it to the operator
before firing the Workflow — options: read it and refine, proceed fresh, or abort. Sidecar absent,
or `prior-art-checker` unresolvable: log a one-liner and proceed to Step 4 — never abort.

## Step 4: Route to Driver

Read and follow the driver file for the parsed mode, passing through remaining arguments:

- `--mode=web` → `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/web-driver.md`
- `--mode=repo` → `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-driver.md`
- `--mode=structured` → `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/structured-driver.md`

The driver handles script preparation, firing, completion, archival.

## Post-Synthesis: Coverage Auditor

Always-on, all four pipelines, no opt-out. After synthesis, before the run concludes, dispatch
the coverage auditor (`agents/coverage-auditor.md`) as a plain `Agent` — it answers "did
the synthesis carry the research?", writes a `-coverage-audit.md` sidecar, never the synthesis
path itself. Full depth→relay mapping (which pipelines also run a fidelity relay, Pipeline D's
MCP-extended/cleanup-deferred divergence): wiki (`deep-research-pipelines`).
