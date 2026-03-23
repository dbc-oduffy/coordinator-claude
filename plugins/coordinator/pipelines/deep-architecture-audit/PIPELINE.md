# Deep Architecture Audit

> Referenced by `/architecture-audit`. This is a pipeline definition, not an invocable skill.

## Overview

Produces a comprehensive **architecture atlas** — function-level connectivity maps, ASCII flow diagrams, cross-system dependency matrices, and per-system observations. The atlas is a persistent artifact that weekly audits maintain incrementally and annotate with grades over time.

**Two modes:**
- **First run:** No atlas exists. Full discovery and mapping of all systems. No grades produced — observations only.
- **Refresh:** Atlas exists. Identifies churned systems via git activity, remaps only those, carries stable systems forward. Substantially cheaper.

**Core principle:** Each model tier does what it's best at. Haiku inventories mechanically (cheap, parallel). Sonnet analyzes and diagrams (analytical depth). Opus synthesizes cross-system (highest judgment for connectivity mapping). Don't waste expensive models on cheap work; don't trust cheap models with judgment calls.

**Sub-chunking principle:** Any system with >12 files is too large for a single Haiku agent. Split into sub-chunks of 8-12 files grouped by concern before dispatching. Large systems multiply agent count — a 59-file system produces 5-7 Haiku scouts and 1 Sonnet analyst (who receives all scouts' reports).

**Announce at start:** "I'm running `/architecture-audit` to [bootstrap the architecture atlas / refresh the architecture atlas for churned systems]."

## When to Use

- **First audit of a repository** — no atlas exists yet
- **Monthly deep refresh** — catch coupling drift, architectural erosion, boundary violations that weekly spot-checks miss
- **Major restructuring** — after significant refactors, new system additions, or large merges
- **Atlas bootstrap** — weekly-architecture-audit requires an atlas; this creates it

**Not for:** Weekly spot-checks (use weekly-architecture-audit), daily commit reviews (use daily-code-health), or one-off file-level investigation.

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
Phase 0 (EM) → [wait] → Phase 1 (Haiku, parallel) → [wait for ALL] → Phase 2 (Sonnet, parallel) → [wait for ALL] → Phase 3 (Opus) → [wait] → Phase 4 (EM+PM)
```

**Phases MUST run sequentially.** Each phase's output shapes the next phase's prompts.

---

### Phase 0: Scope and Chunking (Coordinator)

**Model:** Coordinator (Opus). **Time:** ~5 min.

1. **Read orientation artifacts:**
   - `tasks/repomap.md` — function-level map with cross-file references
   - `DIRECTORY.md` — directory structure documentation

2. **Detect mode — first run vs. refresh:**
   - Check for `tasks/architecture-atlas/systems-index.md`
   - **If not found:** First run. Proceed to step 3.
   - **If found:** Refresh run. Proceed to step 4.

3. **First run — define system boundaries and sub-chunks:**
   - Derive 4-8 system boundaries from repo map + directory structure
   - Each file is assigned to exactly ONE system. No overlapping assignments.
   - Shared utilities go to a dedicated "shared/core" system or to the most dependent system.
   - **Sub-chunk large systems:** Any system with >12 files splits into sub-chunks of 8-12 files grouped by concern. Sub-chunks within the same system are labeled with the system name and a letter suffix (e.g., `physics-A`, `physics-B`). Sub-chunks share the same Sonnet analyst in Phase 2; each gets its own Haiku scout in Phase 1.
   - Write focus questions for each chunk (what are the key design decisions? what patterns dominate?)
   - **Generate run ID** — format: `YYYY-MM-DD-HHhMM` (current timestamp). This identifies the scratch directory: `tasks/scratch/deep-architecture-audit/{run-id}/`
   - **Output:** Chunk table using the **First Run Chunk Table** from `agent-prompts.md`. All chunks get `mode: full`.

4. **Refresh run — identify churned systems:**
   - Read `systems-index.md` for existing system list and `Last mapped` dates
   - Diff git activity since each system's last mapped date:
     ```bash
     git log --since="<last-mapped-date>" --name-only --pretty=format: -- <system-dirs> | sort -u
     ```
   - Systems with changed files → `mode: refresh` (get Phases 1R-2R)
   - Systems with no changes → `mode: stable` (carry forward, skip Phases 1-2)
   - Apply same sub-chunking rule to churned systems: >12 files → split into 8-12 file sub-chunks
   - **Generate run ID** — format: `YYYY-MM-DD-HHhMM` (current timestamp). This identifies the scratch directory: `tasks/scratch/deep-architecture-audit/{run-id}/`
   - **Output:** Chunk table using the **Refresh Chunk Table** from `agent-prompts.md`.

---

### Phase 1: Function-Level Inventory (Haiku agents, parallel)

**Model:** Haiku. **Dispatch:** One agent per sub-chunk with `mode: full`.

Each agent reads every file in its sub-chunk and produces:
- File path, line count, key structs/functions with signatures
- **Caller/callee relationships** — for each function: "Called by" and "Calls" with file paths
- **`[ENTRY]` markers** — functions called from outside the sub-chunk
- **`[BOUNDARY -> system-name]` markers** — calls to functions in other systems
- **`[INTERNAL -> sub-chunk-name]` markers** — calls to functions in a different sub-chunk of the same system
- Constants with actual values
- Cross-subsystem data flow

**Why Haiku:** Mechanical file reading and relationship cataloging requires no judgment. Haiku is 10x cheaper than Sonnet and fully sufficient for directing Phase 2.

**DISPATCH:** Open `agent-prompts.md` in this directory. Copy the **Phase 1: Haiku Function-Level Inventory Prompt** template verbatim. Fill in the bracketed fields: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[LIST OF DIRECTORIES/FILES]`. Dispatch that. Do NOT write a custom prompt — the template's guardrails (especially "[UNKNOWN]" for indeterminate callers and "completeness matters more than analysis") prevent Haiku from confabulating relationships.

**Scratch path:** `tasks/scratch/deep-architecture-audit/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md` (e.g., `B2-phase1-haiku.md`). Pass this as `[SCRATCH_PATH]` in the template. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

---

### Phase 1R: Delta Inventory (Haiku agents, parallel — refresh only)

**Model:** Haiku. **Dispatch:** One agent per sub-chunk with `mode: refresh`.

Each agent receives the existing atlas entry for its system and focuses only on changed files. Produces a delta inventory:
- New functions added
- Functions removed
- Changed signatures
- New cross-system boundaries added
- Cross-system boundaries removed

Same guardrails as Phase 1 — `[UNKNOWN]` for indeterminate relationships, completeness over analysis.

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 1R: Haiku Delta Inventory Prompt (Refresh)** template verbatim. Fill in: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[CHANGED FILES LIST]`, `[EXISTING ATLAS ENTRY]`. Do NOT write a custom prompt.

**Scratch path:** `tasks/scratch/deep-architecture-audit/{run-id}/{chunk-letter}{sub-chunk}-phase1R-haiku.md`. Pass this as `[SCRATCH_PATH]` in the template. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

**Scratch verification:** Before proceeding to Phase 2, verify all expected Phase 1 scratch files exist (`ls tasks/scratch/deep-architecture-audit/{run-id}/*-phase1-haiku.md`). If any are missing, re-dispatch the failed agent once. If it fails again, skip that sub-chunk and note the gap — the Sonnet analyst will work with incomplete inventory for that system.

---

### Phase 2: System Analysis + Diagrams (Sonnet agents, parallel)

**Model:** Sonnet. **Dispatch:** One agent per system (reads ALL sub-chunk inventories from `tasks/scratch/deep-architecture-audit/{run-id}/*-phase1-haiku.md` for that system).

Each agent reads the source files deeply and produces:

1. **System narrative** — purpose, responsibilities, design philosophy
2. **ASCII information flow diagram** — max 100 chars wide, split complex flows into labeled sub-diagrams:
   ```
   [Input] -> function_a() -> [Transform] -> function_b() -> [Output]
                                    |
                            function_c() -> [Side Effect]
   ```
3. **Boundary catalog** — every cross-system connection:
   ```
   {function} -> {target_system}:{target_function} | {data_type}
   ```
4. **Key architectural observations** — strengths, concerns, notable patterns. No grade.

**No grading in Phase 2.** Observations only. Grades come from weekly-architecture-audit rotation after the atlas is established.

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 2: Sonnet System Analysis Prompt (Discovery)** template verbatim. Fill in `[SYSTEM NAME]`, `[CHUNK DESCRIPTION]`, and read the Phase 1 output from scratch files for all sub-chunks of this system and paste it where indicated. Do NOT write a custom prompt — the template's observation-only structure prevents grade confabulation on first pass.

**Scratch path:** `tasks/scratch/deep-architecture-audit/{run-id}/{chunk-letter}-phase2-sonnet.md`. Pass this as `[SCRATCH_PATH]` in the template. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

---

### Phase 2R: System Analysis Update (Sonnet agents, parallel — refresh only)

**Model:** Sonnet. **Input:** Existing atlas page + Phase 1R delta inventory (read from `tasks/scratch/deep-architecture-audit/{run-id}/*-phase1R-haiku.md`, all sub-chunks).

Each agent receives:
1. The existing atlas page for the system (the full `systems/{name}.md`)
2. The Phase 1R delta inventory from the refresh Haiku pass (all sub-chunks combined)

Produces an updated analysis that:
- Preserves unchanged sections from the existing atlas page
- Updates functions, boundaries, and data flows that changed
- Regenerates the ASCII diagram if flow changed materially
- Updates architectural observations (no grade)

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 2R: Sonnet System Analysis Update Prompt (Refresh)** template verbatim. Fill in `[SYSTEM NAME]`, `[EXISTING ATLAS PAGE]`, and read the Phase 1R output from scratch files for all sub-chunks of this system and paste it as `[PHASE 1R DELTA]`. Do NOT write a custom prompt.

**Scratch path:** `tasks/scratch/deep-architecture-audit/{run-id}/{chunk-letter}-phase2R-sonnet.md`. Pass this as `[SCRATCH_PATH]` in the template. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

**Scratch verification:** Before proceeding to Phase 3, verify all expected Phase 2/2R scratch files exist. Re-dispatch once on failure; skip that system on second failure and note the gap for Opus.

---

### Phase 3: Cross-System Synthesis (Opus, single agent — full mode)

**Model:** Opus. **Input:** ALL Phase 2 reports (read from `tasks/scratch/deep-architecture-audit/{run-id}/*-phase2-sonnet.md`).

**Context overflow guard:** If total Phase 2 output exceeds ~80K tokens, the coordinator summarizes per-system reports to boundary catalogs + key observations before passing to Opus. Do not pass raw reports that would exceed context. Heuristic: ~80K tokens is approximately 300KB of markdown or ~4000 lines. If the combined Phase 2 output exceeds this, summarize each system to its boundary catalog + top 5 observations before passing to the Phase 3 agent.

Opus cross-references all boundary catalogs and produces:

1. **`systems-index.md`** — master index:

   | System | File Count | Entry Points | Cross-System Connections | Dependencies | Last Mapped |
   |--------|-----------|-------------|------------------------|-------------|------------|

2. **`cross-system-map.md`** — unified ASCII diagram with box-drawing characters showing all systems and their connections

3. **`connectivity-matrix.md`** — system-to-system dependency counts:

   |          | System A | System B | System C |
   |----------|----------|----------|----------|
   | System A | -        | 5        | 2        |

4. **`file-index.md`** — one line per tracked file, mapping it to its system:
   ```
   src/physics/aerodynamics.cpp -> physics
   src/physics/engine.cpp -> physics
   src/comms/radio.cpp -> communications
   ```

5. **Per-system files** (`systems/{name}.md`) — full analysis with YAML frontmatter:
   ```yaml
   ---
   system: coordinator-plugin
   last_mapped: 2026-03-18
   entry_points: 14
   cross_system_connections: 8
   dependencies: [plugin-infrastructure, documentation]
   ---
   ```

**No grades in Phase 3.** The systems-index.md has no Grade or Status columns. Per-system YAML frontmatter has no grade or status fields. Weekly-architecture-audit adds these incrementally as systems are reviewed.

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 3: Opus Cross-System Synthesis Prompt (Full)** template verbatim. Fill in `[N]` (number of systems) and read the Phase 2 reports from scratch files and paste them where indicated. Do NOT write a custom prompt.

---

### Phase 3R: Cross-System Synthesis (Opus, single agent — refresh mode)

**Model:** Opus. **Input:** ALL existing atlas pages (stable systems, read-only) + new Phase 2R reports (read from `tasks/scratch/deep-architecture-audit/{run-id}/*-phase2R-sonnet.md`).

Opus:
- Regenerates `cross-system-map.md` and `connectivity-matrix.md` from the union of stable + churned
- Updates `systems-index.md` rows for churned systems only; preserves stable rows
- Updates `file-index.md` to reflect any file additions, removals, or system reassignments
- Updates per-system files for churned systems only

**Context overflow guard:** Same as Phase 3 — summarize if >80K tokens.

**No grades in Phase 3R.** Observations only; grade updates are the weekly audit's domain.

**DISPATCH:** Open `agent-prompts.md`. Copy the **Phase 3R: Opus Cross-System Synthesis Prompt (Refresh)** template verbatim. Fill in `[N]`, paste stable system atlas pages where indicated, and read the Phase 2R reports from scratch files and paste them where indicated. Do NOT write a custom prompt.

---

### Phase 4: Integration and Report (Coordinator + PM)

**Model:** Coordinator (Opus). **Time:** ~5 min.

1. **Review atlas artifacts for completeness:**
   - Every system has a per-system file in `systems/`
   - `systems-index.md` has a row for every system
   - `cross-system-map.md`, `connectivity-matrix.md`, and `file-index.md` are present
   - All per-system YAML frontmatter has required fields

2. **Present summary to PM:**
   - Systems discovered, file counts, key entry points
   - Key architectural observations — coupling hotspots, boundary patterns, notable design choices
   - Systems that may warrant early audit priority (high cross-system connections, large file counts)
   - Comparison with previous mapping if refresh run

3. **Atomic commit:**
   ```bash
   git add tasks/architecture-atlas/
   git commit -m "deep-architecture-audit: [first run|refresh] — [N] systems mapped"
   ```
   If Phase 3 failed, the previous atlas remains intact — no partial writes.

4. **Calculate initial weekly rotation target:**
   - Systems with highest cross-system connectivity and oldest `Last mapped` dates get priority for first audit
   - Note suggested starting point for weekly-architecture-audit rotation

5. **Triage scratch files:**
   - **Default: DELETE all.** Phase 1/1R (Haiku) output was consumed by Phase 2/2R. Phase 2/2R (Sonnet) was consumed by Phase 3/3R and written to atlas artifacts.
   - **Recovery on failure:** If a Phase 2/3 agent fails, the scratch directory contains the completed earlier phases' output. Re-dispatching the failed phase will read from the existing scratch files — do NOT delete the scratch directory until all phases complete successfully. Only delete after Phase 4 commit succeeds.
   - **Clean up:** `rm -rf tasks/scratch/deep-architecture-audit/{run-id}/`

---

## Common Failure Modes

| Failure | Prevention |
|---------|------------|
| Haiku invents call relationships | "write [UNKNOWN], do NOT guess" |
| Haiku analyzes instead of inventorying | "completeness > analysis" (inherited from deep-research) |
| Dispatching agents with >12 files | Sub-chunk to 8-12 files per agent before dispatch |
| ASCII diagrams too wide | "max 100 chars, split if needed" |
| Atlas grows stale | Weekly updates individual pages; refresh mode remaps churned systems |
| Custom prompts instead of templates | "Copy template verbatim" (inherited from deep-research) |
| Chunk boundary overlap | Phase 0: each file assigned to exactly ONE system; shared utilities to dedicated system |
| Opus context overflow | If Phase 2 output >80K tokens, coordinator summarizes to boundary catalogs + observations before Opus |
| Partial write on failure | Phase 4 atomic commit; Phase 3 failure leaves previous atlas intact |
| Grades added during discovery | Phase 2 uses Discovery template (no grade); weekly audit adds grades incrementally |

## Cost Profile

| Scenario | Haiku | Sonnet | Opus | Wall-Clock |
|----------|-------|--------|------|------------|
| First run, 6 systems (all ≤12 files) | 6 | 6 | 1 | ~25-35 min |
| First run, 8 systems (all ≤12 files) | 8 | 8 | 1 | ~35-45 min |
| First run with large system (e.g., 59-file system → 5-6 sub-chunks) | 10-14 | 6-8 | 1 | ~40-55 min |
| Refresh, 2 churned | 2 | 2 | 1 | ~15-20 min |
| Refresh, 5 churned | 5 | 5 | 1 | ~25-30 min |

**Note:** Large systems multiply Haiku agent count but not Sonnet count — one Sonnet analyst receives all sub-chunk reports for a given system. Sub-chunking adds Haiku cost only.

## Integration

- **REQUIRED BACKGROUND:** coordinator:dispatching-parallel-agents for Phase 1/2 dispatch
- Atlas feeds weekly-architecture-audit with per-system context (Step 2.5: Load Atlas Context)
- `file-index.md` feeds update-docs new-system detection (changed files not in index → flag for PM)
- **All dispatch prompts use templates from `agent-prompts.md` — verbatim, with blanks filled in.** The templates are tested infrastructure, not suggestions. Writing custom prompts discards guardrails that prevent known failure modes (Haiku confabulation, grade confabulation on first pass, Opus system-skipping). If a template genuinely doesn't fit, say so explicitly before deviating.
