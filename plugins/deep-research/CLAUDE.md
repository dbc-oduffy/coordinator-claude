# Deep Research Plugin

Multi-agent deep research pipelines for Claude Code. All pipelines use Agent Teams (fire-and-forget):

- **Pipeline A (Internet Research)** — investigate a topic across web sources via 1 Haiku scout (source corpus) + 3-5 Sonnet specialists (deep-read + verify) + 1 Opus synthesizer
- **Pipeline B (Repo Research)** — study a repository's architecture via 2 Haiku scouts (file inventory) → 4 Sonnet specialists (analysis + optional comparison) → 1 Opus synthesizer
- **Pipeline C (Structured Research, v2.1)** — schema-conforming batch research via 1 Haiku scout + 1-5 Sonnet verifiers (adversarial peer challenges, CONTESTED resolution) + 1 Opus synthesizer (output-first with file-existence gate); outputs YAML/JSON matching the spec's output_schema
- **Pipeline D (NotebookLM Research)** — media research via NotebookLM for YouTube, podcasts, and content Claude can't access directly; 1 Haiku scout + 1-3 Sonnet workers + 1 Opus sweep; requires the NotebookLM MCP server (scoped to the `notebooklm` sub-plugin — enable before use)

## Prerequisites

### Agent Teams (required for all pipelines)
Set in your `settings.json` under `env`:
```json
"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
```
Without this, `/deep-research` will fail.

## Commands

- `/deep-research web <topic>` — Pipeline A: internet research
- `/deep-research repo <path> [--compare <project-path>] [--deeper] [--deepest]` — Pipeline B: repo assessment (+ optional comparison, repomap, atlas)
- `/deep-research structured <spec-path> [subject-key]` — Pipeline C: structured research
- `/notebooklm-research <topic>` — Pipeline D: media research via NotebookLM (NotebookLM MCP server required)

## How It Works

All three pipelines follow the same Agent Teams pattern:

1. **EM scopes** — defines chunks/topics, estimates sizes, asks PM for timing (~2 min)
2. **EM creates team** and spawns all teammates in parallel (~1 min)
3. **EM is freed** — team works autonomously
4. **Haiku scouts** build shared artifacts (file inventories for repo, source corpus for web)
5. **Sonnet specialists** unblock, deep-read, cross-pollinate via messaging, self-govern timing
6. Each specialist sends `DONE` message to synthesizer (`blockedBy` is a status gate, not an event trigger)
7. **Opus synthesizer** reads specialist outputs, cross-references, writes final document(s), and optionally writes a **Synthesizer Advisory** — a companion file with staff-engineer observations beyond the research scope (framing concerns, blind spots, surprising connections). Absent if there's nothing beyond scope.
8. EM receives notification → cleanup (archive, commit, present results)

### Pipeline C specifics (v2.1)
- EM pre-processes spec YAML into flat `scout-brief.md` (Haiku can't parse complex YAML)
- EM runs spec quality checklist (6 items: schema clarity, falsifiable criteria, field mapping, existing data, extractable gates, adversarial terms)
- Scout maps findings to schema fields from the brief — per-topic output files, not a single corpus; includes adversarial search pass-through
- Verifiers produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED/CONTESTED), actively challenge peers' schema field values, use SCHEMA_OVERLAP messages for cross-field evidence sharing
- Quality gates + acceptance criteria embedded in verifier prompts for self-validation
- Synthesizer uses output-first ordering: writes skeleton to output path immediately (crash insurance), then reconciles, resolves CONTESTED fields, validates, and overwrites with final output
- EM validates via hard file-existence gate — missing output file blocks archival and triggers correction
- Annotations written to `synthesis-annotations.md` (separate from structured data)
- Manifest tracks completion per subject with `manifest_version: 2`
- Team protocol: `pipelines/structured-team-protocol.md`

### Pipeline A specifics
- 1 Haiku scout — builds shared source corpus from web searches
- Specialists verify claims, resolve contradictions, enforce source recency
- Team protocol: `pipelines/team-protocol.md`

### Pipeline B specifics
- 2 Haiku scouts (2 chunks each) — produces structured file inventories with function signatures, constants, data flow
- In `--compare` mode: scouts also identify equivalent project files; specialists produce both assessment and comparison artifacts; synthesizer produces ASSESSMENT.md + GAP-ANALYSIS.md
- In `--deeper` mode: EM generates dependency-weighted repomap during scoping; specialists read it before inventories to prioritize structurally central files
- In `--deepest` mode (implies `--deeper`): after synthesis, a Sonnet subagent produces architecture atlas artifacts (file index, system map, connectivity matrix, architecture summary) from the team's findings
- Team protocol: `pipelines/repo-team-protocol.md`

### Pipeline C specifics (v2.1)
- 1 Haiku scout — reads EM-processed scout-brief.md, maps findings to schema fields, writes per-topic discovery files, includes adversarial search pass-through
- 1-5 Sonnet verifiers (1 per topic) — verify scout's discoveries against existing data, challenge peers' field values, produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED/CONTESTED)
- Acceptance criteria + quality gate rules embedded in verifier prompts (self-validation replaces orchestrator re-dispatch)
- Synthesizer uses output-first ordering (skeleton → reconcile → validate → overwrite), resolves CONTESTED fields, writes annotations separately
- EM validates via hard file-existence gate before archival
- Team protocol: `pipelines/structured-team-protocol.md`
- Invoked via `/structured-research <spec-path> <subject>` or `/deep-research structured <spec-path> <subject>`
