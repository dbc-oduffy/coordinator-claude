---
title: Stuck Detection and Repomap
system: stuck-detection
status: distilled
distilled_from:
  - archive/specs/2026-03-16-tier1-repomap-stuckdetect.md
  - plugins/coordinator-claude/coordinator/skills/stuck-detection/SKILL.md
distilled_at: 2026-05-06
distilled_run: 2026-05-06-13h00
---

# Stuck Detection and Repomap

## Overview

Two complementary subsystems for keeping agents productive:

1. **Stuck detection** — prompt-based self-monitoring (with TodoWrite anti-amnesia assist) for the canonical stuck patterns: repetition, oscillation, analysis paralysis, post-compaction repetition, anti-repetition violation. Also covers stuck Agent Teams teammates.
2. **Repomap** — own tree-sitter integration that ranks files by recency / frequency / centrality / size for context-injection. Awareness-based per-task scoping; not forced.

## Pattern Catalog and Recovery Protocol (Operational)

Maintain a mental tally of recent actions. After each tool call, check against these patterns:

### Pattern 1: Repetition (same action, same/error result)

If you have called the same tool with the same arguments 3+ times and received the same result (or the same error), you are stuck. (Two retries are allowed — the third repetition triggers detection.)

**Recovery:** Stop retrying. Read the error output carefully. Describe what you expected vs what happened. Try a fundamentally different approach — not a variant of the same approach.

### Pattern 2: Oscillation (A-B-A-B)

If your last 4+ actions alternate between two patterns (e.g., edit-undo-edit-undo, or read-file-A, read-file-B, read-file-A, read-file-B), you are oscillating.

**Recovery:** Pick one approach and commit. If you're uncertain which is correct, escalate with BLOCKED rather than oscillating.

### Pattern 3: Analysis Paralysis (no action for 3+ paragraphs)

If you've written 3+ paragraphs of analysis without making a single tool call, you're stalling.

**Recovery:** State your plan in one sentence. Execute the first concrete step immediately. Analysis without action is not progress.

### Pattern 4: Post-Compaction Repetition

After context compaction, check your tasks (TaskList/TaskGet) for "tried and abandoned" notes before attempting any approach. Check both `metadata.tried_and_abandoned` and task descriptions (legacy format). If a task records that an approach was tried and failed, do not retry it.

**Recovery:** Read all task metadata and descriptions via TaskGet for notes about failed approaches. Choose a different strategy.

### Pattern 5: Anti-Repetition Violation

Before beginning work, review any ANTI-REPETITION section in your dispatch prompt. Plan your approach to be fundamentally different from all listed failed approaches. If during execution you realize you are converging on a listed failed approach, STOP.

**Recovery:** Choose a fundamentally different approach. If no alternative exists, report BLOCKED with Type: Structural — "All known approaches exhausted."

### Stuck Teammates: Protect the Work First

Some Agent Teams teammates enter an idle loop where they stop processing shutdown requests and plain-text messages. `TeamDelete` rejects while they are "active." There is no clean live-kill mechanism — they will eventually time out on their own.

**Before attempting any cleanup of a stuck teammate:**
1. **Commit all in-progress work** — identify the specific deliverable paths the stuck agent (or its peers) wrote, stage those paths explicitly, and commit via the scoped helper: `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "<subject>"`. Do not use `git add -A` or `git add .` — under stress-of-recovery, blanket staging is tempting but produces audit-trail-misleading commits. Stage only the deliverables you can name.
2. **Archive the deliverable** — if the session's output is a file, verify it exists on disk and is substantive before attempting team teardown.
3. **Then** attempt shutdown/TeamDelete. If it fails, leave the agent to time out. The work is safe.

The stuck agent's timeout does not block the session from advancing. Once deliverables are committed and archived, the EM can proceed to the next phase or close the session.

### When Stuck Detection Triggers

