---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work. No handoff — this is for work that's *done*.

> **Mutual exclusion with `/handoff`.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP, use `/handoff`. Two workstreams (one done, one live) → end each separately, naming which. Exception: the review-owed-close class (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4) → the trampoline, § Resolve judgment points.

This ceremony is computed end to end — session-shape, plan reconciliation, lessons, completion-entry, memo lifecycle, scratch self-clean, orientation refresh, and commit-tail ship as `directives[]`; what cannot be resolved ships as `judgment_points[]`. Never recompute by hand what a field already answers.

`$ARGUMENTS`, if given, fold into Final Summary and completion-entry prose.

**Turn 4 of the four-turn loop (sizing, plan, execute, workstream-complete), every mode (hands-on, pm, ceo).** Fires in the same EM turn as `dispatch.terminal_commit`, after the PM accepts the execute digest. It never commits the run's product changes — the terminal commit already landed them; this is bookkeeping (plan status, lessons, docs, commit/merge hygiene, handoff). The § Final Summary one-line-plus-exceptions output IS the `close` wake digest: verdict → `outcome`, exceptions → `decision_required` and `deviations`.

---

## Compute the ceremony

Shown in Shape W (PowerShell, rung 0). POSIX hosts take Shape A/B — ladder/shapes:
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

`& "$env:COORDINATOR_SETTINGS_HOME\bin\workstream-complete-assemble.exe" brief [--decisions-file <path>]`
**Prefer `--decisions-file` on both subcommands; `--decisions '<json>'` is the short-payload
convenience.** A real payload carries prose (completion rationale, commit subject, review records),
and prose on argv is mangled by the tool seam. Supplying both channels at once fails loud.

Returns `artifact`/`preflight`/`gates`/`directives`/`judgment_points`/`decisions`/`narration`/`next_move`. `preflight.session_shape` (= `gates.session_shape`) carries `sid`, `disposition` (`single-session`/`predecessor-consumed` — reads backward: consumed a predecessor, not that a successor follows), `consumed_handoff`, detector diagnostics. `jp-session-shape` is the untrusted-gate point for an uncertain resolution.


---

## Genuine EM actions — no directive can perform these

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

