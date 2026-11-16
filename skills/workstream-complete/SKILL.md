---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work. No handoff — this is for work that's *done*.

> **Mutual exclusion with `/handoff`.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP, use `/handoff`. Two workstreams → end each separately. Exception: the review-owed-close class (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4) → the trampoline, § Resolve judgment points.

This ceremony is computed end to end; never recompute what a field already answers. It declines `/workday-complete`'s dirty-tree auto-disposition.

`$ARGUMENTS` folds into the summary and completion entry.
**Fallback close:** an `emit-dispatch-workflow` run closes in-run; this is the relay fallback's last turn, every mode, fired with `dispatch.land_run` once the PM accepts the execute digest. § Final Summary IS the `close` wake digest: verdict → `outcome`, exceptions → `decision_required` and `deviations`.

---

## Compute the ceremony

Shape W (PowerShell) shown; POSIX: `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

`& "$env:COORDINATOR_SETTINGS_HOME\bin\workstream-complete-assemble.exe" brief [--decisions-file <path>]`
Work its output top to bottom ([computed-skills](../../docs/wiki/skills-corpus/computed-skills.md)).
**Prefer `--decisions-file`.**

`preflight.session_shape.disposition` is `single-session` or `predecessor-consumed`.

---

## Genuine EM actions — no directive can perform these

**Dispatch authorization — invoking this skill IS the request.** Its dispatches are constitutive steps, so a harness line permitting dispatch "unless the user requested it" is satisfied here, not overridden. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds (per-session cross-repo-commit assent, ask-before-external-action, any other this skill's own body names). Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

- **Execution-observations fold**: read each sidecar's `divergence` as quoted narrative; surface a crashed-executor marker before deleting it. A `## Tasks`-spine plan cites `plan-completeness status <plan-path>`'s divergence rollup.
- **Memo-resolution / self-clean disposition**: decide once.
- **Session Ledger row append** (predecessor-consumed only): one row via the `handoff.append_session_ledger` op, never hand-typed.
- **Prime exit criterion assertion**: a run-stamped plan already carries `exit_criterion_met`; verify it, never recompute. Absent blocks; so does an absent judge-authored sidecar: the EM never writes `asserted: true` itself (`AN-EM-NEVER-SELF-ASSERTS-EXIT-CRITERION-MET`); clear it by the re-judge route. `asserted: false` routes to `/handoff` or a Phase-5 halt. [terminal-judge](../../docs/wiki/reviewer-pipeline/terminal-judge.md); `A-PLAN-SELF-COMPLETES-ONLY-ON-A-MET-TERMINAL-JUDGE`.
- **Stop the session's own watchers — MANDATORY.** `coordinator-invoke workstream_complete.stand_down_watchers '{"session_id":"<sid>"}'` stops this session's, never a peer's. Render `stopped` (name each), each `survivors` entry as **not verified**, `expires_on_its_own` (`notify_when_idle`, no action), and every `unattributed` entry and `warnings` line. A Group EM holder relays the returned `notice`. `A-CLOSED-SESSION-LEAVES-NO-WATCHER-RUNNING`.
- **Terminal-baton drain — MANDATORY, and the last thing this ceremony does.**
  1. Hand-stamp `deployment_state`/`shipped_in` on **only** the two batons § Apply's carve-out omits from the payload; **never re-stamp one the payload already stamped.**
  2. **After** `apply`'s disposal read, run `sweep-terminal-handoffs`.
  3. **Close condition: `state/handoffs/` holds no record carrying a terminal `deployment_state`** (`shipped`/`continued`/`closed`) **when this ceremony reports complete.**
     <!-- enum-prose: schema=handoff field=deployment_state omit=awaiting_gate,ready_to_fire,in_flight -->

  `[[terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony]]`
- **Kira runs only when the EM or PM names Kira.**
- **An idle subagent has not failed.** Recover its verdict from its transcript under `subagents/`; never replace it with `em-verified`. `AN-IDLE-SUBAGENT-HAS-NOT-NECESSARILY-FAILED`.

