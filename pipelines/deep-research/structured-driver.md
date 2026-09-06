---
description: "PM-GATED — only invoke when the PM explicitly asks; EM must ask first if it thinks it's warranted; NEVER invoke from a subagent. Pipeline C (Structured Research) using Agent Teams — schema-conforming research with a Haiku scout, Sonnet verifiers, and an Opus synthesizer, all as teammates. EM reads spec, pre-processes into scout-brief.md, spawns the team, and is freed. The team handles everything autonomously."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<spec-path> <subject-key>"
---

# Deep Research — Pipeline C v2.1 (Structured Research) Agent Teams Driver

The EM reads the spec and pre-processes it, creates a team, spawns all teammates, and is **freed**. The team works autonomously:
- **Haiku scout** (1) — executes spec-derived search queries from scout-brief.md, maps findings to schema fields, writes per-topic discovery files
- **Sonnet verifiers** (1-5) — blocked until scout completes, then verify per-topic findings, compare against existing data, challenge peers' schema field values, produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED/CONTESTED)
- **Opus synthesizer** (1) — blocked until all verifiers complete, then writes skeleton output immediately, cross-reconciles, resolves CONTESTED fields, validates schema, and overwrites with final output

The scout handles mechanical source discovery so verifiers can focus on schema-mapped verification. Verifiers self-govern their timing (floor, diminishing returns, ceiling), self-check acceptance criteria and gate rules embedded in their prompts, and actively challenge each other's schema field values. The EM does not monitor or broadcast WRAP_UP. When the synthesizer marks its task complete, the EM receives a notification, validates schema conformance via a hard file-existence gate, and does cleanup.

## Arguments

`$ARGUMENTS`:
- `create <output-dir>` — Create Mode: build a new research spec from the PM's brief (see Step 0)
- `<spec-path> [subject-key|'next'|'batch']` — Run Mode: execute an existing spec

**Invocation:** `/research --mode=structured create <output-dir>` (Create Mode) or `/research --mode=structured <spec-path> [subject-key]` (Run Mode)

## Step 0 — Create Mode Gate

If `$ARGUMENTS` starts with `create`, run Create Mode (Steps 0a–0d below) instead of Run Mode. Do NOT proceed to Step 1 until the PM approves the spec.

### Step 0a: Understand the Brief

Gather from the PM (ask if not already clear):
1. **What entities?** — Where's the list? How many? Any tiers/priority grouping?
2. **What topics per entity?** — What facets to research? (These become `topics` in the spec)
3. **What schema?** — Does a data schema already exist in the project? (Check for JSON schemas, TypeScript types, prompt files that define the output structure)
4. **What's already known?** — Is there existing data per entity? Where?
5. **What quality matters?** — Any acceptance criteria? Source language requirements? Freshness requirements?

### Step 0b: Discover Project Context

Before writing the spec, read the project:
1. **Find the data schema** — look for existing type definitions, JSON schemas, or prompt files that define the output structure. This becomes the `output_schema`.
2. **Find existing data** — look for per-entity data files. The path pattern becomes `known_context.per_subject.source_file`.
3. **Find any prior research** — check for research docs, notes, or briefs that inform topic areas.

### Step 0c: Write the Spec

Write to `<output-dir>/spec.yaml` using the format from `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/spec-format.md`:

1. **subjects** — source file, key field, total, batching tiers
2. **topics** — 2-6 topic areas with search domains and focus questions derived from the schema gaps
3. **acceptance_criteria** — per-topic and per-subject quality requirements
4. **gates** — quality gates between phases (at minimum: official source check after Phase 1, schema conformance after Phase 2)
5. **output_schema** — key fields with types, enums, required/optional fields — derived from the project's data schema
6. **known_context** — path to existing data per entity
7. **phases** — output path templates with variable substitution
8. **manifest_path** — `<output-dir>/manifest.json`

### Step 0d: PM Review

Present the spec to the PM:
- "I've written a research spec at [path]. It covers [N subjects] across [M topics]. Here's a summary: [topics list, batching plan, key gates]. Review and approve before I run it?"

