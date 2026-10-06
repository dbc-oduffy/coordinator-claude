---
description: "PM-GATED — only invoke when the PM explicitly asks; EM must ask first if it thinks it's warranted; NEVER invoke from a subagent. Pipeline A v3.0 (Internet Research) as a chatty background Workflow — a Haiku scout, Sonnet specialists (adversarial peers exchanging challenges through mailbox files, with structured output), and an Opus sweep, run in stage order by one script. EM scopes research, fires the Workflow, and is freed. Optional iterative deepening: after pass 1 completes, the EM evaluates the gap report and may fire a smaller second Workflow for targeted follow-up."
allowed-tools: ["Agent", "Workflow", "Read", "Write", "Bash", "Glob", "Grep"]
argument-hint: "<topic>"
---

# Deep Research — Pipeline A v3.0 (Internet Research) Chatty-Workflow Driver

The EM scopes the research, writes `{workdir}/scope.md`, fires ONE background `Workflow`, and is **freed**. The script runs the stages in order:
- **Haiku scout** (1) — executes EM-crafted search queries, builds a shared source corpus
- **Sonnet specialists** (up to 5) — start after the scout returns, then deep-read from the corpus, verify, challenge peers through mailbox files, output structured claims JSON + markdown summary; a rebuttal round answers the challenges
- **Opus sweep** (1, the overseer) — starts after the specialists return, reads their outputs directly, performs adversarial coverage check, fills gaps with targeted research, writes executive summary and conclusion

The scout handles mechanical source discovery. Specialists self-govern their timing and challenge each other's claims. The Opus sweep reads specialist outputs directly (no consolidator intermediate), checks coverage adversarially, fills gaps, and frames the final document; its return value is the only one that reaches the EM. The EM does not monitor the run. Protocol, mailbox format, and the engine-emitted fire: `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/team-protocol.md`.

## Arguments

`$ARGUMENTS`:
- `<topic>` — the research topic (required)
- Additional context may follow the topic as free text
- `--shallow` — skip the deepening decision gate (force single-pass, v2.1 behavior)

## Step 1 — Setup

1. Parse arguments: extract research topic
2. Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp)
3. Decide the timing numbers (floor/ceiling) for the script's briefs after asking the PM in Step 2
4. Generate topic slug (e.g., `novel-claude-code-implementations`)
5. Create work directory — **accept-if-passed:** if `{scratch-dir}` is already bound (supplied by `research.md` Step 0), skip creating it and set `{workdir}` = `{scratch-dir}`; otherwise `mkdir -p docs/research/{run-id}-{topic-slug}-workdir` and set `{workdir}` to that path for use in subsequent steps.
6. Set output path: `docs/research/YYYY-MM-DD-{topic-slug}-web.md`
7. Set advisory path: `docs/research/YYYY-MM-DD-{topic-slug}-web-advisory.md` (replace `.md` with `-advisory.md`)
8. Parse `--shallow` flag from arguments (default: false)

Announce: "Running deep research (chatty Workflow) on '{topic}'."

## Step 2 — Scope Research (EM Direct)

This is judgment work — the EM does it directly. Use the scoping checklist below to ensure quality.

1. Define 3-5 topic areas to investigate
2. Write focus questions for each topic
3. List any known sources
4. Note cross-cutting themes between topics
5. **Craft search queries for the scout** — for each topic area, write 3-5 suggested search queries:
   - Varied phrasings targeting different source types (docs, blogs, repos, forums)
   - Include 1-2 adversarial queries per topic ("X problems", "X limitations", "why not X")
   - Cross-cutting queries that span multiple topics
   - These are starting suggestions, not exhaustive instructions — the scout runs them mechanically
6. **Ask the PM for timing preferences:**
   > "Research timing: default is 5-15 min with 5-source minimum. For a trivial topic, I'd suggest 3-8 min / 3 sources. For a complex topic, 5-20 min / 5 sources. What ceiling works for you?"

Default 4 topics; topic count is bounded only by the Workflow tool's own agent cap. Write scope AND search queries to `{workdir}/scope.md`; that file is the brief. Beside the scope it carries the fields the prompts read: a topic table (letter, description, focus questions, known sources, effort), `min_sources`, `min_minutes`, `max_minutes` (Step 2's timing answer), `corpus_path`, `output_path`, `advisory_path`, and `run_stem`.

### EM Scoping Checklist (review before dispatching)

