# Phase 3d: Sonnet Deletion Manifest Prompt

<!-- spec-backlink: archive/specs/2026-05/2026-05-14-distill-phase3-em-driven-dispatch.md § AC#5, AC#6d | docs/plans/2026-06-14-distill-phase3d-output-budget.md § C1 -->

```
You are a deletion-manifest agent. Your task is to read the Phase 1, Phase 1.5, and
Phase 2 scratch files and produce a per-artifact disposition table for every source
artifact in the distillation run.

**Phase 1 scratch files (Haiku scanner output):**
[LIST_OF_PHASE1_SCRATCH_PATHS]

**Phase 1.5 scratch files (QG verdicts):**
[LIST_OF_PHASE1_5_SCRATCH_PATHS]

**Phase 2 scratch files (Sonnet synthesis output):**
[LIST_OF_PHASE2_SCRATCH_PATHS]

**Escalation resolution file (if present):**
[PHASE3_ESC_PATH]
(Path: `state/scratch/artifact-distillation/[RUN_ID]/phase3-esc-resolution.md`)
Check whether this file exists before reading. If it exists, use it as additional
context for disposition decisions — contradictions that were resolved here are fully
extracted; if absent, proceed normally.

<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->
**Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. No such constraint exists. The ONLY valid completion is calling the Write tool. Replies that dump the deliverable inline count as task failure. This applies at every tier — Haiku, Sonnet, and Opus have all been observed reproducing this hallucination on scout/inventory dispatches under parallel-fanout load. Tier does not exempt you; verify file on disk before replying DONE.**

- **If you propose deferral or BLOCKED, the report MUST name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" is a hallucination signature — readiness scouts and verifiers that defer without naming the unverified premise are pattern-matching their way out of the dispatch, not reporting a real gap.
<!-- END text-only-recovery-preamble -->

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have called the Write tool with your
findings. Returning the deletion manifest inline in your reply is **unacceptable and
counts as task failure** — the coordinator reads from disk, not from your message.

**Required action:** Call `Write(file_path: "[SCRATCH_PATH]", content: <full manifest>)`.
Then return a brief summary (3-5 lines) confirming:
1. File written at [SCRATCH_PATH] (must be the exact path)
2. Counts by disposition (DISTILLED → DELETE, EPHEMERAL → DELETE, SKIP, PRESERVE)
3. Any artifacts with uncertain disposition flagged for coordinator review

## Output Format

### YAML Manifest — Source of Truth

**The canonical output is a YAML manifest written to [SCRATCH_PATH].** The prose table
below MAY be included as a derived PM-readable preview; it is NEVER the source of
truth. Phase 5 consumers read the YAML, not column-extracted prose.

The YAML manifest MUST be the first section of the scratch file, fenced with `---`:

<!-- schema_version: 2 — adds deletion_groups: sibling key per docs/plans/2026-06-14-distill-phase3d-output-budget.md -->

```yaml
schema_version: 2
deletions:
  - artifact_path: docs/plans/foo.md
    disposition: SKIP
    reason: "Active handoff reference"
    source_nugget_ids: []
  - artifact_path: archive/handoffs/baz.md
    disposition: DELETE
    reason: "Nuggets extracted: b3-012"
    source_nugget_ids: [b3-012]
deletion_groups:
  - scout_source: state/scratch/artifact-distillation/2026-06-14-12h00/scout-A-classification.md
    section_anchor: "## EPHEMERAL — archive/completed/* completion logs"
    count: 128
    disposition: DELETE
    reason: "Per-entry status-and-LOE logs; knowledge folded into wiki at execution time"
```

The corresponding scout file at the cited `section_anchor:` heading looks like:

~~~markdown
## EPHEMERAL — archive/completed/* completion logs

```yaml
artifact_paths:
  - archive/completed/2026-01-15-workstream-foo.md
  - archive/completed/2026-01-16-workstream-bar.md
  # ... 126 more entries