Do NOT proceed to Run Mode (Step 1) until the PM approves.

---

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
7. Create workdir — **accept-if-passed:** if `{scratch-dir}` is already bound (supplied by `research.md` Step 0), skip the `mkdir` and use the supplied value; otherwise create `docs/research/{run-id}-{subject-slug}-workdir`.
   Set `{scratch-dir}` = `docs/research/{run-id}-{subject-slug}-workdir`

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
7. **Include adversarial search terms** in the scout brief — at least one adversarial query per topic (e.g., "{subject} {field} problems", "{subject} controversy", "{subject} limitations")
8. **Ask the PM for timing preferences:**
   > "Research timing: default is 5-15 min with 5-source minimum per verifier. For a narrow subject, 3-8 min / 3 sources. For a complex subject, 5-20 min / 5 sources. What ceiling works for you?"

### EM Spec Quality Self-Score (required before dispatching)

Before creating the team, score the spec against the 6 items below and write the result to `{scratch-dir}/spec-score.md`. **This file must exist before Step 3 begins** — it is a hard gate, not advisory. The score is run metadata and will be archived with the paper trail.

Score each item pass (`[x]`) or fail (`[ ]`) and write this block to `{scratch-dir}/spec-score.md`:

```markdown
## Spec Quality Score
- [ ] Schema provided with field descriptions
- [ ] Acceptance criteria per field
- [ ] Scout search queries specified
- [ ] Verifier topic assignments clear
- [ ] Output path and format specified
- [ ] Subjects list complete
Score: N/6
```

A score below 5/6 requires PM alignment before proceeding — flag which items failed and why.

**Scoring criteria:**
- **Schema provided with field descriptions** — each field in `output_schema` has a clear type, allowed values (for enums), and enough context that a verifier can determine the correct value from a source
- **Acceptance criteria per field** — each criterion has a concrete pass/fail condition (not "good coverage" but "minimum 3 sources per topic")
- **Scout search queries specified** — spec or scout-brief.md includes explicit search queries per topic, not just topic names; includes at least one adversarial query per topic
- **Verifier topic assignments clear** — every required schema field is assigned to exactly one topic; no unassigned fields, no multiply-assigned fields
- **Output path and format specified** — spec defines the output file path and format (YAML/JSON) for this subject
- **Subjects list complete** — the subjects list in the spec is finalized; no placeholder or TBD entries

## Step 3 — Create Team and All Tasks

Spawn the first teammate via the `Agent` tool — the team auto-forms; no explicit create step.

### Create Tasks (explicit ordering — blocking chain depends on this)

**Order matters.** Task IDs from earlier steps are referenced in later steps.

**1. Synthesizer task** (created first — will be blocked later):
```
TaskCreate(subject: "Synthesize all verifier findings into schema-conforming output", description: "Read all verifier outputs from {scratch-dir}/, write skeleton structured data to {output-path} immediately, cross-reconcile across topics, resolve CONTESTED fields, validate against output_schema, overwrite {output-path} with final output, write annotations to {scratch-dir}/synthesis-annotations.md. Spec path: {spec-path}. Subject: {subject-key}. Scratch dir: {scratch-dir}. Output path: {output-path}.")
```

**2. Scout task** (no blockers — reads queries from disk):
```
TaskCreate(subject: "Execute spec-derived search queries and map findings to schema fields", description: "Read search topics from {scratch-dir}/scout-brief.md, execute via WebSearch, vet accessibility via WebFetch, map each finding to schema fields, write per-topic discovery files to {scratch-dir}/{subject-slug}-scout-{topic_id}.md")
```

**3. Verifier tasks** (each blocked by scout, one per topic):
For each topic:
```
TaskCreate(subject: "Verify topic {topic_id}: {topic_name}", description: "Read scout's per-topic discovery file at {scratch-dir}/{subject-slug}-scout-{topic_id}.md, compare against existing data, challenge peers' schema field values, produce schema field table with change types (CONFIRMED/UPDATED/NEW/REFUTED/CONTESTED), self-check acceptance criteria and gate rules.")
TaskUpdate(taskId: "{verifier-id}", addBlockedBy: ["{scout-task-id}"])
```

