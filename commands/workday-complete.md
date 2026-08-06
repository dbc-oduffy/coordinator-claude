---
name: workday-complete
description: "End-of-day wrap — validate, consolidate branches, review, changelog."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Lightweight daily wrap: validate, consolidate branches, run the strategic daily review, append to the week-changelog, and surface staleness signals. **Does NOT merge to main.** Heavy ceremony (docs sweep, ShellCheck, improvement-queue triage) is weekly — see `/workweek-complete`.

The `workday_complete` assembler (`claude-klabauter coordinator_core/workday_complete/`) computes this ceremony: every mechanical step collapses to one `directives[]` entry naming an existing CLI, and every open question surfaces as one `judgment_points[]` entry for you to resolve. Nothing below branches on what the assembler already resolved — you read the resolved judgment array and answer it; the assembler's own `directives[]` fire the mechanics. A handful of steps have no consumes-manifest CLI at all (front-door argument parsing, the RAG staleness nudge, the plugin validation suite, the daily-review Sonnet dispatch, the health-ledger edit, scratch cleanup) — those are genuinely EM-side actions no directive can perform, not branches on an assembler decision, and stay as direct steps below.

`$ARGUMENTS` refers to the user-supplied day-summary argument to the slash command (may be empty), per Claude Code conventions.

---

## Step 1: Front Door — Parse Arguments (must run before the assembler)

The assembler is a pure compute call with no `$ARGUMENTS` parameter and cannot export a variable back into your shell — front-door parsing has to happen here, first, in your own shell:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-complete-args-and-validate" parse-front-door "${ARGUMENTS:-}"
```

Capture stdout AND the real exit code separately (a command-substitution assignment discards the exit code). Non-zero — stop; the parser exits loud on stderr when `--only` was supplied without `--for-date`. Otherwise `eval` the captured stdout to set `$FOR_DATE`, `$ONLY_MODE`, `$ONLY_FLAG`, `$SCOPE_SUMMARY`. `$ONLY_MODE` is the `0`/`1` value the steps below branch on; `$ONLY_FLAG` is the same fact pre-rendered as the CLI form (`--only` or empty) for Step 2 to splice into an argv without a shell value-test.

Cross-machine restriction (`--for-date` is current-machine-only — a cross-machine `--for-date` would silently produce a summary-only block):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-complete-args-and-validate" check-cross-machine "${ARGUMENTS:-}"
```

No-op (exit 0) unless both `--for-date` and a `--machine <other>` were supplied together; fails loud (stderr, exit 1) on a mismatch — stop and report rather than retrying.

**Routing:** `--for-date <date>` without `--only` targets that date via the assembler's backfill Phase-B directive (part of Step 6's apply), then continues the full today-ceremony. `--for-date <date> --only` wraps ONLY the targeted date: Steps 1–3 (front door, compute ceremony, RAG staleness nudge) run as usual, and Step 4 (Plugin Validation Suite) still runs unconditionally — it is a repo-health gate, not a date-scoped one, and must never be skipped under `--only`. Step 5 resolves judgment points and Step 6 applies directives as usual, including the Phase-B backfill wrap — date-scoped to `$FOR_DATE` under `--only` since Step 2 now threads `--for-date`/`--only` into the assembler (see Step 6b) — followed by Step 6b's per-gap-day analyst dispatch. Step 6's own week-changelog directive (`d_step9_changelog`) correctly self-skips under `--only`, since Phase B already committed the targeted block — it receives `--only-mode` from Step 2's threading, without which a targeted wrap writes a spurious today-scoped block alongside the backfilled one. Step 7 (Daily-Summary Dispatch and Stitch) re-targets to `$FOR_DATE` rather than being skipped — see Step 7's own `$ONLY_MODE` handling. Steps 8 (Completion-Log Clustering), 9 (Completed Archive Audit), and 9b (Coverage & Baton-Drift) self-skip under `$ONLY_MODE=1` per their own step text, since they are inherently today-scoped rollups rather than per-day artifacts. Step 10 prints the final summary as usual, prefixed with the `Targeted wrap` line. Default (no flags): unchanged today-keyed ceremony, `$SCOPE_SUMMARY` equals `$ARGUMENTS`.

---

