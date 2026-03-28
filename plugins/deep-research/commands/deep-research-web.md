---
description: "Pipeline A (Internet Research) using Agent Teams — collaborative research with a Haiku scout, Sonnet specialists, a Sonnet consolidator, and an Opus sweep agent, all as teammates. EM scopes research, spawns the team, and is freed. The team handles everything autonomously."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<topic>"
---

# Deep Research — Pipeline A (Internet Research) Agent Teams Driver

The EM scopes the research, creates a team, spawns all teammates, and is **freed**. The team works autonomously:
- **Haiku scout** (1) — executes EM-crafted search queries, builds a shared source corpus
- **Sonnet specialists** (3-4) — blocked until scout completes, then deep-read from the corpus, verify, cross-pollinate
- **Sonnet consolidator** (1) — blocked until all specialists complete, then merges their outputs into a single deduped document with cross-topic connections flagged
- **Opus sweep** (1) — blocked until consolidator completes, then reads the combined findings, identifies negative space, fills gaps with targeted research, writes executive summary and conclusion

The scout handles mechanical source discovery. Specialists self-govern their timing and actively coordinate to avoid duplication. The consolidator produces a single aligned document. The Opus sweep does the judgment work — filling gaps the specialists couldn't see and framing the whole thing. The EM does not monitor or broadcast WRAP_UP.

## Arguments

`$ARGUMENTS`:
- `<topic>` — the research topic (required)
- Additional context may follow the topic as free text

## Step 1 — Setup

1. Parse arguments: extract research topic
2. Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp)
3. Record spawn timestamp: `date +%s` (Unix epoch seconds — passed to teammates for timing)
4. Generate topic slug (e.g., `novel-claude-code-implementations`)
5. Create scratch directory:
   ```bash
   mkdir -p tasks/scratch/deep-research-teams/{run-id}
   ```
6. Set output path: `docs/research/YYYY-MM-DD-{topic-slug}.md`
7. Set advisory path: `docs/research/YYYY-MM-DD-{topic-slug}-advisory.md` (replace `.md` with `-advisory.md`)

Announce: "Running deep research (Agent Teams) on '{topic}'."

## Step 2 — Scope Research (EM Direct)

This is judgment work — the EM does it directly:

1. Define 3-4 topic areas to investigate
2. Write focus questions for each topic
3. List any known sources
4. Note cross-cutting themes between topics
5. **Craft search queries for the scout** — for each topic area, write 3-5 suggested search queries:
   - Varied phrasings targeting different source types (docs, blogs, repos, forums)
   - Include 1-2 adversarial queries per topic ("X problems", "X limitations", "why not X")
   - Cross-cutting queries that span multiple topics
   - These are starting suggestions, not exhaustive instructions — the scout runs them mechanically
6. **Ask the PM for timing preferences:**
   > "Research timing: default is 5-15 min with 5-source minimum. For a trivial topic, I'd suggest 3-8 min / 3 sources. For a complex topic, 5-20 min / 5 sources. What ceiling works for you?"

Cap at 4 topics (team size constraint: 1 scout + 4 specialists + 1 consolidator + 1 sweep = 7 teammates). Write scope AND search queries to `{scratch-dir}/scope.md`.

## Step 3 — Create Team and All Tasks

### Create Team

```
TeamCreate(team_name: "research-{topic-slug}")
```

### Create Tasks (explicit ordering — blocking chain depends on this)

**Order matters.** Task IDs from earlier steps are referenced in later steps.

**1. Sweep task** (created first — will be blocked later):
```
TaskCreate(subject: "Sweep: fill gaps, write framing", description: "Read combined findings from {scratch-dir}/combined-findings.md, identify negative space, fill gaps via web research, write exec summary + conclusion to {output-path}")
```

**2. Consolidator task** (created second — will be blocked later):
```
TaskCreate(subject: "Consolidate specialist findings", description: "Read all specialist outputs from {scratch-dir}/, deduplicate, flag cross-topic connections, write combined document to {scratch-dir}/combined-findings.md")
```

**3. Scout task** (no blockers — reads queries from disk):
```
TaskCreate(subject: "Build shared source corpus", description: "Read search queries from {scratch-dir}/scope.md, execute via WebSearch, vet accessibility via WebFetch, write corpus to {scratch-dir}/source-corpus.md")
```

**4. Specialist tasks** (each blocked by scout):
For each topic:
```
TaskCreate(subject: "Analyze topic {letter}: {description}", description: "...")
TaskUpdate(taskId: "{specialist-id}", addBlockedBy: ["{scout-task-id}"])
```

**5. Block consolidator on all specialists:**
```
TaskUpdate(taskId: "{consolidator-id}", addBlockedBy: ["{specialist-A-id}", "{specialist-B-id}", ...])
```

**6. Block sweep on consolidator:**
```
TaskUpdate(taskId: "{sweep-id}", addBlockedBy: ["{consolidator-id}"])
```

## Step 4 — Spawn All Teammates

### Scout (Haiku)

Read the scout prompt template from:
`~/.claude/plugins/oduffy-custom/deep-research/pipelines/scout-prompt-template.md`

Fill in template fields: `[RESEARCH_TOPIC]`, `[PROJECT_CONTEXT]`, `[SCRATCH_DIR]`, `[TASK_ID]`, `[SPAWN_TIMESTAMP]`.

