# Warp touchpoints fragment

`warp-touchpoints-fragment.json` positions each engine touchpoint id at a stage boundary of the
warp run and lists the stages each route runs. This plugin owns the positions; the engine's
`emit-dispatch-workflow` reads this file and never re-derives or copies it, on the
`pm-gate-signal-fragment` precedent.

## What it carries

- `stages`: the run's stages in order, `sizing` through `terminal-commit`.
- `positions`: exactly the five ids the engine's `TOUCHPOINTS_BY_MODE` carries
  (`accept_sizing`, `execute_go`, `wrap_up`, `accept_result`, `accept_exit_criterion`), each
  mapped to `after:<stage>` or `before:<stage>`.
- `route_stages`: the stages each route runs. `shape`, `roadmap` and `pm-decision` are refused by
  name, and each names the room the route sends to.
- `ids_source`: where the ids come from. The fragment never restates which ids each mode has;
  the engine's table owns that, and the fragment positions its ids.

## No discharge list

A sizing carrying `exit_criterion.accepted` has already passed every `after:sizing` id, so a
`--sizing` run starts at `plan`. That rule is derived from `positions`, never stored beside it.

## An `after:terminal-commit` position is a report, not a halt

`wrap_up` and `accept_result` sit after the run's last stage. There is nothing left to resume, so
the run reports to the PM at that point and does not stop inside itself. Only `after:sizing` and
`before:execute-plan` positions halt, and a mode halts only where its own table has an id at such
a position.

## Changing it

Adding or moving an id here changes where a run stops. `coordinator/tests/test_supplied_fragments.py` pins
the five ids, the stage order, the route table and the absence of any per-mode id list.
