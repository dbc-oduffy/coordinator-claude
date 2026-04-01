# notebooklm

Research YouTube videos, podcasts, and media that Claude cannot access directly. Uses Google NotebookLM as a research intermediary via MCP — it handles transcription, source ingestion, and AI-assisted querying. Structured claims extraction with adversarial coverage checking by the sweep agent.

## What It Does

The plugin dispatches an Agent Teams pipeline (Pipeline D): a scout finds sources, parallel workers each run one NotebookLM notebook, and a sweep agent cross-references findings, fills gaps, and writes the final document. The EM scopes the research and is freed once the team is running.

**Use this when:**
- Researching YouTube talks, conference videos, or podcasts
- PM provides URLs that need transcription or media processing
- NotebookLM's cross-source citation tracking adds value

**Use other pipelines when:**
- Codebase research → `/deep-research repo`
- Text articles and documentation → `/deep-research web`
- Structured batch research → `/structured-research`

## Prerequisites

- `notebooklm-mcp-cli` MCP server running and authenticated (`nlm login`)
- Plugin must be **manually enabled** in `settings.json` before use — disabled by default to avoid loading 35 MCP tools into every session
- Claude Code CLI

## Agents

| Agent | Model | Role |
|-------|-------|------|
| **research-scout** | Haiku | Source discovery — searches for YouTube/podcast/article URLs, vets accessibility, writes `sources.md` |
| **research-worker** | Sonnet | Notebook execution — creates one NLM notebook, ingests sources, runs queries, extracts structured claims to `{letter}-claims.json` |
| **research-sweep** | Opus | Coverage synthesis — cross-references worker findings, fills gaps via web research, writes final document and optional advisory |

Worker count (1-3) is decided by the EM based on topic breadth and NLM tier query budget.

## Commands

| Command | Purpose |
|---------|---------|
| `/notebooklm-research <topic>` | Run a full Pipeline D research run on the given topic |

**Flags:**
- `--context file1 file2` — background files to inform scoping
- `--sources url1 url2` — PM-provided URLs to research directly
- `--cleanup` — delete notebooks after run (default: preserve)

## Usage

```
/notebooklm-research "AI agent evaluation frameworks"
/notebooklm-research "Unreal Engine 5 performance" --sources https://youtube.com/watch?v=...
/notebooklm-research "GDC 2025 talks on procedural generation" --cleanup
```

Output is written to `~/docs/research/YYYY-MM-DD-{topic-slug}.md`. An advisory file (`-advisory.md`) is written by the sweep agent if it finds observations beyond the research scope.

## Rate Limits

| Tier | Queries/day | Sources/notebook |
|------|-------------|-----------------|
| Free | 50 | 50 |
| Plus | 500 | 100 |
| Ultra | 5,000 | 300 |

The EM asks for tier + timing ceiling before scoping to avoid quota exhaustion.

## Integration

Works standalone or alongside the coordinator plugin. The coordinator's `/session-end` and `/workday-complete` are unaffected — this plugin runs its own team autonomously and the EM is freed after spawning.

## Authors

Dónal O'Duffy & Claude