---

## Resolve judgment points

**A judgment point earns its place only if a different competent EM, with the same artifacts, could reasonably answer it differently.** `A-FACT-WITH-A-CLOSED-ENUM-IS-NOT-A-JUDGMENT-POINT`.

**3 classes.** 1 = CLI-computable (not listed here). 2 = interpretation, but not *this EM's* — the output enum is already closed; demote when a path exists. 3 = judgment/taste/tradeoff. Never author a class-2 fact as a judgment point. Calibration: `coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md`.

**A shipped `recommendation` is applied by default and shown, not asked.** A null matters only when genuine: `jp-session-shape` always, tail-blocking scaffold/commit-subject/consumed-handoff when they fire. A blocked computation or missing producer is a break-class engine defect: resolve or memo.

**`jp-session-shape`:** confirm from `apply`'s output, never re-`brief`, never re-answer or reach for `override-known-in-flight`.

**Completion entry:** TITLE + ≤8-sentence body, banned sections `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria`, `## Universal lessons captured`. Never write receipt fields (`completion-receipts.md`).

**Review — 4 class-3 survivors, none demotable:** `shared-schema-touch-check`, `governing-spec-identification`, `finding-tradeoff-escalation-check`, `shallow-row3-waive-check` (`coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md` § Review class-3 survivors).

**Verify once:** a close-time suite or oracle check runs once, foreground.

