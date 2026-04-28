# Pipeline A (Web Research) — Internals Reference

Detail companion to `commands/web.md`. Step numbers refer to that command. Trimmed out to keep the procedural skeleton readable; consult here when implementing or debugging a specific phase.

## Sweep Prompt Contents (Step 4)

The Opus sweep teammate is dispatched with a prompt that must include:

- The research question and project context
- The scratch directory path: `{scratch-dir}`
- The list of specialist topic letters and their output file paths
- The output path for the final document: `{output-path}`
- The advisory output path: `{advisory-path}` (pre-computed in Step 1)
- The sweep task ID to mark complete when done
- Instruction (verbatim):
  > Read all specialist outputs from `{scratch-dir}/` (`{letter}-claims.json` and `{letter}-summary.md` for each specialist). Follow your agent definition's three phases: Phase 1 — assess all claims and emit gap report, Phase 2 — fill gaps via WebSearch/WebFetch, Phase 3 — frame with exec summary and conclusion. Write the final document to `{output-path}` and `{scratch-dir}/synthesis.md`. Write advisory to `{advisory-path}` and `{scratch-dir}/advisory.md` if you have observations beyond scope. If nothing beyond scope, note 'No advisory' in your completion message. You are explicitly encouraged to go beyond the original research scope where your judgment says it's warranted.

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
> "Gap report shows {high_severity_gaps} high-severity gaps and coverage score {coverage_score}/5. Recommending a deepening pass with {N} gap-specialists. Dispatching Team 2."

## Step 6.6 — Team 2 Dispatch Details

### Cluster gap targets
Read the Gap Targets table from the gap report. Cluster related gaps into 1-3 specialist assignments (e.g., two absent claims in the same domain → one gap-specialist). Only include HIGH and MEDIUM severity gaps.

### Decide scout inclusion
Include a Haiku scout with new search queries if gap targets require research in topic areas not covered by Team 1's corpus. Skip the scout if gaps are refinements (contradictions, uncorroborated claims within existing topics) — gap-specialists do their own targeted searches.

### Team 2 task creation

```
TeamCreate(team_name: "research-{topic-slug}-t2")
```

**Sweep task (merge mode):**
```
TaskCreate(subject: "Merge sweep: produce deepening delta", description: "Read Team 1 gap report + Team 2 gap-specialist outputs, produce deepening-delta.md")
```

**Scout task (if needed):**
```
TaskCreate(subject: "Build supplementary corpus for gaps", description: "Execute new search queries for gap targets, write to {scratch-dir}/gap-corpus.md")
```

**Gap-specialist tasks (1-3):** for each gap cluster, fill `pipelines/gap-specialist-prompt-template.md` with: `[GAP_ID]`, `[GAP_DESCRIPTION]`, `[GAP_TYPE]`, `[GAP_SEVERITY]`, `[SUGGESTED_QUERIES]`, `[RELEVANT_TOPIC_LETTER]`, `[GAP_LETTER]` (use letters starting after Team 1's last — e.g., A-D used → gap-specialists use E-G), `[SCRATCH_DIR]`, `[TASK_ID]`, `[SPAWN_TIMESTAMP]`, `[SWEEP_NAME]` = `"sweep-t2"`, peer list, research question, project context.

```
TaskCreate(subject: "Fill gap {GAP_ID}: {description}", description: "...")
TaskUpdate(taskId: "{gap-specialist-id}", addBlockedBy: ["{scout-task-id}"])  # only if scout exists
TaskUpdate(taskId: "{sweep-t2-id}", addBlockedBy: ["{gap-specialist-ids...}"])
```

### Team 2 spawn (single message, parallel)

```
Agent(team_name: "research-{topic-slug}-t2", name: "scout-t2", model: "haiku",
      subagent_type: "deep-research:research-scout", prompt: <gap-specific queries>)

Agent(team_name: "research-{topic-slug}-t2", name: "gap-{letter}", model: "sonnet",
      subagent_type: "deep-research:research-specialist", prompt: <filled gap-specialist prompt>)

Agent(team_name: "research-{topic-slug}-t2", name: "sweep-t2", model: "opus",
      subagent_type: "deep-research:research-synthesizer",
      prompt: <merge-mode sweep prompt — see below>)
```

**Merge-mode sweep prompt** must include: `[MERGE_MODE: true]`, Team 1 synthesis path, gap report path, gap-specialist output paths, delta output path = `{scratch-dir}/deepening-delta.md`.

### Announce
> "Deepening team (Team 2) dispatched: {scout status} + {N} gap-specialists + 1 Opus merge sweep. Gap-specialists fill targeted gaps (~3-8 min each), then the sweep produces a delta. I'll be notified when complete."

EM is freed again. Do not poll.

## Step 6.7 — Merge Delta into Synthesis

When the Team 2 sweep completes, merge `{scratch-dir}/deepening-delta.md` into the Team 1 synthesis at `{output-path}`:

- **Resolved Contradictions:** find the corresponding synthesis section, update with the resolution, remove `[CONTESTED]` markers.
- **Filled Gaps:** find the appropriate topic section, integrate new findings, replace `[UNFILLED GAP]` markers where applicable.
- **Updated Claims:** update the relevant finding.
- **Open Questions:** remove questions that were answered, add any from "Still Unresolved".
- **Strip all `[DEEPENING ADDITION]` and `[SWEEP ADDITION]` markers** — provenance served its purpose during merge; the final document should read seamlessly.

Write the merged document back to `{output-path}` and `{scratch-dir}/synthesis-merged.md`.

## Error Handling Matrix

| Failure | Action |
|---------|--------|
| Scout fails (no corpus written) | Specialists fall back to self-directed discovery — the corpus is optional, not required. |
| Scout times out (partial corpus) | Specialists use what's there + supplement with own searches. |
| Specialist hits ceiling and self-converges | Normal — specialist writes what it has and marks task complete. |
| Sweep doesn't wake after all specialists complete | Verify specialists sent DONE to sweep; if not, manual `SendMessage` nudge. After 5 min stalled, EM reads raw specialist outputs for PM. |
| All specialists fail | `TeamDelete`, report to PM. |
| Agents stuck in idle loops | Known platform issue. Commit and archive results before `TeamDelete`. If `TeamDelete` fails ("active" agents), wait for timeout. Do not block — read available outputs and present to PM. |
| Team creation fails | Fall back to relay pattern or manual research. |
| Team 2 sweep fails | EM reads raw gap-specialist outputs from `{scratch-dir}/{letter}-*-claims.json` and manually integrates into Team 1 synthesis. |
| All Team 2 gap-specialists fail | `TeamDelete` Team 2, proceed to Step 7 with Team 1 synthesis as-is. Deepening failure is non-blocking — Team 1's output is already complete. |
| Gap report has no YAML front-matter | Treat as `coverage_score: 4, high_severity_gaps: 0` — skip deepening (sweep may be running an older version). |
