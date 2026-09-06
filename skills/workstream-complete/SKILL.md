---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work. No handoff — this is for work that's *done*.

> **Mutual exclusion with `/handoff`.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP, use `/handoff`. Two workstreams (one done, one live) → end each separately, naming which. Exception: the review-owed-close class (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4) → the trampoline, § Review. → coordinator CLAUDE.md § Handoff Lineage.

This ceremony is computed end to end — session-shape, plan reconciliation, lessons, completion-entry, memo lifecycle, scratch self-clean, orientation refresh, and commit-tail ship as `directives[]` naming a CLI; what cannot be resolved ships as `judgment_points[]`. Never recompute by hand what a field already answers.

`$ARGUMENTS`, if provided: fold into Final Summary and completion-entry prose.

---

## Compute the ceremony

Shown in Shape W (PowerShell, rung 0). POSIX hosts take Shape A/B — ladder and shapes:
`snippets/resolve-coordinator-bin.md`.

`& "$env:COORDINATOR_SETTINGS_HOME\bin\workstream-complete-assemble.exe" brief [--decisions-file <path>]`
**Prefer `--decisions-file` on both subcommands; `--decisions '<json>'` is the short-payload
convenience.** A real payload carries prose (completion rationale, commit subject, review records),
and prose on argv is mangled by the tool seam. Supplying both channels at once fails loud.
(resolved per `snippets/resolve-coordinator-bin.md`: Shape A/B on POSIX hosts, Shape W on PowerShell)

Returns (`artifact`/`preflight`/`gates`/`directives`/`judgment_points`/`decisions`/`narration`/`next_move`). `preflight.session_shape` (= `gates.session_shape`) carries `sid`, `disposition` (`single-session`/`predecessor-consumed`; reads backward — consumed a predecessor, not that a successor follows), `consumed_handoff`, detector diagnostics. `jp-session-shape` is the untrusted-gate point for an uncertain resolution.

---

## Genuine EM actions — no directive can perform these

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

- **Review-partition dispatch**: freeze each slice's diff first; one `code-reviewer` per slice, `run_in_background: true`; one 1:1 `review-integrator` per slice, never a union-integrator. The integrator is unconditional on verdict — an `OK` slice with findings is still a slice with findings, and a reviewer's self-disposition closes nothing. Tripwire: `REVIEWER-SELF-DISPOSITION-IS-NOT-CLOSURE`. **Exception, not a special case of the above:** a verdict carrying `rebuild_recommended: true` (`agents/overengineering-reviewer.md` § Rebuild Verdict) never enters this integrator path at all — see the routing rule immediately below.
- **Rebuild-verdict routing**: on any reviewer verdict where `rebuild_recommended: true`, do NOT dispatch `review-integrator` for that slice — `review-integrator` applies findings to an existing artifact one at a time, the wrong mechanism for "discard this shape and build it again from the spec." Instead dispatch one `coordinator:executor` carrying an explicit refactor remit: brief body = `rebuild_rationale`, `writes:` scope = the file/module boundary named in `rebuild_scope` (never wider), and the brief states plainly that this is a rebuild, not a findings-application pass. The reviewer's ordinary findings on that same slice (if any) travel in the same brief as context, not as a separate integrator dispatch — one slice, one route, never both. Record the dispatch (target, verdict, outcome) in the closing session's run-report sidecar; this is the mechanism AC3's "exercised at least once" clause checks against `state/review-trail`/`state/subagent-share`. Tripwire: `A-REBUILD-VERDICT-IS-NOT-A-FINDINGS-LIST`.
- **Doc-fragile domain lens**: `compute_doc_fragile_gate` match → dispatch `coordinator:docs-checker` alongside `code-reviewer`, same diff.
- **Execution-observations fold**: read each sidecar's `divergence` as quoted narrative, never EM-authored prose; surface a crashed-executor marker before deleting it.
- **Memo-resolution / self-clean disposition**: no signal for which memos resolved, or which scratch files to keep — ask/decide once, plain prose; evidence is surfaced, never picked for you.
- **Session Ledger row append** (predecessor-consumed only): one row to the consumed handoff's `## Session Ledger` — the sole edit `/pickup`'s frozen-body rule carves out. Append it via the `handoff.append_session_ledger` engine op, never a hand-typed row.
- **Prime exit criterion assertion**: a plan this session executed whose `exit_criterion_met` is absent blocks the close — no directive can compute this. `asserted: false` is a legitimate, first-class outcome and does not block; it routes to `/handoff` or a Phase-5 halt instead.
- **Terminal-baton drain — MANDATORY, and the last thing this ceremony does.** After stamping `deployment_state` + `shipped_in`, run `sweep-terminal-handoffs`. This is not a tidy-up you may defer to the next ceremony: a record stamped archivable and left in `state/handoffs/` is an unfinished close, because every surface that counts open batons reads it as *unstarted* for however long the gap runs. **The close condition is checkable and you check it: `state/handoffs/` holds no record carrying a terminal `deployment_state` (`shipped`/`continued`/`closed`, plus legacy `abandoned` — `HANDOFF_TERMINAL_DEPLOYMENT`; `declined`/`superseded` are sizing-object and retired-handoff `status` values, never `deployment_state`) when this ceremony reports complete.** The drain is idempotent and a sub-second no-op when there is nothing to move, so there is no cost that justifies skipping it, and it drains other sessions' terminal residue too — that is a feature, not overreach. No directive performs this today; nothing downstream catches the miss. `[[terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony]]`
- **Kira-routing enforcement is mechanical, not prose**: the routing rule above (§ Resolve judgment points, Kira paragraph) is checked by `coordinator/hooks/scripts/guard-kira-verdict-routed.py`, a `stop-dispatch.py` `StopGuard` reading only sidecar frontmatter. It is a Stop hook, not a close gate — it fires at every turn end, and `stop_hook_active` makes it block the next turn end once then pass on replay. An unrouted Kira verdict blocks the next turn end once and surfaces the owed route — there is no warn tier and no override. Tripwire: `KIRA-ROUTING-IS-STAMPED-NOT-REMEMBERED`.

