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

`/pickup`'s auto-fire claims batons on the invocation line — **check that it did, don't assume
it.** No claimed-baton list in `additionalContext` means the hook did not fire, and its bootstrap
fails OPEN: a missing or unresolved script produces silence, not an error, so a run that skipped
this phase's engine inputs reads exactly like one that had them. Claim by hand
(`pickup-assemble apply <path>`), say so in the announcement, and carry on — the run is correct
either way, but only if you noticed. Then resolve open judgment points and claim residue. Not ready → `pickup-assemble drop <path>`;
readiness-routed but still coherent → keep the claim, name routed items in the Phase 1 ledger and
the successor handoff. No brief → `pickup-assemble brief <path> [AND <path>]...`. Announce:
"Claimed N batons: [paths]. [M put back down: reason.]" Detail: wiki.

**Aggregate execution baton** (a baton carrying an `aggregate_execution` block): read the roll-up,
never infer it — `python3 "${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/skills/pickup/aggregate-rollup.py" <baton>`. `FIRE` (exit 0)
fires every constituent; `PARTIAL-FIRE` (exit 1) fires the named subset, and its `excluded` and
`withheld` rows enter the Phase 1 inventory as items with a named non-terminal disposition;
`NO-FIRE` (exit 2) fires nothing — put the baton back down. **Exit 1 is a membership fact, not an
error**, and a PARTIAL-FIRE forces CONTINUANCE at Phase 6: a partial fire that reads as completion
is the drop this shape exists to stop. Contract: wiki.

## Resolving the scripts this ceremony runs

These live only in the doctrine repo's `coordinator/bin/` and get no settings-home launcher, so
rung 2 404s. Open every fence below with the prescribed rung from
`snippets/resolve-coordinator-bin.md` § CLIs with no launcher — `_doe_root` does not survive from
one Bash call to the next:

    _sh=${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}
    _doe_root=$(cat "$_sh/machine-local/.doe-root" 2>/dev/null || cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)
    [ -n "$_doe_root" ] && [ -d "$_doe_root/coordinator" ] || { echo "unresolved .doe-root — re-run /coordinator:install" >&2; exit 1; }

**Keep the `:-`, never `:?`, and keep the emptiness check.** `CLAUDE_PLUGIN_ROOT` is EMPTY in a
Bash tool call, so the default arm is the one that carries; unguarded, it expands to a
root-relative `/coordinator` that reads as "this script does not exist" rather than "the root did
not resolve".

## Phase 0: Readiness Gate

**Certification leg — runs first, and the bypass below does not reach it.** Plan-sourced items
only; an item with no plan has nothing to certify and is not refused for it. One revalidation
step, two ordered legs: recompute the plan body sha against `mise_prepped_sha` (pure, spawn-free);
only if that passes, re-run each `census[].command` and diff against `result`. Fire on sha-leg
CERTIFIED with no entry-level census DRIFT; an unclosed census leg (`UNDECIDABLE` / `REFUSED` /
`UNRUNNABLE`, per-entry or rolled up) does not block the fire — record it as a named,
non-blocking finding in the Phase 1 ledger. STALE → re-gate (`python3 "${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/bin/mise-prep-gate.py" <plan>`), then re-stamp;
UNSTAMPED → gate and stamp; MALFORMED → a hand-written stamp, repair the frontmatter; census
drift → the premise moved, re-plan. **Name the state** — "not certified" sends an author to the
wrong repair. A handoff can assert executability; it cannot assert a sha. States, recipe and the
four repairs: `coordinator/docs/wiki/mise-prepped-attest.md`.

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

Quote the `additionalContext`-minted run-id (`backlog-grind-assemble mint-run-id mise-en-place`
if the hook didn't fire on either entry path — typed `UserPromptExpansion` or a model-invoked
`Skill` call through the `preuse-skill-dispatch.py` fan-in). **`mint-run-id` is a subcommand of
`backlog-grind-assemble`, never a CLI of its own** — no launcher carries that name, so the bare
verb exits 127. If two engine-minted run ids are in context, use the first.
Capture `git rev-parse HEAD` as start SHA before dispatching.

