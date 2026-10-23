---
name: execute-plan
description: Execute a PM-approved plan via per-chunk executor waves.
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — End-to-End Plan Execution

Run a PM-approved plan end-to-end without stopping for permission between tasks. Fire with context, own the swimlanes (`THE-EM-TIME-AND-COST-SPENT-IS-A-RED-FLAG`). Invoking `/execute-plan` on a plan IS the PM's authorizing act; frontmatter
`execution_authorized_at` records it; it is no precondition. **It also
satisfies a chunk body's own "needs PM assent at execution dispatch" clause.** Never re-ask per
chunk or offer to halt a fired run at its wave. A chunk gate the invocation does
NOT satisfy names another act — a cross-repo commit (per-session assent, obtained at
that dispatch) or an external-facing action. No chain into branch disposition (the PM-gated `/merging-to-main`).

Executing a plan is restructure-then-dispatch: build the dispatch-gate graph, decompose into
per-chunk dispatches — parallel where gates allow, serial where not, via a background Workflow. A serial chain is N fresh
dispatches with EM-verify between. No per-chunk reviewer gate —
code review is the emitted workflow's own review (reviewers apply their own findings),
per executor group as rows land (`review-roster-fragment.md` § Stages), at every size. The EM never hand-dispatches a reviewer. Tripwire: `CODE-REVIEW-IS-A-STAGE-OF-THE-EXECUTE-WORKFLOW`. **A chunk that
registers an op is verified with the registry-completeness tests, never the full suite**
(`execute-plan-residue.md` § Op-registering chunk). **EM-verify means the EM itself runs the chunk's
tests (scoped paths), never trusts an executor's pass claim**; "PASS (by inspection)" is not verification. A
host-dependent chunk's red is not a verdict until EM-verify's interpreter matches the canonical
gate env. **A chunk that ships a new helper/hook/injector is not done on
green tests alone**; a mechanism with no caller never counts as shipped. That check gates
Phase 3's mark-complete and is re-checked in Phase 4 before the stamp (`coordinator/docs/wiki/reviewer-pipeline/review-integration-doctrine.md`).
Dispatched executors are always Sonnet; self-execute only on a named token-economics carve-out.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## Arguments

`$ARGUMENTS` is the plan path. No path or file not found → report and stop.

---

## Phase 1: Load, Authorize, Review

1. Read the plan in full, then run `python3 "${CLAUDE_PLUGIN_ROOT:?plugin root unset}/lib/plan_scaffold_markers.py" <plan-path>`;
   exit 3 (`PLAN-SCAFFOLD-UNFILLED`) means the plan is an unfilled scaffold — report and stop.
