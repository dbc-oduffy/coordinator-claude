---
name: execute-plan
description: Execute a PM-approved plan via per-chunk executor waves.
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — End-to-End Plan Execution

Run a PM-approved plan end-to-end to full completion without stopping for permission between
tasks. Invoking `/execute-plan` on a plan IS the PM's authorizing act; plan-frontmatter
`execution_authorized_at` is the record of that act, not a precondition for it. **It also
satisfies a chunk body's own "needs PM assent at execution dispatch" clause.** Never re-ask per
chunk, and never offer to halt a fired run at that chunk's wave. A chunk gate the invocation does
NOT satisfy is one naming a different act — a cross-repo commit (per-session assent, obtained at
that dispatch) or an external-facing action. Does not chain into branch disposition (the PM-gated `/merging-to-main`). Rationale: wiki.

Executing a plan is restructure-then-dispatch: build the dispatch-gate graph, decompose into
per-chunk dispatches — parallel where gates allow, serial where they don't, default vehicle a
background Workflow. A serial chain is still N fresh
dispatches with EM-verify between, never one long-lived executor. No per-chunk reviewer gate —
code review is the emitted workflow's own review wave (every reviewer applies its own findings;
partitioned into file slices at or above `review-brightline-gate`), run once per plan after every
row has written, on every plan at every size. The EM never hand-dispatches a reviewer after the workflow returns. Tripwire: `CODE-REVIEW-IS-A-STAGE-OF-THE-EXECUTE-WORKFLOW`. **A chunk that
registers an op is verified with the registry-completeness tests, never the full suite**
(`execute-plan-residue.md` § Op-registering chunk). **EM-verify means the EM itself runs the chunk's
tests, never trusts an executor's pass claim**; "PASS (by inspection)" is not verification. A
host-dependent chunk's red is not a verdict until EM-verify's interpreter matches the canonical
gate env, not a bare `python3`. **A chunk
that ships a new helper/hook/injector is not done on green tests alone**; a mechanism with no
caller is never accepted as shipped. That check gates Phase 3's mark-complete and is re-checked in
Phase 4 before the stamp (`coordinator/docs/wiki/reviewer-pipeline/review-integration-doctrine.md`
§ An observable-outcome acceptance criterion is never satisfied by a tested pure function alone).
Dispatched executors are always Sonnet; self-execute only on a named token-economics carve-out.
Phase boundaries are not stop boundaries: ship Phase N green, dispatch N+1, no checkpoint offer.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill: invoking a skill requests the actions it performs, so a harness line permitting dispatch "unless the user requested it" is **satisfied here, not overridden**. Re-asking spends the context the dispatch protects. The rule dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

Firing the Phase 1.5/1.6 background Workflow is one of those dispatches; asking approval re-asks what invocation requested.

---

## Arguments

`$ARGUMENTS` is the plan document path. No path or file not found → report and stop.

---

## Phase 1: Load, Authorize, Review

1. Read the plan in full, then run `python3 "${CLAUDE_PLUGIN_ROOT:?plugin root unset}/lib/plan_scaffold_markers.py" <plan-path>`;
   exit 3 (`PLAN-SCAFFOLD-UNFILLED`) means the plan is an unfilled scaffold — report and stop.
