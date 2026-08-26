---
name: workday-complete
description: "End-of-day wrap — validate, consolidate branches, review, changelog."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Daily wrap: validate, consolidate branches, daily review, week-changelog, staleness. Does NOT
merge to main — `/workweek-complete` is the weekly heavy ceremony.

An assembler computes this into an 8-key decision object. An unconditional directive fires when
reached; a gated one fires once its judgment point resolves. Below: the judgment residue, plus
steps with no consumes-manifest CLI (dispatch/gate steps). Wiring detail throughout: wiki.
`$ARGUMENTS` is the optional day-summary.

## Step 0.9-1: Grant, Front Door

One shell call — this grant covers the Tier-U consumers this ceremony invokes downstream,
including the test-suite step inside `workday-complete-assemble`, which is the single most
expensive thing this ceremony runs (source its magnitude from `python
coordinator/tests/_spawn_budget.py`, never a hardcoded number here):

POSIX hosts: Shape A, `coordinator/snippets/resolve-coordinator-bin.md` — resolve
`tier-u-grant-cli`, then `workday-complete-args-and-validate parse-front-door`, then
`workday-complete-args-and-validate check-cross-machine`, each with `"${ARGUMENTS:-}"`.

PowerShell hosts (rung 0, Shape W, same snippet), one command per line:

    & "$env:COORDINATOR_SETTINGS_HOME\bin\tier-u-grant-cli.cmd" grant ceremony "workday-complete Tier-U consumers" --ceremony workday-complete
    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-args-and-validate.cmd" parse-front-door "$ARGUMENTS"
    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-args-and-validate.cmd" check-cross-machine "$ARGUMENTS"

Capture stdout+exit code of each; non-zero on either stops. `eval` the front-door's stdout to set
`$FOR_DATE`/`$ONLY_MODE`/`$ONLY_FLAG`/`$SCOPE_SUMMARY`. The cross-machine check fails loud on a
cross-machine `--for-date` mismatch — stop and report.

## Step 2: Compute the Ceremony

POSIX hosts: Shape A, resolving `workday-complete-assemble brief
${FOR_DATE:+--for-date "$FOR_DATE"} $ONLY_FLAG ${SCOPE_SUMMARY:+--scope-summary="$SCOPE_SUMMARY"}`.

PowerShell hosts (rung 0, Shape W):

    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-assemble.cmd" brief $(if ($FOR_DATE) { "--for-date", $FOR_DATE }) $ONLY_FLAG $(if ($SCOPE_SUMMARY) { "--scope-summary=$SCOPE_SUMMARY" })

Splice `$ONLY_FLAG`/`${SCOPE_SUMMARY:+...}` exactly as shown — do not hand-derive (wiki).

## Step 3-4: RAG Nudge, Plugin Validation

If `ToolSearch` finds `mcp__project-rag__*`, run the staleness survey; surface only if
stale/very-stale. Run `node --test tests/plugin-ecosystem/run.js` — hook-behavior failures block;
non-hook failures report and continue.

## Step 5: Resolve Judgment Points

Read each `judgment_points[]` entry verbatim — question/evidence/dispositions are fully formed.

- `jp_step2_5_dirty_tree_ambiguous`: adopt-commit / discard / attribute-to-session; look harder if
  in doubt (wiki).
- `jp_step3_5_backfill_cap`: backfill all, or bounded subset (default).
- `jp_step4b_analyst_dispatch` / `jp_step4c_observer_dispatch`: dispatch unless
  `skip_no_new_work`.
- `jp_step4_5_clustering_dispatch`: dispatch per ≥2-entry chain; `skip_only_mode` under
  `$ONLY_MODE=1`.
- `jp_step4e_health_ledger_new_rows`: add `?` rows for touched systems; never audit clocks/grades.
- `jp_day_goal_closeout`: `decisions["day_goal_closeout"] = {goal_id: "done"|"dropped"}`, or skip.

## Step 6: Apply

POSIX hosts: Shape A, resolving `workday-complete-assemble apply --decisions '<json map of
judgment_point_id -> {"disposition": "<value>"}>' ${FOR_DATE:+--for-date "$FOR_DATE"} $ONLY_FLAG`.

PowerShell hosts (rung 0, Shape W):

    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-assemble.cmd" apply --decisions '<json map of judgment_point_id -> {"disposition": "<value>"}>' $(if ($FOR_DATE) { "--for-date", $FOR_DATE }) $ONLY_FLAG

Read `landed`/`blocked`/`failed`; `blocked` returns to Step 5. Exit-code tables: wiki.

## Step 6b-7: Daily-Summary Dispatch and Stitch