Quality gates derived from published guidance (OpenAI, Perplexity, Google, STORM, Anthropic):

- [ ] **Sub-questions are explicit and falsifiable.** Each topic's focus questions have concrete answers that evidence can confirm or deny — not "what is the best X?" without criteria.
- [ ] **Effort budgets are set per topic.** Mark each topic as surface / moderate / deep. This calibrates how many sources specialists pursue before converging.
- [ ] **Source-type constraints are specified.** Default: "Prioritize primary sources (official docs, peer-reviewed, original reporting). Flag secondary sources. Note confidence for claims with <3 corroborating sources."
- [ ] **Adversarial queries are included.** At least 1 query per topic targeting criticism, limitations, or failure modes. Absence of criticism in sources ≠ absence of real limitations.
- [ ] **Search queries use varied phrasings.** Different wordings surface different source ecosystems. Include at least one query targeting each of: official docs, practitioner blogs, community forums.
- [ ] **Cross-cutting themes are named.** Connections between topics are where individual specialists have blind spots — name them so the sweep knows to look.
- [ ] **Each specialist assignment has: (a) specific objective, (b) output format reference,
      (c) tool/source guidance, (d) clear task boundaries vs. peers.** Vague assignments
      ("research X") lead to duplication — be specific about what each specialist SHOULD
      and SHOULD NOT cover.

## Step 3 — Prepare the Brief and Inputs

The brief file (`scope.md`) carries everything the prompts read; the engine op renders the Workflow from `web.manifest.yaml`, so no script is hand-filled. Inputs: the brief path, the topic letters (one per topic), and the scratch dir. Ordering is the manifest's stage order — there is no task graph and no `blockedBy`. Create `{workdir}/mail/` (`mkdir -p`) before firing.

## Step 4 — Stage Prompts and the Fire

### Scout (Haiku)

Read the scout prompt template from:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/scout-prompt-template.md`

The template carries no fill-tokens: the scout reads the research topic, project context, and search queries from the brief (`scope.md`). It is the `scout` stage of `web.manifest.yaml`.

### Specialists (Sonnet)

The specialist prompt template is `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/specialist-prompt-template.md`; the rebuttal, sweep, and relay prompts are `web-rebuttal-prompt-template.md`, `web-sweep-prompt-template.md`, and `web-relay-prompt-template.md` beside it. None carries fill-tokens. The only per-run values are the `topics` list (one lowercase letter per topic; the letter names the role `specialist-<letter>`, its mailbox, and its files; a gap-specialist's letter likewise names `gap-<letter>`) and the brief file. Everything else the specialists read from the brief: the topic table (a row per letter: description, focus questions, known sources; the other rows are the peers), `min_sources`, `min_minutes`, `max_minutes`, `output_path`, `advisory_path`, and `run_stem`. Specialists address peers by mailbox file, never by `SendMessage`. A rebuttal continuation runs for each specialist whose letter appears in a peer's returned `challenged` list.

### Opus Sweep

The script dispatches the sweep after the rebuttal stage returns, as `agent(prompt, { model: 'opus', agentType: 'coordinator:research-synthesizer', label: 'sweep', phase: 'Sweep', schema })`.

**Sweep prompt fields and verbatim instruction:** see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/web-research-internals.md` § Sweep Prompt Contents.

### Fire