- Report the pattern you detected (1–5)
- State what you tried and why it failed
- If you're a dispatched agent (executor/enricher): report BLOCKED with the stuck pattern as the blocker type
- If you're the coordinator: flag the stuck state to the PM and propose a different approach

## Architecture — Stuck Detection

### Five OpenHands scenarios mapped to four canonical patterns

The detection layer responds to the OpenHands taxonomy:
1. Same action, same observation
2. Same action, error observation
3. Monologue (3+ paragraphs without tool call)
4. Alternating actions A-B-A-B
5. Condensation loops (post-compaction repetition)

### Layered detection

| Layer | Implementation | Status |
|-------|----------------|--------|
| 1 | Prompt-based self-monitoring (all agents) | Shipped |
| 2 | TodoWrite anti-amnesia (`tried and abandoned` field that survives compaction) | Shipped |
| 3 | PostToolUse hook-based assist | **Hard-deferred** — PostToolUse hooks cannot inject user messages, only approve/deny. Revisit only if API changes. |

### Pattern catalog (canonical)

| Pattern | Trigger | Response |
|---------|---------|----------|
| 1 — Repetition | Same tool/args **3+** times | Stop, read error carefully, fundamentally different approach |
| 2 — Oscillation | **4+** alternating actions | Pick one and commit, escalate `BLOCKED` if uncertain |
| 3 — Analysis Paralysis | **3+** paragraphs, no tool call | State plan in one sentence and execute |
| 4 — Post-Compaction Repetition | (any retry after compaction) | Check TodoWrite for "tried and abandoned" before retrying |

**Threshold:** 3 repetitions (allow 2 retries) — consistent across all docs.

## Architecture — Repomap (Three-Tier)

### Why not wrap Aider's repomap.py

- Tightly coupled to Aider's persistent chat model (chat-file boost).
- Heavy deps (networkx, pygments, diskcache).
- Aider's ranking is purely structural; the coordinator blends operational + structural signals, doesn't replace.

Build own tree-sitter integration directly.

### tree-sitter parser surface

- **Priority languages:** Python (P0), TypeScript (P1), C++ (P1 for DroneSim).
- **Fallback:** Markdown / JSON / Shell keep regex.
- **Returns:** `(definitions, references)` tuple.
- **Cache schema v2:** `{"defs": [...], "refs": [...]}` with `_version: 2` root key.
- **References usage:** symbol → file index, file-to-file directed graph (dict-based, no NetworkX).

### Ranking weights

`35 / 25 / 30 / 10` (recency / frequency / centrality / size_inverse), with rank-based normalization and a **40% centrality cap**. The cap prevents base classes from dominating; tune empirically after 2-3 projects.

### Per-step selective loading boost multipliers

| Tier | Multiplier |
|------|------------|
| `focus_files` | ×5.0 |
| 1-hop graph neighbors | ×2.5 |
| 2-hops | ×1.5 |
| Rest | ×1.0 |

Two outputs:
- `.claude/repomap.md` — global static
- `.claude/repomap-task.md` — task-scoped dynamic

### Dependency installation

Option 3: `requirements-repomap.txt` with pinned versions + inline stdlib fallback.

## Key Patterns

- **Task-scoped maps are awareness-based, not forced.** The Coordinator uses judgment per dispatch; not every dispatch needs a fresh task-scoped repomap.
- **Self-monitor as a doctrine, not a hook.** Layer 1 (prompt-based) is load-bearing — Layer 3 hooks can't deliver the corrective signal because PostToolUse can only approve/deny.

## Gotchas

- **Layer 3 is hard-deferred, not forgotten.** If the Claude Code API ever lets PostToolUse inject user messages, this becomes the cleanest implementation. Until then, prompt-based self-monitoring is the contract.
- **Centrality cap is empirical.** 40% works on the projects audited so far; if a project's hottest base class still dominates, retune the cap before the weights.

## Reference

- Related: [agent-hierarchy](agent-hierarchy.md)
- Source plan: `archive/specs/2026-03-16-tier1-repomap-stuckdetect.md`
