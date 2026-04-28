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

**Sweep prompt** should include:
- The research question and project context
- The scratch directory path: `{scratch-dir}`
- The list of specialist topic letters and their output file paths
- The output path for the final document: `{output-path}`
- The advisory output path: `{advisory-path}` (pre-computed in Step 1)
- The sweep task ID to mark complete when done
- Instruction: "Read all specialist outputs from {scratch-dir}/ ({letter}-claims.json and {letter}-summary.md for each specialist). Follow your agent definition's three phases: Phase 1 — assess all claims and emit gap report, Phase 2 — fill gaps via WebSearch/WebFetch, Phase 3 — frame with exec summary and conclusion. Write the final document to {output-path} and {scratch-dir}/synthesis.md. Write advisory to {advisory-path} and {scratch-dir}/advisory.md if you have observations beyond scope. If nothing beyond scope, note 'No advisory' in your completion message. You are explicitly encouraged to go beyond the original research scope where your judgment says it's warranted."

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

Parse the gap report's YAML front-matter. Evaluate:

```
DEEPEN if ANY of:
  - high_severity_gaps >= 2
  - contested_unresolved >= 1 AND the contradiction is material to the research question
  - coverage_score <= 3
  - The EM judges (from reading the prose) that a gap would materially change
    the document's recommendations or conclusions

DO NOT DEEPEN if ALL of:
  - high_severity_gaps == 0
  - coverage_score >= 4
  - Remaining gaps are cosmetic (low-severity, nice-to-have, tangential)

ALSO DO NOT DEEPEN if:
  - The PM's timing preference was fast/short (3-8 min ceiling) — honor the budget
```

**If NO DEEPEN:** Announce:
> "Gap report reviewed — {gap_count} gaps identified, {high_severity_gaps} high-severity. Coverage score: {coverage_score}/5. Gaps are minor — proceeding with current synthesis."

Proceed to Step 7.

**If DEEPEN:** Announce:
> "Gap report shows {high_severity_gaps} high-severity gaps and coverage score {coverage_score}/5. Recommending a deepening pass with {N} gap-specialists. Dispatching Team 2."

Proceed to Step 6.6.

## Step 6.6 — Dispatch Team 2 (Deepening Pass)

1. **Cluster gap targets:** Read the Gap Targets table from the gap report. Cluster related gaps into 1-3 specialist assignments (e.g., two absent claims in the same domain → one gap-specialist). Only include HIGH and MEDIUM severity gaps.

2. **Decide scout inclusion:** If gap targets require research in new topic areas not covered by Team 1's corpus, include a Haiku scout with new search queries. If gaps are refinements (contradictions, uncorroborated claims within existing topics), skip the scout — gap-specialists will do their own targeted searches.

3. **Record Team 2 spawn timestamp:** `date +%s`

4. **Create Team 2:**
   ```
   TeamCreate(team_name: "research-{topic-slug}-t2")
   ```

