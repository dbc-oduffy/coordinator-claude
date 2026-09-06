# Pipeline B (Repo Research) — Internals Reference

Detail companion to `pipelines/deep-research/repo-driver.md`. Step numbers refer to that command. Trimmed out of the command itself to keep the procedural skeleton readable; consult here when implementing or debugging a specific phase.

## Phase 1.5 — Repomap Generation (`--deeper`)

Used by Step 3 Phase 1.5 in `commands/repo.md`. Goal: dependency-weighted file ranking to inform chunk scoping and specialist deep-read prioritization.

**Steps A-C — Language census, import/dependency edges, cross-reference counts:** a single invocation of the `repo-census` CLI:

```text
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/repo-census" <repo-path>
```

`repo-census` walks the target repo (honoring `.gitignore` and a fixed vendor skip-list), ranks file extensions by frequency, extracts per-language import/dependency-statement targets ranked by occurrence count for the top 2 languages by census (Python, JS/TS, Go, Rust, C/C++, and Java are covered; polyglot repos get the top 2 by census unless overridden), and — for the most-imported modules — resolves a best-effort file path and counts *distinct referencing files*. Add `--json` for machine consumption. The pipeline consumes this as scoping signal, not a build-accurate dependency graph: it tells the EM which files are structurally central before specialists are dispatched, the same role Steps A-C's shell shapes served, minus the copy-paste-and-fill-in-placeholders step.

Note: `repo-census` is a distinct tool from the tree-sitter-based `repomap` (`coordinator/bin/repomap/generate-repomap.py`, claude-klabauter) that backs this project's own orientation hook — that one ranks a repo WE work in by PageRank centrality + git activity for a token-budgeted context map; `repo-census` has no git-activity signal and targets an arbitrary external repo we've never seen. Don't conflate the two.

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

After the team is deleted and the assessment verified, dispatch a Sonnet subagent to refine the preliminary atlas using specialist analysis and synthesis findings.

1. **Read template:** `${CLAUDE_PLUGIN_ROOT}/pipelines/repo-atlas-prompt-template.md`
2. **Fill fields:** `[REPO_NAME]`, `[DATE]`, `[RUN_ID]`, `[VERSION]`; `[SYSTEM_A_NAME]`–`[SYSTEM_D_NAME]` and `[CHUNK_A_DESCRIPTION]`–`[CHUNK_D_DESCRIPTION]` from scope.md; `[SCRATCH_DIR]`, `[SYNTHESIS_PATH]` (= `{output-path}`), `[SPAWN_TIMESTAMP]` (= current `date +%s`); preliminary artifact paths `[PRELIMINARY_FILE_INDEX]`, `[PRELIMINARY_SYSTEM_MAP]`, `[PRELIMINARY_CONNECTIVITY_MATRIX]` from `{scratch-dir}/atlas-sketch-*.md`.
3. **Dispatch as regular Sonnet subagent** (NOT a teammate — team is deleted).
4. **Verify** all 4 artifacts exist and have substantive content: `atlas-file-index.md`, `atlas-system-map.md`, `atlas-connectivity-matrix.md`, `atlas-architecture-summary.md`.
5. **If verification passes:** copy the 4 artifacts from scratch to the `docs/research/...` paths set in Step 1.
6. **If verification fails:** proceed without atlas. Note to PM: "Atlas generation failed or produced thin output — assessment is complete, atlas artifacts missing." Atlas is additive, not blocking.

## Phase B — Atlas Sketch Details (`--deepest`, in Step 5)

After scouts complete, before specialists are spawned:

1. **Read template:** `${CLAUDE_PLUGIN_ROOT}/pipelines/repo-atlas-sketch-prompt-template.md`
2. **Fill fields** using scope.md chunk descriptions: `[REPO_NAME]`, `[DATE]`, `[RUN_ID]`, `[SYSTEM_A_NAME]`–`[SYSTEM_D_NAME]`, `[CHUNK_A_DESCRIPTION]`–`[CHUNK_D_DESCRIPTION]`, `[SCRATCH_DIR]`, `[SPAWN_TIMESTAMP]`.
3. **Dispatch as a regular Haiku subagent** (NOT a teammate — preserves the 7-teammate limit).
4. **Verify** all three sketch artifacts exist in `{scratch-dir}/atlas-sketch-*.md`.
5. **Mark task completed:** `TaskUpdate(taskId: "{atlas-sketch-id}", status: "completed")`.
6. **If verification fails:** proceed without atlas sketch. Specialists operate in `--deeper` mode (repomap only). Atlas refinement still runs post-synthesis. Note to PM.

## Fidelity Relay Protocol (`--deepest` runs only)

> Upstream doctrine: `~/.claude/CLAUDE.md § Agent Teams — blockedBy Is a Gate, Not a Trigger`

The fidelity relay is a **Team-1 internal phase** that fires inside the sweep agent (see `agents/research-synthesizer.md § Fidelity Relay`) — it is NOT a post-synthesis teardown activity. This section documents the EM-side preconditions and the relay's placement in the command sequence.

### Gating condition (repo-specific)

The relay fires on `--deepest` runs only. The `--deepest` flag (`repo-driver.md:22-23`) implies `--deeper` + `--survey` — the three-phase deep pipeline with atlas sketch, repomap, and full specialist context. `--deeper` alone does NOT trigger the relay. Plain `repo` and `--survey` mode skip the relay.

The relay runs **before** the synthesizer marks its task complete and **before** the team is torn down (auto, on session exit).

### Relay locus — Team 1, pre-Step-7

**The relay always executes inside the Team-1 synthesizer, not as a separate post-synthesis dispatch.** Specialists are alive-but-idle in Team 1 when the synthesizer finishes (`team-protocol.md:138`); the team is not yet torn down. This is the correct execution window: the authors whose content the relay protects are still reachable. Atlas refinement (Step 7.5) runs after the team is torn down (auto, on session exit) and is unrelated to the relay.

### Relay sequence (synthesizer-internal; summarized for EM debuggability)

1. Synthesizer wakes each Team-1 specialist via `SendMessage` with a `FIDELITY_RELAY` prompt scoped to misrepresentation only — "did the synthesis flatten, distort, or misrepresent YOUR finding?"
2. **Per-specialist bounded timeout:** 2 minutes (mirrors the `team-protocol.md:140` CHALLENGE timeout). Specialists are alive per `team-protocol.md:138`.
3. **Non-response fallback:** if a specialist does not reply within 2 minutes, the synthesizer proceeds without their confirmation and annotates the synthesis: `[RELAY: {TOPIC_LETTER} specialist did not respond within timeout — relay unconfirmed for this topic]`. The pipeline never hangs on a non-responding specialist.
4. **Bloat-guard (structural discriminator):** a valid fidelity correction must reference an existing synthesis sentence and assert it misrepresents the source. A correction that only asks to ADD a sentence is out of scope by construction — the relay is scoped to misrepresentation, not coverage inflation. The synthesizer rejects add-content requests.
5. Synthesizer integrates valid corrections and performs a second coherence pass on touched sections.
6. Only after steps 1–5 does the synthesizer mark its task complete.

### EM-side error handling

If the synthesizer reports `RELAY_STALLED` (no specialist responses after timeout across all specialists), the relay proceeds with all-non-response annotations. This is not a pipeline failure — the assessment stands; relay coverage was unconfirmed. Atlas refinement (Step 7.5) is unaffected.

## Coverage-Auditor Lifecycle (repo pipeline)

> Agent definition: `agents/coverage-auditor.md`

The coverage auditor is a **non-teammate Agent dispatched by the EM** after the synthesis is complete and the synthesizer has marked its task done. It is dispatched at the driver's "On Completion Notification" step — **after** synthesis is written, **before** the run concludes (the team is torn down automatically on session exit).

### Placement in the repo command

After the EM receives the synthesizer's `DONE` message (Step 7 of `commands/research.md` — repo mode), and before the run concludes:

