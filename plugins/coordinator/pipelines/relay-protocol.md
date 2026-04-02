# Relay Protocol — Command ↔ Orchestrator Communication

> Shared reference for all relay-pattern pipelines. Referenced by orchestrator agents and relay driver commands.

## Why Relay?

Claude Code subagents cannot dispatch other subagents (no nested Agent tool). The relay pattern moves all agent dispatch to the **command layer** (which has Agent access), while orchestrators become pure judgment agents that communicate via disk artifacts.

**Actors:**
- **Command** — slash command with Agent tool. Drives phase sequencing, all worker dispatch, verification, and commits.
- **Orchestrator** — dispatched as subagent (fresh per phase), NO Agent tool. Does judgment: scoping, quality gates, cross-pollination, synthesis. Reads prior decisions from disk.
- **Workers** — Haiku/Sonnet subagents dispatched by command. Mechanical/analytical work. Write to scratch files.

**Reference implementation:** `deep-research/notebooklm/commands/research.md` — proven relay with 2 orchestrator dispatches + 1 worker dispatch.

---

## Dispatch Manifest

Written by the orchestrator to `{scratch-dir}/dispatch-manifest.md`. The command reads this to know what to dispatch next.

### Format

```markdown
# Dispatch Manifest

## Status
{STATUS_VALUE}

## Workers

### {worker-id}
- model: {haiku|sonnet}
- prompt: {scratch-dir}/prompts/{worker-id}.md
- output: {scratch-dir}/phase-{N}/{worker-id}.md
- background: {true|false}

### {worker-id-2}
...

## Parallel: {true|false}
```

### Status Values

| Status | Meaning | Command Action |
|--------|---------|----------------|
| `DISPATCH_WORKERS` | Workers listed are ready for dispatch | Dispatch all listed workers |
| `RETRY` | Quality gate failed for some workers | Re-dispatch ONLY the listed workers (gate feedback baked into prompts). Max one retry per topic. |
| `COMPLETE` | Pipeline finished | Orchestrator has written its final output. No more dispatches needed. |
| `ERROR: {reason}` | Unrecoverable problem | Command aborts pipeline and reports to PM. |

### Model Mapping

| Manifest value | Agent tool parameter |
|----------------|---------------------|
| `haiku` | `model: "haiku"` |
| `sonnet` | `model: "sonnet"` |

No other model values. Orchestrator dispatches are always the orchestrator's own model (typically Opus).

### Worker Prompts

The orchestrator writes full worker prompts as separate `.md` files in `{scratch-dir}/prompts/`. Each file is a complete, self-contained prompt — the command reads the file content and passes it as the Agent dispatch prompt verbatim. No parsing, no modification.

Prompt files MUST use templates from `agent-prompts.md` verbatim (with bracketed placeholders filled in). The templates encode critical guardrails that custom prompts lose silently.

---

## Decisions Log

Written by the orchestrator, appended each phase. Located at `{scratch-dir}/decisions.md`.

### Critical Rule

**The orchestrator MUST read `decisions.md` before writing to it.** Each orchestrator dispatch is a fresh agent with no memory of prior phases. If it writes from scratch, it overwrites prior phase decisions. The pattern is: read existing content → append new phase section → write back.

### Format

```markdown
# Decisions Log

## Phase 0 — {Phase Name}
- {key decisions, scope boundaries, chunk definitions}
- {run mode, comparison targets, etc.}

## Phase 1.5 — {Phase Name}
- {quality gate verdicts per topic/chunk}
- {cross-pollination notes}
- {retry decisions}

## Phase N — {Phase Name}
- {synthesis judgments, source quality ranking}
- {contradictions resolved and how}
```

This log is the "sitemap" — it captures what was mapped, verified, judged, and why. It enables:
- **Follow-up research** — future agents query the paper trail, not just the polished result
- **Investigation pivots** — PM changes direction without re-running discovery/verification
- **EM critique** — coordinator audits orchestrator reasoning at any point
- **Revert safety** — phase commits mean hallucinating synthesis can be rolled back

---

## Artifact Layout

### Default Layout (always used)

```
docs/research/
  YYYY-MM-DD-{topic-slug}.md              <- Final result (Opus synthesis)
  archive/YYYY-MM-DD-{topic-slug}/        <- Paper trail (straight to archive)
    decisions.md                           <- Orchestrator judgment log
    prompts/                               <- Worker prompts (what was asked)
    phase-1/                               <- Haiku discovery outputs
    phase-2/                               <- Sonnet verification outputs
    dispatch-manifest.md                   <- Last manifest
```