## Step 2: Compute the Ceremony

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-complete-assemble" brief ${FOR_DATE:+--for-date "$FOR_DATE"} $ONLY_FLAG ${SCOPE_SUMMARY:+--scope-summary="$SCOPE_SUMMARY"}
```

`--for-date`/`--only` thread into `d_step3_5_backfill_phase_b` (Step 6's Phase-B backfill dispatch) so a targeted wrap actually stays within its target — see Step 6b. `$ONLY_FLAG` comes from Step 1's `eval`, already resolved to `--only` or the empty string. Use it as-is; **do not hand-write `${ONLY_MODE:+--only}`** — `$ONLY_MODE` is `0` or `1` and never empty, so that expansion emits `--only` on `0` too, silently converting a plain `--for-date` run into a targeted-only wrap that skips every other gap day. `${SCOPE_SUMMARY:+--scope-summary="$SCOPE_SUMMARY"}` is the CORRECT idiom here (unlike `$ONLY_MODE`'s trap above) — `$SCOPE_SUMMARY` is genuinely empty when the user supplied no day-summary prose (never the string `"0"` or any other always-truthy placeholder), so `:+` only fires when there is real prose to thread. The single-token `--scope-summary=VALUE` eq-form (never a two-token `--scope-summary "$VALUE"` split) is deliberate — it is the one spelling immune to a leading-dash `$SCOPE_SUMMARY` (e.g. a user typing `"-- wrapped the refactor"`) being misparsed by argparse as a new option; see `brief.py`'s own `main()`/`_build_directives` docstrings for the full hazard writeup. `$SCOPE_SUMMARY` reaches `d_step9_changelog` (the default route) unconditionally, and `d_step3_5_backfill_phase_b` (the backfill route) only when `--for-date` is also set.

Returns the 8-key decision object (`artifact`/`preflight`/`gates`/`directives`/`judgment_points`/`decisions`/`narration`/`next_move`). `preflight.consumes_manifest` names every CLI the assembler orchestrates — read `brief.py`'s own module docstring for the closed set; it is not duplicated here.

---

## Step 3: RAG Staleness Nudge (informational, no consumes-manifest CLI)

If `ToolSearch` finds any `mcp__project-rag__*` tool, run the staleness survey. Surface in the final summary only if verdict is `stale` or `very-stale`. Skip silently otherwise.

---

## Step 4: Plugin Validation Suite (blocking gate, no consumes-manifest CLI)

Run `node --test tests/plugin-ecosystem/run.js` from the resolved coordinator plugin root and capture its exit code.

- **Hook-behavior failures:** blocking — stop and fix.
- **Non-hook failures:** report in summary, flag for morning, do not block git steps.

---

## Step 5: Resolve Judgment Points

Present each open `judgment_points[]` entry from Step 2's envelope as a legible question — never a raw JSON dump — and record your disposition. The assembler offers a `recommendation` on the dispatch-shaped points; it is an offer, never a control-flow input you must accept.

**Ambiguous dirty-tree files** (`jp_step2_5_dirty_tree_ambiguous`, fires only when `workday-complete-step2_5-dirty-tree` found source-tree edits without attribution or other unresolved paths): _"Adopt-commit (mine, forgot to attribute), discard (abandoned), or attribute to another session?"_ **If in doubt — look harder**, don't guess: read the file, `git log -- <path>` for prior touches, check `state/handoffs/` and `archive/handoffs/` for a `scope:` block naming it. This gates Step 6's branch consolidation — until it resolves, the branch stays as-is.

**Backfill cap** (`jp_step3_5_backfill_cap`, fires only when the post-A0 gap-row count exceeds 10): _"Backfill scan found more than 10 skipped days. Backfill all, or a bounded subset?"_ A 10+-day gap is a signal worth a human glance, not a silent 10-agent burst — the assembler's own default recommendation is `bounded_subset`.

**Daily-summary analyst dispatch** (`jp_step4b_analyst_dispatch`): dispatch the Sonnet daily-summary analyst for today unless the skip condition holds (zero new commits AND no agent-driven changes outside commits) — resolve `skip_no_new_work` in that case and write a one-line "no work today" summary instead.

**Strategic observer dispatch** (`jp_step4c_observer_dispatch`): dispatch in parallel with 4b whenever 4b itself dispatches; skip together under the same no-new-work condition.

**Completion-log clustering dispatch** (`jp_step4_5_clustering_dispatch`): dispatch a clustering worker per chain with ≥2 completion entries found in today's completions; resolve `skip_only_mode` when `$ONLY_MODE=1` (targeted wraps don't cluster).

**Health-ledger new rows** (`jp_step4e_health_ledger_new_rows`): add unaudited `?` rows for systems touched today with no existing row. **Do NOT touch audit clocks** (`Last full audit`, `Last targeted audit`) or any grade on any row — those are written only by `/architecture-survey` (full) and `/architecture-audit` (targeted).

---

## Step 6: Apply — Execute the Directives

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-complete-assemble" apply --decisions '<json map of judgment_point_id -> {"disposition": "<value>"}>' ${FOR_DATE:+--for-date "$FOR_DATE"} $ONLY_FLAG
```