- **Execution-observations fold**: read each sidecar's `divergence` as quoted narrative, never EM-authored prose; surface a crashed-executor marker before deleting it. A `## Tasks`-spine plan cites `plan-completeness status <plan-path>`'s divergence rollup (with its non-conformant count) instead of per-chunk sidecars; a pre-spine plan reads sidecars.
- **Memo-resolution / self-clean disposition**: no signal says which memos resolved or which scratch to keep — decide once, plain prose; evidence is surfaced, never picked.
- **Session Ledger row append** (predecessor-consumed only): one row to the consumed handoff's `## Session Ledger` , the sole edit `/pickup`'s frozen-body rule carves out, via the `handoff.append_session_ledger` op, never hand-typed.
- **Prime exit criterion assertion**: a run-stamped plan already carries `exit_criterion_met`; verify it, never recompute. Absent blocks; clear it by the re-judge route (terminal-judge § Closing a plan whose run judged `not_met`). `asserted: false` routes to `/handoff` or a Phase-5 halt. [terminal-judge](../../docs/wiki/reviewer-pipeline/terminal-judge.md); `A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`.
- **Terminal-baton drain — MANDATORY, and the last thing this ceremony does.** No directive
  performs it and nothing downstream catches the miss.
  1. Hand-stamp `deployment_state`/`shipped_in` on **only** the two batons § Apply's carve-out
     omits from the payload; **never re-stamp one the payload already stamped.**
  2. **After** `apply`'s own disposal read — once every payload-stamped and
     hand-stamped baton carries a terminal `deployment_state` — run
     `sweep-terminal-handoffs` (idempotent no-op when nothing moves; also
     drains other sessions' terminal residue).
  3. **Check the close condition: `state/handoffs/` holds no record carrying a terminal
     `deployment_state`** (`shipped`/`continued`/`closed` —
     `HANDOFF_TERMINAL_DEPLOYMENT`; `declined`/`superseded` are sizing-object and retired-handoff
     `status` values, never `deployment_state`) **when this ceremony reports complete.** Never
     defer the drain to the next ceremony.
     <!-- enum-prose: schema=handoff field=deployment_state omit=awaiting_gate,ready_to_fire,in_flight -->

  `[[terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony]]`
- **Kira-routing enforcement is mechanical:** `coordinator/hooks/scripts/guard-kira-verdict-routed.py`, a `stop-dispatch.py` `StopGuard`, blocks the next turn end once on an unrouted Kira verdict and surfaces the owed route. Tripwire: `KIRA-ROUTING-IS-STAMPED-NOT-REMEMBERED`.
- **An idle subagent has not failed.** Recover a review that never delivered its verdict from its transcript under `subagents/` (`stop_reason: end_turn` = finished); never replace it with `em-verified`, which overwrites an independent finding. `AN-IDLE-SUBAGENT-HAS-NOT-NECESSARILY-FAILED`.

---

## Resolve judgment points

**The discriminator: a judgment point earns its place only if a different competent EM, with the
same artifacts on disk, could reasonably answer it differently.** `A-FACT-WITH-A-CLOSED-ENUM-IS-NOT-A-JUDGMENT-POINT`.

**3 classes.** 1 = CLI-computable (not listed here). 2 = interpretation, but not *this EM's* — the passage already specifies the inputs and closes the output enum, so a differing answer is demonstrably wrong; demote when a path exists, else carry it as a judgment point by necessity, named as such. 3 = judgment/taste/tradeoff — two competent EMs can disagree and both be right. Never author a class-2 fact as a judgment point. A re-test names a class per item it **keeps**, not only those it demotes. Calibration (`completion-nature-classification` is class 2; `finding-tradeoff-escalation-check` stays class 3): `coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md`.

**A shipped `recommendation` is applied by default and shown, not asked** — carry it into the decisions map and report what was filed (`completion-nature-classification`/`jp-coverage-verdict` both ship one). A null matters only when genuine: `jp-session-shape` always, tail-blocking scaffold/commit-subject/consumed-handoff when they fire. Blocked computation or a missing producer is a break-class engine defect — resolve cheaply or memo, once confirmed absent.

**`jp-session-shape` is honoured by the tail but a re-`brief` still shows the original detector verdict** — confirm from `apply`'s output, never re-`brief`, never re-answer or reach for `override-known-in-flight`.

**The rest — read the object.** Unnamed points carry their own prompt/evidence on `judgment_points[]`.

**Completion entry:** TITLE + ≤8-sentence body, banned sections `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria`, `## Universal lessons captured`. With run receipts, `d-complete-entry` scaffolds a meta-entry with `receipts` (`commits`,`loe` derived); write only title/prose/nature, never receipt fields (`completion-receipts.md`).

**Review — 4 class-3 survivors, none demotable:** `shared-schema-touch-check`, `governing-spec-identification`, `finding-tradeoff-escalation-check`, `shallow-row3-waive-check` (`coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md` § Review class-3 survivors). The other four named there (`review-partition-strategy`, `reviewer-count-on-oracle-disagreement`, `review-dispatch-vehicle-choice`, `quota-retry-vs-escalate`) belong to the execute workflow's review stage (`coordinator/skills/execute-plan/SKILL.md`, `review-brightline-gate`), not this ceremony.

**Verify once and trust it:** a close-time suite or oracle check runs once, foreground — no rerun loops or background waiters (`coordinator/docs/wiki/test-design-discipline.md` § Verify once and trust it).

**L+ code-quality trigger — a separate derivation, not a parameter on Scale's measurement.** Scale
keys off *measured* `gross_loc`/`commit_count`/`surface_count` (`commit_count` excludes zero-diff bookkeeping commits; `surface_count` counts all); L+ answers *how big was this meant
to be* and keys off the **cited sizing-object's `estimate.tshirt`** — resolve the closing plan's
`sizing_object:` frontmatter citation and read `estimate.tshirt` off the artifact it names. `plan.schema.json`
carries no t-shirt field and none is added here. Fires at `L` or `XL`. Never use Scale's measured
computation to answer it.

**The review record is the plan's `review_stamp`, not something this ceremony runs or dispatches.**
For a plan-bearing close, code review already ran and integrated as review stages of the emitted
execute-plan workflow; `review-stamp mint` recorded the outcome on the plan, via `terminal_commit`
(never re-minted by hand), before this ceremony starts; `gates.review_receipt` reads that
`review_stamp` (MK2). Where that stamp exists, this ceremony reads the gate and writes no trail.
**Review absent at close → this ceremony dispatches review; there is no skip.** A close with no
governing plan, or a plan whose `review_stamp` is missing (a mise-en-place landing included), runs
`/review-code` over the close's diff before `apply` — at least one reviewer, partitioned when the
diff is PARTITION-MANDATORY. Never dispose the gap with `proceed-unresolved` or any other skip; an
absent review is not an EM confirmation to give. The terminal-review Stop gate still holds
regardless of route.

**Hand-measuring the brightline is a last resort** — only once `stage_paths` is supplied and `review_scale` still returns `resolved: false`. **Sum per-owned-commit diffs** (`<sha>~1..<sha>` — `~1`, never `^`, which cmd.exe eats), **never an `oldest..newest` range** (a shared branch adds every peer commit), and **count code only** (`.md`/`.yaml`/`.yml` excluded). Method and evidence: `coordinator/docs/wiki/ceremony-calibration/workstream-complete-review.md` § Hand-measuring the brightline.

**The trampoline — hand the whole ceremony to a fresh session rather than cap with the review unrun.** Low
context is not a trigger-4 reason; it takes the ordinary `/handoff` route. When the owed review is
genuinely un-runnable here (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4 — a ratified
closed class, never admitted by analogy), exit via `/handoff` naming which member fires and the
event outside this session's reach that clears it.

**Capping with the review unrun is forbidden; `verdict: pending` is not the escape hatch.** Tells to trampoline instead: "the next session can review this"; `reviewer: waived` paired with a non-`waived` verdict; a range narrowed because the honest range was refused; "mandatory" reasoned as advisory. Tripwire: `PARTITION-MANDATORY`.

**A chain-ancestry waiver is provenance, not review discharge — it does not clear a HALT.** `certifies_review: false` reads "ancestry NOT reviewed," and re-running does not clear it either. Tripwire: `WAIVER-IS-PROVENANCE-NOT-DISCHARGE`.

---

## Concurrent-EM shared-branch disposition

**Case (c) is not always an orphan** — often a live peer's in-flight files. `brief` classifies
a/b/c mechanically and surfaces the peer-vs-orphan call as `concurrent-peer-attribution`;
disposing case (c) is EM judgment; weak signals default to case (c).
**If a peer is plausibly live, never adopt their paths** — commit only your own files by
explicit path. Once ruled out, take exactly one, never leaving case-(c) files dirty and
unnamed: **commit** with provenance (per `snippets/scoped-commit-route.md`), or **leave it
explicitly owned by X**. Never `git stash`: it captures every peer's work. Orphan `.tmp.<pid>.<nanos>` files are Edit-tool crash
artifacts: diff before deleting.

---

## Apply — execute the directives

`& "$env:COORDINATOR_SETTINGS_HOME\bin\workstream-complete-assemble.exe" apply --decisions-file <path>` — the file is a JSON
object whose keys are *either* a `judgment_point_id` (value `{"disposition": "<value>"}`) *or* one of the non-JP decisions keys (`stage_paths`, `review`, ...), each with its own flat shape. **Never wrap a non-JP key's value in a `{"disposition": ...}` envelope** — a nested `{"disposition": [...]}` for `stage_paths` reads as the key being absent. `stage_paths` is a flat list: `{"stage_paths": ["<path>", ...]}`.

`decisions` carries what the compute half can't read off disk — lessons, completion-nature/prose, memo/scratch dispositions, commit subject/prose.

**`handoff_dispositions` is another non-JP key**, `{"<handoff-basename>.md": {...}, ...}` — one entry per baton this close disposes, each value an **object**, never a bare string (`"shipped"` alone is dropped, not coerced). All four consumer-resolved values are carried: `shipped` (with `shipped_in`, below); `closed`/`abandoned` (each with `closed_reason` from `cancelled`/`displaced`/`stale` — **never defaulted, never fabricated**; anything else, however well-written, is refused); `continued` (neither field).

**`shipped_in`:** one full-length sha per baton — the last commit in this session's own owned-commit list (sliced `<sha>~1..<sha>`, never `oldest..newest`; no code-only filter) touching the `writes:` paths of the plan spine whose `deliverable_id` matches the baton. Never a range, PR ref, list, or the close's own commit-tail sha. No such plan or commit → not `shipped`: `closed` (with `closed_reason`) or `continued`, never a placeholder.

**An entry is silently dropped** unless it is an object, this session holds the claim, and the record is still active under `state/handoffs/` at `apply`; the leg also needs `decisions.subject`.

**Omit the baton in exactly two states:** (1) the deliverable is carried only by the close's own commit; (2) the record was already archived (e.g. `/handoff` supersession). Any stamp still owed is the residual hand route (§ Genuine EM actions). Every other `closed`/`abandoned`/`continued` baton is emitted.

Order is transition, dispose, archive: `continued` needs `deployment_state` already `continued`; disposal is refused once the record left `state/handoffs/`. Full rules: `coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md` § Handoff-disposition payload rules.


**`apply` commits — `_run_close_commit_tail` is not optional.** It runs after `_execute_directives`, gated only on a `decisions.subject` (and `sid`), folding the `handoff_dispositions` ship-stamps into its `stage_paths`. **Never read `apply`'s exit as leaving nothing landed.** Then, still yours:

- **Scoped commit** of the completion entry, Session Ledger row, and your own files, per `snippets/scoped-commit-route.md` — a **second** commit after `apply`'s own close commit, never carrying the stamps.
- **Nothing** — for a plan-bearing close, the review record is the plan's `review_stamp`, minted
   before this ceremony ran; confirm `gates.review_receipt.blocks` is `false` and name any gap in
   the summary. Where review was absent, the `/review-code` dispatch above already ran before
   `apply`.

**`apply` runs the post-close steps itself, after its close commit — never by hand:**
`d-baton-chain-closure`, `d-structural-index-refresh`, `d-ceremony-reindex`, then a release of
every touch claim the session holds. Read outcomes off `post_close[]`; `scip-rebuild: skipped -- <reason>` is the box declining.

**A run-stamped plan already carries `implemented`; the ceremony verifies it, never restamps.** Where `terminal_commit` did not stamp, `d-stamp-plan-implemented` is gated engine-side (a blocked stamp is not a failed one) with three empty-`resolves` judgment points on its `depends_on`: `jp-open-spine-rows-block-stamp` (unwaived `open` rows, or `indeterminate`), `jp-landed-reconciliation-block-stamp` (plan `landed` with unticked ACs), `jp-review-receipt-block-stamp`. An unresolved one lands in `report["blocked"]` under `HALTED_AT_JUDGMENT`, not `report["failed"]` — a close exits non-failing with no stamp. `waived_open_spine_row_ids` clears leg 1's `applicable` arm only. Never build a doctrine gate beside these. Tripwire: `AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`.

**A stamp line can carry a failed archival move** (`N of M moves failed`): move the remainder, or the plan's `.workflow.mjs`/`.emitted.json` sidecars stay orphaned.

`apply` prints diagnostics on every non-zero exit — read them, don't memorize codes. Exit `2` (`DIRECTIVE_FAILED`) = nothing landed; exit `4` (`PARTIAL_MUTATION`) = some landed, some failed. A client-side timeout is no failure signal: reconcile against commit state before re-running.

Push runs on a cadence, not on this commit: `push_status` `"cadence-pending"`, `"pushed"` and (older engines) `"deferred"` are all success — the branch publishes at the next named checkpoint (`/pickup`, `/quick-wrap`, `/workday-start`, the workday/workweek closes). Only `"deferred"` wants confirming, via `git branch -r --contains <sha>`. **Never `git push` to "fix" an apparent delay.** Unfamiliar string: `commit_pipeline.py`'s `PUSH_STATUS_*` block.

---

## Execution-Residual Sweep (judgment step — nothing computes it)

A residual discovered mid-execution never counts in the harvest — `Queued 0` reads as "nothing left behind." One disposition per item; nothing to sweep is ordinary — omit the line. **Default is fix it now**; routing elsewhere costs a named reason from a closed class: `peer-contention`, `other-repo`, `own-plan`, `irreversible`, `not-real` — in full, `coordinator/docs/wiki/ceremony-calibration/workstream-complete-review.md` § Execution-residual reason classes. A break-class residual with none of the five is fixed, not filed. The auto-memory drain gate runs only at `/workday-complete`/`/workweek-complete`, never here.

**Spinoff overlap re-check, same step.** `/pickup`'s no-overlap reconcile is point-in-time; a peer may have forked a handoff for the same scope since. Before reporting complete, for every open (`kind: spinoff`) handoff this session or its chain authored, run <!-- VERBATIM -->`git log --since=<its authored-at> -- <its named scope/paths>` against `state/handoffs/` and the scope paths. A hit means the scope landed since the fork — surface it to the PM as a `superseded`/`consumed` candidate. No hit is ordinary — omit the line. `coordinator/docs/wiki/ceremony-calibration/workstream-complete-review.md` § Re-check for overlapping peer spinoffs at workstream-complete.
---

## Completion verdict

**Consume `gates.completion_verdict` in the close narration.** It composes the five gates this
ceremony reads (`session_shape`, `review_receipt`, spine-row completeness, plan-landed
reconciliation, consumed-handoff completeness) into one verdict — read it off `gates`, never
hand-derived.

**It is not a pass/fail lens.** `indeterminate` is the ordinary case — 3 of the 5 gates on a
typical close — so **render it as `indeterminate`, never as "incomplete"**, naming only the ones a
gate-specific reading says are worth naming. `applies: false` is not a uniform status axis across
gates; readings and the non-PM-facing `review_scale`-exclusion objection:
`coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md` § Reading `gates.completion_verdict`.

**Residue → verb lookup, for whatever the verdict leaves outstanding:**

| Residue shape | Verb |
|---|---|
| Blocked on further work this session should still finish | trampoline (`/handoff`) |
| Not worth doing | won't-do |
| Worth doing, not now | backlog |
| A distinct workstream someone else should pick up | spinoff |

---

## Final Summary

**Report by exception.** One line always; everything else only when *not* clean. A Group EM
session additionally follows `coordinator/snippets/group-em-output-contract.md` — one emission
form only (a decision awaiting the PM), offers/self-labelled-optional asks excluded, filtered at
source, never appended at the end.

**A baton shipping here can newly close its whole chain.** Relay `d-baton-chain-closure`'s `post_close[].output` when it carries one; it is silent unless the chain fully resolved, and its output already conforms to `group-em-output-contract.md`. Never run `chains` here (diagnostic, not PM-facing).

**A leg parked as blocked on a sibling repo carries its exchange, or it is not parked.** Check
the three conjuncts in `coordinator/snippets/cross-repo-block-exchange.md` — declared, addressed,
answered — name the one that failed, never the repo. Tripwire: `A-SENT-MEMO-IS-NOT-AN-EXCHANGE`.

```
## Session Complete

**Work done:** [1-2 sentence summary]
```

Append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Completeness checklist:**` | `gates.completeness_checklist` WARN — name the N unverified items |
| `**Consumed-handoff completeness:**` | element reports `blocks`/`indeterminate` — name handoff+leg (`not-applicable` is a 4th leg-A verdict, NOT reported) |
| `**Deferral harvest:**` | N ≥ 1 queued |
| `**Execution residuals:**` | sweep resolved ≥1 item — `<residual> -> fixed <sha>` or `-> <queue id \| memo \| spine row> (<reason-class>: <clause>)` |
| `**Post-summary reconcile:**` | commits were folded |
| `**Pushed:**` | the push did **not** land — `deferred`/`detached` is success and stays silent |
| `**Publish lag:**` | `compute_publish_lag_advisory` reports a lag worth naming — silent when clean |
| `**PM ask:**` | the closing plan resolves ≥1 PM verbatim — one line, `pm-brief render <closing-plan>` names each ask, then `met` or the residue verb from § Completion verdict; read via the plan's own `sizing_object`, never by scanning `state/sizings/` (`A-ROUTED-SIZING-IS-NOT-A-LIVE-ASK`); all-met collapses to one `met` |
| `**Flag to PM:**` | a direction-class item survived severity classification below |

**`not-applicable` is not `indeterminate`.** `not-applicable` = nothing to look at (e.g. a `session-handoff` leg A finds no live plan) — silent, like `clean`. `indeterminate` = the gate tried and couldn't — report it. Tripwire: `NOT-APPLICABLE-SPANS-TWO-SILENCES`.

**Do not print** `Lessons captured`/`Work archived`/`Docs updated`/`Orientation refreshed` — counts the commit already records, not PM decisions. **An automated mechanism's routine success is never a PM line**: report the machine only when it *failed*. **Archival is NOT in that set — not automatic; this ceremony emits NO archival directive.** Disposal is not archival: the record stays under `state/handoffs/` until the drain moves it, a mandatory EM action (§ Genuine EM actions), never a machine step. Never author a second sweep beside the drain. Backstop: `coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md` § Archival is not automatic.

**Classify flags by severity first.** A break-class defect (broken/would-break/fails/leaks/silently-bypasses) is fix-by-default — fix it, report the fix, never a passive `Flag to PM:`; only direction-class items go there. → global `CLAUDE.md § Flag Severity`.

---

## What this does NOT do

- Rebuild the Step-0 session-shape gate, the coverage judgment point, or `resolve_repo_root`.
- Compose or extend `apply_base.py`, or propagate `/workday-complete`'s dirty-tree auto-disposition.
- Auto-resolve tier-A oracle disagreement — a hard stop; needs `/autonomous` plus a recorded reviewer.
