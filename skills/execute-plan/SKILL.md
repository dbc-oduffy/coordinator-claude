---
name: execute-plan
description: Execute a PM-approved plan via per-chunk executor waves.
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — End-to-End Plan Execution

Run a PM-approved plan end-to-end without stopping for permission between tasks. Invoking `/execute-plan` on a plan IS the PM's authorizing act; frontmatter
`execution_authorized_at` records that act; it is no precondition. **It also
satisfies a chunk body's own "needs PM assent at execution dispatch" clause.** Never re-ask per
chunk or offer to halt a fired run at that chunk's wave. A chunk gate the invocation does
NOT satisfy names another act — a cross-repo commit (per-session assent, obtained at
that dispatch) or an external-facing action. No chain into branch disposition (the PM-gated `/merging-to-main`). Rationale: wiki.

Executing a plan is restructure-then-dispatch: build the dispatch-gate graph, decompose into
per-chunk dispatches — parallel where gates allow, serial where not, default vehicle a background Workflow. A serial chain is N fresh
dispatches with EM-verify between, never one long-lived executor. No per-chunk reviewer gate —
code review is the emitted workflow's own review wave (every reviewer applies its own findings;
partitioned into file slices at or above `review-brightline-gate`), run once per plan after every
row has written, at every size. The EM never hand-dispatches a reviewer afterward. Tripwire: `CODE-REVIEW-IS-A-STAGE-OF-THE-EXECUTE-WORKFLOW`. **A chunk that
registers an op is verified with the registry-completeness tests, never the full suite**
(`execute-plan-residue.md` § Op-registering chunk). **EM-verify means the EM itself runs the chunk's
tests (scoped paths), never trusts an executor's pass claim**; "PASS (by inspection)" is not verification. A
host-dependent chunk's red is not a verdict until EM-verify's interpreter matches the canonical
gate env, not a bare `python3`. **A chunk that ships a new helper/hook/injector is not done on
green tests alone**; a mechanism with no caller never counts as shipped. That check gates
Phase 3's mark-complete and is re-checked in Phase 4 before the stamp (`coordinator/docs/wiki/reviewer-pipeline/review-integration-doctrine.md`
§ An observable-outcome acceptance criterion is never satisfied by a tested pure function alone).
Dispatched executors are always Sonnet; self-execute only on a named token-economics carve-out.
Phase boundaries are not stop boundaries: ship Phase N green, dispatch N+1.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

Firing the Phase 1.5/1.6 background Workflow is one of those dispatches.

---

## Arguments

`$ARGUMENTS` is the plan document path. No path or file not found → report and stop.

---

## Phase 1: Load, Authorize, Review

1. Read the plan in full, then run `python3 "${CLAUDE_PLUGIN_ROOT:?plugin root unset}/lib/plan_scaffold_markers.py" <plan-path>`;
   exit 3 (`PLAN-SCAFFOLD-UNFILLED`) means the plan is an unfilled scaffold — report and stop.