---

## Resolve judgment points

**3 classes.** 1 = CLI-computable (not listed here). 2 = interpretation but not *this EM's* — closed enum, a differing answer is demonstrably wrong; demote when possible. 3 = judgment/taste/tradeoff. A re-test names a class per item it **keeps**, not only those it demotes.

**A shipped `recommendation` is applied by default and shown, not asked** — carry it into the decisions map and report what was filed as a receipt (`completion-nature-classification`/`jp-coverage-verdict` both ship one). A null earns attention only when genuine: `jp-session-shape` always, `jp-review-scale` while unresolved, tail-blocking scaffold/commit-subject/consumed-handoff whenever they fire. Blocked computation or a missing producer is a break-class engine defect — resolve cheaply or memo, after verifying the producer is really absent.

**`jp-session-shape` is honoured by the tail but never reflected back in `brief`'s gate readout** — after you answer it, a re-`brief` still shows `gates.session_shape.disposition` at the original detector verdict, with exit 0 and no diagnostic. That is not a discarded decision. Confirm from `apply`'s own output, never by re-`brief`; re-answering and reaching for `override-known-in-flight` are both wrong.

**The rest — read the object.** Every point not named here carries its own prompt/evidence on `judgment_points[]`.

**Completion entry:** TITLE + ≤8-sentence body, banned sections `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria`, `## Universal lessons captured`. `d-complete-entry` scaffolds placeholders only — hand-write the resolved title/prose/nature before commit-tail; a scaffold still carrying placeholders is refused.

**Review — 8 class-3 survivors, no mechanical rule for any:** `review-partition-strategy`, `reviewer-count-on-oracle-disagreement` (tier A is a hard stop), `shared-schema-touch-check`, `governing-spec-identification`, `finding-tradeoff-escalation-check`, `shallow-row3-waive-check`, `review-dispatch-vehicle-choice` (hand-dispatch — a Workflow `agent()` spawn skips the sidecar-provisioning hook), `quota-retry-vs-escalate`.

