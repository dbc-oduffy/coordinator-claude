---
description: "Distill accumulated session artifacts (plans, handoffs, completed work) into evergreen wiki documents (docs/wiki/, docs/decisions/); trim + archive canonical specs to archive/specs/; delete scaffolding. Extract knowledge and preserve provenance before pruning — the pipeline that bridges artifact-consolidation and wiki maintenance."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[--dry-run] [--no-delete] [path]"
---

# Distill — Artifact Distillation Pipeline

Extract knowledge from accumulated session artifacts into evergreen wiki documents. Trim and archive canonical specs; delete scaffolding; write or update wiki entries. The archive is the long-term record; the wiki is the navigable present.

**Three categories, three fates:**

| Artifact | Fate | Rationale |
|---|---|---|
| Canonical plan / spec (`docs/plans/*.md`) | **Trim → move to `archive/specs/`** | Keep the "how" greppable; strip review-applied wrappers and side-channel meta only after re-homing any constraints they introduced. |
| Enriched stubs, reviewer outputs, integrator triage, docs-checker reports | **Delete** | Pure scaffolding. Recoverable from git via distillation log. |
| Wiki entries (`docs/wiki/*.md`) | **Write/update** | What-and-why summary. Carries provenance frontmatter. |

**Reference:** Full pipeline design in `${CLAUDE_PLUGIN_ROOT}/pipelines/artifact-distillation/PIPELINE.md`. Agent prompt templates in the same directory's `agent-prompts.md`.

**Announce at start:** "I'm running `/distill` to extract knowledge from [N artifacts / artifacts in path] into wiki documents."

**For bulk pruning without knowledge extraction, use `coordinator:artifact-consolidation` instead.**

---

## Arguments

`$ARGUMENTS` may include any combination of:

**`--dry-run`**
Run Phases 0-3 only. Preview extraction results and the deletion manifest, but apply nothing to disk. Presents the summary at Phase 4 and stops. Use to verify what would be extracted before committing.

**`--no-delete`**
Apply wiki updates (Phases 0-5 write steps), but skip scaffolding deletion AND skip moving specs to `archive/specs/` (specs stay in `docs/plans/`). Wiki writes still apply.

**`--allow-drop`**
Bypass the negative-AC halt for this run after EM eyeballs the diff and confirms no semantic loss. Logs the bypass to distillation-log.md Manual Review section for audit.
<!-- Review: Patrik R3 — F3: --allow-drop was referenced in the set-diff section but absent from Arguments; F6: dropped stale "Previously:" migration commentary from --no-delete -->

**`[path]`**
Scope the inventory to a specific subdirectory. Only artifacts under that path are processed. Example: `/distill tasks/camera-refactor/` distills a single feature directory.

### Examples

```
/distill                          # full repo distillation
/distill --dry-run                # preview only, no writes
/distill --no-delete              # extract wiki content, keep source files in place
/distill tasks/camera-refactor/   # scope to a single feature dir
/distill --dry-run plans/         # preview what would be extracted from plans/
```

---

## Phase Overview

Full phase definitions, dispatch instructions, scratch path conventions, and failure modes are in `PIPELINE.md`. This is a summary for orientation.

```
Phase 0 (Coordinator) → Phase 1 (Haiku ×N, parallel) → Phase 1.5 (Haiku ×N, QG)
  → [Clustering] → Phase 2 (Sonnet ×M, parallel) → Phase 3 (Opus, single)
  → Phase 4 (PM gate) → Phase 5 (Coordinator, apply + trim/archive + delete scaffolding)
```

| Phase | Model | Purpose |
|-------|-------|---------|
| **Phase 0** | Coordinator | Inventory artifacts, catalog formats, read existing wiki, group into batches, generate run ID |
| **Phase 1** | Haiku (parallel) | Scan each batch — extract knowledge nuggets (`[DECISION]`, `[KNOWLEDGE]`, `[EPHEMERAL]`, `[AMBIGUOUS]`) |
| **Phase 1.5** | Haiku (parallel) | Quality gate — verify Phase 1 coverage, template compliance, and path spot-checks |
| **Clustering** | Coordinator or Haiku | Regroup nuggets from input-batch ordering to output-topic ordering |
| **Phase 2** | Sonnet (parallel) | One agent per guide topic — synthesize nuggets into guide content and decision records |
| **Phase 3** | Opus (single) | Cross-reference assembly — resolve contradictions, deduplicate decision records, produce deletion manifest (does NOT apply delta ops) |
| **Phase 4** | Coordinator | PM approval gate — present deletion manifest, wait for explicit approval |
| **Phase 5** | Coordinator | Apply wiki writes, trim + archive canonical specs (including rationale extraction), delete scaffolding, update distillation log, run link-heal pass |
<!-- Review: Patrik R3 — F1: Phase 5 row omitted Decision Rationale extraction; an executor scanning the overview without reading 5a could miss it -->