2. Unless `/autonomous`: run `pickup-assemble brief <plan-path>` FIRST, before minting — it emits
   `gates.execution_stamp_match`, the check this step needs (the CLI has no `stamp-check` verb).
   Minting first erases the staleness signal. FRESH or STALE-bookkeeping → proceed **without
   re-stamping**. A business-fail of "carries no `execution_authorized_sha`" means nothing to
   compare yet → proceed. STALE-substantive surfaces the delta and STOPS. A body changed since
   approval (`approved_body_sha`, which a row added mid-run also moves) goes back through plan
   review (`coordinator:review` on the plan) — never re-mint over it; once re-reviewed,
   `review-exec-auth-stamp restamp` rebinds it. Tripwire: `AN-APPROVED-PLAN-WHOSE-BODY-CHANGED-IS-UNREVIEWED`.
   THEN mint the record from this invocation:
   `review-exec-auth-stamp authorize-invocation <plan-path> --typed-command /execute-plan
   [--utterance "<PM's verbatim words>"]`. Pass `--utterance` whenever the PM's invocation carries
   words; emit refuses a plan whose PM words resolve nowhere. On Git Bash,
   prefix the call with `MSYS_NO_PATHCONV=1` (or use PowerShell) — MSYS rewrites `/execute-plan`
   and the mint refuses. Under `/autonomous` the stamp is skipped; skip both legs.
   **`mise_prepped_*` is a different axis; neither it nor the quartet substitutes for the other.**
   This step writes only the quartet. Tripwire: `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.
2a. **Turn 3 by mode (the four-turn loop: sizing, plan, execute, workstream-complete).** In
   **pm** and **ceo** modes the execute decision is not a further PM ask: the stamp records
   `authorized by accepted sizing (mode=<mode>)`, citing the sizing path, and passes no
   `--utterance` — never the sizing's `pm_quote`, and never invented words. **hands-on** is
   unchanged: today's `--utterance` ask, using the PM's own execution words.
   **Chained.** When the engine publishes `plan_chain.run`, the chain driver runs Phase 1 to 1.6
   for a sizing-routed pm/ceo plan and records that stamp; the EM invokes /execute-plan there only
   to resume a halted chain. Absent the op, run it as written. Contract:
   `docs/wiki/em-operating-model/sizing-to-commit-chain-contract.md`.
   **A delegated run** mints with `--authorized-by-delegation <delegate>` and `--delegation-source <ref>`,
   the PM's standing words, if any, in `--standing-direction-quote`, and never `--utterance`. Tripwire:
   `A-DELEGATED-RUN-STAMPS-THE-DELEGATE-NOT-THE-PM`.
3. **Remaining-context gate** (skip under `/autonomous`): read this session's own remaining-context
   reading (the statusline's context-window percentage; harness-reported, not visible to the engine) before committing to same-session
   execution. LOW remaining context is the narrow carve-out; a fresh (picked-up)
   session is the default. Detail: wiki.

4. Resolve EM-resolvable concerns at EM altitude, not by surfacing them to the PM. A
   concern revealing the plan isn't executable → Phase 1.4.
5. Announce and continue.

---

## Phase 1.4: Executability Gate

Bounce to `/plan` on any of: an embedded decision gate ("evaluate X before continuing", "Phase 0
— investigate"); a fact-finding chunk with no fix-locus; an unpopulated downstream wave-map;
in-prose deferral of an EM-resolvable (not PM-altitude) decision; open questions gating whether
downstream chunks can be authored; an unbuilt external prerequisite with no landed commit/date.
A chunk with an irreversible external side effect (send, publish, mail, third-party call) naming no skip-if-already-delivered marker also bounces. Tripwire:
`A-FIRE-WITHOUT-A-SHIPPED-SIGNAL-RECHECK-REDELIVERS-AN-IRREVERSIBLE-CHUNK`.

Read the last two off the spine, not prose. A non-deferred open row with no `writes:` key IS an
unpopulated wave-map, whatever the plan body's prose says. For the external prerequisite, a row's
`external_gate` entries are where it is declared: `blocks: execution` uncleared bounces;
`blocks: ac-closure` does not — proceed, telling the PM at dispatch that the terminal state is `approved`, not `implemented`.
`plan-spine-check --for-execution <plan>` exiting 1 is the unpopulated-wave-map bounce; report its WIDTH line at dispatch.
An M+ plan whose `prime_exit_criterion` carries no `falsifier` block and no `falsifier_exemption`
bounces to `/plan` to dispatch `coordinator:exit-criterion-falsifier` — close-out refuses
`implemented` on it. Tripwire:
`AN-OWED-FALSIFIER-IS-CAUGHT-BEFORE-EXECUTION-NOT-AT-CLOSE-OUT`.
Signal catalog: wiki.

---

## Phase 1.5/1.6: Dispatch-Gate Graph and Wave-Map

**Roadmap-baton execution gate — check before claiming.** A plan executing a `blocked_by` roadmap
baton needs every blocker **coded**, not merely planned. Read it, never derive it —
`coordinator-invoke roadmap.plan_gate '{"subject":"<baton-id>","gate":"execution"}'` returns
`verdict.open` plus the blockers holding it shut. Shut → stop; the plan is written and waiting, the correct state. Tripwire: `A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`.

Claim the plan (`session-claim-cli claim-plan <slug> --for-execution`) before any gate-graph work
— a live peer holding it means reconcile with them first, never race. A live holder that has
formally handed off (relinquishment evidence, not mere liveness) → `take_over_claim`,
fail-loud without evidence; never a bare retry of `claim-plan`. **`--for-execution` is not
optional here**: it is what flips the plan to `status: executing`, and this step is its only
caller fleet-wide. (`coordinator-tripwires/plan-status-ladder.md`.)

Immediately after that claim, run `plan-completeness generate "$ARGUMENTS"`: a BASELINE SNAPSHOT at execution start, diffed against the Phase 4 run.

**Plan prose does not pick the vehicle.** A sentence forbidding fan-out, or prescribing
EM-sequenced chunk-at-a-time execution, is overridden: the vehicle follows from the classification
below, default a background Workflow; note the override in one line, do not ask. Only a prohibition
traceable to a genuine Workflow-inexpressible shape
(`coordinator/docs/wiki/em-operating-model/workflow-orchestration.md` § What qualifies as a carve-out) survives.
Tripwire: `A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`.

**Read each chunk pair's `gate_kind` off the `dispatch.emit` wave map — never classify by hand.** What each kind means for running a pair together:
- **File-write overlap** → gates authoring, no escape hatch — predecessor lands first.
- **Output/contract consumption** → both author concurrently if A's interface is pinned up front
  (verify at merge); no pinnable interface → predecessor-wave.
- **Runtime consumption** (B needs A's artifact to *exist and run*) → gates authoring, no escape.
- **Epistemic/premise** (A decides whether B's chunks should exist) → A ships alone in its own
  wave first; B isn't drafted until A's verdict lands.
- **Independent** → same wave, no gate.

A row carrying an uncleared `external_gate` entry with `blocks: execution` is unschedulable in any
wave: the gate is on another repo, so no pair-classification clears it.

**Cross-check the AC table against the chunk list before emitting.** An `## Acceptance Criteria`
row with no chunk citing it (frontmatter list, `covers:`, or body reference) is a silent gap:
walk every AC row, confirm a `## Tasks` row names it, and fix an uncovered AC in the plan before dispatching.