`--for-date`/`--only` are threaded here for the same reason Step 2 threads them: `apply` never trusts the printed brief — it recomputes it in-process before executing anything, so without these two flags the recompute rebuilds `d_step3_5_backfill_phase_b` unscoped and a targeted wrap silently wraps every gap day in the half that actually mutates. `$ONLY_FLAG` bare and unquoted, exactly as at Step 2 — see that step's note on why `${ONLY_MODE:+--only}` is the trap.

Executes every directive whose gate is open — a directive with no `depends_on` fires unconditionally; a gated directive fires only once its judgment point's CHOSEN disposition names it in `resolves`. This covers: Step-1 validate, cruft-sweep, completion-entry reconcile, crash-orphan reap, branch consolidation, backfill scan + anchor injection + Phase-B wrap dispatch, daily inventory (`standup`), today's-completions pull for the archive audit, bug-backlog prune, improvement-queue depth nudge, day-goal closeout (`goal-close-day`), week-changelog append, weekly staleness check, and the post-command hook + emission-cadence tail. Read the printed `landed`/`blocked`/`failed` report — a `blocked` entry means its gating judgment point is still unresolved; go back to Step 5. The Phase-B backfill directive's own week-changelog append is mechanical (a directive can run a CLI); the per-gap-day daily-summary *artifact* is not — go to Step 6b to dispatch it.

**Backfill Phase-B's stdin/stdout wiring, for reading the report:** `d_step3_5_backfill_scan` (unconditional) prints one TSV row per gap day it found; that captured stdout is BOTH fed as stdin to `d_step3_5_backfill_phase_b` (which appends one week-changelog block per row) AND re-emitted verbatim into this apply report, in that order — so a gap day's row is visible in the report before Phase B ever touches it. Step 6b reads that same printed row set.

**Validate exit-code meaning** (surfaces via the `d_step1_validate` result): `0` proceed; `1` UBT resolved blocked — stop and fix the C++ compile error (override only with PM authorization, `COORDINATOR_OVERRIDE_UBT_GATE=1`); `2` fast-test build failure or missing interpreter — stop and fix; `3` fast-test failures only — fix what's quick, flag the rest, proceed; `4` resolver lib missing — configure `fast_test_cmd:` in `coordinator.local.md` or repair the install.

**Branch-consolidation exit-code meaning** (`d_step3_consolidate`): `0` full success; `1` startup error (detached HEAD, or current branch is `main`/`master`) — report and stop; `2` merge conflict during sibling merge — report and halt; `3` reconcile conflict with `origin/main`; `4` push rejected twice — report to PM; `5` `cs_compute_machine` lib unavailable — report to PM.

**Auto-disposition is workday-complete-specific by design.** The dirty-tree gate is replicated across all three session terminators (workstream-complete, handoff, workday-complete), but the disposition diverges — the daily wrap absorbs the day's cross-session housekeeping accumulation, which is why it auto-disposes clear-wins and only surfaces the genuinely ambiguous case above. Do NOT propagate this allow-list to the other two terminators.

---

## Step 6b: Phase-B Daily-Summary Backfill Dispatch (genuine EM action — no directive can dispatch a subagent)

`d_step3_5_backfill_phase_b` (Step 6) appends the week-changelog block for every gap day the scan found, but it never produces a daily-summary artifact — that requires a subagent dispatch, which is genuinely EM-side.

