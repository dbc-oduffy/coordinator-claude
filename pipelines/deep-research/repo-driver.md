---
description: "PM-GATED — only invoke when the PM explicitly asks; EM must ask first if it thinks it's warranted; NEVER invoke from a subagent. Pipeline B (Repo Research) using Agent Teams — optional Opus survey for holistic orientation, scouts (Haiku for small repos, Sonnet for large) build file inventories, 4 Sonnet specialists analyze and optionally compare, 1 Opus synthesizer produces the final document. In --deepest mode: three-phase pipeline with atlas sketch and refinement."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<repo-path> [--compare <project-path>] [--code-compare <peer-target> --axes <axis-list>] [--survey] [--deeper] [--deepest] [--scout-model {haiku|sonnet}]"
---

# Deep Research — Pipeline B (Repo Research) Agent Teams Driver

The EM scopes the repository, creates a team, spawns all teammates, and is **freed**. The team works autonomously:
- **Haiku scouts** (2) — inventory all files in their assigned chunks, build structured file maps
- **Sonnet specialists** (4) — blocked until all scouts complete (2 on the Haiku tier, 4 on the Sonnet tier), then deep-read files, analyze, optionally compare
- **Opus synthesizer** (1) — blocked until all specialists complete, then reads findings and writes final document(s)

Scouts produce the shared thoroughness artifact that Sonnets would naturally skim past. Specialists self-govern their timing (floor, diminishing returns, ceiling). The EM does not monitor or broadcast WRAP_UP. When the synthesizer marks its task complete, the EM receives a notification and does quick cleanup.

## Arguments

`$ARGUMENTS`:
- `<repo-path>` — path to the repository to research (required)
- `--compare <project-path>` — optional path to a project to compare against
- `--code-compare <peer-target> --axes <axis-list>` — routes to the single-agent Code-Comparison mode (see `## Mode Dispatch — --code-compare` below) instead of the Pipeline B scout→specialist→synthesizer team. Distinct from `--compare`: `--compare` runs the Pipeline B prose gap-analysis team; `--code-compare` dispatches one self-contained agent per (subject, peer) pair via fan-out and does NOT invoke the team protocol at all — no scouts, no specialists, no synthesizer.
- `--survey` — dispatch a solo Opus agent to produce a holistic 20-30KB narrative overview before the team runs. Useful when the EM is cold on the repo. The survey becomes both a standalone deliverable and a specialist input artifact. Implied by `--deepest` unless the EM already has context.
- `--deeper` — generate a dependency-weighted repomap during scoping, giving specialists structural centrality rankings to prioritize deep-reads
- `--deepest` — all of `--deeper` and `--survey`, plus generate architecture atlas artifacts in two passes: a preliminary sketch from scout data (pre-specialist) and a refined atlas from the full research (post-synthesis). Three-phase pipeline.
- `--scout-model {haiku|sonnet}` — override the size-derived scout tier (Step 5 Phase A). Default is size-derived (Sonnet for large or high-volume repos, Haiku for small). The tier selects the dispatch vehicle, not a `model:` parameter — see Step 5 Phase A's tier table.

## Mode Dispatch — `--code-compare`

If `--code-compare <peer-target> --axes <axis-list>` is supplied, this run does NOT follow the
Agent Teams flow below (Steps 1-7.5) — skip straight to a single-agent dispatch:

1. Read the single-agent prompt template from
   `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/code-comparison-agent-prompt-template.md`.
2. Fill in the bracketed fields (subject repo, peer target, axis list). **`[OUTPUT_PATH]` is
   bound, not an EM fill-in:** `<repo-root>/state/emissions/code-comparison/{run-id}.yaml`, where
   `<repo-root>` resolves via the running repo's own tree-root pointer (DoE's is `.doe-root`;
   never `${CLAUDE_PLUGIN_ROOT}`, which names the plugin source tree, not `state/`'s parent) and
   `{run-id}` is generated fresh (`YYYY-MM-DD-HHhMM`, current timestamp) — Mode Dispatch skips
   Step 1, so this mode generates its own run-id rather than reusing one. Each repo writes its
   own records into its own tree — this is not a central directory shared across repos.
3. Dispatch one `Agent(...)` call per `(subject, peer)` pair (fan-out shape, NOT `TaskCreate`/team
   formation) — no scouts, no specialists, no synthesizer.
4. Each agent emits structured comparison records per the schema at
   `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/code-comparison-record-schema.md`, writing the
   output file itself.

