---
title: Agent Dispatch Economics
status: active
kind: doctrine-wiki
created: 2026-05-18
---

# Agent Dispatch Economics

> When to dispatch a sub-agent vs. do work EM-inline. Default: dispatch for any non-trivial job; fan out when the job decomposes. EM-inline is the carve-out, not the default.

<!-- spec-backlink: docs/plans/2026-05-27-fan-out-default-doctrine.md § Chunk 3 — § Overview and § The Economics reanchored wall-clock-first per AC5. -->

## Overview

**Wall-clock is the primary objective. Token cost and worktree overhead are subordinate.**

Sub-agent dispatch has fixed costs: worktree creation on large repos, prompt-bootstrap tokens, and context-loading time for the sub-agent's system prompt re-read. These costs are real and are worth accounting for on sub-60s mechanical fixes where worktree creation alone would exceed the work duration. Outside that narrow carve-out, the default is to dispatch — and when the work decomposes into independent chunks, to fan out across N agents.

Surfaced empirically when Claude Code 2.1.141 introduced `isolation: "worktree"` as the default dispatch mode. On a 58k-file repo (project-rag-ue-addon, 2026-05-15), each dispatch added 30–60s of worktree creation overhead before the sub-agent's first tool call. A rename that takes the EM 20 seconds of typing became a 90-second round-trip when dispatched. The lesson from that data point is that **sub-60s mechanical fixes on known loci warrant EM-inline** — not that dispatch is expensive in general.

Empirical antecedent (2026-05-20, `tasks/lessons.md`): *"Many agents often beat one — don't overload a single Sonnet when the work decomposes [universal]."* A cross-repo slow-test sweep dispatched as one agent grinding ~10 independent chunks crashed at 35 min / 43 tool uses; only 1 of 10 deliverables landed. The correct shape was N parallel agents at the natural decomposition unit. Independent chunks have zero cross-chunk data dependency; coordination cost is zero; wall-clock is N× faster; failure blast-radius is contained per-chunk; the PM gets partial results immediately as each agent lands.

<!-- negative-spec: The co-equal cost framing ("token + worktree overhead as co-equal with wall-clock") that appeared in the 2026-05-18 draft of this file was incorrect as a general rule. It is valid only for sub-60s mechanical fixes on known loci. The § Overview previously read "This is a real economic call, not a default-to-delegate rule" — that framing caused over-application as cover for under-dispatching genuinely large jobs. Reanchored 2026-05-27. -->

**Anti-monolith HARD RULE** (see `em-operating-model.md` HARD RULES and `coordinator/CLAUDE.md` § Subagent Dispatch): a large job is fanned out, or chunked into a sequence of fresh per-chunk agents — never one agent grinding chunk after chunk. To fan out, run `fan-out-dispatch.sh` (overlap pass + scoped-prompt compiler), then follow the fan-out methodology (`dispatching-parallel-agents.md` § Executing a Fan-Out Wave) to dispatch the compiled wave via `Agent` (which a bin script cannot call directly) and hold the EM-serial commit.

## The Economics

Wall-clock cost is the primary axis. Token and worktree overhead are subordinate — they matter only when worktree creation alone would dominate the work being done.

| Repo size | Worktree creation | Dispatch fixed cost | EM-inline cost |
|---|---|---|---|
| <5k files | <1s | ~3s overhead | typing + read tokens |
| 10k–30k files | 5–15s | 8–20s overhead | typing + read tokens |
| 30k–60k files | 30–60s | 35–65s overhead | typing + read tokens |
| 60k+ files | 60s+ | 65s+ overhead | typing + read tokens |

**Reading the table correctly:** the overhead column is a brake on dispatch *only for work that fits entirely within the worktree-creation time window*. A fix the EM can type in 20s on a 30k-file repo is legitimately EM-inline — dispatching it doubles wall-clock. A multi-file refactor that takes an executor 5 minutes is still a dispatch regardless of worktree cost: 5 min + 60s overhead vs. EM-inline serial is not a close call, and the EM keeps its context window for other work in parallel.

