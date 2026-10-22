---
name: bug-blitz
description: "Submit a bug-blitz as one coordinator:bug-blitz Workflow call."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--targets=<red-set dir|failing-tests file|backlog>] [--appetite=hunt|standard|sweep] [--max=N] [--budget-tokens=N]"
---

# Bug Blitz — Grind the Bug Backlog and the Test Suite

Two work sources, one pass: `state/bug-backlog/` and the full test suite (Tier-U authorized,
Phase 0.6). No separate triage step — failing tests mint `TF-*` items that ride the same
triage → fix → verify path as backlog bugs, through the emitted grind. Green suite is part of
done once Tier-U is granted; declined runs the backlog leg only. Empty/absent backlog never
halts the run; suite leg still fires. The submission is the commit authority and the emitted
grind carries its own templates — read them, don't hand-narrate them. Never infer a suite grant
the PM did not state.
Rationale, worked examples, and full phase mechanics: wiki.

**Announce:** "Running `/bug-blitz` — one authorization ask for the full test suite (baseline +
confirm-green), then an emitted grind through every fixable item. Default is dispatch, not
defer; defer needs named evidence."

## Default Stance

Dispatch, don't defer — defer needs named evidence, never a hunch. The operative triage policy
(what counts as evidence, what is NOT a valid defer reason, severity classification) lives only
in `${CLAUDE_PLUGIN_ROOT}/queue-profiles/bug.yaml` § `triage_policy`; this command cites it, it does not
restate it.

## Arguments

`--targets=<red-set dir | failing-tests file | backlog>` — the submission's `targets` arg (required;
`backlog` when none is named and no evidence exists). `--appetite=hunt|standard|sweep` (default `standard`) — passed through to the engine; its
meaning is the profile's `appetite` block. `standard` stops at 40 agent calls and its `where`
excludes P3: name `sweep` for a large TF set. `--max=N` → `--limit N`. `--budget-tokens=N` — passed through.
To subset rows add `--where '<JSON DNF>'` (or `--where-file`) to the emit call: an OR of AND-lists
of `[field, op, value]`, ops `==`/`in`; state in the report any rows it excluded.

## Out of Scope

`gh pr merge`/`create` against main, `git push origin main`, hibernate/shutdown/kill-process,
`--no-verify`/`--no-gpg-sign`. No exceptions, no mid-run ask.

## Phase 0 — Preflight

Note backlog presence/count; confirm `git branch --show-current` is the day branch and capture it
as `BLITZ_BRANCH`: the `coordinator.dayBranch` designation when the repo has one (a cloud session
records its harness-assigned branch there at SessionStart), else `work/{machine}/{date-or-span}`.
Halt on anything else, always on `main`, the default branch, or a detached HEAD — fail-closed, no
override. After `/merging-to-main` deleted the day branch, cut a fresh `work/{machine}/{date}` from main first. Cited evidence, including the engine's per-item `.done.md` and `.verify.md` records, goes to `state/queue-grind/bug/evidence/{run-id}/`. Mechanics: wiki.

## Phase 0.6 — Tier-U Authorization

Compute the ask, then put it once, before Phase 0.7. Resolve the fast and full commands with
`coordinator-resolve-validation-cmd --fast` and `--full`. Name each resolved command, and say
"both tiers run `<cmd>`" when the two are byte-identical. Quote each tier's last duration from `tier-last-run read` or the measured
note in `coordinator.local.md`, else the literal "no recorded duration". Ask: *"This run needs
the suite — once now to baseline, once after fixes to confirm green. Fast runs `<cmd>`, last <duration>.
Full runs `<cmd>`, last <duration>. Authorize the suite for this run?"* Only an
explicit affirmative naming its subject (or a terse "yes" in direct reply) qualifies — general
blitz approval doesn't. Granted → `tier-u-grant-cli grant pm <note>`, proceed; the same session-scoped
token covers the confirm-green re-run (`tier-u-grant-cli check`, no second ask). Declined → write
nothing, backlog-only leg, note the decline in the report.

