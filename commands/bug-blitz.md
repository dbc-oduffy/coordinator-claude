---
name: bug-blitz
description: "Emit and fire a canonical bug-backlog queue grind; dispatch, don't defer."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--appetite=hunt|standard|sweep] [--max=N] [--budget-tokens=N]"
---

# Bug Blitz — Grind the Bug Backlog and the Test Suite

Two work sources, one pass: `state/bug-backlog/` and the full test suite (Tier-U authorized,
Phase 0.6). No separate triage step — failing tests mint `TF-*` items that ride the same
triage → fix → verify path as backlog bugs, through the emitted grind. Green suite is part of
done once Tier-U is granted; declined runs the backlog leg only. Empty/absent backlog never
halts the run; suite leg still fires. `backlog-grind-assemble brief bug-blitz` emits
`j-bug-blitz-commit-readiness` (resolve it before the emitted grind's first commit),
`executor-dispatch-prompt-template`, and `spinoff-handoff-template` — read them, don't
hand-narrate them. Rationale, worked examples, and full phase mechanics: wiki.

**Announce:** "Running `/bug-blitz` — one authorization ask for the full test suite (baseline +
confirm-green), then an emitted grind through every fixable item. Default is dispatch, not
defer; defer needs named evidence."

## Default Stance

Dispatch, don't defer — defer needs named evidence, never a hunch. The operative triage policy
(what counts as evidence, what is NOT a valid defer reason, severity classification) lives only
in `${CLAUDE_PLUGIN_ROOT}/queue-profiles/bug.yaml` § `triage_policy`; this command cites it, it does not
restate it.

## Arguments

`--appetite=hunt|standard|sweep` (default `standard`) — passed through to the emitter; its
meaning is the profile's `appetite` block, not restated here. `--max=N` → `--limit N` on the
emit call. `--budget-tokens=N` — passed through to the emit call unchanged.

## Out of Scope

`gh pr merge`/`create` against main, `git push origin main`, hibernate/shutdown/kill-process,
`--no-verify`/`--no-gpg-sign`. No exceptions, no mid-run ask.

## Phase 0 — Preflight

Note backlog presence/count; confirm `git branch --show-current` is the day branch and capture it
as `BLITZ_BRANCH`: the `coordinator.dayBranch` designation when the repo has one (a cloud session
records its harness-assigned branch there at SessionStart), else `work/{machine}/{date-or-span}`.
Halt on anything else, always on `main`, the default branch, or a detached HEAD — fail-closed, no
override. Mint run ID; scratch `state/scratch/bug-blitz/{run-id}/`. Mechanics: wiki.

## Phase 0.6 — Tier-U Authorization

Ask once, before Phase 0.7: *"This run needs the full test suite — once now to baseline, once
after fixes to confirm green. Authorize the full-suite tier for this run?"* Only an explicit
affirmative naming its subject (or a terse "yes" in direct reply) qualifies — general blitz
approval doesn't. Granted → `tier-u-grant-cli grant pm <note>`, proceed; the same session-scoped
token covers the confirm-green re-run (`tier-u-grant-cli check`, no second ask). Declined → write
nothing, backlog-only leg, note the decline in the report.

## Phase 0.7 — Suite Baseline (no-op unless granted)

`coordinator-resolve-validation-cmd --full` resolves `TEST_CMD`: exit 0 full suite; exit 3
fast-tier fallback, report as `fast-fallback`, never call it the full suite; exit 2 unconfigured,
continue backlog-only, name the remediation, never fabricate a command. EM runs it directly (Tier-U
— subagents never run the suite), dispatches `test-evidence-parser` to classify the captured
output. Each `real` failure mints `TF-{run-id}-{n}`; `flake`/`env`/`timeout`/`known-skip` aren't
dispatched. Mechanics: wiki.

**Empty-backlog-and-green-suite short-circuit:** absent/empty backlog AND fully green resolved
suite → skip to a one-line all-clear, no commit. Not reachable under decline.

## Phase 1 — Emit and Fire the Grind

After Phase 0.7, emit through C4's queue route and fire it interactively:

```
python3 coordinator/bin/emit-dispatch-workflow.py --queue state/bug-backlog --profile bug \
  --appetite <a> --limit <N> --budget-tokens <N> \
  --out state/scratch/bug-blitz/{run-id}/blitz.workflow.mjs
```

Resolve `j-bug-blitz-commit-readiness` before firing — firing IS the emitted grind's first
commit. Fire with `Workflow({scriptPath: ...})`; firing is interactive, never `--fire` — the
wrapper docstring (`coordinator/bin/emit-dispatch-workflow.py`) says why. Firing this Workflow is
the PM's standing approval for every safe fix, refute-confirmed close and plan-weight baton the
run produces — no further per-item ask.

