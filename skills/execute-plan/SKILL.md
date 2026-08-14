---
name: execute-plan
description: "Executes a PM-approved plan via dispatched per-chunk executor waves."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: <plan-path>
---

# Execute Plan — End-to-End Plan Execution

Run a PM-approved plan end-to-end to full completion without stopping for permission between
tasks. Plan-frontmatter `execution_authorized_at` is the authorization of record, not chat
history. Does not chain into branch disposition — that's the PM-gated `/merge-to-main`. Full
rationale and mechanics: wiki.

Executing a plan is restructure-then-dispatch, not "type the plan's steps": build the
dispatch-gate graph, decompose into per-chunk dispatches — parallel where gates allow, serial
where they don't, default vehicle a background Workflow. A serial chain is still N fresh
dispatches with EM-verify between, never one long-lived executor. No per-chunk reviewer gate —
EM-serial verify between waves, code review defers to `/workstream-complete`. Dispatched
executors are always Sonnet; self-execute only on a named token-economics carve-out. Invoking
this skill IS the dispatch request. Phase boundaries are not stop boundaries: ship Phase N green,
dispatch Phase N+1 immediately, no checkpoint offer.

---

## Arguments

`$ARGUMENTS` is the plan document path. No path or file not found → report and stop.

---

## Phase 1: Load, Authorize, Review

1. Read the plan in full.
2. `execution_authorized_at` + `execution_authorized_by: PM` present, or `/autonomous` sentinel →
   proceed. Absent otherwise → stop, ask the PM. Then (unless `/autonomous`) confirm the stamp
   still binds to current content via `pickup-assemble stamp-check <plan-path>`: FRESH proceeds;
   STALE-bookkeeping re-stamps via `--append-note` (never `--note`) and proceeds;
   STALE-substantive surfaces the delta and STOPS.
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
Full signal catalog and non-signals: wiki.

---

## Phase 1.5/1.6: Dispatch-Gate Graph and Wave-Map

Claim the plan (`session-claim-cli claim-plan <slug>`) before any gate-graph work — a live peer
holding it means reconcile with them first, never race.

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

Build wave shape from the file-write graph, never the plan's section/theme structure. One
dispatch per chunk — never bundle multiple chunks into one long-lived executor because they
happen to be serial; a serial dependency removes concurrency, not decomposition. Fire the
wave-map by default as a background Workflow, authored as that vehicle's own on-disk input, never
plan-body prose or a chat emission. Full taxonomy detail, malformed-wave checks, sizing rules, and
authoring mechanics: wiki.

---

## Phase 2: Create Flight Recorder

TaskCreate: one session-goal task (objective + plan path), one task per plan phase/major task,
session-goal marked `in_progress` immediately.

---

## Phase 3: Execute All Tasks

Default: execute every task in sequence without stopping to ask. Per task: write-ahead (mark
`In progress` on disk + TaskUpdate `in_progress`) → execute (follow the plan, fix routine errors,
move on) → mark complete (on disk + TaskUpdate `completed`) → proceed immediately, including
across phase boundaries, same session, same flight recorder.

Mid-dispatch decisions are EM decisions — pick, record a one-line rationale inline, continue;
only the Phase 5 list escalates. A resolved fork is not a residual you left behind: a residual (a
site the sweep missed, a fix wider than the AC) needs a closed exit — dispatch it, add a spine
row for the Phase 4 harvest, `coordinator-queue-append --schema
bug-backlog|debt-backlog|improvement-queue`, or take it to the PM. A written reason with no queue
id/spine row/commit behind it is not a routed item.

---

## Phase 4: Finalize and Report

**Precondition:** every wave-map chunk has landed, confirmed via the recovery triple.
Unconfirmed chunks → return to Phase 3.

**Before any cleanup:** `coordinator-harvest-deferrals --plan "$ARGUMENTS"`, surfacing its
`"Queued N ..."` line even on `Queued 0`. A `defer` grouping approval (or legacy
`pm_approved: true`) is a claim of ratification the harvest selects on, not something this step
may stamp — closing a row mid-execution is a scope decision that needs the PM first.

**Commit sequence, two commits, never one:**
1. Land the chunk work in your own scoped commit(s) — explicit pathspec, never `git add -A`. The
   commit MUST carry a `Deliverable-Id:` trailer matching the plan's `deliverable_id` (produced
   automatically via `scoped-git-commit`; a plain `git` commit is silently unattributable at
   close-out).
2. `close-out-and-stamp "$ARGUMENTS"` — stamps `status: implemented` and commits the plan path
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

Default upstream entry is `/handoff` + `/pickup`: review stamps `execution_authorized_at` and
writes an execution handoff. `/enrich-and-review` runs before dispatch when the plan isn't
chunk-ready; `/review-code` is an optional post-execution pass. `coordinator:workstream-complete`
is offered, never auto-invoked, in Phase 4; `coordinator:finishing-a-development-branch` is not
chained here — reached separately via `/merge-to-main`. Full failure-mode table: wiki.
