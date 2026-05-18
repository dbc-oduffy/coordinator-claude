---
title: prior-art-checker pre-review doctrine
created: 2026-05-06
type: doctrine
related:
  - plugins/coordinator/agents/prior-art-checker.md
  - plugins/coordinator/snippets/prior-art-check-consumption.md
  - plugins/coordinator/docs/wiki/reviewer-pipeline.md
  - plugins/coordinator/skills/learn-lessons/SKILL.md
  - docs/wiki/docs-checker-pre-review.md
  - docs/wiki/lesson-triage.md
  - tasks/handoffs/2026-05-06_165124_wired-in-wikis-lesson-checker.md
---

# prior-art-checker Pre-Review Doctrine

## What is prior-art-checker?

prior-art-checker is a Sonnet-tier agent that cross-references a plan artifact against the coordinator's accumulated prior art before the artifact reaches an Opus reviewer. It reads the plan, enumerates its claim surface, then searches four corpora — project wikis (`docs/wiki/` recursively, including subdirectories `marketplace/`, `opensource/`, `competitors/`, and `codebase-judgment/`), global wikis (`~/.claude/docs/wiki/`), `tasks/lessons.md`, and the central improvement queue — and reports each claim as **Conflict**, **Compatible-but-relevant**, or **Silent**.

The output is a sidecar at `<plan-path>.prior-art-check.md`. The agent makes no judgments and applies no fixes; it surfaces matches with verbatim quotes for the EM to disposition.

The result: Opus reviewers receive a plan that has already been cross-referenced against captured wisdom and can focus their attention on architecture and approach instead of re-deriving lessons we have already learned.

## Why this exists — the capture-recall loop

The coordinator system captures lessons via `tasks/lessons.md` → `learn-lessons` → `docs/wiki/` and the central improvement queue. **Capture is mature; recall was broken.**

Wikis sat in `docs/wiki/` without being part of any EM's default context. The EM rarely read them at plan time. Lessons promoted to wikis silently decayed because nothing in the workflow reached for them. The fix was not more wikis — it was a process loop that consults them automatically.

prior-art-checker is the recall side of the loop. Without it, captured wikis are storage; with it, captured wikis become live doctrine that shapes plans before they ship.

## What counts as "prior art"

Two kinds, both equally in scope:

1. **Doctrine** — rules about how things should be done. Project-agnostic patterns, conventions, anti-patterns. Examples: `test-design-discipline.md`, `cleanup-sweep-hazards.md`, `round-trip-contract-tests.md`.
2. **Institutional memory** — project-specific history. What we tried, what broke, why we made the call we did. Examples: `daily-branch-discipline.md` (born of a real incident), `scoped-safety-commits.md` (born of audit-trail corruption).

Both are equally important. A plan can be doctrinally fine and still violate a project-specific decision; a plan can be project-fine and still violate doctrine. The agent checks both corpora every run.

## Role in the review pipeline

**The prior-art-checker is a recall pre-flight, not a reviewer.** It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed by all downstream reviewers. Running it does not satisfy the "sequential" requirement; it sits upstream of the reviewer sequence entirely.

## When does it run? — EM Decision Rules

| Artifact type | Default | EM discretion |
|---|---|---|
| **Plan documents** (`docs/plans/*.md`, `~/.claude/plans/*.md`) | **Run by default.** | Skip only when the plan is a single-file mechanical bug-fix with no architectural decision. |
| **Enriched stubs with architectural decisions** | Run when chunks introduce a new pattern, new agent, new convention, or modify cross-cutting doctrine. | Skip for stubs that are mechanical execution of a previously-checked plan. |
| **Code review (no plan artifact)** | Skip. | Run when a PR/diff lacks a plan but introduces a new pattern worth checking against doctrine. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — no claim surface to cross-reference. |
| **Trivial single-file edits** | Skip. | None — overhead exceeds the benefit. |

**Special case — premise reversals.** When a plan reverses a prior decision (regenerates torn-down structure, re-introduces a pattern we previously removed), ALWAYS run the prior-art-checker. This is exactly the case where prior art most matters; per the coordinator's "Premise-pass before regenerating torn-down structure" rule, the prior-art-checker is the mechanical implementation of that premise pass.

**Skip is silent.** No flag needed, no justification required. EM judgment.

## Output format

```markdown
## Prior-Art Verification

**Plan:** <path>
**Verdict:** COMPATIBLE | WARN | BLOCKED-SURFACE-TO-PM | DEGRADED
**Claims checked:** N
**Conflicts:** X | **Compatible-but-relevant:** Y | **Silent:** Z

### Conflicts (plan contradicts prior art)
[verbatim quotes from prior art with EM-action suggestions]

### Compatible-but-relevant (plan should cite or align)
[verbatim quotes with citation suggestions]

### Silent areas (no prior art found)
[bulleted list of uncovered claims]
```

The verdict is advisory. The agent never auto-blocks; only the EM/PM may halt a review.

## Verdict semantics

