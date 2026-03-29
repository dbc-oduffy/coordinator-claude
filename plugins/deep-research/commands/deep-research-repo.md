---
description: "Pipeline B (Repo Research) using Agent Teams — 2 Haiku scouts build file inventories, 4 Sonnet specialists analyze and optionally compare, 1 Opus synthesizer produces the final document. EM scopes, spawns the team, and is freed."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<repo-path> [--compare <project-path>]"
---

# Deep Research — Pipeline B (Repo Research) Agent Teams Driver

The EM scopes the repository, creates a team, spawns all teammates, and is **freed**. The team works autonomously:
- **Haiku scouts** (2) — inventory all files in their assigned chunks, build structured file maps
- **Sonnet specialists** (4) — blocked until both scouts complete, then deep-read files, analyze, optionally compare
- **Opus synthesizer** (1) — blocked until all specialists complete, then reads findings and writes final document(s)

Scouts produce the shared thoroughness artifact that Sonnets would naturally skim past. Specialists self-govern their timing (floor, diminishing returns, ceiling). The EM does not monitor or broadcast WRAP_UP. When the synthesizer marks its task complete, the EM receives a notification and does quick cleanup.

## Arguments

`$ARGUMENTS`:
- `<repo-path>` — path to the repository to research (required)
- `--compare <project-path>` — optional path to a project to compare against

## Step 1 — Setup

1. Parse arguments: extract repo path and optional comparison path
2. Verify the repo path exists and contains files
3. Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp)
4. Generate topic slug from repo name (e.g., `onnxruntime`, `langchain`)
5. Record spawn timestamp: `date +%s` (Unix epoch seconds — passed to teammates for timing)
6. Create scratch directory:
   ```bash
   mkdir -p tasks/scratch/deep-research-teams/{run-id}
   ```
7. Set output path: `docs/research/YYYY-MM-DD-{topic-slug}.md`
8. Set advisory path: `docs/research/YYYY-MM-DD-{topic-slug}-advisory.md` (replace `.md` with `-advisory.md` on the assessment output path)
9. If `--compare`: set gap analysis path: `docs/research/YYYY-MM-DD-{topic-slug}-gap-analysis.md`

Announce: "Running Pipeline B (repo research, Agent Teams) on {repo-path}."

## Step 2 — Scope Repository (EM Direct)

This is judgment work — the EM does it directly:

1. **Read the README** — understand the repo's purpose and architecture
2. **Pin the version** — record the repo's current version (git tag, release, or commit hash)
3. **Survey repo structure** — 2-3 `ls` commands on the target repo, plus `find {repo-path} -name '*.py' -o -name '*.ts' -o -name '*.go' | wc -l` (or similar) for file count estimates
4. **Define exactly 4 chunks** — domain-aligned, based on the repo's own architecture. (4 chunks because: 7-teammate ceiling - 2 scouts - 1 synthesizer = 4 specialist slots.)
5. **Assign chunks to scouts** — Scout 1 gets chunks A+B, Scout 2 gets chunks C+D
6. **Estimate file counts per chunk** — rough counts from the survey (these become `[EXPECTED_FILE_COUNT]` in specialist prompts, used as a tripwire for detecting thin scout output)
7. **Write focus questions** — what are the key design decisions? What patterns?
8. **If `--compare`:** identify the project's domain keywords per chunk for comparison file identification
9. **Ask the PM for timing preferences:**
   > "Research timing: default is 5-15 min specialist window with 3-file minimum deep-read. For a small repo, I'd suggest 3-10 min / 3 files. For a large repo, 5-20 min / 5 files. What ceiling works for you?"

Write scope to `{scratch-dir}/scope.md`:

```markdown
# Repo Research Scope

**Repository:** {repo-name}
**Path:** {repo-path}
**Version:** {version}
**Date:** {date}
**Comparison:** {project-path or "none"}

## Chunks

| Chunk | Scout | Directories/Files | Est. Files | Focus Question |
|-------|-------|-------------------|-----------|----------------|
| A | 1 | {dirs} | ~{count} | {question} |
| B | 1 | {dirs} | ~{count} | {question} |
| C | 2 | {dirs} | ~{count} | {question} |
| D | 2 | {dirs} | ~{count} | {question} |

{If --compare:}
## Comparison Targets
| Chunk | Project Domain Keywords |
|-------|----------------------|
| A | {keywords for globbing} |
| B | {keywords} |
| C | {keywords} |
| D | {keywords} |
```

## Step 3 — Create Team and All Tasks

### Create Team

```
TeamCreate(team_name: "repo-research-{topic-slug}")
```

### Create Tasks (explicit ordering — blocking chain depends on this)

**Order matters.** Task IDs from earlier steps are referenced in later steps.

**1. Synthesizer task** (created first — will be blocked later):
```
TaskCreate(subject: "Synthesize all findings into final document(s)", description: "Read all specialist assessments from {scratch-dir}/, cross-reference, write synthesis to {output-path} and {scratch-dir}/synthesis.md. If comparison mode: also write gap analysis to {gap-analysis-path}.")
```

**2. Scout tasks** (no blockers):
```
TaskCreate(subject: "Scout 1: Inventory chunks A and B", description: "Read and inventory all files in chunks A and B. Write to {scratch-dir}/A-inventory.md and {scratch-dir}/B-inventory.md. {If compare: also identify comparison file candidates in project.}")

TaskCreate(subject: "Scout 2: Inventory chunks C and D", description: "Read and inventory all files in chunks C and D. Write to {scratch-dir}/C-inventory.md and {scratch-dir}/D-inventory.md. {If compare: also identify comparison file candidates in project.}")
```