**If `--dry-run`:** Phases 4-5 are skipped. The pipeline stops after Phase 3 and presents the summary.

**If `--no-delete`:** Phase 5 applies wiki writes and commits, but skips scaffolding deletion and spec archival.

---

## Phase 5 — Apply, Trim + Archive, Delete, Heal

Phase 5 has four major sub-steps. They run in order; each depends on the prior.

### 5a. Spec Trim + Archive — Structural Rubric

Canonical specs (`docs/plans/*.md`) are trimmed to remove post-review scaffolding and moved to `archive/specs/YYYY-MM-DD-<name>.md`. Do not delete — move. The trimmed spec remains greppable by RAG.

**ALLOWLIST sections — survive verbatim:**
- Goal
- Premise
- Acceptance Criteria
- File Lists
- Decision Records / Decisions Made
- Function Signatures / API Contracts
- Sequencing
- Out-of-Scope
- Risks (if normative — i.e., describes a constraint the implementation must respect)

**DENYLIST sections — strip after re-homing + rationale extraction:**
- "Reviewer Plan"
- "Patrik Round N Findings"
- "Camelia/Sid Findings"
- "Integrator Triage"
- "Docs-Checker Pass"
- "Open Questions (resolved)"
- "Scope-Expansion Side-Channel" / "Heavy-Investment Pass" wrappers

**MIDDLE — keep + flag for EM eyeball in dry-run:** any section heading not matching either list above. Do not auto-strip; surface in dry-run for EM decision.

**Re-homing step (mandatory before any DENYLIST section is stripped):**

For every DENYLIST section, scan it for content introducing a constraint, AC, or decision that does not appear in any ALLOWLIST section. Each such item must be re-homed into the appropriate ALLOWLIST section (typically Acceptance Criteria or Decisions Made) before the wrapper is stripped. Re-homing produces a diff in the trim preview that the EM reviews at Phase 4. Do not strip before the EM has approved the re-homing diff.

**Decision Rationale extraction (required, not optional — per Camelia F3):**

Re-homing handles structural items (constraints, ACs, decisions stated as such). It does NOT capture conversational *why-we-chose-X-over-Y* rationale that lives in review threads — exactly the kind of question retrieval most often surfaces. Before stripping any DENYLIST section, extract decision rationale into a dedicated `## Decision Rationale` section of the archived spec (or a sibling `archive/specs/<name>-rationale.md` if the spec is long). Format: one paragraph per decision, naming the alternatives considered and why this one won, citing reviewer findings by reference if relevant. This section is indexed by RAG and is retrievable by future EMs without `git show`.

**Procedure:**
1. Capture `last_sha` of original verbose form before any mutation: `git log -1 --format=%H -- <path>`.
2. Stage re-homing additions into ALLOWLIST sections (do not yet strip DENYLIST). EM reviews and approves the re-homing diff.
3. Extract Decision Rationale from DENYLIST sections (still in place) into `## Decision Rationale` section.
4. Strip DENYLIST sections — runs only after steps 2 + 3 are complete and EM-approved.
5. Review MIDDLE sections for EM approval.
6. Move (not copy) trimmed result to `archive/specs/YYYY-MM-DD-<name>.md`.
<!-- Review: Patrik R3 — F0: steps 2+3 both operate on the pre-strip spec; step 3 sources rationale FROM DENYLIST sections, so stripping (step 4) must follow both; preconditions made explicit -->

---

### 5b. Provenance Frontmatter on Wiki Entries

Every wiki entry produced by or updated during a distill run that summarizes a now-archived spec must carry provenance frontmatter:

