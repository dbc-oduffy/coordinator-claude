# NotebookLM Research Team Protocol

> Referenced by agent definitions and the `notebooklm-research` command.

## Overview

Chatty-Workflow NotebookLM research: the EM scopes research directly — designing notebook topology, questions, source strategy, and worker count — writes `strategy.md`, then fires ONE background `Workflow` whose script runs a scout stage, a worker stage (one `agent()` per notebook), and a sweep stage, and is **freed**. Completion is the Workflow's task notification. The agents handle everything autonomously — source discovery, notebook creation, ingestion, querying, coverage assessment, and gap-filling. Notebook cleanup is optional (`--cleanup` flag; default: keep).

## Architecture

```
EM: Scope research → Write strategy.md → Fire Workflow → FREED
         │
         ├── Stage 1: Haiku scout
         │   Reads strategy.md, finds best YouTube / podcast / article sources
         │   Writes: {scratch-dir}/sources.md
         │
         ├── Stage 2: Sonnet worker(s) — 1 to 3, per strategy.md, in parallel
         │   Each creates own notebook, ingests assigned sources, queries
         │   Writes: {scratch-dir}/{letter}-claims.json + {letter}-summary.md
         │
         └── Stage 3: Opus sweep (the overseer)
             Reads all claims (JSON), assesses coverage, fills gaps
             Writes: {output-path}
             Writes: {output-path}-advisory.md (if anything beyond scope)
             Returns the completion message to the EM
```

## Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** (`scout`) | Haiku | 1 | Reads strategy.md, finds best YouTube / podcast / article sources via WebSearch, writes sources.md |
| **Worker** (`worker-a`…) | Sonnet | 1-3 | Creates own notebook, tags it with the run slug, ingests assigned sources, runs queries, extracts structured claims, writes `{letter}-claims.json` + `{letter}-summary.md`, returns |
| **Sweep** (`sweep`, overseer) | Opus | 1 | Reads all worker claims (JSON), assesses coverage, fills gaps via follow-up queries and WebSearch, writes final polished document, merges worker claims to `{scratch-dir}/merged-claims.json` (the EM emits the durable claims pair from it), optionally writes advisory, lists preserved notebook IDs for the EM to delete post-audit (sweep does NOT delete). Its return value is the only one that reaches the EM. |

## Stage Ordering

```
Stage 1  scout                    → returns, sources.md written
Stage 2  workers (parallel)       → all return, {letter}-claims.json + {letter}-summary.md written
Stage 3  sweep                    → returns the completion message to the EM
```

Ordering gates the stages: a stage starts when the previous stage's `agent()` calls return (`await`, or `parallel()` for the worker fan-out). A returned agent is never woken; the next stage is a fresh dispatch. Workers never address the EM, the sweep, or each other — they operate independent notebooks with no cross-pollination during execution, so no mailbox traffic is expected. A role that must leave a note for a peer appends `{"from": "<role>", "text": "..."}` to `{scratch-dir}/mail/<role>.jsonl`, and a reader appends `{"read": true}` after reading.

A scout that fails or returns without `sources.md` does not stop the run: workers fall back to self-directed discovery (§ Failure Handling).

## Scout Protocol

The scout finds media sources — optimized for YouTube, podcasts, and audio content that NLM excels at.

- Reads `{scratch-dir}/strategy.md` for search guidance per notebook (see "Search guidance for scout" field)
- **For "scout-provided" notebooks:** WebSearch + WebFetch to find and verify YouTube videos, podcasts, articles
- **For "research_start" notebooks:** Note in sources.md that this notebook uses NLM built-in discovery — the worker will use `research_start` MCP tool
- Writes `{scratch-dir}/sources.md` using `## Sources for Notebook A/B/C` convention
- **No messaging** — returning starts the worker stage
- **Timing:** 5 minute ceiling. This is mechanical discovery — go fast.

## Worker Protocol

The worker stage starts after the scout has returned, so `strategy.md` and `sources.md` are complete when a worker begins.

- Reads `## Notebook {letter}` section from strategy.md for its assignment
- Reads `## Sources for Notebook {letter}` from sources.md for its source list
- Bootstraps MCP tools via graduated ToolSearch (exact names → keyword fallback → fail gracefully)
- If source strategy is "scout-provided": ingest scout-provided URLs via `source_add`
- If source strategy is "research_start": use `research_start` MCP tool for NLM discovery
- Creates own notebook named `{topic-slug}-{letter}`
- Runs all assigned research questions, extracting structured claims per response
- **Records notebook ID in summary file** (for sweep cleanup)
- Writes `{scratch-dir}/{letter}-claims.json` (structured claim objects) and `{scratch-dir}/{letter}-summary.md` (human-readable overview with notebook metadata)
- Returns `DONE: Notebook {letter} complete — {claims path} + {summary path}`; the script passes each return value to the sweep stage