Full mode description, architecture rationale, and record-schema detail:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/PIPELINE.md` § Code-Comparison Mode.

## Step 1 — Setup

1. Parse arguments: extract repo path, optional comparison path, `--survey` flag, `--deeper` flag, and `--deepest` flag. **Note:** `--deepest` implies both `--deeper` and `--survey` — if `--deepest` is set, treat both as also set. However, the EM MAY skip the survey step if they already have sufficient context on the repo (e.g., it's the project's own repo, or a prior survey exists). State this judgment explicitly: "Skipping survey — I already have context on this repo from [reason]." **Survey caching:** If a prior survey exists at the output path and is less than 7 days old, the EM MAY reuse it instead of regenerating. State: "Reusing prior survey from [date] — [reason still valid]." **Also parse `--scout-model {haiku|sonnet}` if present** — it overrides the Step 5 Phase A size-derived scout-model default.
2. Verify the repo path exists and contains files. **Note:** the path may have been resolved from a repo-target name by the entry point (via `machine-local get repos.<name>`, `~/Documents/Code_Reference/<name>`, or an opt-in shallow clone); if a shallow clone was created by the entry point, record its path in `scope.md` under `## Clone Disposition` for explicit cleanup consideration — do NOT auto-delete; only a pipeline-created shallow clone is cleanup-eligible, and even then surface-don't-auto-rm.
3. Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp)
4. Generate topic slug from repo name (e.g., `onnxruntime`, `langchain`)
5. Record spawn timestamp: `date +%s` (Unix epoch seconds — passed to teammates for timing)
6. Create working directory — **accept-if-passed:** if `{scratch-dir}` is already bound (supplied by `research.md` Step 0), skip the `mkdir` and use the supplied value; otherwise create it (`mkdir -p docs/research/{run-id}-{topic-slug}-workdir`).
   Set `{scratch-dir}` = `docs/research/{run-id}-{topic-slug}-workdir`
7. Set output path: `docs/research/YYYY-MM-DD-repo-{topic-slug}.md` — the `repo-` infix distinguishes this pipeline's artifacts from web/structured pipeline outputs on the same date.
8. Set advisory path: `docs/research/YYYY-MM-DD-repo-{topic-slug}-advisory.md`
9. If `--compare`: set gap analysis path: `docs/research/YYYY-MM-DD-repo-{topic-slug}-gap-analysis.md`
10. If `--deeper`: set repomap path: `{scratch-dir}/repomap.md`
11. If `--survey` or `--deepest`: set survey path: `{scratch-dir}/survey.md`; set survey output path: `docs/research/YYYY-MM-DD-repo-{topic-slug}-survey.md`
12. If `--deepest`: set atlas sketch (scratch) and refined-output (docs/research/) paths — see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Atlas Path Conventions for the 3 sketch + 4 final artifact paths.
13. Set claims path: `docs/research/YYYY-MM-DD-repo-{topic-slug}.claims.json` — durable queryable index of per-specialist claim records merged by the synthesizer.

Announce: "Running Pipeline B (repo research, Agent Teams{', deepest mode' if --deepest}{', deeper mode' if --deeper and not --deepest}{', survey mode' if --survey and not --deepest}{', comparison mode' if --compare}) on {repo-path}."

## Step 2 — Holistic Survey (only if `--survey`)

If `--survey` is set and the EM judges a holistic overview is warranted:

1. **Read the survey prompt template** from:
   `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-survey-prompt-template.md`

2. **Fill in template fields:**
   - `[REPO_NAME]`, `[REPO_PATH]`, `[DATE]`
   - `[SCRATCH_DIR]` → scratch directory path
   - `[SPAWN_TIMESTAMP]` → current `date +%s`
   - If `--compare`: `[COMPARE_PROJECT_NAME]`, `[COMPARE_PROJECT_PATH]`

3. **Dispatch the survey agent:**
   ```
   Agent(
     model: "opus",
     prompt: <filled survey prompt>
   )
   ```
   This is a regular subagent — not a teammate. 30-minute ceiling.

4. **Read the survey** at `{scratch-dir}/survey.md`

5. **Decision gate — present to PM:**
   > "Survey complete — [brief 2-3 sentence summary of key findings]. Two options:
   > 1. **Survey is sufficient** — we have the overview we need. I'll save this as the deliverable.
   > 2. **Proceed with team pipeline** — use this survey as specialist context and go deep.
   > Which approach?"

6. **If PM chooses option 1:**
   - Copy survey to output path: `cp {scratch-dir}/survey.md {survey-output-path}`
   - Commit and present to PM. Pipeline ends here.

7. **If PM chooses option 2:** Proceed to Step 3 (Orient and Scope). The survey is saved
   and will be passed to specialists as context.

## Step 3 — Orient and Scope Repository (EM Direct)

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

Generate a dependency-weighted repomap before defining chunks — gives structural centrality data for chunk scoping and specialist deep-read prioritization. Five steps: (A) detect primary language(s), (B) extract import edges via language-appropriate grep, (C) resolve to files and count cross-references, (D) extract key exports, (E) write `{scratch-dir}/repomap.md` (Tier 1/2/3 by ref count) or skip if the import graph is too thin (<5 files with 2+ refs).

**Full grep patterns per language, repomap template, and skip criteria:** see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Phase 1.5.

### Phase 2: Scoping (informed by orientation{' and repomap' if --deeper})

