---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work. No handoff — this is for work that's *done*.

> **Mutual exclusion with `/handoff`.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP, use `/handoff`. Two workstreams (one done, one live) → end each separately, naming which. Exception: the review-owed-close class (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4) → the trampoline, § Review.

This ceremony is computed end to end — session-shape, plan reconciliation, lessons, completion-entry, memo lifecycle, scratch self-clean, orientation refresh, and commit-tail ship as `directives[]`; what cannot be resolved ships as `judgment_points[]`. Never recompute by hand what a field already answers.

`$ARGUMENTS`, if given, fold into Final Summary and completion-entry prose.

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

- **Review-partition dispatch**: freeze each slice's diff first; one `code-reviewer` per slice, `run_in_background: true`; one 1:1 `review-integrator` per slice, never a union-integrator. Unconditional on verdict — an `OK` slice with findings is still a slice with findings; a reviewer's self-disposition closes nothing. Tripwire: `REVIEWER-SELF-DISPOSITION-IS-NOT-CLOSURE`. **Exception:** `rebuild_recommended: true` (`agents/overengineering-reviewer.md` § Rebuild Verdict) never enters this integrator path — take the next bullet. This is the partitioned-close carve-out `coordinator/skills/review/SKILL.md` § A.3 names: each slice is its own diff, its own lens, so fanning them out is not the same-artifact race that rule forbids.
- **Rebuild-verdict routing**: on `rebuild_recommended: true`, do NOT dispatch `review-integrator` for that slice. Dispatch one `coordinator:executor` with an explicit refactor remit: brief body = `rebuild_rationale`, `writes:` scope = the file/module boundary named in `rebuild_scope` (never wider), brief states plainly this is a rebuild, not a findings pass. Ordinary findings travel in the same brief as context — one slice, one route, never both. Record the dispatch (target, verdict, outcome) in the closing session's run-report sidecar. Tripwire: `A-REBUILD-VERDICT-IS-NOT-A-FINDINGS-LIST`.
- **Doc-fragile domain lens**: `compute_doc_fragile_gate` match → dispatch `coordinator:docs-checker` alongside `code-reviewer`, same diff.
- **Execution-observations fold**: read each sidecar's `divergence` as quoted narrative, never EM-authored prose; surface a crashed-executor marker before deleting it. For a plan carrying a `## Tasks` spine, cite `plan-completeness status <plan-path>`'s divergence rollup — including its non-conformant count — rather than re-reading N per-chunk sidecars one at a time; a plan predating the spine still reads sidecars directly.
- **Memo-resolution / self-clean disposition**: no signal for which memos resolved, or which scratch files to keep — ask/decide once, plain prose; evidence is surfaced, never picked.
- **Session Ledger row append** (predecessor-consumed only): one row to the consumed handoff's `## Session Ledger` — the sole edit `/pickup`'s frozen-body rule carves out. Append via the `handoff.append_session_ledger` engine op, never a hand-typed row.
- **Prime exit criterion assertion**: a plan this session executed whose `exit_criterion_met` is absent blocks the close — no directive computes it. `asserted: false` is a legitimate, first-class outcome and does not block: it routes to `/handoff` or a Phase-5 halt.
- **Terminal-baton drain — MANDATORY, and the last thing this ceremony does.** No directive
  performs it and nothing downstream catches the miss.
  1. Hand-stamp `deployment_state`/`shipped_in` on **only** the two batons § Apply's carve-out
     omits from the payload; **never re-stamp one the payload already stamped.**
  2. Bind strictly **after** `apply`'s own disposal read — once every payload-stamped and
     hand-stamped carve-out baton alike carries a terminal `deployment_state` — then run
     `sweep-terminal-handoffs`. Idempotent, sub-second no-op when there is nothing to move; also
     drains other sessions' terminal residue.
  3. **Check the close condition: `state/handoffs/` holds no record carrying a terminal
     `deployment_state`** (`shipped`/`continued`/`closed` —
     `HANDOFF_TERMINAL_DEPLOYMENT`; `declined`/`superseded` are sizing-object and retired-handoff
     `status` values, never `deployment_state`) **when this ceremony reports complete.** Never
     defer the drain to the next ceremony.
     <!-- enum-prose: schema=handoff field=deployment_state omit=awaiting_gate,ready_to_fire,in_flight -->

  `[[terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony]]`
