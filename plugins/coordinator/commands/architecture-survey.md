---
name: architecture-survey
description: Bootstrap or refresh the architecture atlas via multi-phase agent pipeline (Haiku scouts → Sonnet analysts → Opus synthesizer)
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: "[--refresh]"
---

# Architecture Survey — Deep System Discovery

Produce a comprehensive **architecture atlas** — narrative system descriptions, philosophy-versus-reality assessments, ASCII flow diagrams, cross-system dependency matrices, and per-system observations. The atlas is a persistent artifact that weekly audits maintain incrementally.

**RAG-era focus:** When project-RAG is present (any `mcp__*project-rag*` tool available), the atlas's value lies in **narrative and judgment** — "does the philosophy match reality?" — not in exhaustive file enumeration, which RAG owns. On RAG repos, Phase 1 haiku inventory still runs but file-level mapping output is summarized rather than enumerated. The full Phase 3 synthesis produces narrative-first system descriptions. On non-RAG repos, behavior is unchanged.

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

Auto-detection: check for `docs/architecture/systems-index.md`. If it exists and `--refresh` wasn't passed, ask the PM: "Atlas already exists. Did you mean `--refresh`?"

Announce: "I'm running `/architecture-survey` to [bootstrap / refresh] the architecture atlas."

## Atlas Directory Structure

**Location: `docs/architecture/`** — the atlas is an evergreen reference artifact (narrative system descriptions, dependency matrices, connectivity diagrams), not work-in-flight. It belongs alongside `docs/wiki/` and `docs/decisions/`, not under `tasks/` (which holds handoffs, backlogs, scratch). Audit run scratch DOES live under `tasks/scratch/deep-architecture-survey/{run-id}/` — that's transient pipeline state, distinct from the persistent atlas output.

