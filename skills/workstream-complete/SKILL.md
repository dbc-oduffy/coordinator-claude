---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work: capture lessons, update docs to reflect completion. No handoff — this is for work that's *done*.

> **Mutual exclusion with `/handoff`.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP, use `/handoff`. Two workstreams (one done, one live) → end each separately, naming which. Exception: a named review scale this session can't run+integrate → the trampoline, § Review. → coordinator CLAUDE.md § Handoff Lineage.

The `workstream_complete` assembler computes this ceremony end to end — session-shape, plan reconciliation, lessons, completion-entry, memo lifecycle, scratch self-clean, orientation refresh, commit-tail are `directives[]` naming a CLI; what it can't resolve ships as `judgment_points[]`. Read the resolved objects — never recompute by hand what a field already answers.

`$ARGUMENTS`, if provided: fold into Final Summary and completion-entry prose.

---

## Compute the ceremony

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workstream-complete-assemble" brief [--decisions '<json>']
```

Returns an 8-key object (`artifact`/`preflight`/`gates`/`directives`/`judgment_points`/`decisions`/`narration`/`next_move`). `preflight.session_shape` (= `gates.session_shape`) carries `sid`, `disposition` (`single-session`/`predecessor-consumed`; reads backward — consumed a predecessor, not that a successor follows), `consumed_handoff`, detector diagnostics. `jp-session-shape` is the untrusted-gate point for an uncertain resolution — see § Resolve judgment points for what that means.

---

## Genuine EM actions — no directive can perform these

**Invoking this skill IS the dispatch request** for `code-reviewer`/`review-integrator`/`docs-checker` below — no separate re-clear. Other PM gates (pre-`/execute-plan`, cross-repo-commit, ask-before-external-action) still bind. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

- **Review-partition dispatch**: freeze each slice's diff first; one `code-reviewer` per slice, `run_in_background: true`; one 1:1 `review-integrator` per slice, never a union-integrator. The integrator is unconditional on verdict — an `OK` slice with findings is still a slice with findings, and a reviewer's self-disposition closes nothing. Tripwire: `REVIEWER-SELF-DISPOSITION-IS-NOT-CLOSURE`.
- **Doc-fragile domain lens**: `compute_doc_fragile_gate` match → dispatch `coordinator:docs-checker` alongside `code-reviewer`, same diff.
- **Execution-observations fold**: read each sidecar's `divergence` as quoted narrative, never EM-authored prose; surface a crashed-executor marker before deleting it.
- **Memo-resolution / self-clean disposition**: no signal for which memos resolved, or which scratch files to keep — ask/decide once, plain prose; assembler surfaces evidence, doesn't pick.
- **Session Ledger row append** (predecessor-consumed only): one row to the consumed handoff's `## Session Ledger` — the sole edit `/pickup`'s frozen-body rule carves out.

---

## Resolve judgment points

**3 classes.** 1 = CLI-computable, not on this list. 2 = interpretation but not *this EM's* — enumerated inputs, closed enum, a differing answer is demonstrably wrong; demote when possible, else carry by necessity. 3 = judgment/taste/tradeoff. A re-test names a class per item it **keeps**, not only demotes — an unclassed kept item is the tell.

**A shipped `recommendation` is applied by default and shown, not asked** — carry into the decisions map, report what was filed as a receipt (`completion-nature-classification`/`jp-coverage-verdict` both ship one). A null earns attention only when genuine: `jp-session-shape` always, `jp-review-scale` while unresolved, tail-blocking scaffold/commit-subject/consumed-handoff whenever they fire (untrusted-gate, no recommendation by design). Blocked computation/missing producer are break-class engine defects instead — resolve cheaply or memo; verify a claimed-absent producer is really absent first.

**The rest — read the object.** Every judgment point not named here carries its own prompt/evidence on `judgment_points[]` — resolve directly against it.

**Completion entry:** TITLE + ≤8-sentence body, banned sections `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria`, `## Universal lessons captured`. `d-complete-entry` scaffolds placeholders only — hand-write the resolved title/prose/nature before commit-tail; a scaffold still carrying placeholders is refused.

**Review — 8 class-3 survivors, no mechanical rule for any:** `review-partition-strategy`, `reviewer-count-on-oracle-disagreement` (tier A is a hard stop), `shared-schema-touch-check`, `governing-spec-identification`, `finding-tradeoff-escalation-check`, `shallow-row3-waive-check`, `review-dispatch-vehicle-choice` (hand-dispatch — a Workflow `agent()` spawn skips the sidecar-provisioning hook), `quota-retry-vs-escalate`.