>3 items → backgrounded Sonnet scout writes `state/mise-inventory/<run-id>.md` (frontmatter
`run_id`, `start_sha`; one row/item under a literal `## Chunk table` heading, first column named
exactly `id`, then: spec path | summary | footprint | deps | verification | complexity |
disposition), sourced from `tasks/*/todo.md`, enriched stubs,
`$ARGUMENTS`, claimed batons — not `tasks/`. `disposition` updates every wave gate: a live row
reads `pending`, `queued` or `in_progress`; a terminal one opens with a § Phase 6 verb. ≤3 items
already read → inline instead. Template/sources: wiki.

## Pre-Dispatch Verification

Backlog/plan-sourced items: Haiku agent per item, `still-open` vs `already-fixed` at HEAD. Drop
`already-fixed` before queuing.

**Falsifier integrity**, same phase, plan-sourced items whose frontmatter carries
`prime_exit_criterion.falsifier`: one `falsifier-integrity-reviewer` dispatch each. Run
`python3 "${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/bin/instrument-can-report-red.py" --json` over the instrument first and pass
the on-disk JSON path as the brief's `can_report_red_report` — a brief field, never an instruction
to go compute it. Verdict `SOUND` | `BROKEN` | `UNREVIEWABLE`, naming the tell; it reports and
never refuses. `BROKEN` routes the item out of the wave with the tell named — the existing
dropped-item behaviour. An item with no `falsifier` sub-object is not reviewed and is not a
finding here. Inputs the phase marshals, and the blinding invariant that bounds them:
`coordinator/docs/wiki/falsifier-integrity.md`.

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
executors, verifiers, and the per-wave commit phase alike. `model: 'sonnet'` on every `agent()` whose `subagent_type` is UNPINNED — never alongside a
`coordinator:*` type, which pins its own tier and whose pin guard refuses the override —
≤5 write-capable executors/barrier. **No hand-dispatch, and no single-wave carve-out:** manual
`Agent` calls spend EM context, which is the binding constraint in a mise run, and "only one wave"
is not a shape a Workflow cannot express. Verifiers ride inside the Workflow — call
`provision-sidecar --agent-type <type>` for any phase whose `report_type_map` row is not
`run-report`.

Don't hand-author the script — mint and emit:
`COORDINATOR_AGENT_TYPE_HOST=coordinator python3 "${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/bin/emit-dispatch-workflow.py" --inventory state/mise-inventory/<run-id>.md`
writes the spine (item-id → chunk-id, footprint → `writes`) plus the `.mjs`; fire it with
`Workflow({scriptPath: ...})`.

**Ignore the Stop-hook's "commit and push" advisory mid-run** — the dirt it flags is a live
wave's footprint. The only commit path is the wave-gate commit above; never widen it to satisfy
the hook.

**Then stay awake for as long as it runs — on a managed-remote host, ending the turn to wait for
the completion notification is what kills the run.** The container is reclaimed on session
inactivity and background work does not count as activity, so a fired wave plus a quiet EM is a
dead wave: journals stop mid-run, no halt verdict is written, and `resumeFromRunId` is
same-session-only so what died is not resumable. Hold the turn with a `Monitor` that emits on a
poll interval and re-arm it at expiry. Push after every wave, not at the end of the run — the repo
volumes and settings home survive reclamation, so an unpushed commit is the only thing that does
not. `a-quiet-session-gets-its-container-reclaimed-under-running-work`.

**The env var is not optional, and omitting it does not fail — it downgrades.** The script probes
for a plugin root to decide whether `coordinator:*` agent types resolve, and a Bash subprocess
carries neither `CLAUDE_PLUGIN_ROOT` nor a roster, so it degrades every `coordinator:executor`,
`git-commit-agent` and `test-runner` in the run to `general-purpose` — no do-not-commit snippet,
no pathspec discipline, no sandbox preamble — and says so in one stderr line that reads like
housekeeping. You are the only party that can see your own agent roster: assert it. Pass
`host` instead if your roster genuinely lacks the `coordinator:*` types, never to silence the
narration. In PowerShell set `$env:COORDINATOR_AGENT_TYPE_HOST = "coordinator"` first. It reads the `## Chunk table` heading and its `id`
column and nothing else — both names are literal, and a record spelling either differently is
refused, not guessed at. It refuses too on an unrecognized disposition or a footprint naming no
backticked path — fix the record, don't work around it. Both artifacts archive with the record.

Enable the sentinel first: `misc-session-and-guards autonomous-sentinel enable --mode
mise-en-place` (disable at Phase 6). Executors always background; only the EM commits, once per
wave, from the DONE summary — never the transcript.

