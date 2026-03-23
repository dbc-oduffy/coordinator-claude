---
description: Systematic codebase bug hunt — find and fix all AI-fixable bugs in-session, defer blocked ones to backlog
allowed-tools: ["Agent", "Read", "Bash"]
argument-hint: "[path]"
---

# Bug Sweep — Dispatch

**Do NOT read the pipeline doc yourself. Dispatch the `bug-sweep-orchestrator` agent.**

## Step 1: Parse Arguments

`$ARGUMENTS` is an optional path to scope the sweep. If omitted, the full codebase is scanned.

## Step 2: Announce

"I'm running `/bug-sweep` — systematic bug hunt [scoped to X / across the full codebase]."

## Step 3: Dispatch Orchestrator

Dispatch a **`bug-sweep-orchestrator`** agent (`subagent_type: "coordinator:bug-sweep-orchestrator"`, `run_in_background: true`).

The dispatch prompt needs only:
- **Scope:** path to scan, or "full codebase"
- **Working directory:** current working directory

The agent reads the pipeline doc from disk. Do NOT paste it into the dispatch prompt.

## Step 4: Return Control

After dispatching, tell the PM:
"Bug sweep orchestrator dispatched [full codebase / scoped to X]. It will scan → analyze → triage → fix autonomously. I'll present findings when it completes."

**Do NOT wait, poll, or drive phases from this context.**