2. Unless `/autonomous`: run `pickup-assemble brief <plan-path>` FIRST, before minting (minting erases the signal) — it emits
   `gates.execution_stamp_match`. FRESH, STALE-bookkeeping, or a "carries no `execution_authorized_sha`" fail → proceed **without re-stamping**. STALE-substantive surfaces the delta and STOPS. A body changed since
   approval (`approved_body_sha`, which a row added mid-run also moves) goes back through plan
   review (`coordinator:review`) — never re-mint over it; once re-reviewed,
   `review-exec-auth-stamp restamp` rebinds it. Tripwire: `AN-APPROVED-PLAN-WHOSE-BODY-CHANGED-IS-UNREVIEWED`.
   THEN mint the record from this invocation:
   `review-exec-auth-stamp authorize-invocation <plan-path> --typed-command /execute-plan
   [--utterance "<PM's verbatim words>"]`. Hands-on, `--utterance` is required when `pm-brief render <plan>`
   resolves no PM brief, sizing pm_verbatims or baton (`A-WORDLESS-TYPED-COMMAND-MINT-IS-NOT-A-PM-BRIEF`). On Git Bash,
   prefix with `MSYS_NO_PATHCONV=1` (or PowerShell). Under `/autonomous`, skip the brief and mint as a delegated run (2a). A body changed before any mint recovers after plan review via `restamp --authorized-by-delegation <d> --delegation-source <ref>`.
   `mise_prepped_*` is not the quartet. Tripwire: `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.
2a. **By mode.** An `engine-ask` run never reaches this skill. In
   **pm** and **ceo** modes the stamp records
   `authorized by accepted sizing (mode=<mode>)`, citing the sizing path, and passes no
   `--utterance` — never the sizing's `pm_quote`, never invented words. **hands-on**: step 2.
   **A delegated run** mints with `--authorized-by-delegation <delegate>` and `--delegation-source <ref>`,
   the PM's standing words, if any, in `--standing-direction-quote`, and never `--utterance`. Tripwire:
   `A-DELEGATED-RUN-STAMPS-THE-DELEGATE-NOT-THE-PM`.
3. **Remaining-context gate** (skip under `/autonomous`): read the statusline's context-window percentage before committing to same-session
   execution. A fresh (picked-up) session is the default; LOW context is the carve-out.
3a. **Re-probe every cited canvas, in the main loop.** For each cited `harvest/harvest.json`, read
   the artifact version and comment threads, then run the engine harvest op's probe mode. A dispatch-leg
   refusal at fire is final for that canvas until re-harvested and `SETTLED.md` updated. An unreadable canvas is reported; the run does not wait on it. Executors read the record, never the canvas.
   Recipe: `snippets/design-canvas-recipe.md`; contract: `coordinator/docs/wiki/schema-and-validation-contracts/canvas-harvest-record.md`.
4. Resolve EM-resolvable concerns yourself; a concern revealing the plan isn't executable → Phase 1.4. Announce and continue.

---

## Phase 1.4: Executability Gate

Bounce to `/plan` on any of: an embedded decision gate ("evaluate X before continuing"); a fact-finding chunk with no fix-locus; an unpopulated downstream wave-map;
in-prose deferral of an EM-resolvable decision; open questions gating whether
downstream chunks can be authored; an unbuilt external prerequisite with no landed commit/date;
a chunk with an irreversible external side effect naming no skip-if-already-delivered marker. Tripwire:
`A-FIRE-WITHOUT-A-SHIPPED-SIGNAL-RECHECK-REDELIVERS-AN-IRREVERSIBLE-CHUNK`.

Read the last two off the spine. A non-deferred open row with no `writes:` key IS an
unpopulated wave-map (`plan-spine-check --for-execution <plan>` exiting 1; report its WIDTH line at dispatch). A row's `external_gate`: `blocks: execution` uncleared bounces;
`blocks: ac-closure` does not — proceed, telling the PM at dispatch the terminal state is `approved`, not `implemented`.
An M plan whose `prime_exit_criterion` carries no `falsifier` block and no `falsifier_exemption`
bounces to `/plan` to dispatch `coordinator:exit-criterion-falsifier`. Tripwire:
`AN-OWED-FALSIFIER-IS-CAUGHT-BEFORE-EXECUTION-NOT-AT-CLOSE-OUT`.

---

## Phase 1.5/1.6: Dispatch-Gate Graph and Wave-Map

**Roadmap-baton execution gate — check before claiming.** A plan executing a `blocked_by` roadmap
baton needs every blocker **coded**, not just planned. Read it, never derive it:
`coordinator-invoke roadmap.plan_gate '{"subject":"<baton-id>","gate":"execution"}'` returns
`verdict.open` plus the blockers holding it shut. Shut → stop; a written, waiting plan is the correct state. Tripwire: `A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`.

Claim the plan (`session-claim-cli claim-plan <slug> --for-execution`) before any gate-graph work;
a live peer holding it means reconcile with them first, never race. A live holder that has
formally handed off (relinquishment evidence, not liveness) → `take_over_claim`; never retry `claim-plan` bare. **`--for-execution` is
mandatory**: it flips the plan to `status: executing`, and this step is its only caller.
After the claim, run `plan-completeness generate "$ARGUMENTS"` (the BASELINE SNAPSHOT, diffed in Phase 4).

**Plan prose does not pick the vehicle.** A sentence forbidding fan-out or prescribing
EM-sequenced chunk-at-a-time execution is overridden by the classification below (default a
background Workflow); note the override in one line, do not ask. Only a prohibition traceable to a Workflow-inexpressible shape
(`coordinator/docs/wiki/em-operating-model/workflow-orchestration.md` § What qualifies as a carve-out) survives.
Tripwire: `A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`.

**Read each pair's `gate_kind` off the `dispatch.emit` wave map — never classify by hand:**
- **File-write overlap** → gates authoring, no escape hatch — predecessor lands first.
- **Output/contract consumption** → concurrent if A's interface is pinned up front (verify at merge); else predecessor-wave.
- **Runtime consumption** (B needs A's artifact to *exist and run*) → gates authoring, no escape.
- **Epistemic/premise** (A decides whether B's chunks should exist) → A ships alone first.
- **Independent** → same wave, no gate.

An uncleared `external_gate` `blocks: execution` row is unschedulable; its owner
must be live and its `memo:` sent (`A-EXTERNAL-OWNER-IS-LIVE-AND-ITS-MEMO-IS-SENT`).

**Cross-check the AC table against the chunk list before emitting.** An `## Acceptance Criteria`
row with no chunk citing it (`covers:` or body reference) is a silent gap:
fix an uncovered AC in the plan before dispatching.

