---
description: "EM-fired on a sizing; never fired from a subagent. Pipeline B (Repo Research) as a chatty Workflow — optional Opus survey for holistic orientation, scouts (Haiku for small repos, Sonnet for large) build file inventories, 4 Sonnet specialists analyze and optionally compare, 1 Opus synthesizer produces the final document. In --deepest mode: three-phase pipeline with atlas sketch and refinement."
allowed-tools: ["Agent", "Workflow", "Read", "Write", "Bash", "Glob", "Grep"]
argument-hint: "<repo-path> [--compare <project-path>] [--code-compare <peer-target> --axes <axis-list>] [--survey] [--deeper] [--deepest] [--scout-model {haiku|sonnet}]"
---

# Deep Research — Pipeline B (Repo Research) Chatty-Workflow Driver

The EM scopes the repository, writes `{scratch-dir}/scope.md`, fires ONE background `Workflow` whose script runs the stages in order, and is **freed**. The workflow runs autonomously:
- **Haiku scouts** (2) — inventory all files in their assigned chunks, build structured file maps
- **Sonnet specialists** (4) — start after the scout stage and its disk gate return (2 scouts on the Haiku tier, 4 on the Sonnet tier), then deep-read files, analyze, optionally compare, and exchange challenges through mailbox files
- **Opus synthesizer** (1, the overseer) — starts after the specialists' stage returns, then reads findings and writes final document(s)

Scouts produce the shared thoroughness artifact that Sonnets would naturally skim past. Specialists self-govern their timing (floor, diminishing returns, ceiling). The EM does not monitor. When the Workflow completes, the EM receives its task notification, carrying the synthesizer's return value, and does quick cleanup.

## Arguments

`$ARGUMENTS`:
- `<repo-path>` — path to the repository to research (required)
- `--compare <project-path>` — optional path to a project to compare against
- `--code-compare <peer-target> --axes <axis-list>` — routes to the single-agent Code-Comparison mode (see `## Mode Dispatch — --code-compare` below) instead of the Pipeline B scout→specialist→synthesizer workflow. Distinct from `--compare`: `--compare` runs the Pipeline B prose gap-analysis workflow; `--code-compare` dispatches one self-contained agent per (subject, peer) pair via fan-out and does NOT invoke the workflow at all — no scouts, no specialists, no synthesizer.
- `--survey` — dispatch a solo Opus agent to produce a holistic 20-30KB narrative overview before the workflow runs. Useful when the EM is cold on the repo. The survey becomes both a standalone deliverable and a specialist input artifact. Implied by `--deepest` unless the EM already has context.
- `--deeper` — generate a dependency-weighted repomap during scoping, giving specialists structural centrality rankings to prioritize deep-reads
- `--deepest` — all of `--deeper` and `--survey`, plus generate architecture atlas artifacts in two passes: a preliminary sketch from scout data (pre-specialist) and a refined atlas from the full research (post-synthesis). Three-phase pipeline.
- `--scout-model {haiku|sonnet}` — override the size-derived scout tier (Step 5 Phase A). Default is size-derived (Sonnet for large or high-volume repos, Haiku for small). The tier selects the dispatch vehicle, not a `model:` parameter — see Step 5 Phase A's tier table.

## Mode Dispatch — `--code-compare`

If `--code-compare <peer-target> --axes <axis-list>` is supplied, this run does NOT follow the
Workflow flow below (Steps 1-7.5) — skip straight to a single-agent dispatch:

1. Read the single-agent prompt template from
   `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/code-comparison-agent-prompt-template.md`.
2. Fill in the bracketed fields (subject repo, peer target, axis list). **`[OUTPUT_PATH]` is
   bound, not an EM fill-in:** `<repo-root>/state/emissions/code-comparison/{run-id}.yaml`, where
   `<repo-root>` resolves via the running repo's own tree-root pointer (this repo's is `.content-root`;
   never `${CLAUDE_PLUGIN_ROOT}`, which names the plugin source tree, not `state/`'s parent) and
   `{run-id}` is generated fresh (`YYYY-MM-DD-HHhMM`, current timestamp) — Mode Dispatch skips
   Step 1, so this mode generates its own run-id rather than reusing one. Each repo writes its
   own records into its own tree — this is not a central directory shared across repos.
