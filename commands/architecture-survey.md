---
name: architecture-survey
description: "Build or refresh the architecture atlas via scout, analyst, synth."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: "[--refresh]"
---

# Architecture Survey — Deep System Discovery

Produce a comprehensive **architecture atlas** — narrative system descriptions, philosophy-versus-reality assessments, ASCII flow diagrams, cross-system dependency matrices, and per-system observations. The atlas is a persistent artifact that weekly audits maintain incrementally.

**Deterministic-extraction rebuild.** Structural extraction — file inventory, LOC/language split, chunk manifests, churn/emergent-set detection, static call-graph edges — is **the deterministic `cartography.*` op output** (per `${CLAUDE_PLUGIN_ROOT}/docs/contracts/arch-engine-scripts.md`), not agentic mechanical work. The mechanical Phase-1 Haiku inventory this command historically ran **collapses entirely**: on a repo where the cartography ops fire (see the Phase-0.5 consume-gate, below), Phase 1 shrinks from full-inventory to *annotate the precomputed table + mark `[UNKNOWN]`/dynamic (`register_op`) edges the static graph categorically cannot resolve*. Agents spend their budget ONLY on judgment — philosophy-vs-reality assessment, migration complexity, boundary evaluation over a pre-computed catalog — never on mechanically re-deriving substrate a deterministic op already emits. This does not change on RAG-present repos, where the pre-existing narrative-first posture (below) already deprioritized exhaustive inventory; it changes the RAG-absent path, which previously ran full agentic inventory unconditionally and now consumes the cartography substrate instead.

**RAG-era focus:** When project-RAG is present (any `mcp__*project-rag*` tool available), the atlas's value lies in **narrative and judgment** — "does the philosophy match reality?" — not in exhaustive file enumeration, which RAG owns. On RAG repos, Phase 1 haiku inventory still runs but file-level mapping output is summarized rather than enumerated. The full Phase 3 synthesis produces narrative-first system descriptions. On non-RAG repos, extraction is claude-klabauter-reliant per above — behavior is no longer "full agentic inventory," but a Phase-0.5 consume-then-annotate pass over claude-klabauter's `cartography.*` output.

**This command occupies your context for ~25-90 min (up to ~90 min on the Hybrid tier — see § Cost Profile). It is not background work.**

**Two modes:**
- **First run (BOOTSTRAP):** No atlas exists. Full discovery and mapping of all systems. No grades — observations only.
- **Refresh:** Atlas exists. Identifies churned systems via git, remaps only those, carries stable systems forward. Substantially cheaper.

**Core principle:** Each model tier does what it's best at. Claude-Klabauter's `cartography.*` ops do the deterministic extraction (structure, churn, edges) unconditionally, at engine cost, not agent budget. Haiku annotates the precomputed table and flags what the static graph can't resolve (cheap, parallel — judgment, not mechanical re-derivation). Sonnet analyzes and diagrams (analytical depth). Opus synthesizes cross-system connectivity (highest judgment). Don't waste expensive models — or agent budget generally — on work a deterministic op already did.

**Orchestration vehicle.** The Phase-1/2/3 pipeline runs as ONE background Workflow (`coordinator/pipelines/deep-architecture-survey/survey.workflow.js`) unconditionally — not an optional escalation for "large enough" runs. The Workflow owns dispatch, polling, condensation, and synthesis so the EM's own context never holds the wave map — that is the vehicle's rationale — and it carries the shared Workflow-resume primitive (`resumeFromRunId`) that lets a throttle-wiped wave re-run only its failed agents rather than restarting the whole phase.

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