**A signature/param-removal chunk scoping only production handlers is the same gap**: its scope
must name test fixture defs and call sites (`execute-plan-residue.md` § Signature/param-removal).

**A static-gate or sweep-predicate chunk** carries a brief sorting every
case into PROVE-BAD, PROVE-GOOD or CANNOT-DECIDE, flagging only PROVE-BAD; a first run of two dozen hits or more gets a hand-read sample before any fix wave. Tripwire:
`A-STATIC-GATE-BRIEF-MUST-SORT-EVERY-CASE-INTO-PROVE-BAD-PROVE-GOOD-OR-CANNOT-DECIDE`.

**Invoke `dispatch.emit` — never derive the wave shape by hand.** It
reads the spine's `writes:`/`depends_on` and emits the ready-to-fire Workflow with each row's
`gate_kind`, `write_files` and `agentType` resolved.

`NoWritesDeclaredError` means an unpopulated spine — fix the plan, never hand-derive. Write
the emitted script to `<plan-basename>.workflow.mjs` next to the plan; scripts and `.emitted.json` receipts are never committed.

<!-- engine-gap: field=execute_plan.ses_fire_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

**Emit and dispatch are ONE action.** The EM runs `emit-dispatch-workflow --plan <plan-path>` (settings-home launcher; resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`, PowerShell included). Before firing, register review targets (EM-only):
`review-findings-ledger targets --from-plan <plan-path>`. Then
call `Workflow({scriptPath: "<emitted path>", args: {repoRoot: "<absolute repo root>"}})` in this
session (the `fire with:` line the emitter prints on stderr).
**Recheck the shipped signal just before the fire:** re-read each dispatchable row's status, the
completion receipt, and the chunk's commit. A row shipped since the emit makes the
script stale: re-emit.

**Emit prints "exceeds the per-workflow cap"** → fire its manifest's staged siblings: wiki `A-PLAN-WIDER-THAN-THE-WORKFLOW-CAP-FIRES-AS-STAGED-SIBLINGS`.

**A row is rechecked at fire, not at emit.** The Workflow skips a row already `coded`; an irreversible-side-effect row
carries a skip-if-delivered check (wiki `execute-plan-residue.md` § Fire-time freshness). Tripwire: `A-ROW-IS-RECHECKED-AT-FIRE-NOT-AT-EMIT`.

**An emitted fire raises no permission prompt.** One that does was edited in
place: `--restamp`, not re-emit. Tripwire:
`AN-EMITTED-WORKFLOW-FIRES-WITHOUT-A-PROMPT-A-HAND-ROLLED-ONE-DOES-NOT`.

**`--fire` is the headless and cron path only**; wrong wherever a session can call the tool.
Wiki: `execute-plan-residue.md` § Phase 1.5/1.6.

**No hand-dispatch fallback.** If the dispatch refuses — the `Workflow` call, or on the
headless path a named fire-leg refusal (`ScriptNotFoundError`, `PluginDirResolutionError`,
`ConcurrencyCapExceededError`, `ChildSpawnFailedError`) — report and stop; hand-dispatching with the Agent tool is never the recovery; a concurrency-cap refusal means wait. The emit refuses with
`DirtyWriteSetError` when a `writes:` path is dirty or untracked — reconcile it with its owner and re-emit; never edit `writes:` to dodge it. Tripwire: A-DIRTY-PATH-IN-THE-WAVE-WRITE-SET-REFUSES-THE-EMIT.

**A fifth state: fired-then-died.** A handle with `log_size_bytes: 0` stalled past startup: report and stop.

**A sixth state: returned `incomplete`, nothing halted.** Not a resume. Run `dispatch.land_run`, then `emit-dispatch-workflow --plan <plan> --only-incomplete <task-output>` and fire; never hand-dispatch. A row partial only on a break outside its files is re-graded by `land_run`; any other is re-verified (`--reverify-delivery <run-record>`, fire, `reverify-delivery record --run-record <that same run-record>`, never the `.emitted.json`). Hand-committing its files refuses the stamp.

**A brief never asks an executor to commit** and never dictates code: it carries intent, the PM verbatims and constraints (wiki `dispatch-briefing.md` § Field rules).

Wave shape comes from the file-write graph, never the plan's section structure; one dispatch per chunk.

**No checkpoint prompt; scripted gates still hold.** The workflow never pauses to ask; a `phase()`'s deterministic gate MAY halt the run, and a halted or edited phase resumes via `resumeFromRunId`.

**One emit per plan — a partial re-run resumes, never re-emits.** On a halt (a BLOCKed executor, review-wave BLOCKED/FAIL, or rebuild verdict) recover with `Workflow({scriptPath, resumeFromRunId: <run>})`
in the same session; resume alone re-halts (the refusal verdict is cached). **Edit the
halting phase's agent step first, and no earlier one**, then
**re-stamp the receipt**: `emit-dispatch-workflow --restamp <script>` (refused unless the receipt names this session); then
resume. A second `emit-dispatch-workflow` narrows to a one-wave script; re-emit only when the spine changed. Tripwire:
`A-SECOND-EMIT-AFTER-A-PARTIAL-RUN-NARROWS-SILENTLY`.

**No watching:** the completion notification is the wake; never `Monitor` or poll.

**Completion — the driver's first act on return is the terminal commit, not a phase inside the workflow.** The
review wave runs inside the workflow; nothing commits mid-run. The driver runs `coordinator-invoke dispatch.land_run` with `script_path` and
`task_output_path`, the task file carrying `next_action.params` (script gone: `plan_path` and `run_id`): the run's ONE commit, carrying the
`Inline-Review:` trailer. `implemented` means a met terminal verdict stamped it and Phase 4 steps 2.5 to 4 ran inside
it. Still `executing`: read the reason; Phase-5-halted. That commit writes one
completion receipt per baton; the EM reads it, never writes it ([`completion-receipts.md`](../../docs/wiki/release-and-distribution/completion-receipts.md)).
See [`terminal-judge.md`](../../docs/wiki/reviewer-pipeline/terminal-judge.md). Tripwire:
`A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`.

Same turn: wake digest to the PM (**hands-on**/**pm**; at once in **ceo**); then fire
`coordinator:workstream-complete`.

---

## Phase 2: Create Flight Recorder

TaskCreate: one task per plan phase/major task, BENEATH the stage rows the sizing lobby
opened (`skills/sizing/SKILL.md` § 4b). Without the lobby: open the recorder here, session goal plus phases, `in_progress` at once.
<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface (`ToolSearch("select:TaskCreate")` returns nothing)
→ fall back to `coordinator-tasks-mirror` for the same flight-recorder role; do not assume either
state without checking. When Task* is unavailable, dispatch the phases in order, waiting on each
completion notification — that is the ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

A plan in another repo than the session's anchor → pass
`coordinator-tasks-mirror --repo-root <plan's repo>`.

---

## Phase 3: Execute All Tasks

<!-- engine-gap: field=execute_plan.wave_boundary_gated_artifact_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

Execute every task in sequence without stopping to ask. Per task: write-ahead (mark
`In progress` on disk + TaskUpdate `in_progress`) → execute (fix routine errors)
→ **reachability gate** (new entry point? confirm a production call site: caller-grep or traced entry, never an import smoke-check; the judge re-checks via `review.reachability`, wiki `judge-reachability-check`) → mark complete (on disk + TaskUpdate `completed`) → proceed
immediately, across phase boundaries.

Phase boundaries are not stop boundaries: ship Phase N green, dispatch N+1. Mid-dispatch decisions are the EM's — pick, note one line, continue; only the
Phase 5 list escalates. A residual needs a closed exit: dispatch it, add a spine row, `coordinator-queue-append --schema
bug-backlog|debt-backlog|improvement-queue`, or take it to the PM; a reason with no queue id, row, or commit is not routed.

---

## Phase 4: Finalize and Report

**At L and above the run's ledger checker is the close**, replacing plan-reviewer, falsifier and
integrity review, both judges and delivery-verifier: none runs beside or after it, and steps 3 to
3.8 apply below L only.

**Precondition:** every wave-map chunk has landed (recovery triple); else return
to Phase 3. Steps 2.5 to 4: manual path, only if the terminal commit did not stamp.
Leg 1 alone yields candidates, never a verdict: corroborate against leg 2 or 3, plus a git log by chunk-id subject unscoped by path.

1. **Leg 1** — the engine op:
   `chunk-commits <plan-path> <chunk-id>` (`ceremony.chunk_commits`) scopes to the plan's add-commit range AND its `Checkpoint-Plan:` trailer, filtering on the commit SUBJECT (never
   `--grep`, a pathspec-scoped query, or a bare grep: chunk ids restart at C1). A `no_join_candidates`-shaped result does not prove the chunks didn't ship.
