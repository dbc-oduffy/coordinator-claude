# Workday / Workweek Cadence

> Spec backlink: `archive/specs/` — cadence doctrine distilled from CLAUDE.md § Workday/Workweek Cadence
> and `/workday-complete` + `/workweek-complete` command bodies.

---

## Overview

Daily and weekly are distinct ceremonies, both PM-invoked, staleness-nudged.
**Handoffs are the atom; the week-changelog is the index over them.**
`/workday-complete` synthesises from existing handoffs and the Step 4 daily summary — does not re-author.
`/workweek-complete` reads the index as ground truth, does not reconstruct from `git log`.

---

## Daily ceremony — `/workday-complete`

Sequential steps (each must complete before the next begins):

| Step | Name | Gate | Notes |
|------|------|------|-------|
| 1 | `/validate` (+ UBT preamble) | blocking | UBT preamble: non-UE repos see silent skip |
| 2 | RAG Staleness Nudge | informational | skip if no project-rag tool |
| 3 | Branch Consolidation | blocking on conflict | see conditional-skip note below |
| 4 | Strategic Daily Review | — | writes `archive/daily-summaries/YYYY-MM-DD.md` |
| 5 | Plugin Validation Suite | blocking on hook failures | non-hook failures: report and flag |
| 6 | Completed Archive Audit | — | |
| 7 | Tier Usage Report | — | |
| 8 | Improvement-Queue Depth Nudge | informational | depth ≥5 → notice only; no triage |
| 9 | Append to Week-Changelog | — | commits daily summary + changelog row |
| 10 | Weekly Staleness Check | informational | |
| 11 | Final Summary | — | |

### Step 3 conditional-skip (first conditional in the daily sequence)

Step 3 (branch consolidation) is the only daily step that may legitimately short-circuit: if HEAD already contains `origin/main` (ahead-only state), the rebase sub-step skips with a "no rebase needed" log. This is an EM-judgment skip, not a blocking gate.

The skip fires when `git rev-list --count HEAD..origin/main` is `0` — meaning every commit on `origin/main` is already an ancestor of HEAD. In this state, `git rebase origin/main` would walk back through merge commits and replay them needlessly. The guard avoids that wasted work.

A missing-ref guard precedes the skip: if `origin/main` is not present locally (fresh clone, network issue, renamed remote), the reconcile sub-step logs an informational skip rather than producing an opaque rebase failure.

Step 3 sub-step 0 (`sync-main.sh`) MUST run before the rebase/skip check — it fetches `origin/main`, ensuring the rev-list count is computed against a fresh ref.

### Week-changelog `Validation:` schema

The changelog block records:
```
Validation: validate=<exit-code-step-1> plugin-suite=<exit-code-step-5>
```

Both fields are auto-filled from ceremony exit codes; neither is LLM-authored prose. On non-UE repos, the Step 1 UBT preamble is a no-op (script absent), so `validate=` reflects only the `run-all-checks.py` result. The `plugin-suite=` field is present even on non-UE repos (reflects Step 5 node test exit code). A value of `N/A` is acceptable when the step was explicitly skipped with PM authorization.

---

## Weekly ceremony — `/workweek-complete`

PM-invoked, release-grade. Reads the week-changelog as the canonical record — does NOT reconstruct from `git log`. Heavy steps absent from daily live here: `/update-docs`, ShellCheck, improvement-queue triage, skill-description advisory, scc, version bump, merge.

Staleness signal: `bin/check-weekly-staleness.sh` (≥5 days AND ≥15 commits since last weekly-reset SHA).

Improvement-queue triage: daily emits depth nudge only (≥5 → notice); weekly triggers action (apply, dispatch executors, delete resolved entries; commit subject names them).

### Step 4d: Skill description length advisory

`check-description-length.sh` runs here as **advisory only** — it can never block the ceremony or propagate a non-zero exit. The validator's stdout and rc are captured into the weekly summary via the `set +e` / `_DESC_RC` / `set -e` pattern. A non-zero rc that produces no findings output indicates a script crash — investigate out-of-band. Skills flagged over-budget are follow-up nudges, not blockers.

---

## Relationship Between the Two Ceremonies

- `/workday-complete` is a branch wrap, not a release ceremony.
- `/workweek-complete` is the release ceremony; it reads what the daily ceremony wrote.
- Neither ceremony merges to main directly — `/workday-complete` never merges; `/workweek-complete` delegates to `/merge-to-main`.
- ShellCheck, scc, improvement-queue triage, and the skill-description lint are weekly-only; they do not belong in the daily wrap.
