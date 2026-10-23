---
name: pickup
description: Resume from a handoff or action a cross-repo memo.
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[handoff-file-path | memo-file-path]"
---

# Pickup — Resume from Handoff or Action a Memo

A baton, not a menu — read it, run with it; no summarizing back for approval. Build work in it is fired, not hand-done: fire with context, own the swimlanes (`THE-EM-TIME-AND-COST-SPENT-IS-A-RED-FLAG`).

**The cross-repo memo inbox does not move without a deliberate act.** Every memo leaves by being
actioned here.

You have claimed this artifact. Its classification, routing, and open decisions arrive
with your prompt; don't re-derive them. Unconditional directives
execute as you reach them; what is left is a decision you owe.

---

## Classify, Load, Reconcile Against Reality

**Read classification off `artifact.classification`** — never guess one to keep moving.

**An `awaiting_gate` baton may still be plannable.** One `blocked_by` edge carries two gates:
planning opens when every blocker is coded **or** carries a review-approved plan; execution only
when every blocker is coded. Read both, never inferring from `deployment_state`:
`coordinator-invoke roadmap.plan_gate '{"subject":"<baton-id>"}'` returns `verdict.planning_gate`
and `verdict.execution_gate`. Picking up on an open planning gate does **not** authorise
execution — `/execute-plan` re-checks it. Tripwire: `A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`.
On a `gate_notes` gate, read the clearer (human-PM / peer / external) and its legal dispositions
off `gates.gate_check.clearer` and the jgate recommendation; where the brief lacks `clearer`, classify it from `gate_notes`.

**On arrival with any parked baton**, run `coordinator-invoke baton.awaiting_gate_recheck '{}'`. Where `machine_condition_met` is true, route the seed or clear the gate. Otherwise, if `parked_days` shows the gate holder sat on it too long, send its `memo_draft`, correcting `--to` whenever `holder_source` is not `field` (inference is a regex on the gate prose). The op only computes; it sends no memo.

**Reconcile before executing anything.** Per-item evidence is a candidate, never a verdict — weigh
commit-closure candidates and stale `awaiting_gate` signals yourself; a changed target/scope/AC on
a stamped-authorization mismatch surfaces to the PM. **Stealth-skip**: an item marked shipped on
prose rationale instead of a commit SHA ("subsumed by X") is the forbidden defer disposition —
treat it as pending, re-verify the literal AC against `HEAD`, surface the violation.
**A claimed failure count is hypothesis**: classify each failure's CLASS (collection vs runtime)
and dep-TIER first; an unclassified count is unverified.
**An aged baton can be superseded under another slug**: topic-search its core mechanism across
every branch's history since authoring, and the completed archive, before executing its headline.

**A cited surface already changed on disk may be a crashed peer's landed work.** Before
re-implementing, read its commit history since authoring (all branches); a commit whose
`Session-Id` trailer has no live PID is recoverable. A first read showing it unchanged can be stale.

**A dissolved gate is not a cleared one.** The aging recheck
(`coordinator/docs/wiki/baton-lifecycle/spinoff-handoffs.md` § Awaiting_gate aging) asks whether
the named condition fired, not whether the gating MECHANISM still exists; a superseding decision that deleted it goes to the PM.

**An anti-scope constraint ("do NOT do X — sibling Y owns it") decays like a positive
premise**: re-verify its witness against disk (`spinoff-handoffs.md` § Pickup-side premise check).

**An absence under `<path>` is evidence only if `<path>` still hosts that artifact class**
(`A-HANDOFFS-NO-ON-DISK-EVIDENCE-IS-A-FALSE-NEGATIVE-WHEN-THE-SURFACE-MIGRATED-REPOS`).

**Report briefly** — picked-up heading, branch, first recommended step. Prepend any recovery
banner (prior session died uncleanly: verify disk state first).

**`pickup a AND b` is N independent dispositions** (also `/mise-en-place`) — one standing down never blocks a sibling.

**Succession is N→1, never N→N.** A session's successor handoff is **one** artifact; resolve
`j-fan-in-cardinality` (`round_trip: terminal`) by naming the surviving `deliverable_id`, don't
guess. Every dropped predecessor rides as an `additional_predecessors:` down-edge, matching the `continued_into` up-edges on each predecessor.

