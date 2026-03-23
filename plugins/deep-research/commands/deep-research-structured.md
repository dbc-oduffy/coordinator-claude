---
description: "Pipeline C (Structured Research) using Agent Teams — schema-conforming research with a Haiku scout, Sonnet verifiers, and an Opus synthesizer, all as teammates. EM reads spec, pre-processes into scout-brief.md, spawns the team, and is freed. The team handles everything autonomously."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<spec-path> <subject-key>"
---

# Deep Research — Pipeline C (Structured Research) Agent Teams Driver

The EM reads the spec and pre-processes it, creates a team, spawns all teammates, and is **freed**. The team works autonomously:
- **Haiku scout** (1) — executes spec-derived search queries from scout-brief.md, maps findings to schema fields, writes per-topic discovery files
- **Sonnet verifiers** (1-5) — blocked until scout completes, then verify per-topic findings, compare against existing data, produce schema field tables with change types
- **Opus synthesizer** (1) — blocked until all verifiers complete, then cross-reconciles and writes schema-conforming output

The scout handles mechanical source discovery so verifiers can focus on schema-mapped verification. Verifiers self-govern their timing (floor, diminishing returns, ceiling) and self-check acceptance criteria and gate rules embedded in their prompts. The EM does not monitor or broadcast WRAP_UP. When the synthesizer marks its task complete, the EM receives a notification, validates schema conformance, and does cleanup.

## Arguments

`$ARGUMENTS`:
- `<spec-path>` — path to the research spec YAML file (required)
- `<subject-key>` — the subject key to research within the spec (required)

## Step 1 — Setup

1. Parse arguments: extract `spec-path` and `subject-key`
2. Read the spec YAML file at `{spec-path}`
3. Read the existing data file for this subject:
   - Find `known_context.per_subject.source_file` in the spec
   - Replace `{SUBJECT}` placeholder with `{subject-key}`
   - Read the resolved file path
4. Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp)
5. Record spawn timestamp: `date +%s` (Unix epoch seconds — passed to teammates for timing)
6. Generate subject slug from `{subject-key}` (e.g., `acme-corp`)
7. Create scratch directory:
   ```bash
   mkdir -p tasks/scratch/deep-research-teams/{run-id}
   ```

Announce: "Running structured research (Pipeline C, Agent Teams) on '{subject-key}' using spec '{spec-path}'."

## Step 2 — Pre-Process Spec (EM Direct)

This is judgment work — the EM does it directly:

1. **Read spec topics** — extract all topics defined in the spec for this subject
2. **Cap at 5 topics** — if >5, merge the two most related topics into one and note the merge in `scout-brief.md`
3. **Read existing data** — review the existing data file loaded in Step 1
4. **Identify schema gaps** — compare existing data fields against `output_schema` in the spec; note which fields are missing, stale, or unconfirmed
5. **Write `{scratch-dir}/scout-brief.md`** in this format:

   ```markdown
   # Scout Brief: {SUBJECT}

   ## Topic 1: {TOPIC_NAME}
   **Search domains:** {flattened from spec}
   **Focus questions:** {flattened from spec}
   **Schema fields to map:** {relevant fields from output_schema}

   ## Topic 2: ...
   (repeat for each topic)

   ## Acceptance Criteria (scout-relevant)
   - Minimum sources per topic: {from spec}
   - Adversarial search required: yes
   ```

6. **Extract quality gate rules** from the spec — these will be embedded in verifier prompts so verifiers can self-check before converging
7. **Ask the PM for timing preferences:**
   > "Research timing: default is 5-15 min with 5-source minimum per verifier. For a narrow subject, 3-8 min / 3 sources. For a complex subject, 5-20 min / 5 sources. What ceiling works for you?"

## Step 3 — Create Team and All Tasks

### Create Team

```
TeamCreate(team_name: "structured-{subject-slug}")
```

### Create Tasks (explicit ordering — blocking chain depends on this)

**Order matters.** Task IDs from earlier steps are referenced in later steps.

**1. Synthesizer task** (created first — will be blocked later):
```
TaskCreate(subject: "Synthesize all verifier findings into schema-conforming output", description: "Read all verifier outputs from {scratch-dir}/, cross-reconcile across topics, resolve contradictions, validate against output_schema, write final YAML/JSON output. Spec path: {spec-path}. Subject: {subject-key}. Scratch dir: {scratch-dir}.")
```

**2. Scout task** (no blockers — reads queries from disk):
```
TaskCreate(subject: "Execute spec-derived search queries and map findings to schema fields", description: "Read search topics from {scratch-dir}/scout-brief.md, execute via WebSearch, vet accessibility via WebFetch, map each finding to schema fields, write per-topic discovery files to {scratch-dir}/{subject-slug}-scout-{topic_id}.md")
```

**3. Verifier tasks** (each blocked by scout, one per topic):
For each topic:
```
TaskCreate(subject: "Verify topic {topic_id}: {topic_name}", description: "Read scout's per-topic discovery file at {scratch-dir}/{subject-slug}-scout-{topic_id}.md, compare against existing data, produce schema field table with change types (CONFIRMED/UPDATED/NEW/REFUTED), self-check acceptance criteria and gate rules.")
TaskUpdate(taskId: "{verifier-id}", addBlockedBy: ["{scout-task-id}"])
```

**4. Block synthesizer on all verifiers:**
```
TaskUpdate(taskId: "{synthesizer-id}", addBlockedBy: ["{verifier-1-id}", "{verifier-2-id}", ...])
```