**Location: `docs/architecture/`** — the atlas is an evergreen reference artifact (narrative system descriptions, dependency matrices, connectivity diagrams), not work-in-flight. It belongs alongside `docs/wiki/` and `docs/decisions/`, not under `tasks/` (which holds handoffs, backlogs, scratch). Audit run scratch DOES live under `state/scratch/deep-architecture-survey/{run-id}/` — that's transient pipeline state, distinct from the persistent atlas output.

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
Phase 0 (YOU) → Phase 0.5 (claude-klabauter consume-gate) → Phase 1 (Haiku, parallel) → [wait] → Phase 2 (Sonnet, parallel) → [wait] → Phase 3 (Opus leaf) → [wait] → Phase 4 (YOU)
```

**Phases MUST run sequentially.** Each phase's output shapes the next phase's prompts. **Phase 0.5 — the consume-gate** — sits between scope/chunking and the Phase-1 fan-out: when claude-klabauter's `cartography.*` ops are available and the RAG-absent predicate fires (`${CLAUDE_PLUGIN_ROOT}/docs/contracts/arch-engine-scripts.md`), the survey calls them for census/chunk/callgraph/churn substrate and Phase 1 downgrades to annotate-only. The Workflow (see below) drives all of Phase 0.5 through Phase 3 as a single background script — the EM never hand-orchestrates the wave map.

**The Phase-0.5 invocation recipe — VERBATIM, transcribed character-for-character from `cartographyOpBriefFor` in `survey.workflow.js` (the source of truth; do not retype from memory):**

```
cd "${CLAUDE_KLABAUTER_ROOT}" && python3 -m coordinator_core.invoke ${op} --params-file - --bare <<'JSON'
${paramsJson}
JSON
```

The heredoc delimiter MUST stay quoted (`<<'JSON'`) — an unquoted delimiter shell-interpolates the payload. `--repo` is deliberately NOT passed: it is inert for cartography ops (scope `"none"`, so `_resolve_repo_root` never fires); targeting is carried entirely by the `target_root` wire param instead. Exit codes: 0 success; 1 generic/transient op-level error, safe to report as a normal failure; **2 `STRUCTURAL_PIN_ERROR` — a structurally-wedged, NON-TRANSIENT contract-pin failure, must not be retried.**

## Phase 0: Scope and Chunking (~5 min, YOU do this)

1. **Read orientation artifacts:** `DIRECTORY.md`. If absent, proceed silently — do not flag, suggest, or scaffold. (`.claude/repomap.md` is retired as a survey orientation input — see the retirement note under § Phase 1/1R below; this was an ad-hoc, ungated consumption, not one of the repomap gating contract's three gated callers.)

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

2.75. **Scale tier — file-count threshold (non-RAG repos; RAG-present repos already get the narrative treatment per § RAG-era focus above):**

   The RAG-present/absent branch (§ RAG-era focus) is not the only scale axis — a large non-RAG repo needs a documented path too. Before entering step 3's system-boundary derivation, count total source files in scope (the same count that later feeds `arch-census`/C-integrate chunking) and select a tier:

   | Tier | File-count threshold | Behavior |
   |------|----------------------|----------|
   | **Narrative** | RAG present (any file count) — see § RAG-era focus | Phase 1 Haiku inventory still runs; file-level mapping is summarized, not enumerated. Phase 3 produces narrative-first descriptions. |
   | **Full** | Non-RAG, ≤~200 source files | Standard first-run flow unchanged: derive 4-8 system boundaries (step 3), sub-chunk any system >12 files into 8-12 file groups, full per-file Phase 1 inventory across every system. |
   | **Hybrid** | Non-RAG, >~200 source files (e.g. DoE-claude at 1859 source files — ~30x the "large system = 59 files" envelope in § Cost Profile) | Full per-file Phase 1 inventory does not scale linearly past this point — dispatching 1859/10 ≈ 186 Haiku sub-chunks in one run is a token-budget and wall-clock failure, not a merely-slow one. Apply BOTH: **(a) directory-level pre-aggregation** — derive system boundaries from top-level/second-level directory structure first (same as step 3) but treat any directory >150 files as a candidate for its OWN synthetic system rather than folding it into a sibling, so no single Phase 1 sub-chunk wave exceeds ~15-20 dispatches; **(b) narrative-summarization within each system** — once a system's Phase 1 sub-chunks return, Phase 2 Sonnet analysis is instructed (same template wording as the RAG narrative mode) to describe boundaries/roles/cross-cutting concerns in prose rather than enumerate every symbol, even though no RAG index exists to fall back on. This tier exists because "non-RAG" was silently assumed synonymous with "small enough to fully enumerate" — untrue at this scale; Phase 0 must not invent this decision live on every oversized run. |

   Record the selected tier in the Phase 0 chunk-table output (step 3's "Output" line) so Phase 2/3 dispatch prompts carry the correct mode. The ~200-file narrative/hybrid boundary and the ~150-file per-directory hybrid sub-boundary are calibration heuristics, not hard cutoffs — an EM operating near either boundary should reason about total Haiku-dispatch count (target ≤20 per wave) rather than treating the file count alone as gospel.

   **"Total source files in scope" is defined precisely, not left to eyeball:** on the cartography path it is the post-consume-gate in-scope source count, `counts.bucketed_total` — the same field the Phase 4 report cites (see § Phase 4 step 7). Five candidate numbers straddled the ~200-file boundary on one real run before this definition landed; count `counts.bucketed_total`, not a raw `find`/`git ls-files` tally, a directory listing, or any other approximation.

   **The "≤20 per wave" and "~150-file per-directory" numbers above are the current MANUAL derivation**, not a mechanically-computed value — an EM had to derive both live, by hand, on a 1246-non-test-file run before this doc named them. They are revisable once the cartography ops' scope-param work (in flight, engine-side) lands a mechanical path; this doc fix is independent of that work and does not wait on it.

   **Classification-boundary note.** The producer op backing this table (`cartography.chunk_table`) emits only matched source files into caller-supplied `{system: [prefix]}` buckets; non-matching files land in `unbucketed`. Classification of which files belong to which system is **producer-side** — the maximal-split posture keeps deterministic extraction engine-side and reserves judgment (which files map to which system) for the caller — so the caller supplies boundary prefixes only; it does not derive or apply classification itself.

3. **First run — define system boundaries and sub-chunks:**
   - Derive 4-8 system boundaries from repo map + directory structure
   - Each file assigned to exactly ONE system. No overlaps.
   - Sub-chunk systems with >12 files into 8-12 file groups by concern. Label: `{system}-A`, `{system}-B`, etc.
   - Write focus questions for each chunk
   - **Generate run ID** — `YYYY-MM-DD-HHhMM`. Create: `state/scratch/deep-architecture-survey/{run-id}/`
   - **Output:** Chunk table (system, sub-chunks, file count, mode: full, focus questions)

4. **Refresh — identify churned systems:**
   _If the PM asked for a targeted single-system audit, jump to the targeted-audit branch in step 2.5 instead — do not enumerate churned systems._
   - Read `systems-index.md` for existing systems and `Last mapped` dates
   - Diff git activity since each system's last mapped date — this is the claude-klabauter-reliant `cartography.churn` op's job (see the Emergence detection subsection below for the full Phase-0.5 consume-gate contract and the documented agentic-path fallback); do not hand-run `git log`/`grep` inline here, consume the op's output.
   - Changed files → `mode: refresh`. No changes → `mode: stable` (carry forward, skip Phases 1-2)
   - Apply sub-chunking to churned systems
   - **Emergence detection (chunk K) — heavy-churn partial-bootstrap guard, engine-reliant.** Before generating the run ID, the survey needs a tree-wide "what's NOT in any system" pass — the emergent set. This is computed by the engine's tested `cartography.churn` op (`arch-churn` lane, `${CLAUDE_PLUGIN_ROOT}/docs/contracts/arch-engine-scripts.md`): the op takes `target_root`, `since` (the oldest catalogued system's last-mapped date), `system_dirs` (the catalogued system directory list), and an optional `excluded_dirs` prefilter (defaults to `docs/`, `tasks/`, `archive/`), and returns `{"emergent": [...], "excluded_by_prefilter": [...], "deleted_at_head": [...]}` as tested, reusable substrate — collation-safe, prefiltered, and deleted-at-HEAD-checked by construction, not by a doc-body mitigation paragraph a future editor has to remember to keep in sync. Do not hand-author inline bash for this pass (`git log`/`grep -vxF` diffing collates unsafely, produces spurious "emergent" hits on files deleted-at-HEAD, and lets doc/tasks/archive churn inflate the emergent set on every `/distill` run) — consume the op's output instead.

     **The survey consumes the op's output; it does not run inline `git log` to compute it.** (Wiring the Phase-0.5 call itself — the Workflow-side consume-gate that invokes `cartography.churn` and feeds its JSON into this step — is the sibling `C-integrate` chunk's responsibility, not this doc; this doc's contract is simply: *the emergent set comes from `arch-churn`'s output, never from hand-authored `git log`/`grep` in this skill body.*) The op explicitly does NOT apply the chunk-K threshold decision itself (see the contract's "Decision-application boundary" invariant) — that policy judgment stays here:

     Fire the chunk-K pass when **either** condition holds:
     - the op's `emergent` list is non-empty (there exist changed files outside every catalogued system), **OR**
     - total churned files exceed 50% of the current catalogued file count — a refresh on a tree this churned is a partial bootstrap, not a delta. **Note the time windows:** the numerator (churn) is measured since the *oldest* system's Last-mapped date, while the denominator (catalogued file count) is the *current* catalogued total — so this threshold measures accumulated churn across the whole mapping-age spread, not churn since the last full audit. See the OPEN QUESTION in § Integration escalations; if the EM elects the "since last full audit" semantics, pass the `Last full audit` clock from `state/health-ledger.md` as `since` instead of the oldest system's last-mapped date.

     **Above ~75% churn (or >2x catalogued growth), ESCALATE instead of firing chunk K.** A refresh this heavily churned is no longer a delta problem chunk K can absorb — it needs a re-bootstrap, not a bigger emergent-set sub-chunk. Surface the recommendation to the PM rather than proceeding through the normal refresh flow; whether to actually re-bootstrap stays a direction-class call for the PM, but recommending it is mechanism and belongs here. **Provenance:** 75% is a first-cut value derived from a single observed run that fired at 93% churn, where the EM had to step outside this command by hand to reach the right outcome — it is not a measured constant. Revisit after the next two heavy-churn refreshes; a later reader should not inherit 75% as settled.

     **Agentic-path fallback if claude-klabauter declines `arch-churn`.** Revert to the retired inline bash verbatim — it is the documented fallback, not deleted knowledge, but reverting drops the op's tested mitigation coverage (see the contract's costed-fallback table) and re-introduces the toil of a hand-run diff on every refresh.

     When fired, add a synthetic **chunk K** ("emergent / uncatalogued") to the Phase 1 fan-out: sub-chunk it like a first-run system (8–12 files per Haiku) and **dispatch it with the first-run Phase 1 (full-inventory) Haiku template from agent-prompts.md, NOT the Phase 1R delta template** — emergent files have no prior atlas entry to delta against, so the 1R delta template would mis-handle them. The Opus synthesizer in Phase 3 then assigns these files to existing systems or proposes new system boundaries. Do NOT silently drop the emergent set — emergent files left uninventoried are the partial-bootstrap failure this guard exists to prevent.
   - **Generate run ID** and create scratch directory
   - **Output:** Chunk table (system, mode: refresh/stable, changed files)

## Phase 1/1R: Function-Level Inventory (dispatch Haiku agents, parallel)

**Engine consume-gate collapses this phase toward zero.** When Phase 0.5 fires the engine's `cartography.*` ops (per `${CLAUDE_PLUGIN_ROOT}/docs/contracts/arch-engine-scripts.md`), Phase 1 is no longer a full mechanical inventory — it is an **annotate-the-precomputed-table** pass: Haiku receives `arch-census`'s file/LOC/language substrate and `arch-callgraph`'s static edge graph already computed, and spends its budget only on (a) marking `[UNKNOWN]`/dynamic (`register_op`-style) edges the static graph is categorically unable to resolve, and (b) any judgment call the deterministic op explicitly does not make (see the op contract's "Decision-application boundary" invariants). Full mechanical inventory — reading every file, hand-deriving LOC, tracing every call edge — is the **agentic-path fallback** for when the engine declines a given op, not the default path. The templates below still apply on the fallback path unchanged; on the consume-gate path, the Phase-0.5 wiring (owned by the C-integrate chunk of this pipeline, not this doc) supplies the precomputed substrate the annotate-only prompt consumes.

**Repomap retirement (finding #4/#11/#13, review: the Director of Engineering finding 5).** This command previously read `.claude/repomap.md` as a Phase-0 orientation artifact (see the old Phase 0 step 1). That consumption was **ad-hoc** — it was never one of the repomap gating contract's three gated callers (`update-docs` / `enrich-and-review` / the project-orientation hook), so it never went through `check-rag-state.py`'s three-tier gate. Retiring it removes an ungated ad-hoc consumption of the repomap artifact; **the gating contract's three-caller enumeration is unaffected** — those three callers are untouched by this change. Do not read this as "the survey dropped out of the caller enumeration" — it was never in it. The survey's structural orientation need is now served by claude-klabauter's `cartography.*` substrate (Phase 0.5) or, on RAG-present repos, by `mcp__*project-rag*` directly.

**Dispatch:** One Haiku agent per sub-chunk with `model: "haiku"`.

**Read the template:** Open `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/agent-prompts.md`. Copy the relevant template verbatim:
- **First run:** Copy **Phase 1: Haiku Function-Level Inventory Prompt**. Fill in: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[LIST OF DIRECTORIES/FILES]`, `[SCRATCH_PATH]`.
- **Refresh:** Copy **Phase 1R: Haiku Delta Inventory Prompt (Refresh)**. Fill in: `[CHUNK LETTER]`, `[SYSTEM NAME]`, `[SUB-CHUNK LABEL]`, `[CHANGED FILES LIST]`, `[EXISTING ATLAS ENTRY]`, `[SCRATCH_PATH]`.