3. Dispatch one `Agent(...)` call per `(subject, peer)` pair (fan-out shape, NOT the Workflow) — no scouts, no specialists, no synthesizer.
4. Each agent emits structured comparison records per the schema at
   `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/code-comparison-record-schema.md`, writing the
   output file itself.

Full mode description, architecture rationale, and record-schema detail:
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/PIPELINE.md` § Code-Comparison Mode.

## Step 1 — Setup

1. Parse arguments: extract repo path, optional comparison path, `--survey` flag, `--deeper` flag, and `--deepest` flag. **Note:** `--deepest` implies both `--deeper` and `--survey` — if `--deepest` is set, treat both as also set. However, the EM MAY skip the survey step if they already have sufficient context on the repo (e.g., it's the project's own repo, or a prior survey exists). State this judgment explicitly: "Skipping survey — I already have context on this repo from [reason]." **Survey caching:** If a prior survey exists at the output path and is less than 7 days old, the EM MAY reuse it instead of regenerating. State: "Reusing prior survey from [date] — [reason still valid]." **Also parse `--scout-model {haiku|sonnet}` if present** — it overrides the Step 5 Phase A size-derived scout-model default.
2. Verify the repo path exists and contains files. **Note:** the path may have been resolved from a repo-target name by the entry point (via `machine-local get repos.<name>`, `~/Documents/Code_Reference/<name>`, or an opt-in shallow clone); if a shallow clone was created by the entry point, record its path in `scope.md` under `## Clone Disposition` for explicit cleanup consideration — do NOT auto-delete; only a pipeline-created shallow clone is cleanup-eligible, and even then surface-don't-auto-rm.
3. Generate run ID: `YYYY-MM-DD-HHhMM` (current timestamp)
4. Generate topic slug from repo name (e.g., `onnxruntime`, `langchain`)
5. Record spawn timestamp: `date +%s` (Unix epoch seconds — the survey's `[SPAWN_TIMESTAMP]`; scouts, specialists, and later stages start their own clock)
6. Create working directory — **accept-if-passed:** if `{scratch-dir}` is already bound (supplied by `research.md` Step 0), skip the `mkdir` and use the supplied value; otherwise create it (`mkdir -p docs/research/{run-id}-{topic-slug}-workdir`).
   Set `{scratch-dir}` = `docs/research/{run-id}-{topic-slug}-workdir`
7. Set output path: `docs/research/YYYY-MM-DD-repo-{topic-slug}.md` — the `repo-` infix distinguishes this pipeline's artifacts from web/structured pipeline outputs on the same date.
8. Set advisory path: `docs/research/YYYY-MM-DD-repo-{topic-slug}-advisory.md`
9. If `--compare`: set gap analysis path: `docs/research/YYYY-MM-DD-repo-{topic-slug}-gap-analysis.md`
10. If `--deeper`: set repomap path: `{scratch-dir}/repomap.md`
11. If `--survey` or `--deepest`: set survey path: `{scratch-dir}/survey.md`; set survey output path: `docs/research/YYYY-MM-DD-repo-{topic-slug}-survey.md`
12. If `--deepest`: set atlas sketch (scratch) and refined-output (docs/research/) paths — see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Atlas Path Conventions for the 3 sketch + 4 final artifact paths.
13. Set claims path: `docs/research/YYYY-MM-DD-repo-{topic-slug}.claims.json` — durable queryable index of per-specialist claim records merged by the synthesizer. A requested output path overrides steps 7-13: every durable path derives from it, never from `docs/research/`.

Announce: "Running Pipeline B (repo research, chatty Workflow{', deepest mode' if --deepest}{', deeper mode' if --deeper and not --deepest}{', survey mode' if --survey and not --deepest}{', comparison mode' if --compare}) on {repo-path}."

## Step 2 — Holistic Survey (only if `--survey`)

If `--survey` is set and the EM judges a holistic overview is warranted:

1. **Read the survey prompt template** from:
   `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-survey-prompt-template.md`

2. **Fill in template fields:**
   - `[REPO_NAME]`, `[REPO_PATH]`, `[DATE]`
   - `[SCRATCH_DIR]` → scratch directory path
   - `[SPAWN_TIMESTAMP]` → current `date +%s`
   - If `--compare`: `[COMPARE_PROJECT_NAME]`, `[COMPARE_PROJECT_PATH]`

3. **Dispatch the survey agent:**
   ```
   Agent(
     model: "opus",
     prompt: <filled survey prompt>
   )
   ```
   This is a regular subagent, dispatched before the Workflow. 30-minute ceiling.

4. **Read the survey** at `{scratch-dir}/survey.md`

5. **Decision gate — present to PM:**
   > "Survey complete — [brief 2-3 sentence summary of key findings]. Two options:
   > 1. **Survey is sufficient** — we have the overview we need. I'll save this as the deliverable.
   > 2. **Proceed with the research workflow** — use this survey as specialist context and go deep.
   > Which approach?"

6. **If PM chooses option 1:**
   - Copy survey to output path: `cp {scratch-dir}/survey.md {survey-output-path}`
   - Commit and present to PM. Pipeline ends here.

7. **If PM chooses option 2:** Proceed to Step 3 (Orient and Scope). The survey is saved
   and will be passed to specialists as context.

## Step 3 — Orient and Scope Repository (EM Direct)

Orientation and scoping are the manifest's `scope` stage: `repo-scope-prompt-template.md` writes `{scratch-dir}/scope.md`, the brief every later stage reads (repomap generation: `repo-research-internals.md` § Phase 1.5).

## Step 4 — Stage Order and Mailboxes

The run is ONE background `Workflow` the engine emits from `repo.manifest.yaml` (Step 5); the EM never writes the script. Doctrine: `coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md`.

- **Ordering replaces `blockedBy`.** Stage N+1 starts when stage N's `agent()` calls return (`await`, or `parallel()` for a fan-out). Nothing else gates a stage.
- **No `SendMessage`** — between agents or to the EM. Peers exchange findings through mailbox files, `{scratch-dir}/mail/<role>.jsonl`. A line is `{"from": "<role>", "text": "..."}`; to message peer X, append to X's file. A reader appends `{"read": true}` after reading its file; it has unread mail when lines follow its last read marker. Roles: `scout-1`/`scout-2` (Haiku tier) or `scout-a`…`scout-d` (Sonnet tier), `specialist-a`…`specialist-d`, `sweep`, `synthesizer`.
- **Challenge and relay rounds are continuation rounds.** Round 1: specialists write their outputs, append challenges to peers' mailboxes, and return. Round 2, after all of round 1 returns: the script probes the mailboxes and dispatches a fresh continuation agent for each specialist with unread mail. A wake is a dispatch, never a resume (`SendMessage` cannot resume a returned workflow agent). One rebuttal round by default.
- **The synthesizer is the overseer** — the only agent whose return value reaches the EM. Workers return a one-line pointer to the script and never address the EM.
- Model tiers are set per stage in `repo.manifest.yaml`; every disk check is an `agent()` call, because the script has no filesystem access.

## Step 5 — Fire the Workflow

Set the brief parameters (Phases A–D below), then emit and fire. Stage order is fixed by the manifest: scouts → gate → [atlas sketch] → specialists → rebuttal → [sweep] → synthesizer (→ relay → pass 2).

Resolve `emit-dispatch-workflow` per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` and run:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/emit-dispatch-workflow" --pipeline repo --brief {scratch-dir}/scope.md --subjects {repo-name} --list chunks=A,B,C,D --list haiku_scouts=1,2 --flag deepest=BOOL --flag compare=BOOL --flag sonnet_scouts=BOOL --scratch-dir {scratch-dir} --out {scratch-dir}/workflow.mjs
```

Each `BOOL` is `true` or `false`.

`--brief` is the path of `scope.md` (a missing file is refused). `--list chunks` and the three `--flag`s come from Step 3 and Phase A; the Sonnet tier still takes `--list chunks=A,B,C,D` and `sonnet_scouts=true`. Fire the printed `Workflow({ scriptPath: ... })` line as a background `Workflow` (`run_in_background: true`). Never hand-write the script: the engine writes the receipt the Workflow hook checks, and re-running emit rewrites both.

The stage templates are filled by the engine from `repo.manifest.yaml`, not by the EM: the EM's whole contribution is `scope.md` (Step 3). A specialist's role is `specialist-{letter, lowercase}`, its peers are the other rows of the Chunks table, and the synthesizer's mailbox is `synthesizer`. The mailbox protocol text lives in each template that uses it.

### Phase A: Scouts

#### Scouts (model scales with repo size)

**Scout model selection — the tier picks the VEHICLE, not a `model:` parameter.** `coordinator:repo-scout` pins `model: haiku` and the engine-plane guard `enforce_agent_model_pin` hard-rejects any dispatch that passes `model:` alongside it. **Never pass `model:` to `coordinator:repo-scout`** — the dispatch is refused outright, and it is refused identically on the Step 5.5 recovery path, when a failed run can least afford it. Scaling up means dispatching a *different agent* carrying the same scout template — the manifest's `scout-haiku` and `scout-sonnet` stages, selected by the `sonnet_scouts` flag:

| Tier | Manifest stage | Ceiling |
|------|----------------|---------|
| Haiku (default) | `scout-haiku`: `coordinator:repo-scout`, **no `model`**; scout keys `1` and `2` | 5 min |
| Sonnet (escalated) | `scout-sonnet`: `general-purpose`, `model: sonnet`; scout keys `A`…`D` | 8–12 min |

Haiku scouts reliably inventory small chunks but fail at large scope — silently, and with confabulated DONE messages (empirically 2/2 Haiku scouts failed on a ~2500-file repo at ~250 files/chunk, 2026-06-27; see Step 5.5). Derive the tier from the Step 3 estimates:

- **`--scout-model {haiku|sonnet}` override (parsed in Step 1) wins if present.** State it: "Scout tier forced to {tier} via --scout-model." If `--scout-model sonnet` forces the Sonnet tier on a small repo, use the Haiku-tier ceiling (5 min) and set `Large-chunk breadth: false` in the brief — the tier is the override, not the chunk size.
- **Else default by size:** **Sonnet tier** if the repo exceeds **~1000 files total**, OR any single scout's combined chunk load exceeds **~150 files**, OR any single scout's combined chunk load exceeds **~1.5MB of source**; **Haiku tier** otherwise.
- **File count is a weak proxy for scout load — check volume too.** A 216-file repo whose single largest file is 6,000+ lines and holds a third of its source loads a scout harder than a 900-file repo of small modules. Get both numbers during Step 3 orientation (`find {repo-path} -type f -name '*.{ext}' | wc -l` and `du -sh` over the chunk's directories) and escalate on whichever crosses first.
- State the derivation: "Repo ~{N} files / ~{S}MB, max scout load ~{M} files (~{V}MB) → scouts run on the {tier} tier."

**Ceiling scales too.** The 5-minute scout ceiling is unachievable at ~250 files/chunk even for a non-hallucinating scout. Set the brief's `Scout ceiling (minutes)` to **5** for Haiku-tier small chunks, **8–12** for Sonnet-tier large chunks (within 8–12: ~8 min for ~100–150 files/chunk, ~10 for ~150–200, ~12 for 200+). AND for large (Sonnet-tier) chunks set `Large-chunk breadth: true` so the scout prioritizes record/contract-bearing files (schemas, public APIs, entry points) with full entries and inventories the rest by signature — breadth over exhaustive deep-read.

The scout template is `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-scout-prompt-template.md`. Its chunk assignment follows the tier (Step 3 item 7) and comes from the brief's Chunks table: on the Haiku tier set the Scout column to `1` (chunks A+B) and `2` (chunks C+D), and the scouts take Variant A; on the Sonnet tier the Scout column is the chunk letter, one chunk each, the scouts take Variant B, and the `sonnet_scouts` flag is true. The template picks its variant from the scout key (number: A, letter: B). A Sonnet-tier scout carrying Variant A is the documented refusal case. The Step 5.5 recovery re-runs failed chunks through the same template with a chunk-letter key, so it takes Variant B.

#### Synthesizer (Opus) — the overseer

The synthesizer template is `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-synthesizer-prompt-template.md`. It reads the brief's `Repository`, `Output path`, `Advisory path`, `Claims path`, `Gap analysis path` and `Comparison` fields, so those must be set in Step 3. Its fidelity-relay passes are selected by the brief's `Deepest mode` field and by whether the specialists' relay lines are in the synthesizer mailbox; nothing is dropped by hand.

The synthesizer runs as `{ agentType: 'coordinator:research-synthesizer', model: 'opus' }`. Its return value is the run's completion message to the EM.

### Phase B: Atlas Sketch (only if `--deepest`)

**If NOT `--deepest`:** Skip this phase.

**If `--deepest`:** The stage starts after the Step 5.5 gate (and any recovery) returns — the script's ordering is the wait. It dispatches a Haiku atlas-sketch agent (`general-purpose`, `model: 'haiku'`) using `pipelines/repo-atlas-sketch-prompt-template.md`; the prompt requires it to verify the 3 sketch artifacts exist in `{scratch-dir}/` before returning. On failure the script logs and the specialists fall back to `--deeper` mode (repomap only).

The sketch reads the brief's Chunks table (the System and Description columns) and `Repomap` field. **Verification details:** see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Phase B.

### Phase C: Spawn Specialists

The specialist template is `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-specialist-prompt-template.md`, one specialist per chunk. Every parameter it needs is a brief field, set in Step 3:
- The chunk's description, directories and `Est. Files` (from the scoping survey) in the Chunks table; peers are the other rows
- `Min minutes`, `Max minutes`, `Min deep-read files` — from PM timing preferences (or defaults: 5 min, 15 min, 3 files)
- `Comparison` — the project name and path when `--compare`, else "none"
- `Repomap` — a path only when `--deeper` generated one (not skipped)
- `Deepest mode` — true only on `--deepest`; the specialist reads the atlas sketch files if they exist
- `Survey` — true only when a survey was produced, and `{scratch-dir}/survey.md` exists

All four run in one fan-out as `{ agentType: 'coordinator:repo-specialist', model: 'sonnet' }`. Specialists start their own clock, so the EM's Step 1 timestamp does not apply to them.

## Step 5.5 — Scout Completion Gate (hard, disk-first)

Scouts can hit the documented "TEXT-ONLY" hallucination (see `coordinator/snippets/em-operating-doctrine.md` § Extensions to coordinator defaults ▸ Fan-out dispatch extras ¶ "Scouts: disk-first"): they return without ever calling Write, leaving specialists with inventories that don't exist. **Worse — a scout can return a confabulated DONE with fabricated line counts and a detailed fake findings summary for files it never wrote** (observed 2026-06-27: scout-2 reported *"both inventories written and verified on disk (8.9K/149 lines, 11K/227 lines)"* with a detailed findings summary, while `find` confirmed zero files on disk). **A return value and a plausible DONE message are NOT evidence of work — only disk is.** The gate is structural: it is a stage of the script, runs on every repo run, and the specialist stage cannot start until it returns.

**When this gate runs:** after every scout `agent()` call returns, in every mode — before the atlas sketch under `--deepest`, before the specialists otherwise. The script's `gate()` dispatches a Sonnet agent that runs:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/stub-file-gate" --min-lines 30 {scratch-dir}/A-inventory.md {scratch-dir}/B-inventory.md {scratch-dir}/C-inventory.md {scratch-dir}/D-inventory.md
```

and returns the chunk letters whose inventories the CLI reports missing or short (`repo-gate-prompt-template.md`).

**GATE PASS (all 4 files exist, ≥30 lines each):** Scouts succeeded; the script proceeds.

**GATE FAIL (any file missing or <30 lines):** a returned scout with no/stub disk output is a **false completion**. The script recovers in this preference order, with no EM involvement:

**Preferred recovery — Sonnet escalation (per coordinator "never re-Haiku" doctrine).** Coordinator CLAUDE.md § "Scouts and Disk-First Verification": *"Haiku TEXT-ONLY on a write-capable worker: escalate or self-execute, never re-Haiku (~30% recurrence)."* The manifest's `rescout` stage redispatches each missing chunk: `agentType: 'general-purpose'`, `model: 'sonnet'`, the filled scout prompt with the Variant B preamble. **Never pass `model: 'sonnet'` to `coordinator:repo-scout`** — that agent pins Haiku and the engine-plane pin guard refuses the call, which would strand this recovery at exactly the moment it is needed (see Phase A's tier table). Apply the same breadth-scoping (record/contract-bearing files first) and a size-derived ceiling (8–12 min). When the Sonnet scouts return, the script re-runs the gate on the failed paths.

**Fallback — stub (only when the Sonnet redispatch also fails, or the scouts already ran on Sonnet).** The manifest's `stub` stage writes a stub inventory for each still-missing chunk at the expected path. A stub is a structured file list pulled from `scope.md`'s chunk definitions, prefixed with:
   ```markdown
   > **Stub inventory** — written after scout failure (TEXT-ONLY hallucination + failed/exhausted Sonnet redispatch).
   > Treat as a file list. Self-discover via Glob/Read; do not assume coverage is exhaustive.
   ```
The stub lists the chunk's directories/files from `scope.md`; if `--compare`, it includes the chunk's domain keywords as comparison hints. The recovery scout (`repo-scout-prompt-template.md`) and the stub agent (`repo-stub-prompt-template.md`) also append a `## Recovery Notes` section to `scope.md` listing which inventories were Sonnet-re-run vs stubbed, so the synthesizer's advisory captures the degraded/recovered run.

No wake step exists: the specialist stage starts after the gate stage returns.

> **The specialists' seam is guarded by the synthesizer.** It treats a missing or under-30-line `{letter}-assessment.md` as a `[COVERAGE GAP]` (`repo-synthesizer-prompt-template.md`).

## Step 5.7 — Comparison-Target Sweep (only if `--compare`)

**The gap this closes.** Chunks are drawn over the **studied** repo. Nobody owns "what does the
*comparison target* do here" — yet in a comparison run that is the entire point. Each specialist
compares within its own lane, so every cross-lane question about the target falls between
chunk boundaries and is answered by whoever happens to think of it. Observed twice on 2026-08-30,
in two repos independently: a peer's run closed four such questions only after specialists
finished and **three of the four flipped direction on closing** — two withdrew a spurious `ADOPT`
once the target turned out to already have the mechanism, and stronger; this repo's own run had
the sharpest Tier 1 finding surfaced by the synthesizer noticing an unowned two-halves transition
in the comparison target's own code, and its scope document had omitted two of the target's
surfaces outright.

**The expensive failure is a wrong-direction recommendation, not a missing one.** An unwithdrawn
spurious `ADOPT` becomes someone's sprint building what they already have.

After all four specialists have returned (rebuttal round included) and cleared the disk
gate, and **before** the synthesizer runs, the script dispatches a single **sweep agent** — the
stage after the specialist stage in the script's order:

The sweep agent gets:

- The four `{letter}-comparison.md` files and every open question, `[CONTESTED]`, and
  `[UNVERIFIED]` marker in them — **its worklist is the union of the four chunks' loose ends**
- **Plus any EM-supplied worklist items.** A fact can enter a run from outside it — a peer session
  messaging a specific claim mid-run, a PM steer, a cross-repo memo — and no marker anywhere in the
  chunk outputs will carry it, because it was never a specialist's open question. Pass such items
  in explicitly (the brief's `## Sweep Worklist` section) so they land in the same verification machinery instead of depending
  on the EM remembering to chase them. One optional input, not a mechanism
- The four `{letter}-assessment.md` files as context for what the studied repo does
- `scope.md`, including § Comparison Targets
- Read access to the **comparison project**, and a standing instruction that the comparison
  project — not the studied repo — is its subject

Its job, stated as three questions:

1. **Verify every absence claim with a targeted grep.** "The target does not have X" is the weakest
   claim class in a comparison run and carries most of its adoption recommendations — a specialist
   who did not find X and one who did not look for X write the same sentence. Grep the target for
   each asserted absence; an absence that survives is worth acting on, and one that does not is
   rewritten as `ALREADY-HAVE` with the file:line disproving it. Frame the arm on the claim, not on
   the verdict: this catches absence claims that never became an `ADOPT`, and it is what withdraws
   spurious steals. Verification is cheap and bounded — one command per claim — which is precisely
   what makes it a sweep job rather than a specialist's.
2. **What did chunking make unaskable?** Name the questions that span two or more chunks of the
   target, which no specialist could have owned, and answer the ones the target's own tree
   settles.
3. **What in the target is dead, disabled, or parameterised into being available?** A flag already
   shipped behind a default, a branch preserved for comparison, a test still asserting a retired
   path — these turn a proposed build into a parameter flip, and they are systematically invisible
   to a specialist reading the *other* repo.

It writes `{scratch-dir}/comparison-target-sweep.md` and returns `DONE: <path>`. The sweep agent gates its own file on disk
(`stub-file-gate --min-lines 20`, `repo-comparison-sweep-prompt-template.md`) before it returns; a false completion here silently
returns the pipeline to the pre-sweep behaviour.

The synthesizer's input list includes the sweep file, and the synthesizer is instructed that **where the
sweep contradicts a specialist verdict, the sweep wins on questions of fact about the comparison
target** — it read the target directly and with the whole worklist in view, which no specialist
did. The synthesizer still presents genuine judgment disagreements as trade-offs.

## Step 6 — EM Is Freed

After firing the Workflow, announce:

**If `--deepest`:**
> "Research workflow running in the background on '{repo-name}': scouts → atlas sketch → 4 specialists (rebuttal round) → synthesizer with fidelity relay. Specialists analyze {MIN_MINUTES}-{MAX_MINUTES} min ({MIN_SOURCES}-file minimum). I'm available for other work — I'll be notified when the workflow completes."

**Otherwise:**
> "Research workflow running in the background on '{repo-name}': {2 or 4} scouts → 4 specialists (rebuttal round) → synthesizer. Scouts inventory files (~5 min), then specialists analyze {MIN_MINUTES}-{MAX_MINUTES} min ({MIN_SOURCES}-file minimum). I'm available for other work — I'll be notified when the workflow completes."

**You are now free to continue the conversation with the PM.** Do not poll, do not monitor, do not message workflow agents. The script handles everything; completion is the Workflow's task notification.

## Step 6.5 — Before Treating the Synthesizer as Stalled

If a check-in (PM question, unrelated notification) finds the Workflow still running long in its synthesis stage, a long silent run is not evidence of a stall — Phase 1's adversarial coverage
read (`agents/research-synthesizer.md` § Phase 1) can run long over large specialist
outputs before anything is written to disk.

**Before writing any EM self-synth fallback** (assembling the document yourself from raw
specialist outputs), disk-check the canonical output path first: Read `{output-path}` and
`{scratch-dir}/synthesis.md`, and note whether each exists and how long it is.

**A Workflow that ended without a synthesis, or a synthesis stage with zero output past a generous read window, is the redispatch
signal.** A self-synth on a slow stage alone overwrites an in-progress synthesis.

## Step 7 — On Completion Notification

When you receive the Workflow's completion notification (its result is the synthesizer's return value):

1. Read the synthesis document at `{output-path}`
2. Verify it has substantive content (not just headers)
3. If comparison mode: read the gap analysis at `{gap-analysis-path}` and verify
4. Check for advisory: `test -f {advisory-path}` — if the file exists, read it
4.2. **Verify the fleet-readable competitor row landed** — third-party runs only (skip for this
   repo or a fleet sibling; the row is deliberately absent there). The synthesizer appends it by
   default, so this confirms the default fired rather than deciding whether to ask for it:

   ```bash
   grep -n '^## Fleet-Readable Competitor Row' {output-path}
   ```

   It prints the heading's line number, or nothing at all — nothing is the missing case.

   If it is missing, append it yourself from § Fleet-Readable Competitor Row of
   `repo-synthesizer-prompt-template.md` — do not re-dispatch the synthesizer for one table.
   **Check the `GitHub` cell is a bare `owner/repo` slug**, not a URL, a markdown link, or a
   directory name: it is the only load-bearing cell, and the downstream fleet reader skips a row
   whose locator is not slug-shaped. A wrong spelling there costs the whole row, silently from
   this side — the run looks complete and the reader renders nothing.
4.5. **Emit the durable claims pair** — you do this, not the synthesizer; the pair has exactly one writer. Never derive the pipeline token from the run-stem.

   **`--ran-at` is measured off disk, never quoted from the agent.** The synthesizer has no shell and no clock; the merge moment is the mtime of `merged-claims.json`. Read it:
   
      ```bash
      python3 "${CLAUDE_PLUGIN_ROOT:?coordinator plugin root unset — run this from a plugin command/skill, or substitute an absolute path}/pipelines/deep-research/merged-claims-ran-at.py" {scratch-dir}/merged-claims.json
      ```
      ```powershell
      python "$env:CLAUDE_PLUGIN_ROOT\pipelines\deep-research\merged-claims-ran-at.py" {scratch-dir}\merged-claims.json
      ```
      It prints one RFC3339 stamp; pass that verbatim as `--ran-at`. It exits 1 rather
      than inventing a stamp for a path it cannot stat.
      A timestamp offered in a completion message is an estimate — `claims-emit` validates RFC3339 *shape*, so a confident guess lands in the durable sidecar indistinguishable from a measured value. Take the pipeline token from the completion message; take the clock from the file.
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/claims-emit" \
     --producer repo-research \
     --out docs/research/{run-stem} \
     --ran-at "$RAN_AT" \
     --pipeline repo \
     < {scratch-dir}/merged-claims.json
   ```
   `--out` takes the stem (`{claims-path}` minus `.claims.json`); the CLI writes `{run-stem}.claims.json` and `{run-stem}.claims.meta.json` together. `--ran-at` must be RFC3339 and timezone-aware (naive, date-only, or empty is rejected — day precision recovered from the run-stem does not satisfy it); `--pipeline` must be non-blank and is never derived from `--producer`. Exit 0 = both written, 1 = producer-side failure, 2 = invalid invocation. A failed emission is a no-op on disk — an occupied stem is restored byte-for-byte, so re-running over an existing run-stem is safe.

5. **Read the coverage audit** — always-on for repo. It runs as the manifest's `coverage` stage (`repo-coverage-prompt-template.md`) before the Workflow returns and writes `{output-path minus .md}-coverage-audit.md`.

6. **Fidelity relay — `--deepest` only.** If `--deepest` was set, the Workflow ran the relay before it returned: the synthesizer's pass 1 drafted the document and returned, the script dispatched a continuation agent for each specialist carrying the `FIDELITY_RELAY` request, each answered `FIDELITY_OK` or `FIDELITY_CORRECTION` in `mail/synthesizer.jsonl`, and the synthesizer's pass 2 integrated corrections scoped strictly to misrepresentation of existing synthesis prose. The relay mechanics live in `agents/research-synthesizer.md` (C5). repo-driver's role is only to state the gate: **the relay runs if and only if `--deepest`**. For `--deeper`-only or default runs, the relay does not fire.

7. Workflow agents end when they return — no teardown step. The scratch directory persists.
8. If `--deepest`: proceed to **Step 7.5** before archiving. Otherwise, skip to step 9.
9. Commit:
   ```bash
   "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-safe-commit" "deep-research: complete — {topic-slug}"
   ```
10. Archive paper trail (atomic rename — no copy-then-delete race window):
    ```bash
    mv docs/research/{run-id}-{topic-slug}-workdir docs/research/archive/YYYY-MM-DD-repo-{topic-slug}
    ```
    **Precondition: `docs/research/` and `docs/research/archive/` resolve to the same filesystem.** If `archive/` is ever moved to a different mount, this archive step must be revisited — POSIX `mv` across filesystems degrades to copy-then-unlink, reopening the race window the change is meant to eliminate. Executor-time guard: `stat -c '%d' docs/research 2>/dev/null || stat -f '%d' docs/research` on both paths before mv; fail-loud if device IDs differ.
11. Commit: `coordinator-safe-commit "deep-research: archive + cleanup"`
12. Present executive summary to PM for discussion. If advisory exists, mention it: "The synthesizer flagged observations beyond scope — see the advisory at `{advisory-path}`." If `--deepest`: mention the atlas artifacts and their locations. Mention the coverage-audit sidecar: "Coverage audit written to `{output-path minus .md}-coverage-audit.md` — {present_count} claims present, {absent_count} absent." Mention the durable index artifacts: "Research-synthesis frontmatter prepended to `{output-path}`. Queryable claims index written to `{claims-path}` ({N} claims across {K} chunks)."

## Step 7.5 — Atlas Refinement (only if `--deepest`)

**Phase 3:** After the Workflow completes and the assessment is verified, dispatch a Sonnet subagent to refine the preliminary atlas using specialist analysis and synthesis findings, producing the 4th artifact (architecture summary) which requires specialist data. Use `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-atlas-prompt-template.md`. Verify all 4 artifacts (`atlas-file-index.md`, `atlas-system-map.md`, `atlas-connectivity-matrix.md`, `atlas-architecture-summary.md`) exist and have substantive content; on success, copy from scratch to the docs/research/ paths set in Step 1; on failure, note to PM and proceed (atlas is additive). Return to Step 7 item 9 (Commit).

**Note on the copy step:** The atlas-refinement step copies artifacts from the workdir into `docs/research/` (using `cp` since both paths are sibling directories); the workdir's atomic `mv` to `archive/` happens at Step 7 item 10 and carries the cross-FS precondition guard there. No separate guard is needed at Step 7.5 because both src and dst are under `docs/research/` by construction.

**Template fields, dispatch syntax, copy commands:** see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Step 7.5.

## Error Handling

See `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/repo-research-internals.md` § Error Handling Matrix for the full failure-mode → action table (survey/scout/atlas-sketch/specialist/synthesizer/atlas-refinement failures).
