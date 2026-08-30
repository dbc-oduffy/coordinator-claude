---
description: "PM-GATED, never from a subagent. NotebookLM research for video/audio sources."
allowed-tools: ["Agent", "Read", "Write", "Bash", "Glob", "Grep", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "SendMessage"]
argument-hint: "<topic> [--context file1 file2] [--sources url1 url2] [--cleanup]"
---

# NotebookLM Research — Pipeline D (Agent Teams)

Research via Google NotebookLM for sources Claude cannot fetch directly: YouTube videos,
podcasts, audio, JS-heavy pages, Google Drive documents. **PM-gated — never invoked from a
subagent.**

**Use for:** PM-supplied video/podcast/audio links; finding the best talks/videos/podcasts on a
topic; source material needing transcription or NotebookLM's cross-source citation synthesis.
**Don't use for:** codebase research (`/coordinator:research --mode=repo`), text/web research
(`--mode=web`), structured batch research (`--mode=structured`), quick API docs (Context7).

Team roles, timing ceilings, data contracts (`strategy.md`, `sources.md`,
`{letter}-claims.json`, `{letter}-summary.md`), failure handling, the coverage-auditor
lifecycle, and why the fidelity relay doesn't apply here all live in
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/notebooklm/team-protocol.md` — read there, don't re-derive.

**Precondition — raise the teams flag first.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` defaults to
`"0"`. Set it to `"1"` in `~/.claude/settings.json` before Step 3, and back to `"0"` when the run
ends, badly or well. No restart is needed; the value is re-read on each spawn.

**This one fails quietly if you skip it.** Step 3 spawns the first teammate *before* any task is
created, so at `"0"` that spawn degrades into an ordinary blocking subagent that runs a full
notebook ingest, and only the later `TaskCreate` errors — leaving a live NotebookLM notebook, a
half-finished run, and no team. Check the flag; do not discover this from the wreckage.

**Announce at start:** "I'm running `/coordinator:notebooklm-research` to research {topic} using
NotebookLM."

---

## Arguments

`$ARGUMENTS`: `<topic> [--context file...] [--sources url...] [--cleanup]`

- **topic** (required)
- `--context` — background files to inform scoping
- `--sources` — PM-provided URLs (YouTube, podcasts, articles)
- `--cleanup` — delete notebooks once research completes. Default: keep them (worth preserving
  for follow-up queries). Deletion is deferred past the coverage auditor — see Step 6.

---

## Execution Flow

### Step 0 — MCP advisory

Probe `mcp__notebooklm-mcp__*` resolution (`ToolSearch("select:mcp__notebooklm-mcp__notebook_query")`).
If it resolves, continue silently. If not, surface once and continue anyway — advisory only,
never a gate:

```
NotebookLM MCP not detected — install: uv tool install notebooklm-mcp-cli && nlm login && nlm setup add claude-code (see wiki)
```

### Step 1 — Setup

Parse `$ARGUMENTS`. Run ID: `{topic-slug}-{YYYYMMDD}`. Workdir:
`docs/research/{run-id}-workdir/` (no trailing `-{topic-slug}` — the run-id already carries the
slug). Output: `docs/research/YYYY-MM-DD-{topic-slug}-nlm.md`. Advisory: same path with
`.md` replaced by `-advisory.md`.

### Step 2 — EM scopes research

Read `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/notebooklm/notebooklm-best-practices.md`
first. Ask the PM for NLM tier (free/plus/ultra — sets worker count per team-protocol.md § Rate
Limit Budgeting) and a timing ceiling if neither is given. Read any `--context` files. Design
notebook topology, questions, source strategy, and worker count directly, then write
`strategy.md` to `{scratch-dir}/strategy.md` per team-protocol.md § Data Contract. Time-box
scoping to 2-3 minutes — pick the simpler topology if still deliberating.

### Step 3 — Create team + tasks

Spawn the first teammate via `Agent` — the team auto-forms. Create a `sweep` task, a `scout`
task, and one `worker-{letter}` task per notebook. Block each worker on `scout`; block `sweep`
on every worker task.

### Step 4 — Spawn teammates

Fill and spawn the scout/worker(s)/sweep prompt templates from
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/notebooklm/{scout,worker,sweep}-prompt-template.md`
— each template's placeholders are self-documenting. Agent types: scout =
`notebooklm:notebooklm-research-scout`, workers = `notebooklm:research-worker`, sweep =
`notebooklm:research-sweep`. Assign task owners at spawn.

### Step 5 — EM freed

Report team composition (1 scout + N workers + 1 sweep) and expected timing to the PM, note the
output path, then stop tracking — the team runs autonomously.

### Step 6 — On completion

The sweep does **not** delete notebooks even with `--cleanup` — deletion is deferred until after
the coverage auditor's sidecar exists (team-protocol.md § Coverage-Auditor Lifecycle).

**6a — Read + emit claims.** Read `{output-path}`, verify it's substantive. Check for and read
an advisory file if present. Emit the durable claims pair (you write it, not the sweep — take
`--ran-at` and the pipeline token from the sweep's completion message, never derive them):

Shape W (`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`). PowerShell has no native stdin
redirect operator, so the `.exe` launcher is invoked through `cmd /c` for the `<` redirect only —
the launcher still runs directly by absolute path, no bareword resolution involved:

```powershell
cmd /c "\"$env:COORDINATOR_SETTINGS_HOME\bin\claims-emit.exe\" --producer notebooklm-research --out {output-path-base} --ran-at {ran_at from sweep's completion message} --pipeline notebooklm < \"{scratch-dir}/merged-claims.json\""
```

**6b — Coverage auditor.** Dispatch it as a plain (non-teammate) `Agent(...)` — never a named
team member, to preserve the 7-teammate ceiling. Build the prompt from
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/coverage-auditor-prompt-template.md`'s Pipeline D input
block (`[SYNTHESIS_PATH]`, `[RUN_STEM]`, `[SCRATCH_DIR]`). Wait for `DONE: {sidecar-path}`.

**6c — Notebook cleanup.** If `--cleanup`: read each `{letter}-summary.md`'s `notebook_id`
frontmatter and call `notebook_delete` for each; log deletions and any failures. Otherwise,
mention preserved notebook names/IDs to the PM for future reference.

**6d — Archive, commit.** Same op and contract as `coordinator/skills/staff-session/SKILL.md`
Step 8: commit the workdir first (`git add -- docs/research/{run-id}-workdir` then
`git commit -- docs/research/{run-id}-workdir`), then invoke `fleet.archive_paper_trail` with
`run_id={run-id}`, `topic_slug={topic-slug}`, `dry_run=false`. Commit the output file and
coverage-audit sidecar.

**6e — Present to PM:** topic + notebooks used, 2-3 key findings, output path, coverage-audit
sidecar path (note absent-claim count if nonzero), any flagged gaps, and the advisory path if one
was written.

---

Failure handling for scout/worker/sweep degrade paths: team-protocol.md § Failure Handling.
