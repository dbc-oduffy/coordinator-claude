---
title: docs-checker pre-review doctrine
created: 2026-05-03
last_calibrated: 2026-05-03
calibrated_against: Claude Opus 4.7 (1M context)
type: doctrine
related:
  - docs/plans/2026-05-03-docs-checker-default-pre-flight.md
  - plugins/coordinator-claude/coordinator/agents/docs-checker.md
  - plugins/coordinator-claude/coordinator/snippets/docs-checker-consumption.md
---

# docs-checker Pre-Review Doctrine

## What is docs-checker?

docs-checker is a Sonnet-tier agent that verifies external API claims in an artifact before the artifact reaches an Opus reviewer. It checks API names, headers, signatures, and enum values against authoritative sources (Context7, LSP, project-RAG) and reports each claim as VERIFIED, UNVERIFIED, or INCORRECT.

With inline-edit authority (shipped 2026-05-03), docs-checker goes one step further: INCORRECT claims that fall within the AUTO-FIX allowlist are corrected in place before the Opus reviewer sees the artifact. Every correction is logged to a timestamped sidecar so the reviewer — and the EM — has a complete audit trail. When project-RAG is present, docs-checker also verifies in-repo symbol claims (C++ classes, functions, Blueprint nodes), not just external library APIs. Without project-RAG, in-repo symbols are skipped and noted as out-of-scope.

The result: Opus reviewers receive a mechanically pre-verified artifact and can direct their attention to architecture, approach, and design instead of spending cycles on API lookups.

## When does it run? — EM Decision Rules

_Last calibrated: 2026-05-03 against Claude Opus 4.7 (1M context) training distribution. Re-evaluate when the underlying model changes._

| Language / Domain | Default | EM discretion |
|---|---|---|
| **C++ (Unreal Engine, native libraries)** | **Always run.** UE's API surface drifts every release; signatures and module/`.Build.cs` boundaries are easy to hallucinate. | None — run it. |
| **C++ (non-UE)** | Run unless trivially small. | Skip only when the artifact cites ≤3 stdlib calls and nothing else. |
| **C# (Unity, .NET)** | EM discretion, bias toward running for Unity package version drift and recent .NET preview features. | Skip for trivial scripts touching only well-known BCL APIs. |
| **Python** | EM discretion. | Run when the artifact pins library versions or uses uncommon SDKs (Stripe, Anthropic SDK new features, ML libraries). Skip for stdlib-only scripts. |
| **TypeScript / JavaScript** | EM discretion. | Run when SDK signatures matter (Anthropic, Stripe, AWS SDK v3 vs v2). Skip for routine React/Node code in the training distribution. |
| **Go, Rust, Swift** | EM discretion. | Bias toward running — fewer training tokens than Python/TS. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — nothing to mechanically verify. |
| **Plans citing in-repo symbols only** | Skip docs-checker (use project-RAG instead). | None — docs-checker is for external APIs. |

**Heuristic, not law.** The EM applies judgment: scale (1-page stub vs 30-page spec), complexity (3 API calls vs 50), distance from training (UE 5.6 features vs `Array.prototype.map`). When in doubt, run it — it's cheap. When skipping, no need to justify; the EM may simply proceed.

**Skip ≠ review skip.** Skipping docs-checker does not skip the Opus review of an EM plan. That rule is unchanged; only the PM may waive a review.

## AUTO-FIX Allowlist

docs-checker may apply inline corrections only for:

- Wrong API or method name (e.g., `FVector::CrossProduct` vs `FVector::Cross`)
- Wrong header `#include` path
- Wrong function or macro signature (parameter types, parameter order)
- Wrong enum value
- Wrong module or `.Build.cs` placement of a symbol — corrected in the artifact text only (see Scope Constraint)

**Hard prohibitions — docs-checker must NOT:**

- Edit prose, descriptions, or rationale text
- Reword comments (wording changes, not correctness fixes)
- Restructure sections or reorganize content
- Edit motivation, decision, or risks sections of plan documents
- Edit any item where two valid forms coexist (e.g., legacy vs new API both still supported)
- Edit files other than the artifact under review
- Auto-fix wrong line-number references in code comments or wrong cited file paths — these may be deliberate battle-story breadcrumbs to historical state; they are reported as UNVERIFIED findings for the Opus reviewer to disposition
- Apply any change classified as UNVERIFIED (report-only) or low-confidence INCORRECT

## Scope Constraint

