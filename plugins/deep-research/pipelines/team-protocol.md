# Deep Research Team Protocol

> Referenced by agent definitions and `deep-research-web.md` command.

## Overview

Agent Teams-based deep research: the EM scopes research and crafts search queries, creates a team of a Haiku scout + Sonnet specialists + an Opus synthesizer, spawns all teammates, and is **freed**. The team handles everything autonomously — source discovery, analysis, cross-pollination, and synthesis. The EM is notified when synthesis completes.

## Team Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** | Haiku | 1 | Execute EM-crafted search queries, mechanically vet accessibility, build shared source corpus |
| **Specialist** | Sonnet | 3-5 | Deep-read sources from corpus, verify claims, cross-pollinate with peers, write findings |
| **Synthesizer** | Opus | 1 | Cross-reference all specialist findings, resolve contradictions, write final document; optionally write Synthesizer Advisory |

## Team Lifecycle

```
EM: Scope + craft queries → write scope.md → Create team → Spawn all teammates → FREED
Scout: Read scope.md → WebSearch → WebFetch (vet accessibility) → Write source-corpus.md → Mark complete → [idle]
Specialists: [blocked by scout] → Read corpus → Deep-read → Cross-pollinate → Converge → Mark complete → DONE to synthesizer
Synthesizer: [blocked by specialists, waiting for DONE msgs] → Verify all complete → Read findings → Synthesize → Write advisory (if anything beyond scope) → Mark complete
```

## Blocking Chain

```
Scout (no blockers) ──────→ task completion unblocks specialists
Specialists (blockedBy: scout) ──→ DONE messages wake synthesizer
Synthesizer (blockedBy: all specialists) ──→ mark complete notifies EM
```

- **Scout → Specialists:** Task-gated via `blockedBy`. Specialists unblock when scout marks its task complete. No messaging needed — specialists haven't started yet (confirmed empirically 2026-03-21).
- **Specialists → Synthesizer:** Task-gated via `blockedBy` + DONE messages as wake-up signals. The synthesizer is already running but idle — it needs explicit DONE messages to trigger its next poll cycle (confirmed empirically 2026-03-21).

### How Agent Teams Blocking Actually Works (empirical + sourced)

Agent Teams uses **file-based polling, not callbacks**. Task state lives in JSON files at `~/.claude/tasks/{team-name}/N.json`. Agents discover available work by calling `TaskList()`, which re-evaluates `blockedBy` arrays fresh on each call. There is no active push/callback when a blocker completes.

**Two distinct scenarios with different wake-up behavior:**

| Scenario | Agent State | Wake-Up Mechanism | Message Needed? |
|----------|-------------|-------------------|-----------------|
| **Task-blocked (pending)** | Not yet started — `pending` status, waiting for blockers | `TaskList()` re-evaluates `blockedBy` on next poll; agent auto-starts when unblocked | No — auto-wake works |
| **Message-blocked (idle)** | Started, checked status, went idle waiting | Needs an inbox message to trigger the next poll cycle | Yes — explicit DONE message required |

The scout→specialist transition is scenario 1 (auto-wake). The specialist→synthesizer transition is scenario 2 (DONE messages needed). Both confirmed empirically 2026-03-21.

**Shutdown behavior:** Teammates prioritize completing their current work loop over acknowledging shutdown requests. Expect convergence protocol (CONVERGING → wait → write → mark complete → DONE) to run before shutdown acknowledgment. This is good for data integrity but means team teardown takes 30-60 seconds after shutdown requests are sent.

