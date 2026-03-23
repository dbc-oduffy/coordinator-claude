# Repo Research Team Protocol

> Referenced by agent definitions and `deep-research-repo.md` command.

## Overview

Agent Teams-based repo research: the EM scopes the target repository into 4 domain-aligned chunks, creates a team of 2 Haiku scouts + 4 Sonnet specialists + 1 Opus synthesizer, spawns all teammates, and is **freed**. The team handles everything autonomously — file inventory, analysis, optional comparison, cross-pollination, and synthesis. The EM is notified when synthesis completes.

## Team Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** | Haiku | 2 | Read and inventory all files in assigned chunks; if comparison mode, identify equivalent project files |
| **Specialist** | Sonnet | 4 | Deep-read files, analyze architecture/patterns/data flow, optionally compare against project, cross-pollinate |
| **Synthesizer** | Opus | 1 | Cross-reference all specialist findings, produce ASSESSMENT.md + GAP-ANALYSIS.md (if comparison) |

## Team Lifecycle

```
EM: Scope into 4 chunks → write scope → Create team → Spawn all teammates → FREED
Scout 1: Read chunks A,B → Inventory files → [If compare: identify project files] → Write inventories → Mark complete → [idle]
Scout 2: Read chunks C,D → Inventory files → [If compare: identify project files] → Write inventories → Mark complete → [idle]
Specialists: [blocked by BOTH scouts] → Read inventories → Deep-read files → Assessment → [If compare: Comparison] → Cross-pollinate → Converge → Mark complete → DONE to synthesizer
Synthesizer: [blocked by all specialists, waiting for DONE msgs] → Verify all complete → Read findings → Synthesize → Mark complete
```

## Blocking Chain

```
Scout 1 (chunks A, B, no blockers) ─┐
                                      ├──→ Specialists A, B, C, D (blocked by BOTH scouts)
Scout 2 (chunks C, D, no blockers) ─┘                │
                                                       ├──→ DONE messages wake synthesizer
                                                       │
                                            Synthesizer (blocked by all 4 specialists)
```

**Why all specialists blocked by both scouts:** Cross-subsystem connections. Scout 1's chunks may have data flow into scout 2's chunks. Specialists need the COMPLETE inventory across all chunks to understand these connections. The latency cost is minimal — Haiku scouts have a 5-minute ceiling.

- **Scouts → Specialists:** Task-gated via `blockedBy`. Specialists unblock when BOTH scouts mark their tasks complete. No messaging needed — specialists haven't started yet.
- **Specialists → Synthesizer:** Task-gated via `blockedBy` + DONE messages as wake-up signals. `blockedBy` is a status gate, not an event trigger — the synthesizer needs explicit DONE messages to know when to re-check task status.

## Scout Protocol

Each scout inventories 2 chunks of the target repository. Scouts produce **structured file inventories** — not analysis, not recommendations, just thorough mechanical cataloging.

- Reads every file in their assigned chunks via Read tool
- Produces: file paths, line counts, key structs/functions with signatures, actual constant values, data flow, cross-subsystem connections
- If `--compare` mode: also globs the user's project for files matching chunk domain keywords, reads first 30 lines to check signatures, writes `{repo-file} → {project-file-candidate}` mappings
- **No messaging** — scout has no SendMessage tool. Task completion is the only signal.
- **Timing:** No floor. Ceiling: 5 minutes. This is mechanical work — go fast. (Pipeline A uses 3 minutes for web scouts; 5 minutes here because repo file reading is heavier.)

## Message Protocol

### Specialist → Specialist (Cross-Pollination)

Send targeted messages to specific peers by name:

| Category | Format | When |
|---|---|---|
| **FINDING** | `"Finding for {peer}: {brief}. File: {path}:{line}. Relevant because {reason}."` | A cross-chunk discovery relevant to another specialist |
| **CONTRADICTION** | `"Contradiction with {peer}: I found {X} in chunk {Y} but your chunk suggests {Z}. Can you verify?"` | Data flow or design pattern conflicts across chunks |
| **CHALLENGE** | `"Challenge to {peer}: Your chunk's {X} at {file}:{line} conflicts with {Y} at {file}:{line}. Which is the intended flow?"` | Direct factual conflict |
| **SOURCE** | `"Source for {peer}: {file-path} — covers {aspect} relevant to your chunk."` | Useful file for a peer's analysis |

### Specialist → Synthesizer (Wake-Up Signal)

