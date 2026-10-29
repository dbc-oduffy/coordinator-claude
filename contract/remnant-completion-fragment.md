# Remnant-completion fragment

`remnant-completion-fragment.json` is the seam contract for in-run completion of a `not_met`
verdict. The doctrine plane states it; the engine implements against it.

## Trigger

A `not_met` from the `judge` stage or the L+ ledger checker. A denied or unreadable leg is a
`not_met` clause, so it is a remnant.

## The `remnant` object

A `not_met` carries `remnant` when the gap is actionable; absent means the manual re-judge route.
When present it has exactly `gap` (non-empty string), `paths` (string[], at least one) and
`checks` (string[], at least one). `met` never carries it. The judge stays read-only: it emits the object and
does no remnant work.

## Dispatch and loop

The `remnant` object is the brief for an **executor** dispatch (`coordinator:executor`), never the
judge. The **engine workflow owns the loop**: remnant executor wave, re-judge, round cap.
`max_remnant_rounds` is 1.

## Re-judge

A fresh judge runs once at the new HEAD through the existing `--rejudge` seam. Remnant commits pass
the review receipt, and the `jp-*-block-stamp` predicates stay binding.

## Terminal fallback

A `not_met` that persists after the round cap, or an emitter with no remnant wave, falls to the
manual re-judge route (terminal-judge wiki, § Closing a plan whose run judged `not_met`).

## Owners

The doctrine plane owns this contract. Engine wiring (the remnant executor wave, the run record carrying
`remnant`) belongs to the engine plane.
