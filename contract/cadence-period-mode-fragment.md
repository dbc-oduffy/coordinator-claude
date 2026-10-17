# Cadence period-mode fragment

`cadence-period-mode-fragment.json` is the contract for the catch-up property: a cadence run
invoked early in its period backfills every missed prior period and leaves the in-progress one
open. It restates the engine's resolver for the plugin's command bodies and tests;
`engine_mirror` names the engine constants.

## Flags

`--catch-up` forces catch-up-only; `--conclude` forces a concluding run. They apply to
`workday-complete` and `workweek-complete`. They are mutually exclusive, and each is refused
alongside `--only` or `--for-date`; `--for-date D [--only]` keeps its single-date semantics.
`workweek-start` and `workday-start` take no flag: the first never archives the in-progress week
and routes missed weeks to `/workweek-complete --catch-up`; the second dispatches one
`workday-complete --catch-up` entry when the scan has a gap row.

## Mode and source

`mode` is `catch_up` or `conclude`. `source` is `explicit` (a flag; always wins) or `auto-clock`.

## Thresholds

Auto rule when no flag is given. `day`: `catch_up` before the local time in
`coordinator.cadence.day_conclude_after` (default `15:00`). `week`: `catch_up` when the local date
is fewer than `coordinator.cadence.week_conclude_after_days` (default `4`) days past the week
anchor. Both are machine-local keys with engine defaults; no body hardcodes a weekday or a clock
time.

## Resolver and week window

`resolve_period_mode(cadence, now_local, explicit, *, week_anchor)` returns a `PeriodMode` of
`mode`, `source`, `in_progress`, `missed` and `reason`. `week_window(d, week_anchor)` returns
`(start, end_exclusive)` on the weekday chain of HEADER.md's `Week starting:`, never assumed
Monday.

## Brief contract

Every cadence brief carries a top-level `period_mode` object, and its narration leads with
`Catch-up run: <missed periods> backfilled; <in_progress> left open`. Under `catch_up`, a
concluding directive is absent from `directives[]`, never present and self-skipping.

## Concluding directives

`concluding_directives` lists, per ceremony, the directive ids a catch-up run omits.
`catch_up_variants` records the two that change shape instead: workday-complete's analyst
dispatch covers gap days only, and workweek-complete's gap backfill stops at the last missed
week's end with one `--week-only` archive directive per missed week. The merge to main is a
nested step of the concluding run, not a directive id; `release_acts_absent_under_catch_up`
names every release act a catch-up workweek-complete performs none of.
