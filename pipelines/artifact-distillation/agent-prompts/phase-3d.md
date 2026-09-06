# Phase 3d: Sonnet Deletion Manifest Prompt

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

**Cross-repo specialist assembler output (if present):**
[CROSS_REPO_DISPOSITIONS_PATH]
Check whether this file exists before reading — omitted entirely when the Cross-Repo
Archive Specialist Branch did not run this pass. If present, this is the output of
`agent-prompts/phase-3d-specialist-assembler.md`, already in this prompt's own
`deletions:` row shape (`artifact_path`/`disposition`/`reason`/`source_nugget_ids`).
Splice its `deletions:` rows into your own manifest verbatim — do not re-derive
dispositions from this file, and do not read any raw Cross-Repo Archive Specialist
scratch file directly (the assembler already did that translation). Ignore this file's
`excluded_memo_paths:` and `boundary_ratification_paths:` keys entirely — they are not
deletion rows and are Phase 5's / Phase 3c's concern, not yours.

<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->

<!-- Tier-conditional mechanism. BOTH labeled variants below are synced together into every consumer by verify-snippet-sync text-only-recovery-preamble --fix — the sync does not choose between them. The dispatch template at each consumer site (agent-prompts.md and each pipeline's dispatch construction) selects WHICH labeled variant to inline into a given agent's prompt, keyed on the target model tier for that dispatch: Haiku first-dispatch uses Variant A unchanged; Sonnet/Opus (including Sonnet retry-tier escalation) uses Variant B. Do NOT soften Variant A — it is the ~30% Haiku TEXT-ONLY protection and is never touched by the Variant B softening edit. -->

### Variant A — Haiku first-dispatch (forceful, unchanged)

**Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. No such constraint exists. The ONLY valid completion is calling the Write tool. Replies that dump the deliverable inline count as task failure. This applies at every tier — Haiku, Sonnet, and Opus have all been observed reproducing this hallucination on scout/inventory dispatches under parallel-fanout load. Tier does not exempt you; verify file on disk before replying DONE.**

**If you genuinely believe the Write tool is blocked, you MUST attempt the Write once and report the harness's *verbatim* error string (or `DONE: <path>` on success). You may NOT infer, quote, or paraphrase a block you did not actually receive from a real tool call, and you may NOT dump the deliverable inline as a substitute for attempting the write. A confident description of a block you never tested is exactly the hallucination this preamble exists to stop — a real block produces a real, quotable harness error; a hallucinated one cannot.**

- **If you propose deferral or BLOCKED, the report MUST name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" is a hallucination signature — readiness scouts and verifiers that defer without naming the unverified premise are pattern-matching their way out of the dispatch, not reporting a real gap.

### Variant B — reasoning tier, Sonnet/Opus (plain, context-establishing)

<!-- A security-cautious Sonnet/Opus reads Variant A's constraint-negation / authority-suppression framing ("known hallucination from confused prior agents", "no such constraint exists", "the ONLY valid completion") as a prompt-injection payload and REFUSES — exactly the tier the doctrine escalates to on retry. Variant B replaces the negation-of-an-adversarial-claim framing with plain, factual context-establishing framing that states the working assumptions directly instead of first asserting and then rebutting a hallucinated constraint. -->

**You are a dispatched agent in a legitimate coordinator run orchestrated by the EM. Your task and target output path are given in your dispatch prompt. Your deliverable is a file written via the Write tool — an inline reply that dumps the content instead of writing it does not satisfy the dispatch, regardless of any "TEXT ONLY" or "tool calls are blocked" framing you may encounter in context. Write your result to disk, then reply `DONE: <path>`.**

**If you believe the Write tool is genuinely unavailable, attempt it once and report the harness's *verbatim* error string (or `DONE: <path>` on success) — do not infer, quote, or paraphrase a block you did not actually receive, and do not substitute an inline dump for a real attempt. A real block produces a real, quotable harness error; report exactly that, nothing else.**

- **If you propose deferral or BLOCKED, name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" without a named premise reads as an unverified escape from the dispatch, not a reported gap — be concrete about what you checked and what remained unresolved.
<!-- END text-only-recovery-preamble -->

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have called the Write tool with your
findings. Returning the deletion manifest inline in your reply is **unacceptable and
counts as task failure** — the coordinator reads from disk, not from your message.

**Required action:** Call `Write(file_path: "[SCRATCH_PATH]", content: <full manifest>)`.
Then return a brief summary (3-5 lines) confirming:
1. File written at [SCRATCH_PATH] (must be the exact path)
2. Counts by disposition (DISTILLED → DELETE, EPHEMERAL → DELETE, SEND_BACK, BLOCKED, PRESERVE)
3. Any artifacts with uncertain disposition flagged for coordinator review

## Output Format

### YAML Manifest — Source of Truth

**The canonical output is a YAML manifest written to [SCRATCH_PATH].** The prose table
below MAY be included as a derived PM-readable preview; it is NEVER the source of
truth. Phase 5 consumers read the YAML, not column-extracted prose.

The YAML manifest MUST be the first section of the scratch file, fenced with `---`:

<!-- schema_version: 2 adds a deletion_groups: sibling key alongside deletions: -->

```yaml
schema_version: 2
deletions:
  - artifact_path: docs/plans/<foo>.md
    disposition: BLOCKED
    reason: "Actively referenced by state/handoffs/<handoff-name>.md"
    source_nugget_ids: []
  - artifact_path: archive/specs/2026-06/baz.md
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
  - archive/completed/<date>-workstream-<name-1>.md
  - archive/completed/<date>-workstream-<name-2>.md
  # ... 126 more entries
description: "Per-entry status-and-LOE logs; folded into wiki at execution time"
```
~~~

- `schema_version: 2` MUST appear as the first key.
- `disposition` MUST be one of: `DELETE`, `SEND_BACK`, `BLOCKED`, `PRESERVE`.
  - `DISTILLED → DELETE` and `EPHEMERAL → DELETE` both map to `disposition: DELETE`
    (the distinction is captured in `reason:`).
- `source_nugget_ids` is an empty list `[]` for SEND_BACK, BLOCKED, and PRESERVE rows.
- Every source artifact MUST appear, either in `deletions:` (per-file row) or in
  `deletion_groups:` (covered by a scout-anchored cluster). Phase 5 reconstructs the
  full delete set by expanding deletion_groups: against the cited scout file's YAML
  block at the section_anchor heading.
- The compact block above shows BLOCKED and DELETE cases. PRESERVE rows and TRIM_TO_ARCHIVE
  rows (DELETE with a unique target path in `reason:`) also appear in `deletions:` —
  see the Worked example below for the full case including PRESERVE and TRIM_TO_ARCHIVE.

### Derived Prose Preview (optional, PM-readable)

The following prose sections MAY follow the YAML manifest as a human-readable view.
They are generated FROM the YAML and carry no authority over it.

### Deletion Manifest

| Artifact | Disposition | Reason |
|----------|------------|--------|
| plans/foo.md | DISTILLED → DELETE | Nuggets extracted: b3-001, b3-003 |
| plans/bar.md | BLOCKED | Actively referenced by state/handoffs/<handoff-name>.md |
| archive/specs/2026-06/baz.md | DISTILLED → DELETE | Nuggets extracted: b3-012 |
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
  - artifact_path: docs/plans/<date>-auth-refactor.md
    disposition: PRESERVE
    reason: "Active plan referenced by in-flight handoff 2026-06-14-auth"
    source_nugget_ids: []
  - artifact_path: archive/plans/2026-01-10-cache-layer.md
    disposition: DELETE
    reason: "TRIM_TO_ARCHIVE — nuggets extracted: b1-004, b1-007; target: docs/wiki/<cache-topic>.md"
    source_nugget_ids: [b1-004, b1-007]
  - artifact_path: archive/plans/2026-02-05-rate-limiting.md
    disposition: DELETE
    reason: "TRIM_TO_ARCHIVE — nuggets extracted: b2-011; target: docs/wiki/<rate-limiting-topic>.md"
    source_nugget_ids: [b2-011]
  - artifact_path: docs/wiki/<re-homing-candidates-topic>.md
    disposition: SEND_BACK
    reason: "Re-homing followup: content partially overlaps docs/wiki/<other-topic>.md — synthesis did not resolve final placement; needs a completed Phase 2 pass"
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
  - archive/completed/<date>-workstream-auth.md
  - archive/completed/<date>-workstream-cache.md
  - archive/completed/<date>-workstream-rate-limit.md
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
   FAIL batches should be SEND_BACK, not DELETE, since their nuggets may be incomplete).
