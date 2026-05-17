# Workday / Workweek Cadence

> Spec backlink: `archive/specs/` — cadence doctrine distilled from CLAUDE.md § Workday/Workweek Cadence
> and `/workday-complete` + `/workweek-complete` command bodies.

**Design source:** `docs/plans/2026-05-04-workweek-cadence-split.md`

## Why Two Ceremonies?

`/workday-complete` was doing double duty: lightweight daily housekeeping (validate, branch consolidate, archive audit) AND release-grade ceremony (full docs sweep, ShellCheck, Codex review, improvement-queue triage). On multi-day workstreams, the heavy half fired at the wrong cadence — workdays don't end on workstream boundaries, so the heavy ceremony was either skipped or inappropriately pulled forward.

The fix: split cleanly. **Daily is a branch wrap. Weekly is a release ceremony.** Both are PM-invoked; both are staleness-nudged so the PM knows when each is overdue.

---

## Overview

Daily and weekly are distinct ceremonies, both PM-invoked, staleness-nudged.
**Handoffs are the atom; the week-changelog is the index over them.**
`/workday-complete` synthesises from existing handoffs and the Step 4 daily summary — does not re-author.
`/workweek-complete` reads the index as ground truth, does not reconstruct from `git log`.

---

## The Four Commands

| Command | Cadence | Who invokes | Weight |
|---|---|---|---|
| `/workday-start` | Daily | PM (or agent on vague opens) | Lightweight orient |
| `/workday-complete` | Daily | PM at end of day | Branch wrap |
| `/workweek-start` | Weekly | PM at workstream boundary | Strategic orient |
| `/workweek-complete` | Weekly | PM when releasing | Release ceremony |

---

## When to Invoke Each

**`/workday-complete`** — at natural end-of-session. Not necessarily tied to a calendar day — invoke whenever a session is wrapping up and the branch should be consolidated. Runs in minutes.

**`/workweek-complete`** — at a workstream boundary: when a meaningful chunk of work is ready to land on main and release notes make sense. This is PM judgment, not a calendar trigger. A week with no meaningful progress doesn't need a release ceremony; a week with three shipped features does. Watch the staleness nudge from `/workday-complete` — once it fires (≥5 days AND ≥15 commits since last weekly reset), consider scheduling the ceremony.

**`/workweek-start`** — immediately after `/workweek-complete` resets the changelog, or at the start of a new project sprint. Sets the week's priorities in `tasks/week-changelog/HEADER.md`. Can be re-run mid-week to update priorities; the command detects whether a full reset or an in-place update is appropriate.

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

## The Week-Changelog

The week-changelog (`tasks/week-changelog/`) is the load-bearing innovation. It converts "weekly EM does archaeology" into "weekly EM reads a structured ledger."

### Structure

```
tasks/week-changelog/
  HEADER.md                          # week metadata — shared, weekly-only writes
  YYYY-MM-DD-{hostname}.md           # daily block, one per machine per day
  YYYY-MM-DD-{hostname}.md
  ...
```

**HEADER.md** holds the week's framing: start date, prior release SHA, last `/workweek-start` date (used for reset-or-update logic), and the PM's priorities. It is written by `/workweek-complete` on reset and by `/workweek-start` on (re-)runs. It is read by all four commands and by `bin/check-weekly-staleness.sh`.

**Daily files** are written by `/workday-complete` — one per machine per calendar day. Per-machine naming eliminates concurrent-write conflicts when multiple machines are active on the same day.

### Daily Block Schema

Each daily file contains a block with fixed fields — no free-form prose:

```markdown
## YYYY-MM-DD — {hostname}

**Branch:** work/{hostname}/YYYY-MM-DD
**Commits:** N (range: <oldest-sha>..<newest-sha>)
**Scope:** <one-line summary>
**Plans touched:** docs/plans/YYYY-MM-DD-foo.md (status: in-progress|shipped|reverted)
**Handoffs:** tasks/handoffs/YYYY-MM-DD-foo.md
**Decisions:** <extracted from today's handoffs — not re-authored>
**Blockers:** <extracted from handoffs, or "none">
**Validation:** validate=<exit-code> plugin-suite=<exit-code>
**Links:** archive/daily-summaries/YYYY-MM-DD.md, archive/completed/YYYY-MM.md
```

`Decisions:` and `Blockers:` are extracted from handoff content, not re-authored. `Validation:` is mechanically populated from gate exit codes — if either gate failed, `/workday-complete` never reaches the changelog append (blocking), so non-zero values appear only when doctrine is bypassed.

### Handoffs Are the Atom

The changelog does not duplicate handoff content — it points to the handoffs that already exist. The `Handoffs:` field is a pointer; the `Decisions:` and `Blockers:` fields are extracted summaries. `/workweek-complete` follows those pointers into the handoffs for deep evidence when drafting release notes.

---

## Staleness Signals

`bin/check-weekly-staleness.sh` reads HEADER.md and emits one of:
- **STALE** — both thresholds crossed: ≥5 days AND ≥15 commits since the `Prior week released:` SHA.
- **MILD** — one threshold crossed.
- **FRESH** — neither crossed.
- **UNKNOWN** — HEADER.md absent or unparseable (treat as never run).

`/workday-complete` calls this script in Step 10 and surfaces the result. STALE triggers a visible nudge; MILD is a softer note; FRESH/UNKNOWN are silent.

The commit-distance threshold is measured from the `Prior week released: ... (commit <sha>, ...)` field in HEADER.md — not from a branch tip. Branch-relative counts are wrong on this setup because `work/{machine}/{YYYY-MM-DD}` branches reset daily.

---

## `/pickup` Integration

`/pickup` gains ambient context from the week-changelog when resuming a prior-day handoff. After reading the handoff, it checks the handoff date:

- **Same day:** straight baton pass — changelog surface skipped.
- **Prior day:** glob `tasks/week-changelog/*.md` for daily files dated since the handoff (exclusive). Emit one line per file: `<date> (<hostname>): <Scope> — <shipped plans>`. Cap at ~10 lines.

This surfaces "while you were away" context without requiring the PM to read the full changelog manually.

---

## Archive Layout

On `/workweek-complete` Step 14 (and on `/workweek-start` full reset), daily files are archived:

```
archive/week-changelogs/
  2026-05-04/
    2026-05-04-striker.md
    2026-05-05-striker.md
    ...
  2026-05-11/
    ...
```

HEADER.md is rewritten in place (not archived). The archived directory is named for the `Week starting:` date from the prior HEADER.md. `/workweek-complete` reads release notes from the daily files before archiving them.

---

## Stale HEADER.md Guard

If `/workday-complete` detects that today is more than 14 days past the `Week starting:` date in HEADER.md, it emits a hard warning and refuses to append:

> "WARN: HEADER.md is stale (week started >14 days ago). Was `/workweek-complete` skipped? Resolve before appending."

This prevents daily files from silently accumulating past a missed weekly reset.

---

## Relationship Between the Two Ceremonies

- `/workday-complete` is a branch wrap, not a release ceremony.
- `/workweek-complete` is the release ceremony; it reads what the daily ceremony wrote.
- Neither ceremony merges to main directly — `/workday-complete` never merges; `/workweek-complete` delegates to `/merge-to-main`.
- ShellCheck, scc, improvement-queue triage, and the skill-description lint are weekly-only; they do not belong in the daily wrap.