2. Unless `/autonomous`: run `pickup-assemble brief <plan-path>` FIRST, before minting — it emits
   `gates.execution_stamp_match`, the check this step needs (no `stamp-check` verb exists). Minting first erases the staleness signal. FRESH, STALE-bookkeeping, or a business-fail of
   "carries no `execution_authorized_sha`" (nothing to compare yet) → proceed **without re-stamping**. STALE-substantive surfaces the delta and STOPS. A body changed since
   approval (`approved_body_sha`, which a row added mid-run also moves) goes back through plan
   review (`coordinator:review`) — never re-mint over it; once re-reviewed,
   `review-exec-auth-stamp restamp` rebinds it. Tripwire: `AN-APPROVED-PLAN-WHOSE-BODY-CHANGED-IS-UNREVIEWED`.
   THEN mint the record from this invocation:
   `review-exec-auth-stamp authorize-invocation <plan-path> --typed-command /execute-plan
   [--utterance "<PM's verbatim words>"]`. Pass `--utterance` whenever the PM's invocation carries
   words; emit refuses a plan whose PM words resolve nowhere. On Git Bash,
   prefix the call with `MSYS_NO_PATHCONV=1` (or use PowerShell): MSYS rewrites `/execute-plan`. Under `/autonomous`, skip the brief and mint as a delegated run (2a) before the claim, never `--typed-command` (a keystroke the PM never made). A body changed before any mint recovers, after plan review, via `restamp --authorized-by-delegation <d> --delegation-source <ref>`.
   **`mise_prepped_*` is a different axis; neither substitutes for the quartet.** This step writes only the quartet. Tripwire: `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.
2a. **Turn 3 by mode (the four-turn loop: sizing, plan, execute, workstream-complete).** In
   **pm** and **ceo** modes the execute decision is not a further PM ask: the stamp records
   `authorized by accepted sizing (mode=<mode>)`, citing the sizing path, and passes no
   `--utterance` — never the sizing's `pm_quote`, and never invented words. **hands-on** is
   unchanged: the `--utterance` ask, using the PM's execution words.
   **Chained.** Only an opt-in `emit-wave-fire --chain` fire (headless, warns) hands a pm/ceo
   plan to the chain driver, which executes and commits it with the same stamp; the EM invokes
   /execute-plan there only to resume a halted chain. Every other run is in-session. Contract:
   `coordinator/docs/wiki/em-operating-model/sizing-to-commit-chain-contract.md`.
   **A delegated run** mints with `--authorized-by-delegation <delegate>` and `--delegation-source <ref>`,
   the PM's standing words, if any, in `--standing-direction-quote`, and never `--utterance`. Tripwire:
   `A-DELEGATED-RUN-STAMPS-THE-DELEGATE-NOT-THE-PM`.
3. **Remaining-context gate** (skip under `/autonomous`): read this session's remaining-context
   reading (the statusline's context-window percentage; the engine cannot see it) before committing to same-session
   execution. A fresh (picked-up) session is the default; LOW remaining context is the narrow carve-out. Detail: wiki.
4. Resolve EM-resolvable concerns at EM altitude. A
   concern revealing the plan isn't executable → Phase 1.4.
5. Announce and continue.

---

## Phase 1.4: Executability Gate

Bounce to `/plan` on any of: an embedded decision gate ("evaluate X before continuing", "Phase 0
— investigate"); a fact-finding chunk with no fix-locus; an unpopulated downstream wave-map;
in-prose deferral of an EM-resolvable decision; open questions gating whether
downstream chunks can be authored; an unbuilt external prerequisite with no landed commit/date;
a chunk with an irreversible external side effect (send, publish, mail, third-party call) naming no skip-if-already-delivered marker. Tripwire:
`A-FIRE-WITHOUT-A-SHIPPED-SIGNAL-RECHECK-REDELIVERS-AN-IRREVERSIBLE-CHUNK`.

Read the last two off the spine, not prose. A non-deferred open row with no `writes:` key IS an
unpopulated wave-map. A row's `external_gate` entries declare the external prerequisite: `blocks: execution` uncleared bounces;
`blocks: ac-closure` does not — proceed, telling the PM at dispatch the terminal state is `approved`, not `implemented`.
`plan-spine-check --for-execution <plan>` exiting 1 is the unpopulated-wave-map bounce; report its WIDTH line at dispatch.
An M+ plan whose `prime_exit_criterion` carries no `falsifier` block and no `falsifier_exemption`
bounces to `/plan` to dispatch `coordinator:exit-criterion-falsifier` — close-out refuses
`implemented` on it. Tripwire:
`AN-OWED-FALSIFIER-IS-CAUGHT-BEFORE-EXECUTION-NOT-AT-CLOSE-OUT`.
Catalog: wiki.

---

## Phase 1.5/1.6: Dispatch-Gate Graph and Wave-Map

**Roadmap-baton execution gate — check before claiming.** A plan executing a `blocked_by` roadmap
baton needs every blocker **coded**, not just planned. Read it, never derive it:
`coordinator-invoke roadmap.plan_gate '{"subject":"<baton-id>","gate":"execution"}'` returns
`verdict.open` plus the blockers holding it shut. Shut → stop; a written, waiting plan is the correct state. Tripwire: `A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`.

Claim the plan (`session-claim-cli claim-plan <slug> --for-execution`) before any gate-graph work;
a live peer holding it means reconcile with them first, never race. A live holder that has
formally handed off (relinquishment evidence, not liveness) → `take_over_claim`,
fail-loud without evidence; never retry `claim-plan` bare. **`--for-execution` is
mandatory**: it flips the plan to `status: executing`, and this step is its only caller fleet-wide. (`coordinator-tripwires/plan-status-ladder.md`.)

After the claim, run `plan-completeness generate "$ARGUMENTS"` (the BASELINE SNAPSHOT, diffed in Phase 4).

**Plan prose does not pick the vehicle.** A sentence forbidding fan-out or prescribing
EM-sequenced chunk-at-a-time execution is overridden: the vehicle follows from the classification
below (default a background Workflow); note the override in one line, do not ask. Only a prohibition
traceable to a genuine Workflow-inexpressible shape
(`coordinator/docs/wiki/em-operating-model/workflow-orchestration.md` § What qualifies as a carve-out) survives.
Tripwire: `A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`.

**Read each chunk pair's `gate_kind` off the `dispatch.emit` wave map — never classify by hand.** Running a pair together:
- **File-write overlap** → gates authoring, no escape hatch — predecessor lands first.
- **Output/contract consumption** → concurrent if A's interface is pinned up front
  (verify at merge); else predecessor-wave.
- **Runtime consumption** (B needs A's artifact to *exist and run*) → gates authoring, no escape.
- **Epistemic/premise** (A decides whether B's chunks should exist) → A ships alone first; B isn't drafted until A's verdict lands.
- **Independent** → same wave, no gate.

An uncleared `external_gate` `blocks: execution` row is unschedulable in any wave; its owner
session must be live and its `memo:` sent (`A-EXTERNAL-OWNER-IS-LIVE-AND-ITS-MEMO-IS-SENT`).

**Cross-check the AC table against the chunk list before emitting.** An `## Acceptance Criteria`
row with no chunk citing it (frontmatter list, `covers:`, or body reference) is a silent gap:
confirm a `## Tasks` row names every AC row, and fix an uncovered AC in the plan before dispatching.

