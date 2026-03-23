# Deep Research Plugin

Multi-agent deep research pipelines for Claude Code. All pipelines use Agent Teams (fire-and-forget):

- **Pipeline A (Internet Research)** — investigate a topic across web sources via 1 Haiku scout (source corpus) + 3-5 Sonnet specialists (deep-read + verify) + 1 Opus synthesizer
- **Pipeline B (Repo Research)** — study a repository's architecture via 2 Haiku scouts (file inventory) → 4 Sonnet specialists (analysis + optional comparison) → 1 Opus synthesizer
- **Pipeline C (Structured Research)** — schema-conforming batch research via 1 Haiku scout + 1-5 Sonnet verifiers (1 per topic) + 1 Opus synthesizer; outputs YAML/JSON matching the spec's output_schema

## Prerequisites

### Agent Teams (required for all pipelines)
Set in your `settings.json` under `env`:
```json
"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
```
Without this, `/deep-research` will fail.

## Commands

- `/deep-research web <topic>` — Pipeline A: internet research
- `/deep-research repo <path> [--compare <project-path>]` — Pipeline B: repo assessment (+ optional comparison)
- `/deep-research structured <spec-path> [subject-key]` — Pipeline C: structured research

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

### Pipeline C specifics
- EM pre-processes spec YAML into flat `scout-brief.md` (Haiku can't parse complex YAML)
- Scout maps findings to schema fields from the brief — per-topic output files, not a single corpus
- Verifiers produce schema field tables with change types, not prose findings
- Quality gates from spec are embedded in verifier prompts for self-validation
- Synthesizer produces YAML/JSON conforming to the spec's `output_schema`
- Manifest tracks completion per subject with `manifest_version: 2`

### Pipeline A specifics
- 1 Haiku scout — builds shared source corpus from web searches
- Specialists verify claims, resolve contradictions, enforce source recency
- Team protocol: `pipelines/team-protocol.md`

### Pipeline B specifics
- 2 Haiku scouts (2 chunks each) — produces structured file inventories with function signatures, constants, data flow
- In `--compare` mode: scouts also identify equivalent project files; specialists produce both assessment and comparison artifacts; synthesizer produces ASSESSMENT.md + GAP-ANALYSIS.md
- Team protocol: `pipelines/repo-team-protocol.md`

### Pipeline C specifics
- 1 Haiku scout — reads EM-processed scout-brief.md, maps findings to schema fields, writes per-topic discovery files
- 1-5 Sonnet verifiers (1 per topic) — verify scout's discoveries against existing data, produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED)
- Acceptance criteria + quality gate rules embedded in verifier prompts (self-validation replaces orchestrator re-dispatch)
- Synthesizer produces schema-conforming YAML/JSON, not prose
- Team protocol: `pipelines/structured-team-protocol.md`
- Invoked via `/structured-research <spec-path> <subject>` or `/deep-research structured <spec-path> <subject>`