**Do NOT write a custom prompt** — the template's guardrails prevent Haiku from confabulating relationships.

**Scratch path:** `state/scratch/deep-architecture-survey/{run-id}/{chunk-letter}{sub-chunk}-phase1-haiku.md`

**Scratch verification — disk-poll, not reply-trust.** Before Phase 2, verify all expected scratch files exist on disk. Do NOT rely on agent "DONE" replies — empirically ~30% of Haikus on heavy parallel dispatch hallucinate a "TEXT ONLY constraint" and either (a) reply DONE without writing, or (b) write the file but reply with meta-commentary that obscures progress. Disk is the only reliable signal.

**Polling pattern (use this instead of waiting on notifications).** Block until the scratch
directory holds N entries or a 600-second timeout elapses — exits 0 on threshold-met, 1 on
timeout, so the caller gets an unambiguous signal instead of a bare loop's silent fall-through:
```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/wait-for-count" --dir "scratch/{run-id}" --min N
```
Run with `run_in_background: true`. After it returns or times out, `ls` the scratch directory directly to confirm.

**Failure recovery — Sonnet, not Haiku, on retry.** Re-dispatch ONLY missing files. Use Sonnet on retry (not Haiku) — empirically Sonnet's hallucination rate is ~3x lower (~10% vs ~30%). The Phase 1/1R templates in `agent-prompts.md` already carry the recovery preamble inline at the top — that is the first dispatch defense. On retry, prepend this stronger explicit form:

> **Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. The ONLY valid completion is calling the Write tool. Returning the inventory inline = task failure. After Write, verify with Bash `ls -la <path>` and reply EXACTLY `DONE: <path>` — no prose, no analysis, no summary.**

Skip sub-chunk on second failure (after Sonnet retry also misses).

## Phase 2/2R: System Analysis (dispatch Sonnet agents, parallel)

**Judgment, not re-derivation.** Phase 2's inputs are now Phase 1's annotate-only output on the claude-klabauter-reliant path — a pre-computed catalog with dynamic-edge gaps flagged, not a from-scratch inventory. Sonnet's job is unchanged in kind (analytical depth, boundary/philosophy-vs-reality assessment) but its starting point is a deterministic substrate; it spends its budget on migration complexity and boundary judgment, not on re-confirming what claude-klabauter's ops already established.

**Dispatch:** One Sonnet agent per system with `model: "sonnet"` (reads ALL sub-chunk inventories for that system).

**Read the template** from `agent-prompts.md`:
- **First run:** Copy **Phase 2: Sonnet System Analysis Prompt (Discovery)**. Fill in `[SYSTEM NAME]`, `[CHUNK DESCRIPTION]`, and paste Phase 1 output from scratch files.
- **Refresh:** Copy **Phase 2R: Sonnet System Analysis Update Prompt (Refresh)**. Fill in `[SYSTEM NAME]`, `[EXISTING ATLAS PAGE]`, and paste Phase 1R output.