Per wave:
1. Mark `in_progress`, tracker-sweep the item (wiki). The Workflow's executor phase carries each
   item's spec, footprint, and the executor **return** contract — done-summary path, touched-files
   set, self-verify constraint — in its emitted row prompt. The brief surfaces that same contract
   as `d-mise-executor-dispatch-prompt-template`; the two are rendered from one definition, not
   passed from one to the other, so reading it in the brief is not what puts it on an executor.
   The wave gate's pathspec and the verifier's first evidence source both read what it produces. Never a hand-rolled `Agent` call to attach
   them: a run that drops the contract reports narrative where the committer needs paths
   (`AN-ORPHANED-RETURN-CONTRACT-IS-A-DROPPED-ONE`).

<!-- engine-gap: field=tracker_sweep.item_state producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->
2. On DONE (verify via disk — DONE path + `dirty-tree-gate --terminator mise-item-done`
   (`--terminator` is a free-form display token, not a validated enum — confirmed against
   `coordinator_core.ops.dirty_tree_gate.main` in `claude-klabauter`, which only interpolates it
   into stderr text — so this value cannot fail loud at runtime; verified, no re-derivation
   needed), which
   classifies every dirty path as session-authored, known-peer, or unattributable rather than a
   hand-parsed status line; never trust idle-alone; never double-dispatch onto a live footprint):
   the Workflow's verifier phase runs a Haiku verifier per
   item from the brief's `d-mise-haiku-verifier-dispatch` fields. Batch per wave; gate on all-`PASS`.
   Non-PASS → re-dispatch, revert+re-plan, defer, or early-stop. **Peers write concurrently to
   this same checkout — footprint verification is scoped to the item's own declared paths.** A
   bare unscoped status/diff read shows every live peer's work; a path outside the item's
   declared footprint is another item's and is not evidence about this one.

   **Partial wave landing** — some items landed, some did not. Commit the PASSed items' footprint
   paths only, never the wave's union; an unlanded item returns to `pending` with
   `tried_and_abandoned` updated, and the wave is not announced complete. Reverting an unlanded
   item's residue is scoped to that item's own declared footprint paths — never a bare
   `git checkout`/`git clean`, which reaches a peer's work. Unlanded items are non-terminal, so
   the run's verdict is CONTINUANCE.
3. Wave gate: a commit phase INSIDE the Workflow — `coordinator:git-commit-agent` over **the
   PASSed items' footprint paths**, via `ceremony.commit_v2` (that plus a plain scoped
   `git commit -- <paths>` is the whole allow surface; `ceremony.scoped_git_commit` is a deleted
   op, not a route). Neither live route re-asserts the branch, so the phase's prompt names the
   expected branch and requires a read-only check before committing. No ledger call in the phase —
   `commit_v2` writes the row itself, so adding one duplicates it. Never hand-typed git.
   Bookkeeping stays EM-side, outside the Workflow: `backlog-grind-assemble apply mise-en-place
   --run-id <id>` with **no** `--wave-path` (that form builds no commit directive).

   **A partial wave still commits, and the pathspec comes from the reports, not the wave.** The
   wave's declared union is INTENT — it names what the wave set out to write; the DONE executors'
   reports are the CLAIM. Derive the pathspec from the reports and commit it. A blocked or
   non-`PASS` item contributes no paths and blocks nothing: its chunk id drops out of the subject
   alongside its paths, and § Partial wave landing above governs the rest. **Refusing to commit
   because one item of N is blocked is the failure mode, not the safe choice** — it is a coherent
   inverse of this rule that has been reasoned to in a live run, and it strands every other
   executor's work uncommitted on a checkout a dozen peers are writing to, where HEAD moves
   underneath it. Holding work back is the expensive outcome here; the unlanded item is
   non-terminal and returns to `pending` either way.

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
  Enforcement detail: `coordinator/docs/wiki/subtractive-adjudication.md`.
- **Exhaustion check** (live disposition ledger): COMPLETE if every item terminal
  (PASSed/routed-out/already-fixed/dropped), else CONTINUANCE — wording only, tail always runs
  full. Three inputs force CONTINUANCE regardless of the item ledger: an aggregate PARTIAL-FIRE
  (its excluded plans ride a successor, so they are not terminal), an unlanded item from a partial
  wave, and an INCOMPLETE adjudication. CONTINUANCE → `state/mise-inventory/<run-id>-continuance.md`
  naming the resume invocation, a Phase-0-bypass assertion, the wave map — committed+pushed before
  hibernating. That record IS the discharge; `/handoff` is keyword-gated, so it is the PM's
  follow-up, and the tail summary names it as such.