**Scale:** doc-only/no-executor/<50 LOC single file → None; executor dispatched, or >50 LOC, or shared-schema touched → `code-reviewer`. **`gates['review_scale']` carries measured `gross_loc`/`commit_count`/`surface_count` only when it resolves** — when `resolved: true`, consume it and never hand-derive; a `decisions` override beats the measurement only for a stated reason. **When it returns `resolved: false`** (all three unresolved, no `commit_slices`), re-run `brief` with `decisions["stage_paths"]` — that key gates the row-4 measurement, and `[]` is a valid, resolving answer when this session has no uncommitted files of its own. **Do NOT hand-sum instead**: `code_loc`, `commit_count` and `surface_count` are *outputs* of that measurement, not values a caller supplies, and a hand count uses different definitions — measured 1245/9 by hand against the engine's 976/26/4 on one diff, a different row. `resolved: false` means the measurement has not run yet, never that none is owed. **Brightline is mandatory, not advisory:** ≥500 gross LOC, OR ≥5 commits, OR ≥4 surfaces forces partitioned. Owns review for the whole chain including upstream `/mise-en-place` work — its clean verifiers never justify a lower scale. **Chain-end** → same rule over the range `resolve_mid_chain_review_scope` resolves, never hand-derived.

**Kira (`coordinator:overengineering-reviewer`) is dispatched on every close, and runs FIRST — before any Scale-selected `code-reviewer`.** A PM ruling, and unlike the L+ trigger below, explicitly NOT gated on the cited sizing-object's `estimate.tshirt`; do not add a threshold here "for symmetry" with that trigger. They are a proportionality lens over the Scale ladder above, never a replacement for it — a close whose Scale resolves to `None` (doc-only/no-executor/<50 LOC single file) still dispatches them. **Ordering is load-bearing, not incidental: a correctness pass over a shape Kira is about to condemn is wasted work, and worse, its integrated findings become sunk cost arguing against the rebuild.** Ask "should this code exist in this shape" before "is this code correct." Reviews are sequential and never parallel (`coordinator/skills/review/SKILL.md` § A.3), so: dispatch Kira → route their verdict → only then dispatch the Scale-selected `code-reviewer` over the resulting tree. Their verdict routes normally through `review-integrator`, except on `rebuild_recommended: true`, which takes the Rebuild-verdict routing rule above — see that rule rather than restating it here. **When a rebuild fires, the `code-reviewer` pass runs over the rebuilt shape, never the discarded one** — that is the whole reason this lens goes first; do not skip correctness review because a rebuild already happened. If their volume proves too noisy in practice, that is a finding to bring to the PM, not a threshold to add here.

**Hand-measuring the brightline — only once `stage_paths` has been supplied and the gate still will not resolve, never as a shortcut past it: sum per-owned-commit diffs, never a range across the oldest..newest span, and count code only** — `.md`/`.yaml`/`.yml` are excluded before counting, so a doc-only commit contributes nothing to `commit_count` or `gross_loc`. This is the same discipline `:86` below states for `sha_range` — write one per-slice record per commit (`<sha>~1..<sha>`, `~1` never `^`: cmd.exe eats a literal `^` in argv on Windows) — extended here to the brightline measurement itself, not a new rule. A range across the full span silently counts every peer commit landed in that window on a shared branch; this is the specimen's own error: measuring `oldest..newest` returned 33,246 gross LOC where summing this session's owned commits (`<sha>~1..<sha>` each) returned 16,037 — the peer-commit inflation this repo's own lessons corpus already names as a confirmed, recurring shared-branch failure mode, not a novel rule invented here. **When `partition_mandatory` is true and `commit_slices` is empty:** derive the slices from the per-owned-commit list this summation already produced — the summation and the slicing are the same walk, not two separate ones.