### Scratch Directory (during execution)

```
tasks/scratch/{pipeline-name}/{run-id}/
  decisions.md                             <- Accumulates across phases
  dispatch-manifest.md                     <- Overwritten each phase
  prompts/                                 <- Worker prompts (overwritten each phase)
    {worker-id}.md
  phase-1/                                 <- Worker outputs, one file per worker
    {worker-id}.md
  phase-2/
    {worker-id}.md
```

Run ID format: `YYYY-MM-DD-HHhMM` (e.g., `2026-03-21-14h30`).

### Post-Completion Archival

At pipeline completion, the command:
1. Copies `decisions.md`, `prompts/`, `phase-*/`, and `dispatch-manifest.md` to the archive path
2. Deletes the scratch directory
3. Reports paper trail location and size to the PM
4. Asks: "Keep the paper trail for follow-up, or delete it?"

### Restructure for Repeatable Research

If the PM indicates the topic will be revisited:
```bash
mkdir -p docs/research/{topic-slug}
mv docs/research/YYYY-MM-DD-{topic-slug}.md docs/research/{topic-slug}/YYYY-MM-DD-result.md
mv docs/research/archive/YYYY-MM-DD-{topic-slug}/ docs/research/{topic-slug}/YYYY-MM-DD-paper-trail/
```

---

## Phase Commits

After each phase's workers complete and output is verified, the command commits:

```bash
git add -A && git commit -m "{pipeline}: phase {N} ({description}) complete"
```

This provides revert safety. The EM does NOT need to read the paper trail when results come back — it's there for later critique if needed.

---

## Command-Side Verification

Before dispatching the next orchestrator phase, the command verifies:

1. **Worker outputs exist** — `ls {scratch-dir}/phase-{N}/` shows expected files
2. **Worker outputs are non-empty** — each file has substantive content (not just headers)
3. **Manifest is well-formed** — has Status, Workers (if DISPATCH_WORKERS), and Parallel fields
4. **Decisions log has expected headers** — each prior phase section present

### Re-dispatch Rules

| Failure | Action |
|---------|--------|
| Worker output missing/empty | Re-dispatch once with same prompt. Skip worker on second failure, note gap. |
| Orchestrator dispatch fails | Re-dispatch once. Abort pipeline on second failure, report to PM. |
| Orchestrator manifest malformed | Re-dispatch once with format reminder. Abort on second failure. |
| Quality gate RETRY | Re-dispatch specific workers with gate feedback. Max one retry per topic. |
| decisions.md corrupted/truncated | Validate phase headers before next dispatch. Re-dispatch prior orchestrator phase if missing. |

---

## Orchestrator Dispatch Template

The command dispatches the orchestrator with this structure:

```
Phase: {N} — {phase name}

Pipeline: {pipeline type}
Target: {repo path / research topic / spec path}
Scratch directory: {scratch-dir}

{Phase-specific inputs — worker output paths, comparison targets, etc.}

Decisions log: {scratch-dir}/decisions.md
{If Phase > 0: "Read decisions.md first — it contains your prior phase judgments."}

Write your outputs to:
1. Dispatch manifest: {scratch-dir}/dispatch-manifest.md
2. Worker prompts: {scratch-dir}/prompts/{worker-id}.md (one per worker)
3. Decisions log: {scratch-dir}/decisions.md (READ existing content first, then APPEND your phase section)

{If final phase: "Write the final synthesis to: {output-path}. Set manifest status to COMPLETE."}
```

---

## Cleanup Nudge

When the command finishes, it reports:

```
Research complete. Paper trail at {archive-path} ({N} files).
If this research won't be revisited, you can delete the paper trail:
rm -rf {archive-path}
```

The EM acts on this or ignores it. No automatic deletion.

---

## Mid-Pipeline Recovery

If the pipeline crashes or the command context is compacted:

1. Scratch files + phase commits persist on disk
2. Re-invoking the command with the same arguments detects partial state:
   - Check which `phase-{N}/` directories exist with content
   - Read `decisions.md` for completed phase sections
   - Resume from the last complete phase
3. Tasks (Tasks API) survive compaction for manual recovery context
