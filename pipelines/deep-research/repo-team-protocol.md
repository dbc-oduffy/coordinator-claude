# Repo Research Team Protocol

> Referenced by agent definitions and `repo.md` command.

## Overview

Chatty-Workflow repo research: the EM scopes the target repository into 4 domain-aligned chunks, writes `{scratch-dir}/scope.md`, and fires ONE background `Workflow` whose script runs 2–4 size-derived scouts (Haiku small / Sonnet large), 4 Sonnet specialists, and 1 Opus synthesizer in order. The EM is **freed**. The workflow handles everything autonomously — file inventory, analysis, optional comparison, cross-pollination, and synthesis. The EM is notified by the Workflow's task notification, whose result is the synthesizer's return value. The engine emits the script from `repo.manifest.yaml` (`repo-driver.md` Step 5, `emit-dispatch-workflow --pipeline repo`); doctrine is `coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md`.

Optional `--deeper` mode adds a dependency-weighted repomap during EM scoping, giving specialists structural centrality rankings to prioritize deep-reads.

## Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** | Haiku | 2 | Read and inventory all files in assigned chunks; if comparison mode, identify equivalent project files |
| **Specialist** | Sonnet | 4 | Deep-read files, analyze architecture/patterns/data flow, optionally compare against project, cross-pollinate by mailbox |
| **Synthesizer** (overseer) | Opus | 1 | Cross-reference all specialist findings, produce ASSESSMENT.md + GAP-ANALYSIS.md (if comparison); the only agent whose return value reaches the EM |

Role names are stable mailbox names: `scout-1`/`scout-2` (or `scout-a`…`scout-d` on the Sonnet tier), `specialist-a`…`specialist-d`, `sweep`, `synthesizer`.

## Workflow Lifecycle

```
EM: Scope into 4 chunks → write scope → fire Workflow → FREED
Scout 1: Read chunks A,B → Inventory files → [If compare: identify project files] → Write inventories → return
Scout 2: Read chunks C,D → Inventory files → [If compare: identify project files] → Write inventories → return
Gate: [after both scouts return] verify inventories on disk → recover failures
Specialists (round 1): Read inventories → Deep-read files → Assessment → [If compare: Comparison] → append challenges to peers' mailboxes → return
Specialists (round 2): [continuation agent per specialist with unread mail] → answer challenges → revise outputs → return
Synthesizer: [after all specialists return] Read findings → Synthesize → return (EM notified)
```

## Stage Order

```
Scout 1 (chunks A, B) ─┐
                        ├──→ Gate ──→ [if --deepest: Atlas Sketch (Haiku)] ──→ Specialists A, B, C, D (round 1)
Scout 2 (chunks C, D) ─┘                                                              │
                                                                          Rebuttal round (continuations)
                                                                                      │
                                                                      [if --compare: Sweep] ──→ Synthesizer
                                                                                      │
                                                                  [if --deepest: relay wake → Synthesizer pass 2]
                                                                                      │
                                                                      [if --deepest: Atlas Refinement (EM, post-run)]
```

**Why all specialists start after all scouts return:** Cross-subsystem connections. Scout 1's chunks may have data flow into scout 2's chunks. Specialists need the COMPLETE inventory across all chunks to understand these connections. The latency cost is minimal — Haiku scouts have a 5-minute ceiling.

- **Ordering, not gating.** The script starts stage N+1 when stage N's `agent()` calls return (`await`, or `parallel()` for a fan-out). No task list, `blockedBy`, or task status gates anything.
- **Wake = continuation dispatch.** A returned agent cannot be resumed. Any hand-off that needs a finished agent's attention — a challenge, a fidelity relay — is a mailbox line plus a fresh continuation agent dispatched by the script after the writers have returned.

## Scout Protocol

Each scout inventories its assigned chunks of the target repository. Scouts produce **structured file inventories** — not analysis, not recommendations, just thorough mechanical cataloging.

- Reads every file in their assigned chunks via Read tool
- Produces: file paths, line counts, key structs/functions with signatures, actual constant values, data flow, cross-subsystem connections
- If `--compare` mode: also globs the user's project for files matching chunk domain keywords, reads first 30 lines to check signatures, writes `{repo-file} → {project-file-candidate}` mappings
- **No messaging** — scouts neither read nor write mailboxes. Returning is the only signal, and it is not evidence: the script's disk gate verifies the inventories.
- **Timing:** No floor. Ceiling: 5 minutes. This is mechanical work — go fast. (Pipeline A uses 3 minutes for web scouts; 5 minutes here because repo file reading is heavier.)

## Message Protocol

Agents never use `SendMessage` — not to peers, not to the EM. Peer exchange goes through mailbox files at `{scratch-dir}/mail/<role>.jsonl`.

