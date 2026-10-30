---
name: execute-plan
description: Execute a PM-approved plan via per-chunk executor waves.
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — End-to-End Plan Execution

Run a PM-approved plan end-to-end without stopping for permission between tasks (`THE-EM-TIME-AND-COST-SPENT-IS-A-RED-FLAG`). Invoking `/execute-plan` IS the PM's authorizing act (`execution_authorized_at` records it; no precondition). **It also
satisfies a chunk body's own "needs PM assent at execution dispatch" clause.** Never re-ask per
chunk or offer to halt a fired run. A gate it does
NOT satisfy names another act: a cross-repo commit (per-session assent, obtained at
that dispatch) or an external-facing action. No chain into `/merging-to-main` (PM-gated).

Execute = build the dispatch-gate graph and dispatch per chunk through a background Workflow (parallel where gates allow; a serial chain is N fresh dispatches with EM-verify between). No per-chunk reviewer gate: code review is the emitted workflow's own (`review-roster-fragment.md` § Stages); the EM never hand-dispatches a reviewer. Tripwire: `CODE-REVIEW-IS-A-STAGE-OF-THE-EXECUTE-WORKFLOW`. **A chunk that
registers an op is verified with the registry-completeness tests, never the full suite**
(`execute-plan-residue.md` § Op-registering chunk). **EM-verify means the EM itself runs the chunk's scoped tests, never trusts an executor's pass claim**; "PASS (by inspection)" is not verification; a host-dependent red is no verdict until the interpreter matches the canonical gate env. **A chunk that ships a new helper/hook/injector is not done on green tests alone**: a mechanism with no caller never counts as shipped, checked at Phase 3's mark-complete and again in Phase 4 before the stamp (`coordinator/docs/wiki/reviewer-pipeline/review-integration-doctrine.md`).
Executors are always Sonnet; self-execute only on a named token-economics carve-out.

