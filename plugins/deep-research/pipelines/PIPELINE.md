# Deep Research

> Referenced by `/deep-research`. This is a pipeline definition, not an invocable skill.

## Overview

Two pipelines for deep investigation, both using Agent Teams (fire-and-forget):

- **Internet Research (Pipeline A v2.1)** — investigate a topic across web sources with multi-agent verification. 1 Haiku scout + up to 5 Sonnet specialists + 1 Opus sweep agent. Specialists research, cross-pollinate, and challenge each other's claims (adversarial peers). Specialists output structured JSON claims + markdown summaries. Opus sweep reads specialist outputs directly, performs adversarial coverage check, fills negative space, and frames the output. No consolidator — specialists own their fidelity, sweep reads directly.
- **Repo Research (Pipeline B)** — study a repository, understand it on its own merits, optionally compare against your project. 2 Haiku scouts + 4 Sonnet specialists + 1 Opus synthesizer. Optional `--deeper` mode adds a dependency-weighted repomap; `--deepest` adds architecture atlas artifacts via a post-synthesis Wave 2 agent.

**Both pipelines use Agent Teams.** The EM scopes, spawns a team, and is freed. The team handles everything autonomously.

**Core principle:** Each model tier does what it's best at. Haiku is fast and cheap for mechanical work (indexing files, filtering URLs). Sonnet is analytical (reading deeply, evaluating architecture, comparing implementations). Opus has the highest judgment (cross-referencing, prioritizing, making architectural calls). Don't waste expensive models on cheap work; don't trust cheap models with judgment calls.

**Key design principle (Pipeline B):** Assessment and comparison are decoupled. The assessment is evergreen — it describes what the repo does and how, independent of your project's state. The comparison is point-in-time and optional — it diffs the assessment against your current implementation. The assessment always stands alone; the comparison is an additional artifact.

**Announce at start:** "I'm running `/deep-research` to run [a repo assessment of X / a repo assessment + comparison of X / internet research on Y]."

## When to Use

**Repo Research:**
- Studying an open-source repository to understand its architecture, patterns, and design decisions
- Building a reusable knowledge base about a reference implementation
- Evaluating a library or framework's internal design quality
- Auditing implementation fidelity after porting from a reference (use `--compare`)
- Investigating runtime behavior that doesn't match expectations (use `--compare`)

**Internet Research:**
- Need verified, multi-source understanding of a technical topic
- Evaluating competing approaches or libraries with specific trade-offs
- Researching best practices where training knowledge may be outdated
- Building a knowledge base on a domain before implementation

**Not for:** Quick lookups (use Context7), single-source documentation reads, or questions answerable from one search.

## The One-Line Bug Principle (Comparison Mode)

The highest-value comparison findings are code that **exists but is disconnected**:

1. Code that exists but is never called from the right place
2. Data that is computed but fed to the wrong downstream consumer
3. Mechanisms present in isolation but disconnected from the pipeline
4. Configuration values that agree by coincidence but have no enforcement

Surface-level research ("does our project have X? yes") cannot find these. Only comparison against a reference that implements the connected pipeline exposes the missing link.

## The Fix-Forward Default

**This is research for fixing things, not deferring things.**

With LLM-assisted implementation, the cost of doing the work is lower than the cost of carrying the debt. Every finding that survives cross-reference gets a tier and effort estimate. Nothing goes into a vague "future work" bucket.

---

# Pipeline B: Repo Research (Agent Teams)

## Architecture

```
EM: Scope (define 4 chunks) → Create team → Spawn all teammates → FREED → [notification] → Cleanup
                                │
                                ├── 2 Haiku scouts (2 chunks each, parallel, no blockers)
                                │   Map target repo files + identify comparison files (if --compare)
                                │   Write to: {chunk-letter}-inventory.md
                                │
                                ├── 4 Sonnet specialists (one per chunk, blocked by BOTH scouts)
                                │   Deep-read repo (assessment) + compare against project (if --compare)
                                │   Write to: {chunk-letter}-assessment.md + {chunk-letter}-comparison.md
                                │
                                └── 1 Opus synthesizer (blocked by all specialists)
                                    Cross-reference, produce ASSESSMENT.md + GAP-ANALYSIS.md (if comparison)
```

**Team size:** 2 + 4 + 1 = 7 (platform ceiling).

**Why 4 chunks:** 7-teammate ceiling - 2 scouts - 1 synthesizer = 4 specialist slots. If a repo naturally has 5-6 areas, the EM merges smaller ones.

**Why 2 scouts, not 1:** Parallelism. Two Haiku scouts inventory the repo in half the time. Each scout gets 2 chunks. The even split is simple and predictable.

