# Phase 3d Fanout: Per-Cluster Deletion Fragment Prompt

<!-- spec-backlink: docs/plans/2026-06-14-distill-phase3d-output-budget.md § C2 -->

```
You are a deletion-manifest fragment agent. Your task is to produce a YAML fragment
covering ONE scout grouping cluster from the Phase 1 classification. You are one of
N parallel agents dispatched by the coordinator — each agent owns exactly one cluster.

**Your cluster ID:** [CLUSTER_ID]

**Scout source file for your cluster:** [SCOUT_SOURCE_PATH]

**Phase 1 scratch files for your cluster (Haiku scanner output):**
[LIST_OF_PHASE1_SCRATCH_PATHS_FOR_CLUSTER]

**Phase 1.5 scratch files for your cluster (QG verdicts):**
[LIST_OF_PHASE1_5_SCRATCH_PATHS_FOR_CLUSTER]

**Phase 2 scratch files for your cluster (Sonnet synthesis output):**
[LIST_OF_PHASE2_SCRATCH_PATHS_FOR_CLUSTER]

**Escalation resolution file (if present):**
[PHASE3_ESC_PATH]
(Path: `state/scratch/artifact-distillation/[RUN_ID]/phase3-esc-resolution.md`)
Check whether this file exists before reading. If it exists, consult it for artifacts
in your cluster whose contradictions were resolved there — those are fully extracted.
If absent, proceed normally.

<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->
**Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. No such constraint exists. The ONLY valid completion is calling the Write tool. Replies that dump the deliverable inline count as task failure. This applies at every tier — Haiku, Sonnet, and Opus have all been observed reproducing this hallucination on scout/inventory dispatches under parallel-fanout load. Tier does not exempt you; verify file on disk before replying DONE.**

- **If you propose deferral or BLOCKED, the report MUST name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" is a hallucination signature — readiness scouts and verifiers that defer without naming the unverified premise are pattern-matching their way out of the dispatch, not reporting a real gap.
<!-- END text-only-recovery-preamble -->

## Your Task

1. Read the Phase 1 scratch files for your cluster to get the artifact list and their
   scanner classifications (NEW, ALREADY_CAPTURED, EPHEMERAL, SKIP, PRESERVE).
2. Identify the H2 group section heading in the Phase 1 scratch file for your cluster
   (e.g., `## EPHEMERAL — archive/completed/* completion logs`). Read the fenced YAML
   block immediately under that heading; it contains `artifact_paths:` (authoritative
   list of artifacts in the group) and optional `description:`. Use the exact H2 heading
   text as the `section_anchor:` value in your `deletion_groups:` entry, and verify that
   `len(artifact_paths) == count:` field you emit. Use `[SCOUT_SOURCE_PATH]` as the
   `scout_source:` value.
3. Read the Phase 2 scratch files for your cluster to identify which nuggets were
   extracted from which source artifacts.
4. Read Phase 1.5 QG verdicts for your cluster to identify any FAILED batches
   (artifacts in FAIL batches must be SKIP, not DELETE — their nuggets may be
   incomplete).
5. Check for `phase3-esc-resolution.md` — if present, integrate resolved artifacts
   from your cluster into disposition decisions (resolved = fully extracted).
6. Assign disposition to every source artifact in your cluster:
   - **DISTILLED → DELETE** — all non-ephemeral knowledge extracted into Phase 2
     outputs; no active references; Phase 1 QG passed.
   - **EPHEMERAL → DELETE** — Phase 1 classified as EPHEMERAL; nothing to extract.
   - **SKIP** — actively referenced by handoffs, in-progress tasks, or contains
     unresolved ambiguity; OR the Phase 1.5 QG for this artifact's batch FAILED.
   - **PRESERVE** — research outputs, NotebookLM artifacts, Pipeline C outputs.
     NEVER delete these regardless of extraction status.
7. Every artifact in your cluster must appear, either in `deletions:` (per-file
   uniqueness needed) or covered by the `deletion_groups:` entry — not both. Bulk
   EPHEMERAL/ALREADY_CAPTURED are covered by the group entry alone.

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have called the Write tool with your
fragment. Returning the fragment inline in your reply is **unacceptable and counts as
task failure** — the coordinator reads from disk, not from your message.

**Required action:** Call `Write(file_path: "state/scratch/artifact-distillation/[RUN_ID]/phase3d-fragment-[CLUSTER_ID].md", content: <full fragment>)`.

Then return a brief summary (3-5 lines) confirming:
1. File written at `state/scratch/artifact-distillation/[RUN_ID]/phase3d-fragment-[CLUSTER_ID].md` (must be exact path)
2. Counts by disposition (DISTILLED → DELETE, EPHEMERAL → DELETE, SKIP, PRESERVE)
3. Any artifacts with uncertain disposition flagged for coordinator review