**Scale:** doc-only/no-executor/<50 LOC single file → None; executor dispatched, or >50 LOC, or shared-schema touched → `code-reviewer`. `gates['review_scale']` carries the measured `gross_loc`/`commit_count`/`surface_count`; a `decisions` override beats the measurement only for a stated reason, never routine. **Brightline is mandatory, not advisory:** ≥500 gross LOC, OR ≥5 commits, OR ≥4 surfaces forces partitioned regardless. Owns review for the whole chain, including upstream `/mise-en-place` work — its clean verifiers never justify a lower scale. **Chain-end** → same scale rule, taken over the range `resolve_mid_chain_review_scope` resolves, never hand-derived.

**The trampoline — under low context, hand the ceremony to a fresh session rather than cap with the review unrun.** Once a scale is named you owe it; if context can't run+integrate, exit via `/handoff` (successor runs-review-then-caps, never cap-and-annotate), naming the context signal. `/handoff`'s NO-tests carve this case out.

**Capping with the review unrun is forbidden; `verdict: pending` is not the escape hatch.** Tells to trampoline instead: "the next session can review this"; `reviewer: waived` pairing a non-`waived` verdict; a range narrowed to one commit because the honest range was refused; "mandatory" reasoned as advisory. Tripwire: `PARTITION-MANDATORY`.

`scan_dispatch_output(text) -> bool` checks every completed Agent dispatch's return body before a verdict-ok trail write (`QUOTA-EXHAUSTED-DISPATCH:` is sufficient alone). Trivial (row 1/2) sessions write no trail record; PM-waived logs `--reviewer waived --verdict waived`; `em-verified` is for a review you ran yourself, not `waived` (no verification) — both need ≥20-char justification.

**`decisions["review"]` keys go nested under `"review"`, never flat `review_*`** — flat keys are silently ignored and the tail skips with no trail while exiting 0, a green-looking ceremony with no record. The engine validates `reviewer`/`scope`/`verdict`/`reviewer_evidence` enum values and names the legal set on rejection. Omit `reviewer_evidence` only for `wsc-auto-adjudication` or a delegate reviewer at `verdict: pending`; everywhere else a missing/unresolvable value refuses the write. **`sha_range`/`diff_loc` come from `gates.review_scale.commit_slices`** — one entry per session-owned commit, oldest-first; fill in `reviewer`/`scope`/`verdict` per entry and pass the list through as `decisions["review"]`, never reconstructed by hand and never a CLI arg (`workstream-complete-assemble` takes only `--decisions`). The key is absent, not empty, when the measurement is unresolvable; a resolved-but-empty list means zero owned commits. `uncommitted_code_loc` names the measured code no slice covers. **On total refusal** (every per-commit slice write refused), `verdict` still reads `blocked`, never `pending`/`waived` — the write raises (exit 2, non-halting), commit lands, no trail lands, defect named in output.

**`sha_range` must contain only this session's own commits** — a foreign-session guard refuses a range carrying another session's `Session-Id` trailer, normal on a shared branch; write one per-slice record per commit (`<sha>~1..<sha>` — `~1`, never `^`: cmd.exe eats a literal `^` in argv on Windows) instead. A gate stops unreviewed work, it does not collect an attestation that work was reviewed — narrowing the range or lowering scale until something writes is forbidden even when the review genuinely ran. **Slice; never narrow** — a legitimate bookkeeping exclusion states itself and its LOC.

**A chain-ancestry waiver is provenance, not review discharge — it does not clear a HALT.** `certifies_review: false` reads "ancestry NOT reviewed," and re-running does not clear it either. Tripwire: `WAIVER-IS-PROVENANCE-NOT-DISCHARGE`.

---

## Concurrent-EM shared-branch disposition

**Case (c) is not always an orphan** — often a live peer's in-flight files (no cross-machine liveness signal exists); `d-run-wsc-tail` classifies (a/b/c) mechanically, disposing case (c) is EM judgment. Weak/contradictory signals default to case (c), never a guess; if a peer is plausibly live, never stash/adopt their paths — commit only your own files by explicit path.