**A signature/param-removal chunk scoping only production handlers is the same gap**: its scope
must name test fixture defs and call sites (`execute-plan-residue.md` § Signature/param-removal).

**A chunk whose deliverable is a static gate or sweep predicate** carries a brief sorting every
case into PROVE-BAD, PROVE-GOOD or CANNOT-DECIDE, flagging only PROVE-BAD; a first run of two dozen hits or more gets a hand-read sample before any fix wave. Tripwire:
`A-STATIC-GATE-BRIEF-MUST-SORT-EVERY-CASE-INTO-PROVE-BAD-PROVE-GOOD-OR-CANNOT-DECIDE`.

**Invoke `dispatch.emit` — never derive the wave shape by hand.** It
reads the spine's `writes:`/`depends_on` and emits the ready-to-fire Workflow, each row's
`gate_kind`, `write_files`, `agentType` resolved, non-dispatchable rows filtered.

`NoWritesDeclaredError` means an unpopulated spine — fix the plan, never hand-derive. Write
the emitted script to `<plan-basename>.workflow.mjs` next to the plan. Emitted scripts and `.emitted.json` receipts are ephemeral: gitignored, never committed, pruned by `/distill`.

<!-- engine-gap: field=execute_plan.ses_fire_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

**Emit and dispatch are ONE action.** In an interactive
session the EM runs `emit-dispatch-workflow --plan <plan-path>` (settings-home launcher; resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`, PowerShell included). Before firing, register review targets (EM-only; reviewers apply findings only to them):
`review-findings-ledger targets --from-plan <plan-path>`. Then
call `Workflow({scriptPath: "<emitted path>", args: {repoRoot: "<absolute repo root>"}})` in this
session, using the `fire with: Workflow(...)` line the emitter prints on stderr.
**Recheck the shipped signal just before the fire:** re-read each dispatchable row's status, the
completion receipt, and the chunk's commit. A row shipped since the emit makes the
script stale: re-emit, never fire old bytes. Tripwire:
`A-FIRE-WITHOUT-A-SHIPPED-SIGNAL-RECHECK-REDELIVERS-AN-IRREVERSIBLE-CHUNK`.

**A row is rechecked at fire, not at emit.** The Workflow skips a row already `coded`; a row with an irreversible external side effect (memo, publish, push, third-party call)
carries a skip-if-delivered check keyed on that effect's receipt (wiki `execute-plan-residue.md` § Fire-time freshness). Tripwire: `A-ROW-IS-RECHECKED-AT-FIRE-NOT-AT-EMIT`.

**An emitted fire raises no permission prompt.** One that does was edited in
place (its `<script>.emitted.json` digest differs): `--restamp`, not re-emit. Tripwire:
`AN-EMITTED-WORKFLOW-FIRES-WITHOUT-A-PROMPT-A-HAND-ROLLED-ONE-DOES-NOT`.

**`--fire` is the headless and cron path only** (`engine_fire.fire_workflow`; returns a run handle
whose `fire_id` `workflow.fire_status` re-reads); wrong wherever a session can call the tool.
Wiki: `execute-plan-residue.md` § Phase 1.5/1.6.

**No hand-dispatch fallback.** If the dispatch refuses — the `Workflow` call, or on the
headless path a named fire-leg refusal (`ScriptNotFoundError`, `PluginDirResolutionError`,
`ConcurrencyCapExceededError`, `ChildSpawnFailedError`) — report it and stop; hand-dispatching with the Agent tool is never the recovery; a concurrency-cap refusal means wait. The emit refuses with
`DirtyWriteSetError` when a path in the dispatchable rows' `writes:` is dirty or untracked — commit or reconcile it with its owner and re-emit; never edit `writes:` to dodge it. Tripwire: A-DIRTY-PATH-IN-THE-WAVE-WRITE-SET-REFUSES-THE-EMIT.

**A fifth state: fired-then-died.** A handle with `log_size_bytes: 0` stalled past startup: report and stop.

**A sixth state: returned `incomplete`, nothing halted.** Not a resume. Run `dispatch.terminal_commit`, then `emit-dispatch-workflow --plan <plan> --only-incomplete <task-output>` and fire; never hand-dispatch. A row partial only on a break outside its files is re-graded by `terminal_commit` (`regraded`); any other is re-verified (`--reverify-delivery <run-record>`, fire, `reverify-delivery record --run-record <that same run-record>`, never the `.emitted.json`). Hand-committing its files refuses the stamp.

**A brief never asks an executor to commit** — its Commit Gate refuses.

Wave shape comes from the file-write graph, never the plan's section structure; one dispatch
per chunk, never bundled. Taxonomy and checks: wiki.

**No checkpoint prompt; scripted gates still hold.** The workflow never pauses to ask; a `phase()`'s deterministic gate MAY halt the run (`return { halted: ... }`, wiki:
`workflow-orchestration.md`), and a halted or edited phase resumes via `resumeFromRunId`.

**One emit per plan — a partial re-run resumes, never re-emits.** The emitted script carries
every open wave through review and the terminal test phase; the run's one commit
(`dispatch.terminal_commit`, below) follows the return. On a halt (a BLOCKed executor, review-wave BLOCKED/FAIL, or rebuild verdict) recover with `Workflow({scriptPath, resumeFromRunId: <run>})`
in the same session; resume alone re-halts (the refusal verdict is cached). **Edit the
halting phase's agent step first, and no earlier one** — fix what the refusal named — then
**re-stamp the receipt** (`block-workflow-foreign-emission.py` denies a fire whose bytes differ):
`emit-dispatch-workflow --restamp <script>` (refused unless the receipt names this session); then
resume. A second `emit-dispatch-workflow` narrows to a one-wave script (`read_spine` excludes
closed rows); re-emit only when the spine changed. Tripwire:
`A-SECOND-EMIT-AFTER-A-PARTIAL-RUN-NARROWS-SILENTLY`.

**Watch with `Monitor`, never hand-polling:** the run's `journal.jsonl` (completion, phase-boundary, failure, every terminal state).

**Completion — the driver's first act on return is the terminal commit, not a phase inside the workflow.** The
review wave runs inside the workflow; nothing commits mid-run. The run's driver commits — the EM for an in-session run, the chain driver for a chained one. The driver runs `coordinator-invoke dispatch.terminal_commit` with `script_path` and
`task_output_path`, the task file carrying `next_action.params`: the run's ONE commit, carrying the
`Inline-Review:` trailer. `implemented` means done: a met terminal judge stamped it and Phase 4 steps 2.5 to 4 ran inside
it. Still `executing`: read the reason and treat the run as Phase-5-halted. That commit writes one
completion receipt per baton; the EM reads it, never writes it ([`completion-receipts.md`](../../docs/wiki/release-and-distribution/completion-receipts.md)).
See [`terminal-judge.md`](../../docs/wiki/reviewer-pipeline/terminal-judge.md). Tripwire:
`A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`.

Same turn: wake digest to the PM in **hands-on**/**pm** modes, at once in **ceo**; then fire
`coordinator:workstream-complete` (turn 4).

---

## Phase 2: Create Flight Recorder

TaskCreate: one task per plan phase/major task, BENEATH the stage rows the sizing lobby
opened (`skills/sizing/SKILL.md` § 4b); its session-goal task is already `in_progress`.
Without the lobby: open the recorder here, session goal plus phases, `in_progress` at once.
<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface (`ToolSearch("select:TaskCreate")` returns nothing)
→ fall back to `coordinator-tasks-mirror` for the same flight-recorder role; do not assume either
state without checking. When Task* is unavailable, dispatch the phases in order, waiting on each
completion notification — that is the ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

A plan in another repo than the session's anchor → pass
`coordinator-tasks-mirror --repo-root <plan's repo>`; bare, the repo-identity gate refuses as a MISMATCH.

---

## Phase 3: Execute All Tasks

<!-- engine-gap: field=execute_plan.wave_boundary_gated_artifact_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

Execute every task in sequence without stopping to ask. Per task: write-ahead (mark
`In progress` on disk + TaskUpdate `in_progress`) → execute (follow the plan, fix routine errors)
→ **reachability gate** (new entry point? confirm a production call site: caller-grep or traced entry, never an import smoke-check; the terminal judge re-checks via `review.reachability`, wiki `judge-reachability-check`) → mark complete (on disk + TaskUpdate `completed`) → proceed
immediately, across phase boundaries, same session, same flight recorder.

Mid-dispatch decisions are the EM's — pick, record a one-line rationale, continue; only the
Phase 5 list escalates. A residual (a missed site, a fix wider than the AC) needs a closed exit: dispatch it, add a spine row for the Phase 4 harvest, `coordinator-queue-append --schema
bug-backlog|debt-backlog|improvement-queue`, or take it to the PM; a reason with no queue id, row, or commit is not routed.

---

## Phase 4: Finalize and Report

**Precondition:** every wave-map chunk has landed, confirmed via the recovery triple; else return
to Phase 3. Steps 2.5 to 4 are the manual path, only when the terminal commit did not stamp.
Leg 1 alone yields candidates, never a verdict: corroborate against leg 2 or 3, plus a git log by chunk-id subject unscoped by path.

1. **Leg 1** — the engine op for this read:
   `chunk-commits <plan-path> <chunk-id>` (`ceremony.chunk_commits`) scopes to the plan's add-commit range (`<add-sha>..HEAD`) AND its `Checkpoint-Plan:` trailer, filtering on the commit SUBJECT (never
   `--grep`, never a pathspec-scoped query, never a bare repo-wide grep: chunk ids restart at C1
   per plan). A `no_join_candidates`-shaped result does not prove the chunks didn't ship. Rationale: wiki residue § Phase 4 Leg 1.