- **COMPATIBLE** — zero conflicts; compatible-but-relevant items are informational only. Proceed to Opus reviewer dispatch.
- **WARN** — one or more conflicts, none severe enough to halt review. EM dispositions each conflict before dispatching the Opus reviewer: fold prior art into the plan, override and document in the plan's "Considered alternatives" section, or escalate one item to PM.
- **BLOCKED-SURFACE-TO-PM** — one or more conflicts contradict load-bearing doctrine (scoped-safety-commits, daily-branch-discipline, round-trip-contract-tests, sequential-review HARD RULE, etc.) OR contradict explicit institutional memory recording a past incident. EM **must** escalate to PM before continuing. Do not dispatch the Opus reviewer until the conflict is resolved or PM authorizes override.
- **DEGRADED** — the agent ran with materially incomplete coverage. Emitted when: (a) Phase 1 capped at 30 claims and the plan has significantly more, (b) Stuck Detection fired ≥1 time, (c) a corpus was unreadable, or (d) estimated token cost exceeded 50K. Treat DEGRADED as no signal — review the plan fully against prior art as if no pre-flight ran. DEGRADED does not block; it flags unreliable coverage.

## Hard prohibitions — prior-art-checker must NOT

- Edit the plan inline. The agent writes exactly one file: the sidecar.
- Edit any wiki, lesson, or queue file (read-only against the corpus).
- Apply auto-fixes of any kind. Recall is judgmental — even compatible-but-relevant findings could be wrong, and conflict resolutions need EM/PM input.
- Fabricate prior art. If a claim is silent, the agent says so. Inventing citations is worse than reporting a gap.
- WebSearch for general guidance. The agent checks **our** prior art, not the open internet's.
- Auto-block a plan. Only the EM/PM may halt a review.

## Distinction from docs-checker

The two pre-flights answer different questions:

| | docs-checker | prior-art-checker |
|---|---|---|
| **Question** | Are these external API claims factually correct? | Have we already established something relevant about this? |
| **Corpus** | Context7, LSP, project-RAG, cppreference | Project wikis, global wikis, `tasks/lessons.md`, central improvement queue |
| **Output** | Per-claim verification table (VERIFIED / UNVERIFIED / INCORRECT) | Three-bucket sidecar (Conflict / Compatible-but-relevant / Silent) |
| **Authority** | AUTO-FIX allowlist for tradeoff-free corrections | REPORT-ONLY — EM dispositions all findings |
| **Surface** | reviewer pipeline Phase 2.7 (`docs/wiki/reviewer-pipeline.md`) | reviewer pipeline Phase 2.7b (`docs/wiki/reviewer-pipeline.md`) |

They are not substitutes; they can both run on the same artifact.

## Sidecar format note

Sidecars use `kind:` rather than `type:` in their frontmatter to distinguish machine-emitted artifacts from authored docs. docs-checker sidecars should adopt the same convention when they are next revised (not in scope for this commit — surfaced as a follow-up).

## Distribution

The reviewer-side consumption block is synced via `plugins/coordinator/bin/verify-prior-art-sync.sh --fix` from `plugins/coordinator/snippets/prior-art-check-consumption.md` to all Opus reviewer prompts:

- `plugins/coordinator/agents/staff-eng.md` (the Staff Engineer)
- `plugins/game-dev/agents/staff-game-dev.md` (the Game Dev Reviewer)
- `plugins/data-science/agents/staff-data-sci.md` (the Data Science Reviewer)
- `plugins/web-dev/agents/senior-front-end.md` (the Front-End Reviewer)
- `<plugin-consumer>/game-dev/agents/staff-game-dev.md` (optional domain-plugin the Game Dev Reviewer variant)

The sync verifier is auto-discovered by `/update-docs` Phase 11b. See the tripwire in `coordinator/CLAUDE.md` — "Adding a Convention to the Coordinator System" section.

## False-positive arbitration

The prior-art-checker is mechanical, not judgmental. It can over-match (false-flag a phrasing difference as a conflict) and under-match (miss a doctrine that applies but uses different keywords). Two arbitration rules:

1. **Override goes in the plan.** When the EM dispositions a conflict as "override," the plan's "Considered alternatives" section gains a one-line entry citing the prior-art quote and the override rationale. This is the durable record; future readers see what was overridden and on what grounds.
2. **Repeated false-positives signal wiki revision.** When the same wiki entry produces multiple bogus conflicts across plans, that is a feedback signal — the wiki is outdated, vague, or wrong. Surface to PM as a candidate for wiki revision. The prior-art-checker thus becomes a quality loop on the wiki corpus.

**Sidecar preservation.** Prior sidecars are never overwritten — on re-run the agent renames the existing sidecar to `<plan-path>.prior-art-check.<UTC-mtime>.md` before writing the new one. This means the arbitration history (what the first run flagged, what changed in the second run) is always available as an archived sidecar alongside the current one. The feedback-loop in rule 2 above depends on this archive existing.

**Operational hook:** during `/workweek-complete` Step 4 (improvement-queue triage), the EM scans recent `docs/plans/**/*.prior-art-check*.md` sidecars for Conflicts dispositioned as "override" and flags wikis cited ≥3 times in overrides as candidates for revision. This is judgment-based, not automated — but the responsibility lives in weekly cadence so it doesn't drift.

## Cost target

Aim for under 10K tokens per plan check. The corpus is bounded (project wikis across all `docs/wiki/` subdirectories — currently ~57 files including `codebase-judgment/` entries — plus global wikis, lessons, and queue). RAG-over-wikis is a phase-2 optimization; for now, full-text reads of relevant entries is the contract.
