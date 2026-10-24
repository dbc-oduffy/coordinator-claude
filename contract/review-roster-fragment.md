# Review-roster fragment

`review-roster-fragment.json` names which reviewers a plan's emitted **execute-review** stage
dispatches, and in what order. `dispatch.emit` (the engine) reads the `execute_review` block
from here and composes it as stages of the same emitted workflow every executed plan gets — size
does not select a roster; every plan is reviewed, at every t-shirt size.

## Consumer version

`schema_version: 6` carries a single `execute_review` block and no top-level `tiers` (v4's
size-keyed shape stays gone). The stage-aware consumer is the engine's
`review_mint/execute_review.py :: compose_execute_review`, which turns `stages` into: a
mechanical prep call, the review wave, an integration call; the engine's
`bookkeep_wave` then writes the wave record. A v4-shaped reader (`list(tier)`) has nothing to key on here.

A stage agent entry may carry one optional `tiers` array (values `lightweight`, `standard`,
`full`); absent means every tier, and `compose_execute_review` filters the entry on the plan's
size tier (the filter lives in the engine and is not exercised by this repo's tests, which pin
only the JSON shape). No entry carries one today. The per-slice code-reviewer reviews every plan.
Delivery claims are checked by that reviewer's brief-conformance rows, not by a separate wave
member.

Kira carries `min_tshirt: "L"`: the integration stage runs on a plan sized L or above; a plan whose
size cannot be derived (a grind row) does not run Kira. `tiers` cannot express L-and-above, because
the engine maps M and L to one tier; do not simplify `min_tshirt` to a `tiers` array.

## Required on every code-landing emit

`execute_review.required_for_emit` names every emit route that lands code: `plan`
(`/execute-plan`), `inventory` (mise-en-place), `queue` (queue-grind / improvement triage) and
`wave-fire-dispatch` (plan-blitz's XS `dispatch` lane). Each composes this review wave into the
emitted script unconditionally — at least one reviewer, partitioned at PARTITION-MANDATORY — and
refuses to emit when the fragment or its stage schemas do not load. No caller input yields a
code-landing script without it, and the terminal commit refuses a run with no review output.
Review is guaranteed by the emitted script, never by an EM or a ceremony remembering it.

## Stages

`execute_review.stages` is an ORDERED list of exactly four kinds: `prep`, `review-wave`,
`integration`, then `judge`. Prep runs first (it partitions the diff and provisions every sidecar
the rest read). The review wave holds only the per-slice code reviewers; each
applies and verifies its own slice's findings (`applies: own-slice`). In a plan-path run an
**executor group** is one emit wave: its slice reviewers start once every row writing any of its
files has landed, while other rows still run; undeclared surface joins the last group, which waits
on every row. The scoped verify leg overlaps whole-diff review and re-verify; re-verify reruns
tests over every group's edits and governs any test covering a review-edited file. Each verify
call is bounded at 300 s (`VERIFY_WALL_BUDGET_S`); an overrun reads `indeterminate`/`error`, never
a pass. Chatty, `writes_under` and review-only runs keep the serial review (all slices after the
last row). The integration stage holds Kira alone, the final Opus pass over the whole diff after
the last row (`applies: whole-diff`): it may change code and must ensure the plan's target is met. Its
exact-text Edits fail rather than clobber a stale read, so it re-reads and re-applies. Named-signal
personas (`review-signals.json`) are not rostered; they stay reachable through manual
`/review --surface diff`. `tests/test_review_roster_fragment.py` enforces the stage order.

`judge` is last and holds exactly one agent, `coordinator:exit-criterion-judge`, returning
`terminal-judge-result`. It reads the plan's prime exit criterion against the tree and the PM's
recorded words, and writes into the run record's `criterion` leg. It never halts the wave: a
`not_met` or `indeterminate` verdict leaves the plan `executing`. It has no `blocking_verdicts`
row because the composer reads none for it.

`per: slice` fans the `coordinator:code-reviewer` review-wave entry out over prep's own slice
list at run time — the fragment names one entry, the run dispatches one call per slice.

## `executor_rows_per_reviewer`

The `coordinator:code-reviewer` entry carries `executor_rows_per_reviewer: {"min": 3, "max": 6}`,
both integers >= 1 with `min <= max`: one slice reviewer per 3-6 executor rows. In grouped review
the ratio applies to each group's rows (`compose_execute_review`'s `review_groups`). A composer
that does not read it keeps the `per: slice` fan-out above.

Every stage entry that carries an `agentType` also carries `model` and `effort`: the roster is
the one place that pins per-call cost for a review dispatch, so a consumer never has to guess.

## `brightline`

`execute_review.brightline` names the op that partitions the diff — `review_brightline_gate` —
and the value `partition_on` returns when the diff is at or above that gate's own thresholds.
**This fragment never restates the gate's LOC/commit/surface numbers.** They live in
`review_brightline_gate` alone; a consumer reads them from there, never from a copy here that
could drift.

## `blocking_verdicts`

Same purpose as v4: it maps every `agentType` an execute-review stage may dispatch — whether
roster-fixed or reached by manual `/review` — to the exact verdict string its own charter declares blocking,
so a consumer never hardcodes agent names or normalises their vocabulary. `code-reviewer` blocks
on `BLOCKED`; `overengineering-reviewer` and every
signal-selectable persona (`staff-eng`, `staff-data-sci`, `senior-front-end`, `staff-ux`) block on
`REJECTED`, their shared reviewer enum's bottom value.

`coordinator:review-integrator`, `coordinator:apm` and `coordinator:eng-director` are not in this
map. The integrator retired; `apm` and the Director of Engineering (`eng-director`) are plan-altitude reviewers, not code
reviewers, and this fragment now names code review only. `coordinator:prior-art-checker` and
`coordinator:docs-checker` are also absent: both were v4's plan-altitude preflight gate, and
`execute_review` has no preflight stage for them to ride along in.

## Unrostered by design

The named-signal personas (`review-signals.json` `"stage": "named"`) stay in `blocking_verdicts`
for manual `/review --surface diff`; a plan's `review_signals` does not add them to the wave.
`coordinator:vp-product` stays PM-directed. `coordinator:plan-reviewer` is a plan-altitude lens
dispatched by the plan lanes (`skills/plan/residue/plan-corpus.md`,
`spec-dispatch-corpus.md`), live though absent here; do not roster it into a diff-review wave.

## Changing it

Every entry carrying an `agentType` must be a real dispatchable one — a name that does not
resolve to `agents/<name>.md` composes a stage that dispatches nobody, and the run reads as
reviewed when it wasn't. `tests/test_review_roster_fragment.py` pins each name against `agents/`,
and the stage-kind/order constraints above.