2. **Leg 2 — the Workflow's own script**, persisted and resumable via
   `resumeFromRunId` (Phase 1).
3. **Leg 3 — the Task-list flight recorder** (Phase 2), which persists through compaction.

**`close-out-and-stamp` reads no commit message at all.** The commit-subject/`Deliverable-Id`-trailer
join was deleted, not narrowed; do not restore it as an oversight. Two sha-ancestry evidence paths survive: a `disposition: coded` spine row's `disposition_ref`, and, for a pre-spine plan, its `## Dispatch Ledger` `committed <sha>` cells.

**The `## Tasks` spine is the only row family close-out reads.** The falsifier delta on
`prime_exit_criterion` — its verdict, not a row's ticked-or-open state — discharges the plan. Tripwire: `AN-UNTICKED-AC-CELL-CARRIES-NO-INFORMATION`.

**Before any cleanup:** `coordinator-harvest-deferrals --plan "$ARGUMENTS"`, surfacing its
`"Queued N ..."` line even on `Queued 0`. A `defer` grouping approval (or legacy
`pm_approved: true`) is a ratification claim the harvest selects on; this step never stamps it
(closing a row mid-execution is a scope decision for the PM).

**Commit sequence, two commits, never one (the resolve step writes the plan, not a third commit):**
1. Land the chunk work in your own scoped commit(s) — explicit pathspec, never `git add -A`. The
   `prepare-commit-msg` hook attaches the `Deliverable-Id:` trailer per
   `snippets/scoped-commit-route.md`; never hand-add it.
