---
kind: wiki
title: Lesson + Improvement Workflow — Triage, Promotion, and Coordinator Sweeps
status: active
created: 2026-05-06
sources:
  - archive/specs/2026-05-05-lesson-triage-skill.md
  - tasks/lesson-triage-2026-05-05/SYNTHESIS.md
  - archive/handoffs/2026-04-27_125441_243a4ab4.md
  - archive/handoffs/2026-04-27_164304_sweep-resume.md
  - archive/handoffs/2026-05-01_193000_pickup01.md
  - archive/handoffs/2026-05-05_104956_lesson-triage-skill.md
  - archive/handoffs/2026-05-05_104958_lesson-triage-structural.md
  - archive/handoffs/2026-05-05_113500_08614bff.md
tags: [lesson-triage, improvement-queue, coordinator-sweep]
---

# Lesson + Improvement Workflow

This guide consolidates three closely-coupled processes that together form the EM's loop for converting per-session war-stories into greppable doctrine:

1. **`lesson-triage`** — the unified skill that processes `tasks/lessons.md` files (project-local maintenance + cross-project promotion + cadence rechecks).
2. **Improvement-queue triage** — the daily/weekly cadence over `~/.claude/tasks/coordinator-improvement-queue.md`.
3. **Coordinator-sweep pattern** — the dispatch/verification shape used when promoting universal patterns into multiple files at once.

Treat the three as one workflow seen from different time horizons (in-session → daily/weekly → multi-repo).

## Why a unified skill replaced `lessons-trim`

