---
description: "PM-GATED — only invoke when the PM explicitly asks; EM must ask first if it thinks it's warranted; NEVER invoke from a subagent. Pipeline A v2.2 (Internet Research) using Agent Teams — collaborative research with a Haiku scout, Sonnet specialists (adversarial peers with structured output), and an Opus sweep agent, all as teammates. EM scopes research, spawns the team, and is freed. The team works autonomously with optional iterative deepening: after Team 1 completes, the EM evaluates the gap report and may dispatch a smaller Team 2 for targeted follow-up."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<topic>"
---

# Deep Research — Pipeline A v2.2 (Internet Research) Agent Teams Driver

The EM scopes the research, creates a team, spawns all teammates, and is **freed**. The team works autonomously:
- **Haiku scout** (1) — executes EM-crafted search queries, builds a shared source corpus
- **Sonnet specialists** (up to 5) — blocked until scout completes, then deep-read from the corpus, verify, challenge peers, output structured claims JSON + markdown summary
- **Opus sweep** (1) — blocked until all specialists complete, then reads specialist outputs directly, performs adversarial coverage check, fills gaps with targeted research, writes executive summary and conclusion

The scout handles mechanical source discovery. Specialists self-govern their timing, actively coordinate to avoid duplication, and challenge each other's claims. The Opus sweep reads specialist outputs directly (no consolidator intermediate), checks coverage adversarially, fills gaps, and frames the final document. The EM does not monitor or broadcast WRAP_UP.

## Arguments

`$ARGUMENTS`:
- `<topic>` — the research topic (required)
- Additional context may follow the topic as free text
- `--shallow` — skip the deepening decision gate (force single-pass, v2.1 behavior)

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
8. Parse `--shallow` flag from arguments (default: false)

Announce: "Running deep research (Agent Teams) on '{topic}'."

## Step 2 — Scope Research (EM Direct)

This is judgment work — the EM does it directly. Use the scoping checklist below to ensure quality.

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

Cap at 5 topics (team size constraint: 1 scout + 5 specialists + 1 sweep = 7 teammates). Default 4 topics. Write scope AND search queries to `{scratch-dir}/scope.md`.

### EM Scoping Checklist (review before dispatching)

Quality gates derived from published guidance (OpenAI, Perplexity, Google, STORM, Anthropic):

- [ ] **Sub-questions are explicit and falsifiable.** Each topic's focus questions have concrete answers that evidence can confirm or deny — not "what is the best X?" without criteria.
- [ ] **Effort budgets are set per topic.** Mark each topic as surface / moderate / deep. This calibrates how many sources specialists pursue before converging.
- [ ] **Source-type constraints are specified.** Default: "Prioritize primary sources (official docs, peer-reviewed, original reporting). Flag secondary sources. Note confidence for claims with <3 corroborating sources."
- [ ] **Adversarial queries are included.** At least 1 query per topic targeting criticism, limitations, or failure modes. Absence of criticism in sources ≠ absence of real limitations.
- [ ] **Search queries use varied phrasings.** Different wordings surface different source ecosystems. Include at least one query targeting each of: official docs, practitioner blogs, community forums.
- [ ] **Cross-cutting themes are named.** Connections between topics are where individual specialists have blind spots — name them so the sweep knows to look.
- [ ] **Each specialist assignment has: (a) specific objective, (b) output format reference,
      (c) tool/source guidance, (d) clear task boundaries vs. peers.** Vague assignments
      ("research X") lead to duplication — be specific about what each specialist SHOULD
      and SHOULD NOT cover.

## Step 3 — Create Team and All Tasks

### Create Team

```
TeamCreate(team_name: "research-{topic-slug}")
```

### Create Tasks (explicit ordering — blocking chain depends on this)

**Order matters.** Task IDs from earlier steps are referenced in later steps.

**1. Sweep task** (created first — will be blocked later):
```
TaskCreate(subject: "Sweep: assess coverage, fill gaps, write framing", description: "Read all specialist outputs from {scratch-dir}/, perform adversarial coverage check, fill gaps via web research, write exec summary + conclusion to {output-path}")
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

**4. Block sweep on all specialists:**
```
TaskUpdate(taskId: "{sweep-id}", addBlockedBy: ["{specialist-A-id}", "{specialist-B-id}", ...])
```

## Step 4 — Spawn All Teammates

### Scout (Haiku)

Read the scout prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/scout-prompt-template.md`

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
`${CLAUDE_PLUGIN_ROOT}/pipelines/specialist-prompt-template.md`

Fill in ALL template fields — including `[SWEEP_NAME]` (use `"sweep"` as the teammate name). This is how specialists know who to send the `DONE` wake-up message to.

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

### Opus Sweep