- A line is `{"from": "<role>", "text": "..."}`. To message peer X, append a line to X's file (create the directory and file if absent).
- A reader appends `{"read": true}` after reading its file. It has unread mail when lines follow its last read marker.
- Every specialist reads its own mailbox before it returns, then appends the read marker.
- The synthesizer is the overseer: its return value is the only one that reaches the EM. Workers return a one-line pointer (`DONE: <paths>`) to the script and never address the EM.

### Specialist → Specialist (Adversarial Cross-Pollination)

Append targeted messages to specific peers' mailboxes. Challenges are **expected**, not just permitted — specialists should actively test each other's claims.

| Category | Format | When |
|---|---|---|
| **FINDING** | `"Finding for {peer}: {brief}. File: {path}:{line}. Relevant because {reason}."` | A cross-chunk discovery relevant to another specialist |
| **CONTRADICTION** | `"Contradiction with {peer}: I found {X} in chunk {Y} but your chunk suggests {Z}. Can you verify?"` | Data flow or design pattern conflicts across chunks |
| **CHALLENGE** | `"Challenge to {peer}: Your chunk's {X} at {file}:{line} conflicts with {Y} at {file}:{line}. Which is the intended flow?"` | Direct factual conflict — resolution expected |
| **SOURCE** | `"Source for {peer}: {file-path} — covers {aspect} relevant to your chunk."` | Useful file for a peer's analysis |

**Resolution protocol (rebuttal round):** Round 1 specialists write their outputs, append challenges to peers' mailboxes, and return. After all of round 1 returns, the script probes the mailboxes and dispatches a fresh continuation agent for each specialist with unread mail. The continuation's brief names its mailbox, its own prior output files, and its predecessor's return value. It answers each challenge with evidence or concedes, revises its outputs, and returns. A challenge still unresolved after the rebuttal round produces a `[CONTESTED]` finding with both sides' evidence. One rebuttal round is the default; the round count is bounded by the script, never by messaging until converged.

### Volume Governance