```yaml
provenance:
  - archived_spec: archive/specs/2026-04-29-port-patterns-implementation.md
    original_path: docs/plans/2026-04-29-port-patterns-implementation.md
    last_verbose_sha: acc49ed5
    distilled: 2026-04-29
```

**Retrieval recipes (in order of preference):**
1. Read the trimmed archived spec at `archive/specs/<name>.md` — covers structure, decisions, and rationale.
2. For verbose original (review history, integrator chatter): `git show <last_verbose_sha>:<original_path>`.

---

### 5c. Distillation Log — Schema-Pinned, Append-Only

Path: `tasks/distillation-log.md` (per-project). Created on first distill run; populated with new rows on every subsequent run.

**Schema header — executor MUST preserve verbatim when writing to the log:**

```
# Distillation Log
# Append-only. Each row = one deleted scaffold OR one archived spec.
# Columns: date | action | path | last_sha | belongs_to_spec | reason
#
# `reason` field MUST be domain-prose using CONTEXT.md vocabulary, not a process tag.
#   Bad:  "scaffolding"
#   Good: "integrator triage resolving async-run wrapper conflict in port-patterns FastMCP transport"
# Minimum: ≥8 words. If CONTEXT.md exists, ≥1 CONTEXT.md term required.
```

**Append-only contract:** Read existing rows first. Append new rows. NEVER rewrite existing rows. Row count is monotonically non-decreasing; strictly increases on any run that deletes scaffolding or archives a spec. This is an AC.
<!-- Review: Patrik R3 — F5: "strictly increase" fails on a no-op run; reworded to monotonically non-decreasing with strict increase on runs that actually act -->

**Mirroring:** For highest-value scaffolds (the canonical spec itself), the distillation log row is also mirrored into the wiki provenance frontmatter as redundancy.

**Why prose-shaped reason fields:** The log itself becomes index-bait. RAG indexes the on-disk filesystem; a log row reading "scaffolding" is invisible to retrieval, but a row reading "integrator triage resolving async-run wrapper conflict in port-patterns FastMCP transport" surfaces on a query about that conflict and gives the future EM a `last_sha` to retrieve the verbose original. The log carries history forward into the retrieval surface — cheapest mitigation for the "git history is out-of-band for RAG" recall hole.

**Vocabulary discipline AC (per Camelia F2):** On a CONTEXT.md-bearing repo, the manual-review log section of `tasks/distillation-log.md` must either flag ≥1 vocabulary-drift hit in sampled executor output OR explicitly attest zero drift after sampling N≥3 modules. Without this, vocabulary discipline is aspirational rather than validated.

---

### 5d. Link-Healing Pass — Expanded Coverage

After specs are moved and scaffolding is deleted, stale references exist across the codebase. The link-heal pass finds and rewrites them.

**Targets to rewrite:**
- Canonical spec path (`docs/plans/foo.md`, with or without `§` section refs) → `archive/specs/<new>.md`
- Deleted stub paths (`tasks/<feature>/stubs/*.md`) → wiki target with parenthetical `(formerly tasks/<feature>/stubs/P1-A.md @ <sha>)`
- Intra-spec references inside the archived spec itself pointing to sibling stubs that were just deleted (second pass on the trimmed spec after archival)

**Tooling:** `ripgrep --multiline --multiline-dotall` covering file types `md, json, yaml, yml, ps1, sh, py, ts, js, txt`. Scan: `.claude/`, `tasks/`, `docs/`, `archive/`, plugin dirs, repo root configs.
<!-- Review: Patrik R3 — F4: plain --multiline does not make . match newlines; --multiline-dotall required for cross-line patterns -->

**Heal-log:** Under a `## Manual Review` section in `tasks/distillation-log.md`, write EVERY unmatched-but-suspicious hit — anything containing `docs/plans/`, `tasks/<feature>/stubs/`, or the deleted-path basenames — for EM eyeball. The EM reviews the Manual Review section before declaring the run complete.

---

## Negative AC — Silent-Loss Guard (Set-Diff Form)

**Dry-run emits a content-drop diff.** The halt-condition is set-diff, not raw match.

An AC-shaped token line (`MUST`, `SHALL`, `AC:`, `Decision:`, `Constraint:`) in the drop-list halts dry-run ONLY if no semantically-equivalent line exists in the re-homed additions OR in surviving ALLOWLIST sections.

