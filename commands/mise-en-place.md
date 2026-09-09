---
name: mise-en-place
description: "Autonomous backlog run — flight-recorder prep, then run-through."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[baton-path [AND baton-path]...] [--hibernate]"
---

# Mise-en-Place — Autonomous Backlog Execution

Flight-record the backlog, then run it straight through — implicit PM authorization, messy parts
included. From Phase 5 on, never pause to ask; stop only for a PM-only question or § When to Stop.
Not plan-as-you-go — decisions are made before the run.

**Announce:** "Running /mise-en-place — prepping flight recorder, then straight shot through the
backlog."

## Arguments

| Trigger | Mode | Tail |
|---|---|---|
| none / no explicit hibernate phrase | Standard (default) | per-wave commit+push, no /update-docs |
| `--hibernate` / "hibernate"/"shut down"/"power off" | Hibernate | verify push, then hibernate |

Soft signals ("overnight," "it's late") do not authorize hibernate. Default standard; never ask.

## Phase 0a: Baton Intake

`/pickup`'s auto-fire already claimed batons on the invocation line. Resolve open judgment points,
claim residue (`pickup-assemble apply <path>`). Not ready → `pickup-assemble drop <path>`;
readiness-routed but still coherent → keep the claim, name routed items in the Phase 1 ledger and
the successor handoff. No brief → `pickup-assemble brief <path> [AND <path>]...`. Announce:
"Claimed N batons: [paths]. [M put back down: reason.]" Detail: wiki.

**Aggregate execution baton** (a baton carrying an `aggregate_execution` block): read the roll-up,
never infer it — `python3 coordinator/skills/pickup/aggregate-rollup.py <baton>`. `FIRE` (exit 0)
fires every constituent; `PARTIAL-FIRE` (exit 1) fires the named subset, and its `excluded` and
`withheld` rows enter the Phase 1 inventory as items with a named non-terminal disposition;
`NO-FIRE` (exit 2) fires nothing — put the baton back down. **Exit 1 is a membership fact, not an
error**, and a PARTIAL-FIRE forces CONTINUANCE at Phase 6: a partial fire that reads as completion
is the drop this shape exists to stop. Contract: wiki.

## Phase 0: Readiness Gate

**Certification leg — runs first, and the bypass below does not reach it.** Plan-sourced items
only; an item with no plan has nothing to certify and is not refused for it. One revalidation
step, two ordered legs: recompute the plan body sha against `mise_prepped_sha` (pure, spawn-free);
only if that passes, re-run each `census[].command` and diff against `result`. Fire on CERTIFIED
alone. STALE → re-gate (`python coordinator/bin/mise-prep-gate.py <plan>`), then re-stamp;
UNSTAMPED → gate and stamp; MALFORMED → a hand-written stamp, repair the frontmatter; census
drift → the premise moved, re-plan. **Name the state** — "not certified" sends an author to the
wrong repair. A handoff can assert executability; it cannot assert a sha. States, recipe and the
four repairs: `docs/wiki/mise-prepped-attest.md`.

Bypass only if the invoking handoff asserts **executability** (not merely pickup-readiness) for
the named items in its body — a stated stop condition or `deployment_state: awaiting_gate` always
wins. Uncertain → don't bypass.

Otherwise, gate every item before Phase 1:

| # | Criterion |
|---|---|
| 1 | Decisions made — AC explicit/verifiable; unwritten detail is fine, an undecided fork is not |
| 2 | Downstream contracts sequenced — decided-but-unbuilt legal, undecided is not |
| 3 | Pure-executor — a Sonnet/inline executor alone can finish it |
| 4 | Footprint declarable and data-reachable at dispatch time |
| 5 | Verification mechanical — checkable, not "looks right" |

Failing item → route out with a named reason, run the rest; decline the whole run only if the
residue isn't coherent or routing needs a PM call. Patterns/examples: wiki.

## Phase 1: Inventory

