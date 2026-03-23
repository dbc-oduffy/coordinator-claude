---
description: Bootstrap or refresh the architecture atlas via a multi-phase agent pipeline (Haiku scouts → Sonnet analysts → Opus synthesizer)
allowed-tools: ["Agent", "Read", "Bash"]
argument-hint: "[--refresh]"
---

# Architecture Audit — Dispatch

**Do NOT read the pipeline doc yourself. Dispatch the `architecture-audit-orchestrator` agent.**

## Step 1: Parse Arguments

`$ARGUMENTS` may contain `--refresh`:
- **No `--refresh`, no atlas:** First run — full discovery
- **`--refresh`:** Refresh mode — identify churned systems, remap only those

Auto-detection: check for `tasks/architecture-atlas/systems-index.md`. If it exists and `--refresh` wasn't passed, ask the PM: "Atlas already exists. Did you mean `--refresh`?"

## Step 2: Announce

"I'm running `/architecture-audit` to [bootstrap / refresh] the architecture atlas."

## Step 3: Dispatch Orchestrator

Dispatch an **`architecture-audit-orchestrator`** agent (`subagent_type: "coordinator:architecture-audit-orchestrator"`, `run_in_background: true`).

The dispatch prompt needs only:
- **Mode:** BOOTSTRAP or REFRESH
- **Working directory:** current working directory
- **Atlas location:** `tasks/architecture-atlas/`

The agent reads the pipeline doc from disk. Do NOT paste it into the dispatch prompt.

## Step 4: Return Control

After dispatching, tell the PM:
"Architecture audit orchestrator dispatched [bootstrap/refresh mode]. It will inventory → analyze → synthesize autonomously. I'll present the updated atlas when it completes."

**Do NOT wait, poll, or drive phases from this context.**
