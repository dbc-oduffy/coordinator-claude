# Pipeline B (Repo Research) — Internals Reference

Detail companion to `commands/repo.md`. Step numbers refer to that command. Trimmed out of the command itself to keep the procedural skeleton readable; consult here when implementing or debugging a specific phase.

## Phase 1.5 — Repomap Generation (`--deeper`)

Used by Step 3 Phase 1.5 in `commands/repo.md`. Goal: dependency-weighted file ranking to inform chunk scoping and specialist deep-read prioritization.

**Step A — Detect primary language(s):**
```bash
find {repo-path} -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10
```

**Step B — Extract import/dependency edges:** Run language-appropriate grep on the dominant language(s). For polyglot repos, run patterns for the top 2.

| Language | Pattern |
|----------|---------|
| Python | `grep -rh "^from \|^import " --include="*.py" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| JS/TS | `grep -rh "from ['\"]" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| Go | `grep -rh '"[^"]*"' --include="*.go" {repo-path} \| grep -v "// " \| sort \| uniq -c \| sort -rn \| head -40` |
| Rust | `grep -rh "^use " --include="*.rs" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| C/C++ | `grep -rh '#include "' --include="*.h" --include="*.cpp" --include="*.c" --include="*.hpp" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |
| Java | `grep -rh "^import " --include="*.java" {repo-path} \| sort \| uniq -c \| sort -rn \| head -40` |

**Step C — Resolve to files and count cross-references:** For each of the top ~20 most-imported modules, resolve to a file path and count distinct referencing files:
```bash
grep -rl "{module-name}" --include="*.{ext}" {repo-path} | wc -l
```

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
- `docs/research/YYYY-MM-DD-{topic-slug}-file-index.md`
- `docs/research/YYYY-MM-DD-{topic-slug}-system-map.md`
- `docs/research/YYYY-MM-DD-{topic-slug}-connectivity-matrix.md`
- `docs/research/YYYY-MM-DD-{topic-slug}-architecture-summary.md` (4th artifact, requires specialist data)

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

> Spec backlink: `archive/specs/2026-05/2026-05-30-deep-research-synthesis-fidelity-coverage-audit.md` § C7, § Resolved Decisions OD-2, § Per-pipeline applicability matrix
> Upstream doctrine: `coordinator/CLAUDE.md § Agent Teams — blockedBy Is a Gate, Not a Trigger`; `docs/wiki/agent-teams-patterns.md:38-44`

The fidelity relay is a **Team-1 internal phase** that fires inside the sweep agent (see `agents/research-synthesizer.md § Fidelity Relay`) — it is NOT a post-TeamDelete activity. This section documents the EM-side preconditions and the relay's placement in the command sequence.

### Gating condition (repo-specific)

The relay fires on `--deepest` runs only. The `--deepest` flag (`repo-driver.md:22-23`) implies `--deeper` + `--survey` — the three-phase deep pipeline with atlas sketch, repomap, and full specialist context. `--deeper` alone does NOT trigger the relay. Plain `repo` and `--survey` mode skip the relay.

The relay runs **before** the synthesizer marks its task complete and **before** the EM triggers TeamDelete at Step 7.

### Relay locus — Team 1, pre-Step-7

**The relay always executes inside the Team-1 synthesizer, not as a separate post-synthesis dispatch.** Specialists are alive-but-idle in Team 1 when the synthesizer finishes (`team-protocol.md:138`); the team is not yet torn down. This is the correct execution window: the authors whose content the relay protects are still reachable. Atlas refinement (Step 7.5) runs after TeamDelete and is unrelated to the relay.

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

> Spec backlink: `archive/specs/2026-05/2026-05-30-deep-research-synthesis-fidelity-coverage-audit.md` § C1–C2, § Resolved Decisions RD-1, RD-3, RD-4, AC1–AC3
> Agent definition: `agents/coverage-auditor.md`

The coverage auditor is a **non-teammate Agent dispatched by the EM** after the synthesis is complete and the synthesizer has marked its task done. It is dispatched at the driver's "On Completion Notification" step — **after** synthesis is written, **before** archive/TeamDelete.

### Placement in the repo command

After the EM receives the synthesizer's `DONE` message (Step 7 of `commands/research.md` — repo mode), and before calling `TeamDelete`:

1. **Dispatch the auditor** as a plain `Agent(...)` (NOT under `TeamCreate`/team_name):
   - `subagent_type: "deep-research:coverage-auditor"`
   - Model: sonnet
   - Tool grant: Read, Grep, Glob (base grant — no write tools on synthesis output path)
   - Provide: synthesis output path (and `ASSESSMENT.md` + `GAP-ANALYSIS.md` paths in `--compare` mode), scratch directory path, pipeline identifier `"B"`
2. **Wait for auditor `DONE: {sidecar-path}` reply.**
3. **Proceed to TeamDelete** (Step 7 TeamDelete). The auditor is already done; the team can be torn down.

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

## Error Handling Matrix

| Failure | Action |
|---------|--------|
| Survey agent fails (`--survey`) | Report to PM: "Survey failed — proceed without survey?" Survey is additive, not blocking. |
| Survey exceeds 30-min ceiling | Proceed with whatever was written. If empty, skip survey. |
| Scout fails (no inventory written) | Specialists fall back to self-directed Glob + Read; budget 3 extra minutes. |
| Scout times out (partial inventory) | Specialists use what's there + supplement with own Glob/Read. |
| Atlas sketch fails (`--deepest`) | Specialists operate in `--deeper` mode. Atlas refinement still runs post-synthesis. |
| Atlas sketch produces partial output | Accept what exists. Missing artifacts are not passed to specialists. |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and marks task complete. |
| Specialist produces thin assessment | Synthesizer notes the gap; EM can supplement manually. |
| Synthesizer doesn't wake after all specialists complete | Verify specialists sent DONE; if not, manual `SendMessage` nudge. After 5 min stalled, EM reads raw specialist outputs for PM. |
| All specialists fail | `TeamDelete`, report to PM. |
| Team creation fails | Report to PM. |
| Atlas refinement fails (`--deepest`) | Commit assessment without atlas. Note to PM. Atlas is additive. |
| Atlas refinement produces partial output (`--deepest`) | Accept what exists, note thin coverage to PM. |
| Atlas refinement exceeds 10-min ceiling (`--deepest`) | Proceed without atlas, report to PM. |
