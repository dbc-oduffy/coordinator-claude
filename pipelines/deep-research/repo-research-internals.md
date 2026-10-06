# Pipeline B (Repo Research) — Internals Reference

Detail companion to `pipelines/deep-research/repo-driver.md`. Step numbers refer to that command. Trimmed out of the command itself to keep the procedural skeleton readable; consult here when implementing or debugging a specific phase.

## Phase 1.5 — Repomap Generation (`--deeper`)

Used by Step 3 Phase 1.5 in `commands/repo.md`. Goal: dependency-weighted file ranking to inform chunk scoping and specialist deep-read prioritization.

**Steps A-C — Language census, import/dependency edges, cross-reference counts:** a single invocation of the `repo-census` CLI:

```text
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/repo-census" <repo-path>
```

`repo-census` walks the target repo (honoring `.gitignore` and a fixed vendor skip-list), ranks file extensions by frequency, extracts per-language import/dependency-statement targets ranked by occurrence count for the top 2 languages by census (Python, JS/TS, Go, Rust, C/C++, and Java are covered; polyglot repos get the top 2 by census unless overridden), and — for the most-imported modules — resolves a best-effort file path and counts *distinct referencing files*. Add `--json` for machine consumption. The pipeline consumes this as scoping signal, not a build-accurate dependency graph: it tells the EM which files are structurally central before specialists are dispatched, the same role Steps A-C's shell shapes served, minus the copy-paste-and-fill-in-placeholders step.

Note: `repo-census` is a distinct tool from the tree-sitter-based `repomap` (`coordinator/bin/repomap/generate-repomap.py`, the engine repo) that backs this project's own orientation hook — that one ranks a repo WE work in by PageRank centrality + git activity for a token-budgeted context map; `repo-census` has no git-activity signal and targets an arbitrary external repo we've never seen. Don't conflate the two.

**Step D — Extract key exports:** For each top-20 file, Read the first 50 lines for class names, function signatures, important constants.

**Step E — Write repomap or skip:** If fewer than 5 files have 2+ incoming references, the import graph is too thin — note in `scope.md` and proceed without a repomap (specialists operate in default mode). Otherwise write `{scratch-dir}/repomap.md`:

```markdown
# Repository Map — {repo-name}

Ranked by structural centrality (incoming cross-file references).
Generated during deeper-mode scoping — use to prioritize deep-reads.

## Tier 1 — Core (10+ incoming refs)
| File | Refs | Key Exports |
|------|------|-------------|
| {path} | {count} | {exports} |

## Tier 2 — Important (5-9 refs)
| File | Refs | Key Exports |
|------|------|-------------|
| {path} | {count} | {exports} |

## Tier 3 — Supporting (2-4 refs)
| File | Refs | Key Exports |
|------|------|-------------|
| {path} | {count} | {exports} |
```

## Atlas Path Conventions (`--deepest`)

Set during Step 1 when `--deepest` is active.

**Sketch (pre-specialist) — scratch dir:**
- `{scratch-dir}/atlas-sketch-file-index.md`
- `{scratch-dir}/atlas-sketch-system-map.md`
- `{scratch-dir}/atlas-sketch-connectivity-matrix.md`

**Refined (post-synthesis) — final outputs:**
- `docs/research/YYYY-MM-DD-repo-{topic-slug}-file-index.md`
- `docs/research/YYYY-MM-DD-repo-{topic-slug}-system-map.md`
- `docs/research/YYYY-MM-DD-repo-{topic-slug}-connectivity-matrix.md`
- `docs/research/YYYY-MM-DD-repo-{topic-slug}-architecture-summary.md` (4th artifact, requires specialist data)

## Step 7.5 — Atlas Refinement Details

After the Workflow completes and the assessment is verified, the EM dispatches a Sonnet subagent to refine the preliminary atlas using specialist analysis and synthesis findings.