**L+ code-quality trigger — a separate derivation from Scale's measurement.** It keys off the cited sizing-object's `estimate.tshirt` (the closing plan's `sizing_object:`); fires at `L` or `XL`; never answer it from Scale's measured `gross_loc`/`commit_count`/`surface_count`.

**The review record is the plan's `review_stamp`; this ceremony neither runs nor mints it.** A plan-bearing close ran review in the execute-plan workflow; read `gates.review_receipt`, write no trail.
**Review absent at close → this ceremony dispatches review; there is no skip.** No governing plan, or no `review_stamp` (mise-en-place included): run `/review-code` over the close's diff before `apply`, bound to `target_plan` so the review mints the plan's `review_stamp` (unbound, `stamp-implemented` refuses), at least one reviewer, partitioned when PARTITION-MANDATORY. A stampless hand-worked plan reaches `implemented` only via the rejudge route (`coordinator/docs/wiki/skills-corpus/workstream-complete-residue.md`, Stampless plan route). Never dispose the gap with `proceed-unresolved` or any skip.

**Hand-measuring the brightline is a last resort** — only once `stage_paths` is supplied and `review_scale` still returns `resolved: false`: per-owned-commit diffs, code only. Method: `coordinator/docs/wiki/ceremony-calibration/workstream-complete-review.md` § Hand-measuring the brightline.

**The trampoline.** When the owed review is genuinely un-runnable here (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4 — a closed class; low context is not a reason), exit via `/handoff` naming the event that clears it. **Capping with the review unrun is forbidden; `verdict: pending` is not the escape hatch.** Tripwire: `PARTITION-MANDATORY`.

**Chain-ancestry is provenance, not review discharge.**

---

## Concurrent-EM shared-branch disposition

**Case (c) is often a live peer's in-flight files, not an orphan.** `brief` classifies a/b/c mechanically and surfaces `concurrent-peer-attribution`. **If a peer is plausibly live, never adopt their paths** — commit only your own files by explicit path. Once ruled out, take exactly one: **commit** with provenance (`snippets/scoped-commit-route.md`), or **leave it explicitly owned by X**. Never `git stash`.

---

## Apply — execute the directives

`& "$env:COORDINATOR_SETTINGS_HOME\bin\workstream-complete-assemble.exe" apply --decisions-file <path>` — a JSON
object whose keys are *either* a `judgment_point_id` (value `{"disposition": "<value>"}`) *or* a non-JP decisions key (`stage_paths`, `review`, ...) with its own flat shape. **Never wrap a non-JP key's value in a `{"disposition": ...}` envelope.** `stage_paths` is a flat list: `{"stage_paths": ["<path>", ...]}`.

`decisions` carries what the compute half can't read off disk: lessons, completion prose, memo/scratch dispositions, commit subject.
After apply, the one per-delivery distill entry point is `/distill --delivery <deliverable_id>`, bounded by the `ceremony-budget.json` slice (`a-ceremony-budget-is-a-whole-backlog-token-bar`). Record-keeping only: it never defers this ceremony's own `git rm`. Script first, previews at most ~10k chars per plan, no fan-out over the corpus. Gated on the engine external_gate; until it lands the `--delivery` stages do not exist and the call is a no-op, never a failure that blocks this ceremony.
**`handoff_dispositions` is another non-JP key**, `{"<handoff-basename>.md": {...}, ...}` — one entry per baton this close disposes, each value an **object**: `shipped` (with `shipped_in`); `closed`/`abandoned` (each with `closed_reason` from `cancelled`/`displaced`/`stale` — **never defaulted**); `continued` (neither field).

**`shipped_in`:** one full-length sha per baton — the last commit in this session's own owned-commit list (`<sha>~1..<sha>`) touching the `writes:` paths of the plan spine whose `deliverable_id` matches the baton. Never a range, PR ref, list, or the close's own commit-tail sha. No such commit → `closed` or `continued`.

**An entry is silently dropped** unless it is an object, this session holds the claim, and the record is still active; the leg also needs `decisions.subject`. **Omit the baton in exactly two states:** its deliverable is carried only by the close's own commit, or it was already archived. Full rules: `coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md` § Handoff-disposition payload rules.

**`apply` commits — `_run_close_commit_tail` is not optional.** Gated on a `decisions.subject` (and `sid`). **Never read `apply`'s exit as leaving nothing landed.** **Residue gate:** run `"$_py" "${CLAUDE_PLUGIN_ROOT}/bin/close-residue-check.py" --session-id <this session's id>` before `apply` only to read its `groups`; the run after the scoped commit gates, and its exit 1 refuses the close. Then, still yours:

- **Scoped commit** of the completion entry, Session Ledger row, and your own files, per `snippets/scoped-commit-route.md` — a **second** commit after `apply`'s close commit.
- **Nothing** for review — confirm `gates.review_receipt.blocks` is `false`.

**`apply` runs the post-close steps itself.** Read outcomes off `post_close[]`; report `d-ceremony-reindex`'s outcome, never re-run it (`A-REINDEX-IS-A-STALENESS-FLAG-NEVER-AN-AGENT-TRIGGER`).

**A run-stamped plan already carries `implemented`; the ceremony verifies it, never restamps.** Where `land_run` did not stamp, `d-stamp-plan-implemented` is gated engine-side by `jp-open-spine-rows-block-stamp`, `jp-landed-reconciliation-block-stamp` and `jp-review-receipt-block-stamp`; unresolved lands in `report["blocked"]` (`HALTED_AT_JUDGMENT`; no stamp, no open census gate). Tripwire: `AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`.

**A stamp line can carry a failed archival move** (`N of M moves failed`): move the remainder.

Exit `2` (`DIRECTIVE_FAILED`) = nothing landed; exit `4` (`PARTIAL_MUTATION`) = a directive failed: **a failed close, never "done with residue"** — fix the cause and re-run `apply`. A client-side timeout is no failure signal: reconcile against commit state first.

`push_status` `"cadence-pending"`, `"pushed"`, `"deferred"` are all success; confirm `"deferred"` via `git branch -r --contains <sha>`. **Never `git push` to "fix" a delay.**

---

## Execution-Residual Sweep (judgment step — nothing computes it)

One disposition per mid-execution residual; none to sweep: omit the line. **Default is fix it now**; routing elsewhere needs a named reason: `peer-contention`, `other-repo`, `own-plan`, `irreversible`, `not-real` (`coordinator/docs/wiki/ceremony-calibration/workstream-complete-review.md` § Execution-residual reason classes). A break-class residual with none of the five is fixed, not filed.

**Spinoff overlap re-check, same step.** Before reporting complete, for every open (`kind: spinoff`) handoff this session or its chain authored, run <!-- VERBATIM -->`git log --since=<its authored-at> -- <its named scope/paths>`. A hit: surface a `superseded`/`consumed` candidate to the PM. No hit: omit.
---

## Completion verdict

**Consume `gates.completion_verdict` in the close narration** — read it off `gates`, never hand-derived.

**Two census gates force completion — the close never reports complete while either is open.** `owned_uncommitted` and `unstamped_run_batons`. Either open goes into `failed` (exit `4`): commit the owned files through the close commit, stamp the batons — never report it as residue or `indeterminate`. Tripwire: `A-CLOSE-WITH-OWNED-UNCOMMITTED-OR-UNSTAMPED-BATONS-IS-NOT-COMPLETE`.

**Render `indeterminate` (the ordinary case) as `indeterminate`, never "incomplete"**, naming only those a gate-specific reading says are worth naming. Readings:
`coordinator/docs/wiki/ceremony-calibration/close-ceremony-residue.md` § Reading `gates.completion_verdict`.

**Residue verbs, for whatever the verdict leaves outstanding** (never the two census gates):

Unfinished work to finish → trampoline (`/handoff`); not worth doing → won't-do; worth doing, not now → backlog; a distinct workstream → spinoff.

**Then append the changelog:** `& "$env:COORDINATOR_SETTINGS_HOME\bin\workday-complete-step9-append-changelog.exe" --no-push` (POSIX: `$COORDINATOR_SETTINGS_HOME/bin/workday-complete-step9-append-changelog --no-push`).

---

## Final Summary

**Report by exception.** One line always; everything else only when *not* clean. A Group EM session additionally follows `coordinator/snippets/group-em-output-contract.md`.

Relay `d-baton-chain-closure`'s `post_close[].output` when it carries one; never run `chains`.

**A leg parked as blocked on a sibling repo carries its exchange, or it is not parked.** Check the three conjuncts in `coordinator/snippets/cross-repo-block-exchange.md` (declared, addressed, answered). Tripwire: `A-SENT-MEMO-IS-NOT-AN-EXCHANGE`.

```
## Session Complete

**Work done:** [1-2 sentence summary]
```

Append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Completeness checklist:**` | `gates.completeness_checklist` WARN — name the N unverified items |
| `**Consumed-handoff completeness:**` | reports `blocks`/`indeterminate` — name handoff+leg (`not-applicable` NOT reported) |
| `**Deferral harvest:**` | N ≥ 1 queued |
| `**Execution residuals:**` | sweep resolved ≥1 item — `<residual> -> fixed <sha>` or `-> <queue id \| memo \| spine row> (<reason-class>)` |
| `**Post-summary reconcile:**` | commits were folded |
| `**Pushed:**` | the push did **not** land (`deferred`/`detached` is success, silent) |
| `**Publish lag:**` | `compute_publish_lag_advisory` reports a lag worth naming |
| `**PM ask:**` | the closing plan resolves ≥1 PM verbatim — `pm-brief render <closing-plan>`; each ask `met` or its residue verb; all-met is one `met` (`A-ROUTED-SIZING-IS-NOT-A-LIVE-ASK`) |
| `**Flag to PM:**` | a direction-class item survived severity classification below |

**`not-applicable` is silent, like `clean`; `indeterminate` is reported.** Tripwire: `NOT-APPLICABLE-SPANS-TWO-SILENCES`.

**Do not print** `Lessons captured`/`Work archived`/`Docs updated`/`Orientation refreshed`. **An automated mechanism's routine success is never a PM line.** This ceremony emits NO archival directive.

**Classify flags by severity first** (global `CLAUDE.md § Flag Severity`): only direction-class items go in `Flag to PM:`.
