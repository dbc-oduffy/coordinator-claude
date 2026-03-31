# D-031: Removed Executor Exit Watchdog

**Date:** 2026-03-31
**Status:** Final
**Category:** Hooks / Agent guardrails

## Decision

Removed the `executor-exit-watchdog.sh` SubagentStop hook after ~6 iterations of trying to make it work reliably. The hook is gone — no SubagentStop hooks remain in the coordinator.

## What It Was

A SubagentStop hook that fired whenever any subagent exited. Two tiers:

1. **Tier 1 (tag-based):** Checked whether the executor included a protocol-compliant exit status tag (`<exit-status>DONE</exit-status>`, `BLOCKED`, `THRASHING`). If missing, blocked exit and demanded a post-mortem.
2. **Tier 2 (edit-count heuristic):** Counted Edit/Write calls per file in the transcript. If any file was edited 8+ times, flagged it as potential thrashing and demanded a post-mortem before allowing exit.

## Why We Removed It

The fundamental problem: **SubagentStop hooks fire for ALL subagents, not just executors.** The hook had no reliable way to distinguish an executor from an enricher, reviewer, research agent, or planning agent — all of which have legitimately different exit patterns.

Iterations of fixes tried:
1. **Initial version** — fired on everything, immediately hit false positives on enrichers and reviewers (which edit the same file many times by design)
2. **Agent-type skip-list** — extracted `agent_type` from hook input and skipped known non-executor types. Helped, but the skip-list was always incomplete as new agent types were added
3. **Edit-count threshold tuning** — raised from 5 to 8. Still hit false positives on plan documents with many checkboxes (4 checkboxes + status lines = 8 edits with zero repetition)
4. **File-type filtering** — tried excluding `.md` files from the count. Defeated the purpose since stubs are markdown
5. **Tier 1 only (tag-based)** — removed the edit-count heuristic entirely. Still fired on non-executor agents that don't use exit status tags (because they're not supposed to)
6. **Coordinator session false positives** — the hook fired on the coordinator itself exiting plan mode, producing absurd "you edited a file 8 times" messages to sessions that made zero edits

The deeper issue is that the hook was trying to enforce executor protocol compliance from outside the executor, using heuristics that couldn't distinguish "thrashing" from "legitimate work pattern." Every fix for one false positive class created a new one.

## What Replaces It

Nothing directly. The executor's self-monitoring (stuck-detection, exit status tags) is the primary guardrail. The coordinator validates executor output on return. If an executor exits without a clean status tag, the coordinator sees it in the return message and handles it — no hook needed.

The exit status tag protocol remains in `executor.md` — executors still emit `DONE`, `BLOCKED`, or `THRASHING` tags. The difference is that compliance is checked by the coordinator reading the return, not by a hook blocking exit.

## Lesson

Hooks that fire on broad event categories (SubagentStop for *all* subagents) and try to infer intent from transcript heuristics are inherently fragile. The signal-to-noise ratio never got good enough to justify the disruption. Agent-level self-monitoring + coordinator-level validation is simpler and more reliable than external watchdog heuristics.
