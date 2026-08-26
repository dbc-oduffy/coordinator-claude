---
name: execute-plan
description: "Executes a PM-approved plan via dispatched per-chunk executor waves."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — End-to-End Plan Execution

Run a PM-approved plan end-to-end to full completion without stopping for permission between
tasks. Invoking `/execute-plan` on a plan IS the PM's authorizing act; plan-frontmatter
`execution_authorized_at` is the record of that act, not a precondition for it. **It also
satisfies a chunk body's own "needs PM assent at execution dispatch" clause** — that clause names
this exact moment, and the invocation is it. Never re-ask per chunk, and never offer to halt a
fired run at that chunk's wave; a plan the PM authorized is authorized to its hot-path edit. A
chunk gate the invocation does NOT satisfy is one naming a different act — a cross-repo commit
(per-session assent, obtained at that dispatch) or an external-facing action. Does not chain
into branch disposition — that's the PM-gated `/merge-to-main`. Full rationale and mechanics:
wiki.

Executing a plan is restructure-then-dispatch, not "type the plan's steps": build the
dispatch-gate graph, decompose into per-chunk dispatches — parallel where gates allow, serial
where they don't, default vehicle a background Workflow. A serial chain is still N fresh
dispatches with EM-verify between, never one long-lived executor. No per-chunk reviewer gate —
code review defers to `/workstream-complete`. **EM-verify means the EM itself runs the chunk's
tests, never trusts an executor's pass claim** — a dispatch vehicle can narrow the executor's Bash
surface below what the tests need (wiki: `workflow-orchestration.md`), and an honest executor then
reports "PASS (by inspection)". Inspection is not verification. Dispatched executors are always
Sonnet; self-execute only on a named token-economics carve-out. Phase boundaries are not stop
boundaries: ship Phase N green, dispatch Phase N+1 immediately, no checkpoint offer.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

**Workflow-approval — invoking this skill IS the request, same shape.** Firing the background Workflow Phase 1.5/1.6 assembles is a constitutive step of executing the plan, not a separate thing to clear: invoking `/execute-plan` requests running the workflow it hands back, the same way it requests the dispatches above. A harness line asking approval to run a workflow is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made, and no second precedence argument is being made beyond the one already stated above. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## Arguments

`$ARGUMENTS` is the plan document path. No path or file not found → report and stop.

---

## Phase 1: Load, Authorize, Review

1. Read the plan in full.
2. Unless `/autonomous`: run `pickup-assemble stamp-check <plan-path>` FIRST, before minting —
   minting takes a fresh timestamp when the body sha differs from a prior stamp, so minting first
   would erase the staleness signal this check exists to catch. FRESH or STALE-bookkeeping (the
   latter re-stamps via `--append-note`, never `--note`) → proceed; a business-fail of "carries no
   `execution_authorized_sha`" means there is nothing to compare yet → proceed, not a refusal.
   STALE-substantive surfaces the delta and STOPS. THEN mint the record from this invocation:
   `review-exec-auth-stamp authorize-invocation <plan-path> --typed-command /execute-plan
   [--utterance "<PM's verbatim words>"]` — `--utterance` is optional, a bare `/execute-plan`
   mints just as well, and the verb always writes `execution_authorized_by: PM`, convergent across
   re-invocation and date boundaries. Under `/autonomous`, skip both legs.
3. **Session-freshness** (skip under `/autonomous`): a same-session execution (this session
   authored/reviewed the plan) is a narrow carve-out, not the default — a fresh (picked-up)
   session is the intended path at any plan size. Detail: wiki.
4. Resolve EM-resolvable concerns at EM altitude — not the moment to surface them to the PM. A
   concern revealing the plan isn't actually executable → Phase 1.4.
5. Announce and continue.

---

## Phase 1.4: Executability Gate