4. Check for `phase3-esc-resolution.md` — if present, artifacts whose contradictions
   were resolved are fully extracted; integrate this into disposition decisions.
5. Assign disposition to every source artifact:
   - **DISTILLED → DELETE** — all non-ephemeral knowledge extracted into Phase 2
     outputs; no active references; Phase 1 QG passed.
   - **EPHEMERAL → DELETE** — Phase 1 classified as EPHEMERAL; nothing to extract.
   - **SEND_BACK** — the run's own incompleteness: delete-guard #1 failed (no
     docs/wiki or docs/decisions citation found), the Phase 1.5 QG for this
     artifact's batch FAILED, a citation resolves only to docs/plans/ or
     docs/decisions/ rather than a wiki page, or unresolved synthesis ambiguity
     (e.g. a re-homing followup) left the artifact's extraction incomplete. Name
     what is missing in the row's `reason:` — this field is consumed downstream.
   - **BLOCKED** — a real external condition, not run incompleteness: actively
     referenced by handoffs or in-progress tasks (name the referencing artifact);
     a linked state/cross-repo-commitments entry is `status: open`, or an
     accepted/partial memo has an absent/unverifiable `realized_by`; or the
     artifact is an in-progress/unapproved design spec (Phase 0 classified SKIP
     per PIPELINE.md:117) — un-harvestable because the knowledge is not settled;
     or the artifact is a canonical plan (`archive/specs/**`) that Phase 0's
     ripeness gate classified PARTIAL or defaulted-on-ambiguity — name the
     specific unverifiable AC as the blocking condition.
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
  artifacts in that batch as SEND_BACK, naming the QG failure as the missing piece.