**L+ code-quality trigger — a separate derivation, not a parameter on Scale's measurement.** Scale
(above) keys off *measured* `gross_loc`/`commit_count`/`surface_count` — what the diff turned out to
be. The L+ trigger answers a different question — *how big was this meant to be* — and keys off the
**cited sizing-object's `estimate.tshirt`**: resolve the closing plan's `sizing_object:` frontmatter
citation and read `estimate.tshirt` off the sizing artifact it names — the plan is derived from the
sizing, so the sizing's t-shirt is the plan's t-shirt, and that pointer is the only keying surface.
`plan.schema.json` carries no t-shirt field of its own and none is added for this trigger; do NOT add
one — it would duplicate `estimate.tshirt` with no synchronization and create two sizes for one plan
that drift. Fires at `L` or `XL`. Do not reach for Scale's measured computation to answer this
question — it answers a different one.

**The trampoline — hand the ceremony to a fresh session rather than cap with the review unrun.** Once a scale is named you owe it. Two DIFFERENT routes reach the same exit, and conflating them is what makes an EM cite the wrong one:

- **Low context is not a trigger-4 reason.** It is ordinary context pressure and takes the ordinary `/handoff` route. Trigger 4's roster is a ratified CLOSED class of *un-runnable-here* reasons — a hard-stop oracle disagreement, a quota-exhausted dispatch, a live peer's files this session must not touch, an unresolved `review_scale` gate — each with a clearing event outside this session's reach, and it explicitly forbids admitting a reason by resemblance or analogy. Running low is not un-runnable; it is the most ordinary handoff condition there is.
- **When the review is genuinely un-runnable here** (`coordinator/skills/handoff/SKILL.md` § Step 0, trigger 4), exit via `/handoff` naming which member of that class fires and the event that clears it.

Both exit through `/handoff`, which is why they read as one route. They are not: one names a blocker with a clearing event, the other names nothing because there is nothing to clear. `/handoff`'s NO-tests carve this case out.

**Capping with the review unrun is forbidden; `verdict: pending` is not the escape hatch.** Tells to trampoline instead: "the next session can review this"; `reviewer: waived` pairing a non-`waived` verdict; a range narrowed to one commit because the honest range was refused; "mandatory" reasoned as advisory. Tripwire: `PARTITION-MANDATORY`.

`scan_dispatch_output(text) -> bool` checks every completed Agent dispatch's return body before a verdict-ok trail write (`QUOTA-EXHAUSTED-DISPATCH:` is sufficient alone). Trivial (row 1/2) sessions write no trail record; PM-waived logs `--reviewer waived --verdict waived`; `em-verified` is for a review you ran yourself, not `waived` (no verification) — both need ≥20-char justification.

**The review record is the RECEIPT on the reviewer's sidecar, not a trail record you write.** A dispatched `code-reviewer`/`review-integrator` stamps `review_receipt:` (session id, agent id, agent type, `stamped_at`) into its own sidecar frontmatter as part of finishing; `gates.review_receipt` reads it and `jp-review-receipt-block-stamp` gates the terminal stamp on it. You write nothing — **dispatching the reviewer records the review; the reviewer returning is what discharges it.** The engine splices that receipt at spawn, so a crashed or still-running reviewer carries one identical to a finished reviewer's; confirm the return (`scan_dispatch_output`) before reading the gate as green. Tripwire: `A-RECEIPT-SPLICED-AT-SPAWN-ATTESTS-DISPATCH-NOT-COMPLETION`. `blocks: false` on that gate is the close's review record. A `detail` reading `no integrator receipt (review ran, findings not recorded as applied)` means the findings were folded in by the EM rather than by a dispatched `review-integrator`: legitimate for a `code-reviewer` slice, but say so at close rather than letting it read as an integrator that ran. **Never for a Kira verdict carrying findings** — that routes to a `review-integrator` (or the refactor executor on `rebuild_recommended: true`), and `guard-kira-verdict-routed` hard-stops the close otherwise: the route's stamp is the only artifact discharging the routing rule, and an EM-folded verdict leaves none. Already applied them yourself? Dispatch the integrator over your own application — verifying and stamping is a legitimate remit. **`decisions["review"]` keys go nested under `"review"`, never flat `review_*`** — flat keys silently skip `d-attest-review-verified` while exiting 0. **`decisions["review"]` itself is dict-XOR-list, never both.** A single-slice close supplies a flat dict of review fields directly under `"review"`; a partitioned close supplies a list, one dict per slice, in slice order. Supplying a dict where slices are partitioned (or a list for a single-slice close) is a shape mismatch, not an equivalent encoding — pick the one matching this close's partition state. **Never hand-roll a per-commit trail write.** `review_trail.write` and its CLIs are a gravestone (kill-ledger K-060) whose successor is this receipt — it has no returning implementation, so a refusal from it is the dead surface answering, never a signal about your close. A close whose reviewers stamped receipts is reviewed; it does not read `blocked` because a dead op declined to record it. Tripwire: `A-SUSPENDED-OP-IS-NOT-A-MECHANISM-TO-WAIT-OUT`.