5. **Create tasks:**

   **Sweep task (merge mode):**
   ```
   TaskCreate(subject: "Merge sweep: produce deepening delta", description: "Read Team 1 gap report + Team 2 gap-specialist outputs, produce deepening-delta.md")
   ```

   **Scout task (if needed):**
   ```
   TaskCreate(subject: "Build supplementary corpus for gaps", description: "Execute new search queries for gap targets, write to {scratch-dir}/gap-corpus.md")
   ```

   **Gap-specialist tasks (1-3):**
   For each gap cluster, read the gap-specialist prompt template from:
   `${CLAUDE_PLUGIN_ROOT}/pipelines/gap-specialist-prompt-template.md`

   Fill in template fields: `[GAP_ID]`, `[GAP_DESCRIPTION]`, `[GAP_TYPE]`, `[GAP_SEVERITY]`, `[SUGGESTED_QUERIES]`, `[RELEVANT_TOPIC_LETTER]`, `[GAP_LETTER]` (use letters starting after Team 1's last letter, e.g., if Team 1 used A-D, gap-specialists use E-G), `[SCRATCH_DIR]`, `[TASK_ID]`, `[SPAWN_TIMESTAMP]`, `[SWEEP_NAME]` = "sweep-t2", peer list, research question, project context.

   ```
   TaskCreate(subject: "Fill gap {GAP_ID}: {description}", description: "...")
   TaskUpdate(taskId: "{gap-specialist-id}", addBlockedBy: ["{scout-task-id}"])  # only if scout exists
   ```

   **Block sweep on all gap-specialists:**
   ```
   TaskUpdate(taskId: "{sweep-t2-id}", addBlockedBy: ["{gap-specialist-ids...}"])
   ```

6. **Spawn all Team 2 teammates in a single message (parallel):**

   **Scout (if needed):**
   ```
   Agent(
     team_name: "research-{topic-slug}-t2",
     name: "scout-t2",
     model: "haiku",
     subagent_type: "deep-research:research-scout",
     prompt: <scout prompt with gap-specific queries>
   )
   ```

   **Gap-specialists:**
   ```
   Agent(
     team_name: "research-{topic-slug}-t2",
     name: "gap-{letter}",
     model: "sonnet",
     subagent_type: "deep-research:research-specialist",
     prompt: <filled gap-specialist prompt>
   )
   ```

   **Sweep (merge mode):**
   ```
   Agent(
     team_name: "research-{topic-slug}-t2",
     name: "sweep-t2",
     model: "opus",
     subagent_type: "deep-research:research-synthesizer",
     prompt: <sweep prompt with [MERGE_MODE: true], Team 1 synthesis path, gap report path, gap-specialist output paths, delta output path = {scratch-dir}/deepening-delta.md>
   )
   ```

7. **Announce:**
   > "Deepening team (Team 2) dispatched: {scout status} + {N} gap-specialists + 1 Opus merge sweep. Gap-specialists fill targeted gaps (~3-8 min each), then the sweep produces a delta. I'll be notified when complete."

**EM is freed again.** Do not poll.

## Step 6.7 — Team 2 Completion + Merge

When you receive a notification that the Team 2 sweep task is complete:

1. Read the delta document at `{scratch-dir}/deepening-delta.md`
2. Verify it has substantive content
3. Read Team 2's advisory if it exists

4. **Merge delta into the Team 1 synthesis at `{output-path}`:**
   - For each "Resolved Contradictions" entry: find the corresponding section in the synthesis and update it with the resolution. Remove any `[CONTESTED]` markers.
   - For each "Filled Gaps" entry: find the appropriate topic section and integrate the new findings. Replace `[UNFILLED GAP]` markers where applicable.
   - For each "Updated Claims" entry: update the relevant finding in the synthesis.
   - Update the "Open Questions" section: remove questions that were answered, add any from "Still Unresolved".
   - Strip all `[DEEPENING ADDITION]` and `[SWEEP ADDITION]` markers from the final document — provenance served its purpose during merge. The final document should read seamlessly.

5. Write the merged document back to `{output-path}` and `{scratch-dir}/synthesis-merged.md`

6. Commit:
   ```bash
   ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit "deep-research: Team 2 deepening merged — {topic-slug}"
   ```

7. Shut down Team 2: `TeamDelete(team_name: "research-{topic-slug}-t2")`

8. Proceed to Step 7.

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

| Failure | Action |
|---------|--------|
| Scout fails (no corpus written) | Specialists fall back to self-directed discovery (existing behavior) — the corpus is optional, not required |
| Scout times out (partial corpus) | Specialists use what's there + supplement with own searches |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and marks task complete |
| Sweep doesn't wake after all specialists complete | Verify specialists sent DONE messages to sweep; if not, send manual nudge via SendMessage. If still stalled after 5 min, EM reads raw specialist outputs for PM |
| All specialists fail | TeamDelete, report to PM |
| Agents stuck in idle loops | Known platform issue — agents may enter idle loops that resist shutdown. Commit and archive results before attempting TeamDelete. If TeamDelete fails ("active" agents), wait for timeout. Do NOT block on stuck agents — read available outputs and present to PM |
| Team creation fails | Fall back to relay pattern or manual research |
| **Team 2 sweep fails** | EM reads raw gap-specialist outputs from `{scratch-dir}/D-*-claims.json` and manually integrates into Team 1 synthesis |
| **All Team 2 gap-specialists fail** | TeamDelete Team 2, proceed to Step 7 with Team 1 synthesis as-is. Note: deepening failure is non-blocking — Team 1's output is already a complete document |
| **Gap report has no YAML front-matter** | Treat as `coverage_score: 4, high_severity_gaps: 0` — skip deepening (the sweep may be running an older version) |
