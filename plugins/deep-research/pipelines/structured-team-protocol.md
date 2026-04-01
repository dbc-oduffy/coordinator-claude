# Deep Research Structured Team Protocol

> Referenced by agent definitions and `structured.md` command.

## Overview

Agent Teams-based structured research: the EM reads a spec YAML, pre-processes it into a scout brief, creates a team of a Haiku scout + Sonnet verifiers + an Opus synthesizer, spawns all teammates, and is **freed**. The team handles everything autonomously — spec-driven source discovery, schema-mapped verification, cross-topic reconciliation, and schema-conforming output. The EM is notified when synthesis completes, validates schema conformance, then cleans up.

Pipeline C is spec-driven and schema-conforming. Unlike Pipeline A (free-form internet research), every finding maps to an output schema field, every verifier self-checks acceptance criteria and gate rules embedded in their prompts, and the final output is validated against the spec before the team is torn down.

## Team Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** | Haiku | 1 | Execute spec-derived search queries from scout-brief.md, map findings to schema fields, write per-topic discovery files |
| **Verifier** | Sonnet | 1-5 | Verify scout's per-topic discovery, compare against existing data, produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED), self-check acceptance criteria and gate rules |
| **Synthesizer** | Opus | 1 | Cross-topic reconciliation, schema validation, produce YAML/JSON output conforming to output_schema |

## Team Lifecycle

```
EM: Read spec → pre-process into scout-brief.md → Create team → Spawn all teammates → FREED
Scout: Read scout-brief.md → WebSearch → WebFetch (vet accessibility) → Map to schema fields → Write per-topic discovery files → Mark complete → [idle]
Verifiers: [blocked by scout] → Read discovery files → Verify + compare existing data → Produce schema field tables → Self-check gate rules → Converge → Mark complete → DONE to synthesizer
Synthesizer: [blocked by verifiers, waiting for DONE msgs] → Verify all complete → Cross-reconcile → Validate schema → Write YAML/JSON output → Mark complete
```

## Blocking Chain

```
Scout (no blockers) ──────→ task completion unblocks verifiers
Verifiers (blockedBy: scout) ──→ DONE messages wake synthesizer
Synthesizer (blockedBy: all verifiers) ──→ mark complete notifies EM
```

- **Scout → Verifiers:** Task-gated via `blockedBy`. Verifiers unblock when scout marks its task complete. No messaging needed — verifiers haven't started yet (confirmed empirically 2026-03-21).
- **Verifiers → Synthesizer:** Task-gated via `blockedBy` + DONE messages as wake-up signals. The synthesizer is already running but idle — it needs explicit DONE messages to trigger its next poll cycle (confirmed empirically 2026-03-21).

### How Agent Teams Blocking Actually Works (empirical + sourced)

Agent Teams uses **file-based polling, not callbacks**. Task state is managed by the platform in `~/.claude/tasks/{team-name}/N.json` (platform-internal; do not read/write these files directly). Agents discover available work by calling `TaskList()`, which re-evaluates `blockedBy` arrays fresh on each call. There is no active push/callback when a blocker completes.

**Two distinct scenarios with different wake-up behavior:**

| Scenario | Agent State | Wake-Up Mechanism | Message Needed? |
|----------|-------------|-------------------|-----------------|
| **Task-blocked (pending)** | Not yet started — `pending` status, waiting for blockers | `TaskList()` re-evaluates `blockedBy` on next poll; agent auto-starts when unblocked | No — auto-wake works |
| **Message-blocked (idle)** | Started, checked status, went idle waiting | Needs an inbox message to trigger the next poll cycle | Yes — explicit DONE message required |

The scout→verifier transition is scenario 1 (auto-wake). The verifier→synthesizer transition is scenario 2 (DONE messages needed). Both confirmed empirically 2026-03-21.

**Shutdown behavior:** Teammates prioritize completing their current work loop over acknowledging shutdown requests. Expect convergence protocol (CONVERGING → wait → write → mark complete → DONE) to run before shutdown acknowledgment. This is good for data integrity but means team teardown takes 30-60 seconds after shutdown requests are sent.