**A signature/param-removal chunk scoping only production handlers is the same gap**: its scope
must also name test fixture defs and call sites (`execute-plan-residue.md` § Signature/param-removal).

**A chunk whose deliverable is a static gate or sweep predicate** carries a brief that sorts every
case into PROVE-BAD, PROVE-GOOD or CANNOT-DECIDE and flags only PROVE-BAD; a first run of two dozen hits or more gets a hand-read sample before any fix wave. Tripwire:
`A-STATIC-GATE-BRIEF-MUST-SORT-EVERY-CASE-INTO-PROVE-BAD-PROVE-GOOD-OR-CANNOT-DECIDE`.

**Invoke `dispatch.emit` — don't derive the wave shape by hand and don't stop at deriving it.** It
reads the spine's `writes:`/`depends_on` and emits the ready-to-fire Workflow itself, each row's
`gate_kind`, `write_files`, and `agentType` already resolved and non-dispatchable rows filtered.

`NoWritesDeclaredError` means the spine is unpopulated — fix the plan, never hand-derive. Write
the emitted script to `<plan-basename>.workflow.mjs` next to the plan, never plan-body prose or a chat wave table. Emitted scripts and `.emitted.json` receipts are ephemeral: gitignored, never committed, pruned by `/distill`.

<!-- engine-gap: field=execute_plan.ses_fire_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

