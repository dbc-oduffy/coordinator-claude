---
name: workday-complete
description: "End-of-day wrap — validate, consolidate, review, changelog."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Daily wrap: validate, consolidate branches, daily review, week-changelog, staleness. Never
merges to main — that is `/workweek-complete`.

An assembler computes this into an 8-key decision object. An unconditional directive fires when
reached; a gated one once its judgment point resolves. Below: the judgment residue, plus steps
with no consumes-manifest CLI (dispatch/gate steps). Wiring detail: wiki.
`$ARGUMENTS` is the optional day-summary.

## Step 0.9-1: Grant, Front Door

One shell call — this grant covers the Tier-U consumers this ceremony invokes downstream,
including the test-suite step inside `workday-complete-assemble`, which is the single most
expensive thing this ceremony runs (source its magnitude from `python
coordinator/tests/_spawn_budget.py`, never a hardcoded number here):

POSIX hosts: Shape A, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` — resolve
`tier-u-grant-cli`, then `workday-complete-args-and-validate check-cross-machine`, each with
`"${ARGUMENTS:-}"`.

PowerShell hosts (rung 0, Shape W, same snippet), one command per line:

    & "$env:COORDINATOR_SETTINGS_HOME\bin\tier-u-grant-cli.exe" grant ceremony "workday-complete Tier-U consumers" --ceremony workday-complete
    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-args-and-validate.exe" check-cross-machine "$ARGUMENTS"

Capture stdout+exit code of each; non-zero on either stops. A cross-machine `--for-date` mismatch
fails loud — stop and report; a pass prints nothing.

No tool exports the variables — parse them from `$ARGUMENTS` yourself: `--for-date <YYYY-MM-DD>`
sets `$FOR_DATE`; `--only` sets `$ONLY_MODE=1` and `$ONLY_FLAG=--only`; `--catch-up` or `--conclude` sets `$PERIOD_FLAG` to that flag (mutually
exclusive, each refused beside `--only`/`--for-date`; neither: empty, the clock decides); the remaining words are
`$SCOPE_SUMMARY`. Anything absent is empty, and `$ONLY_MODE=0`. No arguments: all empty.

## Step 2: Compute the Ceremony

POSIX hosts: Shape A, resolving `workday-complete-assemble brief
${FOR_DATE:+--for-date "$FOR_DATE"} $ONLY_FLAG $PERIOD_FLAG ${SCOPE_SUMMARY:+--scope-summary="$SCOPE_SUMMARY"}`.

PowerShell hosts (rung 0, Shape W):

    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-assemble.exe" brief $(if ($FOR_DATE) { "--for-date", $FOR_DATE }) $ONLY_FLAG $PERIOD_FLAG $(if ($SCOPE_SUMMARY) { "--scope-summary=$SCOPE_SUMMARY" })

Splice `$ONLY_FLAG`/`$PERIOD_FLAG`/`${SCOPE_SUMMARY:+...}` exactly as shown (wiki).

## Step 3-4: RAG Nudge, Plugin Validation

If `ToolSearch` finds `mcp__project-rag__*`, run the staleness survey with this repo's root as
`project_root` (an unnamed call is ambiguous with a second live session). Surface
stale/very-stale only for a repo `project_list_sources` reports as `origin: consumer-project` —
elsewhere the step is N/A and silent (`A-RAG-VERDICT-ON-AN-UNINDEXED-REPO-IS-NOT-STALENESS`).
A consumer-project registration with `reachable=false`/`root_exists=false` while the root exists
on disk is a broken registration, not staleness: report one line naming the repo and the `origin`/`reachable`/`root_exists` values the tool returned (it returns no `resolution` field), and route it to the index owner; never re-index from here.

Plugin validation runs only in the plugin source repo: where `coordinator/tests/plugin-ecosystem/run.js` exists under
the repo root, run `node --test coordinator/tests/plugin-ecosystem/run.js` from `coordinator/`
— hook-behavior failures block; non-hook failures report and continue. Every other repo: N/A,
one report line, never the plugin-cache copy (it cannot resolve the engine checkout).

**The register stall check:** `coordinator-invoke requirement_register.stall_report '{"today":"<today>"}'` (settings-home forwarder); render findings in the wrap report under `### Register stall check`, omitted when empty.

