# Deep Research Team Protocol (v2.1)

> Referenced by agent definitions and `web.md` command.

## Overview

Agent Teams-based deep research: the EM scopes research and crafts search queries, creates a team of a Haiku scout + Sonnet specialists + Opus sweep agent, spawns all teammates, and is **freed**. The team handles everything autonomously — source discovery, analysis, adversarial cross-pollination, and synthesis. The EM is notified when the sweep completes.

## Team Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** | Haiku | 1 | Execute EM-crafted search queries, mechanically vet accessibility, build shared source corpus |
| **Specialist** | Sonnet | up to 5 | Deep-read sources from corpus, verify claims, challenge peers (adversarial), coordinate ownership of overlapping topics, output structured claims JSON + markdown summary |
| **Sweep** | Opus | 1 | Read all specialist outputs directly, adversarial coverage check, fill negative space via web research, write executive summary and conclusion; may go beyond original scope where judgment warrants |

## Team Lifecycle

```
EM: Scope + craft queries → write scope.md → Create team → Spawn all teammates → FREED
Scout: Read scope.md → WebSearch → WebFetch (vet accessibility) → Write source-corpus.md → Mark complete → [idle]
Specialists: [blocked by scout] → Read corpus → Deep-read → Challenge peers → Converge → Write claims.json + summary.md → Mark complete → DONE to sweep
Sweep: [blocked by specialists, waiting for DONE msgs] → Read all specialist outputs → Phase 1: Assess → Phase 2: Fill gaps → Phase 3: Frame → Mark complete
```

## Blocking Chain

```
Scout (no blockers) ──────────────→ task completion unblocks specialists
Specialists (blockedBy: scout) ───→ DONE messages wake sweep
Sweep (blockedBy: all specialists) → mark complete notifies EM
```

- **Scout → Specialists:** Task-gated via `blockedBy`. Specialists unblock when scout marks its task complete. No messaging needed — specialists haven't started yet.
- **Specialists → Sweep:** Task-gated via `blockedBy` + DONE messages as wake-up signals. The sweep is already running but idle — it needs explicit DONE messages to trigger its next poll cycle.

### How Agent Teams Blocking Actually Works (empirical + sourced)

Agent Teams uses **file-based polling, not callbacks**. Task state is managed by the platform in `~/.claude/tasks/{team-name}/N.json` (platform-internal; do not read/write these files directly). Agents discover available work by calling `TaskList()`, which re-evaluates `blockedBy` arrays fresh on each call. There is no active push/callback when a blocker completes.

**Two distinct scenarios with different wake-up behavior:**

| Scenario | Agent State | Wake-Up Mechanism | Message Needed? |
|----------|-------------|-------------------|-----------------|
| **Task-blocked (pending)** | Not yet started — `pending` status, waiting for blockers | `TaskList()` re-evaluates `blockedBy` on next poll; agent auto-starts when unblocked | No — auto-wake works |
| **Message-blocked (idle)** | Started, checked status, went idle waiting | Needs an inbox message to trigger the next poll cycle | Yes — explicit message required |

The scout→specialist transition is scenario 1 (auto-wake). The specialist→sweep transition is scenario 2 (messages needed).

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

### Specialist → Specialist (Adversarial Cross-Pollination)

Send targeted messages to specific peers by name. Challenges are **expected**, not just permitted — specialists should actively test each other's claims.

| Category | Format | When |
|---|---|---|
| **FINDING** | `"Finding for {peer}: {brief}. Source: {URL}. Relevant because {reason}."` | A discovery relevant to another specialist's topic |
| **CONTRADICTION** | `"Contradiction with {peer}: I found {X} but your area suggests {Y}. Can you verify?"` | Sources disagree across topics |
| **CHALLENGE** | `"Challenge to {peer}: Your finding {X} conflicts with {Y} from {source}. Which is current?"` | Direct factual conflict — resolution expected |
| **SOURCE** | `"Source for {peer}: {URL} — covers {aspect} relevant to your topic."` | Useful source for a peer |
| **OVERLAP** | `"Overlap with {peer}: I'm also covering {X}. Should I defer or should you?"` | Coordinate ownership of shared territory |

**Resolution protocol:** When a peer challenges a claim, the challenged specialist must respond with evidence or concede. Unresolved challenges (2-minute timeout) produce `[CONTESTED]` claims in structured output with both sides' evidence.

### Specialist → Sweep (Wake-Up Signal)

`blockedBy` is a status gate, not an event trigger — completing a blocker task does NOT automatically wake the blocked teammate. Specialists must explicitly message the sweep after completing their task:

| Category | Format | When |
|---|---|---|
| **DONE** | `"DONE: {topic-letter} findings written to {scratch-dir}/{topic-letter}-claims.json and {topic-letter}-summary.md"` | After marking own task `completed` |