1. **Read template:** `${CLAUDE_PLUGIN_ROOT}/pipelines/repo-atlas-prompt-template.md`
2. **Fill fields:** `[REPO_NAME]`, `[DATE]`, `[RUN_ID]`, `[VERSION]`; `[SYSTEM_A_NAME]`–`[SYSTEM_D_NAME]` and `[CHUNK_A_DESCRIPTION]`–`[CHUNK_D_DESCRIPTION]` from scope.md; `[SCRATCH_DIR]`, `[SYNTHESIS_PATH]` (= `{output-path}`), `[SPAWN_TIMESTAMP]` (= current `date +%s`); preliminary artifact paths `[PRELIMINARY_FILE_INDEX]`, `[PRELIMINARY_SYSTEM_MAP]`, `[PRELIMINARY_CONNECTIVITY_MATRIX]` from `{scratch-dir}/atlas-sketch-*.md`.
3. **Dispatch as a regular Sonnet subagent.**
4. **Verify** all 4 artifacts exist and have substantive content: `atlas-file-index.md`, `atlas-system-map.md`, `atlas-connectivity-matrix.md`, `atlas-architecture-summary.md`.
5. **If verification passes:** copy the 4 artifacts from scratch to the `docs/research/...` paths set in Step 1.
6. **If verification fails:** proceed without atlas. Note to PM: "Atlas generation failed or produced thin output — assessment is complete, atlas artifacts missing." Atlas is additive, not blocking.

## Phase B — Atlas Sketch Details (`--deepest`, in Step 5)

The script runs this stage after the scout gate returns, before the specialist stage:

1. **Read template:** `${CLAUDE_PLUGIN_ROOT}/pipelines/repo-atlas-sketch-prompt-template.md`
2. **Fill fields** using scope.md chunk descriptions: `[REPO_NAME]`, `[DATE]`, `[RUN_ID]`, `[SYSTEM_A_NAME]`–`[SYSTEM_D_NAME]`, `[CHUNK_A_DESCRIPTION]`–`[CHUNK_D_DESCRIPTION]`, `[SCRATCH_DIR]`, `[SPAWN_TIMESTAMP]`.
3. **Dispatch as a Haiku agent** — `agent(prompt, { agentType: 'general-purpose', model: 'haiku' })` in the script.
4. **Verify** all three sketch artifacts exist in `{scratch-dir}/atlas-sketch-*.md`.
5. **If verification fails:** proceed without atlas sketch. Specialists operate in `--deeper` mode (repomap only). Atlas refinement still runs post-synthesis. Note to PM.

## Fidelity Relay Protocol (`--deepest` runs only)

> Upstream doctrine: `coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md` (delivery and wake rules)

The fidelity relay runs inside the Workflow, between the synthesizer's two passes (see `agents/research-synthesizer.md § Fidelity Relay`) — it is NOT a post-run activity. This section documents the EM-side preconditions and the relay's placement in the stage order.

### Gating condition (repo-specific)

The relay fires on `--deepest` runs only. The `--deepest` flag (`repo-driver.md:22-23`) implies `--deeper` + `--survey` — the three-phase deep pipeline with atlas sketch, repomap, and full specialist context. `--deeper` alone does NOT trigger the relay. Plain `repo` and `--survey` mode skip the relay.

The relay runs **before** the synthesizer's final pass returns, so the Workflow's completion notification already carries its outcome.

### Relay locus — between the synthesizer's passes, pre-Step-7

**The relay executes as stages of the one Workflow, not as a separate post-synthesis dispatch.** The synthesizer's pass 1 returns its draft; the script dispatches a fresh continuation agent per specialist (the specialists have returned, and a wake is a dispatch, never a resume); then the script dispatches the synthesizer's pass 2. The authors whose content the relay protects are represented by their continuations, which name each specialist's own output files and predecessor return value. Atlas refinement (Step 7.5) runs after the Workflow completes and is unrelated to the relay.

### Relay sequence (script-driven; summarized for EM debuggability)

1. Synthesizer pass 1 writes the draft and returns without messaging anyone.
2. The script dispatches one continuation per specialist with a `FIDELITY_RELAY` request scoped to misrepresentation only — "did the synthesis flatten, distort, or misrepresent YOUR finding?" Each appends `FIDELITY_OK` or `FIDELITY_CORRECTION` to `{scratch-dir}/mail/synthesizer.jsonl`.
3. **Bounded:** one round. **Non-response fallback:** a specialist with no line in the mailbox is unconfirmed; the synthesizer's pass 2 proceeds without their confirmation and annotates the synthesis: `[RELAY: {TOPIC_LETTER} specialist did not respond — relay unconfirmed for this topic]`. The pipeline never hangs on a non-responding specialist.
4. **Bloat-guard (structural discriminator):** a valid fidelity correction must reference an existing synthesis sentence and assert it misrepresents the source. A correction that only asks to ADD a sentence is out of scope by construction — the relay is scoped to misrepresentation, not coverage inflation. The synthesizer rejects add-content requests.
5. Synthesizer pass 2 integrates valid corrections, performs a second coherence pass on touched sections, and returns.