**Timing:** 25 minute ceiling (configurable via `estimated_ceiling` in strategy.md). Note: source ingestion time depends on NLM processing speed for the content type.

## Return Protocol

- **Worker return:** exactly one `DONE: Notebook {letter} ...` line per worker, with a failure or rate-limit note appended when applicable. Never a message to a peer or the EM.
- **Sweep return:** the completion message the EM acts on (output path, merged-claims path, preserved notebook IDs, advisory status). The only return value that reaches the EM.
- **Scout:** returns when `sources.md` is written; no message.

## Self-Governance Timing

| Agent | Ceiling | Notes |
|-------|---------|-------|
| Scout | 5 min | Mechanical discovery — go fast |
| Workers | 25 min (default) | Configurable via strategy.md `estimated_ceiling` field. NLM ingestion time varies. |
| Sweep | No strict ceiling | Starts after all workers return; assesses coverage, fills gaps, writes final doc then cleans up notebooks |

**Clock mechanism:** Spawn timestamp is provided in each prompt as `[SPAWN_TIMESTAMP]` (Unix epoch seconds). Agents check elapsed time via `date +%s` in Bash and compare against spawn timestamp.

## Rate Limit Budgeting

The EM factors NLM tier limits into its scoping decisions:

| Tier | Queries/day | Worker count guidance |
|------|-------------|----------------------|
| Free | 50 | 1 worker, 5-6 questions (use ~12 queries/run) |
| Plus | 500 | Up to 2 workers, 7-8 questions each (~30 queries/run) |
| Ultra | 5,000 | Up to 3 workers, 8 questions each (~50 queries/run) |

Workers report remaining quota if available from MCP responses. Strategy.md includes `total_expected_queries` to help the EM track budget.

## Data Contract

**strategy.md** (written by EM, read by scout + workers):

```markdown
---
worker_count: N
total_expected_queries: M
tier_assumption: free|plus|ultra
---

## Notebook A
- Focus: ...
- Custom instructions: ...
- Questions: [list]
- Source strategy: scout-provided | research_start
- Search guidance for scout: ...
- Estimated ceiling: N min

## Notebook B (if worker_count >= 2)
...
```

**sources.md** (written by scout, read by workers):

```markdown
# Sources for NotebookLM Research

Generated by scout at [timestamp].

## Sources for Notebook A
1. [title] — [URL]
   - Type: YouTube / Podcast / Article
   - Accessible: YES / NO / PARTIAL
   - Notes: ...

## Sources for Notebook B (if applicable)
...

## Notes for research_start notebooks
Notebook C uses research_start — worker should use NLM discovery, not scout-provided URLs.
```

**{letter}-claims.json** (written by workers, read by sweep):

```json
[
  {
    "id": "{letter}-001",
    "finding": "Specific factual finding extracted from NLM response",
    "evidence_excerpt": "Most relevant 1-3 sentences from NLM response. Prefix with [PARAPHRASED] if condensed.",
    "query": "The question that produced this finding",
    "notebook_sources": ["Source 1 title", "Source 3 title"],
    "source_url": "https://www.youtube.com/watch?v=... (or null)",
    "source_date": "YYYY-MM-DD (or null)",
    "confidence": "HIGH | MEDIUM | LOW",
    "type": "fact | limitation | pattern | recommendation | capability",
    "cross_notebook": "B — contradicts their source quality finding (or null)",
    "transcription_suspect": false
  }
]
```

**{letter}-summary.md** (written by workers, read by sweep):

```markdown
# NotebookLM Research: {topic} — Notebook {letter}

## Metadata
- **Notebook ID:** {id}    ← sweep reads this for cleanup
- **Notebook Name:** {name}
- **Queries Asked:** {N}
- **Sources Ingested:** {M}
- ...

## Overview
[Human-readable summary of the notebook's findings]
```

## Durable claims field mapping

The sole statement of how `{letter}-claims.json` worker fields map to `research-claim.schema.json`. The sweep merges all workers' arrays into `{scratch-dir}/merged-claims.json` with this mapping; the EM emits the durable claims pair from it.

| Worker field | `research-claim.schema.json` field | Rule |
|---|---|---|
| `id` | `id` | As-is (e.g. `A-001`) |
| `finding` | `claim_text` | Direct |
| `confidence` | `confidence` | Direct |
| `type` | `type` | `capability` → `fact`; fact/limitation/pattern/recommendation direct |
| `evidence_excerpt` | `evidence` | Direct |
| `cross_notebook` | `contested_by` (contradiction) or `corroborated_by` (corroboration) | By value semantics |
| `source_url` | `source_url` | Carried through when the worker supplied a non-null value |
| `source_date` | `source_date` | Carried through when the worker supplied a non-null value |
| (derived by sweep) | `topic_tags` | `["nlm", "notebook-{letter}", "{focus-area-slug}"]` |
| `query`, `notebook_sources`, `transcription_suspect` | (dropped) | Scratch-only |