**Ordering here is load-bearing — Step 6 (scan + Phase-B wrap) must complete before this step writes any `archive/daily-summaries/<day>-<machine>.md`.** `workday-complete-backfill-scan`'s coverage predicate treats a day as covered if a matching file exists in EITHER `state/week-changelog/` OR `archive/daily-summaries/` — writing a gap day's daily-summary artifact before the scan runs flips that day to "covered," the scan returns zero rows for it, and Phase B silently no-ops (exit 0, empty stdout, no week-changelog block) with nothing to alert you. Never write a gap day's daily-summary artifact ahead of Step 6, including when backfilling multiple gap days by hand.

**Phase B is date-scoped via `--for-date`/`--only`, threaded from Step 2 into the assembler's `d_step3_5_backfill_phase_b` directive.** `workday-complete-close backfill-dispatch-rows` accepts `--for-date` and `--only-mode`; Step 2 now supplies both when set, so `--only` genuinely wraps ONLY `$FOR_DATE` — every other gap row is left entirely untouched (no week-changelog block, no daily-summary artifact), matching what a targeted wrap should do. Without `--only` (default, or `--for-date` given alone), Phase B still wraps every gap row the scan found, unchanged from before.

Under `$ONLY_MODE=1`, this step is a clean no-op: Phase B touched only the `$FOR_DATE` row, and that row's daily-summary artifact is already covered by Step 7 (re-targeted per its own text) — dispatching an analyst here too would duplicate that work. Do not dispatch for any other row; Phase B did not wrap them.

Otherwise (default, `$ONLY_MODE=0`), read the gap-row TSV from Step 6's apply report (`d_step3_5_backfill_scan`'s captured stdout, re-emitted before Phase B consumes it — see Step 6's wiring note above): `workday-complete-backfill-scan`'s row format is `<YYYY-MM-DD>\t<commit_count>\t<baseline_sha>\t<tip_sha>`, one row per gap day, oldest-first; empty stdout means no gap days and this step is a clean no-op. For each row, dispatch one Sonnet daily-summary analyst for that row's date — same prompt shape as Step 7's Analyst below, substituting the row's `<YYYY-MM-DD>` for the target day and `<baseline_sha>..<tip_sha>` for the `git diff` range.

---

## Step 7: Daily-Summary Dispatch and Stitch (genuine EM action — no directive can dispatch a subagent)

**Target day:** `$FOR_DATE` when `$ONLY_MODE=1` (re-targeted, never skipped — a targeted wrap must still produce its own daily-summary artifact, per the incident this section was rewritten to close); today's local calendar day otherwise. Produce `archive/daily-summaries/<target-day>-<machine>.md` (per-machine naming — mirrors `state/week-changelog/<target-day>-<machine>.md`). Skip this whole step only when `jp_step4b_analyst_dispatch` resolved `skip_no_new_work` (a genuinely empty day) — `$ONLY_MODE=1` alone is never a reason to skip.

**Analyst** (per `jp_step4b_analyst_dispatch`'s resolution): dispatch a Sonnet analyst (`model: "sonnet"`, `run_in_background: true`) that reads `inventory.md` (Step 6's `standup` directive output) + the target day's completions (Step 6's completions-pull directive output, or a completions pull scoped to `$FOR_DATE` when `$ONLY_MODE=1`) + `git diff <baseline>..HEAD` for the target day, then writes `archive/daily-summaries/<target-day>-<machine>.md` with Work Completed / Systems Affected / Architectural Decisions sections — identify decisions made (even implicit ones) and their consequences, not just what changed. Include a `covered_tip_sha` field: the newest commit the summary's prose *actually describes* (never blindly the day's actual tip — a downstream backfill scan treats a missing or wrong-tip anchor as a gap), and a `covered_machine` field naming the resolved machine slug.