6. **Define exactly 4 chunks** — domain-aligned, based on the repo's own architecture as understood from orientation. (4 chunks because the 4 specialists are teammates and the ceiling is 7: 7 - 2 teammate scouts - 1 synthesizer = 4 specialist slots. **The `- 2 scouts` term is Haiku-tier arithmetic only** — see Step 5 Phase A: Sonnet-tier scouts dispatch as non-teammate `general-purpose` agents and consume no slot, so the scout count is free there. The chunk count stays 4 on both tiers, because it is the specialist count that fixes it.) If `--deeper` produced a repomap, review Tier 1 file distribution across chunks — avoid concentrating all core files in a single chunk.
7. **Assign chunks to scouts** — the mapping is tier-dependent (derive the tier at Step 5 Phase A; the estimates in step 8 feed it). **Haiku tier: 2 scouts, Scout 1 gets chunks A+B, Scout 2 gets chunks C+D** — teammate slots are scarce. **Sonnet tier: one scout per chunk (4 scouts, 1 chunk each)** — they are not teammates, so nothing is bought by pairing, and halving each scout's load attacks the exact failure mode the tier exists to avoid.
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

## Step 4 — Create Team and All Tasks

### Spawn the First Teammate

Spawn the first teammate via the `Agent` tool — the team auto-forms (session-derived name); no explicit create step.

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

**2.5. Atlas sketch task** (only if `--deepest`, blocked by BOTH scouts):
```
TaskCreate(subject: "Atlas sketch: produce preliminary structural artifacts from scout data", description: "Read scout inventories and repomap, produce preliminary file index, system map, and connectivity matrix to {scratch-dir}/atlas-sketch-*.md")
TaskUpdate(taskId: "{atlas-sketch-id}", addBlockedBy: [<every scout task id>])   # 2 on the Haiku tier, 4 on the Sonnet tier
```

**3. Specialist tasks** (each blocked by BOTH scouts; also by atlas sketch if `--deepest`):
For each chunk (A, B, C, D):
```
TaskCreate(subject: "Analyze chunk {letter}: {description}", description: "Deep-read files, write assessment to {scratch-dir}/{letter}-assessment.md. {If compare: also write comparison to {scratch-dir}/{letter}-comparison.md.}")
TaskUpdate(taskId: "{specialist-id}", addBlockedBy: [<every scout task id>])   # 2 on the Haiku tier, 4 on the Sonnet tier
```
If `--deepest`:
```
TaskUpdate(taskId: "{specialist-id}", addBlockedBy: ["{atlas-sketch-id}"])
```

**Note:** In `--deepest` mode, specialist tasks are created upfront with blockers (same as other modes), but specialist agents are spawned LATER — after the atlas sketch completes (see Step 5 phased spawning). The `blockedBy` on atlas-sketch is belt-and-suspenders; the real gate is that specialist agents don't exist yet.

**3.5. Comparison-target sweep task** (only if `--compare`, blocked by all four specialists):
```
TaskCreate(subject: "Sweep the comparison target for questions no chunk owns", description: "Read all four comparisons and their open questions, sweep {compare-project-path} for the cross-lane facts chunking could not assign, write {scratch-dir}/comparison-target-sweep.md.")
TaskUpdate(taskId: "{sweep-id}", addBlockedBy: ["{specialist-A-id}", "{specialist-B-id}", "{specialist-C-id}", "{specialist-D-id}"])
```

**4. Block synthesizer on all specialists** (and on the sweep, if `--compare`):
```
TaskUpdate(taskId: "{synthesizer-id}", addBlockedBy: ["{specialist-A-id}", "{specialist-B-id}", "{specialist-C-id}", "{specialist-D-id}"])
```
If `--compare`:
```
TaskUpdate(taskId: "{synthesizer-id}", addBlockedBy: ["{sweep-id}"])
```

<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface (`ToolSearch("select:TaskCreate")` returns nothing)
→ fall back to `coordinator-tasks-mirror` for the same flight-recorder role; do not assume either
state without checking. When Task* is unavailable, dispatch the phases in order, waiting on each
completion notification — that is the ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

## Step 5 — Spawn Teammates

**Spawning model depends on mode:**
- **Default / `--deeper` / `--survey`:** Spawn all 7 teammates in one message (parallel). EM is freed immediately.
- **`--deepest`:** Phased spawning — spawn scouts + synthesizer first, wait for scouts, run atlas sketch, then spawn specialists. EM is freed after specialists are spawned (~7 min delay).

### Phase A: Spawn Scouts + Synthesizer

#### Scouts (model scales with repo size)

**Scout model selection — the tier picks the VEHICLE, not a `model:` parameter.** `coordinator:repo-scout` pins `model: haiku` and the engine-plane guard `enforce_agent_model_pin` hard-rejects any dispatch that passes `model:` alongside it. **Never pass `model:` to `coordinator:repo-scout`** — the dispatch is refused outright, and it is refused identically on the Step 5.5 recovery path, when a failed run can least afford it. Scaling up means dispatching a *different agent* carrying the same filled scout prompt:

| Tier | Dispatch | Ceiling |
|------|----------|---------|
| Haiku (default) | `subagent_type: "coordinator:repo-scout"`, **no `model:` parameter** | 5 min |
| Sonnet (escalated) | `subagent_type: "general-purpose"`, `model: "sonnet"`, prompt = the same filled scout template | 8–12 min |