docs-checker edits the artifact under review ONLY. It NEVER edits files referenced by the artifact — build files, source files, cited specs. Even if the artifact cites a wrong header, docs-checker corrects the citation in the plan or stub, not the `.cpp` or `.h` that `#include`s it. Corrections to live source files are out of scope; those are findings for the Opus reviewer.

## Project-RAG Staleness Rule

When project-RAG is available, docs-checker uses it to verify in-repo symbol claims. Three cases apply:

1. **RAG fresh, symbol found:** VERIFIED. docs-checker may auto-fix an incorrect in-repo symbol claim if it falls within the allowlist.
2. **RAG fresh, symbol not found:** INCORRECT. If the allowlist applies and confidence is high, auto-fix. Otherwise report as finding.
3. **`project_staleness_check` reports drift:** All in-repo symbol claims downgrade to UNVERIFIED (report-only), regardless of what the RAG index says. Auto-fix on in-repo symbols requires a fresh index OR a confirmatory LSP or Grep pass on HEAD. Stale RAG can produce both false-INCORRECT (RAG says missing, HEAD has it) and false-VERIFIED (RAG says present, HEAD removed it) — auto-fixing on either is wrong.

When project-RAG is absent, in-repo symbol claims are skipped and noted as out-of-scope in the verification report.

## Sidecar Schema

Each auto-fix is logged as a YAML block in `tasks/review-findings/{timestamp}-docs-checker-edits.md`:

```yaml
- file: <path>
  line_before: <line number before edit>
  line_after: <line number after edit>
  content_before: <original text>
  content_after: <replacement text>
  source:
    tool: <Context7 | LSP | project-RAG | Grep>
    query: <query string used>
    result_id: <stable ID if tool provides one>
  claim_id: <sequential ID for this edit in this run>
  confidence: <high | medium>
```

The sidecar path is included verbatim in the Opus reviewer's dispatch prompt. The sidecar becomes part of the review record and is archived alongside the reviewer's findings JSON.

## Edit-Budget Cap

docs-checker may apply at most `max(10, claims_count/3)` edits per artifact. Beyond the cap, remaining INCORRECT items report as findings rather than auto-fixes. This bounds blast radius if a verification source returns inconsistent results across the run and prevents oscillation across different lines — a failure mode the existing stuck-detection rule does not cover.

## Integrator Bypass + Rollback

docs-checker auto-fixes are NOT integrator-gated. The integrator runs after the Opus reviewer on the reviewer's findings, unchanged. The compensation for bypassing the integrator:

1. All edits land as a single git-revertible commit — "undo all docs-checker edits" is one command: `git revert <docs-checker-commit-sha>`.
2. The changelog sidecar is included verbatim in the Opus reviewer's dispatch prompt, so the reviewer sees exactly what was pre-applied.
3. After the Opus review completes, the EM **must** diff the docs-checker commit against the pre-edit artifact for any auto-fix the Opus reviewer did not explicitly endorse. This spot-check is mandatory and time-bounded, not discretionary. The EM reads the changelog AND runs the diff before marking the review stage done.
4. Rollback is `git revert <docs-checker-commit-sha>` — one command, all fixes reverted atomically.

The integrator continues to handle Opus reviewer findings as today. The docs-checker changelog is part of the permanent review record.

## Distribution

The reviewer-side consumption block is synced via `bin/verify-docs-checker-sync.sh --fix` from `snippets/docs-checker-consumption.md` to all Opus reviewer prompts:

- `plugins/coordinator-claude/coordinator/agents/staff-eng.md` (Patrik)
- `plugins/coordinator-claude/game-dev/agents/staff-game-dev.md` (Sid)
- `plugins/coordinator-claude/data-science/agents/staff-data-sci.md` (Camelia)
- `plugins/coordinator-claude/web-dev/agents/senior-front-end.md` (Palí)
- `plugins/claude-unreal-holodeck/game-dev/agents/staff-game-dev.md` (holodeck Sid variant)

See the tripwire in `coordinator/CLAUDE.md` — "Adding a Convention to the Coordinator System" section. The sync script is added to `/update-docs` Phase 11c alongside the calibration and project-rag-preamble syncs. Never edit consumer sentinel blocks directly — the `--fix` pass overwrites them.

## Recalibration

The EM Decision Rules table is calibrated against the current Claude model's training distribution. Re-evaluate when the underlying model changes. A note is recorded in `tasks/coordinator-improvement-queue.md` to flag this for the next model upgrade.