**Strategic observer** (per `jp_step4c_observer_dispatch`'s resolution, parallel with the analyst): skip under `$ONLY_MODE=1` — its debt-backlog / `weekly-arch-review` output is a today-cadence signal, and re-running it once per backfilled day would duplicate weekly-review material without a corresponding today-cadence benefit. Otherwise dispatch an unnamed Sonnet worker (`general-purpose`, `run_in_background: true`) — NOT a named persona; personas are Opus-only and reserved for `/workweek-complete`. It reads the same inputs as the analyst, never the analyst's prose, and writes debt-backlog YAML entries via `coordinator-queue-append --schema debt-backlog` (`tags: [weekly-arch-review]` for architectural-risk candidates) plus a `## Strategic Review (Sonnet daily observer)` sidecar at `archive/daily-summaries/<target-day>-<machine>.observer.md`.

**Stitch:** once both complete (or immediately when the observer was skipped under `$ONLY_MODE=1`), fold the sidecar into the main summary and remove it — pass `--today` with the target day when `$ONLY_MODE=1`, to retarget the stitch off its today-default:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workday-complete-close" stitch-sidecar
```

A non-zero exit is a HARD FAIL — the sidecar is left in place; investigate before continuing rather than re-running blind. On a backfilled/skip day where the observer never ran, this is a clean no-op.

**Then verify the stitch actually landed — a clean exit is not evidence it did.** The sidecar is transient by design (`stitch-observer-sidecar.py` removes it on success), so zero `*.observer.md` on disk is the HEALTHY steady state, and the `observer-sidecar-scan` probe at `/workday-start` Step 649 detects only the *orphaned*-sidecar leak class. Neither surface can distinguish "stitched cleanly" from "the observer was never dispatched" — both leave zero sidecars. The signal that separates them is the placeholder line the analyst writes in place of the section (`_Strategic Review section will be appended by the reviewer agent._`), which the stitch is precisely what replaces:

```bash
grep -l 'Strategic Review section will be appended by the reviewer agent' \
  archive/daily-summaries/<target-day>-<machine>.md
```

A hit means the observer half of this step did not complete, whatever the stitch exit code said. Dispatch the observer and re-stitch before moving on; do not carry the day forward on the analyst artifact alone. **Negative spec — an unresolved placeholder is never "close enough".** It silently starves every downstream consumer of the strategic-observer trail — chiefly `/workweek-complete` Step 9's arch-pass skip-condition (`commands/workweek-complete.md:344`), which skips the architecture pass when the trail carries no `for-weekly-arch-review` flags. An always-empty trail therefore reads as "no architectural risk this week" and biases that pass toward silently skipping. This failure mode can run undetected for many consecutive daily wraps precisely because every surface that could catch it reads an absence as health.

**Health ledger** (per `jp_step4e_health_ledger_new_rows`'s resolution): read `state/health-ledger.md`. If it doesn't exist, create it with two audit clocks above a per-system table — `**Last full audit:**`, `**Last targeted audit:**`, `**Next rotation target:**`, then a `| System | Grade | Last Audited | Notes |` table. Add a row (grade `?`, unaudited) for any system touched by today's commits with no row yet. Do NOT update grades or the two audit clocks from the daily wrap — `Last full audit` is written only by a PM-invoked `/architecture-survey`, `Last targeted audit` only by `/architecture-audit`; the daily observer renders no grades, it only flags candidates as debt-backlog entries for the weekly arch pass to adjudicate.

**Clean scratch:** remove `tasks/daily-review-scratch`. The daily summary artifact and today's completion-entry `narrative:` edits (below) are committed by the changelog-append directive, not here.

---

## Step 8: Completion-Log Clustering (genuine EM action, per `jp_step4_5_clustering_dispatch`'s resolution)

Skip when `$ONLY_MODE=1`. For each completion-entry chain with ≥2 entries today (from Step 6's completions pull) whose lead entry lacks a current `narrative:`: dispatch a Sonnet `general-purpose` worker to synthesize a chain-level `narrative:` paragraph (≤300 words, preserving commit SHAs, no editorial bucketing — that's `/workweek-complete`'s job) and write it into the lead entry's frontmatter via `narrative: |`; mark each non-lead entry with `narrative_in: <path-to-lead-entry>`.

---

## Step 9: Completed Archive Audit (genuine EM judgment, beyond the completions-pull directive)

Skip when `$ONLY_MODE=1`. Using today's commits and Step 6's completions pull: add missing entries via per-entry write, fix inaccurate ones, skip trivial commits. If `docs/project-tracker.md` exists, verify completed workstreams have updated status. Report: _"Archive audit: N verified, M added, K corrected."_

---

## Step 9b: Coverage & Baton-Drift (non-blocking, no consumes-manifest CLI)

Two informational lines — neither blocks the ceremony; both report, never fail. Skip this whole step when `$ONLY_MODE=1`.

**Commit coverage buckets:** target day is `$FOR_DATE` when Step 1 set it (backfill wrap), else today's UTC date (`date -u +%Y-%m-%d`, resolved once, EM-side, before the call below):

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/day-coverage-sweep" <resolved day, YYYY-MM-DD>
```

Renders `day_coverage_sweep`'s reverse (commit → completion-entry) membership sweep for the day as: _"N claimed, F foreign-authored, R recoverable, M in-flight, S sibling-homed, K orphaned (of T total commits)"_ — read the six counts straight off the printed `claimed=`/`foreign=`/`recoverable=`/`in_flight=`/`sibling_homed=`/`orphaned=`/`total_commits=` lines. Buckets read completely differently at the same percentage-claimed (12% claimed / 70% in-flight is a quiet day; 12% claimed / 88% orphaned is not) — never collapse this to one percentage. **`foreign=` and `sibling_homed=` are NOT gaps:** the first counts cross-repo memo deliveries a sibling engine committed directly into this tree, the second counts commits from sessions homed in another fleet repo. No local session authored either, and completion entries are single-repo by construction, so no entry is ever owed for them — reading either as a coverage failure is a misread, and on a busy day they are most of what `orphaned` used to absorb. Both partitions fail closed: an unresolvable registry or an absent sibling clone yields fewer classifications and leaves those commits in `orphaned`, so the gap number over-reports rather than silently exonerating.

**Baton-drift:**

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/baton-drift-sweep"
```

Renders `baton_drift_sweep`'s classification of every open baton (`state/handoffs/*.md`) as: _"held: H (successor still live — expected, roughly one per live chain), stranded: S (successor terminal/archived — investigate)"_ — read straight off the printed `held=`/`stranded=` lines. **Never report a single "N open batons, of which M have a named successor" count** — under the C1/C5 cascade design, a predecessor whose successor is still in flight is correctly held, not stranded, so that single count is never zero and becomes a line nobody reads. Held and stranded are the only split that survives daily exposure: stranded must be zero, held does not have to be. A non-zero `stranded` count names its paths on the indented `  stranded <path>` lines — surface those verbatim, they are the investigation starting point.

---

## Step 9c: Auto-Memory Drain (blocking gate, no consumes-manifest CLI)

Auto-memory is ephemeral by definition — this ceremony drains it to zero every close. Run:

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-auto-memory-drained" --root .
```

Exit 0: nothing under the auto-memory store — skip to Step 10. Exit 1: it prints every residual `*.md` path (index and/or sibling body files) to stderr. For EACH one, resolve exactly one disposition — silence is not a disposition:

- **PROMOTE** — write the fact to its durable home (doctrine, wiki, `docs/decisions/`, `state/lessons/` via `/learn-lessons`, or the orientation cache — per C1's channel contract) and note the target path. This is a real authoring act: most memory rows are private shorthand that will not survive a reader who lacks the session, so restate the claim in the destination's own voice rather than copying the row verbatim.
- **DROP** — say so explicitly.

Then delete every file the gate named (the gate itself never mutates — it only detects residue) and re-run the command above to confirm exit 0. Record the full disposition list — path, PROMOTE/DROP, and target path for each PROMOTE — in Step 10's final summary under **Auto-memory drain**; the memory dir carries no git history, so this ceremony's own output is the only record of what was destroyed.

**On the first gate invocation this ceremony exiting 0 immediately (no residue ever printed):** the store was empty from the start — omit the `**Auto-memory drain:**` line entirely.
**If the gate ever printed residue this run, even once:** the disposition list is mandatory in the final summary — even though the store is empty by the time you write it. Omitting the line at that point would erase the only record of what was destroyed.

ZERO MEANS THE DIRECTORY, NOT THE INDEX — a drained `MEMORY.md` with surviving sibling body files still fails the gate and is not done.

This complements the write-time size cap on the auto-memory store (a spatial bound — how big memory gets within a day), not a duplicate of it (a temporal bound — how long anything survives in it at all); neither supersedes the other.

---

## Step 10: Final Summary

**Report by exception.** This is still an EM→PM reply and still owes the ≤200-word budget from global `CLAUDE.md § Communication Style` — a fixed block of all-clean status lines spends that budget on facts the PM can already read off the commit, then gets measured as a verbosity violation by the Stop-hook altitude gate. Print what needs a reader, not what needs a checkbox: a clean daily wrap is the common run, so a clean daily wrap must be the *shortest* run, not the longest.

```
## Workday Complete

**Branch state:** [branch name], rebased on main, pushed
**Day-goal closeout:** [Step 6 goal-close-day summary]
**NOT merged to main** — use `/merge-to-main` when ready
```

Then append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `Day summary:` (prepended, no bold) | `$SCOPE_SUMMARY` is non-empty — _"Day summary: {scope summary}"_ |
| `Targeted wrap:` (prepended, no bold) | `$FOR_DATE` was set — _"Targeted wrap: <date> (backfilled via the Phase-B directive)"_ |
| `**Validation:**` | Step 6 validate exit code is non-zero — name the exit code and what it means |
| `**Orphan reap:**` | Step 6 reap summary is non-zero (releases actually happened) — omit entirely when clean |
| `**Plugin validation:**` | Step 4 has any failures — `[N pass / N fail]` |
| `**Archive audit:**` | Step 9 added or corrected any entries — `N added, K corrected` (omit when N=0 and K=0, i.e. all verified) |
| `**Commit coverage:**` | `$ONLY_MODE=0` AND `orphaned` > 0 — Step 9b three-bucket line; omit entirely when `$ONLY_MODE=1`, and omit when `orphaned` is 0 even under `$ONLY_MODE=0` |
| `**Baton drift:**` | `$ONLY_MODE=0` AND `stranded` > 0 — Step 9b stranded-paths line; omit entirely when `$ONLY_MODE=1`, and omit when `stranded` is 0 even under `$ONLY_MODE=0` |
| `**Auto-memory drain:**` | Step 9c's gate printed residue at any point this run — full `path -> PROMOTE(target)/DROP` disposition list, mandatory even though the store is now empty; omit entirely ONLY if the gate exited 0 on its first invocation this ceremony |
| `**Weekly staleness:**` | verdict is STALE or MILD — omit when FRESH |
| `**Post-ceremony hook:**` | Step 6 tail hook line is non-empty — omit entirely when empty/unset |

**Negative-spec — these are gone, do not restore them.** `Branches consolidated`, `Daily review`, `Completion reconcile`, and `Week-changelog` are no longer printed at all. Each was a count or a file path the ceremony's own commit already records, carrying no PM decision: the branch-consolidation directive's result is the branch itself; the daily-review artifact is `archive/daily-summaries/YYYY-MM-DD-<machine>.md`, findable by path convention; the reconcile fold and the week-changelog append are both visible in `git show` on this ceremony's own commit. Their absence is not a signal the step was skipped — the directives still run, and the commit is their record. Do not re-add any of them "for completeness": completeness of the *ceremony* is the assembler's job, completeness of the *report* is not the same thing.

---

### What This Does NOT Do

- **Merge to main** — `/merge-to-main` runs the test suite first.
- **`/update-docs`** — weekly only.
- **Triage the improvement queue** — depth nudge only; triage is weekly.
- **ShellCheck or scc stats** — `/workweek-complete`.
- **Delete the work branch** — stays alive for morning.
- **Delete handoffs** — `/pickup` archives, `/distill` deletes from archive (guarded).
- **Abandon crash-orphaned handoffs** — the orphan-reap directive RELEASES a dead holder's claim back to the pool; it never judges the deliverable abandoned.
- **Propagate dirty-tree auto-disposition to other terminators** — Step 5's allow-list logic is workday-complete-specific; `/workstream-complete` and `/handoff` keep their stricter surface where unattributable IS a real signal worth surfacing.

### Concurrent Session Safety

Per-machine files under `state/week-changelog/` eliminate concurrent-write conflicts. HEADER.md is touched only by the two weekly commands. Health files are global — workday-complete is the single daily writer.

### Relationship to Other Commands

- **`/merge-to-main`** — supervised merge; morning.
- **`archive/daily-summaries/YYYY-MM-DD-<machine>.md`** — produced by Step 7; feeds Step 6's changelog-append.
- **`/workweek-complete`** — weekly release: docs sweep, ShellCheck, triage, version bump, merge.
- **`/workweek-start`** — PM-facing weekly orient; sets priorities in HEADER.md.
