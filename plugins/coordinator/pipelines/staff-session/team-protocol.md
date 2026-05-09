# Staff Session Team Protocol

> Referenced by `coordinator/commands/staff-session.md` and debater/synthesizer prompt templates.

## Overview

Agent Teams-based collaborative planning and review: the EM writes a scope document, selects a team of persona-based debaters + one synthesizer, spawns all teammates, and is **freed**. The team debates autonomously — forming positions, challenging each other, converging, and synthesizing output. The EM is notified when synthesis completes.

## Team Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Debater** | Opus | 2-5 | Persona agent (Patrik, Zoli, Sid, etc.). Reads scope + codebase, forms a position from their persona's perspective, debates peers via messaging, converges, writes final position document |
| **Synthesizer** | Opus | 1 | Zolí (eng-director). Director of Engineering. Blocked by all debaters. Cross-references all position documents, resolves disagreements through his ambition-calibrated lens, produces plan (plan mode) or synthesized findings (review mode). Represents all positions fairly but doesn't default to conservative resolutions. Writes optional advisory with ambition assessment. |

## Team Lifecycle

```
EM: Write scope.md → Select team → Create team → Spawn all teammates → FREED
Debaters: [no blockers — start immediately in parallel]
  → Read scope.md + context files
  → Research codebase (Glob/Grep/Read)
  → Form initial position
  → Send POSITION to peers
  → Exchange CHALLENGEs, QUESTIONs, CONCESSIONs
  → Self-govern timing (floor → diminishing returns → ceiling)
  → CONVERGING → wait → finalize → write position doc → mark complete → DONE to synthesizer
Synthesizer: [blocked by all debaters, waiting for DONE messages]
  → Re-check TaskList on each DONE message
  → Proceed when all debater tasks show completed
  → Read all position documents
  → Synthesize (plan: consensus + dissent | review: findings + verdict)
  → Write advisory if applicable
  → Mark complete
```

## Blocking Chain

```
Debater A (no blockers) ─┐
Debater B (no blockers) ─┤──→ DONE messages wake synthesizer
Debater C (no blockers) ─┘
                               │
                      Synthesizer (blockedBy: all debaters)
```

No scout phase — debaters read the EM's scope document and the codebase directly.

**Wake-up mechanism:** `blockedBy` is a file-based polling gate, not an event trigger. The synthesizer starts, checks TaskList, sees unfinished blockers, and goes idle. DONE messages from debaters cause the synthesizer to re-poll TaskList. Each debater MUST send DONE to the synthesizer after marking their task complete — this is the wake-up mechanism, not just a courtesy. Without DONE messages, the synthesizer may idle indefinitely.

## Message Protocol — Debate

| Category | Format | When |
|---|---|---|
| **POSITION** | `"Position for {peer}: On {topic}, I propose {X} because {reasoning}. See {file}:{lines}."` | Initial stance on a design element or finding |
| **CHALLENGE** | `"Challenge to {peer}: Your position on {topic} has weakness {X}. Evidence: {reasoning}."` | Disagreement with a peer's position |
| **CONCESSION** | `"Concession to {peer}: You're right about {topic}. Updating my position to incorporate {X}."` | Accepting a peer's challenge |
| **QUESTION** | `"Question for {peer}: Regarding {topic}, have you considered {X}? I found {evidence}."` | Seeking clarification or raising a consideration |
| **DONE** | `"DONE: Position written to {output-file}"` | After marking own task completed — sent to synthesizer only |

**Volume governance:** Max 4 messages per peer, max 12 total outgoing messages per debater. This prevents message floods in full teams while preserving per-peer depth.

**Message ordering:** Debaters start simultaneously, so a debater may receive CHALLENGE or QUESTION messages before publishing their own POSITION. Handle gracefully: queue incoming messages and address them after forming initial position. Early messages are normal, not errors.

## Self-Governance Timing

Debaters manage their own timing. No EM broadcasts WRAP_UP.

| Parameter | Plan Mode | Review Mode |
|-----------|-----------|-------------|
| **Floor** | 3 min AND 1 peer exchange round | 3 min AND 1 peer exchange round |
| **Diminishing returns** | Last 2 exchanges produced no position changes | Last 2 exchanges produced no position changes |
| **Ceiling** | 10 min | 8 min |

Review mode gets a shorter ceiling — the artifact already exists, less codebase research needed.

**Clock mechanism:** Spawn timestamp is provided in the debater prompt as `[SPAWN_TIMESTAMP]` (Unix epoch seconds). Debaters check elapsed time via `date +%s` in Bash after each exchange and compare against spawn timestamp.

**Ceiling behavior:** Ceiling triggers mandatory convergence. The convergence protocol (steps 1-6 below) runs to completion even if it extends 1-2 minutes past the ceiling. No new CHALLENGE messages accepted after ceiling — only final responses to in-flight challenges.

## Convergence Protocol

Begin convergence when ANY of these conditions are met (AND the floor is satisfied):
- 1 peer exchange round completed and last 2 exchanges produced no position changes (diminishing returns)
- Ceiling time reached (mandatory)

**Steps:**
1. Send `CONVERGING` to all peers
2. Wait ~20 seconds for final challenges
3. Answer any final challenges
4. Write complete position document to `{scratch-dir}/{persona-slug}-position.md`
5. Mark task `completed` (TaskUpdate)
6. Send `DONE` to synthesizer: `SendMessage(to: "[SYNTHESIZER_NAME]", message: "DONE: Position written to {scratch-dir}/{persona-slug}-position.md")`

**Backstop suspension:** Persona agents' built-in backstop invocations (e.g., Patrik's "invoke Zoli at High effort") are suspended during staff sessions. The parallel debate serves the same function — multi-perspective challenge. Debater prompt templates explicitly override backstop invocation. Debaters debate directly with peers.

## Failure Handling

| Failure | Action |
|---------|--------|
| Single debater crashes (no position written) | Synthesizer works with remaining positions. Note the gap: "Missing perspective: {persona}." EM can supplement manually. |
| Majority debater failure (>50% crash) | EM is notified (only 1 or fewer debater tasks completed). TeamDelete, fall back to `/review-dispatch` for the same artifact. |
| Synthesizer fails | EM reads raw debater position documents from scratch dir. Manual synthesis is feasible — position docs are structured. |
| Team creation fails | Report to PM. Fall back to `/review-dispatch` or EM-authored plan. |
| DONE message not received (debater marked complete but synthesizer not woken) | Synthesizer checks TaskList on a polling cycle. If all debater tasks show `completed` but no DONE received after 2 minutes, synthesizer proceeds anyway. EM can send a manual nudge via SendMessage if synthesizer appears stalled. |
| Debate loops (no convergence) | Ceiling time is a hard cutoff. Diminishing returns detection also triggers convergence after 2 no-change exchanges. Position documents capture the disagreement; synthesizer resolves or presents as dissent. |

## Scratch Directory Structure

```
tasks/scratch/staff-session/{run-id}/
  scope.md                    (EM input — objectives or artifact reference)
  patrik-position.md          (debater output)
  sid-position.md             (debater output)
  [camelia-position.md]       (optional debater output — full tier)
  synthesis.md                (Zolí's synthesis — backup copy)
  advisory.md                 (Zolí's advisory, optional)
```
