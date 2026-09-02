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

## Phase 0: Readiness Gate

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
**Risks:** [...]
**Tail:** [standard | hibernate line]
**Estimated scope:** [...]

Proceeding.
```

## Phase 5: Execute

Default: one background Workflow per wave (the Phase 2 DAG), EM commits between waves,
`model: 'sonnet'` on every `agent()`, ≤5 write-capable executors/barrier. Single-wave runs may
hand-dispatch — same wave gate. Verifiers/reviewers dispatch via `Agent`, never inside a Workflow.

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
   Non-PASS → re-dispatch, revert+re-plan, defer, or early-stop.
3. Wave gate: `backlog-grind-assemble apply mise-en-place --wave-path <path>... --granularity
   per-wave --message "mise: wave N — <items>"` over the union of changed paths — never hand-typed
   git. Poll `git branch --show-current` between waves; recovery commits don't advance the chain.
4. "Wave N complete ([items]). Firing wave N+1 ([items])." — never a question.

No worktrees.

## Phase 6: Tail

Mark tasks `completed`, disable the sentinel, then in order: exhaustion check, anti-vacuity gate,
diff freeze, inventory archival (COMPLETE only), tracker sweep.

- **Exhaustion check** (live disposition ledger): COMPLETE if every item terminal
  (PASSed/routed-out/already-fixed/dropped), else CONTINUANCE — wording only, tail always runs
  full. CONTINUANCE → `/handoff` naming the resume invocation, a Phase-0-bypass assertion, the
  wave map — authored+pushed before hibernating.
- **Anti-vacuity:** scoped `git status --porcelain -- <this run's footprint paths>`, never bare
  unscoped. Non-empty → repair via the wave-commit op before freezing.
- **Review routing:** no review gate of its own (PM ruling). Freeze:
  `freeze-review-diff --range "<start-sha>..HEAD" --slice-id "mise-<run-id>"`; name
  `/workstream-complete` or a review-and-cap `/handoff` in the tail summary.
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
| Push fails before hibernate | Do NOT hibernate — stop and report |
| Compacted mid-run | Re-orient via TaskList/TaskGet; check `tried_and_abandoned`; resume `in_progress` |

## Relationship to Other Commands

`/update-docs`, `/workday-complete`, `/merging-to-main` are PM-run afterward, never auto-invoked.
`/autonomous` composes with this run: it governs the unattended posture (sentinel, nudge
suppression), this command governs the backlog sequence — the sentinel is enabled here with
`--mode mise-en-place` precisely so a reader can tell a `/mise` run's sentinel from an
`/autonomous` one.
`pipelines/mise-en-place/PIPELINE.md` carries this sequence at greater depth, where shipped.
