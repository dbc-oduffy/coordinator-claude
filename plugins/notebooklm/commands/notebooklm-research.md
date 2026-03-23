---
description: "NotebookLM research using Agent Teams — two-phase: Opus strategist plans, then right-sized team (scout + N workers + synthesizer) executes. Best for YouTube videos, podcasts, audio content, and media Claude cannot access directly."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<topic> [--context file1 file2] [--sources url1 url2]"
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

**Announce at start:** "I'm running `/notebooklm-research` to research {topic} using NotebookLM."

---

## Arguments

`$ARGUMENTS` provides the topic and optional context/sources.

**Basic:** `/notebooklm-research <topic>`

**With context files:** `/notebooklm-research <topic> --context path/to/file1.md path/to/file2.md`

**With PM-provided sources:** `/notebooklm-research <topic> --sources url1 url2`

**Both:** `/notebooklm-research <topic> --context file.md --sources url1`

---

## Execution Flow

### Step 1 — Setup

Parse `$ARGUMENTS`:
- **Topic** (required) — the research subject
- `--context` (optional) — files to give the strategist as background
- `--sources` (optional) — PM-provided URLs to research (YouTube, podcasts, articles)

Generate run ID: `{topic-slug}-{YYYYMMDD}` (e.g., `ai-agents-20260321`)

Create scratch directory:
```bash
mkdir -p tasks/scratch/notebooklm-research/{run-id}/
```

Set output path: `~/.claude/docs/research/YYYY-MM-DD-{topic-slug}.md`

Set advisory path: `~/.claude/docs/research/YYYY-MM-DD-{topic-slug}-advisory.md` (replace `.md` with `-advisory.md` on the output path)

### Step 2 — Scope (lightweight context pass-through)

Write `{scratch-dir}/em-context.md`:

```markdown
# EM Context for NotebookLM Research

## Topic
{topic and desired outcome — what the PM wants to learn}

## Background Files
{list of --context file paths, or "none"}

## PM-Provided Sources
{list of --sources URLs, or "none"}

## Timing Preferences
{any timing constraints from PM, or "none specified"}

## NLM Tier
{free | plus | ultra — ask PM if not known: "What NotebookLM tier are you on? (free/plus/ultra — this affects how many notebooks we can run in parallel)"}

## Queries Used Today
{number if known, else "unknown"}
```

**The EM does NOT design questions, craft NLM instructions, decide team size, or search for sources.** That's the strategist's job.

If the PM hasn't specified their NLM tier, ask before proceeding:
> "What NotebookLM tier are you on? (free/plus/ultra) This determines how many parallel notebooks we can run."

### Step 3 — Phase 1: Dispatch Strategist

Dispatch the strategist as a regular Agent (NOT a teammate):

```
Agent(
  subagent_type: "notebooklm:notebooklm-research-strategist",
  prompt: <fill strategist-prompt-template.md with:
    [RESEARCH_TOPIC] = topic
    [EM_CONTEXT] = "See em-context.md"
    [SCRATCH_DIR] = full path to scratch dir
    [MAX_MINUTES] = 5
    [TIER] = tier from em-context.md
    [QUERIES_USED_TODAY] = queries used today or "unknown"
    [PM_SOURCES] = --sources URLs or "none"
  >
)
```

Wait for completion (Phase 1 is synchronous — EM waits here).

Read `{scratch-dir}/strategy.md`. Verify it contains YAML frontmatter with `worker_count`.

Extract `worker_count: N` from YAML frontmatter.

### Step 4 — Phase 2: Create Right-Sized Team

```
TeamCreate("notebooklm-{topic-slug}")

// Create tasks
synthesizer_task = TaskCreate(name: "synthesizer", description: "Cross-notebook synthesis + notebook cleanup")
scout_task = TaskCreate(name: "scout", description: "Source discovery for all notebooks")

worker_tasks = []
For letter in A..{Nth letter}:
  task = TaskCreate(name: "worker-{letter}", description: "NotebookLM research — Notebook {letter}")
  TaskUpdate(task_id: task.id, blockedBy: [scout_task.id])
  worker_tasks.append(task.id)

TaskUpdate(task_id: synthesizer_task.id, blockedBy: worker_tasks)
```

### Step 5 — Spawn Team (parallel, single message)

Read the prompt templates from `pipelines/`:
- `pipelines/scout-prompt-template.md`
- `pipelines/worker-prompt-template.md`
- `pipelines/synthesizer-prompt-template.md`

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
- `[MAX_MINUTES]` = ceiling from strategy.md `estimated_ceiling`, or 25 if not specified
- `[SYNTHESIZER_NAME]` = synthesizer teammate name

**Synthesizer prompt** (fill template):
- `[RESEARCH_TOPIC]` = topic
- `[WORKER_COUNT]` = N (from strategy.md)
- `[WORKER_TASK_IDS]` = comma-separated worker task IDs
- `[SCRATCH_DIR]` = scratch dir path
- `[OUTPUT_PATH]` = `~/.claude/docs/research/YYYY-MM-DD-{topic-slug}.md`
- `[ADVISORY_PATH]` = advisory path computed in Step 1 (e.g., `~/.claude/docs/research/YYYY-MM-DD-{topic-slug}-advisory.md`)
- `[TASK_ID]` = synthesizer_task.id

Assign task owners when spawning each teammate.

### Step 6 — EM Freed

After spawning the team, report to the PM and stop tracking:

> "NotebookLM research team running on **{topic}** with 1 scout + {N} worker(s) + 1 synthesizer.
>
> - Scout is finding sources (~3-5 min)
> - Workers will run parallel notebooks (~15-25 min each)
> - Synthesizer will cross-reference findings and clean up notebooks when done
>
> Output will be written to: `{output-path}`
>
> I'm available for other work — the team runs autonomously."

### Step 7 — On Completion

When the synthesizer sends a completion message:

1. Read `{output-path}`. Verify it's substantive (not empty, not error-only).
2. Notebooks already cleaned up by synthesizer — note cleanup status from the synthesis doc.
3. Check for advisory: `test -f {advisory-path}` — if the file exists, read it.
4. Archive scratch directory:
   ```bash
   mv tasks/scratch/notebooklm-research/{run-id}/ tasks/scratch/archive/notebooklm-research/{run-id}/
   ```
5. Delete the team: `TeamDelete("notebooklm-{topic-slug}")`
6. Commit the output file.
7. Present summary to PM:
   - Topic researched + notebooks used
   - Key findings (2-3 bullet executive summary from the synthesis doc)
   - Output path
   - Any gaps flagged for follow-up
   - If advisory exists: "The synthesizer flagged observations beyond scope — see the advisory at `{advisory-path}`."
