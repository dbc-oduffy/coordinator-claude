---
name: mise-prep
description: "Certify approved plans; route residue to plan-author-residue."
allowed-tools: ["Read", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[plan ...] [--roadmap-id <id>] [--dry-run]"
---

# Mise-Prep — Certify Approved Plans

The stage between `plan-blitz` and `/mise-en-place`: gate every approved plan against the
authoring bar and stamp the ones that pass. It stops at certification — it fires nothing.
Certification is per plan; the seam check runs over the set (`lesson-triage/mise-seam-check.md`),
and this command owns the seam pass: no EM step sits between a refusal and its fix.
Before stamping, prep re-runs each `census[]` command of the plan and refuses drift as
`CENSUS-DRIFT`; it never rewrites a `result:`. The stamp certifies the plan body's sha only and
makes no claim about census freshness at fire time, which `/mise-en-place` Phase 0 adjudicates
(benign-growth class).

## 1. Run the seam-pass loop

`mise-prep-run --repo-root <this repo, absolute> --upgrade [--dry-run] [plan ...] [--roadmap-id <id>]`

Run the settings-home launcher, resolved per `coordinator/snippets/resolve-coordinator-bin.md`;
the plugin's `bin/mise-prep-run.py` run directly cannot import `coordinator_core`. A warm-engine
`-32004` timeout on a large set re-runs cold with `COORDINATOR_WARM=0`.

Pass on only the plan paths and flags the invocation names; free text is context, never a plan
path. A free-text set ("the plans blitz approved") is the trail's fire results' `ready[].planPath`
list. **No plan arguments means every plan the last landing left fireable — BOTH exits**, not only
`status: approved`: the S lane parks its spec execution-ready and leaves the plan `draft` by
design, and those certify too. `--upgrade` writes only the declarations derivable from a plan's
own text; `plan.stamp_prepped`, inside the run, writes the stamp.

Loop, bounded:

1. **Round.** Run with `--dry-run`. Read the report; classify each `SEAM-REFUSED` / `NOT-PREPPED`
   row by the table below and apply every fix it admits (step 2 drafts).
2. **Re-check.** Run `--dry-run` again. A **fixpoint** is a round that changes no plan file; stop
   looping there.
3. **Bound.** At most 3 dry-run rounds. If round 3 still changed a plan file, go on anyway: every
   finding still open becomes a receipt line (APM-routed or `Escalate to PM`), never a fourth round.
4. **Stamp.** One run without `--dry-run`. A plan body is never edited after it is stamped.

Route by row:

- **exit 2, REFUSED** — no verdict computed. Relay it verbatim and stop; an engine-root refusal is
  an engine-root defect, never NOT-PREPPED.
- `refused`, or a MALFORMED stamp → not authoring residue. Relay it; a MALFORMED stamp was
  hand-written, and its repair is the frontmatter, never a stamp over it.
- `CENSUS-DRIFT` (exit 1) → the counted premise moved. Repair is a re-plan or an APM format-only /
  benign-growth ruling, never the step 2 residue plan-author; relay it as a receipt line.
- `NOT-PREPPED` with a `bar:` line → step 2.
- `SEAM-REFUSED` with `seam:` lines, by class:
  - `capabilities-undeclared` → one `coordinator:plan-author-residue` dispatch over those plans,
    step 2's charter; the stage covers NOT-PREPPED only.
  - `writes-collision` where every writing row only adds an entry to a shared registry file → step 2
    declares that path in the row's `appends:`. A collision between two already-certified plans is
    never fixed by `plan.seam_fix` (the edge is a body edit and voids the stamp): its ordering is
    owned by `/mise-en-place`, derived at Phase 0 from the plans' declared writes with no EM step
    and no body edit (`lesson-triage/mise-seam-check.md`); report it, write no edge. Any other
    collision is fixed by `plan.seam_fix`
    over the set (a mutating op: `depends_on_plan` edges, cycle-checked, idempotent); a
    `skipped_cycles` entry is APM-routed. The out-of-set pass is `plan.seam_check` with
    `universe: true` (non-blocking `missing-seam`); a flag handling cannot resolve goes to
    `seam.mint_batons` (staged, at most 5 plus a rollup, deduped on `class|plan|path`). Never
    hand-roll an edge writer, a seam-baton minter, or an out-of-set scanner here.
  - `capability-without-ui-consumer`, `unpromised-export`, a cycle → `coordinator:apm`; the stage's
    Persist phase writes its `pm_ruling:`. A no-correct-answer item goes in the receipt's
    `Escalate to PM` section and its row stays unresolved. Never dispatch a plan-author to add a
    consumer.

## 2. Draft the residue

Residue the loop cannot fix mechanically is authorship: the bar asks what only a plan's author
knows. `mise-prep-run` emits it as the **residue-author workflow stage** and prints a
`Workflow({scriptPath})` line: **fire that line** — never compose the stage by hand, and never a
hand-dispatched Opus `plan-author` Agent batch. The stage runs at the Sonnet tier: one
`coordinator:residue-author` agent per up to 8 plans, in parallel, each plan file with one
owner, over the default set too. Leftover census rows and seam_fix `skipped_cycles` go to the
stage's own `coordinator:apm` step; the EM relays neither. Each stage agent is briefed with:

- each plan's path with its `bar:` / `seam:` lines verbatim;
- the bar's own refusal, naming each missing declaration and its declared-empty form:
  `mise-prep-gate --repo-root <repo> <plan>` (resolve per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`);
- the charter: amend each plan in place, declaring only `capabilities:` and, on rows the collision
  record names as append-only, `appends:`, plus the spine repair below. Nothing else: no
  `ui_carve_out` (a proposed carve-out is an `Escalate to PM` line), no scaffold, no `status` change, no `mise_prepped_*` key, no body edit
  beyond a named class. Never fill a capability row with a plausible guess to clear a refusal.
  Declared-empty only where true. A matter that is scope, direction or priority goes to
  `coordinator:apm` (code, to `coordinator:staff-eng`), whose ruling Persist writes as `pm_ruling:`; only
  a `pm_only` matter (important, urgent, no clear answer) goes in the summary, class left undeclared.
- spine repair, a sanctioned stage job when a `bar:` line cites it: a `python -c` or pytest census
  check moved into the owning row's step 0 with the displaced census entries renumbered; a memo row
  missing `receipt:` / `memo_to:`; an invalid `change_kind`; a test-runner row the gate refuses,
  split into an `em` verify row; an unquoted `on:` key quoted. The charter is the agent's.

Not `coordinator:enricher` — it gathers facts and never decides, and a `prime_exit_criterion` is
carried from the sizing's accepted `exit_criterion`; plan-author authors it only when the sizing
carries none. Tripwire: `NOT-PREPPED-RESIDUE-IS-AUTHORED-BY-PLAN-AUTHOR`.

`/spinoff` is never run from here: out-of-set gaps are the engine's mint path, bounded and
receipted, not a hand-filed baton.

Never a stage of an engineering ask's one submission or its relay fallback: it serves backlog runs
and hands-on re-plans.

## 3. Receipt, then stop

A plan still NOT-PREPPED after the loop is reported with its `bar:` line and its author's summary.
Emit the receipt: its sections and line format are `lesson-triage/mise-seam-check.md`'s, the single
home — cite, never restate. Then report certified/short counts and stop.
Neither the stamp nor the seam op commits: the EM's scoped commit of the stamps also names each
plan's `.seam.yaml`.

Never write `mise_prepped_*` by hand, and never execute: `/mise-en-place` fires certified plans,
re-checking each stamp at Phase 0.
