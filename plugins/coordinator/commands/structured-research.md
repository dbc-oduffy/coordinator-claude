---
description: "Create and run structured research campaigns — batch research across multiple subjects with the same topics, acceptance criteria, and output schema. Use when the PM asks for research on N entities with repeating structure (teams, companies, tools, etc.), when you need schema-conforming data (not prose), when existing data needs re-verification against fresh sources, or when a research spec already exists and needs execution."
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob", "Bash", "Agent", "WebSearch", "WebFetch", "AskUserQuestion"]
argument-hint: "'create' <output-dir> | <spec-path> [subject-key|'next'|'batch']"
---

# Structured Research — Pipeline C

Create and execute structured research campaigns. Two modes: **create** a research spec from the PM's brief, or **run** an existing spec by dispatching orchestrator agents.

**When to use this (EM pattern recognition):**
- PM asks you to research N entities with the same questions (e.g., "research all 65 teams", "compare these 12 services", "verify data for all players")
- You have a data schema and need to populate it from web sources
- You need to re-verify existing structured data against fresh sources
- The research has repeating structure across subjects — same topics, same acceptance criteria, same output shape

**When NOT to use this:**
- Exploring an unknown topic (use Pipeline A: `/deep-research`)
- Studying a codebase (use Pipeline B: `/deep-research`)
- One-off research with no repeating structure
- Quick lookups (use Context7)

**Reference:** Full pipeline design in `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/PIPELINE.md`. Spec format reference in `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/spec-format.md`.

## Arguments

`$ARGUMENTS` determines the mode:

### Create Mode
`/structured-research create <output-dir>`

Creates a new research spec from the PM's brief and the project's existing schema/data.

### Run Mode
`/structured-research <spec-path> [subject-key|'next'|'batch']`

Executes an existing spec by dispatching orchestrator agents. Second argument:
- A specific subject key (e.g., `FRA`) → run only that subject
- `next` → pick the next pending subject from the manifest
- `batch` → propose a batch based on batching config (default if omitted)

### Examples
- `/structured-research create tasks/journalism-research` — create a new spec
- `/structured-research tasks/journalism-research/spec.yaml FRA` — run FRA
- `/structured-research tasks/journalism-research/spec.yaml batch` — run next batch

---

## Create Mode: Build a Research Spec

When `$ARGUMENTS` starts with `create`:

### Step 1: Understand the Brief

Gather from the PM (ask if not already clear):
1. **What entities?** — Where's the list? How many? Any tiers/priority grouping?
2. **What topics per entity?** — What facets to research? (These become `topics` in the spec)
3. **What schema?** — Does a data schema already exist in the project? (Check for JSON schemas, TypeScript types, prompt files that define the output structure)
4. **What's already known?** — Is there existing data per entity? Where?
5. **What quality matters?** — Any acceptance criteria? Source language requirements? Freshness requirements?

### Step 2: Discover Project Context

Before writing the spec, read the project:
1. **Find the data schema** — look for existing type definitions, JSON schemas, or prompt files that define the output structure. This becomes the `output_schema`.
2. **Find existing data** — look for per-entity data files. The path pattern becomes `known_context.per_subject.source_file`.
3. **Find any prior research** — check for research docs, notes, or briefs that inform topic areas.

### Step 3: Write the Spec

Write to `<output-dir>/spec.yaml` using the format from `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/spec-format.md`:

1. **subjects** — source file, key field, total, batching tiers
2. **topics** — 2-6 topic areas with search domains and focus questions derived from the schema gaps
3. **acceptance_criteria** — per-topic and per-subject quality requirements
4. **gates** — quality gates between phases (at minimum: official source check after Phase 1, schema conformance after Phase 2)
5. **output_schema** — key fields with types, enums, required/optional fields — derived from the project's data schema
6. **known_context** — path to existing data per entity
7. **phases** — output path templates with variable substitution
8. **manifest_path** — `<output-dir>/manifest.json`

### Step 4: PM Review

Present the spec to the PM:
- "I've written a research spec at [path]. It covers [N subjects] across [M topics]. Here's a summary: [topics list, batching plan, key gates]. Review and approve before I run it?"

Do NOT proceed to run mode until the PM approves.

---

## Run Mode: Dispatch Orchestrator Agents

When `$ARGUMENTS` is a spec path:

### Step 1: Read Spec and Manifest

1. **Read the spec file** at the path from `$ARGUMENTS`
2. **Read or initialize the manifest** at the spec's `manifest_path`
   - If manifest exists: compare `spec_hash` against current spec file hash
     - If hash differs: **HALT** — report spec drift to PM. Options: `continue` (keep completed subjects) or `reset` (re-run all). Do not proceed without PM decision.
   - If no manifest: initialize with all subjects as `pending`, set `spec_path` and `spec_hash`
3. **Determine subject set** based on the second argument:
   - Specific key → verify it exists, check manifest status
   - `next` → find the first `pending` or `in_progress` subject
   - `batch` (or no argument) → read batching config, identify pending subjects, propose batch to PM, wait for approval

Report: "Spec loaded. [N] subjects selected: [list]. Dispatching orchestrators."

### Step 2: Dispatch via Deep Research Plugin

Use the Skill tool to invoke Pipeline C in the deep-research plugin:

```
Skill(skill: "deep-research:deep-research-structured", args: "<spec-path> <subject-key>")
```

For batch mode with multiple subjects, invoke the skill once per subject. The deep-research command handles team creation, spawn, and cleanup internally.

**Sequential execution (Phase 1):** Run subjects one at a time. Wait for each to complete before starting the next. This is the validated-first approach until Agent Teams concurrency is empirically tested.

### Step 3: Receive Results

When each Skill invocation returns:
1. **Read the status** — complete or partial
2. **Read the output file** at the path the skill reports (manifest updated internally by the deep-research pipeline)
3. **Validate schema conformance** — spot-check that required fields are present and enums use allowed values
4. **Commit** any output files the skill did not commit itself. Commit with message: `structured-research: {SUBJECT} complete`

### Step 4: Report to PM

After all subjects in the batch complete:

```
Structured research batch complete.
Spec: [path]
Subjects processed: [list with status]
Subjects remaining: [count pending in manifest]
Output files: [list of synthesis paths]
```

Report any schema conformance issues or gaps flagged by the synthesizer. Present the output for PM review before applying it to the project data.

---

## Failure Modes

| Failure | Prevention |
|---------|------------|
| Spec path doesn't exist | Check file exists before dispatching. Report clear error. |
| Manifest spec_hash drift | HALT and report to PM. Never silently continue on a changed spec. |
| Orchestrator returns partial | Report which phases completed and which failed. PM decides retry or skip. |
| Orchestrator returns empty output | Check output file exists and has content. Report failure to PM. |
| Mid-run crash | Manifest tracks progress per subject. Next `/structured-research` invocation resumes from where it left off. |
| Too many concurrent orchestrators | **Max 4 orchestrators at once.** Each orchestrator spawns N×topic parallel sub-agents. 68 Opus orchestrators each spawning Haiku/Sonnet agents caused catastrophic failure. Batch >4 subjects into waves of 4. |