**Emit and dispatch are ONE action; the dispatch leg is not optional.** In an interactive
session the EM runs `emit-dispatch-workflow --plan <plan-path>` (settings-home launcher; resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`, PowerShell included). Before firing, register review targets (EM-only; the confined reviewers cannot apply findings without it):
`review-findings-ledger targets --from-plan <plan-path>`. Then
call `Workflow({scriptPath: "<emitted path>", args: {repoRoot: "<absolute repo root>"}})` in this
session, using the exact `fire with: Workflow(...)` line the emitter prints on stderr. An emitted script is not a delivered dispatch; emitting and stopping runs nothing.
**Recheck the shipped signal just before the fire:** re-read each dispatchable row's status, the
completion receipt, and the chunk's commit on disk. A row that shipped since the emit makes the
script stale: re-emit, never fire old bytes. Tripwire:
`A-FIRE-WITHOUT-A-SHIPPED-SIGNAL-RECHECK-REDELIVERS-AN-IRREVERSIBLE-CHUNK`.

**A row is rechecked at fire, not at emit.** The Workflow skips a row already `coded`; a row with an irreversible external side effect (memo, publish, push, third-party call)
carries a skip-if-delivered check in its brief, keyed on that effect's own receipt (wiki `execute-plan-residue.md` § Fire-time freshness). Tripwire: `A-ROW-IS-RECHECKED-AT-FIRE-NOT-AT-EMIT`.

**An emitted fire raises no permission prompt.** One that does was edited in
place (its `<script>.emitted.json` digest differs): `--restamp`, not a re-emit. Tripwire:
`AN-EMITTED-WORKFLOW-FIRES-WITHOUT-A-PROMPT-A-HAND-ROLLED-ONE-DOES-NOT`.

**`--fire` is the headless and cron path only** (`engine_fire.fire_workflow`; returns a run handle
whose `fire_id` `workflow.fire_status` re-reads); wrong wherever a session can call the tool.
Wiki: `execute-plan-residue.md` § Phase 1.5/1.6.

**There is no hand-dispatch fallback.** If the dispatch refuses — the `Workflow` call, or on the
headless path a named fire-leg refusal (`ScriptNotFoundError`, `PluginDirResolutionError`,
`ConcurrencyCapExceededError`, `ChildSpawnFailedError`) — report it and stop; hand-dispatching with the Agent tool is never the recovery, and a concurrency-cap refusal means wait. The emit itself refuses with
`DirtyWriteSetError` when a path in the dispatchable rows' `writes:` is dirty or untracked — commit or reconcile it with its owner and re-emit, never edit `writes:` to dodge it. Tripwire: A-DIRTY-PATH-IN-THE-WAVE-WRITE-SET-REFUSES-THE-EMIT.

**A fifth state: fired-then-died.** A handle with `log_size_bytes: 0` stalled past startup: report and stop.

**A sixth state: returned `incomplete`, nothing halted.** Not a resume: run `dispatch.terminal_commit`, then `emit-dispatch-workflow --plan <plan> --only-incomplete <task-output>` and fire. Never hand-dispatch them.

**A brief never asks an executor to commit** — its Commit Gate refuses.

Wave shape comes from the file-write graph, never the plan's section/theme structure. One dispatch
per chunk inside the script — never bundle serial chunks into one executor. Taxonomy and checks: wiki.

**No checkpoint prompt; scripted gates still hold.** The workflow never pauses to ask whether to
continue; a `phase()`'s deterministic gate MAY halt the run (`return { halted: ... }`, wiki:
`workflow-orchestration.md`), and a halted or edited phase resumes via `resumeFromRunId`.

**One emit per plan — a partial re-run resumes, it does not re-emit.** The emitted script carries
every open wave through review and the terminal test phase; the run's one commit
(`dispatch.terminal_commit`, below) follows the return. On a halt — a BLOCKed executor, a
review-wave BLOCKED/FAIL, or a rebuild verdict — recover with `Workflow({scriptPath, resumeFromRunId: <run>})`
in the same session; resume alone re-halts, since the refusal verdict is cached. **Edit the
halting phase's agent step first, and no earlier one** — fix what the refusal named — then
**re-stamp the receipt** (`block-workflow-foreign-emission.py` denies a fire whose bytes differ):
`emit-dispatch-workflow --restamp <script>` (refused unless the receipt names this session); then
resume. A second `emit-dispatch-workflow` narrows to a one-wave script (`read_spine` excludes
closed rows), so re-emit only when the spine changed. Tripwire:
`A-SECOND-EMIT-AFTER-A-PARTIAL-RUN-NARROWS-SILENTLY`.

**Watch with `Monitor`, never by hand-polling:** the run's `journal.jsonl` (completion, phase-boundary, failure, every terminal state).

**Completion — the driver's first act on return is the terminal commit, not a phase inside the workflow.** The
review wave runs inside the workflow; a Workflow never commits. The driver (the EM, or the chain driver on a chained run) runs `coordinator-invoke dispatch.terminal_commit` with `script_path` and
`task_output_path`, the task file carrying `next_action.params`: the run's ONE commit, carrying the
`Inline-Review:` trailer. `implemented` means done: a met terminal judge stamped it and Phase 4 steps 2.5 to 4 ran inside
it. Still `executing`: read the reason; treat the run as Phase-5-halted. That commit writes one
completion receipt per baton; the EM reads it, never writes one ([`completion-receipts.md`](../../docs/wiki/release-and-distribution/completion-receipts.md)).
See [`terminal-judge.md`](../../docs/wiki/reviewer-pipeline/terminal-judge.md). Tripwire:
`A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`.

Same turn: wake digest to the PM in **hands-on**/**pm** modes, at once in **ceo**; then fire
`coordinator:workstream-complete` (turn 4).

---

## Phase 2: Create Flight Recorder

TaskCreate: one task per plan phase/major task, added BENEATH the stage rows the sizing lobby
already opened (`skills/sizing/SKILL.md` § 4b); its session-goal task is already `in_progress`.
Entered without the lobby: open the recorder here, session goal plus phases, `in_progress` at once.
<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface (`ToolSearch("select:TaskCreate")` returns nothing)
→ fall back to `coordinator-tasks-mirror` for the same flight-recorder role; do not assume either
state without checking. When Task* is unavailable, dispatch the phases in order, waiting on each
completion notification — that is the ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

Executing a plan in another repo than the session's anchor → pass
`coordinator-tasks-mirror --repo-root <plan's repo>`; bare, the repo-identity gate refuses the write as a MISMATCH.

---

## Phase 3: Execute All Tasks

<!-- engine-gap: field=execute_plan.wave_boundary_gated_artifact_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

Default: execute every task in sequence without stopping to ask. Per task: write-ahead (mark
`In progress` on disk + TaskUpdate `in_progress`) → execute (follow the plan, fix routine errors,
move on) → **reachability gate** (task shipped a new helper/hook/injector? confirm a production
call site reaches it — caller-grep or traced entry point, never an import smoke-check — before
proceeding; unit-green alone does not clear this, per Phase 1 § EM-verify) → mark complete (on
disk + TaskUpdate `completed`) → proceed immediately, including across phase boundaries, same
session, same flight recorder.

Mid-dispatch decisions are EM decisions — pick, record a one-line rationale, continue; only the
Phase 5 list escalates. A residual (a missed site, a fix wider than the AC) needs a closed exit:
dispatch it, add a spine row for the Phase 4 harvest, `coordinator-queue-append --schema
bug-backlog|debt-backlog|improvement-queue`, or take it to the PM; a reason with no queue id, row, or commit behind it is not routed.

---

## Phase 4: Finalize and Report

**Precondition:** every wave-map chunk has landed, confirmed via the recovery triple; else return
to Phase 3. Steps 2.5 to 4 are the manual path, only when the terminal commit did not stamp.
Leg 1 alone yields candidates, never a verdict: corroborate against leg 2 or 3, plus a git log by chunk-id subject unscoped by path.

1. **Leg 1** — the engine op for this read:
   `chunk-commits <plan-path> <chunk-id>` (`ceremony.chunk_commits`) resolves the plan's add-commit, range-scopes to `<add-sha>..HEAD`, filters on the commit SUBJECT (never
   `--grep`, never a pathspec-scoped query, never a bare repo-wide grep: chunk ids restart at C1
   per plan). A `no_join_candidates`-shaped result is that contradiction, not proof the chunks
   didn't ship. Rationale: wiki residue § Phase 4 — Leg 1 negative-spec.