`lessons-trim` was a per-project periodic-maintenance skill called from `/update-docs` Phase 6. Cross-project promotion of universal patterns happened ad-hoc, then twice deliberately, before reaching the "wait for instance #3" threshold. Rather than fork two skills, `lesson-triage` is a single skill with three modes — see [DR-001](#dr-001) and [DR-002](#dr-002).

## Three modes (single skill, mode-detected)

| Mode | Trigger | Authority | Output |
|---|---|---|---|
| **project-local** | `/update-docs` Phase 6 OR direct invoke from project root | Auto-applies bounded items; surfaces structural changes to PM | Trimmed `tasks/lessons.md`, append-only wiki edits |
| **cross-project** | PM-invoked from `~/.claude` central root | PM gate on every apply (even auto-apply class) | Routing manifest grouped by destination repo + change_kind |
| **recheck** | `tasks/lesson-triage-recheck-*.md` marker via `/workday-start` | Auto-extends cadence if delta ≤5 new universals; otherwise dispatches cross-project | Updated marker or cross-project dispatch |

**Default mode detection:** `/lesson-triage` without args inspects cwd. Running from `~/.claude` central → default cross-project; else default project-local.

## Improvement Queue Discipline

### Queue routing — universal vs project-specific

Every entry in `tasks/coordinator-improvement-queue.md` should route to one of:
- **universal** — applies to any coordinator user / any project type → keep in global `~/.claude/tasks/coordinator-improvement-queue.md`
- **project-specific** — rooted in a specific project's codebase → route to `tasks/improvement-queue.md` in that repo
- **delete (resolved/dropped)** — already applied/marked resolved/promoted; no signal left in keeping it
- **delete (dup)** — crossed out by sentinels in-file

**Routing key test:** "If a different project type used the coordinator pipeline, would this rule apply?" → if yes, universal; if no, project-specific.

### Delete-on-resolution (2026-05-07 doctrine, amended 2026-05-17)

**Original (rejected) pattern:** flip `resolution: pending` → `resolution: resolved YYYY-MM-DD <commit>` and move to `## Processed`. Created a graveyard — central queue grew to 864 lines with 113 resolved rows (~13% bloat).

**Current pattern:** On resolution, **delete the entry**. The commit subject names the closed entry. `git log -- <queue-file>` is the audit trail. `/update-docs` Phase 11i strips any drift back to closure-log shape — `## Processed` / `## Resolved*` / `## History` / `## Closed` / `## Done` / `## Archive` / `## Closeout` sections, and any entry whose `resolution:` value is anything other than `pending`/`in_progress` (or which carries a `**Closeout:**` annotation).

**Schema amendment (2026-05-17 — DR-056 amended):** The `recurring:` and `resolution:` sub-lines are dropped from the canonical schema. Empirical data showed 100% of central-queue entries had `recurring: 0` and `resolution: pending` (266 lines of unchanging ceremony across 133 entries). The fields never moved. New schema is main-line-only; recurrence bumps are recorded as ` [recurring: N]` on the main line when N ≥ 1. The pruner strips trivial sub-lines (`recurring: 0`, `resolution: pending`, `resolution: in_progress`) on every `/update-docs` run.

**Why:** Closure-log retention contradicted wiki doctrine (DR-020: "improvement queue is a triage surface, not a paper trail"). Schema ceremony that never changes is the same anti-pattern at the sub-line level. Git log recovers the full lifecycle for both.

Source: `docs/plans/2026-05-07-prune-resolved-state-bloat.md` (original, status: approved 2026-05-07); 2026-05-17 amendment captured in `docs/decisions/DR-056-queue-delete-on-resolution.md`.

### Triage cadence — three-session execution plan

From the 2026-05-07 queue cleanup session (drove 131 → 91 entries via 1 session):

- **Session A:** Pre-dispatch verification + Verifying executor/handoff premises + Implementation standards micro-rules. All target CLAUDE.md sections — serialize these. ~25 entries.
- **Session B:** Ceremony-calibration new wiki synthesis (instance-#3 gate met). ~9 entries.
- **Session C:** Clusters 4+6 + 18 STANDALONE-WIKI bulk + 5 SMALL-CODE-PATCH + 4 MULTI-FILE-SWEEP. ~35 entries.

Queue cleanup at entry level 91 residual was ~6:1 prose-doctrine to engineering work ratio.

## Per-lesson routing schema

Each candidate lesson is shaped into a YAML record:

```yaml
id: <source-shortname>-<entry-id>      # stable
source: <file>:<line>                  # at extraction time
summary: <one-line>
scope: universal | project | wiki-only
destinations:
  - target: <file>
    section: <heading or anchor>
    change_kind: <enum>                # see taxonomy below
    rationale: <one-line>
    priority: HIGH | MEDIUM | LOW
    depends_on: <other id|null>
open_questions: [...]
```

## Change-kind taxonomy (closed enum, 12 kinds)

`doctrine-edit`, `agent-prompt-edit`, `hook-edit`, `script-edit`, `snippet-sync-update`, `wiki-new`, `wiki-append`, `memory-pointer`, `project-structural`, `retag-local`, `strip-local` (gated on central commit SHA), `discard`.

## Mode-conditional authorization

**project-local auto-applies:** discard pure-ephemeral, append to existing wiki guide, re-tag local within same file, dedupe duplicates.

**project-local SURFACES (no auto-apply):** doctrine-edit, wiki-new, agent-prompt-edit, hook-edit, script-edit, project-structural outside same repo.

**cross-project PM-gates EVERY apply** — even auto-apply class. PM authorization is the load-bearing surface; the synthesis is the authorization document, not an execution kickoff.

## Cross-project six-phase pipeline

- **Phase 0 — Configuration:** read `lesson_triage:` block in `~/.claude/coordinator.local.md` (roots, exclude, glob, recheck_cadence_days). Never hardcode `X:/`.
- **Phase 1 — Discovery:** glob configured roots, count tagged universals.
- **Phase 2 — Fan-out scouts:** one per repo, parallel `general-purpose` Sonnet, two-pass extraction (tagged + untagged candidates), themes section, DONE protocol.
- **Phase 3 — Synthesis:** EM directly produces the four-section A/B/C/D structure (see below).
- **Phase 4 — PM review:** authorize strip list, B prioritization, C re-tag list.
- **Phase 5 — Apply:** central first, then strip locals; one commit per repo with explicit pathspec. **Order is load-bearing: central change lands → strip locals.** A strip without the central anchor leaves a doctrine-shaped hole.
- **Phase 6 — Recheck marker:** today + cadence days.

### A/B/C/D synthesis structure

- **A.** Already encoded centrally — safe to delete from local files now.
- **B.** Net-new universals — central change warranted (HIGH/MEDIUM/LOW priority subsections with proposal field).
- **C.** Defer / discard — entries tagged `[universal]` but actually domain-specific; re-tag locally as `[ue]`/`[rag]`/etc.
- **D.** Repeatable triage pattern (omit on subsequent runs).

## Concurrent-EM race guard for strips

Phase 5 strips need `git pull --rebase` + scoped pathspec + clean-state check before edit. If `lessons.md` has uncommitted local edits OR recent commits within the triage window, surface to PM rather than auto-strip — a concurrent peer EM may have added entries the synthesis didn't see.

## Capturing lessons that should promote

When writing a `[universal]` lesson in a project's `tasks/lessons.md`, also append to `~/.claude/tasks/coordinator-improvement-queue.md`:

```
- YYYY-MM-DD | <source-repo> | <source-file>:<line> | <one-line summary> | proposed target: <coordinator file>
```

Test: "If a different project type also used the coordinator pipeline, would this rule apply?" Universal → tag and append. Project-specific → leave un-tagged.

## Improvement-queue cadence — daily depth nudge vs weekly action

Two distinct cadences operate on the same queue file:

- **Daily (`/workday-complete`)** — emits a depth nudge only. ≥5 new entries → notice, no action. The daily ceremony does not consume the queue; it surfaces volume.
- **Weekly (`/workweek-complete`) Step 4** — triggers triage action. Apply tradeoff-free items, dispatch executors, move to Processed block. Recheck mode fires from `tasks/lesson-triage-recheck-due-*.md` markers.

This split enforces "don't theatre the queue daily" — entries either get acted on at weekly cadence or they're explicitly deferred. Promoting through the queue solely for symmetry is theater (see [DR-007](#dr-007)).

### Triage verdict taxonomy

A 144-entry triage in 2026-05-05 produced this empirical distribution:

| Verdict | Share |
|---|---|
| ALREADY-DONE | 28 |
| DUPLICATE-MERGE | 21 |
| QUICK-WIN | 71 |
| REQUIRES-DESIGN | 14 |
| DROP | 10 |

**Lesson:** the queue accumulates ~50% true work, ~35% already-done/duplicate noise, and ~15% drop/design — budget triage time accordingly.

## Coordinator-sweep dispatch pattern

When the synthesis produces multi-file changes (the "promote universals into N files" surface), the canonical shape is:

1. **Reviewer (the Staff Engineer) BEFORE dispatch, not after first executor returns.** the Staff Engineer's pre-dispatch pass detects cluster-disjointness (last-writer-wins risk between parallel executors). 16 findings on a 35-finding plan, 6 of which were P0/P1 cluster disjointness, is a typical hit rate. See [DR-009](#dr-009).
2. **Pre-create shared parent dirs** rather than letting one executor own a directory two executors will write to. Race avoidance > serialization.
3. **Cross-cluster findings register** identifies which findings intentionally land in 2+ files. Don't treat as duplicates during deduplication passes.
4. **Executors return canonical-phrase JSON for deterministic post-execution grep.** EM verifies via `grep -F` against the exact phrase list. Don't trust free-text summaries.
5. **Verify percolation by per-file `diff`,** not by trusting agent self-reports. Self-applying the lesson it encodes is the cleanest dogfood.
6. **Concurrent peer detection.** If a sweep detects a peer EM has absorbed the same mandate, stand down. Cost of a merge conflict on the queue file > cost of stopping early. ([DR-010](#dr-010))

### Promotion patterns observed

- **In-place to CLAUDE.md** is acceptable even when it grows the file (293→396 lines = 35% growth). CLAUDE.md is the surface agents read; wiki guides are second-class for invariants. The `lessons-trim` pattern can prune later.
- **Three commits per integration round, not one bundled.** When R2 produces auto-fixes + W1 polish + architecture refactor, three commits make the audit trail per category greppable.
- **Phase 11d frontmatter-drift sweep reports only, never auto-fixes.** Schema violations frequently encode an intentional decision; auto-fix would silently corrupt those. Carve out: tradeoff-free fixes on records the EM authored *this same session*.

## Counts as orientation

Empirical scale for `~/.claude` central + 4 X:/ project repos as of 2026-05-05:

| Repo | Tagged | Untagged candidates |
|---|---|---|
| holodeck | 87 | 19 |
| project-rag | 31 | 0 |
| coordinator | 24 | 7 |
| DroneSim | 3 | 12 |
| **Total** | **145** | **38** |

This sets expectations for fan-out budget: 4 parallel scouts, ~5 minutes each, ≤200 entries total.

## Decision Records

### DR-001 — Single skill with three modes, not three skills

**Status:** accepted (PM resolved 2026-05-05)
**Context:** `lessons-trim` was per-project Phase 6 maintenance. Cross-project promotion was ad-hoc twice. Need: a stable surface for both, plus cadence rechecks.
**Decision:** One skill, three modes (project-local, cross-project, recheck). Pipeline split deferred until SKILL.md exceeds 500 lines or modes diverge.
**Consequences:** Single mode-detection point at default invocation; mode-conditional authorization rules live in one place; alias `lessons-trim` for one cadence cycle to avoid breaking Phase 6 invocation.
**Source:** `archive/specs/2026-05-05-lesson-triage-skill.md`

### DR-002 — Wait-for-instance-3 doctrine on skill creation

**Status:** accepted
**Context:** Cross-project promotion was performed ad-hoc twice before formal skill.
**Decision:** Don't formalize a skill until the third instance. The third invocation is the one that justifies skill scaffolding.
**Consequences:** Bias toward executing patterns in-prose; only codify when repetition is empirically confirmed.
**Source:** `archive/handoffs/2026-05-05_104956_lesson-triage-skill.md`

### DR-003 — Config in `coordinator.local.md`, not sibling file

**Status:** accepted (PM resolved)
**Decision:** Extend `~/.claude/coordinator.local.md` with `lesson_triage:` block; do not create `~/.claude/lesson-triage.local.md`.
**Consequences:** Fewer files to discover; co-located with other coordinator config.
**Source:** `archive/specs/2026-05-05-lesson-triage-skill.md`

### DR-004 — Fan-out is information gathering, not workstream emission

**Status:** accepted
**Decision:** The skill itself does NOT auto-emit spinoff handoffs. Synthesis may surface "missing skill X" recommendations advisory-only; acting is a separate session decision.
**Consequences:** Triage outputs are documents, not commitments. Prevents skill from racing the PM into dispatching workstreams.
**Source:** `archive/specs/2026-05-05-lesson-triage-skill.md`

### DR-005 — Self-exclusion of central root

**Status:** accepted
**Decision:** Exclude central `~/.claude` from cross-project discovery set when central is the running root.
**Consequences:** Avoids the central repo's own lessons being treated as a promotion candidate to itself.

### DR-006 — Treat HIGH-priority synthesis items as PM-pending, not auto-execute

**Status:** accepted
**Context:** Even HIGH-priority items have shape choices the PM might disagree with (wiki link vs CLAUDE.md section; consolidation grouping).
**Decision:** Synthesis is the authorization surface; PM reviews then this handoff's picking-up EM applies what's authorized.
**Source:** `archive/handoffs/2026-05-05_104958_lesson-triage-structural.md`

### DR-007 — Improvement-queue daily depth nudge, weekly action

**Status:** accepted
**Decision:** `/workday-complete` emits depth notice only at ≥5 new entries; `/workweek-complete` Step 4 triggers triage action.
**Consequences:** Queue is not "consumed daily"; promoting through it solely for symmetry is theater.
**Source:** `archive/handoffs/2026-05-01_193000_pickup01.md`, `archive/handoffs/2026-05-05_113500_08614bff.md`

### DR-008 — Phase 11d reports only, never auto-fixes

**Status:** accepted
**Decision:** Frontmatter drift sweep is a visibility tool. Schema violations frequently encode intentional decisions (record predates schema, deprecation in flight). Carve-out: tradeoff-free fixes on records the EM authored *this same session*.
**Source:** `archive/handoffs/2026-05-01_193000_pickup01.md`

### DR-009 — the Staff Engineer review BEFORE dispatch on multi-file sweeps

**Status:** accepted
**Context:** 35-finding sweep across 7 executors hit 16 review findings (6 P0/P1) at the cluster-disjointness layer. Without pre-dispatch review, parallel executors would have stomped each other's edits.
**Decision:** Run the Staff Engineer review pre-dispatch when sweep targets >5 files in parallel; pre-create shared parent dirs.
**Source:** `archive/handoffs/2026-04-27_164304_sweep-resume.md`

### DR-010 — Stand down on concurrent peer absorption

**Status:** accepted
**Decision:** When a peer EM is detected absorbing the same mandate during a sweep, stand down rather than push on. Cost of merge conflict > cost of stopping. Promote the lesson; hand off.
**Source:** `archive/handoffs/2026-05-05_113500_08614bff.md`

### DR-011 — Promotion in-place to CLAUDE.md is acceptable

**Status:** accepted
**Context:** 7 cluster groups all targeted CLAUDE.md; one big executor produced +103 lines (35% file growth).
**Decision:** Accept growth in CLAUDE.md when every line is a unique lesson. The file is the surface agents read; wiki guides are second-class. `lessons-trim` can prune later.
**Source:** `archive/handoffs/2026-05-05_113500_08614bff.md`

### DR-012 — Three commits per integration round, not one bundled

**Status:** accepted
**Decision:** When review findings span small auto-fixes + a real refactor + a third orthogonal category, ship as three commits so the audit trail per category is greppable.
**Source:** `archive/handoffs/2026-05-01_185201_532ebcc5.md`