**Step 4b: Structural index.** Run `"$_py" "$COORDINATOR_SETTINGS_HOME/bin/structural-index-refresh"` (POSIX; on PowerShell `& "$env:COORDINATOR_SETTINGS_HOME\bin\structural-index-refresh.exe"`, `snippets/resolve-coordinator-bin.md`) (non-blocking, always exit 0; `COORDINATOR_STRUCTURAL_INDEX_REFRESH_OFF=1` disables) — report its line if it prints one. A "still running" or "cold build started" line has no
completion signal in this run: the detached run writes its outcome (`exit_code`,
`stderr_tail`, `deferred`) to `.structural-index/refresh-last.json`. Read it at Step 10; a
non-zero or missing `exit_code` there is a report line, still non-blocking.

## Step 5: Resolve Judgment Points

Read each `judgment_points[]` entry verbatim — question/evidence/dispositions are fully formed.

- `jp_step2_5_dirty_tree_ambiguous`: adopt-commit / discard / attribute-to-session. Attribute only
  to a session the claim index shows holding the path — `liveness=dead` is an orphan, not an
  owner, even where the tool labels it `peer-claim (needs PM)`; that label routes nowhere, and
  an orphan is adopt-commit. Everything left over is adopt-commit; Step 9e will not let the ceremony end while any of
  it is still dirty.
- `jp_step3_5_backfill_cap`: a backfill disposition the PM already stated this session ("backfill any records we've missed") settles it as backfill all. The point is raised only when the scan exceeds the cap; the backfill-cap run rule resolves it to `backfill_all`.
- `jp_step4b_analyst_dispatch`: dispatch unless `skip_no_new_work`. `jp_step4c_observer_dispatch`:
  never dispatch daily; the observer runs weekly (`/workweek-complete` Step 7b).
- `jp_step4_5_clustering_dispatch`: dispatch per ≥2-entry chain; `skip_only_mode` under `$ONLY_MODE=1`.
- `jp_step4e_health_ledger_new_rows`: add `?` rows for touched systems; never audit clocks/grades.
- `jp_day_goal_closeout`: `day_goal_closeout` is a top-level key of the decisions file, beside the judgment-point entries: `{"day_goal_closeout": {goal_id: "done"|"dropped"}}`, or skip (shape: wiki).

## Step 6: Apply

POSIX hosts: Shape A, resolving `workday-complete-assemble apply --decisions-file <path>` (path to
a file containing the json map of judgment_point_id -> {"disposition": "<value>"}) `${FOR_DATE:+--for-date "$FOR_DATE"} $ONLY_FLAG $PERIOD_FLAG`.

PowerShell hosts (rung 0, Shape W):

    & "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-assemble.exe" apply --decisions-file <path> $(if ($FOR_DATE) { "--for-date", $FOR_DATE }) $ONLY_FLAG $PERIOD_FLAG

Read `landed`/`blocked`/`failed`; `blocked` returns to Step 5; a `blocked` directive the decisions file set to `skip` is settled, never a return (exit codes: wiki).

## Step 6b-7: Daily-Summary Dispatch and Stitch

Dispatch a Sonnet analyst (target day: `$FOR_DATE` under `$ONLY_MODE=1`, else today; under catch-up, gap-day analysts only) writing
`archive/daily-summaries/<target-day>-<machine>.md` (analyst only; the strategic observer runs
weekly in `/workweek-complete` Step 7b). Skip on `skip_no_new_work`. Each Step 6 backfill gap-row
TSV entry (oldest-first) gets its own analyst dispatch, only after Step 6 completes (wiki).

A daily summary carries no `## Strategic Review` heading and no `.observer.md` sidecar; no stitch
runs and the heading count is not checked.

Health ledger (`jp_step4e_health_ledger_new_rows`): add `?` rows to `state/health-ledger.md`
for touched systems. Remove `tasks/daily-review-scratch`.

## Step 8: Completion-Log Clustering

Skip `$ONLY_MODE=1` or catch-up. Per `jp_step4_5_clustering_dispatch`: dispatch a `narrative:` synthesis
worker per ≥2-entry chain lacking one (≤300 words, SHAs preserved, no editorial bucketing).

## Step 9: Completed Archive Audit

Skip `$ONLY_MODE=1` or catch-up. Add/fix entries from today's commits and the brief's receipts (see
`release-and-distribution/completion-receipts.md`); an uncovered receipt goes into a meta-entry. Report: _"Archive audit: N verified, M added, K corrected; R receipts, U without
a covering entry."_

## Step 9b-9c: Coverage, Baton-Drift, Auto-Memory Drain

POSIX hosts: Shape A, resolving `day-coverage-sweep <resolved day, YYYY-MM-DD>` then
`baton-drift-sweep`.