2. **Leg 2 — the Workflow's own script**, persisted and resumable via
   `resumeFromRunId` (Phase 1).
3. **Leg 3 — the Task-list flight recorder** (Phase 2), which persists through compaction.

**`close-out-and-stamp` reads no commit message at all.** The commit-subject/`Deliverable-Id`-trailer
join was deleted, not narrowed; do not restore it as an oversight. Two sha-ancestry paths survive: a `disposition: coded` row's `disposition_ref`, and, for a pre-spine plan, its `## Dispatch Ledger` `committed <sha>` cells.

**The `## Tasks` spine is the only row family close-out reads.** The falsifier verdict on
`prime_exit_criterion`, not a row's ticked state, discharges the plan. Tripwire: `AN-UNTICKED-AC-CELL-CARRIES-NO-INFORMATION`.

**Before any cleanup:** `coordinator-harvest-deferrals --plan "$ARGUMENTS"`, surfacing its
`"Queued N ..."` line even on `Queued 0`. A `defer` grouping approval (or legacy
`pm_approved: true`) is a ratification claim the harvest selects on; this step never stamps it
(closing a row mid-execution is a scope decision for the PM).

**Commit sequence, two commits, never one:**
1. Land the chunk work in your own scoped commit(s) — explicit pathspec, never `git add -A`. The
   `prepare-commit-msg` hook attaches the `Deliverable-Id:` trailer (`snippets/scoped-commit-route.md`); never hand-add it.