### EM-side error handling

If the synthesizer reports `RELAY_STALLED` (no specialist left a mailbox line), the relay proceeds with all-non-response annotations. This is not a pipeline failure — the assessment stands; relay coverage was unconfirmed. Atlas refinement (Step 7.5) is unaffected.

## Coverage-Auditor Lifecycle (repo pipeline)

> Agent definition: `agents/coverage-auditor.md`

The coverage auditor is a plain `Agent` dispatched by the EM after the Workflow completes. It is dispatched at the driver's "On Completion Notification" step — **after** synthesis is written, **before** the run concludes.

### Placement in the repo command

After the EM receives the Workflow's completion notification (Step 7 of `commands/research.md` — repo mode), and before the run concludes:

1. **Dispatch the auditor** as a plain `Agent` (it stays independent of the Workflow):
   - `subagent_type: "coordinator:coverage-auditor"`
   - Model: sonnet
   - Tool grant: Read, Grep, Glob (base grant — no write tools on synthesis output path)
   - Provide: synthesis output path (and `ASSESSMENT.md` + `GAP-ANALYSIS.md` paths in `--compare` mode), scratch directory path, pipeline identifier `"B"`
2. **Wait for auditor `DONE: {sidecar-path}` reply.**
3. **Proceed to cleanup** (Step 7 archive + commit). The auditor is already done.

In `--compare` mode, the auditor receives both the assessment and gap-analysis output paths and audits each synthesis artifact separately.

### What the auditor does

The auditor reads `{scratch-dir}/*-claims.json` and `*-summary.md` specialist claim records and the synthesis. It cross-references each claim (binary: `present-with-pointer` / `absent`) and produces a sidecar at `{output-path minus .md}-coverage-audit.md` with two structured sections:

- **Coverage Pointers** — claim-by-claim presence table. Input universe is specialist claim records (`*-claims.json`, `*-summary.md`); `[SWEEP ADDITION]` content is explicitly excluded from the denominator (no upstream claim record exists).
- **Completeness Map** — topics distilled out of the synthesis, with source pointers so a reader can self-serve the full architectural picture without reading every specialist output. Also consolidates any `[UNFILLED GAP]` inline markers from the synthesis.

The `gap-report.md` answers "did we research enough?" (input coverage, synthesizer-owned). The coverage-audit sidecar answers "did the synthesis carry the research?" (output coverage, reader-facing completeness). **These are two separate artifacts with two separate questions — do not conflate them.**

The auditor never edits the synthesis. It emits the sidecar only.

### Invariants

- Auditor is always-on — fires on plain `--mode=repo`, `--deeper`, and `--deepest` alike. No skip condition.
- The synthesizer's `[UNFILLED GAP]` inline markers remain in synthesis prose (reader-facing). The auditor's Completeness Map supersedes the synthesizer's free-prose "thin areas" meta-observations paragraph and consolidates/references the inline markers — it does not delete them.

## Queryable Index Layer (durable artifacts)

> Output must conform to `coordinator/schemas/research-synthesis.schema.json` and `coordinator/schemas/research-claim.schema.json`.

### Run-stem naming convention

All repo-pipeline durable outputs share the stem `YYYY-MM-DD-repo-{topic-slug}` under `docs/research/`. The `repo-` infix distinguishes them from web-pipeline (`YYYY-MM-DD-{topic-slug}`) and structured-pipeline outputs on the same date. The `pipeline: repo` frontmatter field provides the same disambiguation for query-records filtering.

### Research-synthesis frontmatter

The synthesizer prepends YAML frontmatter to `docs/research/YYYY-MM-DD-repo-{topic-slug}.md` per `coordinator/schemas/research-synthesis.schema.json`. Fields: `title`, `question`, `date`, `pipeline: repo`, `source_count`, `topic_facets[]`, `coverage_score`, `confidence_summary` (optional). **The prose body is always agent-authored** — frontmatter is the only deterministic layer.

