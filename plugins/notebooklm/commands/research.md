---
description: "NotebookLM research using Agent Teams — EM scopes directly, then right-sized team (scout + N workers + sweep) executes autonomously. Best for YouTube videos, podcasts, audio content, and media Claude cannot access directly."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<topic> [--context file1 file2] [--sources url1 url2] [--cleanup]"
---

# NotebookLM Research — Pipeline D (Agent Teams)

Research via Google NotebookLM for media-rich sources Claude cannot access directly: YouTube videos, podcasts, audio content, web pages with heavy JavaScript rendering, and Google Drive documents.

**When to use this:**
- PM provides YouTube links, podcast URLs, or audio content to research
- PM wants to find the best talks/videos/podcasts on a topic (Google is better at this than our WebSearch)
- The source material requires transcription or media processing Claude can't do
- NotebookLM's AI analysis adds value (cross-source synthesis, citation tracking)

**When NOT to use this:**
- Codebase research → `/deep-research repo`
- Web topic research (text articles, docs) → `/deep-research web`
- Structured batch research → `/structured-research`
- Quick API docs → Context7

**Announce at start:** "I'm running `/research` to research {topic} using NotebookLM."

---

## Arguments

`$ARGUMENTS` provides the topic and optional context/sources.

**Basic:** `/notebooklm-research <topic>`

**With context files:** `/notebooklm-research <topic> --context path/to/file1.md path/to/file2.md`

**With PM-provided sources:** `/notebooklm-research <topic> --sources url1 url2`

**Both:** `/notebooklm-research <topic> --context file.md --sources url1`

**With cleanup:** `/notebooklm-research <topic> --cleanup`

---

## Execution Flow

### Step 1 — Setup

Parse `$ARGUMENTS`:
- **Topic** (required) — the research subject
- `--context` (optional) — background files to inform scoping
- `--sources` (optional) — PM-provided URLs to research (YouTube, podcasts, articles)
- `--cleanup` (optional) — delete notebooks after research completes. **Default: notebooks are kept.** A lot of work goes into assembling research notebooks (source ingestion, processing); they're usually worth keeping for follow-up queries, re-research, or sharing.

Generate run ID: `{topic-slug}-{YYYYMMDD}` (e.g., `ai-agents-20260321`)

Create scratch directory:
```bash
mkdir -p tasks/scratch/notebooklm-research/{run-id}/
```

Set output path: `~/docs/research/YYYY-MM-DD-{topic-slug}.md`

Set advisory path: `~/docs/research/YYYY-MM-DD-{topic-slug}-advisory.md` (replace `.md` with `-advisory.md` on the output path)

---

### Step 2 — EM Scopes Research

**Read the best practices reference** before scoping:
```
Read("pipelines/notebooklm-best-practices.md")
```

**Gather two pieces of required information from the PM before proceeding:**

1. **NLM tier** — if not known, ask:
   > "What NotebookLM tier are you on? (free/plus/ultra) This determines how many parallel notebooks we can run."

2. **Timing ceiling** — if not specified, ask:
   > "What's your timing ceiling for this research run? (e.g., 25 min standard, 45 min deep)"

If `--context` files were provided, read them now for topic background.

**Design the research strategy directly.** Apply the best practices reference to decide:

- **Notebook topology** — how many notebooks, what topic cluster goes in each
- **Questions per notebook** — apply anti-hallucination rules (citation-forcing, specificity, structured synthesis template, source gap audit query)
- **Custom instructions per notebook** — Role + Context + Rules, max 10,000 characters
- **Source strategy per notebook** — scout-provided vs research_start (or direct PM URLs)
- **Studio artifacts** — what to request, if anything
- **Worker count** — based on tier, topic breadth, and query budget

**EM Scoping Checklist:**
- [ ] Topic is narrowly defined per notebook (one cluster each)
- [ ] Questions are citation-forcing and specify output format
- [ ] Source strategy per notebook is set (scout-provided vs research_start)
- [ ] Studio artifacts requested match the use case (or skipped)
- [ ] Rate limit budget accounts for tier + queries used today

**Time-box:** Scoping should take 2-3 minutes. If deliberating longer, pick the simpler topology.

**Write `strategy.md`** to `{scratch-dir}/strategy.md` using this exact format:

```markdown
---
worker_count: N
total_expected_queries: M
tier_assumption: free|plus|ultra
timing:
  max_minutes: 25
---

## Notebook A
- **Focus:** [specific topic cluster for this notebook]
- **Custom instructions:** [role + context + rules, max 10K chars]
- **Questions:**
  1. [question 1 — include citation requirement]
  2. [question 2]
  ...
  N. [source gap audit query]
- **Source strategy:** scout-provided | research_start
- **Search guidance for scout:** [specific search terms, content types, or exact URLs if PM provided them]
- **Studio artifacts:** [list, or "none"]
- **Estimated ceiling:** 25 min

## Notebook B (if worker_count >= 2)
- **Focus:** ...
- **Custom instructions:** ...
- **Questions:**
  ...
- **Source strategy:** scout-provided | research_start
- **Search guidance for scout:** ...
- **Studio artifacts:** [list, or "none"]
- **Estimated ceiling:** 25 min

## Notebook C (if worker_count >= 3)
...
```