2. Resolve each landed row's `disposition_ref`, the only thing close-out counts:
   `plan-tasks-resolve --plan "$ARGUMENTS" --id <row> --coded <sha> --disposition-detail "<why>"`,
   then close out. `missing_chunk_ids` at exit 0 over a range that provably holds every chunk SHA means unresolved rows: resolve and re-run, never rewrite shared history. Record the
   sha where the work actually landed.
2.5. Run `plan-completeness status "$ARGUMENTS"` (never writes). Paste its raw rollup line into
   `exit_criterion_met.prose`, beside the baseline's. A `CONTRADICTION: ` line
   carries verbatim into the close-out report; never stamp over it.
3. Re-run `prime_exit_criterion.falsifier.how` against `HEAD`, paste its raw output into
   `exit_criterion_met.falsifier_output`, and judge it against
   `prime_exit_criterion.falsifier.expected_when_true` — never against `baseline_output`. Record
   the verdict in `exit_criterion_met.falsifier_verdict` (`pass`/`fail`; a changed-but-non-matching
   output is `fail`); the gate refuses the
   stamp unless it is `pass`; `exit_criterion_met.prose` ties it to the prime criterion.
   `fail` → `asserted: false`, Phase-5-halted, no stamp.
3.4. **Bounded EM verification.** Verify a DONE executor by its report plus the one step-3 falsifier run; no EM probe scripts or suite re-runs, gaps go to `coordinator:test-runner`. `AN-EM-RE-VERIFIES-WHAT-AN-EXECUTOR-ALREADY-VALIDATED`.
3.5. **Promote the falsifier, when it promotes.** An executable, deterministic falsifier graduates into the suite: `promotion: promoted` plus `promoted_to: <test path>` (`partial`: the path of the promoted portion); already a standing test → `already-in-suite`, no `promoted_to`, test named in `promotion_reason`. PROMOTION IS AN OUTCOME, NOT A GATE: a one-shot query or manual observation records `not-applicable` plus a reason.
3.6. **Adversarial criterion-only reader, M plans that went green first time only.** M per
   `sizing_object.estimate.tshirt` AND no executor BLOCKed — dispatch one reader given the prime exit criterion, the plan, and `HEAD`: does HEAD
   do this? A roster's judge stage (`coordinator:exit-criterion-judge`) is this reader; no second. **THE DENIAL LIST IS THE MECHANISM AND MUST BE EXPLICIT IN THE DISPATCH:**
   no agent's account of the run: no run reports, reviewer sidecars or executor output.