2. **Leg 2 — the Workflow's own resumable script**, persisted and resumable via
   `resumeFromRunId` (Phase 1 above).
3. **Leg 3 — the Task-list flight recorder** (Phase 2 above), persists through compaction by
   design.

**`close-out-and-stamp` reads no commit message at all.** The commit-subject/`Deliverable-Id`-trailer
join was deleted, not narrowed; do not restore it as an oversight. Two sha-ancestry evidence paths survive: a `disposition: coded` spine row's `disposition_ref`, and, for a pre-spine plan, its `## Dispatch Ledger` `committed <sha>` cells.

**The `## Tasks` spine is the only row family close-out reads.** Delivery evidence is the
falsifier delta on `prime_exit_criterion` — its verdict, not a row's ticked-or-open state, is what
discharges the plan. Tripwire: `AN-UNTICKED-AC-CELL-CARRIES-NO-INFORMATION`.

**Before any cleanup:** `coordinator-harvest-deferrals --plan "$ARGUMENTS"`, surfacing its
`"Queued N ..."` line even on `Queued 0`. A `defer` grouping approval (or legacy
`pm_approved: true`) is a claim of ratification the harvest selects on, not something this step
may stamp — closing a row mid-execution is a scope decision that needs the PM first.

**Commit sequence, two commits, never one — the resolve step below writes the plan, not a third
commit:**
1. Land the chunk work in your own scoped commit(s) — explicit pathspec, never `git add -A`. The
   `prepare-commit-msg` hook attaches the `Deliverable-Id:` trailer per
   `snippets/scoped-commit-route.md`; never hand-add it. Close-out does not read it.
