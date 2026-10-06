# Pipeline A (Web Research) — Internals Reference

Detail companion to `pipelines/deep-research/web-driver.md`. Step numbers refer to that command. Trimmed out to keep the procedural skeleton readable; consult here when implementing or debugging a specific phase.

## Sweep Prompt Contents (Step 4)

The sweep prompt is `web-sweep-prompt-template.md`; the engine-emitted Workflow renders it, and the sweep reads its inputs from the brief file. Brief values the EM must supply: the research question and project context, the topic table, `output_path` — **must include the pipeline suffix `-web`** (e.g. `docs/research/YYYY-MM-DD-<topic>-web.md`) so same-day/same-topic runs across pipelines do not collide on the stem (see § Run-Stem Uniqueness below) — and `advisory_path` (pre-computed in Step 1). The sweep's mailbox is `{scratch-dir}/mail/sweep.jsonl` (fidelity corrections arrive there).

Reference copy of the template's instruction (the template governs):
  > Read all specialist outputs from `{scratch-dir}/` (`{letter}-claims.json` and `{letter}-summary.md` for each specialist). Follow your agent definition's three phases: Phase 1 — assess all claims and emit gap report to `{scratch-dir}/gap-report.md` AND the durable path `docs/research/{run-stem}-gap-report.md`, Phase 2 — fill gaps via WebSearch/WebFetch, Phase 3 — frame with exec summary and conclusion. Write the final document to `{output-path}` and `{scratch-dir}/synthesis.md` — the synthesis document MUST begin with `research-synthesis` frontmatter (title, question, date, pipeline: web, source_count, topic_facets[], coverage_score from gap-report). After writing the synthesis, merge all `{letter}-claims.json` files into `{scratch-dir}/merged-claims.json` (bare JSON array) — do NOT write `docs/research/{run-stem}.claims.json` or its sidecar; the EM emits that durable pair. Report `pipeline: web` and `deepeningRecommended` (from the gap-report) in your return value; do NOT report `ran_at` — you have no shell and therefore no clock, and writing `merged-claims.json` is itself the stamp (the EM reads its mtime). Emit frontmatter deterministically; DO NOT provide a body template — the body stays agent-authored. Write advisory to `{advisory-path}` and `{scratch-dir}/advisory.md` if you have observations beyond scope. If nothing beyond scope, note 'No advisory' in your return value. You are explicitly encouraged to go beyond the original research scope where your judgment says it's warranted.

## Run-Stem Uniqueness (P2-2 obligation)

The run-stem (`{run-stem}`) is derived from `{output-path}` by stripping `docs/research/` and `.md`. **The EM must ensure `{output-path}` incorporates the pipeline letter** (e.g. `docs/research/2026-06-30-my-topic-web.md` → `{run-stem}` = `2026-06-30-my-topic-web`) so that the stem is unique per pipeline. Two pipelines covering the same topic on the same day would otherwise collide on `docs/research/YYYY-MM-DD-<topic>.md` and all sibling durable records (`.claims.json`, `-gap-report.md`, `-coverage-audit.md`). The `-web` suffix is required for web-pipeline runs; other pipelines use their own suffix (`-repo`, `-structured`, `-notebooklm`).

Pre-compute `{run-stem}` in Step 1 alongside `{output-path}` and `{advisory-path}`, and pass all three to the sweep agent in the Step 4 prompt.

## Step 6.5 — Deepening Decision Logic

Parse the gap report's YAML front-matter. Evaluate:

```
DEEPEN if ANY of:
  - high_severity_gaps >= 2
  - contested_unresolved >= 1 AND the contradiction is material to the research question
  - coverage_score <= 3
  - The EM judges (from reading the prose) that a gap would materially change
    the document's recommendations or conclusions

DO NOT DEEPEN if ALL of:
  - high_severity_gaps == 0
  - coverage_score >= 4
  - Remaining gaps are cosmetic (low-severity, nice-to-have, tangential)

ALSO DO NOT DEEPEN if:
  - The PM's timing preference was fast/short (3-8 min ceiling) — honor the budget
```

**Announce-NO-DEEPEN template:**
> "Gap report reviewed — {gap_count} gaps identified, {high_severity_gaps} high-severity. Coverage score: {coverage_score}/5. Gaps are minor — proceeding with current synthesis."

**Announce-DEEPEN template:**
> "Gap report shows {high_severity_gaps} high-severity gaps and coverage score {coverage_score}/5. Recommending a deepening pass with {N} gap-specialists. Firing the pass-2 Workflow."

## Step 6.6 — Pass 2 Dispatch Details

### Cluster gap targets
Read the Gap Targets table from the gap report. Cluster related gaps into 1-3 specialist assignments (e.g., two absent claims in the same domain → one gap-specialist). Only include HIGH and MEDIUM severity gaps.

