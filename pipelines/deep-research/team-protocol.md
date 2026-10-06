# Deep Research Team Protocol (v3.0)

> Referenced by agent definitions and `web-driver.md`. Doctrine: `coordinator/docs/wiki/dispatching-parallel-agents/chatty-workflows.md`.

## Overview

Chatty-Workflow deep research: the EM scopes research and crafts search queries, writes `{workdir}/scope.md`, fires ONE background `Workflow` whose script runs a Haiku scout, Sonnet specialists, and an Opus sweep in stage order, and is **freed**. The workers handle source discovery, analysis, adversarial cross-pollination, and synthesis autonomously. The EM is notified by the Workflow's task notification when the sweep stage returns.

## Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** (`scout`) | Haiku | 1 | Execute EM-crafted search queries, mechanically vet accessibility, build shared source corpus |
| **Specialist** (`specialist-a`…`specialist-e`) | Sonnet | up to 5 | Deep-read sources from corpus, verify claims, challenge peers (adversarial) through mailboxes, answer challenges in a rebuttal round, output structured claims JSON + markdown summary |
| **Sweep** (`sweep`) | Opus | 1 | The overseer. Read all specialist outputs directly, adversarial coverage check, fill negative space via web research, write executive summary and conclusion; may go beyond original scope where judgment warrants. The only worker whose return value reaches the EM |

## Stage Order

```
EM: Scope + craft queries → write scope.md → fire Workflow → FREED
Stage 1 Scout:        Read scope.md → WebSearch → WebFetch (vet accessibility) → Write source-corpus.md → return
Stage 2 Specialists:  (parallel, after scout returns) Read corpus → Deep-read → Write claims.json + summary.md → append challenges to peer mailboxes → return
Stage 3 Rebuttal:     (after all specialists return) Continuation agent per specialist with unread mail → answer challenges → revise outputs → return
Stage 4 Sweep:        (after rebuttal returns) Read all specialist outputs → Phase 1: Assess → Phase 2: Fill gaps → Phase 3: Frame → return
Stage 5 Relay:        (deep tier only) Specialist fidelity checks → sweep continuation integrates corrections
```

Ordering is the script's `await` order. Stage N+1 starts when stage N's `agent()` calls return; a fan-out is a `parallel()`. There is no task graph, no `blockedBy`, and no wake message. A worker that must wait on another worker returns, and the script dispatches its continuation after the awaited stage.

## Fire (Engine-Emitted Workflow)