**Why all specialists blocked by BOTH scouts:** Cross-subsystem connections. Scout 1's chunks may have data flow into scout 2's chunks. Specialists need the COMPLETE inventory to understand these connections.

## Blocking Chain

```
Scout 1 (chunks A, B) ─┐
                        ├──→ Specialists A, B, C, D (all blocked by BOTH scouts)
Scout 2 (chunks C, D) ─┘                │
                                         ├──→ DONE messages wake synthesizer
                                         │
                              Synthesizer (blocked by all 4 specialists)
```

- **Scouts → Specialists:** Task-gated via `blockedBy`. No messaging — task completion is the signal.
- **Specialists → Synthesizer:** Task-gated via `blockedBy` + explicit DONE messages as wake-up signals. `blockedBy` is a status gate, not an event trigger.

## Phase 0: Scope Definition (EM Direct)

**Model:** EM (Opus). **Time:** ~5 min (~7 min with `--deeper`).

1. Read the README, pin the version
2. Survey repo structure (2-3 `ls` commands + file count estimates)
2b. If `--deeper`: generate dependency-weighted repomap via import extraction + cross-reference counting. Writes `{scratch-dir}/repomap.md`. Skipped if import graph is too thin (<5 files with 2+ refs).
3. Define exactly 4 domain-aligned chunks (informed by repomap centrality data if `--deeper`)
4. Assign chunks to scouts (A+B to scout 1, C+D to scout 2)
5. Estimate file counts per chunk (tripwire for specialist quality recovery)
6. Write focus questions
7. If `--compare`: identify domain keywords for comparison file identification
8. Ask PM for timing preferences

**Output:** `{scratch-dir}/scope.md`

## Phase 1: File Inventory (Haiku scouts, parallel)

**Model:** Haiku. **Count:** 2 scouts, 2 chunks each. **Timing:** Ceiling 5 min.

Each scout reads every file in its chunks and produces structured inventory:
- File path, line count, key structs/functions with signatures
- Actual numeric constant values
- Data flow: what each function consumes, produces, who calls it
- Cross-subsystem connections
- If `--compare`: comparison file candidate mapping (glob project → match → map)

**Why Haiku:** Mechanical file reading requires no judgment. Haiku is 10x cheaper than Sonnet and the output quality is sufficient for directing specialists.

**Why this matters:** Haiku scouts produce a thoroughness artifact that Sonnets would naturally skip. Code comprehension benefits from exhaustive inventory — Sonnets will skim; Haiku is forced to read everything.

**Timing note:** Pipeline A uses a 3-minute scout ceiling (web searching is fast). Repo scouts use 5 minutes because file reading is heavier. Tighten if dry runs show <3 min consistently.

**Output:** `{scratch-dir}/{chunk-letter}-inventory.md` (one per chunk, two per scout)

## Phase 2: Analysis (Sonnet specialists, parallel)

**Model:** Sonnet. **Count:** 4 specialists (one per chunk). **Timing:** Floor 5 min + 3 files; ceiling 15 min.

Each specialist:
1. If `--deeper`: reads the repomap first (structural importance lens)
2. Reads the scout inventory for their chunk
3. Deep-reads the most important files (using inventory as map, prioritized by repomap if available)
4. Analyzes architecture, patterns, data flow, strengths, limitations
5. Cross-pollinates with peers (max 3 messages per peer)
6. If `--compare`: reads project files identified by scout, produces comparison artifact
7. Self-governs timing (floor/diminishing returns/ceiling)
8. Converges: writes output, marks complete, sends DONE to synthesizer

**Quality recovery for thin scout output:** If inventory lists fewer files than `[EXPECTED_FILE_COUNT]`, specialist uses Glob to discover additional files and budgets 3 extra minutes for self-directed discovery.

**Dual output:**
- Assessment artifact (`{chunk-letter}-assessment.md`): Always. Repo on its own merits.
- Comparison artifact (`{chunk-letter}-comparison.md`): Only if `--compare`. Gap analysis per chunk.

Assessment is written FIRST, comparison SECOND. The assessment stands alone.

## Phase 3: Synthesis (Opus synthesizer)

**Model:** Opus. **Input:** All specialist assessments + comparisons (if any).

Cross-references all findings and produces:
- **ASSESSMENT.md** (always) — evergreen document describing the repo on its own terms
- **GAP-ANALYSIS.md** (if `--compare`) — point-in-time comparison with tiered findings

**Output format:** Inline in `repo-synthesizer-prompt-template.md`.

## Phase 3.5: Atlas Generation (only if `--deepest`)

**Model:** Sonnet (subagent, not teammate). **Input:** All scout inventories, specialist assessments, synthesis, repomap.