**`sha_range` must contain only this session's own commits** — a foreign-session guard refuses a range carrying another session's `Session-Id` trailer (normal on a shared branch); write one per-slice record per commit instead (`<sha>~1..<sha>` — `~1`, never `^`: cmd.exe eats a literal `^` in argv on Windows). **Slice; never narrow** — narrowing the range or lowering scale until something writes is forbidden even when the review genuinely ran. A legitimate bookkeeping exclusion states itself and its LOC.

**A chain-ancestry waiver is provenance, not review discharge — it does not clear a HALT.** `certifies_review: false` reads "ancestry NOT reviewed," and re-running does not clear it either. Tripwire: `WAIVER-IS-PROVENANCE-NOT-DISCHARGE`.

---

## Concurrent-EM shared-branch disposition

**Case (c) is not always an orphan** — often a live peer's in-flight files (no cross-machine liveness signal exists). `brief` classifies a/b/c mechanically and surfaces the peer-vs-orphan call as `concurrent-peer-attribution` (revalidated at dispatch — a peer can claim between brief and apply); disposing case (c) is EM judgment. Weak or contradictory signals default to case (c), never a guess. If a peer is plausibly live, never stash or adopt their paths — commit only your own files by explicit path.

Once ruled out: **commit** with provenance (per `snippets/scoped-commit-route.md`), **stash with provenance** (`git stash push -u -m "orphaned-WT <date> workstream-complete: <path> — left by unknown session" -- <path>`), or **explicitly leave it owned by X**. Never terminate with case-(c) files dirty and unnamed. Orphan `.tmp.<pid>.<nanos>` files are an Edit-tool crash artifact — diff before deleting.

---

## Apply — execute the directives

`& "$env:COORDINATOR_SETTINGS_HOME\bin\workstream-complete-assemble.exe" apply --decisions-file <path>` — the file is a JSON
object whose keys are *either* a `judgment_point_id` (value `{"disposition": "<value>"}`) *or* one of the non-JP decisions keys (`stage_paths`, `review`, ...), each with its own flat shape — never wrap a non-JP key's value in a `{"disposition": ...}` envelope; a nested `{"disposition": [...]}` for `stage_paths` is not a recognized shape and the gate cannot distinguish it from the key being absent. `stage_paths` itself is a flat list: `{"stage_paths": ["<path>", ...]}`.
(resolved per `snippets/resolve-coordinator-bin.md`: Shape A/B on POSIX hosts, Shape W on PowerShell)

`decisions` carries every value the compute half can't read off disk — lessons, resolved completion-nature/prose, memo/scratch dispositions, review-partition slice map, commit subject/prose. Fires every open-gated directive.

**`apply` does not commit — there is no commit-tail directive.** It exits 0 with every directive `returned` and the tree still dirty; treating that as a clean close is exactly the green-looking-ceremony-with-no-record failure. The tail is yours, in this order:

1. **Scoped commit** of the completion entry, Session Ledger row, and your own files, per `snippets/scoped-commit-route.md`.
2. **Nothing** — the review record landed when the reviewer stamped its sidecar receipt. Confirm
   `gates.review_receipt.blocks` is `false` and name any missing integrator receipt in the summary.

