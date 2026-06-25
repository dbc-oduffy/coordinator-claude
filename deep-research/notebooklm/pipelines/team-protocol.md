# NotebookLM Research Team Protocol

> Referenced by agent definitions and `research.md` command.

## Overview

Agent Teams-based NotebookLM research: the EM scopes research directly — designing notebook topology, questions, source strategy, and worker count — then creates a right-sized team (scout + N workers + sweep) and is **freed**. The team handles everything autonomously — source discovery, notebook creation, ingestion, querying, coverage assessment, and gap-filling. Notebook cleanup is optional (`--cleanup` flag; default: keep).

## Architecture

```
EM: Scope research → Write strategy.md → Create team → Spawn (scout + workers + sweep) → FREED
         │
         ├── Haiku scout (no blockers)
         │   Reads strategy.md, finds best YouTube / podcast / article sources
         │   Writes: {scratch-dir}/sources.md
         │
         ├── Sonnet worker(s) (blockedBy: scout) — 1 to 3, per strategy.md
         │   Each creates own notebook, ingests assigned sources, queries
         │   Writes: {scratch-dir}/{letter}-claims.json + {letter}-summary.md
         │   Sends DONE → sweep
         │
         └── Opus sweep (blockedBy: all workers)
             Reads all claims (JSON), assesses coverage, fills gaps
             Writes: {output-path}
             Writes: {output-path}-advisory.md (if anything beyond scope)
             Cleans up notebooks (if --cleanup)
```

## Team Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** | Haiku | 1 | Reads strategy.md, finds best YouTube / podcast / article sources via WebSearch, writes sources.md |
| **Worker** | Sonnet | 1-3 | Creates own notebook, tags it with the run slug, ingests assigned sources, runs queries, extracts structured claims, writes `{letter}-claims.json` + `{letter}-summary.md`, sends DONE to sweep |
| **Sweep** | Opus | 1 | Reads all worker claims (JSON), assesses coverage, fills gaps via follow-up queries and WebSearch, writes final polished document, optionally writes advisory, lists preserved notebook IDs for the EM to delete post-audit (sweep does NOT delete) |

## Team Lifecycle

```
EM: Scope research → Write strategy.md → Create team → Spawn (scout + workers + sweep) → FREED

Scout: Read strategy.md → WebSearch / WebFetch → Write sources.md → Mark complete → [idle]
Workers: [blocked by scout] → Read strategy.md (own ## Notebook letter) + sources.md → Bootstrap MCP → Create notebook → Tag with run slug → Ingest → Query → Extract claims → Write {letter}-claims.json + {letter}-summary.md → Mark complete → DONE to sweep
Sweep: [blocked by all workers, waiting for DONE msgs] → Verify all complete → Read claims (JSON) → Assess coverage → Fill gaps → Write advisory (if anything beyond scope) → List preserved notebook IDs for EM (EM deletes post-audit if --cleanup) → Mark complete
```

## Blocking Chain

```
Scout (no blockers) ──────→ task completion unblocks workers
Workers (blockedBy: scout) ──→ DONE messages wake sweep
Sweep (blockedBy: all workers) ──→ mark complete notifies EM
```

- **Scout → Workers:** Task-gated via `blockedBy`. Workers unblock when scout marks its task complete. No messaging needed — workers haven't started yet (auto-wake confirmed empirically 2026-03-21).
- **Workers → Sweep:** Task-gated via `blockedBy` + DONE messages as wake-up signals. The sweep is already running but idle — it needs explicit DONE messages to trigger its next poll cycle (confirmed empirically 2026-03-21).

### How Agent Teams Blocking Actually Works (empirical + sourced)

Agent Teams uses **file-based polling, not callbacks**. Task state lives in JSON files at `~/.claude/tasks/{team-name}/N.json`. Agents discover available work by calling `TaskList()`, which re-evaluates `blockedBy` arrays fresh on each call. There is no active push/callback when a blocker completes.

**Two distinct scenarios with different wake-up behavior:**

| Scenario | Agent State | Wake-Up Mechanism | Message Needed? |
|----------|-------------|-------------------|-----------------|
| **Task-blocked (pending)** | Not yet started — `pending` status, waiting for blockers | `TaskList()` re-evaluates `blockedBy` on next poll; agent auto-starts when unblocked | No — auto-wake works |
| **Message-blocked (idle)** | Started, checked status, went idle waiting | Needs an inbox message to trigger the next poll cycle | Yes — explicit DONE message required |