`blockedBy` is a status gate, not an event trigger — completing a blocker task does NOT automatically wake the blocked teammate. Specialists must explicitly message the synthesizer after completing their task:

| Category | Format | When |
|---|---|---|
| **DONE** | `"DONE: {chunk-letter} assessment written to {scratch-dir}/{chunk-letter}-assessment.md [+ comparison written to {chunk-letter}-comparison.md]"` | After marking own task `completed` |

This is the synthesizer's wake-up mechanism. Each DONE message causes the synthesizer to re-check `TaskList`. When all specialist tasks show `completed`, it proceeds with synthesis.

### Volume Governance

- **Peer messages: max 3 per peer** (max 9 total for a 4-specialist team since you don't message yourself)
- **DONE message: exactly 1 per specialist** (sent to synthesizer only)
- **Scouts: no messages** (task completion handles unblocking)
- Quality over quantity

## Self-Governance Timing

Specialists manage their own timing. No EM broadcasts WRAP_UP.

### Three-Part Model

1. **Floor (minimum before convergence allowed)**
   - Must have deep-read at least `MIN_SOURCES` files (not just listed — actually Read and analyzed) AND worked for at least `MIN_MINUTES` minutes
   - Both conditions must be met — prevents "skimmed 3 files in 2 minutes" thin convergence
   - Defaults: 3 files deep-read, 5 minutes

2. **Diminishing Returns (between floor and ceiling)**
   - After the floor, self-assess after each file read: "Did this add new architectural insights?"
   - If last 2 consecutive file reads added no new findings → convergence signal
   - Note in output: "Converging: diminishing returns after file N"

3. **Ceiling (maximum research time)**
   - Configurable by the EM at team creation (default: 15 minutes)
   - Begin convergence regardless of state
   - Check time via `date +%s` in Bash, compare against spawn timestamp

### Clock Mechanism

Spawn timestamp is provided in the specialist prompt as `[SPAWN_TIMESTAMP]` (Unix epoch seconds). Specialists check elapsed time via `date +%s` in Bash after every 2-3 file reads and compare.

## Convergence Protocol

Begin convergence when ANY of these conditions are met (AND the floor is satisfied):
- At least `MIN_SOURCES` files deep-read and cross-chunk connections addressed
- Last 2 file reads added no new findings (diminishing returns)
- Ceiling time reached

**Steps:**
1. Send `CONVERGING` to all peers
2. Wait ~30 seconds for final challenges
3. Answer any challenges
4. Write complete output files (assessment + comparison if enabled)
5. Mark task `completed`
6. Send `DONE` to synthesizer (wake-up signal — see Message Protocol above)

**Early convergence note:** Specialists who converge early remain alive — late-arriving peer messages may warrant a quick update to findings before the agent terminates.

**Timeout:** If a CHALLENGE goes unanswered for 2 minutes → mark finding as `[UNVERIFIED]`.

## Failure Handling

- **Scout fails (no inventory):** Specialists fall back to self-directed file discovery (Glob + Read workflow). Budget 3 extra minutes.
- **Scout times out (partial inventory):** Specialists use what's there + supplement with own Glob/Read for missing directories.
- **Self-timed convergence (ceiling):** Specialists begin convergence autonomously after max time, without EM intervention.
- **Read failures:** If a file can't be read (binary, permissions), skip it and note in output.
- **All specialists fail:** EM is notified (no completed specialist tasks), reports to PM.

## Scratch Directory

`tasks/scratch/deep-research-teams/{run-id}/`

- Scout 1 writes to: `{scratch-dir}/A-inventory.md`, `{scratch-dir}/B-inventory.md`
- Scout 2 writes to: `{scratch-dir}/C-inventory.md`, `{scratch-dir}/D-inventory.md`
- Each specialist writes to: `{scratch-dir}/{chunk-letter}-assessment.md` (always) + `{scratch-dir}/{chunk-letter}-comparison.md` (if comparison mode)
- Synthesizer writes to: `{output-path}` + `{scratch-dir}/synthesis.md`

## Comparison Mode

When `--compare <project-path>` is provided:

1. **Scouts** identify equivalent project files during inventory (mechanical pattern-matching)
2. **Specialists** deep-read the project files identified by scouts and produce comparison artifacts
3. **Synthesizer** produces both ASSESSMENT.md (evergreen) and GAP-ANALYSIS.md (point-in-time)

The assessment always stands alone — it describes the repo on its own merits, with no reference to the comparison project. The gap analysis is a separate artifact.