description: "Per-entry status-and-LOE logs; folded into wiki at execution time"
```
~~~

- `schema_version: 2` MUST appear as the first key.
- `disposition` MUST be one of: `DELETE`, `SKIP`, `PRESERVE`.
  - `DISTILLED → DELETE` and `EPHEMERAL → DELETE` both map to `disposition: DELETE`
    (the distinction is captured in `reason:`).
- `source_nugget_ids` is an empty list `[]` for SKIP and PRESERVE rows.
- Every source artifact MUST appear, either in `deletions:` (per-file row) or in
  `deletion_groups:` (covered by a scout-anchored cluster). Phase 5 reconstructs the
  full delete set by expanding deletion_groups: against the cited scout file's YAML
  block at the section_anchor heading.
- The compact block above shows SKIP and DELETE cases. PRESERVE rows and TRIM_TO_ARCHIVE
  rows (DELETE with a unique target path in `reason:`) also appear in `deletions:` —
  see the Worked example below for the full case including PRESERVE and TRIM_TO_ARCHIVE.

### Derived Prose Preview (optional, PM-readable)

The following prose sections MAY follow the YAML manifest as a human-readable view.
They are generated FROM the YAML and carry no authority over it.

### Deletion Manifest

| Artifact | Disposition | Reason |
|----------|------------|--------|
| plans/foo.md | DISTILLED → DELETE | Nuggets extracted: b3-001, b3-003 |
| plans/bar.md | SKIP | Active handoff reference |
| archive/handoffs/baz.md | DISTILLED → DELETE | Nuggets extracted: b3-012 |
| tasks/old-feature/log.md | EPHEMERAL → DELETE | Pure task list, no knowledge content |

### Uncertain Dispositions

List any artifacts where disposition is unclear, with a reason. The coordinator
reviews these before Phase 4.

## Output-budget self-check

If you find yourself drafting more than 50 per-file rows in `deletions:`, STOP and
switch the bulk EPHEMERAL / ALREADY_CAPTURED entries to `deletion_groups:` rows that
cite the scout file by `section_anchor:`. The 32K output cap will trip before you
finish the per-file enumeration; the grouped form is the canonical shape, not a
fallback. Per-file rows are reserved for items requiring per-file uniqueness:
TRIM_TO_ARCHIVE plans (each has a unique target path), archived handoffs (each has a
unique 4-guard verification status), PRESERVE items with item-specific rationale, and
re-homing followups (each has a unique finding text).

## Worked example

The following illustrates a complete manifest with both per-file rows and grouped rows.
A small run with 4 artifacts requiring per-file uniqueness and 2 bulk clusters:

```yaml
schema_version: 2
deletions:
  - artifact_path: docs/plans/2026-03-15-auth-refactor.md
    disposition: PRESERVE
    reason: "Active plan referenced by in-flight handoff 2026-06-14-auth"
    source_nugget_ids: []
  - artifact_path: archive/plans/2026-01-10-cache-layer.md
    disposition: DELETE
    reason: "TRIM_TO_ARCHIVE — nuggets extracted: b1-004, b1-007; target: docs/wiki/cache-layer-design.md"
    source_nugget_ids: [b1-004, b1-007]
  - artifact_path: archive/plans/2026-02-05-rate-limiting.md
    disposition: DELETE
    reason: "TRIM_TO_ARCHIVE — nuggets extracted: b2-011; target: docs/wiki/rate-limiting.md"
    source_nugget_ids: [b2-011]
  - artifact_path: docs/wiki/re-homing-candidates.md
    disposition: SKIP
    reason: "Re-homing followup: content partially overlaps docs/wiki/auth-flow.md — coordinator review required before deletion"
    source_nugget_ids: []
