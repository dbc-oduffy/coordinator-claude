---
description: "Pipeline A (Internet Research) using Agent Teams — collaborative research with a Haiku scout, Sonnet specialists, and an Opus synthesizer, all as teammates. EM scopes research, spawns the team, and is freed. The team handles everything autonomously."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<topic>"
---

# Deep Research — Pipeline A (Internet Research) Agent Teams Driver

The EM scopes the research, creates a team, spawns all teammates, and is **freed**. The team works autonomously:
- **Haiku scout** (1) — executes EM-crafted search queries, builds a shared source corpus
- **Sonnet specialists** (3-5) — blocked until scout completes, then deep-read from the corpus, verify, cross-pollinate
- **Opus synthesizer** (1) — blocked until all specialists complete, then reads their outputs and writes the final document

The scout handles mechanical source discovery so specialists can focus on analysis. Specialists self-govern their timing (floor, diminishing returns, ceiling). The EM does not monitor or broadcast WRAP_UP. When the synthesizer marks its task complete, the EM receives a notification and does quick cleanup.

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

1. Define 3-5 topic areas to investigate
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

Cap at 5 topics (team size constraint: 1 scout + 5 specialists + 1 synthesizer = 7 teammates). Write scope AND search queries to `{scratch-dir}/scope.md`.

## Step 3 — Create Team and All Tasks

### Create Team

```
TeamCreate(team_name: "research-{topic-slug}")
```

### Create Tasks (explicit ordering — blocking chain depends on this)

**Order matters.** Task IDs from earlier steps are referenced in later steps.

**1. Synthesizer task** (created first — will be blocked later):
```
TaskCreate(subject: "Synthesize all findings into final document", description: "Read all specialist outputs from {scratch-dir}/, cross-reference, resolve contradictions, write synthesis to {output-path} and {scratch-dir}/synthesis.md")
```

**2. Scout task** (no blockers — reads queries from disk):
```
TaskCreate(subject: "Build shared source corpus", description: "Read search queries from {scratch-dir}/scope.md, execute via WebSearch, vet accessibility via WebFetch, write corpus to {scratch-dir}/source-corpus.md")
```

**3. Specialist tasks** (each blocked by scout):
For each topic:
```
TaskCreate(subject: "Analyze topic {letter}: {description}", description: "...")
TaskUpdate(taskId: "{specialist-id}", addBlockedBy: ["{scout-task-id}"])
```

**4. Block synthesizer on all specialists:**
```
TaskUpdate(taskId: "{synthesizer-id}", addBlockedBy: ["{specialist-A-id}", "{specialist-B-id}", ...])
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

Fill in ALL template fields — including `[SYNTHESIZER_NAME]` (use `"synthesizer"` as the teammate name). This is how specialists know who to send the `DONE` wake-up message to.

Fill in the template and spawn:
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

### Synthesizer (Opus)

Spawn the synthesizer with its task (which is blocked until specialists finish):
```
Agent(
  team_name: "research-{topic-slug}",
  name: "synthesizer",
  model: "opus",
  subagent_type: "deep-research:research-synthesizer",
  prompt: <filled synthesis prompt — see below>
)
TaskUpdate(taskId: "{synthesis-id}", owner: "synthesizer")
```

**Synthesis prompt** should include:
- The research question and project context
- The scratch directory path (where specialist outputs will be): `{scratch-dir}`
- The output path for the final document: `{output-path}`
- The advisory output path: `{advisory-path}` (pre-computed in Step 1 — do not ask the synthesizer to derive it)
- The synthesis task ID to mark complete when done
- Instruction: "Read all {scratch-dir}/*-findings.md files, cross-reference, resolve contradictions, and write the synthesis document. Follow your agent definition's output format and principles. After synthesis, write an advisory if you have substantive observations beyond the scope (see advisory template in your agent definition). Write advisory to both {advisory-path} AND {scratch-dir}/advisory.md. If nothing beyond scope, skip and note 'No advisory' in your completion message."

Dispatch ALL teammates in a single message (parallel).

## Step 5 — EM Is Freed

After spawning all teammates, announce:

> "Research team is running autonomously on '{topic}' with 1 scout + {N} specialists + 1 synthesizer. Scout builds the shared corpus (~2-3 min), then specialists deep-read and cross-pollinate ({MIN_MINUTES}-{MAX_MINUTES} min, {MIN_SOURCES}-source minimum). I'm available for other work — I'll be notified when the synthesizer completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not broadcast WRAP_UP. The team handles everything.

## Step 6 — On Completion Notification

When you receive a notification that the synthesis task is complete:

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
7. Present executive summary to PM for discussion. If advisory exists, mention it: "The synthesizer flagged observations beyond scope — see the advisory at `{advisory-path}`."

## Error Handling

| Failure | Action |
|---------|--------|
| Scout fails (no corpus written) | Specialists fall back to self-directed discovery (existing behavior) — the corpus is optional, not required |
| Scout times out (partial corpus) | Specialists use what's there + supplement with own searches |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and marks task complete |
| Synthesizer doesn't wake after all specialists complete | Verify specialists sent DONE messages; if not, send manual nudge via SendMessage. If still stalled after 5 min, EM reads raw specialist outputs for PM |
| All specialists fail | TeamDelete, report to PM |
| Team creation fails | Fall back to relay pattern or manual research |