- **Anti-vacuity:** scoped `git status --porcelain -- <this run's footprint paths>`, never bare
  unscoped. Non-empty → repair via the wave-commit op before freezing.
- **Review routing:** no review gate of its own (PM ruling). Freeze:
  `freeze-review-diff --range "<start-sha>..HEAD" --slice-id "mise-<run-id>"`; name
  `/workstream-complete` or a review-and-cap `/handoff` in the tail summary. An aggregate baton's
  membership inherits this discharge unchanged — the obligation is keyed on the diff range, which
  every constituent lands inside; `/workstream-complete`'s chain diff covers a different object
  and is untouched. **The frozen diff and its `.head.sha` (`state/review-trail/`) and executor
  evidence (`.coordinator-local/plan-sidecars/`) are gitignored by design — absence from the commit is EXPECTED
  and is not a missing step.** <!-- Review: coordinator-code-reviewer -- distinct fact the trim
  dropped: an item can legitimately go DONE while its sidecar record contributes nothing to the
  wave commit, so DONE must never be inferred from commit contents. --> A DONE item's evidence can
  legitimately contribute nothing to the wave commit — never infer DONE-ness from commit
  contents. Tripwire:
  `A-GITIGNORED-DELIVERABLE-IS-INVISIBLE-TO-EVERY-COMMIT-BASED-READER`.
- **Orphan check**, on that same range and inside this phase, never a mechanism of its own: read
  the `.diff` file § Review routing just froze — a plain unified diff, not `--name-status` — and
  take the added paths (each `--- /dev/null` / `new file mode` hunk) off it (never a fresh raw
  diff re-run — the freeze already materialized this range to disk one bullet above), intersect with
  the run's declared `writes:`, and ask of each whether any other file in the tree references it.
  Zero
  referencers → **ORPHAN-CANDIDATE**, named in the tail summary with its path. It is
  **necessary, not sufficient, and is never reported as a correctness verdict** — a surface can
  acquire a referencer and still be wrong, and a clean check licenses no claim that the run's work
  is right. It gates nothing, routes nothing, and never moves the verdict line.
- **End-of-run verification:** run every test file the cumulative diff touched, once, EM-only,
  naming each path literally. Never the repo's fast- or full-suite command — the suite guard
  refuses it without a PM grant; say which files you ran instead.
- **Tracker sweep:** final pass, same procedure as the per-wave sweep (wiki); commit
  (`--message "mise: tracker sync"`).
- **Baton disposition (whenever Phase 0a ran):** the engine flips a baton terminal when its plan is stamped `implemented` or its workstream concludes — no manual flip. One still advertising live work after that is a **defect**: report it, don't hand-correct. Unstarted → `pickup-assemble drop <path>`; mid-stream → successor via `/handoff`. State each disposition in the tail summary.
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
pushes the CONTINUANCE record first if applicable, then `shutdown /h` / `systemctl hibernate`.

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
claims the batons. **And either entry path fires them:** a typed slash command reaches both hooks
under `UserPromptExpansion`; a model-invoked `Skill` call for either verb reaches the same two
hooks' legs through `preuse-skill-dispatch.py`, the `PreToolUse`/`Skill` fan-in that hosts them —
so a PM writing the verb inline, a skill forwarding to this one, or a skill fired under context
pressure starts with the same inputs a typed invocation would have gotten. The engine vocabulary
does not follow the verb — the sentinel mode, the cadence passed to `mint-run-id`/`brief`, and
`handoff.schema.json`'s cadence key all stay `mise-en-place`, which is why this file keeps that
name.

`/update-docs`, `/workday-complete`, `/merging-to-main` are PM-run afterward, never auto-invoked.
`/autonomous` composes with this run: it governs the unattended posture (sentinel, nudge
suppression), this command governs the backlog sequence — the sentinel is enabled here with
`--mode mise-en-place` precisely so a reader can tell a `/mise` run's sentinel from an
`/autonomous` one.
`pipelines/mise-en-place/PIPELINE.md` carries this sequence at greater depth, where shipped.