- **Kira-routing enforcement is mechanical, not prose**: checked by
  `coordinator/hooks/scripts/guard-kira-verdict-routed.py`, a `stop-dispatch.py` `StopGuard`
  reading only sidecar frontmatter. A Stop hook, not a close gate: an unrouted Kira verdict blocks
  the next turn end once (`stop_hook_active` passes it on replay) and surfaces the owed route — no
  warn tier, no override. Tripwire: `KIRA-ROUTING-IS-STAMPED-NOT-REMEMBERED`.

---

## Resolve judgment points

**The discriminator: a judgment point earns its place only if a different competent EM, with the
same artifacts on disk, could reasonably answer it differently.** `A-FACT-WITH-A-CLOSED-ENUM-IS-NOT-A-JUDGMENT-POINT`.

**3 classes.** 1 = CLI-computable (not listed here). 2 = interpretation, but not *this EM's* — the
passage raising it already specifies the inputs and closes the output enum, so a differing answer
is demonstrably wrong, not merely differently defensible; demote off the EM's plate when a
demotion path exists, and when none does it is carried as a judgment point **by necessity**, named
as such. 3 = judgment/taste/tradeoff — two competent EMs can disagree and both be right. **Do not
author a fact as a judgment point when the same passage specifies its inputs and output enum** —
that is class 2, not class 3. Calibration: `completion-nature-classification` (four inputs, closed
output enum off the diff — a differing classification is demonstrably wrong) is class 2;
`review-partition-strategy` and `finding-tradeoff-escalation-check` (below) take a diff and a
review posture but close on no enumerable output — two competent EMs partition or weigh a tradeoff
differently and both are defensible, so they stay class 3. A re-test names a class per item it
**keeps**, not only those it demotes — a keep with no stated class is the tell the test was not
applied.

**A shipped `recommendation` is applied by default and shown, not asked** — carry it into the decisions map and report what was filed as a receipt (`completion-nature-classification`/`jp-coverage-verdict` both ship one). A null earns attention only when genuine: `jp-session-shape` always, `jp-review-scale` while unresolved, tail-blocking scaffold/commit-subject/consumed-handoff whenever they fire. Blocked computation or a missing producer is a break-class engine defect — resolve cheaply or memo, once confirmed absent.

**`jp-session-shape` is honoured by the tail but never reflected back in `brief`'s gate readout** — a re-`brief` still shows `gates.session_shape.disposition` at the original detector verdict, exit 0, no diagnostic. That is not a discarded decision: confirm from `apply`'s own output, never by re-`brief`, and never re-answer or reach for `override-known-in-flight`.

**The rest — read the object.** Every point not named here carries its own prompt/evidence on `judgment_points[]`.

**Completion entry:** TITLE + ≤8-sentence body, banned sections `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria`, `## Universal lessons captured`. `d-complete-entry` scaffolds placeholders only — hand-write the resolved title/prose/nature before commit-tail; a placeholder-carrying scaffold is refused.

**Review — 8 class-3 survivors, no mechanical rule for any**, so none demotes: `review-partition-strategy`, `reviewer-count-on-oracle-disagreement` (tier A is a hard stop), `shared-schema-touch-check`, `governing-spec-identification`, `finding-tradeoff-escalation-check`, `shallow-row3-waive-check`, `review-dispatch-vehicle-choice` (hand-dispatch), `quota-retry-vs-escalate` (`coordinator/docs/wiki/close-ceremony-residue.md` § Review class-3 survivors).

**Scale:** doc-only/no-executor/<50 LOC single file → None; executor dispatched, or >50 LOC, or shared-schema touched → `code-reviewer`.

