---
title: Agent Dispatch Economics
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Agent Dispatch Economics

> When to dispatch a sub-agent vs. do work EM-inline. This is a real economic call, not a default-to-delegate rule.

## Overview

Sub-agent dispatch has fixed costs: worktree creation on large repos, prompt-bootstrap tokens, and context-loading time for the sub-agent's system prompt re-read. These costs are non-trivial. For sub-30-second mechanical fixes on a >10k-file repo, EM-inline beats per-item executor dispatch on both wall-clock time and token spend.

Surfaced empirically when Claude Code 2.1.141 introduced `isolation: "worktree"` as the default dispatch mode. On a 58k-file repo (project-rag-ue-addon, 2026-05-15), each dispatch added 30–60s of worktree creation overhead before the sub-agent's first tool call. A rename that takes the EM 20 seconds of typing became a 90-second round-trip when dispatched.

## The Economics

| Repo size | Worktree creation | Dispatch fixed cost | EM-inline cost |
|---|---|---|---|
| <5k files | <1s | ~3s overhead | typing + read tokens |
| 10k–30k files | 5–15s | 8–20s overhead | typing + read tokens |
| 30k–60k files | 30–60s | 35–65s overhead | typing + read tokens |
| 60k+ files | 60s+ | 65s+ overhead | typing + read tokens |

For a fix that takes the EM 30 seconds on a known-locus file, dispatching a 60s-worktree executor doubles the wall-clock cost and adds tokens for the sub-agent's read-then-edit-then-report cycle. The sub-agent provides no judgment value on mechanical work; the overhead is pure waste.

## When to Dispatch

- **Work is independently verifiable.** A scout returns a structured deliverable the EM reads; concurrency is real leverage.
- **Work spans contexts the EM hasn't loaded.** Sub-agent loads a directory's worth of code the EM doesn't need to hold in its own context window.
- **Work is parallel-shaped.** N independent edits to N different files; sequential EM would gate each behind the last.
- **Work needs persona judgment.** Patrik / Sid / Camelia / Fru bring framing, calibration, and review lens the EM doesn't have.
- **Work would blow EM context.** Reading 50k tokens of code to make a small edit is sub-agent shape — the sub-agent reads, acts, and reports a summary.
- **Work is long-running and the EM needs to continue.** Background dispatch with disk-based signaling lets the EM make progress while the sub-agent works.

## When to EM-Inline

- **Fix locus is known and ≤3 files.** No exploration needed; no value in delegation.
- **Estimated EM wall-clock is <60s on a >30k-file repo.** Worktree creation alone exceeds the work duration.
- **Fix is mechanical** — rename, version bump, single-line tweak, import addition. Judgment value is zero; overhead is not.
- **Sub-agent would just re-read what the EM has already loaded.** If the relevant context is already in the EM's window, dispatch adds a re-read cycle for no gain.
- **Fix is in a file the EM is already editing.** Mid-edit dispatch mid-session creates a concurrent-edit hazard on the same file.

## Heuristic

> Dispatch when the sub-agent brings something the EM doesn't have: context, concurrency, judgment, or isolation from a large read. EM-inline when the fix is small and the locus is already known.

A useful smell test: if the EM's dispatch prompt would be "read file X, change line Y, report back" — and the EM already has file X in context — the dispatch is overhead theater, not delegation.

## Mitigation for the Worktree Default

Anthropic CLI v2.1.141 ships no opt-out for `isolation: "worktree"`. Per-agent worktrees on large repos accumulate creation cost and leave orphaned worktree directories if sub-agents crash or timeout.

Mitigations:

- **`bin/agent-worktree-sweep.sh`** — reaps orphan worktrees. Wired into `/workday-start` Step 0.6 and `/session-start` warn-detect.
- **`disableAgentView: true` in settings.json** — nuclear option; disables agent telemetry alongside worktree creation. Use only if worktree overhead is untenable and sweep is insufficient.
- **File upstream.** Issue #58597 is open as a request for a `defaultIsolation` settings key that would allow per-project opt-down to `isolation: "none"` for large repos.
- **Coordinator-side dispatch throttling.** On repos confirmed >30k files, prefer batching mechanical fixes into a single executor pass over N individual dispatches. One worktree creation + N edits beats N worktree creations.

## Cluster Execution — Full Ceremony on the Novel Item, Direct Dispatch on the Rest

*2026-05-17, coordinator-claude.* When a cluster of related fixes shares a single architectural shape (one novel pattern + N surgical follow-ups that mirror it), front-load the review ceremony on the novel item and direct-dispatch the surgical follow-ups against the established pattern. Full plan-review + prior-art-check + post-impl code-review on every cluster member is ceremony inflation — the second through Nth instances re-verify the same pattern with diminishing return.

**Rule:**
- **Item 1 (the novel one):** full ceremony — plan, prior-art-check, Patrik, post-impl review.
- **Items 2..N (surgical follow-ups of the same shape):** direct executor dispatch with the item-1 spec as reference. EM spot-check post-commit.

Tell for cluster shape: each item edits a different file, the *shape* of the edit is the same, and the only judgment in items 2..N is "apply the item-1 pattern to this file's specifics." When you find yourself drafting the same plan body N times with the file path changed, that's the tell — promote item 1 to canonical and direct-dispatch the rest.

## Related

- → `docs/wiki/dispatching-parallel-agents.md` — when parallel-shape is appropriate
- → `docs/wiki/delegate-execution.md` — EM-vs-executor altitude
- → `bin/agent-worktree-sweep.sh` — sweep mechanics
- Anthropic issue #58597 — settings.json `defaultIsolation` key proposal