**Dispatch authorization — invoking this skill IS the request.** Its dispatches are constitutive steps, so a harness line permitting dispatch "unless the user requested it" is satisfied here, not overridden. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds (per-session cross-repo-commit assent, ask-before-external-action, any other this skill's own body names). Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## Arguments

`$ARGUMENTS` is the plan path; none or missing → report and stop.

---

## Phase 1: Load, Authorize, Review

0. **One box per plan**, claimed before execute; another box's claim stops
   this run (`A-PLAN-EXECUTES-ON-ONE-BOX-CLAIMED-BEFORE-EXECUTE`).
1. Read the plan in full, then run `python3 "${CLAUDE_PLUGIN_ROOT:?plugin root unset}/lib/plan_scaffold_markers.py" <plan-path>`;
   exit 3 (`PLAN-SCAFFOLD-UNFILLED`) = unfilled scaffold — report and stop.
2. Unless `/autonomous`: run `pickup-assemble brief <plan-path>` FIRST, before minting (minting erases the signal) — it emits
   `gates.execution_stamp_match`. FRESH, STALE-bookkeeping, or a "carries no `execution_authorized_sha`" fail → proceed **without re-stamping**. STALE-substantive surfaces the delta and STOPS. A body changed since
   approval (`approved_body_sha`, which a mid-run row also moves) goes back through
   `coordinator:review`, never re-minted over; then
   `review-exec-auth-stamp restamp` rebinds it. Tripwire: `AN-APPROVED-PLAN-WHOSE-BODY-CHANGED-IS-UNREVIEWED`.
   THEN mint: `review-exec-auth-stamp authorize-invocation <plan-path> --typed-command /execute-plan [--utterance "<PM's verbatim words>"]`.
   Hands-on, `--utterance` is required when `pm-brief render <plan>`
   resolves no PM brief, sizing pm_verbatims or baton (`A-WORDLESS-TYPED-COMMAND-MINT-IS-NOT-A-PM-BRIEF`). Git Bash: prefix `MSYS_NO_PATHCONV=1`. `/autonomous`: mint as a delegated run (2a). `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.
2a. **By mode** (`execute-plan-residue.md` § Mint mechanics). **pm**/**ceo**: stamp `authorized by accepted sizing (mode=<mode>)`, sizing path cited, no `--utterance`. **Delegated run**: `--authorized-by-delegation <delegate>` and `--delegation-source <ref>`, never `--utterance`. Tripwire:
   `A-DELEGATED-RUN-STAMPS-THE-DELEGATE-NOT-THE-PM`.
3. **Remaining-context gate** (skip under `/autonomous`): read the statusline's context % before same-session execution; a fresh (picked-up) session is the default.
3a. **Re-probe every cited canvas, in the main loop**: read each `harvest/harvest.json`'s version and comments, run the engine harvest op's probe mode. A dispatch-leg
   refusal at fire is final until re-harvested; an unreadable canvas is reported, not waited on. Executors read the record (`snippets/design-canvas-recipe.md`).
4. Resolve EM-resolvable concerns yourself; one revealing the plan isn't executable → Phase 1.4. Announce and continue.

---

## Phase 1.4: Executability Gate

Bounce to `/plan` on any of: an embedded decision gate ("evaluate X before continuing"); a fact-finding chunk with no fix-locus; an unpopulated downstream wave-map;
in-prose deferral of an EM-resolvable decision; open questions gating whether
downstream chunks can be authored; an unbuilt external prerequisite with no landed commit/date;
an irreversible-side-effect chunk naming no skip-if-already-delivered marker (`A-FIRE-WITHOUT-A-SHIPPED-SIGNAL-RECHECK-REDELIVERS-AN-IRREVERSIBLE-CHUNK`).

Read the last two off the spine (`execute-plan-residue.md` § Executability gate): a non-deferred open row with no `writes:` key bounces (`plan-spine-check --for-execution <plan>` exits 1; report its WIDTH line at dispatch); an uncleared `external_gate` `blocks: execution` bounces, `blocks: ac-closure` does not; an M plan whose `prime_exit_criterion` has no `falsifier` block and no `falsifier_exemption`
bounces to `/plan` for `coordinator:exit-criterion-falsifier` (`AN-OWED-FALSIFIER-IS-CAUGHT-BEFORE-EXECUTION-NOT-AT-CLOSE-OUT`).

---

## Phase 1.5/1.6: Dispatch-Gate Graph and Wave-Map

**Roadmap-baton gate, before claiming:** every `blocked_by` blocker must be **coded**;
`coordinator-invoke roadmap.plan_gate '{"subject":"<baton-id>","gate":"execution"}'` returns
`verdict.open`. Shut → stop (`A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`).

Claim the plan (`session-claim-cli claim-plan <slug> --for-execution`) before any gate-graph work; a live peer holding it means reconcile, never race; a live holder that formally handed off (relinquishment evidence, not liveness) → `take_over_claim`, never a bare `claim-plan` retry. **`--for-execution` is mandatory** (it flips the plan to `status: executing`; this step is its only caller).
Then `plan-completeness generate "$ARGUMENTS"` (BASELINE SNAPSHOT, diffed in Phase 4).

**Plan prose does not pick the vehicle.** A sentence forbidding fan-out or prescribing EM-sequenced execution is overridden (default a background Workflow); note it in one line, do not ask. Only a prohibition traceable to a Workflow-inexpressible shape (`coordinator/docs/wiki/em-operating-model/workflow-orchestration.md` § What qualifies as a carve-out) survives (`A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`).

**Read each pair's `gate_kind` off the `dispatch.emit` wave map — never classify by hand** (`execute-plan-residue.md` § The gate-kind discriminator table, in full): overlap and runtime consumption gate authoring (predecessor first); contract consumption is concurrent only if A's interface is pinned up front; epistemic ships A alone first; independent shares a wave.

An uncleared `external_gate` `blocks: execution` row is unschedulable; its owner
must be live and its `memo:` sent (`A-EXTERNAL-OWNER-IS-LIVE-AND-ITS-MEMO-IS-SENT`).

**Cross-check the AC table against the chunk list before emitting**: an `## Acceptance Criteria`
row no chunk cites (`covers:` or body) is a silent gap; fix it in the plan first.

A signature/param-removal chunk's scope must name test fixture defs and call sites (`execute-plan-residue.md` § Signature/param-removal). A static-gate or sweep-predicate chunk's brief sorts every
case PROVE-BAD, PROVE-GOOD or CANNOT-DECIDE, flagging only PROVE-BAD; two dozen first-run hits get a hand-read sample before any fix wave (`A-STATIC-GATE-BRIEF-MUST-SORT-EVERY-CASE-INTO-PROVE-BAD-PROVE-GOOD-OR-CANNOT-DECIDE`).

**Invoke `dispatch.emit` — never derive the wave shape by hand.** It
reads the spine's `writes:`/`depends_on` and emits the ready-to-fire Workflow
(`NoWritesDeclaredError` = unpopulated spine: fix the plan). Write
the script to `<plan-basename>.workflow.mjs` next to the plan; scripts and `.emitted.json` are never committed.

<!-- engine-gap: field=execute_plan.ses_fire_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

**Emit and dispatch are ONE action.** The EM runs `emit-dispatch-workflow --plan <plan-path>` (launcher resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`), registers review targets (EM-only) `review-findings-ledger targets --from-plan <plan-path>`, then calls `Workflow({scriptPath: "<emitted path>", args: {repoRoot: "<absolute repo root>"}})` in this session. **Recheck the shipped signal just before the fire** (row status, completion receipt, chunk commit): a row shipped since the emit makes the script stale: re-emit.

**Emit prints "exceeds the per-workflow cap"** → fire its manifest's staged siblings (`A-PLAN-WIDER-THAN-THE-WORKFLOW-CAP-FIRES-AS-STAGED-SIBLINGS`).

**A row is rechecked at fire, not at emit.** The Workflow skips a row already `coded`; an irreversible-side-effect row
carries a skip-if-delivered check (`execute-plan-residue.md` § Fire-time freshness; `A-ROW-IS-RECHECKED-AT-FIRE-NOT-AT-EMIT`).

**An emitted fire raises no permission prompt**; one that does was edited in
place: `--restamp`, not re-emit (`AN-EMITTED-WORKFLOW-FIRES-WITHOUT-A-PROMPT-A-HAND-ROLLED-ONE-DOES-NOT`). **`--fire` is the headless and cron path only** (`execute-plan-residue.md` § Phase 1.5/1.6).

**No hand-dispatch fallback.** A refused dispatch (the `Workflow` call, or a headless fire-leg refusal: `ScriptNotFoundError`, `PluginDirResolutionError`,
`ConcurrencyCapExceededError`, `ChildSpawnFailedError`) means report and stop, never the Agent tool; a concurrency-cap refusal means wait. `DirtyWriteSetError` (a `writes:` path dirty or untracked) → reconcile with its owner and re-emit; never edit `writes:` to dodge it. Tripwire: A-DIRTY-PATH-IN-THE-WAVE-WRITE-SET-REFUSES-THE-EMIT.

**Fired-then-died** (`log_size_bytes: 0` past startup): report and stop. **Returned `incomplete`, nothing halted:** not a resume; `dispatch.land_run`, then `emit-dispatch-workflow --plan <plan> --only-incomplete <task-output>` and fire; never hand-dispatch or hand-commit its files (`execute-plan-residue.md` § Fired-run states).

**A brief never asks an executor to commit** and never dictates code: intent, PM verbatims and constraints only (`dispatch-briefing.md` § Field rules). Wave shape comes from the file-write graph, never the plan's section structure; one dispatch per chunk. The workflow never pauses to ask; a `phase()`'s deterministic gate MAY halt it, resumed via `resumeFromRunId`.

**One emit per plan — a partial re-run resumes, never re-emits.** On a halt (BLOCKed executor, review-wave BLOCKED/FAIL, or rebuild verdict): edit the
halting phase's agent step first (no earlier one), `emit-dispatch-workflow --restamp <script>` (refused unless the receipt names this session), then `Workflow({scriptPath, resumeFromRunId: <run>})`
in the same session (resume alone re-halts). Re-emit only when the spine changed (`A-SECOND-EMIT-AFTER-A-PARTIAL-RUN-NARROWS-SILENTLY`).

**No watching:** the completion notification is the wake; never poll.

**Completion — the driver's first act on return is the terminal commit.** Nothing commits mid-run. The driver runs `coordinator-invoke dispatch.land_run` with `script_path` and
`task_output_path` (`next_action.params`; script gone: `plan_path`, `run_id`): the run's ONE commit (`Inline-Review:` trailer, one completion receipt per baton; EM reads, never writes: [`completion-receipts.md`](../../docs/wiki/release-and-distribution/completion-receipts.md)). `implemented` = a met terminal verdict stamped it and Phase 4 steps 2.5 to 4 ran inside
it; still `executing` → read the reason; Phase-5-halted
([`terminal-judge.md`](../../docs/wiki/reviewer-pipeline/terminal-judge.md); `A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`). With `state/warp/<run_id>/objective.json`
present, a `not_met` verdict goes to the reacher loop (`coordinator:objective-reacher`) at the terminal gate only; the run ends only on that doc's exit set, never partial or unknown.

Same turn: wake digest to the PM (**hands-on**/**pm**; at once in **ceo**); then fire `coordinator:workstream-complete`.

---

## Phase 2: Create Flight Recorder

TaskCreate one task per plan phase/major task, BENEATH the stage rows the sizing lobby
opened (`skills/sizing/SKILL.md` § 4b); without the lobby, open the recorder here (session goal plus phases, `in_progress` at once).
<!-- BEGIN task-tool-availability (synced from snippets/task-tool-availability.md) -->
`TaskCreate` absent from this session's surface (`ToolSearch("select:TaskCreate")` returns nothing)
→ fall back to `coordinator-tasks-mirror` for the same flight-recorder role; do not assume either
state without checking. When Task* is unavailable, dispatch the phases in order, waiting on each
completion notification — that is the ordering a `blockedBy` chain would otherwise express.
<!-- END task-tool-availability -->

Plan in another repo → pass `coordinator-tasks-mirror --repo-root <plan's repo>`.

---

## Phase 3: Execute All Tasks

<!-- engine-gap: field=execute_plan.wave_boundary_gated_artifact_check producer=unknown memo=2026-08-27-claude-klabauter-em-doe-unmarked-obligations-and-four-lost-markers.md -->

Per task: write-ahead (mark
`In progress` on disk + TaskUpdate `in_progress`) → execute (fix routine errors)
→ **reachability gate** (new entry point? confirm a production call site: caller-grep or traced entry, never an import smoke-check; the judge re-checks via `review.reachability`, wiki `judge-reachability-check`) → mark complete (on disk + TaskUpdate `completed`) → proceed
immediately, never stopping to ask. Phase boundaries are not stop boundaries: ship Phase N green, dispatch N+1. Mid-dispatch decisions are the EM's: pick, note one line, continue; only the Phase 5 list escalates. A residual needs a closed exit: dispatch it, add a spine row, `coordinator-queue-append --schema
bug-backlog|debt-backlog|improvement-queue`, or take it to the PM; a reason alone is not routed.

---

## Phase 4: Finalize and Report

**At L and above the run's ledger checker is the close**, replacing plan-reviewer, integrity review,
and both judges: no judge slot runs beside or after it, except the
fresh re-judge after a `not_met` remnant wave; steps 3 to 3.8 apply below L only. The close runs the
plan's recorded falsifier; a failing one is `not_met` per
`coordinator/docs/wiki/em-operating-model/run-objective-loop.md`, never partial; its `remnant` follows
`coordinator/contract/remnant-completion-fragment.json`.

**Precondition:** every wave-map chunk has landed (recovery triple: leg 1 `chunk-commits <plan-path> <chunk-id>`, leg 2 the Workflow script, leg 3 the Phase 2 Task list); else return
to Phase 3. Steps 2.5 to 4: manual path, only if the terminal commit did not stamp.
Leg 1 alone yields candidates, never a verdict: corroborate against leg 2 or 3 and a git log by chunk-id subject unscoped by path (never
`--grep` or a pathspec: chunk ids restart at C1); `no_join_candidates` does not prove the chunks didn't ship.

**`close-out-and-stamp` reads no commit message at all.** The commit-subject/`Deliverable-Id`-trailer
join was deleted, not narrowed; do not restore it as an oversight. Two sha-ancestry paths survive: a `disposition: coded` row's `disposition_ref`, and a pre-spine plan's `## Dispatch Ledger` `committed <sha>` cells.

**The `## Tasks` spine is the only row family close-out reads**; the falsifier verdict on
`prime_exit_criterion`, not a ticked row, discharges the plan (`AN-UNTICKED-AC-CELL-CARRIES-NO-INFORMATION`).

**Before any cleanup:** `coordinator-harvest-deferrals --plan "$ARGUMENTS"`, surfacing its
`"Queued N ..."` line even on `Queued 0`; it never stamps a `defer` grouping approval or `pm_approved: true` (closing a row mid-execution is the PM's call).

**Commit sequence, two commits, never one:**
1. Land the chunk work in your own scoped commit(s) — explicit pathspec, never `git add -A`; never hand-add `Deliverable-Id:` (the hook attaches it; `snippets/scoped-commit-route.md`).
2. Resolve each landed row's `disposition_ref`, the only thing close-out counts:
   `plan-tasks-resolve --plan "$ARGUMENTS" --id <row> --coded <sha> --disposition-detail "<why>"`,
   then close out. `missing_chunk_ids` at exit 0 means unresolved rows: resolve and re-run, never rewrite shared history (`execute-plan-residue.md` § Phase 4 finalize). Record the
   sha where the work landed.
2.5. Run `plan-completeness status "$ARGUMENTS"` (never writes); paste its raw rollup line into
   `exit_criterion_met.prose`. A `CONTRADICTION: ` line carries verbatim into the close-out report; never stamp over it.
3. Re-run `prime_exit_criterion.falsifier.how` against `HEAD`; paste the raw output into `exit_criterion_met.falsifier_output` and judge it against `prime_exit_criterion.falsifier.expected_when_true`, never `baseline_output`. Record `exit_criterion_met.falsifier_verdict` (`pass`/`fail`; changed-but-non-matching is `fail`); the gate refuses the stamp unless `pass`. `fail` → `asserted: false`, Phase-5-halted, no stamp.
3.4. **Bounded EM verification:** a DONE executor is verified by its report plus the step-3 falsifier run; no EM probe scripts or suite re-runs (gaps → `coordinator:test-runner`; `AN-EM-RE-VERIFIES-WHAT-AN-EXECUTOR-ALREADY-VALIDATED`).
3.5-3.6 (`execute-plan-residue.md` § Phase 4 steps 3.4 to 3.7): promote an executable falsifier (`promotion:` + `promoted_to:`; a one-shot is `not-applicable`); on M plans with no BLOCK one criterion-only reader (the roster's `coordinator:exit-criterion-judge`) gets the prime criterion, the plan and `HEAD`, **THE DENIAL LIST EXPLICIT IN THE DISPATCH** (no run reports, sidecars or executor output).
3.7. **Reachability re-check, before the stamp:** the judge's `reachability` block (`review.reachability`, wiki `judge-reachability-check`); else caller-grep at `HEAD`. Unconfirmed → Phase-5-halted, no stamp.
3.8. **`review-stamp mint`, by hand only when `dispatch.land_run` did not report
   `review_stamp: minted`:** `review-stamp mint --plan "$ARGUMENTS" --build-test <wake digest's
   tests.sidecar>` (not required when the spine wrote nothing testable and the criterion is `met`). A refusal is Phase-5-halted: report, skip step 4
   (`A-PLAN-REACHES-IMPLEMENTED-ONLY-THROUGH-A-REVIEW-STAMP`). A review or commit gate halts only per C0 (caused reds); other reds go in the delivery note.
4. `close-out-and-stamp "$ARGUMENTS"` stamps `status: implemented` and commits the plan path, or reports uncommitted chunks and skips the stamp
   (Phase-5-halted); it refuses `implemented` without a `review_stamp` (3.8).

**Offer, stamp-aware.** Stamped `implemented` → offer `/workstream-complete`. Unstamped for **any** reason → offer resolve-and-resume, `/handoff`, or commit-and-stop. Never auto-invoke these or `coordinator:finishing-a-development-branch`
(`AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`).

**A cross-repo leg names its failing conjunct, not its repo** (*undeclared*, *unaddressed*, *unanswered*; `coordinator/snippets/cross-repo-block-exchange.md`; `A-SENT-MEMO-IS-NOT-AN-EXCHANGE`).

---

## Phase 5: When to Stop — PM-Only Emergencies

Complete the plan. Stop only for: **external trust surface change**
(user-visible behavior, privacy, security, billing/onboarding, any
externally-observable contract the plan didn't call out); **plan-invalidating substrate change**
(disk changed since drafting — `/plan`); **scope explosion** (≥3× anticipated size, no 5-15min-chunk decomposition of the
remainder — `/plan`); **unauthorized irreversible action required**
(destructive op, force-push, cross-repo write to a sibling's code, credential write, or
anything gated by `~/.claude/CLAUDE.md` § Executing actions with care); **discovery the plan
would ship something unauthorized** (premise X; it also does Y).

Everything else is an EM decision (ambiguity, structural verification failure via
`/systematic-debugging`, routine errors, wanting to check in):
record `Tried:/Failed:` in the plan doc and `metadata.tried_and_abandoned`; surface a recommendation, not a question.

**Usage-limit advisory** (a pause): dispatch nothing new, let in-flight agents
land, commit scoped, hand off with the reset time, stop (`A-DRIVER-PAST-ITS-USAGE-THRESHOLD-FIRES-NOTHING-NEW`, `usage-limit-pause.md`).

---

## Relationship to Other Commands

Upstream entry is `/handoff` + `/pickup`; `coordinator:finishing-a-development-branch` is reached via `/merging-to-main` (`execute-plan-residue.md` § Relationship to other commands).