2. Resolve each landed row's `disposition_ref`, the only thing close-out counts:
   `plan-tasks-resolve --plan "$ARGUMENTS" --id <row> --coded <sha> --disposition-detail "<why>"`,
   per row, then close out. `missing_chunk_ids` at exit 0 over a range that provably holds every
   chunk SHA means unresolved rows: resolve and re-run, never rewrite shared history. Record the
   sha where the work actually landed: the anti-self-attestation gate cannot catch a row pointing
   at a peer's commit.
2.5. Run `plan-completeness status "$ARGUMENTS"` (never writes). Paste its raw rollup line into
   `exit_criterion_met.prose`, beside the baseline's rollup line. A `CONTRADICTION: ` line
   carries verbatim into the close-out report; never stamp over it.
3. Re-run `prime_exit_criterion.falsifier.how` against `HEAD`, paste its raw output into
   `exit_criterion_met.falsifier_output`, and judge it against
   `prime_exit_criterion.falsifier.expected_when_true` — never against `baseline_output`. Record
   the verdict in `exit_criterion_met.falsifier_verdict` (`pass`/`fail`; a changed-but-non-matching
   output is `fail`); the gate refuses the
   stamp unless it is `pass`. `exit_criterion_met.prose` ties it to the prime criterion.
   `fail` → `asserted: false`, Phase-5-halted, no stamp.
