# Deep Research Pipelines

> **SUBAGENT PROHIBITION:** Deep Research pipelines are NEVER invoked by subagents, scouts, or dispatched agents acting on the EM's behalf. They are exclusively PM-gated: the PM asks for deep research, the EM confirms and runs it. A Sonnet scout doing a web brief must use WebSearch and WebFetch directly — NOT this pipeline. Any agent that is not the top-level EM must treat all deep-research commands as off-limits.

The coordinator ships multi-agent deep research pipelines for Claude Code. All pipelines use Agent Teams (fire-and-forget):

- **Pipeline A (Internet Research)** — investigate a topic across web sources via 1 Haiku scout (source corpus) + 3-5 Sonnet specialists (deep-read + verify) + 1 Opus synthesizer
- **Pipeline B (Repo Research)** — study a repository's architecture via 2 size-derived scouts (Haiku for small repos, Sonnet for large; file inventory) → 4 Sonnet specialists (analysis + optional comparison) → 1 Opus synthesizer
- **Pipeline C (Structured Research, v2.1)** — schema-conforming batch research via 1 Haiku scout + 1-5 Sonnet verifiers (adversarial peer challenges, CONTESTED resolution) + 1 Opus synthesizer (output-first with file-existence gate); outputs YAML/JSON matching the spec's output_schema
- **Pipeline D (NotebookLM)** — media research via NotebookLM for YouTube, podcasts, and content Claude can't access directly; 1 Haiku scout + 1-3 Sonnet workers + 1 Opus sweep; requires the NotebookLM MCP server. **Activation:** Pipeline D is default-off. Enable by activating the `notebooklm` carrier plugin (one settings flag), which carries its `.mcp.json`. Requires `uvx` and a valid `nlm login` session.

## Prerequisites

### Agent Teams (required for all pipelines)

Set in your `settings.json` under `env`:

```json
"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
```

Without this the pipelines will fail.

## Commands

- `/coordinator:research --mode=web <topic>` — Pipeline A: internet research
- `/coordinator:research --mode=repo <path> [--compare <project-path>] [--survey] [--deeper] [--deepest]` — Pipeline B: repo assessment (+ optional comparison, survey, repomap, atlas)
- `/coordinator:research --mode=structured <spec-path> [subject-key]` — Pipeline C: structured research
- Pipeline D is reached through the `notebooklm` carrier plugin once enabled — see § Pipeline D boundaries below

## Scope Limits

**More than 5 topics? Use `/spinoff`, not a bigger harness.** The web pipeline caps at 5 topics to stay under the web-tool concurrency ceiling. When a research need exceeds 5 topics, `/spinoff` the question set into chunks across separate sessions — each running the canonical pipeline under the cap — rather than hand-rolling an over-cap Workflow harness (which self-throttles indistinguishably from a platform gate; see `dispatching-parallel-agents.md` § Concurrency Budget).

## How It Works

All pipelines follow the same Agent Teams pattern:

1. **EM scopes** — defines chunks/topics, estimates sizes, asks PM for timing (~2 min)
2. **EM spawns the first teammate** via the `Agent` tool — the team auto-forms; teammates are then spawned in parallel (~1 min)
3. **EM is freed** — team works autonomously
4. **Haiku scouts** build shared artifacts (file inventories for repo, source corpus for web)
5. **Sonnet specialists** unblock, deep-read, cross-pollinate via messaging, self-govern timing
6. Each specialist sends `DONE` message to synthesizer (`blockedBy` is a status gate, not an event trigger)
7. **Opus synthesizer** reads specialist outputs, cross-references, writes final document(s), and optionally writes a **Synthesizer Advisory** — a companion file with staff-engineer observations beyond the research scope (framing concerns, blind spots, surprising connections). Absent if there's nothing beyond scope.
8. EM receives notification → cleanup (archive, commit, present results)

### Prior-Art Pre-Flight (always-on, all modes)

Before fan-out to any driver, the research skill dispatches `prior-art-checker` as a non-teammate advisory Agent. The pre-flight writes a sidecar to `{scratch-dir}/prior-art-check.md`; the EM reads the "Existing corpus" bucket and surfaces any same-subject corpus to the operator before spawning the research team. This step is advisory / REPORT-ONLY — it never blocks or aborts the run. If `prior-art-checker` is unavailable (e.g., deep-research installed standalone without coordinator), the step is gracefully skipped with a one-line log: *"prior-art pre-flight skipped: prior-art-checker not installed"*.

### Pipeline A specifics

- 1 Haiku scout — builds shared source corpus from web searches
- Specialists verify claims, resolve contradictions, enforce source recency
- Team protocol: `pipelines/deep-research/team-protocol.md`
<!-- Review: code-reviewer — F10: missing deep-research/ infix post-C4 pipeline relocation -->

### Pipeline B specifics

- 2 size-derived scouts (2 chunks each; Haiku for small repos, Sonnet for large) — produce structured file inventories with function signatures, constants, data flow
- In `--compare` mode: scouts also identify equivalent project files; specialists produce both assessment and comparison artifacts; synthesizer produces ASSESSMENT.md + GAP-ANALYSIS.md (with deduplication — assessment describes what IS, gap analysis describes what to CHANGE)
- In `--survey` mode: a solo Opus subagent produces a holistic 20-30KB narrative overview before the team runs. PM decides whether to proceed with the team or accept the survey as the deliverable. If the team proceeds, the survey is passed to specialists as context.
- In `--deeper` mode: EM generates dependency-weighted repomap during scoping; specialists read it before inventories to prioritize structurally central files
- In `--deepest` mode (implies `--deeper` and `--survey`): three-phase pipeline: (1) scouts + Haiku atlas sketch producing preliminary structural artifacts (file index, system map, connectivity matrix), (2) specialists with full context (survey + repomap + atlas sketch + inventory) validate atlas connections + synthesis with deduplication, (3) Sonnet atlas refinement post-synthesis producing the full 4-artifact architecture atlas including architecture summary
- Team protocol: `pipelines/deep-research/repo-team-protocol.md`
<!-- Review: code-reviewer — F10: missing deep-research/ infix post-C4 pipeline relocation -->