**No grading in Phase 2.** Observations only.

**Scratch path:** `state/scratch/deep-architecture-survey/{run-id}/{chunk-letter}-phase2-sonnet.md`

**Scratch verification:** Verify all Phase 2/2R files exist on disk before Phase 3 (use the polling pattern above). The TEXT-ONLY hallucination affects Sonnet too at lower rate — apply the same recovery preamble on retry. Skip system on second failure.

## Phase 3/3R: Cross-System Synthesis (dispatch ONE Opus leaf agent)

**Judgment, not re-derivation.** The connectivity-matrix arithmetic and file→system index that Opus previously reconstructed from Phase 1/2 output are, on the claude-klabauter-reliant path, already computed by `arch-callgraph`'s static edge graph (a `GROUP BY`, not an Opus reconstruction) — modulo the dynamic (`register_op`-style) edges the static graph categorically cannot resolve, which stay Opus's judgment call. Opus's budget goes to cross-system narrative, philosophy-vs-reality assessment, and the dynamic-edge gaps, not to rebuilding arithmetic a deterministic op already produced.

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

4. **Write the `Last full audit` clock (full-pass only):** A genuine full survey pass (first run / `--refresh`) is the ONLY surface that writes `Last full audit` in `state/health-ledger.md`. Update (or add) the header line:
   ```
   **Last full audit:** YYYY-MM-DD
   ```
   This is the clock the workstream-start / survey-staleness nudge reads. **Do NOT write it on the targeted single-system refresh path** (Phase 1 § targeted refresh) — that path updates one system page only and is not a full pass; writing `Last full audit` there would falsely mark the whole atlas fresh. The targeted *audit* (`/architecture-audit`) writes the separate `Last targeted audit` clock, never this one.