3.5. **Promote the falsifier, when it promotes.** An executable, deterministic falsifier graduates into the repo's test suite: `promotion: promoted` plus `promoted_to: <test path>`, or `partial`
   with the path the promoted portion landed at; already a standing test → `already-in-suite`, no
   `promoted_to`, the test named in `promotion_reason`. PROMOTION IS AN OUTCOME, NOT A GATE: a
   one-shot query, manual observation, or live measurement records `not-applicable` plus a reason.
3.6. **Adversarial criterion-only reader, M+ plans that went green first time only.** M+ per
   `sizing_object.estimate.tshirt` (never an S-lane spec-dispatch) AND every wave-map chunk
   landed without an executor BLOCKing — dispatch one reader that receives only the prime exit criterion statement and `HEAD`, and answers one question: does HEAD
   do this? A roster's judge stage (`coordinator:exit-criterion-judge`) is this reader; no second. **THE DENIAL LIST IS THE MECHANISM AND MUST BE EXPLICIT IN THE DISPATCH:**
   no plan body, no AC table, no chunk bodies, no run reports, no reviewer sidecars.
3.7. **Reachability re-check, before the stamp.** The judge's `reachability` block (`review.reachability`, wiki `judge-reachability-check`) is the re-check; unreachable is its not_met. No block (op absent, error): caller-grep at `HEAD`. Unconfirmed → Phase-5-halted, no stamp.
3.8. **`review-stamp mint`, owed by hand only when `dispatch.terminal_commit` did not report
   `review_stamp: minted`.** `review-stamp mint --plan "$ARGUMENTS" --build-test <wake digest's
   tests.sidecar>` (not required when the spine wrote nothing testable and the criterion is
   `met`). It resolves the terminal commit via `Inline-Review:` and writes `review_stamp:`. Refusal
   (incl. a `refused` from `terminal_commit`) — no stamp-able review, no build/test record,
   `delivery.verdict == FAIL`, `unresolved > 0`, a confinement violation, or non-empty
   `foreign_claims[]` — is Phase-5-halted: report, skip step 4. Tripwire:
   `A-PLAN-REACHES-IMPLEMENTED-ONLY-THROUGH-A-REVIEW-STAMP`.
   **A `delivery.verdict == FAIL` since repaired by fix-forward commits** is cleared only by
   `emit-dispatch-workflow --reverify-delivery`, never a hand-authored record
   (`execute-plan-residue.md` § Reverify a delivery FAIL). Re-run 3.8, then step 4.