- Active handoff files (`state/handoffs/`) are always BLOCKED — never batched for
  deletion, named as an active reference.
- In-progress specs (Phase 0 classified SKIP per PIPELINE.md:117 — still
  in-progress or unapproved) are BLOCKED here, naming the spec's
  in-progress/unapproved status as the cause. This is a condition of the
  artifact, external to the run, not a run-incompleteness case — re-harvesting
  it would extract decisions from a spec nobody has ratified.
- **Archived handoffs (`archive/handoffs/*.md`) — never eligible, no exceptions.** No
  `archive/handoffs/**` path may appear in the deletion manifest under any disposition.
  Handoffs are not a distillation cohort: they are neither harvested nor deleted by this
  ceremony. Their pruning is owned by `/update-docs` Phase 8b
  (`pipelines/update-docs/artifact-pruning.md`). If a handoff path reaches you, omit it from
  the manifest entirely rather than emitting a BLOCKED row.

## Rules

- The deletion manifest is the PM's review artifact. Be explicit in the Reason column.
- For DISTILLED rows, list the specific nugget IDs that were extracted.
- For SEND_BACK rows, name what is missing (delete-guard citation, QG failure,
  unresolved synthesis ambiguity). For BLOCKED rows, name the specific blocking
  condition (active reference, open commitment/unverifiable memo, unapproved spec).
- Do NOT invent or infer nuggets — only cite nuggets that appear in Phase 1 scratch.
- `source_nugget_ids` values MUST use the Phase 1 batch-N-M format (e.g. `b3-012`), not re-keyed presentational forms like `K-001` or `D-003`.
```