Run `emit-dispatch-workflow --pipeline web --brief <brief path> --list topics=<a,b,...> --scratch-dir <scratch dir> --out <scratch dir>/web.workflow.mjs` (resolve the CLI per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`), then fire the emitted script as one background `Workflow` call. The pass-2 fire is `--pipeline web-deepening` (see `team-protocol.md` § Deepening Protocol).

## Step 5 — EM Is Freed

After firing the Workflow, announce:

> "Research workflow is running autonomously on '{topic}' with 1 scout + {N} specialists + 1 Opus sweep. The scout builds the shared corpus (~2-3 min), then specialists deep-read, verify, and challenge each other through mailboxes ({MIN_MINUTES}-{MAX_MINUTES} min, {MIN_SOURCES}-source minimum), and a rebuttal round answers the challenges. After that, the Opus sweep reads their outputs directly, checks coverage, fills gaps, and frames the final document. I'm available for other work — I'll be notified when the Workflow completes."

**You are now free to continue the conversation with the PM.** Do not poll and do not monitor. The Workflow handles everything.

## Step 6 — Pass 1 Completion

When the Workflow's task notification arrives (its result is the sweep's return value):

1. Read the synthesis document at `{output-path}`
2. Verify it has substantive content (not just headers)
3. Check for advisory: `test -f {advisory-path}` — if the file exists, read it
4. Read the gap report at `{workdir}/gap-report.md`
5. **Emit the durable claims pair** — you do this, not the synthesizer; the pair has exactly one writer. Never derive the pipeline token from `{run-stem}`.

   **`--ran-at` is measured off disk, never quoted from the agent.** The synthesizer has no shell and no clock; the merge moment is the mtime of `merged-claims.json`. Read it:
   
      ```bash
      python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/pipelines/deep-research/merged-claims-ran-at.py" {workdir}/merged-claims.json
      ```
      ```powershell
      python "$env:CLAUDE_PLUGIN_ROOT\pipelines\deep-research\merged-claims-ran-at.py" {workdir}\merged-claims.json
      ```
      It prints one RFC3339 stamp; pass that verbatim as `--ran-at`. It exits 1 rather
      than inventing a stamp for a path it cannot stat.
      A timestamp offered in a completion message is an estimate — `claims-emit` validates RFC3339 *shape*, so a confident guess lands in the durable sidecar indistinguishable from a measured value. Take the pipeline token from the completion message; take the clock from the file.
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/claims-emit" \
     --producer web-research \
     --out docs/research/{run-stem} \
     --ran-at "$RAN_AT" \
     --pipeline web \
     < {workdir}/merged-claims.json
   ```
   `--out` takes the stem; the CLI writes `{run-stem}.claims.json` and `{run-stem}.claims.meta.json` together. `--ran-at` must be RFC3339 and timezone-aware (naive, date-only, or empty is rejected — day precision recovered from the run-stem does not satisfy it); `--pipeline` must be non-blank and is never derived from `--producer`. Exit 0 = both written, 1 = producer-side failure, 2 = invalid invocation. A failed emission is a no-op on disk — an occupied stem is restored byte-for-byte, so re-running over an existing run-stem is safe.

6. Commit:
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" "deep-research: pass 1 complete — {topic-slug}"
   ```
7. **Dispatch the coverage auditor** (always-on for web — see § Coverage Auditor Dispatch below).
8. Scratch that persists across runs lives in `{workdir}/`.

**Proceed to Step 6.5** (do NOT archive yet — deepening may add to the work directory).

### Coverage Auditor Dispatch

The coverage auditor is **always-on for web**. Dispatch it after reading the synthesis (steps 1–4 above) and **before the run concludes** — this is the resolved-decision contract (RD-1). Do not defer it.

**The auditor is a plain `Agent(...)` — dispatched by the EM after the Workflow has completed, not as a stage of the research script.** Precedent: `repo-driver.md` survey (`:65`) and atlas-sketch (`:265`) as plain Agent dispatches.

Fill the dispatch prompt from the Pipeline A block of `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/coverage-auditor-prompt-template.md`. Required fields:

- `[SYNTHESIS_PATH]` → `{output-path}`
- `[RUN_STEM]` → strip `docs/research/` prefix and `.md` suffix from `{output-path}` (e.g. `docs/research/2026-06-30-topic-web.md` → `2026-06-30-topic-web`)
- `[SCRATCH_DIR]` → `{workdir}`
- Pipeline input block: **Pipeline A — Web Research**

```
Agent(
  subagent_type: "coordinator:coverage-auditor",
  prompt: <filled coverage-auditor-prompt-template.md — Pipeline A block>
)
```

Await the auditor's return (`{sidecar-path}`) before proceeding to Step 6.5. The sidecar is written to `{output-path minus .md}-coverage-audit.md`.

**Present the coverage-audit sidecar to the PM in Step 7** alongside the synthesis (see § Step 7 update below).

### Fidelity Relay — Locus and Gating (web)

The fidelity relay (deep tier only) is a **pass-1 script stage that runs after the sweep's draft and before the sweep's final return**. Its mechanics live in `team-protocol.md` § Fidelity Relay Protocol and `agents/research-synthesizer.md`. This driver states the gating contract so executors cannot mis-wire it:

- **Locus is always pass 1.** The original specialists (the authors whose content the relay protects) are re-dispatched as fidelity-check continuations; pass 2 is fresh gap-specialists, not original authors.
- **The relay is decoupled from the Step 6.5 deepening gate.** It fires when the sweep's return reports `deepeningRecommended: true`, in the same Workflow, whether or not the EM then deepens.
- **Do NOT wire the relay into pass 2 (Step 6.6).** The Step 6.5 / 6.6 blocks are deepening-only; the relay completes inside the pass-1 Workflow before the EM reaches them.

## Step 6.5 — Deepening Decision Gate

**Skip this step entirely if `--shallow` was passed.** Proceed directly to Step 7.

Parse the gap report's YAML front-matter and apply the DEEPEN / DO NOT DEEPEN rules in `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/web-research-internals.md` § Step 6.5. The decision turns on `high_severity_gaps`, `contested_unresolved`, `coverage_score`, plus the PM's timing budget.

- **If NO DEEPEN:** announce per the template in the internals doc, then proceed to Step 7.
- **If DEEPEN:** announce per the template, then proceed to Step 6.6.

## Step 6.6 — Fire Pass 2 (Deepening Pass)

1. **Cluster gap targets** (HIGH/MEDIUM only) into 1-3 specialist assignments. Two absent claims in the same domain → one gap-specialist. Record the clusters in the pass-2 brief (a copy of `scope.md` with `pass: 2` and `merge_mode: true` added): a gap table (letter, gap id, description, type, severity, suggested queries, relevant pass 1 topic letter), with gap letters continuing after pass 1's last topic letter, and `needs_scout` decided in item 2.
2. **Decide scout inclusion:** include a Haiku scout if gaps require new topic areas; skip if gaps are refinements within existing topics (gap-specialists do their own targeted searches).
3. **Fire one background Workflow** — scout (if any) → gap-specialists in parallel → rebuttal continuations → merge-mode sweep, in `await` order. Then announce per the template and free the EM.

**Gap-specialist template field list, script differences from pass 1, merge-mode sweep prompt fields, announce template:** see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/web-research-internals.md` § Step 6.6.

**EM is freed again.** Do not poll.

## Step 6.7 — Pass 2 Completion + Merge

When the pass-2 Workflow's task notification arrives:

1. Read `{workdir}/deepening-delta.md`; verify substantive content; read pass-2 advisory if present.
2. **Merge delta into `{output-path}`** per the rules in `pipelines/web-research-internals.md` § Step 6.7 (Resolved Contradictions, Filled Gaps, Updated Claims, Open Questions, strip provenance markers).
3. Write merged doc back to `{output-path}` and `{workdir}/synthesis-merged.md`.
4. Commit via the settings-home forwarder: `coordinator-safe-commit "deep-research: pass 2 deepening merged — {topic-slug}"` (resolve as `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit"`, per Step 6's fenced form).
5. Proceed to Step 7.

## Step 7 — Finalize

1. Archive work directory:
   ```bash
   mv docs/research/{run-id}-{topic-slug}-workdir docs/research/archive/YYYY-MM-DD-{topic-slug}
   ```

   **Precondition: `docs/research/` and `docs/research/archive/` resolve to the same filesystem.** If `archive/` is ever moved to a different mount, this archive step must be revisited — POSIX `mv` across filesystems degrades to copy-then-unlink, reopening the race window the change is meant to eliminate. Executor-time guard: `stat -c '%d' docs/research 2>/dev/null || stat -f '%d' docs/research` on both paths before mv; fail-loud if device IDs differ.
2. Commit via the settings-home forwarder: `coordinator-safe-commit "deep-research: archive + cleanup — {topic-slug}"` (resolve as `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit"`, per Step 6's fenced form).
3. Present executive summary to PM for discussion:
   - If deepening occurred: "Research complete (2 passes). Pass 1 identified {gap_count} gaps ({high_severity_gaps} high-severity); pass 2 filled {N}. See synthesis at `{output-path}`."
   - If no deepening: "Research complete (single pass). Coverage score: {coverage_score}/5. See synthesis at `{output-path}`."
   - If advisory exists: "The sweep agent flagged observations beyond scope — see the advisory at `{advisory-path}`."
   - Always include: "Coverage audit: `{output-path minus .md}-coverage-audit.md` — {present_count} specialist claims present, {absent_count} absent. {If absent_count > 0: 'See the Completeness Map in the sidecar for gaps and deeper-reading pointers.'}"

## Error Handling

See `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/web-research-internals.md` § Error Handling Matrix for the full failure-mode → action table (scout/specialist/sweep/pass-2 failures).