- **Peer messages: max 3 per peer** (max 9 total for a 4-specialist run since you don't message yourself)
- **Completion signal: none** — a specialist's return is its completion; the synthesizer stage starts after all specialists return
- **Scouts: no messages**
- Quality over quantity

## Self-Governance Timing

Specialists manage their own timing. The EM does not broadcast WRAP_UP.

### Three-Part Model

1. **Floor (minimum before convergence allowed)**
   - Must have deep-read at least `MIN_SOURCES` files (not just listed — actually Read and analyzed) AND worked for at least `MIN_MINUTES` minutes
   - Both conditions must be met — prevents "skimmed 3 files in 2 minutes" thin convergence
   - Defaults: 3 files deep-read, 5 minutes

2. **Diminishing Returns (between floor and ceiling)**
   - After the floor, self-assess after each file read: "Did this add new architectural insights?"
   - If last 2 consecutive file reads added no new findings → convergence signal
   - Note in output: "Converging: diminishing returns after file N"

3. **Ceiling (maximum research time)**
   - Configurable by the EM when it fills the specialist prompts (default: 15 minutes)
   - Begin convergence regardless of state
   - Check time via `date +%s` in Bash, compare against the specialist's own start timestamp

### Clock Mechanism

A specialist records its own start with `date +%s` as its first action (the script's brief says so) and re-checks after every 2-3 file reads. The EM's Step 1 timestamp does not apply: the specialist stage starts after the scouts and the gate.

## Convergence Protocol

Begin convergence when ANY of these conditions are met (AND the floor is satisfied):
- At least `MIN_SOURCES` files deep-read and cross-chunk connections addressed
- Last 2 file reads added no new findings (diminishing returns)
- Ceiling time reached

**Steps:**
1. Append any remaining challenges and findings to peers' mailboxes (within the 3-per-peer cap)
2. Read your own mailbox; answer any challenge already in it
3. Write complete output files (assessment, claims, and comparison if enabled)
4. Append `{"read": true}` to your mailbox
5. Return `DONE: <paths written>` — the script's ordering wakes the synthesizer stage

**Timeout:** A challenge that arrives after a peer has returned is answered by that peer's continuation agent in the rebuttal round. A challenge still unanswered after that round → mark the finding `[UNVERIFIED]`.

## Failure Handling

- **Scout fails (no inventory):** The script's gate redispatches the chunk to a Sonnet scout, then stubs it; specialists fall back to self-directed file discovery (Glob + Read workflow) on a stub. Budget 3 extra minutes.
- **Scout times out (partial inventory):** Specialists use what's there + supplement with own Glob/Read for missing directories.
- **Self-timed convergence (ceiling):** Specialists begin convergence autonomously after max time, without EM intervention.
- **Read failures:** If a file can't be read (binary, permissions), skip it and note in output.
- **All specialists fail:** The synthesizer stage finds no assessments and the Workflow's result says so; the EM reports to PM.

## Working Directory

`docs/research/{run-id}-{topic-slug}-workdir/`

- Scouts write to: `{scratch-dir}/{chunk-letter}-inventory.md` for their assigned chunks (Haiku tier: scout-1 → A, B; scout-2 → C, D)
- Each specialist writes to: `{scratch-dir}/{chunk-letter}-assessment.md` (always) + `{scratch-dir}/{chunk-letter}-comparison.md` (if comparison mode)
- Mailboxes: `{scratch-dir}/mail/<role>.jsonl`
- Synthesizer writes to: `{output-path}` + `{scratch-dir}/synthesis.md`

## Deeper Mode

When `--deeper` is provided, the EM generates a dependency-weighted repomap during Phase 0 (scoping), before chunk definition. The repomap:

1. Extracts import/include/require statements via language-specific grep patterns
2. Resolves imports to actual files, counts cross-references
3. Reads top ~20 files to extract key exports
4. Writes `{scratch-dir}/repomap.md` with files ranked into Tier 1 (10+ refs), Tier 2 (5-9), Tier 3 (2-4)

**Fallback:** If fewer than 5 files have 2+ incoming references (thin import graph), the repomap is skipped and specialists operate in default mode.

**Specialist usage:** Specialists read the repomap BEFORE the scout inventory. The repomap provides the importance lens (what matters); the inventory provides the detail (what exists). Specialists prioritize Tier 1/2 files in their chunk for deep-reading and use cross-chunk references to understand inter-system dependencies.

**Composes with `--compare`:** Both flags can be used simultaneously. The repomap informs prioritization; comparison mode adds the project comparison artifacts.

## Survey Mode

When `--survey` is provided (or implied by `--deepest`), the EM dispatches a solo Opus subagent before the Workflow to produce a holistic 20-30KB narrative overview. The survey:

1. Reads the entire repo in one context window
2. Catches cross-cutting insights that chunked analysis structurally misses
3. Produces a decision gate: PM can accept the survey as the deliverable or proceed with the workflow

If the workflow proceeds, the survey is passed to specialists as their first context artifact, read before repomap and scout inventories.

**Survey caching:** If a prior survey exists at the output path and is less than 7 days old, the EM may reuse it instead of regenerating.

## Deepest Mode

When `--deepest` is provided, Pipeline B runs as a **three-phase pipeline**. `--deepest` implies both `--deeper` and `--survey`.

**Phase 1 (Scouts + Atlas Sketch):** The script runs the scouts and the gate. After the gate returns, it dispatches a Haiku atlas sketch agent that reads scout inventories + repomap and produces 3 preliminary atlas artifacts: file index, system map, connectivity matrix. NOT the architecture summary — that requires specialist analysis.

**Phase 2 (Specialists + Synthesis):** The script dispatches the 4 specialists. Specialists receive: survey (if produced) + repomap + atlas sketch + scout inventory. They validate atlas sketch connections with `[CONFIRMED]`/`[REFUTED]`/`[MISSING]` markers. The synthesizer cross-references and produces assessment + gap analysis (with deduplication — assessment describes what IS, gap analysis describes what to CHANGE), then runs the fidelity relay (see below).

**Phase 3 (Atlas Refinement — post-synthesis):** After the Workflow completes, the EM dispatches a Sonnet subagent that refines the preliminary atlas using specialist validation data and synthesis findings, and produces the architecture summary (the 4th artifact). This is the only artifact not in the sketch.

```
Scout 1 (chunks A, B) ─┐
                        ├──→ Gate ──→ Atlas Sketch (Haiku) ──→ Specialists A,B,C,D
Scout 2 (chunks C, D) ─┘                                          │
                                                                    ├──→ Synthesizer (+ relay)
                                                                    │
                                                         Atlas Refinement (post-run)
```

**System taxonomy:** Systems map to EM-defined chunks (A, B, C, D) with their chunk descriptions as system names. The atlas agent does not invent its own groupings.

**Atlas from assessment only:** Atlas artifacts describe the repo on its own merits — no comparison data incorporated, consistent with the assessment/comparison decoupling principle.

**Error handling:** Atlas sketch failure is non-blocking — specialists proceed without structural orientation (same as `--deeper` mode). Atlas refinement failure is also non-blocking — assessment is committed without atlas artifacts.

**Composes with `--compare`:** `--deepest --compare` produces assessment + comparison + atlas. The atlas draws from assessment data only; comparison artifacts are independent.

## Fidelity Relay Protocol

**When this fires:** Repo runs only — gated to `--deepest` flag. `--deeper` and non-flag runs skip this phase entirely.

**Relay locus: inside the Workflow, between the synthesizer's two passes.** The synthesizer's pass 1 writes the draft and returns without messaging anyone. The script then dispatches a fresh continuation agent for each specialist, carrying the relay request, and after they return dispatches the synthesizer's pass 2. Specialists have returned by then, so a continuation agent answers for each; no live agent is woken.

**Relay sequence (see `agents/research-synthesizer.md § Fidelity Relay`):**

1. Synthesizer pass 1: write the synthesis draft, then return.

2. Script: dispatch a continuation agent per specialist (naming its mailbox, its own prior outputs, and its predecessor's return value) with this request:
   ```
   FIDELITY_RELAY: [CHUNK_LETTER]
   Please verify that YOUR contributed findings are faithfully represented in the
   synthesis draft at {output-path}. Check ONLY for misrepresentation, flattening,
   or distortion of your existing findings — NOT for missing content you wish were added.
   Reply by appending FIDELITY_CORRECTION or FIDELITY_OK to mail/synthesizer.jsonl.
   ```
   Each continuation answers and returns.

3. **Bounded:** one relay round. **On non-response:** a specialist whose continuation wrote no reply is unconfirmed. Synthesizer pass 2 notes it explicitly in the synthesis (`[RELAY: {CHUNK_LETTER} specialist did not respond — relay unconfirmed for this chunk]`). **Never hang the pipeline waiting for a non-responding specialist.**

4. **Bloat-guard (structural discriminator):** A valid fidelity correction must reference an **existing synthesis sentence** and assert it misrepresents the source. A correction that only asks to ADD a sentence is out of scope by construction — the relay is scoped to misrepresentation, not coverage inflation. Reject add-content requests under the synthesizer's existing preserve-don't-inflate mandate.

5. Synthesizer pass 2: read `mail/synthesizer.jsonl`, integrate valid corrections, do a second pass for coherence on touched prose only, finish the durable index artifacts, and return.

**Author-scoped check (for specialist continuations):** When your continuation brief carries `FIDELITY_RELAY`:
- Check ONLY: is YOUR finding faithfully represented, or was it flattened/distorted/over-stated?
- Do NOT request additions of content you wish were included — that is out of scope by construction.
- Append `FIDELITY_CORRECTION: [CHUNK_LETTER]` with the existing synthesis sentence and the misrepresentation, OR `FIDELITY_OK: [CHUNK_LETTER]`, to `mail/synthesizer.jsonl`.

## Coverage-Auditor Lifecycle

The coverage auditor is a plain `Agent` dispatched by the EM **after the Workflow completes** (at the "On Completion Notification" step in `pipelines/repo-driver.md`), before the run concludes. It is a fresh-eyes Sonnet cross-reference pass — not the synthesizer grading its own homework.

**What it does:** Cross-references specialist `*-claims.json` and `*-summary.md` records against the synthesis. Emits one sidecar: `{output-path minus .md}-coverage-audit.md`. Never writes the synthesis output path.

**Two coverage artifacts, two questions — explicit reader contract:**
- `gap-report.md` (where applicable) — "Did we research enough?" (input coverage, synthesizer-owned)
- `-coverage-audit.md` — "Did the synthesis carry the research?" (output coverage, reader-facing completeness, auditor-owned)

**Auditor lifecycle notes:**
- Dispatched by the EM as a plain `Agent(...)` call after the Workflow's completion notification (precedent: Atlas Refinement in `--deepest` mode is also EM-dispatched after the run).
- Input universe: specialist claim records only (`*-claims.json`, `*-summary.md`). `[SWEEP ADDITION]` content is excluded from the denominator (no upstream claim record; including it causes false-absent noise).
- Coverage classification is binary: **present-with-pointer** or **absent**. "Under-represented" is a judgment beyond a Sonnet cross-reference pass.
- `[UNFILLED GAP]` inline markers in the synthesis remain in synthesis prose (reader-facing); the auditor's Completeness Map consolidates and references them — it does not delete them.

See `agents/coverage-auditor.md` for the full agent spec.

## Comparison Mode

When `--compare <project-path>` is provided:

1. **Scouts** identify equivalent project files during inventory (mechanical pattern-matching)
2. **Specialists** deep-read the project files identified by scouts and produce comparison artifacts
3. **Synthesizer** produces both ASSESSMENT.md (evergreen) and GAP-ANALYSIS.md (point-in-time)

The assessment always stands alone — it describes the repo on its own merits, with no reference to the comparison project. The gap analysis is a separate artifact.