## Step 4 — Spawn All Teammates

### Scout (Haiku)

Read the scout prompt template from:
`~/.claude/plugins/oduffy-custom/deep-research/pipelines/structured-scout-prompt-template.md`

Fill in template fields: `[SUBJECT]`, `[SPEC_PATH]`, `[SCRATCH_DIR]`, `[TASK_ID]`, `[SPAWN_TIMESTAMP]`.

```
Agent(
  team_name: "structured-{subject-slug}",
  name: "scout",
  model: "haiku",
  subagent_type: "deep-research:research-scout",
  prompt: <filled scout prompt>
)
TaskUpdate(taskId: "{scout-id}", owner: "scout")
```

### Verifiers (Sonnet)

For each topic, read the verifier prompt template from:
`~/.claude/plugins/oduffy-custom/deep-research/pipelines/structured-verifier-prompt-template.md`

Fill in ALL template fields — including `[SYNTHESIZER_NAME]` (use `"synthesizer"` as the teammate name), `[GATE_RULES]` (extracted from spec in Step 2), and `[ACCEPTANCE_CRITERIA]` (from spec). This is how verifiers know who to send the `DONE` wake-up message to and how to self-check before converging.

Fill in the template and spawn:
```
Agent(
  team_name: "structured-{subject-slug}",
  name: "verifier-{topic_id}",
  model: "sonnet",
  subagent_type: "deep-research:research-specialist",
  prompt: <filled verifier prompt>
)
TaskUpdate(taskId: "{id}", owner: "verifier-{topic_id}")
```

### Synthesizer (Opus)

Read the synthesizer prompt template from:
`~/.claude/plugins/oduffy-custom/deep-research/pipelines/structured-synthesizer-prompt-template.md`

Fill in ALL template fields — including `[OUTPUT_SCHEMA]` (full schema from spec), `[PHASE_2_GATE_RULES]` (quality gate rules for final output from spec), `[SUBJECT]`, `[SCRATCH_DIR]`, `[SPEC_PATH]`, `[TASK_ID]`.

```
Agent(
  team_name: "structured-{subject-slug}",
  name: "synthesizer",
  model: "opus",
  subagent_type: "deep-research:structured-synthesizer",
  prompt: <filled synthesizer prompt>
)
TaskUpdate(taskId: "{synthesizer-id}", owner: "synthesizer")
```

Dispatch ALL teammates in a single message (parallel).

## Step 5 — EM Is Freed

After spawning all teammates, announce:

> "Structured research team is running autonomously on '{subject-key}' with 1 scout + {N} verifiers + 1 synthesizer. Scout maps findings to schema fields (~2-3 min), then verifiers verify per-topic and produce schema field tables ({MIN_MINUTES}-{MAX_MINUTES} min, {MIN_SOURCES}-source minimum). I'm available for other work — I'll be notified when the synthesizer completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not broadcast WRAP_UP. The team handles everything.

## Step 6 — On Completion Notification

When you receive a notification that the synthesis task is complete:

1. Read the synthesizer output from `{scratch-dir}/synthesis-output.yaml` (or `.json`)
2. Check for advisory: `test -f {scratch-dir}/advisory.md` — if the file exists, read it (advisory is archived automatically with the scratch directory in step 6)
3. **Validate schema conformance BEFORE TeamDelete:**
   - Check all required fields from `output_schema` are present
   - Check enum values match the spec's allowed values
   - Check array fields meet minimum length requirements from spec
   - If validation **fails**: keep team alive, send a correction message to the synthesizer via `SendMessage` listing the specific fields that failed, and wait for a revised output
   - If validation **passes**: proceed to step 4
4. Update the manifest:
   - Set subject status to `complete`
   - Record `manifest_version: 2`
5. Commit:
   ```bash
   git add -A && git commit -m "deep-research: structured complete — {subject-slug}"
   ```
6. Archive paper trail (advisory archived automatically here with the rest of scratch):
   ```bash
   mkdir -p docs/research/archive/YYYY-MM-DD-{subject-slug}
   cp -r {scratch-dir}/* docs/research/archive/YYYY-MM-DD-{subject-slug}/
   rm -rf {scratch-dir}
   ```
7. Shut down the team: `TeamDelete(team_name: "structured-{subject-slug}")`
8. Commit: `git add -A && git commit -m "deep-research: structured archive + cleanup"`
9. Present summary of schema changes (CONFIRMED / UPDATED / NEW / REFUTED counts) to PM for review. If advisory exists, mention it: "The synthesizer flagged observations beyond scope — see the advisory (archived with paper trail at `docs/research/archive/YYYY-MM-DD-{subject-slug}/advisory.md`)."

## Error Handling

| Failure | Action |
|---------|--------|
| Scout fails (no discovery files written) | Verifiers fall back to self-directed discovery from spec focus questions — scout output is optional, not required |
| Scout times out (partial discovery files) | Verifiers use what's there + supplement with own searches for missing topics |
| Verifier hits ceiling and self-converges | Normal — verifier writes schema field table with what it has, marks task complete, sends DONE to synthesizer |
| Synthesizer doesn't wake after all verifiers complete | Verify verifiers sent DONE messages; if not, send manual nudge via SendMessage. If still stalled after 5 min, EM reads raw verifier outputs for PM |
| Schema validation fails after synthesizer completes | Keep team alive, message synthesizer with specific correction list; retry validation on revised output |
| All verifiers fail | TeamDelete, report to PM |
| Team creation fails | Fall back to relay pattern or manual research |
