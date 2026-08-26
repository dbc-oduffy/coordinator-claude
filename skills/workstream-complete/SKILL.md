---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work. No handoff — this is for work that's *done*.

> **Mutual exclusion with `/handoff`.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP, use `/handoff`. Two workstreams (one done, one live) → end each separately, naming which. Exception: a named review scale this session can't run+integrate → the trampoline, § Review. → coordinator CLAUDE.md § Handoff Lineage.

This ceremony is computed end to end — session-shape, plan reconciliation, lessons, completion-entry, memo lifecycle, scratch self-clean, orientation refresh, and commit-tail ship as `directives[]` naming a CLI; what cannot be resolved ships as `judgment_points[]`. Never recompute by hand what a field already answers.

`$ARGUMENTS`, if provided: fold into Final Summary and completion-entry prose.

---

## Compute the ceremony

On a PowerShell host, use the `.cmd` sibling through the call operator (Shape W) instead of the
`${...}` POSIX-shell form below — ladder and shapes: `snippets/resolve-coordinator-bin.md`.

```bash
workstream-complete-assemble brief [--decisions-file <path>]
```
**Prefer `--decisions-file` on both subcommands; `--decisions '<json>'` is the short-payload
convenience.** A real payload carries prose (completion rationale, commit subject, review records),
and prose on argv is mangled by the tool seam. Supplying both channels at once fails loud.
(resolved per `snippets/resolve-coordinator-bin.md`: Shape A/B on POSIX hosts, Shape W on PowerShell)

Returns (`artifact`/`preflight`/`gates`/`directives`/`judgment_points`/`decisions`/`narration`/`next_move`). `preflight.session_shape` (= `gates.session_shape`) carries `sid`, `disposition` (`single-session`/`predecessor-consumed`; reads backward — consumed a predecessor, not that a successor follows), `consumed_handoff`, detector diagnostics. `jp-session-shape` is the untrusted-gate point for an uncertain resolution.

---

## Genuine EM actions — no directive can perform these

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

- **Review-partition dispatch**: freeze each slice's diff first; one `code-reviewer` per slice, `run_in_background: true`; one 1:1 `review-integrator` per slice, never a union-integrator. The integrator is unconditional on verdict — an `OK` slice with findings is still a slice with findings, and a reviewer's self-disposition closes nothing. Tripwire: `REVIEWER-SELF-DISPOSITION-IS-NOT-CLOSURE`.
- **Doc-fragile domain lens**: `compute_doc_fragile_gate` match → dispatch `coordinator:docs-checker` alongside `code-reviewer`, same diff.
- **Execution-observations fold**: read each sidecar's `divergence` as quoted narrative, never EM-authored prose; surface a crashed-executor marker before deleting it.
- **Memo-resolution / self-clean disposition**: no signal for which memos resolved, or which scratch files to keep — ask/decide once, plain prose; evidence is surfaced, never picked for you.
- **Session Ledger row append** (predecessor-consumed only): one row to the consumed handoff's `## Session Ledger` — the sole edit `/pickup`'s frozen-body rule carves out.

---

## Resolve judgment points

**3 classes.** 1 = CLI-computable (not listed here). 2 = interpretation but not *this EM's* — closed enum, a differing answer is demonstrably wrong; demote when possible. 3 = judgment/taste/tradeoff. A re-test names a class per item it **keeps**, not only those it demotes.

**A shipped `recommendation` is applied by default and shown, not asked** — carry it into the decisions map and report what was filed as a receipt (`completion-nature-classification`/`jp-coverage-verdict` both ship one). A null earns attention only when genuine: `jp-session-shape` always, `jp-review-scale` while unresolved, tail-blocking scaffold/commit-subject/consumed-handoff whenever they fire. Blocked computation or a missing producer is a break-class engine defect — resolve cheaply or memo, after verifying the producer is really absent.

**`jp-session-shape` is honoured by the tail but never reflected back in `brief`'s gate readout** — after you answer it, a re-`brief` still shows `gates.session_shape.disposition` at the original detector verdict, with exit 0 and no diagnostic. That is not a discarded decision. Confirm from `wsc-tail`'s own output, never by re-`brief`; re-answering and reaching for `override-known-in-flight` are both wrong.