PowerShell hosts (rung 0, Shape W), one command per line:

    & "$env:COORDINATOR_SETTINGS_HOME\bin\day-coverage-sweep.exe" <resolved day, YYYY-MM-DD>
    & "$env:COORDINATOR_SETTINGS_HOME\bin\baton-drift-sweep.exe"

Skip both under `$ONLY_MODE=1` or catch-up. Read counts straight off, never collapsed to one number
(`foreign`/`sibling_homed` are not gaps; `stranded` must be zero, `held` need not be — wiki). Act on `orphaned`/`stranded`/non-terminal
handoff counts by their category, not the raw total: a large unclaimed or non-terminal count is
a backlog to triage by category, not one failure (wiki).

POSIX hosts: Shape A, resolving `check-auto-memory-drained --root .`.

PowerShell hosts (rung 0, Shape W):

    & "$env:COORDINATOR_SETTINGS_HOME\bin\check-auto-memory-drained.exe" --root .

Blocking. Exit 1 names every residual path this session owns — PROMOTE (durable home, own voice)
or DROP per path, delete, re-run to confirm exit 0 (wiki).

## Step 8a: Scratch Purge

`fleet.scratch_hygiene` cadence `workday_complete`, advisory, dry-run first; no local delete fallback:

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" fleet.scratch_hygiene '{"repo_root":"<repo-root>","cadence":"workday_complete","apply":false}'`

Re-call with `"apply":true` only when the summary's `capabilities` includes `hold_pending_marker`.
Op absent, capability absent, or error: report the plan or "fleet.scratch_hygiene not yet
available" and continue. Exit 1 is a report section.

## Step 8b: Maintenance Checkpoint

`git.maintenance` daily tier. Advisory, non-zero reported, ceremony continues:

`& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" git.maintenance '{"tier":"daily","repo":"<repo-root>"}'`

Shape W above / Shape A/B POSIX — `snippets/resolve-coordinator-bin.md`. `--repo` flag refused
(`scope='none'`); `repo` goes in the JSON params, not omitted.

## Step 9e: Emitted Workflow Script Sweep

Run `coordinator-invoke fleet.prune_emitted_output '{}' --repo <repo-root>` (Shape W/A as Step 8b)
over `state/**/fire-*.mjs` and `state/**/*.mjs.emitted.json`: it deletes finished units;
`git rm --cached` any that are tracked and commit from the index.
Advisory; the ceremony continues on failure.

## Step 9d: claudemeta Manifest Cadence

Skip the step entirely if `state/reference/generate-claudemeta-manifest.py` is absent —
source-repo only, no-op in every other repo. Where it exists, no prompt:

```
python state/reference/generate-claudemeta-manifest.py --cadence
```

One process, not a shell conditional — it checks, and regenerates plus commits only on real drift.
Clean: silent. Drifted: surface the generator's own stdout line, nothing more.

## Step 10: Final Summary

Report by exception, ≤200 words — a clean wrap is the shortest run. Under catch-up, lead with the brief's narration line `Catch-up run: <missed periods> backfilled; <in_progress> left open`.

```
## Workday Complete

**Branch state:** [branch name], rebased on main, pushed
**Day-goal closeout:** [Step 6 goal-close-day summary]
**NOT merged to main** — use `/merging-to-main` when ready
```

Append only if true: day summary / targeted wrap prefix; validate exit non-zero; orphan-reap
non-zero; plugin-validation failures; archive-audit added/corrected; commit-coverage/baton-drift
(`$ONLY_MODE=0` AND `orphaned`/`stranded` > 0); auto-memory disposition list (residue printed);
weekly staleness STALE/MILD; post-ceremony hook line non-empty; spec-dispatch discharge (scoped
reviewer verdict, integration commit, plan-reconciliation state); the number of Step 6
backfill gap rows dispatched, when > 0. Never print consolidated/review/reconcile lines or a
changelog path — the commit already records them.

**Negative-spec — these are gone, do not restore them.** `Branches consolidated`, `Daily review`,
`Completion reconcile`, and the `Week-changelog` path/count line are not printed at all. Each was a count or path the
ceremony's own commit already records, carrying no PM decision. The one changelog line that prints is the Step 6 backfill gap-row count when > 0. Their absence is not a signal the
step was skipped — the directives still run, the commit is their record. Do not re-add any of them
"for completeness": completeness of the *ceremony* is the assembler's job, completeness of the
*report* is not the same thing.

Scope boundary and command relationships: wiki.