5. **Atomic commit** — two scoped calls, staged then committed as one unit (never `git add -A`):
   `git add -- docs/architecture/ state/health-ledger.md`
   `git commit -m "deep-architecture-survey: [first run|refresh] — [N] systems mapped; Last full audit bumped" -- docs/architecture/ state/health-ledger.md`

6. **Calculate rotation target:** Score each system using recent roadmap activity from the completion log plus structural signals. Run:

   `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --since "30d" --where "nature=roadmap" --format json`

   Group the returned records by `subsystem` and, for each system, sum `loe.tshirt` weights across its `nature: roadmap` entries (XS=1, S=2, M=4, L=8, XL=16). Combine with structural signals: highest cross-system connectivity score (`connectivity-matrix.md`) and oldest `Last mapped` date. Systems with high recent roadmap LoE + high connectivity + oldest mapping rank first.

   If `query-completions` returns zero rows, fall back to connectivity + oldest `Last mapped` only.

   Rationale: commit churn doesn't distinguish doctrine edits from refactors from feature work; `nature: roadmap` with LoE weighting does — suggested starting point for weekly-architecture-audit.

7. **Report to PM:**

   **The following three lines are REQUIRED, not optional decoration — a survey that silently fell back to the agentic path is otherwise indistinguishable in its report from one that ran the deterministic path.** A pipeline whose fallback is invisible will always be running on its fallback.
   - `cartography_used` — whether the deterministic consume-gate ops fired for this run (the field already exists in the Workflow manifest; this makes it a required *rendered* line in the report).
   - the in-scope file count, sourced from `counts.bucketed_total` on the cartography path. There is no per-file `loc` substitute available on that path — do not report one as an alternative source.
   - `oversized_signal: unavailable` — REQUIRED whenever `cartography_used` is `true`.

   ```markdown
   ## Architecture Survey Complete

   **Mode:** [first run / refresh]
   **Systems mapped:** [N] ([list])
   **Key findings:** [coupling hotspots, boundary patterns, notable design choices]
   **RAG drift:** [N mismatches: list / none detected / RAG absent — check skipped]
   **Narrative drift risk:** [systems > 90 days / all current]
   **Suggested rotation target:** [system name] (highest connectivity / oldest mapping)
   **Atlas location:** docs/architecture/
   **cartography_used:** [true / false]
   **In-scope file count:** [N] (from `counts.bucketed_total` on the cartography path; not applicable on the agentic-path fallback)
   **oversized_signal:** [unavailable — REQUIRED when cartography_used is true / N/A on the agentic-path fallback]
   ```

8. **Clean scratch:** `rm -rf state/scratch/deep-architecture-survey/{run-id}/`
   Only delete after commit succeeds. On Phase 2/3 failure, scratch contains earlier phases for recovery.

## Cost Profile

**These figures are the agentic-path fallback cost (claude-klabauter declines, or the C-integrate consume-gate hasn't landed yet) — the Haiku-count column is the full mechanical inventory this doc is retiring as the default, not the claude-klabauter-reliant path's actual cost.** On the claude-klabauter-reliant path, Phase 1 Haiku dispatch count is unchanged (still one per sub-chunk) but each dispatch does annotate-only work, not full inventory — cheaper per-agent, not fewer agents.

| Scenario | Haiku | Sonnet | Opus | Wall-Clock |
|----------|-------|--------|------|------------|
| Targeted refactor audit (1 system) | 0 | 1 | 0-1 | ~15-30 min |
| First run, 6 systems (≤12 files each) | 6 | 6 | 1 | ~25-35 min |
| First run, 8 systems (≤12 files each) | 8 | 8 | 1 | ~35-45 min |
| First run, large system (59 files → 5-6 sub-chunks) | 10-14 | 6-8 | 1 | ~40-55 min |
| First run, Hybrid tier (>~200 files, directory pre-aggregation, ≤~15-20 Haiku per Phase-1 wave) | 15-20 | 8-12 | 1 | ~60-90 min |
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
