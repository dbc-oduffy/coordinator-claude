# NotebookLM Plugin — Operating Notes

This plugin provides access to Google NotebookLM via the [notebooklm-mcp-cli](https://github.com/jacob-bd/notebooklm-mcp-cli) MCP server. It enables research on YouTube videos, podcasts, audio content, and other media that Claude cannot access directly.

## Plugin Lifecycle

This plugin is kept **disabled** in `settings.json` by default to avoid loading 35 MCP tools into the EM's context on every session. Enable it manually in `settings.json` when running NotebookLM research. The `/notebooklm-research` command does NOT enable or disable the plugin automatically — you must enable it before running the command and disable it when done. **The EM/coordinator should never call NotebookLM MCP tools directly** — all research flows through the `notebooklm-research-worker` agents dispatched by the command.

## Architecture — Pipeline D (Agent Teams)

This plugin uses a single-phase Agent Teams architecture. The EM scopes the research directly — designing notebook topology, questions, source strategy, and worker count with baked-in NLM best practices — then creates the team and is freed.

**Pipeline design informed by NotebookLM best practices research (2026-03-31, 413 lines, 35+ sources). Key findings folded into EM scoping guidance: source quality cascade, 10-25 optimal sources/notebook, citation-forcing question design, Studio output diversity.**

**Agent Team (scout + N workers + synthesizer):**
- **Haiku scout** — reads strategy.md, finds YouTube/podcast/article sources via WebSearch, writes `sources.md`. Task completion auto-unblocks workers.
- **Sonnet workers (1-3)** — each creates one NotebookLM notebook, ingests assigned sources (or uses `research_start`), runs queries, writes `{letter}-findings.md`. Sends DONE to synthesizer when complete.
- **Opus synthesizer** — blocked until all workers DONE. Reads all findings, cross-references across notebooks, writes final polished document, optionally writes a **Synthesizer Advisory** (`{output-path}-advisory.md`) with staff-engineer observations beyond the research scope (framing concerns, blind spots, surprising connections), then deletes all notebooks via MCP. Advisory is skipped if there's nothing beyond scope.

**Worker count is decided by the EM** based on topic breadth, NLM tier, and daily query budget:
- Free tier (50 queries/day): typically 1 worker, 5-6 questions
- Plus tier (500 queries/day): 1-2 workers, 7-8 questions each
- Ultra tier (5,000 queries/day): up to 3 workers, 8 questions each

## Authentication

- **Initial login:** Run `nlm login` in a terminal. This opens a browser for Google account authentication and extracts session cookies automatically.
- **Credentials stored at:** `~/.notebooklm-mcp-cli/`
- **If auth fails mid-session:** Call the `refresh_auth` MCP tool first. If that fails, re-run `nlm login` in a separate terminal.

## Rate Limits

| Tier | Queries/day | Sources/notebook | Notebooks |
|------|-------------|-----------------|-----------|
| Free | 50 | 50 | 100 |
| Plus | 500 | 100 | 500 |
| Ultra | 5,000 | 300 | 500 |

The 50 queries/day free-tier limit is the binding constraint. A single run with 3 workers × 5-8 questions = 15-24 queries. The EM factors tier and daily usage into worker count decisions to prevent quota exhaustion.

## Important Caveats

- Uses undocumented Google APIs — may break without notice
- NotebookLM is a Google product with its own terms of service
- AI-generated transcriptions and analysis may contain errors — cross-reference critical findings

## Notebook Housekeeping

Notebooks are automatically deleted by the synthesizer after each run. For orphan notebooks from crashed sessions:
1. List notebooks via `notebook_list`
2. Delete stale research notebooks that are no longer needed
3. Watch for notebooks named `{topic-slug}-{a|b|c}` — these are Pipeline D research notebooks

## MCP Tools

The MCP server exposes ~35 tools. Workers use a subset (~13) for the research pipeline. The synthesizer uses `notebook_delete` for cleanup. The full tool list is available via `ToolSearch("notebooklm")`. Key tools for research:

- `notebook_create` / `notebook_delete` — lifecycle management
- `notebook_get` / `notebook_list` — status and inventory
- `source_add` — ingest URLs, YouTube links, Drive files, text, PDFs
- `source_describe` / `source_get_content` — inspect processed sources
- `notebook_query` — ask questions with AI, get cited responses
- `studio_create` / `studio_status` / `download_artifact` — generate reports, mind maps, slides
- `research_start` / `research_status` / `research_import` — NLM built-in content discovery
- `refresh_auth` — refresh authentication tokens
