---
description: Bootstrap or refresh the architecture atlas via multi-phase agent pipeline (Haiku scouts → Sonnet analysts → Opus synthesizer)
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: "[--refresh]"
---

# Architecture Audit — Deep System Discovery

Produce a comprehensive **architecture atlas** — function-level connectivity maps, ASCII flow diagrams, cross-system dependency matrices, and per-system observations. The atlas is a persistent artifact that weekly audits maintain incrementally.

**This command occupies your context for ~25-55 min. It is not background work.**

**Two modes:**
- **First run (BOOTSTRAP):** No atlas exists. Full discovery and mapping of all systems. No grades — observations only.
- **Refresh:** Atlas exists. Identifies churned systems via git, remaps only those, carries stable systems forward. Substantially cheaper.

**Core principle:** Each model tier does what it's best at. Haiku inventories mechanically (cheap, parallel). Sonnet analyzes and diagrams (analytical depth). Opus synthesizes cross-system connectivity (highest judgment). Don't waste expensive models on cheap work.

**Sub-chunking principle:**
- **First run (Phase 1, full inventory):** Any system with >12 files splits into sub-chunks of **8-12 files** grouped by concern.
- **Refresh (Phase 1R, delta-only):** Phase 1R inventories ONLY new/changed symbols — not every function — so each Haiku can absorb a much larger file count tractably. Use sub-chunks of **30-60 changed files**. Empirically this cuts wall-clock ~3x vs. the default chunk size on large refresh runs (e.g., 27-Haiku audits) without degrading delta quality. Do NOT apply this widening to first-run / full inventories.

**Not for:** Weekly spot-checks (use weekly-architecture-audit), daily commit reviews (use daily-code-health), or one-off investigation.

## Arguments

`$ARGUMENTS` may contain `--refresh`:
- **No `--refresh`, no atlas:** First run — full discovery
- **`--refresh`:** Refresh — remap only churned systems

Auto-detection: check for `tasks/architecture-atlas/systems-index.md`. If it exists and `--refresh` wasn't passed, ask the PM: "Atlas already exists. Did you mean `--refresh`?"

Announce: "I'm running `/architecture-audit` to [bootstrap / refresh] the architecture atlas."

## Atlas Directory Structure

```
tasks/architecture-atlas/
  systems-index.md          # Master index — stats, last mapped (no grades)
  cross-system-map.md       # Unified connectivity diagram
  connectivity-matrix.md    # Dependency counts table
  file-index.md             # File-to-system mapping for new-system detection
  systems/
    {system-name}.md        # Per-system detail pages with YAML frontmatter
```

## Phase Pipeline — STRICT SEQUENCE

```
Phase 0 (YOU) → Phase 1 (Haiku, parallel) → [wait] → Phase 2 (Sonnet, parallel) → [wait] → Phase 3 (Opus leaf) → [wait] → Phase 4 (YOU)
```

**Phases MUST run sequentially.** Each phase's output shapes the next phase's prompts.

## Phase 0: Scope and Chunking (~5 min, YOU do this)

1. **Read orientation artifacts:** `tasks/repomap.md` and `DIRECTORY.md`

2. **Detect mode:**
   - Check for `tasks/architecture-atlas/systems-index.md`
   - **Not found:** First run → step 3
   - **Found:** Refresh → step 4

3. **First run — define system boundaries and sub-chunks:**
   - Derive 4-8 system boundaries from repo map + directory structure
   - Each file assigned to exactly ONE system. No overlaps.
   - Sub-chunk systems with >12 files into 8-12 file groups by concern. Label: `{system}-A`, `{system}-B`, etc.
   - Write focus questions for each chunk
   - **Generate run ID** — `YYYY-MM-DD-HHhMM`. Create: `tasks/scratch/deep-architecture-audit/{run-id}/`
   - **Output:** Chunk table (system, sub-chunks, file count, mode: full, focus questions)

4. **Refresh — identify churned systems:**
   - Read `systems-index.md` for existing systems and `Last mapped` dates
   - Diff git activity since each system's last mapped date:
     ```bash
     git log --since="<last-mapped-date>" --name-only --pretty=format: -- <system-dirs> | sort -u
     ```
   - Changed files → `mode: refresh`. No changes → `mode: stable` (carry forward, skip Phases 1-2)
   - Apply sub-chunking to churned systems
   - **Generate run ID** and create scratch directory
   - **Output:** Chunk table (system, mode: refresh/stable, changed files)

## Phase 1/1R: Function-Level Inventory (dispatch Haiku agents, parallel)

**Dispatch:** One Haiku agent per sub-chunk with `model: "haiku"`.

**Read the template:** Open `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-audit/agent-prompts.md`. Copy the relevant template verbatim:
- **First run:** Copy **Phase 1: Haiku Function-Level Inventory Prompt**. Fill in: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[LIST OF DIRECTORIES/FILES]`, `[SCRATCH_PATH]`.
- **Refresh:** Copy **Phase 1R: Haiku Delta Inventory Prompt (Refresh)**. Fill in: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[CHANGED FILES LIST]`, `[EXISTING ATLAS ENTRY]`, `[SCRATCH_PATH]`.

**Do NOT write a custom prompt** — the template's guardrails prevent Haiku from confabulating relationships.

**Scratch path:** `tasks/scratch/deep-architecture-audit/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md`

**Scratch verification:** Before Phase 2, verify all expected files exist. Re-dispatch once on missing. Skip sub-chunk on second failure.