After synthesis completes, TeamDelete frees the team slot. The EM dispatches a Sonnet subagent that produces 4 atlas artifacts from the research findings:
- **File index** — every file → system (chunk) mapping
- **System map** — ASCII connectivity diagram
- **Connectivity matrix** — cross-system dependency counts
- **Architecture summary** — per-system details with YAML metadata

Systems = EM-defined chunks. Atlas from assessment data only (no comparison data). Atlas failure is non-blocking — assessment is committed regardless.

**Timing:** 10-minute ceiling with self-timing.

## Phase 4: Cleanup (EM)

1. Verify synthesis has substantive content
2. If `--deepest`: verify atlas artifacts, copy to output directory
3. Commit
4. Archive paper trail to `docs/research/archive/`
5. Delete scratch directory
6. Present executive summary to PM (mention atlas artifacts if `--deepest`)

## Protocol and Templates

- **Team protocol:** `repo-team-protocol.md` — blocking chain, timing, DONE messages, comparison mode, deeper/deepest modes
- **Scout prompt template:** `repo-scout-prompt-template.md` — file inventory + comparison file identification
- **Specialist prompt template:** `repo-specialist-prompt-template.md` — dual-output analysis + DONE convergence
- **Synthesizer prompt template:** `repo-synthesizer-prompt-template.md` — synthesis with Phase 4 template reference
- **Atlas prompt template:** `repo-atlas-prompt-template.md` — post-synthesis atlas generation (`--deepest` only)
- **Scout agent:** `agents/repo-scout.md` — Haiku, Read/Glob/Grep, no SendMessage
- **Specialist agent:** `agents/repo-specialist.md` — Sonnet, Read/Glob/Grep + SendMessage
- **Synthesizer agent:** `agents/research-synthesizer.md` — Opus, shared with Pipeline A

---

# Pipeline C: Structured Research (Agent Teams)

## Architecture

```
EM: Read spec → Pre-process into scout-brief.md → Create team → Spawn teammates → FREED
                  │
                  ├── 1 Haiku scout (reads scout-brief.md, maps findings to schema fields)
                  │   Writes per-topic: {scratch-dir}/{subject}-scout-{topic_id}.md
                  │
                  ├── 1-5 Sonnet verifiers (1 per topic, blocked by scout)
                  │   Verify claims, compare against existing data, produce schema field tables
                  │   Writes: {scratch-dir}/{topic_id}-findings.md
                  │
                  └── 1 Opus synthesizer (blocked by all verifiers)
                      Cross-topic reconciliation, schema validation, YAML/JSON output
```

**Team size:** 1 + N + 1 where N = topic count. Maximum N = 5 (team ceiling of 7).

**Topic ceiling enforcement:** If spec has > 5 topics, the EM merges the two most related topics before team creation.

**Key difference from Pipeline A:** The EM pre-processes the spec YAML into a flat `scout-brief.md` because Haiku cannot reliably parse complex YAML. Quality gates from the spec are embedded directly in verifier prompts — self-validation replaces orchestrator re-dispatch.

## Phase 0: Spec Pre-Processing (EM Direct, ~1 min)

1. Read spec YAML and existing data for subject
2. Compare existing data against output_schema — identify gaps
3. Write `{scratch-dir}/scout-brief.md` with flattened topics, search domains, focus questions, schema field targets
4. Extract gate rules for embedding in verifier prompts
5. Ask PM for timing preferences

## Phase 1: Discovery (Haiku scout)

**Model:** Haiku. **Timing:** Ceiling 3 min.

Scout reads scout-brief.md, executes searches per topic, maps findings to schema fields, writes per-topic discovery files. Same mechanical rules as Pipeline A scout.

## Phase 2: Verification (Sonnet verifiers, parallel)

**Model:** Sonnet. **Timing:** Floor 5 min + 5 sources; ceiling 15 min.

Each verifier:
1. Reads scout's per-topic discovery
2. Deep-reads recommended sources via WebFetch
3. Verifies or refutes claims
4. Compares against existing subject data (CONFIRMED/UPDATED/NEW/REFUTED)
5. Structures output as schema field table
6. Self-checks acceptance criteria AND gate rules (embedded in prompt)
7. Cross-pollinates with peer verifiers
8. Converges, sends DONE to synthesizer

## Phase 3: Synthesis (Opus synthesizer)

**Model:** Opus. **Input:** All verifier schema field tables.

Produces:
- Schema-conforming YAML/JSON matching the spec's `output_schema`
- Annotations table (field → source → confidence → notes)
- Cross-topic reconciliation table (where verifiers conflicted)
- Gaps remaining table (unfillable fields with reasons)

## Phase 4: Validation + Cleanup (EM)

1. Read synthesizer output
2. Validate schema conformance BEFORE TeamDelete
3. If validation fails: keep team alive, message synthesizer with corrections
4. If passes: update manifest, commit, TeamDelete, archive, present to PM