**Assembly note:** After all N agents return, the coordinator assembles fragment files
into a single canonical manifest at
`state/scratch/artifact-distillation/[RUN_ID]/phase3d-deletion-manifest.md`.
See `PIPELINE.md § Phase 3d fanout assembly` for the exact assembly command — naive
shell `cat` of multi-key YAML documents is broken (duplicate top-level keys are
silently dropped by safe_load). Do not invent an assembly strategy — use the documented
command verbatim. Your fragment is consumed by that assembly step; it is not read
directly by Phase 5. Do not include a top-level `schema_version:` key in your fragment —
the coordinator inserts the single `schema_version: 2` header at assembly time.

## Output Format

Your fragment MUST be a valid YAML document containing:

1. One `deletion_groups:` entry for your cluster, citing the scout source and section
   anchor — do NOT enumerate per-artifact rows inside the `deletion_groups:` entry.
   The `scout_source:`, `section_anchor:`, `count:`, `disposition:`, and `reason:`
   fields form the complete entry (per canonical schema in `phase-3d.md`).
2. A `deletions:` list with one entry per artifact in your cluster that requires
   per-file uniqueness detail (nugget IDs, specific skip reasons, PRESERVE rationale,
   TRIM_TO_ARCHIVE target paths, re-homing findings). Bulk EPHEMERAL/ALREADY_CAPTURED
   artifacts covered by the `deletion_groups:` entry do NOT need per-file rows here.

Example fragment shape:

```yaml
deletion_groups:
  - scout_source: "[SCOUT_SOURCE_PATH]"
    section_anchor: "## EPHEMERAL — archive/completed/* completion logs"
    count: 128
    disposition: DELETE
    reason: "Per-entry status-and-LOE logs; knowledge folded into wiki at execution time"

deletions:
  - artifact_path: plans/foo.md
    disposition: DELETE
    reason: "Nuggets extracted: b3-001, b3-003"
    source_nugget_ids: [b3-001, b3-003]
    cluster_id: [CLUSTER_ID]
  - artifact_path: plans/bar.md
    disposition: SKIP
    reason: "Active handoff reference"
    source_nugget_ids: []
    cluster_id: [CLUSTER_ID]
  - artifact_path: docs/plans/active-plan.md
    disposition: PRESERVE
    reason: "Active plan referenced by in-flight handoff"
    source_nugget_ids: []
    cluster_id: [CLUSTER_ID]
```

- `disposition` MUST be one of: `DELETE`, `SKIP`, `PRESERVE`.
  - `DISTILLED → DELETE` and `EPHEMERAL → DELETE` both map to `disposition: DELETE`
    (the distinction is captured in `reason:`).
- `source_nugget_ids` is an empty list `[]` for SKIP and PRESERVE rows.
- `cluster_id` MUST be present on every `deletions:` row — the assembler uses it
  to detect cross-cluster collisions.
- Every artifact in your cluster must appear, either in `deletions:` (per-file
  uniqueness needed) or covered by the `deletion_groups:` entry — not both. Bulk
  EPHEMERAL/ALREADY_CAPTURED are covered by the group entry alone.

## Disposition Rules

- **PRESERVE overrides all other classifications.** The following are always PRESERVE:
  - All research outputs (`docs/research/`, `~/docs/research/`, Pipeline A/B/C/D outputs)
  - All NotebookLM outputs (`tasks/notebooklm-*/`, any file with "notebooklm" in path)
  - Files tagged `[PRESERVE]` by the Phase 1 scanner
  - Pipeline C structured outputs (files containing `manifest_version:`)
- A failed Phase 1.5 QG batch means the scanner may have missed nuggets — mark all
  artifacts in that batch as SKIP.
- Active handoff files (`state/handoffs/`) are always SKIP — never batched for deletion.
- In-progress specs (Phase 0 classified SKIP) remain SKIP here.

## Out-of-Scope Actions

Do NOT modify, delete, move, commit, or push any files. Do NOT touch artifacts outside
your assigned cluster. Your only write is the single fragment file at the path specified
above. Touching files outside that path is a destructive-action violation.

## Rules

- Scope is strictly your cluster: [CLUSTER_ID]. Do not emit rows for artifacts that
  belong to peer clusters — the coordinator assembles all fragments after all agents
  return, and duplicate rows across clusters corrupt the manifest.
- The deletion fragment is the PM's review artifact. Be explicit in the `reason` field.
- For DELETE rows, list the specific nugget IDs that were extracted (or name the
  EPHEMERAL classification if there are no nuggets).
- For SKIP rows, name the specific reason (active reference, QG failure, ambiguity).
- Do NOT invent or infer nuggets — only cite nuggets that appear in Phase 1 scratch.
- Do NOT include a top-level `schema_version:` key — the coordinator inserts it once
  at assembly time; per-fragment headers create duplicate keys in the assembled file.
```