```
Agent(
  team_name: "research-{topic-slug}",
  name: "scout",
  model: "haiku",
  subagent_type: "deep-research:research-scout",
  prompt: <filled scout prompt>
)
TaskUpdate(taskId: "{scout-id}", owner: "scout")
```

### Specialists (Sonnet)

For each topic area, read the specialist prompt template from:
`~/.claude/plugins/oduffy-custom/deep-research/pipelines/specialist-prompt-template.md`

Fill in ALL template fields — including `[CONSOLIDATOR_NAME]` (use `"consolidator"` as the teammate name). This is how specialists know who to send the `DONE` wake-up message to.

```
Agent(
  team_name: "research-{topic-slug}",
  name: "topic-{letter}",
  model: "sonnet",
  subagent_type: "deep-research:research-specialist",
  prompt: <filled specialist prompt>
)
TaskUpdate(taskId: "{id}", owner: "topic-{letter}")
```

### Consolidator (Sonnet)

Read the consolidator prompt template from:
`~/.claude/plugins/oduffy-custom/deep-research/pipelines/consolidator-prompt-template.md`

Fill in template fields: `[RESEARCH_QUESTION]`, `[PROJECT_CONTEXT]`, `[SPECIALIST_COUNT]`, `[SPECIALIST_LIST]`, `[SWEEP_NAME]` (use `"sweep"`), `[SCRATCH_DIR]`, `[TASK_ID]`.

```
Agent(
  team_name: "research-{topic-slug}",
  name: "consolidator",
  model: "sonnet",
  subagent_type: "deep-research:research-consolidator",
  prompt: <filled consolidator prompt>
)
TaskUpdate(taskId: "{consolidator-id}", owner: "consolidator")
```

### Opus Sweep

Spawn the sweep agent with its task (which is blocked until consolidator finishes):
```
Agent(
  team_name: "research-{topic-slug}",
  name: "sweep",
  model: "opus",
  subagent_type: "deep-research:research-synthesizer",
  prompt: <filled sweep prompt — see below>
)
TaskUpdate(taskId: "{sweep-id}", owner: "sweep")
```

**Sweep prompt** should include:
- The research question and project context
- The scratch directory path: `{scratch-dir}`
- The output path for the final document: `{output-path}`
- The advisory output path: `{advisory-path}` (pre-computed in Step 1)
- The sweep task ID to mark complete when done
- Instruction: "Read the combined findings at {scratch-dir}/combined-findings.md. Follow your agent definition's three phases: assess, fill negative space, frame. You have WebSearch and WebFetch for gap-filling research. Write the final document to {output-path} and {scratch-dir}/synthesis.md. Write advisory to {advisory-path} and {scratch-dir}/advisory.md if you have observations beyond scope. If nothing beyond scope, note 'No advisory' in your completion message. You are explicitly encouraged to go beyond the original research scope where your judgment says it's warranted."

Dispatch ALL teammates in a single message (parallel).

## Step 5 — EM Is Freed

After spawning all teammates, announce:

> "Research team is running autonomously on '{topic}' with 1 scout + {N} specialists + 1 consolidator + 1 Opus sweep. Scout builds the shared corpus (~2-3 min), then specialists deep-read and cross-pollinate ({MIN_MINUTES}-{MAX_MINUTES} min, {MIN_SOURCES}-source minimum). After specialists finish, the consolidator merges and deduplicates their outputs, then the Opus sweep fills gaps and frames the final document. I'm available for other work — I'll be notified when the sweep completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not broadcast WRAP_UP. The team handles everything.

## Step 6 — On Completion Notification

When you receive a notification that the sweep task is complete:

1. Read the synthesis document at `{output-path}`
2. Verify it has substantive content (not just headers)
3. Check for advisory: `test -f {advisory-path}` — if the file exists, read it
4. Commit:
   ```bash
   git add -A && git commit -m "deep-research: complete — {topic-slug}"
   ```
4. Archive paper trail:
   ```bash
   mkdir -p docs/research/archive/YYYY-MM-DD-{topic-slug}
   cp -r {scratch-dir}/* docs/research/archive/YYYY-MM-DD-{topic-slug}/
   rm -rf {scratch-dir}
   ```
5. Shut down the team: `TeamDelete(team_name: "research-{topic-slug}")`
6. Commit: `git add -A && git commit -m "deep-research: archive + cleanup"`
7. Present executive summary to PM for discussion. If advisory exists, mention it: "The sweep agent flagged observations beyond scope — see the advisory at `{advisory-path}`."

## Error Handling

| Failure | Action |
|---------|--------|
| Scout fails (no corpus written) | Specialists fall back to self-directed discovery (existing behavior) — the corpus is optional, not required |
| Scout times out (partial corpus) | Specialists use what's there + supplement with own searches |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and marks task complete |
| Consolidator doesn't wake after all specialists complete | Verify specialists sent DONE messages to consolidator; if not, send manual nudge via SendMessage |
| Sweep doesn't wake after consolidator completes | Send manual nudge to sweep. If still stalled after 5 min, EM reads combined-findings.md for PM |
| All specialists fail | TeamDelete, report to PM |
| Team creation fails | Fall back to relay pattern or manual research |
