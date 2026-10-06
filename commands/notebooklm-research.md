---
name: notebooklm-research
description: "PM-GATED, never from a subagent. NotebookLM research for video/audio sources."
allowed-tools: ["Workflow", "Agent", "Read", "Write", "Bash", "Glob", "Grep"]
argument-hint: "<topic> [--context file1 file2] [--sources url1 url2] [--cleanup]"
disable-model-invocation: true
---

# NotebookLM Research — Pipeline D (chatty Workflow)

Research via Google NotebookLM for sources Claude cannot fetch directly: YouTube videos,
podcasts, audio, JS-heavy pages, Google Drive documents. **PM-gated — never invoked from a
subagent.**

**Use for:** PM-supplied video/podcast/audio links; finding the best talks/videos/podcasts on a
topic; source material needing transcription or NotebookLM's cross-source citation synthesis.
**Don't use for:** codebase research (`/coordinator:research --mode=repo`), text/web research
(`--mode=web`), structured batch research (`--mode=structured`), quick API docs (Context7).

Roles, stage ordering (the stage graph is `notebooklm.manifest.yaml`, fired by Step 4), timing ceilings, data contracts (`strategy.md`, `sources.md`,
`{letter}-claims.json`, `{letter}-summary.md`), failure handling, the coverage-auditor
lifecycle, and why the fidelity relay doesn't apply here all live in
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/notebooklm/team-protocol.md` — read there, don't re-derive.

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
never a gate. `notebooklm-mcp` is registered **per project**, so it is absent from a session
whose repo has not registered it even when the CLI is installed and authenticated — the probe
reports this session's surface, never whether the capability exists on the machine:

```
NotebookLM MCP not registered for this project — install: uv tool install notebooklm-mcp-cli && nlm login && nlm setup add claude-code (see wiki)
```

`mcp__notebooklm-mcp__*` is the only prefix this pipeline uses. The CLI's source directory is
named `gemini-notebook-mcp-cli` after its upstream; the registered server key is not, and a probe
against a prefix derived from the directory name resolves nothing.

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

### Step 3 — Complete the brief

There are no prompts to fill. The templates
(`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/notebooklm/{scout,worker,sweep}-prompt-template.md`)
read every per-run parameter from `strategy.md`, which is the brief
(`notebooklm.manifest.yaml` in the same directory is the stage graph). Add these fields to
`strategy.md`'s frontmatter, beside those in team-protocol.md § Data Contract:

- `research_topic`, `topic_slug`
- `output_path` (Step 1's output), `output_path_base` (it without `.md`), `advisory_path`
- `cleanup_notebooks` (`true` or `false`, from `--cleanup`)
- `scout_ceiling_minutes` (default 5)

Notebook letters are the manifest's `notebooks` list: A, B, C as many as `worker_count`.
Each notebook's `## Notebook {letter}` section carries its `estimated_ceiling`.

### Step 4 — Fire the Workflow

Run the engine op `emit-dispatch-workflow --pipeline notebooklm --brief {scratch-dir}/strategy.md
--list notebooks=A,B,C --out {scratch-dir}/workflow.mjs` (CLI resolved per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; `--brief` is a path and a missing
file is refused; `--list notebooks` is the notebook letters, one per worker). Fire the printed
`Workflow` line as ONE background `Workflow` (`run_in_background: true`). The emitted script runs
scout, then the workers in parallel, then the sweep, per `notebooklm.manifest.yaml`; stage
ordering gates each stage on the previous one returning. Never hand-fill a script.

### Step 5 — EM freed

Report the stage plan (1 scout + N workers + 1 sweep) and expected timing to the PM, note the
output path, then stop tracking — the Workflow runs autonomously and its completion notification
carries the sweep's return value.

### Step 6 — On completion

The sweep does **not** delete notebooks even with `--cleanup` — deletion is deferred until after
the coverage auditor's sidecar exists (team-protocol.md § Coverage-Auditor Lifecycle).

**6a — Read + emit claims.** Read `{output-path}`, verify it's substantive. Check for and read
an advisory file if present. Emit the durable claims pair (you write it, not the sweep). Take the pipeline
token from the sweep's completion message; **take `--ran-at` from the mtime of
`{scratch-dir}/merged-claims.json`, never from the message** — the sweep has no shell and no
clock, so a timestamp it states is an estimate that `claims-emit`'s RFC3339 shape check cannot
distinguish from a measured value:

```powershell
$RanAt = (Get-Item "{scratch-dir}/merged-claims.json").LastWriteTimeUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
```

Shape W (`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`). PowerShell has no native stdin
redirect operator, so the `.exe` launcher is invoked through `cmd /c` for the `<` redirect only —
the launcher still runs directly by absolute path, no bareword resolution involved:

```powershell
cmd /c "\"$env:COORDINATOR_SETTINGS_HOME\bin\claims-emit.exe\" --producer notebooklm-research --out {output-path-base} --ran-at $RanAt --pipeline notebooklm < \"{scratch-dir}/merged-claims.json\""
```

**6b — Coverage auditor.** Dispatch it as a plain `Agent(...)`. Build the prompt from
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/coverage-auditor-prompt-template.md`'s Pipeline D input
block (`[SYNTHESIS_PATH]`, `[RUN_STEM]`, `[SCRATCH_DIR]`). Wait for `DONE: {sidecar-path}`.

**6c — Notebook cleanup.** If `--cleanup`: read each `{letter}-summary.md`'s `notebook_id`
frontmatter and call `notebook_delete` for each; log deletions and any failures. Otherwise,
mention preserved notebook names/IDs to the PM for future reference.

**6d — Archive, commit.** Same op and contract as `coordinator/skills/staff-session/SKILL.md`
Step 8. First commit the workdir's Data Contract files (team-protocol.md § Data Contract) as one
scoped unit, never the whole workdir — under `docs/research/{run-id}-workdir/`: `strategy.md`,
`sources.md`, `*-claims.json`, `*-summary.md`, `merged-claims.json`, and `advisory.md` if the
sweep wrote one. Then invoke `fleet.archive_paper_trail` with `run_id={run-id}`,
`topic_slug={topic-slug}`, `dry_run=false`. Commit the output file and coverage-audit sidecar
yourself — the op commits only what it authored.

**6e — Present to PM:** topic + notebooks used, 2-3 key findings, output path, coverage-audit
sidecar path (note absent-claim count if nonzero), any flagged gaps, and the advisory path if one
was written.

---

Failure handling for scout/worker/sweep degrade paths: team-protocol.md § Failure Handling.