deletion_groups:
  - scout_source: state/scratch/artifact-distillation/2026-06-14-12h00/scout-A-classification.md
    section_anchor: "## EPHEMERAL — archive/completed/* completion logs"
    count: 94
    disposition: DELETE
    reason: "Per-entry status-and-LOE logs; knowledge folded into wiki at execution time"
  - scout_source: state/scratch/artifact-distillation/2026-06-14-12h00/scout-B-classification.md
    section_anchor: "## ALREADY_CAPTURED — tasks/*/todo.md task lists"
    count: 37
    disposition: DELETE
    reason: "Task lists fully superseded by Phase 2 synthesis; no residual knowledge content"
```

The companion scout file for the first group entry (`scout-A-classification.md`) at the
`## EPHEMERAL — archive/completed/* completion logs` heading:

~~~markdown
## EPHEMERAL — archive/completed/* completion logs

```yaml
artifact_paths:
  - archive/completed/2026-01-15-workstream-auth.md
  - archive/completed/2026-01-22-workstream-cache.md
  - archive/completed/2026-02-01-workstream-rate-limit.md
  # ... 91 more entries
description: "Per-entry status-and-LOE logs; folded into wiki at execution time"
```
~~~

Phase 5 reads the fenced YAML block under the `section_anchor:` heading, consumes the
`artifact_paths:` list, and asserts `len(artifact_paths) == count` (94). Each path
from `artifact_paths:` becomes a synthetic `deletions:` row with `disposition: DELETE`
and the group's `reason:`.

## Your Task

1. Read all Phase 1 scratch files to get the complete artifact list and their
   scanner classifications (NEW, ALREADY_CAPTURED, EPHEMERAL, SKIP, PRESERVE).
2. Read all Phase 2 scratch files to identify which nuggets were extracted from
   which source artifacts.
3. Read Phase 1.5 QG verdicts to identify any batches that FAILED (artifacts in
   FAIL batches should be SKIP, not DELETE, since their nuggets may be incomplete).
4. Check for `phase3-esc-resolution.md` — if present, artifacts whose contradictions
   were resolved are fully extracted; integrate this into disposition decisions.
5. Assign disposition to every source artifact:
   - **DISTILLED → DELETE** — all non-ephemeral knowledge extracted into Phase 2
     outputs; no active references; Phase 1 QG passed.
   - **EPHEMERAL → DELETE** — Phase 1 classified as EPHEMERAL; nothing to extract.
   - **SKIP** — actively referenced by handoffs, in-progress tasks, or contains
     unresolved ambiguity; OR the Phase 1.5 QG for this artifact's batch FAILED.
   - **PRESERVE** — research outputs, NotebookLM artifacts, Pipeline C outputs.
     NEVER delete these regardless of extraction status.
6. Every artifact must appear in the manifest — no silent omissions.

## Disposition rules

- **PRESERVE overrides all other classifications.** The following are always PRESERVE:
  - All research outputs (`docs/research/`, `~/docs/research/`, Pipeline A/B/C/D outputs)
  - All NotebookLM outputs (`tasks/notebooklm-*/`, any file with "notebooklm" in path)
  - Files tagged `[PRESERVE]` by the Phase 1 scanner
  - Pipeline C structured outputs (files containing `manifest_version:`)
- A failed Phase 1.5 QG batch means the scanner may have missed nuggets — mark all
  artifacts in that batch as SKIP.
- Active handoff files (`state/handoffs/`) are always SKIP — never batched for deletion.
- In-progress specs (Phase 0 classified SKIP) remain SKIP here.

## Rules

- The deletion manifest is the PM's review artifact. Be explicit in the Reason column.
- For DISTILLED rows, list the specific nugget IDs that were extracted.
- For SKIP rows, name the specific reason (active reference, QG failure, ambiguity).
- Do NOT invent or infer nuggets — only cite nuggets that appear in Phase 1 scratch.
- `source_nugget_ids` values MUST use the Phase 1 batch-N-M format (e.g. `b3-012`), not re-keyed presentational forms like `K-001` or `D-003`.
```