**Sources:** [Claude Code official docs](https://code.claude.com/docs/en/agent-teams), [reverse-engineering analysis (nwyin.com)](https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered.html), [swarm orchestration guide (kieranklaassen gist)](https://gist.github.com/kieranklaassen/4f2aba89594a4aea4ad64d753984b2ea).

## Scout Protocol

The scout builds a **shared corpus** — a pool of broadly useful sources. It does NOT try to be exhaustive per-topic.

- Reads search queries from `{scratch-dir}/scope.md` (written by EM during scoping)
- Executes queries via WebSearch
- Mechanically vets each result via WebFetch: accessible? paywall? date? source type?
- Writes corpus to `{scratch-dir}/source-corpus.md`
- **No messaging** — scout has no SendMessage tool. Task completion is the only signal.
- **Timing:** No floor. Ceiling: 3 minutes. This is mechanical work — go fast.

## Message Protocol

### Specialist → Specialist (Cross-Pollination)

Send targeted messages to specific peers by name:

| Category | Format | When |
|---|---|---|
| **FINDING** | `"Finding for {peer}: {brief}. Source: {URL}. Relevant because {reason}."` | A discovery relevant to another specialist's topic |
| **CONTRADICTION** | `"Contradiction with {peer}: I found {X} but your area suggests {Y}. Can you verify?"` | Sources disagree across topics |
| **CHALLENGE** | `"Challenge to {peer}: Your finding {X} conflicts with {Y} from {source}. Which is current?"` | Direct factual conflict |
| **SOURCE** | `"Source for {peer}: {URL} — covers {aspect} relevant to your topic."` | Useful source for a peer |

### Specialist → Synthesizer (Wake-Up Signal)

`blockedBy` is a status gate, not an event trigger — completing a blocker task does NOT automatically wake the blocked teammate. Specialists must explicitly message the synthesizer after completing their task:

| Category | Format | When |
|---|---|---|
| **DONE** | `"DONE: {topic-letter} findings written to {output-file}"` | After marking own task `completed` |

This is the synthesizer's wake-up mechanism. Each DONE message causes the synthesizer to re-check `TaskList`. When all specialist tasks show `completed`, it proceeds with synthesis.

### Volume Governance

- **Peer messages: max 3 per peer** (max 12 total for a 5-specialist team)
- **DONE message: exactly 1 per specialist** (sent to synthesizer only)
- **Scout: no messages** (task completion handles unblocking)
- Quality over quantity

## Self-Governance Timing

Specialists manage their own timing. No EM broadcasts WRAP_UP.

### Three-Part Model

1. **Floor (minimum before convergence allowed)**
   - Must have fetched at least `MIN_SOURCES` sources AND worked for at least `MIN_MINUTES` minutes
   - Both conditions must be met — prevents "fast 3 sources in 2 minutes" thin convergence
   - Defaults: 5 sources, 5 minutes

2. **Diminishing Returns (between floor and ceiling)**
   - After the floor, self-assess after each source: "Did this add new verified findings?"
   - If last 3 consecutive sources added no new verified findings → convergence signal
   - Note in Investigation Log: "Converging: diminishing returns after source N"

3. **Ceiling (maximum research time)**
   - Configurable by the EM at team creation (defaults: 15 minutes)
   - Begin convergence regardless of state
   - Check time via `date +%s` in Bash, compare against spawn timestamp

### Clock Mechanism

Spawn timestamp is provided in the specialist prompt as `[SPAWN_TIMESTAMP]` (Unix epoch seconds). Specialists check elapsed time via `date +%s` in Bash at each source-fetch cycle and compare.

## Convergence Protocol

Begin convergence when ANY of these conditions are met (AND the floor is satisfied):
- At least `MIN_SOURCES` verified sources and contradictions addressed
- Last 3 sources added no new findings (diminishing returns)
- Ceiling time reached

**Steps:**
1. Send `CONVERGING` to all peers
2. Wait ~30 seconds for final challenges
3. Answer any challenges
4. Write complete output file
5. Mark task `completed`
6. Send `DONE` to synthesizer (wake-up signal)

**Early convergence note:** Specialists who converge early remain alive — late-arriving peer messages may warrant a quick update to findings before the agent terminates.

**Timeout:** If a CHALLENGE goes unanswered for 2 minutes → mark finding as `[UNVERIFIED]`.

## Failure Handling

- **Scout fails (no corpus):** Specialists fall back to self-directed discovery (full WebSearch workflow)
- **Scout times out (partial corpus):** Specialists use what's there + supplement with own searches
- **Self-timed convergence (ceiling):** Specialists begin convergence autonomously after max time, without EM intervention
- **WebSearch/WebFetch failures:** If 3 consecutive fetch attempts fail, converge with what you have and note failures in Investigation Log
- **All specialists fail:** EM is notified (no completed specialist tasks), reports to PM

## Scratch Directory

`tasks/scratch/deep-research-teams/{run-id}/`

- Scout writes to: `{scratch-dir}/source-corpus.md`
- Each specialist writes to: `{scratch-dir}/{topic-letter}-findings.md`
- Synthesizer writes advisory to: `{output-path}-advisory.md` (+ backup at `{scratch-dir}/advisory.md`); omitted if nothing beyond scope