```
docs/architecture/
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
   - Check for `docs/architecture/systems-index.md`
   - **Not found:** First run → step 3
   - **Found:** Refresh → step 2.5

2.5. **Calibrate scope — targeted refactor audit vs atlas refresh:**

   Discriminate on PM phrasing before entering the Phase 1/2/3 fan-out:

   - **Targeted refactor audit** — PM names ONE system OR cites a specific architectural concern (e.g. "audit the executor", "I want to look at the ingestion pipeline"). Mode is a single-system spike:
     - Skip Phases 1R/2R fan-out across all systems entirely.
     - Dispatch ONE Sonnet analyst against the named system (read its existing atlas page + git-diff since last mapped date for delta context).
     - Dispatch ONE optional Opus synthesis pass ONLY if the named system has ≥2 cross-system dependencies flagged in `connectivity-matrix.md` — skip Opus otherwise.
     - Wall-clock ~15-30 min. Does NOT update `systems-index.md` Last-mapped dates for sibling systems.
     - After the Sonnet analyst returns, update ONLY the named system's page (`systems/{name}.md`) and its row in `systems-index.md`. Atlas-wide artifacts (`cross-system-map.md`, `connectivity-matrix.md`, `file-index.md`) are not regenerated.
     - Report to PM with the targeted-audit variant of the Phase 4 template (system name, key findings, updated date).

   - **Atlas refresh** — PM names no specific system, OR names ≥3 systems, OR invokes `--refresh` without further scope. Continue to step 4 (Refresh — identify churned systems). Existing Phase 1R/2R/3R flow applies across all churned systems.

   - **First run (BOOTSTRAP)** — no atlas exists. Step 2 already routed here via "Not found → step 3". Unchanged.

3. **First run — define system boundaries and sub-chunks:**
   - Derive 4-8 system boundaries from repo map + directory structure
   - Each file assigned to exactly ONE system. No overlaps.
   - Sub-chunk systems with >12 files into 8-12 file groups by concern. Label: `{system}-A`, `{system}-B`, etc.
   - Write focus questions for each chunk
   - **Generate run ID** — `YYYY-MM-DD-HHhMM`. Create: `tasks/scratch/deep-architecture-survey/{run-id}/`
   - **Output:** Chunk table (system, sub-chunks, file count, mode: full, focus questions)

4. **Refresh — identify churned systems:**
   _If the PM asked for a targeted single-system audit, jump to the targeted-audit branch in step 2.5 instead — do not enumerate churned systems._
   - Read `systems-index.md` for existing systems and `Last mapped` dates
   - Diff git activity since each system's last mapped date:
     ```bash
     git log --since="<last-mapped-date>" --name-only --pretty=format: -- <system-dirs> | sort -u
     ```
   - Changed files → `mode: refresh`. No changes → `mode: stable` (carry forward, skip Phases 1-2)
   - Apply sub-chunking to churned systems
   - **Emergence detection (chunk K) — heavy-churn partial-bootstrap guard:** Before generating the run ID, run a tree-wide "what's NOT in any system" pass. The key is to compute both lists at **file-path granularity** — comparing changed file paths against catalogued *directory prefixes* is a category error (a file path never equals a directory line), so it is the catalogued *files* that must be differenced, not the directories.
     ```bash
     # 1. All files changed across the tree since the oldest system's Last-mapped date:
     git log --since="<oldest-last-mapped-date>" --name-only --pretty=format: \
       | sed '/^$/d' | LC_ALL=C sort -u > churned-all.txt
     # 2. The subset of those files that fall under a catalogued system directory.
     #    Scope the SAME diff to the union of all catalogued system dirs from systems-index.md
     #    (<system-dirs> is the space-separated list of every system's mapped directories):
     git log --since="<oldest-last-mapped-date>" --name-only --pretty=format: -- <system-dirs> \
       | sed '/^$/d' | LC_ALL=C sort -u > catalogued.txt
     # 3. Emergent = changed-but-uncatalogued, at file granularity (no sort/collation footgun):
     grep -vxF -f catalogued.txt churned-all.txt > emergent.txt
     ```
     `emergent.txt` is the **emergent set** — changed files that belong to no existing system. Both files are pulled from the *same* `git log` diff (one tree-wide, one scoped to `-- <system-dirs>`), so they are at identical file-path granularity; `grep -vxF` does a literal full-line difference with no sort/collation precondition. (If you prefer `comm -23` instead of `grep -vxF`, both inputs MUST be `LC_ALL=C sort`'d on the same collation or comm silently emits garbage — `grep -vxF` sidesteps that and is the drafted default.)

     **Pre-filter emergent.txt against source dirs before chunk-K.** On doc-heavy repos, `tasks/`, `docs/`, `archive/`, and similar meta-directories contribute large volumes of churn that is not architectural. Before applying the chunk-K threshold test, filter `emergent.txt` to retain only files under catalogued **source directories** (e.g. `src/`, `Source/`, `lib/`, `plugin/`, `Content/` for UE repos) — exclude pure-documentation and archival directories. `tasks/`/`docs/`/`archive/` churn is not "uncatalogued architecture"; including it inflates the emergent set and triggers false chunk-K passes on every `/distill` or lesson-learn run. *2026-05-28, claude-unreal-holodeck.*

     **Cross-check emergent candidates against HEAD before declaring drift.** `git log --name-only` lists both additions AND deletions. A file that appears in `churned-all.txt` but was deleted at HEAD is not uncatalogued architecture — it is a deletion record. After computing `emergent.txt`, filter out any path that does not exist at HEAD: `git ls-files -- $(cat emergent.txt) > head-present.txt` and work from `head-present.txt` in the chunk-K decision and dispatch. Declaring a deleted file "emergent" triggers a spurious Haiku inventory of a non-existent surface. *2026-05-28, claude-unreal-holodeck.*

     Fire the chunk-K pass when **either** condition holds:
     - `emergent.txt` is non-empty (there exist changed files outside every catalogued system), **OR**
     - total churned files (`wc -l < churned-all.txt`) exceed 50% of the current catalogued file count (`wc -l < catalogued.txt`) — a refresh on a tree this churned is a partial bootstrap, not a delta. **Note the time windows:** the numerator (churn) is measured since the *oldest* system's Last-mapped date, while the denominator (catalogued file count) is the *current* catalogued total — so this threshold measures accumulated churn across the whole mapping-age spread, not churn since the last full audit. See the OPEN QUESTION in § Integration escalations; if the EM elects the "since last full audit" semantics, replace `<oldest-last-mapped-date>` with the `Last full audit` clock from `tasks/health-ledger.md`.

     When fired, add a synthetic **chunk K** ("emergent / uncatalogued") to the Phase 1 fan-out: sub-chunk it like a first-run system (8–12 files per Haiku) and **dispatch it with the first-run Phase 1 (full-inventory) Haiku template from agent-prompts.md, NOT the Phase 1R delta template** — emergent files have no prior atlas entry to delta against, so the 1R delta template would mis-handle them. The Opus synthesizer in Phase 3 then assigns these files to existing systems or proposes new system boundaries. Do NOT silently drop the emergent set — emergent files left uninventoried are the partial-bootstrap failure this guard exists to prevent.
   - **Generate run ID** and create scratch directory
   - **Output:** Chunk table (system, mode: refresh/stable, changed files)

## Phase 1/1R: Function-Level Inventory (dispatch Haiku agents, parallel)

**Dispatch:** One Haiku agent per sub-chunk with `model: "haiku"`.

**Read the template:** Open `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/agent-prompts.md`. Copy the relevant template verbatim:
- **First run:** Copy **Phase 1: Haiku Function-Level Inventory Prompt**. Fill in: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[LIST OF DIRECTORIES/FILES]`, `[SCRATCH_PATH]`.
- **Refresh:** Copy **Phase 1R: Haiku Delta Inventory Prompt (Refresh)**. Fill in: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[CHANGED FILES LIST]`, `[EXISTING ATLAS ENTRY]`, `[SCRATCH_PATH]`.

**Do NOT write a custom prompt** — the template's guardrails prevent Haiku from confabulating relationships.

**Scratch path:** `tasks/scratch/deep-architecture-survey/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md`

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

**Scratch path:** `tasks/scratch/deep-architecture-survey/{run-id}/{chunk-letter}-phase2-sonnet.md`

**Scratch verification:** Verify all Phase 2/2R files exist on disk before Phase 3 (use the polling pattern above). The TEXT-ONLY hallucination affects Sonnet too at lower rate — apply the same recovery preamble on retry. Skip system on second failure.

## Phase 3/3R: Cross-System Synthesis (dispatch ONE Opus leaf agent)

**Dispatch:** One agent with `model: "opus"`. This is a leaf agent — it synthesizes and writes files but does NOT spawn further agents.

**Context overflow guard:** If total Phase 2 output exceeds ~80K tokens (~300KB / ~4000 lines of markdown), summarize each system to its boundary catalog + top 5 observations before passing to the Opus agent.

**Read the template** from `agent-prompts.md`:
- **First run:** Copy **Phase 3: Opus Cross-System Synthesis Prompt (Full)**. Fill in `[N]` and paste Phase 2 reports.
- **Refresh:** Copy **Phase 3R: Opus Cross-System Synthesis Prompt (Refresh)**. Fill in `[N]`, paste stable atlas pages, and paste Phase 2R reports.

**RAG-era synthesis instruction (add to Opus prompt when project-RAG is present):**

> Project-RAG is available on this repo and owns file-level structural mapping. Your atlas is the narrative layer — describe WHAT each system does, WHY it exists, and HOW its design philosophy plays out in practice. You do NOT need to enumerate every file; instead, describe the boundaries, roles, and cross-cutting concerns in prose. The `file-index.md` artifact should still be produced (the integrity-check skill needs it), but keep it summary-level: directory-to-system mappings are sufficient, not individual files. The goal is a narrative that survives a re-read by a future EM and answers "does the philosophy still match reality?" — not "does every file have a system assignment?"

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

**No grades in Phase 3.** Weekly-architecture-survey adds grades incrementally.

## Phase 4: Integration and Report (YOU do this)

**Out-of-scope actions for all dispatched agents in this pipeline:** DO NOT run `gh pr create`, `gh pr merge`, `git push origin main`, `gh release create`, or any `gh` command that mutates GitHub state beyond pushing the current branch. DO NOT commit to `main` directly. If you find yourself reaching for a merge, STOP and surface the question to the EM in your final reply. The EM merges via `/merge-to-main`; architecture-survey agents do not.

1. **Review atlas for completeness:**
   - Every system has a file in `systems/`
   - `systems-index.md` has a row for every system
   - `cross-system-map.md`, `connectivity-matrix.md`, `file-index.md` present
   - All YAML frontmatter has required fields

2. **Flag-drift-from-RAG check (when project-RAG is present):**
   - Call `project_subsystem_profile` (or equivalent `mcp__*project-rag*` tool) to retrieve the project-RAG subsystem list.
   - Compare against the systems named in `docs/architecture/systems-index.md`.
   - Flag any mismatches: systems named in the atlas that don't appear in RAG's profile (may be renamed or merged), or RAG-known subsystems not mentioned in the atlas (may be new systems that emerged since last audit).
   - Record mismatches in the Phase 4 report under "RAG drift". These are suggestions, not blockers.
   - If project-RAG is absent, skip this step silently.

3. **Quarterly narrative-drift reminder (per the Data Science Reviewer F7):**
   - Check each system's `last_mapped` date in `systems-index.md`. For any system >90 days since last mapped, note it in the report: "Narrative drift risk: [system] mapped [date]. Recommend a re-read sweep — narrative atlases drift silently when systems reorganize."

4. **Write the `Last full audit` clock (full-pass only):** A genuine full survey pass (first run / `--refresh`) is the ONLY surface that writes `Last full audit` in `tasks/health-ledger.md`. Update (or add) the header line:
   ```
   **Last full audit:** YYYY-MM-DD
   ```
   This is the clock the workstream-start / survey-staleness nudge reads. **Do NOT write it on the targeted single-system refresh path** (Phase 1 § targeted refresh) — that path updates one system page only and is not a full pass; writing `Last full audit` there would falsely mark the whole atlas fresh. The targeted *audit* (`/architecture-audit`) writes the separate `Last targeted audit` clock, never this one. (Clock-separation rationale: `docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md` § Strand 3b.)

5. **Atomic commit:**
   ```bash
   git add docs/architecture/ tasks/health-ledger.md
   git commit -m "deep-architecture-survey: [first run|refresh] — [N] systems mapped; Last full audit bumped"
   ```

6. **Calculate rotation target:** Score each system using recent roadmap activity from the completion log plus structural signals. Run:

   ```bash
   bin/query-completions --since "30d" --where "nature=roadmap" --format json \
     | jq -r '.[] | .subsystem // "unknown"' | sort | uniq -c | sort -rn
   ```

   For each system, sum `loe.tshirt` weights across its `nature: roadmap` entries (XS=1, S=2, M=4, L=8, XL=16). Combine with structural signals: highest cross-system connectivity score (`connectivity-matrix.md`) and oldest `Last mapped` date. Systems with high recent roadmap LoE + high connectivity + oldest mapping rank first.

   If `query-completions` returns zero rows, fall back to connectivity + oldest `Last mapped` only.

   Rationale: commit churn doesn't distinguish doctrine edits from refactors from feature work; `nature: roadmap` with LoE weighting does — suggested starting point for weekly-architecture-audit.

7. **Report to PM:**
   ```markdown
   ## Architecture Survey Complete

   **Mode:** [first run / refresh]
   **Systems mapped:** [N] ([list])
   **Key findings:** [coupling hotspots, boundary patterns, notable design choices]
   **RAG drift:** [N mismatches: list / none detected / RAG absent — check skipped]
   **Narrative drift risk:** [systems > 90 days / all current]
   **Suggested rotation target:** [system name] (highest connectivity / oldest mapping)
   **Atlas location:** docs/architecture/
   ```

8. **Clean scratch:** `rm -rf tasks/scratch/deep-architecture-survey/{run-id}/`
   Only delete after commit succeeds. On Phase 2/3 failure, scratch contains earlier phases for recovery.

## Cost Profile

| Scenario | Haiku | Sonnet | Opus | Wall-Clock |
|----------|-------|--------|------|------------|
| Targeted refactor audit (1 system) | 0 | 1 | 0-1 | ~15-30 min |
| First run, 6 systems (≤12 files each) | 6 | 6 | 1 | ~25-35 min |
| First run, 8 systems (≤12 files each) | 8 | 8 | 1 | ~35-45 min |
| First run, large system (59 files → 5-6 sub-chunks) | 10-14 | 6-8 | 1 | ~40-55 min |
| Refresh, 2 churned | 2 | 2 | 1 | ~15-20 min |
| Refresh, 5 churned | 5 | 5 | 1 | ~25-30 min |

## Failure Modes

| Failure | Prevention |
|---------|------------|
| Atlas refresh dispatched when targeted audit was the right shape | Phase 0 step 2.5 calibrates scope before chunking |
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
