# deep-research

Multi-agent deep research pipelines for Claude Code. Three pipelines cover internet sources, repository codebases, and schema-conforming structured research — all using Agent Teams with tiered model allocation.

## What It Does

### Pipeline A — Internet Research (v2.2)

1 Haiku scout builds a shared source corpus via web search. 3–5 Sonnet specialists deep-read sources, verify claims, and challenge each other adversarially. 1 Opus sweep agent checks coverage, fills gaps, and frames the final document. After Team 1 completes, an optional **iterative deepening pass** (Team 2) targets high-severity gaps identified in the sweep's gap report.

### Pipeline B — Repository Research

2 Haiku scouts inventory every file in assigned chunks of the target repo. 4 Sonnet specialists deep-read, analyze architecture, and optionally compare against a second project. 1 Opus synthesizer writes the final assessment.

- `--compare <path>` — adds a gap-analysis artifact comparing the target repo to your project
- `--deeper` — EM generates a dependency-weighted repomap during scoping; specialists use it to prioritize structurally central files
- `--deepest` — everything in `--deeper`, plus a Sonnet atlas agent produces architecture artifacts (file index, system map, connectivity matrix) after synthesis

### Pipeline C — Structured Research (v2.1)

Schema-conforming batch research across N entities. 1 Haiku scout maps findings to schema fields. 1–5 Sonnet verifiers challenge each other's field values and produce schema field tables with change types (CONFIRMED / UPDATED / NEW / REFUTED / CONTESTED). 1 Opus synthesizer writes a skeleton structured file immediately (crash insurance), resolves CONTESTED fields, validates, and overwrites with final YAML/JSON output.

## Prerequisites

- **Claude Code CLI**
- **Agent Teams experimental flag** — set in `settings.json` under `env`:
  ```json
  "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  ```
  Without this, all pipelines will fail.

## Agents

| Agent | Model | Role |
|-------|-------|------|
| **research-scout** | Haiku | Executes search queries, vets accessibility, builds shared source corpus |
| **research-specialist** | Sonnet | Deep-reads sources, verifies claims, challenges peers, outputs structured claims + summary |
| **research-synthesizer** | Opus | Adversarial coverage check, gap-filling, executive summary and conclusion (Pipeline A/B) |
| **repo-scout** | Haiku | Inventories repo files with function signatures, constants, and data flow |
| **repo-specialist** | Sonnet | Deep-reads repo chunks, optional project comparison, peer challenges |
| **structured-synthesizer** | Opus | Output-first skeleton → reconcile → validate → final YAML/JSON (Pipeline C) |

## Commands

| Command | Purpose |
|---------|---------|
| `/deep-research` | Router — dispatches to Pipeline A, B, or C based on first argument |
| `/web` | Pipeline A driver — internet research with iterative deepening |
| `/research` | Alias for `/deep-research` |
| `/structured` | Pipeline C driver — structured schema-conforming research |

**Invocation patterns:**

```
/deep-research web <topic>
/deep-research repo <path> [--compare <path>] [--deeper] [--deepest]
/deep-research structured <spec-path> <subject-key>
```

## Usage

**Internet research:**
```
/deep-research web "agent orchestration patterns in LLM frameworks"
```

**Repo assessment:**
```
/deep-research repo /path/to/onnxruntime --deeper
```

**Repo comparison:**
```
/deep-research repo /path/to/target-lib --compare /path/to/my-project
```

**Structured research (schema-conforming batch):**
```
/deep-research structured tasks/research/competitor-spec.yaml acme-corp
```

All pipelines are fire-and-forget — the EM spawns the team and is freed. Results are written to `docs/research/` and committed automatically.

## Integration with coordinator

This plugin works standalone. When used alongside the [coordinator plugin](https://github.com/oduffy-delphi/coordinator-claude), the EM delegates research directly via the commands above. The coordinator's `suggest-sonnet-research` hook (PreToolUse on WebSearch/WebFetch) nudges the EM toward these pipelines instead of ad-hoc direct web calls.

## Source of Truth

This plugin lives in [coordinator-claude](https://github.com/oduffy-delphi/coordinator-claude) at `plugins/deep-research/`.

## Authors

Dónal O'Duffy & Claude