**The rest — read the object.** Every point not named here carries its own prompt/evidence on `judgment_points[]`.

**Completion entry:** TITLE + ≤8-sentence body, banned sections `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria`, `## Universal lessons captured`. `d-complete-entry` scaffolds placeholders only — hand-write the resolved title/prose/nature before commit-tail; a scaffold still carrying placeholders is refused.

**Review — 8 class-3 survivors, no mechanical rule for any:** `review-partition-strategy`, `reviewer-count-on-oracle-disagreement` (tier A is a hard stop), `shared-schema-touch-check`, `governing-spec-identification`, `finding-tradeoff-escalation-check`, `shallow-row3-waive-check`, `review-dispatch-vehicle-choice` (hand-dispatch — a Workflow `agent()` spawn skips the sidecar-provisioning hook), `quota-retry-vs-escalate`.

**Scale:** doc-only/no-executor/<50 LOC single file → None; executor dispatched, or >50 LOC, or shared-schema touched → `code-reviewer`. `gates['review_scale']` carries measured `gross_loc`/`commit_count`/`surface_count`; a `decisions` override beats the measurement only for a stated reason. **Brightline is mandatory, not advisory:** ≥500 gross LOC, OR ≥5 commits, OR ≥4 surfaces forces partitioned. Owns review for the whole chain including upstream `/mise-en-place` work — its clean verifiers never justify a lower scale. **Chain-end** → same rule over the range `resolve_mid_chain_review_scope` resolves, never hand-derived.

**The trampoline — under low context, hand the ceremony to a fresh session rather than cap with the review unrun.** Once a scale is named you owe it; if context can't run+integrate, exit via `/handoff` (successor runs-review-then-caps), naming the context signal. `/handoff`'s NO-tests carve this case out.

**Capping with the review unrun is forbidden; `verdict: pending` is not the escape hatch.** Tells to trampoline instead: "the next session can review this"; `reviewer: waived` pairing a non-`waived` verdict; a range narrowed to one commit because the honest range was refused; "mandatory" reasoned as advisory. Tripwire: `PARTITION-MANDATORY`.

`scan_dispatch_output(text) -> bool` checks every completed Agent dispatch's return body before a verdict-ok trail write (`QUOTA-EXHAUSTED-DISPATCH:` is sufficient alone). Trivial (row 1/2) sessions write no trail record; PM-waived logs `--reviewer waived --verdict waived`; `em-verified` is for a review you ran yourself, not `waived` (no verification) — both need ≥20-char justification.

**`decisions["review"]` keys go nested under `"review"`, never flat `review_*`** — flat keys are silently ignored and the tail skips with no trail while exiting 0, a green-looking ceremony with no record. The engine validates `reviewer`/`scope`/`verdict`/`reviewer_evidence` enum values and names the legal set on rejection. Omit `reviewer_evidence` only for `wsc-auto-adjudication` or a delegate reviewer at `verdict: pending`; everywhere else a missing/unresolvable value refuses the write. **`sha_range`/`diff_loc` come from `gates.review_scale.commit_slices`** — one entry per session-owned commit, oldest-first; fill in `reviewer`/`scope`/`verdict` per entry and pass the list through as `decisions["review"]`, never reconstructed by hand and never a dedicated CLI arg (it rides the `decisions` payload like every other value). The key is absent, not empty, when the measurement is unresolvable; a resolved-but-empty list means zero owned commits. `uncommitted_code_loc` names the measured code no slice covers. **On total refusal** (every per-commit slice write refused), `verdict` still reads `blocked`, never `pending`/`waived` — the write raises (exit 2, non-halting), commit lands, no trail lands, defect named in output.

**`sha_range` must contain only this session's own commits** — a foreign-session guard refuses a range carrying another session's `Session-Id` trailer (normal on a shared branch); write one per-slice record per commit instead (`<sha>~1..<sha>` — `~1`, never `^`: cmd.exe eats a literal `^` in argv on Windows). **Slice; never narrow** — narrowing the range or lowering scale until something writes is forbidden even when the review genuinely ran. A legitimate bookkeeping exclusion states itself and its LOC.