1. **Dispatch the auditor** as a non-teammate Agent — do not pass `team_name` (it keeps the auditor independent of the team):
   - `subagent_type: "coordinator:coverage-auditor"`
   - Model: sonnet
   - Tool grant: Read, Grep, Glob (base grant — no write tools on synthesis output path)
   - Provide: synthesis output path (and `ASSESSMENT.md` + `GAP-ANALYSIS.md` paths in `--compare` mode), scratch directory path, pipeline identifier `"B"`
2. **Wait for auditor `DONE: {sidecar-path}` reply.**
3. **Proceed to cleanup** (Step 7 archive + commit). The auditor is already done; the team auto-cleans on session exit.

In `--compare` mode, the auditor receives both the assessment and gap-analysis output paths and audits each synthesis artifact separately.

### What the auditor does

The auditor reads `{scratch-dir}/*-claims.json` and `*-summary.md` specialist claim records and the synthesis. It cross-references each claim (binary: `present-with-pointer` / `absent`) and produces a sidecar at `{output-path minus .md}-coverage-audit.md` with two structured sections:

- **Coverage Pointers** — claim-by-claim presence table. Input universe is specialist claim records (`*-claims.json`, `*-summary.md`); `[SWEEP ADDITION]` content is explicitly excluded from the denominator (no upstream claim record exists).
- **Completeness Map** — topics distilled out of the synthesis, with source pointers so a reader can self-serve the full architectural picture without reading every specialist output. Also consolidates any `[UNFILLED GAP]` inline markers from the synthesis.

The `gap-report.md` answers "did we research enough?" (input coverage, synthesizer-owned). The coverage-audit sidecar answers "did the synthesis carry the research?" (output coverage, reader-facing completeness). **These are two separate artifacts with two separate questions — do not conflate them.**

The auditor never edits the synthesis. It emits the sidecar only.

### Invariants

- 7-teammate ceiling is unaffected — auditor is a non-teammate subagent (same pattern as the atlas-sketch dispatch at Step 5 `repo-research-internals.md § Phase B` and atlas-refinement at Step 7.5).
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
| Scout fails (no inventory / stub / false completion) | Step 5.5 hard gate catches it (`ls` + ≥30-line check; a `completed` task or plausible DONE message is NOT evidence). Re-open the scout task, then redispatch the chunk to a non-teammate **Sonnet** scout (never re-Haiku — `coordinator/snippets/em-operating-doctrine.md` § Extensions to coordinator defaults ▸ Fan-out dispatch extras ¶ "Scouts: disk-first"; formerly `coordinator/CLAUDE.md` § "Scouts and Disk-First Verification", retired 2026-07-27). EM-stub only if Sonnet also fails; specialist self-directed Glob+Read is the last resort, not the first. |
| Scout times out (partial inventory) | Step 5.5 gate: a partial inventory <30 lines fails the gate → Sonnet-escalation; ≥30 lines passes and specialists supplement with their own Glob/Read. |
| Atlas sketch fails (`--deepest`) | Specialists operate in `--deeper` mode. Atlas refinement still runs post-synthesis. |
| Atlas sketch produces partial output | Accept what exists. Missing artifacts are not passed to specialists. |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and marks task complete. |
| Specialist produces thin assessment | Synthesizer notes the gap; EM can supplement manually. |
| Synthesizer doesn't wake after all specialists complete | Verify specialists sent DONE; if not, manual `SendMessage` nudge. After 5 min stalled, EM reads raw specialist outputs for PM. |
| All specialists fail | Report to PM; team auto-cleans on session exit. |
| Team creation fails | Report to PM. |
| Atlas refinement fails (`--deepest`) | Commit assessment without atlas. Note to PM. Atlas is additive. |
| Atlas refinement produces partial output (`--deepest`) | Accept what exists, note thin coverage to PM. |
| Atlas refinement exceeds 10-min ceiling (`--deepest`) | Proceed without atlas, report to PM. |