**Inline-markdown failure mode:** ~10% of Haiku Phase 1/1R agents return the inventory as inline markdown in their reply instead of calling Write — even when the prompt names the path. Detect by: scratch file missing/empty AND the agent's reply contains a heavy markdown body (e.g., multiple `### ` headings or >100 lines of structured output). On detection, re-dispatch with this prefix prepended to the prompt: `CRITICAL: Inline markdown is unacceptable. You MUST call the Write tool with file_path="[SCRATCH_PATH]" or your task fails. Do not return the inventory in your reply.` This recovery prompt has reliably converted inline-output Haikus on retry.

## Phase 2/2R: System Analysis (dispatch Sonnet agents, parallel)

**Dispatch:** One Sonnet agent per system with `model: "sonnet"` (reads ALL sub-chunk inventories for that system).

**Read the template** from `agent-prompts.md`:
- **First run:** Copy **Phase 2: Sonnet System Analysis Prompt (Discovery)**. Fill in `[SYSTEM NAME]`, `[CHUNK DESCRIPTION]`, and paste Phase 1 output from scratch files.
- **Refresh:** Copy **Phase 2R: Sonnet System Analysis Update Prompt (Refresh)**. Fill in `[SYSTEM NAME]`, `[EXISTING ATLAS PAGE]`, and paste Phase 1R output.

**No grading in Phase 2.** Observations only.

**Scratch path:** `tasks/scratch/deep-architecture-audit/{run-id}/{chunk-letter}-phase2-sonnet.md`

**Scratch verification:** Verify all Phase 2/2R files exist before Phase 3. Re-dispatch once; skip on second failure.

## Phase 3/3R: Cross-System Synthesis (dispatch ONE Opus leaf agent)

**Dispatch:** One agent with `model: "opus"`. This is a leaf agent — it synthesizes and writes files but does NOT spawn further agents.

**Context overflow guard:** If total Phase 2 output exceeds ~80K tokens (~300KB / ~4000 lines of markdown), summarize each system to its boundary catalog + top 5 observations before passing to the Opus agent.

**Read the template** from `agent-prompts.md`:
- **First run:** Copy **Phase 3: Opus Cross-System Synthesis Prompt (Full)**. Fill in `[N]` and paste Phase 2 reports.
- **Refresh:** Copy **Phase 3R: Opus Cross-System Synthesis Prompt (Refresh)**. Fill in `[N]`, paste stable atlas pages, and paste Phase 2R reports.

The Opus agent produces all atlas artifacts:
- `systems-index.md` — master index (no grades)
- `cross-system-map.md` — unified ASCII diagram
- `connectivity-matrix.md` — dependency counts
- `file-index.md` — file-to-system mapping
- `systems/{name}.md` — per-system pages with YAML frontmatter

**No grades in Phase 3.** Weekly-architecture-audit adds grades incrementally.

## Phase 4: Integration and Report (YOU do this)

1. **Review atlas for completeness:**
   - Every system has a file in `systems/`
   - `systems-index.md` has a row for every system
   - `cross-system-map.md`, `connectivity-matrix.md`, `file-index.md` present
   - All YAML frontmatter has required fields

2. **Atomic commit:**
   ```bash
   git add tasks/architecture-atlas/
   git commit -m "deep-architecture-audit: [first run|refresh] — [N] systems mapped"
   ```

3. **Calculate rotation target:** Systems with highest cross-system connectivity and oldest `Last mapped` → suggested starting point for weekly-architecture-audit.

4. **Report to PM:**
   ```markdown
   ## Architecture Audit Complete

   **Mode:** [first run / refresh]
   **Systems mapped:** [N] ([list])
   **Key findings:** [coupling hotspots, boundary patterns, notable design choices]
   **Suggested rotation target:** [system name] (highest connectivity / oldest mapping)
   **Atlas location:** tasks/architecture-atlas/
   ```

5. **Clean scratch:** `rm -rf tasks/scratch/deep-architecture-audit/{run-id}/`
   Only delete after commit succeeds. On Phase 2/3 failure, scratch contains earlier phases for recovery.

## Cost Profile

| Scenario | Haiku | Sonnet | Opus | Wall-Clock |
|----------|-------|--------|------|------------|
| First run, 6 systems (≤12 files each) | 6 | 6 | 1 | ~25-35 min |
| First run, 8 systems (≤12 files each) | 8 | 8 | 1 | ~35-45 min |
| First run, large system (59 files → 5-6 sub-chunks) | 10-14 | 6-8 | 1 | ~40-55 min |
| Refresh, 2 churned | 2 | 2 | 1 | ~15-20 min |
| Refresh, 5 churned | 5 | 5 | 1 | ~25-30 min |

## Failure Modes

| Failure | Prevention |
|---------|------------|
| Haiku invents call relationships | Template says "write [UNKNOWN], do NOT guess" |
| Haiku analyzes instead of inventorying | Template says "completeness > analysis" |
| >12 files per agent | Sub-chunk to 8-12 files before dispatch |
| ASCII diagrams too wide | Template says "max 100 chars, split if needed" |
| Custom prompts instead of templates | Copy template verbatim from agent-prompts.md |
| Haiku returns inline markdown instead of calling Write | Phase 1/1R templates carry MANDATORY Write framing; on detection (empty scratch + heavy markdown reply), re-dispatch with the CRITICAL prefix shown in Phase 1 Scratch verification |
| Phase 1R refresh runs slow due to over-narrow chunking | Use 30-60 changed files per Haiku for refresh (Phase 1R is delta-only); keep 8-12 only for first-run full inventories |
| Opus context overflow | Summarize Phase 2 to boundary catalogs if >80K tokens |
| Partial write on failure | Atomic commit in Phase 4; failure leaves previous atlas intact |
| Grades added during discovery | Templates enforce observations only; weekly audit adds grades |