### Pipeline C specifics (v2.1)

- EM pre-processes spec YAML into flat `scout-brief.md` (Haiku can't parse complex YAML)
- EM runs spec quality checklist (6 items: schema clarity, falsifiable criteria, field mapping, existing data, extractable gates, adversarial terms)
- 1 Haiku scout — reads EM-processed scout-brief.md, maps findings to schema fields, writes per-topic discovery files, includes adversarial search pass-through
- 1-5 Sonnet verifiers (1 per topic) — verify scout's discoveries against existing data, challenge peers' field values, produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED/CONTESTED)
- Acceptance criteria + quality gate rules embedded in verifier prompts (self-validation replaces orchestrator re-dispatch)
- Synthesizer uses output-first ordering (skeleton → reconcile → validate → overwrite), resolves CONTESTED fields, writes annotations separately
- EM validates via hard file-existence gate before archival
- Annotations written to `synthesis-annotations.md` (separate from structured data)
- Manifest tracks completion per subject with `manifest_version: 2`
- Team protocol: `pipelines/deep-research/structured-team-protocol.md`
<!-- Review: code-reviewer — F10: missing deep-research/ infix post-C4 pipeline relocation -->

## Post-Synthesis: Coverage Auditor

After every synthesis — across all four pipelines — the EM dispatches the **coverage auditor** (`agents/coverage-auditor.md`) as a **non-teammate Agent**. This convention is always-on: no size floor, no opt-out. The synthesizer cannot grade its own homework; the auditor is the fresh-eyes corrective.

The auditor answers: *"Did the synthesis carry the research?"* It emits a `-coverage-audit.md` sidecar. It never writes the synthesis output path. Canonical pattern: `coordinator/docs/wiki/independent-coverage-auditor-pattern.md`.

**Two coverage artifacts, two questions** — a hard reader contract across all pipelines:

- `gap-report.md` — answers "did we research enough?" (input coverage; drives the web deepening gate; synthesizer-owned)
- `-coverage-audit.md` — answers "did the synthesis carry the research?" (output coverage; reader-facing completeness; auditor-owned)

These are distinct artifacts with distinct owners. The auditor does not replace or modify `gap-report.md`.

**Dispatch context — Agent-Teams vs `Workflow()`.** The pipelines natively dispatch the auditor as an Agent-Teams non-teammate, where `Write` to its sidecar path is permitted. If you instead drive the repo pipeline inside a `Workflow()`, the Workflow runtime denies subagent `Write` ("subagents return findings as text"). The auditor carries `Bash` and self-heals via a heredoc fallback (see `agents/coverage-auditor.md` § Persistence), so its sidecar still lands on disk — but **verify the sidecar exists on disk** after a Workflow-dispatched audit. A Workflow-driven research pipeline is bound by the same concurrency ceiling as the canonical Agent-Teams path — **≤5 concurrent web-tool callers** (the specialist-phase peak; see `dispatching-parallel-agents.md` § Concurrency Budget).

### Depth→relay mapping

In addition to the always-on coverage auditor, deep-tier pipelines run a **fidelity relay**: idle specialists are woken (via `SendMessage`) to verify their own content was faithfully represented in the synthesis. The relay runs as an internal synthesizer phase before the synthesizer marks its task complete — never as a Team-2 step.

| Pipeline | Coverage Auditor | Fidelity Relay | Relay trigger |
|---|---|---|---|
| A (web) | Always-on | Yes — Team-1 internal sweep phase, before synthesizer marks task complete | Gap-report / deepening-threshold signal |
| B (repo) | Always-on | Yes — Team-1 internal sweep phase | `--deepest` flag only |
| C (structured) | Reduced (drop-annotation check against `synthesis-annotations.md`) | OOS — no prose synthesis to distort; CONTESTED pre-empts | N/A |
| D (notebooklm) | Always-on (documented divergence — see below) | OOS — no depth tier; structurally cannot gate | N/A |

### Pipeline D boundaries (documented divergence)

Pipeline D is default-off. Enable the `notebooklm` carrier plugin (one settings flag) to activate it; that plugin carries its own `.mcp.json`. Requires `uvx` and `nlm login`.

D diverges from the unified auditor in two ways, both architectural:

1. **MCP-extended auditor.** On-disk `{letter}-claims.json` are a lossy extraction of the actual notebook content. The D auditor additionally carries notebooklm MCP tools (`notebook_query` and `cross_notebook_query` at minimum) with a graduated bootstrap (exact names → keyword fallback → graceful-skip-if-unavailable); `cross_notebook_query` lets it verify a cross-notebook claim against all spanned notebooks in one aggregated call. If MCP tools are absent, the auditor proceeds on `claims.json`-only and notes the degradation in the sidecar.

2. **Cleanup-deferred ordering.** The D auditor must run before notebook deletion. When `--cleanup` is in effect, notebook deletion at Step 6 is deferred until after the D auditor completes and its sidecar is written. Sequence: run auditor → delete notebooks.

3. **Relay is OOS for D** until D gains a depth concept. This is an architectural boundary (D has no `--deeper`/`--deepest` flags), not an appetite call. Revisit only if D adds depth flags.

See `agents/coverage-auditor.md` for the full auditor spec (input universe, sidecar format, D-specific MCP bootstrap). See `coordinator/docs/wiki/independent-coverage-auditor-pattern.md` for the canonical pattern.