**The terminal stamp is gated engine-side, and a blocked stamp is not a failed one.**
`d-stamp-plan-implemented` carries three empty-`resolves` judgment points on its `depends_on` —
`jp-open-spine-rows-block-stamp` (unwaived `open` rows, or `indeterminate`),
`jp-landed-reconciliation-block-stamp` (plan `landed` with unticked ACs), and
`jp-review-receipt-block-stamp`. An unresolved one lands in `report["blocked"]` under
`HALTED_AT_JUDGMENT`, **not** `report["failed"]` — so a close exits non-failing with no stamp.
`waived_open_spine_row_ids` clears leg 1's `applicable` arm only, never `indeterminate`. Do not
build a doctrine gate beside these; report the incomplete and resolve the leg. Tripwire:
`AN-HONEST-INCOMPLETE-DOES-NOT-EARN-THE-WRAP-OFFER`.

`apply` prints diagnostics on every non-zero exit — read them, don't memorize codes. Exit `2` (`DIRECTIVE_FAILED`) means nothing landed; exit `4` (`PARTIAL_MUTATION`) means some landed and some failed. A client-side timeout is not a failure signal. In every case reconcile against actual commit state before re-running.

Push runs on a cadence, not on this commit. `push_status: "cadence-pending"` is success — nothing is in flight and nothing needs re-checking; the branch publishes at the next named checkpoint (`/pickup`, `/quick-wrap`, `/workday-start`, the workday/workweek close ceremonies). `push_status: "pushed"` is equally success; `"deferred"` still reads as success where an older engine emits it, and there alone the confirm-via-`git branch -r --contains <sha>` guidance applies. Never `git push` to "fix" an apparent delay. Confirm the canonical string against `commit_pipeline.py`'s `PUSH_STATUS_*` block if it looks unfamiliar.

---

## Execution-Residual Sweep (judgment step — nothing computes it)

A residual discovered mid-execution never counts in the harvest — `Queued 0` reads as "nothing left behind." Tell: a residual recorded only in prose, with no queue id/spine row/commit behind it. One disposition per item; nothing to sweep is ordinary — omit the line. **Default is fix it now**; routing elsewhere costs a named reason from a closed class:

| reason class | means |
|---|---|
| `peer-contention` | live peer holds the file — name the surface, confirm via session-registry |
| `other-repo` | belongs to a sibling — memo routes it, or a live send only if peer confirmed live and both gates pass; default to memo when unclear |
| `own-plan` | large enough to need its own plan — name the scale |
| `irreversible` | needs PM assent |
| `not-real` | doesn't survive examination — say why |

**Not a named reason:** *"predating this work"*, *"pre-existing"*, *"not now"*, *"follow-up"*, *"out of scope"*, *"noted for the next sweep"*. A break-class residual with none of the five is fixed, not filed. The auto-memory drain gate runs only at `/workday-complete`/`/workweek-complete`, never here.

---

## Completion verdict

**Consume `gates.completion_verdict` in the close narration.** It composes the five gates this
ceremony already reads (`session_shape`, `review_receipt`, spine-row completeness, plan-landed
reconciliation, consumed-handoff completeness) into one verdict — read it off `gates` rather than
re-deriving a close narrative by hand from the individual gate objects.

**Three things to hold in mind reading it, none of them a simple pass/fail lens:**

- The completeness gate collapses two distinct cases into one `indeterminate`: a leg that is "not
  chain-terminal" (nothing to check yet) and a leg that "is chain-terminal but the consumed handoff
  could not be read" (an archived-away handoff degrades into this case). Both read `indeterminate`
  on the wire; the narration cannot tell them apart without checking the underlying leg detail.
- `applies: false` does not mean the same thing on every gate within one envelope — it is not a
  uniform status axis. Treating an `applies: false` on one gate as equivalent to `applies: false`
  on another gives a false-clean reading.
- `indeterminate` is the ordinary case, not the exception — a typical close reads `indeterminate`
  on 3 of the 5 gates. Narration that treats any `indeterminate` as noteworthy will fire on nearly
  every close; only a gate-specific reading (per the two points above) tells you which
  `indeterminate`s are routine and which are worth naming.

**Residue → verb lookup, for whatever the verdict leaves outstanding:**

