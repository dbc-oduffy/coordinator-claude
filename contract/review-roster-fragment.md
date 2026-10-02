# Review-roster fragment

`review-roster-fragment.json` names which reviewers a plan's emitted **execute-review** stage
dispatches, and in what order. `dispatch.emit` (the engine) reads the `execute_review` block
from here and composes it as stages of the same emitted workflow every executed plan gets — size
no longer selects a roster; every plan is reviewed, at every t-shirt size.

## Consumer version

`schema_version: 5` replaces v4's size-selected `tiers` with a single `execute_review` block. The
stage-aware consumer is the engine's `review_mint/execute_review.py ::
compose_execute_review`, which turns `stages` into: one mechanical prep call, one `parallel()`
review wave; the engine's `bookkeep_wave` then writes the wave record. A v4-shaped reader (`list(tier)`) has nothing
to key on here — there is no `tiers` key left to misread.

## Required on every code-landing emit

`execute_review.required_for_emit` names every emit route that lands code: `plan`
(`/execute-plan`), `inventory` (mise-en-place), `queue` (queue-grind / improvement triage) and
`wave-fire-dispatch` (plan-blitz's XS `dispatch` lane). Each composes this review wave into the
emitted script unconditionally — at least one reviewer, partitioned at PARTITION-MANDATORY — and
refuses to emit when the fragment or its stage schemas do not load. No caller input yields a
code-landing script without it, and the terminal commit refuses a run with no review output.
Review is guaranteed by the emitted script, never by an EM or a ceremony remembering it.

## Stages

`execute_review.stages` is an ORDERED list of exactly three kinds: `prep`, `review-wave`, then
`judge`. Prep runs first (it partitions the diff and provisions every sidecar the rest read).
The review wave is **one parallel stage**: every agent in it — the per-slice code reviewers, Kira,
each signal-named persona, and the delivery verifier — runs concurrently. There is no second
review round and no sequential ordering among reviewers; that already-parallel invariant from v4
("two or more agents in one stage run in parallel — that is what a stage means") carries over
unchanged. Each slice reviewer applies and verifies its own findings; the whole-diff lenses
(`applies: none`) report only. No `integration` stage exists, and
`tests/test_review_roster_fragment.py` enforces that.

`judge` is last and holds exactly one agent, `coordinator:exit-criterion-judge`, returning
`terminal-judge-result`. It reads the plan's prime exit criterion against the tree and the PM's
recorded words, and writes into the run record's `criterion` leg. It never halts the wave: a
`not_met` or `indeterminate` verdict leaves the plan `executing`. It has no `blocking_verdicts`
row because the composer reads none for it.

`per: slice` fans the `coordinator:code-reviewer` review-wave entry out over prep's own slice
list at run time — the fragment names one entry, the run dispatches one call per slice.

Every stage entry that carries an `agentType` also carries `model` and `effort`: the roster is
the one place that pins per-call cost for a review dispatch, so a consumer never has to guess.
An `accepts_signals` entry carries neither `agentType`, `model` nor `effort` — it has no fixed
identity of its own. At run time it inherits whichever persona a `review_signals` name resolves
to (`review-signals.json`), including that persona's own frontmatter `model`/`effort`.

## `brightline`

`execute_review.brightline` names the op that partitions the diff — `review_brightline_gate` —
and the value `partition_on` returns when the diff is at or above that gate's own thresholds.
**This fragment never restates the gate's LOC/commit/surface numbers.** They live in
`review_brightline_gate` alone; a consumer reads them from there, never from a copy here that
could drift.

## `blocking_verdicts`

Same purpose as v4: it maps every `agentType` an execute-review stage may dispatch — whether
roster-fixed or signal-selected — to the exact verdict string its own charter declares blocking,
so a consumer never hardcodes agent names or normalises their vocabulary. `code-reviewer` blocks
on `BLOCKED`; `delivery-verifier` blocks on `FAIL`; `overengineering-reviewer` and every
signal-selectable persona (`staff-eng`, `staff-data-sci`, `senior-front-end`, `staff-ux`) block on
`REJECTED`, their shared reviewer enum's bottom value.

`coordinator:review-integrator`, `coordinator:apm` and `coordinator:eng-director` are not in this
map. The integrator retired; `apm` and the Director of Engineering (`eng-director`) are plan-altitude reviewers, not code
reviewers, and this fragment now names code review only. `coordinator:prior-art-checker` and
`coordinator:docs-checker` are also absent: both were v4's plan-altitude preflight gate, and
`execute_review` has no preflight stage for them to ride along in.

## What a review_signals entry can put in the wave

Any persona `review-signals.json` marks `"stage": "named"` — `staff-eng` (architecture, backend,
security), `staff-data-sci` (data-science), `senior-front-end` (front-end), `staff-ux` (ux-flow) —
can be merged into the review-wave's `accepts_signals: "named"` entry when the plan's own
`review_signals` selects it. A plan selecting no named signal dispatches the wave's four fixed
agents (per-slice code-reviewer, Kira, delivery-verifier) plus nothing extra; a mechanical plan is
never charged a domain specialist it didn't ask for. `coordinator:vp-product` stays PM-directed,
never signal-matched, and is not part of this fragment.

## `plan-reviewer` is unrostered

`coordinator:plan-reviewer` is deliberately unrostered in `review-roster-fragment.json`. It is a
plan-altitude lens dispatched by the plan lanes (accepted-XL ahead of the named persona; `spec-dispatch`
ahead of emit-and-dispatch), and this fragment names execute-review code review only. Nothing here
dispatches it, and rostering it would put a plan-stage agent into a diff-review wave. A later session
that finds an unrostered plan-stage reviewer here should not roster it, and should not conclude the
doctrine is fiction: `plan-reviewer` is live, wired in `skills/plan/residue/plan-corpus.md` and
`spec-dispatch-corpus.md`. The `.json` carries no entry for it by design.

## Changing it

Every entry carrying an `agentType` must be a real dispatchable one — a name that does not
resolve to `agents/<name>.md` composes a stage that dispatches nobody, and the run reads as
reviewed when it wasn't. `tests/test_review_roster_fragment.py` pins each name against `agents/`,
the stage-kind/order constraints above, and that no integration stage exists.