**Cost reporting.** Read the engine's run-cost record, `state/queue-grind/bug/runs/<run-id>.json`,
beside the hand-back, and report its spend next to the hand-back counts. This command makes no
pre-run cost estimate.

## Spinoff Gate — Mint Themed Batons from the Baton Hand-Back After the Run

Cluster the hand-back's `baton` rows with `detect-initiative-candidates`, author to
`coordinator/docs/wiki/baton-authoring-bar.md`'s bar. The only mint-time check that remains here
is "not already covered by a live handoff or plan" — phantom and mis-size checks are triage
policy already applied inside the grind, per the profile. No PM authorization message: the fire
already discharged it.

Only `park`, `wont-do`, `yagni`, `unclear-direction` and `needs-judgment` rows go to the PM list.
`plan-substrate-collision` is not on that list: fold the row into the colliding plan as a
committed annotation, per the memo-to-plan write-through discipline, and close the row citing
that plan; if the colliding plan is terminal, the row becomes a baton instead. The universal
engine types (`budget-exhausted`, `verify-failed`, and the rest) are reported, with the re-emit
command from the receipt.

## Queue Terminus

The four outcome classes of `coordinator/docs/wiki/queue-terminus-doctrine.md` — cite, don't
restate: dispatch (`small`/`fix`), solo spinoff (`big`, PM-authorized), close
(already-fixed/file-removed/wontfix), themed baton (N `small` items sharing a thesis, clustered
via `detect-initiative-candidates`, authored to `coordinator/docs/wiki/baton-authoring-bar.md`'s
bar as one multi-item handoff). Firing the emitted grind is the run-authority act: it stands in
for the PM-authorization gate a themed baton or a `big` item would otherwise need, per the Spinoff
Gate above. Bug-specific dispositions — severity, repro, the `wontfix` status value — are
preserved; the four classes are the terminus, not a replacement for bug triage's own semantics.
Mechanics: wiki.

## Phase 4 — Archive and Report

Archive only the rows this command disposes after the run: baton-minted rows, closed with
`closed_by: spun-off-<path>`, via a plain rename plus `--declared-revert`. The in-run committer
closes every other row. The EM commits each minted baton together with the archival of the rows
it absorbs, as one scoped commit per baton via the committer route, with `--declared-revert` for
the removed rows.
<!-- engine-gap: field=directives[build_verifier_dispatch].dispatch_entry producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

**Per-item cadence.** One commit per verified fix, never collapsed per batch.

Re-run the suite (mandatory if any fix dispatched, only if Tier-U was granted). All clear → PASS.
**Disposition splits on whether the failure was already red at baseline:** a pre-existing failure
still red after one corrective wave means stop chasing in-wave — either leave it reverted to
baseline (acceptable) or, if the attempted fix is committed and not working, `git revert` that
non-working fix commit — then surface it as a spinoff candidate; a NEW failure that was green at
baseline is a self-inflicted regression and its revert is **mandatory, not optional**: `git revert
<introducing-sha>` (never `git reset` — branch is pushed), confirm green, name it in the report.
**Loop bound: one corrective wave only, then the forced terminal state above — never a second
corrective wave, in either branch.** Never report green with a known-red suite. Clean scratch
after the archive commit succeeds. Full mechanics: wiki.

**Report by exception** — two lines always, rest only when not clean:

```markdown
## Bug Blitz Complete

**Backlog:** N → M
**Resolved this run:** F items (backlog: Fb, failing tests fixed: Ft)
```

Add `**Spun off (need plan):**` / `**Re-attempted (still blocked):**` / `**Suite gate:**` /
`**Suite noise (not chased):**` / `**Closed already-fixed:** R ran / I inspected` only when
non-empty — that last one splits by evidence rung because one number over two standards hides
the weaker half from the reader, and from you. Never restore a run-id line, a silent
already-fixed line, or a clean `Suite gate: PASS` line — their absence already means clean.

## Failure Modes, Stop-Early, Relationship to Other Commands

Full tables: wiki. The load-bearing invariants that stay here: never rollback completed work on
early stop; never fabricate a test command; never weaken an assertion; `git revert` (never `git
reset`) for a self-inflicted regression on a pushed branch.

`/workstream-start` advocates this command on backlog depth and, independently of it, on a **red-suite predicate** — a non-empty delta in `state/test-red/<machine>.yaml` against the acknowledged baseline, never bare redness. Both arrive here as the same emitted grind.