---

### Step 3 — Create Team + Tasks

```
TeamCreate("notebooklm-{topic-slug}")

// Create tasks
sweep_task = TaskCreate(name: "sweep", description: "Coverage assessment + gap fill + notebook cleanup")
scout_task = TaskCreate(name: "scout", description: "Source discovery for all notebooks")

worker_tasks = []
For letter in A..{Nth letter}:
  task = TaskCreate(name: "worker-{letter}", description: "NotebookLM research — Notebook {letter}")
  TaskUpdate(task_id: task.id, blockedBy: [scout_task.id])
  worker_tasks.append(task.id)

TaskUpdate(task_id: sweep_task.id, blockedBy: worker_tasks)
```

---

### Step 4 — Spawn Teammates

Read the prompt templates from `pipelines/`:
- `pipelines/scout-prompt-template.md`
- `pipelines/worker-prompt-template.md`
- `pipelines/sweep-prompt-template.md`

Spawn all teammates in one operation:

**Scout prompt** (fill template):
- `[RESEARCH_TOPIC]` = topic
- `[SCRATCH_DIR]` = scratch dir path
- `[TASK_ID]` = scout_task.id
- `[SPAWN_TIMESTAMP]` = current Unix timestamp (`date +%s`)
- `[MAX_MINUTES]` = 5

**Worker prompt(s)** — one per letter (fill template for each):
- `[NOTEBOOK_LETTER]` = A, B, C as applicable
- `[NOTEBOOK_NAME]` = `{topic-slug}-{letter}` (e.g., `ai-agents-a`)
- `[RESEARCH_TOPIC]` = topic
- `[SCRATCH_DIR]` = scratch dir path
- `[TASK_ID]` = worker_task.id for this letter
- `[SPAWN_TIMESTAMP]` = current Unix timestamp
- `[MAX_MINUTES]` = `max_minutes` from strategy.md YAML, or 25 if not specified
- `[SWEEP_NAME]` = sweep teammate name

**Sweep prompt** (fill template):
- `[RESEARCH_TOPIC]` = topic
- `[WORKER_COUNT]` = N (from strategy.md YAML frontmatter — already known from scoping)
- `[WORKER_TASK_IDS]` = comma-separated worker task IDs
- `[SCRATCH_DIR]` = scratch dir path
- `[OUTPUT_PATH]` = `~/docs/research/YYYY-MM-DD-{topic-slug}.md`
- `[ADVISORY_PATH]` = advisory path computed in Step 1
- `[TASK_ID]` = sweep_task.id
- `[CLEANUP_NOTEBOOKS]` = `true` if `--cleanup` was passed, `false` otherwise

Spawn teammates using these agent types:
- Scout: `notebooklm:research-scout`
- Workers: `notebooklm:research-worker`
- Sweep: `notebooklm:research-sweep`

Assign task owners when spawning each teammate.

---

### Step 5 — EM Freed

After spawning the team, report to the PM and stop tracking:

> "NotebookLM research team running on **{topic}** with 1 scout + {N} worker(s) + 1 sweep agent.
>
> - Scout is finding sources (~3-5 min)
> - Workers will run parallel notebooks (~15-25 min each), writing structured claims (JSON) and a summary per notebook
> - Sweep agent will assess coverage, fill gaps{', and clean up notebooks' if --cleanup} when done
>
> Output will be written to: `{output-path}`
>
> I'm available for other work — the team runs autonomously."

---

### Step 6 — On Completion

When the sweep agent sends a completion message:

1. Read `{output-path}`. Verify it's substantive (not empty, not error-only).
2. If `--cleanup`: notebooks were deleted by sweep agent — note cleanup status from the output doc. If no `--cleanup`: notebooks are preserved — mention their names/IDs to PM for future reference.
3. Check for advisory: `test -f {advisory-path}` — if the file exists, read it.
4. Archive scratch directory:
   ```bash
   mv tasks/scratch/notebooklm-research/{run-id}/ tasks/scratch/archive/notebooklm-research/{run-id}/
   ```
5. Delete the team: `TeamDelete("notebooklm-{topic-slug}")`
6. Commit the output file.
7. Present summary to PM:
   - Topic researched + notebooks used
   - Key findings (2-3 bullet executive summary from the output doc)
   - Output path
   - Any gaps flagged for follow-up
   - If advisory exists: "The sweep agent flagged observations beyond scope — see the advisory at `{advisory-path}`."

---

## Error Handling

| Failure | Action |
|---------|--------|
| Scout fails (no sources.md) | Workers fall back to research_start discovery |
| Worker auth expiry | Worker calls refresh_auth, retries; if persistent, writes partial findings |
| Worker hits rate limit | Worker writes partial findings, sends DONE |
| Worker can't ingest source (paywall, format) | Worker logs failure, continues with remaining sources |
| Sweep can't query notebooks | Sweep proceeds with claims files only (skip follow-up queries) |
| Agents stuck in idle loops | Commit/archive before TeamDelete. Don't block — read available outputs |
| All workers fail | TeamDelete, report to PM with failure details |