- **`gates['review_scale']` carries measured `gross_loc`/`commit_count`/`surface_count` only when it resolves.** `resolved: true` → consume it, never hand-derive; a `decisions` override beats the measurement only for a stated reason.
- **`resolved: false`** (all three unresolved, no `commit_slices`) → re-run `brief` with `decisions["stage_paths"]`; that key gates the row-4 measurement, and `[]` resolves it when this session has no uncommitted files. Means the measurement has not run, never that none is owed. **Do NOT hand-sum instead** — `code_loc`/`commit_count`/`surface_count` are *outputs* of that measurement; a hand count uses different definitions, landing on a different row.
- **Brightline is mandatory, not advisory:** ≥500 gross LOC, OR ≥5 commits, OR ≥4 surfaces forces partitioned. It owns review for the whole chain including upstream `/mise-en-place` work — clean verifiers never justify a lower scale. **Chain-end** → same rule over the range `resolve_mid_chain_review_scope` resolves, never hand-derived.
- **`review-brightline-gate`'s verdict enum is `PARTITION-MANDATORY|single-reviewer-ok|indeterminate`.** Its `indeterminate` fires on `--session-id` zero-match (`VERDICT=indeterminate` plus a stderr note to verify by hand) — distinct from `gates['completion_verdict']`'s per-leg `indeterminate`, not the same value reused (`coordinator/docs/wiki/workstream-complete-review.md` § Zero-match semantics).

**Kira (`coordinator:overengineering-reviewer`) is dispatched on every close, and runs FIRST — before any Scale-selected `code-reviewer`.** A PM ruling, NOT gated on the cited sizing-object's `estimate.tshirt` (no threshold added here). A proportionality lens over the Scale ladder, never a replacement — a close whose Scale resolves to `None` still dispatches them. **Ordering is load-bearing.** Reviews are sequential, never parallel (`coordinator/skills/review/SKILL.md` § A.3): dispatch Kira → route their verdict → only then dispatch the Scale-selected `code-reviewer` over the resulting tree. Their verdict routes through `review-integrator`, except on `rebuild_recommended: true` (Rebuild-verdict routing, above). **A rebuild fires** → the `code-reviewer` pass runs over the rebuilt shape, never the discarded one. Too-noisy volume is a PM finding, not a threshold to add here.

**Hand-measuring the brightline is a last resort, never a shortcut past the gate** — only once `stage_paths` has been supplied and it still will not resolve. **Sum per-owned-commit diffs** (`<sha>~1..<sha>` each — `~1`, never `^`: cmd.exe eats a literal `^` in argv on Windows), **never a range across `oldest..newest` — a shared branch adds peer commits (specimen: 33,246 LOC vs its own 16,037)**, **count code only** (`.md`/`.yaml`/`.yml` excluded). **`partition_mandatory` true and `commit_slices` empty** → derive slices from that same list. Method, evidence, definition gap: `coordinator/docs/wiki/workstream-complete-review.md` § Hand-measuring the brightline.

**L+ code-quality trigger — a separate derivation, not a parameter on Scale's measurement.** Scale
keys off *measured* `gross_loc`/`commit_count`/`surface_count`; L+ answers *how big was this meant
to be* and keys off the **cited sizing-object's `estimate.tshirt`** — resolve the closing plan's
`sizing_object:` frontmatter citation and read `estimate.tshirt` off the artifact it names. The
only keying surface: `plan.schema.json` carries no t-shirt field of its own and none is added here
(a second size per plan would drift). Fires at `L` or `XL`. Never reach for Scale's measured
computation to answer it.

**The trampoline — hand the ceremony to a fresh session rather than cap with the review unrun.** Once a scale is named you owe it. Two DIFFERENT routes both exit through `/handoff`, which is why they read as one route; they are not.