Haiku scouts reliably inventory small chunks but fail at large scope — silently, and with confabulated DONE messages (empirically 2/2 Haiku scouts failed on a ~2500-file repo at ~250 files/chunk, 2026-06-27; see Step 5.5). Derive the tier from the Step 3 estimates:

- **`--scout-model {haiku|sonnet}` override (parsed in Step 1) wins if present.** State it: "Scout tier forced to {tier} via --scout-model." If `--scout-model sonnet` forces the Sonnet tier on a small repo, use the Haiku-tier ceiling (5 min) and OMIT the `[IF LARGE_CHUNK_BREADTH:]` block — the tier is the override, not the chunk size.
- **Else default by size:** **Sonnet tier** if the repo exceeds **~1000 files total**, OR any single scout's combined chunk load exceeds **~150 files**, OR any single scout's combined chunk load exceeds **~1.5MB of source**; **Haiku tier** otherwise.
- **File count is a weak proxy for scout load — check volume too.** A 216-file repo whose single largest file is 6,000+ lines and holds a third of its source loads a scout harder than a 900-file repo of small modules. Get both numbers during Step 3 orientation (`find {repo-path} -type f -name '*.{ext}' | wc -l` and `du -sh` over the chunk's directories) and escalate on whichever crosses first.
- State the derivation: "Repo ~{N} files / ~{S}MB, max scout load ~{M} files (~{V}MB) → scouts run on the {tier} tier."

**Ceiling scales too.** The 5-minute scout ceiling is unachievable at ~250 files/chunk even for a non-hallucinating scout. Fill `[CEILING_MINUTES]` in the scout prompt: **5** for Haiku-tier small chunks, **8–12** for Sonnet-tier large chunks (within 8–12: ~8 min for ~100–150 files/chunk, ~10 for ~150–200, ~12 for 200+). AND for large (Sonnet-tier) chunks, include the template's `[IF LARGE_CHUNK_BREADTH:]` block so the scout prioritizes record/contract-bearing files (schemas, public APIs, entry points) with full entries and inventories the rest by signature — breadth over exhaustive deep-read.

Read the scout prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-scout-prompt-template.md`

Fill in template fields for each scout (including `[CEILING_MINUTES]`, and the `[IF LARGE_CHUNK_BREADTH:]` block on the Sonnet tier). Chunk assignment follows the tier (Step 3 item 7): Haiku tier pairs chunks across 2 scouts; Sonnet tier gives each of 4 scouts a single chunk.

**Haiku tier (default) — no `model:` parameter:**
```
Agent(
  name: "scout-1",
  subagent_type: "coordinator:repo-scout",   # pinned haiku; passing model: is REFUSED
  prompt: <filled scout prompt for chunks A+B, Variant A preamble>
)
TaskUpdate(taskId: "{scout-1-id}", owner: "scout-1")

Agent(
  name: "scout-2",
  subagent_type: "coordinator:repo-scout",
  prompt: <filled scout prompt for chunks C+D, Variant A preamble>
)
TaskUpdate(taskId: "{scout-2-id}", owner: "scout-2")
```

**Sonnet tier — a different vehicle carrying the same prompt, one scout per chunk:**
```
Agent(
  name: "scout-a",
  model: "sonnet",
  subagent_type: "general-purpose",       # NOT a teammate — no team_name, no slot consumed
  prompt: <filled scout prompt for chunk A, Variant B preamble>
)
TaskUpdate(taskId: "{scout-a-id}", owner: "scout-a")
```
…and likewise `scout-b`, `scout-c`, `scout-d` for chunks B, C, D — all four in a single message. Because these are not teammates, **the 7-teammate ceiling does not constrain scout count on this tier**; one chunk each keeps every load inside the reliable range rather than pairing it back out of range. Create one scout task per scout and add all four to the specialists' (and, if `--deepest`, the atlas sketch's) `addBlockedBy` list, in place of the two `scout-1`/`scout-2` ids shown at Step 4.
Swap the TEXT-ONLY preamble variant with the tier: Variant A (forceful) for Haiku, Variant B (plain) for Sonnet. A Sonnet-tier scout carrying Variant A is the documented refusal case.

#### Synthesizer (Opus)

Read the synthesizer prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-synthesizer-prompt-template.md`

Fill in ALL template fields:
- `[REPO_NAME]`, `[SCRATCH_DIR]`, `[OUTPUT_PATH]`, `[TASK_ID]`
- `[ADVISORY_PATH]` → advisory path computed in Step 1
- `[CLAIMS_PATH]` → claims path computed in Step 1 (= `docs/research/YYYY-MM-DD-repo-{topic-slug}.claims.json`)
- `[COMPARE_MODE]` → true/false
- If compare: `[COMPARE_PROJECT_NAME]`, `[GAP_ANALYSIS_PATH]`

```
Agent(
  name: "synthesizer",
  model: "opus",
  subagent_type: "coordinator:research-synthesizer",
  prompt: <filled synthesizer prompt>
)
TaskUpdate(taskId: "{synthesizer-id}", owner: "synthesizer")
```

### Phase B: Atlas Sketch (only if `--deepest`)

**If NOT `--deepest`:** Skip this phase — spawn specialists immediately in Phase C alongside scouts and synthesizer (all in one message).

**If `--deepest`:** After spawning scouts + synthesizer, **run the Step 5.5 Scout Completion Gate now** — it is the wait-for-scouts-and-verify-disk mechanism. Do NOT dispatch the atlas sketch until the gate returns GATE PASS (or you have completed Step 5.5 recovery). Only then dispatch a Haiku atlas-sketch subagent (NOT a teammate — preserves the 7-teammate limit) using `pipelines/repo-atlas-sketch-prompt-template.md`. Verify the 3 sketch artifacts exist in `{scratch-dir}/`, mark the atlas-sketch task completed. On failure, specialists fall back to `--deeper` mode (repomap only).

**Template fields, dispatch syntax, verification details:** see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Phase B.

### Phase C: Spawn Specialists

For each chunk, read the specialist prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-specialist-prompt-template.md`

Fill in ALL template fields — including:
- `[SYNTHESIZER_NAME]` → `"synthesizer"`
- `[PEER_LIST]` → the other 3 specialists with their teammate names and chunk descriptions
- `[EXPECTED_FILE_COUNT]` → from the scoping survey
- `[MIN_MINUTES]`, `[MAX_MINUTES]`, `[MIN_SOURCES]` → from PM timing preferences (or defaults: 5 min, 15 min, 3 files)
- If `--compare`: include `[COMPARE_PROJECT_PATH]` and `[COMPARE_PROJECT_NAME]`
- If `--deeper` and repomap was generated (not skipped): include the `[IF DEEPER MODE]` section with `[SCRATCH_DIR]/repomap.md`
- If `--deepest` and atlas sketch artifacts exist: include the `[IF DEEPEST MODE]` section with atlas sketch paths
- If `--survey` and survey was produced: include the `[IF SURVEY MODE]` section with `[SCRATCH_DIR]/survey.md`

```
Agent(
  name: "chunk-{letter}",
  model: "sonnet",
  subagent_type: "coordinator:repo-specialist",
  prompt: <filled specialist prompt>
)
TaskUpdate(taskId: "{specialist-id}", owner: "chunk-{letter}")
```

**Dispatch all 4 specialists in a single message (parallel).**

## Step 5.5 — Scout Completion Gate (hard, disk-first)

Scouts can hit the documented "TEXT-ONLY" hallucination (see `coordinator/snippets/em-operating-doctrine.md` § Extensions to coordinator defaults ▸ Fan-out dispatch extras ¶ "Scouts: disk-first"; formerly `coordinator/CLAUDE.md` § "Scouts and Disk-First Verification", retired 2026-07-27): they go idle without ever calling Write, leaving specialists blocked on inventories that don't exist. **Worse — a scout can mark its task `completed` AND send a confabulated DONE message with fabricated line counts and a detailed fake findings summary for files it never wrote** (observed 2026-06-27: scout-2 reported *"both inventories written and verified on disk (8.9K/149 lines, 11K/227 lines)"* with a detailed findings summary, while `find` confirmed zero files on disk). **A `completed` task status and a plausible DONE message are NOT evidence of work — only disk is.** This gate is structural, not EM-diligence-dependent: it runs on every repo run and blocks downstream spawn until inventories are verified on disk.

**When this gate runs (mode-dependent):**
- **`--deepest`:** the gate runs at the END of Phase A — after every scout completes and **before** Phase B (atlas sketch) dispatches. Phase B's wait-for-all-scout-tasks clause IS this gate; do not dispatch the atlas sketch until GATE PASS (or a completed recovery).
- **Default / `--deeper` / `--survey`:** specialists were spawned upfront in Phase C, held by the scout task's `blockedBy` status. The gate runs here, before the EM is freed (Step 6), and re-opens the scout task to re-arm that block on failure.

Wait until every scout task reports `completed`, every scout emits `idle_notification`, or ~6 minutes have elapsed since spawn (whichever comes first) — "every", not "both": the Sonnet tier runs 4 scouts. Then run the automated disk-first gate:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/stub-file-gate" --min-lines 30 {scratch-dir}/A-inventory.md {scratch-dir}/B-inventory.md {scratch-dir}/C-inventory.md {scratch-dir}/D-inventory.md
```

**GATE PASS (all 4 files exist, ≥30 lines each):** Scouts succeeded. Proceed — default mode → Step 6 (EM Freed); `--deepest` → Phase B (Atlas Sketch).

**GATE FAIL (any file missing or <30 lines):** Do NOT proceed — a `completed` scout task with no/stub disk output is a **false completion**. First **re-open the scout task to re-arm the block** (`TaskUpdate(taskId: "{scout-N-id}", status: "in_progress")`) so atlas-sketch/specialist spawn stays gated, then recover in this preference order:

> **First, halt any already-running teammates.** In default/`--deeper`/`--survey` mode the specialists were spawned upfront and a false `completed` may have cleared their `blockedBy` before this gate fired — re-opening the scout task does NOT stop a teammate that is already executing. For each specialist (and `atlas-sketch` if `--deepest`) whose task shows `in_progress`, `SendMessage`: *"Gate detected scout false-completion — your inventory at `{path}` does not exist on disk. Pause: do not analyze or self-discover yet. Wait for a follow-up message pointing you to a valid inventory."* Then proceed with recovery below; the post-recovery wake step re-activates them.

**Preferred recovery — Sonnet-escalation (per coordinator "never re-Haiku" doctrine).** Coordinator CLAUDE.md § "Scouts and Disk-First Verification": *"Haiku TEXT-ONLY on a write-capable worker: escalate or self-execute, never re-Haiku (~30% recurrence)."* If the failed scout(s) ran on Haiku, redispatch the missing chunk(s) to a **non-teammate Sonnet scout** — the scout task is already gate-cleared, so a plain `Agent(...)`: no `team_name`, `model: "sonnet"`, **`subagent_type: "general-purpose"`** carrying the filled scout prompt with the Variant B preamble, `run_in_background: true`. **Do NOT pass `model: "sonnet"` to `coordinator:repo-scout`** — that agent pins Haiku and the engine-plane pin guard refuses the call, which would strand this recovery at exactly the moment it is needed (see Step 5 Phase A's tier table). Apply the same breadth-scoping (record/contract-bearing files first) and a size-derived ceiling (8–12 min). When the Sonnet scout's inventory lands, **re-run the gate `bash` block above**; only on PASS proceed to the post-recovery steps.

**Fallback — EM-stub (only when Sonnet redispatch also fails, or the scouts already ran on Sonnet).** Write stub inventories yourself for each still-missing chunk at the expected path. A stub is a structured file list pulled from `scope.md`'s chunk definitions, prefixed with:
   ```markdown
   > **Stub inventory** — written by EM after scout failure (TEXT-ONLY hallucination + failed/exhausted Sonnet redispatch).
   > Treat as a file list. Self-discover via Glob/Read; do not assume coverage is exhaustive.
   ```
List the chunk's directories/files from `scope.md`. If `--compare`, include the chunk's domain keywords as comparison hints.

**After either recovery path:**

1. **Mark scout tasks completed:** `TaskUpdate(taskId: "{scout-N-id}", status: "completed")` — clears the `blockedBy` gate on specialists and (if `--deepest`) atlas-sketch. For Sonnet-escalation, only after the gate `bash` block re-PASSES; for the EM-stub fallback, immediately after stubbing.
2. **Wake the blocked teammates** — `blockedBy` is a gate, not a trigger. `SendMessage` to each specialist (and `atlas-sketch` if `--deepest`):
   > "Scout recovery for the inventory at `{path}` — {re-ran on Sonnet / EM wrote a stub}. You are unblocked. {If stub: the stub is a file list, not a structured inventory; treat it accordingly and Read/Glob the named files yourself.}"
3. **Note the recovery in scope.md** so the synthesizer's advisory captures the degraded/recovered run: append a `## Recovery Notes` section listing which inventories were Sonnet-re-run vs stubbed.

After recovery, proceed to Step 6 (or Phase B if `--deepest`).

> **Generalizing the gate (note).** A specialist can false-complete the same way a scout can. The synthesizer's `blockedBy` on specialists is a status gate; the analogous structural guard is a hard disk check on `{scratch-dir}/{letter}-assessment.md` (≥30 lines each) before treating the synthesizer as ready. Apply this Step 5.5 gate pattern at that seam if specialist false-completion is observed.

## Step 5.7 — Comparison-Target Sweep (only if `--compare`)

**The gap this closes.** Chunks are drawn over the **studied** repo. Nobody owns "what does the
*comparison target* do here" — yet in a comparison run that is the entire point. Each specialist
compares within its own lane, so every cross-lane question about the target falls between
chunk boundaries and is answered by whoever happens to think of it. Observed twice on 2026-08-30,
in two repos independently: a peer's run closed four such questions only after specialists
finished and **three of the four flipped direction on closing** — two withdrew a spurious `ADOPT`
once the target turned out to already have the mechanism, and stronger; this repo's own run had
the sharpest Tier 1 finding surfaced by the synthesizer noticing an unowned two-halves transition
in the comparison target's own code, and its scope document had omitted two of the target's
surfaces outright.

**The expensive failure is a wrong-direction recommendation, not a missing one.** An unwithdrawn
spurious `ADOPT` becomes someone's sprint building what they already have.

After all four specialists have written their assessments and comparisons and cleared the disk
gate, and **before** the synthesizer runs, dispatch a single **plain background `Agent`** (not a
teammate — this preserves the 7-teammate limit; same pattern as the survey and the atlas sketch):

```
Agent(
  model: "sonnet",
  subagent_type: "general-purpose",
  run_in_background: true,
  prompt: <filled sweep prompt — see below>
)
```

The sweep agent gets:

- The four `{letter}-comparison.md` files and every open question, `[CONTESTED]`, and
  `[UNVERIFIED]` marker in them — **its worklist is the union of the four chunks' loose ends**
- **Plus any EM-supplied worklist items.** A fact can enter a run from outside it — a peer session
  messaging a specific claim mid-run, a PM steer, a cross-repo memo — and no marker anywhere in the
  chunk outputs will carry it, because it was never a specialist's open question. Pass such items
  in explicitly so they land in the same verification machinery instead of depending on the EM
  remembering to chase them. One optional input, not a mechanism
- The four `{letter}-assessment.md` files as context for what the studied repo does
- `scope.md`, including § Comparison Targets
- Read access to the **comparison project**, and a standing instruction that the comparison
  project — not the studied repo — is its subject

Its job, stated as three questions:

1. **Verify every absence claim with a targeted grep.** "The target does not have X" is the weakest
   claim class in a comparison run and carries most of its adoption recommendations — a specialist
   who did not find X and one who did not look for X write the same sentence. Grep the target for
   each asserted absence; an absence that survives is worth acting on, and one that does not is
   rewritten as `ALREADY-HAVE` with the file:line disproving it. Frame the arm on the claim, not on
   the verdict: this catches absence claims that never became an `ADOPT`, and it is what withdraws
   spurious steals. Verification is cheap and bounded — one command per claim — which is precisely
   what makes it a sweep job rather than a specialist's.
2. **What did chunking make unaskable?** Name the questions that span two or more chunks of the
   target, which no specialist could have owned, and answer the ones the target's own tree
   settles.
3. **What in the target is dead, disabled, or parameterised into being available?** A flag already
   shipped behind a default, a branch preserved for comparison, a test still asserting a retired
   path — these turn a proposed build into a parameter flip, and they are systematically invisible
   to a specialist reading the *other* repo.

It writes `{scratch-dir}/comparison-target-sweep.md` and replies `DONE: <path>`. Gate it on disk
(`stub-file-gate --min-lines 20`) exactly as scouts are gated; a false completion here silently
returns the pipeline to the pre-sweep behaviour.

Add the sweep file to the synthesizer's input list, and instruct the synthesizer that **where the
sweep contradicts a specialist verdict, the sweep wins on questions of fact about the comparison
target** — it read the target directly and with the whole worklist in view, which no specialist
did. The synthesizer still presents genuine judgment disagreements as trade-offs.

## Step 6 — EM Is Freed

After spawning all teammates (including specialists), announce:

**If `--deepest`:**
> "Research team running — scouts completed, atlas sketch produced, now 4 specialists + 1 synthesizer working autonomously on '{repo-name}'. Specialists analyze {MIN_MINUTES}-{MAX_MINUTES} min ({MIN_SOURCES}-file minimum). I'm available for other work — I'll be notified when the synthesizer completes."

**Otherwise:**
> "Research team is running autonomously on '{repo-name}' with 2 scouts + 4 specialists + 1 synthesizer. Scouts inventory files (~5 min), then specialists analyze {MIN_MINUTES}-{MAX_MINUTES} min ({MIN_SOURCES}-file minimum). I'm available for other work — I'll be notified when the synthesizer completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not broadcast WRAP_UP. The team handles everything.

## Step 7 — On Completion Notification

When you receive a notification that the synthesis task is complete:

1. Read the synthesis document at `{output-path}`
2. Verify it has substantive content (not just headers)
3. If comparison mode: read the gap analysis at `{gap-analysis-path}` and verify
4. Check for advisory: `test -f {advisory-path}` — if the file exists, read it
4.2. **Verify the fleet-readable competitor row landed** — third-party runs only (skip for this
   repo or a fleet sibling; the row is deliberately absent there). The synthesizer appends it by
   default, so this confirms the default fired rather than deciding whether to ask for it:

   ```bash
   grep -q '^## Fleet-Readable Competitor Row' {output-path} || echo "MISSING: competitor row"
   ```

   If it is missing, append it yourself from § Fleet-Readable Competitor Row of
   `repo-synthesizer-prompt-template.md` — do not re-dispatch the synthesizer for one table.
   **Check the `GitHub` cell is a bare `owner/repo` slug**, not a URL, a markdown link, or a
   directory name: it is the only load-bearing cell, and the downstream fleet reader skips a row
   whose locator is not slug-shaped. A wrong spelling there costs the whole row, silently from
   this side — the run looks complete and the reader renders nothing.
4.5. **Emit the durable claims pair** — you do this, not the synthesizer; the pair has exactly one writer. Never derive the pipeline token from the run-stem.

   **`--ran-at` is measured off disk, never quoted from the agent.** The synthesizer has no shell and no clock; the merge moment is the mtime of `merged-claims.json`. Read it:
   
      ```bash
      RAN_AT=$(python -c "import datetime,os,sys; print(datetime.datetime.fromtimestamp(os.path.getmtime(sys.argv[1]), datetime.timezone.utc).isoformat())" {scratch-dir}/merged-claims.json)
      ```
      ```powershell
      $RanAt = (Get-Item "{scratch-dir}/merged-claims.json").LastWriteTimeUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
      ```
      A timestamp offered in a completion message is an estimate — `claims-emit` validates RFC3339 *shape*, so a confident guess lands in the durable sidecar indistinguishable from a measured value. Take the pipeline token from the completion message; take the clock from the file.
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/claims-emit" \
     --producer repo-research \
     --out docs/research/{run-stem} \
     --ran-at "$RAN_AT" \
     --pipeline repo \
     < {scratch-dir}/merged-claims.json
   ```
   `--out` takes the stem (`{claims-path}` minus `.claims.json`); the CLI writes `{run-stem}.claims.json` and `{run-stem}.claims.meta.json` together. `--ran-at` must be RFC3339 and timezone-aware (naive, date-only, or empty is rejected — day precision recovered from the run-stem does not satisfy it); `--pipeline` must be non-blank and is never derived from `--producer`. Exit 0 = both written, 1 = producer-side failure, 2 = invalid invocation. A failed emission is a no-op on disk — an occupied stem is restored byte-for-byte, so re-running over an existing run-stem is safe.

5. **Dispatch the coverage auditor** — always-on for repo. Read the auditor prompt template from `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/coverage-auditor-prompt-template.md`, select the Pipeline B input block, fill in `[SYNTHESIS_PATH]`, `[RUN_STEM]` (strip `docs/research/` prefix and `.md` suffix from `{output-path}`), and `[SCRATCH_DIR]`, then dispatch as a **non-teammate Agent** (same pattern as the survey at Step 2, atlas-sketch at Step 5 Phase B, and atlas-refinement at Step 7.5 — all plain `Agent(...)` without `team_name`):
   ```
   Agent(
     model: "sonnet",
     prompt: <filled coverage-auditor prompt — Pipeline B input block>
   )
   ```
   The auditor reads `{scratch-dir}/*-claims.json` and `*-summary.md`, cross-references against the synthesis, and writes `{output-path minus .md}-coverage-audit.md`. It does not write the synthesis output path. Wait for `DONE: {sidecar-path}` before proceeding.

6. **Fidelity relay — `--deepest` only.** If `--deepest` was set, the synthesizer runs a gated internal fidelity-relay phase **before it marks its task complete** (the team is still alive at that point — the team is torn down automatically on session exit). This is a Team-1 internal sweep phase: the synthesizer wakes idle specialists via SendMessage, collects corrections scoped strictly to misrepresentation of existing synthesis prose, integrates, and runs a second pass. The relay mechanics live in `agents/research-synthesizer.md` (C5). repo-driver's role is only to state the gate: **the relay runs if and only if `--deepest`**. For `--deeper`-only or default runs, the relay does not fire.

7. The team auto-cleans on session exit — no explicit teardown step. The scratch directory persists.
8. If `--deepest`: proceed to **Step 7.5** before archiving. Otherwise, skip to step 9.
9. Commit:
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" "deep-research: complete — {topic-slug}"
   ```
10. Archive paper trail (atomic rename — no copy-then-delete race window):
    ```bash
    mv docs/research/{run-id}-{topic-slug}-workdir docs/research/archive/YYYY-MM-DD-repo-{topic-slug}
    ```
    **Precondition: `docs/research/` and `docs/research/archive/` resolve to the same filesystem.** If `archive/` is ever moved to a different mount, this archive step must be revisited — POSIX `mv` across filesystems degrades to copy-then-unlink, reopening the race window the change is meant to eliminate. Executor-time guard: `stat -c '%d' docs/research 2>/dev/null || stat -f '%d' docs/research` on both paths before mv; fail-loud if device IDs differ.
11. Commit: `coordinator-safe-commit "deep-research: archive + cleanup"`
12. Present executive summary to PM for discussion. If advisory exists, mention it: "The synthesizer flagged observations beyond scope — see the advisory at `{advisory-path}`." If `--deepest`: mention the atlas artifacts and their locations. Mention the coverage-audit sidecar: "Coverage audit written to `{output-path minus .md}-coverage-audit.md` — {present_count} claims present, {absent_count} absent." Mention the durable index artifacts: "Research-synthesis frontmatter prepended to `{output-path}`. Queryable claims index written to `{claims-path}` ({N} claims across {K} chunks)."

## Step 7.5 — Atlas Refinement (only if `--deepest`)

**Phase 3:** After the team is deleted and the assessment is verified, dispatch a Sonnet subagent (NOT a teammate — team is deleted) to refine the preliminary atlas using specialist analysis and synthesis findings, producing the 4th artifact (architecture summary) which requires specialist data. Use `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-atlas-prompt-template.md`. Verify all 4 artifacts (`atlas-file-index.md`, `atlas-system-map.md`, `atlas-connectivity-matrix.md`, `atlas-architecture-summary.md`) exist and have substantive content; on success, copy from scratch to the docs/research/ paths set in Step 1; on failure, note to PM and proceed (atlas is additive). Return to Step 7 item 9 (Commit).

**Note on the copy step:** The atlas-refinement step copies artifacts from the workdir into `docs/research/` (using `cp` since both paths are sibling directories); the workdir's atomic `mv` to `archive/` happens at Step 7 item 10 and carries the cross-FS precondition guard there. No separate guard is needed at Step 7.5 because both src and dst are under `docs/research/` by construction.

**Template fields, dispatch syntax, copy commands:** see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Step 7.5.

## Error Handling

See `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Error Handling Matrix for the full failure-mode → action table (survey/scout/atlas-sketch/specialist/synthesizer/atlas-refinement failures).