**Sources:** [Claude Code official docs](https://code.claude.com/docs/en/agent-teams), [reverse-engineering analysis (nwyin.com)](https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered.html), [swarm orchestration guide (kieranklaassen gist)](https://gist.github.com/kieranklaassen/4f2aba89594a4aea4ad64d753984b2ea).

## Scout Protocol

The scout builds **per-topic discovery files** — schema-mapped findings, one file per topic. It does NOT try to produce finished analysis.

- Reads topic queries and schema field mappings from `{scratch-dir}/scout-brief.md` (written by EM during pre-processing)
- Executes queries via WebSearch
- Mechanically vets each result via WebFetch: accessible? paywall? date? source type?
- Maps each finding to schema fields (as listed in scout-brief.md)
- Writes one discovery file per topic: `{scratch-dir}/{subject}-scout-{topic_id}.md`
- **No messaging** — scout has no SendMessage tool. Task completion is the only signal.
- **Timing:** No floor. Ceiling: 3 minutes. This is mechanical work — go fast.

## Message Protocol

### Verifier → Verifier (Cross-Pollination)

Send targeted messages to specific peers by name:

| Category | Format | When |
|---|---|---|
| **FINDING** | `"Finding for {peer}: {brief}. Source: {URL}. Schema field: {field_name}. Relevant because {reason}."` | A discovery relevant to another verifier's topic or schema field |
| **CONTRADICTION** | `"Contradiction with {peer}: I found {X} for field {field_name} but your area suggests {Y}. Can you verify?"` | Sources disagree on a schema field value across topics |
| **CHALLENGE** | `"Challenge to {peer}: Your finding {X} for field {field_name} conflicts with {Y} from {source}. Which is current?"` | Direct factual conflict on a schema field |
| **SOURCE** | `"Source for {peer}: {URL} — covers {aspect} relevant to your topic / field {field_name}."` | Useful source for a peer's topic or schema field |

### Verifier → Synthesizer (Wake-Up Signal)

`blockedBy` is a status gate, not an event trigger — completing a blocker task does NOT automatically wake the blocked teammate. Verifiers must explicitly message the synthesizer after completing their task:

| Category | Format | When |
|---|---|---|
| **DONE** | `"DONE: {topic_id} findings written to {scratch-dir}/{topic_id}-findings.md"` | After marking own task `completed` |

This is the synthesizer's wake-up mechanism. Each DONE message causes the synthesizer to re-check `TaskList`. When all verifier tasks show `completed`, it proceeds with synthesis.

### Volume Governance

- **Peer messages: max 3 per peer** (max 12 total for a 5-verifier team)
- **DONE message: exactly 1 per verifier** (sent to synthesizer only)
- **Scout: no messages** (task completion handles unblocking)
- Quality over quantity

## Self-Governance Timing

Verifiers manage their own timing. No EM broadcasts WRAP_UP.

### Three-Part Model

1. **Floor (minimum before convergence allowed)**
   - Must have fetched at least `MIN_SOURCES` sources AND worked for at least `MIN_MINUTES` minutes
   - Both conditions must be met — prevents "fast 3 sources in 2 minutes" thin convergence
   - Defaults: 5 sources, 5 minutes

2. **Diminishing Returns (between floor and ceiling)**
   - After the floor, self-assess after each source: "Did this add new verified schema field values?"
   - If last 3 consecutive sources added no new verified findings → convergence signal
   - Note in Investigation Log: "Converging: diminishing returns after source N"

3. **Ceiling (maximum research time)**
   - Configurable by the EM at team creation (default: 15 minutes)
   - Begin convergence regardless of state
   - Check time via `date +%s` in Bash, compare against spawn timestamp

### Clock Mechanism

Spawn timestamp is provided in the verifier prompt as `[SPAWN_TIMESTAMP]` (Unix epoch seconds). Verifiers check elapsed time via `date +%s` in Bash at each source-fetch cycle and compare.

## Convergence Protocol

Begin convergence when ANY of these conditions are met (AND the floor is satisfied):
- At least `MIN_SOURCES` verified sources and contradictions addressed
- Last 3 sources added no new schema field findings (diminishing returns)
- Ceiling time reached

**Steps:**
1. **Self-check acceptance criteria** — verify minimum sources met and required schema fields covered
2. **Self-check gate rules** — verify embedded quality gate rules pass (e.g., source recency, source type requirements)
3. Send `CONVERGING` to all peers
4. Wait ~30 seconds for final challenges
5. Answer any challenges
6. Write complete output file (schema field table with change types)
7. Mark task `completed`
8. Send `DONE` to synthesizer (wake-up signal)

**Early convergence note:** Verifiers who converge early remain alive — late-arriving peer messages may warrant a quick update to findings before the agent terminates.

**Timeout:** If a CHALLENGE goes unanswered for 2 minutes → mark finding as `[UNVERIFIED]`.

## Output Format

### Scout Output (per topic)

`{scratch-dir}/{subject}-scout-{topic_id}.md`:
```markdown
# Scout Discovery: {TOPIC_NAME}

## Sources Found

| URL | Title | Date | Type | Accessible | Schema Fields |
|-----|-------|------|------|------------|---------------|
| ... | ...   | ...  | ...  | yes/no     | field_a, field_b |

## Raw Findings by Schema Field

**{field_name}:** {raw finding} [Source: URL]
...
```

### Verifier Output (per topic)

`{scratch-dir}/{topic_id}-findings.md`:
```markdown
# Verifier Findings: {TOPIC_NAME}

## Schema Field Table

| Field | Change Type | New Value | Previous Value | Source | Confidence |
|-------|-------------|-----------|----------------|--------|------------|
| ...   | CONFIRMED   | ...       | ...            | URL    | high       |
| ...   | UPDATED     | ...       | ...            | URL    | medium     |
| ...   | NEW         | ...       | n/a            | URL    | high       |
| ...   | REFUTED     | n/a       | ...            | URL    | high       |

## Gate Rule Self-Check
- {Gate rule 1}: PASS / FAIL — {evidence}
- {Gate rule 2}: PASS / FAIL — {evidence}

## Acceptance Criteria Self-Check
- Minimum sources: {N} / {MIN_SOURCES} required — PASS / FAIL
- Required schema fields covered: {list} — PASS / FAIL
```

## Failure Handling

- **Scout fails (no discovery files):** Verifiers fall back to self-directed discovery using focus questions from scout-brief.md (full WebSearch workflow)
- **Scout times out (partial discovery files):** Verifiers use what's there + supplement with own searches for missing topics
- **Self-timed convergence (ceiling):** Verifiers begin convergence autonomously after max time, without EM intervention
- **WebSearch/WebFetch failures:** If 3 consecutive fetch attempts fail, converge with what you have and note failures in Investigation Log
- **Gate rule failure at convergence:** Note in output as `GATE_FAIL: {rule}` — verifier still completes and sends DONE; synthesizer and EM handle escalation
- **All verifiers fail:** EM is notified (no completed verifier tasks), reports to PM

## Scratch Directory

`tasks/scratch/deep-research-teams/{run-id}/`

- Scout writes to: `{scratch-dir}/{subject}-scout-{topic_id}.md` (one per topic)
- Each verifier writes to: `{scratch-dir}/{topic_id}-findings.md` (schema field tables)
- Synthesizer writes to: `{scratch-dir}/synthesis-output.yaml` (or `.json`)