### Per-specialist claims files

Repo specialists write `{scratch-dir}/{chunk-letter}-claims.json` alongside their assessment (see `agents/repo-specialist.md` § Claims Output). Each file is a JSON array of claim objects conforming to `coordinator/schemas/research-claim.schema.json`. The coverage auditor reads these as input; the synthesizer merges them into the durable index.

### Merged claims index

The synthesizer merges `{scratch-dir}/[A-D]-claims.json` into `{scratch-dir}/merged-claims.json` and reports `pipeline: repo` (never `ran_at` — it has no clock; the EM measures the merge moment as the mtime of `merged-claims.json`); the **EM** then emits the durable pair `docs/research/YYYY-MM-DD-repo-{topic-slug}.claims.json` + `.claims.meta.json` via the single `claims-emit` writer (repo-driver Step 7.4.5). Claim `id` values are scoped per chunk (e.g., `"A-1"`, `"B-3"`) — no deduplication is needed. If no per-specialist claims files exist, the synthesizer derives claims from the assessment files (fallback documented in `repo-synthesizer-prompt-template.md` § Durable Index Artifacts).

### Gap-report — NOT produced by the repo pipeline

The `*-gap-report.md` artifact (`coordinator/schemas/gap-report.schema.json`) is a **web-pipeline construct** — it drives the web pipeline's deepening gate ("did we research enough?"). The repo pipeline does not implement a deepening gate and does not produce a gap-report.

Repo-pipeline gap signals appear as `[COVERAGE GAP]` inline markers in the synthesis prose (synthesizer-authored) and, in `--compare` mode, as the tiered action items in `docs/research/YYYY-MM-DD-repo-{topic-slug}-gap-analysis.md`. The coverage-audit sidecar (`*-coverage-audit.md`, auditor-owned) answers "did the synthesis carry the research?" — this is the repo pipeline's analog to the web pipeline's gap-report for output-coverage purposes.

Do not fabricate a gap-report for a repo pipeline run. If a caller expects `*-gap-report.md`, direct them to the `[COVERAGE GAP]` markers in the synthesis and the coverage-audit sidecar.

## Error Handling Matrix

| Failure | Action |
|---------|--------|
| Survey agent fails (`--survey`) | Report to PM: "Survey failed — proceed without survey?" Survey is additive, not blocking. |
| Survey exceeds 30-min ceiling | Proceed with whatever was written. If empty, skip survey. |
| Scout fails (no inventory / stub / false completion) | The script's Step 5.5 gate catches it (`stub-file-gate`, ≥30 lines; a returned scout or plausible DONE message is NOT evidence). The script redispatches the chunk to a **Sonnet** scout (never re-Haiku — `coordinator/snippets/em-operating-doctrine.md` § Extensions to coordinator defaults ▸ Fan-out dispatch extras ¶ "Scouts: disk-first"). Stub only if Sonnet also fails; specialist self-directed Glob+Read is the last resort, not the first. |
| Scout times out (partial inventory) | Step 5.5 gate: a partial inventory <30 lines fails the gate → Sonnet-escalation; ≥30 lines passes and specialists supplement with their own Glob/Read. |
| Atlas sketch fails (`--deepest`) | Specialists operate in `--deeper` mode. Atlas refinement still runs post-synthesis. |
| Atlas sketch produces partial output | Accept what exists. Missing artifacts are not passed to specialists. |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and returns. |
| Specialist produces thin assessment | Synthesizer notes the gap; EM can supplement manually. |
| Workflow ends without a synthesis | Disk-check `{output-path}` and `{scratch-dir}/synthesis.md` (Step 6.5); read the Workflow's result. Redispatch the synthesizer, or if specialist outputs are present, EM reads raw specialist outputs for PM. |
| All specialists fail | The synthesizer reports no assessments in the Workflow result; report to PM. |
| Workflow fails to start or errors mid-run | Report to PM with the Workflow's error; completed stages' files persist in the scratch directory. |
| Atlas refinement fails (`--deepest`) | Commit assessment without atlas. Note to PM. Atlas is additive. |
| Atlas refinement produces partial output (`--deepest`) | Accept what exists, note thin coverage to PM. |
| Atlas refinement exceeds 10-min ceiling (`--deepest`) | Proceed without atlas, report to PM. |