## Protocol and Templates

- **Team protocol:** `structured-team-protocol.md`
- **Scout prompt template:** `structured-scout-prompt-template.md`
- **Verifier prompt template:** `structured-verifier-prompt-template.md`
- **Synthesizer prompt template:** `structured-synthesizer-prompt-template.md`
- **Scout agent:** `agents/research-scout.md` (reused from Pipeline A)
- **Verifier agent:** `agents/research-specialist.md` (reused from Pipeline A)
- **Synthesizer agent:** `agents/structured-synthesizer.md` (new — schema-conforming output)

---

# Pipeline A: Internet Research (Agent Teams)

## Architecture (v2.1)

```
EM: Phase 0 (scope) → Create team + tasks → Spawn all teammates → FREED → [notification] → Cleanup
                        │
                        ├── 1 Haiku scout (read queries from scope.md, build source corpus)
                        │
                        ├── up to 5 Sonnet specialists (one per topic, blocked by scout)
                        │   Deep-read sources, verify, challenge peers, output structured claims + summary
                        │
                        └── 1 Opus sweep (blocked by all specialists)
                            Adversarial coverage check → gap-fill research → exec summary + framing
```

**Key design decisions (v2.1):**
- **No consolidator.** v2 had a Sonnet consolidator between specialists and sweep — it became a bottleneck (empirically 4 min slower than the sweep). Specialists own their fidelity via adversarial peer interaction; the sweep reads their outputs directly.
- **Structured specialist output.** Specialists write JSON claims (`{LETTER}-claims.json`) + markdown summary (`{LETTER}-summary.md`). Primary reader is the EM (Opus), not humans.
- **Adversarial specialists.** Challenges are expected, not just permitted. Unresolved challenges produce `[CONTESTED]` claims with both sides' evidence.
- **Sweep phased discipline.** Three explicit sequential phases: (1) assess all claims + emit gap report, (2) fill gaps via web research, (3) frame with exec summary + conclusion.
- **Deferred to v2.2:** Iterative deepening (research → assess gaps → re-dispatch to specialists), citation-first synthesis, fail-and-retry on weak retrieval.

## Phase 0: Research Framing (EM Direct, ~5 min)

1. Define 3-5 topic areas to investigate
2. Write focus questions for each topic
3. Craft search queries for the scout (3-5 per topic, including adversarial)
4. Ask PM for timing preferences
5. Write scope to `{scratch-dir}/scope.md`

Cap at 5 topics (team size: 1 scout + 5 specialists + 1 sweep = 7). Default 4 topics.

## Phase 1: Source Discovery (Haiku scout)

**Model:** Haiku. **Timing:** Ceiling 3 min.

Scout reads search queries from scope.md, executes via WebSearch, vets accessibility via WebFetch, writes shared corpus to `{scratch-dir}/source-corpus.md`.

## Phase 2: Analysis (Sonnet specialists, parallel)

**Model:** Sonnet. **Timing:** Floor 5 min + 5 sources; ceiling 15 min.

Each specialist:
1. Reads shared corpus, identifies sources relevant to their topic
2. Supplements with own WebSearch if corpus is thin
3. Deep-reads top sources via WebFetch
4. Verifies claims, resolves contradictions
5. Cross-pollinates AND challenges peers (adversarial interaction expected)
6. Outputs structured claims JSON + markdown summary
7. Self-governs timing, converges, sends DONE to sweep

## Phase 3: Sweep (Opus)

Three explicit sequential phases:
1. **Assess:** Read all specialist claims, compare across specialists for contradictions, identify absent claims. Emit gap report.
2. **Fill gaps:** Research gaps via WebSearch/WebFetch. Investigate cross-topic connections and negative space.
3. **Frame:** Write exec summary, conclusion, advisory (if beyond-scope).

## Protocol and Templates

- **Team protocol:** `team-protocol.md` — messaging, adversarial challenges, convergence, DONE messages
- **Scout prompt template:** `scout-prompt-template.md` — web search + accessibility vetting
- **Specialist prompt template:** `specialist-prompt-template.md` — structured claims + adversarial messaging
- **Scout agent:** `agents/research-scout.md` — Haiku, WebSearch/WebFetch
- **Specialist agent:** `agents/research-specialist.md` — Sonnet, WebSearch/WebFetch + SendMessage
- **Sweep agent:** `agents/research-synthesizer.md` — Opus, shared with Pipeline B

---

## Scratch Directory

Both pipelines use `tasks/scratch/deep-research-teams/{run-id}/`. Run ID format: `YYYY-MM-DD-HHhMM`.

After completion, paper trail is archived to `docs/research/archive/YYYY-MM-DD-{topic-slug}/` and scratch is deleted.