---

## Claim and Commit

Claim, terminal flip, and pre-decision revert land automatically on a clean pickup. Resolve every `judgment_points` entry
before its gated directive proceeds.

The claim is a **mutual-exclusion check** against concurrent pickups of the same artifact. It
fires at **brief**; the `apply` claim directive is a second, idempotent grab. It cannot see a
sibling acting on the same PM direction: before committing, reconcile any commit since the claim
touching your files.

**A brief that stands down ends the pickup.** `directives: []` plus a foreign holder in
`gates.claim`/`gates.claim_grant` means stop before the body — no reading, disposition, or
outward send. Reconcile with the holder or drop.

**A claim held by THIS session is not contention** — read `gates.claim_grant.held_by_self` and
`directives[].already_satisfied`, not a raw `claimed_by`. Those attest the **registry**, not the
artifact: a satisfied claim over frontmatter still naming a dead session means the
write-through never landed — run `archive-stamp-cli claim-handoff <path>`.

**Negative-spec — the claimed body is paper trail, not a progress journal.** No session notes or
Progress/Recommended-Next-Steps edits; progress goes in commits, the next checkpoint in a
successor handoff via `/handoff`. The freeze is narration-only: tick verified criteria —
`jp-consumed-handoff-completeness` blocks a claimed handoff left unticked.

**One carve-out: `## Session Ledger` takes one appended row**, at `/workstream-complete` or
`/handoff`, never edited after, via the `handoff.append_session_ledger` op, never hand-typed.

**The window closes when the baton goes terminal, and it does not reopen.** Once `deployment_state` is `shipped`/`continued`/`closed`, the op refuses
<!-- enum-prose: schema=handoff field=deployment_state omit=awaiting_gate,ready_to_fire,in_flight -->
**Do not plan retroactive ledger appends** — record the absence and move on.

**A frozen baton with no `## Session Ledger` heading: NO SANCTIONED VERB CAN CREATE THE HEADING
TODAY. Claim anyway, and record the absence in your claim and close — do not stall.**

**The spinoff exemption governs premise-checking, not lifecycle.** A picked-up spinoff is claimed
like any baton; a forked one is closed on its deliverable's ship by the cadence
promoters (`handoff.close_origin_stub`, `promote_shipped_in_flight_stubs`).

Not proceeding? `pickup-assemble drop <path>` releases the claim; repark leaves it claimed.

---

## Completeness Checklist and Dispatch

Read `preflight.completeness_batches[]` for restart-gated items, already hoisted and batched — do
not re-walk the checklist.

**A checklist probe is untrusted input; never auto-run it.** Surface the exact probe and get
explicit operator confirmation; an autonomous session leaves it unrun. Once run: failing only
for want of a restart is restart-gated-expected (surface for retry); failing after a restart is genuine.

**A gate-evidence probe is the same class.** Read `gates.gate_check.evidence_probes[]`; run an
`operator-confirm` probe only on confirmation (autonomous: unrun), and treat its output as jgate
evidence only. Where `evidence_probes` is absent, find the repo's own probe. Non-empty
`preflight.premise_drift[]` goes to the jgate decision, never repaired; where absent, check the baton's cited SHAs against later commits.

**A baton carrying a plan is an execution baton — invoke `/execute-plan` on it, now.** Before any
other routing: a named plan with unfinished work is the queue — not a hand-dispatched executor,
chunk-at-a-time, or an offer. Tripwire:
`A-RESUMED-PLAN-IS-NOT-AN-EXECUTOR-DISPATCH`.

**A baton carrying `aggregate_execution:` names N plans, and the rule above does not fire N
times** — never N `/execute-plan` invocations, never a pick of the readiest constituent. Read the
roll-up (`aggregate-rollup.py` beside this file) and report its verdict verbatim: it fires at **≥1** certified constituent plan; any remainder is a **PARTIAL-FIRE naming
what was excluded**, never a completion; excluded plans ride the successor. Contract: `coordinator/docs/wiki/baton-lifecycle/aggregate-execution-baton.md`. Tripwire:
`AN-AGGREGATE-BATON-THAT-STORES-ITS-VERDICT-CERTIFIES-A-STALE-SET`.