**A chain-ancestry waiver is provenance, not review discharge — it does not clear a HALT.** `certifies_review: false` reads "ancestry NOT reviewed," and re-running does not clear it either. Tripwire: `WAIVER-IS-PROVENANCE-NOT-DISCHARGE`.

---

## Concurrent-EM shared-branch disposition

**Case (c) is not always an orphan** — often a live peer's in-flight files (no cross-machine liveness signal exists). `d-run-wsc-tail` classifies a/b/c mechanically; disposing case (c) is EM judgment. Weak or contradictory signals default to case (c), never a guess. If a peer is plausibly live, never stash or adopt their paths — commit only your own files by explicit path.

Once ruled out: **commit** with provenance (per `snippets/scoped-commit-route.md`), **stash with provenance** (`git stash push -u -m "orphaned-WT <date> workstream-complete: <path> — left by unknown session" -- <path>`), or **explicitly leave it owned by X**. Never terminate with case-(c) files dirty and unnamed. Orphan `.tmp.<pid>.<nanos>` files are an Edit-tool crash artifact — diff before deleting.

---

## Apply — execute the directives

```bash
workstream-complete-assemble apply --decisions-file <path>   # json map of judgment_point_id -> {"disposition": "<value>"}
```
(resolved per `snippets/resolve-coordinator-bin.md`: Shape A/B on POSIX hosts, Shape W on PowerShell)

`decisions` carries every value the compute half can't read off disk — lessons, resolved completion-nature/prose, memo/scratch dispositions, review-partition slice map, commit subject/prose. Fires every open-gated directive through the commit-tail keystone.

`d-run-wsc-tail`/`apply` print diagnostics on every non-zero exit — read them, don't memorize codes. Their exit `2` means opposite things: for `d-run-wsc-tail` the commit **landed** (never re-run blind against an already-clean tree); for `apply` (`DIRECTIVE_FAILED`) nothing landed. `apply` exit `4` (`PARTIAL_MUTATION`) means some landed and some failed. A client-side timeout is not a failure signal. In every case reconcile against actual commit state before re-running.
<!-- engine-gap: field=directives[d-run-wsc-tail].commit_landed producer=claude_klabauter:workstream_complete.apply memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

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

## Final Summary

**Report by exception.** One line always; everything else only when *not* clean.

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
| `**Flag to PM:**` | a direction-class item survived severity classification below |

**`not-applicable` is not `indeterminate`.** `not-applicable`: nothing to look at (e.g. a `session-handoff`'s leg A resolves via `deliverable_id`/plan `status:` and finds no live plan) — stays silent, same as `clean`. `indeterminate`: the gate tried to look and couldn't — declining to look because a field said it needn't is `indeterminate` wearing the wrong token, and must be reported. Tripwire: `NOT-APPLICABLE-SPANS-TWO-SILENCES`.

**Do not print** `Lessons captured`/`Work archived`/`Docs updated`/`Orientation refreshed` — counts the commit already records, not PM decisions. **An automated mechanism's routine success is never a PM line**: pushing is auto-pushed, archival is swept, the cache regenerates itself. Report the machine only when it *failed*, and never ask the PM to verify what it already did.

**Classify flags by severity first.** A break-class defect (broken/would-break/fails/leaks/silently-bypasses) is fix-by-default — fix it and report the fix, never a passive `Flag to PM:`; only direction-class items go there. → global `CLAUDE.md § Flag Severity`.

---

## What this does NOT do

- Rebuild the Step-0 session-shape gate, the coverage judgment point, or `resolve_repo_root` — already correct.
- Compose or extend `apply_base.py` — a deliberate divergence from the `pickup`/`baton`/`merge`/`consolidate` lineage.
- Propagate `/workday-complete`'s dirty-tree auto-disposition — stricter surface here, on purpose.
- Auto-resolve tier-A oracle disagreement — a hard stop; needs `/autonomous` plus a recorded reviewer.
