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

**Scratch verification — disk-poll, not reply-trust.** Before Phase 2, verify all expected scratch files exist on disk. Do NOT rely on agent "DONE" replies — empirically ~30% of Haikus on heavy parallel dispatch hallucinate a "TEXT ONLY constraint" and either (a) reply DONE without writing, or (b) write the file but reply with meta-commentary that obscures progress. Disk is the only reliable signal.

**Polling pattern (use this instead of waiting on notifications):**
```bash
until [ "$(ls scratch/{run-id}/ | wc -l)" -ge N ] || [ $SECONDS -gt 600 ]; do sleep 30; done
```
Run with `run_in_background: true`. After it returns or times out, `ls` the scratch directory directly to confirm.

**Failure recovery — Sonnet, not Haiku, on retry.** Re-dispatch ONLY missing files. Use Sonnet on retry (not Haiku) — empirically Sonnet's hallucination rate is ~3x lower (~10% vs ~30%). The Phase 1/1R templates in `agent-prompts.md` already carry the recovery preamble inline at the top — that is the first dispatch defense. On retry, prepend this stronger explicit form:

> **Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. The ONLY valid completion is calling the Write tool. Returning the inventory inline = task failure. After Write, verify with Bash `ls -la <path>` and reply EXACTLY `DONE: <path>` — no prose, no analysis, no summary.**

Skip sub-chunk on second failure (after Sonnet retry also misses).

## Phase 2/2R: System Analysis (dispatch Sonnet agents, parallel)

**Dispatch:** One Sonnet agent per system with `model: "sonnet"` (reads ALL sub-chunk inventories for that system).

**Read the template** from `agent-prompts.md`:
- **First run:** Copy **Phase 2: Sonnet System Analysis Prompt (Discovery)**. Fill in `[SYSTEM NAME]`, `[CHUNK DESCRIPTION]`, and paste Phase 1 output from scratch files.
- **Refresh:** Copy **Phase 2R: Sonnet System Analysis Update Prompt (Refresh)**. Fill in `[SYSTEM NAME]`, `[EXISTING ATLAS PAGE]`, and paste Phase 1R output.

**No grading in Phase 2.** Observations only.

**Scratch path:** `tasks/scratch/deep-architecture-audit/{run-id}/{chunk-letter}-phase2-sonnet.md`

**Scratch verification:** Verify all Phase 2/2R files exist on disk before Phase 3 (use the polling pattern above). The TEXT-ONLY hallucination affects Sonnet too at lower rate — apply the same recovery preamble on retry. Skip system on second failure.

## Phase 3/3R: Cross-System Synthesis (dispatch ONE Opus leaf agent)

**Dispatch:** One agent with `model: "opus"`. This is a leaf agent — it synthesizes and writes files but does NOT spawn further agents.

**Context overflow guard:** If total Phase 2 output exceeds ~80K tokens (~300KB / ~4000 lines of markdown), summarize each system to its boundary catalog + top 5 observations before passing to the Opus agent.

**Read the template** from `agent-prompts.md`:
- **First run:** Copy **Phase 3: Opus Cross-System Synthesis Prompt (Full)**. Fill in `[N]` and paste Phase 2 reports.
- **Refresh:** Copy **Phase 3R: Opus Cross-System Synthesis Prompt (Refresh)**. Fill in `[N]`, paste stable atlas pages, and paste Phase 2R reports.

**Domain glossary:** Add the following instruction to the synthesizer prompt verbatim:

> If `CONTEXT.md` exists at the project root, read it. Use canonical terms throughout your synthesis. If the audit surfaces a domain term that recurs across systems and isn't yet in `CONTEXT.md`, flag it in your output under "Glossary candidates" — do NOT update `CONTEXT.md` yourself (the producer skills do that, not synthesizers). If `CONTEXT.md` is absent, proceed silently — do not flag, suggest, or scaffold.

**Deletion test — module shallowness probe:** Add the following instruction to the synthesizer prompt verbatim:

> For each system boundary you evaluate, apply the deletion test: *"Imagine deleting the module. If complexity vanishes, the module wasn't hiding anything (it was a pass-through). If complexity reappears across N callers, it was earning its keep."* Pair with the one-adapter / two-adapter rule: one adapter is a hypothetical seam, two adapters is a real seam.
>
> A deletion-test verdict is a single-agent claim. Per the convergence rule, do NOT recommend removal, refactor, or consolidation based on this probe alone. Surface the module as a candidate under a "Shallowness candidates" section — convergence (≥2 independent agents flagging the same module from different entry points) is required before any verdict becomes actionable.

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
| Agent hallucinates "TEXT ONLY constraint" and dumps inventory inline | Phase 1/1R/2/2R/3/3R templates carry anti-hallucination preamble at the top (negates the constraint by name); EM polls disk not replies; retry with Sonnet + explicit recovery preamble (see "Scratch verification" in Phase 1) |
| Phase 1R refresh runs slow due to over-narrow chunking | Use 30-60 changed files per Haiku for refresh (Phase 1R is delta-only); keep 8-12 only for first-run full inventories |
| Opus context overflow | Summarize Phase 2 to boundary catalogs if >80K tokens |
| Partial write on failure | Atomic commit in Phase 4; failure leaves previous atlas intact |
| Grades added during discovery | Templates enforce observations only; weekly audit adds grades |