2. Resolve each landed row's own `disposition_ref`, the only thing close-out counts:
   `plan-tasks-resolve --plan "$ARGUMENTS" --id <row> --coded <sha> --disposition-detail "<why>"`,
   per row, then close out. `missing_chunk_ids` at exit 0 over a range that provably holds every
   chunk SHA means unresolved rows — resolve and re-run, never rewrite shared history. Record the
   sha where the work actually landed: the anti-self-attestation gate cannot catch a row pointing
   at a peer's commit.
2.5. Run `plan-completeness status "$ARGUMENTS"` (never writes). Paste its raw rollup line into
   `exit_criterion_met.prose`, beside the baseline's rollup line. Any `CONTRADICTION: ` line
   carries verbatim into the close-out report; never stamp over it.
3. Re-run `prime_exit_criterion.falsifier.how` against `HEAD`, paste its raw output into
   `exit_criterion_met.falsifier_output`, and judge it against
   `prime_exit_criterion.falsifier.expected_when_true` — never against `baseline_output`. Record
   the verdict in `exit_criterion_met.falsifier_verdict` (`pass`/`fail`; a changed-but-non-matching
   output is `fail`); `exit_criterion_met.prose` ties it to the prime exit criterion.
   `fail` → `asserted: false`, Phase-5-halted, no stamp.
3.5. **Promote the falsifier, when it promotes.** An executable, deterministic falsifier graduates
   into the repo's test suite: `promotion: promoted` plus `promoted_to: <test path>`, or `partial`
   with the path the promoted portion landed at; already a standing test → `already-in-suite`, no
   `promoted_to`, the test named in `promotion_reason`. PROMOTION IS AN OUTCOME, NOT A GATE: a
   one-shot query, manual observation, or live measurement records `not-applicable` plus a reason.
3.6. **Adversarial criterion-only reader, M+ plans that went green first time only.** M+ per
   `sizing_object.estimate.tshirt` (never an S-lane spec-dispatch) AND
   every wave-map chunk landed without an executor BLOCKing — dispatch one reader that
   receives only the prime exit criterion statement and `HEAD`, and answers one question: does HEAD
   do this? A roster's judge stage (`coordinator:exit-criterion-judge`) is this
   reader; no second. **THE DENIAL LIST IS THE MECHANISM AND MUST BE EXPLICIT IN THE DISPATCH, not implied:**
   no plan body, no AC table, no chunk bodies, no run reports, no reviewer sidecars.
3.7. **Reachability re-check, before the stamp.** For any landed row that shipped a new
   helper/hook/injector, re-confirm at `HEAD` by caller-grep that the Phase 3 call site still
   reaches it. Unconfirmed → Phase-5-halted, no stamp; `close-out-and-stamp` does not check this.