**4. Block synthesizer on all verifiers:**
```
TaskUpdate(taskId: "{synthesizer-id}", addBlockedBy: ["{verifier-1-id}", "{verifier-2-id}", ...])
```

<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface (`ToolSearch("select:TaskCreate")` returns nothing)
→ fall back to `coordinator-tasks-mirror` for the same flight-recorder role; do not assume either
state without checking. When Task* is unavailable, dispatch the phases in order, waiting on each
completion notification — that is the ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

## Step 4 — Spawn All Teammates

### Scout (Haiku)

Read the scout prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/structured-scout-prompt-template.md`

Fill in template fields: `[SUBJECT]`, `[SPEC_PATH]`, `[SCRATCH_DIR]`, `[TASK_ID]`, `[SPAWN_TIMESTAMP]`.

```
Agent(
  name: "scout",
  model: "haiku",
  subagent_type: "coordinator:research-scout",
  prompt: <filled scout prompt>
)
TaskUpdate(taskId: "{scout-id}", owner: "scout")
```

### Verifiers (Sonnet)

For each topic, read the verifier prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/structured-verifier-prompt-template.md`

Fill in ALL template fields — including `[SYNTHESIZER_NAME]` (use `"synthesizer"` as the teammate name), `[GATE_RULES]` (extracted from spec in Step 2), and `[ACCEPTANCE_CRITERIA]` (from spec). This is how verifiers know who to send the `DONE` wake-up message to and how to self-check before converging.

Fill in the template and spawn:
```
Agent(
  name: "verifier-{topic_id}",
  model: "sonnet",
  subagent_type: "coordinator:research-specialist",
  prompt: <filled verifier prompt>
)
TaskUpdate(taskId: "{id}", owner: "verifier-{topic_id}")
```

### Synthesizer (Opus)