### Decide scout inclusion
Include a Haiku scout with new search queries if gap targets require research in topic areas not covered by pass 1's corpus. Skip the scout if gaps are refinements (contradictions, uncorroborated claims within existing topics) — gap-specialists do their own targeted searches.

### Pass 2 script

Fire one background `Workflow` emitted by `emit-dispatch-workflow --pipeline web-deepening --brief <brief path> --list gaps=<letters> --flag needs_scout=<true|false> --scratch-dir <scratch dir> --out <path>` (`web-deepening.manifest.yaml`; see `team-protocol.md` § Fire). Stage order is the manifest's; there are no tasks and no `blockedBy`. The stage notes below describe what the manifest runs.

- **Scout stage (if needed):** `needs_scout=true`; gap-specific queries, corpus to `{scratch-dir}/gap-corpus.md`. Omit when no scout is needed.
- **Gap-specialist stage (1-3):** one per letter in `--list gaps` (letters start after pass 1's last — e.g., A-D used → gap-specialists use E-G), rendered from `gap-specialist-prompt-template.md`. The brief's gap table carries, per gap letter: gap id, description, type, severity, suggested queries, and relevant pass-1 topic letter; plus the research question and project context. Peers are mailbox roles `gap-{letter}`.
- **Rebuttal stage:** a continuation per gap-specialist whose letter appears in a peer's returned `challenged` list.
- **Merge sweep:** `{ model: 'opus', agentType: 'coordinator:research-synthesizer', label: 'sweep-t2' }` after the rebuttal stage returns.

**Merge-mode sweep prompt** must include: `[MERGE_MODE: true]`, pass 1 synthesis path, gap report path, gap-specialist output paths, delta output path = `{scratch-dir}/deepening-delta.md`.

### Announce
> "Deepening pass (pass 2) fired: {scout status} + {N} gap-specialists + 1 Opus merge sweep. Gap-specialists fill targeted gaps (~3-8 min each), then the sweep produces a delta. I'll be notified when the Workflow completes."

EM is freed again. Do not poll.

## Step 6.7 — Merge Delta into Synthesis

When the pass-2 Workflow completes, merge `{scratch-dir}/deepening-delta.md` into the pass-1 synthesis at `{output-path}`:

- **Resolved Contradictions:** find the corresponding synthesis section, update with the resolution, remove `[CONTESTED]` markers.
- **Filled Gaps:** find the appropriate topic section, integrate new findings, replace `[UNFILLED GAP]` markers where applicable.
- **Updated Claims:** update the relevant finding.
- **Open Questions:** remove questions that were answered, add any from "Still Unresolved".
- **Strip all `[DEEPENING ADDITION]` and `[SWEEP ADDITION]` markers** — provenance served its purpose during merge; the final document should read seamlessly.

Write the merged document back to `{output-path}` and `{scratch-dir}/synthesis-merged.md`.

## Fidelity Relay Protocol (deep-tier runs only)

> Mechanics and script placement: `team-protocol.md` § Fidelity Relay Protocol.

The fidelity relay is a **pass-1 stage** of the Workflow script (see `agents/research-synthesizer.md § Fidelity Relay`) — it is NOT a pass-2 activity. This section documents the EM-side preconditions and the relay's placement in the command sequence.

### Gating condition (web-specific)

The relay fires when the sweep's return reports `deepeningRecommended: true` (the gap-report's YAML front-matter value) AND the coverage score crossed the deepening threshold (see § Step 6.5 Deepening Decision Logic). It runs inside the pass-1 Workflow, after the sweep's draft and before the sweep's final return.

Shallow runs (`--shallow`, or gap-report `deepening_recommended: false`) skip the relay entirely.

### Relay locus — pass 1, before the EM reads the result

**The relay always executes inside the pass-1 Workflow, never inside a pass-2 agent.** Rationale: the original specialists are the authors whose content the relay protects; pass-2 gap-specialists did not author it, so asking them would verify the wrong authors. The script re-dispatches each original specialist as a fidelity-check continuation.

### Relay sequence (script-driven; summarized for EM debuggability)

1. After the sweep returns its draft, the script dispatches a fresh `specialist-{letter}` continuation per pass-1 specialist, scoped to misrepresentation only — "did the synthesis flatten, distort, or misrepresent YOUR finding?" Each appends `FIDELITY_CORRECTION` or `FIDELITY_OK` to `mail/sweep.jsonl` and returns.
2. **Bounded:** one dispatch per specialist; no waiting loop.
3. **Non-response fallback:** a continuation that fails or leaves no mailbox line counts as non-response; the sweep continuation annotates the synthesis: `[RELAY: {TOPIC_LETTER} specialist did not respond — relay unconfirmed for this topic]`. The pipeline never hangs on a non-responding specialist.
4. **Bloat-guard (structural discriminator):** a valid fidelity correction must reference an existing synthesis sentence and assert it misrepresents the source. A correction that only asks to ADD a sentence is out of scope by construction — the relay is scoped to misrepresentation, not coverage inflation. The sweep rejects add-content requests.
5. A `sweep` continuation integrates valid corrections, performs a second coherence pass on touched sections, and returns to the EM.

