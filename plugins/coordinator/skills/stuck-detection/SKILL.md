---
name: stuck-detection
description: Self-monitoring protocol for detecting and recovering from stuck patterns. Referenced by agent prompts — not invoked directly.
---

# Stuck Detection Protocol

You MUST maintain a mental tally of your recent actions. After each tool call, check against these patterns:

## Pattern 1: Repetition (same action, same/error result)

If you have called the same tool with the same arguments 3+ times and received the same result (or the same error), you are stuck. (Two retries are allowed — the third repetition triggers detection.)

**Recovery:** Stop retrying. Read the error output carefully. Describe what you expected vs what happened. Try a fundamentally different approach — not a variant of the same approach.

## Pattern 2: Oscillation (A-B-A-B)

If your last 4+ actions alternate between two patterns (e.g., edit-undo-edit-undo, or read-file-A, read-file-B, read-file-A, read-file-B), you are oscillating.

**Recovery:** Pick one approach and commit. If you're uncertain which is correct, escalate with BLOCKED rather than oscillating.

## Pattern 3: Analysis Paralysis (no action for 3+ paragraphs)

If you've written 3+ paragraphs of analysis without making a single tool call, you're stalling.

**Recovery:** State your plan in one sentence. Execute the first concrete step immediately. Analysis without action is not progress.

## Pattern 4: Post-Compaction Repetition

After context compaction, check your tasks (TaskList/TaskGet) for "tried and abandoned" notes before attempting any approach. Check both `metadata.tried_and_abandoned` and task descriptions (legacy format). If a task records that an approach was tried and failed, do not retry it.

**Recovery:** Read all task metadata and descriptions via TaskGet for notes about failed approaches. Choose a different strategy.

## When Stuck Detection Triggers

- Report the pattern you detected (1-4)
- State what you tried and why it failed
- If you're a dispatched agent (executor/enricher): report BLOCKED with the stuck pattern as the blocker type
- If you're the coordinator: flag the stuck state to the PM and propose a different approach