Bounce to `/plan` on any of: an embedded decision gate ("evaluate X before continuing", "Phase 0
— investigate"); a fact-finding chunk with no fix-locus; an unpopulated downstream wave-map;
in-prose deferral of an EM-resolvable (not PM-altitude) decision; open questions gating whether
downstream chunks can be authored; an unbuilt external prerequisite with no landed commit/date.

Read the last two off the spine, not prose. A non-deferred open row with no `writes:` key IS an
unpopulated wave-map, whatever the plan body's prose says. For the external prerequisite, a row's
`external_gate` entries are where it is declared: `blocks: execution` uncleared bounces;
`blocks: ac-closure` does not — proceed, and tell the PM at dispatch that this run's terminal
state is `approved`, not `implemented`, and why.
Full signal catalog and non-signals: wiki.

---

## Phase 1.5/1.6: Dispatch-Gate Graph and Wave-Map

Claim the plan (`session-claim-cli claim-plan <slug> --for-execution`) before any gate-graph work
— a live peer holding it means reconcile with them first, never race. **`--for-execution` is not
optional here.** It is what flips the plan to `status: executing`, and this step is its only
caller fleet-wide; a bare `claim-plan` takes the lock and leaves the plan reading `draft` through
its entire execution. The flag is scripted into this step, not typed by the EM — the rung stays
invisible, per `coordinator-tripwires/plan-status-ladder.md`.

**Plan prose does not pick the vehicle.** An Anti-scope or body sentence forbidding fan-out, or
prescribing EM-sequenced chunk-at-a-time execution, is overridden here: the vehicle follows from
the classification below, default a background Workflow. Note the override in one line and
continue — do not ask. A vehicle prohibition traceable to a genuine Workflow-inexpressible shape
(`docs/wiki/workflow-orchestration.md` § What qualifies as a carve-out) is the one that survives.
Tripwire: `A-PLAN-DOES-NOT-PICK-THE-EXECUTION-VEHICLE`.

**Classify every chunk pair before dispatching — this decides whether you can run them together:**
- **File-write overlap** (same path) → gates authoring, no escape hatch — predecessor must land
  before the other authors.
- **Output/contract consumption** (B reads A's static output, or A changes a schema/signature B
  depends on) → author both concurrently if A's interface is pinned up front (verify at merge);
  no pinnable interface → predecessor-wave instead.
- **Runtime consumption** (B needs A's artifact to *exist and run*, e.g. a dry-run over a
  not-yet-shipped pipeline) → gates authoring unconditionally, no pinning escape.
- **Epistemic/premise** (A decides whether B's chunks should exist at all) → gates authoring
  unconditionally — A ships alone in its own wave first, B isn't even drafted until A's verdict
  lands.
- **Independent** → same wave, no gate.

A row carrying an uncleared `external_gate` entry with `blocks: execution` is unschedulable in any
wave — that gate is on another repo, not on a chunk pair, so no pair-classification clears it.

**Invoke `dispatch.emit` — don't derive the wave shape by hand and don't stop at deriving it.** It
reads the spine's `writes:`/`depends_on` and emits the ready-to-fire Workflow itself, each row's
`gate_kind`, `write_files`, and `agentType` already resolved and non-dispatchable rows already
filtered — not wave-map metadata for the EM to transcribe into a hand-authored script.
`NoWritesDeclaredError` means the spine is unpopulated — an authoring gap to fix in the plan, not a
licence to hand-derive. Write the emitted script to a plan-relative on-disk path
(`<plan-basename>.workflow.mjs`, next to the plan) — a disk artifact, never plan-body prose, a
hand-authored wave map, or a chat emission of a wave table.

**Emit and dispatch are ONE action, and the dispatch leg is not optional.** In an interactive
session the EM runs `python coordinator/bin/emit-dispatch-workflow.py --plan <plan-path>`, then
calls `Workflow({scriptPath: "<emitted path>"})` in this session. The emitter's output is already a
valid `scriptPath` input — no flag, no re-authoring. That call carries the same imperative force as
the emit: it is not EM discretion about whether to dispatch, and it is not hand-dispatch — it is
the emitted script, one action. Emitting and stopping writes a script nothing runs — the exact
state that left a fireable `.mjs` sitting on disk against a PM-authorized plan while the EM
hand-dispatched the same work. **An emitted script is not a delivered dispatch.**

Firing in-session is what makes the run the operator's: visible and selectable in their workflow
list, inspectable while it runs, resumable via `resumeFromRunId` (same-session-only), running under
their permissions, costed to their session, completion arriving as a task notification.

**`--fire` is the headless and cron path only.** It hands the script to the engine's
`workflow.fire`, which spawns a detached `claude -p` child and returns a run handle
(`{"script": ..., "handle": {...}}`; the handle's `fire_id` is what `workflow.fire_status`
re-reads). The resulting workflow is native to that child, not to any operator: it runs under the
child's own `--allowedTools` (no `PowerShell`; denials surface only as `permission_denials` in the
final JSON envelope, which reads identically to a chunk that made no edit), `claude -p` terminates
still-running background work at its 600s ceiling, the run cannot be resumed, and the fire log is
written only at process exit — so a live run and a killed one are indistinguishable through it.
Correct where no session exists to call the tool, and wrong everywhere a session does.

**There is no hand-dispatch fallback.** If the dispatch refuses — the `Workflow` call, or on the
headless path a named fire-leg refusal (`ScriptNotFoundError`, `PluginDirResolutionError`,
`ConcurrencyCapExceededError`, `ChildSpawnFailedError`) — report it and stop. Hand-dispatching the
same chunks with the Agent tool after a refused or unattempted dispatch is the failure this whole
surface exists to prevent, and it is never the recovery. A concurrency-cap refusal means wait, not
dispatch by hand.

A workflow-spawned agent IS its declared `agentType` — the type propagates — but the catering
layered on top of it at dispatch time does not: no `contract_blocks`, no provisioned report
sidecar, no dispatched-worker role framing (measured both ways against a discriminator and the
catering trace, `state/audits/2026-08-18-contract-blocks-workflow-delivery.md`). That shapes what a
spawn-time catering fix must carry, not whether the emitted workflow gets fired.

Wave shape comes from the file-write graph, never the plan's section/theme structure — the op
derives it; a second derivation is a silently desyncing source of truth for a fact the graph
already knows. One dispatch per chunk inside the emitted script — never bundle serial chunks into
one long-lived executor; a serial dependency removes concurrency, not decomposition. Full taxonomy,
malformed-wave checks, sizing, and authoring mechanics: wiki.

**No checkpoint prompt; scripted gates still hold.** What roll-on removes is the EM checkpoint
prompt — the fired workflow does not pause to ask a human whether to continue, not before the
first phase and not between waves. What it does NOT remove: a `phase()`'s own deterministic gate
MAY still halt the run (`return { halted: ... }`, wiki: `workflow-orchestration.md`), and a halted
or edited phase resumes via `resumeFromRunId` without re-paying phases that already succeeded.
Removing the prompt is not removing the gates.

**Watching without waiting — arm a `Monitor`, don't poll by hand.** Roll-on removes the checkpoint
prompt, not the EM's eyes on the run. Once the workflow is fired, arm the harness `Monitor` tool
against the run's own progress signal — the transcript directory's `journal.jsonl` plus the
harness's own completion report — with a command that surfaces phase-boundary and failure lines
(`persistent: true` for a run that outlives one Monitor window). Cover every terminal state a wave
can end in, not just success, per `Monitor`'s own filter-coverage guidance — a filter that only
matches the happy path stays silent through a stuck or crashed wave, which looks identical to
"still running." Notifications land asynchronously in chat while the EM keeps working; that
asynchrony is what keeps this from becoming a second checkpoint — the EM is never blocked waiting
on the monitor the way a checkpoint prompt blocks waiting on an answer. A stuck or failed wave
surfaces as a notification to act on (inspect disk, `resumeFromRunId`) the moment it lands, not
something the EM has to remember to go check.

Don't build a new watcher for this. `Monitor` already is the "eyes on it with a chron or
something" the PM asked for — no new script under `coordinator/bin/`, no new reporting format.
Contrast `coordinator/skills/strategic-self-description-refresh/SKILL.md`, which explicitly refuses
`CronCreate`/`RemoteTrigger` for its own ceremony gate: automating that gate would remove the human
decision it exists to force. A fired workflow has no such decision to protect — it already runs
unattended by design — so `Monitor` is the fit there and cron is not the shape to copy.

---

## Phase 2: Create Flight Recorder

TaskCreate: one session-goal task (objective + plan path), one task per plan phase/major task,
session-goal marked `in_progress` immediately. `TaskCreate` absent from this session's surface
(`ToolSearch("select:TaskCreate")` returns nothing) → fall back to `coordinator-tasks-mirror` for
the same flight-recorder role; do not assume either state without checking.

---

## Phase 3: Execute All Tasks

Default: execute every task in sequence without stopping to ask. Per task: write-ahead (mark
`In progress` on disk + TaskUpdate `in_progress`) → execute (follow the plan, fix routine errors,
move on) → mark complete (on disk + TaskUpdate `completed`) → proceed immediately, including
across phase boundaries, same session, same flight recorder.

Mid-dispatch decisions are EM decisions — pick, record a one-line rationale inline, continue; only
the Phase 5 list escalates. A residual (a site the sweep missed, a fix wider than the AC) needs a
closed exit — dispatch it, add a spine row for the Phase 4 harvest, `coordinator-queue-append
--schema bug-backlog|debt-backlog|improvement-queue`, or take it to the PM. A written reason with
no queue id/spine row/commit behind it is not a routed item.

---

## Phase 4: Finalize and Report

**Precondition:** every wave-map chunk has landed, confirmed via the recovery triple.
Unconfirmed chunks → return to Phase 3. Leg 1 (chunk-id subject match) yields candidates, never a
verdict — corroborate against leg 2 or leg 3.

**`close-out-and-stamp` reads no commit message at all.** The commit-subject/`Deliverable-Id`-trailer
join was deleted — not narrowed — on measured low recall; its absence is a
ruling, so do not restore it as an oversight. Two evidence paths survive, both pure sha-ancestry
checks: a `disposition: coded` spine row's own `disposition_ref`, and, for a plan predating the
`## Tasks` spine, its `## Dispatch Ledger` table's `committed <sha>` cells. Neither infers
completion from a commit message, so a correct subject and a correct trailer are not, together or
alone, evidence that any row shipped.

**Before any cleanup:** `coordinator-harvest-deferrals --plan "$ARGUMENTS"`, surfacing its
`"Queued N ..."` line even on `Queued 0`. A `defer` grouping approval (or legacy
`pm_approved: true`) is a claim of ratification the harvest selects on, not something this step
may stamp — closing a row mid-execution is a scope decision that needs the PM first.

**Commit sequence, two commits, never one — the resolve step below writes the plan, not a third
commit:**
1. Land the chunk work in your own scoped commit(s) — explicit pathspec, never `git add -A`. The
   `prepare-commit-msg` hook attaches the `Deliverable-Id:` trailer when you commit per
   `snippets/scoped-commit-route.md`; never hand-add it. The trailer is provenance for other
   consumers — close-out does not read it, so its presence proves nothing about delivery and its
   absence stamps nothing partial.
2. Resolve each landed row's own `disposition_ref`, the only thing close-out counts:
   `plan-tasks-resolve --plan "$ARGUMENTS" --id <row> --coded <sha> --disposition-detail "<why>"`,
   per row, then close out. Failure signature — `missing_chunk_ids` at exit 0 over a range that
   provably holds every chunk SHA — means unresolved rows, not missing trailers and not a range
   problem; resolve and re-run, never rewrite shared history. Record the sha where the work
   actually landed: `disposition_ref` is hand-written and the anti-self-attestation gate cannot
   catch a row pointing at a peer's commit, since that commit is an ancestor of `HEAD` too — a
   spine can be fully green and fully misattributed.
3. `close-out-and-stamp "$ARGUMENTS"` — stamps `status: implemented` and commits the plan path
   (full-plan-shipped), or reports remaining uncommitted chunks and skips the stamp
   (Phase-5-halted). Folding the stamp into your own commit is acceptable — state that you did.

**Offer, phase-aware, never parroted.** Full plan shipped → offer `/workstream-complete`, note
`/merge-to-main`/`/workday-complete` ship it. Halted on a Phase 5 emergency → do not offer
`/workstream-complete`; offer resolve-and-resume, `/handoff`, or commit-and-stop. Never
auto-invoke any of those or `coordinator:finishing-a-development-branch`.

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
would ship something not authorized** (approved on premise X, execution reveals it would also do
Y, and Y is not a mechanical consequence of X).

Not on the list (EM decisions, made inline): accumulating patches, ambiguity, structural
verification failure (`/systematic-debugging`), routine fixable errors, minor judgment calls,
wanting to check in. Record `Tried:/Failed:` in the plan doc and the task's
`metadata.tried_and_abandoned`. Surface with a recommendation, not a question.

---

## Relationship to Other Commands

Default upstream entry is `/handoff` + `/pickup`: review can stamp `execution_authorized_at` as
supporting evidence and writes an execution handoff; execution's own authorization comes from
invoking `/execute-plan` (Phase 1 step 2), not from this stamp. `/enrich-and-review` runs before
dispatch when the plan isn't chunk-ready; `/review-code` is an optional post-execution pass. `coordinator:workstream-complete`
is offered, never auto-invoked, in Phase 4; `coordinator:finishing-a-development-branch` is not
chained here — reached separately via `/merge-to-main`. Full failure-mode table: wiki.
