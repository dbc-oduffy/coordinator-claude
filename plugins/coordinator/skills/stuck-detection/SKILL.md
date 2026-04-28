---
name: stuck-detection
description: "This skill should be used when detecting repetitive actions, oscillating between approaches, or stalling without progress — the three stuck patterns. Referenced by agent prompts for self-monitoring."
version: 1.0.0
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

## Pattern 5: Anti-Repetition Violation

Before beginning work, review any ANTI-REPETITION section in your dispatch prompt. Plan your approach to be fundamentally different from all listed failed approaches. If during execution you realize you are converging on a listed failed approach, STOP.

**Recovery:** Choose a fundamentally different approach. If no alternative exists, report BLOCKED with Type: Structural — "All known approaches exhausted."

## Stuck Teammates: Protect the Work First

Some Agent Teams teammates enter an idle loop where they stop processing shutdown requests and plain-text messages. `TeamDelete` rejects while they are "active." There is no clean live-kill mechanism — they will eventually time out on their own.

**Before attempting any cleanup of a stuck teammate:**
1. **Commit all in-progress work** — identify the specific deliverable paths the stuck agent (or its peers) wrote, stage those paths explicitly, and commit via the scoped helper: `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "<subject>"`. Do not use `git add -A` or `git add .` — under stress-of-recovery, blanket staging is tempting but produces audit-trail-misleading commits. Stage only the deliverables you can name.
2. **Archive the deliverable** — if the session's output is a file, verify it exists on disk and is substantive before attempting team teardown.
3. **Then** attempt shutdown/TeamDelete. If it fails, leave the agent to time out. The work is safe.

The stuck agent's timeout does not block the session from advancing. Once deliverables are committed and archived, the EM can proceed to the next phase or close the session.

## When Stuck Detection Triggers

- Report the pattern you detected (1-5)
- State what you tried and why it failed
- If you're a dispatched agent (executor/enricher): report BLOCKED with the stuck pattern as the blocker type
- If you're the coordinator: flag the stuck state to the PM and propose a different approach