- **Low context is not a trigger-4 reason** — ordinary context pressure takes the ordinary `/handoff` route. Trigger 4's roster is a ratified CLOSED class of *un-runnable-here* reasons (hard-stop oracle disagreement, quota-exhausted dispatch, a live peer's untouchable files, an unresolved `review_scale` gate), each with a clearing event outside this session's reach; admitting a reason by resemblance or analogy is forbidden.
- **When the review is genuinely un-runnable here** (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4), exit via `/handoff` naming which member of that class fires and the event that clears it. `/handoff`'s NO-tests carve this case out.

**Capping with the review unrun is forbidden; `verdict: pending` is not the escape hatch.** Tells to trampoline instead: "the next session can review this"; `reviewer: waived` pairing a non-`waived` verdict; a range narrowed to one commit because the honest range was refused; "mandatory" reasoned as advisory. Tripwire: `PARTITION-MANDATORY`.

`scan_dispatch_output(text) -> bool` checks every completed Agent dispatch's return body before any verdict-ok record (`QUOTA-EXHAUSTED-DISPATCH:` is sufficient alone). Trivial (row 1/2) sessions write no trail record; PM-waived logs `--reviewer waived --verdict waived`; `em-verified` is a review you ran yourself, never `waived` — both need ≥20-char justification.

**A dispatch that went idle without returning is a DELIVERY failure, not an execution one — recover the report before reaching for `em-verified`.** The agent's final text is on disk at `~/.claude/projects/<project-slug>/<session-id>/subagents/agent-<name>-<hash>.jsonl`; the report is the last assistant message's `text` block, and `stop_reason: end_turn` on it confirms a clean finish. Writing `em-verified` over a verdict you never read replaces an independent reviewer's finding with your own and still writes a green trail. Tripwire: `AN-IDLE-SUBAGENT-HAS-NOT-NECESSARILY-FAILED`.

**The review record is the RECEIPT on the reviewer's sidecar, not a trail record you write.** A dispatched `code-reviewer`/`review-integrator` stamps `review_receipt:` (session id, agent id, agent type, `stamped_at`) into its own sidecar frontmatter as it finishes; `gates.review_receipt` reads it, `jp-review-receipt-block-stamp` gates the terminal stamp on it. **Dispatching the reviewer records the review; the reviewer returning discharges it** — you write nothing.

