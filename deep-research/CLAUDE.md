# Deep Research Plugin

> **SUBAGENT PROHIBITION:** Deep Research pipelines are NEVER invoked by subagents, scouts, or dispatched agents acting on the EM's behalf. They are exclusively PM-gated: the PM asks for deep research, the EM confirms and runs it. A Sonnet scout doing a web brief must use WebSearch and WebFetch directly — NOT this pipeline. Any agent that is not the top-level EM must treat all deep-research commands as off-limits.

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

- `/deep-research:research --mode=web <topic>` — Pipeline A: internet research
- `/deep-research:research --mode=repo <path> [--compare <project-path>] [--survey] [--deeper] [--deepest]` — Pipeline B: repo assessment (+ optional comparison, survey, repomap, atlas)
- `/deep-research:research --mode=structured <spec-path> [subject-key]` — Pipeline C: structured research
- `/notebooklm-research <topic>` — Pipeline D: media research via NotebookLM (NotebookLM MCP server required)

**Former slash-commands** (`/web`, `/repo`, `/structured`) removed in Phase C skill-budget consolidation 2026-05-06; pipeline driver files moved to `pipelines/web-driver.md`, `pipelines/repo-driver.md`, `pipelines/structured-driver.md`. In v1.3.0 the three remaining mode-named commands collapsed into the single `--mode`-routed entry point (`/deep-research:research`).

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
- In `--compare` mode: scouts also identify equivalent project files; specialists produce both assessment and comparison artifacts; synthesizer produces ASSESSMENT.md + GAP-ANALYSIS.md (with deduplication — assessment describes what IS, gap analysis describes what to CHANGE)
- In `--survey` mode: a solo Opus subagent produces a holistic 20-30KB narrative overview before the team runs. PM decides whether to proceed with the team or accept the survey as the deliverable. If the team proceeds, the survey is passed to specialists as context.
- In `--deeper` mode: EM generates dependency-weighted repomap during scoping; specialists read it before inventories to prioritize structurally central files
- In `--deepest` mode (implies `--deeper` and `--survey`): three-phase pipeline: (1) scouts + Haiku atlas sketch producing preliminary structural artifacts (file index, system map, connectivity matrix), (2) specialists with full context (survey + repomap + atlas sketch + inventory) validate atlas connections + synthesis with deduplication, (3) Sonnet atlas refinement post-synthesis producing the full 4-artifact architecture atlas including architecture summary
- Team protocol: `pipelines/repo-team-protocol.md`

### Pipeline C specifics (v2.1)
- 1 Haiku scout — reads EM-processed scout-brief.md, maps findings to schema fields, writes per-topic discovery files, includes adversarial search pass-through
- 1-5 Sonnet verifiers (1 per topic) — verify scout's discoveries against existing data, challenge peers' field values, produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED/CONTESTED)
- Acceptance criteria + quality gate rules embedded in verifier prompts (self-validation replaces orchestrator re-dispatch)
- Synthesizer uses output-first ordering (skeleton → reconcile → validate → overwrite), resolves CONTESTED fields, writes annotations separately
- EM validates via hard file-existence gate before archival
- Team protocol: `pipelines/structured-team-protocol.md`
- Invoked via `/deep-research:research --mode=structured <spec-path> <subject>`

## Post-Synthesis: Coverage Auditor

After every synthesis — across all four pipelines — the EM dispatches the **coverage auditor** (`agents/coverage-auditor.md`) as a **non-teammate Agent**. This convention is always-on: no size floor, no opt-out. The synthesizer cannot grade its own homework; the auditor is the fresh-eyes corrective.

The auditor answers: *"Did the synthesis carry the research?"* It emits a `-coverage-audit.md` sidecar. It never writes the synthesis output path. Canonical pattern: `coordinator/docs/wiki/independent-coverage-auditor-pattern.md`.

**Two coverage artifacts, two questions** — a hard reader contract across all pipelines:
- `gap-report.md` — answers "did we research enough?" (input coverage; drives the web deepening gate; synthesizer-owned)
- `-coverage-audit.md` — answers "did the synthesis carry the research?" (output coverage; reader-facing completeness; auditor-owned)

These are distinct artifacts with distinct owners. The auditor does not replace or modify `gap-report.md`.

### Depth→relay mapping

In addition to the always-on coverage auditor, deep-tier pipelines run a **fidelity relay**: idle specialists are woken (via `SendMessage`) to verify their own content was faithfully represented in the synthesis. The relay runs as an internal synthesizer phase before TeamDelete — never as a Team-2 step.

| Pipeline | Coverage Auditor | Fidelity Relay | Relay trigger |
|---|---|---|---|
| A (web) | Always-on | Yes — Team-1 internal sweep phase, before Step 6 TeamDelete | Gap-report / deepening-threshold signal |
| B (repo) | Always-on | Yes — Team-1 internal sweep phase | `--deepest` flag only |
| C (structured) | Reduced (drop-annotation check against `synthesis-annotations.md`) | OOS — no prose synthesis to distort; CONTESTED pre-empts | N/A |
| D (notebooklm) | Always-on (documented divergence — see below) | OOS — no depth tier; structurally cannot gate | N/A |

### Pipeline D boundaries (documented divergence)

D diverges from the unified auditor in two ways, both architectural:

1. **MCP-extended auditor.** On-disk `{letter}-claims.json` are a lossy extraction of the actual notebook content. The D auditor additionally carries notebooklm MCP tools (`notebook_query` at minimum) with a graduated bootstrap (exact names → keyword fallback → graceful-skip-if-unavailable); if MCP tools are absent, the auditor proceeds on `claims.json`-only and notes the degradation explicitly in the sidecar.

2. **Cleanup-deferred ordering.** The D auditor must run before notebook deletion. When `--cleanup` is in effect, notebook deletion at Step 6 is deferred until after the D auditor completes and its sidecar is written. Sequence: run auditor → delete notebooks.

3. **Relay is OOS for D** until D gains a depth concept. This is an architectural boundary (D has no `--deeper`/`--deepest` flags), not an appetite call. Revisit only if D adds depth flags.

See `agents/coverage-auditor.md` for the full auditor spec (input universe, sidecar format, D-specific MCP bootstrap). See `coordinator/docs/wiki/independent-coverage-auditor-pattern.md` for the canonical pattern with both named instantiations (deep-research coverage-auditor and coordinator comprehensiveness-auditor-DRAFT).