**When the job decomposes:** N parallel executors at the natural chunk boundary beat one executor grinding serially on wall-clock *every time*, for any N ≥ 2 with independent chunks. The worktree overhead is paid once per chunk, not once per job; the wall-clock gain from parallelism dwarfs the overhead for any non-trivial chunk size.

## When to Dispatch

- **Work is independently verifiable.** A scout returns a structured deliverable the EM reads; concurrency is real leverage.
- **Work spans contexts the EM hasn't loaded.** Sub-agent loads a directory's worth of code the EM doesn't need to hold in its own context window.
- **Work is parallel-shaped.** N independent edits to N different files; sequential EM would gate each behind the last.
- **Work needs persona judgment.** Patrik / Sid / Camelia / Fru bring framing, calibration, and review lens the EM doesn't have.
- **Work would blow EM context.** Reading 50k tokens of code to make a small edit is sub-agent shape — the sub-agent reads, acts, and reports a summary.
- **Work is long-running and the EM needs to continue.** Background dispatch with disk-based signaling lets the EM make progress while the sub-agent works.
- **Work decomposes into ≥2 independent chunks.** Fan out — don't hand a multi-chunk job to one agent. See anti-monolith HARD RULE above.

## When to EM-Inline

- **Fix locus is known and ≤3 files.** No exploration needed; no value in delegation.
- **Estimated EM wall-clock is <60s on a >30k-file repo.** Worktree creation alone exceeds the work duration.
- **Fix is mechanical** — rename, version bump, single-line tweak, import addition. Judgment value is zero; overhead is not.
- **Sub-agent would just re-read what the EM has already loaded.** If the relevant context is already in the EM's window, dispatch adds a re-read cycle for no gain.
- **Fix is in a file the EM is already editing.** Mid-edit dispatch mid-session creates a concurrent-edit hazard on the same file.

## Heuristic

> Fan out when the job decomposes. Dispatch when the sub-agent brings something the EM doesn't have: context, concurrency, judgment, or isolation from a large read. EM-inline only when the fix is small, the locus is already known, and the work fits inside the worktree-overhead window.

A useful smell test: if the EM's dispatch prompt would be "read file X, change line Y, report back" — and the EM already has file X in context — the dispatch is overhead theater, not delegation.

## Mitigation for the Worktree Default

Anthropic CLI v2.1.141 ships no opt-out for `isolation: "worktree"`. Per-agent worktrees on large repos accumulate creation cost and leave orphaned worktree directories if sub-agents crash or timeout.

Mitigations:

- **`agent-worktree-sweep.sh`** — reaps orphan worktrees. Wired into `/workday-start` Step 0.6 and `/session-start` warn-detect.
- **`disableAgentView: true` in settings.json** — nuclear option; disables agent telemetry alongside worktree creation. Use only if worktree overhead is untenable and sweep is insufficient.
- **File upstream.** Issue #58597 is open as a request for a `defaultIsolation` settings key that would allow per-project opt-down to `isolation: "none"` for large repos.
- **Coordinator-side dispatch throttling.** On repos confirmed >30k files, prefer batching mechanical fixes into a single executor pass over N individual dispatches. One worktree creation + N edits beats N worktree creations.

## Cluster Execution — Full Ceremony on the Novel Item, Direct Dispatch on the Rest

*2026-05-17, coordinator-claude.* When a cluster of related fixes shares a single architectural shape (one novel pattern + N surgical follow-ups that mirror it), front-load the review ceremony on the novel item and direct-dispatch the surgical follow-ups against the established pattern. Full plan-review + prior-art-check + post-impl code-review on every cluster member is ceremony inflation — the second through Nth instances re-verify the same pattern with diminishing return.

**Rule:**
- **Item 1 (the novel one):** full ceremony — plan, prior-art-check, Patrik, post-impl review.
- **Items 2..N (surgical follow-ups of the same shape):** direct executor dispatch with the item-1 spec as reference. EM spot-check post-commit.

