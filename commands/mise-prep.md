---
name: mise-prep
description: "Certify approved plans; route residue to plan-author."
allowed-tools: ["Read", "Bash", "Grep", "Glob", "Agent"]
argument-hint: "[plan ...] [--roadmap-id <id>] [--dry-run]"
---

# Mise-Prep — Certify Approved Plans

The stage between `plan-blitz` and `/mise-en-place`: gate every approved plan against the
authoring bar and stamp the ones that pass. It stops at certification — it fires nothing.
Certification is per plan; the seam check runs over the set (`lesson-triage/mise-seam-check.md`),
and this command owns the seam pass: no EM step sits between a refusal and its fix.

## 1. Run the seam-pass loop

`python3 "<plugin root>/bin/mise-prep-run.py" --repo-root <this repo, absolute> --upgrade [--dry-run] [plan ...] [--roadmap-id <id>]`

**Resolve the plugin root to an absolute path yourself** — the directory holding this command's
sibling `bin/`. `${CLAUDE_PLUGIN_ROOT}` is a POSIX expansion, unset in a PowerShell tool shell, so
pasting it runs nothing and explains little.

Pass on only the plan paths and flags the invocation names; free text is context, never a plan
path. **No plan arguments means every plan the last landing left fireable — BOTH exits**, not only
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
- `NOT-PREPPED` with a `bar:` line → step 2.
- `SEAM-REFUSED` with `seam:` lines, by class:
  - `capabilities-undeclared` (named or default set) → step 2.
  - `writes-collision` where every writing row only adds an entry to a shared registry file → step 2
    declares that path in the row's `appends:`. Any other collision is fixed by `plan.seam_fix`
    over the set (a mutating op: `depends_on_plan` edges, cycle-checked, idempotent); a
    `skipped_cycles` entry is APM-routed. The out-of-set pass is `plan.seam_check` with
    `universe: true` (non-blocking `missing-seam`); a flag handling cannot resolve goes to
    `seam.mint_batons` (staged, at most 5 plus a rollup, deduped on `class|plan|path`). Never
    hand-roll an edge writer, a seam-baton minter, or an out-of-set scanner here.
  - `capability-without-ui-consumer`, `unpromised-export`, a cycle → `coordinator:apm`, which
    writes `pm_ruling:` on the plan. A no-correct-answer item goes in the receipt's
    `Escalate to PM` section and its row stays unresolved. Never dispatch a plan-author to add a
    consumer.

## 2. Draft the residue

Residue the loop cannot fix mechanically is authorship: the bar asks what only a plan's author
knows. Dispatch `coordinator:plan-author` in parallel, one agent per up to 8 plans — each plan file
has one owner. This runs over the default set too, not only a named one. Brief each with:

- each plan's path with its `bar:` / `seam:` lines verbatim;
- the bar's own refusal, naming each missing declaration and its declared-empty form:
  `mise-prep-gate --repo-root <repo> <plan>` (resolve per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`);
- the charter: amend each plan in place, declaring only `capabilities:` and, on rows the collision
  record names as append-only, `appends:`. Nothing else: no `ui_carve_out` (a proposed carve-out is
  an `Escalate to PM` line), no scaffold, no `status` change, no `mise_prepped_*` key, no body edit
  beyond a named class. Never fill a capability row with a plausible guess to clear a refusal.
  Declared-empty only where true. A matter that is scope, direction or priority goes to
  `coordinator:apm` (code, to `coordinator:staff-eng`), which writes `pm_ruling:` on the plan; only
  a `pm_only` matter (important, urgent, no clear answer) goes in the summary, class left undeclared.

Not `coordinator:enricher` — it gathers facts and never decides, and a `prime_exit_criterion` is
carried from the sizing's accepted `exit_criterion`; plan-author authors it only when the sizing
carries none. Tripwire: `NOT-PREPPED-RESIDUE-IS-AUTHORED-BY-PLAN-AUTHOR`.

`/spinoff` is never run from here: out-of-set gaps are the engine's mint path, bounded and
receipted, not a hand-filed baton.

Not an EM step on the M/L four-turn loop — this command runs for backlog runs and hands-on
re-plans (`em-loop-factfind.md` §1, census rows 7 and 8).

## 3. Receipt, then stop

A plan still NOT-PREPPED after the loop is reported with its `bar:` line and its author's summary.
Emit the receipt: its sections and line format are `lesson-triage/mise-seam-check.md`'s, the single
home — cite, never restate. Then report certified/short counts and stop.
Neither the stamp nor the seam op commits: the EM's scoped commit of the stamps also names each
plan's `.seam.yaml`.

Never write `mise_prepped_*` by hand, and never execute: `/mise-en-place` fires certified plans,
re-checking each stamp at Phase 0.
