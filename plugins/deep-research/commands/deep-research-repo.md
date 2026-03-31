---
description: "Pipeline B (Repo Research) using Agent Teams — 2 Haiku scouts build file inventories, 4 Sonnet specialists analyze and optionally compare, 1 Opus synthesizer produces the final document. EM scopes, spawns the team, and is freed."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<repo-path> [--compare <project-path>] [--deeper]"
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
- `--deeper` — generate a dependency-weighted repomap during scoping, giving specialists structural centrality rankings to prioritize deep-reads

## Step 1 — Setup

1. Parse arguments: extract repo path, optional comparison path, and `--deeper` flag
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
10. If `--deeper`: set repomap path: `{scratch-dir}/repomap.md`

Announce: "Running Pipeline B (repo research, Agent Teams{', deeper mode' if --deeper}{', comparison mode' if --compare}) on {repo-path}."

## Step 2 — Orient and Scope Repository (EM Direct)

This is judgment work — the EM does it directly. Two phases: orient first, then scope.

### Phase 1: Structural Orientation (do this BEFORE defining chunks)

Read the repo's structural skeleton to ground your scoping in reality, not assumptions:

1. **Read the README** — understand the repo's purpose and architecture
2. **Pin the version** — record the repo's current version (git tag, release, or commit hash)
3. **Survey repo structure** — 2-3 `ls` commands on the target repo, plus `find {repo-path} -name '*.py' -o -name '*.ts' -o -name '*.go' | wc -l` (or similar) for file count estimates
4. **Answer four orientation questions** (write answers into scope.md):
   - What are the entry points? (main files, CLI entry, request handlers, etc.)
   - What are the 5 most important directories?
   - What is the architecture pattern? (monolith, microservices, layered, plugin, etc.)
   - What external dependencies are material to the analysis questions?
5. **Check for LLM context files** — look for `CONTEXT.md`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, or similar. If present, read them — they're high-signal orientation material that should be surfaced to all specialists.

### Phase 1.5: Repomap Generation (only if `--deeper`)

If `--deeper` is set, generate a dependency-weighted repomap before defining chunks. This gives you structural centrality data to inform chunk scoping and gives specialists prioritization guidance.

**Step A — Detect primary language(s):**
Count files by extension to identify the dominant language(s):
```bash
find {repo-path} -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10
```

**Step B — Extract import/dependency edges:**
Run language-appropriate grep patterns on the repo. Use the top language(s) detected above:

| Language | Pattern |
|----------|---------|
| Python | `grep -rh "^from \|^import " --include="*.py" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| JS/TS | `grep -rh "from ['\"]" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| Go | `grep -rh '"[^"]*"' --include="*.go" {repo-path} \| grep -v "// " \| sort \| uniq -c \| sort -rn \| head -40` |
| Rust | `grep -rh "^use " --include="*.rs" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| C/C++ | `grep -rh '#include "' --include="*.h" --include="*.cpp" --include="*.c" --include="*.hpp" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| Java | `grep -rh "^import " --include="*.java" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |

For polyglot repos, run patterns for the top 2 languages.

**Step C — Resolve to files and count cross-references:**
From the import output, identify the top ~20 most-imported modules/files. For each, resolve to an actual file path in the repo and count how many distinct files reference it:
```bash
grep -rl "{module-name}" --include="*.{ext}" {repo-path} | wc -l
```

**Step D — Extract key exports:**
For each of the top ~20 files by reference count, Read the first 50 lines to extract key exports (class names, function signatures, important constants).

**Step E — Write repomap or skip:**
If fewer than 5 files have 2+ incoming references, the import graph is too thin to be useful. Note this in `scope.md` and proceed without a repomap (specialists operate in default mode).

Otherwise, write `{scratch-dir}/repomap.md`:

```markdown
# Repository Map — {repo-name}

Ranked by structural centrality (incoming cross-file references).
Generated during deeper-mode scoping — use to prioritize deep-reads.

## Tier 1 — Core (10+ incoming refs)
| File | Refs | Key Exports |
|------|------|-------------|
| {path} | {count} | {exports} |

## Tier 2 — Important (5-9 refs)
| File | Refs | Key Exports |
|------|------|-------------|
| {path} | {count} | {exports} |

## Tier 3 — Supporting (2-4 refs)
| File | Refs | Key Exports |
|------|------|-------------|
| {path} | {count} | {exports} |
```

### Phase 2: Scoping (informed by orientation{' and repomap' if --deeper})

6. **Define exactly 4 chunks** — domain-aligned, based on the repo's own architecture as understood from orientation. (4 chunks because: 7-teammate ceiling - 2 scouts - 1 synthesizer = 4 specialist slots.) If `--deeper` produced a repomap, review Tier 1 file distribution across chunks — avoid concentrating all core files in a single chunk.
7. **Assign chunks to scouts** — Scout 1 gets chunks A+B, Scout 2 gets chunks C+D
8. **Estimate file counts per chunk** — rough counts from the survey (these become `[EXPECTED_FILE_COUNT]` in specialist prompts, used as a tripwire for detecting thin scout output)
9. **Write focus questions using execution-trace framing** — instead of "describe the architecture of X", prefer "trace the request from [entry] to [exit]" or "how does data flow from [input] to [output]?" Execution-trace questions produce more accurate specialist output than structural questions.
10. **If `--compare`:** identify the project's domain keywords per chunk for comparison file identification. For comparison mode: specialists will analyze each codebase independently first, then compare answers against the focus questions — not compare code directly.
11. **Ask the PM for timing preferences:**
    > "Research timing: default is 5-15 min specialist window with 3-file minimum deep-read. For a small repo, I'd suggest 3-10 min / 3 files. For a large repo, 5-20 min / 5 files. What ceiling works for you?"

Write scope to `{scratch-dir}/scope.md`:

```markdown
# Repo Research Scope

**Repository:** {repo-name}
**Path:** {repo-path}
**Version:** {version}
**Date:** {date}
**Comparison:** {project-path or "none"}
**Deeper mode:** {true/false}
**Repomap:** {repomap path or "skipped — thin import graph" or "N/A"}

## Structural Orientation

**Entry points:** {main files, CLI entry, request handlers}
**Key directories:** {top 5 most important directories}
**Architecture pattern:** {monolith, microservices, layered, plugin, etc.}
**Material dependencies:** {external deps relevant to analysis}
**LLM context files:** {CONTEXT.md, CLAUDE.md, etc. — "none" if absent}

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
- If `--deeper` and repomap was generated (not skipped): include the `[IF DEEPER MODE]` section with `[SCRATCH_DIR]/repomap.md`

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