4. `close-out-and-stamp "$ARGUMENTS"` stamps `status: implemented` and commits the plan path
   (full-plan-shipped), or reports remaining uncommitted chunks and skips the stamp
   (Phase-5-halted). The engine refuses `implemented` without a `review_stamp` (step 3.8).

**Offer, stamp-aware.** Whether step 4 stamped `implemented` decides it.
Stamped → offer `/workstream-complete`, noting `/merging-to-main`/`/workday-complete` ship it.
Unstamped for **any** reason (Phase 5 halt, open spine row, a leg unmet in another repo) → offer
resolve-and-resume, `/handoff`, or commit-and-stop. Never auto-invoke these or `coordinator:finishing-a-development-branch`.
Tripwire: `AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`.

**A cross-repo leg names its failing conjunct, not its repo** (*undeclared*, *unaddressed*, *unanswered*), per `coordinator/snippets/cross-repo-block-exchange.md`. Tripwire:
`A-SENT-MEMO-IS-NOT-AN-EXCHANGE`.

---

## Phase 5: When to Stop — PM-Only Emergencies

Default: complete the plan. Stop only for: **external trust surface change**
(user-visible behavior, privacy, security boundary, billing/pricing/onboarding, or any
externally-observable contract the plan didn't call out); **plan-invalidating substrate change**
(disk state changed since drafting, making the plan structurally wrong — bounce to
`/plan`); **scope explosion** (≥3× anticipated size, no 5-15min-chunk decomposition for the
remainder — route back to `/plan`); **unauthorized irreversible action required**
(destructive op, force-push, cross-repo write to a sibling's code, credential/cookie write, or
anything gated by `~/.claude/CLAUDE.md` § Executing actions with care); **discovery the plan
would ship something not authorized** (approved on premise X; execution reveals it also does Y, not a mechanical consequence of X).

Not on the list (EM decisions): accumulating patches, ambiguity, structural verification failure
(`/systematic-debugging`), routine fixable errors, minor judgment calls, wanting to check in.
Record `Tried:/Failed:` in the plan doc and `metadata.tried_and_abandoned`; surface a recommendation, not a question.

**Usage-limit advisory** (a pause, no PM emergency): dispatch nothing new, let in-flight agents
land, commit scoped, write the handoff with the reset time in its next steps, stop.
`A-DRIVER-PAST-ITS-USAGE-THRESHOLD-FIRES-NOTHING-NEW` —
`coordinator/docs/wiki/skills-corpus/usage-limit-pause.md`.

---

## Relationship to Other Commands

Default upstream entry is `/handoff` + `/pickup`; enrichment has happened upstream.
`/review-code` stays an optional ad-hoc pass; the plan's review is the fired workflow's (Phase 1.5/1.6).
`coordinator:workstream-complete` is offered, never auto-invoked, in Phase 4;
`coordinator:finishing-a-development-branch` is reached via `/merging-to-main`. Failure modes: wiki.