3.7. **Reachability re-check, before the stamp.** The judge's `reachability` block (`review.reachability`, wiki `judge-reachability-check`) is the re-check; unreachable is its not_met. No block: caller-grep at `HEAD`. Unconfirmed → Phase-5-halted, no stamp.
3.8. **`review-stamp mint`, by hand only when `dispatch.land_run` did not report
   `review_stamp: minted`:** `review-stamp mint --plan "$ARGUMENTS" --build-test <wake digest's
   tests.sidecar>` (not required when the spine wrote nothing testable and the criterion is `met`). Any refusal is Phase-5-halted: report, skip step 4. Tripwire:
   `A-PLAN-REACHES-IMPLEMENTED-ONLY-THROUGH-A-REVIEW-STAMP`.
   A `delivery.verdict == FAIL` repaired by fix-forward commits is cleared only by
   `emit-dispatch-workflow --reverify-delivery` (`execute-plan-residue.md` § Reverify a delivery FAIL). Re-run 3.8, then step 4.
4. `close-out-and-stamp "$ARGUMENTS"` stamps `status: implemented` and commits the plan path
   (full-plan-shipped), or reports remaining uncommitted chunks and skips the stamp
   (Phase-5-halted). The engine refuses `implemented` without a `review_stamp` (step 3.8).

**Offer, stamp-aware.** Stamped `implemented` → offer `/workstream-complete`, noting `/merging-to-main`/`/workday-complete` ship it.
Unstamped for **any** reason → offer
resolve-and-resume, `/handoff`, or commit-and-stop. Never auto-invoke these or `coordinator:finishing-a-development-branch`.
Tripwire: `AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`.

**A cross-repo leg names its failing conjunct, not its repo** (*undeclared*, *unaddressed*, *unanswered*), per `coordinator/snippets/cross-repo-block-exchange.md`. Tripwire:
`A-SENT-MEMO-IS-NOT-AN-EXCHANGE`.

---

## Phase 5: When to Stop — PM-Only Emergencies

Complete the plan. Stop only for: **external trust surface change**
(user-visible behavior, privacy, security boundary, billing/pricing/onboarding, or any
externally-observable contract the plan didn't call out); **plan-invalidating substrate change**
(disk state changed since drafting — bounce to `/plan`); **scope explosion** (≥3× anticipated size, no 5-15min-chunk decomposition for the
remainder — route back to `/plan`); **unauthorized irreversible action required**
(destructive op, force-push, cross-repo write to a sibling's code, credential/cookie write, or
anything gated by `~/.claude/CLAUDE.md` § Executing actions with care); **discovery the plan
would ship something not authorized** (approved on premise X; execution reveals it also does Y, not a mechanical consequence of X).

EM decisions, not on the list: accumulating patches, ambiguity, structural verification failure
(`/systematic-debugging`), routine errors, minor judgment calls, wanting to check in.
Record `Tried:/Failed:` in the plan doc and `metadata.tried_and_abandoned`; surface a recommendation, not a question.

**Usage-limit advisory** (a pause, no PM emergency): dispatch nothing new, let in-flight agents
land, commit scoped, write the handoff with the reset time, stop.
`A-DRIVER-PAST-ITS-USAGE-THRESHOLD-FIRES-NOTHING-NEW` —
`coordinator/docs/wiki/skills-corpus/usage-limit-pause.md`.

---

## Relationship to Other Commands

Upstream entry is `/handoff` + `/pickup`. `/review-code` is an optional ad-hoc pass; the plan's review is the fired workflow's.
`coordinator:workstream-complete` is offered, never auto-invoked;
`coordinator:finishing-a-development-branch` is reached via `/merging-to-main`.
