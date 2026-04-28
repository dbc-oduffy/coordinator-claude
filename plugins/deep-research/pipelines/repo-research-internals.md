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