**Implementation:** Normalize whitespace and lowercase the token-bearing lines. Compute the set-diff of drop-tokens vs kept-tokens. Halt on non-empty difference.

This prevents the muscle-memory bypass where every distill halts on review noise and operators default to `--allow-drop`. The halt fires only on genuine content loss.

**False-halt mode:** Word-order-permuted equivalent lines will register as differing and trigger a halt. When this happens, the EM eyeballs the diff, confirms semantic equivalence, and proceeds with `--allow-drop` on that specific run. This is acceptable because the EM still sees the diff — the bypass becomes an inspection, not a rubber-stamp.
<!-- Review: Patrik R3 — F2: set-diff normalization is weaker than the plan's 'semantically-equivalent line' intent; word-order permutations register as different and trigger spurious halts -->

---

## Validation Prerequisite

Before declaring W4 production-ready, the rubric (steps 5a–5d + the negative AC set-diff logic) must be dry-run tested against `docs/plans/2026-04-29-port-patterns-implementation.md` — a verbose, real-world spec produced by a full plan→review×2→chunk→enrich→review pipeline. The dry-run must show: (i) trim preview with diff of re-homed constraints, (ii) provenance block, (iii) deletion list for scaffolding, (iv) rewrite list for code/wiki references, (v) manual-review hits. This is a prerequisite AC; do not declare distill production-ready until it passes.

---

## Acceptance Criteria

- `/distill --dry-run` on a repo with a real spec + stubs shows: (i) trim preview with diff of re-homed constraints, (ii) provenance block, (iii) deletion list for scaffolding, (iv) rewrite list for code/wiki references, (v) manual-review hits.
- After real `/distill`: canonical spec at `archive/specs/`, stubs gone, wiki has provenance frontmatter, distillation-log appended.
- `git show <last_verbose_sha>:<original path>` retrieves verbose original.
- Post-distill `rg -F '<old-spec-path>'` returns zero hits across the entire repo.
- **Negative AC (silent-loss guard):** dry-run emits a content-drop diff. Halt-condition is set-diff, not raw match: an AC-shaped token line (`MUST`, `SHALL`, `AC:`, `Decision:`, `Constraint:`) in the drop-list halts dry-run only if no semantically-equivalent line exists in the re-homed additions OR in surviving ALLOWLIST sections. Cheap implementation: normalize whitespace + lowercase the token-bearing lines, set-diff drop-tokens vs kept-tokens, halt on non-empty difference. This prevents the muscle-memory bypass where every distill halts and operators default to `--allow-drop`. Word-order-permuted equivalent lines may trigger false halts; use `--allow-drop` after EM eyeballs the diff and confirms no semantic loss (see set-diff section).
- **Validation prerequisite:** rubric is dry-run tested against `docs/plans/2026-04-29-port-patterns-implementation.md` (verbose, real-world) before declaring distill production-ready.
- Distillation log `tasks/distillation-log.md` row count is monotonically non-decreasing; strictly increases on any run that deletes scaffolding or archives a spec; schema header preserved verbatim; reason fields are domain-prose (≥8 words; ≥1 CONTEXT.md term when CONTEXT.md exists).
- Wiki provenance frontmatter includes `archived_spec`, `original_path`, `last_verbose_sha`, `distilled`.
- `## Decision Rationale` section present in archived spec (or sibling rationale file) for every spec that had DENYLIST content; rationale covers alternatives-considered + why this won per reviewer finding.
- Link-heal pass rewrites all three target types; `## Manual Review` section in distillation log captures unmatched-but-suspicious hits.
- **Vocabulary discipline AC (Camelia F2):** /distill manual-review log on a CONTEXT.md-bearing repo flags ≥1 vocabulary-drift hit on sampled executor output OR attests zero drift after sampling N≥3 modules.

---

## Relationship to Other Commands

| Command | When to use |
|---------|-------------|
| `/distill` | Extract knowledge into wiki docs, trim + archive canonical specs, delete scaffolding |
| `coordinator:artifact-consolidation` | Bulk prune without knowledge extraction — count, classify, delete |

`artifact-consolidation` remains available for repos that want to clean up without wiki investment. `/distill` supersedes it for the distill-then-delete workflow.