## Phase 0.7 — Choose Targets

Targets are one of: existing evidence, a fresh `testing.suite_runs` record, a baseline taken when
granted, or `backlog`. Take any baseline before a committing grind fires in this tree (including
`/debt-triage` Step 1's) or wait for it to finish; a baseline straddling another run's commits
misattributes.

**Cloud session: no baseline.** The cloud environment bars every broad suite. Skip the grant ask and this phase, report
`suite: not-run (cloud)`, and prove each fix with the tests covering its surface.

**Existing evidence is the baseline.** A captured suite log or red-set audit record the PM or a
prior run named (a `state/test-runs/` record, `state/audits/*red-set*`) replaces a fresh run and
becomes `targets`. When the machine-wide suite mutex is held, proceed on that record and take the
confirm-green suite when the lock frees.

Otherwise `coordinator-resolve-validation-cmd --full` resolves `TEST_CMD`: exit 0 full suite; exit 3
fast-tier fallback, report as `fast-fallback`, never call it the full suite; exit 2 unconfigured,
continue backlog-only, name the remediation, never fabricate a command. EM runs it directly as
`with-suite-mutex --collection full -- <TEST_CMD>` (`--collection fast` on exit 3) (subagents never run the suite); its `state/test-runs/<suite>-last.txt`
is the `targets`.

**Empty-backlog-and-green-suite short-circuit:** absent/empty backlog AND fully green resolved
suite → skip to a one-line all-clear, no commit. Not reachable under decline.

## Phase 1 — Submit the Run

Submit — one call, the whole run:

`Workflow({name: "coordinator:bug-blitz", args: {targets: "<red-set dir | failing-tests file | state/bug-backlog>", appetite?, limit?, budget_tokens?}})`

The engine's PreToolUse hook parses the targets, mints one `TF-*` row per failing test file, emits
the grind and fires it. Never parse, mint or emit by hand; a stub return of `halted: true` means the
hook didn't run — report it. The run's committer lands the minted rows with the fixes; commit nothing before the fire. Submitting is the PM's standing approval for every safe fix,
refute-confirmed close and plan-weight baton the run produces — no per-item ask.

**Cost.** Report the spend in `state/queue-grind/bug/runs/<run-id>.json` beside the hand-back
counts; no pre-run estimate.

## Spinoff Gate — Mint Themed Batons from the Baton Hand-Back After the Run

Cluster the hand-back's `baton` rows with `detect-initiative-candidates`, author to
`coordinator/docs/wiki/baton-lifecycle/baton-authoring-bar.md`'s bar. The only mint-time check that remains here
is "not already covered by a live handoff or plan" — phantom and mis-size checks are triage
policy already applied inside the grind, per the profile. No PM authorization message: the fire
already discharged it.

`park`, `wont-do`, `yagni`, `unclear-direction` and `needs-judgment` rows go to `coordinator:apm` (staff-eng for code) for a `pm_ruling:` disposition, not to the PM; only a `pm_only` matter reaches the PM, and the PM sees the receipt.
`plan-substrate-collision` is not on that list: fold the row into the colliding plan as a
committed annotation, per the memo-to-plan write-through discipline, and close the row citing
that plan; if the colliding plan is terminal, the row becomes a baton instead. The universal
engine types (`budget-exhausted`, `verify-failed`, and the rest) are reported, with the re-emit
command from the receipt.

## Queue Terminus

The four outcome classes of `coordinator/docs/wiki/ceremony-calibration/queue-terminus-doctrine.md` — cite, don't
restate: dispatch (`small`/`fix`), solo spinoff (`big`, PM-authorized), close
(already-fixed/file-removed/wontfix), themed baton (N `small` items sharing a thesis). Firing the
emitted grind is the run-authority act standing in for the PM-authorization a themed baton or
`big` item would otherwise need (Spinoff Gate). Bug-specific dispositions — severity, repro, the
`wontfix` status value — are preserved; the four classes are the terminus, not a replacement.

**Partition.** File footprint governs wave dispatch; theme governs baton authorship only: a baton
whose members land in different footprint waves is one baton citing each wave. **Gate.** A themed
baton is never dispatched as a `small` immediate fix; it is minted at the Spinoff Gate.
Mechanics: wiki.

## Phase 4 — Archive and Report

Archive only the rows this command disposes after the run: baton-minted rows, closed with
`closed_by: spun-off-<path>`, via a plain rename plus `--declared-revert`. The in-run committer
closes every other row. The EM commits each minted baton together with the archival of the rows
it absorbs, as one scoped commit per baton via the committer route, with `--declared-revert` for
the removed rows.

**Per-item cadence.** One commit per verified fix, never collapsed per batch.

**Review routing.** No in-run review gate (PM ruling `ecbb6b786`). Freeze the run range:
`freeze-review-diff --range "<start-sha>..HEAD" --slice-id "bug-blitz-<run-id>"`; name
`/workstream-complete`'s downstream coverage (`code-reviewer` on any executor dispatched) in the
report as the surface the frozen path is handed to. Under `/autonomous` no surface fires that
review for a hands-off grind: the gap is documented, not closed.
The `j-bug-blitz-commit-readiness` hold
is the engine's pre-commit precondition, not a review gate; never claim in-run reviewer coverage,
never hand-apply findings, write no `state/review-trail/` record. BLOCKED under `/autonomous`:
halt, fixes left uncommitted
(`coordinator/docs/wiki/bug-blitz-residue/bug-blitz-review-gate.md`).

Re-run the suite (mandatory if any fix dispatched, only if Tier-U was granted). All clear → PASS.
**Disposition splits on whether the failure was already red at baseline:** a pre-existing failure
still red after one corrective wave: stop chasing — leave it reverted to baseline, or `git revert`
a committed non-working fix — and surface it as a spinoff candidate; a NEW failure green at
baseline is a self-inflicted regression: `git revert <introducing-sha>` is **mandatory** (never
`git reset` — branch is pushed), confirm green, name it in the report. **One corrective wave only,
in either branch.** Never report green with a known-red suite. Clean scratch
after the archive commit succeeds. Full mechanics: wiki.

**Report by exception** — two lines always, rest only when not clean:

```markdown
## Bug Blitz Complete

**Backlog:** N → M
**Resolved this run:** F items (backlog: Fb, failing tests fixed: Ft)
```

Add `**Fix correct, commit refused:**` (id, reason) / `**Spun off (need plan):**` / `**Re-attempted (still blocked):**` / `**Suite gate:**` /
`**Suite noise (not chased):**` / `**Closed already-fixed:** R ran / I inspected` only when
non-empty — that last one splits by evidence rung because one number over two standards hides
the weaker half from the reader, and from you. Never restore a run-id line, a silent
already-fixed line, or a clean `Suite gate: PASS` line — their absence already means clean.

## Failure Modes, Stop-Early, Relationship to Other Commands

Full tables: wiki. The load-bearing invariants that stay here: never rollback completed work on
early stop; never fabricate a test command; never weaken an assertion; `git revert` (never `git
reset`) for a self-inflicted regression on a pushed branch.

**Usage-limit advisory.** On the usage-limit advisory, finish the item in hand, open no next
item, then run Phase 4 (archive and report) and stop. See
`coordinator/docs/wiki/skills-corpus/usage-limit-pause.md`; token
`A-DRIVER-PAST-ITS-USAGE-THRESHOLD-FIRES-NOTHING-NEW`.

`/workstream-start` advocates this command on backlog depth and, independently of it, on a **red-suite predicate** — a non-empty delta in `state/test-red/<machine>.yaml` against the acknowledged baseline, never bare redness. Both arrive here as the same emitted grind.