- The engine splices that receipt at spawn, so a crashed/still-running reviewer carries one identical to a finished reviewer's; confirm the return (`scan_dispatch_output`) before reading the gate as green. Tripwire: `A-RECEIPT-SPLICED-AT-SPAWN-ATTESTS-DISPATCH-NOT-COMPLETION`.
- `blocks: false` on that gate is the close's review record only when a reviewer this close dispatched has returned; per-wave receipts never discharge it. `detail: no integrator receipt (review ran, findings not recorded as applied)` means the EM folded findings in — legitimate for a `code-reviewer` slice, **never for a Kira verdict carrying findings** (`guard-kira-verdict-routed` hard-stops otherwise). Applied them yourself? Dispatch the integrator over your own application. Per-wave sidecars are integration inputs only: `workstream-complete-review.md` § Per-wave sidecars are integration inputs, never the close's review record — NO-AUTO-INTEGRATE, an emitted Workflow never gains integrator-dispatch authority.
- **`decisions["review"]` keys nest under `"review"`, never flat `review_*`** — flat keys silently skip `d-attest-review-verified` while exiting 0.
- **`decisions["review"]` itself is dict-XOR-list, never both.** Single-slice close → flat dict under `"review"`; partitioned close → a list, one dict per slice, in slice order.
- **Never hand-roll a per-commit trail write.** `review_trail.write` and its CLIs are a K-060 gravestone whose successor is this receipt; a refusal from them is the dead surface answering, not a signal about your close. An unrecordable real review is a named-cause open gap — naming it *is* the discharge; narrowing the range, dropping a slice, or lowering scale until something writes is forbidden here for the same reason it's forbidden with no review at all. Tripwire: `A-SUSPENDED-OP-IS-NOT-A-MECHANISM-TO-WAIT-OUT`.
- **On total refusal — no trail record can be written at all — `decisions["review"]` still resolves, never left empty.** `verdict: blocked` with no trail write is legal: `apply` never writes a trail record regardless of outcome (`review_trail.write` is the K-060 gravestone with no returning successor; the reviewer's own sidecar receipt is the only artifact). `reviewer_evidence` names the gap and its cause in place of a resolvable path or receipt — the same ≥20-char justification `em-verified`/`waived` require — never a narrowed range or lowered scale standing in for it.

**`sha_range` must contain only this session's own commits** — a foreign-session guard refuses a range carrying another session's `Session-Id` trailer (normal on a shared branch); write one per-slice record per commit instead (`<sha>~1..<sha>`). **Slice; never narrow** (`SLICE_NEVER_NARROW`) — narrowing the range or lowering scale until something writes is forbidden even when the review ran; a legitimate exclusion states itself and its LOC.

**A chain-ancestry waiver is provenance, not review discharge — it does not clear a HALT.** `certifies_review: false` reads "ancestry NOT reviewed," and re-running does not clear it either. Tripwire: `WAIVER-IS-PROVENANCE-NOT-DISCHARGE`.

---

## Concurrent-EM shared-branch disposition

**Case (c) is not always an orphan** — often a live peer's in-flight files. `brief` classifies
a/b/c mechanically and surfaces the peer-vs-orphan call as `concurrent-peer-attribution`;
disposing case (c) is EM judgment, weak/contradictory signals default to case (c), never a guess.
**If a peer is plausibly live, never stash or adopt their paths** — commit only your own files by
explicit path. Once ruled out, take exactly one, never terminate with case-(c) files dirty and
unnamed: **commit** with provenance (per `snippets/scoped-commit-route.md`); **stash with
provenance** (`git stash push -u -m "orphaned-WT <date> workstream-complete: <path> — left by
unknown session" -- <path>`); or **leave it explicitly owned by X**. Orphan `.tmp.<pid>.<nanos>`
files are an Edit-tool crash artifact — diff before deleting.

---

## Apply — execute the directives

`& "$env:COORDINATOR_SETTINGS_HOME\bin\workstream-complete-assemble.exe" apply --decisions-file <path>` — the file is a JSON
object whose keys are *either* a `judgment_point_id` (value `{"disposition": "<value>"}`) *or* one of the non-JP decisions keys (`stage_paths`, `review`, ...), each with its own flat shape. **Never wrap a non-JP key's value in a `{"disposition": ...}` envelope** — a nested `{"disposition": [...]}` for `stage_paths` is not a recognized shape and the gate cannot distinguish it from the key being absent. `stage_paths` is a flat list: `{"stage_paths": ["<path>", ...]}`.

`decisions` carries every value the compute half can't read off disk — lessons, resolved completion-nature/prose, memo/scratch dispositions, review-partition slice map, commit subject/prose — firing every open-gated directive.

**`handoff_dispositions` is another non-JP key**, `{"<handoff-basename>.md": {...}, ...}` — one entry per baton this close disposes, each value an **object**, never a bare string (`"shipped"` alone is dropped, not coerced). All four consumer-resolved values are carried: `shipped` (with `shipped_in`, below); `closed`/`abandoned` (each with `closed_reason` from `cancelled`/`displaced`/`stale` — **never defaulted, never fabricated**; anything else, however well-written, is refused); `continued` (neither field).

**The `shipped_in` rule.** Deliverable paths are declared, not guessed: the union of `writes:`
across spine rows of the plan whose frontmatter `deliverable_id` matches the baton —
grep-resolvable, the only declared source; no `deliverable_paths` key exists anywhere, and
`deliverable_id` is plan-level, never per-row. No such plan → no `shipped` arm. `shipped_in` is
the last commit in this session's own owned-commit list touching those paths, sliced per commit
exactly as `sha_range` above, filtered on path-touch — **never** the code-only `.md`/`.yaml`/`.yml`
filter, which discards the doc-only commits batons usually ship in. One full-length sha per baton
(`git rev-parse` form) — never a range, PR ref, list, or the close's own commit-tail sha; the
engine derives and defaults none. **No fallback arm**: no commit touched the deliverable → not
`shipped` — routes to `closed` (with `closed_reason`) or `continued`, never a placeholder or
nearest sha.

**An entry is silently dropped unless three preconditions hold**: an object (never a bare string); this session holds the claim; the record is still active under `state/handoffs/` at `apply` invocation (not a later commit-tail moment). Miss one and `apply` drops the entry with no error — a silent skip, not a raised error. **Separately, reachability**: the whole disposition leg runs only when `decisions` also carries a `subject` — a payload emitted on a close with no `subject` is read by nothing.

**Two reachable states get no entry at all — deliberate omission, a narrow named carve-out, never the memo's blanket exclude-by-omission rule (which told this repo to omit every non-`shipped` baton and starved the disposal leg).** (1) The deliverable is carried only by the close's own commit: no `shipped_in` sha exists yet, no `closed_reason` is honest, `continued` is refused. **Payload: omit the baton**, and the terminal stamp is owed to the residual hand route (§ Genuine EM actions). (2) The record was already archived — typically by `/handoff`'s supersession route, the only writer of `deployment_state: continued`, which archives the predecessor in the same move on a clean chain. **Payload: omit the baton.** **Nothing wider** — a `closed`/`abandoned`/`continued` baton outside these two named states is always emitted.

**The payload implies a ceremony order — transition, dispose, archive — not optional.** `continued` is refused unless `deployment_state` already reads `continued` (transition before disposal); disposition is refused once the record has left `state/handoffs/` (disposal before archival, never after). A successful disposal releases this session's claim; `closed`/`abandoned` alike land the record at `deployment_state: closed`.

**`apply` commits — `_run_close_commit_tail` is not optional.** It runs unconditionally,
immediately after `_execute_directives` returns, gated only on `decisions` carrying a `subject`
(and `sid`) — the same `subject` the disposal leg requires. When it fires it folds the
`handoff_dispositions` ship-stamps into that commit's `stage_paths` **before** committing, so the
stamps land inside `apply`'s own commit, never separately-committed. **Never read `apply`'s exit
as leaving nothing landed.** Then, still yours to make:

1. **Scoped commit** of the completion entry, Session Ledger row, and your own files, per
   `snippets/scoped-commit-route.md` — a **second** commit, landing after `apply`'s own close
   commit and never carrying the stamps itself.
2. **Nothing** — the review record landed when the reviewer stamped its sidecar receipt. Confirm
   `gates.review_receipt.blocks` is `false` and name any missing integrator receipt in the summary.

**The terminal stamp is gated engine-side, and a blocked stamp is not a failed one.**
`d-stamp-plan-implemented` carries three empty-`resolves` judgment points on its `depends_on`:
`jp-open-spine-rows-block-stamp` (unwaived `open` rows, or `indeterminate`),
`jp-landed-reconciliation-block-stamp` (plan `landed` with unticked ACs),
`jp-review-receipt-block-stamp`. An unresolved one lands in `report["blocked"]` under
`HALTED_AT_JUDGMENT`, **not** `report["failed"]` — a close exits non-failing with no stamp.
`waived_open_spine_row_ids` clears leg 1's `applicable` arm only, never `indeterminate`. Never
build a doctrine gate beside these — report the incomplete, resolve the leg. Tripwire:
`AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`.

**A stamp line can carry a failed archival move.** The sweep reports `status draft -> implemented`
and `N of M moves failed` on one line — read all of it and move any remainder, or the plan's
`.workflow.mjs`/`.emitted.json` sidecars stay orphaned in `docs/plans/` while the plan sits in
`archive/specs/`.

`apply` prints diagnostics on every non-zero exit — read them, don't memorize codes. Exit `2` (`DIRECTIVE_FAILED`) = nothing landed; exit `4` (`PARTIAL_MUTATION`) = some landed, some failed. A client-side timeout is not a failure signal — reconcile against actual commit state before re-running.

Push runs on a cadence, not on this commit: `push_status` `"cadence-pending"`, `"pushed"` and (older engines) `"deferred"` are all success — the branch publishes at the next named checkpoint (`/pickup`, `/quick-wrap`, `/workday-start`, the workday/workweek closes). Only `"deferred"` wants confirming, via `git branch -r --contains <sha>`. **Never `git push` to "fix" an apparent delay.** Check an unfamiliar string against `commit_pipeline.py`'s `PUSH_STATUS_*` block.

---

## Execution-Residual Sweep (judgment step — nothing computes it)

A residual discovered mid-execution never counts in the harvest — `Queued 0` reads as "nothing left behind." One disposition per item; nothing to sweep is ordinary — omit the line. **Default is fix it now**; routing elsewhere costs a named reason from a closed class: `peer-contention`, `other-repo`, `own-plan`, `irreversible`, `not-real` — in full, `coordinator/docs/wiki/workstream-complete-review.md` § Execution-residual reason classes. A break-class residual with none of the five is fixed, not filed. The auto-memory drain gate runs only at `/workday-complete`/`/workweek-complete`, never here.

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
`coordinator/docs/wiki/close-ceremony-residue.md` § Reading `gates.completion_verdict`.

**Residue → verb lookup, for whatever the verdict leaves outstanding:**

| Residue shape | Verb |
|---|---|
| Blocked on further work this session should still finish | trampoline (`/handoff`, review-owed-close class) |
| Not worth doing | won't-do |
| Worth doing, not now | backlog |
| A distinct workstream someone else should pick up | spinoff |

---

## Final Summary

**Report by exception.** One line always; everything else only when *not* clean. A Group EM
session additionally follows `coordinator/snippets/group-em-output-contract.md` — one emission
form only (a decision awaiting the PM), offers/self-labelled-optional asks excluded, filtered at
source, never appended at the end.

**A baton shipping here can newly close its whole chain.** Run
`<plugin-root>/bin/baton-chain-closure.py signal <this-handoff-path>` after this ceremony's own
close. It re-derives chain closure from disk and emits nothing unless this baton's whole chain has
resolved — silence is the common case. Output already conforms to `group-em-output-contract.md` —
do not re-shape it. **Do not run `chains` here**: that verb enumerates the corpus and is
diagnostic, never PM-facing.

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
| `**Flag to PM:**` | a direction-class item survived severity classification below |

**`not-applicable` is not `indeterminate`.** `not-applicable` = nothing to look at (e.g. a `session-handoff`'s leg A resolves via `deliverable_id`/plan `status:` and finds no live plan) — stays silent, as `clean` does. `indeterminate` = the gate tried to look and couldn't, and must be reported. Tripwire: `NOT-APPLICABLE-SPANS-TWO-SILENCES`.

**Do not print** `Lessons captured`/`Work archived`/`Docs updated`/`Orientation refreshed` — counts the commit already records, not PM decisions. **An automated mechanism's routine success is never a PM line**: report the machine only when it *failed*. **Archival is NOT in that set — not automatic; this ceremony emits NO archival directive.** Disposal is not archival: the record stays under `state/handoffs/` until the drain moves it, a mandatory EM action (§ Genuine EM actions), never a machine step. Never author a second sweep beside the drain. Backstop: `coordinator/docs/wiki/close-ceremony-residue.md` § Archival is not automatic.

**Classify flags by severity first.** A break-class defect (broken/would-break/fails/leaks/silently-bypasses) is fix-by-default — fix it, report the fix, never a passive `Flag to PM:`; only direction-class items go there. → global `CLAUDE.md § Flag Severity`.

---

## What this does NOT do

- Rebuild the Step-0 session-shape gate, the coverage judgment point, or `resolve_repo_root` — already correct.
- Compose or extend `apply_base.py` — a deliberate divergence from the `pickup`/`baton`/`merge`/`consolidate` lineage.
- Propagate `/workday-complete`'s dirty-tree auto-disposition — stricter surface here, on purpose.
- Auto-resolve tier-A oracle disagreement — a hard stop; needs `/autonomous` plus a recorded reviewer.