**3. Specialist tasks** (each blocked by BOTH scouts):
For each chunk (A, B, C, D):
```
TaskCreate(subject: "Analyze chunk {letter}: {description}", description: "Deep-read files, write assessment to {scratch-dir}/{letter}-assessment.md. {If compare: also write comparison to {scratch-dir}/{letter}-comparison.md.}")
TaskUpdate(taskId: "{specialist-id}", addBlockedBy: ["{scout-1-id}", "{scout-2-id}"])
```

**4. Block synthesizer on all specialists:**
```
TaskUpdate(taskId: "{synthesizer-id}", addBlockedBy: ["{specialist-A-id}", "{specialist-B-id}", "{specialist-C-id}", "{specialist-D-id}"])
```

## Step 4 — Spawn All Teammates

### Scouts (Haiku)

Read the scout prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/repo-scout-prompt-template.md`

Fill in template fields for each scout. Scout 1 gets chunks A+B, Scout 2 gets chunks C+D.

```
Agent(
  team_name: "repo-research-{topic-slug}",
  name: "scout-1",
  model: "haiku",
  subagent_type: "deep-research:repo-scout",
  prompt: <filled scout prompt for chunks A+B>
)
TaskUpdate(taskId: "{scout-1-id}", owner: "scout-1")

Agent(
  team_name: "repo-research-{topic-slug}",
  name: "scout-2",
  model: "haiku",
  subagent_type: "deep-research:repo-scout",
  prompt: <filled scout prompt for chunks C+D>
)
TaskUpdate(taskId: "{scout-2-id}", owner: "scout-2")
```

### Specialists (Sonnet)

For each chunk, read the specialist prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/repo-specialist-prompt-template.md`

Fill in ALL template fields — including:
- `[SYNTHESIZER_NAME]` → `"synthesizer"`
- `[PEER_LIST]` → the other 3 specialists with their teammate names and chunk descriptions
- `[EXPECTED_FILE_COUNT]` → from the scoping survey
- `[MIN_MINUTES]`, `[MAX_MINUTES]`, `[MIN_SOURCES]` → from PM timing preferences (or defaults: 5 min, 15 min, 3 files)
- If `--compare`: include `[COMPARE_PROJECT_PATH]` and `[COMPARE_PROJECT_NAME]`

```
Agent(
  team_name: "repo-research-{topic-slug}",
  name: "chunk-{letter}",
  model: "sonnet",
  subagent_type: "deep-research:repo-specialist",
  prompt: <filled specialist prompt>
)
TaskUpdate(taskId: "{specialist-id}", owner: "chunk-{letter}")
```

### Synthesizer (Opus)

Read the synthesizer prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/repo-synthesizer-prompt-template.md`

Fill in ALL template fields:
- `[REPO_NAME]`, `[SCRATCH_DIR]`, `[OUTPUT_PATH]`, `[TASK_ID]`
- `[ADVISORY_PATH]` → advisory path computed in Step 1
- `[COMPARE_MODE]` → true/false
- If compare: `[COMPARE_PROJECT_NAME]`, `[GAP_ANALYSIS_PATH]`

```
Agent(
  team_name: "repo-research-{topic-slug}",
  name: "synthesizer",
  model: "opus",
  subagent_type: "deep-research:research-synthesizer",
  prompt: <filled synthesizer prompt>
)
TaskUpdate(taskId: "{synthesizer-id}", owner: "synthesizer")
```

Dispatch ALL teammates in a single message (parallel).

## Step 5 — EM Is Freed

After spawning all teammates, announce:

> "Research team is running autonomously on '{repo-name}' with 2 scouts + 4 specialists + 1 synthesizer. Scouts inventory files (~5 min), then specialists analyze {MIN_MINUTES}-{MAX_MINUTES} min ({MIN_SOURCES}-file minimum). I'm available for other work — I'll be notified when the synthesizer completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not broadcast WRAP_UP. The team handles everything.

## Step 6 — On Completion Notification

When you receive a notification that the synthesis task is complete:

1. Read the synthesis document at `{output-path}`
2. Verify it has substantive content (not just headers)
3. If comparison mode: read the gap analysis at `{gap-analysis-path}` and verify
4. Check for advisory: `test -f {advisory-path}` — if the file exists, read it
5. Commit:
   ```bash
   git add -A && git commit -m "deep-research: complete — {topic-slug}"
   ```
5. Archive paper trail:
   ```bash
   mkdir -p docs/research/archive/YYYY-MM-DD-{topic-slug}
   cp -r {scratch-dir}/* docs/research/archive/YYYY-MM-DD-{topic-slug}/
   rm -rf {scratch-dir}
   ```
6. Shut down the team: `TeamDelete(team_name: "repo-research-{topic-slug}")`
7. Commit: `git add -A && git commit -m "deep-research: archive + cleanup"`
8. Present executive summary to PM for discussion. If advisory exists, mention it: "The synthesizer flagged observations beyond scope — see the advisory at `{advisory-path}`."

## Error Handling

| Failure | Action |
|---------|--------|
| Scout fails (no inventory written) | Specialists fall back to self-directed file discovery (Glob + Read). Budget 3 extra minutes. |
| Scout times out (partial inventory) | Specialists use what's there + supplement with own Glob/Read |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and marks task complete |
| Specialist produces thin assessment | Synthesizer notes the gap; EM can supplement manually |
| Synthesizer doesn't wake after all specialists complete | Verify specialists sent DONE messages; if not, send manual nudge via SendMessage. If still stalled after 5 min, EM reads raw specialist outputs for PM |
| All specialists fail | TeamDelete, report to PM |
| Team creation fails | Report to PM |