Dispatch a Sonnet analyst (target day: `$FOR_DATE` under `$ONLY_MODE=1`, else today) writing
`archive/daily-summaries/<target-day>-<machine>.md` (field detail: wiki), plus a parallel
strategic observer (skip under `$ONLY_MODE=1`) writing debt-backlog YAML + a
`<target-day>-<machine>.observer.md` sidecar (field detail: wiki). Skip both on
`skip_no_new_work`. Each Step 6 backfill gap-row TSV entry (oldest-first) gets its own analyst
dispatch, only after Step 6 completes (wiki).

POSIX hosts: Shape A, resolving `workday-complete-close stitch-sidecar`.

PowerShell hosts (rung 0, Shape W):

    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-close.cmd" stitch-sidecar

Pass `--today` with the target day under `$ONLY_MODE=1`. Non-zero is a HARD FAIL. Verify the
stitch landed via a single-line Grep/read check on
`archive/daily-summaries/<target-day>-<machine>.md` for `^## Strategic Review` occurrence count
(harness `Grep`/`Select-String`, not a shell pipeline — the check is read-only on both hosts).

Zero: dispatch the observer and re-stitch. Two-plus: reconcile by hand, never re-dispatch.

Health ledger (`jp_step4e_health_ledger_new_rows`): add `?` rows to `state/health-ledger.md` for
newly-touched systems. Remove `tasks/daily-review-scratch`.

## Step 8: Completion-Log Clustering

Skip `$ONLY_MODE=1`. Per `jp_step4_5_clustering_dispatch`: dispatch a `narrative:` synthesis
worker per ≥2-entry chain lacking one (≤300 words, SHAs preserved, no editorial bucketing).

## Step 9: Completed Archive Audit

Skip `$ONLY_MODE=1`. Add/fix completion entries from today's commits. Report: _"Archive audit: N
verified, M added, K corrected."_

## Step 9b-9c: Coverage, Baton-Drift, Auto-Memory Drain

POSIX hosts: Shape A, resolving `day-coverage-sweep <resolved day, YYYY-MM-DD>` then
`baton-drift-sweep`.

PowerShell hosts (rung 0, Shape W), one command per line:

    & "$env:COORDINATOR_SETTINGS_HOME\bin\day-coverage-sweep.cmd" <resolved day, YYYY-MM-DD>
    & "$env:COORDINATOR_SETTINGS_HOME\bin\baton-drift-sweep.cmd"

Skip both under `$ONLY_MODE=1`. Read their counts straight off, never collapsed to one number
(`foreign`/`sibling_homed` are not gaps; `stranded` must be zero, `held` need not be — wiki).

POSIX hosts: Shape A, resolving `check-auto-memory-drained --root .`.

PowerShell hosts (rung 0, Shape W):

    & "$env:COORDINATOR_SETTINGS_HOME\bin\check-auto-memory-drained.cmd" --root .

Blocking. Exit 1 names every residual path owned by this session — resolve PROMOTE (durable home,
restated in its own voice) or DROP per path, delete, re-run to confirm exit 0 (disposition detail:
wiki).

## Step 9d: claudemeta Manifest Cadence

Skip the step entirely if `state/reference/generate-claudemeta-manifest.py` is absent —
DoE-specific, no-op in every other repo. Where it exists, no prompt:

```
python state/reference/generate-claudemeta-manifest.py --cadence
```

One process, not a shell conditional — it checks, and regenerates plus commits only on real drift.
Clean: silent. Drifted: surface the generator's own stdout line, nothing more.

## Step 10: Final Summary

Report by exception, ≤200 words — a clean wrap is the shortest run.

```
## Workday Complete

**Branch state:** [branch name], rebased on main, pushed
**Day-goal closeout:** [Step 6 goal-close-day summary]
**NOT merged to main** — use `/merge-to-main` when ready
```

Append only if true: day summary / targeted wrap prefix; validate exit non-zero; orphan-reap
non-zero; plugin-validation failures; archive-audit added/corrected; commit-coverage/baton-drift
(`$ONLY_MODE=0` AND `orphaned`/`stranded` > 0); auto-memory disposition list (residue printed);
weekly staleness STALE/MILD; post-ceremony hook line non-empty; spec-dispatch discharge (scoped
reviewer verdict, integration commit, plan-reconciliation state). Never print
consolidated/review/reconcile/changelog lines — the commit already records them.

**Negative-spec — these are gone, do not restore them.** `Branches consolidated`, `Daily review`,
`Completion reconcile`, and `Week-changelog` are not printed at all. Each was a count or path the
ceremony's own commit already records, carrying no PM decision. Their absence is not a signal the
step was skipped — the directives still run, the commit is their record. Do not re-add any of them
"for completeness": completeness of the *ceremony* is the assembler's job, completeness of the
*report* is not the same thing.

Scope boundary and command relationships: wiki.