### EM-side error handling

If the sweep's return reports `RELAY_STALLED` (no specialist left a mailbox line), the relay proceeds with all-non-response annotations. This is not a pipeline failure — the synthesis stands; relay coverage was unconfirmed.

## Coverage-Auditor Lifecycle (web pipeline)

> Agent definition: `agents/coverage-auditor.md`

The coverage auditor is a **plain `Agent` dispatched by the EM** after the synthesis is complete and the Workflow's task notification has arrived. It is dispatched at the driver's completion step — **after** synthesis is written, **before** archive.

### Placement in the web command

After the EM receives the Workflow's task notification, and before archival:

0. **Emit the durable claims pair.** Authoritative sequence and invocation: `web-driver.md` Step 6 item 5 (claims-emit runs before Commit, which runs before auditor dispatch).

1. **Dispatch the auditor** as a plain `Agent(...)` (not as a stage of the research script):
   - `subagent_type: "coordinator:coverage-auditor"`
   - Model: sonnet
   - Tool grant: Read, Grep, Glob (base grant — no write tools on synthesis output path)
   - Provide: synthesis output path, scratch directory path, pipeline identifier `"A"`
2. **Wait for the auditor's return (`{sidecar-path}`).**
3. **Proceed to Step 6.5** (deepening decision gate). The auditor is already done.

### What the auditor does

The auditor reads all `{scratch-dir}/*-claims.json` specialist claim records and the synthesis. It cross-references each claim (binary: `present-with-pointer` / `absent`) and produces a sidecar at `{output-path minus .md}-coverage-audit.md` with two structured sections:

- **Coverage Pointers** — claim-by-claim presence table. Input universe is specialist claim records only; `[SWEEP ADDITION]` content is explicitly excluded from the denominator (no upstream claim record exists).
- **Completeness Map** — topics distilled out of the synthesis, with source pointers so a reader can self-serve the full picture without trawling every source document. Also consolidates any `[UNFILLED GAP]` inline markers from the synthesis.

The web gap-report (`gap-report.md`) answers "did we research enough?" (input coverage, drives the Step 6.5 deepening gate). The coverage-audit sidecar answers "did the synthesis carry the research?" (output coverage, reader-facing completeness). **These are two separate artifacts with two separate questions — do not conflate them.**

The auditor never edits the synthesis. It emits the sidecar only.

### Invariants

- The auditor adds no concurrent web caller — it runs after the Workflow has returned (precedent: `repo-driver.md:65` survey agent, `:265` atlas-sketch, `:363-365` atlas-refinement).
- Auditor is always-on — no size floor, no skip condition. A short synthesis that silently drops two claims is the highest-risk case, not the lowest (plan-coverage-checker principle: author confidence is the failure mode).
- The synthesizer's `[UNFILLED GAP]` inline markers remain in synthesis prose (reader-facing). The auditor's Completeness Map supersedes and consolidates the synthesizer's free-prose "thin areas" meta-observations paragraph; it references the inline markers rather than deleting them.

## Error Handling Matrix

| Failure | Action |
|---------|--------|
| Scout fails (no corpus written) | Specialists fall back to self-directed discovery — the corpus is optional, not required. |
| Scout times out (partial corpus) | Specialists use what's there + supplement with own searches. |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and returns. |
| A specialist agent fails | Its `parallel()` slot is null; later stages proceed with the survivors and the sweep notes the missing topic. |
| Sweep fails or the Workflow errors | EM reads raw specialist outputs from `{scratch-dir}/{letter}-claims.json` and `{letter}-summary.md` and presents to PM. |
| All specialists fail | Report to PM. |
| A Workflow stage stalls | Read the available outputs from `{scratch-dir}`, commit and archive them, and present to PM. Do not block. |
| Pass-2 sweep fails | EM reads raw gap-specialist outputs from `{scratch-dir}/D-{letter}-claims.json` and manually integrates into the pass-1 synthesis. |
| All pass-2 gap-specialists fail | Proceed to Step 7 with the pass-1 synthesis as-is. Deepening failure is non-blocking — pass 1's output is already complete. |
| Gap report has no YAML front-matter | Treat as `coverage_score: 4, high_severity_gaps: 0` — skip deepening (sweep may be running an older version). |