3.8. **`review-stamp mint`, owed by hand only when `dispatch.terminal_commit` did not report
   `review_stamp: minted`.** `review-stamp mint --plan "$ARGUMENTS" --build-test <wake digest's
   tests.sidecar>` (not required when the spine wrote nothing testable and the criterion is
   `met`). It resolves the terminal commit via `Inline-Review:` and writes `review_stamp:`. Refusal
   (including a `refused` from `terminal_commit`) — no stamp-able review, no build/test record,
   `delivery.verdict == FAIL`, `unresolved > 0`, a confinement violation, or non-empty
   `foreign_claims[]` — is Phase-5-halted: report it; skip step 4. Tripwire:
   `A-PLAN-REACHES-IMPLEMENTED-ONLY-THROUGH-A-REVIEW-STAMP`.
   **A `delivery.verdict == FAIL` since repaired by fix-forward commits** is cleared only by
   `emit-dispatch-workflow --reverify-delivery`, never a hand-authored record
   (`execute-plan-residue.md` § Reverify a delivery FAIL). Re-run 3.8, then step 4.
4. `close-out-and-stamp "$ARGUMENTS"` — stamps `status: implemented` and commits the plan path
   (full-plan-shipped), or reports remaining uncommitted chunks and skips the stamp
   (Phase-5-halted). The engine refuses `implemented` without a `review_stamp` (step 3.8).

**Offer, stamp-aware, never parroted.** Whether step 4 stamped `implemented` decides it.
Stamped → offer `/workstream-complete`, noting `/merging-to-main`/`/workday-complete` ship it.
Unstamped for **any** reason (Phase 5 halt, open spine row, a leg unmet in another repo) → offer
resolve-and-resume, `/handoff`, or commit-and-stop. Never auto-invoke
any of those or `coordinator:finishing-a-development-branch`.
Tripwire: `AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`.

**A cross-repo leg names its failing conjunct, not its repo** (*undeclared*, *unaddressed*, *unanswered*) per `coordinator/snippets/cross-repo-block-exchange.md`. Tripwire:
`A-SENT-MEMO-IS-NOT-AN-EXCHANGE`.

---

## Phase 5: When to Stop — PM-Only Emergencies

The default is complete the plan. Stop only for: **external trust surface change**
(user-visible behavior, privacy, security boundary, billing/pricing/onboarding, or any
externally-observable contract the plan didn't call out); **plan-invalidating substrate change**
(disk state changed since drafting in a way that makes the plan structurally wrong — bounce to
`/plan`); **scope explosion** (≥3× anticipated size, no 5-15min-chunk decomposition articulable
for the remainder — route back to `/plan`); **unauthorized irreversible action required**
(destructive op, force-push, cross-repo write to a sibling's code, credential/cookie write, or
anything gated by `~/.claude/CLAUDE.md` § Executing actions with care); **discovery the plan
would ship something not authorized** (approved on premise X, execution reveals it would also do Y, not a mechanical consequence of X).

Not on the list (EM decisions): accumulating patches, ambiguity, structural verification failure
(`/systematic-debugging`), routine fixable errors, minor judgment calls, wanting to check in.
Record `Tried:/Failed:` in the plan doc and `metadata.tried_and_abandoned`; surface a recommendation, not a question.

**Usage-limit advisory** (a pause, not a PM emergency): dispatch nothing new, let in-flight agents
land, commit scoped, write the handoff with the reset time in its next steps, stop.
`A-DRIVER-PAST-ITS-USAGE-THRESHOLD-FIRES-NOTHING-NEW` —
`coordinator/docs/wiki/skills-corpus/usage-limit-pause.md`.

---

## Relationship to Other Commands

Default upstream entry is `/handoff` + `/pickup`; enrichment has already happened upstream.
`/review-code` stays an optional ad-hoc pass — the plan's review is the execute-review stages
inside the fired workflow (Phase 1.5/1.6).
`coordinator:workstream-complete` is offered, never auto-invoked, in Phase 4;
`coordinator:finishing-a-development-branch` is reached via `/merging-to-main`. Failure modes: wiki.