Once ruled out: **commit** with provenance (`ceremony.scoped_git_commit`), **stash-with-provenance** (`git stash push -u -m "orphaned-WT <date> workstream-complete: <path> — left by unknown session" -- <path>`), or **explicit "leave it owned by X."** Never terminate with case-(c) files still dirty and unnamed. Orphan `.tmp.<pid>.<nanos>` files are an Edit-tool crash artifact — diff before deleting.

---

## Apply — execute the directives

```bash
"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workstream-complete-assemble" apply --decisions '<json map of judgment_point_id -> {"disposition": "<value>"}>'
```

`decisions` carries every value the compute half can't read off disk — lessons, resolved completion-nature/prose, memo/scratch dispositions, review-partition slice map, commit subject/prose. Fires every open-gated directive through the commit-tail keystone.

`d-run-wsc-tail`/`apply` print their own diagnostics on every non-zero exit — read them, don't memorize codes. Their exit `2` means opposite things: `d-run-wsc-tail` exit `2` means the commit **landed** — read diagnostics, never re-run blind against an already-clean tree; `apply` exit `2` (`DIRECTIVE_FAILED`) means nothing landed. `apply` exit `4` (`PARTIAL_MUTATION`) means some directives landed and some failed — reconcile before re-running, never blind-retry. A client-side timeout is not a failure signal either — reconcile against the actual commit state first, never re-run on the strength of a timeout alone.
<!-- engine-gap: field=directives[d-run-wsc-tail].commit_landed producer=claude_klabauter:workstream_complete.apply memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

Push is deferred/detached — `push_status: "deferred"` is success; confirm via `git branch -r --contains <sha>`, never `git push` to "fix" an apparent delay.

---

## Execution-Residual Sweep (judgment step — nothing computes it)

A residual discovered mid-execution never counts in the harvest — `Queued 0` reads as "nothing left behind." Tell: a residual recorded only in prose, no queue id/spine row/commit behind it. One disposition per item; nothing to sweep is ordinary — omit the line. **Default is fix it now**; routing elsewhere costs a named reason from a closed class:

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

**Report by exception.** Two lines always; everything else only when *not* clean.

```
## Session Complete

**Work done:** [1-2 sentence summary]
**Pushed:** [branch name (deferred/detached) / no — reason]
```

Append a line **only** if its condition holds:

| Line | Include only when |
|---|---|
| `**Completeness checklist:**` | `gates.completeness_checklist` WARN — name the N unverified items |
| `**Consumed-handoff completeness:**` | element reports `blocks`/`indeterminate` — name handoff+leg (`not-applicable` is a 4th leg-A verdict, NOT reported) |
| `**Deferral harvest:**` | N ≥ 1 queued |
| `**Execution residuals:**` | sweep resolved ≥1 item — `<residual> -> fixed <sha>` or `-> <queue id \| memo \| spine row> (<reason-class>: <clause>)` |
| `**Post-summary reconcile:**` | commits were folded |
| `**Flag to PM:**` | a direction-class item survived severity classification below |

**`not-applicable` is not `indeterminate`.** `not-applicable`: nothing to look at (e.g. a `session-handoff`'s leg A resolves via `deliverable_id`/plan `status:` and finds no live plan) — stays silent, same as `clean`. `indeterminate`: the gate tried to look and couldn't — declining to look because a field said it needn't is `indeterminate` wearing the wrong token, and must be reported. Tripwire: `NOT-APPLICABLE-SPANS-TWO-SILENCES`.

**Do not print** `Lessons captured`/`Work archived`/`Docs updated`/`Orientation refreshed` — each is a count the commit already records, not a PM decision.

**Classify flags by severity first.** A break-class defect (broken/would-break/fails/leaks/silently-bypasses) is fix-by-default — fix it, report the fix, never a passive `Flag to PM:` choice; only direction-class items go there. → global `CLAUDE.md § Flag Severity`.

---

## What this does NOT do

- Rebuild the Step-0 session-shape gate, the coverage judgment point, or `resolve_repo_root` — already correct.
- Compose or extend `apply_base.py` — a deliberate divergence from the `pickup`/`baton`/`merge`/`consolidate` lineage.
- Propagate `/workday-complete`'s dirty-tree auto-disposition — stricter surface here, on purpose.
- Auto-resolve tier-A oracle disagreement — a hard stop; needs `/autonomous` plus a recorded reviewer.