Each DONE message causes the sweep to re-check `TaskList`. When all specialist tasks show `completed`, it proceeds.

### Volume Governance

- **Peer messages: max 3 per peer** (max 12 total for a 5-specialist team)
- **DONE message: exactly 1 per specialist** (sent to sweep only)
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
4. Write complete output files (claims.json + summary.md)
5. Mark task `completed`
6. Send `DONE` to sweep (wake-up signal)

**Early convergence note:** Specialists who converge early remain alive — late-arriving peer messages may warrant a quick update to findings before the agent terminates.

**Timeout:** If a CHALLENGE goes unanswered for 2 minutes → mark claim as `[CONTESTED]` with both sides' evidence.

## Failure Handling

- **Scout fails (no corpus):** Specialists fall back to self-directed discovery (full WebSearch workflow)
- **Scout times out (partial corpus):** Specialists use what's there + supplement with own searches
- **Self-timed convergence (ceiling):** Specialists begin convergence autonomously after max time, without EM intervention
- **WebSearch/WebFetch failures:** If 3 consecutive fetch attempts fail, converge with what you have and note failures in Investigation Log
- **Sweep fails:** EM reads raw specialist outputs from `{scratch-dir}/*-claims.json` and `*-summary.md` and presents to PM
- **All specialists fail:** EM is notified (no completed specialist tasks), reports to PM

## Scratch Directory

`tasks/scratch/deep-research-teams/{run-id}/`

- Scout writes to: `{scratch-dir}/source-corpus.md`
- Each specialist writes to: `{scratch-dir}/{topic-letter}-claims.json` + `{scratch-dir}/{topic-letter}-summary.md`
- Sweep writes synthesis to: `{output-path}` + `{scratch-dir}/synthesis.md`
- Sweep writes advisory to: `{advisory-path}` + `{scratch-dir}/advisory.md` (optional — omitted if nothing beyond scope)

## Deepening Protocol (v2.2)

When Team 1's sweep identifies significant coverage gaps, the EM may dispatch a smaller Team 2 for targeted follow-up. This is the deepening protocol.

### Team 2 Composition

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** (optional) | Haiku | 0-1 | Only if gap targets require new topic areas not in Team 1's corpus |
| **Gap-Specialist** | Sonnet | 1-3 | One per gap cluster. Fill specific gaps from Team 1's gap report |
| **Sweep** | Opus | 1 | Merge mode — produce delta document, not full synthesis |

Team size: 2-5 teammates (well under the 7 ceiling).

### Team 2 Lifecycle

```
EM: Read gap-report.md → Cluster gaps → Create Team 2 → Spawn → FREED
Scout (if any): New queries → gap-corpus.md → Mark complete → [idle]
Gap-Specialists: [blocked by scout if any] → Read prior findings → Targeted research → Converge → D-{letter}-claims.json + D-{letter}-summary.md → DONE to sweep
Sweep: [blocked by gap-specialists] → Read Team 1 synthesis + gap-specialist outputs → Delta → deepening-delta.md → Mark complete
```

### Team 2 Blocking Chain

```
Scout (if any) ──→ task completion unblocks gap-specialists
Gap-Specialists ──→ DONE messages wake sweep
Sweep ──────────→ mark complete notifies EM
```

Same mechanics as Team 1: task-gated blocking for scout→specialists, explicit DONE messages for specialists→sweep.

### Team 2 Timing

Gap-specialists use tighter timing than Team 1 specialists because their scope is narrower:

| Parameter | Team 1 Specialist | Team 2 Gap-Specialist |
|-----------|------------------|----------------------|
| Floor (minutes) | 5 | 3 |
| Floor (sources) | 5 | 3 |
| Ceiling (minutes) | 15 | 8 |
| Diminishing returns | 3 consecutive | 2 consecutive |
| Peer messages per peer | 3 | 2 |

### Team 2 Output

Gap-specialists write to `D-{letter}-claims.json` and `D-{letter}-summary.md` (D- prefix distinguishes from Team 1). The sweep operates in merge mode and writes `deepening-delta.md` — a structured delta that the EM integrates into Team 1's synthesis.

### Depth Limit

**Maximum two passes.** Team 1 + Team 2. No further iteration. Team 2's sweep may still identify remaining gaps — these go into the "Open Questions" section of the final document, not into a Team 3.

### Failure Handling

Team 2 failure is **non-blocking**. Team 1 already produced a complete document. If Team 2 fails entirely (all gap-specialists crash, sweep doesn't complete), the EM proceeds to finalization with Team 1's synthesis as-is. The deepening pass is an improvement opportunity, not a requirement.