The EM never writes the script. Given the brief file, the engine op emits the receipted Workflow from `web.manifest.yaml`:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/emit-dispatch-workflow" --pipeline web --brief <brief path> --list topics=<a,b,...> --scratch-dir <scratch dir> --out <scratch dir>/web.workflow.mjs
```

Topics are lowercase letters. The manifest carries the stage graph, models and schemas; the templates carry the prompts. The deep tier (`sweep.deepeningRecommended`) runs the relay stage between the sweep and its continuation (see § Fidelity Relay Protocol). Deepening is a second fire (see § Deepening Protocol).

## Mailboxes

Workers never `SendMessage` each other or the EM, and a workflow agent that has returned cannot be resumed. Peers exchange findings through `{workdir}/mail/<role>.jsonl`; roles are the stable names above.

- A line is `{"from": "<role>", "text": "..."}`. To message peer X, append one line to X's file (create it if absent).
- A reader appends `{"read": true}` after reading its file. It has unread mail when lines follow its last read marker.
- The sweep's mailbox is `mail/sweep.jsonl`; fidelity corrections arrive there.

### Specialist → Specialist (Adversarial Cross-Pollination)

Challenges are **expected**, not just permitted — specialists actively test each other's claims. Each line's `text` starts with its category.

| Category | Format | When |
|---|---|---|
| **FINDING** | `"FINDING for {peer}: {brief}. Source: {URL}. Relevant because {reason}."` | A discovery relevant to another specialist's topic |
| **CONTRADICTION** | `"CONTRADICTION with {peer}: I found {X} but your area suggests {Y}. Can you verify?"` | Sources disagree across topics |
| **CHALLENGE** | `"CHALLENGE to {peer}: Your finding {X} conflicts with {Y} from {source}. Which is current?"` | Direct factual conflict — resolution expected |
| **SOURCE** | `"SOURCE for {peer}: {URL} — covers {aspect} relevant to your topic."` | Useful source for a peer |
| **OVERLAP** | `"OVERLAP with {peer}: I'm also covering {X}. Should I defer or should you?"` | Coordinate ownership of shared territory |

**Resolution protocol:** In the rebuttal round the challenged specialist answers with evidence or concedes. A challenge still unanswered after the rebuttal round produces a `[CONTESTED]` claim in structured output with both sides' evidence. Ownership questions (OVERLAP) resolve the same way: the answering specialist states in its rebuttal which side owns the territory and revises accordingly.

### Volume Governance

- **Peer mailbox lines: max 3 per peer** (max 12 total for a 5-specialist run)
- **Rebuttal rounds: 1** (a bounded round count replaces converging by messaging)
- **Scout: no mail** — its return is the signal
- **No DONE messages** — stage order replaces them
- Quality over quantity

## Scout Protocol

The scout builds a **shared corpus** — a pool of broadly useful sources. It does NOT try to be exhaustive per-topic.

- Reads search queries from `{workdir}/scope.md` (written by EM during scoping)
- Executes queries via WebSearch
- Mechanically vets each result via WebFetch: accessible? paywall? date? source type?
- Writes corpus to `{workdir}/source-corpus.md`
- **No mail** — the scout's return ends its stage.
- **Timing:** No floor. Ceiling: 3 minutes. This is mechanical work — go fast.

## Self-Governance Timing

Specialists manage their own timing. The EM never interrupts a running Workflow.

### Three-Part Model

1. **Floor (minimum before convergence allowed)**
   - Must have fetched at least `MIN_SOURCES` sources AND worked for at least `MIN_MINUTES` minutes
   - Both conditions must be met — prevents "fast 3 sources in 2 minutes" thin convergence
   - Defaults: 5 sources, 5 minutes

2. **Diminishing Returns (between floor and ceiling)**
   - After the floor, self-assess after each source: "Did this add new verified findings?"
   - If last 3 consecutive sources added no new verified findings → convergence signal
   - Note in Investigation Log: "Converging: diminishing returns after source N"

3. **Ceiling (maximum research time)**
   - Configurable by the EM when it fills the script (defaults: 15 minutes)
   - Begin convergence regardless of state

### Clock Mechanism

A worker records its own start with `date +%s` in Bash as its first action and checks elapsed time against it at each source-fetch cycle. The script has no clock, so the brief carries the floor and ceiling numbers, not a timestamp.

## Convergence Protocol

Begin convergence when ANY of these conditions are met (AND the floor is satisfied):
- At least `MIN_SOURCES` verified sources and contradictions addressed
- Last 3 sources added no new findings (diminishing returns)
- Ceiling time reached

**Steps:**
1. Append challenges and findings to peers' mailboxes (within the 3-per-peer cap)
2. Write complete output files (claims.json + summary.md)
3. Append `{"read": true}` to your own mailbox if you read it
4. Return `{letter, challenged, claimsPath}` — `challenged` lists every peer letter whose mailbox you wrote to

The rebuttal round answers the challenges. A specialist converges once; the continuation is its only second turn.

## Failure Handling

- **Scout fails (no corpus):** Specialists fall back to self-directed discovery (full WebSearch workflow)
- **Scout times out (partial corpus):** Specialists use what's there + supplement with own searches
- **Self-timed convergence (ceiling):** Specialists begin convergence autonomously after max time, without EM intervention
- **WebSearch/WebFetch failures:** If 3 consecutive fetch attempts fail, converge with what you have and note failures in Investigation Log
- **A specialist agent fails:** the script's `parallel()` result carries a null for it; the rebuttal and sweep stages proceed with the survivors, and the sweep notes the missing topic in its return
- **Sweep fails:** EM reads raw specialist outputs from `{workdir}/*-claims.json` and `*-summary.md` and presents to PM
- **All specialists fail:** the sweep reports no inputs; EM reports to PM

## Work Directory

`docs/research/{run-id}-{topic-slug}-workdir/`

- Scout writes to: `{workdir}/source-corpus.md`
- Each specialist writes to: `{workdir}/{topic-letter}-claims.json` + `{workdir}/{topic-letter}-summary.md`
- Mailboxes: `{workdir}/mail/<role>.jsonl`
- Sweep writes synthesis to: `{output-path}` + `{workdir}/synthesis.md`
- Sweep writes advisory to: `{advisory-path}` + `{workdir}/advisory.md` (optional — omitted if nothing beyond scope)

## Fidelity Relay Protocol

**When this fires:** Web runs only — gated to the deep tier (the sweep's return reports `deepeningRecommended: true`). Shallow runs (`--shallow` or `deepening_recommended: false`) skip this stage entirely. Structured (Pipeline C) and notebooklm (Pipeline D) are out of scope (no prose synthesis to distort / no depth concept respectively).

**Relay locus: pass 1, before the sweep's final return.** The original specialists wrote the content, so they are the checkers. Pass 2 gap-specialists are fresh agents who did not author the original content — the wrong execution locus.

**Relay sequence (script-driven; the synthesis draft is on disk before the relay starts):**

1. The sweep returns its draft with `deepeningRecommended` in its schema. When true, the script dispatches, in parallel, a fresh `specialist-{letter}` continuation per specialist whose brief names its claims and summary files and the synthesis draft at `{output-path}`:
   ```
   FIDELITY CHECK: [TOPIC_LETTER]
   Verify that YOUR contributed findings are faithfully represented in the synthesis
   draft at {output-path}. Check ONLY for misrepresentation, flattening,
   or distortion of your existing findings — NOT for missing content you wish were added.
   Append one line to mail/sweep.jsonl: FIDELITY_CORRECTION (quote the existing synthesis
   sentence and state the misrepresentation) or FIDELITY_OK. Then return.
   ```

2. **Bounded:** the check is one dispatch per specialist. A continuation that fails or returns without a mailbox line counts as non-response.

3. **On non-response:** proceed without that specialist's confirmation. The sweep continuation notes it in the synthesis (`[RELAY: {TOPIC_LETTER} specialist did not respond — relay unconfirmed for this topic]`). Never hang the pipeline on a non-responding specialist.

4. **Bloat-guard (structural discriminator):** A valid fidelity correction references an **existing synthesis sentence** and asserts it misrepresents the source. A correction that only asks to ADD a sentence is out of scope by construction — the relay is scoped to misrepresentation, not coverage inflation. The sweep rejects add-content requests under its preserve-don't-inflate mandate.

5. The script then dispatches a `sweep` continuation (Opus) that reads `mail/sweep.jsonl`, integrates valid corrections, does a second pass for coherence on touched prose only, and returns the final result to the EM.

**Author-scoped check (for specialists):** On a fidelity check:
- Check ONLY: is YOUR finding faithfully represented, or was it flattened/distorted/over-stated?
- Do NOT request additions of content you wish were included.
- Reply by mailbox line, then return.

## Coverage-Auditor Lifecycle

The coverage auditor is a **plain `Agent` dispatch by the EM after the Workflow's task notification** (at the completion step in `pipelines/deep-research/web-driver.md`), before archive. It is a fresh-eyes Sonnet cross-reference pass — not the synthesizer grading its own homework.

**What it does:** Cross-references specialist `*-claims.json` records against the synthesis. Emits one sidecar: `{output-path minus .md}-coverage-audit.md`. Never writes the synthesis output path.

**Two coverage artifacts, two questions — explicit reader contract:**
- `gap-report.md` — "Did we research enough?" (input coverage, drives the deepening gate, synthesizer-owned)
- `-coverage-audit.md` — "Did the synthesis carry the research?" (output coverage, reader-facing completeness, auditor-owned)

**Auditor lifecycle notes:**
- Dispatched as a plain `Agent(...)` call, outside the Workflow.
- Input universe: specialist claim records only (`*-claims.json`). `[SWEEP ADDITION]` content is excluded from the denominator (no upstream claim record; including it causes false-absent noise).
- Coverage classification is binary: **present-with-pointer** or **absent**. "Under-represented" is a judgment beyond a Sonnet cross-reference pass.
- `[UNFILLED GAP]` inline markers in the synthesis remain in synthesis prose (reader-facing); the auditor's Completeness Map consolidates and references them — it does not delete them.

See `agents/coverage-auditor.md` for the full agent spec.

## Deepening Protocol (v3.0)

When pass 1's sweep identifies significant coverage gaps, the EM may fire a smaller second Workflow for targeted follow-up. This is the deepening protocol.

### Pass 2 Composition

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** (`scout-t2`, optional) | Haiku | 0-1 | Only if gap targets require new topic areas not in pass 1's corpus |
| **Gap-Specialist** (`gap-{letter}`) | Sonnet | 1-3 | One per gap cluster. Fill specific gaps from pass 1's gap report |
| **Sweep** (`sweep-t2`) | Opus | 1 | Merge mode — produce delta document, not full synthesis |

### Pass 2 Stage Order

```
EM: Read gap-report.md → Cluster gaps → fire Workflow 2 → FREED
Stage 1 Scout (if any): New queries → gap-corpus.md → return
Stage 2 Gap-Specialists: Read prior findings → Targeted research → D-{letter}-claims.json + D-{letter}-summary.md → challenges to peer mailboxes → return
Stage 3 Rebuttal: continuation per gap-specialist with unread mail → return
Stage 4 Sweep (merge mode): Read pass 1 synthesis + gap-specialist outputs → deepening-delta.md → return
```

The deepening pass fires `emit-dispatch-workflow --pipeline web-deepening --brief <brief path> --list gaps=<e,f,...> --flag needs_scout=<true|false> --scratch-dir <scratch dir> --out <scratch dir>/deepening.workflow.mjs` from `web-deepening.manifest.yaml`: the scout stage is gated by `needs_scout`, gap-specialists use `gap-specialist-prompt-template.md`, and the sweep runs in merge mode. No relay stage — pass 1's relay already ran.

### Pass 2 Timing

Gap-specialists use tighter timing than pass 1 specialists because their scope is narrower:

| Parameter | Pass 1 Specialist | Pass 2 Gap-Specialist |
|-----------|------------------|----------------------|
| Floor (minutes) | 5 | 3 |
| Floor (sources) | 5 | 3 |
| Ceiling (minutes) | 15 | 8 |
| Diminishing returns | 3 consecutive | 2 consecutive |
| Peer mailbox lines per peer | 3 | 2 |

### Pass 2 Output

Gap-specialists write to `D-{letter}-claims.json` and `D-{letter}-summary.md` (D- prefix distinguishes from pass 1). The sweep operates in merge mode and writes `deepening-delta.md` — a structured delta that the EM integrates into pass 1's synthesis.

### Depth Limit

**Maximum two passes.** Pass 1 + pass 2. No further iteration. Pass 2's sweep may still identify remaining gaps — these go into the "Open Questions" section of the final document, not into a pass 3.

### Failure Handling

Pass 2 failure is **non-blocking**. Pass 1 already produced a complete document. If pass 2 fails entirely (all gap-specialists fail, sweep does not return), the EM proceeds to finalization with pass 1's synthesis as-is. The deepening pass is an improvement opportunity, not a requirement.