Spawn the sweep agent with its task (which is blocked until all specialists finish):
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

**Sweep prompt fields and verbatim instruction:** see `pipelines/web-research-internals.md` § Sweep Prompt Contents.

Dispatch ALL teammates in a single message (parallel).

## Step 5 — EM Is Freed

After spawning all teammates, announce:

> "Research team is running autonomously on '{topic}' with 1 scout + {N} specialists + 1 Opus sweep. Scout builds the shared corpus (~2-3 min), then specialists deep-read, verify, and challenge each other ({MIN_MINUTES}-{MAX_MINUTES} min, {MIN_SOURCES}-source minimum). After all specialists finish, the Opus sweep reads their outputs directly, checks coverage, fills gaps, and frames the final document. I'm available for other work — I'll be notified when the sweep completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not broadcast WRAP_UP. The team handles everything.

## Step 6 — Team 1 Completion

When you receive a notification that the sweep task is complete:

1. Read the synthesis document at `{output-path}`
2. Verify it has substantive content (not just headers)
3. Check for advisory: `test -f {advisory-path}` — if the file exists, read it
4. Read the gap report at `{scratch-dir}/gap-report.md`
5. Commit:
   ```bash
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "deep-research: Team 1 complete — {topic-slug}"
   ```
6. Shut down Team 1: `TeamDelete(team_name: "research-{topic-slug}")`

**Proceed to Step 6.5** (do NOT archive yet — deepening may add to the scratch directory).

## Step 6.5 — Deepening Decision Gate

**Skip this step entirely if `--shallow` was passed.** Proceed directly to Step 7.

Parse the gap report's YAML front-matter and apply the DEEPEN / DO NOT DEEPEN rules in `pipelines/web-research-internals.md` § Step 6.5. The decision turns on `high_severity_gaps`, `contested_unresolved`, `coverage_score`, plus the PM's timing budget.

- **If NO DEEPEN:** announce per the template in the internals doc, then proceed to Step 7.
- **If DEEPEN:** announce per the template, then proceed to Step 6.6.

## Step 6.6 — Dispatch Team 2 (Deepening Pass)

1. **Cluster gap targets** (HIGH/MEDIUM only) into 1-3 specialist assignments. Two absent claims in the same domain → one gap-specialist.
2. **Decide scout inclusion:** include a Haiku scout if gaps require new topic areas; skip if gaps are refinements within existing topics (gap-specialists do their own targeted searches).
3. **Record Team 2 spawn timestamp:** `date +%s`.
4. **Create team, tasks, and dispatch all teammates in a single message (parallel)** — sweep is in merge mode and blocks on all gap-specialists; gap-specialists block on the scout if one exists. Then announce per the template and free the EM.

**Full team/task creation snippets, gap-specialist template field list, parallel-dispatch syntax, merge-mode sweep prompt fields, announce template:** see `pipelines/web-research-internals.md` § Step 6.6.

**EM is freed again.** Do not poll.

## Step 6.7 — Team 2 Completion + Merge

When the Team 2 sweep completes:

1. Read `{scratch-dir}/deepening-delta.md`; verify substantive content; read Team 2 advisory if present.
2. **Merge delta into `{output-path}`** per the rules in `pipelines/web-research-internals.md` § Step 6.7 (Resolved Contradictions, Filled Gaps, Updated Claims, Open Questions, strip provenance markers).
3. Write merged doc back to `{output-path}` and `{scratch-dir}/synthesis-merged.md`.
4. Commit: `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "deep-research: Team 2 deepening merged — {topic-slug}"`
5. `TeamDelete(team_name: "research-{topic-slug}-t2")`
6. Proceed to Step 7.

## Step 7 — Finalize

1. Archive paper trail:
   ```bash
   mkdir -p docs/research/archive/YYYY-MM-DD-{topic-slug}
   cp -r {scratch-dir}/* docs/research/archive/YYYY-MM-DD-{topic-slug}/
   rm -rf {scratch-dir}
   ```
2. Commit: `~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "deep-research: archive + cleanup — {topic-slug}"`
3. Present executive summary to PM for discussion:
   - If deepening occurred: "Research complete (2 passes). Team 1 identified {gap_count} gaps ({high_severity_gaps} high-severity); Team 2 filled {N}. See synthesis at `{output-path}`."
   - If no deepening: "Research complete (single pass). Coverage score: {coverage_score}/5. See synthesis at `{output-path}`."
   - If advisory exists: "The sweep agent flagged observations beyond scope — see the advisory at `{advisory-path}`."

## Error Handling

See `pipelines/web-research-internals.md` § Error Handling Matrix for the full failure-mode → action table (scout/specialist/sweep/Team-2 failures).