The scout→worker transition is scenario 1 (auto-wake). The worker→sweep transition is scenario 2 (DONE messages needed). Both confirmed empirically 2026-03-21.

**Shutdown behavior:** Teammates prioritize completing their current work loop over acknowledging shutdown requests. Expect the convergence protocol (write → mark complete → DONE) to run before shutdown acknowledgment. This is good for data integrity but means team teardown takes 30-60 seconds after shutdown requests are sent.

**Sources:** [Claude Code official docs](https://code.claude.com/docs/en/agent-teams), [reverse-engineering analysis (nwyin.com)](https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered.html), [swarm orchestration guide (kieranklaassen gist)](https://gist.github.com/kieranklaassen/4f2aba89594a4aea4ad64d753984b2ea).

## Scout Protocol

The scout finds media sources — optimized for YouTube, podcasts, and audio content that NLM excels at.

- Reads `{scratch-dir}/strategy.md` for search guidance per notebook (see "Search guidance for scout" field)
- **For "scout-provided" notebooks:** WebSearch + WebFetch to find and verify YouTube videos, podcasts, articles
- **For "research_start" notebooks:** Note in sources.md that this notebook uses NLM built-in discovery — the worker will use `research_start` MCP tool
- Writes `{scratch-dir}/sources.md` using `## Sources for Notebook A/B/C` convention
- **No SendMessage** — task completion unblocks workers automatically
- **Timing:** 5 minute ceiling. This is mechanical discovery — go fast.

## Worker Protocol

**Critical: read-after-unblock sequencing.** Workers must follow this startup sequence:

1. **Check TaskList FIRST** — verify your task is unblocked before doing anything else
2. **Wait until unblocked** — if still blocked, wait for scout to complete
3. **THEN read shared artifacts** — strategy.md and sources.md (after confirmed unblocked)

This prevents a race condition where a worker reads sources.md before the scout has written it.

- Reads `## Notebook {letter}` section from strategy.md for its assignment
- Reads `## Sources for Notebook {letter}` from sources.md for its source list
- Bootstraps MCP tools via graduated ToolSearch (exact names → keyword fallback → fail gracefully)
- If source strategy is "scout-provided": ingest scout-provided URLs via `source_add`
- If source strategy is "research_start": use `research_start` MCP tool for NLM discovery
- Creates own notebook named `{topic-slug}-{letter}`
- Runs all assigned research questions, extracting structured claims per response
- **Records notebook ID in summary file** (for sweep cleanup)
- Writes `{scratch-dir}/{letter}-claims.json` (structured claim objects) and `{scratch-dir}/{letter}-summary.md` (human-readable overview with notebook metadata)
- Marks task `completed`, sends DONE message to sweep

**Timing:** 25 minute ceiling (configurable via `estimated_ceiling` in strategy.md). Note: source ingestion time depends on NLM processing speed for the content type.

## Message Protocol

### Worker → Sweep (Wake-Up Signal)

`blockedBy` is a status gate, not an event trigger — completing a blocker task does NOT automatically wake the blocked teammate. Workers must explicitly message the sweep after completing their task:

| Category | Format | When |
|---|---|---|
| **DONE** | `"DONE: Notebook {letter} claims written to {scratch-dir}/{letter}-claims.json and {scratch-dir}/{letter}-summary.md"` | After marking own task `completed` |

This is the sweep's wake-up mechanism. Each DONE message causes the sweep to re-check `TaskList`. When all worker tasks show `completed`, it proceeds with coverage assessment and gap-filling.

### Volume Governance

- **Worker → sweep: exactly 1 DONE message per worker**
- **Scout: no messages** (task completion handles unblocking)
- **No worker → worker messaging** — workers operate independent notebooks with no cross-pollination during execution

## Self-Governance Timing

| Agent | Ceiling | Notes |
|-------|---------|-------|
| Scout | 5 min | Mechanical discovery — go fast |
| Workers | 25 min (default) | Configurable via strategy.md `estimated_ceiling` field. NLM ingestion time varies. |
| Sweep | No strict ceiling | Runs after all workers complete; assesses coverage, fills gaps, writes final doc then cleans up notebooks |

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

## Failure Handling

- **Auth expiry (worker):** Call `refresh_auth`, retry once. If it fails again, write partial claims and send DONE with failure note.
- **Source ingestion failure (worker):** Log the failure in summary.md, continue with remaining sources. Do not abort.
- **research_start failure (worker):** Retry once. If persistent, note failure in summary.md and attempt alternative sources if scout provided any.
- **Rate limiting (worker):** Write partial claims immediately. Send DONE with rate limit note. Do not retry — the sweep will note the gap.
- **Query failure (worker):** Retry once. Log and continue with remaining questions.
- **Scout finds no sources for a notebook:** Worker falls back to self-directed discovery (targeted WebSearch for the notebook's topic area) or uses `research_start` if topic allows.
- **Scout times out (partial sources.md):** Workers use what's available + note which notebooks have incomplete source lists.
- **All workers fail:** Sweep marks itself failed, EM is notified (no completed worker tasks).

## Coverage-Auditor Lifecycle

> **Spec backlink:** `archive/specs/2026-05/2026-05-30-deep-research-synthesis-fidelity-coverage-audit.md` § Pipeline D RESOLVED, § C6, § AC12, § AC15, § AC16

Pipeline D uses the **always-on** coverage auditor — dispatched by the EM as a non-teammate Agent **after** the sweep completes and **before** notebook cleanup. The auditor answers the same two questions as the web/repo auditor: (1) did the synthesis carry each worker claim? (2) what did the synthesis compress, and where can a reader go deeper?

**D-specific divergence — MCP tool grant:** the on-disk `{letter}-claims.json` files are a lossy extraction of the actual NotebookLM notebook content. The D auditor is additionally granted the `notebook_query` and `cross_notebook_query` MCP tools to verify claims against the actual notebooks — `cross_notebook_query` verifies a cross-notebook claim against all spanned notebooks in one aggregated call. The EM grants these at dispatch time. Notebook IDs/names are sourced from each `{letter}-summary.md` YAML frontmatter (`notebook_id` / `notebook_name` fields) — do not parse them from markdown prose.

**Graduated bootstrap for MCP tools (required):**

1. Try exact names: `ToolSearch("select:mcp__plugin_notebooklm_notebooklm__notebook_query,mcp__plugin_notebooklm_notebooklm__cross_notebook_query")`
2. If Step 1 returns nothing, keyword fallback: `ToolSearch("+notebooklm notebook_query", max_results=5)`
3. If both return nothing — **graceful degrade:** proceed on `{letter}-claims.json` only and include this note in the sidecar header:

   > `DEGRADED: notebooklm MCP tools unavailable. Coverage audit based on on-disk claims.json only.`
   > `Notebook queries were not run. A re-audit with MCP tools available may surface additional gaps.`

**Cleanup-deferred ordering (hard constraint):** notebook deletion (`--cleanup`) MUST be deferred until **after** the auditor sidecar is written. The EM's Step 6 completion sequence is: run auditor → confirm sidecar exists → THEN delete notebooks. This ordering is enforced in `notebooklm/commands/notebooklm-research.md` Step 6. The sweep agent does not delete notebooks directly; deletion is an EM-step that runs post-audit.

## Fidelity Relay: OUT OF SCOPE

> **Spec backlink:** `archive/specs/2026-05/2026-05-30-deep-research-synthesis-fidelity-coverage-audit.md` § Pipeline D RESOLVED, § Per-pipeline applicability matrix (D row)

The fidelity relay is **not applicable to Pipeline D.** The relay's gating condition is a depth tier (`--deeper` / `--deepest` for repo, gap-report deepening threshold for web). Pipeline D has no depth concept — only `--cleanup`. No deepening gate exists; no depth flags are defined. The gating condition structurally cannot fire.

This is an architectural boundary, not an appetite call. The relay is revisited only if Pipeline D adds depth flags or a deepening gate. Until then, it is absent by construction — not deferred.

## Scratch Directory

`docs/research/{run-id}-{topic-slug}-workdir/`

- Strategy: `{scratch-dir}/strategy.md`
- Scout output: `{scratch-dir}/sources.md`
- Worker outputs: `{scratch-dir}/{letter}-claims.json` + `{scratch-dir}/{letter}-summary.md` (A, B, C as applicable)
- Final output: `~/docs/research/YYYY-MM-DD-{topic-slug}.md`
- Sweep advisory: `{output-path}-advisory.md` (+ backup at `{scratch-dir}/advisory.md`); omitted if nothing beyond scope