Read the synthesizer prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/structured-synthesizer-prompt-template.md`

Fill in ALL template fields — including `[OUTPUT_SCHEMA]` (full schema from spec), `[PHASE_2_GATE_RULES]` (quality gate rules for final output from spec), `[OUTPUT_PATH]` (the spec-defined output path for this subject), `[SUBJECT]`, `[SCRATCH_DIR]`, `[SPEC_PATH]`, `[TASK_ID]`.

```
Agent(
  name: "synthesizer",
  model: "opus",
  subagent_type: "coordinator:structured-synthesizer",
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

1. **File-existence gate (HARD GATE):** Check whether the structured data file exists at `{output-path}`:
   <!-- NOTE: The synthesizer writes a schema-invalid skeleton immediately for crash insurance, then overwrites with the final valid output. This gate checks file-existence only — NOT schema validity; schema validity is step 2's job, run once the skeleton window has closed. Validating here, during the synthesis window, would cause false failures against the skeleton. -->
   - If **missing**: schema validation FAILED. Do NOT archive. Keep team alive.
     Send correction message to synthesizer via `SendMessage`:
     > "OUTPUT FILE MISSING: Expected structured data at {output-path}. You must write schema-conforming YAML/JSON to this path. Your annotations at synthesis-annotations.md are supplementary — the structured data file IS the deliverable."
     Wait for revised output. Re-validate from step 1.
   - If **exists**: proceed to content validation.

2. **Content validation:** Read `{output-path}` and validate schema conformance BEFORE archival:
   - Check all required fields from `output_schema.key_fields` are present
   - Check enum values match the spec's allowed values
   - Check array fields meet minimum length requirements from spec
   - **If `output_schema.reference` is set:** resolve it relative to the spec file's own
     directory (see `spec-format.md`), read the referenced schema, and check the output against
     it structurally — required top-level keys present, types matching, no fields typed outside
     the referenced definition. This is real conformance checking against the external
     definition, not the file-existence check in step 1 above.
   - If validation **fails**: keep team alive, send a correction message to the synthesizer via `SendMessage` listing the specific fields that failed, and wait for a revised output
   - If validation **passes**: proceed to step 3

3. **Coverage auditor dispatch (always-on, non-teammate Agent):**

   > **Fidelity relay is OOS for Pipeline C.** The relay's job is catching post-hoc prose
   > distortion of a specialist finding whose author is now idle. Structured synthesis has no
   > prose to distort — the output is schema-conforming YAML/JSON (`structured-synthesizer.md:59`).
   > Additionally, verifiers already challenge each other's field values adversarially pre-synthesis
   > (CONTESTED resolution is mandatory, `structured-team-protocol.md:44-49`). The relay would
   > solve a problem that structurally cannot occur.

   The reduced coverage auditor for Pipeline C verifies that every verifier finding either
   maps to a schema field in the structured output OR was explicitly dropped with an annotation
   in `synthesis-annotations.md`. Findings absent from both constitute silent coverage loss.

   Read the prompt template from:
   `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/coverage-auditor-prompt-template.md`

   Select the **Pipeline C — Structured Research (reduced auditor)** input block. Fill in:
   - `[SYNTHESIS_PATH]` — `{output-path}`
   - `[RUN_STEM]` — strip `docs/research/` prefix and `.md` suffix from `{output-path}` (e.g. `docs/research/2026-06-30-subject-structured.md` → `2026-06-30-subject-structured`)
   - `[SCRATCH_DIR]` — `{scratch-dir}`
   - `[OUTPUT_DIR]` — directory containing `synthesis-annotations.md` (same as `{scratch-dir}`)

   Dispatch as a **plain Agent — NOT a teammate** (preserves the 7-slot ceiling):

   ```
   Agent(
     prompt: <filled coverage-auditor prompt with structured input block>,
     model: "sonnet",
     subagent_type: "coordinator:coverage-auditor"
   )
   ```

   Wait for the auditor to complete and return `DONE: {sidecar-path}`.
   The sidecar is written to `{output-path minus .md}-coverage-audit.md`.

   If the auditor reports `absent` findings (verifier findings with no field mapping and no drop
   annotation), read the sidecar and include an `absent_findings` summary in the PM-facing report
   at step 10. Do not re-open the team or re-request synthesis changes — the auditor is a
   completeness pointer, not a correction trigger.

3.5. **Queryable index layer — run-record + claims + gap-report (always-on):**

   <!-- Pipeline C divergence: body is a thin link to the structured payload, NOT prose.
        emit frontmatter deterministically; DO NOT template prose in the body —
        the body stays agent-authored (for pipeline C the body is a thin link). -->

   Derive the run-stem: `{run-id}-{subject-slug}-structured`

   **a. Run-record** (`docs/research/{run-stem}.md`):

   Read `{scratch-dir}/gap-signal.md` for `coverage_score` (from its frontmatter).
   Compute `source_count` by counting unique URL entries across all "Sources Cited"
   sections in `{scratch-dir}/*-findings.md`.
   Derive `topic_facets` as the list of topic names from the spec.
   Derive `confidence_summary` as the majority Confidence value (HIGH/MEDIUM/LOW)
   across all schema field table rows in all verifier findings files.

   Write `docs/research/{run-stem}.md` — frontmatter block first, then thin-link body:

   ```markdown
   ---
   title: "Structured Research: {subject-key}"
   question: "{research_question from spec if present; else '{subject-key} schema field population'}"
   created: {YYYY-MM-DD}
   pipeline: structured
   source_count: {N}
   topic_facets: [{topic1}, {topic2}, ...]
   coverage_score: {coverage_score from gap-signal.md frontmatter, or null if file absent}
   confidence_summary: "HIGH|MEDIUM|LOW"
   ---
   ```

   Body (EM authors directly — 2–3 lines; DO NOT inline the structured payload):
   Write a thin-link body pointing to the structured output and claims index. Example shape
   (adapt subject and paths, keep body minimal):

   ```
   Structured research output for **{subject-key}** (Pipeline C).
   Structured payload: [{output-path}]({output-path})
   Claims index: [docs/research/{run-stem}.claims.json](docs/research/{run-stem}.claims.json)
   ```

   **b. Claims** (`docs/research/{run-stem}.claims.json`):

   Read all `{scratch-dir}/*-findings.md`. For each data row in each "## Schema Field Table"
   section (skip header rows and rows where the Field cell is a placeholder), emit one
   JSON claim object. Field mapping:

   | Verifier finding column | research-claim field | Notes |
   |------------------------|---------------------|-------|
   | `Field` (schema field path) | `topic_tags[1]` | Also use as second topic tag alongside `{topic-id}` |
   | `Value` (verified value) | `claim_text` | Format: `"Schema field [{Field}] for [{subject-key}]: {Value}"` |
   | `Source` (`{URL} ({YYYY-MM-DD})`) | `source_url` + `source_date` | Split on ` (` — URL before, date inside parens |
   | `Confidence` | `confidence` | Direct: HIGH / MEDIUM / LOW |
   | `Change Type` | `type` + `contested_by` | CONFIRMED/UPDATED/NEW → `"fact"`; REFUTED → `"limitation"`; CONTESTED → `"fact"` + set `contested_by` |
   | `Existing Value` (when not `"—"`) | `evidence` | Omit if value is `"—"` |

   For CONTESTED rows, set:
   ```json
   "contested_by": "Peer challenge — see {scratch-dir}/synthesis-annotations.md for resolution"
   ```

   Generate `id` for each row: `"{run-stem}-{topic-id}-{row-index-zero-padded-3}"`,
   e.g., `"2026-06-30-12h00-acme-structured-t1-001"`.

   The array shape:
   ```json
   [
     {
       "id": "...",
       "claim_text": "...",
       "confidence": "HIGH|MEDIUM|LOW",
       "source_url": "...",
       "source_date": "YYYY-MM-DD",
       "topic_tags": ["{topic-id}", "{field-path}"],
       "type": "fact|limitation",
       "evidence": "...",
       "contested_by": "..."
     }
   ]
   ```

   Omit optional fields (`evidence`, `contested_by`, `source_date`) when they have no value.

   **Do not write the durable files yourself** — the pair
   (`docs/research/{run-stem}.claims.json` + `.claims.meta.json`) has exactly one writer.
   Pipe the array you just constructed into it:

   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/claims-emit" \
     --producer structured-research \
     --out docs/research/{run-stem} \
     --ran-at {RFC3339 timezone-aware timestamp captured now} \
     --pipeline structured \
     < {scratch-dir}/merged-claims.json
   ```

   Write the array to `{scratch-dir}/merged-claims.json` first (bare top-level JSON array),
   then invoke the above. `--out` takes the stem; the CLI writes both files together.
   `--ran-at` must be RFC3339 and timezone-aware (naive, date-only, or empty is rejected — day
   precision recovered from `{run-stem}` does not satisfy it, and makes a same-day run
   unrecoverable downstream). `--pipeline` is `structured`, matching the run-record
   frontmatter's `pipeline:` value; it must be non-blank and is never derived from
   `--producer`. Exit 0 = both written, 1 = producer-side
   failure, 2 = invalid invocation. A failed emission is a
   no-op on disk — an occupied stem is restored byte-for-byte, so re-running over an existing
   run-stem is safe.

   **c. Gap-report** (`docs/research/{run-stem}-gap-report.md`):

   Read `{scratch-dir}/gap-signal.md`.

   - If the file **is absent** (synthesizer crashed before Step 6.5): log warning
     "gap-signal.md absent — gap-report skipped" and omit the gap-report file. Note in
     Step 10 summary.
   - If `gap_count` is **0 AND** `contested_unresolved` is **0**: skip the gap-report file
     entirely. Note "No gap-report emitted — all schema fields resolved, no contested
     unresolved" in Step 10 summary.
   - Otherwise (`gap_count > 0` OR `contested_unresolved > 0`): write the gap-report file:

   ```markdown
   ---
   deepening_recommended: {deepening_recommended from gap-signal.md}
   gap_count: {gap_count}
   coverage_score: {coverage_score}
   high_severity_gaps: {high_severity_gaps}
   medium_severity_gaps: {medium_severity_gaps}
   contested_unresolved: {contested_unresolved}
   ---

   {Gap Targets section verbatim from gap-signal.md "## Gap Targets" block}
   ```

4. Check for advisory: `test -f {scratch-dir}/advisory.md` — if the file exists, read it

5. Update the manifest:
   - Set subject status to `complete`
   - Record `manifest_version: 2`

6. Commit (includes `docs/research/{run-stem}.md`, the `docs/research/{run-stem}.claims.json`
   + `docs/research/{run-stem}.claims.meta.json` pair emitted by `claims-emit` at step b, and
   `docs/research/{run-stem}-gap-report.md` if emitted):
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" "deep-research: structured complete — {subject-slug}"
   ```

7. Archive paper trail (atomic rename — no copy-then-delete race window):
   ```bash
   mv docs/research/{run-id}-{subject-slug}-workdir docs/research/archive/YYYY-MM-DD-{subject-slug}
   ```

   **Precondition: `docs/research/` and `docs/research/archive/` resolve to the same filesystem.** If `archive/` is ever moved to a different mount, this archive step must be revisited — POSIX `mv` across filesystems degrades to copy-then-unlink, reopening the race window the change is meant to eliminate. Executor-time guard: `stat -c '%d' docs/research 2>/dev/null || stat -f '%d' docs/research` on both paths before mv; fail-loud if device IDs differ.

8. The team auto-cleans on session exit — no explicit teardown step.

9. Commit: `coordinator-safe-commit "deep-research: structured archive + cleanup"`

10. Present summary of schema changes (CONFIRMED / UPDATED / NEW / REFUTED / CONTESTED-resolved counts) to PM for review. Include the queryable index layer locations: "Run-record at `docs/research/{run-stem}.md`; claims index at `docs/research/{run-stem}.claims.json`." If a gap-report was emitted, note it: "Gap-report at `docs/research/{run-stem}-gap-report.md` ({gap_count} gaps, coverage score {coverage_score})." If no gap-report was emitted, note why (all resolved or gap-signal missing). If advisory exists, mention it: "The synthesizer flagged observations beyond scope — see the advisory (archived with paper trail at `docs/research/archive/YYYY-MM-DD-{subject-slug}/advisory.md`)." If the coverage auditor reported absent findings, include a brief summary: "The coverage auditor found {N} verifier findings with no field mapping and no drop annotation — see `{output-path minus .md}-coverage-audit.md`."

## Error Handling

| Failure | Action |
|---------|--------|
| Scout fails (no discovery files written) | Verifiers fall back to self-directed discovery from spec focus questions — scout output is optional, not required |
| Scout times out (partial discovery files) | Verifiers use what's there + supplement with own searches for missing topics |
| Verifier hits ceiling and self-converges | Normal — verifier writes schema field table with what it has, marks task complete, sends DONE to synthesizer |
| Synthesizer doesn't wake after all verifiers complete | Verify verifiers sent DONE messages; if not, send manual nudge via SendMessage. If still stalled after 5 min, EM reads raw verifier outputs for PM |
| Schema validation fails after synthesizer completes | Keep team alive, message synthesizer with specific correction list; retry validation on revised output |
| Synthesizer writes prose but no structured data file | File-existence gate catches this. Keep team alive, send correction message listing the expected output path and format. Re-validate on revised output. |
| All verifiers fail | Team auto-cleans on session exit; report to PM |
| Team creation fails | Fall back to relay pattern or manual research |
| Agents stuck in idle loops | Known platform issue — commit and archive available results; agents auto-clean on session exit. Read available outputs and present to PM. |