Tell for cluster shape: each item edits a different file, the *shape* of the edit is the same, and the only judgment in items 2..N is "apply the item-1 pattern to this file's specifics." When you find yourself drafting the same plan body N times with the file path changed, that's the tell — promote item 1 to canonical and direct-dispatch the rest.

## Run-Cost Calibration — Budget for Longest-Reasonable-Success, Build a Short Repro Before the Long One

Three facets of the same discipline: the wall-clock budget for a dispatched run, and the loop you iterate inside it, must be sized against the *actual* cost of the run, not a worst-case imagination or the convenience of re-firing the whole thing.

**Budget for "longest reasonable success," not "worst-case imagined."** *(2026-05-20, project-rag.)* A diagnostic or e2e run's timeout should be set from the longest a *successful* run plausibly takes — not the catastrophic upper bound your anxiety reaches for. Over-budgeting wastes the EM's polling window (a run that would have failed at 90s is given 10 minutes before the EM looks); a too-tight budget kills legitimate slow-but-succeeding runs. Estimate the success-path duration, add headroom, and treat overrun as signal (it hung) rather than as a margin you padded to avoid thinking.

**Build a 60s repro before re-firing a 30-min job.** *(2026-05-22, project-rag-ue-addon.)* When a long-running pipeline fails, the temptation is to tweak one thing and re-fire the whole 30-minute job. The short-loop discipline: extract the failing stage into a sub-minute reproducer first, iterate against *that* until green, then re-fire the full job once. The repro-construction cost is paid back on the second iteration — and most long-pipeline failures need 3-5 iterations to resolve. Re-firing the full job per iteration is the single most expensive iteration shape available.

**The harness Bash 5-minute timeout is hostile to long-running e2e — three workarounds.** *(2026-05-20, project-rag-ue-addon.)* The Bash tool caps at a hard timeout (default 2 min, max 10 min); genuinely long e2e runs (full index build, cold-cache install verification) exceed it. Do not paper over this by splitting the *test* into artificially small pieces that no longer exercise the integration. The three legitimate shapes:

1. **PM-manual** — hand the PM the exact command to run in a real terminal with no timeout; the EM consumes the result. Right when the run is genuinely one indivisible long operation.
2. **Warm-cache splits** — run the expensive setup phase once (priming the cache), then the EM's repeated verification runs hit warm cache and fit the budget. Right when the cost is front-loaded setup, not the assertion.
3. **Passive sibling verification** — a sibling process (daemon, watcher, already-running server) does the long work; the EM polls its status artifact rather than blocking on it. Right when the long work is someone else's to own (see `dispatching-parallel-agents.md` § Long-Running Dispatched Process for the status-file/heartbeat protocol).

## Related

- → `docs/wiki/dispatching-parallel-agents.md` — when parallel-shape is appropriate; Coupling Rules Out Concurrency; Peer-Scope Prohibition
- → `docs/wiki/delegate-execution.md` — EM-vs-executor altitude
- → `agent-worktree-sweep.sh` — sweep mechanics
- → `fan-out-dispatch.sh` — overlap pass + scoped-prompt compiler (run this to fan out a wave)
- → `dispatching-parallel-agents.md` § Executing a Fan-Out Wave — the fan-out methodology execution follows; runs the helper, dispatches the compiled wave via `Agent`, holds EM-serial commit between waves (not a skill — the `/fan-out` command was demoted 2026-05-30, vocabulary collision with native Claude Code)
- → `em-operating-model.md` HARD RULES — anti-monolith HARD RULE (a large job is fanned out or chunked per-fresh-agent, never one agent grinding chunk after chunk)
- → `tasks/lessons.md` line 85 — 2026-05-20 "Many agents often beat one [universal]" empirical antecedent
- Anthropic issue #58597 — settings.json `defaultIsolation` key proposal