`backlog-grind-assemble brief mise-en-place --run-id <run-id>` computes the empty-backlog judgment
point and the `d-mise-executor-dispatch-prompt-template` directive; not Phase 0.

Quote the `additionalContext`-minted run-id (`mint-run-id mise-en-place` if the hook didn't fire).
Capture `git rev-parse HEAD` as start SHA before dispatching.

>3 items → backgrounded Sonnet scout writes `state/mise-inventory/<run-id>.md` (frontmatter
`run_id`, `start_sha`; one row/item: identifier | spec path | summary | footprint | deps |
verification | complexity | disposition), sourced from `tasks/*/todo.md`, enriched stubs,
`$ARGUMENTS`, claimed batons — not `tasks/`. `disposition` updates every wave gate. ≤3 items
already read → inline instead. Template/sources: wiki.

## Pre-Dispatch Verification

Backlog/plan-sourced items: Haiku agent per item, `still-open` vs `already-fixed` at HEAD. Drop
`already-fixed` before queuing.

**Falsifier integrity**, same phase, plan-sourced items whose frontmatter carries
`prime_exit_criterion.falsifier`: one `falsifier-integrity-reviewer` dispatch each. Run
`python coordinator/bin/instrument-can-report-red.py --json` over the instrument first and pass
the on-disk JSON path as the brief's `can_report_red_report` — a brief field, never an instruction
to go compute it. Verdict `SOUND` | `BROKEN` | `UNREVIEWABLE`, naming the tell; it reports and
never refuses. `BROKEN` routes the item out of the wave with the tell named — the existing
dropped-item behaviour. An item with no `falsifier` sub-object is not reviewed and is not a
finding here. Inputs the phase marshals, and the blinding invariant that bounds them:
`docs/wiki/falsifier-integrity.md`.

## Phase 2: Sequence and Parallelize

Max concurrency, zero overlap within a wave. Sort by dependency then size. Footprint =
write-targets from the spec (stub `touches:` overrides a cached README graph; a consumer-layer
item's data source is part of its footprint). Wave 1 = no deps/overlap; Wave N = depends on or
overlaps earlier. All-overlap → N waves of 1, fine. N-plan convergence and risk-flagging: wiki. No
worktrees, ever.

## Phase 3: Flight Recorder

`TaskCreate`: goal task (item list, tail mode); per-item task (id, spec path, wave, footprint,
verification, `pending`, empty `tried_and_abandoned`); hibernate-only tail tasks ("Verify pushes,"
"Hibernate PC").

<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface
(`ToolSearch("select:TaskCreate")` returns nothing) → fall back to `coordinator-tasks-mirror` for
the same flight-recorder role; do not assume either state without checking. When Task* is
unavailable, dispatch the phases in order, waiting on each completion notification — that is the
ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

Update `tried_and_abandoned` before any new approach; read it back after compaction before retrying
anything.

## Phase 4: Confirm and Fire

Output, then start Phase 5 immediately:

```
## Mise-en-Place — Ready to Fire

**Items queued:** [N items] across [M waves]
**Wave 1** (parallel): [items] — file-disjoint ✓
**Wave 2** (parallel): [items] — depends on Wave 1
**Aggregate:** [FIRE | PARTIAL-FIRE, N of M plans — excluded: [plan (state)]; withheld: [plan rows]]
**Risks:** [...]
**Tail:** [standard | hibernate line]
**Estimated scope:** [...]

Proceeding.
```

## Phase 5: Execute

Default: ONE background Workflow for the whole run, carrying the Phase 2 DAG across every wave —
executors, verifiers, and the per-wave commit phase alike. `model: 'sonnet'` on every `agent()`,
≤5 write-capable executors/barrier. **No hand-dispatch, and no single-wave carve-out:** manual
`Agent` calls spend EM context, which is the binding constraint in a mise run, and "only one wave"
is not a shape a Workflow cannot express. Verifiers ride inside the Workflow — call
`provision-sidecar --agent-type <type>` for any phase whose `report_type_map` row is not
`run-report`.

Don't hand-author the script — mint and emit:
`python coordinator/bin/emit-dispatch-workflow.py --inventory state/mise-inventory/<run-id>.md`
writes the spine (item-id → chunk-id, footprint → `writes`) plus the `.mjs`; fire it with
`Workflow({scriptPath: ...})`. It refuses on an unrecognized disposition or a footprint naming no
backticked path — fix the record, don't work around it. Both artifacts archive with the record.

Enable the sentinel first: `misc-session-and-guards autonomous-sentinel enable --mode
mise-en-place` (disable at Phase 6). Executors always background; only the EM commits, once per
wave, from the DONE summary — never the transcript.

Per wave:
1. Mark `in_progress`, tracker-sweep the item (wiki), dispatch each to a `run_in_background`
   Sonnet executor with the spec, footprint, and the brief's
   `d-mise-executor-dispatch-prompt-template` fields.

<!-- engine-gap: field=tracker_sweep.item_state producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->
2. On DONE (verify via disk — DONE path + scoped `git status`; never trust idle-alone; never
   double-dispatch onto a live footprint): dispatch a Haiku verifier per item using the
   brief's `d-mise-haiku-verifier-dispatch` fields. Batch per wave; gate on all-`PASS`.
   Non-PASS → re-dispatch, revert+re-plan, defer, or early-stop. **Peers write concurrently to
   this same checkout — footprint verification is scoped to the item's own declared paths.** A
   bare unscoped `git status`/`git diff` shows every live peer's work; a path outside the item's
   declared footprint is another item's and is not evidence about this one.

   **Partial wave landing** — some items landed, some did not. Commit the PASSed items' footprint
   paths only, never the wave's union; an unlanded item returns to `pending` with
   `tried_and_abandoned` updated, and the wave is not announced complete. Reverting an unlanded
   item's residue is scoped to that item's own declared footprint paths — never a bare
   `git checkout`/`git clean`, which reaches a peer's work. Unlanded items are non-terminal, so
   the run's verdict is CONTINUANCE.
3. Wave gate: a commit phase INSIDE the Workflow — `coordinator:git-commit-agent` over the union
   of changed paths, via `ceremony.commit_v2` (that plus a plain scoped `git commit -- <paths>`
   is the whole allow surface; `ceremony.scoped_git_commit` is a deleted op, not a route). Neither
   live route re-asserts the branch, so the phase's prompt names the expected branch and requires
   a read-only check before committing. No ledger call in the phase — `commit_v2` writes the row
   itself, so adding one duplicates it. Never hand-typed git.
   Bookkeeping stays EM-side, outside the Workflow: `backlog-grind-assemble apply mise-en-place
   --run-id <id>` with **no** `--wave-path` (that form builds no commit directive).

   **Peer-session commit collision**, checked before the commit and not after:
   `git log <wave-dispatch-sha>..HEAD --name-only -- <this wave's footprint paths>`. Non-empty
   means a peer landed **inside** this wave's footprint — a collision, distinct from the
   concurrent-session churn in § When to Stop, which lands outside it. Next call: re-dispatch the
   wave's verifier over the merged state for the colliding items only; still-`PASS` commits
   normally, non-`PASS` routes the item out with the collision named and its residue rides the
   successor. **Never revert, rebase, amend or force-push over the peer's commit** — a hard block,
   not a judgment call.
4. "Wave N complete ([items]). Firing wave N+1 ([items])." — never a question.

No worktrees.

## Phase 6: Tail

Mark tasks `completed`, disable the sentinel, then in order: subtractive adjudication, exhaustion
check, anti-vacuity gate, diff freeze, inventory archival (COMPLETE only), tracker sweep.

- **Subtractive adjudication** — the terminal pass over what the review layer added, run before
  the exhaustion check because its coverage feeds it. Build the revocation candidate ledger from
  **review-layer artifacts in this run's own sha range only** — integrator disposition blocks
  bucketed `applied`/`deferred` and their reviewer sidecars, keyed `<sidecar-stem>#finding-N`,
  each stamped `costRank` by the size of the integrated change. **The ledger is the address
  space**: sourcing it from the run diff or an executor report widens the adjudicator's authority
  silently, which is the thing to check in review, not its wording. Empty ledger →
  `NO-CANDIDATES`, no dispatch, recorded — a `/mise` run runs no review of its own, so empty is
  the ordinary reading. Non-empty → one `subtractive-adjudicator` dispatch, then land its return
  under the seven landing rules in the wiki. Every candidate — revoked, accepted, refused,
  unadjudicated — lands in `state/mise-inventory/<run-id>-adjudication.md`. Any `unadjudicated`
  candidate makes the phase INCOMPLETE, and the verdict line may not read COMPLETE while it is.
  Enforcement detail: `docs/wiki/subtractive-adjudication.md`.
- **Exhaustion check** (live disposition ledger): COMPLETE if every item terminal
  (PASSed/routed-out/already-fixed/dropped), else CONTINUANCE — wording only, tail always runs
  full. Three inputs force CONTINUANCE regardless of the item ledger: an aggregate PARTIAL-FIRE
  (its excluded plans ride a successor, so they are not terminal), an unlanded item from a partial
  wave, and an INCOMPLETE adjudication. CONTINUANCE → `/handoff` naming the resume invocation, a
  Phase-0-bypass assertion, the wave map — authored+pushed before hibernating.
- **Anti-vacuity:** scoped `git status --porcelain -- <this run's footprint paths>`, never bare
  unscoped. Non-empty → repair via the wave-commit op before freezing.
- **Review routing:** no review gate of its own (PM ruling). Freeze:
  `freeze-review-diff --range "<start-sha>..HEAD" --slice-id "mise-<run-id>"`; name
  `/workstream-complete` or a review-and-cap `/handoff` in the tail summary. An aggregate baton's
  membership inherits this discharge unchanged — the obligation is keyed on the diff range, which
  every constituent lands inside; `/workstream-complete`'s chain diff covers a different object
  and is untouched.
- **Orphan check**, on that same range and inside this phase, never a mechanism of its own: take
  the paths `git diff --name-status "<start-sha>..HEAD"` marks `A`, intersect with the run's
  declared `writes:`, and ask of each whether any other file in the tree references it. Zero
  referencers → **ORPHAN-CANDIDATE**, named in the tail summary with its path. It is
  **necessary, not sufficient, and is never reported as a correctness verdict** — a surface can
  acquire a referencer and still be wrong, and a clean check licenses no claim that the run's work
  is right. It gates nothing, routes nothing, and never moves the verdict line.
- **End-of-run verification:** run any deferred fast-test command once, EM-only, over the
  cumulative diff. Never run a deferred full-suite/unscoped command unilaterally — surface it.
- **Tracker sweep:** final pass, same procedure as the per-wave sweep (wiki); commit
  (`--message "mise: tracker sync"`).
- **Baton disposition:** claimed+completed → `/workstream-complete` (`pickup-assemble apply` is
  claim-side only, never a terminal-flip); unstarted → `pickup-assemble drop`; mid-stream → the
  one successor `/handoff`, naming every non-primary baton's residue.
- **Verdict line** reads exactly `COMPLETE` or `CONTINUANCE` — never a bare "done."
  The run-level verdict line MUST read exactly COMPLETE or CONTINUANCE; the word 'complete'
  may not appear as the run's disposition unless the exhaustion check passed. Item-level,
  wave-level and task-level uses of 'completed' (TaskUpdate, tracker sweep, baton
  disposition) are unaffected.
- **Composite disclaimer, once, beside the verdict.** Three instruments feed this line and each
  is honest alone: `mise_prepped_*` certifies a defect-class floor and attests nothing about
  completion; the orphan check is necessary-not-sufficient; an all-`accept` adjudication is a
  null result. Nothing composes them, so a reader seeing `COMPLETE` from a run that was
  prepped, orphan-checked and adjudicated reads a strong claim no constituent makes. Print the
  composition, not three caveats in three contracts nobody reads together:
  `COMPLETE — entry floor certified, no orphan found, nothing revoked. None of the three is a
  correctness verdict.`

**Close:** scoped footprint clean, commit residue, report the verdict, discharge review routing.
Standard stops there. Hibernate additionally verifies+pushes (never on push failure), authors+
pushes a CONTINUANCE handoff first if applicable, then `shutdown /h` / `systemctl hibernate`.

Never merge to main; never worktrees, any phase. Full mechanics for every bullet above: wiki.

## When to Stop

**Do NOT stop for:**
- Routine fixable errors — fix and continue.
- Minor ambiguity resolvable with one judgment call — make the call, note it.
- A single item being harder than expected — push through.
- Wanting to "check in" — the PM authorized the full run.
- **Agent recovery** (rate-limited/crashed agents, auth failures, uncommitted disk state left by a
  stalled executor, missing subsystem registrations) — routine operational handling. Re-dispatch,
  audit what's on disk, finish the work; recovery IS the work the PM authorized, and asking
  whether to finish tractable, scoped, roadmap-aligned work is a failure of the role.
- **Concurrent-session churn** (another session's commits sweeping staged changes, attribution
  splits, shared-file merges) — the ordinary agree-case, closed per `snippets/scoped-commit-route.md`.
  Then continue.
- **Subsystem registration gaps** — a handler on disk but unregistered in `Subsystem.h`/`.cpp` is
  a routine finish-the-work case, not a PM question.

Full worked rationale for each: wiki. Context exhaustion with backlog remaining is non-failure:
run the full Phase 6 tail, take CONTINUANCE.

| Situation | Action |
|---|---|
| Ambiguous spec / scope far larger / breaking change / 2+ workaround pattern / structural verification failure | Stop early: commit current work, update tasks/plan status, verify pushed, hibernate anyway if invoked |
| Fixable verification error | Fix and continue |
| Executor BLOCKED | Spec-fixable → update+re-dispatch; architectural → stop early |
| Executor wrote outside its footprint | Revert, re-analyze overlap, adjust waves, re-execute |
| Peer commit landed INSIDE this wave's footprint (a collision, not churn) | Re-verify the merged state for the colliding items; PASS commits, non-PASS routes out. Never revert the peer's commit |
| Wave landed partially | Commit the PASSed items' paths only; unlanded items return to `pending`; verdict is CONTINUANCE |
| Push fails before hibernate | Do NOT hibernate — stop and report |
| Compacted mid-run | Re-orient via TaskList/TaskGet; check `tried_and_abandoned`; resume `in_progress` |

## Relationship to Other Commands

**This run is `warp-speed-execute`; this file is it.** `/warp-speed-execute` is a forwarding alias
onto this body, not a second ceremony — there is one wide-run ceremony. **Either verb is a
first-class invocation:** both autofire hooks admit both spellings
(`hooks/scripts/mise-autofire.py :: _MISE_COMMAND_NAMES`,
`hooks/scripts/pickup-autofire.py :: _BATON_GRAB_COMMAND_NAMES`), so either mints the run-id and
claims the batons. The engine vocabulary does not follow the verb — the sentinel mode, the cadence
passed to `mint-run-id`/`brief`, and `handoff.schema.json`'s cadence key all stay `mise-en-place`,
which is why this file keeps that name.

`/update-docs`, `/workday-complete`, `/merging-to-main` are PM-run afterward, never auto-invoked.
`/autonomous` composes with this run: it governs the unattended posture (sentinel, nudge
suppression), this command governs the backlog sequence — the sentinel is enabled here with
`--mode mise-en-place` precisely so a reader can tell a `/mise` run's sentinel from an
`/autonomous` one.
`pipelines/mise-en-place/PIPELINE.md` carries this sequence at greater depth, where shipped.