| Residue shape | Verb |
|---|---|
| Blocked on further work this session should still finish | trampoline (`/handoff`, review-owed-close class) |
| Not worth doing | won't-do |
| Worth doing, not now | backlog |
| A distinct workstream someone else should pick up | spinoff |

`indeterminate` renders as `indeterminate` — never as "incomplete". It is 3 of 5 gates on an
ordinary close, so rendering the common case as a failure state makes a healthy close look broken.
The `review_scale` exclusion (`resolved: false` feeding no verdict input) is objected to, not
accepted as designed; the objection is recorded and sits on the engine plane. Neither is an open
call and neither goes to the PM (DR-190 § 46).

---

## Final Summary

**Report by exception.** One line always; everything else only when *not* clean. When this
session holds the Group EM role, the report additionally follows
`coordinator/snippets/group-em-output-contract.md` — one emission form only (a decision awaiting
the PM), offers and self-labelled-optional asks excluded, filtered at source not appended at the
end.

**A baton shipping here can newly close its whole chain.** Run
`<plugin-root>/bin/baton-chain-closure.py signal <this-handoff-path>` after this ceremony's own
close — it re-derives chain closure from disk (never a remembered duty) and emits nothing unless
this baton's whole chain, not this baton alone, has resolved. Silence is the common case. Any
output it prints already conforms to `group-em-output-contract.md`; do not re-shape it, and do
not run `chains` here — that verb enumerates the corpus and is diagnostic, never PM-facing.

**A leg parked as blocked on a sibling repo carries its exchange, or it is not parked.** Check the
three conjuncts in `coordinator/snippets/cross-repo-block-exchange.md` — declared, addressed,
answered — and name the one that failed, never the repo. Tripwire:
`A-SENT-MEMO-IS-NOT-AN-EXCHANGE`.

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

**`not-applicable` is not `indeterminate`.** `not-applicable`: nothing to look at (e.g. a `session-handoff`'s leg A resolves via `deliverable_id`/plan `status:` and finds no live plan) — stays silent, same as `clean`. `indeterminate`: the gate tried to look and couldn't — declining to look because a field said it needn't is `indeterminate` wearing the wrong token, and must be reported. Tripwire: `NOT-APPLICABLE-SPANS-TWO-SILENCES`.

**Do not print** `Lessons captured`/`Work archived`/`Docs updated`/`Orientation refreshed` — counts the commit already records, not PM decisions. **An automated mechanism's routine success is never a PM line**: pushing is auto-pushed, the cache regenerates itself. Report the machine only when it *failed*, and never ask the PM to verify what it already did. **Archival is NOT in that set — it is not automatic, and this ceremony performs no directive that does it.** The spine stamps the governing plan and any actioned memo, but it emits NO archival directive and it does NOT stamp the baton: no close writes `shipped_in`/`shipped_in_kind` or flips a handoff's `deployment_state`, since K-046 (2026-08-23) deleted the `wsc_tail` hop that did. The drain is a mandatory EM action (§ Genuine EM actions), not a machine step — so do not describe archival to the PM as something that happened by itself, and do not author a second sweep against the one that exists: the drain is the only implementation, backstopped (not owned) by the `/workday-complete` spine's `reap-orphaned-in-flight-handoffs` + `handoff-housekeeping` pair (`coordinator/docs/wiki/coordinator-tripwires/terminal-batons-are-swept-at-close-not-left-to-the-next-ceremony.md`).

**Classify flags by severity first.** A break-class defect (broken/would-break/fails/leaks/silently-bypasses) is fix-by-default — fix it and report the fix, never a passive `Flag to PM:`; only direction-class items go there. → global `CLAUDE.md § Flag Severity`.

---

## What this does NOT do

- Rebuild the Step-0 session-shape gate, the coverage judgment point, or `resolve_repo_root` — already correct.
- Compose or extend `apply_base.py` — a deliberate divergence from the `pickup`/`baton`/`merge`/`consolidate` lineage.
- Propagate `/workday-complete`'s dirty-tree auto-disposition — stricter surface here, on purpose.
- Auto-resolve tier-A oracle disagreement — a hard stop; needs `/autonomous` plus a recorded reviewer.