**Null-omission rule:** omit the key entirely when the worker value is null — never emit `null` and never a placeholder. `claims-emit` rejects the whole batch on the first null, and a fabricated citation is worse than an absent one.

`source_url` is consumed by external corpus readers; the sweep reports the count of claims lacking one in its completion message.

## Failure Handling

- **Auth expiry (worker):** Call `refresh_auth`, retry once. If it fails again, write partial claims and return with a failure note.
- **Source ingestion failure (worker):** Log the failure in summary.md, continue with remaining sources. Do not abort.
- **research_start failure (worker):** Retry once. If persistent, note failure in summary.md and attempt alternative sources if scout provided any.
- **Rate limiting (worker):** Write partial claims immediately. Return with a rate limit note. Do not retry — the sweep will note the gap.
- **Query failure (worker):** Retry once. Log and continue with remaining questions.
- **Scout finds no sources for a notebook:** Worker falls back to self-directed discovery (targeted WebSearch for the notebook's topic area) or uses `research_start` if topic allows.
- **Scout times out (partial sources.md):** Workers use what's available + note which notebooks have incomplete source lists.
- **All workers fail:** The sweep finds no worker outputs and says so in its return value; the EM reports it to the PM.

## Coverage-Auditor Lifecycle

Pipeline D uses the **always-on** coverage auditor — dispatched by the EM as a plain `Agent` **after** the sweep returns and **before** notebook cleanup. The auditor answers the same two questions as the web/repo auditor: (1) did the synthesis carry each worker claim? (2) what did the synthesis compress, and where can a reader go deeper?

**D-specific divergence — MCP tool grant:** the on-disk `{letter}-claims.json` files are a lossy extraction of the actual NotebookLM notebook content. The D auditor is additionally granted the `notebook_query` and `cross_notebook_query` MCP tools to verify claims against the actual notebooks — `cross_notebook_query` verifies a cross-notebook claim against all spanned notebooks in one aggregated call. The EM grants these at dispatch time. Notebook IDs/names are sourced from each `{letter}-summary.md` YAML frontmatter (`notebook_id` / `notebook_name` fields) — do not parse them from markdown prose.

**Graduated bootstrap for MCP tools (required):**

1. Try exact names: `ToolSearch("select:mcp__notebooklm-mcp__notebook_query,mcp__notebooklm-mcp__cross_notebook_query")`
2. If Step 1 returns nothing, keyword fallback: `ToolSearch("+notebooklm notebook_query", max_results=5)`
3. If both return nothing — **graceful degrade:** proceed on `{letter}-claims.json` only and include this note in the sidecar header:

   > `DEGRADED: notebooklm MCP tools unavailable. Coverage audit based on on-disk claims.json only.`
   > `Notebook queries were not run. A re-audit with MCP tools available may surface additional gaps.`

**Cleanup-deferred ordering (hard constraint):** notebook deletion (`--cleanup`) MUST be deferred until **after** the auditor sidecar is written. The EM's Step 6 completion sequence is: run auditor → confirm sidecar exists → THEN delete notebooks. This ordering is enforced in `coordinator/commands/notebooklm-research.md` Step 6. The sweep agent does not delete notebooks directly; deletion is an EM-step that runs post-audit.

## Fidelity Relay: OUT OF SCOPE

The fidelity relay is **not applicable to Pipeline D.** The relay's gating condition is a depth tier (`--deeper` / `--deepest` for repo, gap-report deepening threshold for web). Pipeline D has no depth concept — only `--cleanup`. No deepening gate exists; no depth flags are defined. The gating condition structurally cannot fire.

This is an architectural boundary, not an appetite call. The relay is revisited only if Pipeline D adds depth flags or a deepening gate. Until then, it is absent by construction — not deferred.

## Scratch Directory

`docs/research/{run-id}-workdir/` (no trailing `-{topic-slug}` — Pipeline D's run-id, `{topic-slug}-{YYYYMMDD}` per `commands/notebooklm-research.md` Step 1, already carries the slug; unlike the repo/web/structured drivers' timestamp-only run-id).

- Strategy: `{scratch-dir}/strategy.md`
- Scout output: `{scratch-dir}/sources.md`
- Worker outputs: `{scratch-dir}/{letter}-claims.json` + `{scratch-dir}/{letter}-summary.md` (A, B, C as applicable)
- Final output: `docs/research/YYYY-MM-DD-{topic-slug}-nlm.md`
- Sweep advisory: `{output-path}-advisory.md` (+ backup at `{scratch-dir}/advisory.md`); omitted if nothing beyond scope