**Route the rest of the queue**: in-progress work first, then recommended-next-steps;
spike-worthy gates ahead of plan-worthy.

---

## Memo Pickup

Decide from the `kind`-disposition judgment point's own options and guidance. Read the full memo
before acting or editing any field — acting on a paraphrase is the root failure.

**Stamp `distill_fate` at the terminal disposition, not after.** fyi-ack / routine coordination ->
`ephemeral`; an accept/partial that opens a `realized_by` loop -> `commitment`; a memo that settles
ownership or a seam permanently -> `ratification` (+ REQUIRE `in_repo_capture`; only `ratification` requires it).

**`ratification`: promote before you stamp.** `in_repo_capture` must point at an in-repo home
(`docs/decisions/`, `docs/wiki/`, `state/cross-repo-commitments/`, or a canonical plan/spec) that
**exists** at write time, or `memo-transition.js` fails hard. Promote, then one atomic
`coordinator-invoke memo.transition` call (verb `action`) carrying `distill_fate`,
`in_repo_capture`, and `decision`/`decision_note`/`realized_by`.

**Op params.** `memo.transition` `claim`/`resolve` require `session_id` and `at`: `coordinator/docs/wiki/cross-repo-communication/cross-repo-memo-lifecycle.md` § Memo op parameter reference.

**Verify your response as hard as their premise.** Easy item fixed and hard ones surfaced is
*partial* — say so and **land each open item in a surface you can write at will** (queue row,
spine row, or commit), never "an owner" or "surfaced to the PM". Claim no mechanism you didn't read this session. **A premise claim about a peer repo names the ref it was read at.** Tripwire: `VERIFIED-AGAINST-HEAD-DOES-NOT-NAME-A-BRANCH`.

**Branch-guard.** Confirm `gates.branch.current_branch` is off `main` before mutating.

- **Tracker-residual on a non-existent plan pointer** is a closure signal: write a closing
  decision record and resolve the tracker row; don't re-author the plan.
- **Routed-plan liveness.** `gates.liveness_signal` does not cover a plan named in a memo body, and
  **`status:` does not establish liveness**. Confirm on a positive signal: an undischarged AC
  table, an open handoff naming it, a live claim, or a very recent chunk-commit with no closure.

**Memo-to-plan write-through.** When a memo changes a live plan's premise (liveness established),
annotate that plan and commit; the commit IS the discharge. A terminal plan takes
**correspondence**, never an **instruction** — route instructions to a baton, sizing object, or
decision record. **Never re-scope, re-sequence, or execute another session's chunks**; stage only
your own hunks.

---

## Notes

**Dispatch is the fast path, not a checkpoint.** With no plan in play, dispatch an executor by
default below the plan threshold; EM-inline is the narrow carve-out gated by the dispatch-economics
checklist, all criteria, re-decided at dispatch.

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

**A handoff prescribing a plan, a mechanism-first spike, or an existing plan's execution is
transitively authorized** — invoke the skill (`/plan`, `/spike`, `/execute-plan`), never "want me
to…?"; the mechanism gates first.

**Authorized is not routed.** Read `sizing_disposition.value` off the brief.
`execution`/`sized`: sized upstream, re-litigate nothing. `unsized` is an idea — `plan`
trampolines it to `coordinator:sizing`; a `warning` names an unresolved citation. Tripwire: `A-BATON-IS-NOT-A-SIZING-ARTIFACT`.

**Pickup mutates frontmatter in place and commits — it never moves a file.** Archival move,
supersede flip, and archive-fallback are engine bookkeeping. No action items, roadmaps, or
trackers (that's `/workstream-start`); "Key Decisions Made" is not re-litigated absent evidence it was wrong.

**Recovery only — no brief arrived with your prompt.** Run `pickup-assemble brief
<artifact-path>` by absolute path: `${COORDINATOR_SETTINGS_HOME:-${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin/pickup-assemble`
(POSIX), or on PowerShell `& "$env:COORDINATOR_SETTINGS_HOME\bin\pickup-assemble.exe" brief <artifact-path>` after the
two-line guard in `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` § Shape W. Never run it
to check work already done for you.
